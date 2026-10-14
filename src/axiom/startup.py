"""Bounded, byte-preserving startup diagnostics without running the game.

Log markers are observations, not authenticated process events, native terminal
results, Windows input qualification, or evidence that a missing stage did not run.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath

SCHEMA_VERSION = 1
MAX_LOG_FILES = 64
MAX_DIRECTORY_ENTRIES = 256
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_MARKER_OBSERVATIONS = 2048
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
SCOPE = "ordinary-immediate-runtime-startup-text-and-declared-runner-output-only"
NORMALIZATION = "utf8-or-bom-utf16-ansi-csi-crlf-for-matching-only-v1"
LIMITS = {
    "log_files": MAX_LOG_FILES,
    "directory_entries_per_group": MAX_DIRECTORY_ENTRIES,
    "file_bytes": MAX_FILE_BYTES,
    "total_bytes": MAX_TOTAL_BYTES,
    "json_bytes": MAX_JSON_BYTES,
}
GROUPS = (("loader_log", "geode/logs"), ("crash_log", "geode/crashlogs"))
STATES = {
    "captured",
    "missing",
    "rejected_path",
    "unreadable",
    "unstable",
    "too_large",
    "total_byte_limit",
    "file_count_limit",
    "out_of_scope",
}
ERROR_STATES = STATES - {"captured", "missing", "out_of_scope"}
ANSI_CSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
AXIOM_LOGGERS = {"AXIOM", "AXIOM Native C>", "AXIOM Native Capture", "AXIOM Native Capture>"}
LOG_LINE = re.compile(
    r"^(?:\d{2}:\d{2}:\d{2}(?:\.\d+)?\s+)?"
    r"(?:TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL)\s+"
    r"\[[^\]\r\n]{1,80}\]\s+"
    r"\[(Geode|AXIOM|AXIOM Native C>|AXIOM Native Capture|AXIOM Native Capture>)\]:\s+(.*)$"
)
MARKERS = {
    "loader_entry": ("Geode", re.compile(r"Entry took \d+(?:\.\d+)?s$")),
    "adapter_loaded": ("AXIOM", re.compile(r"AXIOM M1 adapter loaded;")),
    "adapter_refused": ("AXIOM", re.compile(r"AXIOM (?:delivery/watch|clock) experiment refused:")),
    "app_init_enter": ("AXIOM", re.compile(r"AXIOM sandbox app init entered$")),
    "app_init_return_true": ("AXIOM", re.compile(r"AXIOM sandbox app init returned: true$")),
    "app_init_return_false": ("AXIOM", re.compile(r"AXIOM sandbox app init returned: false$")),
    "menu_init_enter": ("AXIOM", re.compile(r"AXIOM sandbox menu init entered$")),
    "menu_init_return_true": ("AXIOM", re.compile(r"AXIOM sandbox menu init returned: true$")),
    "menu_init_return_false": ("AXIOM", re.compile(r"AXIOM sandbox menu init returned: false$")),
    "save_isolation": ("AXIOM", re.compile(r"AXIOM sandbox isolated writable path:")),
    "manual_ready": ("AXIOM", re.compile(r"AXIOM sandbox manual test ready;")),
    "fixture_launch_request": ("AXIOM", re.compile(r"AXIOM sandbox fixture launched;")),
    "capture_start": (
        "AXIOM",
        re.compile(r"AXIOM local capture active; command-call clock, selected-state only$"),
    ),
    "capture_export": ("AXIOM", re.compile(r"AXIOM native capture exported locally:")),
}


class _ReadFailure(ValueError):
    def __init__(self, state: str):
        super().__init__(state)
        self.state = state


def _absolute(path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _ordinary(path: Path, *, directory: bool | None = None, missing_ok: bool = False) -> None:
    """Inspect lexical ancestors; resolve() would hide a redirected ancestor."""
    for item in reversed((path, *path.parents)):
        try:
            info = item.lstat()
        except FileNotFoundError:
            if missing_ok:
                continue
            raise _ReadFailure("missing") from None
        except OSError:
            raise _ReadFailure("unreadable") from None
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & REPARSE_POINT:
            raise _ReadFailure("rejected_path")
        if item != path and not stat.S_ISDIR(info.st_mode):
            raise _ReadFailure("rejected_path")
        if item == path and directory is not None:
            valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
            if not valid:
                raise _ReadFailure("rejected_path")


def _fingerprint(info) -> tuple:
    # Windows stat/lstat and fstat disagree on deprecated ctime semantics in
    # some Python versions. Birth time is comparable when both expose it.
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, getattr(info, "st_birthtime_ns", None)


def _read_once(stream, maximum: int) -> bytes:
    return stream.read(maximum + 1)


def _read_stable(path: Path, maximum: int) -> bytes:
    _ordinary(path, directory=False)
    try:
        before = path.lstat()
        if before.st_size > maximum:
            raise _ReadFailure("too_large")
        with path.open("rb") as stream:
            if _fingerprint(os.fstat(stream.fileno())) != _fingerprint(before):
                raise _ReadFailure("unstable")
            data = _read_once(stream, maximum)
            if len(data) > maximum:
                raise _ReadFailure("too_large")
            stream.seek(0)
            if _read_once(stream, maximum) != data:
                raise _ReadFailure("unstable")
            if _fingerprint(os.fstat(stream.fileno())) != _fingerprint(before):
                raise _ReadFailure("unstable")
        _ordinary(path, directory=False)
        if _fingerprint(path.lstat()) != _fingerprint(before) or len(data) != before.st_size:
            raise _ReadFailure("unstable")
        return data
    except _ReadFailure:
        raise
    except FileNotFoundError:
        raise _ReadFailure("unstable") from None
    except OSError:
        raise _ReadFailure("unreadable") from None


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_fresh(path: Path, data: bytes) -> None:
    _ordinary(path.parent, directory=True)
    _ordinary(path, directory=False, missing_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")


def _json_object(data: bytes) -> dict:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate startup JSON field")
            value[key] = item
        return value

    def invalid_constant(_):
        raise ValueError("Nonfinite startup JSON number")

    try:
        value = json.loads(
            data.decode("utf-8-sig"), object_pairs_hook=unique, parse_constant=invalid_constant
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Invalid startup JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("Startup JSON must be an object")
    return value


def _fields(value, names: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != names:
        raise ValueError(f"Invalid {label} fields")
    return value


def _integer(value, maximum: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise ValueError(f"Invalid {label}")
    return value


def _string(value, maximum: int, label: str) -> str:
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f"Invalid {label}")
    return value


def _sha(value) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Invalid startup SHA-256")
    return value


def _time(value, label: str) -> datetime:
    _string(value, 64, label)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|\+00:00)", value) is None:
        raise ValueError(f"{label} must declare a bounded UTC timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid {label}") from exc
    if result.tzinfo is None or result.utcoffset().total_seconds() != 0:
        raise ValueError(f"{label} must declare UTC")
    return result


def _time_order(value: str, label: str) -> tuple[int, int]:
    parsed = _time(value, label)
    seconds = parsed.replace(microsecond=0) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    fraction = re.search(r"\.(\d{1,9})(?:Z|\+00:00)$", value)
    nanoseconds = int(fraction.group(1).ljust(9, "0")) if fraction else 0
    return seconds.days * 86400 + seconds.seconds, nanoseconds


def _same_declared_path(left: str, right: str) -> bool:
    # Archive inspection does not require a live source path. Windows origins
    # remain comparable when a frozen bundle is inspected on another OS.
    if re.match(r"^[A-Za-z]:[\\/]", left) or left.startswith("\\\\"):
        return PureWindowsPath(left) == PureWindowsPath(right)
    return left == right


def _safe_leaf(name: str) -> bool:
    return (
        bool(name)
        and name not in {".", ".."}
        and not name.endswith((".", " "))
        and not any(ord(char) < 32 or char in '\\/:<>"|?*' for char in name)
        and name.split(".", 1)[0].upper()
        not in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }
    )


def _allowed_runtime(relative: str, category: str) -> bool:
    if PurePosixPath(relative).as_posix() != relative or "\\" in relative:
        return False
    parts = PurePosixPath(relative).parts
    if category == "early_error":
        return relative == "_geode_early_error.txt"
    if len(parts) != 3 or not _safe_leaf(parts[-1]):
        return False
    if category == "loader_log":
        return parts[:2] == ("geode", "logs") and parts[-1].lower().endswith(".log")
    return (
        category == "crash_log"
        and parts[:2] == ("geode", "crashlogs")
        and PurePosixPath(parts[-1]).suffix.lower() in {".txt", ".log"}
    )


def _record(scope: str, category: str, relative: str, state: str, data: bytes | None = None) -> dict:
    return {
        "scope": scope,
        "category": category,
        "relative_path": relative,
        "state": state,
        "size_bytes": len(data) if data is not None else None,
        "sha256": _hash(data) if data is not None else None,
        "error": state if state in ERROR_STATES else None,
    }


def _inventory(runtime: Path, *, initial_bytes: int = 0) -> tuple[dict, dict[str, bytes]]:
    _ordinary(runtime, directory=True)
    groups = []
    records = []
    blobs = {}
    total = initial_bytes
    eligible_count = 0

    def read(category, relative):
        nonlocal total, eligible_count
        try:
            _ordinary(runtime / relative, directory=False)
        except _ReadFailure as exc:
            records.append(_record("runtime", category, relative, exc.state))
            return
        eligible_count += 1
        if eligible_count > MAX_LOG_FILES:
            records.append(_record("runtime", category, relative, "file_count_limit"))
            return
        if total >= MAX_TOTAL_BYTES:
            records.append(_record("runtime", category, relative, "total_byte_limit"))
            return
        maximum = min(MAX_FILE_BYTES, MAX_TOTAL_BYTES - total)
        try:
            data = _read_stable(runtime / relative, maximum)
        except _ReadFailure as exc:
            state = "total_byte_limit" if exc.state == "too_large" and maximum < MAX_FILE_BYTES else exc.state
            records.append(_record("runtime", category, relative, state))
            return
        total += len(data)
        blobs[relative] = data
        records.append(_record("runtime", category, relative, "captured", data))

    for category, relative in GROUPS:
        path = runtime / relative
        group = {"category": category, "relative_directory": relative, "state": "present", "entries_seen": 0}
        try:
            _ordinary(path, directory=True)
            names = []
            with os.scandir(path) as entries:
                for entry in entries:
                    group["entries_seen"] += 1
                    if group["entries_seen"] > MAX_DIRECTORY_ENTRIES:
                        group["state"] = "directory_entry_limit"
                        break
                    names.append(entry.name)
            for name in sorted(names):
                source = relative + "/" + name
                if not _allowed_runtime(source, category):
                    # Names only: out-of-scope files/directories are not opened.
                    records.append(_record("runtime", category, source, "out_of_scope"))
                else:
                    read(category, source)
        except _ReadFailure as exc:
            group["state"] = exc.state
        except OSError:
            group["state"] = "unreadable"
        groups.append(group)
    read("early_error", "_geode_early_error.txt")
    complete = all(group["state"] in {"present", "missing"} for group in groups) and not any(
        record["state"] in ERROR_STATES for record in records
    )
    inventory = {
        "kind": "startup_log_inventory",
        "schema_version": SCHEMA_VERSION,
        "runtime_directory": str(runtime),
        "created_at_utc": _utc_now(),
        "scope": SCOPE,
        "limits": LIMITS,
        "groups": groups,
        "files": records,
        "complete": complete,
    }
    return inventory, blobs


def snapshot_startup_logs(runtime_directory, output_path) -> dict:
    """Write a fresh bounded prelaunch inventory without copying or modifying logs."""
    inventory, _ = _inventory(_absolute(runtime_directory))
    data = _json_bytes(inventory)
    if len(data) > MAX_JSON_BYTES:
        raise ValueError("Startup inventory JSON exceeds bound")
    _write_fresh(_absolute(output_path), data)
    return inventory


def _validate_manifest(data: dict, runtime: str) -> None:
    if data.get("kind") != "native_windows_input_observation":
        raise ValueError("Startup evidence requires a native Windows observation manifest")
    declared = _string(data.get("runtime_directory"), 4096, "manifest runtime_directory")
    if not _same_declared_path(declared, runtime):
        raise ValueError("Observation manifest names a different runtime directory")
    for name in ("started_at_utc", "finished_at_utc", "process_started_at_utc"):
        if data.get(name) is not None:
            _time(data[name], name)
    if data.get("process_id") is not None:
        if not _integer(data["process_id"], 2**32 - 1, "process_id"):
            raise ValueError("process_id must be positive")
    if data.get("process_exit_code") is not None:
        # Historical .NET ExitCode may be signed; preserve the raw value in the
        # frozen manifest and expose its uint32 interpretation separately.
        code = data["process_exit_code"]
        if isinstance(code, bool) or not isinstance(code, int) or not -(2**31) <= code <= 2**32 - 1:
            raise ValueError("Invalid process_exit_code")
    if "timeout_reached" in data and not isinstance(data["timeout_reached"], bool):
        raise ValueError("timeout_reached must be boolean")
    if data.get("error") is not None:
        _string(data["error"], 16384, "manifest error")
    if "cleanup_errors" in data:
        errors = data["cleanup_errors"]
        if not isinstance(errors, list) or len(errors) > 64:
            raise ValueError("Invalid cleanup_errors")
        for error in errors:
            _string(error, 16384, "cleanup error")
    if data.get("process_cleanup") is not None:
        cleanup = _fields(
            data["process_cleanup"],
            {"exit_observed_before_cleanup", "termination_requested", "natural_exit_code"},
            "process_cleanup",
        )
        for name in ("exit_observed_before_cleanup", "termination_requested"):
            if not isinstance(cleanup[name], bool):
                raise ValueError(f"{name} must be boolean")
        if cleanup["natural_exit_code"] is not None:
            code = cleanup["natural_exit_code"]
            if isinstance(code, bool) or not isinstance(code, int) or not -(2**31) <= code <= 2**32 - 1:
                raise ValueError("Invalid natural_exit_code")


def _validate_inventory(data: dict) -> None:
    _fields(
        data,
        {
            "kind",
            "schema_version",
            "runtime_directory",
            "created_at_utc",
            "scope",
            "limits",
            "groups",
            "files",
            "complete",
        },
        "startup inventory",
    )
    if (
        data["kind"] != "startup_log_inventory"
        or type(data["schema_version"]) is not int
        or data["schema_version"] != 1
    ):
        raise ValueError("Unsupported startup inventory kind/schema")
    _string(data["runtime_directory"], 4096, "inventory runtime_directory")
    _time(data["created_at_utc"], "inventory created_at_utc")
    if data["scope"] != SCOPE or data["limits"] != LIMITS:
        raise ValueError("Unsupported startup inventory scope/limits")
    _validate_groups(data["groups"])
    _validate_records(data["files"], bundle=False)
    expected = all(group["state"] in {"present", "missing"} for group in data["groups"]) and not any(
        record["state"] in ERROR_STATES for record in data["files"]
    )
    if not isinstance(data["complete"], bool) or data["complete"] != expected:
        raise ValueError("Inconsistent startup inventory completeness")


def _validate_groups(groups) -> None:
    if not isinstance(groups, list) or len(groups) != len(GROUPS):
        raise ValueError("Invalid startup groups")
    for group, (category, relative) in zip(groups, GROUPS, strict=True):
        _fields(group, {"category", "relative_directory", "state", "entries_seen"}, "startup group")
        if group["category"] != category or group["relative_directory"] != relative:
            raise ValueError("Invalid startup group identity")
        _string(group["state"], 64, "startup group state")
        if group["state"] not in {
            "present",
            "missing",
            "rejected_path",
            "unreadable",
            "directory_entry_limit",
        }:
            raise ValueError("Invalid startup group state")
        _integer(group["entries_seen"], MAX_DIRECTORY_ENTRIES + 1, "group entries_seen")


def _validate_records(records, *, bundle: bool) -> None:
    maximum_records = 2 * MAX_DIRECTORY_ENTRIES + (MAX_LOG_FILES + 3 if bundle else 1)
    if not isinstance(records, list) or len(records) > maximum_records:
        raise ValueError("Startup file count exceeds the bounded inventory")
    seen = set()
    captured_count = 0
    total = 0
    for record in records:
        fields = {"scope", "category", "relative_path", "state", "size_bytes", "sha256", "error"}
        if bundle:
            fields |= {"retained_path", "baseline_state"}
        _fields(record, fields, "startup file record")
        relative = _string(record["relative_path"], 1024, "startup relative path")
        _string(record["scope"], 64, "startup record scope")
        _string(record["category"], 64, "startup record category")
        _string(record["state"], 64, "startup record state")
        identity = record["scope"], relative
        if identity in seen:
            raise ValueError("Duplicate startup source path")
        seen.add(identity)
        if record["state"] not in STATES:
            raise ValueError("Invalid startup file state")
        if record["scope"] == "runtime":
            valid = _allowed_runtime(relative, record["category"])
            # Skipped entries are names within the two immediate known groups.
            if record["state"] == "out_of_scope":
                valid = any(
                    relative.startswith(directory + "/")
                    and "/" not in relative[len(directory) + 1 :]
                    and "\\" not in relative
                    and _safe_leaf(relative[len(directory) + 1 :])
                    for _, directory in GROUPS
                )
            if not valid:
                raise ValueError("Startup runtime path escapes the allowed scope")
        elif bundle and record["scope"] == "observation":
            if record["category"] != "runner_output" or relative not in {"stdout.txt", "stderr.txt"}:
                raise ValueError("Invalid startup observation output path")
        else:
            raise ValueError("Invalid startup file scope")
        if record["state"] == "captured":
            captured_count += 1
            total += _integer(record["size_bytes"], MAX_FILE_BYTES, "startup file size")
            _sha(record["sha256"])
            if record["error"] is not None:
                raise ValueError("Captured startup file cannot declare a read error")
        elif record["size_bytes"] is not None or record["sha256"] is not None:
            raise ValueError("Uncaptured startup file cannot declare byte identity")
        elif record["error"] != (record["state"] if record["state"] in ERROR_STATES else None):
            raise ValueError("Inconsistent startup file error")
        if bundle:
            _string(record["baseline_state"], 64, "startup baseline state")
            if record["baseline_state"] not in {
                "not_supplied",
                "not_applicable",
                "new",
                "unchanged",
                "changed",
                "baseline_uncertain",
                "removed",
            }:
                raise ValueError("Invalid startup baseline state")
            if record["state"] == "captured":
                if (
                    not isinstance(record["retained_path"], str)
                    or re.fullmatch(r"files/\d{4}\.bin", record["retained_path"]) is None
                ):
                    raise ValueError("Retained startup path escapes bundle")
            elif record["retained_path"] is not None:
                raise ValueError("Uncaptured startup file has a retained payload")
    if captured_count > MAX_LOG_FILES + (2 if bundle else 0) or total > MAX_TOTAL_BYTES:
        raise ValueError("Startup captured payload exceeds limits")


def _artifact(original: Path, retained: str, data: bytes) -> dict:
    return {
        "original_path": str(original),
        "retained_path": retained,
        "size_bytes": len(data),
        "sha256": _hash(data),
    }


def collect_startup_evidence(
    runtime_directory, observation_manifest_path, output_directory, baseline_path=None
) -> dict:
    """Freeze bounded startup bytes in a new bundle; never modify old evidence."""
    runtime = _absolute(runtime_directory)
    manifest_path = _absolute(observation_manifest_path)
    out = _absolute(output_directory)
    _ordinary(runtime, directory=True)
    manifest_bytes = _read_stable(manifest_path, MAX_JSON_BYTES)
    manifest = _json_object(manifest_bytes)
    _validate_manifest(manifest, str(runtime))
    baseline = None
    baseline_bytes = None
    if baseline_path is not None:
        baseline_path = _absolute(baseline_path)
        baseline_bytes = _read_stable(baseline_path, MAX_JSON_BYTES)
        baseline = _json_object(baseline_bytes)
        _validate_inventory(baseline)
        if not _same_declared_path(baseline["runtime_directory"], str(runtime)):
            raise ValueError("Startup baseline names a different runtime directory")
    initial = len(manifest_bytes) + len(baseline_bytes or b"")
    if initial > MAX_TOTAL_BYTES:
        raise ValueError("Startup identity JSON exceeds total byte bound")
    inventory, blobs = _inventory(runtime, initial_bytes=initial)
    records = inventory["files"]
    before = {record["relative_path"]: record for record in baseline["files"]} if baseline else {}
    for record in records:
        old = before.get(record["relative_path"])
        if baseline is None:
            state = "not_supplied"
        elif old is None or old["state"] == "missing":
            state = "new" if record["state"] != "missing" else "unchanged"
        elif old["state"] != "captured":
            state = "baseline_uncertain"
        elif record["state"] == "captured":
            state = (
                "unchanged"
                if record["sha256"] == old["sha256"] and record["size_bytes"] == old["size_bytes"]
                else "changed"
            )
        elif record["state"] == "missing":
            state = "removed"
        else:
            state = "baseline_uncertain"
        record["baseline_state"] = state
    present = {record["relative_path"] for record in records}
    group_states = {group["category"]: group["state"] for group in inventory["groups"]}
    for relative, old in before.items():
        if relative not in present and old["state"] == "captured":
            group_state = group_states.get(old["category"], "unreadable")
            known_absent = group_state in {"present", "missing"}
            state = (
                "missing"
                if known_absent
                else "rejected_path"
                if group_state == "rejected_path"
                else "unreadable"
            )
            record = _record("runtime", old["category"], relative, state)
            record["baseline_state"] = "removed" if known_absent else "baseline_uncertain"
            records.append(record)
    total = initial + sum(len(data) for data in blobs.values())
    for relative in ("stdout.txt", "stderr.txt"):
        maximum = min(MAX_FILE_BYTES, max(0, MAX_TOTAL_BYTES - total))
        try:
            data = _read_stable(manifest_path.parent / relative, maximum)
        except _ReadFailure as exc:
            state = "total_byte_limit" if exc.state == "too_large" and maximum < MAX_FILE_BYTES else exc.state
            record = _record("observation", "runner_output", relative, state)
        else:
            total += len(data)
            blobs["observation/" + relative] = data
            record = _record("observation", "runner_output", relative, "captured", data)
        record["baseline_state"] = "not_applicable"
        records.append(record)
    _ordinary(out.parent, directory=True)
    _ordinary(out, directory=True, missing_ok=True)
    out.mkdir()  # Fresh, non-overwriting ownership even after a concurrent create.
    (out / "files").mkdir()
    _write_fresh(out / "frozen-manifest.json", manifest_bytes)
    if baseline_bytes is not None:
        _write_fresh(out / "frozen-baseline.json", baseline_bytes)
    for index, record in enumerate(records):
        record["retained_path"] = None
        if record["state"] == "captured":
            key = (
                record["relative_path"]
                if record["scope"] == "runtime"
                else "observation/" + record["relative_path"]
            )
            retained = f"files/{index:04d}.bin"
            _write_fresh(out / retained, blobs[key])
            record["retained_path"] = retained
    bundle = {
        "kind": "startup_evidence_bundle",
        "schema_version": SCHEMA_VERSION,
        "runtime_directory": str(runtime),
        "created_at_utc": _utc_now(),
        "scope": SCOPE,
        "limits": LIMITS,
        "observation_manifest": _artifact(manifest_path, "frozen-manifest.json", manifest_bytes),
        "baseline_inventory": _artifact(baseline_path, "frozen-baseline.json", baseline_bytes)
        if baseline_bytes is not None
        else None,
        "groups": inventory["groups"],
        "files": records,
        "complete": inventory["complete"] and not any(record["state"] in ERROR_STATES for record in records),
    }
    _validate_records(records, bundle=True)
    bundle_bytes = _json_bytes(bundle)
    if len(bundle_bytes) > MAX_JSON_BYTES:
        raise ValueError("Startup bundle JSON exceeds bound; copied bytes preserved")
    bundle_path = out / "bundle.json"
    _write_fresh(bundle_path, bundle_bytes)
    return {
        "kind": "startup_evidence_collection",
        "schema_version": SCHEMA_VERSION,
        "bundle_path": str(bundle_path),
        "bundle_sha256": _hash(bundle_bytes),
        "status": "collected" if bundle["complete"] else "collected_with_read_failures",
        "complete": bundle["complete"],
        "record_count": len(records),
    }


def _bound_artifact(root: Path, artifact: dict, expected_path: str) -> bytes:
    _fields(artifact, {"original_path", "retained_path", "size_bytes", "sha256"}, "startup artifact")
    _string(artifact["original_path"], 4096, "startup artifact original_path")
    if artifact["retained_path"] != expected_path:
        raise ValueError("Startup identity artifact path escapes bundle")
    _integer(artifact["size_bytes"], MAX_JSON_BYTES, "startup artifact size")
    _sha(artifact["sha256"])
    data = _read_stable(root / expected_path, MAX_JSON_BYTES)
    if len(data) != artifact["size_bytes"] or _hash(data) != artifact["sha256"]:
        raise ValueError("Startup identity artifact hash/size mismatch")
    return data


def _bound_payload(root: Path, record: dict) -> bytes:
    data = _read_stable(root / record["retained_path"], MAX_FILE_BYTES)
    if len(data) != record["size_bytes"] or _hash(data) != record["sha256"]:
        raise ValueError("Retained startup file hash/size mismatch")
    return data


def _lifecycle(manifest: dict) -> dict:
    cleanup = manifest.get("process_cleanup")
    status = "unknown_not_recorded"
    if cleanup is not None:
        if cleanup["exit_observed_before_cleanup"] and cleanup["termination_requested"]:
            status = "inconsistent_runner_exit_declaration"
        elif cleanup["termination_requested"]:
            status = "runner_requested_termination"
        elif cleanup["exit_observed_before_cleanup"]:
            status = "runner_observed_exit_before_cleanup"
        else:
            status = "no_exit_observed_before_cleanup"
    raw_exit = manifest.get("process_exit_code")
    cleanup_exit = cleanup["natural_exit_code"] if cleanup is not None else None
    return {
        "status": status,
        "process_id": manifest.get("process_id"),
        "process_started_at_utc": manifest.get("process_started_at_utc"),
        "process_exit_code_raw": raw_exit,
        "process_exit_code_uint32": raw_exit & (2**32 - 1) if raw_exit is not None else None,
        "natural_exit_code_raw": cleanup_exit,
        "natural_exit_code_uint32": cleanup_exit & (2**32 - 1) if cleanup_exit is not None else None,
        "timeout_reached": manifest.get("timeout_reached"),
        "process_cleanup": cleanup,
        "primary_error": manifest.get("error"),
        "cleanup_errors": manifest.get("cleanup_errors"),
        "cause": "unknown",
        "provenance": "frozen_runner_manifest_declarations_not_independent_exit_authentication",
    }


def _decode(data: bytes) -> str | None:
    encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    try:
        return data.decode(encoding)
    except UnicodeError:
        return None


def inspect_startup_evidence(bundle_path) -> dict:
    """Verify frozen byte identities and report observed stages conservatively."""
    path = _absolute(bundle_path)
    source = _read_stable(path, MAX_JSON_BYTES)
    bundle = _json_object(source)
    _fields(
        bundle,
        {
            "kind",
            "schema_version",
            "runtime_directory",
            "created_at_utc",
            "scope",
            "limits",
            "observation_manifest",
            "baseline_inventory",
            "groups",
            "files",
            "complete",
        },
        "startup bundle",
    )
    if (
        bundle["kind"] != "startup_evidence_bundle"
        or type(bundle["schema_version"]) is not int
        or bundle["schema_version"] != 1
    ):
        raise ValueError("Unsupported startup bundle kind/schema")
    if bundle["scope"] != SCOPE or bundle["limits"] != LIMITS:
        raise ValueError("Unsupported startup bundle scope/limits")
    _string(bundle["runtime_directory"], 4096, "bundle runtime_directory")
    _time(bundle["created_at_utc"], "bundle created_at_utc")
    _validate_groups(bundle["groups"])
    _validate_records(bundle["files"], bundle=True)
    complete = all(group["state"] in {"present", "missing"} for group in bundle["groups"]) and not any(
        record["state"] in ERROR_STATES for record in bundle["files"]
    )
    if not isinstance(bundle["complete"], bool) or bundle["complete"] != complete:
        raise ValueError("Inconsistent startup bundle completeness")
    manifest_bytes = _bound_artifact(path.parent, bundle["observation_manifest"], "frozen-manifest.json")
    manifest = _json_object(manifest_bytes)
    _validate_manifest(manifest, bundle["runtime_directory"])
    baseline = None
    identity_bytes = len(manifest_bytes)
    if bundle["baseline_inventory"] is not None:
        baseline_bytes = _bound_artifact(path.parent, bundle["baseline_inventory"], "frozen-baseline.json")
        identity_bytes += len(baseline_bytes)
        baseline = _json_object(baseline_bytes)
        _validate_inventory(baseline)
        if not _same_declared_path(baseline["runtime_directory"], bundle["runtime_directory"]):
            raise ValueError("Frozen startup baseline names a different runtime")
    if identity_bytes + sum(record["size_bytes"] or 0 for record in bundle["files"]) > MAX_TOTAL_BYTES:
        raise ValueError("Startup bundle exceeds total retained-byte bound")
    before_start = bool(
        baseline is not None
        and baseline["complete"]
        and manifest.get("process_id") is not None
        and manifest.get("process_started_at_utc") is not None
        and _time_order(baseline["created_at_utc"], "baseline creation")
        <= _time_order(manifest["process_started_at_utc"], "process start")
    )
    before = {record["relative_path"]: record for record in baseline["files"]} if baseline else {}
    markers = {
        name: {
            "status": "not_observed_in_retained_diagnostics",
            "observations": [],
            "current_attempt_status": "not_established",
        }
        for name in MARKERS
    }
    payloads = set()
    file_reports = []
    marker_count = 0
    matching_complete = True
    for index, record in enumerate(bundle["files"]):
        current = False
        old = before.get(record["relative_path"])
        if record["scope"] == "observation":
            expected_baseline = "not_applicable"
        elif baseline is None:
            expected_baseline = "not_supplied"
        elif old is None or old["state"] == "missing":
            expected_baseline = "new" if record["state"] != "missing" else "unchanged"
        elif old["state"] != "captured":
            expected_baseline = "baseline_uncertain"
        elif record["state"] == "captured":
            expected_baseline = (
                "unchanged"
                if record["sha256"] == old["sha256"] and record["size_bytes"] == old["size_bytes"]
                else "changed"
            )
        elif record["state"] == "missing":
            expected_baseline = "removed"
        else:
            expected_baseline = "baseline_uncertain"
        if record["baseline_state"] != expected_baseline:
            raise ValueError("Startup baseline classification does not match frozen byte identities")
        file_report = dict(record)
        file_report["text_status"] = "not_retained"
        file_report["current_attempt_attribution"] = "not_established"
        if record["state"] != "captured":
            file_reports.append(file_report)
            continue
        retained = record["retained_path"]
        if retained in payloads:
            raise ValueError("Duplicate retained startup payload path")
        payloads.add(retained)
        data = _bound_payload(path.parent, record)
        # New runtime filenames are only log-level attribution under a complete
        # prelaunch snapshot. Changed same-name rows are not independently bound.
        current = complete and before_start and record["scope"] == "runtime" and expected_baseline == "new"
        if current:
            file_report["current_attempt_attribution"] = "new_since_complete_prelaunch_runtime_inventory"
        text = _decode(data)
        file_report["text_status"] = (
            "decoded_for_matching" if text is not None else "unsupported_text_encoding"
        )
        if text is None and record["category"] in {"loader_log", "runner_output"}:
            matching_complete = False
        if text is not None and record["category"] in {"loader_log", "runner_output"}:
            normalized = ANSI_CSI.sub("", text).replace("\r\n", "\n").replace("\r", "\n")
            for line_number, line in enumerate(normalized.split("\n"), 1):
                matched = LOG_LINE.fullmatch(line)
                if matched is None:
                    continue
                origin, payload = matched.groups()
                for name, (expected_origin, expression) in MARKERS.items():
                    if (
                        origin == "Geode" if expected_origin == "Geode" else origin in AXIOM_LOGGERS
                    ) and expression.match(payload):
                        if marker_count >= MAX_MARKER_OBSERVATIONS:
                            matching_complete = False
                            file_report["text_status"] = "marker_matching_limit"
                            continue
                        marker_count += 1
                        observation = {
                            "record_index": index,
                            "line_number": line_number,
                            "payload": payload[:512],
                            "payload_truncated": len(payload) > 512,
                            "current_attempt_attribution": file_report["current_attempt_attribution"],
                        }
                        markers[name]["observations"].append(observation)
                        markers[name]["status"] = "observed_in_retained_diagnostics"
                        if current:
                            markers[name]["current_attempt_status"] = "observed_in_new_runtime_diagnostics"
        file_reports.append(file_report)
    if not matching_complete:
        for marker in markers.values():
            marker["current_attempt_status"] = "not_established"
    ready = markers["manual_ready"]["current_attempt_status"] == "observed_in_new_runtime_diagnostics"
    # Reject a frozen artifact changed after its first read while another file
    # was being inspected. No source-runtime or personal-profile reread occurs.
    _bound_artifact(path.parent, bundle["observation_manifest"], "frozen-manifest.json")
    if bundle["baseline_inventory"] is not None:
        _bound_artifact(path.parent, bundle["baseline_inventory"], "frozen-baseline.json")
    for record in bundle["files"]:
        if record["state"] == "captured":
            _bound_payload(path.parent, record)
    if _read_stable(path, MAX_JSON_BYTES) != source:
        raise ValueError("Startup bundle changed during inspection")
    return {
        "kind": "startup_diagnostic_report",
        "schema_version": SCHEMA_VERSION,
        "source_path": str(path),
        "source_sha256": _hash(source),
        "complete": complete and matching_complete,
        "marker_matching_complete": matching_complete,
        "runtime_directory": bundle["runtime_directory"],
        "observation_manifest_sha256": _hash(manifest_bytes),
        "attribution": {
            "mode": "prospective_runtime_baseline" if before_start else "retrospective_runtime_unbound",
            "baseline_supplied": baseline is not None,
            "complete_inventory_declared_before_process_start": before_start,
            "authenticated_process_membership": False,
            "changed_log_rows": "not_independently_attributable_to_this_attempt",
        },
        "normalization": NORMALIZATION,
        "files": file_reports,
        "markers": markers,
        "current_attempt_readiness": {
            "status": "observed_in_new_runtime_diagnostics" if ready else "not_established",
            "criterion": "manual_ready_marker_in_new_runtime_file_since_complete_prelaunch_inventory",
            "evidence": [
                item
                for item in markers["manual_ready"]["observations"]
                if item["current_attempt_attribution"] != "not_established"
            ]
            if ready
            else [],
            "authenticated_process_membership": False,
        },
        "lifecycle": _lifecycle(manifest),
        "cause": "unknown",
        "ordinary_input_equivalence": "not_established",
        "hardware_authentication": "not_established",
        "m1_gate": "not_established",
        "limitations": [
            "A missing marker means not observed in retained diagnostics, not proof that a stage did not execute.",
            "Frozen byte/hash consistency does not independently authenticate source process membership or engine execution.",
            "A fixture launch or export log marker is not a verified native capture or completed attempt.",
            "An Attention caption alone cannot distinguish Geode Shift safe mode from Alt+Shift clean mode.",
            "Unsupported encodings and read failures retain explicit diagnostic states without guessed text or causes.",
        ],
    }
