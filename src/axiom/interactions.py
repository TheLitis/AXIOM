"""Compare frozen geometry/trigger variants with the same owned input plan."""

import re
from pathlib import Path

from .fixtures import get_fixture_case, get_fixture_run, inspect_fixture_capture, load_fixture_matrix
from .ingest import parse_level_string
from .native import MAX_TRACE_RECORDS, load_native_capture, native_event_signature
from .validation import finite, mapping, read_json, sha256, string

_EVENT_ARGS = {
    "PlayerObject::collidedWithObject": {"dt_seconds", "skip_check"},
    "PlayerObject::updateCollide": {"direction"},
    "PlayerObject::collidedWithSlopeInternal": {"dt_seconds", "forced"},
    "PlayLayer::destroyPlayer": set(),
    "GJBaseGameLayer::triggerMoveCommand": {"target_group_id", "duration", "move_offset_x", "move_offset_y"},
    "GJBaseGameLayer::toggleGroupTriggered": {"group", "activate", "trigger_id", "control_id"},
    "GJBaseGameLayer::toggleGroup": {"group", "activate"},
    "GJBaseGameLayer::spawnGroup": {"group", "ordered", "delay", "trigger_id", "control_id"},
    "EffectGameObject::triggerObject": {"unique_id"},
}


def _fields(value, keys, name):
    data = mapping(value, name)
    if data.keys() != keys:
        raise ValueError(f"{name} requires exactly {sorted(keys)}")
    return data


