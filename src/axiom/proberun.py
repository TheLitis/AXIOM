"""Freeze probe jobs and exercise their contract with an explicit synthetic backend.

The materialized replay files are native adapter inputs, not engine executions.
Synthetic terminal witnesses are a separate format and cannot become captures or
establish physical feasibility, input equivalence, or human timing tolerances.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Callable, Literal, Protocol, TypedDict
from uuid import uuid4

from .probeplan import point_replay, replay_bytes, study_sha256, validate_probe_study
from .validation import MAX_JSON_BYTES, string

REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
MAX_ERROR_CHARACTERS = 1024


class SyntheticTerminalWitness(TypedDict):
    kind: Literal["synthetic-full-run-terminal"]
    start_kind: Literal["level_start"]
    event: Literal["completed", "died"]
    replay_file_sha256: str
    environment_sha256: str
    execution_id: str


class ProbeBackendResult(TypedDict):
    outcome: Literal["completed", "died", "runner_error"]
    terminal_witness: SyntheticTerminalWitness | None
    error: str | None


class ProbeBackend(Protocol):
    """Synchronous backend; a backend must report its own deadline failures.

    Only synthetic implementations are admitted in this version. External native
    execution requires a future capture-qualified adapter, not this witness type.
    """

    id: str
    origin: Literal["synthetic"]

    def run(self, trial: dict, replay_plan: dict) -> ProbeBackendResult: ...


def _absolute(path: str | Path) -> Path:
    # Keep the lexical path so a redirected ancestor cannot disappear in resolve().
    return Path(os.path.abspath(os.fspath(path)))


def _ordinary(path: Path, *, directory: bool | None = None, missing_ok: bool = False) -> None:
    for item in reversed((path, *path.parents)):
        try:
            info = item.lstat()
        except FileNotFoundError:
            if missing_ok:
                continue
            raise ValueError(f"Missing probe path: {item}") from None
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & REPARSE_POINT:
            raise ValueError(f"Redirected probe path: {item}")
        if item != path and not stat.S_ISDIR(info.st_mode):
            raise ValueError(f"Probe path ancestor is not a directory: {item}")
        if item == path and directory is not None:
            valid = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
            if not valid:
                raise ValueError(f"Probe path has the wrong file type: {item}")


def _fresh(path: Path) -> None:
    _ordinary(path, missing_ok=True)
    _ordinary(path.parent, directory=True)
    try:
        path.lstat()
    except FileNotFoundError:
        return
    raise ValueError(f"Probe output already exists: {path}")


def _fingerprint(info: os.stat_result) -> tuple:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, getattr(info, "st_birthtime_ns", None)


def _read_stable(path: Path) -> bytes:
    _ordinary(path, directory=False)
    before = path.lstat()
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise ValueError("Probe study exceeds the 16 MiB JSON limit")
        stream.seek(0)
        again = stream.read(MAX_JSON_BYTES + 1)
        after_read = os.fstat(stream.fileno())
    _ordinary(path, directory=False)
    after = path.lstat()
    if raw != again or len({_fingerprint(row) for row in (before, opened, after_read, after)}) != 1:
        raise ValueError("Probe study changed during reading")
    return raw


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate probe study field: {key}")
        result[key] = value
    return result


def _invalid_constant(_: str) -> None:
    raise ValueError("Probe study JSON contains a nonfinite number")


def _read_study(path: Path) -> tuple[dict, bytes]:
    raw = _read_stable(path)
    try:
        data = json.loads(
            raw.decode("utf-8-sig"), object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Invalid probe study JSON") from exc
    return validate_probe_study(data), raw


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode(
        "utf-8"
    )


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_fresh_atomic(path: Path, data: bytes) -> None:
    """Publish only a complete file, using a hard link that cannot replace a target.

    A filesystem without atomic hard-link creation is refused. No rename fallback
    is used because POSIX rename can overwrite an existing destination.
    """
    _fresh(path)
    descriptor, name = tempfile.mkstemp(prefix=".axiom-probe-", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _ordinary(temporary, directory=False)
        _fresh(path)
        os.link(temporary, path, follow_symlinks=False)
    finally:
        temporary.unlink(missing_ok=True)


def write_probe_json(path: str | Path, value: dict) -> None:
    """Publish fresh JSON atomically, refusing redirected paths or replacement."""
    if not isinstance(value, dict):
        raise ValueError("Probe JSON must be an object")
    try:
        data = _json_bytes(value)
    except (UnicodeError, TypeError, ValueError, RecursionError) as exc:
        raise ValueError("Probe output must contain finite UTF-8 JSON values") from exc
    if len(data) > MAX_JSON_BYTES:
        raise ValueError("Probe output exceeds the 16 MiB JSON limit")
    _write_fresh_atomic(_absolute(path), data)


def prepare_probe_directory(path: str | Path) -> Path:
    """Reserve a fresh ordinary directory whose parent already exists."""
    out = _absolute(path)
    _fresh(out)
    try:
        out.mkdir()
    except FileExistsError as exc:
        raise ValueError("Probe output directory already exists") from exc
    _ordinary(out, directory=True)
    return out


def materialize_probe_study(study_path: str | Path, output_directory: str | Path) -> dict:
    """Create a fresh job bundle, without launching any backend or game.

    study.json preserves the exact input bytes. Its byte digest is distinct from
    the canonical study digest. jobs.json is written last and is the completion
    marker; a partial directory after an I/O failure is never resumed implicitly.
    The output parent must already be an ordinary directory.
    """
    source, out = _absolute(study_path), _absolute(output_directory)
    if source == out or out in source.parents or source in out.parents:
        raise ValueError("Probe output must not overlap the study source")
    study, raw = _read_study(source)
    _fresh(out)
    plans = {}
    for point in study["points"]:
        if point["status"] != "scheduled":
            continue
        data = replay_bytes(point_replay(study, point))
        if _hash(data) != point["replay_file_sha256"]:
            raise ValueError("Probe point replay hash differs from its frozen study")
        plans[point["id"]] = data
    jobs = [
        {
            "trial_id": trial["id"],
            "point_id": trial["point_id"],
            "repetition": trial["repetition"],
            "replay_path": f"plans/{trial['point_id']}.json",
            "replay_file_sha256": _hash(plans[trial["point_id"]]),
            "clock_policy": "fixed-scheduler-240",
            "input_driver": "owned-pre-command",
            "start_kind": "level_start",
        }
        for trial in study["trials"]
    ]
    manifest = {
        "schema_version": 1,
        "kind": "native_probe_jobs",
        "study_sha256": study_sha256(study),
        "study_file_sha256": _hash(raw),
        "study_path": "study.json",
        "jobs": jobs,
    }
    if _read_stable(source) != raw:
        raise ValueError("Probe study source changed before materialization")
    prepare_probe_directory(out)
    (out / "plans").mkdir()
    _write_fresh_atomic(out / "study.json", raw)
    for point_id, data in plans.items():
        _write_fresh_atomic(out / "plans" / f"{point_id}.json", data)
    write_probe_json(out / "jobs.json", manifest)
    return manifest


def _backend_text(value, name: str) -> str:
    text = string(value, name)
    try:
        text.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError(f"{name} must contain valid UTF-8 text") from exc
    return text


def _backend_identity(backend: ProbeBackend) -> dict:
    if getattr(backend, "origin", None) != "synthetic":
        raise ValueError("This runner admits only explicit synthetic backends")
    backend_id = _backend_text(getattr(backend, "id", None), "backend.id")
    if not callable(getattr(backend, "run", None)):
        raise ValueError("Probe backend must supply run(trial, replay_plan)")
    return {"id": backend_id, "origin": "synthetic"}


def _validated_result(result, point: dict, study: dict, seen: set[str]) -> ProbeBackendResult:
    if not isinstance(result, dict) or set(result) != {"outcome", "terminal_witness", "error"}:
        raise ValueError("Malformed probe backend result fields")
    outcome, witness, error = result["outcome"], result["terminal_witness"], result["error"]
    if outcome not in ("completed", "died", "runner_error"):
        raise ValueError("Unknown probe backend outcome")
    if outcome == "runner_error":
        if witness is not None:
            raise ValueError("Runner error must not carry a terminal witness")
        _backend_text(error, "backend.error")
        return {"outcome": "runner_error", "terminal_witness": None, "error": error}
    fields = {"kind", "start_kind", "event", "replay_file_sha256", "environment_sha256", "execution_id"}
    if not isinstance(witness, dict) or set(witness) != fields or error is not None:
        raise ValueError("A synthetic terminal requires an exact witness and no runner error")
    if (
        witness["kind"] != "synthetic-full-run-terminal"
        or witness["start_kind"] != "level_start"
        or witness["event"] != outcome
        or witness["replay_file_sha256"] != point["replay_file_sha256"]
        or witness["environment_sha256"] != study["reference"]["environment_sha256"]
    ):
        raise ValueError("Synthetic terminal witness does not match the frozen replay and environment")
    execution_id = _backend_text(witness["execution_id"], "backend.execution_id")
    if execution_id in seen:
        raise ValueError("Duplicate synthetic terminal execution identity")
    seen.add(execution_id)
    return deepcopy(result)


def _runner_error(exc: Exception) -> ProbeBackendResult:
    try:
        detail = str(exc)
    except Exception:
        detail = "Backend exception message unavailable"
    detail = f"{type(exc).__name__}: {detail}".encode("utf-8", errors="replace").decode("utf-8")
    return {
        "outcome": "runner_error",
        "terminal_witness": None,
        "error": detail[:MAX_ERROR_CHARACTERS],
    }


def run_probe_backend(study_path: str | Path, backend: ProbeBackend, results_path: str | Path) -> dict:
    """Run each frozen scheduled trial once in order, publishing a fresh result file.

    Backend exceptions, deadline exceptions, malformed outputs and repeated witness
    identities become runner_error records. They never become deaths. Trial and
    replay arguments are deep copies; this synchronous interface has no implicit
    retries, parallelism, resume, process launch or input injection.
    """
    source, out = _absolute(study_path), _absolute(results_path)
    if source == out or out in source.parents or source in out.parents:
        raise ValueError("Probe results must not overlap the study source")
    study, raw = _read_study(source)
    identity = _backend_identity(backend)
    _fresh(out)
    points = {point["id"]: point for point in study["points"]}
    plans = {
        point_id: point_replay(study, point)
        for point_id, point in points.items()
        if point["status"] == "scheduled"
    }
    seen: set[str] = set()
    attempts = []
    for trial in study["trials"]:
        point = points[trial["point_id"]]
        try:
            response = backend.run(deepcopy(trial), deepcopy(plans[point["id"]]))
            result = _validated_result(response, point, study, seen)
        except Exception as exc:
            result = _runner_error(exc)
        attempts.append({"trial_id": trial["id"], **result})
    result = {
        "schema_version": 1,
        "kind": "probe_backend_results",
        "study_sha256": study_sha256(study),
        "backend": identity,
        "attempts": attempts,
    }
    if _read_stable(source) != raw:
        raise ValueError("Probe study source changed during execution")
    write_probe_json(out, result)
    return result


class SyntheticProbeBackend:
    """Deterministic controlled region over frozen integer command offsets.

    region_function receives an immutable tuple in declared axis order and must
    return a bool. It may encode disconnected or coupled regions. The predicate
    is supplied synthetic truth, not Geometry Dash physics or human feasibility.
    """

    origin: Literal["synthetic"] = "synthetic"

    def __init__(
        self,
        study: dict,
        region_function: Callable[[tuple[int, ...]], bool],
        *,
        backend_id: str = "synthetic-grid-v1",
    ) -> None:
        self.id = _backend_text(backend_id, "backend.id")
        if not callable(region_function):
            raise ValueError("Synthetic region_function must be callable")
        frozen = deepcopy(validate_probe_study(deepcopy(study)))
        self._points = {point["id"]: point for point in frozen["points"]}
        self._trials = {trial["id"]: trial for trial in frozen["trials"]}
        self._environment_sha256 = frozen["reference"]["environment_sha256"]
        self._region_function = region_function

    def run(self, trial: dict, replay_plan: dict) -> ProbeBackendResult:
        if not isinstance(trial, dict) or self._trials.get(trial.get("id")) != trial:
            raise ValueError("Synthetic trial differs from its frozen study")
        point = self._points[trial["point_id"]]
        if _hash(replay_bytes(replay_plan)) != point["replay_file_sha256"]:
            raise ValueError("Synthetic replay differs from its frozen point")
        accepted = self._region_function(tuple(point["offsets_commands"]))
        if not isinstance(accepted, bool):
            raise ValueError("Synthetic region_function must return a bool")
        outcome = "completed" if accepted else "died"
        return {
            "outcome": outcome,
            "terminal_witness": {
                "kind": "synthetic-full-run-terminal",
                "start_kind": "level_start",
                "event": outcome,
                "replay_file_sha256": point["replay_file_sha256"],
                "environment_sha256": self._environment_sha256,
                "execution_id": f"synthetic-{uuid4().hex}",
            },
            "error": None,
        }
