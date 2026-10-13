"""Opt-in Windows observations keep compatible candidates distinct from causes."""

import hashlib

import pytest
from test_input_entries import entry
from test_native import (
    capture,
    collision_capture,
    input_entry_capture,
    mechanics_capture,
    refresh_environment,
    rich_capture,
    save,
)
from test_replaybridge import recorded_source, schema6_replay, target_baseline

from axiom.native import compare_native_captures, inspect_native_capture, load_native_capture
from axiom.replaybridge import export_recorded_replay_plan
from axiom.windowsinput import SDK_KEYBOARD, SDK_MOUSE


def message(*, sequence=0, role="raw", enter=200_000, exit_time=400_000, start=10.0, finish=10.1, raw=None):
    if raw is None and role == "raw":
        raw = {"kind": "keyboard", "vkey": 32, "scan_code": 57, "flags": 0, "keyboard_message": 256}
    return {
        "sequence": sequence,
        "parent_sequence": None,
        "window_role": role,
        "message": 255 if role == "raw" else 8,
        "wparam": 0,
        "lparam": -1,
        "thread_id": 22 if role == "raw" else 11,
        "foreground_before": True,
        "foreground_after": True,
        "wall_enter_ns": enter,
        "wall_exit_ns": exit_time,
        "input_timestamp_enter": start,
        "input_timestamp_exit": finish,
        "native_return": 0,
        "raw_input": raw,
    }


def sdk(*, sequence=0, event=SDK_KEYBOARD, timestamp=10.05, wall=500_000):
    return {
        "sequence": sequence,
        "event": event,
        "thread_id": 11,
        "wall_time_ns": wall,
        "command_index": 0,
        "in_command": False,
        "update_sequence": None,
        "scheduler_sequence": None,
        "phase": {"level_end_animation_started": False, "has_completed_level": False},
        "queue_snapshot": [],
        "data": {
            "key_code": 32,
            "action": "press",
            "native_code": 32,
            "native_extra": 57,
            "timestamp": timestamp,
            "modifiers": 0,
        }
        if event == SDK_KEYBOARD
        else {"button": "left", "action": "press", "timestamp": timestamp, "modifiers": 0},
    }


def windows_capture():
    data = input_entry_capture(driver="none")
    data["schema_version"] = 7
    data["environment"]["windows_input_observer"] = "raw-dispatch-v1"
    refresh_environment(data)
    ui = entry()
    ui["arguments"]["timestamp"] = 10.05
    ui["thread_id"] = 11
    data["attempt"]["delivery_events"] = [ui]
    data["attempt"]["windows_input"] = {
        "enabled": True,
        "scope": "active-guarded-sandbox-attempt-foreground-raw-only",
        "main_thread_id": 11,
        "windows": [
            {"role": "main", "thread_id": 11, "process_id": 33, "hwnd": 44, "installed": True},
            {"role": "raw", "thread_id": 22, "process_id": 33, "hwnd": 55, "installed": True},
        ],
        "messages": [message()],
        "sdk_events": [sdk()],
        "integrity": {
            "overflow_count": 0,
            "pending_callbacks_at_snapshot": 0,
            "read_error_count": 0,
            "errors": [],
        },
        "skipped": {"background_raw_count": 0, "mouse_motion_count": 0, "unsupported_raw_count": 0},
        "timestamp_unit": "Geode-getInputTimestamp-QPC-seconds",
        "sdk_listener_phase": "public-global-listener-receipt",
        "sdk_listener_priority": -(2**31),
    }
    return data


def inspect(tmp_path, data):
    return inspect_native_capture(save(tmp_path, data))


