"""Joint discrete samples do not become interpolated human timing windows."""

import hashlib
import json
from copy import deepcopy

import pytest
from test_probeplan import probe_spec, reference_capture, save

from axiom.cli import main
from axiom.probeplan import create_probe_study, study_sha256
from axiom.proberun import SyntheticProbeBackend, run_probe_backend
from axiom.probes import (
    _synthetic_observations,
    analyze_probe_results,
    summarize_probe_observations,
    synthetic_probe_demo,
)


def run(tmp_path, predicate, *, axes=None, repetitions=3):
    source = save(tmp_path, reference_capture(), "reference.json")
    spec = save(tmp_path, probe_spec(axes, repetitions=repetitions), "spec.json")
    study = create_probe_study(source, spec)
    study_path = save(tmp_path, study, "study.json")
    results_path = tmp_path / "results.json"
    results = run_probe_backend(study_path, SyntheticProbeBackend(study, predicate), results_path)
    return study, study_path, results, results_path


def test_joint_disconnected_demo_catches_marginal_product_counterexamples(tmp_path):
    axes = [{"event_index": i, "offsets_commands": [-2, -1, 0, 1, 2]} for i in (0, 1)]
    source = save(tmp_path, reference_capture(), "reference.json")
    spec = save(tmp_path, probe_spec(axes, repetitions=3), "spec.json")
    metadata = synthetic_probe_demo(source, spec, tmp_path / "demo")
    report = json.loads((tmp_path / "demo/map.json").read_text(encoding="utf-8"))
    assert metadata["new_native_execution"] is False
    assert report["counts"]["planned_trials"] == report["counts"]["observed_trials"] == 75
    assert report["counts"]["accepted_sample"] == 3
    assert report["counts"]["death_sample"] == 22
    assert len(report["accepted_sample_components"]) == 3
    assert all(component["sample_count"] == 1 for component in report["accepted_sample_components"])
    assert report["marginal_accepted_projections_commands"] == [[-2, 0, 2], [-2, 0, 2]]
    assert len(report["observed_marginal_product_counterexamples"]) == 6
    assert all(row["accepted_offsets_commands"] == [0] for row in report["axis_slices"])
    assert report["grid_status"] == "complete_declared_grid"
    assert report["baseline_control"]["established"] is True
    assert report["offset_unit"] == "command_call"
    assert report["scope"]["continuous_windows"] == "not_established"
    assert report["scope"]["human_calibration"] == report["scope"]["real_level_ar"] == "not_established"


def test_nonmonotonic_single_axis_is_not_binary_searched_into_one_window(tmp_path):
    axes = [{"event_index": 1, "offsets_commands": [-2, -1, 0, 1, 2]}]
    _, study_path, _, results_path = run(tmp_path, lambda x: x[0] in {-2, 0, 2}, axes=axes)
    report = analyze_probe_results(study_path, results_path)
    assert report["counts"]["accepted_sample"] == 3
    assert report["counts"]["death_sample"] == 2
    assert len(report["accepted_sample_components"]) == 3
    assert report["axis_slices"][0]["accepted_offsets_commands"] == [-2, 0, 2]
    assert report["axis_slices"][0]["interpolation"] == "not_performed"


def test_missing_grid_sites_are_not_bridged_as_a_continuous_component(tmp_path):
    axes = [{"event_index": 1, "offsets_commands": [-3, 0, 3]}]
    _, study_path, _, results_path = run(tmp_path, lambda x: True, axes=axes)
    report = analyze_probe_results(study_path, results_path)
    assert len(report["accepted_sample_components"]) == 3
    assert report["scope"]["between_grid_samples"] == "not_tested"


def test_neighboring_integer_samples_form_only_a_discrete_graph(tmp_path):
    axes = [{"event_index": 1, "offsets_commands": [-1, 0, 1]}]
    _, study_path, _, results_path = run(tmp_path, lambda x: True, axes=axes)
    report = analyze_probe_results(study_path, results_path)
    assert len(report["accepted_sample_components"]) == 1
    assert report["accepted_sample_components"][0]["sample_count"] == 3
    assert report["scope"]["continuous_windows"] == "not_established"


