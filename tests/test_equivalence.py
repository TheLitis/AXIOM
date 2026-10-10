"""Synthetic adversarial evidence for a bounded delivery comparison."""

import json
from copy import deepcopy

import pytest
from test_native import collision_capture, delivery_event, mechanic_event, refresh_environment, save

from axiom.cli import main
from axiom.equivalence import compare_native_delivery


def delivery_pair():
    owned = collision_capture(attempt_id="synthetic-owned")
    ui = collision_capture(attempt_id="synthetic-ui", driver="scheduled-ui-callback")
    callback = delivery_event()
    callback.update(wall_enter_ns=900_000, wall_exit_ns=900_005)
    processing = deepcopy(callback)
    processing.update(
        sequence=1,
        event="GJBaseGameLayer::processQueuedButtons",
        arguments={"dt_seconds": 0.02, "clear_input_queue": False},
        queue_before=deepcopy(callback["queue_after"]),
        queue_after=[],
        wall_enter_ns=900_006,
        wall_exit_ns=1_000_010,
    )
    ui["attempt"]["delivery_events"] = [callback, processing]
    return owned, ui


def compare(tmp_path, owned, ui):
    return compare_native_delivery(save(tmp_path, owned, "owned.json"), save(tmp_path, ui, "ui.json"))


def test_supplied_matching_routes_require_actual_queue_and_native_receipts(tmp_path):
    result = compare(tmp_path, *delivery_pair())
    assert result["status"] == "recorded_delivery_subset_consistent"
    assert all(result["checks"].values())
    witness = result["ui_queue_path"]["witnesses"][0]["witness"]
    assert witness["queued_button"]["timestamp"] == 0.004
    assert witness["request_sequence"] == 0
    assert result["ordinary_os_input_equivalence"] == "not_established"
    assert result["human_authorship"] == "not_established"
    assert result["captures"][0]["origin"] == "synthetic"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda ui: ui["attempt"]["delivery_events"].clear(),
        lambda ui: ui["attempt"]["delivery_events"][0].update(queue_after=[]),
        lambda ui: ui["attempt"]["delivery_events"][1].update(
            queue_after=deepcopy(ui["attempt"]["delivery_events"][1]["queue_before"])
        ),
        lambda ui: ui["attempt"]["delivery_events"][0]["arguments"].update(timestamp=0.005),
        lambda ui: ui["attempt"]["delivery_events"][1].update(wall_exit_ns=999_999),
    ],
)
def test_missing_wrong_or_unprocessed_queue_cannot_pass(tmp_path, mutation):
    owned, ui = delivery_pair()
    mutation(ui)
    result = compare(tmp_path, owned, ui)
    assert result["status"] == "recorded_delivery_equivalence_not_established"
    assert result["checks"]["ui_plan_queue_path_witnessed"] is False


@pytest.mark.parametrize(
    "mutation,component",
    [
        (
            lambda ui: ui["attempt"]["trace"][1]["state"]["player1"].update(y=106.0),
            "process_commands_trace_equal",
        ),
        (
            lambda ui: ui["attempt"]["trace"][1]["state"]["player1"].update(is_on_ground=False),
            "process_commands_trace_equal",
        ),
        (
            lambda ui: ui["attempt"]["trace"][1]["watched_objects"][0].update(is_disabled=True),
            "process_commands_trace_equal",
        ),
        (lambda ui: ui["attempt"]["inputs"][1].update(native_return=False), "native_input_receipts_equal"),
        (lambda ui: ui["attempt"]["inputs"][0].update(in_command=False), "native_input_receipts_equal"),
        (
            lambda ui: ui["attempt"]["terminal"]["state"]["player1"].update(rotation=1),
            "terminal_snapshot_equal",
        ),
    ],
)
def test_selected_divergences_have_exact_component_diagnostics(tmp_path, mutation, component):
    owned, ui = delivery_pair()
    mutation(ui)
    result = compare(tmp_path, owned, ui)
    assert result["status"] == "recorded_delivery_equivalence_not_established"
    assert result["checks"][component] is False
    diagnostic = result["diagnostics"][component.removesuffix("_equal")]
    assert diagnostic["first_difference"] is not None


