"""Startup archives cannot promote stale, unbound, or incomplete log readiness."""

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from axiom import startup
from axiom.startup import collect_startup_evidence, inspect_startup_evidence, snapshot_startup_logs


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def environment(tmp_path, **fields):
    tmp_path.mkdir(parents=True, exist_ok=True)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    observation = tmp_path / "observation"
    observation.mkdir()
    manifest = {
        "kind": "native_windows_input_observation",
        "status": "observation_not_established",
        "runtime_directory": str(runtime),
        "process_id": 123,
        "process_started_at_utc": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(),
        "error": None,
        **fields,
    }
    path = write_json(observation / "startup-manifest-snapshot.json", manifest)
    (observation / "stdout.txt").write_bytes(b"")
    (observation / "stderr.txt").write_bytes(b"")
    return runtime, path


def log_file(runtime, data, relative="geode/logs/Geode 2026-10-14 12.00.00.log"):
    path = runtime / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def native_line(payload):
    return f"12:00:00 INFO  [Main] [AXIOM Native C>]: {payload}\n".encode()


def bundle(runtime, manifest, baseline=None):
    metadata = collect_startup_evidence(runtime, manifest, manifest.parent / "startup", baseline)
    return metadata, inspect_startup_evidence(metadata["bundle_path"])


def report_file(report, relative):
    return next(item for item in report["files"] if item["relative_path"] == relative)


def baseline(runtime, manifest):
    path = manifest.parent / "baseline.json"
    snapshot_startup_logs(runtime, path)
    return path


def rewrite_bundle(metadata, mutate):
    path = Path(metadata["bundle_path"])
    data = json.loads(path.read_bytes())
    mutate(data)
    write_json(path, data)
    return path


def symlink_or_skip(path, target, *, directory=False):
    try:
        path.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"This host cannot create the test symlink: {exc}")


def test_retrospective_bytes_and_observed_stages_do_not_authenticate_current_readiness(tmp_path):
    runtime, manifest = environment(tmp_path)
    original = (
        b"\x1b[38;5;45m12:00:00 INFO \x1b[0m [Main] [Geode]: Entry took 0.077s\r\n"
        + native_line("AXIOM M1 adapter loaded; selected-state only").replace(b"\n", b"\r\n")
        + native_line("AXIOM sandbox manual test ready; waiting for the user's Start AXIOM Test button")
        + native_line(
            "AXIOM sandbox fixture launched; input authorship is not authenticated by the collector"
        )
        + native_line("AXIOM native capture exported locally: C:/test/capture.json")
    )
    source = log_file(runtime, original)
    manifest_before = manifest.read_bytes()
    metadata, report = bundle(runtime, manifest)
    record = report_file(report, source.relative_to(runtime).as_posix())
    retained = Path(metadata["bundle_path"]).parent / record["retained_path"]
    assert retained.read_bytes() == original == source.read_bytes()
    assert record["sha256"] == hashlib.sha256(original).hexdigest()
    assert report["source_sha256"] == metadata["bundle_sha256"]
    assert report["observation_manifest_sha256"] == hashlib.sha256(manifest_before).hexdigest()
    assert manifest.read_bytes() == manifest_before
    assert report["attribution"]["mode"] == "retrospective_runtime_unbound"
    assert report["markers"]["loader_entry"]["status"] == "observed_in_retained_diagnostics"
    assert report["markers"]["manual_ready"]["observations"][0]["line_number"] == 3
    assert report["current_attempt_readiness"]["status"] == "not_established"
    assert report["markers"]["fixture_launch_request"]["current_attempt_status"] == "not_established"
    assert report["markers"]["capture_export"]["current_attempt_status"] == "not_established"
    assert report["cause"] == "unknown"
    assert report["m1_gate"] == report["hardware_authentication"] == "not_established"
    assert report["kind"] == "startup_diagnostic_report"


