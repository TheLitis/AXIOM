"""Read frozen native probe exchanges without launching an executor.

An exchange consists only of study.json, jobs.json and its scheduled plans.
Byte identity and generated job order are checked independently of any native
execution or scientific qualification. Callers must recheck retained inventories
before and after each external attempt; these checks do not lock the filesystem.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path, PureWindowsPath

from .probeplan import MAX_PROBE_POINTS, point_replay, replay_bytes, study_sha256
from .proberun import (
    _absolute,
    _invalid_constant,
    _json_bytes,
    _ordinary,
    _read_stable,
    _read_study,
    _unique_object,
)
from .validation import _validate_tree, sha256

_PLAN_PATH = re.compile(r"plans/p[0-9]{4}\.json\Z")
_MANIFEST_FIELDS = {
    "kind",
    "schema_version",
    "study_sha256",
    "study_file_sha256",
    "study_path",
    "jobs",
}


def _exchange_directory(value: str | Path) -> Path:
    try:
        text = os.fspath(value)
    except TypeError as exc:
        raise ValueError("Probe exchange directory must be a path") from exc
    if not isinstance(text, str) or not text or "\x00" in text:
        raise ValueError("Probe exchange directory must be a nonempty text path")
    windows = PureWindowsPath(text)
    if ".." in windows.parts or ".." in Path(text).parts:
        raise ValueError("Probe exchange directory must not contain traversal")
    if windows.drive and (not windows.root or windows.drive.startswith("\\") or os.name != "nt"):
        raise ValueError("Probe exchange directory must not use a drive alias or device path")
    if os.name == "nt" and windows.root and not windows.drive:
        raise ValueError("Probe exchange directory must not use a current-drive alias")
    parts = windows.parts[1:] if windows.anchor else windows.parts
    if any(part.endswith((".", " ")) or ":" in part for part in parts):
        raise ValueError("Probe exchange directory must not use path aliases or alternate streams")
    directory = _absolute(text)
    _ordinary(directory, directory=True)
    return directory


def _entries(directory: Path, expected: set[str], *, directories: set[str] = frozenset()) -> None:
    """Check exactly the bounded expected children, without following any entry."""
    _ordinary(directory, directory=True)
    seen: set[str] = set()
    for child in directory.iterdir():
        if child.name not in expected or child.name in seen:
            raise ValueError(f"Unexpected probe exchange entry: {child}")
        _ordinary(child, directory=child.name in directories)
        seen.add(child.name)
    if seen != expected:
        raise ValueError(
            f"Missing probe exchange entries in {directory}: {', '.join(sorted(expected - seen))}"
        )


def _tree(directory: Path, plans: set[str]) -> None:
    _entries(directory, {"jobs.json", "study.json", "plans"}, directories={"plans"})
    _entries(directory / "plans", {Path(path).name for path in plans})


def _manifest(raw: bytes) -> dict:
    try:
        value = json.loads(
            raw.decode("utf-8-sig"), object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Invalid native probe jobs JSON") from exc
    _validate_tree(value)
    if not isinstance(value, dict) or value.keys() != _MANIFEST_FIELDS:
        raise ValueError("Native probe jobs require exact manifest fields")
    return value


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _inventory(value: dict | list) -> list[dict]:
    if isinstance(value, dict):
        if value.keys() != {"study", "manifest", "files"}:
            raise ValueError("Probe exchange inventory object requires study, manifest and files")
        value = value["files"]
    if not isinstance(value, list) or not 2 <= len(value) <= MAX_PROBE_POINTS + 2:
        raise ValueError("Probe exchange inventory must contain bounded file records")
    paths = []
    for record in value:
        if not isinstance(record, dict) or record.keys() != {"relative_path", "sha256"}:
            raise ValueError("Probe exchange inventory requires exact file record fields")
        relative = record["relative_path"]
        if not isinstance(relative, str) or (
            relative not in ("jobs.json", "study.json") and not _PLAN_PATH.fullmatch(relative)
        ):
            raise ValueError("Invalid probe exchange inventory relative path")
        sha256(record["sha256"], "inventory.sha256")
        paths.append(relative)
    if paths[:2] != ["jobs.json", "study.json"] or paths[2:] != sorted(set(paths[2:])):
        raise ValueError("Probe exchange inventory must preserve unique canonical file order")
    if len(set(paths)) != len(paths):
        raise ValueError("Duplicate probe exchange inventory file")
    return value


def assert_probe_exchange_unchanged(exchange_directory: str | Path, inventory: dict | list) -> None:
    """Re-read every retained file and exact tree, refusing any changed byte.

    inventory accepts either load_probe_exchange's full result or its files list.
    It is an input-file inventory, not an authenticated native execution record.
    Each file is read twice with ordinary-path and stable descriptor checks. The
    final tree check also rejects added files and directory redirection.
    """
    directory = _exchange_directory(exchange_directory)
    files = _inventory(inventory)
    plans = {row["relative_path"] for row in files[2:]}
    _tree(directory, plans)
    for row in files:
        relative = row["relative_path"]
        if _digest(_read_stable(directory / relative)) != row["sha256"]:
            raise ValueError(f"Probe exchange file changed: {relative}")
    _tree(directory, plans)


def load_probe_exchange(exchange_directory: str | Path) -> dict:
    """Load an exact generated exchange and return only study, manifest, files.

    study is fully reconstructed and validated. manifest must match every frozen
    trial in generated order, including baseline repetitions. Each unique replay
    must match the canonical generated bytes, including the final LF. Invalid
    schedules have no plan or job. Source study whitespace is retained and bound
    by its raw digest separately from its canonical study digest.
    """
    directory = _exchange_directory(exchange_directory)
    _entries(directory, {"jobs.json", "study.json", "plans"}, directories={"plans"})
    study, study_raw = _read_study(directory / "study.json")
    manifest_raw = _read_stable(directory / "jobs.json")
    manifest = _manifest(manifest_raw)
    scheduled = [point for point in study["points"] if point["status"] == "scheduled"]
    plan_paths = {f"plans/{point['id']}.json" for point in scheduled}
    _tree(directory, plan_paths)
    files = [
        {"relative_path": "jobs.json", "sha256": _digest(manifest_raw)},
        {"relative_path": "study.json", "sha256": _digest(study_raw)},
    ]
    generated_hashes = {}
    for point in scheduled:
        relative = f"plans/{point['id']}.json"
        expected = replay_bytes(point_replay(study, point))
        raw = _read_stable(directory / relative)
        digest = _digest(expected)
        if digest != point["replay_file_sha256"]:
            raise ValueError("Generated probe replay differs from its frozen study")
        if raw != expected:
            raise ValueError(f"Probe replay differs from canonical generated bytes: {relative}")
        generated_hashes[point["id"]] = digest
        files.append({"relative_path": relative, "sha256": digest})
    expected_manifest = {
        "kind": "native_probe_jobs",
        "schema_version": 1,
        "study_sha256": study_sha256(study),
        "study_file_sha256": _digest(study_raw),
        "study_path": "study.json",
        "jobs": [
            {
                "trial_id": trial["id"],
                "point_id": trial["point_id"],
                "repetition": trial["repetition"],
                "replay_path": f"plans/{trial['point_id']}.json",
                "replay_file_sha256": generated_hashes[trial["point_id"]],
                "clock_policy": "fixed-scheduler-240",
                "input_driver": "owned-pre-command",
                "start_kind": "level_start",
            }
            for trial in study["trials"]
        ],
    }
    # Serialized comparison distinguishes JSON booleans/floats from frozen ints.
    if _json_bytes(manifest) != _json_bytes(expected_manifest):
        raise ValueError("Native probe jobs differ from the reconstructed frozen study")
    result = {"study": study, "manifest": manifest, "files": files}
    assert_probe_exchange_unchanged(directory, files)
    return result