def test_missing_repeat_keeps_point_incomplete_without_fabricating_death(tmp_path):
    _, study_path, results, results_path = run(tmp_path, lambda x: True)
    results["attempts"].pop()
    save(tmp_path, results, "results.json")
    report = analyze_probe_results(study_path, results_path)
    assert report["counts"]["missing_trials"] == 1
    assert report["counts"]["incomplete"] == 1
    assert report["counts"]["death_sample"] == 0
    assert report["grid_status"] == "partially_observed_grid"


def test_runner_error_is_unknown_and_unestablished_baseline_cannot_qualify_map(tmp_path):
    def failed_control(x):
        if x == (0, 0):
            raise TimeoutError("synthetic execution deadline")
        return True

    _, study_path, _, results_path = run(tmp_path, failed_control)
    report = analyze_probe_results(study_path, results_path)
    assert report["counts"]["unknown"] == 1
    assert report["counts"]["death_sample"] == 0
    assert report["eligible_for_sampled_map"] is False
    assert report["baseline_control"]["status"] == "unknown"
    assert report["grid_status"] == "partially_observed_grid"


def test_conflicting_repetitions_remain_inconsistent(tmp_path):
    calls = {}

    def inconsistent(offsets):
        calls[offsets] = calls.get(offsets, 0) + 1
        return calls[offsets] % 2 == 0

    _, study_path, _, results_path = run(tmp_path, inconsistent)
    report = analyze_probe_results(study_path, results_path)
    assert report["counts"]["inconsistent_repeats"] == 9
    assert not report["accepted_sample_components"]
    assert report["eligible_for_sampled_map"] is False


def test_invalid_schedule_is_recorded_without_a_backend_execution(tmp_path):
    axes = [{"event_index": 0, "offsets_commands": [-4, 0, 5]}]
    study, study_path, _, results_path = run(tmp_path, lambda x: True, axes=axes)
    report = analyze_probe_results(study_path, results_path)
    assert report["counts"]["invalid_schedule"] == 2
    assert report["counts"]["planned_trials"] == 3
    assert len(study["trials"]) == 3
    assert report["counts"]["death_sample"] == 0
    assert report["points"][0]["required_repetitions"] == 0


@pytest.mark.parametrize("outcome", [None, True, [], {}, "alive", "completed-local-horizon"])
def test_invalid_backend_outcomes_are_rejected(tmp_path, outcome):
    study, _, results, _ = run(tmp_path, lambda x: True)
    results["attempts"][0]["outcome"] = outcome
    with pytest.raises(ValueError, match="outcome"):
        _synthetic_observations(study, results)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(study_sha256="f" * 64),
        lambda r: r["backend"].update(origin="external-native"),
        lambda r: r["attempts"].append(deepcopy(r["attempts"][0])),
        lambda r: r["attempts"][0].update(trial_id="unknown-job"),
        lambda r: r["attempts"][0]["terminal_witness"].update(start_kind="checkpoint"),
        lambda r: r["attempts"][0]["terminal_witness"].update(environment_sha256="f" * 64),
        lambda r: r["attempts"][0]["terminal_witness"].update(replay_file_sha256="f" * 64),
        lambda r: r["attempts"][1]["terminal_witness"].update(
            execution_id=r["attempts"][0]["terminal_witness"]["execution_id"]
        ),
        lambda r: r["attempts"][0].update(error="terminal but error"),
        lambda r: r["attempts"][0].update(outcome="runner_error", error="late", terminal_witness={}),
    ],
)
def test_foreign_or_ambiguous_witnesses_cannot_qualify_samples(tmp_path, mutate):
    study, _, results, _ = run(tmp_path, lambda x: True)
    mutate(results)
    with pytest.raises(ValueError):
        _synthetic_observations(study, results)


