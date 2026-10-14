"""Joint command-index plans are synthetic requests, never engine outcomes."""

import hashlib
import itertools
import json
from copy import deepcopy

import pytest
from test_native import input_entry_capture, mechanics_capture, refresh_environment

from axiom.native import MAX_PLANNED_INPUTS, MAX_TRACE_RECORDS, canonical_sha256, load_native_capture
from axiom.probeplan import (
    MAX_OFFSET,
    create_probe_study,
    load_probe_study,
    point_replay,
    replay_bytes,
    study_sha256,
    validate_probe_study,
)


def reference_capture(inputs=None, *, version=5):
    """A fully synthetic owned replay with four inputs and terminal command 20.

    This reusable test builder does not represent a real game execution. Schema
    4 is also available; custom nonempty input schedules may lie in 1..20.
    """
    result = input_entry_capture(policy="fixed-scheduler-240")
    result["schema_version"] = version
    result["challenge"]["id"] = "synthetic-probe-reference"
    result["attempt"]["id"] = "synthetic-probe-reference-1"
    if inputs is None:
        inputs = [
            {"command_index": command, "player": 1, "button": 1, "pressed": pressed}
            for command, pressed in ((4, True), (8, False), (12, True), (16, False))
        ]
    attempt = result["attempt"]
    initial, middle, last = attempt["trace"]
    attempt["trace"] = [initial]
    for command in range(1, 21):
        sample = deepcopy(last if command == 20 else middle)
        sample["command_index"] = command
        sample["state"]["player1"]["x"] = float(command)
        attempt["trace"].append(sample)
    attempt["terminal"]["command_index"] = 20
    for row in attempt["updates"] + attempt["scheduler_updates"]:
        row["command_index_after"] = 20
    attempt["phase_events"][0]["command_index"] = 20
    attempt["planned_inputs"] = deepcopy(inputs)
    attempt["inputs"] = []
    for event in inputs:
        for phase in ("requested", "push" if event["pressed"] else "release"):
            index = len(attempt["inputs"])
            attempt["inputs"].append(
                {
                    **deepcopy(event),
                    "sequence": index,
                    "phase": phase,
                    "source": "replay",
                    "native_return": None if phase == "requested" else True,
                    "wall_time_ns": 1_000_001 + index,
                    "in_command": True,
                    "update_sequence": 0,
                    "scheduler_sequence": 0,
                }
            )
    return result


def probe_spec(axes=None, *, repetitions=2, run_budget=128):
    """A synthetic two-axis request; no empirical timing windows are supplied."""
    return {
        "schema_version": 1,
        "kind": "native_probe_spec",
        "id": "synthetic-command-grid",
        "axes": axes
        if axes is not None
        else [
            {"event_index": 0, "offsets_commands": [-1, 0, 1]},
            {"event_index": 1, "offsets_commands": [-1, 0, 1]},
        ],
        "repetitions": repetitions,
        "run_budget": run_budget,
    }


def save(tmp_path, value, name):
    path = tmp_path / name
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def study(tmp_path, *, reference=None, spec=None):
    return create_probe_study(
        save(tmp_path, reference_capture() if reference is None else reference, "reference.json"),
        save(tmp_path, probe_spec() if spec is None else spec, "spec.json"),
    )


def test_full_joint_grid_and_baseline_first_repetitions(tmp_path):
    result = study(tmp_path)
    assert [point["offsets_commands"] for point in result["points"]] == [
        list(item) for item in itertools.product([-1, 0, 1], repeat=2)
    ]
    assert result["trials"][:2] == [
        {"id": "p0004-r1", "point_id": "p0004", "repetition": 1},
        {"id": "p0004-r2", "point_id": "p0004", "repetition": 2},
    ]
    assert len(result["points"]) == 9
    assert len(result["trials"]) == 18
    assert all(point["status"] == "scheduled" and point["reason"] is None for point in result["points"])
    assert validate_probe_study(result) is result


def test_three_axis_grid_is_not_the_union_of_single_axis_tests(tmp_path):
    axes = [{"event_index": index, "offsets_commands": [-1, 0, 1]} for index in range(3)]
    result = study(tmp_path, spec=probe_spec(axes))
    assert len(result["points"]) == 27
    joint = next(point for point in result["points"] if point["offsets_commands"] == [-1, 1, 1])
    assert [event["command_index"] for event in point_replay(result, joint)["inputs"]] == [3, 9, 13, 16]