def test_extra_native_cleanup_receipts_cannot_disappear(tmp_path):
    owned, ui = delivery_pair()
    extra = deepcopy(ui["attempt"]["inputs"])
    for index, row in enumerate(extra):
        row.update(sequence=index + 2, pressed=False, wall_time_ns=1_000_003 + index)
        if row["phase"] == "push":
            row["phase"] = "release"
    ui["attempt"]["inputs"] += extra
    result = compare(tmp_path, owned, ui)
    diagnostic = result["diagnostics"]["native_input_receipts"]
    assert diagnostic["owned_record_count"] == 2
    assert diagnostic["ui_record_count"] == 4
    assert result["checks"]["native_input_receipts_equal"] is False
    assert diagnostic["first_difference"]["record_index"] == 2


def test_native_mechanic_return_and_snapshot_remain_compared(tmp_path):
    owned, ui = delivery_pair()
    owned["attempt"]["mechanic_events"] = [mechanic_event(owned)]
    ui["attempt"]["mechanic_events"] = [mechanic_event(ui)]
    ui["attempt"]["mechanic_events"][0]["state_after"]["player1"]["y_velocity"] = 0.001
    result = compare(tmp_path, owned, ui)
    assert result["checks"]["selected_mechanic_events_equal"] is False


def test_object_runtime_ids_are_diagnostic_but_stable_group_and_type_are_identity(tmp_path):
    owned, ui = delivery_pair()
    ui["object_watches"][0]["runtime_unique_id"] = 999
    assert compare(tmp_path, owned, ui)["status"] == "recorded_delivery_subset_consistent"
    ui["object_watches"][0]["object_id"] = 2
    with pytest.raises(ValueError, match="object watches"):
        compare(tmp_path, owned, ui)


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda ui: ui["attempt"].update(id="synthetic-owned"), "distinct"),
        (lambda ui: ui["attempt"].update(start_kind="practice"), "full-start"),
        (lambda ui: ui["challenge"].update(level_sha256="a" * 64), "challenge"),
        (lambda ui: ui["collector"].update(source_tree_sha256="a" * 64), "collector"),
        (lambda ui: ui["attempt"]["planned_inputs"][0].update(command_index=2), "same declared"),
    ],
)
def test_incompatible_pair_cannot_be_pooled(tmp_path, mutation, match):
    owned, ui = delivery_pair()
    mutation(ui)
    with pytest.raises(ValueError, match=match):
        compare(tmp_path, owned, ui)


def test_environment_refresh_still_cannot_pool_changed_game_build(tmp_path):
    owned, ui = delivery_pair()
    ui["environment"]["game_executable_sha256"] = "9" * 64
    refresh_environment(ui)
    with pytest.raises(ValueError, match="challenge|environment"):
        compare(tmp_path, owned, ui)


def test_empty_plans_do_not_establish_queue_equivalence(tmp_path):
    owned, ui = delivery_pair()
    for capture in (owned, ui):
        capture["attempt"].update(planned_inputs=[], inputs=[])
    with pytest.raises(ValueError, match="nonempty"):
        compare(tmp_path, owned, ui)


def test_cli_writes_valid_negative_result_without_confusing_exit_status(tmp_path):
    owned, ui = delivery_pair()
    ui["attempt"]["delivery_events"].clear()
    output = tmp_path / "result.json"
    assert (
        main(
            [
                "native-delivery-compare",
                str(save(tmp_path, owned, "owned.json")),
                str(save(tmp_path, ui, "ui.json")),
                "--json",
                str(output),
            ]
        )
        == 0
    )
    assert (
        json.loads(output.read_text(encoding="utf-8"))["status"]
        == "recorded_delivery_equivalence_not_established"
    )
