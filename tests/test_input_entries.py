"""Raw input entry evidence must retain identity without inventing device origin."""

from copy import deepcopy

import pytest
from test_equivalence import delivery_pair
from test_fixtures import capture_v4, effect_check, matrix_v2, matrix_v3, response
from test_interactions import artifacts as variant_artifacts
from test_interactions import compare as compare_variants
from test_native import (
    capture,
    collision_capture,
    delivery_event,
    input_entry_capture,
    mechanic_event,
    mechanics_capture,
    rich_capture,
    save,
)

from axiom.equivalence import compare_native_delivery
from axiom.fixtures import inspect_fixture_capture
from axiom.native import (
    compare_native_captures,
    delivery_context_signature,
    delivery_timestamp_signature,
    inspect_native_capture,
    load_native_capture,
)


def upgrade(document):
    data = deepcopy(document)
    data["schema_version"] = 5
    for event in data["attempt"]["delivery_events"]:
        event["native_return"] = None
    return data


def entry(*, event="UILayer::keyDown", code=32):
    row = delivery_event(event=event)
    row["native_return"] = True if event == "UILayer::ccTouchBegan" else None
    if event.startswith("UILayer::ccTouch"):
        row["arguments"] = {"touch_id": -7, "view_x": -3.5, "view_y": 280.5, "timestamp": 8.25}
    else:
        row["arguments"]["key_code"] = code
    return row


def inspect(tmp_path, data):
    return inspect_native_capture(save(tmp_path, data))


def repeat(tmp_path, first, second):
    return compare_native_captures(
        [save(tmp_path, first, "first.json"), save(tmp_path, second, "second.json")]
    )


@pytest.mark.parametrize(
    "event", ["UILayer::ccTouchBegan", "UILayer::ccTouchEnded", "UILayer::ccTouchCancelled"]
)
@pytest.mark.parametrize("null_pointer", [False, True])
def test_touch_payload_and_native_result_are_retained_without_device_name(tmp_path, event, null_pointer):
    data = input_entry_capture(driver="none")
    row = entry(event=event)
    if null_pointer:
        row["arguments"] = dict.fromkeys(row["arguments"], None)
    data["attempt"]["delivery_events"] = [row]
    report = inspect(tmp_path, data)
    observations = report["input_entry_observations"]
    touch = observations["touch_edges"][0]
    assert {key: touch[key] for key in row["arguments"]} == row["arguments"]
    assert touch["native_return"] == row["native_return"]
    assert observations["counts"]["null_touch_arguments"] == int(null_pointer)
    assert observations["physical_device"] == "not_identified"
    assert observations["touch_timestamp_units"] == "raw_CCTouch_getTimestamp_uncharacterized"
    assert report["attempt"]["input_source"] == "unknown"
    assert report["authentication_status"] == "not_authenticated"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.pop("native_return"),
        lambda r: r.update(native_return=None),
        lambda r: r.update(native_return=1),
        lambda r: r["arguments"].update(touch_id=True),
        lambda r: r["arguments"].update(touch_id=1.0),
        lambda r: r["arguments"].update(touch_id=2**31),
        lambda r: r["arguments"].update(view_x=True),
        lambda r: r["arguments"].update(view_y=float("inf")),
        lambda r: r["arguments"].update(timestamp=float("nan")),
        lambda r: r["arguments"].update(touch_id=None),
        lambda r: r["arguments"].update(timestamp=None),
        lambda r: r["arguments"].pop("view_x"),
        lambda r: r["arguments"].update(device="left_mouse"),
    ],
)
def test_touch_partial_null_bad_raw_values_and_fabricated_device_are_rejected(tmp_path, mutation):
    data = input_entry_capture()
    row = entry(event="UILayer::ccTouchBegan")
    mutation(row)
    data["attempt"]["delivery_events"] = [row]
    with pytest.raises(ValueError):
        load_native_capture(save(tmp_path, data))