def test_compatible_chain_preserves_unknown_origins_and_all_raw_values(tmp_path):
    data = windows_capture()
    result = inspect(tmp_path, data)
    summary = result["windows_input_observations"]
    assert result["capture_schema_version"] == 7
    assert summary["messages"] == data["attempt"]["windows_input"]["messages"]
    assert summary["sdk_events"][0]["compatible_windows_message_sequences"] == [0]
    assert summary["delivery_correlations"][0]["compatible_sdk_event_sequences"] == [0]
    assert summary["delivery_correlations"][0]["candidate_windows_message_sequences"] == [0]
    edge = result["input_entry_observations"]["keyboard_edges"][0]
    assert edge["windows_input_correlation"]["correlation_status"] == "one_compatible_candidate"
    assert edge["thread_id"] == 11
    assert summary["private_raw_input_queue_ownership"] == "not_established"
    assert summary["authentication_status"] == "not_authenticated"
    assert result["attempt"]["input_source"] == "unknown"


def test_all_repeated_packet_candidates_retained_at_shared_timestamp_boundary(tmp_path):
    data = windows_capture()
    rows = data["attempt"]["windows_input"]
    rows["messages"] = [
        message(finish=10.05, exit_time=300_000),
        message(sequence=1, enter=350_000, exit_time=450_000, start=10.05),
    ]
    rows["sdk_events"] = [sdk(), sdk(sequence=1, wall=550_000)]
    summary = inspect(tmp_path, data)["windows_input_observations"]
    assert summary["sdk_events"][0]["compatible_windows_message_sequences"] == [0, 1]
    assert summary["sdk_events"][0]["correlation_status"] == "ambiguous_compatible_candidates"
    assert summary["delivery_correlations"][0]["compatible_sdk_event_sequences"] == [0, 1]
    assert summary["counts"]["ui_with_ambiguous_sdk_candidates"] == 1


@pytest.mark.parametrize("change", ["timestamp", "native_code", "native_extra", "action", "raw_null"])
def test_no_time_nearness_or_guessed_raw_matches(tmp_path, change):
    data = windows_capture()
    rows = data["attempt"]["windows_input"]
    if change == "raw_null":
        rows["messages"][0]["raw_input"] = None
    else:
        rows["sdk_events"][0]["data"][change] = 99 if change != "action" else "release"
    summary = inspect(tmp_path, data)["windows_input_observations"]
    assert summary["sdk_events"][0]["compatible_windows_message_sequences"] == []
    assert summary["message_sequences_without_sdk_candidate"] == [0]


def test_repeat_direction_and_break_flag_remain_distinct(tmp_path):
    data = windows_capture()
    data["attempt"]["windows_input"]["sdk_events"][0]["data"]["action"] = "repeat"
    assert inspect(tmp_path, data)["windows_input_observations"]["sdk_events"][0][
        "compatible_windows_message_sequences"
    ] == [0]
    data["attempt"]["windows_input"]["messages"][0]["raw_input"]["flags"] = 1
    assert (
        inspect(tmp_path, data)["windows_input_observations"]["sdk_events"][0][
            "compatible_windows_message_sequences"
        ]
        == []
    )


@pytest.mark.parametrize(
    "button,flags", [("left", 1), ("right", 4), ("middle", 16), ("button4", 64), ("button5", 256)]
)
def test_mouse_packet_candidates_do_not_invent_touch_for_other_buttons(tmp_path, button, flags):
    data = windows_capture()
    data["attempt"]["windows_input"]["messages"][0]["raw_input"] = {"kind": "mouse", "button_flags": flags}
    receipt = sdk(event=SDK_MOUSE)
    receipt["data"]["button"] = button
    data["attempt"]["windows_input"]["sdk_events"] = [receipt]
    touch = entry(event="UILayer::ccTouchBegan")
    touch["thread_id"] = 11
    touch["arguments"]["timestamp"] = 10.05
    data["attempt"]["delivery_events"] = [touch]
    summary = inspect(tmp_path, data)["windows_input_observations"]
    assert summary["sdk_events"][0]["compatible_windows_message_sequences"] == [0]
    assert summary["delivery_correlations"][0]["compatible_sdk_event_sequences"] == (
        [0] if button == "left" else []
    )


