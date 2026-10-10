"""Constructed geometry is intent; requirements depend on supplied observations."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_native import collision_capture, mechanic_event

from axiom.fixtures import (
    compare_fixture_response,
    get_fixture_case,
    get_fixture_run,
    inspect_fixture_capture,
    load_fixture_matrix,
    validate_fixture_matrix,
)
from axiom.native import canonical_sha256

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_MATRIX = ROOT / "examples/native/fixture-matrix.json"
CAPTURE = ROOT / "examples/native/synthetic-clock-a.json"


def matrix():
    result = load_fixture_matrix(PUBLIC_MATRIX)
    case = result["cases"][0]
    result["cases"] = [case]
    case["runs"][1]["inputs"] = [{"command_index": 1, "player": 1, "button": 1, "pressed": True}]
    return result


def capture(*, replay=True, plan=True):
    result = json.loads(CAPTURE.read_text(encoding="utf-8"))
    result["challenge"]["level_sha256"] = matrix()["cases"][0]["level_sha256"]
    attempt = result["attempt"]
    if not plan:
        attempt["planned_inputs"] = []
        attempt["inputs"] = []
    if not replay:
        attempt["input_source"] = "unknown"
        attempt["replay_sha256"] = None
    return result


def matrix_v2():
    result = matrix()
    result["schema_version"] = 2
    for run in result["cases"][0]["runs"]:
        run["required_mechanics_sequences"] = {
            "player1": {"gravity_inverted": [False], "vehicle_size": [1.0], "player_speed": [0.9]},
            "player2": None,
            "dual_active": [False],
        }
    for check in result["cases"][0]["response_checks"]:
        check["required_mechanics"] = {
            "gravity_inverted": None,
            "vehicle_size": 1.0,
            "player_speed": None,
            "dual_active": False,
        }
    return result


def capture_v3(*, replay=True, plan=True):
    # Constructed schema values, not empirical physical calibration.
    result = capture(replay=replay, plan=plan)
    result["schema_version"] = 3
    result["state_fields"] += ["gravity_inverted", "vehicle_size", "player_speed"]
    result["layer_state_fields"] = ["dual_active"]
    states = [row["state"] for row in result["attempt"]["trace"]]
    states.append(result["attempt"]["terminal"]["state"])
    for state in states:
        state["dual_active"] = False
        for player in ("player1", "player2"):
            if state[player] is not None:
                state[player].update(gravity_inverted=False, vehicle_size=1.0, player_speed=0.9)
    return result


def matrix_v3():
    result = matrix_v2()
    result["schema_version"] = 3
    result["cases"][0]["watch_groups"] = [1]
    for run in result["cases"][0]["runs"]:
        run["required_state_witnesses"] = [
            {
                "id": "grounded-cube",
                "player": 1,
                "mode": "cube",
                "command_window": {"first": 0, "last": 2},
                "min_samples": 1,
                "predicates": {
                    "is_on_ground": True,
                    "is_on_slope": False,
                    "gravity_inverted": False,
                    "vehicle_size": 1.0,
                    "player_speed": 0.9,
                    "dual_active": False,
                    "y": {"minimum": 100.0, "maximum": 110.0},
                },
            }
        ]
        run["required_effect_checks"] = []
    return result


def capture_v4(*, replay=True, plan=True, driver=None):
    evidence = collision_capture(driver=driver or ("owned-pre-command" if replay else "none"))
    evidence["challenge"]["level_sha256"] = matrix()["cases"][0]["level_sha256"]
    if not plan:
        evidence["attempt"].update(planned_inputs=[], inputs=[])
    return evidence


def effect_check(*, event="PlayerObject::collidedWithObject"):
    check = {
        "id": "applied-contact",
        "event": event,
        "player": 1,
        "object_group_id": 1,
        "command_window": {"first": 1, "last": 3},
        "min_events": 1,
        "native_return": True,
        "player_change": {"field": "is_on_ground", "before": False, "after": True},
        "target_change": None,
    }
    if event != "PlayerObject::collidedWithObject":
        check["native_return"] = None
    if event == "PlayerObject::collidedWithSlopeInternal":
        check["player_change"]["field"] = "is_on_slope"
    if event == "PlayLayer::destroyPlayer":
        check["player_change"]["field"] = "is_dead"
    if event.startswith("GJBaseGameLayer::"):
        check.update(
            player=None,
            object_group_id=None,
            player_change=None,
            target_change={"group_id": 1, "field": "y", "before": 90.0, "after": 120.0},
        )
    return check


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
    return path


def inspect(tmp_path, spec=None, evidence=None, run="replay"):
    return inspect_fixture_capture(
        save(tmp_path / "matrix.json", spec or matrix()),
        "cube-flat",
        run,
        save(tmp_path / "capture.json", evidence or capture()),
    )


def response(tmp_path, spec=None, reference=None, changed=None):
    return compare_fixture_response(
        save(tmp_path / "matrix.json", spec or matrix()),
        "cube-flat",
        "jump-response",
        save(tmp_path / "reference.json", reference or capture(plan=False)),
        save(tmp_path / "changed.json", changed or capture()),
    )


def test_public_catalogue_separates_synthetic_construction_from_execution():
    result = load_fixture_matrix(PUBLIC_MATRIX)
    assert result["provenance"] == {"origin": "generated_synthetic", "native_verification": "not_recorded"}
    assert result["clock"] == "processCommands_call_index"
    assert {case["id"] for case in result["cases"]} >= {"cube-flat", "cube-spike"}
    for case in result["cases"]:
        assert case["level_sha256"] == hashlib.sha256(case["level_string"].encode()).hexdigest()
        assert all(run["expected_outcome"] in {"completed", "died"} for run in case["runs"])
        assert all(check["mode"] for check in case["response_checks"])
    assert "rating" not in result


def test_run_spec_preserves_exact_payload_and_clock_indices():
    result = matrix()
    run = get_fixture_run(result, "cube-flat", "replay")
    assert run["level_string"] == result["cases"][0]["level_string"]
    assert run["inputs"][0]["command_index"] == 1
    assert run["input_mode"] == "replay"
    assert get_fixture_case(result, "cube-flat")["id"] == "cube-flat"
    with pytest.raises(ValueError, match="Unknown fixture case"):
        get_fixture_case(result, "missing")
    with pytest.raises(ValueError, match="Unknown fixture run"):
        get_fixture_run(result, "cube-flat", "missing")


def test_public_matrix_declares_eleven_cases_with_owned_counterfactuals():
    result = load_fixture_matrix(PUBLIC_MATRIX)
    assert len(result["cases"]) == 11
    for case in result["cases"]:
        runs = {run["id"]: run for run in case["runs"]}
        assert runs["baseline"]["input_mode"] == "observation"
        assert runs["skip-input"]["input_mode"] == "replay"
        assert runs["skip-input"]["inputs"] == []
        assert case["response_checks"][0]["reference_run"] == "skip-input"
        assert case["response_checks"][0]["changed_run"] == "replay"
    multi = get_fixture_run(result, "cube-multi-jump", "replay")
    assert [event["command_index"] for event in multi["inputs"]] == [60, 90, 220, 250, 380, 410]
    hold = get_fixture_run(result, "cube-long-hold", "replay")
    assert [event["command_index"] for event in hold["inputs"]] == [60, 300]


@pytest.mark.parametrize("mode", ["ship", "ball", "ufo", "wave", "robot", "spider", "swing"])
def test_portal_specs_require_actual_mode_and_do_not_invent_return_transition(mode):
    result = load_fixture_matrix(PUBLIC_MATRIX)
    replay = get_fixture_run(result, mode + "-portal", "replay")
    control = get_fixture_run(result, mode + "-portal", "skip-input")
    required_replay = ["cube", mode] if mode in {"ball", "spider", "swing"} else ["cube", mode, "cube"]
    assert replay["required_mode_sequences"]["player1"] == required_replay
    assert control["required_mode_sequences"]["player1"] == ["cube", mode, "cube"]
    assert [event["command_index"] for event in replay["inputs"]] == [130, 160]
    assert get_fixture_case(result, mode + "-portal")["response_checks"][0]["mode"] == mode


@pytest.mark.parametrize("version", [True, 1.0, 4, "1"])
def test_version_is_strict_integer(version):
    data = matrix()
    data["schema_version"] = version
    with pytest.raises(ValueError, match="schema_version"):
        validate_fixture_matrix(data)


@pytest.mark.parametrize(
    "keys,value",
    [
        (("kind",), "native_capture"),
        (("clock",), "milliseconds"),
        (("provenance", "native_verification"), "verified"),
        (("cases", 0, "id"), "../outside"),
        (("cases", 0, "level_sha256"), "a" * 64),
        (("cases", 0, "level_string"), "invalid;"),
        (("cases", 0, "level_string"), " ;"),
        (("cases", 0, "level_string"), "\ud800;"),
        (("cases", 0, "runs", 1, "role"), {}),
        (("cases", 0, "runs", 1, "input_mode"), []),
        (("cases", 0, "runs", 1, "expected_outcome"), {}),
        (("cases", 0, "runs", 1, "inputs", 0, "command_index"), True),
        (("cases", 0, "runs", 1, "inputs", 0, "command_index"), 1.0),
        (("cases", 0, "runs", 1, "inputs", 0, "command_index"), 20_001),
        (("cases", 0, "runs", 1, "inputs", 0, "player"), 3),
        (("cases", 0, "runs", 1, "inputs", 0, "pressed"), 1),
        (("cases", 0, "runs", 1, "required_mode_sequences", "player1"), ["cube", "cube"]),
        (("cases", 0, "runs", 1, "required_mode_sequences", "player1"), ["cube", {}]),
        (("cases", 0, "runs", 1, "required_mode_sequences", "player1"), ["gravity-inverted"]),
        (("cases", 0, "runs", 1, "required_mode_sequences", "player2"), []),
        (("cases", 0, "response_checks", 0, "mode"), {}),
        (("cases", 0, "response_checks", 0, "fields"), ["rotation"]),
        (("cases", 0, "response_checks", 0, "fields"), ["y", "y"]),
        (("cases", 0, "response_checks", 0, "fields"), [{}]),
        (("cases", 0, "response_checks", 0, "reference_run"), "baseline"),
        (("cases", 0, "response_checks", 0, "reference_run"), "absent"),
        (("cases", 0, "response_checks", 0, "player"), 2),
    ],
)
def test_untrusted_schema_rejected_with_value_error(keys, value):
    data = matrix()
    target = data
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value
    with pytest.raises(ValueError):
        validate_fixture_matrix(data)


@pytest.mark.parametrize("where", [(), ("cases", 0), ("cases", 0, "runs", 1)])
def test_unknown_fields_cannot_silently_change_requirement_semantics(where):
    data = matrix()
    target = data
    for key in where:
        target = target[key]
    target["unknown"] = True
    with pytest.raises(ValueError, match="requires exactly"):
        validate_fixture_matrix(data)


@pytest.mark.parametrize("collection", ["cases", "runs", "response_checks"])
def test_duplicate_identifiers_rejected(collection):
    data = matrix()
    target = data["cases"] if collection == "cases" else data["cases"][0][collection]
    target.append(deepcopy(target[0]))
    with pytest.raises(ValueError, match="Duplicate"):
        validate_fixture_matrix(data)


def test_empty_or_oversized_catalogue_rejected():
    data = matrix()
    data["cases"] = []
    with pytest.raises(ValueError, match="cases must contain"):
        validate_fixture_matrix(data)
    data["cases"] = [matrix()["cases"][0]] * 65
    with pytest.raises(ValueError, match="cases must contain"):
        validate_fixture_matrix(data)


def test_input_plan_must_change_held_state_and_preserve_order():
    data = matrix()
    inputs = data["cases"][0]["runs"][1]["inputs"]
    inputs.append(dict(inputs[0]))
    with pytest.raises(ValueError, match="held state"):
        validate_fixture_matrix(data)
    inputs[-1].update(command_index=2, pressed=False)
    assert validate_fixture_matrix(data)
    inputs[0]["command_index"] = 3
    with pytest.raises(ValueError, match="ordered"):
        validate_fixture_matrix(data)


def test_baseline_cannot_claim_an_owned_input_plan():
    data = matrix()
    data["cases"][0]["runs"][0]["inputs"] = data["cases"][0]["runs"][1]["inputs"]
    with pytest.raises(ValueError, match="observation baseline"):
        validate_fixture_matrix(data)


def test_response_requires_distinct_owned_plans():
    data = matrix()
    data["cases"][0]["response_checks"][0]["reference_run"] = "replay"
    with pytest.raises(ValueError, match="different input plans"):
        validate_fixture_matrix(data)


def test_duplicate_json_keys_rejected_before_schema(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        load_fixture_matrix(path)


def test_capture_checks_retained_synthetic_provenance_and_actual_callbacks(tmp_path):
    result = inspect(tmp_path)
    assert result["status"] == "fixture_observations_match"
    assert all(result["checks"].values())
    assert result["capture_provenance"]["origin"] == "synthetic"
    assert result["observed_mode_sequences"]["player1"] == ["cube"]
    assert result["missing_native_callbacks"] == []
    assert "Axiom Rating" in result["limitations"][-1]


@pytest.mark.parametrize("native_return", [False, "missing"])
def test_requested_input_does_not_prove_successful_native_callback(tmp_path, native_return):
    data = capture()
    if native_return == "missing":
        data["attempt"]["inputs"].pop()
    else:
        data["attempt"]["inputs"][1]["native_return"] = native_return
    result = inspect(tmp_path, evidence=data)
    assert result["status"] == "fixture_observations_mismatch"
    assert result["checks"]["native_callbacks_observed"] is False
    assert result["missing_native_callbacks"][0]["required_phase"] == "push"


def test_encoded_portal_intent_is_insufficient_without_observed_mode(tmp_path):
    spec = matrix()
    spec["cases"][0]["mechanics_intent"] = ["ship-portal"]
    spec["cases"][0]["runs"][1]["required_mode_sequences"]["player1"] = ["cube", "ship"]
    result = inspect(tmp_path, spec=spec)
    assert result["status"] == "fixture_observations_mismatch"
    assert result["checks"]["required_modes_observed"] is False
    evidence = capture()
    evidence["attempt"]["trace"][1]["state"]["player1"]["mode"] = "ship"
    result = inspect(tmp_path, spec=spec, evidence=evidence)
    assert result["status"] == "fixture_observations_match"
    assert result["observed_mode_sequences"]["player1"] == ["cube", "ship"]


def test_mismatch_and_unexecuted_planned_tail_remain_failures(tmp_path):
    spec = matrix()
    spec["cases"][0]["runs"][1]["inputs"].append(
        {"command_index": 10, "player": 1, "button": 1, "pressed": False}
    )
    evidence = capture()
    evidence["attempt"]["planned_inputs"] = spec["cases"][0]["runs"][1]["inputs"]
    result = inspect(tmp_path, spec=spec, evidence=evidence)
    assert result["checks"]["planned_inputs_match"]
    assert not result["checks"]["complete_plan_executed"]
    assert result["status"] == "fixture_observations_mismatch"


def test_baseline_checks_no_observed_input_and_skip_plan_keeps_replay_mode(tmp_path):
    result = inspect(tmp_path, evidence=capture(replay=False, plan=False), run="baseline")
    assert result["status"] == "fixture_observations_match"
    result = inspect(tmp_path, evidence=capture(plan=False), run="skip-input")
    assert result["status"] == "fixture_observations_match"
    result = inspect(tmp_path, evidence=capture(replay=False, plan=False), run="skip-input")
    assert result["checks"]["input_mode_matches"] is False


def test_unknown_and_wrong_level_or_start_do_not_match(tmp_path):
    data = capture()
    data["challenge"]["level_sha256"] = "0" * 64
    data["attempt"]["start_kind"] = "practice"
    result = inspect(tmp_path, evidence=data)
    assert not result["checks"]["level_identity_matches"]
    assert not result["checks"]["full_start"]
    with pytest.raises(ValueError, match="Unknown fixture run"):
        inspect(tmp_path, run="unknown")


def test_any_terminal_is_explicitly_exploratory(tmp_path):
    spec = matrix()
    spec["cases"][0]["runs"][1]["expected_outcome"] = "any_terminal"
    result = inspect(tmp_path, spec=spec)
    assert result["exploratory_outcome"]
    assert result["checks"]["terminal_outcome_matches"]


def test_invalid_native_recording_is_rejected_by_native_validator(tmp_path):
    evidence = capture()
    evidence["integrity"]["recording_complete"] = False
    with pytest.raises(ValueError, match="Incomplete native recording"):
        inspect(tmp_path, evidence=evidence)


def test_ending_and_terminal_mode_changes_do_not_satisfy_portal_requirement(tmp_path):
    spec = matrix()
    spec["cases"][0]["runs"][1]["required_mode_sequences"]["player1"] = ["cube", "ship"]
    evidence = capture()
    evidence["attempt"]["trace"][2]["state"]["player1"]["mode"] = "ship"
    evidence["attempt"]["terminal"]["state"]["player1"]["mode"] = "ship"
    result = inspect(tmp_path, spec=spec, evidence=evidence)
    assert result["observed_mode_sequences"]["player1"] == ["cube"]
    assert not result["checks"]["required_modes_observed"]
    assert result["mode_observation_scope"] == "before_native_end_animation"


def test_schema1_cannot_invent_gameplay_phase_for_mode_coverage(tmp_path):
    evidence = json.loads((ROOT / "examples/native/synthetic-capture-a.json").read_text())
    evidence["challenge"]["level_sha256"] = matrix()["cases"][0]["level_sha256"]
    result = inspect(tmp_path, evidence=evidence)
    assert result["status"] == "fixture_observations_mismatch"
    assert result["mode_observation_scope"] == "unavailable_schema1"
    assert result["observed_mode_sequences"]["player1"] == []
    assert not result["checks"]["native_phase_boundary_available"]
    assert not result["checks"]["required_modes_observed"]


def test_owned_plan_contrast_requires_selected_motion_not_rotation(tmp_path):
    changed = capture()
    changed["attempt"]["trace"][1]["state"]["player1"]["rotation"] = 45
    result = response(tmp_path, changed=changed)
    assert result["status"] == "selected_response_not_established"
    changed["attempt"]["trace"][1]["state"]["player1"]["y_velocity"] = 3
    result = response(tmp_path, changed=changed)
    assert result["status"] == "selected_response_observed"
    assert result["first_difference"]["command_index"] == 1
    assert result["required_observed_mode"] == "cube"
    assert result["first_changed_input_command_index"] == 1


def test_motion_in_cube_prefix_does_not_establish_ship_response(tmp_path):
    spec = matrix()
    spec["cases"][0]["response_checks"][0]["mode"] = "ship"
    changed = capture()
    changed["attempt"]["trace"][1]["state"]["player1"]["y"] += 10
    result = response(tmp_path, spec=spec, changed=changed)
    assert result["status"] == "selected_response_not_established"
    assert result["shared_observed_rows"] == 0
    assert result["first_difference"] is None


def test_ending_animation_motion_does_not_establish_input_response(tmp_path):
    changed = capture()
    changed["attempt"]["trace"][2]["state"]["player1"]["y"] += 10
    changed["attempt"]["terminal"]["state"]["player1"]["y"] += 10
    result = response(tmp_path, changed=changed)
    assert result["status"] == "selected_response_not_established"
    assert not result["checks"]["selected_response_differs"]
    assert result["shared_observed_rows"] == 1


def test_response_requires_both_samples_in_requested_mode(tmp_path):
    spec = matrix()
    spec["cases"][0]["response_checks"][0]["mode"] = "ship"
    changed = capture()
    changed["attempt"]["trace"][1]["state"]["player1"].update(y=115, mode="ship")
    result = response(tmp_path, spec=spec, changed=changed)
    assert result["status"] == "selected_response_not_established"


def test_changed_initial_state_and_environment_do_not_establish_response(tmp_path):
    changed = capture()
    changed["attempt"]["trace"][0]["state"]["player1"]["y"] = 104
    changed["attempt"]["trace"][1]["state"]["player1"]["y"] = 115
    result = response(tmp_path, changed=changed)
    assert not result["checks"]["same_selected_initial_state"]
    assert not result["checks"]["same_selected_prefix_before_changed_input"]
    assert result["status"] == "selected_response_not_established"
    changed = capture()
    changed["environment"]["game_executable_sha256"] = "f" * 64
    environment_sha = canonical_sha256(changed["environment"])
    changed["environment_sha256"] = environment_sha
    changed["challenge"]["environment_id"] = environment_sha
    changed["attempt"]["trace"][1]["state"]["player1"]["y"] = 115
    result = response(tmp_path, changed=changed)
    assert not result["checks"]["same_environment"]
    assert result["status"] == "selected_response_not_established"


def test_response_does_not_ignore_fixture_requirement_failures(tmp_path):
    changed = capture()
    changed["attempt"]["inputs"][1]["native_return"] = False
    changed["attempt"]["trace"][1]["state"]["player1"]["y"] += 10
    result = response(tmp_path, changed=changed)
    assert result["checks"]["selected_response_differs"]
    assert not result["checks"]["changed_requirements_match"]
    assert result["status"] == "selected_response_not_established"


def test_v2_inspector_requires_selected_raw_schema3_fields(tmp_path):
    result = inspect(tmp_path, spec=matrix_v2(), evidence=capture_v3())
    assert result["schema_version"] == 2
    assert result["status"] == "fixture_observations_match"
    assert result["checks"]["native_mechanics_available"]
    assert result["observed_mechanics_sequences"]["player1"] == {
        "gravity_inverted": [False],
        "vehicle_size": [1.0],
        "player_speed": [0.9],
    }
    assert result["observed_mechanics_sequences"]["dual_active"] == [False]
    assert result["mechanics_availability"]["player2_active_samples"] == 0
    assert result["mechanics_checks"]["player2"] is None


@pytest.mark.parametrize("legacy", [1, 2])
def test_legacy_captures_cannot_supply_missing_raw_mechanics(tmp_path, legacy):
    evidence = (
        capture()
        if legacy == 2
        else json.loads((ROOT / "examples/native/synthetic-capture-a.json").read_text())
    )
    evidence["challenge"]["level_sha256"] = matrix()["cases"][0]["level_sha256"]
    result = inspect(tmp_path, spec=matrix_v2(), evidence=evidence)
    assert result["status"] == "fixture_observations_mismatch"
    assert not result["checks"]["native_mechanics_available"]
    assert not result["checks"]["required_mechanics_observed"]
    assert result["observed_mechanics_sequences"]["player1"]["vehicle_size"] is None
    assert not result["mechanics_availability"]["player1"]["vehicle_size"]


def test_v1_output_fieldsets_are_preserved_for_schema3_observations(tmp_path):
    expected = inspect(tmp_path)
    result = inspect(tmp_path, evidence=capture_v3())
    assert result.keys() == expected.keys()
    assert result["schema_version"] == 1
    assert result["status"] == "fixture_observations_match"
    changed = capture_v3()
    changed["attempt"]["trace"][1]["state"]["player1"]["y"] += 1
    result = response(tmp_path, reference=capture_v3(plan=False), changed=changed)
    assert result.keys() == response(tmp_path).keys()
    assert result["schema_version"] == 1
    assert result["status"] == "selected_response_observed"


@pytest.mark.parametrize(
    "field,value",
    [
        ("gravity_inverted", [0]),
        ("gravity_inverted", [False, 0]),
        ("gravity_inverted", [False, False]),
        ("gravity_inverted", []),
        ("vehicle_size", [True]),
        ("vehicle_size", [1, 1.0]),
        ("vehicle_size", [float("nan")]),
        ("vehicle_size", [float("inf")]),
        ("vehicle_size", [2**2000]),
        ("player_speed", ["0.9"]),
        ("player_speed", [0.9, 0.9]),
        ("player_speed", [1] * 65),
    ],
)
def test_v2_sequence_types_limits_and_nonfinite_values_are_strict(field, value):
    data = matrix_v2()
    data["cases"][0]["runs"][1]["required_mechanics_sequences"]["player1"][field] = value
    with pytest.raises(ValueError):
        validate_fixture_matrix(data)


def test_v2_runs_cannot_be_all_null_or_add_undeclared_mechanics():
    data = matrix_v2()
    requirement = data["cases"][0]["runs"][1]["required_mechanics_sequences"]
    requirement["player1"] = {field: None for field in requirement["player1"]}
    requirement["dual_active"] = None
    with pytest.raises(ValueError, match="at least one non-null"):
        validate_fixture_matrix(data)
    requirement["dual_active"] = [False]
    assert validate_fixture_matrix(data)
    requirement["player1"]["inferred_mini"] = [False]
    with pytest.raises(ValueError, match="requires exactly"):
        validate_fixture_matrix(data)


def test_raw_numeric_constraints_have_no_invented_physical_ranges():
    data = matrix_v2()
    data["cases"][0]["runs"][1]["required_mechanics_sequences"]["player1"]["vehicle_size"] = [-1.0]
    data["cases"][0]["response_checks"][0]["required_mechanics"]["player_speed"] = -2.0
    assert validate_fixture_matrix(data)


def test_raw_mechanics_are_exact_and_compressed_before_ending(tmp_path):
    spec, evidence = matrix_v2(), capture_v3()
    spec["cases"][0]["runs"][1]["required_mechanics_sequences"]["player1"]["gravity_inverted"] = [False, True]
    evidence["attempt"]["trace"][1]["state"]["player1"]["gravity_inverted"] = True
    evidence["attempt"]["trace"][2]["state"]["player1"].update(gravity_inverted=False, vehicle_size=0.5)
    evidence["attempt"]["terminal"]["state"]["player1"]["vehicle_size"] = 0.5
    result = inspect(tmp_path, spec=spec, evidence=evidence)
    assert result["status"] == "fixture_observations_match"
    assert result["observed_mechanics_sequences"]["player1"]["gravity_inverted"] == [False, True]
    assert result["observed_mechanics_sequences"]["player1"]["vehicle_size"] == [1.0]
    spec["cases"][0]["runs"][1]["required_mechanics_sequences"]["player1"]["vehicle_size"] = [1.0000000001]
    result = inspect(tmp_path, spec=spec, evidence=evidence)
    assert not result["mechanics_checks"]["player1"]["vehicle_size"]
    assert result["status"] == "fixture_observations_mismatch"


def dual_spec():
    spec = matrix_v2()
    run = spec["cases"][0]["runs"][1]
    run["required_mode_sequences"]["player2"] = ["cube"]
    run["required_mechanics_sequences"]["player2"] = {
        "gravity_inverted": [False],
        "vehicle_size": [0.5],
        "player_speed": [0.9],
    }
    run["required_mechanics_sequences"]["dual_active"] = [False, True]
    return spec


def test_inactive_player2_pointer_does_not_prove_dual_mechanics(tmp_path):
    evidence = capture_v3()
    for row in evidence["attempt"]["trace"]:
        row["state"]["player2"] = deepcopy(row["state"]["player1"])
        row["state"]["player2"]["vehicle_size"] = 0.5
    result = inspect(tmp_path, spec=dual_spec(), evidence=evidence)
    assert result["status"] == "fixture_observations_mismatch"
    assert result["observed_mode_sequences"]["player2"] == []
    assert result["observed_mechanics_sequences"]["player2"]["vehicle_size"] == []
    assert not result["mechanics_checks"]["player2_active_samples_observed"]
    evidence["attempt"]["trace"][1]["state"]["dual_active"] = True
    result = inspect(tmp_path, spec=dual_spec(), evidence=evidence)
    assert result["status"] == "fixture_observations_match"
    assert result["observed_mechanics_sequences"]["player2"]["vehicle_size"] == [0.5]
    assert result["observed_mode_sequences"]["player2"] == ["cube"]


def test_active_dual_flag_without_player2_state_cannot_satisfy_requirements(tmp_path):
    evidence = capture_v3()
    evidence["attempt"]["trace"][1]["state"]["dual_active"] = True
    result = inspect(tmp_path, spec=dual_spec(), evidence=evidence)
    assert not result["mechanics_checks"]["player2_active_samples_observed"]
    assert not result["mechanics_availability"]["player2"]["vehicle_size"]
    assert result["observed_mechanics_sequences"]["player2"]["vehicle_size"] == [None]


def test_null_player2_scope_claims_none_and_empty_scope_needs_mode_requirement():
    spec = matrix_v2()
    run = spec["cases"][0]["runs"][1]
    run["required_mechanics_sequences"]["player2"] = {
        "gravity_inverted": None,
        "vehicle_size": None,
        "player_speed": None,
    }
    with pytest.raises(ValueError, match="explicit player2 mode"):
        validate_fixture_matrix(spec)
    run["required_mode_sequences"]["player2"] = ["cube"]
    assert validate_fixture_matrix(spec)


@pytest.mark.parametrize(
    "field,value",
    [("dual_active", 0), ("gravity_inverted", 1), ("vehicle_size", True), ("player_speed", float("inf"))],
)
def test_response_predicates_preserve_raw_types(field, value):
    spec = matrix_v2()
    spec["cases"][0]["response_checks"][0]["required_mechanics"][field] = value
    with pytest.raises(ValueError):
        validate_fixture_matrix(spec)


def test_response_predicates_required_and_player2_cannot_request_inactive_dual():
    spec = matrix_v2()
    check = spec["cases"][0]["response_checks"][0]
    check["required_mechanics"] = {key: None for key in check["required_mechanics"]}
    with pytest.raises(ValueError, match="at least one mechanics predicate"):
        validate_fixture_matrix(spec)
    check["required_mechanics"]["dual_active"] = False
    check["player"] = 2
    spec["cases"][0]["runs"][1]["inputs"][0]["player"] = 2
    with pytest.raises(ValueError, match="dual_active=false"):
        validate_fixture_matrix(spec)


def test_motion_after_size_reverts_cannot_satisfy_target_parameter_response(tmp_path):
    spec = matrix_v2()
    spec["cases"][0]["response_checks"][0]["required_mechanics"]["vehicle_size"] = 0.5
    changed = capture_v3()
    changed["attempt"]["trace"][1]["state"]["player1"]["y"] += 1
    result = response(tmp_path, spec=spec, reference=capture_v3(plan=False), changed=changed)
    assert result["schema_version"] == 2
    assert result["status"] == "selected_response_not_established"
    assert result["shared_pre_ending_mode_samples"] == 1
    assert result["shared_mechanics_predicate_samples"] == 0
    assert result["first_difference"] is None


def test_v2_response_conditions_must_hold_in_both_samples_and_are_auditable(tmp_path):
    spec, reference, changed = matrix_v2(), capture_v3(plan=False), capture_v3()
    check = spec["cases"][0]["response_checks"][0]
    check["required_mechanics"]["vehicle_size"] = 0.5
    for run in spec["cases"][0]["runs"]:
        run["required_mechanics_sequences"]["player1"]["vehicle_size"] = [1.0, 0.5]
    changed["attempt"]["trace"][1]["state"]["player1"].update(y=115, vehicle_size=0.5)
    result = response(tmp_path, spec=spec, reference=reference, changed=changed)
    assert result["shared_mechanics_predicate_samples"] == 0
    reference["attempt"]["trace"][1]["state"]["player1"]["vehicle_size"] = 0.5
    result = response(tmp_path, spec=spec, reference=reference, changed=changed)
    assert result["status"] == "selected_response_observed"
    assert result["first_difference"]["observed_mechanics"]["reference"]["vehicle_size"] == 0.5
    assert result["first_difference"]["observed_mechanics"]["changed"]["dual_active"] is False
    assert all(result["mechanics_predicate_availability"].values())


def test_v2_response_cannot_invent_parameter_values_from_legacy_capture(tmp_path):
    changed = capture()
    changed["attempt"]["trace"][1]["state"]["player1"]["y"] += 1
    result = response(tmp_path, spec=matrix_v2(), reference=capture(plan=False), changed=changed)
    assert not result["checks"]["mechanics_predicates_available"]
    assert result["shared_mechanics_predicate_samples"] == 0
    assert result["status"] == "selected_response_not_established"


@pytest.mark.parametrize("field", ["gravity_inverted", "vehicle_size", "player_speed", "dual_active"])
def test_schema3_response_prefix_includes_all_new_actor_and_layer_fields(tmp_path, field):
    reference, changed = capture_v3(plan=False), capture_v3()
    # Change the replay event to index 2, leaving row 1 as an unchanged-plan prefix.
    changed["attempt"]["planned_inputs"][0]["command_index"] = 2
    for event in changed["attempt"]["inputs"]:
        event["command_index"] = 2
    spec = matrix_v2()
    spec["cases"][0]["runs"][1]["inputs"][0]["command_index"] = 2
    state = changed["attempt"]["trace"][1]["state"]
    if field == "dual_active":
        state[field] = True
    else:
        state["player1"][field] = True if field == "gravity_inverted" else 0.5
    result = response(tmp_path, spec=spec, reference=reference, changed=changed)
    assert not result["checks"]["same_selected_prefix_before_changed_input"]
    assert result["status"] == "selected_response_not_established"


def test_v2_player2_response_always_requires_dual_active_in_both_samples(tmp_path):
    spec = matrix_v2()
    spec["cases"][0]["runs"][1]["inputs"][0]["player"] = 2
    check = spec["cases"][0]["response_checks"][0]
    check["player"] = 2
    check["required_mechanics"]["dual_active"] = None
    reference, changed = capture_v3(plan=False), capture_v3()
    changed["attempt"]["planned_inputs"][0]["player"] = 2
    for event in changed["attempt"]["inputs"]:
        event["player"] = 2
    for evidence in (reference, changed):
        states = [row["state"] for row in evidence["attempt"]["trace"]]
        states.append(evidence["attempt"]["terminal"]["state"])
        for state in states:
            state["player2"] = deepcopy(state["player1"])
    changed["attempt"]["trace"][1]["state"]["player2"]["y"] += 1
    result = response(tmp_path, spec=spec, reference=reference, changed=changed)
    assert result["checks"]["reference_requirements_match"]
    assert result["checks"]["changed_requirements_match"]
    assert result["shared_pre_ending_mode_samples"] == 1
    assert result["shared_mechanics_predicate_samples"] == 0
    assert result["status"] == "selected_response_not_established"
    reference["attempt"]["trace"][1]["state"]["dual_active"] = True
    changed["attempt"]["trace"][1]["state"]["dual_active"] = True
    for run in spec["cases"][0]["runs"]:
        run["required_mechanics_sequences"]["dual_active"] = [False, True]
    result = response(tmp_path, spec=spec, reference=reference, changed=changed)
    assert result["status"] == "selected_response_observed"
    assert result["first_difference"]["observed_mechanics"]["reference"]["dual_active"] is True


def test_v1_player2_mode_semantics_are_preserved_without_new_dual_claim(tmp_path):
    spec, evidence = matrix(), capture_v3()
    spec["cases"][0]["runs"][1]["required_mode_sequences"]["player2"] = ["cube"]
    for row in evidence["attempt"]["trace"]:
        row["state"]["player2"] = deepcopy(row["state"]["player1"])
    result = inspect(tmp_path, spec=spec, evidence=evidence)
    assert result["schema_version"] == 1
    assert result["mode_checks"]["player2"]
    assert "mechanics_availability" not in result
    assert result["status"] == "fixture_observations_match"


def test_versioned_mechanics_field_shapes_are_exact():
    spec = matrix_v2()
    del spec["cases"][0]["runs"][1]["required_mechanics_sequences"]
    with pytest.raises(ValueError, match="requires exactly"):
        validate_fixture_matrix(spec)
    spec = matrix_v2()
    del spec["cases"][0]["response_checks"][0]["required_mechanics"]
    with pytest.raises(ValueError, match="requires exactly"):
        validate_fixture_matrix(spec)
    spec = matrix()
    spec["cases"][0]["runs"][1]["required_mechanics_sequences"] = matrix_v2()["cases"][0]["runs"][1][
        "required_mechanics_sequences"
    ]
    with pytest.raises(ValueError, match="requires exactly"):
        validate_fixture_matrix(spec)


def test_matrix3_joint_witness_matches_one_actual_pre_ending_sample(tmp_path):
    spec, evidence = matrix_v3(), capture_v4()
    result = inspect(tmp_path, spec=spec, evidence=evidence)
    assert result["schema_version"] == 3
    assert result["status"] == "fixture_observations_match"
    assert result["checks"]["watch_groups_match"]
    witness = result["state_witness_checks"][0]
    assert witness["matching_command_indices"] == [0, 1]
    assert witness["first_matching_sample"]["observed_predicates"]["is_on_ground"] is True
    assert get_fixture_run(spec, "cube-flat", "replay")["watch_groups"] == [1]


def test_matrix3_separate_matching_flags_cannot_satisfy_joint_contact_witness(tmp_path):
    spec, evidence = matrix_v3(), capture_v4()
    spec["cases"][0]["runs"][1]["required_state_witnesses"][0]["predicates"]["is_on_slope"] = True
    evidence["attempt"]["trace"][1]["state"]["player1"].update(is_on_ground=False, is_on_slope=True)
    result = inspect(tmp_path, spec=spec, evidence=evidence)
    assert result["state_witness_checks"][0]["matching_sample_count"] == 0
    assert result["status"] == "fixture_observations_mismatch"


def test_matrix3_end_animation_or_outside_y_window_cannot_satisfy_contact_witness(tmp_path):
    spec, evidence = matrix_v3(), capture_v4()
    witness = spec["cases"][0]["runs"][1]["required_state_witnesses"][0]
    witness["predicates"]["is_on_slope"] = True
    evidence["attempt"]["trace"][2]["state"]["player1"]["is_on_slope"] = True
    result = inspect(tmp_path, spec=spec, evidence=evidence)
    assert not result["state_witness_checks"][0]["matched"]
    witness["predicates"]["is_on_slope"] = False
    witness["predicates"]["y"] = {"minimum": 105.1, "maximum": 106}
    assert not inspect(tmp_path, spec=spec, evidence=evidence)["state_witness_checks"][0]["matched"]


def test_matrix3_inactive_player2_pointer_cannot_satisfy_joint_witness(tmp_path):
    spec, evidence = matrix_v3(), capture_v4()
    witness = spec["cases"][0]["runs"][1]["required_state_witnesses"][0]
    witness["player"] = 2
    witness["predicates"]["dual_active"] = None
    for row in evidence["attempt"]["trace"]:
        row["state"]["player2"] = deepcopy(row["state"]["player1"])
    assert not inspect(tmp_path, spec=spec, evidence=evidence)["state_witness_checks"][0]["matched"]
    evidence["attempt"]["trace"][1]["state"]["dual_active"] = True
    spec["cases"][0]["runs"][1]["required_mechanics_sequences"]["dual_active"] = [False, True]
    assert inspect(tmp_path, spec=spec, evidence=evidence)["state_witness_checks"][0]["matched"]


@pytest.mark.parametrize("legacy", [capture, capture_v3])
def test_matrix3_legacy_capture_contact_fields_are_unavailable(tmp_path, legacy):
    result = inspect(tmp_path, spec=matrix_v3(), evidence=legacy())
    assert not result["checks"]["native_contact_effect_fields_available"]
    assert not result["state_witness_checks"][0]["available"]
    assert result["state_witness_checks"][0]["first_matching_sample"] is None
    assert result["status"] == "fixture_observations_mismatch"


def test_matrix3_collision_requires_changed_actor_field_and_true_native_return(tmp_path):
    spec, evidence = matrix_v3(), capture_v4()
    spec["cases"][0]["runs"][1]["required_effect_checks"] = [effect_check()]
    evidence["attempt"]["mechanic_events"] = [mechanic_event(evidence)]
    result = inspect(tmp_path, spec=spec, evidence=evidence)
    assert result["status"] == "fixture_observations_match"
    assert result["effect_checks"][0]["matching_event_sequences"] == [0]
    event = evidence["attempt"]["mechanic_events"][0]
    event["native_return"] = False
    assert not inspect(tmp_path, spec=spec, evidence=evidence)["effect_checks"][0]["matched"]
    event["native_return"] = True
    event["state_before"]["player1"]["is_on_ground"] = True
    assert not inspect(tmp_path, spec=spec, evidence=evidence)["effect_checks"][0]["matched"]


@pytest.mark.parametrize("event", ["PlayerObject::collidedWithSlopeInternal", "PlayLayer::destroyPlayer"])
def test_matrix3_slope_and_death_require_actual_actor_transition(tmp_path, event):
    spec, evidence = matrix_v3(), capture_v4()
    requirement = effect_check(event=event)
    spec["cases"][0]["runs"][1]["required_effect_checks"] = [requirement]
    record = mechanic_event(evidence, event=event)
    field = requirement["player_change"]["field"]
    record["state_before"]["player1"][field] = False
    record["state_after"]["player1"][field] = True
    evidence["attempt"]["mechanic_events"] = [record]
    result = inspect(tmp_path, spec=spec, evidence=evidence)
    assert result["effect_checks"][0]["witnesses"][0]["player_transition"]["field"] == field
    record["object"]["group_ids"] = [2]
    assert not inspect(tmp_path, spec=spec, evidence=evidence)["effect_checks"][0]["matched"]


@pytest.mark.parametrize(
    "event",
    [
        "GJBaseGameLayer::triggerMoveCommand",
        "GJBaseGameLayer::toggleGroup",
        "GJBaseGameLayer::toggleGroupTriggered",
        "GJBaseGameLayer::spawnGroup",
    ],
)
def test_matrix3_group_callback_presence_alone_never_satisfies_applied_effect(tmp_path, event):
    spec, evidence = matrix_v3(), capture_v4()
    spec["cases"][0]["runs"][1]["required_effect_checks"] = [effect_check(event=event)]
    record = mechanic_event(evidence, event=event)
    evidence["attempt"]["mechanic_events"] = [record]
    assert not inspect(tmp_path, spec=spec, evidence=evidence)["effect_checks"][0]["matched"]
    record["watched_after"][0]["y"] = 120
    result = inspect(tmp_path, spec=spec, evidence=evidence)
    transition = result["effect_checks"][0]["witnesses"][0]["target_transition"]
    assert transition["source"] == "paired_native_callback"
    assert transition["before"] == 90
    assert transition["after"] == 120


def test_matrix3_actual_toggle_group_requires_watched_raw_flag_transition(tmp_path):
    spec, evidence = matrix_v3(), capture_v4()
    requirement = effect_check(event="GJBaseGameLayer::toggleGroup")
    requirement["target_change"] = {
        "group_id": 1,
        "field": "is_group_disabled",
        "before": False,
        "after": True,
    }
    spec["cases"][0]["runs"][1]["required_effect_checks"] = [requirement]
    record = mechanic_event(evidence, event="GJBaseGameLayer::toggleGroup")
    record["watched_after"][0]["is_group_disabled"] = True
    evidence["attempt"]["mechanic_events"] = [record]
    result = inspect(tmp_path, spec=spec, evidence=evidence)
    assert result["effect_checks"][0]["witnesses"][0]["target_transition"]["after"] is True
    record["arguments"]["group"] = 2
    assert not inspect(tmp_path, spec=spec, evidence=evidence)["effect_checks"][0]["matched"]


def add_later_pre_ending_sample(evidence):
    later = deepcopy(evidence["attempt"]["trace"][1])
    later["command_index"] = 2
    evidence["attempt"]["trace"][2]["command_index"] = 3
    evidence["attempt"]["trace"].insert(2, later)
    evidence["attempt"]["terminal"]["command_index"] = 3
    evidence["attempt"]["updates"][0]["command_index_after"] = 3
    evidence["attempt"]["scheduler_updates"][0]["command_index_after"] = 3
    evidence["attempt"]["phase_events"][0]["command_index"] = 3
    return later


def test_matrix3_async_target_transition_requires_strictly_later_pre_ending_command(tmp_path):
    spec, evidence = matrix_v3(), capture_v4()
    spec["cases"][0]["runs"][1]["required_effect_checks"] = [
        effect_check(event="GJBaseGameLayer::triggerMoveCommand")
    ]
    record = mechanic_event(evidence, event="GJBaseGameLayer::triggerMoveCommand")
    evidence["attempt"]["mechanic_events"] = [record]
    # A same-counter trace cannot establish that it followed the callback.
    evidence["attempt"]["trace"][1]["watched_objects"][0]["y"] = 120
    assert not inspect(tmp_path, spec=spec, evidence=evidence)["effect_checks"][0]["matched"]
    later = add_later_pre_ending_sample(evidence)
    later["watched_objects"][0]["y"] = 120
    result = inspect(tmp_path, spec=spec, evidence=evidence)
    transition = result["effect_checks"][0]["witnesses"][0]["target_transition"]
    assert transition["source"] == "later_pre_ending_command_sample"
    assert transition["command_index"] == 2
    assert result["effect_checks"][0]["witnesses"][0]["event_command_index"] == 1
    later["phase"]["level_end_animation_started"] = True
    assert not inspect(tmp_path, spec=spec, evidence=evidence)["effect_checks"][0]["matched"]


def test_matrix3_target_receipt_group_and_command_window_must_match(tmp_path):
    spec, evidence = matrix_v3(), capture_v4()
    check = effect_check(event="GJBaseGameLayer::triggerMoveCommand")
    spec["cases"][0]["runs"][1]["required_effect_checks"] = [check]
    record = mechanic_event(evidence, event=check["event"])
    record["watched_after"][0]["y"] = 120
    record["arguments"]["target_group_id"] = 2
    evidence["attempt"]["mechanic_events"] = [record]
    assert not inspect(tmp_path, spec=spec, evidence=evidence)["effect_checks"][0]["matched"]
    record["arguments"]["target_group_id"] = 1
    check["command_window"]["first"] = 2
    assert not inspect(tmp_path, spec=spec, evidence=evidence)["effect_checks"][0]["matched"]


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d["cases"][0].update(watch_groups=[1, 1]),
        lambda d: d["cases"][0].update(watch_groups=[True]),
        lambda d: d["cases"][0]["runs"][1].update(required_state_witnesses=[], required_effect_checks=[]),
        lambda d: d["cases"][0]["runs"][1]["required_state_witnesses"][0].update(min_samples=True),
        lambda d: d["cases"][0]["runs"][1]["required_state_witnesses"][0].update(min_samples=4),
        lambda d: d["cases"][0]["runs"][1]["required_state_witnesses"][0]["predicates"].update(
            is_on_ground=1
        ),
        lambda d: d["cases"][0]["runs"][1]["required_state_witnesses"][0]["predicates"].update(
            is_on_ground=None, is_on_slope=None
        ),
        lambda d: d["cases"][0]["runs"][1]["required_state_witnesses"][0]["predicates"].update(
            y={"minimum": 106, "maximum": 105}
        ),
        lambda d: d["cases"][0]["runs"][1]["required_effect_checks"][0].update(
            event="EffectGameObject::triggerObject"
        ),
        lambda d: d["cases"][0]["runs"][1]["required_effect_checks"][0].update(native_return=False),
        lambda d: d["cases"][0]["runs"][1]["required_effect_checks"][0].update(player_change=None),
        lambda d: d["cases"][0]["runs"][1]["required_effect_checks"][0].update(object_group_id=2),
        lambda d: d["cases"][0]["runs"][1]["required_effect_checks"][0]["player_change"].update(before=True),
    ],
)
def test_matrix3_strict_joint_and_effect_declarations_reject_invalid_constraints(change):
    spec = matrix_v3()
    spec["cases"][0]["runs"][1]["required_effect_checks"] = [effect_check()]
    change(spec)
    with pytest.raises(ValueError):
        validate_fixture_matrix(spec)


def test_matrix3_can_freeze_empty_owned_trigger_plans_without_input_response_claims(tmp_path):
    spec = matrix_v3()
    spec["cases"][0]["response_checks"] = []
    for run in spec["cases"][0]["runs"]:
        run["inputs"] = []
    evidence = capture_v4(plan=False)
    assert inspect(tmp_path, spec=spec, evidence=evidence)["status"] == "fixture_observations_match"


def test_schema4_ui_receipts_cannot_become_owned_fixture_response_evidence(tmp_path):
    spec = matrix_v2()
    reference, changed = capture_v4(plan=False), capture_v4(driver="scheduled-ui-callback")
    changed["attempt"]["trace"][1]["state"]["player1"]["y"] += 1
    result = response(tmp_path, spec=spec, reference=reference, changed=changed)
    assert result["first_difference"] is not None
    assert not result["checks"]["owned_replay_delivery_in_both_captures"]
    assert not result["checks"]["changed_requirements_match"]
    assert result["status"] == "selected_response_not_established"


def test_schema4_watched_initial_or_prefix_difference_blocks_owned_response(tmp_path):
    reference, changed = capture_v4(plan=False), capture_v4()
    changed["attempt"]["trace"][1]["state"]["player1"]["y"] += 1
    changed["attempt"]["trace"][0]["watched_objects"][0]["y"] += 1
    result = response(tmp_path, spec=matrix_v2(), reference=reference, changed=changed)
    assert not result["checks"]["same_selected_initial_watched_objects"]
    assert not result["checks"]["same_watched_prefix_before_changed_input"]
    assert result["status"] == "selected_response_not_established"