def test_no_milliseconds_conversion_and_source_bytes_remain_unchanged(tmp_path):
    result = study(tmp_path)
    reference_path = tmp_path / "reference.json"
    before = reference_path.read_bytes()
    assert hashlib.sha256(before).hexdigest() == result["reference"]["capture_sha256"]
    point = result["points"][-1]
    plan = point_replay(result, point["id"])
    assert plan["clock"] == "processCommands_call_index"
    assert [event["command_index"] for event in plan["inputs"]] == [5, 9, 12, 16]
    assert set(plan["inputs"][0]) == {"command_index", "player", "button", "pressed"}
    assert reference_path.read_bytes() == before
    assert result["reference"]["inputs"][0]["command_index"] == 4


def test_replay_serialization_is_actual_canonical_file_identity(tmp_path):
    result = study(tmp_path)
    for point in result["points"]:
        plan = point_replay(result, point)
        expected = (
            json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        ).encode()
        assert replay_bytes(plan) == expected
        assert not expected.startswith(b"\xef\xbb\xbf")
        assert expected.endswith(b"\n") and not expected.endswith(b"\r\n")
        assert hashlib.sha256(expected).hexdigest() == point["replay_file_sha256"]


def test_baseline_plan_retains_every_source_input_and_identity(tmp_path):
    result = study(tmp_path)
    baseline = next(point for point in result["points"] if point["offsets_commands"] == [0, 0])
    plan = point_replay(result, baseline)
    assert plan["inputs"] == result["reference"]["inputs"]
    assert plan["environment_sha256"] == result["reference"]["challenge"]["environment_id"]
    assert plan["level_sha256"] == result["reference"]["challenge"]["level_sha256"]


def test_tied_events_are_stable_but_crossovers_are_invalid_not_deaths(tmp_path):
    axes = [{"event_index": 0, "offsets_commands": [0, 4, 5]}]
    result = study(tmp_path, spec=probe_spec(axes))
    tied, crossed = result["points"][1:]
    inputs = point_replay(result, tied)["inputs"]
    assert inputs[:2] == [
        {"command_index": 8, "player": 1, "button": 1, "pressed": True},
        {"command_index": 8, "player": 1, "button": 1, "pressed": False},
    ]
    assert crossed["status"] == "invalid_schedule"
    assert "reverses" in crossed["reason"]
    assert crossed["replay_file_sha256"] is None
    assert not any(trial["point_id"] == crossed["id"] for trial in result["trials"])
    assert "outcome" not in crossed
    with pytest.raises(ValueError, match="invalid_schedule"):
        point_replay(result, crossed)


def test_outside_command_bounds_is_retained_as_invalid_schedule(tmp_path):
    offsets = [-MAX_OFFSET, -4, -3, 0, MAX_TRACE_RECORDS, MAX_OFFSET]
    result = study(tmp_path, spec=probe_spec([{"event_index": 0, "offsets_commands": offsets}]))
    assert [point["status"] for point in result["points"]] == [
        "invalid_schedule",
        "invalid_schedule",
        "scheduled",
        "scheduled",
        "invalid_schedule",
        "invalid_schedule",
    ]
    assert len(result["trials"]) == 4
    assert all(
        "outside" in point["reason"] for point in result["points"] if point["status"] == "invalid_schedule"
    )


def test_order_is_global_even_across_independent_channels(tmp_path):
    inputs = [
        {"command_index": 4, "player": 1, "button": 1, "pressed": True},
        {"command_index": 5, "player": 2, "button": 3, "pressed": True},
        {"command_index": 8, "player": 1, "button": 1, "pressed": False},
        {"command_index": 9, "player": 2, "button": 3, "pressed": False},
    ]
    result = study(
        tmp_path,
        reference=reference_capture(inputs),
        spec=probe_spec([{"event_index": 0, "offsets_commands": [0, 1, 2]}]),
    )
    assert result["points"][1]["status"] == "scheduled"
    assert result["points"][2]["status"] == "invalid_schedule"
    assert point_replay(result, "p0001")["inputs"][1]["player"] == 2


