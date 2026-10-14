"""The console startup workflow remains separate from native qualification."""

import hashlib
import json
from pathlib import Path

from test_startup import environment, log_file, native_line

from axiom.cli import main


def test_baseline_collection_and_inspection_cli_keep_unverified_log_scope(tmp_path, capsys):
    runtime, manifest = environment(tmp_path)
    inventory = tmp_path / "baseline.json"
    assert main(["native-startup-baseline", str(runtime), "--output", str(inventory)]) == 0
    assert json.loads(capsys.readouterr().out)["kind"] == "startup_log_inventory"
    log_file(
        runtime,
        native_line("AXIOM sandbox manual test ready; waiting for the user's Start AXIOM Test button"),
    )
    evidence = tmp_path / "evidence"
    assert (
        main(
            [
                "native-startup-collect",
                str(runtime),
                "--attempt-manifest",
                str(manifest),
                "--output",
                str(evidence),
                "--baseline",
                str(inventory),
            ]
        )
        == 0
    )
    metadata = json.loads(capsys.readouterr().out)
    assert metadata["complete"] is True
    bundle = Path(metadata["bundle_path"])
    before = hashlib.sha256(bundle.read_bytes()).hexdigest()
    assert before == metadata["bundle_sha256"]
    output = tmp_path / "inspection.json"
    assert main(["native-startup", str(bundle), "--json", str(output)]) == 0
    report = json.loads(output.read_text())
    assert report["attribution"]["mode"] == "prospective_runtime_baseline"
    assert report["current_attempt_readiness"]["status"] == "observed_in_new_runtime_diagnostics"
    assert report["current_attempt_readiness"]["authenticated_process_membership"] is False
    assert report["m1_gate"] == "not_established"
    assert report["cause"] == "unknown"
    assert hashlib.sha256(bundle.read_bytes()).hexdigest() == before


def test_retrospective_cli_cannot_claim_current_attempt_readiness(tmp_path, capsys):
    runtime, manifest = environment(tmp_path)
    log_file(
        runtime,
        native_line("AXIOM sandbox manual test ready; waiting for the user's Start AXIOM Test button"),
    )
    assert (
        main(
            [
                "native-startup-collect",
                str(runtime),
                "--attempt-manifest",
                str(manifest),
                "--output",
                str(tmp_path / "evidence"),
            ]
        )
        == 0
    )
    metadata = json.loads(capsys.readouterr().out)
    assert main(["native-startup", metadata["bundle_path"]]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["attribution"]["mode"] == "retrospective_runtime_unbound"
    assert report["markers"]["manual_ready"]["status"] == "observed_in_retained_diagnostics"
    assert report["current_attempt_readiness"]["status"] == "not_established"


def test_cli_refuses_overwriting_retained_startup_evidence(tmp_path, capsys):
    runtime, manifest = environment(tmp_path)
    assert (
        main(
            [
                "native-startup-collect",
                str(runtime),
                "--attempt-manifest",
                str(manifest),
                "--output",
                str(tmp_path / "evidence"),
            ]
        )
        == 0
    )
    metadata = json.loads(capsys.readouterr().out)
    bundle = Path(metadata["bundle_path"])
    before = bundle.read_bytes()
    assert main(["native-startup", str(bundle), "--json", str(bundle)]) == 2
    assert "outside the retained evidence directory" in capsys.readouterr().err
    assert bundle.read_bytes() == before


def test_missing_startup_bundle_cli_reports_error_without_native_status(tmp_path, capsys):
    assert main(["native-startup", str(tmp_path / "missing.json")]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("axiom:")