@pytest.mark.parametrize(
    "event",
    [
        "UILayer::keyDown",
        "UILayer::keyUp",
        "UILayer::ccTouchEnded",
        "UILayer::ccTouchCancelled",
        "GJBaseGameLayer::processQueuedButtons",
    ],
)
@pytest.mark.parametrize("result", [False, True, 0])
def test_void_delivery_callbacks_cannot_claim_boolean_native_result(tmp_path, event, result):
    data = input_entry_capture()
    row = entry(event=event)
    if event == "GJBaseGameLayer::processQueuedButtons":
        row.update(
            arguments={"dt_seconds": 0.02, "clear_input_queue": False},
            queue_before=deepcopy(row["queue_after"]),
        )
    row["native_return"] = result
    data["attempt"]["delivery_events"] = [row]
    with pytest.raises(ValueError, match="native_return"):
        load_native_capture(save(tmp_path, data))


@pytest.mark.parametrize(
    "event", ["UILayer::keyDown", "UILayer::keyUp", "GJBaseGameLayer::processQueuedButtons"]
)
def test_every_schema5_legacy_delivery_kind_requires_explicit_null_result(tmp_path, event):
    data = input_entry_capture()
    row = entry(event=event)
    if event == "GJBaseGameLayer::processQueuedButtons":
        row.update(
            arguments={"dt_seconds": 0.02, "clear_input_queue": False},
            queue_before=deepcopy(row["queue_after"]),
        )
    row.pop("native_return")
    data["attempt"]["delivery_events"] = [row]
    with pytest.raises(ValueError, match="native_return"):
        load_native_capture(save(tmp_path, data))


@pytest.mark.parametrize(
    "code,name",
    [
        (0, "KEY_None"),
        (32, "KEY_Space"),
        (87, "KEY_W"),
        (83, "KEY_S"),
        (65, "KEY_A"),
        (68, "KEY_D"),
        (37, "KEY_Left"),
        (38, "KEY_Up"),
        (39, "KEY_Right"),
        (40, "KEY_Down"),
        (283, "KEY_ArrowUp"),
        (4352, "MOUSE_4"),
        (4353, "MOUSE_5"),
        (2**31 - 1, "Unknown Cocos key code 2147483647"),
    ],
)
def test_all_raw_key_codes_named_when_known_and_never_filtered_to_space(tmp_path, code, name):
    data = input_entry_capture(driver="none")
    row = entry(code=code)
    row.update(
        command_index=0,
        in_command=False,
        update_sequence=None,
        scheduler_sequence=None,
        wall_enter_ns=0,
        wall_exit_ns=1,
        queue_after=[],
    )
    row["arguments"]["timestamp"] = 900.5
    data["attempt"]["delivery_events"] = [row]
    summary = inspect(tmp_path, data)["input_entry_observations"]
    edge = summary["keyboard_edges"][0]
    assert edge["key_code"] == code and edge["key_name"] == name
    assert edge["command_index"] == 0 and edge["in_command"] is False
    assert edge["appended_queued_commands"] == []
    assert edge["timestamp"] != edge["layer_timestamp_before"]
    assert summary["game_action_mapping"] == "not_inferred_from_callback_entry"
    assert summary["counts"]["keys"][0]["key_down_count"] == 1


def test_keyboard_autorepeat_edges_are_ordered_and_not_flattened(tmp_path):
    data = input_entry_capture(driver="none")
    events = [entry(code=87), entry(code=87), entry(event="UILayer::keyUp", code=87)]
    for index, event in enumerate(events):
        event.update(sequence=index, wall_enter_ns=1_000_003 + 3 * index, wall_exit_ns=1_000_005 + 3 * index)
    data["attempt"]["delivery_events"] = events
    summary = inspect(tmp_path, data)["input_entry_observations"]
    assert [row["sequence"] for row in summary["keyboard_edges"]] == [0, 1, 2]
    assert [row["pressed"] for row in summary["keyboard_edges"]] == [True, True, False]
    assert summary["counts"]["keys"] == [
        {"key_code": 87, "key_name": "KEY_W", "key_down_count": 2, "key_up_count": 1}
    ]


def test_nonprefix_queue_change_has_no_invented_appended_command_attribution(tmp_path):
    data = input_entry_capture()
    row = entry(code=65)
    row["queue_before"] = deepcopy(row["queue_after"])
    row["queue_after"][0]["pressed"] = False
    data["attempt"]["delivery_events"] = [row]
    edge = inspect(tmp_path, data)["input_entry_observations"]["keyboard_edges"][0]
    assert edge["queue_prefix_retained"] is False
    assert edge["appended_queued_commands"] is None
    assert edge["queue_attribution"] == "unavailable_nonprefix_queue_change"