def test_complete_prelaunch_inventory_admits_only_log_level_new_file_readiness(tmp_path):
    runtime, manifest = environment(tmp_path)
    initial = baseline(runtime, manifest)
    original = b"".join(
        native_line(payload)
        for payload in (
            "AXIOM sandbox app init entered",
            "AXIOM sandbox app init returned: true",
            "AXIOM sandbox menu init entered",
            "AXIOM sandbox menu init returned: true",
            "AXIOM sandbox isolated writable path: C:/test/sandbox-saves",
            "AXIOM sandbox manual test ready; waiting for the user's Start AXIOM Test button",
            "AXIOM local capture active; command-call clock, selected-state only",
        )
    )
    log_file(runtime, original)
    metadata, report = bundle(runtime, manifest, initial)
    assert metadata["complete"] is True
    assert report["attribution"]["mode"] == "prospective_runtime_baseline"
    assert report["current_attempt_readiness"]["status"] == "observed_in_new_runtime_diagnostics"
    assert report["current_attempt_readiness"]["authenticated_process_membership"] is False
    for name in (
        "app_init_enter",
        "app_init_return_true",
        "menu_init_enter",
        "menu_init_return_true",
        "save_isolation",
        "capture_start",
    ):
        assert report["markers"][name]["current_attempt_status"] == "observed_in_new_runtime_diagnostics"
    assert report["markers"]["menu_init_return_false"]["status"] == "not_observed_in_retained_diagnostics"
    assert report["m1_gate"] == report["ordinary_input_equivalence"] == "not_established"


def test_unchanged_preexisting_ready_log_cannot_establish_current_readiness(tmp_path):
    runtime, manifest = environment(tmp_path)
    path = log_file(runtime, native_line("AXIOM sandbox manual test ready; stale prior run"))
    initial = baseline(runtime, manifest)
    _, report = bundle(runtime, manifest, initial)
    record = report_file(report, path.relative_to(runtime).as_posix())
    assert record["baseline_state"] == "unchanged"
    assert report["markers"]["manual_ready"]["status"] == "observed_in_retained_diagnostics"
    assert report["markers"]["manual_ready"]["current_attempt_status"] == "not_established"
    assert report["current_attempt_readiness"]["evidence"] == []


@pytest.mark.parametrize("append", [False, True])
def test_same_name_overwrite_or_append_retains_changes_without_attributing_rows(tmp_path, append):
    runtime, manifest = environment(tmp_path)
    previous = b"12:00:00 INFO [Main] [Geode]: Entry took 0.01s\n"
    path = log_file(runtime, previous)
    initial = baseline(runtime, manifest)
    replacement = native_line("AXIOM sandbox manual test ready; changed same filename")
    path.write_bytes(previous + replacement if append else replacement)
    metadata, report = bundle(runtime, manifest, initial)
    record = report_file(report, path.relative_to(runtime).as_posix())
    assert record["baseline_state"] == "changed"
    assert (Path(metadata["bundle_path"]).parent / record["retained_path"]).read_bytes() == path.read_bytes()
    assert report["markers"]["manual_ready"]["current_attempt_status"] == "not_established"
    assert report["current_attempt_readiness"]["status"] == "not_established"


def test_missing_empty_and_removed_files_remain_distinct(tmp_path):
    runtime, manifest = environment(tmp_path)
    log = log_file(runtime, b"previous log")
    initial = baseline(runtime, manifest)
    log.unlink()
    (manifest.parent / "stderr.txt").unlink()
    _, report = bundle(runtime, manifest, initial)
    empty = report_file(report, "stdout.txt")
    missing = report_file(report, "stderr.txt")
    removed = report_file(report, log.relative_to(runtime).as_posix())
    assert (empty["state"], empty["size_bytes"], empty["sha256"]) == (
        "captured",
        0,
        hashlib.sha256(b"").hexdigest(),
    )
    assert (missing["state"], missing["size_bytes"], missing["sha256"]) == ("missing", None, None)
    assert (removed["state"], removed["baseline_state"]) == ("missing", "removed")
    assert report["cause"] == "unknown"


def test_attention_caption_and_error_words_cannot_invent_a_guard_or_timeout(tmp_path):
    runtime, manifest = environment(tmp_path, error="Timeout or crash? unknown historical statement")
    log_file(runtime, b"Attention\nSHIFT\nALT+SHIFT\nError: crash\n")
    _, report = bundle(runtime, manifest)
    assert all(
        item["status"] == "not_observed_in_retained_diagnostics" for item in report["markers"].values()
    )
    assert report["lifecycle"]["timeout_reached"] is None
    assert report["lifecycle"]["status"] == "unknown_not_recorded"
    assert report["lifecycle"]["cause"] == "unknown"


