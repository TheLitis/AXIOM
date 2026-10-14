"""File ingestion checks for supplied command-probe outcomes, without a game."""

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_native import collision_capture, input_entry_capture, mechanics_capture, refresh_environment

import axiom.probeadapter as adapter
from axiom.native import canonical_sha256, load_native_capture
from axiom.probeadapter import inspect_native_probe_results
from axiom.probeplan import create_probe_study, point_replay, replay_bytes, study_sha256


def store(folder, name, document):
    path = folder / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def prepare_study(tmp_path, *, offsets=(0, 1), schema=5):
    source = input_entry_capture(policy="fixed-scheduler-240")
    source["schema_version"] = schema
    source_path = store(tmp_path, "reference.json", source)
    spec = {
        "schema_version": 1,
        "kind": "native_probe_spec",
        "id": "ingestion-test",
        "axes": [{"event_index": 0, "offsets_commands": list(offsets)}],
        "repetitions": 2,
        "run_budget": len(offsets) * 2,
    }
    study = create_probe_study(source_path, store(tmp_path, "spec.json", spec))
    return study, store(tmp_path, "study.json", study)


def trial_capture(study, trial_id, *, outcome="completed", schema=5, origin="synthetic"):
    trial = next(row for row in study["trials"] if row["id"] == trial_id)
    replay = point_replay(study, trial["point_id"])
    data = input_entry_capture(attempt_id=f"execution-{trial_id}", policy="fixed-scheduler-240")
    data["schema_version"] = schema
    data["provenance"]["origin"] = origin
    attempt = data["attempt"]
    requested, receipt = deepcopy(attempt["inputs"])
    rows = []
    for event in replay["inputs"]:
        if event["command_index"] > attempt["terminal"]["command_index"]:
            continue
        for template in (requested, receipt):
            row = {**template, **event, "sequence": len(rows), "wall_time_ns": 1_000_001 + len(rows)}
            if template["phase"] != "requested":
                row["phase"] = "push" if event["pressed"] else "release"
            rows.append(row)
    attempt.update(
        planned_inputs=deepcopy(replay["inputs"]),
        replay_sha256=hashlib.sha256(replay_bytes(replay)).hexdigest(),
        inputs=rows,
    )
    if outcome == "died":
        attempt["terminal"].update(outcome="died", event="PlayLayer::destroyPlayer")
        for sample in (attempt["trace"][-1], attempt["terminal"]):
            sample["state"]["player1"]["is_dead"] = True
        before = {"level_end_animation_started": False, "has_completed_level": False}
        for sample in [*attempt["trace"], attempt["terminal"]]:
            sample["phase"] = deepcopy(before)
        for stream in (attempt["updates"], attempt["scheduler_updates"]):
            for row in stream:
                row.update(phase_before=deepcopy(before), phase_after=deepcopy(before))
        attempt["phase_events"] = []
    return data


