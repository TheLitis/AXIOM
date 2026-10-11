"""The native file path can establish consistency, never authenticity."""

import hashlib
import json
import struct
from copy import deepcopy

import pytest

from axiom.cli import main
from axiom.native import (
    INPUT_POLICY_V4,
    LEGACY_INPUT_POLICY,
    canonical_sha256,
    compare_native_captures,
    delivery_context_signature,
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


def rich_capture(*, attempt_id="synthetic-attempt-1", policy="native"):
    data = capture(attempt_id=attempt_id)
    data["schema_version"] = 2
    hooks = {
        "native": "none",
        "fixed-base-60": "GJBaseGameLayer::update",
        "fixed-scheduler-240": "CCScheduler::update",
    }
    denominator = {"native": 1, "fixed-base-60": 60, "fixed-scheduler-240": 240}[policy]
    data["environment"]["clocks"].update(
        clock_policy=policy,
        intervention_hook=hooks[policy],
        step_numerator=0 if policy == "native" else 1,
        step_denominator=denominator,
        intervention_scope="guarded-sandbox-process",
        update_unit="GJBaseGameLayer::update_call_index",
        scheduler_unit="CCScheduler::update_call_index",
    )
    refresh_environment(data)
    before = {"level_end_animation_started": False, "has_completed_level": False}
    transition = {"level_end_animation_started": True, "has_completed_level": False}
    completed = {"level_end_animation_started": True, "has_completed_level": True}
    for index, row in enumerate(data["attempt"]["trace"]):
        row.update(
            phase=deepcopy(completed if index == 2 else before),
            update_sequence=0 if index else None,
            scheduler_sequence=0 if index else None,
        )
    data["attempt"]["terminal"].update(phase=deepcopy(completed), update_sequence=0, scheduler_sequence=0)
    fixed = struct.unpack("f", struct.pack("f", 1 / denominator))[0]
    update = {
        "sequence": 0,
        "parent_sequence": None,
        "original_dt_seconds": 0.02,
        "delivered_dt_seconds": fixed if policy == "fixed-base-60" else 0.02,
        "command_index_before": 0,
        "command_index_after": 2,
        "phase_before": deepcopy(before),
        "phase_after": deepcopy(completed),
        "wall_enter_ns": 0,
        "wall_exit_ns": 21_000_000,
        "scheduler_sequence": 0,
    }
    scheduler = {key: value for key, value in deepcopy(update).items() if key != "scheduler_sequence"}
    scheduler["delivered_dt_seconds"] = fixed if policy == "fixed-scheduler-240" else 0.02
    scheduler["wall_exit_ns"] = 22_000_000
    data["attempt"].update(
        updates=[update],
        scheduler_updates=[scheduler],
        phase_events=[
            {
                "sequence": 0,
                "event": "PlayLayer::playEndAnimationToPos",
                "command_index": 2,
                "update_sequence": 0,
                "scheduler_sequence": 0,
                "phase_before": deepcopy(before),
                "phase_after": transition,
                "wall_enter_ns": 1_500_000,
                "wall_exit_ns": 1_600_000,
            }
        ],
    )
    return data


def mechanics_capture(*, attempt_id="synthetic-attempt-1", policy="native"):
    """Schema-3 synthetic raw observations, with no inferred mechanic coverage."""
    data = rich_capture(attempt_id=attempt_id, policy=policy)
    data["schema_version"] = 3
    data["state_fields"] += ["gravity_inverted", "vehicle_size", "player_speed"]
    data["layer_state_fields"] = ["dual_active"]
    for sample in [*data["attempt"]["trace"], data["attempt"]["terminal"]]:
        sample["state"]["dual_active"] = False
        for name in ("player1", "player2"):
            if sample["state"][name] is not None:
                sample["state"][name].update(gravity_inverted=False, vehicle_size=1.0, player_speed=0.9)
    return data


def collision_capture(*, attempt_id="synthetic-attempt-1", policy="native", driver="owned-pre-command"):
    """Schema-4 synthetic observations, never proof of real native execution."""
    data = mechanics_capture(attempt_id=attempt_id, policy=policy)
    data["schema_version"] = 4
    data["state_fields"] += ["is_on_ground", "is_on_slope"]
    data["environment"]["input_policy"] = INPUT_POLICY_V4
    data["challenge"]["input_policy"] = INPUT_POLICY_V4
    refresh_environment(data)
    data["object_watches"] = [{"group_id": 1, "object_id": 1, "runtime_unique_id": 42}]
    watch = {"group_id": 1, "x": 30.0, "y": 90.0, "is_group_disabled": False, "is_disabled": False}
    for row in [*data["attempt"]["trace"], data["attempt"]["terminal"]]:
        row["watched_objects"] = [deepcopy(watch)]
        for actor in ("player1", "player2"):
            if row["state"][actor] is not None:
                row["state"][actor].update(is_on_ground=True, is_on_slope=False)
    delivery = {
        "none": ("unknown", None, "none", "not-applicable"),
        "owned-pre-command": (
            "synthetic-scheduled",
            "GJBaseGameLayer::handleButton",
            "processCommands-entry-before-original",
            "not-applicable",
        ),
        "scheduled-ui-callback": (
            "synthetic-scheduled",
            "UILayer::keyDown/keyUp",
            "processCommands-entry-before-original",
            "layer-m_timestamp",
        ),
    }[driver]
    data["attempt"]["input_delivery"] = dict(
        zip(
            ("driver", "provenance", "entry_point", "injection_phase", "timestamp_policy"),
            (driver, *delivery),
        )
    )
    for event in data["attempt"]["inputs"]:
        event.update(in_command=True, update_sequence=0, scheduler_sequence=0)
        event["source"] = "replay" if driver == "owned-pre-command" else "observed"
    if driver == "none":
        data["attempt"].update(input_source="unknown", replay_sha256=None, planned_inputs=[])
    data["attempt"].update(delivery_events=[], mechanic_events=[])
    return data


schema4_capture = collision_capture


def input_entry_capture(*, attempt_id="synthetic-attempt-1", policy="native", driver="owned-pre-command"):
    """Schema-5 synthetic input entries; no authenticated native/physical origin."""
    data = collision_capture(attempt_id=attempt_id, policy=policy, driver=driver)
    data["schema_version"] = 5
    return data


schema5_capture = input_entry_capture


def mechanic_event(document, *, event="PlayerObject::collidedWithObject"):
    phase = {"level_end_animation_started": False, "has_completed_level": False}
    before = deepcopy(document["attempt"]["trace"][1]["state"])
    after = deepcopy(before)
    before["player1"]["is_on_ground"] = False
    record = {
        "sequence": 0,
        "parent_sequence": None,
        "event": event,
        "command_index": 1,
        "in_command": True,
        "update_sequence": 0,
        "scheduler_sequence": 0,
        "player": 1,
        "object": {"object_id": 1, "runtime_unique_id": 42, "group_ids": [1]},
        "arguments": {
            "dt_seconds": 1 / 240,
            "rect": {"x": 0, "y": 0, "width": 30, "height": 30},
            "skip_check": False,
        },
        "state_before": before,
        "state_after": after,
        "watched_before": deepcopy(document["attempt"]["trace"][1]["watched_objects"]),
        "watched_after": deepcopy(document["attempt"]["trace"][1]["watched_objects"]),
        "phase_before": deepcopy(phase),
        "phase_after": deepcopy(phase),
        "native_return": True,
        "wall_enter_ns": 1_000_003,
        "wall_exit_ns": 1_000_005,
    }
    payloads = {
        "PlayerObject::updateCollide": {"direction": 1},
        "PlayerObject::collidedWithSlopeInternal": {"dt_seconds": 1 / 240, "forced": False},
        "PlayLayer::destroyPlayer": {},
        "GJBaseGameLayer::triggerMoveCommand": {
            "target_group_id": 1,
            "duration": 0.5,
            "move_offset_x": 0,
            "move_offset_y": 30,
        },
        "GJBaseGameLayer::toggleGroupTriggered": {
            "group": 1,
            "activate": False,
            "remap_keys": [],
            "trigger_id": 0,
            "control_id": 0,
        },
        "GJBaseGameLayer::toggleGroup": {"group": 1, "activate": False},
        "GJBaseGameLayer::spawnGroup": {
            "group": 1,
            "ordered": False,
            "delay": 0.5,
            "remap_keys": [],
            "trigger_id": 0,
            "control_id": 0,
        },
        "EffectGameObject::triggerObject": {"unique_id": 0, "remap_keys": None},
    }
    if event in payloads:
        record.update(arguments=payloads[event], native_return=None)
    if not event.startswith("PlayerObject::") and event != "PlayLayer::destroyPlayer":
        record["player"] = None
    if event in {
        "GJBaseGameLayer::toggleGroup",
        "GJBaseGameLayer::toggleGroupTriggered",
        "GJBaseGameLayer::spawnGroup",
    }:
        record["object"] = None
    return record


def delivery_event(*, event="UILayer::keyDown"):
    phase = {"level_end_animation_started": False, "has_completed_level": False}
    queue = [{"button": 1, "pressed": True, "player": 1, "step": 1, "timestamp": 0.004}]
    return {
        "sequence": 0,
        "parent_sequence": None,
        "event": event,
        "command_index": 1,
        "in_command": True,
        "update_sequence": 0,
        "scheduler_sequence": 0,
        "arguments": {"key_code": 32, "timestamp": 0.004},
        "queue_before": [],
        "queue_after": queue,
        "layer_timestamp_before": 0.004,
        "layer_timestamp_after": 0.004,
        "phase_before": deepcopy(phase),
        "phase_after": deepcopy(phase),
        "wall_enter_ns": 1_000_003,
        "wall_exit_ns": 1_000_005,
    }


def mechanics_sample(document, sample):
    return (
        document["attempt"]["terminal"]["state"]
        if sample == "terminal"
        else document["attempt"]["trace"][sample]["state"]
    )


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


def test_legacy_input_policy_can_be_inspected_without_claiming_owned_channel(tmp_path):
    data = capture()
    data["environment"]["input_policy"] = "process-commands-pre-hook-v1"
    data["challenge"]["input_policy"] = data["environment"]["input_policy"]
    data["attempt"].pop("blocked_inputs")
    refresh_environment(data)
    report = inspect(tmp_path, data)
    assert report["capture_schema_version"] == 1
    assert report["blocked_input_diagnostics"]["status"] == "not_recorded_legacy_policy"
    assert report["blocked_input_diagnostics"]["delivery_status"] == "not_recorded"
    assert any("legacy input policy" in warning for warning in report["warnings"])
    data["attempt"]["blocked_inputs"] = []
    with pytest.raises(ValueError, match="unknown blocked_inputs"):
        inspect(tmp_path, data)


def test_legacy_comparison_cannot_invent_absent_diagnostics(tmp_path):
    first = capture()
    first["environment"]["input_policy"] = "process-commands-pre-hook-v1"
    first["challenge"]["input_policy"] = first["environment"]["input_policy"]
    first["attempt"].pop("blocked_inputs")
    refresh_environment(first)
    second = deepcopy(first)
    second["attempt"]["id"] = "other"
    report = compare(tmp_path, first, second)
    assert report["status"] == "recorded_subset_consistent"
    assert report["blocked_input_diagnostics"]["status"] == "not_recorded_legacy_policy"
    assert report["blocked_input_diagnostics"]["delivery_status"] == "not_recorded"
    assert any("legacy input policy" in warning for warning in report["warnings"])


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


@pytest.mark.parametrize("policy", ["native", "fixed-base-60", "fixed-scheduler-240"])
def test_schema2_inspection_records_clock_phase_and_paired_cadence(tmp_path, policy):
    data = rich_capture(policy=policy)
    report = inspect(tmp_path, data)
    assert report["capture_schema_version"] == 2
    observations = report["native_cadence_observations"]
    assert observations["status"] == "recorded"
    assert observations["clock_identity"]["clock_policy"] == policy
    assert observations["original_dt_and_wall_cadence"] == "diagnostic_only"
    assert observations["render_cadence"] == "not_captured"
    assert observations["updates"] == data["attempt"]["updates"]
    assert observations["scheduler_updates"] == data["attempt"]["scheduler_updates"]
    assert report["terminal"]["phase"]["has_completed_level"] is True
    assert report["m1_gate"] == "not_established_by_file_inspection"
    assert not any(key in report["attempt"] for key in ("updates", "scheduler_updates", "phase_events"))


def test_schema1_phase_prefix_is_unavailable_instead_of_guessed(tmp_path):
    report = compare(tmp_path, capture(), capture(attempt_id="other"))
    assert report["comparisons"][0]["pre_end_animation_diagnostics"]["status"] == "not_recorded_schema1"
    assert inspect(tmp_path, capture())["native_cadence_observations"]["status"] == "not_recorded_schema1"


def test_schema2_matching_prefix_never_greenlights_differing_full_rotation(tmp_path):
    first = rich_capture()
    second = rich_capture(attempt_id="other")
    second["attempt"]["trace"][2]["state"]["player1"]["rotation"] = 1e-12
    report = compare(tmp_path, first, second)
    assert report["status"] == "recorded_subset_inconsistent"
    prefix = report["comparisons"][0]["pre_end_animation_diagnostics"]
    assert prefix["status"] == "available"
    assert prefix["consistent"] is True
    assert prefix["full_comparison_influence"] == "none"
    assert prefix["m1_gate"] == "not_established_by_prefix_comparison"
    assert prefix["player_field_diagnostics"]["baseline_record_count"] == 2


def test_schema2_original_fixed_clock_dt_is_explicitly_diagnostic_not_silent(tmp_path):
    first = rich_capture(policy="fixed-base-60")
    second = rich_capture(policy="fixed-base-60", attempt_id="other")
    second["attempt"]["updates"][0]["original_dt_seconds"] = 0.03
    second["attempt"]["updates"][0]["wall_exit_ns"] += 1000
    report = compare(tmp_path, first, second)
    assert report["status"] == "recorded_subset_consistent"
    rich = report["comparisons"][0]["rich_observation_diagnostics"]
    assert rich["update_records"]["equal"] is True
    diagnostics = rich["original_cadence_diagnostics"]["updates"]
    assert diagnostics["original_dt"]["equal"] is False
    assert diagnostics["original_dt"]["first_difference"]["compared"] == {"original_dt_seconds": 0.03}
    assert diagnostics["wall_cadence"]["equal"] is False
    assert diagnostics["comparison_influence"] == "excluded_original_dt_and_wall_cadence"


def test_schema2_delivered_cadence_difference_still_fails_full_comparison(tmp_path):
    first = rich_capture()
    second = rich_capture(attempt_id="other")
    second["attempt"]["updates"][0].update(original_dt_seconds=0.03, delivered_dt_seconds=0.03)
    report = compare(tmp_path, first, second)
    assert report["status"] == "recorded_subset_inconsistent"
    assert report["component_consistency"]["delivered_update_records_equal"] is False
    assert report["comparisons"][0]["rich_observation_diagnostics"]["update_records"]["equal"] is False


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d["environment"]["clocks"].update(step_denominator=60.0),
        lambda d: d["environment"]["clocks"].update(step_numerator=True),
        lambda d: d["environment"]["clocks"].update(intervention_hook="CCScheduler::update"),
        lambda d: d["environment"]["clocks"].update(intervention_scope="ordinary-game"),
        lambda d: d["attempt"].pop("phase_events"),
        lambda d: d["attempt"]["trace"][1]["phase"].update(has_completed_level=1),
        lambda d: d["attempt"]["trace"][0].update(update_sequence=0),
        lambda d: d["attempt"]["trace"][1].update(scheduler_sequence=1),
        lambda d: d["attempt"]["updates"][0].update(sequence=1),
        lambda d: d["attempt"]["updates"][0].update(parent_sequence=0),
        lambda d: d["attempt"]["updates"][0].update(command_index_after=3),
        lambda d: d["attempt"]["updates"][0].update(wall_exit_ns=-1),
        lambda d: d["attempt"]["updates"][0].update(delivered_dt_seconds=1 / 60),
        lambda d: d["attempt"]["scheduler_updates"][0].update(wall_exit_ns=20_500_000),
        lambda d: d["attempt"]["terminal"].update(update_sequence=1),
        lambda d: d["attempt"]["phase_events"][0].update(event="guessed-finish"),
        lambda d: d["attempt"]["phase_events"][0].update(sequence=1),
        lambda d: d["attempt"]["phase_events"][0].update(wall_enter_ns=23_000_000, wall_exit_ns=24_000_000),
    ],
)
def test_schema2_malformed_clock_context_phase_and_partial_pairs_rejected(tmp_path, change):
    data = rich_capture(policy="fixed-base-60")
    change(data)
    refresh_environment(data)
    with pytest.raises(ValueError):
        inspect(tmp_path, data)