def test_marker_match_requires_its_logger_source_and_exact_message_shape(tmp_path):
    runtime, manifest = environment(tmp_path)
    data = (
        b"12:00:00 INFO [Main] [Other Mod]: AXIOM sandbox manual test ready; forged source\n"
        b"12:00:00 INFO [Main] [AXIOM Native C> impostor]: AXIOM sandbox manual test ready; foreign tag\n"
        b"12:00:00 INFO [Main] [Geode]: AXIOM sandbox manual test ready; wrong logger\n"
        b"12:00:00 INFO [Main] [AXIOM Native C>]: quoted: AXIOM sandbox manual test ready; not emitted\n"
        + native_line("AXIOM sandbox menu init returned: false")
        + native_line("AXIOM delivery/watch experiment refused: explicit guard")
    )
    log_file(runtime, data)
    _, report = bundle(runtime, manifest)
    assert report["markers"]["manual_ready"]["status"] == "not_observed_in_retained_diagnostics"
    assert report["markers"]["menu_init_return_false"]["status"] == "observed_in_retained_diagnostics"
    assert report["markers"]["adapter_refused"]["status"] == "observed_in_retained_diagnostics"
    assert report["cause"] == "unknown"


def test_only_immediate_text_scope_is_read_and_dumps_are_explicitly_skipped(tmp_path):
    runtime, manifest = environment(tmp_path)
    ready = native_line("AXIOM sandbox manual test ready; must never come from a dump")
    log_file(runtime, ready, "geode/crashlogs/crash.dmp")
    log_file(runtime, ready, "geode/logs/nested/hidden.log")
    log_file(runtime, b"early loader diagnostic", "_geode_early_error.txt")
    log_file(runtime, b"crash text", "geode/crashlogs/crash.txt")
    _, report = bundle(runtime, manifest)
    assert report_file(report, "geode/crashlogs/crash.dmp")["state"] == "out_of_scope"
    assert report_file(report, "geode/logs/nested")["state"] == "out_of_scope"
    assert not any(item["relative_path"].endswith("hidden.log") for item in report["files"])
    assert report_file(report, "_geode_early_error.txt")["state"] == "captured"
    assert report_file(report, "geode/crashlogs/crash.txt")["state"] == "captured"
    assert report["markers"]["manual_ready"]["status"] == "not_observed_in_retained_diagnostics"


def test_real_mutation_during_read_is_retained_as_incomplete_without_ready_promotion(tmp_path, monkeypatch):
    runtime, manifest = environment(tmp_path)
    initial = baseline(runtime, manifest)
    log = log_file(runtime, native_line("AXIOM sandbox manual test ready; first byte version"))
    original_read = startup._read_once
    changed = False

    def mutate_during_read(stream, maximum):
        nonlocal changed
        data = original_read(stream, maximum)
        if Path(stream.name) == log and not changed:
            changed = True
            log.write_bytes(native_line("AXIOM sandbox manual test ready; different byte version"))
        return data

    monkeypatch.setattr(startup, "_read_once", mutate_during_read)
    metadata, report = bundle(runtime, manifest, initial)
    assert changed
    assert metadata["complete"] is report["complete"] is False
    assert metadata["status"] == "collected_with_read_failures"
    assert report_file(report, log.relative_to(runtime).as_posix())["state"] == "unstable"
    assert report["current_attempt_readiness"]["status"] == "not_established"


def test_per_file_and_total_byte_bounds_preserve_distinct_failures(tmp_path, monkeypatch):
    runtime, manifest = environment(tmp_path)
    log = log_file(runtime, b"x" * 513)
    monkeypatch.setattr(startup, "MAX_FILE_BYTES", 512)
    metadata, report = bundle(runtime, manifest)
    assert metadata["complete"] is False
    assert report_file(report, log.relative_to(runtime).as_posix())["state"] == "too_large"

    runtime2, manifest2 = environment(tmp_path / "second")
    log2 = log_file(runtime2, b"x" * 129)
    monkeypatch.setattr(startup, "MAX_TOTAL_BYTES", len(manifest2.read_bytes()) + 128)
    metadata2, report2 = bundle(runtime2, manifest2)
    assert metadata2["complete"] is False
    assert report_file(report2, log2.relative_to(runtime2).as_posix())["state"] == "total_byte_limit"


