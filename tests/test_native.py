"""The native file path can establish consistency, never authenticity."""

import hashlib
import json
from copy import deepcopy

import pytest

from axiom.cli import main
from axiom.native import (
    canonical_sha256,
    compare_native_captures,
    inspect_native_capture,
    load_native_capture,
)


def player(x=0.0, *, dead=False):
    return {"x": x, "y": 105.0, "y_velocity": 0.0, "rotation": 0.0, "is_dead": dead, "mode": "cube"}


def capture(*, attempt_id="synthetic-attempt-1", replay=True, outcome="completed"):
    environment = {
        "game_executable_sha256": "a" * 64,
        "game_version": "2.2081",
        "geode_version": "5.8.2",
        "adapter_binary_sha256": "b" * 64,
        "platform": "windows-x64",
        "mods": [{"id": "synthetic.axiom", "version": "0.1.0", "binary_sha256": "c" * 64}],
        "configuration_complete": False,
        "input_policy": "process-commands-pre-hook-owned-input-v1",
        "clocks": {
            "unit": "processCommands_call_index",
            "dt_unit": "seconds_as_passed_to_hook",
            "hardware_arrival": "unknown",
            "render_cadence": "not_captured",
        },
    }
    environment_sha = canonical_sha256(environment)
    return {
        "schema_version": 1,
        "kind": "native_capture",
        "provenance": {
            "origin": "synthetic",
            "independently_verified": False,
            "state_completeness": "selected_fields_only",
        },
        "collector": {
            "id": "synthetic.axiom",
            "version": "0.1.0",
            "source_commit": "d" * 40,
            "source_tree_sha256": "6" * 64,
            "sdk_commit": "e" * 40,
            "bindings_commit": "f" * 40,
        },
        "environment": environment,
        "environment_sha256": environment_sha,
        "challenge": {
            "id": "synthetic-fixture",
            "level_sha256": "1" * 64,
            "game_version": "2.2081",
            "physics_version": "recorded-processCommands-v1",
            "input_policy": environment["input_policy"],
            "environment_id": environment_sha,
        },
        "integrity": {"recording_complete": True, "dropped_records": 0, "errors": []},
        "state_fields": ["x", "y", "y_velocity", "rotation", "is_dead", "mode"],
        "attempt": {
            "id": attempt_id,
            "start_kind": "level_start",
            "input_source": "replay" if replay else "unknown",
            "replay_sha256": "2" * 64 if replay else None,
            "planned_inputs": [{"command_index": 1, "player": 1, "button": 1, "pressed": True}]
            if replay
            else [],
            "inputs": [
                {
                    "sequence": 0,
                    "command_index": 1,
                    "player": 1,
                    "button": 1,
                    "pressed": True,
                    "phase": "requested",
                    "source": "replay" if replay else "observed",
                    "native_return": None,
                    "wall_time_ns": 1_000_001,
                },
                {
                    "sequence": 1,
                    "command_index": 1,
                    "player": 1,
                    "button": 1,
                    "pressed": True,
                    "phase": "push",
                    "source": "replay" if replay else "observed",
                    "native_return": True,
                    "wall_time_ns": 1_000_002,
                },
            ],
            "blocked_inputs": [],
            "trace": [
                {
                    "command_index": 0,
                    "dt_seconds": 0.0,
                    "is_half_tick": False,
                    "is_last_tick": False,
                    "state": {"player1": player(), "player2": None},
                },
                {
                    "command_index": 1,
                    "dt_seconds": 1 / 240,
                    "is_half_tick": False,
                    "is_last_tick": True,
                    "state": {"player1": player(1), "player2": None},
                },
                {
                    "command_index": 2,
                    "dt_seconds": 1 / 240,
                    "is_half_tick": False,
                    "is_last_tick": True,
                    "state": {"player1": player(2, dead=outcome == "died"), "player2": None},
                },
            ],
            "terminal": {
                "outcome": outcome,
                "event": "PlayLayer::levelComplete" if outcome == "completed" else "PlayLayer::destroyPlayer",
                "command_index": 2,
                "wall_elapsed_seconds": 0.02,
                "state": {"player1": player(1.95, dead=outcome == "died"), "player2": None},
            },
        },
        "limitations": ["SYNTHETIC TEST FIXTURE", "Selected player fields only, no full-state proof"],
    }