def test_multi_button_packet_and_down_up_precedence_keep_every_sdk_receipt(tmp_path):
    data = windows_capture()
    data["attempt"]["windows_input"]["messages"][0]["raw_input"] = {
        "kind": "mouse",
        "button_flags": 1 | 2 | 4,
    }
    left, right, release = (
        sdk(event=SDK_MOUSE),
        sdk(sequence=1, event=SDK_MOUSE, wall=550_000),
        sdk(sequence=2, event=SDK_MOUSE, wall=600_000),
    )
    right["data"]["button"] = "right"
    release["data"]["action"] = "release"
    data["attempt"]["windows_input"]["sdk_events"] = [left, right, release]
    rows = inspect(tmp_path, data)["windows_input_observations"]["sdk_events"]
    assert [row["compatible_windows_message_sequences"] for row in rows] == [[0], [0], []]


def test_focus_release_without_raw_packet_and_touch_cancel_remain_unmatched(tmp_path):
    data = windows_capture()
    data["attempt"]["windows_input"]["messages"] = [message(role="main")]
    data["attempt"]["windows_input"]["sdk_events"][0]["data"]["action"] = "release"
    data["attempt"]["delivery_events"][0]["event"] = "UILayer::keyUp"
    summary = inspect(tmp_path, data)["windows_input_observations"]
    assert summary["sdk_events"][0]["compatible_windows_message_sequences"] == []
    assert summary["delivery_correlations"][0]["compatible_sdk_event_sequences"] == [0]
    cancel = entry(event="UILayer::ccTouchCancelled")
    cancel["thread_id"] = 11
    data["attempt"]["delivery_events"] = [cancel]
    assert (
        inspect(tmp_path, data)["windows_input_observations"]["delivery_correlations"][0][
            "compatible_sdk_event_sequences"
        ]
        == []
    )


def test_per_thread_overlaps_and_same_thread_nested_intervals_are_supported(tmp_path):
    data = windows_capture()
    rows = [
        message(exit_time=700_000),
        message(sequence=1, role="main", enter=250_000, exit_time=600_000),
        message(sequence=2, enter=300_000, exit_time=400_000),
    ]
    rows[2]["parent_sequence"] = 0
    data["attempt"]["windows_input"]["messages"] = rows
    assert len(inspect(tmp_path, data)["windows_input_observations"]["messages"]) == 3


