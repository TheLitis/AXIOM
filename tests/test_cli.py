import json

import pytest

from axiom.cli import main
from axiom.report import render_report


def test_cli_error_is_concise(tmp_path, capsys):
    assert main(["timing", str(tmp_path / "missing.json")]) == 2
    assert "axiom:" in capsys.readouterr().err


def test_all_sample_commands(tmp_path):
    commands = [
        ("timing", "examples/timing.json"),
        ("cohort", "examples/cohort.json"),
        ("level", "examples/level.txt"),
        ("replay", "examples/replays/synthetic.gdr.json"),
        ("trials", "examples/trials.json"),
    ]
    for command, path in commands:
        output = tmp_path / f"{command}.json"
        assert main([command, path, "--json", str(output)]) == 0
        assert isinstance(json.loads(output.read_text(encoding="utf-8")), dict)


def test_report_script_injection_escaped(tmp_path):
    payload = {"label": '</script><script>alert("unsafe")</script><img onerror="alert(1)">'}
    report = render_report(tmp_path / "report.html", timing=payload).read_text(encoding="utf-8")
    assert '</script><script>alert("unsafe")' not in report
    assert "\\u003c/script\\u003e" in report
    assert '<img onerror="alert(1)">' not in report


def test_demo_creates_portable_report(tmp_path):
    assert main(["demo", "--out", str(tmp_path), "--trials", "50"]) == 0
    assert (tmp_path / "index.html").is_file()
    assert json.loads((tmp_path / "timing.json").read_text())["ar"] is None
    assert json.loads((tmp_path / "cohort.json").read_text())["synthetic"] is True


def test_report_rejects_mismatched_challenge(tmp_path):
    with pytest.raises(ValueError, match="challenge identities"):
        render_report(
            tmp_path / "bad.html", timing={"challenge": {"id": "one"}}, cohort={"challenge": {"id": "two"}}
        )
