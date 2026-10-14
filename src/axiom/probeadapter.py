"""Bind supplied native terminal files to a frozen command-perturbation study.

This adapter reads evidence files only. An accepted native callback records an
outcome under the declared intervention; neither a file nor its declared origin
authenticates an execution or establishes ordinary device-input equivalence.
"""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .native import canonical_sha256, load_native_capture
from .probeplan import load_probe_study, point_replay, replay_bytes, study_sha256
from .validation import mapping, read_json, sha256, string

MAX_CAPTURE_PATH_CHARS = 1024
MAX_CAPTURE_PATH_PARTS = 16
MAX_ERROR_CHARS = 1024
_INPUT_FIELDS = ("command_index", "player", "button", "pressed")


def _fields(value: Any, name: str, required: set[str]) -> dict:
    value = mapping(value, name)
    missing, unexpected = required - value.keys(), value.keys() - required
    if missing or unexpected:
        details = []
        if missing:
            details.append("missing " + ", ".join(sorted(missing)))
        if unexpected:
            details.append("unknown " + ", ".join(sorted(unexpected)))
        raise ValueError(f"{name}: {'; '.join(details)}")
    return value


def _ordinary_file(path: str | Path) -> Path:
    """Refuse links/reparse points along the entire lexical absolute path."""
    absolute = Path(os.path.abspath(path))
    for ancestor in reversed((absolute, *absolute.parents)):
        info = ancestor.lstat()
        if stat.S_ISLNK(info.st_mode) or (
            getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise ValueError("Probe evidence paths cannot contain links or reparse points")
        if ancestor == absolute:
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("Probe evidence must be an ordinary file")
        elif not stat.S_ISDIR(info.st_mode):
            raise ValueError("Probe evidence parent must be an ordinary directory")
    return absolute


def _signature(path: Path) -> tuple:
    info = _ordinary_file(path).lstat()
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        getattr(info, "st_birthtime_ns", None),
    )


def _stable_json(path: str | Path) -> tuple[dict, str, Path, tuple]:
    ordinary = _ordinary_file(path)
    before = _signature(ordinary)
    document, digest = read_json(ordinary)
    if _signature(ordinary) != before:
        raise ValueError("Probe evidence changed while it was read")
    return document, digest, ordinary, before


def _relative_capture_path(root: Path, value: Any) -> Path:
    value = string(value, "attempt.capture_path")
    windows, portable = PureWindowsPath(value), PurePosixPath(value)
    if (
        len(value) > MAX_CAPTURE_PATH_CHARS
        or value != value.strip()
        or "\\" in value
        or ":" in value
        or "\x00" in value
        or windows.drive
        or windows.root
        or portable.is_absolute()
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or len(portable.parts) > MAX_CAPTURE_PATH_PARTS
        or any(len(part) > 255 for part in portable.parts)
    ):
        raise ValueError("attempt.capture_path must be a bounded relative path within the results directory")
    candidate = root.joinpath(*portable.parts)
    if not candidate.is_relative_to(root):
        raise ValueError("attempt.capture_path escapes the results directory")
    return candidate


def _validate_results(value: Any, study: dict, root: Path) -> list[dict]:
    results = _fields(value, "native_probe_results", {"schema_version", "kind", "study_sha256", "attempts"})
    if type(results["schema_version"]) is not int or results["schema_version"] != 1:
        raise ValueError("native_probe_results schema_version must be integer 1")
    if results["kind"] != "native_probe_results":
        raise ValueError("Expected kind native_probe_results")
    if sha256(results["study_sha256"], "study_sha256") != study_sha256(study):
        raise ValueError("Results study_sha256 differs from the frozen probe study")
    trials = {row["id"]: row for row in study["trials"]}
    rows = results["attempts"]
    if not isinstance(rows, list) or len(rows) > len(trials):
        raise ValueError("native_probe_results.attempts must be an array bounded by the planned trials")
    seen_trials, seen_paths, seen_hashes = set(), set(), set()
    for index, value in enumerate(rows):
        name = f"attempts[{index}]"
        row = mapping(value, name)
        required = {"trial_id", "error"} if "error" in row else {"trial_id", "capture_path", "capture_sha256"}
        _fields(row, name, required)
        trial_id = string(row["trial_id"], f"{name}.trial_id")
        if trial_id not in trials or trial_id in seen_trials:
            raise ValueError("Results contain an unknown or duplicate trial_id")
        seen_trials.add(trial_id)
        if "error" in row:
            error = string(row["error"], f"{name}.error")
            if len(error) > MAX_ERROR_CHARS or error != error.strip():
                raise ValueError("Runner errors must be trimmed, nonempty bounded strings")
            continue
        path = _relative_capture_path(root, row["capture_path"])
        path_key = os.path.normcase(str(path))
        digest = sha256(row["capture_sha256"], f"{name}.capture_sha256")
        if path_key in seen_paths or digest in seen_hashes:
            raise ValueError("Independent trials cannot reuse a capture path or capture SHA-256")
        seen_paths.add(path_key)
        seen_hashes.add(digest)
    return rows


def _empty_observation(trial_id: str, outcome: str, error: str | None = None) -> dict:
    return {
        "trial_id": trial_id,
        "outcome": outcome,
        "terminal_state_sha256": None,
        "native_terminal_event": None,
        "command_index": None,
        "evidence_sha256": None,
        "evidence_origin": None,
        "execution_id": None,
        "error": error,
    }