def test_file_count_limit_does_not_silently_drop_eligible_logs(tmp_path, monkeypatch):
    runtime, manifest = environment(tmp_path)
    initial = baseline(runtime, manifest)
    log_file(runtime, native_line("AXIOM sandbox manual test ready; new but partial"), "geode/logs/a.log")
    log_file(runtime, b"also eligible", "geode/logs/b.log")
    monkeypatch.setattr(startup, "MAX_LOG_FILES", 1)
    metadata, report = bundle(runtime, manifest, initial)
    assert metadata["complete"] is False
    assert report_file(report, "geode/logs/b.log")["state"] == "file_count_limit"
    assert report["markers"]["manual_ready"]["status"] == "observed_in_retained_diagnostics"
    assert report["current_attempt_readiness"]["status"] == "not_established"


def test_directory_scan_bound_and_partial_baseline_do_not_promote_new_readiness(tmp_path, monkeypatch):
    runtime, manifest = environment(tmp_path)
    for name in ("a", "b", "c"):
        log_file(runtime, b"old", f"geode/logs/{name}.log")
    monkeypatch.setattr(startup, "MAX_DIRECTORY_ENTRIES", 2)
    initial = baseline(runtime, manifest)
    inventory = json.loads(initial.read_bytes())
    assert inventory["complete"] is False
    assert inventory["groups"][0]["state"] == "directory_entry_limit"
    for path in (runtime / "geode/logs").iterdir():
        path.unlink()
    log_file(
        runtime, native_line("AXIOM sandbox manual test ready; incomplete baseline"), "geode/logs/new.log"
    )
    metadata, report = bundle(runtime, manifest, initial)
    assert metadata["complete"] is True
    assert report["attribution"]["mode"] == "retrospective_runtime_unbound"
    assert report["current_attempt_readiness"]["status"] == "not_established"