def save(tmp_path, document, filename="capture.json"):
    path = tmp_path / filename
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def blocked_input(*, sequence=0, command_index=1, button=1, wall_time_ns=1_000_003):
    return {
        "sequence": sequence,
        "command_index": command_index,
        "player": 1,
        "button": button,
        "pressed": False,
        "source": "unknown",
        "wall_time_ns": wall_time_ns,
    }


def inspect(tmp_path, document):
    return inspect_native_capture(save(tmp_path, document))


def compare(tmp_path, first, second):
    return compare_native_captures(
        [
            save(tmp_path, first, "first.json"),
            save(tmp_path, second, "second.json"),
        ]
    )


def refresh_environment(document):
    digest = canonical_sha256(document["environment"])
    document["environment_sha256"] = digest
    document["challenge"]["environment_id"] = digest


def test_inspection_is_explicitly_unauthenticated_selected_evidence(tmp_path):
    data = capture(replay=False)
    report = inspect(tmp_path, data)
    assert report["status"] == "synthetic_fixture"
    assert report["authentication_status"] == "not_authenticated"
    assert report["physics_status"] == "not_independently_verified"
    assert report["m1_gate"] == "not_established_by_file_inspection"
    assert report["counts"] == {
        "input_records": 2,
        "blocked_input_records": 0,
        "state_records": 3,
        "planned_inputs": 0,
        "unexecuted_planned_tail": 0,
    }
    assert report["source_sha256"] == hashlib.sha256((tmp_path / "capture.json").read_bytes()).hexdigest()
    assert "inputs" not in report["attempt"]
    assert "blocked_inputs" not in report["attempt"]
    assert any("SYNTHETIC" in warning for warning in report["warnings"])
    assert any("not a controlled" in warning for warning in report["warnings"])
    json.dumps(report, allow_nan=False)


def test_native_origin_claim_does_not_authenticate_it(tmp_path):
    data = capture()
    data["provenance"]["origin"] = "native-engine-capture"
    report = inspect(tmp_path, data)
    assert report["status"] == "supplied_native_observer_evidence"
    assert report["authentication_status"] == "not_authenticated"
    assert report["m1_gate"] == "not_established_by_file_inspection"


def test_same_replay_exact_subset_consistency_excludes_wall_clock(tmp_path):
    first = capture()
    second = capture(attempt_id="synthetic-attempt-2")
    second["attempt"]["inputs"][0]["wall_time_ns"] += 10000
    second["attempt"]["inputs"][1]["wall_time_ns"] += 10000
    second["attempt"]["terminal"]["wall_elapsed_seconds"] = 0.5
    report = compare(tmp_path, first, second)
    assert report["status"] == "recorded_subset_consistent"
    assert report["complete_state_determinism"] == "not_established"
    assert report["authentication_status"] == "not_authenticated"
    assert report["comparisons"][0]["consistent"] is True
    assert report["m1_gate"] == "not_established_by_file_inspection"


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d["attempt"]["trace"][1]["state"]["player1"].update(x=1.001),
        lambda d: d["attempt"]["trace"][1].update(dt_seconds=1 / 120),
        lambda d: d["attempt"]["trace"][1].update(is_half_tick=True),
        lambda d: d["attempt"]["inputs"][1].update(native_return=False),
        lambda d: d["attempt"]["terminal"]["state"]["player1"].update(rotation=1),
    ],
)
def test_repeat_comparison_reports_specific_divergence(tmp_path, change):
    first = capture()
    second = capture(attempt_id="synthetic-attempt-2")
    change(second)
    report = compare(tmp_path, first, second)
    assert report["status"] == "recorded_subset_inconsistent"
    assert report["comparisons"][0]["consistent"] is False


def test_terminal_snapshot_is_separate_from_postprocess_snapshot(tmp_path):
    data = capture()
    assert data["attempt"]["terminal"]["state"] != data["attempt"]["trace"][-1]["state"]
    assert inspect(tmp_path, data)["terminal"]["outcome"] == "completed"


