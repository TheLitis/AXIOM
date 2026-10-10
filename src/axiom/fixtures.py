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


def validate_fixture_matrix(data: object) -> dict:
    """Validate a bounded, versioned catalogue; native verification stays separate."""
    matrix = _fields(data, "fixture matrix", {"schema_version", "kind", "provenance", "clock", "cases"})
    if type(matrix["schema_version"]) is not int or matrix["schema_version"] not in {1, 2}:
        raise ValueError("Expected fixture matrix schema_version 1 or 2")
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
            {"id", "label", "level_string", "level_sha256", "mechanics_intent", "runs", "response_checks"},
        )
        case_id = _id(case["id"], "case.id")
        if case_id in case_ids:
            raise ValueError("Duplicate fixture case id")
        case_ids.add(case_id)
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
                | ({"required_mechanics_sequences"} if matrix["schema_version"] == 2 else set()),
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
            if matrix["schema_version"] == 2:
                _mechanics_sequences(run["required_mechanics_sequences"], run["required_mode_sequences"])
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
                | ({"required_mechanics"} if matrix["schema_version"] == 2 else set()),
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
            if matrix["schema_version"] == 2:
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
                **run,
            }
    raise ValueError(f"Unknown fixture run: {case_id}/{run_id}")


def _pre_end_rows(capture: dict) -> list[dict]:
    if capture["schema_version"] not in {2, 3}:
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
                if capture["schema_version"] != 3 or not state["dual_active"]:
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
        "native_schema3_fields": capture["schema_version"] == 3,
        "player1": {field: False for field in _MECHANICS_FIELDS},
        "player2": {field: False for field in _MECHANICS_FIELDS},
        "dual_active": False,
        "player2_active_samples": 0,
    }
    if capture["schema_version"] != 3:
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


def _evaluate_capture(matrix: dict, case_id: str, run_id: str, capture: dict) -> dict:
    run = get_fixture_run(matrix, case_id, run_id)
    attempt = capture["attempt"]
    source = "unknown" if run["input_mode"] == "observation" else "replay"
    mechanics_required = matrix["schema_version"] == 2
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
        "native_phase_boundary_available": capture["schema_version"] in {2, 3},
        "terminal_outcome_matches": attempt["terminal"]["outcome"] in {"completed", "died"}
        if run["expected_outcome"] == "any_terminal"
        else attempt["terminal"]["outcome"] == run["expected_outcome"],
        "required_modes_observed": all(mode_checks.values()),
    }
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
        if capture["schema_version"] in {2, 3}
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
    predicates_required = matrix["schema_version"] == 2
    mechanics_available = reference["schema_version"] == 3 and changed["schema_version"] == 3
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
        if reference["schema_version"] not in {2, 3} or changed["schema_version"] not in {2, 3}:
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
                "reference_schema3": reference["schema_version"] == 3,
                "changed_schema3": changed["schema_version"] == 3,
            },
            shared_pre_ending_mode_samples=shared_mode_rows,
            shared_mechanics_predicate_samples=shared_rows,
            mechanics_observation_scope="schema3_both_samples_match_all_declared_predicates",
        )
        result["limitations"].append(
            "Player-2 response samples require dual_active=true in both captures, irrespective of nullable predicates."
        )
    return result
