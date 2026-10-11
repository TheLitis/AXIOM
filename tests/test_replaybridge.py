"""Strict source-to-recorded-plan contracts, using explicitly synthetic records."""

import json
import struct
from copy import deepcopy

import pytest
from test_native import input_entry_capture, refresh_environment

from axiom.cli import main
from axiom.native import (
    compare_native_captures,
    inspect_native_capture,
    load_native_capture,
    validate_recorded_replay_plan,
)
from axiom.replaybridge import compare_recorded_replay, export_recorded_replay_plan
from axiom.validation import read_json


def store(folder, name, data):
    path = folder / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def recorded_source():
    """Include initial release, P2 channel/P1 response and two-request batch."""
    data = input_entry_capture(driver="none")
    data["environment"]["mods"] = [
        {
            "id": data["collector"]["id"],
            "version": data["collector"]["version"],
            "binary_sha256": data["environment"]["adapter_binary_sha256"],
        }
    ]
    refresh_environment(data)
    attempt = data["attempt"]
    attempt["id"] = "synthetic-observed-source"
    scheduler = attempt["scheduler_updates"][0]
    dt = struct.unpack("f", struct.pack("f", 1 / 60))[0]
    scheduler["original_dt_seconds"] = scheduler["delivered_dt_seconds"] = dt
    inputs = []
    for command, player, pressed, wall in (
        (1, 1, False, 1_000_000),
        (1, 2, True, 1_100_000),
        (2, 2, False, 2_000_000),
    ):
        base = {
            "command_index": command,
            "player": player,
            "button": 1,
            "pressed": pressed,
            "source": "observed",
            "in_command": True,
            "update_sequence": 0,
            "scheduler_sequence": 0,
        }
        inputs.append(
            {
                **base,
                "sequence": len(inputs),
                "phase": "requested",
                "native_return": None,
                "wall_time_ns": wall,
            }
        )
        inputs.append(
            {
                **base,
                "player": 1,
                "sequence": len(inputs),
                "phase": "push" if pressed else "release",
                "native_return": True,
                "wall_time_ns": wall + 10_000,
            }
        )
    attempt["inputs"] = inputs
    events = []
    for command, enter, exit_time in ((1, 900_000, 1_200_000), (2, 1_900_000, 2_200_000)):
        requests = [row for row in inputs if row["command_index"] == command and row["phase"] == "requested"]
        events.append(
            {
                "sequence": len(events),
                "parent_sequence": None,
                "event": "GJBaseGameLayer::processQueuedButtons",
                "command_index": command,
                "in_command": True,
                "update_sequence": 0,
                "scheduler_sequence": 0,
                "arguments": {
                    "dt_seconds": attempt["trace"][command]["dt_seconds"],
                    "clear_input_queue": True,
                },
                "phase_before": deepcopy(attempt["trace"][command]["phase"]),
                "phase_after": deepcopy(attempt["trace"][command]["phase"]),
                "native_return": None,
                "wall_enter_ns": enter,
                "wall_exit_ns": exit_time,
                "queue_before": [
                    {
                        **{key: row[key] for key in ("button", "pressed", "player")},
                        "step": 0,
                        "timestamp": 1234.0 + index,
                    }
                    for index, row in enumerate(requests)
                ],
                "queue_after": [],
                "layer_timestamp_before": 1234.0,
                "layer_timestamp_after": 1234.0,
            }
        )
    # processCommands raw native args are float32, unlike the schema-1 fixture's Python 1/240.
    for row in attempt["trace"][1:]:
        row["dt_seconds"] = struct.unpack("f", struct.pack("f", row["dt_seconds"]))[0]
    for event in events:
        event["arguments"]["dt_seconds"] = attempt["trace"][event["command_index"]]["dt_seconds"]
    attempt["delivery_events"] = events
    events[0]["queue_before"][0]["timestamp"] = 0
    return data


