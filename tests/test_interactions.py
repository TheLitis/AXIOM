"""Variant gates require a frozen change, applied effect and eligible response."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_fixtures import effect_check, matrix_v3
from test_native import collision_capture, mechanic_event, save

from axiom.interactions import compare_fixture_variants, load_variant_study


def test_public_variant_study_binds_all_frozen_collision_and_trigger_pairs():
    root = Path(__file__).resolve().parents[1]
    study = load_variant_study(
        root / "examples/native/interaction-variants.json", root / "examples/native/interaction-matrix.json"
    )
    assert {case["id"] for case in study["cases"]} == {
        "raised-platform",
        "slope-ascent",
        "ceiling-contact",
        "toggle-solid-off",
        "move-solid-away",
        "spawn-toggle-chain",
    }
    assert len({case[role]["case_id"] for case in study["cases"] for role in ("positive", "control")}) == 12
    assert all(case["receipt_requirements"] for case in study["cases"])


def artifacts(tmp_path):
    matrix = matrix_v3()
    base = matrix["cases"][0]
    base["response_checks"] = []
    control = deepcopy(base)
    for case, role, y in ((base, "positive", 15), (control, "control", -15)):
        case["id"] = role
        case["level_string"] = f"kA13,0,kA15,0,kA16,0,kA14,0;1,1,2,30,3,{y},57,1;1,1,2,600,3,-15;"
        case["level_sha256"] = hashlib.sha256(case["level_string"].encode()).hexdigest()
    base["runs"][1]["required_effect_checks"] = [effect_check()]
    matrix["cases"] = [base, control]
    matrix_path = save(tmp_path, matrix, "matrix.json")
    study = {
        "schema_version": 1,
        "kind": "native_fixture_variant_study",
        "provenance": {"origin": "generated_synthetic", "native_verification": "not_recorded"},
        "fixture_matrix_sha256": hashlib.sha256(matrix_path.read_bytes()).hexdigest(),
        "cases": [
            {
                "id": "raised-variant",
                "positive": {"case_id": "positive", "run_id": "replay"},
                "control": {"case_id": "control", "run_id": "replay"},
                "controlled_changes": [
                    {"object_index": 0, "property_key": "3", "positive": "15", "control": "-15"}
                ],
                "prefix_window": {"first": 0, "last": 0},
                "response_window": {"first": 1, "last": 1},
                "response_kind": "selected_trajectory",
                "player": 1,
                "fields": ["y"],
                "required_mechanics": {
                    "mode": "cube",
                    "gravity_inverted": False,
                    "vehicle_size": 1.0,
                    "player_speed": 0.9,
                    "dual_active": False,
                },
                "receipt_requirements": [],
                "constant_target_checks": [],
            }
        ],
    }
    captures = []
    for case in matrix["cases"]:
        capture = collision_capture(attempt_id="synthetic-" + case["id"])
        capture["challenge"]["level_sha256"] = case["level_sha256"]
        captures.append(capture)
    captures[0]["attempt"]["trace"][1]["state"]["player1"]["y"] = 106.0
    captures[0]["attempt"]["mechanic_events"] = [mechanic_event(captures[0])]
    return matrix_path, study, captures


def compare(tmp_path, matrix_path, study, captures):
    return compare_fixture_variants(
        save(tmp_path, study, "study.json"),
        matrix_path,
        "raised-variant",
        save(tmp_path, captures[0], "positive.json"),
        save(tmp_path, captures[1], "control.json"),
    )


def test_frozen_change_and_applied_effect_with_live_trajectory_pass(tmp_path):
    result = compare(tmp_path, *artifacts(tmp_path))
    assert result["status"] == "declared_variant_effect_observed"
    assert all(result["checks"].values())
    assert result["trajectory_witness"]["command_index"] == 1
    assert result["ordinary_input_equivalence"] == "not_established"


@pytest.mark.parametrize(
    "change",
    [
        lambda study: study["cases"][0]["controlled_changes"][0].update(positive="16"),
        lambda study: study["cases"][0]["controlled_changes"].clear(),
        lambda study: study.update(fixture_matrix_sha256="a" * 64),
        lambda study: study["cases"][0].update(prefix_window={"first": 1, "last": 1}),
        lambda study: study["cases"][0].update(response_kind=[]),
        lambda study: study["cases"][0]["required_mechanics"].update(mode=[]),
        lambda study: study["cases"][0].update(player=True),
    ],
)
def test_invalid_or_incomplete_controlled_declarations_rejected(tmp_path, change):
    matrix_path, study, captures = artifacts(tmp_path)
    change(study)
    with pytest.raises(ValueError):
        compare(tmp_path, matrix_path, study, captures)


def test_callback_presence_without_applied_change_cannot_pass(tmp_path):
    matrix_path, study, captures = artifacts(tmp_path)
    event = captures[0]["attempt"]["mechanic_events"][0]
    event["state_after"] = deepcopy(event["state_before"])
    result = compare(tmp_path, matrix_path, study, captures)
    assert result["checks"]["positive_fixture_matches"] is False
    assert result["checks"]["declared_response_observed"] is True
    assert result["status"] == "declared_variant_effect_not_established"


def test_response_outside_declared_live_domain_and_changed_prefix_fail(tmp_path):
    matrix_path, study, captures = artifacts(tmp_path)
    captures[0]["attempt"]["trace"][1]["state"]["player1"]["vehicle_size"] = 0.6
    captures[0]["attempt"]["trace"][0]["state"]["player1"]["y"] = 105.1
    result = compare(tmp_path, matrix_path, study, captures)
    assert result["checks"]["declared_response_observed"] is False
    assert result["checks"]["selected_initial_prefix_matches"] is False


def test_constant_target_requires_all_declared_eligible_samples(tmp_path):
    matrix_path, study, captures = artifacts(tmp_path)
    study["cases"][0]["constant_target_checks"] = [
        {
            "variant": "control",
            "group_id": 1,
            "field": "is_group_disabled",
            "command_window": {"first": 0, "last": 1},
            "value": False,
        }
    ]
    assert compare(tmp_path, matrix_path, study, captures)["checks"]["control_target_requirements_observed"]
    captures[1]["attempt"]["trace"][1]["watched_objects"][0]["is_group_disabled"] = True
    assert not compare(tmp_path, matrix_path, study, captures)["checks"][
        "control_target_requirements_observed"
    ]


def test_receipt_argument_and_ancestor_require_actual_context(tmp_path):
    matrix_path, study, captures = artifacts(tmp_path)
    requirement = {
        "variant": "positive",
        "event": "PlayerObject::collidedWithObject",
        "player": 1,
        "object_group_id": 1,
        "command_window": {"first": 1, "last": 1},
        "arguments": {"skip_check": False},
        "min_events": 1,
        "ancestor": None,
    }
    study["cases"][0]["receipt_requirements"] = [requirement]
    assert compare(tmp_path, matrix_path, study, captures)["checks"]["required_callback_contexts_observed"]
    requirement["ancestor"] = {"event": "GJBaseGameLayer::spawnGroup", "arguments": {"group": 202}}
    assert not compare(tmp_path, matrix_path, study, captures)["checks"][
        "required_callback_contexts_observed"
    ]


def test_unmentioned_second_raw_change_is_rejected(tmp_path):
    matrix_path, study, _ = artifacts(tmp_path)
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    case = matrix["cases"][0]
    case["level_string"] = case["level_string"].replace("2,30,", "2,31,")
    case["level_sha256"] = hashlib.sha256(case["level_string"].encode()).hexdigest()
    save(tmp_path, matrix, "matrix.json")
    study["fixture_matrix_sha256"] = hashlib.sha256(matrix_path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="ALL changed"):
        load_variant_study(save(tmp_path, study, "study.json"), matrix_path)


def test_nested_receipt_requires_matching_actual_ancestor_arguments(tmp_path):
    matrix_path, study, captures = artifacts(tmp_path)
    parent = mechanic_event(captures[0], event="GJBaseGameLayer::spawnGroup")
    parent["arguments"]["group"] = 202
    child = captures[0]["attempt"]["mechanic_events"][0]
    child.update(sequence=1, parent_sequence=0, wall_enter_ns=1_000_004, wall_exit_ns=1_000_004)
    captures[0]["attempt"]["mechanic_events"] = [parent, child]
    requirement = {
        "variant": "positive",
        "event": "PlayerObject::collidedWithObject",
        "player": 1,
        "object_group_id": 1,
        "command_window": {"first": 1, "last": 1},
        "arguments": {"skip_check": False},
        "min_events": 1,
        "ancestor": {"event": "GJBaseGameLayer::spawnGroup", "arguments": {"group": 202}},
    }
    study["cases"][0]["receipt_requirements"] = [requirement]
    result = compare(tmp_path, matrix_path, study, captures)
    assert result["status"] == "declared_variant_effect_observed"
    assert result["receipt_checks"][0]["witnesses"][0]["ancestor_sequences"] == [0]
    parent["arguments"]["group"] = 999
    result = compare(tmp_path, matrix_path, study, captures)
    assert result["checks"]["required_callback_contexts_observed"] is False