@pytest.mark.parametrize("kind", ["missing", "revert", "early", "multiple"])
def test_schema2_prefix_requires_unique_recorded_phase_transition(tmp_path, kind):
    first = rich_capture()
    second = rich_capture(attempt_id="other")
    for data in (first, second):
        if kind == "missing":
            data["attempt"]["phase_events"] = []
        elif kind == "revert":
            data["attempt"]["trace"][2]["phase"]["level_end_animation_started"] = False
        elif kind == "early":
            data["attempt"]["trace"][0]["phase"]["level_end_animation_started"] = True
        else:
            event = deepcopy(data["attempt"]["phase_events"][0])
            event["sequence"] = 1
            data["attempt"]["phase_events"].append(event)
    report = compare(tmp_path, first, second)
    assert report["status"] == "recorded_subset_consistent"
    prefix = report["comparisons"][0]["pre_end_animation_diagnostics"]
    assert prefix["status"] == "not_available"
    assert prefix["full_comparison_influence"] == "none"


def test_schema2_different_boundary_and_early_flags_remain_strict(tmp_path):
    first = rich_capture()
    second = rich_capture(attempt_id="other")
    second["attempt"]["phase_events"][0]["command_index"] = 1
    second["attempt"]["trace"][1]["phase"]["level_end_animation_started"] = True
    report = compare(tmp_path, first, second)
    assert report["status"] == "recorded_subset_inconsistent"
    assert report["component_consistency"]["recorded_native_phase_equal"] is False
    assert report["component_consistency"]["native_phase_events_equal"] is False
    prefix = report["comparisons"][0]["pre_end_animation_diagnostics"]
    assert prefix["status"] == "available"
    assert prefix["boundary_equal"] is False
    assert prefix["consistent"] is False
    assert prefix["call_argument_diagnostics"]["unmatched_record_count"] == 1


