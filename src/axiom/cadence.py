"""Finite diagnostics of recorded hook arguments and paired wall intervals.

These observations are neither render FPS nor CPU/recording overhead, hardware
latency, elapsed simulation time, independently measured physics or difficulty.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from pathlib import Path

from .native import _load, canonical_sha256

BUCKETS = ("start_warmup", "normal_pre_end", "ending", "crosses_phase_boundary", "unknown")
QUANTILE_METHOD = "empirical_nearest_rank_sorted_values[max(0,ceil(p*n)-1)]"


def _finite_sum(values) -> float:
    try:
        result = math.fsum(values)
    except OverflowError as exc:
        raise ValueError("Cadence diagnostic sum exceeds finite numeric range") from exc
    if not math.isfinite(result):
        raise ValueError("Cadence diagnostic sum exceeds finite numeric range")
    return result


def _statistics(values: list[float]) -> dict:
    ordered = sorted(values)
    total = _finite_sum(ordered)
    result = {"sample_count": len(values), "sum": total}
    result.update(min=None, max=None, mean=None, p50=None, p95=None, p99=None)
    if ordered:
        result.update(min=ordered[0], max=ordered[-1], mean=total / len(values))
        for key, numerator in (("p50", 50), ("p95", 95), ("p99", 99)):
            # Integer arithmetic gives the exact nearest rank, including ties.
            rank = (numerator * len(values) + 99) // 100
            result[key] = ordered[max(0, rank - 1)]
    return result


def _rate(count: int, seconds: float, *, enough_samples: bool = True) -> dict:
    if not enough_samples:
        return {"value": None, "status": "insufficient_entries"}
    if seconds <= 0:
        return {"value": None, "status": "zero_denominator"}
    value = count / seconds
    return {
        "value": value if math.isfinite(value) else None,
        "status": "recorded_ratio" if math.isfinite(value) else "nonfinite_ratio_unavailable",
    }


def _union_ns(intervals: list[tuple]) -> float:
    if not intervals:
        return 0
    ordered = sorted(intervals)
    start, end = ordered[0]
    lengths = []
    for next_start, next_end in ordered[1:]:
        if next_start <= end:
            end = max(end, next_end)
        else:
            lengths.append(end - start)
            start, end = next_start, next_end
    lengths.append(end - start)
    return _finite_sum(lengths)


def _intervals(rows: list[dict], terminal_ns: float) -> dict:
    intervals = [(row["wall_enter_ns"], row["wall_exit_ns"]) for row in rows]
    clipped = [
        (max(0, start), min(end, terminal_ns))
        for start, end in intervals
        if min(end, terminal_ns) >= max(0, start)
    ]
    tails = [(max(start, terminal_ns), end) for start, end in intervals if end > terminal_ns]
    inclusive = _finite_sum(end - start for start, end in intervals) / 1e9
    union = _union_ns(intervals) / 1e9
    return {
        "unit": "seconds_of_recorded_wall_interval",
        "inclusive_interval_sum_seconds": inclusive,
        "interval_union_seconds": union,
        "overlap_seconds": max(0.0, inclusive - union),
        "through_terminal_inclusive_sum_seconds": _finite_sum(end - start for start, end in clipped) / 1e9,
        "through_terminal_union_seconds": _union_ns(clipped) / 1e9,
        "late_exit_record_count": sum(end > terminal_ns for _, end in intervals),
        "late_exit_max_seconds": max(
            (end - terminal_ns for _, end in intervals if end > terminal_ns), default=0
        )
        / 1e9,
        "after_terminal_union_seconds": _union_ns(tails) / 1e9,
        "aggregation_scope": "this_stream_only_never_added_to_another_stream",
    }


def _bucket(row: dict) -> str:
    before, after = row.get("phase_before"), row.get("phase_after")
    if before is None or after is None:
        return "unknown"
    if before != after:
        return "crosses_phase_boundary"
    if not before["level_end_animation_started"] and not before["has_completed_level"]:
        return (
            "start_warmup"
            if row["command_index_before"] == row["command_index_after"] == 0
            else "normal_pre_end"
        )
    return "ending" if before["level_end_animation_started"] else "unknown"


def _dt_arguments(rows: list[dict]) -> dict:
    return {
        "unit": "seconds_as_passed_to_hook",
        "original": _statistics([row["original_dt_seconds"] for row in rows]),
        "delivered": _statistics([row["delivered_dt_seconds"] for row in rows]),
        "original_zero_count": sum(row["original_dt_seconds"] == 0 for row in rows),
        "delivered_zero_count": sum(row["delivered_dt_seconds"] == 0 for row in rows),
        "original_delivered_different_count": sum(
            row["original_dt_seconds"] != row["delivered_dt_seconds"] for row in rows
        ),
        "sum_interpretation": "sum_of_recorded_arguments_not_elapsed_simulation_or_wall_time",
    }


def _command_deltas(rows: list[dict]) -> dict:
    roots = [row for row in rows if row["parent_sequence"] is None]
    counts = Counter(row["command_index_after"] - row["command_index_before"] for row in roots)
    return {
        "scope": "root_rows_only_inclusive_command_spans_nested_rows_not_added",
        "root_row_count": len(roots),
        "sum": sum(delta * count for delta, count in counts.items()),
        "distribution": [{"command_delta": delta, "row_count": counts[delta]} for delta in sorted(counts)],
    }


def _stream_report(rows: list[dict], attempt: dict, context_key: str) -> dict:
    elapsed = attempt["terminal"]["wall_elapsed_seconds"]
    terminal_ns = elapsed * 1e9
    if not math.isfinite(terminal_ns):
        raise ValueError("Cadence terminal wall time exceeds finite nanosecond range")
    roots = [row for row in rows if row["parent_sequence"] is None]
    entries = [row["wall_enter_ns"] for row in rows]
    gaps = [(right - left) / 1e9 for left, right in zip(entries, entries[1:])]
    span = (entries[-1] - entries[0]) / 1e9 if entries else 0.0
    command_rows = attempt["trace"][1:]
    associations = Counter(row[context_key] for row in command_rows)
    grouping = [
        {
            key: row[key]
            for key in ("sequence", "parent_sequence", "command_index_before", "command_index_after")
        }
        | ({"scheduler_sequence": row["scheduler_sequence"]} if context_key == "update_sequence" else {})
        | {"direct_trace_command_count": associations[row["sequence"]]}
        for row in rows
    ]
    prefix = next((index for index, row in enumerate(rows) if row["command_index_after"] != 0), len(rows))
    tail = 0
    for row in reversed(rows):
        if (
            row["command_index_before"] != attempt["terminal"]["command_index"]
            or row["command_index_after"] != attempt["terminal"]["command_index"]
        ):
            break
        tail += 1
    buckets = {}
    for name in BUCKETS:
        selected = [row for row in rows if _bucket(row) == name]
        buckets[name] = {
            "row_count": len(selected),
            "root_row_count": sum(row["parent_sequence"] is None for row in selected),
            "nested_row_count": sum(row["parent_sequence"] is not None for row in selected),
            "dt_arguments": _dt_arguments(selected),
            "wall_intervals": _intervals(selected, terminal_ns),
            "command_deltas": _command_deltas(selected),
        }
    return {
        "status": "recorded" if rows else "empty_recorded_stream",
        "row_count": len(rows),
        "root_row_count": len(roots),
        "nested_row_count": len(rows) - len(roots),
        "capture_count_per_declared_wall_second": _rate(len(rows), elapsed),
        "stream_entry_interval_rate": {
            **_rate(max(0, len(rows) - 1), span, enough_samples=len(rows) >= 2),
            "numerator_intervals": max(0, len(rows) - 1),
            "entry_span_seconds": span,
        },
        "entry_gap_seconds": _statistics(gaps),
        "paired_duration_seconds": _statistics(
            [(row["wall_exit_ns"] - row["wall_enter_ns"]) / 1e9 for row in rows]
        ),
        "dt_arguments": _dt_arguments(rows),
        "root_dt_arguments": _dt_arguments(roots),
        "wall_intervals": _intervals(rows, terminal_ns),
        "root_wall_intervals": _intervals(roots, terminal_ns),
        "command_deltas": _command_deltas(rows),
        "command_free_prefix_row_count": prefix,
        "terminal_command_free_tail_row_count": tail,
        "command_associations": {
            "known_trace_command_count": len(command_rows) - associations[None],
            "unknown_trace_command_count": associations[None],
            "rows": grouping,
            "grouping_sha256": canonical_sha256(grouping),
        },
        "phase_buckets": buckets,
    }


def inspect_native_cadence(path: str | Path) -> dict:
    """Describe one validated immutable capture; never pool clock domains."""
    try:
        return _inspect_native_cadence(path)
    except OverflowError as exc:
        raise ValueError("Cadence diagnostic exceeds finite numeric range") from exc


def _inspect_native_cadence(path: str | Path) -> dict:
    capture, source_sha256 = _load(path)
    attempt = capture["attempt"]
    elapsed = attempt["terminal"]["wall_elapsed_seconds"]
    commands = attempt["trace"][1:]
    rich = capture["schema_version"] >= 2
    streams = {
        name: _stream_report(attempt[name], attempt, context) if rich else {"status": "not_recorded_schema1"}
        for name, context in (("updates", "update_sequence"), ("scheduler_updates", "scheduler_sequence"))
    }
    report = {
        "schema_version": 1,
        "kind": "native_cadence_diagnostics",
        "source_sha256": source_sha256,
        "capture_schema_version": capture["schema_version"],
        "status": "supplied_native_observer_diagnostics"
        if capture["provenance"]["origin"] == "native-engine-capture"
        else "synthetic_fixture_diagnostics",
        "provenance": capture["provenance"],
        "collector": capture["collector"],
        "environment": capture["environment"],
        "environment_sha256": capture["environment_sha256"],
        "challenge": capture["challenge"],
        "integrity": capture["integrity"],
        "clock_identity": capture["environment"]["clocks"],
        "attempt": {key: attempt[key] for key in ("id", "start_kind", "input_source", "replay_sha256")},
        "terminal": attempt["terminal"],
        "capture_ratios": {
            "declared_terminal_wall_seconds": elapsed,
            "command_count": len(commands),
            "commands_per_declared_wall_second": _rate(len(commands), elapsed),
            "initial_trace_row_is_command": False,
            "scope": "count_ratio_over_declared_attempt_wall_elapsed_not_a_stream_entry_frequency",
        },
        "command_dt_arguments": {
            "unit": "seconds_as_passed_to_hook",
            **_statistics([row["dt_seconds"] for row in commands]),
        },
        "streams": streams,
        "phase_events": {
            "status": "recorded" if rich else "not_recorded_schema1",
            "rows": attempt["phase_events"] if rich else [],
        },
        "phase_bucket_rules": {
            "start_warmup": "whole row has command_before=command_after=0 and both raw phase flags false",
            "normal_pre_end": "whole row has identical before/after raw phase flags, both false, excluding start_warmup",
            "ending": "whole row has identical before/after raw phase flags and level_end_animation_started true",
            "crosses_phase_boundary": "raw phase_before differs from raw phase_after; row remains unsplit",
            "unknown": "raw phase profile unavailable or not covered by the structural rules",
        },
        "statistics_method": {
            "quantiles": QUANTILE_METHOD,
            "sum": "math.fsum",
            "empty_samples": "null quantiles/mean/min/max and zero sum",
            "confidence_intervals": "not_estimated",
        },
        "authentication_status": "not_authenticated",
        "render_fps": "not_measured",
        "cpu_cost": "not_measured",
        "recording_overhead": "not_attributed",
        "hardware_latency": "not_measured",
        "difficulty_calibration": "not_established",
        "m1_gate": "not_established_by_cadence_diagnostics",
        "limitations": [
            "Supplied native origin is not authenticated; synthetic fixtures remain labelled synthetic.",
            "Paired durations include original engine work, other hooks, instrumentation and scheduling/waits; no cause or CPU cost is assigned.",
            "Nested intervals overlap. Inclusive sums and unions are separate, and update/Scheduler streams must never be added together.",
            "Original/delivered dt sums are sums of hook arguments, not calibrated elapsed simulation time or capture overhead.",
            "Whole-row phase buckets use recorded raw flags and command counters; no unrecorded command entry time or partial-row allocation is invented.",
            "Declared count/wall ratios and observed entry-interval rates have different numerators and scopes; neither is render FPS.",
            "Late enclosing callback exits are retained and separately clipped at the declared native terminal wall time.",
        ],
    }
    if capture["schema_version"] >= 4:
        report["attempt"]["input_delivery"] = attempt["input_delivery"]
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != source_sha256:
        raise ValueError("Capture bytes changed during cadence analysis")
    report["source_bytes_unchanged_during_analysis"] = True
    return report
