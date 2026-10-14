"""Real Windows junction rejection complements portable synthetic path checks."""

import os
import shutil
import subprocess
import sys

import pytest
from test_startup import environment, native_line

from axiom.startup import collect_startup_evidence, inspect_startup_evidence


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junction semantics")
def test_redirected_windows_log_directory_never_imports_foreign_readiness(tmp_path):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if shell is None:
        pytest.skip("PowerShell unavailable for the filesystem-only junction check")
    runtime, manifest = environment(tmp_path)
    foreign = tmp_path / "foreign-owned-test-data"
    foreign.mkdir()
    log = foreign / "foreign.log"
    content = native_line("AXIOM sandbox manual test ready; waiting for the user's Start AXIOM Test button")
    log.write_bytes(content)
    (runtime / "geode").mkdir()
    junction = runtime / "geode" / "logs"
    process = subprocess.run(
        [
            shell,
            "-NoProfile",
            "-Command",
            "$ErrorActionPreference = 'Stop'; New-Item -ItemType Junction -Path "
            "$env:AXIOM_TEST_JUNCTION_PATH -Target $env:AXIOM_TEST_JUNCTION_TARGET | Out-Null",
        ],
        env={
            **os.environ,
            "AXIOM_TEST_JUNCTION_PATH": str(junction),
            "AXIOM_TEST_JUNCTION_TARGET": str(foreign),
        },
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=True,
    )
    assert process.returncode == 0
    try:
        assert junction.lstat().st_file_attributes & 0x400
        metadata = collect_startup_evidence(runtime, manifest, tmp_path / "evidence")
        report = inspect_startup_evidence(metadata["bundle_path"])
        assert metadata["complete"] is False
        assert report["complete"] is False
        assert report["markers"]["manual_ready"]["status"] == "not_observed_in_retained_diagnostics"
        assert report["current_attempt_readiness"]["status"] == "not_established"
        assert report["m1_gate"] == "not_established"
        assert log.read_bytes() == content
    finally:
        # Remove only the verified, explicitly created link; never recurse or
        # remove its target. The owned target bytes are retained for pytest.
        if junction.exists() and junction.lstat().st_file_attributes & 0x400:
            os.rmdir(junction)