def test_schema2_recursive_paired_updates_and_terminal_before_outer_exit_are_valid(tmp_path):
    data = rich_capture()
    child = deepcopy(data["attempt"]["updates"][0])
    child.update(sequence=1, parent_sequence=0, wall_enter_ns=500_000, wall_exit_ns=20_500_000)
    data["attempt"]["updates"].append(child)
    data["attempt"]["trace"][1]["update_sequence"] = 1
    data["attempt"]["trace"][2]["update_sequence"] = 1
    data["attempt"]["terminal"]["update_sequence"] = 1
    assert inspect(tmp_path, data)["native_cadence_observations"]["updates"][1]["parent_sequence"] == 0
    child["wall_exit_ns"] = 22_000_000
    with pytest.raises(ValueError, match="outside its parent"):
        inspect(tmp_path, data)


def test_schema2_versions_and_clock_interventions_cannot_be_pooled(tmp_path):
    with pytest.raises(ValueError, match="schema_version"):
        compare(tmp_path, capture(), rich_capture(attempt_id="other"))
    with pytest.raises(ValueError, match="Incompatible"):
        compare(
            tmp_path,
            rich_capture(policy="fixed-base-60"),
            rich_capture(policy="fixed-scheduler-240", attempt_id="other"),
        )


def test_schema2_cli_roundtrip_and_clock_identity_rejection(tmp_path, capsys):
    first = save(tmp_path, rich_capture(policy="fixed-scheduler-240"), "first.json")
    second = save(tmp_path, rich_capture(policy="fixed-scheduler-240", attempt_id="other"), "second.json")
    assert main(["native", str(first)]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["capture_schema_version"] == 2
    assert inspected["native_cadence_observations"]["clock_identity"]["clock_policy"] == "fixed-scheduler-240"
    output = tmp_path / "rich-comparison.json"
    assert main(["native-compare", str(first), str(second), "--json", str(output)]) == 0
    compared = json.loads(output.read_text())
    assert compared["status"] == "recorded_subset_consistent"
    assert compared["component_consistency"]["delivered_scheduler_records_equal"] is True
    assert compared["comparisons"][0]["pre_end_animation_diagnostics"]["consistent"] is True
    assert compared["m1_gate"] == "not_established_by_file_inspection"
    third = save(tmp_path, rich_capture(policy="fixed-base-60", attempt_id="third"), "third.json")
    assert main(["native-compare", str(first), str(third)]) == 2
    assert "Incompatible" in capsys.readouterr().err


def test_schema2_sibling_overlap_and_false_trace_membership_rejected(tmp_path):
    data = rich_capture()
    first_child = deepcopy(data["attempt"]["updates"][0])
    first_child.update(
        sequence=1, parent_sequence=0, wall_enter_ns=500_000, wall_exit_ns=10_000_000, command_index_after=1
    )
    second_child = deepcopy(first_child)
    second_child.update(
        sequence=2,
        wall_enter_ns=500_001,
        wall_exit_ns=20_500_000,
        command_index_before=1,
        command_index_after=2,
    )
    data["attempt"]["updates"].extend([first_child, second_child])
    with pytest.raises(ValueError, match="sibling records overlap"):
        inspect(tmp_path, data)
    data = rich_capture()
    child = deepcopy(data["attempt"]["updates"][0])
    child.update(
        sequence=1, parent_sequence=0, wall_enter_ns=500_000, wall_exit_ns=20_500_000, command_index_before=1
    )
    data["attempt"]["updates"].append(child)
    data["attempt"]["trace"][1]["update_sequence"] = 1
    with pytest.raises(ValueError, match="must follow the entry counter"):
        inspect(tmp_path, data)


def test_schema2_capture_begun_inside_unrecorded_outer_context_does_not_invent_membership(tmp_path):
    data = rich_capture()
    data["attempt"]["updates"][0]["scheduler_sequence"] = None
    data["attempt"]["scheduler_updates"] = []
    for row in [*data["attempt"]["trace"], data["attempt"]["terminal"], *data["attempt"]["phase_events"]]:
        row["scheduler_sequence"] = None
    report = inspect(tmp_path, data)
    assert report["terminal"]["scheduler_sequence"] is None
    assert report["native_cadence_observations"]["scheduler_updates"] == []


@pytest.mark.parametrize("stream", ["updates", "scheduler_updates", "phase_events"])
def test_schema2_cannot_open_new_rich_records_after_terminal_callback(tmp_path, stream):
    data = rich_capture()
    if stream == "phase_events":
        data["attempt"][stream][0].update(wall_enter_ns=20_500_000, wall_exit_ns=20_600_000)
    else:
        row = deepcopy(data["attempt"][stream][0])
        enter = 21_100_000 if stream == "updates" else 22_100_000
        row.update(
            sequence=1,
            command_index_before=2,
            command_index_after=2,
            wall_enter_ns=enter,
            wall_exit_ns=enter + 100_000,
            phase_before=deepcopy(data["attempt"]["terminal"]["phase"]),
        )
        data["attempt"][stream].append(row)
    with pytest.raises(ValueError, match="entry is after the reported terminal callback"):
        inspect(tmp_path, data)


def test_schema2_enclosing_rich_hooks_may_finish_after_terminal_callback(tmp_path):
    data = rich_capture()
    data["attempt"]["phase_events"][0].update(
        wall_enter_ns=19_900_000,
        wall_exit_ns=20_600_000,
        phase_after=deepcopy(data["attempt"]["terminal"]["phase"]),
    )
    report = inspect(tmp_path, data)
    cadence = report["native_cadence_observations"]
    terminal_ns = report["terminal"]["wall_elapsed_seconds"] * 1e9
    assert all(
        cadence[name][0]["wall_exit_ns"] > terminal_ns
        for name in ("updates", "scheduler_updates", "phase_events")
    )
    assert report["m1_gate"] == "not_established_by_file_inspection"


@pytest.mark.parametrize("entry_ns,valid", [(20_001_000, True), (20_001_001, False)])
def test_schema2_entry_timestamp_uses_existing_one_microsecond_allowance(tmp_path, entry_ns, valid):
    data = rich_capture()
    data["attempt"]["phase_events"][0].update(wall_enter_ns=entry_ns, wall_exit_ns=20_100_000)
    if valid:
        assert inspect(tmp_path, data)["capture_schema_version"] == 2
    else:
        with pytest.raises(ValueError, match="entry is after the reported terminal callback"):
            inspect(tmp_path, data)


@pytest.mark.parametrize("policy", ["native", "fixed-base-60", "fixed-scheduler-240"])
def test_schema3_raw_observations_keep_rich_clock_contract_without_certifying_coverage(tmp_path, policy):
    data = mechanics_capture(policy=policy)
    report = inspect(tmp_path, data)
    assert report["capture_schema_version"] == 3
    assert len(report["state_fields"]) == 9
    assert report["layer_state_fields"] == ["dual_active"]
    assert report["native_cadence_observations"]["status"] == "recorded"
    assert report["native_cadence_observations"]["clock_identity"]["clock_policy"] == policy
    assert report["terminal"]["state"] == data["attempt"]["terminal"]["state"]
    assert report["status"] == "synthetic_fixture"
    assert report["physics_status"] == "not_independently_verified"
    assert report["m1_gate"] == "not_established_by_file_inspection"
    assert any("speed units" in warning for warning in report["warnings"])
    comparison = compare(tmp_path, data, mechanics_capture(policy=policy, attempt_id="other"))
    assert comparison["status"] == "recorded_subset_consistent"
    assert len(comparison["component_consistency"]) == 14
    assert all(comparison["component_consistency"].values())
    assert comparison["component_consistency"]["recorded_dual_active_equal"] is True
    assert comparison["component_consistency"]["terminal_dual_active_equal"] is True
    assert comparison["comparisons"][0]["pre_end_animation_diagnostics"]["consistent"] is True


@pytest.mark.parametrize("sample", [0, 1, 2, "terminal"])
@pytest.mark.parametrize("player_name", ["player1", "player2"])
@pytest.mark.parametrize(
    "field,value",
    [("gravity_inverted", True), ("vehicle_size", 1.0000000000000002), ("player_speed", 0.9000000000000001)],
)
def test_schema3_every_selected_raw_player_field_affects_exact_comparison(
    tmp_path, sample, player_name, field, value
):
    first = mechanics_capture()
    second = mechanics_capture(attempt_id="other")
    for data in (first, second):
        for state in [row["state"] for row in data["attempt"]["trace"]] + [
            data["attempt"]["terminal"]["state"]
        ]:
            state["player2"] = deepcopy(state["player1"])
    mechanics_sample(second, sample)[player_name][field] = value
    report = compare(tmp_path, first, second)
    row = report["comparisons"][0]
    assert report["status"] == "recorded_subset_inconsistent"
    assert row["recorded_dual_active_equal"] is True
    assert row["terminal_dual_active_equal"] is True
    if sample == "terminal":
        assert row["recorded_player_fields_equal"] is True
        assert row["terminal_player_fields_equal"] is False
        differences = row["terminal_diagnostics"]["selected_player_field_differences"]
        assert differences[f"{player_name}.{field}"]["compared"] == value
    else:
        assert row["recorded_player_fields_equal"] is False
        assert row["terminal_player_fields_equal"] is True
        difference = row["player_field_diagnostics"]["field_differences"][f"{player_name}.{field}"]
        assert difference["first_different_call_index"] == sample
        assert difference["compared"] == value
    prefix = row["pre_end_animation_diagnostics"]
    assert prefix["status"] == "available"
    assert prefix["consistent"] is (sample in {2, "terminal"})
    assert prefix["full_comparison_influence"] == "none"


@pytest.mark.parametrize("sample", [0, 1, 2, "terminal"])
def test_schema3_layer_dual_changes_have_separate_diagnostics_and_fail_full_gate(tmp_path, sample):
    first = mechanics_capture()
    second = mechanics_capture(attempt_id="other")
    mechanics_sample(second, sample)["dual_active"] = True
    report = compare(tmp_path, first, second)
    row = report["comparisons"][0]
    assert report["status"] == "recorded_subset_inconsistent"
    assert row["recorded_player_fields_equal"] is True
    assert row["terminal_player_fields_equal"] is True
    assert row["recorded_dual_active_equal"] is (sample == "terminal")
    assert row["terminal_dual_active_equal"] is (sample != "terminal")
    if sample == "terminal":
        assert row["terminal_diagnostics"]["dual_active_difference"] == {"baseline": False, "compared": True}
        assert row["terminal_diagnostics"]["selected_player_field_differences"] == {}
    else:
        difference = row["dual_active_diagnostics"]["field_differences"]["dual_active"]
        assert difference["first_different_call_index"] == sample
        assert difference["baseline"] is False and difference["compared"] is True
    prefix = row["pre_end_animation_diagnostics"]
    assert prefix["dual_active_diagnostics"]["equal"] is (sample in {2, "terminal"})
    assert prefix["consistent"] is (sample in {2, "terminal"})
    assert prefix["m1_gate"] == "not_established_by_prefix_comparison"


@pytest.mark.parametrize("sample", [0, 1, 2, "terminal"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("gravity_inverted", 0),
        ("gravity_inverted", "false"),
        ("gravity_inverted", None),
        ("vehicle_size", True),
        ("vehicle_size", "1.0"),
        ("vehicle_size", None),
        ("vehicle_size", float("nan")),
        ("vehicle_size", float("inf")),
        ("player_speed", False),
        ("player_speed", "0.9"),
        ("player_speed", None),
        ("player_speed", float("-inf")),
    ],
)
def test_schema3_raw_player_types_are_strict_in_every_sample(tmp_path, sample, field, value):
    data = mechanics_capture()
    mechanics_sample(data, sample)["player1"][field] = value
    with pytest.raises(ValueError):
        inspect(tmp_path, data)


@pytest.mark.parametrize("sample", [0, 1, 2, "terminal"])
@pytest.mark.parametrize("value", [0, 1, "false", None, [], {}])
def test_schema3_dual_flag_is_required_boolean_in_every_sample(tmp_path, sample, value):
    data = mechanics_capture()
    mechanics_sample(data, sample)["dual_active"] = value
    with pytest.raises(ValueError, match="dual_active"):
        inspect(tmp_path, data)


@pytest.mark.parametrize("sample", [0, 1, 2, "terminal"])
@pytest.mark.parametrize("field", ["gravity_inverted", "vehicle_size", "player_speed", "dual_active"])
def test_schema3_missing_raw_fields_never_receive_defaults(tmp_path, sample, field):
    data = mechanics_capture()
    state = mechanics_sample(data, sample)
    target = state if field == "dual_active" else state["player1"]
    target.pop(field)
    with pytest.raises(ValueError, match=field):
        inspect(tmp_path, data)


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.pop("layer_state_fields"),
        lambda d: d.update(layer_state_fields=[]),
        lambda d: d.update(layer_state_fields=["dual_active", "dual_active"]),
        lambda d: d.update(layer_state_fields="dual_active"),
        lambda d: d.update(layer_state_fields=["is_dual"]),
        lambda d: d["state_fields"].remove("vehicle_size"),
        lambda d: d["state_fields"].append("vehicle_size"),
        lambda d: d["state_fields"].append("is_mini"),
        lambda d: d["attempt"]["trace"][1]["state"].update(is_dual=False),
        lambda d: d["attempt"]["terminal"]["state"]["player1"].update(is_mini=False),
        lambda d: d["attempt"].pop("updates"),
        lambda d: d["attempt"].pop("scheduler_updates"),
        lambda d: d["attempt"].pop("phase_events"),
        lambda d: d["attempt"]["trace"][1].pop("phase"),
        lambda d: d["attempt"]["terminal"].pop("scheduler_sequence"),
        lambda d: d["environment"].update(input_policy=LEGACY_INPUT_POLICY),
        lambda d: d["attempt"]["scheduler_updates"][0].update(delivered_dt_seconds=1 / 240),
        lambda d: d["attempt"]["terminal"].update(update_sequence=1),
    ],
)
def test_schema3_exact_declarations_and_all_rich_contracts_remain_required(tmp_path, change):
    data = mechanics_capture(policy="fixed-scheduler-240")
    change(data)
    refresh_environment(data)
    with pytest.raises(ValueError):
        inspect(tmp_path, data)