def test_late_message_exit_is_valid_but_late_entry_is_not(tmp_path):
    data = windows_capture()
    data["attempt"]["windows_input"]["messages"][0]["wall_exit_ns"] = 25_000_000
    assert inspect(tmp_path, data)["capture_schema_version"] == 7
    data["attempt"]["windows_input"]["messages"][0]["wall_enter_ns"] = 21_000_000
    with pytest.raises(ValueError, match="entry"):
        inspect(tmp_path, data)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["attempt"]["windows_input"].update(enabled=1),
        lambda d: d["attempt"]["windows_input"].update(scope="all_windows"),
        lambda d: d["attempt"]["windows_input"].update(timestamp_unit="physical_input_time"),
        lambda d: d["attempt"]["windows_input"].update(sdk_listener_priority=0),
        lambda d: d["attempt"]["windows_input"].update(extra=True),
        lambda d: d["attempt"]["windows_input"]["windows"][1].update(role="main"),
        lambda d: d["attempt"]["windows_input"]["windows"][1].update(process_id=34),
        lambda d: d["attempt"]["windows_input"]["windows"][1].update(installed=False),
        lambda d: d["attempt"]["windows_input"]["windows"][0].update(thread_id=0),
        lambda d: d["attempt"]["windows_input"]["messages"][0].update(wparam=-1),
        lambda d: d["attempt"]["windows_input"]["messages"][0].update(lparam=2**63),
        lambda d: d["attempt"]["windows_input"]["messages"][0].update(native_return=None),
        lambda d: d["attempt"]["windows_input"]["messages"][0].update(foreground_before=False),
        lambda d: d["attempt"]["windows_input"]["messages"][0].update(message=256),
        lambda d: d["attempt"]["windows_input"]["messages"][0].update(raw_input=[]),
        lambda d: d["attempt"]["windows_input"]["messages"][0].update(input_timestamp_exit=9.0),
        lambda d: d["attempt"]["windows_input"]["messages"][0]["raw_input"].update(vkey=65536),
        lambda d: d["attempt"]["windows_input"]["sdk_events"][0].update(thread_id=22),
        lambda d: d["attempt"]["windows_input"]["sdk_events"][0].update(in_command=True),
        lambda d: d["attempt"]["windows_input"]["sdk_events"][0].update(wall_time_ns=21_000_000),
        lambda d: d["attempt"]["windows_input"]["sdk_events"][0]["data"].update(action=[]),
        lambda d: d["attempt"]["windows_input"]["sdk_events"][0]["data"].update(native_code=-1),
        lambda d: d["attempt"]["windows_input"]["sdk_events"][0]["data"].update(timestamp=float("nan")),
        lambda d: d["attempt"]["windows_input"]["sdk_events"][0]["data"].update(modifiers=True),
        lambda d: d["attempt"]["delivery_events"][0].update(thread_id=22),
        lambda d: d["attempt"]["delivery_events"][0].pop("thread_id"),
        lambda d: d["attempt"].update(replay_bridge={}),
        lambda d: d["environment"].update(windows_input_observer="different-observer"),
    ],
)
def test_schema7_strict_negative_records(tmp_path, mutation):
    data = windows_capture()
    mutation(data)
    refresh_environment(data)
    with pytest.raises(ValueError):
        inspect(tmp_path, data)


@pytest.mark.parametrize(
    "key,value",
    [
        ("overflow_count", 1),
        ("pending_callbacks_at_snapshot", 1),
        ("read_error_count", 1),
        ("errors", ["read failed"]),
    ],
)
def test_incomplete_windows_records_never_establish_valid_terminal_evidence(tmp_path, key, value):
    data = windows_capture()
    data["attempt"]["windows_input"]["integrity"][key] = value
    with pytest.raises(ValueError, match="incomplete"):
        inspect(tmp_path, data)


def test_per_thread_false_parent_and_same_thread_sibling_overlap_rejected(tmp_path):
    data = windows_capture()
    data["attempt"]["windows_input"]["messages"] = [
        message(role="main", exit_time=700_000),
        message(sequence=1, enter=300_000),
    ]
    data["attempt"]["windows_input"]["messages"][1]["parent_sequence"] = 0
    with pytest.raises(ValueError, match="cross threads"):
        inspect(tmp_path, data)
    data["attempt"]["windows_input"]["messages"][0] = message(exit_time=700_000)
    data["attempt"]["windows_input"]["messages"][1]["parent_sequence"] = None
    with pytest.raises(ValueError, match="siblings overlap"):
        inspect(tmp_path, data)


@pytest.mark.parametrize(
    "builder", [capture, rich_capture, mechanics_capture, collision_capture, input_entry_capture]
)
def test_old_schema_outputs_and_strict_fields_are_preserved(tmp_path, builder):
    data = builder()
    result = inspect(tmp_path, data)
    assert "windows_input_observations" not in result
    data["environment"]["windows_input_observer"] = "raw-dispatch-v1"
    refresh_environment(data)
    with pytest.raises(ValueError, match="unknown"):
        load_native_capture(save(tmp_path, data))