def test_late_baseline_cannot_be_declared_prelaunch(tmp_path):
    runtime, manifest = environment(
        tmp_path, process_started_at_utc=(datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    )
    initial = baseline(runtime, manifest)
    log_file(runtime, native_line("AXIOM sandbox manual test ready; new since late snapshot"))
    _, report = bundle(runtime, manifest, initial)
    assert report["attribution"]["baseline_supplied"] is True
    assert report["attribution"]["complete_inventory_declared_before_process_start"] is False
    assert report["current_attempt_readiness"]["status"] == "not_established"


def test_windows_seven_digit_timestamps_keep_prelaunch_order_exact(tmp_path):
    runtime, manifest = environment(tmp_path, process_started_at_utc="2026-10-14T12:00:00.1234561Z")
    initial = baseline(runtime, manifest)
    inventory = json.loads(initial.read_bytes())
    inventory["created_at_utc"] = "2026-10-14T12:00:00.1234562Z"
    write_json(initial, inventory)
    log_file(runtime, native_line("AXIOM sandbox manual test ready; 100 ns late baseline"))
    _, report = bundle(runtime, manifest, initial)
    assert report["attribution"]["complete_inventory_declared_before_process_start"] is False
    assert report["current_attempt_readiness"]["status"] == "not_established"


def test_failed_directory_read_cannot_be_reported_as_removed_prior_log(tmp_path, monkeypatch):
    runtime, manifest = environment(tmp_path)
    log = log_file(runtime, b"prior log bytes")
    initial = baseline(runtime, manifest)
    original_scandir = startup.os.scandir

    def refuse_known_log_directory(path):
        if Path(path) == log.parent:
            raise PermissionError("synthetic denied directory read")
        return original_scandir(path)

    monkeypatch.setattr(startup.os, "scandir", refuse_known_log_directory)
    metadata, report = bundle(runtime, manifest, initial)
    record = report_file(report, log.relative_to(runtime).as_posix())
    assert metadata["complete"] is False
    assert record["state"] == "unreadable"
    assert record["baseline_state"] == "baseline_uncertain"
    assert log.read_bytes() == b"prior log bytes"


@pytest.mark.parametrize("raw_exit", [0, 42, 0xC0000005, 0xFFFFFFFF, -1073741819])
def test_exit_declarations_preserve_windows_unsigned_codes_without_crash_inference(tmp_path, raw_exit):
    runtime, manifest = environment(
        tmp_path,
        process_exit_code=raw_exit,
        timeout_reached=False,
        process_cleanup={
            "exit_observed_before_cleanup": True,
            "termination_requested": False,
            "natural_exit_code": raw_exit,
        },
        cleanup_errors=[],
    )
    _, report = bundle(runtime, manifest)
    lifecycle = report["lifecycle"]
    assert lifecycle["status"] == "runner_observed_exit_before_cleanup"
    assert lifecycle["process_exit_code_raw"] == raw_exit
    assert lifecycle["process_exit_code_uint32"] == raw_exit & 0xFFFFFFFF
    assert lifecycle["natural_exit_code_raw"] == raw_exit
    assert lifecycle["natural_exit_code_uint32"] == raw_exit & 0xFFFFFFFF
    assert lifecycle["cause"] == "unknown"


def test_timeout_runner_termination_and_primary_cleanup_errors_are_separate(tmp_path):
    runtime, manifest = environment(
        tmp_path,
        timeout_reached=True,
        error="Timeout waiting for export",
        cleanup_errors=["preservation failed"],
        process_cleanup={
            "exit_observed_before_cleanup": False,
            "termination_requested": True,
            "natural_exit_code": None,
        },
    )
    _, report = bundle(runtime, manifest)
    lifecycle = report["lifecycle"]
    assert lifecycle["status"] == "runner_requested_termination"
    assert lifecycle["timeout_reached"] is True
    assert lifecycle["primary_error"] == "Timeout waiting for export"
    assert lifecycle["cleanup_errors"] == ["preservation failed"]
    assert lifecycle["cause"] == "unknown"


@pytest.mark.parametrize("target", ["file", "manifest", "baseline"])
def test_frozen_payload_identity_tampering_is_rejected(tmp_path, target):
    runtime, manifest = environment(tmp_path)
    initial = baseline(runtime, manifest)
    log_file(runtime, b"original log")
    metadata, report = bundle(runtime, manifest, initial)
    root = Path(metadata["bundle_path"]).parent
    relative = {
        "file": report_file(report, "geode/logs/Geode 2026-10-14 12.00.00.log")["retained_path"],
        "manifest": "frozen-manifest.json",
        "baseline": "frozen-baseline.json",
    }[target]
    frozen = root / relative
    frozen.write_bytes(frozen.read_bytes() + b" ")
    with pytest.raises(ValueError, match="hash/size mismatch"):
        inspect_startup_evidence(metadata["bundle_path"])


@pytest.mark.parametrize(
    "relative", ["../outside.log", "/outside.log", "files/../outside.log", "files\\0000.bin"]
)
def test_bundle_payload_path_escape_is_rejected(tmp_path, relative):
    runtime, manifest = environment(tmp_path)
    log_file(runtime, b"log")
    metadata, _ = bundle(runtime, manifest)
    path = rewrite_bundle(metadata, lambda data: data["files"][0].update(retained_path=relative))
    with pytest.raises(ValueError, match="path escapes bundle"):
        inspect_startup_evidence(path)


def test_forged_baseline_classification_cannot_promote_unchanged_log(tmp_path):
    runtime, manifest = environment(tmp_path)
    log_file(runtime, native_line("AXIOM sandbox manual test ready; stale"))
    initial = baseline(runtime, manifest)
    metadata, _ = bundle(runtime, manifest, initial)
    path = rewrite_bundle(metadata, lambda data: data["files"][0].update(baseline_state="new"))
    with pytest.raises(ValueError, match="classification does not match"):
        inspect_startup_evidence(path)


def test_different_runtime_manifest_or_baseline_is_rejected_before_writing_bundle(tmp_path):
    runtime, manifest = environment(tmp_path)
    second = tmp_path / "different-runtime"
    second.mkdir()
    initial = manifest.parent / "foreign-baseline.json"
    snapshot_startup_logs(second, initial)
    out = manifest.parent / "startup"
    with pytest.raises(ValueError, match="different runtime"):
        collect_startup_evidence(runtime, manifest, out, initial)
    assert not out.exists()
    data = json.loads(manifest.read_bytes())
    data["runtime_directory"] = str(second)
    write_json(manifest, data)
    with pytest.raises(ValueError, match="different runtime"):
        collect_startup_evidence(runtime, manifest, out)
    assert not out.exists()


def test_symlinked_source_or_runtime_never_reads_foreign_ready_lines(tmp_path):
    runtime, manifest = environment(tmp_path)
    outside = tmp_path / "outside.log"
    outside.write_bytes(native_line("AXIOM sandbox manual test ready; foreign file"))
    log_dir = runtime / "geode/logs"
    log_dir.mkdir(parents=True)
    symlink_or_skip(log_dir / "linked.log", outside)
    metadata, report = bundle(runtime, manifest)
    assert metadata["complete"] is False
    assert report_file(report, "geode/logs/linked.log")["state"] == "rejected_path"
    assert report["markers"]["manual_ready"]["status"] == "not_observed_in_retained_diagnostics"
    alias = tmp_path / "alias"
    symlink_or_skip(alias, runtime, directory=True)
    with pytest.raises(ValueError, match="rejected_path"):
        snapshot_startup_logs(alias, manifest.parent / "alias.json")


def test_symlinked_retained_payload_is_rejected_even_with_matching_bytes(tmp_path):
    runtime, manifest = environment(tmp_path)
    original = b"same bytes through unsafe path"
    log_file(runtime, original)
    metadata, report = bundle(runtime, manifest)
    root = Path(metadata["bundle_path"]).parent
    retained = root / report_file(report, "geode/logs/Geode 2026-10-14 12.00.00.log")["retained_path"]
    foreign = tmp_path / "foreign.bin"
    foreign.write_bytes(original)
    retained.unlink()
    symlink_or_skip(retained, foreign)
    with pytest.raises(ValueError, match="rejected_path"):
        inspect_startup_evidence(metadata["bundle_path"])


def test_new_snapshot_and_collection_refuse_overwrites(tmp_path):
    runtime, manifest = environment(tmp_path)
    initial = baseline(runtime, manifest)
    original = initial.read_bytes()
    with pytest.raises(FileExistsError):
        snapshot_startup_logs(runtime, initial)
    assert initial.read_bytes() == original
    out = manifest.parent / "startup"
    out.mkdir()
    sentinel = out / "keep.txt"
    sentinel.write_bytes(b"prior evidence")
    with pytest.raises(FileExistsError):
        collect_startup_evidence(runtime, manifest, out)
    assert sentinel.read_bytes() == b"prior evidence"


def test_unsupported_encoding_is_preserved_and_not_guessed(tmp_path):
    runtime, manifest = environment(tmp_path)
    data = b"\xff\x80AXIOM sandbox manual test ready;"
    path = log_file(runtime, data)
    metadata, report = bundle(runtime, manifest)
    record = report_file(report, path.relative_to(runtime).as_posix())
    assert record["text_status"] == "unsupported_text_encoding"
    assert report["complete"] is report["marker_matching_complete"] is False
    assert (Path(metadata["bundle_path"]).parent / record["retained_path"]).read_bytes() == data
    assert report["markers"]["manual_ready"]["status"] == "not_observed_in_retained_diagnostics"


def test_bom_utf16_logs_match_without_reencoding_retained_bytes(tmp_path):
    runtime, manifest = environment(tmp_path)
    data = native_line("AXIOM sandbox menu init returned: true").decode().encode("utf-16")
    path = log_file(runtime, data)
    metadata, report = bundle(runtime, manifest)
    record = report_file(report, path.relative_to(runtime).as_posix())
    assert (Path(metadata["bundle_path"]).parent / record["retained_path"]).read_bytes() == data
    assert report["markers"]["menu_init_return_true"]["status"] == "observed_in_retained_diagnostics"


def test_marker_matching_bound_is_explicit_and_downgrades_readiness(tmp_path, monkeypatch):
    runtime, manifest = environment(tmp_path)
    initial = baseline(runtime, manifest)
    log_file(runtime, native_line("AXIOM sandbox manual test ready; repeated") * 3)
    monkeypatch.setattr(startup, "MAX_MARKER_OBSERVATIONS", 2)
    metadata, report = bundle(runtime, manifest, initial)
    assert metadata["complete"] is True
    assert report["complete"] is report["marker_matching_complete"] is False
    assert len(report["markers"]["manual_ready"]["observations"]) == 2
    assert report["current_attempt_readiness"]["status"] == "not_established"


def test_bundle_mutation_during_inspection_is_rejected(tmp_path, monkeypatch):
    runtime, manifest = environment(tmp_path)
    source = log_file(runtime, b"retained log")
    metadata, report = bundle(runtime, manifest)
    path = Path(metadata["bundle_path"])
    retained = path.parent / report_file(report, source.relative_to(runtime).as_posix())["retained_path"]
    original_read = startup._read_once
    mutated = False

    def alter_bundle_after_loading(stream, maximum):
        nonlocal mutated
        data = original_read(stream, maximum)
        if Path(stream.name) == retained and not mutated:
            mutated = True
            path.write_bytes(path.read_bytes() + b" ")
        return data

    monkeypatch.setattr(startup, "_read_once", alter_bundle_after_loading)
    with pytest.raises(ValueError, match="bundle changed"):
        inspect_startup_evidence(path)


def test_earlier_payload_mutation_while_inspecting_later_file_is_rejected(tmp_path, monkeypatch):
    runtime, manifest = environment(tmp_path)
    log_file(runtime, b"first retained log", "geode/logs/a.log")
    log_file(runtime, b"second retained log", "geode/logs/b.log")
    metadata, report = bundle(runtime, manifest)
    root = Path(metadata["bundle_path"]).parent
    first = root / report_file(report, "geode/logs/a.log")["retained_path"]
    second = root / report_file(report, "geode/logs/b.log")["retained_path"]
    original_read = startup._read_once
    changed = False

    def mutate_prior_payload(stream, maximum):
        nonlocal changed
        data = original_read(stream, maximum)
        if Path(stream.name) == second and not changed:
            changed = True
            first.write_bytes(first.read_bytes() + b" changed later")
        return data

    monkeypatch.setattr(startup, "_read_once", mutate_prior_payload)
    with pytest.raises(ValueError, match="hash/size mismatch"):
        inspect_startup_evidence(metadata["bundle_path"])


@pytest.mark.parametrize(
    "field,value", [("kind", "native_capture"), ("schema_version", True), ("complete", True)]
)
def test_strict_bundle_kind_schema_and_completeness(tmp_path, field, value):
    runtime, manifest = environment(tmp_path)
    log_file(runtime, b"oversized" * 100)
    # Produce genuine partial evidence; mutating complete then creates a false claim.
    original_bound = startup.MAX_FILE_BYTES
    startup.MAX_FILE_BYTES = 512
    try:
        metadata, _ = bundle(runtime, manifest)
        path = rewrite_bundle(metadata, lambda data: data.update({field: value}))
        with pytest.raises(ValueError):
            inspect_startup_evidence(path)
    finally:
        startup.MAX_FILE_BYTES = original_bound


def test_duplicate_json_fields_are_rejected(tmp_path):
    path = tmp_path / "bundle.json"
    path.write_bytes(b'{"kind":"startup_evidence_bundle","kind":"native_capture"}')
    with pytest.raises(ValueError, match="Duplicate startup JSON field"):
        inspect_startup_evidence(path)


@pytest.mark.parametrize("value", [True, 1.5, -(2**31) - 1, 2**32])
def test_cleanup_exit_code_domain_is_strict(tmp_path, value):
    runtime, manifest = environment(
        tmp_path,
        process_cleanup={
            "exit_observed_before_cleanup": True,
            "termination_requested": False,
            "natural_exit_code": value,
        },
    )
    with pytest.raises(ValueError, match="Invalid natural_exit_code"):
        collect_startup_evidence(runtime, manifest, manifest.parent / "startup")