@pytest.mark.parametrize("factory", [capture, rich_capture])
@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(layer_state_fields=["dual_active"]),
        lambda d: d["attempt"]["trace"][0]["state"].update(dual_active=False),
        lambda d: d["attempt"]["terminal"]["state"].update(dual_active=False),
        lambda d: d["attempt"]["trace"][1]["state"]["player1"].update(gravity_inverted=False),
        lambda d: d["attempt"]["terminal"]["state"]["player1"].update(vehicle_size=1.0),
        lambda d: d["state_fields"].append("player_speed"),
    ],
)
def test_schema1_and_schema2_reject_mechanics_fields_instead_of_silently_upgrading(tmp_path, factory, change):
    data = factory()
    change(data)
    with pytest.raises(ValueError):
        inspect(tmp_path, data)


def test_schema3_raw_finite_values_are_preserved_without_size_or_speed_classification(tmp_path):
    data = mechanics_capture()
    for state in [row["state"] for row in data["attempt"]["trace"]] + [data["attempt"]["terminal"]["state"]]:
        state["player1"].update(vehicle_size=1e-300, player_speed=-1e300)
        state["dual_active"] = True
    data["attempt"]["terminal"]["state"]["dual_active"] = False
    report = inspect(tmp_path, data)
    assert report["terminal"]["state"]["player1"]["vehicle_size"] == 1e-300
    assert report["terminal"]["state"]["player1"]["player_speed"] == -1e300
    assert report["terminal"]["state"]["player2"] is None
    assert report["terminal"]["state"]["dual_active"] is False
    assert report["m1_gate"] == "not_established_by_file_inspection"
    assert "is_mini" not in report["terminal"]["state"]["player1"]
    assert "speed_units" not in report