def target_baseline(source):
    data = deepcopy(source)
    data["attempt"]["id"] = "synthetic-new-collector-baseline"
    data["collector"].update(source_commit="new-collector-commit", source_tree_sha256="c" * 64)
    data["environment"]["adapter_binary_sha256"] = "d" * 64
    for row in data["environment"]["mods"]:
        if row["id"] == data["collector"]["id"]:
            row["binary_sha256"] = "d" * 64
    refresh_environment(data)
    data["attempt"]["inputs"] = data["attempt"]["inputs"][:2]
    data["attempt"]["delivery_events"] = data["attempt"]["delivery_events"][:1]
    data["attempt"]["delivery_events"][0]["queue_before"] = data["attempt"]["delivery_events"][0][
        "queue_before"
    ][:1]
    return data


def schema6_replay(source, baseline, plan, plan_hash, attempt_id="synthetic-recorded-1"):
    data = deepcopy(source)
    data["schema_version"] = 6
    data["collector"] = deepcopy(baseline["collector"])
    data["environment"] = deepcopy(baseline["environment"])
    data["environment"]["clocks"].update(
        clock_policy="recorded-scheduler-stream",
        intervention_hook="CCScheduler::update",
        step_numerator=0,
        step_denominator=1,
    )
    refresh_environment(data)
    data["attempt"].update(
        id=attempt_id,
        input_source="replay",
        replay_sha256=plan_hash,
        planned_inputs=deepcopy(plan["inputs"]),
        replay_bridge=deepcopy(plan),
        input_delivery={
            "driver": "owned-processing-entry",
            "provenance": "synthetic-scheduled",
            "entry_point": "GJBaseGameLayer::handleButton",
            "injection_phase": "GJBaseGameLayer::processQueuedButtons-entry-before-original",
            "timestamp_policy": "not-applicable",
        },
    )
    for row in data["attempt"]["inputs"]:
        row["source"] = "replay"
    for row in data["attempt"]["delivery_events"]:
        row["queue_before"] = []
    return data


@pytest.fixture
def bridge(tmp_path):
    source = recorded_source()
    baseline = target_baseline(source)
    source_path = store(tmp_path, "source.json", source)
    baseline_path = store(tmp_path, "baseline.json", baseline)
    plan = export_recorded_replay_plan(source_path, baseline_path)
    plan_path = store(tmp_path, "plan.json", plan)
    replays = [
        schema6_replay(source, baseline, plan, read_json(plan_path)[1], f"synthetic-recorded-{index}")
        for index in range(3)
    ]
    paths = [store(tmp_path, f"replay-{index}.json", replay) for index, replay in enumerate(replays)]
    return source, baseline, plan, source_path, baseline_path, plan_path, replays, paths


def test_complete_source_export_retains_initial_release_channels_and_batch_order(bridge):
    source, baseline, plan, source_path, _, _, _, _ = bridge
    assert plan["schema_version"] == 2
    assert plan["source_capture_sha256"] == read_json(source_path)[1]
    assert plan["target_collector"] == baseline["collector"]
    assert plan["inputs"] == [
        {"command_index": 1, "player": 1, "button": 1, "pressed": False},
        {"command_index": 1, "player": 2, "button": 1, "pressed": True},
        {"command_index": 2, "player": 2, "button": 1, "pressed": False},
    ]
    assert [row["source_input_sequence"] for row in plan["processing_batches"][0]["inputs"]] == [0, 2]
    assert plan["scheduler_updates"][0]["update_count"] == 1
    assert all(row["player"] == 1 for row in source["attempt"]["inputs"] if row["phase"] != "requested")


def test_exact_source_correspondence_and_three_fresh_repeats(bridge):
    _, _, plan, source, _, plan_path, _, paths = bridge
    result = compare_recorded_replay(source, plan_path, paths)
    assert result["status"] == "recorded_source_subset_and_repeats_consistent"
    assert result["source_correspondence_consistent"] and result["same_route_repeats_consistent"]
    assert result["replay_count"] == 3
    assert result["plan"] == plan
    assert len(result["same_route_repeat_comparison"]["component_consistency"]) == 18
    assert all(not row["source_vs_replay_delivery_diagnostics"]["equal"] for row in result["comparisons"])
    assert result["source_input_provenance"] == "unknown"
    assert result["ordinary_os_input_equivalence"] == "not_established"