def test_schema6_and_7_domains_cannot_be_promoted_to_recorded_replay(tmp_path):
    source = recorded_source()
    baseline = target_baseline(source)
    source_path = save(tmp_path, source, "source.json")
    baseline_path = save(tmp_path, baseline, "baseline.json")
    plan = export_recorded_replay_plan(source_path, baseline_path)
    plan_path = save(tmp_path, plan, "plan.json")
    data = schema6_replay(source, baseline, plan, hashlib.sha256(plan_path.read_bytes()).hexdigest())
    data["environment"]["windows_input_observer"] = "raw-dispatch-v1"
    refresh_environment(data)
    with pytest.raises(ValueError, match="unknown"):
        inspect(tmp_path, data)
    windows = save(tmp_path, windows_capture(), "windows.json")
    with pytest.raises(ValueError, match="schema 5"):
        export_recorded_replay_plan(windows, baseline_path)
    second = windows_capture()
    second["attempt"]["id"] = "another-observer"
    with pytest.raises(ValueError, match="controlled source-replay"):
        compare_native_captures([windows, save(tmp_path, second, "second.json")])


def test_opt_in_environment_identity_changes_and_skipped_scope_is_explicit(tmp_path):
    data = windows_capture()
    data["attempt"]["windows_input"]["skipped"] = {
        "background_raw_count": 5,
        "mouse_motion_count": 17,
        "unsupported_raw_count": 3,
    }
    data["attempt"]["windows_input"]["messages"] = []
    data["attempt"]["windows_input"]["sdk_events"] = []
    summary = inspect(tmp_path, data)["windows_input_observations"]
    assert summary["skipped"] == data["attempt"]["windows_input"]["skipped"]
    assert summary["delivery_correlations"][0]["correlation_status"] == "no_compatible_candidate"
    assert data["environment_sha256"] != input_entry_capture(driver="none")["environment_sha256"]


@pytest.mark.parametrize("kind", ["messages", "sdk_events"])
def test_workload_bounds_do_not_silently_truncate_windows_evidence(tmp_path, kind):
    data = windows_capture()
    data["attempt"]["windows_input"][kind] *= 2049
    with pytest.raises(ValueError, match="2048"):
        inspect(tmp_path, data)


def test_native_only_observer_rejects_clock_intervention_and_missing_contract(tmp_path):
    data = windows_capture()
    data["environment"]["clocks"].update(
        clock_policy="fixed-base-60",
        intervention_hook="GJBaseGameLayer::update",
        step_numerator=1,
        step_denominator=60,
    )
    refresh_environment(data)
    with pytest.raises(ValueError, match="clock policy"):
        inspect(tmp_path, data)
    data = windows_capture()
    data["attempt"].pop("windows_input")
    with pytest.raises(ValueError, match="missing windows_input"):
        inspect(tmp_path, data)


def test_sdk_future_point_and_bad_native_context_cannot_match_ui(tmp_path):
    data = windows_capture()
    data["attempt"]["windows_input"]["sdk_events"][0]["wall_time_ns"] = 1_100_000
    summary = inspect(tmp_path, data)["windows_input_observations"]
    assert summary["delivery_correlations"][0]["compatible_sdk_event_sequences"] == []
    data["attempt"]["windows_input"]["sdk_events"][0].update(
        update_sequence=0, scheduler_sequence=0, wall_time_ns=21_500_000
    )
    with pytest.raises(ValueError):
        inspect(tmp_path, data)


def test_unknown_cocos_codes_and_full_raw_integer_precision_are_preserved(tmp_path):
    data = windows_capture()
    row = data["attempt"]["windows_input"]["messages"][0]
    row.update(wparam=2**64 - 1, lparam=-(2**63), native_return=2**63 - 1)
    receipt = data["attempt"]["windows_input"]["sdk_events"][0]
    receipt["data"]["key_code"] = 2147483647
    data["attempt"]["delivery_events"][0]["arguments"]["key_code"] = 2147483647
    result = inspect(tmp_path, data)
    assert result["windows_input_observations"]["messages"][0]["wparam"] == 2**64 - 1
    assert (
        result["input_entry_observations"]["keyboard_edges"][0]["key_name"]
        == "Unknown Cocos key code 2147483647"
    )
    assert result["windows_input_observations"]["delivery_correlations"][0][
        "compatible_sdk_event_sequences"
    ] == [0]