def test_schema3_death_and_completion_checks_do_not_treat_layer_boolean_as_player(tmp_path):
    data = mechanics_capture()
    data["attempt"]["terminal"].update(outcome="died", event="PlayLayer::destroyPlayer")
    data["attempt"]["terminal"]["state"]["player1"]["is_dead"] = True
    report = inspect(tmp_path, data)
    assert report["terminal"]["outcome"] == "died"
    data["attempt"]["terminal"]["state"]["player1"]["is_dead"] = False
    with pytest.raises(ValueError, match="recorded dead player"):
        inspect(tmp_path, data)
    data = mechanics_capture()
    data["attempt"]["terminal"]["state"]["player2"] = deepcopy(
        data["attempt"]["terminal"]["state"]["player1"]
    )
    data["attempt"]["terminal"]["state"]["player2"]["is_dead"] = True
    assert any("complete player lifecycle" in warning for warning in inspect(tmp_path, data)["warnings"])


def test_schema2_comparison_components_and_inspection_do_not_fabricate_layer_fields(tmp_path):
    data = rich_capture()
    report = inspect(tmp_path, data)
    assert "layer_state_fields" not in report
    assert "dual_active" not in report["terminal"]["state"]
    comparison = compare(tmp_path, data, rich_capture(attempt_id="other"))
    assert len(comparison["component_consistency"]) == 12
    assert "recorded_dual_active_equal" not in comparison["component_consistency"]
    assert "dual_active_diagnostics" not in comparison["comparisons"][0]
    assert "dual_active_equal" not in comparison["comparisons"][0]["terminal_diagnostics"]