def _read_capture(path: Path, declared_hash: str) -> tuple[dict, str]:
    document, digest, ordinary, signature = _stable_json(path)
    if digest != declared_hash:
        raise ValueError("Capture SHA-256 differs from its results manifest")
    capture = load_native_capture(ordinary)
    final_document, final_digest = read_json(_ordinary_file(ordinary))
    if (
        digest != final_digest
        or document != capture
        or document != final_document
        or signature != _signature(ordinary)
    ):
        raise ValueError("Capture evidence changed during native validation")
    return capture, digest


def _validate_trial_capture(capture: dict, study: dict, trial: dict) -> None:
    if capture["schema_version"] not in {4, 5}:
        raise ValueError("Probe trials require native capture schema 4 or 5")
    attempt = capture["attempt"]
    if (
        attempt["start_kind"] != "level_start"
        or attempt["input_source"] != "replay"
        or attempt["input_delivery"]["driver"] != "owned-pre-command"
        or capture["environment"]["clocks"]["clock_policy"] != "fixed-scheduler-240"
    ):
        raise ValueError("Probe trials require full-start owned-pre-command fixed-scheduler-240 execution")
    for name in (
        "challenge",
        "environment",
        "environment_sha256",
        "collector",
        "state_fields",
        "layer_state_fields",
    ):
        if capture[name] != study["reference"][name]:
            raise ValueError(f"Probe capture identity differs from the study reference: {name}")
    replay = point_replay(study, trial["point_id"])
    if attempt["planned_inputs"] != replay["inputs"]:
        raise ValueError("Capture planned_inputs differs from the complete generated point replay")
    expected_replay_hash = hashlib.sha256(replay_bytes(replay)).hexdigest()
    if attempt["replay_sha256"] != expected_replay_hash:
        raise ValueError("Capture replay_sha256 differs from the generated replay file bytes")
    requested = [row for row in attempt["inputs"] if row["phase"] == "requested"]
    if any(row["in_command"] is not True for row in requested):
        raise ValueError("Owned probe requests must be delivered within command processing")
    terminal = attempt["terminal"]
    if terminal["outcome"] == "completed":
        if any(row["command_index"] > terminal["command_index"] for row in replay["inputs"]):
            raise ValueError("Completed probe cannot leave an unexecuted planned input tail")
        if [{name: row[name] for name in _INPUT_FIELDS} for row in requested] != replay["inputs"]:
            raise ValueError("Completed probe must contain every planned requested input")


def inspect_native_probe_results(study_path: str | Path, results_path: str | Path) -> dict:
    """Normalize only supplied trials; absent trials remain unrecorded upstream.

    Manifest shape, plan identity and reused evidence fail the complete import.
    File/collector/terminal rejections remain explicit per-trial rejections;
    runner errors are preserved separately and never become native deaths.
    """
    study_document, study_digest, ordinary_study, study_signature = _stable_json(study_path)
    study = load_probe_study(ordinary_study)
    if study_document != study or _signature(ordinary_study) != study_signature:
        raise ValueError("Probe study changed during validation")
    results, results_digest, ordinary_results, results_signature = _stable_json(results_path)
    rows = _validate_results(results, study, ordinary_results.parent)
    trials = {row["id"]: row for row in study["trials"]}
    seen_execution_ids = set()
    observations = []
    for row in rows:
        trial_id = row["trial_id"]
        if "error" in row:
            observations.append(_empty_observation(trial_id, "runner_error", row["error"]))
            continue
        observation = _empty_observation(trial_id, "rejected")
        try:
            capture, digest = _read_capture(
                _relative_capture_path(ordinary_results.parent, row["capture_path"]),
                row["capture_sha256"],
            )
        except (OSError, ValueError) as error:
            observation["error"] = str(error)[:MAX_ERROR_CHARS]
        else:
            execution_id = capture["attempt"]["id"]
            if execution_id in seen_execution_ids:
                raise ValueError("Independent probe trials cannot reuse a native attempt.id")
            seen_execution_ids.add(execution_id)
            try:
                _validate_trial_capture(capture, study, trials[trial_id])
            except ValueError as error:
                observation["error"] = str(error)[:MAX_ERROR_CHARS]
            else:
                terminal = capture["attempt"]["terminal"]
                observation.update(
                    outcome=terminal["outcome"],
                    terminal_state_sha256=canonical_sha256(terminal["state"]),
                    native_terminal_event=terminal["event"],
                    command_index=terminal["command_index"],
                    evidence_sha256=digest,
                    evidence_origin=capture["provenance"]["origin"],
                    execution_id=execution_id,
                )
        observations.append(observation)
    final_study, final_study_digest, _, _ = _stable_json(ordinary_study)
    final_results, final_results_digest, _, _ = _stable_json(ordinary_results)
    if (
        final_study != study
        or final_study_digest != study_digest
        or final_results != results
        or final_results_digest != results_digest
        or _signature(ordinary_study) != study_signature
        or _signature(ordinary_results) != results_signature
    ):
        raise ValueError("Probe study or results manifest changed during import")
    return {
        "schema_version": 1,
        "kind": "probe_observations",
        "study_sha256": study_sha256(study),
        "origin": "native-capture-files",
        "authentication_status": "not_authenticated",
        "attempts": observations,
    }