def test_death_terminal_is_valid_evidence_not_completion(tmp_path):
    data = capture(outcome="died")
    assert inspect(tmp_path, data)["terminal"]["outcome"] == "died"
    data["attempt"]["terminal"]["state"]["player1"]["is_dead"] = False
    with pytest.raises(ValueError, match="recorded dead player"):
        inspect(tmp_path, data)


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(schema_version=True),
        lambda d: d["provenance"].update(independently_verified=True),
        lambda d: d["provenance"].update(state_completeness="full"),
        lambda d: d["provenance"].update(origin=[]),
        lambda d: d["environment"].update(game_executable_sha256="unknown"),
        lambda d: d["environment"].update(configuration_complete="true"),
        lambda d: d["environment"]["clocks"].update(unit="physics_tick"),
        lambda d: d["environment"]["mods"][0].update(binary_sha256="unknown"),
        lambda d: d["challenge"].update(environment_id="other"),
        lambda d: d["challenge"].update(input_policy="other"),
        lambda d: d["integrity"].update(recording_complete=False),
        lambda d: d["integrity"].update(dropped_records=1),
        lambda d: d["integrity"].update(errors=["disk error"]),
        lambda d: d["attempt"].update(input_source=[]),
        lambda d: d["attempt"].update(start_kind=[]),
        lambda d: d["attempt"].update(replay_sha256=None),
        lambda d: d["attempt"]["trace"].pop(1),
        lambda d: d["attempt"]["trace"][0].update(dt_seconds=0.1),
        lambda d: d["attempt"]["trace"][0].update(is_last_tick=True),
        lambda d: d["attempt"]["trace"][1]["state"]["player1"].update(x=float("nan")),
        lambda d: d["attempt"]["trace"][1]["state"]["player1"].update(is_dead=0),
        lambda d: d["attempt"]["inputs"][0].update(sequence=1),
        lambda d: d["attempt"]["inputs"][0].update(command_index=3),
        lambda d: d["attempt"]["inputs"][0].update(command_index=1.0),
        lambda d: d["attempt"]["inputs"][0].update(player=True),
        lambda d: d["attempt"]["inputs"][0].update(pressed=1),
        lambda d: d["attempt"]["inputs"][0].update(native_return=True),
        lambda d: d["attempt"]["inputs"][1].update(phase=[]),
        lambda d: d["attempt"]["inputs"][1].update(native_return=None),
        lambda d: d["attempt"]["inputs"][1].update(pressed=False),
        lambda d: d["attempt"]["inputs"][1].update(source="observed"),
        lambda d: d["attempt"]["inputs"][1].update(wall_time_ns=1_000_000),
        lambda d: d["attempt"]["terminal"].update(outcome="error"),
        lambda d: d["attempt"]["terminal"].update(outcome="aborted"),
        lambda d: d["attempt"]["terminal"].update(outcome=[]),
        lambda d: d["attempt"]["terminal"].update(event="progress100"),
        lambda d: d["attempt"]["terminal"].update(command_index=1),
    ],
)
def test_malformed_partial_and_error_captures_rejected(tmp_path, change):
    data = capture()
    change(data)
    with pytest.raises(ValueError):
        inspect(tmp_path, data)


def test_canonical_environment_detects_changed_manifest(tmp_path):
    data = capture()
    data["environment"]["geode_version"] = "other"
    with pytest.raises(ValueError, match="environment_sha256"):
        inspect(tmp_path, data)
    refresh_environment(data)
    assert load_native_capture(save(tmp_path, data))["environment"]["geode_version"] == "other"


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d["challenge"].update(level_sha256="3" * 64),
        lambda d: d["collector"].update(bindings_commit="4" * 40),
        lambda d: d["attempt"].update(replay_sha256="4" * 64),
        lambda d: d["attempt"].update(id="synthetic-attempt-1"),
        lambda d: d["attempt"].update(start_kind="practice"),
        lambda d: d["attempt"].update(start_kind="start_position"),
    ],
)
def test_incompatible_or_nonfull_repetitions_rejected(tmp_path, change):
    first = capture()
    second = capture(attempt_id="synthetic-attempt-2")
    change(second)
    with pytest.raises(ValueError):
        compare(tmp_path, first, second)


def test_changed_build_or_mod_manifest_cannot_be_pooled(tmp_path):
    first = capture()
    second = capture(attempt_id="synthetic-attempt-2")
    second["environment"]["game_executable_sha256"] = "5" * 64
    refresh_environment(second)
    with pytest.raises(ValueError, match="Incompatible"):
        compare(tmp_path, first, second)


def test_observed_and_practice_files_can_be_inspected_but_not_replay_verified(tmp_path):
    first = capture(replay=False)
    second = capture(replay=False, attempt_id="synthetic-attempt-2")
    assert inspect(tmp_path, first)["attempt"]["input_source"] == "unknown"
    with pytest.raises(ValueError, match="controlled source-replay"):
        compare(tmp_path, first, second)
    first["attempt"]["start_kind"] = "practice"
    assert any("not a declared true" in warning for warning in inspect(tmp_path, first)["warnings"])