def test_schema2_and_schema3_cannot_be_compared_as_compatible_recorded_state(tmp_path):
    with pytest.raises(ValueError, match="schema_version"):
        compare(tmp_path, rich_capture(), mechanics_capture(attempt_id="other"))


def test_schema4_retains_raw_contacts_watches_and_paired_callbacks(tmp_path):
    data = collision_capture()
    data["attempt"]["mechanic_events"] = [mechanic_event(data)]
    report = inspect(tmp_path, data)
    assert report["capture_schema_version"] == 4
    assert report["object_watches"] == data["object_watches"]
    assert report["terminal"]["state"]["player1"]["is_on_ground"] is True
    assert report["native_object_observations"]["mechanic_event_count"] == 1
    assert "mechanic_events" not in report["attempt"]
    assert any("synthetic in-engine delivery" in warning for warning in report["warnings"])


@pytest.mark.parametrize(
    "event",
    [
        "PlayerObject::collidedWithObject",
        "PlayerObject::updateCollide",
        "PlayerObject::collidedWithSlopeInternal",
        "PlayLayer::destroyPlayer",
        "GJBaseGameLayer::triggerMoveCommand",
        "GJBaseGameLayer::toggleGroupTriggered",
        "GJBaseGameLayer::toggleGroup",
        "GJBaseGameLayer::spawnGroup",
        "EffectGameObject::triggerObject",
    ],
)
def test_schema4_each_supported_native_mechanic_payload_is_valid(tmp_path, event):
    data = collision_capture()
    data["attempt"]["mechanic_events"] = [mechanic_event(data, event=event)]
    assert load_native_capture(save(tmp_path, data))["attempt"]["mechanic_events"][0]["event"] == event