def test_native_repeat_scope_keeps_disagreeing_terminal_states_inconsistent(tmp_path):
    study, _, results, _ = run(tmp_path, lambda x: True)
    observations = _synthetic_observations(study, results)
    observations["origin"] = "native-capture-files"
    for index, row in enumerate(observations["attempts"]):
        row.update(
            evidence_origin="synthetic",
            evidence_sha256=f"{index:064x}",
            terminal_state_sha256="a" * 64,
            native_terminal_event="PlayLayer::levelComplete",
            command_index=20,
        )
    observations["attempts"][0]["terminal_state_sha256"] = "b" * 64
    report = summarize_probe_observations(study, observations)
    assert report["counts"]["inconsistent_repeats"] == 1
    assert report["baseline_control"]["established"] is False
    assert report["points"][0]["repeat_check_scope"] == "terminal_outcome_state_event_command_only"
    assert report["scope"]["m1_gate"] == "not_established"


def test_result_and_study_hashes_and_input_bytes_remain_bound(tmp_path):
    study, study_path, _, results_path = run(tmp_path, lambda x: True)
    before = [path.read_bytes() for path in (study_path, results_path)]
    report = analyze_probe_results(study_path, results_path)
    assert report["study_sha256"] == study_sha256(study)
    assert report["study_file_sha256"] == hashlib.sha256(before[0]).hexdigest()
    assert report["results_file_sha256"] == hashlib.sha256(before[1]).hexdigest()
    assert before == [path.read_bytes() for path in (study_path, results_path)]


def test_map_construction_rejects_changed_results_bytes(tmp_path, monkeypatch):
    import axiom.probes as module

    _, study_path, _, results_path = run(tmp_path, lambda x: True)
    original = module.summarize_probe_observations

    def changed(study, observations):
        report = original(study, observations)
        results_path.write_bytes(results_path.read_bytes() + b"\n")
        return report

    monkeypatch.setattr(module, "summarize_probe_observations", changed)
    with pytest.raises(ValueError, match="changed"):
        analyze_probe_results(study_path, results_path)


def test_cli_plan_export_map_roundtrip_and_fresh_output_refusal(tmp_path, capsys):
    reference = save(tmp_path, reference_capture(), "reference.json")
    spec = save(tmp_path, probe_spec(), "spec.json")
    before = reference.read_bytes()
    assert main(["probe-plan", str(reference), str(spec), "--json", str(reference)]) == 2
    assert "already exists" in capsys.readouterr().err
    assert reference.read_bytes() == before
    study_path = tmp_path / "study.json"
    assert main(["probe-plan", str(reference), str(spec), "--json", str(study_path)]) == 0
    assert main(["probe-export", str(study_path), "--output", str(tmp_path / "exchange")]) == 0
    jobs = json.loads(capsys.readouterr().out)
    assert len(jobs["jobs"]) == 18
    for job in jobs["jobs"]:
        payload = (tmp_path / "exchange" / job["replay_path"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == job["replay_file_sha256"]
    study = json.loads(study_path.read_text(encoding="utf-8"))
    results_path = tmp_path / "results.json"
    run_probe_backend(study_path, SyntheticProbeBackend(study, lambda x: x[0] == x[1]), results_path)
    map_path = tmp_path / "map.json"
    assert main(["probe-map", str(study_path), str(results_path), "--json", str(map_path)]) == 0
    report = json.loads(map_path.read_text(encoding="utf-8"))
    assert report["counts"]["accepted_sample"] == 3
    assert report["counts"]["death_sample"] == 6
    map_bytes = map_path.read_bytes()
    assert main(["probe-map", str(study_path), str(results_path), "--json", str(map_path)]) == 2
    assert "already exists" in capsys.readouterr().err
    assert map_path.read_bytes() == map_bytes


def test_public_example_demo_is_explicit_synthetic(tmp_path, capsys):
    assert main(["probe-demo", "--out", str(tmp_path / "demo")]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["counts"]["planned_trials"] == 75
    assert output["new_native_execution"] is False
    assert main(["probe-demo", "--out", str(tmp_path / "demo")]) == 2
    assert "already exists" in capsys.readouterr().err
