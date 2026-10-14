"""Frozen jobs and synthetic terminals stay distinct from engine qualification."""

import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_native import input_entry_capture

import axiom.proberun as runner
from axiom.probeplan import create_probe_study, point_replay, replay_bytes, study_sha256
from axiom.proberun import (
    SyntheticProbeBackend,
    materialize_probe_study,
    prepare_probe_directory,
    run_probe_backend,
    write_probe_json,
)


def store(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def study_fixture(tmp_path, *, offsets=(-1, 0, 1), repetitions=2):
    source = input_entry_capture(policy="fixed-scheduler-240")
    release = {"command_index": 2, "player": 1, "button": 1, "pressed": False}
    source["attempt"]["planned_inputs"].append(release)
    for sequence, phase, native_return in ((2, "requested", None), (3, "release", True)):
        source["attempt"]["inputs"].append(
            {
                **deepcopy(source["attempt"]["inputs"][0]),
                **release,
                "sequence": sequence,
                "phase": phase,
                "native_return": native_return,
                "wall_time_ns": 2_000_001 + sequence,
            }
        )
    capture_path = store(tmp_path / "source.json", source)
    spec = {
        "schema_version": 1,
        "kind": "native_probe_spec",
        "id": "controlled-coupled-grid",
        "axes": [{"event_index": index, "offsets_commands": list(offsets)} for index in (0, 1)],
        "repetitions": repetitions,
        "run_budget": len(offsets) ** 2 * repetitions,
    }
    spec_path = store(tmp_path / "spec.json", spec)
    study = create_probe_study(capture_path, spec_path)
    path = store(tmp_path / "study.json", study)
    return study, path


def region(offsets):
    return offsets in ((0, 0), (1, 1))


class CountingBackend:
    id = "synthetic-counting"
    origin = "synthetic"

    def __init__(self, study, transform=None):
        self.delegate = SyntheticProbeBackend(study, region)
        self.calls = []
        self.transform = transform

    def run(self, trial, plan):
        self.calls.append((deepcopy(trial), deepcopy(plan)))
        result = self.delegate.run(trial, plan)
        return result if self.transform is None else self.transform(result, trial, plan)


def test_job_bundle_preserves_exact_source_bytes_and_every_frozen_replay_hash(tmp_path):
    study, path = study_fixture(tmp_path)
    raw = b"\xef\xbb\xbf" + path.read_bytes() + b"\n\n"
    path.write_bytes(raw)
    before = deepcopy(study)
    bundle = tmp_path / "jobs"
    manifest = materialize_probe_study(path, bundle)
    assert manifest == json.loads((bundle / "jobs.json").read_bytes())
    assert set(manifest) == {
        "schema_version",
        "kind",
        "study_sha256",
        "study_file_sha256",
        "study_path",
        "jobs",
    }
    assert manifest["kind"] == "native_probe_jobs"
    assert manifest["schema_version"] == 1
    assert manifest["study_sha256"] == study_sha256(study)
    assert manifest["study_file_sha256"] == hashlib.sha256(raw).hexdigest()
    assert manifest["study_path"] == "study.json"
    assert (bundle / "study.json").read_bytes() == path.read_bytes() == raw
    scheduled = {point["id"]: point for point in study["points"] if point["status"] == "scheduled"}
    assert len(list((bundle / "plans").iterdir())) == len(scheduled)
    for trial, job in zip(study["trials"], manifest["jobs"], strict=True):
        assert job == {
            "trial_id": trial["id"],
            "point_id": trial["point_id"],
            "repetition": trial["repetition"],
            "replay_path": f"plans/{trial['point_id']}.json",
            "replay_file_sha256": scheduled[trial["point_id"]]["replay_file_sha256"],
            "clock_policy": "fixed-scheduler-240",
            "input_driver": "owned-pre-command",
            "start_kind": "level_start",
        }
        retained = (bundle / job["replay_path"]).read_bytes()
        assert retained == replay_bytes(point_replay(study, trial["point_id"]))
        assert hashlib.sha256(retained).hexdigest() == job["replay_file_sha256"]
    baseline = next(point["id"] for point in study["points"] if point["offsets_commands"] == [0, 0])
    assert [job["trial_id"] for job in manifest["jobs"][:2]] == [f"{baseline}-r1", f"{baseline}-r2"]
    assert study == before
    assert not list(bundle.rglob("*.tmp"))


@pytest.mark.parametrize("target_kind", ["file", "empty-directory", "populated-directory"])
def test_materialization_refuses_existing_destinations_without_modifying_them(tmp_path, target_kind):
    _, path = study_fixture(tmp_path)
    target = tmp_path / "output"
    if target_kind == "file":
        target.write_bytes(b"untouched")
    else:
        target.mkdir()
        if target_kind == "populated-directory":
            (target / "retained.bin").write_bytes(b"untouched")
    with pytest.raises(ValueError, match="already exists"):
        materialize_probe_study(path, target)
    if target_kind == "file":
        assert target.read_bytes() == b"untouched"
    elif target_kind == "empty-directory":
        assert not list(target.iterdir())
    else:
        assert (target / "retained.bin").read_bytes() == b"untouched"


@pytest.mark.parametrize("target", ["source", "source-parent", "child-of-source"])
def test_materialization_refuses_source_overlaps(tmp_path, target):
    _, path = study_fixture(tmp_path)
    output = {"source": path, "source-parent": path.parent, "child-of-source": path / "nested"}[target]
    raw = path.read_bytes()
    with pytest.raises(ValueError, match="overlap"):
        materialize_probe_study(path, output)
    assert path.read_bytes() == raw


@pytest.mark.parametrize("mutation", ["point-sha", "trial-order", "budget", "unknown-field"])
def test_invalid_frozen_studies_never_create_jobs_or_call_backends(tmp_path, mutation):
    study, path = study_fixture(tmp_path)
    backend = CountingBackend(study)
    if mutation == "point-sha":
        next(point for point in study["points"] if point["status"] == "scheduled")["replay_file_sha256"] = (
            "a" * 64
        )
    elif mutation == "trial-order":
        study["trials"].reverse()
    elif mutation == "budget":
        study["spec"]["run_budget"] = 1
    else:
        study["unexpected"] = True
    store(path, study)
    with pytest.raises(ValueError):
        materialize_probe_study(path, tmp_path / "jobs")
    with pytest.raises(ValueError):
        run_probe_backend(path, backend, tmp_path / "results.json")
    assert not (tmp_path / "jobs").exists()
    assert not (tmp_path / "results.json").exists()
    assert backend.calls == []


def test_duplicate_study_json_fields_are_rejected_before_output(tmp_path):
    _, path = study_fixture(tmp_path)
    raw = path.read_bytes()
    path.write_bytes(raw.rstrip()[:-1] + b', "schema_version": 1}\n')
    with pytest.raises(ValueError, match="Duplicate"):
        materialize_probe_study(path, tmp_path / "jobs")
    assert not (tmp_path / "jobs").exists()


def test_partial_io_failure_has_no_jobs_completion_marker_and_is_not_silently_resumed(tmp_path, monkeypatch):
    _, path = study_fixture(tmp_path)
    raw = path.read_bytes()
    original = runner._write_fresh_atomic

    def fail_plan(destination, data):
        if destination.parent.name == "plans":
            raise OSError("controlled disk failure")
        return original(destination, data)

    monkeypatch.setattr(runner, "_write_fresh_atomic", fail_plan)
    output = tmp_path / "jobs"
    with pytest.raises(OSError, match="controlled disk failure"):
        materialize_probe_study(path, output)
    assert (output / "study.json").read_bytes() == raw
    assert not (output / "jobs.json").exists()
    assert path.read_bytes() == raw
    with pytest.raises(ValueError, match="already exists"):
        materialize_probe_study(path, output)


def test_sequential_synthetic_grid_keeps_coupled_disconnected_truth_and_repeat_identity(tmp_path):
    study, path = study_fixture(tmp_path)
    raw = path.read_bytes()
    backend = CountingBackend(study)
    output = tmp_path / "results.json"
    result = run_probe_backend(path, backend, output)
    assert result == json.loads(output.read_bytes())
    assert set(result) == {"schema_version", "kind", "study_sha256", "backend", "attempts"}
    assert result["kind"] == "probe_backend_results"
    assert result["backend"] == {"id": "synthetic-counting", "origin": "synthetic"}
    assert result["study_sha256"] == study_sha256(study)
    assert len(result["attempts"]) == len(backend.calls) == len(study["trials"])
    points = {point["id"]: point for point in study["points"]}
    executions = []
    for trial, attempt, (called_trial, plan) in zip(
        study["trials"], result["attempts"], backend.calls, strict=True
    ):
        point = points[trial["point_id"]]
        assert called_trial == trial
        expected = "completed" if region(tuple(point["offsets_commands"])) else "died"
        assert set(attempt) == {"trial_id", "outcome", "terminal_witness", "error"}
        assert attempt["trial_id"] == trial["id"]
        assert attempt["outcome"] == expected
        assert attempt["error"] is None
        witness = attempt["terminal_witness"]
        assert witness["kind"] == "synthetic-full-run-terminal"
        assert witness["start_kind"] == "level_start"
        assert witness["event"] == expected
        assert witness["replay_file_sha256"] == hashlib.sha256(replay_bytes(plan)).hexdigest()
        assert witness["environment_sha256"] == study["reference"]["environment_sha256"]
        executions.append(witness["execution_id"])
    assert len(set(executions)) == len(executions)
    assert path.read_bytes() == raw


def test_backend_mutated_arguments_never_contaminate_later_trials_or_source(tmp_path):
    study, path = study_fixture(tmp_path)
    raw = path.read_bytes()

    def mutate(result, trial, plan):
        trial.clear()
        plan["inputs"].clear()
        plan["environment_sha256"] = "f" * 64
        return result

    backend = CountingBackend(study, mutate)
    result = run_probe_backend(path, backend, tmp_path / "results.json")
    assert all(attempt["outcome"] in {"completed", "died"} for attempt in result["attempts"])
    assert [trial for trial, _ in backend.calls] == study["trials"]
    for trial, plan in backend.calls:
        assert plan == point_replay(study, trial["point_id"])
    assert path.read_bytes() == raw


def test_backend_errors_and_deadlines_are_runner_errors_with_no_death_witness_or_retry(tmp_path):
    study, path = study_fixture(tmp_path)
    backend = CountingBackend(study)
    original = backend.run
    calls = []

    def controlled(trial, plan):
        calls.append(trial["id"])
        if len(calls) == 1:
            raise TimeoutError("controlled deadline exceeded")
        if len(calls) == 2:
            raise RuntimeError("controlled backend failure")
        if len(calls) == 3:
            return {"outcome": "runner_error", "terminal_witness": None, "error": "explicit failure"}
        return original(trial, plan)

    backend.run = controlled
    result = run_probe_backend(path, backend, tmp_path / "results.json")
    assert calls == [trial["id"] for trial in study["trials"]]
    first, second, third = result["attempts"][:3]
    assert first["error"] == "TimeoutError: controlled deadline exceeded"
    assert second["error"] == "RuntimeError: controlled backend failure"
    assert third["error"] == "explicit failure"
    for attempt in (first, second, third):
        assert attempt["outcome"] == "runner_error"
        assert attempt["terminal_witness"] is None
    assert all(attempt["error"] is None for attempt in result["attempts"][3:])


def test_exception_messages_are_bounded_valid_utf8_and_do_not_become_terminals(tmp_path):
    study, path = study_fixture(tmp_path)
    backend = CountingBackend(study)

    def fail(trial, plan):
        raise RuntimeError("invalid surrogate \ud800 " + "x" * 2000)

    backend.run = fail
    result = run_probe_backend(path, backend, tmp_path / "results.json")
    for attempt in result["attempts"]:
        assert attempt["outcome"] == "runner_error"
        assert attempt["terminal_witness"] is None
        assert len(attempt["error"]) == 1024
        assert "invalid surrogate ?" in attempt["error"]
        attempt["error"].encode("utf-8")


@pytest.mark.parametrize(
    "change",
    [
        "non-object",
        "unknown-field",
        "unknown-outcome",
        "missing-witness",
        "terminal-with-error",
        "native-kind",
        "checkpoint-start",
        "event-mismatch",
        "plan-mismatch",
        "environment-mismatch",
        "unknown-witness-field",
        "empty-execution",
        "invalid-unicode-execution",
        "runner-error-with-terminal",
        "runner-error-with-empty-message",
        "invalid-unicode-error",
    ],
)
def test_malformed_backend_outputs_are_refused_as_runner_errors(tmp_path, change):
    study, path = study_fixture(tmp_path)

    def corrupt(result, trial, plan):
        if change == "non-object":
            return None
        if change == "unknown-field":
            result["native_capture"] = True
        elif change == "unknown-outcome":
            result["outcome"] = "timeout"
        elif change == "missing-witness":
            result["terminal_witness"] = None
        elif change == "terminal-with-error":
            result["error"] = "ambiguous"
        elif change == "native-kind":
            result["terminal_witness"]["kind"] = "native-full-run-terminal"
        elif change == "checkpoint-start":
            result["terminal_witness"]["start_kind"] = "checkpoint"
        elif change == "event-mismatch":
            result["terminal_witness"]["event"] = "died" if result["outcome"] == "completed" else "completed"
        elif change == "plan-mismatch":
            result["terminal_witness"]["replay_file_sha256"] = "a" * 64
        elif change == "environment-mismatch":
            result["terminal_witness"]["environment_sha256"] = "f" * 64
        elif change == "unknown-witness-field":
            result["terminal_witness"]["engine_verified"] = True
        elif change == "empty-execution":
            result["terminal_witness"]["execution_id"] = ""
        elif change == "invalid-unicode-execution":
            result["terminal_witness"]["execution_id"] = "\ud800"
        elif change == "runner-error-with-terminal":
            result["outcome"] = "runner_error"
            result["error"] = "failed"
        elif change == "runner-error-with-empty-message":
            result = {"outcome": "runner_error", "terminal_witness": None, "error": " "}
        else:
            result = {"outcome": "runner_error", "terminal_witness": None, "error": "\ud800"}
        return result

    backend = CountingBackend(study, corrupt)
    result = run_probe_backend(path, backend, tmp_path / "results.json")
    assert len(backend.calls) == len(study["trials"])
    assert all(attempt["outcome"] == "runner_error" for attempt in result["attempts"])
    assert all(attempt["terminal_witness"] is None for attempt in result["attempts"])
    assert all(attempt["error"].startswith("ValueError: ") for attempt in result["attempts"])


def test_reused_execution_identity_cannot_supply_repeated_successes(tmp_path):
    study, path = study_fixture(tmp_path)

    def reused(result, trial, plan):
        result["terminal_witness"]["execution_id"] = "reused-synthetic-execution"
        return result

    result = run_probe_backend(path, CountingBackend(study, reused), tmp_path / "results.json")
    assert result["attempts"][0]["outcome"] == "completed"
    for attempt in result["attempts"][1:]:
        assert attempt["outcome"] == "runner_error"
        assert attempt["terminal_witness"] is None
        assert "Duplicate" in attempt["error"]


@pytest.mark.parametrize("origin", ["external-native", "native-engine-capture", "unknown", None])
def test_external_native_identity_is_not_admitted_to_synthetic_terminal_contract(tmp_path, origin):
    study, path = study_fixture(tmp_path)
    backend = CountingBackend(study)
    backend.origin = origin
    with pytest.raises(ValueError, match="only explicit synthetic"):
        run_probe_backend(path, backend, tmp_path / "results.json")
    assert backend.calls == []
    assert not (tmp_path / "results.json").exists()


@pytest.mark.parametrize("target", ["source", "retained-result", "missing-parent"])
def test_runner_output_refusals_happen_before_backend_calls(tmp_path, target):
    study, path = study_fixture(tmp_path)
    backend = CountingBackend(study)
    output = {
        "source": path,
        "retained-result": tmp_path / "existing.json",
        "missing-parent": tmp_path / "missing" / "result.json",
    }[target]
    if target == "retained-result":
        output.write_bytes(b"retained result")
    before = path.read_bytes()
    with pytest.raises(ValueError):
        run_probe_backend(path, backend, output)
    assert backend.calls == []
    assert path.read_bytes() == before
    if target == "retained-result":
        assert output.read_bytes() == b"retained result"


def test_study_change_during_backend_calls_prevents_result_publication(tmp_path):
    study, path = study_fixture(tmp_path)

    def change_source(result, trial, plan):
        if path.read_bytes().endswith(b"\n"):
            path.write_bytes(path.read_bytes() + b" ")
        return result

    backend = CountingBackend(study, change_source)
    with pytest.raises(ValueError, match="source changed during execution"):
        run_probe_backend(path, backend, tmp_path / "results.json")
    assert len(backend.calls) == len(study["trials"])
    assert not (tmp_path / "results.json").exists()


def test_synthetic_backend_freezes_constructor_state_and_only_accepts_exact_trials_and_plans(tmp_path):
    study, path = study_fixture(tmp_path)
    before = deepcopy(study)
    backend = SyntheticProbeBackend(study, region)
    study["reference"]["inputs"].clear()
    result = run_probe_backend(path, backend, tmp_path / "results.json")
    assert result["attempts"][0]["outcome"] == "completed"
    trial = deepcopy(before["trials"][0])
    plan = point_replay(before, trial["point_id"])
    trial["repetition"] = 7
    with pytest.raises(ValueError, match="trial differs"):
        backend.run(trial, plan)
    trial = deepcopy(before["trials"][0])
    plan["inputs"][0]["command_index"] += 1
    with pytest.raises(ValueError, match="replay differs"):
        backend.run(trial, plan)


@pytest.mark.parametrize("predicate_result", [1, "true", None, [], {}])
def test_synthetic_region_predicate_requires_a_boolean(tmp_path, predicate_result):
    study, path = study_fixture(tmp_path)
    backend = SyntheticProbeBackend(study, lambda _: predicate_result)
    result = run_probe_backend(path, backend, tmp_path / "results.json")
    assert all(attempt["outcome"] == "runner_error" for attempt in result["attempts"])
    assert all("must return a bool" in attempt["error"] for attempt in result["attempts"])


def test_writer_publishes_complete_bytes_only_and_never_replaces_a_racing_destination(tmp_path, monkeypatch):
    path = tmp_path / "result.json"
    original_link = os.link
    observations = []

    def raced_link(source, destination, **kwargs):
        observations.append(json.loads(Path(source).read_bytes()))
        assert not Path(destination).exists()
        Path(destination).write_bytes(b"racing retained bytes")
        return original_link(source, destination, **kwargs)

    monkeypatch.setattr(os, "link", raced_link)
    with pytest.raises(FileExistsError):
        write_probe_json(path, {"complete": True})
    assert observations == [{"complete": True}]
    assert path.read_bytes() == b"racing retained bytes"
    assert not list(tmp_path.glob("*.tmp"))


def test_failed_atomic_publication_never_exposes_a_partial_destination(tmp_path, monkeypatch):
    path = tmp_path / "result.json"

    def rejected_link(source, destination, **kwargs):
        assert json.loads(Path(source).read_bytes()) == {"complete": True}
        assert not Path(destination).exists()
        raise OSError("controlled unsupported filesystem")

    monkeypatch.setattr(os, "link", rejected_link)
    with pytest.raises(OSError, match="unsupported filesystem"):
        write_probe_json(path, {"complete": True})
    assert not path.exists()
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("value", [[], {"value": float("nan")}, {"value": "\ud800"}, {"value": object()}])
def test_writer_rejects_non_object_nonfinite_non_utf8_or_non_json_before_output(tmp_path, value):
    path = tmp_path / "result.json"
    with pytest.raises(ValueError):
        write_probe_json(path, value)
    assert not path.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_prepare_directory_does_not_accept_existing_empty_directories(tmp_path):
    path = tmp_path / "new-directory"
    assert prepare_probe_directory(path) == path.absolute()
    with pytest.raises(ValueError, match="already exists"):
        prepare_probe_directory(path)
    assert not list(path.iterdir())


def test_reparse_ancestor_is_refused_for_reading_and_writing_before_backend_calls(tmp_path, monkeypatch):
    study, path = study_fixture(tmp_path)
    backend = CountingBackend(study)
    original_lstat = Path.lstat

    def redirected_lstat(candidate, *args, **kwargs):
        info = original_lstat(candidate, *args, **kwargs)
        if candidate == tmp_path:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=runner.REPARSE_POINT)
        return info

    monkeypatch.setattr(Path, "lstat", redirected_lstat)
    with pytest.raises(ValueError, match="Redirected"):
        run_probe_backend(path, backend, tmp_path / "results.json")
    with pytest.raises(ValueError, match="Redirected"):
        materialize_probe_study(path, tmp_path / "jobs")
    with pytest.raises(ValueError, match="Redirected"):
        write_probe_json(tmp_path / "direct.json", {"value": 1})
    with pytest.raises(ValueError, match="Redirected"):
        prepare_probe_directory(tmp_path / "fresh")
    assert backend.calls == []