@pytest.mark.parametrize("driver", ["none", "owned-pre-command", "scheduled-ui-callback"])
def test_schema4_driver_provenance_is_distinct_from_native_receipt_source(tmp_path, driver):
    data = collision_capture(driver=driver)
    if driver != "owned-pre-command":
        # Extra native requests remain observed data; scheduled UI intent does
        # not falsely attribute every native receipt to its planned source.
        extra = deepcopy(data["attempt"]["inputs"][0])
        extra.update(sequence=2, command_index=2, pressed=False, wall_time_ns=1_000_004)
        data["attempt"]["inputs"].append(extra)
    assert load_native_capture(save(tmp_path, data))["attempt"]["input_delivery"]["driver"] == driver


def test_schema4_delivery_records_keep_queue_and_layer_timing(tmp_path):
    data = collision_capture(driver="scheduled-ui-callback")
    queued = delivery_event(event="GJBaseGameLayer::processQueuedButtons")
    queued.update(
        sequence=1,
        arguments={"dt_seconds": 1 / 240, "clear_input_queue": False},
        queue_before=deepcopy(queued["queue_after"]),
        queue_after=[],
        wall_enter_ns=1_000_006,
        wall_exit_ns=1_000_007,
    )
    data["attempt"]["delivery_events"] = [delivery_event(), queued]
    assert inspect(tmp_path, data)["native_object_observations"]["delivery_event_count"] == 2


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d["state_fields"].remove("is_on_ground"),
        lambda d: d["attempt"]["trace"][1]["state"]["player1"].update(is_on_slope=1),
        lambda d: d["attempt"]["terminal"]["state"]["player1"].pop("is_on_ground"),
        lambda d: d["object_watches"][0].update(group_id=0),
        lambda d: d["object_watches"].append(deepcopy(d["object_watches"][0])),
        lambda d: d["attempt"]["trace"][1]["watched_objects"][0].update(group_id=2),
        lambda d: d["attempt"]["trace"][1]["watched_objects"][0].update(is_disabled=0),
        lambda d: d["attempt"]["terminal"]["watched_objects"][0].update(x=float("inf")),
        lambda d: d["attempt"].update(input_delivery=[]),
        lambda d: d["attempt"]["input_delivery"].update(provenance="hardware"),
        lambda d: d["attempt"]["inputs"][0].update(in_command=1),
        lambda d: d["attempt"]["inputs"][0].update(update_sequence=1),
        lambda d: d["attempt"]["mechanic_events"][0].update(native_return=None),
        lambda d: d["attempt"]["mechanic_events"][0].update(sequence=1),
        lambda d: d["attempt"]["mechanic_events"][0].update(parent_sequence=0),
        lambda d: d["attempt"]["mechanic_events"][0].update(
            wall_enter_ns=30_000_000, wall_exit_ns=31_000_000
        ),
        lambda d: d["attempt"]["mechanic_events"][0].update(wall_exit_ns=30_000_000),
        lambda d: d["attempt"]["mechanic_events"][0]["arguments"].update(skip_check=0),
        lambda d: d["attempt"]["mechanic_events"][0]["object"].update(group_ids=[2, 1]),
        lambda d: d["attempt"]["mechanic_events"][0]["state_after"]["player1"].pop("is_on_slope"),
        lambda d: d["attempt"]["delivery_events"][0]["queue_after"][0].update(timestamp=True),
        lambda d: d["attempt"]["delivery_events"][0].update(layer_timestamp_after=float("nan")),
        lambda d: d["attempt"]["delivery_events"][0].update(event="invented-hook"),
    ],
)
def test_schema4_malformed_observations_rejected(tmp_path, change):
    data = collision_capture()
    data["attempt"]["mechanic_events"] = [mechanic_event(data)]
    data["attempt"]["delivery_events"] = [delivery_event()]
    change(data)
    with pytest.raises(ValueError):
        load_native_capture(save(tmp_path, data))


def test_schema4_runtime_uids_and_wall_timing_are_diagnostic_only(tmp_path):
    first = collision_capture()
    first["attempt"]["mechanic_events"] = [mechanic_event(first)]
    second = deepcopy(first)
    second["attempt"]["id"] = "other"
    second["object_watches"][0]["runtime_unique_id"] = 99
    second["attempt"]["mechanic_events"][0]["object"]["runtime_unique_id"] = 99
    second["attempt"]["mechanic_events"][0]["wall_enter_ns"] += 10
    second["attempt"]["mechanic_events"][0]["wall_exit_ns"] += 10
    report = compare(tmp_path, first, second)
    assert report["status"] == "recorded_subset_consistent"
    assert len(report["component_consistency"]) == 18


@pytest.mark.parametrize(
    "change,component",
    [
        (
            lambda d: d["attempt"]["trace"][1]["state"]["player1"].update(is_on_ground=False),
            "recorded_player_fields_equal",
        ),
        (
            lambda d: d["attempt"]["trace"][1]["watched_objects"][0].update(y=100),
            "recorded_watched_objects_equal",
        ),
        (
            lambda d: d["attempt"]["terminal"]["watched_objects"][0].update(is_disabled=True),
            "terminal_watched_objects_equal",
        ),
        (
            lambda d: d["attempt"]["mechanic_events"][0].update(native_return=False),
            "native_mechanic_events_equal",
        ),
        (
            lambda d: d["attempt"]["delivery_events"][0]["queue_after"][0].update(step=2),
            "native_delivery_context_equal",
        ),
        (
            lambda d: d["attempt"]["delivery_events"][0]["arguments"].update(key_code=33),
            "native_delivery_context_equal",
        ),
    ],
)
def test_schema4_each_new_component_influences_full_repeat_result(tmp_path, change, component):
    first = collision_capture()
    first["attempt"]["mechanic_events"] = [mechanic_event(first)]
    first["attempt"]["delivery_events"] = [delivery_event()]
    second = deepcopy(first)
    second["attempt"]["id"] = "other"
    change(second)
    report = compare(tmp_path, first, second)
    assert report["status"] == "recorded_subset_inconsistent"
    assert report["component_consistency"][component] is False


def test_schema4_repeat_rejects_different_delivery_and_watch_identities(tmp_path):
    first = collision_capture()
    with pytest.raises(ValueError, match="input_delivery"):
        compare(tmp_path, first, collision_capture(attempt_id="other", driver="scheduled-ui-callback"))
    second = collision_capture(attempt_id="other")
    second["object_watches"][0]["object_id"] = 2
    with pytest.raises(ValueError, match="object_watches"):
        compare(tmp_path, first, second)


