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


def test_fixture_catalogue_cli_keeps_native_verification_unknown(tmp_path):
    output = tmp_path / "catalogue.json"
    assert main(["fixtures", "examples/native/fixture-matrix.json", "--json", str(output)]) == 0
    catalogue = json.loads(output.read_text(encoding="utf-8"))
    assert catalogue["provenance"]["native_verification"] == "not_recorded"
    specification = tmp_path / "run.json"
    assert (
        main(
            [
                "fixtures",
                "examples/native/fixture-matrix.json",
                "--case",
                "ship-portal",
                "--run",
                "replay",
                "--json",
                str(specification),
            ]
        )
        == 0
    )
    run = json.loads(specification.read_text(encoding="utf-8"))
    assert run["required_mode_sequences"]["player1"] == ["cube", "ship", "cube"]
    assert [event["command_index"] for event in run["inputs"]] == [130, 160]


def test_fixture_cli_rejects_partial_selector(tmp_path, capsys):
    output = tmp_path / "invalid.json"
    assert (
        main(
            [
                "fixtures",
                "examples/native/fixture-matrix.json",
                "--case",
                "cube-flat",
                "--json",
                str(output),
            ]
        )
        == 2
    )
    assert "supplied together" in capsys.readouterr().err
    assert not output.exists()


@pytest.mark.parametrize("command", ["fixture-check", "fixture-response"])
def test_fixture_cli_reports_mismatch_in_json_instead_of_attesting_execution(tmp_path, command):
    output = tmp_path / "mismatch.json"
    args = [command, "examples/native/fixture-matrix.json", "examples/native/synthetic-clock-a.json"]
    if command == "fixture-check":
        args += ["--case", "cube-flat", "--run", "replay"]
    else:
        args += ["examples/native/synthetic-clock-b.json", "--case", "cube-flat", "--check", "jump-response"]
    assert main([*args, "--json", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] in {"fixture_observations_mismatch", "selected_response_not_established"}
    assert not all(report["checks"].values())
