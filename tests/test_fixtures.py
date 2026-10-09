"""Constructed geometry is intent; requirements depend on supplied observations."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

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


@pytest.mark.parametrize("version", [True, 1.0, 2, "1"])
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