def test_exact_selected_rotation_divergence_is_negative_result(bridge, tmp_path):
    _, _, _, source, _, plan, replays, paths = bridge
    for index, data in enumerate(replays):
        data["attempt"]["trace"][1]["state"]["player1"]["rotation"] += 0.0000001
        paths[index] = store(tmp_path, f"changed-{index}.json", data)
    result = compare_recorded_replay(source, plan, paths)
    assert result["same_route_repeats_consistent"]
    assert not result["source_correspondence_consistent"]
    assert not result["comparisons"][0]["checks"]["selected_trajectory_equal"]
    assert result["status"] == "recorded_source_replay_consistency_not_established"


@pytest.mark.parametrize("extra", [False, True])
def test_specific_initial_cleanup_allowed_but_extra_interference_rejects(bridge, tmp_path, extra):
    paths = []
    for index, replay in enumerate(bridge[6]):
        replay["attempt"]["delivery_events"][0]["queue_before"] = [
            deepcopy(bridge[0]["attempt"]["delivery_events"][0]["queue_before"][0])
        ]
        replay["attempt"]["blocked_inputs"] = [
            {
                "sequence": 0,
                "command_index": 1,
                "player": 1,
                "button": 1,
                "pressed": False,
                "source": "unknown",
                "wall_time_ns": 1_180_000,
            }
        ]
        if extra:
            replay["attempt"]["blocked_inputs"].append(
                {
                    "sequence": 1,
                    "command_index": 1,
                    "player": 2,
                    "button": 1,
                    "pressed": False,
                    "source": "unknown",
                    "wall_time_ns": 1_190_000,
                }
            )
        paths.append(store(tmp_path, f"cleanup-{index}.json", replay))
    result = compare_recorded_replay(bridge[3], bridge[5], paths)
    assert result["same_route_repeats_consistent"]
    assert result["source_correspondence_consistent"] is not extra
    check = result["comparisons"][0]["input_interference_qualification"]
    assert check["record_count"] == (2 if extra else 1)
    assert check["status"] == (
        "additional_or_ambiguous_suppressed_interference"
        if extra
        else "one_initial_cleanup_release_witnessed"
    )
    assert len(result["comparisons"][0]["blocked_unknown_input_diagnostics"]) == (2 if extra else 1)


def test_plan_retains_warmup_multicommand_and_terminal_scheduler_without_update(bridge):
    plan = deepcopy(bridge[2])
    original = deepcopy(plan["scheduler_updates"][0])
    empty = {
        **deepcopy(original),
        "command_index_after": 0,
        "update_count": 0,
        "phase_after": deepcopy(original["phase_before"]),
    }
    tail = {
        **deepcopy(original),
        "command_index_before": 2,
        "update_count": 0,
        "phase_before": deepcopy(original["phase_after"]),
    }
    plan["scheduler_updates"] = [{**deepcopy(empty), "sequence": index} for index in range(244)] + [
        {**original, "sequence": 244},
        {**tail, "sequence": 245},
    ]
    for row in plan["processing_batches"]:
        row["scheduler_sequence"] = 244
    assert validate_recorded_replay_plan(plan) == plan
    assert len(plan["scheduler_updates"]) == 246
    assert plan["scheduler_updates"][244]["command_index_after"] == 2
    assert plan["scheduler_updates"][-1]["update_count"] == 0


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.update(extra=True),
        lambda p: p.update(schema_version=True),
        lambda p: p["inputs"][0].update(pressed=0),
        lambda p: p["inputs"].pop(0),
        lambda p: p["scheduler_updates"][0].update(sequence=1),
        lambda p: p["scheduler_updates"][0].update(delivered_dt_seconds=0.02),
        lambda p: p["scheduler_updates"][0].update(delivered_dt_seconds=float("inf")),
        lambda p: p["scheduler_updates"][0].update(command_index_before=1),
        lambda p: p["scheduler_updates"][0].update(update_count=0),
        lambda p: p["processing_batches"][1].update(command_index=1),
        lambda p: p["processing_batches"][1].update(source_delivery_sequence=0),
        lambda p: p["processing_batches"][1]["inputs"][0].update(source_input_sequence=2),
        lambda p: p["processing_batches"][0].update(update_sequence=None),
        lambda p: p["processing_batches"][0].update(dt_seconds=0.02),
        lambda p: p["processing_batches"][0].update(clear_input_queue=1),
        lambda p: p["processing_batches"][0]["inputs"][0].update(button=4),
        lambda p: p["target_collector"].update(extra="unknown"),
    ],
)
def test_strict_versioned_plan_rejections(bridge, mutation):
    plan = deepcopy(bridge[2])
    mutation(plan)
    with pytest.raises(ValueError):
        validate_recorded_replay_plan(plan)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["attempt"].pop("replay_bridge"),
        lambda d: d["attempt"]["replay_bridge"].update(environment_sha256="e" * 64),
        lambda d: d["attempt"]["replay_bridge"]["target_collector"].update(source_commit="wrong"),
        lambda d: d["attempt"]["scheduler_updates"][0].update(delivered_dt_seconds=0.02),
        lambda d: d["attempt"]["delivery_events"][0]["arguments"].update(clear_input_queue=False),
        lambda d: d["attempt"]["inputs"][0].update(source="observed"),
        lambda d: d["attempt"]["input_delivery"].update(driver="owned-pre-command"),
        lambda d: d["environment"]["clocks"].update(clock_policy="native", intervention_hook="none"),
    ],
)
def test_schema6_identity_cadence_and_delivery_fail_closed(bridge, tmp_path, mutation):
    data = deepcopy(bridge[6][0])
    mutation(data)
    refresh_environment(data)
    with pytest.raises(ValueError):
        load_native_capture(store(tmp_path, "invalid.json", data))


