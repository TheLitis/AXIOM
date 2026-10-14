"""Sequential capture-producing probe execution with an owned Windows worker.

The worker launches the pinned sandbox; the Python layer validates captures and
never substitutes process exit status for the native terminal oracle.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from .probeadapter import inspect_native_probe_results
from .probejobs import assert_probe_exchange_unchanged, load_probe_exchange
from .proberun import (
    _absolute,
    _fingerprint,
    _ordinary,
    _read_stable,
    _write_fresh_atomic,
    prepare_probe_directory,
    write_probe_json,
)
from .probes import analyze_probe_results
from .validation import read_json, string


class CaptureBackend(Protocol):
    """Produce an ordinary attempt-local capture or an explicit execution error."""

    id: str

    def run(self, job: dict, replay_path: Path, attempt_directory: Path, study: dict) -> dict: ...


def _error(exc):
    try:
        message = str(exc)
    except Exception:
        message = "Exception message unavailable"
    return f"{type(exc).__name__}: {message}".encode("utf-8", errors="replace").decode("utf-8")[:1024]


def _file_hash(path):
    path = _absolute(path)
    _ordinary(path, directory=False)
    before = path.lstat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        if _fingerprint(os.fstat(stream.fileno())) != _fingerprint(before):
            raise ValueError("Native execution input changed while opening")
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        if _fingerprint(os.fstat(stream.fileno())) != _fingerprint(before):
            raise ValueError("Native execution input changed while hashing")
    _ordinary(path, directory=False)
    if _fingerprint(path.lstat()) != _fingerprint(before):
        raise ValueError("Native execution input changed while hashing")
    return digest.hexdigest()


def _positive_limit(value, name, maximum):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer from 1 to {maximum}")
    return value


def _relative_capture(response, attempt_directory):
    if not isinstance(response, dict) or response.keys() != {"capture_path", "error"}:
        raise ValueError("Capture backend must return capture_path and error")
    if response["error"] is not None:
        if response["capture_path"] is not None:
            raise ValueError("Execution errors cannot substitute a capture for clean completion")
        string(response["error"], "backend.error")
        try:
            response["error"].encode("utf-8")
        except UnicodeError as exc:
            raise ValueError("Backend error must contain valid UTF-8 text") from exc
        return None
    if response["capture_path"] != "capture.json":
        raise ValueError("A backend must retain its capture as attempt-local capture.json")
    path = attempt_directory / "capture.json"
    _ordinary(path, directory=False)
    return path


def run_native_probe_jobs(
    exchange_directory, backend: CaptureBackend, output_directory, *, max_jobs=None, keep_going=False
):
    """Execute frozen jobs serially; checkpoint every attempt and preserve partial results.

    Native death is an ordinary terminal result. Launch, integrity and cleanup
    failures stop scheduling by default. No implicit retries or resume are used.
    A test backend may produce explicitly synthetic capture fixtures; their origin
    remains synthetic in the capture adapter and map.
    """
    exchange = _absolute(exchange_directory)
    bundle = load_probe_exchange(exchange)
    backend_id = string(getattr(backend, "id", None), "capture backend.id")
    if not callable(getattr(backend, "run", None)):
        raise ValueError("Capture backend must provide run")
    if type(keep_going) is not bool:
        raise ValueError("keep_going must be boolean")
    jobs = bundle["manifest"]["jobs"]
    limit = len(jobs) if max_jobs is None else min(_positive_limit(max_jobs, "max_jobs", 4096), len(jobs))
    out = _absolute(output_directory)
    if out == exchange or exchange in out.parents or out in exchange.parents:
        raise ValueError("Execution output must not overlap the frozen exchange")
    out = prepare_probe_directory(out)
    (out / "attempts").mkdir()
    frozen = out / "exchange"
    frozen.mkdir()
    (frozen / "plans").mkdir()
    for record in bundle["files"]:
        raw = _read_stable(exchange / record["relative_path"])
        if hashlib.sha256(raw).hexdigest() != record["sha256"]:
            raise ValueError("Exchange bytes changed before execution snapshot")
        _write_fresh_atomic(frozen / record["relative_path"], raw)
    assert_probe_exchange_unchanged(exchange, bundle)
    frozen_bundle = load_probe_exchange(frozen)
    study_path = frozen / "study.json"
    study = frozen_bundle["study"]
    rows, records, seen_hashes, seen_ids = [], [], set(), set()
    stop_reason, global_error = "completed", None
    prepare = getattr(backend, "prepare", None)
    if callable(prepare):
        try:
            prepare(deepcopy(study), out)
        except KeyboardInterrupt:
            stop_reason, global_error = "cancelled", "Preparation cancelled; no terminal outcome inferred"
        except Exception as exc:
            stop_reason, global_error = "preflight_error", _error(exc)
    scheduled = jobs[:limit] if stop_reason == "completed" else []
    for index, job in enumerate(scheduled, 1):
        try:
            assert_probe_exchange_unchanged(exchange, bundle)
            assert_probe_exchange_unchanged(frozen, frozen_bundle)
            unchanged = getattr(backend, "assert_unchanged", None)
            if callable(unchanged):
                unchanged()
        except (ValueError, OSError) as exc:
            stop_reason, global_error = "input_changed", _error(exc)
            break
        attempt = prepare_probe_directory(out / "attempts" / job["trial_id"])
        row = {"trial_id": job["trial_id"]}
        status, observation, detail = "runner_error", None, None
        try:
            response = backend.run(deepcopy(job), frozen / job["replay_path"], attempt, deepcopy(study))
            capture = _relative_capture(response, attempt)
            if capture is None:
                row["error"] = response["error"]
                detail = response["error"]
            else:
                digest = _file_hash(capture)
                row.update(capture_path=capture.relative_to(out).as_posix(), capture_sha256=digest)
                one_manifest = out / f"check-{index:04d}.json"
                write_probe_json(
                    one_manifest,
                    {
                        "schema_version": 1,
                        "kind": "native_probe_results",
                        "study_sha256": bundle["manifest"]["study_sha256"],
                        "attempts": [row],
                    },
                )
                observation = inspect_native_probe_results(study_path, one_manifest)["attempts"][0]
                if observation["outcome"] in {"completed", "died"}:
                    if digest in seen_hashes or observation["execution_id"] in seen_ids:
                        raise ValueError(
                            "A native repetition cannot reuse capture bytes or execution identity"
                        )
                    required_origin = getattr(backend, "capture_origin_required", None)
                    if required_origin is not None and observation["evidence_origin"] != required_origin:
                        raise ValueError("Native sandbox returned a capture with an unexpected origin")
                    seen_hashes.add(digest)
                    seen_ids.add(observation["execution_id"])
                    status = observation["outcome"]
                else:
                    status, detail = "rejected", observation["error"]
        except KeyboardInterrupt:
            stop_reason, detail = "cancelled", "Execution cancelled; no terminal outcome inferred"
            row = {"trial_id": job["trial_id"], "error": detail}
        except Exception as exc:
            detail = _error(exc)
            row = {"trial_id": job["trial_id"], "error": detail}
        rows.append(row)
        record = {
            "trial_id": job["trial_id"],
            "status": status,
            "error": detail,
            "observation": observation,
        }
        records.append(record)
        write_probe_json(
            out / f"results-{index:04d}.json",
            {
                "schema_version": 1,
                "kind": "native_probe_results",
                "study_sha256": bundle["manifest"]["study_sha256"],
                "attempts": rows,
            },
        )
        write_probe_json(attempt / "executor-observation.json", record)
        if getattr(backend, "cancelled", False) or stop_reason == "cancelled":
            stop_reason = "cancelled"
            break
        if status in {"runner_error", "rejected"} and not keep_going:
            stop_reason = "job_error"
            break
    if stop_reason == "completed" and limit < len(jobs):
        stop_reason = "job_budget"
    try:
        assert_probe_exchange_unchanged(exchange, bundle)
        assert_probe_exchange_unchanged(frozen, frozen_bundle)
        unchanged = getattr(backend, "assert_unchanged", None)
        if callable(unchanged):
            unchanged()
    except (ValueError, OSError) as exc:
        stop_reason, global_error = "input_changed", _error(exc)
    results_path = out / "results.json"
    write_probe_json(
        results_path,
        {
            "schema_version": 1,
            "kind": "native_probe_results",
            "study_sha256": bundle["manifest"]["study_sha256"],
            "attempts": rows,
        },
    )
    probe_map, map_path, map_error = None, None, None
    try:
        probe_map = analyze_probe_results(study_path, results_path)
        write_probe_json(out / "map.json", probe_map)
        map_path = out / "map.json"
    except (ValueError, OSError) as exc:
        map_error = _error(exc)
        if global_error is None:
            global_error = map_error
        if stop_reason in {"completed", "job_budget"}:
            stop_reason = "map_error"
    confirmed_launches = getattr(backend, "native_launch_attempts", 0)
    uncertain_launches = getattr(backend, "native_launch_uncertain_attempts", 0)
    execution = {
        "schema_version": 1,
        "kind": "native_probe_execution",
        "backend_id": backend_id,
        "study_sha256": bundle["manifest"]["study_sha256"],
        "source_exchange": str(exchange),
        "exchange_files": bundle["files"],
        "stop_reason": stop_reason,
        "error": global_error,
        "keep_going": keep_going,
        "requested_job_limit": limit,
        "total_jobs": len(jobs),
        "attempted_jobs": len(rows),
        "remaining_jobs": len(jobs) - len(rows),
        "error_jobs": sum(record["status"] in {"runner_error", "rejected"} for record in records),
        "attempts": records,
        "results_path": str(results_path),
        "results_sha256": _file_hash(results_path),
        "map_path": str(map_path) if map_path is not None else None,
        "map_sha256": _file_hash(map_path) if map_path is not None else None,
        "map_error": map_error,
        "worker_invocations": getattr(backend, "worker_invocations", 0),
        "native_launch_attempts": confirmed_launches,
        "native_launch_uncertain_attempts": uncertain_launches,
        "new_native_execution": True if confirmed_launches else None if uncertain_launches else False,
        "scope": probe_map["scope"]
        if map_path is not None
        else {
            "map_available": False,
            "m1_gate": "not_established",
            "m2_gate": "not_established",
            "human_calibration": "not_established",
            "real_level_ar": "not_established",
        },
    }
    write_probe_json(out / "executor.json", execution)
    return execution


class WindowsSandboxCaptureBackend:
    """Use the repository worker and pinned sandbox, with cooperative cancellation."""

    id = "windows-sandbox-capture-v1"
    capture_origin_required = "native-engine-capture"

    def __init__(self, workspace, game_directory, native_package, level_path, *, timeout_seconds=90):
        if os.name != "nt":
            raise ValueError("The native sandbox backend is supported on Windows only")
        if type(timeout_seconds) is not int or not 30 <= timeout_seconds <= 600:
            raise ValueError("Attempt timeout must be an integer from 30 to 600 seconds")
        self.workspace = _absolute(workspace)
        self.game_directory = _absolute(game_directory)
        self.native_package = _absolute(native_package)
        self.level_path = _absolute(level_path)
        self.timeout_seconds = timeout_seconds
        self.worker = self.workspace / "scripts/run-native-probe-attempt.ps1"
        self.powershell = shutil.which("pwsh") or shutil.which("powershell")
        if not self.powershell:
            raise ValueError("PowerShell is required for the Windows sandbox backend")
        for path in (self.workspace, self.game_directory, self.workspace / ".tools"):
            _ordinary(path, directory=True)
        self.native_launch_attempts = 0
        self.native_launch_uncertain_attempts = 0
        self.worker_invocations = 0
        self.cancelled = False
        self._inputs = []
        self._level_retained = None

    def prepare(self, study, output):
        if self.workspace not in _absolute(output).parents:
            raise ValueError("Native execution evidence must remain inside its worker checkout")
        if study["reference"]["provenance"]["origin"] != "native-engine-capture":
            raise ValueError("Live sandbox execution requires a declared native-engine reference")
        game = self.game_directory / "GeometryDash.exe"
        environment = study["reference"]["environment"]
        if _file_hash(game) != environment["game_executable_sha256"]:
            raise ValueError("Game executable differs from the frozen reference environment")
        if _file_hash(self.level_path) != study["reference"]["challenge"]["level_sha256"]:
            raise ValueError("Level bytes differ from the frozen reference challenge")
        _ordinary(self.native_package, directory=False)
        with zipfile.ZipFile(self.native_package) as package:
            dlls = [
                item for item in package.infolist() if item.filename.lower() == "axiom.native-capture.dll"
            ]
            if (
                len(dlls) != 1
                or dlls[0].filename != "axiom.native-capture.dll"
                or not 1 <= dlls[0].file_size <= 64 * 1024 * 1024
            ):
                raise ValueError("Native package must contain one bounded root adapter DLL")
            if hashlib.sha256(package.read(dlls[0])).hexdigest() != environment["adapter_binary_sha256"]:
                raise ValueError("Native package DLL differs from the frozen reference environment")
        sources = [
            game,
            self.native_package,
            self.level_path,
            self.worker,
            self.workspace / "scripts/native-probe-process.ps1",
            self.workspace / "scripts/native-experiment-state.ps1",
            self.workspace / "scripts/prepare-native-sandbox.ps1",
            *sorted(self.game_directory.glob("*.dll")),
            self.game_directory / "steam_appid.txt",
        ]
        self._inputs = [{"path": str(path), "sha256": _file_hash(path)} for path in sources]
        raw = _read_stable(self.level_path)
        self._level_retained = output / "level.txt"
        _write_fresh_atomic(self._level_retained, raw)
        write_probe_json(
            output / "backend-inputs.json",
            {
                "kind": "native_probe_backend_inputs",
                "schema_version": 1,
                "files": self._inputs,
                "level_sha256": hashlib.sha256(raw).hexdigest(),
                "worker_deadline_policy": "worker_owned_game_timeout_cooperative_cancellation",
            },
        )
        self.assert_unchanged()

    def assert_unchanged(self):
        for record in self._inputs:
            if _file_hash(record["path"]) != record["sha256"]:
                raise ValueError(f"Native backend input changed: {record['path']}")
        if self._level_retained is not None and _file_hash(self._level_retained) != _file_hash(
            self.level_path
        ):
            raise ValueError("Retained level bytes changed")

    def _wait_worker(self, process, attempt):
        while True:
            try:
                return process.wait(timeout=0.25)
            except subprocess.TimeoutExpired:
                continue
            except KeyboardInterrupt:
                self.cancelled = True
                try:
                    marker = attempt / "cancel.request.json"
                    if not marker.exists():
                        write_probe_json(marker, {"cancel_requested": True})
                except (ValueError, OSError, KeyboardInterrupt):
                    # Even another interrupt during signaling must keep ownership
                    # until the ordinary game deadline and restoration.
                    pass
                # The worker owns the game deadline and restoration. Do not
                # terminate it before its finally block restores profile bytes.

    def run(self, job, replay_path, attempt_directory, study):
        self.assert_unchanged()
        environment = study["reference"]["environment"]
        request = {
            "schema_version": 1,
            "kind": "native_probe_attempt_request",
            "trial_id": job["trial_id"],
            "workspace": str(self.workspace),
            "attempt_directory": str(attempt_directory),
            "runtime_directory": str(self.workspace / ".tools" / f"probe-runtime-{uuid4().hex}"),
            "game_directory": str(self.game_directory),
            "native_package": str(self.native_package),
            "native_package_sha256": _file_hash(self.native_package),
            "level_path": str(self._level_retained),
            "replay_path": str(replay_path),
            "level_sha256": study["reference"]["challenge"]["level_sha256"],
            "replay_file_sha256": job["replay_file_sha256"],
            "environment_sha256": study["reference"]["environment_sha256"],
            "game_executable_sha256": environment["game_executable_sha256"],
            "adapter_binary_sha256": environment["adapter_binary_sha256"],
            "timeout_seconds": self.timeout_seconds,
        }
        request_path = attempt_directory / "request.json"
        write_probe_json(request_path, request)
        for name in ("worker.stdout.txt", "worker.stderr.txt"):
            _write_fresh_atomic(attempt_directory / name, b"")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        with (
            (attempt_directory / "worker.stdout.txt").open("wb") as out,
            (attempt_directory / "worker.stderr.txt").open("wb") as err,
        ):
            process = subprocess.Popen(
                [
                    self.powershell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(self.worker),
                    "-RequestPath",
                    str(request_path),
                ],
                cwd=self.workspace,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                creationflags=flags,
            )
            self.worker_invocations = getattr(self, "worker_invocations", 0) + 1
            self.native_launch_uncertain_attempts = getattr(self, "native_launch_uncertain_attempts", 0) + 1
            code = self._wait_worker(process, attempt_directory)
        manifest_path = attempt_directory / "attempt.json"
        _ordinary(manifest_path, directory=False)
        manifest, _ = read_json(manifest_path)
        if (
            manifest.get("kind") != "native_probe_attempt"
            or type(manifest.get("schema_version")) is not int
            or manifest["schema_version"] != 1
            or manifest.get("trial_id") != job["trial_id"]
            or manifest.get("request_sha256") != _file_hash(request_path)
            or manifest.get("status") not in {"capture_retained", "runner_error"}
            or type(manifest.get("timeout_reached")) is not bool
            or not isinstance(manifest.get("cleanup_errors"), list)
        ):
            raise ValueError("Worker result differs from its frozen request")
        cleanup = manifest.get("process_cleanup")
        if cleanup is None and manifest["cleanup_errors"]:
            raise ValueError("Missing process cleanup metadata cannot confirm absence of a launch")
        if cleanup is not None and (
            not isinstance(cleanup, dict)
            or type(cleanup.get("exit_observed_before_cleanup")) is not bool
            or type(cleanup.get("termination_requested")) is not bool
            or cleanup.get("natural_exit_code") is not None
            and type(cleanup["natural_exit_code"]) is not int
        ):
            raise ValueError("Worker process cleanup metadata is invalid")
        self.native_launch_uncertain_attempts -= 1
        if cleanup is not None:
            self.native_launch_attempts += 1
        self.assert_unchanged()
        if code != 0 or manifest.get("status") != "capture_retained":
            return {"capture_path": None, "error": str(manifest.get("error") or f"Worker exit {code}")[:1024]}
        preservation = manifest.get("preservation")
        if (
            manifest.get("error") is not None
            or manifest.get("timeout_reached") is not False
            or manifest.get("cleanup_errors") != []
            or not isinstance(preservation, list)
            or len(preservation) != 4
            or any(
                not isinstance(record, dict) or record.get("preserved") is not True for record in preservation
            )
            or any(
                record.get("existed_before") != record.get("exists_after")
                or record.get("sha256_before") != record.get("sha256_after")
                for record in preservation
            )
            or manifest.get("process_cleanup") is None
        ):
            raise ValueError("Worker cleanup/preservation did not pass")
        capture = manifest.get("capture")
        if (
            not isinstance(capture, dict)
            or capture.keys() != {"path", "sha256"}
            or capture["path"] != "capture.json"
        ):
            raise ValueError("Worker capture descriptor is invalid")
        if _file_hash(attempt_directory / "capture.json") != capture["sha256"]:
            raise ValueError("Worker capture bytes changed after retention")
        return {"capture_path": "capture.json", "error": None}