def test_duplicate_mods_and_empty_trace_rejected(tmp_path):
    data = capture()
    data["environment"]["mods"].append(deepcopy(data["environment"]["mods"][0]))
    refresh_environment(data)
    with pytest.raises(ValueError, match="Duplicate"):
        inspect(tmp_path, data)
    data = capture()
    data["attempt"]["trace"] = []
    with pytest.raises(ValueError, match="trace must contain"):
        inspect(tmp_path, data)


def test_comparison_requires_multiple_paths(tmp_path):
    path = save(tmp_path, capture())
    with pytest.raises(ValueError):
        compare_native_captures([path])
    with pytest.raises(ValueError):
        compare_native_captures(str(path))


def test_nanosecond_values_are_integer_and_precede_terminal(tmp_path):
    data = capture()
    path = save(tmp_path, data)
    loaded = load_native_capture(path)
    assert loaded["attempt"]["inputs"][0]["wall_time_ns"] == 1_000_001
    assert loaded["attempt"]["inputs"][1]["wall_time_ns"] == 1_000_002
    data["attempt"]["inputs"][1]["wall_time_ns"] = 2**53 + 1
    with pytest.raises(ValueError, match="after the reported terminal"):
        inspect(tmp_path, data)
    data["attempt"]["inputs"][1]["wall_time_ns"] = 1_000_002.0
    with pytest.raises(ValueError, match="integer"):
        inspect(tmp_path, data)


def test_replay_requests_must_match_planned_prefix(tmp_path):
    data = capture()
    data["attempt"]["planned_inputs"][0]["pressed"] = False
    with pytest.raises(ValueError, match="planned prefix"):
        inspect(tmp_path, data)
    data = capture()
    data["attempt"]["planned_inputs"].append({"command_index": 2, "player": 1, "button": 1, "pressed": False})
    with pytest.raises(ValueError, match="planned prefix"):
        inspect(tmp_path, data)


def test_plan_after_terminal_is_explicit_unexecuted_tail_not_full_playback(tmp_path):
    data = capture(outcome="died")
    data["attempt"]["planned_inputs"].append({"command_index": 3, "player": 1, "button": 1, "pressed": False})
    report = inspect(tmp_path, data)
    assert report["counts"]["unexecuted_planned_tail"] == 1
    assert report["replay_execution_status"] == "observed_prefix_through_terminal"
    second = deepcopy(data)
    second["attempt"]["id"] = "other"
    second["attempt"]["planned_inputs"][-1]["command_index"] = 4
    report = compare(tmp_path, data, second)
    assert report["status"] == "recorded_subset_inconsistent"
    assert report["comparisons"][0]["planned_inputs_equal"] is False


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d["collector"].update(source_tree_sha256="unknown"),
        lambda d: d["challenge"].update(game_version="other"),
        lambda d: d.update(state_fields=["x"]),
        lambda d: d.update(state_fields=[{}, "x", "y", "rotation", "is_dead", "mode"]),
        lambda d: d["attempt"]["planned_inputs"][0].update(command_index=0),
        lambda d: d["attempt"]["planned_inputs"][0].update(pressed=0),
    ],
)
def test_actual_collector_contract_additions_validated(tmp_path, change):
    data = capture()
    change(data)
    with pytest.raises(ValueError):
        inspect(tmp_path, data)


