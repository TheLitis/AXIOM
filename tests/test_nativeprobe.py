"""Capture-producing execution tests without launching Geometry Dash."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_probeadapter import prepare_study, trial_capture

import axiom.nativeprobe as module
from axiom.cli import main
from axiom.nativeprobe import WindowsSandboxCaptureBackend, run_native_probe_jobs
from axiom.proberun import materialize_probe_study, write_probe_json


def bundle(tmp_path):
    study, study_path = prepare_study(tmp_path)
    exchange = tmp_path / "exchange"
    materialize_probe_study(study_path, exchange)
    return study, exchange


class CaptureFixtureBackend:
    """An explicit synthetic capture producer, not an engine execution."""

    id = "synthetic-capture-fixture"

    def __init__(self, *, outcomes=None, modify=None):
        self.calls = []
        self.outcomes = outcomes or {}
        self.modify = modify

    def run(self, job, replay_path, attempt, study):
        self.calls.append(job["trial_id"])
        assert hashlib.sha256(replay_path.read_bytes()).hexdigest() == job["replay_file_sha256"]
        outcome = self.outcomes.get(job["trial_id"], "completed")
        if outcome == "error":
            return {"capture_path": None, "error": "fixture execution failed"}
        if outcome == "exception":
            raise TimeoutError("fixture attempt deadline")
        if outcome == "cancel":
            raise KeyboardInterrupt
        data = trial_capture(study, job["trial_id"], outcome=outcome)
        if self.modify:
            self.modify(data, job, replay_path)
        write_probe_json(attempt / "capture.json", data)
        return {"capture_path": "capture.json", "error": None}


def test_each_full_start_job_is_consumed_once_and_checkpointed(tmp_path):
    study, exchange = bundle(tmp_path)
    backend = CaptureFixtureBackend()
    output = tmp_path / "run"
    execution = run_native_probe_jobs(exchange, backend, output)
    assert backend.calls == [job["id"] for job in study["trials"]]
    assert execution["attempted_jobs"] == 4
    assert execution["remaining_jobs"] == 0
    assert execution["stop_reason"] == "completed"
    assert execution["new_native_execution"] is False
    assert len(list(output.glob("results-*.json"))) == 4
    results = json.loads((output / "results.json").read_text())
    report = json.loads((output / "map.json").read_text())
    assert len(results["attempts"]) == 4
    assert report["counts"]["accepted_sample"] == 2
    assert report["measurement_origin"] == "native-capture-files"
    assert all(row["evidence_origin"] == "synthetic" for row in report["attempts"])
    assert report["scope"]["m2_gate"] == "not_established"
    assert (output / "exchange/study.json").read_bytes() == (exchange / "study.json").read_bytes()


def test_death_is_normal_terminal_result_not_executor_error(tmp_path):
    study, exchange = bundle(tmp_path)
    first = study["trials"][0]["id"]
    backend = CaptureFixtureBackend(outcomes={first: "died"})
    execution = run_native_probe_jobs(exchange, backend, tmp_path / "run")
    assert execution["stop_reason"] == "completed"
    assert len(backend.calls) == 4
    assert execution["attempts"][0]["status"] == "died"
    report = json.loads(Path(execution["map_path"]).read_text())
    assert report["counts"]["inconsistent_repeats"] == 1


@pytest.mark.parametrize("outcome", ["error", "exception"])
def test_errors_stop_by_default_and_unattempted_jobs_stay_missing(tmp_path, outcome):
    study, exchange = bundle(tmp_path)
    first = study["trials"][0]["id"]
    backend = CaptureFixtureBackend(outcomes={first: outcome})
    execution = run_native_probe_jobs(exchange, backend, tmp_path / "run")
    assert execution["stop_reason"] == "job_error"
    assert backend.calls == [first]
    assert execution["remaining_jobs"] == 3
    report = json.loads(Path(execution["map_path"]).read_text())
    assert report["counts"]["missing_trials"] == 3
    assert report["counts"]["death_sample"] == 0
    assert report["baseline_control"]["established"] is False


def test_explicit_keep_going_preserves_errors_and_continues(tmp_path):
    study, exchange = bundle(tmp_path)
    backend = CaptureFixtureBackend(outcomes={study["trials"][0]["id"]: "error"})
    execution = run_native_probe_jobs(exchange, backend, tmp_path / "run", keep_going=True)
    assert len(backend.calls) == 4
    report = json.loads(Path(execution["map_path"]).read_text())
    assert report["counts"]["unknown"] == 1
    assert report["counts"]["missing_trials"] == 0


def test_partial_job_budget_does_not_change_frozen_study(tmp_path):
    _, exchange = bundle(tmp_path)
    before = (exchange / "jobs.json").read_bytes()
    backend = CaptureFixtureBackend()
    execution = run_native_probe_jobs(exchange, backend, tmp_path / "run", max_jobs=2)
    assert execution["stop_reason"] == "job_budget"
    assert execution["attempted_jobs"] == execution["remaining_jobs"] == 2
    report = json.loads(Path(execution["map_path"]).read_text())
    assert report["counts"]["incomplete"] == 1
    assert (exchange / "jobs.json").read_bytes() == before


@pytest.mark.parametrize("max_jobs", [0, True, 1.0, -1, 4097])
def test_invalid_budget_refused_before_any_output_or_backend_call(tmp_path, max_jobs):
    _, exchange = bundle(tmp_path)
    backend = CaptureFixtureBackend()
    output = tmp_path / "run"
    with pytest.raises(ValueError, match="max_jobs"):
        run_native_probe_jobs(exchange, backend, output, max_jobs=max_jobs)
    assert backend.calls == []
    assert not output.exists()


def test_existing_output_and_exchange_overlap_are_refused(tmp_path):
    _, exchange = bundle(tmp_path)
    backend = CaptureFixtureBackend()
    for path in (exchange, exchange / "nested", tmp_path):
        with pytest.raises(ValueError):
            run_native_probe_jobs(exchange, backend, path)
    assert not backend.calls


def test_changed_exchange_stops_further_scheduling_with_frozen_partial_results(tmp_path):
    _, exchange = bundle(tmp_path)
    backend = CaptureFixtureBackend()
    original = backend.run

    def changed(*args):
        result = original(*args)
        path = exchange / "jobs.json"
        path.write_bytes(path.read_bytes() + b"\n")
        return result

    backend.run = changed
    execution = run_native_probe_jobs(exchange, backend, tmp_path / "run")
    assert execution["stop_reason"] == "input_changed"
    assert execution["attempted_jobs"] == 1
    assert execution["error"]


def test_damaged_frozen_study_still_publishes_failure_report(tmp_path):
    _, exchange = bundle(tmp_path)
    backend = CaptureFixtureBackend()
    original = backend.run
    output = tmp_path / "run"

    def damage(*args):
        response = original(*args)
        (output / "exchange/study.json").write_bytes(b"damaged frozen evidence")
        return response

    backend.run = damage
    execution = run_native_probe_jobs(exchange, backend, output)
    assert execution["stop_reason"] == "input_changed"
    assert execution["attempted_jobs"] == 1
    assert execution["remaining_jobs"] == 3
    assert execution["map_path"] is execution["map_sha256"] is None
    assert execution["map_error"]
    assert execution["scope"]["map_available"] is False
    assert json.loads((output / "executor.json").read_text()) == execution
    assert (output / "results.json").is_file()
    assert (output / "attempts" / backend.calls[0] / "capture.json").is_file()
    assert (output / "exchange/study.json").read_bytes() == b"damaged frozen evidence"


def test_preflight_failure_publishes_all_jobs_missing_without_backend_calls(tmp_path):
    _, exchange = bundle(tmp_path)
    backend = CaptureFixtureBackend()

    def fail_prepare(*args):
        raise ValueError("fixture environment mismatch")

    backend.prepare = fail_prepare
    execution = run_native_probe_jobs(exchange, backend, tmp_path / "run")
    assert execution["stop_reason"] == "preflight_error"
    assert execution["attempted_jobs"] == 0
    assert execution["remaining_jobs"] == 4
    assert execution["new_native_execution"] is False
    report = json.loads(Path(execution["map_path"]).read_text())
    assert report["counts"]["missing_trials"] == 4
    assert backend.calls == []


@pytest.mark.parametrize("confirmed,uncertain,reported", [(0, 0, False), (0, 1, None), (1, 1, True)])
def test_missing_worker_evidence_is_not_reported_as_confirmed_absence(
    tmp_path, confirmed, uncertain, reported
):
    study, exchange = bundle(tmp_path)
    backend = CaptureFixtureBackend(outcomes={study["trials"][0]["id"]: "error"})
    backend.native_launch_attempts = confirmed
    backend.native_launch_uncertain_attempts = uncertain
    execution = run_native_probe_jobs(exchange, backend, tmp_path / "run")
    assert execution["new_native_execution"] is reported
    assert execution["native_launch_attempts"] == confirmed
    assert execution["native_launch_uncertain_attempts"] == uncertain


def test_foreign_capture_is_retained_rejected_without_a_death(tmp_path):
    _, exchange = bundle(tmp_path)

    def wrong(data, job, replay):
        data["collector"]["source_commit"] = "a" * 40

    backend = CaptureFixtureBackend(modify=wrong)
    output = tmp_path / "run"
    execution = run_native_probe_jobs(exchange, backend, output)
    assert execution["stop_reason"] == "job_error"
    assert execution["attempts"][0]["status"] == "rejected"
    assert list((output / "attempts").rglob("capture.json"))
    report = json.loads(Path(execution["map_path"]).read_text())
    assert report["attempts"][0]["outcome"] == "rejected"
    assert report["counts"]["death_sample"] == 0


def test_reused_execution_id_cannot_fake_an_independent_repeat(tmp_path):
    _, exchange = bundle(tmp_path)

    def reused(data, job, replay):
        data["attempt"]["id"] = "reused-capture-execution"

    backend = CaptureFixtureBackend(modify=reused)
    execution = run_native_probe_jobs(exchange, backend, tmp_path / "run")
    assert execution["attempted_jobs"] == 2
    assert execution["attempts"][1]["status"] == "runner_error"
    results = json.loads(Path(execution["results_path"]).read_text())
    assert "error" in results["attempts"][1]


def test_cancelled_backend_keeps_partial_artifact_and_stops(tmp_path):
    study, exchange = bundle(tmp_path)
    backend = CaptureFixtureBackend(outcomes={study["trials"][0]["id"]: "cancel"})
    execution = run_native_probe_jobs(exchange, backend, tmp_path / "run")
    assert execution["stop_reason"] == "cancelled"
    assert execution["attempted_jobs"] == 1
    assert execution["remaining_jobs"] == 3


@pytest.mark.parametrize(
    "reply",
    [
        None,
        {},
        {"capture_path": "../capture.json", "error": None},
        {"capture_path": "capture.json", "error": "failed"},
        {"capture_path": None, "error": "\ud800"},
    ],
)
def test_malformed_backend_reply_is_preserved_as_runner_error(tmp_path, reply):
    _, exchange = bundle(tmp_path)
    backend = SimpleNamespace(id="malformed-fixture", run=lambda *args: reply)
    execution = run_native_probe_jobs(exchange, backend, tmp_path / "run")
    assert execution["attempts"][0]["status"] == "runner_error"
    assert execution["remaining_jobs"] == 3


def test_backend_cannot_mutate_frozen_job_or_study_arguments(tmp_path):
    study, exchange = bundle(tmp_path)
    backend = CaptureFixtureBackend()
    original = backend.run

    def mutate(job, replay, attempt, passed_study):
        response = original(job, replay, attempt, passed_study)
        job["trial_id"] = "changed"
        passed_study["reference"]["environment_sha256"] = "f" * 64
        return response

    backend.run = mutate
    execution = run_native_probe_jobs(exchange, backend, tmp_path / "run")
    assert [row["trial_id"] for row in execution["attempts"]] == [row["id"] for row in study["trials"]]


def test_cooperative_cancel_waits_for_worker_completion_without_forced_termination(tmp_path):
    backend = object.__new__(WindowsSandboxCaptureBackend)
    backend.cancelled = False
    calls = []

    class Worker:
        def wait(self, timeout):
            calls.append(timeout)
            if len(calls) < 3:
                raise KeyboardInterrupt
            return 2

    assert backend._wait_worker(Worker(), tmp_path) == 2
    assert backend.cancelled is True
    assert json.loads((tmp_path / "cancel.request.json").read_text()) == {"cancel_requested": True}


def test_interrupt_during_cancel_signal_still_waits_for_owned_worker(tmp_path, monkeypatch):
    backend = object.__new__(WindowsSandboxCaptureBackend)
    backend.cancelled = False
    calls = []

    class Worker:
        def wait(self, timeout):
            calls.append(timeout)
            if len(calls) == 1:
                raise KeyboardInterrupt
            return 2

    def interrupted_write(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(module, "write_probe_json", interrupted_write)
    assert backend._wait_worker(Worker(), tmp_path) == 2
    assert backend.cancelled is True
    assert len(calls) == 2


def test_cli_binds_native_options_to_executor_without_starting_processes(tmp_path, monkeypatch, capsys):
    _, exchange = bundle(tmp_path)
    backend = CaptureFixtureBackend()
    received = {}

    def construct(*args, **kwargs):
        received.update(args=args, kwargs=kwargs)
        return backend

    monkeypatch.setattr(module, "WindowsSandboxCaptureBackend", construct)
    arguments = [
        "probe-run",
        str(exchange),
        "--workspace",
        str(tmp_path),
        "--game-directory",
        "game",
        "--native-package",
        "package.geode",
        "--level",
        "level.txt",
        "--output",
        str(tmp_path / "run"),
        "--timeout-seconds",
        "45",
        "--max-jobs",
        "2",
    ]
    assert main(arguments) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["attempted_jobs"] == 2
    assert result["new_native_execution"] is False
    assert received["kwargs"]["timeout_seconds"] == 45


@pytest.mark.parametrize("outcome,exit_code", [("error", 2), ("cancel", 130)])
def test_cli_reports_failure_or_cancellation_after_retaining_partial_results(
    tmp_path, monkeypatch, capsys, outcome, exit_code
):
    study, exchange = bundle(tmp_path)
    backend = CaptureFixtureBackend(outcomes={study["trials"][0]["id"]: outcome})
    monkeypatch.setattr(module, "WindowsSandboxCaptureBackend", lambda *args, **kwargs: backend)
    output = tmp_path / "run"
    assert (
        main(
            [
                "probe-run",
                str(exchange),
                "--game-directory",
                "game",
                "--native-package",
                "package.geode",
                "--level",
                "level.txt",
                "--output",
                str(output),
            ]
        )
        == exit_code
    )
    result = json.loads(capsys.readouterr().out)
    assert json.loads((output / "executor.json").read_text()) == result
    assert result["remaining_jobs"] == 3


@pytest.mark.parametrize("worker_result", ["good", "missing", "invalid", "changed", "prelaunch_error"])
def test_worker_request_keeps_arguments_data_and_checks_cleanup(tmp_path, monkeypatch, worker_result):
    study, exchange = bundle(tmp_path)
    backend = object.__new__(WindowsSandboxCaptureBackend)
    backend.workspace = tmp_path
    backend.game_directory = tmp_path / "game"
    backend.native_package = tmp_path / "package.geode"
    backend.native_package.write_bytes(b"package fixture")
    backend._level_retained = tmp_path / "level.txt"
    backend._level_retained.write_bytes(b"level fixture")
    backend.worker = tmp_path / "worker.ps1"
    backend.worker.write_bytes(b"not executed")
    backend.powershell = "powershell"
    backend.timeout_seconds = 30
    backend.native_launch_attempts = 0
    backend.cancelled = False
    backend.assert_unchanged = lambda: None
    job = json.loads((exchange / "jobs.json").read_text())["jobs"][0]
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    calls = []

    def unchanged():
        if calls and worker_result == "changed":
            raise ValueError("fixture backend input changed")

    backend.assert_unchanged = unchanged

    class Worker:
        def wait(self, timeout):
            return 2 if worker_result == "prelaunch_error" else 0

    def popen(arguments, **kwargs):
        calls.append((arguments, kwargs))
        request = json.loads((attempt / "request.json").read_text())
        assert request["native_package_sha256"] == hashlib.sha256(b"package fixture").hexdigest()
        capture_path = attempt / "capture.json"
        write_probe_json(capture_path, trial_capture(study, job["trial_id"]))
        if worker_result == "missing":
            return Worker()
        write_probe_json(
            attempt / "attempt.json",
            {
                "schema_version": 1,
                "kind": "native_probe_attempt",
                "trial_id": job["trial_id"],
                "request_sha256": hashlib.sha256((attempt / "request.json").read_bytes()).hexdigest(),
                "status": "runner_error" if worker_result == "prelaunch_error" else "capture_retained",
                "error": "fixture prelaunch failure" if worker_result == "prelaunch_error" else None,
                "timeout_reached": False,
                "process_cleanup": None
                if worker_result == "prelaunch_error"
                else {
                    "exit_observed_before_cleanup": False,
                    "termination_requested": "invalid" if worker_result == "invalid" else True,
                    "natural_exit_code": None,
                },
                "preservation": [
                    {
                        "preserved": True,
                        "existed_before": False,
                        "exists_after": False,
                        "sha256_before": None,
                        "sha256_after": None,
                    }
                    for _ in range(4)
                ],
                "cleanup_errors": [],
                "capture": {
                    "path": "capture.json",
                    "sha256": hashlib.sha256(capture_path.read_bytes()).hexdigest(),
                },
            },
        )
        return Worker()

    monkeypatch.setattr(module.subprocess, "Popen", popen)
    if worker_result in {"missing", "invalid", "changed"}:
        with pytest.raises((ValueError, OSError)):
            backend.run(job, exchange / job["replay_path"], attempt, study)
    else:
        response = backend.run(job, exchange / job["replay_path"], attempt, study)
        if worker_result == "prelaunch_error":
            assert response == {"capture_path": None, "error": "fixture prelaunch failure"}
        else:
            assert response == {"capture_path": "capture.json", "error": None}
    assert backend.native_launch_attempts == int(worker_result in {"good", "changed"})
    assert backend.native_launch_uncertain_attempts == int(worker_result in {"missing", "invalid"})
    assert backend.worker_invocations == 1
    assert calls[0][0][-2:] == ["-RequestPath", str(attempt / "request.json")]
    assert calls[0][1]["stdin"] == module.subprocess.DEVNULL
    assert "shell" not in calls[0][1]


@pytest.mark.parametrize("mismatch", [None, "game", "level", "dll", "origin", "alias"])
def test_native_preflight_binds_exact_files_before_worker_start(tmp_path, mismatch):
    study, _ = bundle(tmp_path)
    workspace = tmp_path / "workspace"
    (workspace / "scripts").mkdir(parents=True)
    (workspace / ".tools").mkdir()
    game = workspace / "game"
    game.mkdir()
    for name in ("GeometryDash.exe", "steam_appid.txt", "Geode.dll"):
        (game / name).write_bytes(("synthetic bytes, never executed: " + name).encode())
    for name in (
        "run-native-probe-attempt.ps1",
        "native-probe-process.ps1",
        "native-experiment-state.ps1",
        "prepare-native-sandbox.ps1",
    ):
        (workspace / "scripts" / name).write_bytes(b"synthetic bytes, never executed")
    level = workspace / "level.txt"
    level.write_bytes(b"synthetic plain level bytes")
    package = workspace / "package.geode"
    with module.zipfile.ZipFile(package, "w") as archive:
        archive.writestr("axiom.native-capture.dll", b"synthetic DLL bytes, never loaded")
        if mismatch == "alias":
            archive.writestr("AXIOM.NATIVE-CAPTURE.DLL", b"alias bytes, never loaded")
    study["reference"]["provenance"]["origin"] = "native-engine-capture"
    study["reference"]["challenge"]["level_sha256"] = module._file_hash(level)
    environment = study["reference"]["environment"]
    environment["game_executable_sha256"] = module._file_hash(game / "GeometryDash.exe")
    environment["adapter_binary_sha256"] = hashlib.sha256(b"synthetic DLL bytes, never loaded").hexdigest()
    if mismatch in {"game", "dll"}:
        environment["game_executable_sha256" if mismatch == "game" else "adapter_binary_sha256"] = "0" * 64
    elif mismatch == "level":
        study["reference"]["challenge"]["level_sha256"] = "0" * 64
    elif mismatch == "origin":
        study["reference"]["provenance"]["origin"] = "synthetic"
    backend = object.__new__(WindowsSandboxCaptureBackend)
    backend.workspace, backend.game_directory = workspace, game
    backend.native_package, backend.level_path = package, level
    backend.worker = workspace / "scripts/run-native-probe-attempt.ps1"
    backend._inputs, backend._level_retained = [], None
    output = workspace / "run"
    output.mkdir()
    if mismatch is not None:
        with pytest.raises(ValueError):
            backend.prepare(study, output)
        assert not list(output.iterdir())
    else:
        backend.prepare(study, output)
        assert (output / "level.txt").read_bytes() == level.read_bytes()
        assert (output / "backend-inputs.json").is_file()
        (game / "Geode.dll").write_bytes(b"changed frozen file")
        with pytest.raises(ValueError, match="input changed"):
            backend.assert_unchanged()