def test_schema5_rejects_schema6_fields_and_clock(bridge, tmp_path):
    data = deepcopy(bridge[6][0])
    data["schema_version"] = 5
    with pytest.raises(ValueError):
        load_native_capture(store(tmp_path, "old-version.json", data))


@pytest.mark.parametrize("field", ["game_executable_sha256", "geode_version", "configuration_complete"])
def test_export_rejects_unapproved_environment_transition(bridge, tmp_path, field):
    source, baseline, _, source_path, _, _, _, _ = bridge
    baseline["environment"][field] = (
        "f" * 64
        if field.endswith("sha256")
        else "changed"
        if field == "geode_version"
        else not baseline["environment"][field]
    )
    refresh_environment(baseline)
    with pytest.raises(ValueError):
        export_recorded_replay_plan(source_path, store(tmp_path, "changed-baseline.json", baseline))


def test_export_rejects_missing_or_unassociated_source_request(bridge, tmp_path):
    source = deepcopy(bridge[0])
    source["attempt"]["delivery_events"][0]["queue_before"].pop()
    with pytest.raises(ValueError, match="complete enclosed requests"):
        export_recorded_replay_plan(store(tmp_path, "unassociated-source.json", source), bridge[4])


def test_raw_plan_bytes_are_bound_not_only_logical_plan(bridge, tmp_path):
    plan_path = tmp_path / "same-plan-different-bytes.json"
    plan_path.write_text(json.dumps(bridge[2], indent=4), encoding="utf-8")
    with pytest.raises(ValueError, match="raw recorded plan"):
        compare_recorded_replay(bridge[3], plan_path, bridge[7])


def test_no_replay_source_baseline_promotion_or_duplicate_attempts(bridge):
    with pytest.raises(ValueError):
        compare_native_captures([bridge[3], bridge[7][0]])
    with pytest.raises(ValueError, match="Duplicate attempt"):
        compare_recorded_replay(bridge[3], bridge[5], [bridge[7][0], bridge[7][0]])


def test_cli_plan_and_comparison_write_valid_json(bridge, tmp_path):
    output = tmp_path / "exported.json"
    assert main(["native-replay-plan", str(bridge[3]), str(bridge[4]), "--json", str(output)]) == 0
    assert read_json(output)[0] == bridge[2]
    report = tmp_path / "comparison.json"
    assert (
        main(
            [
                "native-recorded-compare",
                str(bridge[3]),
                str(bridge[5]),
                *map(str, bridge[7]),
                "--json",
                str(report),
            ]
        )
        == 0
    )
    assert read_json(report)[0]["status"] == "recorded_source_subset_and_repeats_consistent"
    assert inspect_native_capture(bridge[7][0])["capture_schema_version"] == 6
