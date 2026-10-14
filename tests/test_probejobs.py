"""Read-only frozen exchange checks; all plans and captures here are synthetic."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_probeplan import probe_spec, reference_capture, save

import axiom.probejobs as reader
from axiom.probejobs import assert_probe_exchange_unchanged, load_probe_exchange
from axiom.probeplan import create_probe_study, point_replay, replay_bytes, study_sha256
from axiom.proberun import REPARSE_POINT, materialize_probe_study
from axiom.validation import MAX_JSON_BYTES


def store(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def exchange(tmp_path, *, invalid=False):
    capture = save(tmp_path, reference_capture(), "reference.json")
    spec = probe_spec()
    if invalid:
        spec["axes"] = [{"event_index": 0, "offsets_commands": [-10, 0, 20]}]
    specification = save(tmp_path, spec, "spec.json")
    study = create_probe_study(capture, specification)
    path = save(tmp_path, study, "source-study.json")
    bundle = tmp_path / "exchange"
    manifest = materialize_probe_study(path, bundle)
    return bundle, study, manifest


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def test_load_returns_only_frozen_study_manifest_and_complete_ordered_byte_inventory(tmp_path):
    bundle, study, manifest = exchange(tmp_path)
    before = {path.relative_to(bundle).as_posix(): path.read_bytes() for path in bundle.rglob("*.json")}
    result = load_probe_exchange(bundle)
    assert set(result) == {"study", "manifest", "files"}
    assert result["study"] == study
    assert result["manifest"] == manifest
    plans = sorted(point["id"] for point in study["points"] if point["status"] == "scheduled")
    paths = ["jobs.json", "study.json", *(f"plans/{point}.json" for point in plans)]
    assert result["files"] == [{"relative_path": path, "sha256": digest(before[path])} for path in paths]
    assert len(result["manifest"]["jobs"]) == len(study["trials"])
    for trial, job in zip(study["trials"], manifest["jobs"], strict=True):
        assert job["trial_id"] == trial["id"]
        assert job["replay_file_sha256"] == digest(replay_bytes(point_replay(study, trial["point_id"])))
    assert assert_probe_exchange_unchanged(bundle, result) is None
    assert assert_probe_exchange_unchanged(bundle, result["files"]) is None
    assert {
        path.relative_to(bundle).as_posix(): path.read_bytes() for path in bundle.rglob("*.json")
    } == before


def test_invalid_schedules_require_neither_native_jobs_nor_plan_files(tmp_path):
    bundle, study, manifest = exchange(tmp_path, invalid=True)
    assert sum(point["status"] == "invalid_schedule" for point in study["points"]) == 2
    result = load_probe_exchange(bundle)
    assert result["manifest"] == manifest
    assert len(result["manifest"]["jobs"]) == 2
    assert [row["relative_path"] for row in result["files"]] == [
        "jobs.json",
        "study.json",
        "plans/p0001.json",
    ]


def test_raw_study_digest_remains_distinct_from_canonical_digest_and_whitespace_is_frozen(tmp_path):
    bundle, study, manifest = exchange(tmp_path)
    path = bundle / "study.json"
    raw = b"\xef\xbb\xbf" + path.read_bytes().replace(b"\n", b"\r\n") + b"  \r\n"
    path.write_bytes(raw)
    manifest["study_file_sha256"] = digest(raw)
    store(bundle / "jobs.json", manifest)
    result = load_probe_exchange(bundle)
    assert result["study"] == study
    assert result["manifest"]["study_sha256"] == study_sha256(study)
    assert result["manifest"]["study_file_sha256"] == digest(raw)
    assert result["files"][1]["sha256"] == digest(raw)
    assert path.read_bytes() == raw


def test_manifest_encoding_and_field_order_can_vary_but_are_bound_by_raw_inventory(tmp_path):
    bundle, _, manifest = exchange(tmp_path)
    raw = b"\xef\xbb\xbf" + json.dumps(manifest, separators=(",", ":"), ensure_ascii=False).encode() + b"\r\n"
    (bundle / "jobs.json").write_bytes(raw)
    result = load_probe_exchange(bundle)
    assert result["manifest"] == manifest
    assert result["files"][0]["sha256"] == digest(raw)


@pytest.mark.parametrize(
    "change",
    [
        "kind",
        "schema-version",
        "schema-bool",
        "schema-float",
        "raw-study-hash",
        "canonical-study-hash",
        "study-path",
        "header-extra",
        "header-missing",
        "jobs-not-list",
        "missing-job",
        "extra-job",
        "duplicate-job",
        "reordered-jobs",
        "wrong-trial",
        "wrong-point",
        "wrong-repetition",
        "bool-repetition",
        "float-repetition",
        "wrong-plan-hash",
        "wrong-plan-path",
        "parent-plan-path",
        "drive-plan-path",
        "stream-plan-path",
        "wrong-clock",
        "wrong-input-driver",
        "checkpoint-start",
        "job-extra",
        "job-missing",
        "job-not-object",
    ],
)
def test_manifest_must_match_all_frozen_trial_identities_and_types_in_generated_order(tmp_path, change):
    bundle, _, manifest = exchange(tmp_path)
    job = manifest["jobs"][0]
    if change == "kind":
        manifest["kind"] = "probe_backend_results"
    elif change == "schema-version":
        manifest["schema_version"] = 2
    elif change == "schema-bool":
        manifest["schema_version"] = True
    elif change == "schema-float":
        manifest["schema_version"] = 1.0
    elif change == "raw-study-hash":
        manifest["study_file_sha256"] = "a" * 64
    elif change == "canonical-study-hash":
        manifest["study_sha256"] = "a" * 64
    elif change == "study-path":
        manifest["study_path"] = "./study.json"
    elif change == "header-extra":
        manifest["trusted"] = True
    elif change == "header-missing":
        del manifest["study_path"]
    elif change == "jobs-not-list":
        manifest["jobs"] = {}
    elif change == "missing-job":
        manifest["jobs"].pop()
    elif change == "extra-job":
        manifest["jobs"].append(deepcopy(job))
    elif change == "duplicate-job":
        manifest["jobs"][1] = deepcopy(job)
    elif change == "reordered-jobs":
        manifest["jobs"].reverse()
    elif change == "wrong-trial":
        job["trial_id"] = "p9999-r1"
    elif change == "wrong-point":
        job["point_id"] = "p9999"
    elif change == "wrong-repetition":
        job["repetition"] = 8
    elif change == "bool-repetition":
        job["repetition"] = True
    elif change == "float-repetition":
        job["repetition"] = 1.0
    elif change == "wrong-plan-hash":
        job["replay_file_sha256"] = "f" * 64
    elif change == "wrong-plan-path":
        job["replay_path"] = "plans/p9999.json"
    elif change == "parent-plan-path":
        job["replay_path"] = "plans/../study.json"
    elif change == "drive-plan-path":
        job["replay_path"] = "C:study.json"
    elif change == "stream-plan-path":
        job["replay_path"] += ":alternate"
    elif change == "wrong-clock":
        job["clock_policy"] = "unmodified"
    elif change == "wrong-input-driver":
        job["input_driver"] = "physical-keyboard"
    elif change == "checkpoint-start":
        job["start_kind"] = "checkpoint"
    elif change == "job-extra":
        job["qualified"] = True
    elif change == "job-missing":
        del job["clock_policy"]
    else:
        manifest["jobs"][0] = None
    store(bundle / "jobs.json", manifest)
    with pytest.raises(ValueError, match="reconstructed frozen study|exact manifest fields"):
        load_probe_exchange(bundle)


@pytest.mark.parametrize("change", ["trials", "points", "source-whitespace", "canonical-body"])
def test_study_validation_and_both_manifest_hashes_are_required(tmp_path, change):
    bundle, study, manifest = exchange(tmp_path)
    if change == "source-whitespace":
        (bundle / "study.json").write_bytes((bundle / "study.json").read_bytes() + b" ")
    else:
        if change == "trials":
            study["trials"].reverse()
        elif change == "points":
            study["points"][0]["replay_file_sha256"] = "a" * 64
        else:
            study["spec"]["id"] = "different-synthetic-study"
        store(bundle / "study.json", study)
        manifest["study_file_sha256"] = digest((bundle / "study.json").read_bytes())
        store(bundle / "jobs.json", manifest)
    with pytest.raises(ValueError):
        load_probe_exchange(bundle)


@pytest.mark.parametrize("change", ["crlf", "indent", "bom", "body", "extra-newline", "hash-rebound"])
def test_replay_body_and_serialization_must_equal_exact_canonical_generated_bytes(tmp_path, change):
    bundle, _, manifest = exchange(tmp_path)
    path = bundle / manifest["jobs"][0]["replay_path"]
    raw = path.read_bytes()
    if change == "crlf":
        raw = raw.replace(b"\n", b"\r\n")
    elif change == "indent":
        raw = (json.dumps(json.loads(raw), indent=2) + "\n").encode()
    elif change == "bom":
        raw = b"\xef\xbb\xbf" + raw
    elif change in ("body", "hash-rebound"):
        replay = json.loads(raw)
        replay["inputs"][0]["command_index"] += 1
        raw = replay_bytes(replay)
    else:
        raw += b"\n"
    path.write_bytes(raw)
    if change == "hash-rebound":
        for job in manifest["jobs"]:
            if job["replay_path"] == path.relative_to(bundle).as_posix():
                job["replay_file_sha256"] = digest(raw)
        store(bundle / "jobs.json", manifest)
    with pytest.raises(ValueError, match="canonical generated bytes"):
        load_probe_exchange(bundle)


@pytest.mark.parametrize("target", ["jobs.json", "study.json", "plans/p0000.json"])
@pytest.mark.parametrize("raw", [b"{", b'{"kind":NaN}', b'{"kind":1,"kind":1}', b"\xff"])
def test_malformed_duplicate_nonfinite_or_non_utf8_source_is_refused(tmp_path, target, raw):
    bundle, _, _ = exchange(tmp_path)
    (bundle / target).write_bytes(raw)
    with pytest.raises(ValueError):
        load_probe_exchange(bundle)


@pytest.mark.parametrize("target", ["jobs.json", "study.json", "plans/p0000.json"])
def test_all_exchange_files_obey_the_16_mib_bounded_read(tmp_path, target):
    bundle, _, _ = exchange(tmp_path)
    (bundle / target).write_bytes(b" " * (MAX_JSON_BYTES + 1))
    with pytest.raises(ValueError, match="16 MiB"):
        load_probe_exchange(bundle)


@pytest.mark.parametrize(
    "target", ["extra.json", ".hidden-script.ps1", "plans/unknown.json", "plans/.hidden", "plans/p9999.json"]
)
def test_unknown_files_are_rejected_by_load_and_retained_inventory_checks(tmp_path, target):
    bundle, _, _ = exchange(tmp_path)
    result = load_probe_exchange(bundle)
    (bundle / target).write_bytes(b"retained foreign bytes")
    with pytest.raises(ValueError, match="Unexpected probe exchange entry"):
        load_probe_exchange(bundle)
    with pytest.raises(ValueError, match="Unexpected probe exchange entry"):
        assert_probe_exchange_unchanged(bundle, result)
    assert (bundle / target).read_bytes() == b"retained foreign bytes"


@pytest.mark.parametrize("target", ["extra-directory", "plans/extra-directory"])
def test_unknown_directories_are_rejected_without_descending_into_them(tmp_path, target):
    bundle, _, _ = exchange(tmp_path)
    directory = bundle / target
    directory.mkdir()
    (directory / "untouched.json").write_bytes(b"retained")
    with pytest.raises(ValueError, match="Unexpected probe exchange entry"):
        load_probe_exchange(bundle)
    assert (directory / "untouched.json").read_bytes() == b"retained"


@pytest.mark.parametrize("target", ["jobs.json", "study.json", "plans/p0000.json"])
def test_missing_files_and_regular_files_replaced_by_directories_are_refused(tmp_path, target):
    bundle, _, _ = exchange(tmp_path)
    result = load_probe_exchange(bundle)
    path = bundle / target
    path.unlink()
    with pytest.raises(ValueError, match="Missing probe"):
        load_probe_exchange(bundle)
    with pytest.raises(ValueError, match="Missing probe"):
        assert_probe_exchange_unchanged(bundle, result)
    path.mkdir()
    with pytest.raises(ValueError, match="wrong file type"):
        load_probe_exchange(bundle)


@pytest.mark.parametrize("target", ["jobs.json", "study.json", "plans/p0000.json"])
def test_retained_inventory_refuses_byte_changes_even_if_size_and_mtime_are_restored(tmp_path, target):
    bundle, _, _ = exchange(tmp_path)
    result = load_probe_exchange(bundle)
    path = bundle / target
    original = path.stat()
    raw = path.read_bytes()
    path.write_bytes(raw[:-1] + b" ")
    os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
    assert path.stat().st_size == original.st_size
    assert path.stat().st_mtime_ns == original.st_mtime_ns
    with pytest.raises(ValueError, match="file changed"):
        assert_probe_exchange_unchanged(bundle, result)


@pytest.mark.parametrize("changed", ["jobs.json", "study.json", "plans/p0000.json"])
def test_final_all_file_reread_rejects_earlier_source_changes_during_loading(tmp_path, monkeypatch, changed):
    bundle, _, _ = exchange(tmp_path)
    last = max((bundle / "plans").iterdir())
    original_read = reader._read_stable
    mutated = False

    def racing_read(path):
        nonlocal mutated
        raw = original_read(path)
        if path == last and not mutated:
            mutated = True
            target = bundle / changed
            original = target.stat()
            before = target.read_bytes()
            target.write_bytes(before[:-1] + b" ")
            os.utime(target, ns=(original.st_atime_ns, original.st_mtime_ns))
        return raw

    monkeypatch.setattr(reader, "_read_stable", racing_read)
    with pytest.raises(ValueError, match="file changed"):
        load_probe_exchange(bundle)
    assert mutated


def test_final_tree_check_rejects_a_file_added_during_the_integrity_pass(tmp_path, monkeypatch):
    bundle, _, _ = exchange(tmp_path)
    result = load_probe_exchange(bundle)
    last = bundle / result["files"][-1]["relative_path"]
    original_read = reader._read_stable

    def racing_read(path):
        raw = original_read(path)
        if path == last:
            (bundle / "injected.ps1").write_bytes(b"never executed")
        return raw

    monkeypatch.setattr(reader, "_read_stable", racing_read)
    with pytest.raises(ValueError, match="Unexpected"):
        assert_probe_exchange_unchanged(bundle, result)
    assert (bundle / "injected.ps1").read_bytes() == b"never executed"


def test_stable_descriptor_reads_refuse_same_size_same_mtime_mutation_between_reads(tmp_path, monkeypatch):
    bundle, _, _ = exchange(tmp_path)
    path = bundle / "jobs.json"
    original_open = Path.open
    original_stat = path.stat()

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
            raw = self.stream.read(maximum)
            if not self.changed:
                self.changed = True
                with original_open(path, "wb") as writer:
                    writer.write(raw[:-1] + b" ")
                os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
            return raw

    def controlled_open(candidate, mode="r", *args, **kwargs):
        stream = original_open(candidate, mode, *args, **kwargs)
        return MutatingReader(stream) if candidate == path and mode == "rb" else stream

    monkeypatch.setattr(Path, "open", controlled_open)
    with pytest.raises(ValueError, match="changed during reading"):
        load_probe_exchange(bundle)


@pytest.mark.parametrize("redirected", ["ancestor", "exchange", "plans", "jobs.json", "plans/p0000.json"])
def test_any_reparse_point_in_source_or_ancestors_is_refused(tmp_path, monkeypatch, redirected):
    bundle, _, _ = exchange(tmp_path)
    result = load_probe_exchange(bundle)
    target = (
        tmp_path if redirected == "ancestor" else bundle if redirected == "exchange" else bundle / redirected
    )
    original_lstat = Path.lstat

    def controlled_lstat(path, *args, **kwargs):
        info = original_lstat(path, *args, **kwargs)
        if path == target:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=REPARSE_POINT)
        return info

    monkeypatch.setattr(Path, "lstat", controlled_lstat)
    with pytest.raises(ValueError, match="Redirected"):
        load_probe_exchange(bundle)
    with pytest.raises(ValueError, match="Redirected"):
        assert_probe_exchange_unchanged(bundle, result)


def test_real_symlink_exchange_is_refused_without_changing_target_bytes(tmp_path):
    bundle, _, _ = exchange(tmp_path)
    result = load_probe_exchange(bundle)
    link = tmp_path / "linked-exchange"
    try:
        link.symlink_to(bundle, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation privileges unavailable")
    raw = (bundle / "jobs.json").read_bytes()
    with pytest.raises(ValueError, match="Redirected"):
        load_probe_exchange(link)
    with pytest.raises(ValueError, match="Redirected"):
        assert_probe_exchange_unchanged(link, result)
    assert (bundle / "jobs.json").read_bytes() == raw


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junction semantics")
def test_real_windows_junction_exchange_is_refused_without_changing_target_bytes(tmp_path):
    bundle, _, _ = exchange(tmp_path)
    result = load_probe_exchange(bundle)
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell unavailable for filesystem-only junction check")
    link = tmp_path / "junction-exchange"
    subprocess.run(
        [
            shell,
            "-NoProfile",
            "-Command",
            "$ErrorActionPreference = 'Stop'; New-Item -ItemType Junction -Path "
            "$env:AXIOM_PROBE_JUNCTION_PATH -Target $env:AXIOM_PROBE_JUNCTION_TARGET | Out-Null",
        ],
        env={
            **os.environ,
            "AXIOM_PROBE_JUNCTION_PATH": str(link),
            "AXIOM_PROBE_JUNCTION_TARGET": str(bundle),
        },
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=True,
    )
    raw = (bundle / "jobs.json").read_bytes()
    try:
        assert link.lstat().st_file_attributes & REPARSE_POINT
        with pytest.raises(ValueError, match="Redirected"):
            load_probe_exchange(link)
        with pytest.raises(ValueError, match="Redirected"):
            assert_probe_exchange_unchanged(link, result)
        assert (bundle / "jobs.json").read_bytes() == raw
    finally:
        if link.exists() and link.lstat().st_file_attributes & REPARSE_POINT:
            # Remove only this explicitly created link, without recursion.
            os.rmdir(link)


@pytest.mark.parametrize(
    "path", ["C:exchange", r"\\?\C:\exchange", r"\\.\C:\exchange", r"\\server\share\exchange"]
)
def test_drive_relative_device_and_network_aliases_are_rejected_before_file_reads(
    tmp_path, monkeypatch, path
):
    reads = []
    monkeypatch.setattr(reader, "_read_stable", lambda value: reads.append(value))
    with pytest.raises(ValueError, match="drive alias or device path"):
        load_probe_exchange(path)
    assert reads == []


@pytest.mark.parametrize("suffix", ["../exchange", "exchange.", "exchange ", "exchange:alternate"])
def test_lexical_traversal_trailing_alias_and_stream_paths_are_rejected_before_file_reads(
    tmp_path, monkeypatch, suffix
):
    bundle, _, _ = exchange(tmp_path)
    reads = []
    monkeypatch.setattr(reader, "_read_stable", lambda value: reads.append(value))
    path = str(bundle / suffix) if suffix.startswith("../") else str(tmp_path / suffix)
    with pytest.raises(ValueError, match="traversal|path aliases or alternate streams"):
        load_probe_exchange(path)
    assert reads == []


@pytest.mark.parametrize(
    "change",
    [
        "non-list",
        "empty",
        "missing-header",
        "extra-field",
        "duplicate",
        "reorder",
        "traversal",
        "drive",
        "sha",
    ],
)
def test_inventory_shape_paths_hashes_and_canonical_order_are_strict(tmp_path, change):
    bundle, _, _ = exchange(tmp_path)
    files = load_probe_exchange(bundle)["files"]
    if change == "non-list":
        files = {"files": files}
    elif change == "empty":
        files = []
    elif change == "missing-header":
        files.pop(0)
    elif change == "extra-field":
        files[0]["trusted"] = True
    elif change == "duplicate":
        files.append(deepcopy(files[-1]))
    elif change == "reorder":
        files[2:] = reversed(files[2:])
    elif change == "traversal":
        files[2]["relative_path"] = "plans/../study.json"
    elif change == "drive":
        files[2]["relative_path"] = "C:plans/p0000.json"
    else:
        files[0]["sha256"] = "not a sha256"
    with pytest.raises(ValueError):
        assert_probe_exchange_unchanged(bundle, files)