def test_cli_native_and_comparison_roundtrip(tmp_path, capsys):
    first_document = capture()
    first_document["attempt"]["blocked_inputs"] = [blocked_input()]
    first = save(tmp_path, first_document, "first.json")
    second = save(tmp_path, capture(attempt_id="other"), "second.json")
    assert main(["native", str(first)]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["kind"] == "native_capture_inspection"
    assert inspected["authentication_status"] == "not_authenticated"
    assert inspected["blocked_input_diagnostics"]["records"][0]["source"] == "unknown"
    output = tmp_path / "comparison.json"
    assert main(["native-compare", str(first), str(second), "--json", str(output)]) == 0
    compared = json.loads(output.read_text(encoding="utf-8"))
    assert compared["status"] == "recorded_subset_consistent"
    assert compared["m1_gate"] == "not_established_by_file_inspection"
    assert compared["blocked_input_diagnostics"]["status"] == "diagnostic_records_different"


def test_cli_comparison_rejects_single_file_and_bad_capture(tmp_path, capsys):
    path = save(tmp_path, capture())
    assert main(["native-compare", str(path)]) == 2
    assert "2 to 16" in capsys.readouterr().err
    data = capture()
    data["integrity"]["recording_complete"] = False
    path = save(tmp_path, data)
    assert main(["native", str(path)]) == 2
    assert "Incomplete native recording" in capsys.readouterr().err


def test_inactive_player_dead_flag_cannot_override_completion_callback(tmp_path):
    data = capture()
    data["attempt"]["terminal"]["state"]["player2"] = player(dead=True)
    report = inspect(tmp_path, data)
    assert report["terminal"]["outcome"] == "completed"
    assert any("player activity is not captured" in warning for warning in report["warnings"])


def test_blocked_requests_preserve_unknown_origin_and_no_counterfactual_claim(tmp_path):
    data = capture()
    data["attempt"]["blocked_inputs"] = [blocked_input(button=-2147483648)]
    report = inspect(tmp_path, data)
    assert report["counts"]["input_records"] == 2
    assert report["counts"]["blocked_input_records"] == 1
    diagnostic = report["blocked_input_diagnostics"]
    assert diagnostic["source"] == "unknown"
    assert diagnostic["delivery_status"] == "not_forwarded_to_native_handleButton"
    assert diagnostic["counterfactual_trajectory_effect"] == "not_measured"
    assert diagnostic["records"] == data["attempt"]["blocked_inputs"]
    assert "native_return" not in diagnostic["records"][0]
    assert "phase" not in diagnostic["records"][0]
    assert report["authentication_status"] == "not_authenticated"
    assert any("vanilla-input equivalence is not established" in warning for warning in report["warnings"])
    assert not any(key in report for key in ("ar", "human_ability", "human_input_count"))


def test_blocked_differences_are_reported_separately_from_delivered_consistency(tmp_path):
    first = capture()
    first["attempt"]["blocked_inputs"] = [blocked_input()]
    second = capture(attempt_id="other")
    second["attempt"]["blocked_inputs"] = [blocked_input(button=2147483647)]
    report = compare(tmp_path, first, second)
    assert report["status"] == "recorded_subset_consistent"
    row = report["comparisons"][0]
    assert row["recorded_inputs_equal"] is True
    assert row["blocked_inputs_equal"] is False
    assert row["consistent"] is True
    assert row["first_blocked_input_difference"]["baseline"]["button"] == 1
    assert row["first_blocked_input_difference"]["compared"]["button"] == 2147483647
    diagnostic = report["blocked_input_diagnostics"]
    assert diagnostic["status"] == "diagnostic_records_different"
    assert diagnostic["comparison_influence"] == "excluded_from_recorded_subset_consistency"
    assert diagnostic["counterfactual_trajectory_effect"] == "not_measured"
    assert [row["record_count"] for row in diagnostic["attempts"]] == [1, 1]


def test_blocked_timestamps_are_diagnostics_and_do_not_change_equality(tmp_path):
    first = capture()
    first["attempt"]["blocked_inputs"] = [blocked_input()]
    second = deepcopy(first)
    second["attempt"]["id"] = "other"
    second["attempt"]["blocked_inputs"][0]["wall_time_ns"] += 1000
    report = compare(tmp_path, first, second)
    assert report["status"] == "recorded_subset_consistent"
    assert report["comparisons"][0]["blocked_inputs_equal"] is True
    assert report["comparisons"][0]["first_blocked_input_difference"] is None


def test_blocked_count_difference_preserves_missing_record_diagnostic(tmp_path):
    first = capture()
    second = capture(attempt_id="other")
    second["attempt"]["blocked_inputs"] = [blocked_input()]
    report = compare(tmp_path, first, second)
    assert report["status"] == "recorded_subset_consistent"
    difference = report["comparisons"][0]["first_blocked_input_difference"]
    assert difference["sequence"] == 0
    assert difference["baseline"] is None
    assert difference["compared"]["source"] == "unknown"


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d["attempt"].pop("blocked_inputs"),
        lambda d: d["attempt"].update(blocked_inputs={}),
        lambda d: d["attempt"]["blocked_inputs"][0].update(sequence=1),
        lambda d: d["attempt"]["blocked_inputs"][0].update(command_index=3),
        lambda d: d["attempt"]["blocked_inputs"][0].update(command_index=True),
        lambda d: d["attempt"]["blocked_inputs"][0].update(player=0),
        lambda d: d["attempt"]["blocked_inputs"][0].update(player=True),
        lambda d: d["attempt"]["blocked_inputs"][0].update(pressed=0),
        lambda d: d["attempt"]["blocked_inputs"][0].update(button=2147483648),
        lambda d: d["attempt"]["blocked_inputs"][0].update(button=-2147483649),
        lambda d: d["attempt"]["blocked_inputs"][0].update(button=True),
        lambda d: d["attempt"]["blocked_inputs"][0].update(source="human"),
        lambda d: d["attempt"]["blocked_inputs"][0].update(source="replay"),
        lambda d: d["attempt"]["blocked_inputs"][0].update(source="observed"),
        lambda d: d["attempt"]["blocked_inputs"][0].update(native_return=False),
        lambda d: d["attempt"]["blocked_inputs"][0].update(phase="requested"),
        lambda d: d["attempt"]["blocked_inputs"][0].update(wall_time_ns=-1),
        lambda d: d["attempt"]["blocked_inputs"][0].update(wall_time_ns=1_000_003.0),
        lambda d: d["attempt"]["blocked_inputs"][0].update(wall_time_ns=20_001_001),
    ],
)
def test_malformed_and_delivered_claims_in_blocked_diagnostics_rejected(tmp_path, change):
    data = capture()
    data["attempt"]["blocked_inputs"] = [blocked_input()]
    change(data)
    with pytest.raises(ValueError):
        inspect(tmp_path, data)