@pytest.mark.parametrize("version", [4, 5])
def test_only_selected_state_provenance_and_configuration_are_retained(tmp_path, version):
    source = reference_capture(version=version)
    result = study(tmp_path, reference=source)
    assert result["reference"]["provenance"] == source["provenance"]
    assert result["reference"]["provenance"]["origin"] == "synthetic"
    assert result["reference"]["provenance"]["independently_verified"] is False
    assert result["reference"]["provenance"]["state_completeness"] == "selected_fields_only"
    assert result["reference"]["environment"]["configuration_complete"] is False
    assert result["reference"]["state_fields"] == source["state_fields"]
    assert result["reference"]["layer_state_fields"] == source["layer_state_fields"]
    assert "AR" not in result and "feasible_region" not in result


def test_claimed_native_origin_is_preserved_without_authentication(tmp_path):
    source = reference_capture()
    source["provenance"]["origin"] = "native-engine-capture"
    result = study(tmp_path, reference=source)
    assert result["reference"]["provenance"]["origin"] == "native-engine-capture"
    assert result["reference"]["provenance"]["independently_verified"] is False


def test_explicitly_suppressed_inputs_are_not_forwarded_into_plans(tmp_path):
    source = reference_capture()
    source["attempt"]["blocked_inputs"] = [
        {
            "sequence": 0,
            "command_index": 1,
            "button": 1,
            "player": 1,
            "pressed": True,
            "source": "unknown",
            "wall_time_ns": 500_000,
        }
    ]
    result = study(tmp_path, reference=source)
    assert len(result["reference"]["inputs"]) == 4
    assert result["reference"]["inputs"][0]["command_index"] == 4


def test_reproducible_study_digest_and_strict_roundtrip(tmp_path):
    first = study(tmp_path)
    second = study(tmp_path)
    assert first == second
    digest = study_sha256(first)
    assert digest == canonical_sha256(first)
    loaded = load_probe_study(save(tmp_path, first, "study.json"))
    assert loaded == first and isinstance(loaded, dict)
    assert study_sha256(loaded) == digest
    assert point_replay(loaded, "p0004") == point_replay(first, first["points"][4])


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(schema_version=True),
        lambda d: d.update(schema_version=1.0),
        lambda d: d.update(kind="native_probe_study"),
        lambda d: d.update(extra="unbounded"),
        lambda d: d.update(id="Uppercase"),
        lambda d: d.update(id="x" * 65),
        lambda d: d.update(axes=[]),
        lambda d: d.update(axes=[{"event_index": i, "offsets_commands": [0]} for i in range(4)]),
        lambda d: d["axes"][0].update(event_index=True),
        lambda d: d["axes"][0].update(event_index=0.0),
        lambda d: d["axes"][0].update(event_index=-1),
        lambda d: d["axes"][0].update(event_index=4),
        lambda d: d["axes"][1].update(event_index=0),
        lambda d: d["axes"][0].update(extra=False),
        lambda d: d["axes"][0].update(offsets_commands=[]),
        lambda d: d["axes"][0].update(offsets_commands=[-1, 1]),
        lambda d: d["axes"][0].update(offsets_commands=[0, 0]),
        lambda d: d["axes"][0].update(offsets_commands=[1, 0]),
        lambda d: d["axes"][0].update(offsets_commands=[False]),
        lambda d: d["axes"][0].update(offsets_commands=[0.0]),
        lambda d: d["axes"][0].update(offsets_commands=[0, MAX_OFFSET + 1]),
        lambda d: d.update(repetitions=True),
        lambda d: d.update(repetitions=2.0),
        lambda d: d.update(repetitions=1),
        lambda d: d.update(repetitions=9),
        lambda d: d.update(run_budget=True),
        lambda d: d.update(run_budget=128.0),
        lambda d: d.update(run_budget=0),
        lambda d: d.update(run_budget=4097),
        lambda d: d.update(run_budget=17),
    ],
)
def test_malformed_specs_are_rejected_before_expansion(tmp_path, mutate, monkeypatch):
    spec = probe_spec()
    mutate(spec)

    def expansion_forbidden(*args):
        raise AssertionError("Malformed spec reached grid expansion")

    monkeypatch.setattr("axiom.probeplan._grid", expansion_forbidden)
    with pytest.raises(ValueError):
        study(tmp_path, spec=spec)