def test_actual_queue_append_keeps_raw_command_timestamp_and_step(tmp_path):
    data = input_entry_capture()
    row = entry(code=38)
    data["attempt"]["delivery_events"] = [row]
    summary = inspect(tmp_path, data)["input_entry_observations"]
    assert summary["keyboard_edges"][0]["appended_queued_commands"] == row["queue_after"]
    assert summary["queue_origin_authentication"] == "not_established"


def test_touch_event_nesting_and_zero_outside_command_counter_remain_validated(tmp_path):
    data = input_entry_capture()
    parent = entry(event="UILayer::ccTouchBegan")
    parent.update(wall_enter_ns=900_000, wall_exit_ns=1_000_010)
    child = entry(code=87)
    child.update(sequence=1, parent_sequence=0)
    data["attempt"]["delivery_events"] = [parent, child]
    assert inspect(tmp_path, data)["input_entry_observations"]["keyboard_edges"][0]["parent_sequence"] == 0
    child["command_index"] = 2
    with pytest.raises(ValueError, match="different command counter"):
        load_native_capture(save(tmp_path, data))
    parent.update(
        command_index=0,
        in_command=False,
        update_sequence=None,
        scheduler_sequence=None,
        wall_enter_ns=0,
        wall_exit_ns=1,
    )
    data["attempt"]["delivery_events"] = [parent]
    assert inspect(tmp_path, data)["input_entry_observations"]["touch_edges"][0]["command_index"] == 0


@pytest.mark.parametrize(
    "field,value", [("touch_id", 12), ("view_x", 5.5), ("view_y", 6.5), ("native_return", False)]
)
def test_touch_identity_coordinates_and_native_result_remain_exact_repeat_gates(tmp_path, field, value):
    first = input_entry_capture()
    first["attempt"]["delivery_events"] = [entry(event="UILayer::ccTouchBegan")]
    second = deepcopy(first)
    second["attempt"]["id"] = "other"
    row = second["attempt"]["delivery_events"][0]
    if field == "native_return":
        row[field] = value
    else:
        row["arguments"][field] = value
    report = repeat(tmp_path, first, second)
    assert report["status"] == "recorded_subset_inconsistent"
    assert report["component_consistency"]["native_delivery_context_equal"] is False


def test_touch_raw_timestamp_is_diagnostic_and_projection_does_not_mutate_it(tmp_path):
    first = input_entry_capture()
    first["attempt"]["delivery_events"] = [entry(event="UILayer::ccTouchBegan")]
    second = deepcopy(first)
    second["attempt"]["id"] = "other"
    row = second["attempt"]["delivery_events"][0]
    row["arguments"]["timestamp"] = -200.0
    projected = delivery_context_signature(second["attempt"]["delivery_events"])
    assert projected[0]["arguments"] == {"touch_id": -7, "view_x": -3.5, "view_y": 280.5}
    assert projected[0]["native_return"] is True
    assert row["arguments"]["timestamp"] == -200.0
    assert (
        delivery_timestamp_signature(second["attempt"]["delivery_events"])[0]["callback_timestamp"] == -200.0
    )
    report = repeat(tmp_path, first, second)
    assert report["status"] == "recorded_subset_consistent"
    assert len(report["component_consistency"]) == 18
    assert report["comparisons"][0]["delivery_absolute_timestamp_diagnostics"]["equal"] is False


def test_extra_actual_inputs_never_disappear_when_touch_time_is_projected(tmp_path):
    first = input_entry_capture(driver="scheduled-ui-callback")
    first["attempt"]["delivery_events"] = [entry(event="UILayer::ccTouchBegan")]
    second = deepcopy(first)
    second["attempt"]["id"] = "other"
    extra = deepcopy(second["attempt"]["inputs"][0])
    extra.update(sequence=2, pressed=False, wall_time_ns=1_000_010)
    second["attempt"]["inputs"].append(extra)
    result = repeat(tmp_path, first, second)
    assert result["component_consistency"]["recorded_inputs_equal"] is False
    assert result["component_consistency"]["native_delivery_context_equal"] is True