def test_schema4_outside_command_native_ui_receipts_preserve_actual_context(tmp_path):
    data = collision_capture(driver="scheduled-ui-callback")
    for receipt in data["attempt"]["inputs"]:
        receipt.update(in_command=False, update_sequence=None, scheduler_sequence=None)
    assert load_native_capture(save(tmp_path, data))["attempt"]["inputs"][1]["in_command"] is False
    changed = deepcopy(data)
    changed["attempt"]["id"] = "other"
    changed["attempt"]["inputs"][1].update(in_command=True, update_sequence=0, scheduler_sequence=0)
    assert compare(tmp_path, data, changed)["component_consistency"]["recorded_inputs_equal"] is False


def test_schema4_nested_event_closure_can_follow_terminal_inside_native_parent_context(tmp_path):
    data = collision_capture()
    parent = mechanic_event(data, event="GJBaseGameLayer::triggerMoveCommand")
    parent.update(wall_enter_ns=1_000_000, wall_exit_ns=20_500_000)
    child = mechanic_event(data, event="PlayLayer::destroyPlayer")
    child.update(sequence=1, parent_sequence=0, wall_enter_ns=1_000_003, wall_exit_ns=20_001_000)
    data["attempt"]["mechanic_events"] = [parent, child]
    assert len(load_native_capture(save(tmp_path, data))["attempt"]["mechanic_events"]) == 2
    child["parent_sequence"] = None
    with pytest.raises(ValueError, match="sibling"):
        load_native_capture(save(tmp_path, data))


@pytest.mark.parametrize(
    "collection,maximum", [("object_watches", 8), ("mechanic_events", 4096), ("delivery_events", 4096)]
)
def test_schema4_record_streams_have_explicit_resource_limits(tmp_path, collection, maximum):
    data = collision_capture()
    if collection == "object_watches":
        data[collection] *= maximum + 1
    else:
        row = mechanic_event(data) if collection == "mechanic_events" else delivery_event()
        data["attempt"][collection] = [row] * (maximum + 1)
    with pytest.raises(ValueError, match="at most"):
        load_native_capture(save(tmp_path, data))


def test_schema4_queue_resource_limit_and_untrusted_event_type_are_rejected(tmp_path):
    data = collision_capture()
    event = delivery_event()
    event["queue_after"] *= 257
    data["attempt"]["delivery_events"] = [event]
    with pytest.raises(ValueError, match="at most"):
        load_native_capture(save(tmp_path, data))
    event = delivery_event()
    event["event"] = []
    data["attempt"]["delivery_events"] = [event]
    with pytest.raises(ValueError, match="Unsupported native delivery"):
        load_native_capture(save(tmp_path, data))


@pytest.mark.parametrize("builder", [capture, rich_capture, mechanics_capture])
def test_schema4_data_is_never_silently_accepted_under_older_capture_versions(tmp_path, builder):
    data = builder()
    data["object_watches"] = []
    with pytest.raises(ValueError, match="unknown object_watches"):
        load_native_capture(save(tmp_path, data))


def test_schema4_raw_hook_numbers_are_finite_without_invented_physical_ranges(tmp_path):
    data = collision_capture()
    event = mechanic_event(data)
    event["arguments"]["rect"]["width"] = -1.0
    event["object"]["runtime_unique_id"] = -(2**31)
    data["attempt"]["mechanic_events"] = [event]
    assert (
        load_native_capture(save(tmp_path, data))["attempt"]["mechanic_events"][0]["arguments"]["rect"][
            "width"
        ]
        == -1.0
    )


def test_schema4_absolute_delivery_timestamps_are_explicit_raw_diagnostics(tmp_path):
    first = collision_capture(driver="scheduled-ui-callback")
    first["attempt"]["delivery_events"] = [delivery_event()]
    second = deepcopy(first)
    second["attempt"]["id"] = "other"
    event = second["attempt"]["delivery_events"][0]
    event["layer_timestamp_before"] += 183_000.0
    event["layer_timestamp_after"] += 183_000.0
    event["arguments"]["timestamp"] += 183_000.0
    event["queue_after"][0]["timestamp"] += 183_000.0
    report = compare(tmp_path, first, second)
    assert report["status"] == "recorded_subset_consistent"
    assert report["component_consistency"]["native_delivery_context_equal"]
    assert report["delivery_context_protocol"]["id"] == "native-delivery-context-v1"
    diagnostic = report["comparisons"][0]["delivery_absolute_timestamp_diagnostics"]
    assert diagnostic["equal"] is False
    assert diagnostic["first_difference"]["sequence"] == 0
    assert diagnostic["baseline_signature_sha256"] != diagnostic["compared_signature_sha256"]
    assert diagnostic["compared_signature"][0]["callback_timestamp"] == event["arguments"]["timestamp"]
    assert first["attempt"]["delivery_events"][0]["arguments"]["timestamp"] == 0.004


def test_delivery_context_projection_keeps_every_queue_command_without_mutating_capture():
    events = [delivery_event()]
    saved = deepcopy(events)
    actual = delivery_context_signature(events)
    assert events == saved
    assert actual[0]["queue_after"] == [{"button": 1, "pressed": True, "player": 1, "step": 1}]
    assert actual[0]["arguments"] == {"key_code": 32}
    assert "layer_timestamp_before" not in actual[0]


def test_schema4_raw_timestamp_exclusion_never_removes_extra_actual_native_receipts(tmp_path):
    first = collision_capture(driver="scheduled-ui-callback")
    first["attempt"]["delivery_events"] = [delivery_event()]
    second = deepcopy(first)
    second["attempt"]["id"] = "other"
    extra = deepcopy(second["attempt"]["inputs"][0])
    extra.update(sequence=2, pressed=False, wall_time_ns=1_000_010)
    second["attempt"]["inputs"].append(extra)
    report = compare(tmp_path, first, second)
    assert report["component_consistency"]["native_delivery_context_equal"]
    assert report["component_consistency"]["recorded_inputs_equal"] is False
    assert report["status"] == "recorded_subset_inconsistent"


def test_schema4_toggle_group_requires_actual_exact_group_and_boolean_arguments(tmp_path):
    data = collision_capture()
    record = mechanic_event(data, event="GJBaseGameLayer::toggleGroup")
    data["attempt"]["mechanic_events"] = [record]
    assert load_native_capture(save(tmp_path, data))["attempt"]["mechanic_events"][0]["arguments"] == {
        "group": 1,
        "activate": False,
    }
    record["arguments"]["activate"] = 0
    with pytest.raises(ValueError, match="JSON boolean"):
        load_native_capture(save(tmp_path, data))