def test_joint_grid_and_expanded_input_limits_precede_enumeration(tmp_path, monkeypatch):
    def expansion_forbidden(*args):
        raise AssertionError("Oversized request reached grid expansion")

    monkeypatch.setattr("axiom.probeplan._grid", expansion_forbidden)
    spec = probe_spec(
        [{"event_index": index, "offsets_commands": list(range(17))} for index in range(3)], run_budget=4096
    )
    with pytest.raises(ValueError, match="4096-point"):
        study(tmp_path, spec=spec)
    # Use a validated frozen context so the expansion test is independent of a
    # source capture's much smaller constructed terminal trace.
    monkeypatch.undo()
    result = study(tmp_path, spec=probe_spec([{"event_index": 0, "offsets_commands": [0]}]))
    events = [
        {"command_index": i + 1, "player": 1, "button": 1, "pressed": i % 2 == 0}
        for i in range(MAX_PLANNED_INPUTS)
    ]
    result["reference"]["inputs"] = events
    result["reference"]["inputs_sha256"] = canonical_sha256(events)
    result["spec"]["axes"][0]["offsets_commands"] = list(range(251))
    result["spec"]["run_budget"] = 4096
    monkeypatch.setattr("axiom.probeplan._grid", expansion_forbidden)
    with pytest.raises(ValueError, match="1,000,000"):
        validate_probe_study(result)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["attempt"].update(start_kind="practice"),
        lambda d: d["attempt"].update(start_kind="start_position"),
        lambda d: d["integrity"].update(recording_complete=False),
        lambda d: d["integrity"].update(dropped_records=1),
        lambda d: d["integrity"].update(errors=["lost callback"]),
        lambda d: d["attempt"]["input_delivery"].update(driver="scheduled-ui-callback"),
        lambda d: d["attempt"]["planned_inputs"][0].update(pressed=False),
        lambda d: d["attempt"]["planned_inputs"][1].update(pressed=True),
        lambda d: d["attempt"]["planned_inputs"][0].update(command_index=0),
    ],
)
def test_unqualified_reference_rejected(tmp_path, mutate):
    source = reference_capture()
    mutate(source)
    with pytest.raises(ValueError):
        study(tmp_path, reference=source)


def test_native_clock_reference_cannot_be_silently_converted(tmp_path):
    source = reference_capture()
    source["environment"]["clocks"].update(
        clock_policy="native", intervention_hook="none", step_numerator=0, step_denominator=1
    )
    source["attempt"]["scheduler_updates"][0]["delivered_dt_seconds"] = 0.02
    refresh_environment(source)
    load_native_capture(save(tmp_path, source, "valid-native.json"))
    with pytest.raises(ValueError, match="fixed-scheduler-240"):
        study(tmp_path, reference=source)


def test_unexecuted_source_suffix_cannot_become_a_baseline(tmp_path):
    source = reference_capture()
    source["attempt"]["planned_inputs"].append(
        {"command_index": 21, "player": 1, "button": 1, "pressed": True}
    )
    load_native_capture(save(tmp_path, source, "valid-prefix.json"))
    with pytest.raises(ValueError, match="consumed"):
        study(tmp_path, reference=source)


def test_structurally_valid_death_cannot_supply_a_completed_baseline(tmp_path):
    source = reference_capture()
    attempt = source["attempt"]
    attempt["terminal"].update(outcome="died", event="PlayLayer::destroyPlayer")
    attempt["terminal"]["state"]["player1"]["is_dead"] = True
    load_native_capture(save(tmp_path, source, "valid-death.json"))
    with pytest.raises(ValueError, match="completed full-start"):
        study(tmp_path, reference=source)


def test_structurally_valid_observation_is_not_owned_execution(tmp_path):
    source = input_entry_capture(policy="fixed-scheduler-240", driver="none")
    load_native_capture(save(tmp_path, source, "valid-observation.json"))
    with pytest.raises(ValueError, match="owned-pre-command"):
        study(tmp_path, reference=source)


def test_structurally_valid_schema3_cannot_supply_missing_selected_contact_fields(tmp_path):
    source = mechanics_capture(policy="fixed-scheduler-240")
    load_native_capture(save(tmp_path, source, "valid-schema3.json"))
    with pytest.raises(ValueError, match="schema 4/5"):
        study(tmp_path, reference=source)


