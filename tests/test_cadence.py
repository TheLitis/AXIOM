"""Cadence diagnostics preserve clock domains, nesting and missing observations."""

import hashlib
import json
from copy import deepcopy

import pytest
from test_native import capture, rich_capture, save
from test_windowsinput import windows_capture

from axiom.cadence import inspect_native_cadence
from axiom.cli import main
from axiom.native import inspect_native_capture


def test_legacy_capture_has_no_invented_wall_streams(tmp_path):
    path = save(tmp_path, capture())
    before = inspect_native_capture(path)
    report = inspect_native_cadence(path)
    assert report["status"] == "synthetic_fixture_diagnostics"
    assert report["capture_ratios"]["command_count"] == 2
    assert report["capture_ratios"]["commands_per_declared_wall_second"]["value"] == 100
    assert report["command_dt_arguments"]["sample_count"] == 2
    assert report["streams"]["updates"] == {"status": "not_recorded_schema1"}
    assert report["phase_events"]["rows"] == []
    assert inspect_native_capture(path) == before
    assert report["source_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_single_entry_and_terminal_clipping_are_distinct(tmp_path):
    report = inspect_native_cadence(save(tmp_path, rich_capture()))
    stream = report["streams"]["scheduler_updates"]
    assert stream["stream_entry_interval_rate"]["status"] == "insufficient_entries"
    assert stream["capture_count_per_declared_wall_second"]["value"] == 50
    assert stream["wall_intervals"]["interval_union_seconds"] == pytest.approx(0.022)
    assert stream["wall_intervals"]["through_terminal_union_seconds"] == pytest.approx(0.02)
    assert stream["wall_intervals"]["after_terminal_union_seconds"] == pytest.approx(0.002)
    assert stream["wall_intervals"]["late_exit_record_count"] == 1
    assert stream["phase_buckets"]["crosses_phase_boundary"]["row_count"] == 1


def test_nested_updates_do_not_double_count_wall_or_commands(tmp_path):
    data = rich_capture()
    child = deepcopy(data["attempt"]["updates"][0])
    child.update(sequence=1, parent_sequence=0, wall_enter_ns=1_000_000, wall_exit_ns=20_500_000)
    data["attempt"]["updates"].append(child)
    report = inspect_native_cadence(save(tmp_path, data))
    stream = report["streams"]["updates"]
    assert (stream["row_count"], stream["root_row_count"], stream["nested_row_count"]) == (2, 1, 1)
    assert stream["wall_intervals"]["inclusive_interval_sum_seconds"] == pytest.approx(0.0405)
    assert stream["wall_intervals"]["interval_union_seconds"] == pytest.approx(0.021)
    assert stream["command_deltas"]["sum"] == 2
    assert stream["command_associations"]["known_trace_command_count"] == 2
    assert [row["direct_trace_command_count"] for row in stream["command_associations"]["rows"]] == [2, 0]
    assert stream["stream_entry_interval_rate"]["value"] == 1000
    assert stream["capture_count_per_declared_wall_second"]["value"] == 100


def test_startup_gaps_and_terminal_tail_remain_separate(tmp_path):
    data = rich_capture()
    original = data["attempt"]["scheduler_updates"][0]
    prefix = deepcopy(original)
    prefix.update(
        command_index_after=0,
        phase_after=deepcopy(prefix["phase_before"]),
        wall_enter_ns=0,
        wall_exit_ns=100_000,
    )
    active = deepcopy(original)
    active.update(sequence=1, wall_enter_ns=200_000)
    tail = deepcopy(original)
    tail.update(
        sequence=2,
        command_index_before=2,
        wall_enter_ns=22_100_000,
        wall_exit_ns=22_200_000,
        phase_before=deepcopy(tail["phase_after"]),
    )
    data["attempt"]["terminal"]["wall_elapsed_seconds"] = 0.023
    data["attempt"]["terminal"]["scheduler_sequence"] = 2
    data["attempt"]["terminal"]["update_sequence"] = None
    # The final command-free row encloses the terminal; command-producing row
    # includes the complete update, then finishes before the terminal callback.
    tail["wall_exit_ns"] = 24_000_000
    data["attempt"]["scheduler_updates"] = [prefix, active, tail]
    data["attempt"]["updates"][0].update(wall_enter_ns=300_000, scheduler_sequence=1)
    for row in data["attempt"]["trace"][1:]:
        row["scheduler_sequence"] = 1
    data["attempt"]["phase_events"][0]["scheduler_sequence"] = 1
    report = inspect_native_cadence(save(tmp_path, data))
    stream = report["streams"]["scheduler_updates"]
    assert stream["command_free_prefix_row_count"] == 1
    assert stream["terminal_command_free_tail_row_count"] == 1
    assert stream["entry_gap_seconds"]["sample_count"] == 2
    assert stream["entry_gap_seconds"]["p50"] == pytest.approx(0.0002)
    assert stream["entry_gap_seconds"]["p95"] == pytest.approx(0.0219)
    assert stream["phase_buckets"]["start_warmup"]["row_count"] == 1
    assert stream["phase_buckets"]["crosses_phase_boundary"]["row_count"] == 1
    assert stream["phase_buckets"]["ending"]["row_count"] == 1


def test_fixed_arguments_are_not_wall_time_or_observed_frequency(tmp_path):
    report = inspect_native_cadence(save(tmp_path, rich_capture(policy="fixed-scheduler-240")))
    stream = report["streams"]["scheduler_updates"]
    assert report["clock_identity"]["clock_policy"] == "fixed-scheduler-240"
    assert stream["dt_arguments"]["original_delivered_different_count"] == 1
    assert stream["dt_arguments"]["original"]["sum"] == 0.02
    assert stream["dt_arguments"]["delivered"]["sum"] != 0.02
    assert report["render_fps"] == "not_measured"
    assert report["recording_overhead"] == "not_attributed"
    assert report["hardware_latency"] == "not_measured"
    assert report["statistics_method"]["confidence_intervals"] == "not_estimated"


def test_empty_stream_and_unknown_memberships_are_preserved(tmp_path):
    data = rich_capture()
    data["attempt"].update(updates=[], scheduler_updates=[], phase_events=[])
    for row in [*data["attempt"]["trace"], data["attempt"]["terminal"]]:
        row.update(update_sequence=None, scheduler_sequence=None)
    stream = inspect_native_cadence(save(tmp_path, data))["streams"]["updates"]
    assert stream["status"] == "empty_recorded_stream"
    assert stream["command_associations"]["unknown_trace_command_count"] == 2
    assert stream["entry_gap_seconds"]["p99"] is None
    assert stream["wall_intervals"]["interval_union_seconds"] == 0


def test_zero_declared_duration_does_not_create_infinity(tmp_path):
    data = capture(replay=False)
    data["attempt"]["inputs"] = []
    data["attempt"]["terminal"]["wall_elapsed_seconds"] = 0
    report = inspect_native_cadence(save(tmp_path, data))
    assert report["capture_ratios"]["commands_per_declared_wall_second"] == {
        "value": None,
        "status": "zero_denominator",
    }
    json.dumps(report, allow_nan=False)


def test_schema7_observation_keeps_its_distinct_environment(tmp_path):
    report = inspect_native_cadence(save(tmp_path, windows_capture()))
    assert report["capture_schema_version"] == 7
    assert report["environment"]["windows_input_observer"] == "raw-dispatch-v1"
    assert report["attempt"]["input_delivery"]["driver"] == "none"
    assert report["authentication_status"] == "not_authenticated"


def test_incomplete_capture_is_rejected(tmp_path):
    data = rich_capture()
    data["integrity"]["recording_complete"] = False
    with pytest.raises(ValueError):
        inspect_native_cadence(save(tmp_path, data))


def test_native_terminal_bound_is_kept_before_calculation(tmp_path, capsys):
    data = rich_capture()
    data["attempt"].update(updates=[], scheduler_updates=[], phase_events=[])
    for row in [*data["attempt"]["trace"], data["attempt"]["terminal"]]:
        row.update(update_sequence=None, scheduler_sequence=None)
    data["attempt"]["terminal"]["wall_elapsed_seconds"] = 1e308
    path = save(tmp_path, data)
    with pytest.raises(ValueError, match="86400"):
        inspect_native_cadence(path)
    assert main(["native-cadence", str(path)]) == 2
    assert "86400" in capsys.readouterr().err


def test_source_mutation_during_analysis_is_rejected(tmp_path, monkeypatch):
    import axiom.cadence as module

    path = save(tmp_path, capture())
    loader = module._load

    def changing_loader(value):
        result = loader(value)
        path.write_bytes(path.read_bytes() + b" ")
        return result

    monkeypatch.setattr(module, "_load", changing_loader)
    with pytest.raises(ValueError, match="changed"):
        inspect_native_cadence(path)


def test_cli_serializes_diagnostics_with_explicit_identity(tmp_path):
    path = save(tmp_path, rich_capture())
    output = tmp_path / "cadence.json"
    assert main(["native-cadence", str(path), "--json", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["kind"] == "native_cadence_diagnostics"
    assert report["source_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert report["difficulty_calibration"] == "not_established"