@pytest.mark.parametrize("field,value", [("command_index", 0), ("wall_time_ns", 1_000_002), ("sequence", 2)])
def test_blocked_stream_is_independently_contiguous_and_monotone(tmp_path, field, value):
    data = capture()
    data["attempt"]["blocked_inputs"] = [blocked_input(), blocked_input(sequence=1)]
    data["attempt"]["blocked_inputs"][1][field] = value
    with pytest.raises(ValueError):
        inspect(tmp_path, data)


def test_observed_attempt_cannot_claim_suppression_or_replay_delivery(tmp_path):
    data = capture(replay=False)
    data["attempt"]["blocked_inputs"] = [blocked_input()]
    with pytest.raises(ValueError, match="Only a replay"):
        inspect(tmp_path, data)
    data["attempt"]["blocked_inputs"] = []
    data["attempt"]["inputs"][0]["source"] = "replay"
    with pytest.raises(ValueError, match="delivered replay input"):
        inspect(tmp_path, data)


def test_blocked_diagnostic_cannot_be_moved_to_delivered_input_stream(tmp_path):
    data = capture()
    data["attempt"]["inputs"].append(blocked_input(sequence=2))
    with pytest.raises(ValueError, match="missing"):
        inspect(tmp_path, data)


@pytest.mark.parametrize("blocked_count,valid", [(11998, True), (11999, False)])
def test_input_limit_is_shared_with_blocked_diagnostics(tmp_path, blocked_count, valid):
    data = capture()
    data["attempt"]["blocked_inputs"] = [blocked_input(sequence=i) for i in range(blocked_count)]
    if valid:
        assert inspect(tmp_path, data)["counts"]["blocked_input_records"] == blocked_count
    else:
        with pytest.raises(ValueError, match="together"):
            inspect(tmp_path, data)


def test_old_input_policy_cannot_be_mislabeled_as_owned_channel_capture(tmp_path):
    data = capture()
    data["environment"]["input_policy"] = "process-commands-pre-hook-v1"
    data["challenge"]["input_policy"] = data["environment"]["input_policy"]
    refresh_environment(data)
    with pytest.raises(ValueError, match="owned-input"):
        inspect(tmp_path, data)


@pytest.mark.parametrize(
    "field,value", [("dt_seconds", 1 / 120), ("is_half_tick", True), ("is_last_tick", False)]
)
def test_command_arguments_are_distinct_from_matching_player_fields(tmp_path, field, value):
    first = capture()
    second = capture(attempt_id="other")
    second["attempt"]["trace"][1][field] = value
    report = compare(tmp_path, first, second)
    row = report["comparisons"][0]
    assert report["status"] == "recorded_subset_inconsistent"
    assert row["recorded_state_equal"] is False
    assert row["recorded_call_arguments_equal"] is False
    assert row["recorded_player_fields_equal"] is True
    assert row["terminal_callback_and_placement_equal"] is True
    assert row["terminal_player_fields_equal"] is True
    diagnostic = row["call_argument_diagnostics"]
    assert diagnostic["differing_common_records"] == 1
    assert diagnostic["unmatched_record_count"] == 0
    assert diagnostic["first_different_call_index"] == 1
    assert diagnostic["field_differences"][field]["compared"] == value
    assert row["player_field_diagnostics"]["first_difference"] is None
    assert report["component_consistency"]["recorded_call_arguments_equal"] is False
    assert report["component_consistency"]["recorded_player_fields_equal"] is True