def test_real_symlink_ancestor_is_refused_without_touching_its_target(tmp_path):
    study, path = study_fixture(tmp_path)
    backend = CountingBackend(study)
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    retained = foreign / "retained.json"
    retained.write_bytes(b"retained")
    link = tmp_path / "redirected"
    try:
        link.symlink_to(foreign, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation privileges unavailable")
    with pytest.raises(ValueError, match="Redirected"):
        run_probe_backend(path, backend, link / "results.json")
    with pytest.raises(ValueError, match="Redirected"):
        materialize_probe_study(path, link / "jobs")
    redirected_source = link / "study.json"
    (foreign / "study.json").write_bytes(path.read_bytes())
    with pytest.raises(ValueError, match="Redirected"):
        materialize_probe_study(redirected_source, tmp_path / "other-jobs")
    with pytest.raises(ValueError, match="Redirected"):
        run_probe_backend(redirected_source, backend, tmp_path / "other-results.json")
    assert backend.calls == []
    assert retained.read_bytes() == b"retained"
    assert not (foreign / "results.json").exists()
    assert not (foreign / "jobs").exists()
    assert not (tmp_path / "other-jobs").exists()
    assert not (tmp_path / "other-results.json").exists()


def test_changed_source_bytes_during_reading_are_rejected(tmp_path, monkeypatch):
    _, path = study_fixture(tmp_path)
    original_open = Path.open

    class MutatingReader:
        def __init__(self, stream):
            self.stream = stream
            self.changed = False

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def read(self, maximum):
            data = self.stream.read(maximum)
            if not self.changed:
                self.changed = True
                with original_open(path, "ab") as writer:
                    writer.write(b" ")
            return data

    def controlled_open(candidate, mode="r", *args, **kwargs):
        stream = original_open(candidate, mode, *args, **kwargs)
        return MutatingReader(stream) if candidate == path and mode == "rb" else stream

    monkeypatch.setattr(Path, "open", controlled_open)
    with pytest.raises(ValueError, match="changed during reading"):
        materialize_probe_study(path, tmp_path / "jobs")
    assert not (tmp_path / "jobs").exists()