def _int(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    return value


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", value):
        raise ValueError("Study id must be a lowercase fixture identifier")
    return value


def _array(value, minimum, maximum, name):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{name} requires {minimum} to {maximum} records")
    return value


def _window(value):
    result = _fields(value, {"first", "last"}, "command window")
    first = _int(result["first"], 0, MAX_TRACE_RECORDS - 1, "window.first")
    _int(result["last"], first, MAX_TRACE_RECORDS - 1, "window.last")
    return result


def _event_selector(event, arguments):
    if not isinstance(event, str) or event not in _EVENT_ARGS:
        raise ValueError("Unsupported study receipt event")
    mapping(arguments, "receipt.arguments")
    if arguments.keys() - _EVENT_ARGS[event]:
        raise ValueError("Unsupported receipt argument predicate")
    for name, value in arguments.items():
        if name in {"activate", "ordered", "forced", "skip_check"}:
            if type(value) is not bool:
                raise ValueError("Receipt flag predicates require JSON booleans")
        elif name in {"group", "target_group_id", "trigger_id", "control_id", "unique_id", "direction"}:
            _int(value, -(2**31), 2**31 - 1, "receipt argument")
        else:
            finite(value, "receipt argument")


def _raw_changes(positive, control):
    levels = [parse_level_string(case["level_string"]) for case in (positive, control)]
    if levels[0]["settings"] != levels[1]["settings"] or len(levels[0]["objects"]) != len(
        levels[1]["objects"]
    ):
        raise ValueError("Variant study requires identical headers and object counts")
    return [
        {
            "object_index": index,
            "property_key": key,
            "positive": left["properties"].get(key),
            "control": right["properties"].get(key),
        }
        for index, (left, right) in enumerate(zip(levels[0]["objects"], levels[1]["objects"]))
        for key in sorted(left["properties"].keys() | right["properties"].keys())
        if left["properties"].get(key) != right["properties"].get(key)
    ]


def load_variant_study(path: str | Path, matrix_path: str | Path) -> dict:
    study, _ = read_json(path)
    _fields(
        study, {"schema_version", "kind", "provenance", "fixture_matrix_sha256", "cases"}, "variant study"
    )
    if type(study["schema_version"]) is not int or study["schema_version"] != 1:
        raise ValueError("Variant study requires schema_version 1")
    if study["kind"] != "native_fixture_variant_study" or study["provenance"] != {
        "origin": "generated_synthetic",
        "native_verification": "not_recorded",
    }:
        raise ValueError("Variant study must declare unverified generated provenance")
    sha256(study["fixture_matrix_sha256"], "fixture_matrix_sha256")
    _, actual_sha = read_json(matrix_path)
    if study["fixture_matrix_sha256"] != actual_sha:
        raise ValueError("Variant study fixture matrix SHA256 mismatch")
    matrix = load_fixture_matrix(matrix_path)
    if matrix["schema_version"] != 3:
        raise ValueError("Variant study requires fixture matrix schema 3")
    identifiers = set()
    for case in _array(study["cases"], 1, 32, "study.cases"):
        _fields(
            case,
            {
                "id",
                "positive",
                "control",
                "controlled_changes",
                "prefix_window",
                "response_window",
                "response_kind",
                "player",
                "fields",
                "required_mechanics",
                "receipt_requirements",
                "constant_target_checks",
            },
            "study case",
        )
        identifier = _identifier(case["id"])
        if identifier in identifiers:
            raise ValueError("Duplicate study case id")
        identifiers.add(identifier)
        runs, fixtures = {}, {}
        for role in ("positive", "control"):
            ref = _fields(case[role], {"case_id", "run_id"}, "variant reference")
            fixtures[role] = get_fixture_case(matrix, ref["case_id"])
            runs[role] = get_fixture_run(matrix, ref["case_id"], ref["run_id"])
            if runs[role]["input_mode"] != "replay" or runs[role]["expected_outcome"] == "any_terminal":
                raise ValueError("Variants require owned replay runs with explicit terminal outcomes")
        if runs["positive"]["inputs"] != runs["control"]["inputs"]:
            raise ValueError("Variants require the same complete owned input plan")
        if fixtures["positive"]["level_sha256"] == fixtures["control"]["level_sha256"]:
            raise ValueError("Variants require different constructed level hashes")
        if fixtures["positive"]["watch_groups"] != fixtures["control"]["watch_groups"]:
            raise ValueError("Variants require the same stable watched group selectors")
        if not runs["positive"]["required_effect_checks"]:
            raise ValueError("Positive variant requires an actual applied effect check")
        changes = _array(case["controlled_changes"], 1, 64, "controlled_changes")
        for change in changes:
            _fields(change, {"object_index", "property_key", "positive", "control"}, "controlled change")
            _int(change["object_index"], 0, 200_000, "object_index")
            string(change["property_key"], "property_key")
            for role in ("positive", "control"):
                if change[role] is not None:
                    string(change[role], "raw property value")
        if changes != _raw_changes(fixtures["positive"], fixtures["control"]):
            raise ValueError("Declared controlled changes must match ALL changed raw object properties")
        prefix, response = _window(case["prefix_window"]), _window(case["response_window"])
        if prefix["first"] != 0 or prefix["last"] >= response["first"]:
            raise ValueError("Study requires an initial prefix before the response window")
        _int(case["player"], 1, 2, "study player")
        fields = _array(case["fields"], 1, 4, "response fields")
        if any(
            not isinstance(field, str) or field not in {"y", "y_velocity", "is_on_ground", "is_on_slope"}
            for field in fields
        ) or len(set(fields)) != len(fields):
            raise ValueError("Unsupported or duplicate selected response field")
        if not isinstance(case["response_kind"], str) or case["response_kind"] not in {
            "selected_trajectory",
            "native_terminal_outcome",
        }:
            raise ValueError("Unsupported response kind")
        if (
            case["response_kind"] == "native_terminal_outcome"
            and runs["positive"]["expected_outcome"] == runs["control"]["expected_outcome"]
        ):
            raise ValueError("Terminal contrast requires explicitly different expected outcomes")
        predicates = _fields(
            case["required_mechanics"],
            {"mode", "gravity_inverted", "vehicle_size", "player_speed", "dual_active"},
            "study mechanics",
        )
        if not isinstance(predicates["mode"], str) or predicates["mode"] not in {
            "cube",
            "ship",
            "ball",
            "ufo",
            "wave",
            "robot",
            "spider",
            "swing",
        }:
            raise ValueError("Unsupported study mode")
        for flag in ("gravity_inverted", "dual_active"):
            if type(predicates[flag]) is not bool:
                raise ValueError("Study mechanics flags must be JSON booleans")
        for field in ("vehicle_size", "player_speed"):
            finite(predicates[field], "study mechanics numeric predicate")
        if case["player"] == 2 and not predicates["dual_active"]:
            raise ValueError("Player2 study requires active dual")
        for req in _array(case["receipt_requirements"], 0, 32, "receipt_requirements"):
            _fields(
                req,
                {
                    "variant",
                    "event",
                    "player",
                    "object_group_id",
                    "command_window",
                    "arguments",
                    "min_events",
                    "ancestor",
                },
                "receipt requirement",
            )
            if not isinstance(req["variant"], str) or req["variant"] not in {"positive", "control"}:
                raise ValueError("Unknown receipt variant")
            _event_selector(req["event"], req["arguments"])
            _window(req["command_window"])
            _int(req["min_events"], 1, 4096, "min_events")
            if req["player"] is not None:
                _int(req["player"], 1, 2, "receipt player")
            if (
                req["object_group_id"] is not None
                and req["object_group_id"] not in fixtures[req["variant"]]["watch_groups"]
            ):
                raise ValueError("Receipt object group must be a declared watch")
            if req["object_group_id"] is not None:
                _int(req["object_group_id"], 1, 9999, "receipt group")
            if req["ancestor"] is not None:
                ancestor = _fields(req["ancestor"], {"event", "arguments"}, "receipt ancestor")
                _event_selector(ancestor["event"], ancestor["arguments"])
        for check in _array(case["constant_target_checks"], 0, 16, "constant_target_checks"):
            _fields(check, {"variant", "group_id", "field", "command_window", "value"}, "constant target")
            if not isinstance(check["variant"], str) or check["variant"] not in {"positive", "control"}:
                raise ValueError("Unknown constant-target variant")
            _int(check["group_id"], 1, 9999, "constant target group")
            if check["group_id"] not in fixtures[check["variant"]]["watch_groups"]:
                raise ValueError("Constant target must name a declared watch")
            _window(check["command_window"])
            if not isinstance(check["field"], str):
                raise ValueError("Unsupported constant target field")
            if check["field"] in {"is_group_disabled", "is_disabled"}:
                if type(check["value"]) is not bool:
                    raise ValueError("Constant-target flag requires a JSON boolean")
            elif check["field"] in {"x", "y"}:
                finite(check["value"], "constant target value")
            else:
                raise ValueError("Unsupported constant target field")
    return study


def _eligible(row, case):
    actor = row["state"][f"player{case['player']}"]
    required = case["required_mechanics"]
    return (
        not any(row["phase"].values())
        and actor is not None
        and not actor["is_dead"]
        and row["state"]["dual_active"] == required["dual_active"]
        and all(actor[key] == value for key, value in required.items() if key != "dual_active")
    )


def _matches_event(event, selector):
    return event["event"] == selector["event"] and all(
        type(event["arguments"].get(key)) is type(value)
        and event["arguments"].get(key) == value
        or type(value) in {int, float}
        and type(event["arguments"].get(key)) in {int, float}
        and event["arguments"].get(key) == value
        for key, value in selector["arguments"].items()
    )


def compare_fixture_variants(study_path, matrix_path, case_id, positive_path, control_path):
    study = load_variant_study(study_path, matrix_path)
    case = next((case for case in study["cases"] if case["id"] == case_id), None)
    if case is None:
        raise ValueError("Unknown variant study case")
    captures = {"positive": load_native_capture(positive_path), "control": load_native_capture(control_path)}
    if any(data["schema_version"] not in {4, 5} for data in captures.values()):
        raise ValueError("Variant contrast requires native capture schema 4 or 5")
    positive, control = captures.values()
    if positive["schema_version"] != control["schema_version"]:
        raise ValueError("Variant contrast requires the same capture schema_version")
    if positive["attempt"]["id"] == control["attempt"]["id"]:
        raise ValueError("Variant contrast requires distinct attempts")
    for key in ("environment", "collector", "state_fields", "layer_state_fields"):
        if positive[key] != control[key]:
            raise ValueError(f"Incompatible variant contrast identity: {key}")
    for key in ("game_version", "physics_version", "input_policy", "environment_id"):
        if positive["challenge"][key] != control["challenge"][key]:
            raise ValueError(f"Incompatible variant challenge domain: {key}")
    inspections = {
        role: inspect_fixture_capture(matrix_path, case[role]["case_id"], case[role]["run_id"], path)
        for role, path in (("positive", positive_path), ("control", control_path))
    }
    prefix = case["prefix_window"]
    actor = f"player{case['player']}"
    shared = zip(positive["attempt"]["trace"], control["attempt"]["trace"])
    rows = [
        (left, right) for left, right in shared if prefix["first"] <= left["command_index"] <= prefix["last"]
    ]
    prefix_ok = len(rows) == prefix["last"] + 1 and all(
        _eligible(left, case)
        and _eligible(right, case)
        and left["state"][actor] == right["state"][actor]
        and left["state"]["dual_active"] == right["state"]["dual_active"]
        for left, right in rows
    )
    response = case["response_window"]
    trajectory_witness = next(
        (
            {
                "command_index": left["command_index"],
                "positive": {key: left["state"][actor][key] for key in case["fields"]},
                "control": {key: right["state"][actor][key] for key in case["fields"]},
            }
            for left, right in zip(positive["attempt"]["trace"], control["attempt"]["trace"])
            if response["first"] <= left["command_index"] <= response["last"]
            and _eligible(left, case)
            and _eligible(right, case)
            and any(left["state"][actor][key] != right["state"][actor][key] for key in case["fields"])
        ),
        None,
    )
    terminal_witness = {
        role: {
            key: captures[role]["attempt"]["terminal"][key] for key in ("outcome", "event", "command_index")
        }
        for role in captures
    }
    terminal_ok = terminal_witness["positive"]["outcome"] != terminal_witness["control"]["outcome"] and all(
        response["first"] <= row["command_index"] <= response["last"] for row in terminal_witness.values()
    )
    receipts = []
    for req in case["receipt_requirements"]:
        events = captures[req["variant"]]["attempt"]["mechanic_events"]
        matched = []
        for event in events:
            if not (
                _matches_event(event, req)
                and event["player"] == req["player"]
                and req["command_window"]["first"] <= event["command_index"] <= req["command_window"]["last"]
                and not any(event["phase_before"].values())
            ):
                continue
            if req["object_group_id"] is not None and (
                event["object"] is None or req["object_group_id"] not in event["object"]["group_ids"]
            ):
                continue
            ancestor = event["parent_sequence"]
            ancestors = []
            while ancestor is not None:
                ancestors.append(events[ancestor])
                ancestor = events[ancestor]["parent_sequence"]
            if req["ancestor"] is not None and not any(
                _matches_event(row, req["ancestor"]) for row in ancestors
            ):
                continue
            matched.append(
                {
                    "sequence": event["sequence"],
                    "command_index": event["command_index"],
                    "arguments": event["arguments"],
                    "object": native_event_signature(event["object"]),
                    "ancestor_sequences": [row["sequence"] for row in ancestors],
                }
            )
        receipts.append(
            {"requirement": req, "matched": len(matched) >= req["min_events"], "witnesses": matched}
        )
    constants = []
    for check in case["constant_target_checks"]:
        rows = [
            row
            for row in captures[check["variant"]]["attempt"]["trace"]
            if check["command_window"]["first"] <= row["command_index"] <= check["command_window"]["last"]
            and _eligible(row, case)
        ]
        observed = [
            next(
                obj[check["field"]] for obj in row["watched_objects"] if obj["group_id"] == check["group_id"]
            )
            for row in rows
        ]
        expected_count = check["command_window"]["last"] - check["command_window"]["first"] + 1
        constants.append(
            {
                "requirement": check,
                "eligible_samples": len(rows),
                "matched": len(rows) == expected_count and all(value == check["value"] for value in observed),
            }
        )
    checks = {
        "positive_fixture_matches": inspections["positive"]["status"] == "fixture_observations_match",
        "control_fixture_matches": inspections["control"]["status"] == "fixture_observations_match",
        "selected_initial_prefix_matches": prefix_ok,
        "declared_response_observed": trajectory_witness is not None
        if case["response_kind"] == "selected_trajectory"
        else terminal_ok,
        "required_callback_contexts_observed": all(row["matched"] for row in receipts),
        "control_target_requirements_observed": all(row["matched"] for row in constants),
    }
    _, study_sha = read_json(study_path)
    return {
        "schema_version": 1,
        "kind": "native_fixture_variant_comparison",
        "case_id": case_id,
        "status": "declared_variant_effect_observed"
        if all(checks.values())
        else "declared_variant_effect_not_established",
        "checks": checks,
        "study_sha256": study_sha,
        "fixture_matrix_sha256": study["fixture_matrix_sha256"],
        "controlled_changes": case["controlled_changes"],
        "prefix_window": prefix,
        "response_kind": case["response_kind"],
        "response_window": response,
        "trajectory_witness": trajectory_witness,
        "terminal_witness": terminal_witness,
        "receipt_checks": receipts,
        "constant_target_checks": constants,
        "fixture_statuses": {role: inspection["status"] for role, inspection in inspections.items()},
        "capture_sha256": {
            role: read_json(path)[1]
            for role, path in (("positive", positive_path), ("control", control_path))
        },
        "ordinary_input_equivalence": "not_established",
        "m1_gate": "not_established_by_file_inspection",
        "limitations": [
            "Controlled raw construction changes are verified; unrecorded state is not proven identical.",
            "An event receipt alone establishes no physical effect; positive fixture checks require raw state changes.",
            "Ancestor constraints describe actual nested callback contexts, not an inferred full trigger dependency graph.",
            "Only declared selected trajectories or explicit native terminal contrasts satisfy the response gate.",
            "Supplied files cannot authenticate native origin or human difficulty.",
        ],
    }