def test_rotation_is_a_strict_player_field_with_separate_exact_diagnostics(tmp_path):
    first = capture()
    second = capture(attempt_id="other")
    second["attempt"]["trace"][1]["state"]["player1"]["rotation"] = 1e-12
    second["attempt"]["trace"][2]["state"]["player1"]["rotation"] = 2e-12
    report = compare(tmp_path, first, second)
    row = report["comparisons"][0]
    assert report["status"] == "recorded_subset_inconsistent"
    assert row["recorded_call_arguments_equal"] is True
    assert row["recorded_player_fields_equal"] is False
    assert row["terminal_equal"] is True
    diagnostic = row["player_field_diagnostics"]
    assert diagnostic["differing_common_records"] == 2
    assert diagnostic["first_different_call_index"] == 1
    assert diagnostic["field_differences"] == {
        "player1.rotation": {
            "differing_common_records": 2,
            "first_different_call_index": 1,
            "baseline": 0.0,
            "compared": 1e-12,
        }
    }


def test_terminal_rotation_difference_cannot_be_hidden_by_matching_completion(tmp_path):
    first = capture()
    second = capture(attempt_id="other")
    second["attempt"]["terminal"]["state"]["player1"]["rotation"] = 1
    report = compare(tmp_path, first, second)
    row = report["comparisons"][0]
    assert report["status"] == "recorded_subset_inconsistent"
    assert row["recorded_state_equal"] is True
    assert row["terminal_equal"] is False
    assert row["terminal_callback_and_placement_equal"] is True
    assert row["terminal_player_fields_equal"] is False
    assert row["terminal_diagnostics"]["callback_and_placement_differences"] == {}
    assert row["terminal_diagnostics"]["selected_player_field_differences"] == {
        "player1.rotation": {"baseline": 0.0, "compared": 1}
    }
    assert report["component_consistency"]["terminal_player_fields_equal"] is False


def test_player_presence_and_missing_trace_tail_are_reported_explicitly(tmp_path):
    first = capture()
    second = capture(attempt_id="other")
    second["attempt"]["trace"][1]["state"]["player2"] = player()
    report = compare(tmp_path, first, second)
    diagnostic = report["comparisons"][0]["player_field_diagnostics"]
    assert diagnostic["field_differences"]["player2.present"]["baseline"] is False
    assert diagnostic["field_differences"]["player2.present"]["compared"] is True
    second = capture(attempt_id="other")
    second["attempt"]["trace"].pop()
    second["attempt"]["terminal"]["command_index"] = 1
    report = compare(tmp_path, first, second)
    row = report["comparisons"][0]
    assert row["call_argument_diagnostics"]["differing_common_records"] == 0
    assert row["call_argument_diagnostics"]["unmatched_record_count"] == 1
    assert row["call_argument_diagnostics"]["first_different_call_index"] == 2
    assert row["call_argument_diagnostics"]["first_difference"]["compared"] is None
    assert row["player_field_diagnostics"]["unmatched_record_count"] == 1
    assert row["terminal_callback_and_placement_equal"] is False
    assert row["terminal_player_fields_equal"] is True
    assert row["terminal_diagnostics"]["callback_and_placement_differences"] == {
        "command_index": {"baseline": 2, "compared": 1}
    }


def test_native_input_return_difference_still_fails_when_other_components_match(tmp_path):
    first = capture()
    second = capture(attempt_id="other")
    second["attempt"]["inputs"][1]["native_return"] = False
    report = compare(tmp_path, first, second)
    row = report["comparisons"][0]
    assert row["recorded_inputs_equal"] is False
    assert row["recorded_call_arguments_equal"] is True
    assert row["recorded_player_fields_equal"] is True
    assert row["terminal_callback_and_placement_equal"] is True
    assert row["terminal_player_fields_equal"] is True
    assert row["consistent"] is False