def test_maximum_run_budget_is_conservative_for_invalid_schedules(tmp_path):
    spec = probe_spec([{"event_index": 0, "offsets_commands": list(range(-1023, 1025))}], run_budget=4096)
    result = study(tmp_path, spec=spec)
    assert len(result["points"]) == 2048
    assert len(result["trials"]) < 4096
    assert any(point["status"] == "invalid_schedule" for point in result["points"])
    assert validate_probe_study(result) == result
    spec["axes"][0]["offsets_commands"].append(1025)
    with pytest.raises(ValueError, match="run budget"):
        study(tmp_path, spec=spec)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(schema_version=True),
        lambda d: d.update(kind="native_probe_spec"),
        lambda d: d.update(protocol="millisecond-window-v1"),
        lambda d: d.update(extra={}),
        lambda d: d["points"][0].update(id="p0009"),
        lambda d: d["points"][0].update(offsets_commands=[0, 0]),
        lambda d: d["points"][0].update(offsets_commands=[-1.0, -1]),
        lambda d: d["points"][0].update(replay_file_sha256="0" * 64),
        lambda d: d["points"][0].update(status="died"),
        lambda d: d["points"][0].update(reason="invented death"),
        lambda d: d["points"].reverse(),
        lambda d: d["points"].pop(),
        lambda d: d["trials"].reverse(),
        lambda d: d["trials"].pop(),
        lambda d: d["trials"][0].update(id="p0004-r3"),
        lambda d: d["trials"][0].update(repetition=True),
        lambda d: d["reference"].update(environment_sha256="0" * 64),
        lambda d: d["reference"]["challenge"].update(environment_id="0" * 64),
        lambda d: d["reference"]["provenance"].update(independently_verified=True),
        lambda d: d["reference"]["provenance"].update(state_completeness="full"),
        lambda d: d["reference"]["collector"].update(extra="missing field"),
        lambda d: d["reference"]["state_fields"].pop(),
        lambda d: d["reference"].update(layer_state_fields=[]),
        lambda d: d["reference"]["inputs"][0].update(command_index=5),
        lambda d: d["reference"]["inputs"][0].update(player=True),
        lambda d: d["reference"]["inputs"][0].update(pressed=1),
    ],
)
def test_frozen_study_tampering_is_rejected(tmp_path, mutate):
    result = study(tmp_path)
    mutate(result)
    with pytest.raises(ValueError):
        validate_probe_study(result)


def test_bad_channel_schedule_rejected_even_with_recomputed_digest(tmp_path):
    result = study(tmp_path)
    result["reference"]["inputs"][1]["pressed"] = True
    result["reference"]["inputs_sha256"] = canonical_sha256(result["reference"]["inputs"])
    with pytest.raises(ValueError, match="alternate"):
        validate_probe_study(result)


@pytest.mark.parametrize(
    "point", ["p9999", "p00000", "p-001", "p0000-r1", 0, None, [], {"id": "p0000", "status": "scheduled"}]
)
def test_point_selection_is_exact_and_bounded(tmp_path, point):
    with pytest.raises(ValueError):
        point_replay(study(tmp_path), point)


def test_duplicate_json_keys_are_rejected_on_study_load(tmp_path):
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        load_probe_study(path)


def test_reference_change_during_freeze_is_rejected(tmp_path, monkeypatch):
    original = load_native_capture

    def change_after_validation(path):
        result = original(path)
        with path.open("a", encoding="utf-8") as stream:
            stream.write("\n")
        return result

    monkeypatch.setattr("axiom.probeplan.load_native_capture", change_after_validation)
    with pytest.raises(ValueError, match="changed"):
        study(tmp_path)


def test_reference_change_during_spec_read_is_rejected(tmp_path, monkeypatch):
    from axiom.validation import read_json

    def change_on_spec_read(path):
        result = read_json(path)
        if path.name == "spec.json":
            with (path.parent / "reference.json").open("a", encoding="utf-8") as stream:
                stream.write("\n")
        return result

    monkeypatch.setattr("axiom.probeplan.read_json", change_on_spec_read)
    with pytest.raises(ValueError, match="changed"):
        study(tmp_path)


def test_reference_parsed_data_cannot_be_paired_with_another_sources_hash(tmp_path, monkeypatch):
    original = load_native_capture

    def different_validated_data(path):
        result = original(path)
        result["attempt"]["id"] = "a-different-validated-source"
        return result

    monkeypatch.setattr("axiom.probeplan.load_native_capture", different_validated_data)
    with pytest.raises(ValueError, match="changed"):
        study(tmp_path)
