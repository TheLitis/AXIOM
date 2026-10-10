"""Validate constructed native fixture specifications and supplied observations.

A level string describes intended test geometry. Only supplied native mode and
input observations can satisfy a fixture requirement; this module runs no game.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .ingest import parse_level_string
from .native import MAX_PLANNED_INPUTS, MAX_TRACE_RECORDS, canonical_sha256, load_native_capture
from .validation import finite, mapping, read_json, sha256, string

MODES = frozenset({"cube", "ship", "ball", "ufo", "wave", "robot", "spider", "swing"})
MAX_CASES = 64
MAX_RUNS = 16
MAX_LEVEL_BYTES = 64 * 1024
_EVENT_FIELDS = frozenset({"command_index", "player", "button", "pressed"})
_MECHANICS_FIELDS = ("gravity_inverted", "vehicle_size", "player_speed")
_CONTACT_FIELDS = ("is_on_ground", "is_on_slope")
MAX_WITNESSES = 32
_EFFECT_EVENTS = frozenset(
    {
        "PlayerObject::collidedWithObject",
        "PlayerObject::updateCollide",
        "PlayerObject::collidedWithSlopeInternal",
        "PlayLayer::destroyPlayer",
        "GJBaseGameLayer::triggerMoveCommand",
        "GJBaseGameLayer::toggleGroupTriggered",
        "GJBaseGameLayer::toggleGroup",
        "GJBaseGameLayer::spawnGroup",
    }
)


def _fields(value: object, name: str, required: set[str] | frozenset[str]) -> dict:
    data = mapping(value, name)
    if data.keys() != required:
        raise ValueError(f"{name} requires exactly: {', '.join(sorted(required))}")
    return data


def _id(value: object, name: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", value):
        raise ValueError(f"{name} must be a lowercase fixture identifier of at most 64 characters")
    return value


def _int(value: object, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    return value


def _array(value: object, name: str, minimum: int, maximum: int) -> list:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{name} must contain {minimum} to {maximum} records")
    return value


def _inputs(value: object, name: str) -> list[dict]:
    events = _array(value, name, 0, MAX_PLANNED_INPUTS)
    previous = 0
    held: set[tuple[int, int]] = set()
    for index, item in enumerate(events):
        event = _fields(item, f"{name}[{index}]", _EVENT_FIELDS)
        command = _int(event["command_index"], "command_index", 1, MAX_TRACE_RECORDS - 1)
        if command < previous:
            raise ValueError("Fixture inputs must be ordered by command index")
        previous = command
        channel = (_int(event["player"], "player", 1, 2), _int(event["button"], "button", 1, 3))
        if type(event["pressed"]) is not bool:
            raise ValueError("Fixture input pressed must be a JSON boolean")
        if event["pressed"] == (channel in held):
            raise ValueError("Fixture inputs must change the held state of their channel")
        if event["pressed"]:
            held.add(channel)
        else:
            held.remove(channel)
    return events


def _mode_sequences(value: object, name: str) -> dict:
    sequences = _fields(value, name, {"player1", "player2"})
    for player, sequence in sequences.items():
        if player == "player2" and sequence is None:
            continue  # Null declares no player-2 requirement, not a missing pointer.
        _array(sequence, f"{name}.{player}", 1, 64)
        if any(not isinstance(mode, str) or mode not in MODES for mode in sequence):
            raise ValueError("Required mode sequences contain an unsupported mode")
        if any(left == right for left, right in zip(sequence, sequence[1:])):
            raise ValueError("Required mode sequences must omit adjacent duplicate modes")
    return sequences


def _raw_equal(left: object, right: object) -> bool:
    # Python equates True with 1; a native boolean must not match a numeric field.
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    return left == right


def _raw_sequence(value: object, name: str, boolean: bool) -> list | None:
    if value is None:
        return None
    sequence = _array(value, name, 1, 64)
    for item in sequence:
        if boolean:
            if type(item) is not bool:
                raise ValueError(f"{name} must contain JSON booleans")
        else:
            finite(item, name)  # Raw finite values; no invented physical range.
    if any(_raw_equal(left, right) for left, right in zip(sequence, sequence[1:])):
        raise ValueError(f"{name} must omit adjacent duplicate values")
    return sequence


def _mechanics_sequences(value: object, modes: dict) -> dict:
    sequences = _fields(value, "required_mechanics_sequences", {"player1", "player2", "dual_active"})
    constraints = 0
    for player in ("player1", "player2"):
        declaration = sequences[player]
        if player == "player2" and declaration is None:
            continue
        fields = _fields(declaration, f"required_mechanics_sequences.{player}", set(_MECHANICS_FIELDS))
        count = 0
        for field, sequence in fields.items():
            _raw_sequence(
                sequence, f"required_mechanics_sequences.{player}.{field}", field == "gravity_inverted"
            )
            count += sequence is not None
        if player == "player2" and not count and modes["player2"] is None:
            raise ValueError("An all-null player2 mechanics scope requires an explicit player2 mode sequence")
        constraints += count
    dual = _raw_sequence(sequences["dual_active"], "required_mechanics_sequences.dual_active", True)
    constraints += dual is not None
    if not constraints:
        raise ValueError("Fixture matrix v2 requires at least one non-null mechanics sequence per run")
    return sequences


def _response_mechanics(value: object, player: int) -> dict:
    predicates = _fields(value, "response_check.required_mechanics", set(_MECHANICS_FIELDS) | {"dual_active"})
    for field, expected in predicates.items():
        if expected is None:
            continue
        if field in {"gravity_inverted", "dual_active"}:
            if type(expected) is not bool:
                raise ValueError(f"response_check.required_mechanics.{field} must be a JSON boolean or null")
        else:
            finite(expected, f"response_check.required_mechanics.{field}")
    if all(value is None for value in predicates.values()):
        raise ValueError("Fixture matrix v2 response checks require at least one mechanics predicate")
    if player == 2 and predicates["dual_active"] is False:
        raise ValueError("Player2 response cannot require dual_active=false")
    return predicates


def _window(value: object, name: str) -> dict:
    window = _fields(value, name, {"first", "last"})
    first = _int(window["first"], f"{name}.first", 0, MAX_TRACE_RECORDS - 1)
    _int(window["last"], f"{name}.last", first, MAX_TRACE_RECORDS - 1)
    return window


def _state_witnesses(value: object) -> list:
    rows = _array(value, "required_state_witnesses", 0, MAX_WITNESSES)
    ids = set()
    for row in rows:
        _fields(row, "state witness", {"id", "player", "mode", "command_window", "min_samples", "predicates"})
        identifier = _id(row["id"], "state witness.id")
        if identifier in ids:
            raise ValueError("Duplicate state witness id")
        ids.add(identifier)
        actor = _int(row["player"], "state witness.player", 1, 2)
        if not isinstance(row["mode"], str) or row["mode"] not in MODES:
            raise ValueError("State witness mode must name a supported mode")
        window = _window(row["command_window"], "state witness.command_window")
        _int(row["min_samples"], "state witness.min_samples", 1, window["last"] - window["first"] + 1)
        predicates = _fields(
            row["predicates"],
            "state witness.predicates",
            {*_CONTACT_FIELDS, *_MECHANICS_FIELDS, "dual_active", "y"},
        )
        for field, expected in predicates.items():
            if expected is None:
                continue
            if field in {*_CONTACT_FIELDS, "gravity_inverted", "dual_active"}:
                if type(expected) is not bool:
                    raise ValueError(f"State witness {field} must be a JSON boolean or null")
            elif field == "y":
                limits = _fields(expected, "state witness.y", {"minimum", "maximum"})
                low = finite(limits["minimum"], "state witness.y.minimum")
                if finite(limits["maximum"], "state witness.y.maximum") < low:
                    raise ValueError("State witness y maximum must be at least its minimum")
            else:
                finite(expected, f"state witness.{field}")
        if all(predicates[field] is None for field in _CONTACT_FIELDS):
            raise ValueError("A state witness requires a non-null contact flag predicate")
        if actor == 2 and predicates["dual_active"] is False:
            raise ValueError("Player2 state witness cannot require dual_active=false")
    return rows


def _effect_change(value: object, name: str, *, target: bool) -> dict | None:
    if value is None:
        return None
    change = _fields(value, name, {"field", "before", "after"} | ({"group_id"} if target else set()))
    boolean_fields = {"is_group_disabled", "is_disabled"} if target else {*_CONTACT_FIELDS, "is_dead"}
    fields = boolean_fields | ({"x", "y"} if target else {"y", "y_velocity"})
    field = change["field"]
    if not isinstance(field, str) or field not in fields:
        raise ValueError(f"{name}.field must name a supported raw observation")
    if target:
        _int(change["group_id"], f"{name}.group_id", 1, 9999)
    for side in ("before", "after"):
        if field in boolean_fields:
            if type(change[side]) is not bool:
                raise ValueError(f"{name}.{side} must be a JSON boolean")
        else:
            finite(change[side], f"{name}.{side}")
    if _raw_equal(change["before"], change["after"]):
        raise ValueError(f"{name} must require a changed raw value")
    return change


def _effect_checks(value: object, watches: list[int]) -> list:
    rows = _array(value, "required_effect_checks", 0, MAX_WITNESSES)
    ids = set()
    for row in rows:
        _fields(
            row,
            "effect check",
            {
                "id",
                "event",
                "player",
                "object_group_id",
                "command_window",
                "min_events",
                "native_return",
                "player_change",
                "target_change",
            },
        )
        identifier = _id(row["id"], "effect check.id")
        if identifier in ids:
            raise ValueError("Duplicate effect check id")
        ids.add(identifier)
        event = row["event"]
        if not isinstance(event, str) or event not in _EFFECT_EVENTS:
            raise ValueError("Effect checks require a supported applied mechanic hook")
        _window(row["command_window"], "effect check.command_window")
        _int(row["min_events"], "effect check.min_events", 1, 4096)
        actor = row["player"]
        if actor is not None:
            _int(actor, "effect check.player", 1, 2)
        group = row["object_group_id"]
        if group is not None:
            _int(group, "effect check.object_group_id", 1, 9999)
            if group not in watches:
                raise ValueError("Effect object_group_id must be a declared watch group")
        player_change = _effect_change(row["player_change"], "effect check.player_change", target=False)
        target_change = _effect_change(row["target_change"], "effect check.target_change", target=True)
        if target_change is not None and target_change["group_id"] not in watches:
            raise ValueError("Effect target_change group must be a declared watch group")
        actor_event = event.startswith("PlayerObject::") or event == "PlayLayer::destroyPlayer"
        if actor_event:
            if actor is None or group is None or player_change is None or target_change is not None:
                raise ValueError(
                    "Collision/death effect checks require an actor, watched object and player change"
                )
            if event == "PlayLayer::destroyPlayer" and (
                player_change["field"] != "is_dead" or player_change["after"] is not True
            ):
                raise ValueError("Death effect checks require a changed is_dead=true observation")
        elif actor is not None or group is not None or player_change is not None or target_change is None:
            raise ValueError(
                "Group effect checks require a watched target change and no actor/object selector"
            )
        if event == "PlayerObject::collidedWithObject":
            if row["native_return"] is not True:
                raise ValueError("Collision effect checks require native_return=true")
        elif row["native_return"] is not None:
            raise ValueError("Void effect checks require native_return=null")
    return rows


def validate_fixture_matrix(data: object) -> dict:
    """Validate a bounded, versioned catalogue; native verification stays separate."""
    matrix = _fields(data, "fixture matrix", {"schema_version", "kind", "provenance", "clock", "cases"})
    if type(matrix["schema_version"]) is not int or matrix["schema_version"] not in {1, 2, 3}:
        raise ValueError("Expected fixture matrix schema_version 1, 2 or 3")
    if matrix["kind"] != "native_fixture_matrix" or matrix["clock"] != "processCommands_call_index":
        raise ValueError("Expected kind native_fixture_matrix and processCommands_call_index clock")
    provenance = _fields(matrix["provenance"], "provenance", {"origin", "native_verification"})
    if provenance != {"origin": "generated_synthetic", "native_verification": "not_recorded"}:
        raise ValueError(
            "Catalogue provenance must declare generated synthetic data, not native verification"
        )
    cases = _array(matrix["cases"], "cases", 1, MAX_CASES)
    case_ids = set()
    for case in cases:
        _fields(
            case,
            "case",
            {"id", "label", "level_string", "level_sha256", "mechanics_intent", "runs", "response_checks"}
            | ({"watch_groups"} if matrix["schema_version"] == 3 else set()),
        )
        case_id = _id(case["id"], "case.id")
        if case_id in case_ids:
            raise ValueError("Duplicate fixture case id")
        case_ids.add(case_id)
        if matrix["schema_version"] == 3:
            watches = _array(case["watch_groups"], "case.watch_groups", 0, 8)
            for group in watches:
                _int(group, "case.watch_groups item", 1, 9999)
            if len(set(watches)) != len(watches):
                raise ValueError("Duplicate case watch group")
        string(case["label"], "case.label")
        level = case["level_string"]
        if not isinstance(level, str):
            raise ValueError("case.level_string must be a string")
        try:
            raw = level.encode("utf-8")
        except UnicodeError as error:
            raise ValueError("case.level_string must be valid UTF-8") from error
        if not raw or len(raw) > MAX_LEVEL_BYTES or not level.endswith(";") or level != level.strip():
            raise ValueError(
                "case.level_string must be a trimmed, semicolon-terminated string of at most 64 KiB"
            )
        parse_level_string(level, max_bytes=MAX_LEVEL_BYTES, max_objects=256)
        if hashlib.sha256(raw).hexdigest() != sha256(case["level_sha256"], "case.level_sha256"):
            raise ValueError("Fixture level_sha256 does not match the exact UTF-8 level_string")
        intents = _array(case["mechanics_intent"], "mechanics_intent", 1, 16)
        for intent in intents:
            _id(intent, "mechanics_intent item")
        if len(set(intents)) != len(intents):
            raise ValueError("Duplicate mechanics intent")
        runs = _array(case["runs"], "runs", 2, MAX_RUNS)
        run_map = {}
        for run in runs:
            _fields(
                run,
                "run",
                {"id", "role", "input_mode", "inputs", "expected_outcome", "required_mode_sequences"}
                | ({"required_mechanics_sequences"} if matrix["schema_version"] >= 2 else set())
                | (
                    {"required_state_witnesses", "required_effect_checks"}
                    if matrix["schema_version"] == 3
                    else set()
                ),
            )
            run_id = _id(run["id"], "run.id")
            if run_id in run_map:
                raise ValueError("Duplicate run id")
            run_map[run_id] = run
            if not isinstance(run["role"], str) or run["role"] not in {
                "baseline",
                "replay",
                "response_control",
            }:
                raise ValueError("Invalid fixture run role")
            if not isinstance(run["input_mode"], str) or run["input_mode"] not in {"observation", "replay"}:
                raise ValueError("Invalid fixture input_mode")
            inputs = _inputs(run["inputs"], "run.inputs")
            if (run["role"] == "baseline") != (run["input_mode"] == "observation"):
                raise ValueError("Only baseline runs use observation input mode")
            if run["input_mode"] == "observation" and inputs:
                raise ValueError("An observation baseline cannot declare scheduled replay inputs")
            if not isinstance(run["expected_outcome"], str) or run["expected_outcome"] not in {
                "completed",
                "died",
                "any_terminal",
            }:
                raise ValueError("Invalid fixture expected_outcome")
            _mode_sequences(run["required_mode_sequences"], "required_mode_sequences")
            if matrix["schema_version"] >= 2:
                _mechanics_sequences(run["required_mechanics_sequences"], run["required_mode_sequences"])
            if matrix["schema_version"] == 3:
                _state_witnesses(run["required_state_witnesses"])
                _effect_checks(run["required_effect_checks"], watches)
                if not run["required_state_witnesses"] and not run["required_effect_checks"]:
                    raise ValueError(
                        "Matrix3 runs require at least one state witness or applied effect check"
                    )
        if sum(run["role"] == "baseline" for run in runs) != 1:
            raise ValueError("Each fixture requires exactly one observation baseline")
        if sum(run["role"] == "replay" for run in runs) != 1:
            raise ValueError("Each fixture requires exactly one repeated replay run")
        checks = _array(case["response_checks"], "response_checks", 0, MAX_RUNS)
        check_ids = set()
        for check in checks:
            _fields(
                check,
                "response check",
                {"id", "reference_run", "changed_run", "player", "fields", "mode"}
                | ({"required_mechanics"} if matrix["schema_version"] >= 2 else set()),
            )
            check_id = _id(check["id"], "response_check.id")
            if check_id in check_ids:
                raise ValueError("Duplicate response check id")
            check_ids.add(check_id)
            pair = []
            for key in ("reference_run", "changed_run"):
                run_id = _id(check[key], f"response_check.{key}")
                if run_id not in run_map or run_map[run_id]["input_mode"] != "replay":
                    raise ValueError("Response checks must name two owned replay runs in the fixture")
                pair.append(run_map[run_id])
            player = _int(check["player"], "response_check.player", 1, 2)
            if matrix["schema_version"] >= 2:
                _response_mechanics(check["required_mechanics"], player)
            if not isinstance(check["mode"], str) or check["mode"] not in MODES:
                raise ValueError("Response check mode must name a supported observed mode")
            if pair[0]["inputs"] == pair[1]["inputs"]:
                raise ValueError("A response check must compare different input plans")
            if not any(event["player"] == player for run in pair for event in run["inputs"]):
                raise ValueError("Response check player must have a planned input in a compared run")
            fields = _array(check["fields"], "response_check.fields", 1, 2)
            if any(not isinstance(field, str) or field not in {"y", "y_velocity"} for field in fields) or len(
                set(fields)
            ) != len(fields):
                raise ValueError("Response fields must be unique y and/or y_velocity observations")
    return matrix


def load_fixture_matrix(path: str | Path) -> dict:
    return validate_fixture_matrix(read_json(path)[0])


def get_fixture_case(matrix: dict, case_id: str) -> dict:
    for case in matrix["cases"]:
        if case["id"] == case_id:
            return case
    raise ValueError(f"Unknown fixture case: {case_id}")


def get_fixture_run(matrix: dict, case_id: str, run_id: str) -> dict:
    """Return a JSON-serializable runner specification with exact level bytes."""
    case = get_fixture_case(matrix, case_id)
    for run in case["runs"]:
        if run["id"] == run_id:
            return {
                "case_id": case_id,
                "level_string": case["level_string"],
                "level_sha256": case["level_sha256"],
                **({"watch_groups": case["watch_groups"]} if matrix["schema_version"] == 3 else {}),
                **run,
            }
    raise ValueError(f"Unknown fixture run: {case_id}/{run_id}")


def _pre_end_rows(capture: dict) -> list[dict]:
    if capture["schema_version"] < 2:
        return []
    return [
        row
        for row in capture["attempt"]["trace"]
        if not row["phase"]["level_end_animation_started"] and not row["phase"]["has_completed_level"]
    ]


def _append_change(sequence: list, value: object) -> None:
    if not sequence or not _raw_equal(sequence[-1], value):
        sequence.append(value)


def _observed_mode_sequences(capture: dict, *, active_player2: bool = False) -> dict[str, list[str | None]]:
    result = {"player1": [], "player2": []}
    for row in _pre_end_rows(capture):
        state = row["state"]
        for player in result:
            if player == "player2" and active_player2:
                if capture["schema_version"] < 3 or not state["dual_active"]:
                    continue
            mode = None if state[player] is None else state[player]["mode"]
            _append_change(result[player], mode)
    return result


def _observed_mechanics_sequences(capture: dict) -> tuple[dict, dict]:
    observed = {
        "player1": {field: None for field in _MECHANICS_FIELDS},
        "player2": {field: None for field in _MECHANICS_FIELDS},
        "dual_active": None,
    }
    availability = {
        "native_schema3_fields": capture["schema_version"] >= 3,
        "player1": {field: False for field in _MECHANICS_FIELDS},
        "player2": {field: False for field in _MECHANICS_FIELDS},
        "dual_active": False,
        "player2_active_samples": 0,
    }
    if capture["schema_version"] < 3:
        return observed, availability
    observed["dual_active"] = []
    for player in ("player1", "player2"):
        observed[player] = {field: [] for field in _MECHANICS_FIELDS}
    rows = _pre_end_rows(capture)
    for row in rows:
        state = row["state"]
        _append_change(observed["dual_active"], state["dual_active"])
        for player in ("player1", "player2"):
            if player == "player2" and not state["dual_active"]:
                continue
            if player == "player2":
                availability["player2_active_samples"] += 1
            for field in _MECHANICS_FIELDS:
                value = None if state[player] is None else state[player][field]
                _append_change(observed[player][field], value)
    availability["dual_active"] = bool(rows)
    for player in ("player1", "player2"):
        availability[player] = {
            field: bool(observed[player][field]) and None not in observed[player][field]
            for field in _MECHANICS_FIELDS
        }
    return observed, availability


def _sequence_matches(observed: list | None, required: list | None) -> bool:
    if required is None:
        return True
    return (
        observed is not None
        and len(observed) == len(required)
        and all(_raw_equal(left, right) for left, right in zip(observed, required))
    )


def _mechanics_checks(required: dict, observed: dict, availability: dict, modes: dict) -> dict:
    checks = {}
    for player in ("player1", "player2"):
        declaration = required[player]
        checks[player] = (
            None
            if declaration is None
            else {
                field: _sequence_matches(observed[player][field], sequence)
                and (sequence is None or availability[player][field])
                for field, sequence in declaration.items()
            }
        )
    checks["dual_active"] = _sequence_matches(observed["dual_active"], required["dual_active"])
    claims_player2 = required["player2"] is not None or modes["player2"] is not None
    checks["player2_active_samples_observed"] = not claims_player2 or (
        availability["player2_active_samples"] > 0 and all(availability["player2"].values())
    )
    return checks


def _witness_observations(capture: dict, declarations: list) -> list[dict]:
    available = capture["schema_version"] == 4
    results = []
    rows = _pre_end_rows(capture) if available else []
    for declaration in declarations:
        actor = f"player{declaration['player']}"
        matches = []
        first_sample = None
        window = declaration["command_window"]
        for row in rows:
            command, state = row["command_index"], row["state"]
            player = state[actor]
            if not window["first"] <= command <= window["last"] or player is None:
                continue
            if declaration["player"] == 2 and not state["dual_active"]:
                continue
            if player["mode"] != declaration["mode"]:
                continue
            actual = {
                **{key: player[key] for key in (*_CONTACT_FIELDS, *_MECHANICS_FIELDS, "y")},
                "dual_active": state["dual_active"],
            }
            matched = True
            for field, expected in declaration["predicates"].items():
                if expected is None:
                    continue
                if field == "y":
                    matched &= expected["minimum"] <= actual[field] <= expected["maximum"]
                else:
                    matched &= _raw_equal(actual[field], expected)
            if matched:
                matches.append(command)
                if first_sample is None:
                    first_sample = {
                        "command_index": command,
                        "update_sequence": row["update_sequence"],
                        "scheduler_sequence": row["scheduler_sequence"],
                        "mode": player["mode"],
                        "observed_predicates": actual,
                    }
        results.append(
            {
                "id": declaration["id"],
                "available": available,
                "matched": available and len(matches) >= declaration["min_samples"],
                "required_min_samples": declaration["min_samples"],
                "matching_sample_count": len(matches),
                "matching_command_indices": matches,
                "first_matching_sample": first_sample,
            }
        )
    return results


def _event_pre_ending(event: dict) -> bool:
    return all(
        not event[key][field]
        for key in ("phase_before", "phase_after")
        for field in ("level_end_animation_started", "has_completed_level")
    )


def _watch_value(rows: list, group: int, field: str) -> object:
    return next((row[field] for row in rows if row["group_id"] == group), None)


def _effect_observations(capture: dict, declarations: list) -> list[dict]:
    available = capture["schema_version"] == 4
    events = capture["attempt"]["mechanic_events"] if available else []
    trace = _pre_end_rows(capture) if available else []
    results = []
    for declaration in declarations:
        witnesses, matched_sequences = [], []
        window = declaration["command_window"]
        for event in events:
            command = event["command_index"]
            if (
                event["event"] != declaration["event"]
                or event["player"] != declaration["player"]
                or not window["first"] <= command <= window["last"]
                or not _event_pre_ending(event)
                or not _raw_equal(event["native_return"], declaration["native_return"])
            ):
                continue
            group = declaration["object_group_id"]
            if group is not None and (event["object"] is None or group not in event["object"]["group_ids"]):
                continue
            evidence = {
                "event_sequence": event["sequence"],
                "event": event["event"],
                "event_command_index": command,
                "in_command": event["in_command"],
                "update_sequence": event["update_sequence"],
                "scheduler_sequence": event["scheduler_sequence"],
                "arguments": event["arguments"],
                "object": event["object"],
                "native_return": event["native_return"],
            }
            change = declaration["player_change"]
            if change is not None:
                actor = f"player{declaration['player']}"
                before, after = event["state_before"], event["state_after"]
                if declaration["player"] == 2 and not (before["dual_active"] and after["dual_active"]):
                    continue
                if before[actor] is None or after[actor] is None:
                    continue
                field = change["field"]
                if not (
                    _raw_equal(before[actor][field], change["before"])
                    and _raw_equal(after[actor][field], change["after"])
                ):
                    continue
                evidence["player_transition"] = {
                    "source": "paired_native_callback",
                    "player": declaration["player"],
                    "field": field,
                    "before": before[actor][field],
                    "after": after[actor][field],
                    "mode_before": before[actor]["mode"],
                    "mode_after": after[actor]["mode"],
                    "dual_active_before": before["dual_active"],
                    "dual_active_after": after["dual_active"],
                }
            change = declaration["target_change"]
            if change is not None:
                field, group = change["field"], change["group_id"]
                argument = (
                    "target_group_id" if event["event"] == "GJBaseGameLayer::triggerMoveCommand" else "group"
                )
                if event["arguments"][argument] != group:
                    continue
                actual_before = _watch_value(event["watched_before"], group, field)
                if not _raw_equal(actual_before, change["before"]):
                    continue
                actual_after = _watch_value(event["watched_after"], group, field)
                transition = None
                if _raw_equal(actual_after, change["after"]):
                    transition = {
                        "source": "paired_native_callback",
                        "command_index": command,
                        "update_sequence": event["update_sequence"],
                        "scheduler_sequence": event["scheduler_sequence"],
                    }
                else:
                    for row in trace:
                        # A trace has no wall timestamp. A strictly later command
                        # is explicit command-order evidence; same-counter rows
                        # cannot establish that they followed the paired call.
                        if not command < row["command_index"] <= window["last"]:
                            continue
                        value = _watch_value(row["watched_objects"], group, field)
                        if _raw_equal(value, change["after"]):
                            actual_after = value
                            transition = {
                                "source": "later_pre_ending_command_sample",
                                "command_index": row["command_index"],
                                "update_sequence": row["update_sequence"],
                                "scheduler_sequence": row["scheduler_sequence"],
                            }
                            break
                if transition is None:
                    continue
                evidence["target_transition"] = {
                    **transition,
                    "group_id": group,
                    "field": field,
                    "before": actual_before,
                    "after": actual_after,
                    "chronology_scope": "paired_original_return_or_strictly_later_command_index",
                }
            matched_sequences.append(event["sequence"])
            if len(witnesses) < MAX_WITNESSES:
                witnesses.append(evidence)
        results.append(
            {
                "id": declaration["id"],
                "available": available,
                "matched": available and len(matched_sequences) >= declaration["min_events"],
                "required_min_events": declaration["min_events"],
                "matching_event_count": len(matched_sequences),
                "matching_event_sequences": matched_sequences,
                "witnesses": witnesses,
                "omitted_witness_count": len(matched_sequences) - len(witnesses),
            }
        )
    return results


def _evaluate_capture(matrix: dict, case_id: str, run_id: str, capture: dict) -> dict:
    run = get_fixture_run(matrix, case_id, run_id)
    attempt = capture["attempt"]
    source = "unknown" if run["input_mode"] == "observation" else "replay"
    mechanics_required = matrix["schema_version"] >= 2
    observed_modes = _observed_mode_sequences(capture, active_player2=mechanics_required)
    mode_checks = {
        player: required is None or observed_modes[player] == required
        for player, required in run["required_mode_sequences"].items()
    }
    missing_callbacks = []
    for planned in run["inputs"]:
        phase = "push" if planned["pressed"] else "release"
        if not any(
            all(event[key] == planned[key] for key in _EVENT_FIELDS)
            and event["phase"] == phase
            and event["native_return"] is True
            for event in attempt["inputs"]
        ):
            missing_callbacks.append({**planned, "required_phase": phase})
    checks = {
        "level_identity_matches": capture["challenge"]["level_sha256"] == run["level_sha256"],
        "full_start": attempt["start_kind"] == "level_start",
        "input_mode_matches": attempt["input_source"] == source,
        "planned_inputs_match": attempt["planned_inputs"] == run["inputs"],
        "complete_plan_executed": all(
            event["command_index"] <= attempt["terminal"]["command_index"] for event in run["inputs"]
        ),
        "native_callbacks_observed": not missing_callbacks,
        "native_phase_boundary_available": capture["schema_version"] >= 2,
        "terminal_outcome_matches": attempt["terminal"]["outcome"] in {"completed", "died"}
        if run["expected_outcome"] == "any_terminal"
        else attempt["terminal"]["outcome"] == run["expected_outcome"],
        "required_modes_observed": all(mode_checks.values()),
    }
    if capture["schema_version"] == 4:
        expected_driver = "none" if run["input_mode"] == "observation" else "owned-pre-command"
        checks["input_delivery_matches_fixture_role"] = attempt["input_delivery"]["driver"] == expected_driver
    result = {
        "schema_version": matrix["schema_version"],
        "kind": "native_fixture_inspection",
        "status": "fixture_observations_match" if all(checks.values()) else "fixture_observations_mismatch",
        "case_id": case_id,
        "run_id": run_id,
        "capture_document_sha256": canonical_sha256(capture),
        "capture_provenance": capture["provenance"],
        "checks": checks,
        "observed_mode_sequences": observed_modes,
        "mode_observation_scope": "before_native_end_animation"
        if capture["schema_version"] >= 2
        else "unavailable_schema1",
        "mode_checks": mode_checks,
        "missing_native_callbacks": missing_callbacks,
        "observed_input_records": len(attempt["inputs"]),
        "observed_terminal_outcome": attempt["terminal"]["outcome"],
        "exploratory_outcome": run["expected_outcome"] == "any_terminal",
        "limitations": [
            "Supplied capture observations do not authenticate native execution or establish complete engine state.",
            "Encoded mechanics intent and editor coordinates are not proof that a mechanic activated.",
            "Mode requirements check selected labels, not gravity, size, speed, collision geometry or dual activity.",
            "Mode coverage uses schema-2/3 pre-ending trace samples only; terminal and ending animation samples are excluded.",
            "No human difficulty, physical impossibility, continuous timing window or Axiom Rating is inferred.",
        ],
    }
    if mechanics_required:
        observed, availability = _observed_mechanics_sequences(capture)
        mechanic_checks = _mechanics_checks(
            run["required_mechanics_sequences"], observed, availability, run["required_mode_sequences"]
        )
        checks["native_mechanics_available"] = availability["native_schema3_fields"]
        checks["required_mechanics_observed"] = all(
            all(value.values()) if isinstance(value, dict) else value is None or value
            for value in mechanic_checks.values()
        )
        result["status"] = (
            "fixture_observations_match" if all(checks.values()) else "fixture_observations_mismatch"
        )
        result.update(
            observed_mechanics_sequences=observed,
            mechanics_availability=availability,
            mechanics_checks=mechanic_checks,
            mechanics_observation_scope="schema3_pre_ending_player2_dual_active_only",
        )
        result["limitations"] += [
            "Mechanics sequences use selected raw schema-3 fields, not inferred portal effects or physical calibration.",
            "Player-2 mode/mechanics samples require recorded dual_active=true; pointer existence proves no dual activity.",
        ]
    if matrix["schema_version"] == 3:
        witnesses = _witness_observations(capture, run["required_state_witnesses"])
        effects = _effect_observations(capture, run["required_effect_checks"])
        checks.update(
            native_contact_effect_fields_available=capture["schema_version"] == 4,
            watch_groups_match=capture["schema_version"] == 4
            and [watch["group_id"] for watch in capture["object_watches"]] == run["watch_groups"],
            required_state_witnesses_observed=all(row["matched"] for row in witnesses),
            required_effect_checks_observed=all(row["matched"] for row in effects),
        )
        result.update(
            state_witness_checks=witnesses,
            effect_checks=effects,
            declared_watch_groups=run["watch_groups"],
            observed_object_watches=capture["object_watches"] if capture["schema_version"] == 4 else None,
            contact_effect_observation_scope="schema4_joint_pre_ending_fields_and_paired_runtime_events",
            status="fixture_observations_match" if all(checks.values()) else "fixture_observations_mismatch",
        )
        result["limitations"] += [
            "Ground/slope witnesses are selected raw flags jointly sampled at declared commands; they do not reconstruct collision geometry.",
            "Applied effect checks require actual callback receipts and changed selected values; object IDs or dispatch callbacks alone satisfy no effect check.",
            "Later target transitions use strictly later command indices, not inferred wall-clock ordering or isolated causal attribution.",
        ]
    return result


def inspect_fixture_capture(
    matrix_path: str | Path, case_id: str, run_id: str, capture_path: str | Path
) -> dict:
    return _evaluate_capture(
        load_fixture_matrix(matrix_path), case_id, run_id, load_native_capture(capture_path)
    )


def compare_fixture_response(
    matrix_path: str | Path, case_id: str, check_id: str, reference_path: str | Path, changed_path: str | Path
) -> dict:
    """Compare two supplied owned replay plans at shared command-clock rows."""
    matrix = load_fixture_matrix(matrix_path)
    case = get_fixture_case(matrix, case_id)
    check = next((item for item in case["response_checks"] if item["id"] == check_id), None)
    if check is None:
        raise ValueError(f"Unknown fixture response check: {check_id}")
    reference, changed = load_native_capture(reference_path), load_native_capture(changed_path)
    inspections = [
        _evaluate_capture(matrix, case_id, check[key], capture)
        for key, capture in (("reference_run", reference), ("changed_run", changed))
    ]
    same_environment = reference["environment_sha256"] == changed["environment_sha256"]
    same_collector = reference["collector"] == changed["collector"]
    same_initial_state = reference["attempt"]["trace"][0]["state"] == changed["attempt"]["trace"][0]["state"]
    player = f"player{check['player']}"
    left_plan, right_plan = reference["attempt"]["planned_inputs"], changed["attempt"]["planned_inputs"]
    common_prefix = 0
    for left, right in zip(left_plan, right_plan):
        if left != right:
            break
        common_prefix += 1
    remaining = left_plan[common_prefix:] + right_plan[common_prefix:]
    first_changed_input = min((event["command_index"] for event in remaining), default=None)
    first_difference = None
    shared_rows = 0
    shared_mode_rows = 0
    predicates_required = matrix["schema_version"] >= 2
    mechanics_available = reference["schema_version"] >= 3 and changed["schema_version"] >= 3
    selected_prefix_matches = True
    for left, right in zip(reference["attempt"]["trace"], changed["attempt"]["trace"]):
        lhs, rhs = left["state"][player], right["state"][player]
        if first_changed_input is not None and left["command_index"] < first_changed_input:
            if lhs != rhs or (
                mechanics_available and left["state"]["dual_active"] != right["state"]["dual_active"]
            ):
                selected_prefix_matches = False
        if lhs is None or rhs is None:
            continue
        if reference["schema_version"] < 2 or changed["schema_version"] < 2:
            continue
        if any(
            row["phase"]["level_end_animation_started"] or row["phase"]["has_completed_level"]
            for row in (left, right)
        ):
            continue
        if lhs["mode"] != check["mode"] or rhs["mode"] != check["mode"]:
            continue
        if first_changed_input is None or left["command_index"] < first_changed_input:
            continue
        shared_mode_rows += 1
        if predicates_required:
            if not mechanics_available:
                continue
            if check["player"] == 2 and not (left["state"]["dual_active"] and right["state"]["dual_active"]):
                continue
            actual_mechanics = {
                label: {
                    **{field: actor[field] for field in _MECHANICS_FIELDS},
                    "dual_active": row["state"]["dual_active"],
                }
                for label, actor, row in (("reference", lhs, left), ("changed", rhs, right))
            }
            if any(
                expected is not None and not _raw_equal(actual[field], expected)
                for actual in actual_mechanics.values()
                for field, expected in check["required_mechanics"].items()
            ):
                continue
        shared_rows += 1
        differences = {
            field: {"reference": lhs[field], "changed": rhs[field]}
            for field in check["fields"]
            if lhs[field] != rhs[field]
        }
        if differences and first_difference is None:
            first_difference = {"command_index": left["command_index"], "fields": differences}
            if predicates_required:
                first_difference["observed_mechanics"] = actual_mechanics
    checks = {
        "reference_requirements_match": inspections[0]["status"] == "fixture_observations_match",
        "changed_requirements_match": inspections[1]["status"] == "fixture_observations_match",
        "same_environment": same_environment,
        "same_collector": same_collector,
        "same_selected_initial_state": same_initial_state,
        "same_selected_prefix_before_changed_input": selected_prefix_matches,
        "input_plans_differ": first_changed_input is not None,
        "selected_response_differs": first_difference is not None,
    }
    if reference["schema_version"] == 4 or changed["schema_version"] == 4:
        checks["owned_replay_delivery_in_both_captures"] = all(
            capture["schema_version"] != 4
            or capture["attempt"]["input_delivery"]["driver"] == "owned-pre-command"
            for capture in (reference, changed)
        )
        checks["same_selected_initial_watched_objects"] = (
            reference["schema_version"] == 4
            and changed["schema_version"] == 4
            and reference["attempt"]["trace"][0]["watched_objects"]
            == changed["attempt"]["trace"][0]["watched_objects"]
        )
        checks["same_watched_prefix_before_changed_input"] = (
            reference["schema_version"] == 4
            and changed["schema_version"] == 4
            and all(
                left["watched_objects"] == right["watched_objects"]
                for left, right in zip(reference["attempt"]["trace"], changed["attempt"]["trace"])
                if first_changed_input is not None and left["command_index"] < first_changed_input
            )
        )
    if predicates_required:
        checks["mechanics_predicates_available"] = mechanics_available
        checks["shared_mechanics_predicate_samples_observed"] = shared_rows > 0
    result = {
        "schema_version": matrix["schema_version"],
        "kind": "native_fixture_response",
        "case_id": case_id,
        "check_id": check_id,
        "status": "selected_response_observed"
        if all(checks.values())
        else "selected_response_not_established",
        "checks": checks,
        "shared_observed_rows": shared_rows,
        "required_observed_mode": check["mode"],
        "first_changed_input_command_index": first_changed_input,
        "first_difference": first_difference,
        "reference_capture_document_sha256": inspections[0]["capture_document_sha256"],
        "changed_capture_document_sha256": inspections[1]["capture_document_sha256"],
        "limitations": [
            "This is a supplied selected-state contrast between different owned input plans, not hardware-input equivalence.",
            "Matching selected initial fields does not establish equality of complete engine state.",
            "A difference proves an observed response only in the declared fixture, environment and command-index clock.",
            "The required mode is sampled after processCommands; it does not establish mode at the input callback.",
            "Response contrasts use schema-2/3 pre-ending samples in both captures; unknown or ending phases are excluded.",
        ],
    }
    if predicates_required:
        result.update(
            required_mechanics=check["required_mechanics"],
            mechanics_predicate_availability={
                "reference_schema3": reference["schema_version"] >= 3,
                "changed_schema3": changed["schema_version"] >= 3,
            },
            shared_pre_ending_mode_samples=shared_mode_rows,
            shared_mechanics_predicate_samples=shared_rows,
            mechanics_observation_scope="schema3_both_samples_match_all_declared_predicates",
        )
        result["limitations"].append(
            "Player-2 response samples require dual_active=true in both captures, irrespective of nullable predicates."
        )
    return result