def native_results(tmp_path, study, captures=(), errors=()):
    rows = []
    for trial_id, capture in captures:
        path = store(tmp_path, f"{trial_id}.json", capture)
        rows.append(
            {
                "trial_id": trial_id,
                "capture_path": path.name,
                "capture_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    rows.extend({"trial_id": trial_id, "error": error} for trial_id, error in errors)
    manifest = {
        "schema_version": 1,
        "kind": "native_probe_results",
        "study_sha256": study_sha256(study),
        "attempts": rows,
    }
    return manifest, store(tmp_path, "results.json", manifest)


@pytest.mark.parametrize("schema", [4, 5])
def test_completed_repetitions_keep_exact_native_identity_and_untrusted_origin(tmp_path, schema):
    study, study_path = prepare_study(tmp_path, schema=schema)
    ids = [row["id"] for row in study["trials"]]
    data = [(trial_id, trial_capture(study, trial_id, schema=schema)) for trial_id in ids]
    manifest, results_path = native_results(tmp_path, study, data)
    report = inspect_native_probe_results(study_path, results_path)
    assert report == {
        "schema_version": 1,
        "kind": "probe_observations",
        "study_sha256": study_sha256(study),
        "origin": "native-capture-files",
        "authentication_status": "not_authenticated",
        "attempts": [
            {
                "trial_id": trial_id,
                "outcome": "completed",
                "terminal_state_sha256": canonical_sha256(capture["attempt"]["terminal"]["state"]),
                "native_terminal_event": "PlayLayer::levelComplete",
                "command_index": 2,
                "evidence_sha256": row["capture_sha256"],
                "evidence_origin": "synthetic",
                "execution_id": f"execution-{trial_id}",
                "error": None,
            }
            for (trial_id, capture), row in zip(data, manifest["attempts"])
        ],
    }
    assert len({row["evidence_sha256"] for row in report["attempts"]}) == len(ids)


def test_omitted_trials_stay_absent_and_runner_failures_are_never_deaths(tmp_path):
    study, study_path = prepare_study(tmp_path)
    _, results_path = native_results(tmp_path, study, errors=[("p0000-r2", "Runner deadline exceeded")])
    attempts = inspect_native_probe_results(study_path, results_path)["attempts"]
    assert len(attempts) == 1
    assert attempts[0]["trial_id"] == "p0000-r2"
    assert attempts[0]["outcome"] == "runner_error"
    assert attempts[0]["native_terminal_event"] is None
    assert attempts[0]["evidence_sha256"] is None
    assert attempts[0]["error"] == "Runner deadline exceeded"


def test_empty_results_do_not_invent_attempts(tmp_path):
    study, study_path = prepare_study(tmp_path)
    _, results_path = native_results(tmp_path, study)
    assert inspect_native_probe_results(study_path, results_path)["attempts"] == []


def test_native_death_accepts_valid_prefix_and_keeps_unexecuted_future_plan(tmp_path):
    study, study_path = prepare_study(tmp_path, offsets=(0, 2))
    capture = trial_capture(study, "p0001-r1", outcome="died")
    assert capture["attempt"]["planned_inputs"][0]["command_index"] == 3
    assert capture["attempt"]["inputs"] == []
    _, results_path = native_results(tmp_path, study, [("p0001-r1", capture)])
    result = inspect_native_probe_results(study_path, results_path)["attempts"][0]
    assert result["outcome"] == "died"
    assert result["native_terminal_event"] == "PlayLayer::destroyPlayer"
    assert result["command_index"] == 2
    assert result["terminal_state_sha256"] == canonical_sha256(capture["attempt"]["terminal"]["state"])


def test_completion_with_unexecuted_tail_is_rejected_instead_of_accepted_prefix(tmp_path):
    study, study_path = prepare_study(tmp_path, offsets=(0, 2))
    capture = trial_capture(study, "p0001-r1")
    assert load_native_capture(store(tmp_path, "valid-prefix.json", capture))
    _, results_path = native_results(tmp_path, study, [("p0001-r1", capture)])
    result = inspect_native_probe_results(study_path, results_path)["attempts"][0]
    assert result["outcome"] == "rejected"
    assert "unexecuted planned input tail" in result["error"]
    assert result["native_terminal_event"] is None


def test_completion_with_inactive_dead_second_player_preserves_native_terminal_contract(tmp_path):
    study, study_path = prepare_study(tmp_path)
    capture = trial_capture(study, "p0000-r1")
    capture["attempt"]["terminal"]["state"]["player2"] = {
        **capture["attempt"]["terminal"]["state"]["player1"],
        "is_dead": True,
    }
    assert capture["attempt"]["terminal"]["state"]["dual_active"] is False
    _, results_path = native_results(tmp_path, study, [("p0000-r1", capture)])
    assert inspect_native_probe_results(study_path, results_path)["attempts"][0]["outcome"] == "completed"


@pytest.mark.parametrize("origin", ["synthetic", "native-engine-capture"])
def test_declared_origin_is_preserved_without_promoting_authentication(tmp_path, origin):
    study, study_path = prepare_study(tmp_path)
    capture = trial_capture(study, "p0000-r1", origin=origin)
    _, results_path = native_results(tmp_path, study, [("p0000-r1", capture)])
    result = inspect_native_probe_results(study_path, results_path)
    assert result["authentication_status"] == "not_authenticated"
    assert result["attempts"][0]["evidence_origin"] == origin


@pytest.mark.parametrize(
    "mutation,reason",
    [
        (lambda d: d["integrity"].update(recording_complete=False), "Incomplete native recording"),
        (lambda d: d["integrity"].update(dropped_records=1), "dropped records"),
        (lambda d: d["integrity"].update(errors=["capture overflow"]), "capture errors"),
        (lambda d: d["attempt"].update(start_kind="practice"), "full-start"),
        (lambda d: d["attempt"]["inputs"][0].update(in_command=False), "within command processing"),
        (lambda d: d["attempt"].update(planned_inputs=[]), "planned prefix"),
        (lambda d: d["attempt"]["inputs"].clear(), "planned prefix"),
        (lambda d: d["attempt"].update(replay_sha256="b" * 64), "generated replay file bytes"),
        (
            lambda d: d["attempt"]["terminal"].update(event="PlayLayer::destroyPlayer"),
            "declared native engine callback",
        ),
        (lambda d: d["challenge"].update(level_sha256="a" * 64), "challenge"),
        (lambda d: d["collector"].update(source_tree_sha256="a" * 64), "collector"),
        (lambda d: d["state_fields"].reverse(), "state_fields"),
        (lambda d: d["provenance"].update(independently_verified=True), "self-certify"),
        (lambda d: d["provenance"].update(origin="human"), "provenance.origin"),
    ],
)
def test_invalid_capture_and_off_protocol_identity_are_explicit_rejections(tmp_path, mutation, reason):
    study, study_path = prepare_study(tmp_path)
    capture = trial_capture(study, "p0000-r1")
    mutation(capture)
    _, results_path = native_results(tmp_path, study, [("p0000-r1", capture)])
    result = inspect_native_probe_results(study_path, results_path)["attempts"][0]
    assert result["outcome"] == "rejected"
    assert reason in result["error"]
    assert result["terminal_state_sha256"] is None


def test_plan_differs_even_when_the_wrong_schedule_has_valid_native_receipts(tmp_path):
    study, study_path = prepare_study(tmp_path)
    capture = trial_capture(study, "p0001-r1")
    _, results_path = native_results(tmp_path, study, [("p0000-r1", capture)])
    result = inspect_native_probe_results(study_path, results_path)["attempts"][0]
    assert result["outcome"] == "rejected"
    assert "complete generated point replay" in result["error"]


def test_replay_digest_binds_exact_exported_lf_bytes_not_logical_payload(tmp_path):
    study, study_path = prepare_study(tmp_path)
    capture = trial_capture(study, "p0000-r1")
    replay = point_replay(study, "p0000")
    assert canonical_sha256(replay) != hashlib.sha256(replay_bytes(replay)).hexdigest()
    capture["attempt"]["replay_sha256"] = canonical_sha256(replay)
    _, results_path = native_results(tmp_path, study, [("p0000-r1", capture)])
    result = inspect_native_probe_results(study_path, results_path)["attempts"][0]
    assert result["outcome"] == "rejected"
    assert "generated replay file bytes" in result["error"]


def test_different_environment_is_not_accepted_as_an_implicit_collector_transition(tmp_path):
    study, study_path = prepare_study(tmp_path)
    capture = trial_capture(study, "p0000-r1")
    capture["environment"]["adapter_binary_sha256"] = "a" * 64
    refresh_environment(capture)
    _, results_path = native_results(tmp_path, study, [("p0000-r1", capture)])
    result = inspect_native_probe_results(study_path, results_path)["attempts"][0]
    assert result["outcome"] == "rejected"
    assert "identity differs" in result["error"]


@pytest.mark.parametrize(
    "builder",
    [
        lambda: mechanics_capture(policy="fixed-scheduler-240"),
        lambda: collision_capture(policy="native"),
        lambda: collision_capture(policy="fixed-scheduler-240", driver="scheduled-ui-callback"),
        lambda: collision_capture(policy="fixed-scheduler-240", driver="none"),
    ],
)
def test_older_capture_native_clock_and_ui_delivery_are_not_silently_promoted(tmp_path, builder):
    study, study_path = prepare_study(tmp_path)
    capture = builder()
    _, results_path = native_results(tmp_path, study, [("p0000-r1", capture)])
    result = inspect_native_probe_results(study_path, results_path)["attempts"][0]
    assert result["outcome"] == "rejected"
    assert "schema 4 or 5" in result["error"] or "full-start" in result["error"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(schema_version=True),
        lambda d: d.update(kind="probe_observations"),
        lambda d: d.update(study_sha256="a" * 64),
        lambda d: d.update(authentication_status="verified"),
        lambda d: d.update(attempts={}),
        lambda d: d["attempts"][0].update(trial_id="unknown-r1"),
        lambda d: d["attempts"][0].update(capture_sha256="invalid"),
        lambda d: d["attempts"][0].update(error="runner failed"),
        lambda d: d["attempts"][0].pop("capture_sha256"),
        lambda d: d["attempts"][0].update(extra=True),
    ],
)
def test_results_manifest_validation_fails_before_any_outcome_import(tmp_path, mutation):
    study, study_path = prepare_study(tmp_path)
    manifest, results_path = native_results(tmp_path, study, [("p0000-r1", trial_capture(study, "p0000-r1"))])
    mutation(manifest)
    store(tmp_path, results_path.name, manifest)
    with pytest.raises(ValueError):
        inspect_native_probe_results(study_path, results_path)


@pytest.mark.parametrize("error", ["", " ", " untrimmed ", "a" * 1025, 42])
def test_runner_error_has_a_bounded_exact_shape(tmp_path, error):
    study, study_path = prepare_study(tmp_path)
    _, results_path = native_results(tmp_path, study, errors=[("p0000-r1", error)])
    with pytest.raises(ValueError):
        inspect_native_probe_results(study_path, results_path)


@pytest.mark.parametrize("duplicate", ["trial_id", "capture_path", "capture_sha256"])
def test_trial_or_evidence_reuse_cannot_counterfeit_repetitions(tmp_path, duplicate):
    study, study_path = prepare_study(tmp_path)
    captures = [(trial_id, trial_capture(study, trial_id)) for trial_id in ("p0000-r1", "p0000-r2")]
    manifest, results_path = native_results(tmp_path, study, captures)
    manifest["attempts"][1][duplicate] = manifest["attempts"][0][duplicate]
    store(tmp_path, results_path.name, manifest)
    with pytest.raises(ValueError, match="duplicate|reuse"):
        inspect_native_probe_results(study_path, results_path)


def test_different_hash_and_path_with_reused_execution_id_are_rejected(tmp_path):
    study, study_path = prepare_study(tmp_path)
    first, second = (trial_capture(study, trial_id) for trial_id in ("p0000-r1", "p0000-r2"))
    second["attempt"]["id"] = first["attempt"]["id"]
    second["attempt"]["terminal"]["state"]["player1"]["rotation"] = 0.25
    _, results_path = native_results(tmp_path, study, [("p0000-r1", first), ("p0000-r2", second)])
    with pytest.raises(ValueError, match="attempt.id"):
        inspect_native_probe_results(study_path, results_path)


def test_execution_id_reuse_is_rejected_even_after_first_capture_identity_rejection(tmp_path):
    study, study_path = prepare_study(tmp_path)
    first, second = (trial_capture(study, trial_id) for trial_id in ("p0000-r1", "p0000-r2"))
    first["challenge"]["level_sha256"] = "a" * 64
    second["attempt"]["id"] = first["attempt"]["id"]
    _, results_path = native_results(tmp_path, study, [("p0000-r1", first), ("p0000-r2", second)])
    with pytest.raises(ValueError, match="attempt.id"):
        inspect_native_probe_results(study_path, results_path)


@pytest.mark.parametrize(
    "capture_path",
    [
        "../outside.json",
        "/outside.json",
        "C:/outside.json",
        "C:relative.json",
        "\\\\server\\share\\capture.json",
        "nested\\capture.json",
        "nested/../capture.json",
        "./capture.json",
        "nested//capture.json",
        "capture.json:alternate-stream",
        "capture.json\x00",
        "a/" * 17 + "capture.json",
        "a" * 256,
    ],
)
def test_capture_paths_are_confined_portable_and_bounded(tmp_path, capture_path):
    study, study_path = prepare_study(tmp_path)
    manifest, results_path = native_results(tmp_path, study, [("p0000-r1", trial_capture(study, "p0000-r1"))])
    manifest["attempts"][0]["capture_path"] = capture_path
    store(tmp_path, results_path.name, manifest)
    with pytest.raises(ValueError, match="relative path"):
        inspect_native_probe_results(study_path, results_path)


@pytest.mark.parametrize("payload", [b'{"schema_version":', b'{"a":1,"a":2}', b'{"a":NaN}'])
def test_malformed_capture_bytes_remain_rejected_evidence_not_native_death(tmp_path, payload):
    study, study_path = prepare_study(tmp_path)
    manifest, results_path = native_results(tmp_path, study, [("p0000-r1", trial_capture(study, "p0000-r1"))])
    (tmp_path / manifest["attempts"][0]["capture_path"]).write_bytes(payload)
    manifest["attempts"][0]["capture_sha256"] = hashlib.sha256(payload).hexdigest()
    store(tmp_path, results_path.name, manifest)
    result = inspect_native_probe_results(study_path, results_path)["attempts"][0]
    assert result["outcome"] == "rejected"
    assert result["native_terminal_event"] is None


def test_missing_and_changed_capture_files_do_not_become_runner_success(tmp_path):
    study, study_path = prepare_study(tmp_path)
    manifest, results_path = native_results(tmp_path, study, [("p0000-r1", trial_capture(study, "p0000-r1"))])
    capture_path = tmp_path / manifest["attempts"][0]["capture_path"]
    capture_path.write_bytes(b"{}")
    result = inspect_native_probe_results(study_path, results_path)["attempts"][0]
    assert result["outcome"] == "rejected"
    assert "SHA-256" in result["error"]
    capture_path.unlink()
    assert inspect_native_probe_results(study_path, results_path)["attempts"][0]["outcome"] == "rejected"


def test_nested_ordinary_capture_file_is_allowed_within_results_root(tmp_path):
    study, study_path = prepare_study(tmp_path)
    manifest, results_path = native_results(tmp_path, study, [("p0000-r1", trial_capture(study, "p0000-r1"))])
    nested = tmp_path / "captures"
    nested.mkdir()
    source = tmp_path / manifest["attempts"][0]["capture_path"]
    source.rename(nested / source.name)
    manifest["attempts"][0]["capture_path"] = f"captures/{source.name}"
    store(tmp_path, results_path.name, manifest)
    assert inspect_native_probe_results(study_path, results_path)["attempts"][0]["outcome"] == "completed"


def test_real_symlink_to_external_capture_is_rejected(tmp_path):
    study, study_path = prepare_study(tmp_path)
    manifest, results_path = native_results(tmp_path, study, [("p0000-r1", trial_capture(study, "p0000-r1"))])
    capture_path = tmp_path / manifest["attempts"][0]["capture_path"]
    original = capture_path.read_bytes()
    outside = tmp_path.parent / f"{tmp_path.name}-outside.json"
    outside.write_bytes(original)
    capture_path.unlink()
    try:
        try:
            capture_path.symlink_to(outside)
        except OSError as error:
            pytest.skip(f"Symlink creation unavailable: {error}")
        result = inspect_native_probe_results(study_path, results_path)["attempts"][0]
        assert result["outcome"] == "rejected"
        assert "links or reparse" in result["error"]
    finally:
        outside.unlink()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junction semantics")
def test_real_windows_junction_to_capture_directory_is_rejected(tmp_path):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell unavailable for the filesystem-only junction check")
    study, study_path = prepare_study(tmp_path)
    manifest, results_path = native_results(tmp_path, study, [("p0000-r1", trial_capture(study, "p0000-r1"))])
    foreign = tmp_path / "foreign-owned-test-data"
    foreign.mkdir()
    capture_name = manifest["attempts"][0]["capture_path"]
    content = (tmp_path / capture_name).read_bytes()
    (foreign / capture_name).write_bytes(content)
    junction = tmp_path / "redirected-captures"
    subprocess.run(
        [
            shell,
            "-NoProfile",
            "-Command",
            "$ErrorActionPreference = 'Stop'; New-Item -ItemType Junction -Path "
            "$env:AXIOM_PROBE_TEST_JUNCTION -Target $env:AXIOM_PROBE_TEST_TARGET | Out-Null",
        ],
        env={
            **os.environ,
            "AXIOM_PROBE_TEST_JUNCTION": str(junction),
            "AXIOM_PROBE_TEST_TARGET": str(foreign),
        },
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=True,
    )
    try:
        assert junction.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
        manifest["attempts"][0]["capture_path"] = f"{junction.name}/{capture_name}"
        store(tmp_path, results_path.name, manifest)
        result = inspect_native_probe_results(study_path, results_path)["attempts"][0]
        assert result["outcome"] == "rejected"
        assert "links or reparse" in result["error"]
        assert (foreign / capture_name).read_bytes() == content
    finally:
        if junction.exists() and junction.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            os.rmdir(junction)


def test_reparse_point_attributes_are_rejected_independently_of_symlink_mode(tmp_path, monkeypatch):
    capture = tmp_path / "capture.json"
    capture.write_text("{}", encoding="utf-8")
    ordinary_lstat = Path.lstat

    def reparse_lstat(self, *args, **kwargs):
        info = ordinary_lstat(self, *args, **kwargs)
        if self == capture:
            return SimpleNamespace(
                st_mode=stat.S_IFREG | 0o600, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT
            )
        return info

    monkeypatch.setattr(Path, "lstat", reparse_lstat)
    with pytest.raises(ValueError, match="links or reparse"):
        adapter._ordinary_file(capture)


def test_capture_changed_during_loader_validation_is_rejected(tmp_path, monkeypatch):
    study, study_path = prepare_study(tmp_path)
    manifest, results_path = native_results(tmp_path, study, [("p0000-r1", trial_capture(study, "p0000-r1"))])
    original = adapter.load_native_capture

    def changing_loader(path):
        capture = original(path)
        capture["attempt"]["terminal"]["state"]["player1"]["rotation"] += 1
        store(tmp_path, Path(path).name, capture)
        return capture

    monkeypatch.setattr(adapter, "load_native_capture", changing_loader)
    result = inspect_native_probe_results(study_path, results_path)["attempts"][0]
    assert result["outcome"] == "rejected"
    assert "changed during native validation" in result["error"]


def test_manifest_changed_during_capture_validation_fails_entire_import(tmp_path, monkeypatch):
    study, study_path = prepare_study(tmp_path)
    manifest, results_path = native_results(tmp_path, study, [("p0000-r1", trial_capture(study, "p0000-r1"))])
    original = adapter.load_native_capture

    def changing_loader(path):
        capture = original(path)
        manifest["attempts"] = []
        store(tmp_path, results_path.name, manifest)
        return capture

    monkeypatch.setattr(adapter, "load_native_capture", changing_loader)
    with pytest.raises(ValueError, match="changed during import"):
        inspect_native_probe_results(study_path, results_path)


def test_study_changed_during_loader_validation_fails_entire_import(tmp_path, monkeypatch):
    study, study_path = prepare_study(tmp_path)
    _, results_path = native_results(tmp_path, study)
    original = adapter.load_probe_study

    def changing_loader(path):
        document = original(path)
        # The JSON tree is equal; changed raw identity still breaks the read.
        Path(path).write_text(json.dumps(document, indent=2), encoding="utf-8")
        return document

    monkeypatch.setattr(adapter, "load_probe_study", changing_loader)
    with pytest.raises(ValueError, match="changed during validation"):
        inspect_native_probe_results(study_path, results_path)


def test_loaded_capture_payload_cannot_diverge_from_bound_source_bytes(tmp_path, monkeypatch):
    study, study_path = prepare_study(tmp_path)
    _, results_path = native_results(tmp_path, study, [("p0000-r1", trial_capture(study, "p0000-r1"))])
    original = adapter.load_native_capture

    def substituted_loader(path):
        document = original(path)
        document["attempt"]["terminal"]["state"]["player1"]["x"] += 100
        return document

    monkeypatch.setattr(adapter, "load_native_capture", substituted_loader)
    result = inspect_native_probe_results(study_path, results_path)["attempts"][0]
    assert result["outcome"] == "rejected"
    assert "changed during native validation" in result["error"]


def test_capture_read_failure_remains_an_explicit_evidence_rejection(tmp_path, monkeypatch):
    study, study_path = prepare_study(tmp_path)
    manifest, results_path = native_results(tmp_path, study, [("p0000-r1", trial_capture(study, "p0000-r1"))])
    capture_path = tmp_path / manifest["attempts"][0]["capture_path"]
    original = adapter.read_json

    def unreadable_json(path):
        if Path(path) == capture_path:
            raise PermissionError("Capture evidence is unreadable")
        return original(path)

    monkeypatch.setattr(adapter, "read_json", unreadable_json)
    result = inspect_native_probe_results(study_path, results_path)["attempts"][0]
    assert result["outcome"] == "rejected"
    assert result["error"] == "Capture evidence is unreadable"