@pytest.mark.parametrize("builder", [capture, rich_capture, mechanics_capture, collision_capture])
def test_older_inspection_outputs_do_not_gain_input_entry_summary(tmp_path, builder):
    assert "input_entry_observations" not in inspect(tmp_path, builder())


def test_schema4_rejects_new_return_field_and_all_touch_event_names(tmp_path):
    data = collision_capture()
    row = entry()
    data["attempt"]["delivery_events"] = [row]
    with pytest.raises(ValueError, match="native_return"):
        load_native_capture(save(tmp_path, data))
    for name in ("UILayer::ccTouchBegan", "UILayer::ccTouchEnded", "UILayer::ccTouchCancelled"):
        row = entry(event=name)
        row.pop("native_return")
        data["attempt"]["delivery_events"] = [row]
        with pytest.raises(ValueError, match="Unsupported native delivery event"):
            load_native_capture(save(tmp_path, data))


def test_schema4_and_schema5_repeat_or_delivery_cannot_be_mixed(tmp_path):
    with pytest.raises(ValueError, match="schema_version"):
        repeat(tmp_path, collision_capture(), input_entry_capture(attempt_id="other"))
    owned, ui = delivery_pair()
    with pytest.raises(ValueError, match="schema_version"):
        compare_native_delivery(save(tmp_path, owned, "owned.json"), save(tmp_path, upgrade(ui), "ui.json"))


def test_same_schema5_synthetic_space_delivery_retains_existing_queue_witness(tmp_path):
    owned, ui = [upgrade(data) for data in delivery_pair()]
    result = compare_native_delivery(save(tmp_path, owned, "owned.json"), save(tmp_path, ui, "ui.json"))
    assert result["status"] == "recorded_delivery_subset_consistent"
    assert result["ordinary_os_input_equivalence"] == "not_established"
    ui["attempt"]["delivery_events"][0]["arguments"]["key_code"] = 87
    result = compare_native_delivery(save(tmp_path, owned, "owned.json"), save(tmp_path, ui, "ui.json"))
    assert result["checks"]["ui_plan_queue_path_witnessed"] is False


def test_same_schema5_matrix_effect_and_owned_response_are_supported(tmp_path):
    evidence, spec = upgrade(capture_v4()), matrix_v3()
    spec["cases"][0]["runs"][1]["required_effect_checks"] = [effect_check()]
    evidence["attempt"]["mechanic_events"] = [mechanic_event(evidence)]
    report = inspect_fixture_capture(
        save(tmp_path, spec, "matrix.json"), "cube-flat", "replay", save(tmp_path, evidence)
    )
    assert report["status"] == "fixture_observations_match"
    assert report["checks"]["native_contact_effect_fields_available"]
    reference, changed = upgrade(capture_v4(plan=False)), upgrade(capture_v4())
    changed["attempt"]["trace"][1]["state"]["player1"]["y"] += 1
    result = response(tmp_path, spec=matrix_v2(), reference=reference, changed=changed)
    assert result["status"] == "selected_response_observed"
    # A mixed version is rejected before any route can be promoted to owned evidence.
    with pytest.raises(ValueError, match="schema_version"):
        response(tmp_path, spec=matrix_v2(), reference=capture_v4(plan=False), changed=upgrade(capture_v4()))


def test_schema5_observed_ui_requests_do_not_become_owned_fixture_response(tmp_path):
    reference = upgrade(capture_v4(plan=False))
    changed = upgrade(capture_v4(driver="scheduled-ui-callback"))
    changed["attempt"]["trace"][1]["state"]["player1"]["y"] += 1
    result = response(tmp_path, spec=matrix_v2(), reference=reference, changed=changed)
    assert result["status"] == "selected_response_not_established"
    assert result["checks"]["owned_replay_delivery_in_both_captures"] is False


def test_same_schema5_variant_effect_supported_but_mixed_versions_rejected(tmp_path):
    matrix_path, study, captures = variant_artifacts(tmp_path)
    captures = [upgrade(data) for data in captures]
    assert (
        compare_variants(tmp_path, matrix_path, study, captures)["status"]
        == "declared_variant_effect_observed"
    )
    captures[1]["schema_version"] = 4
    with pytest.raises(ValueError, match="schema_version"):
        compare_variants(tmp_path, matrix_path, study, captures)
