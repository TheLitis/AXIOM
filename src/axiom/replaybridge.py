"""Explicit bridge from observed requests/cadence to a synthetic intervention.

Exact selected records can be compared across the declared collector transition.
The bridge does not replay UI callbacks or establish OS input equivalence.
"""

from copy import deepcopy
from pathlib import Path
from typing import Sequence

from .native import (
    KEYBOARD_EVENTS,
    MAX_COMPARISON_FILES,
    TOUCH_EVENTS,
    canonical_sha256,
    compare_native_captures,
    delivery_timestamp_signature,
    load_native_capture,
    native_event_signature,
    validate_recorded_replay_plan,
)
from .validation import read_json


def _observed_source(capture: dict) -> None:
    attempt = capture["attempt"]
    if (
        capture["schema_version"] != 5
        or capture["environment"]["clocks"]["clock_policy"] != "native"
        or attempt["input_delivery"]["driver"] != "none"
        or attempt["input_source"] != "unknown"
        or attempt["start_kind"] != "level_start"
        or attempt["terminal"]["outcome"] != "completed"
    ):
        raise ValueError("Recorded replay source requires completed full-start schema 5 native observation")


def _environment_transition(source: dict, target: dict, *, recorded: bool) -> None:
    """Allow only explicit adapter/collector source changes and named clock policy."""
    left, right = source["collector"], target["collector"]
    if any(left[key] != right[key] for key in ("id", "version", "sdk_commit", "bindings_commit")):
        raise ValueError("Recorded bridge collector id/version/SDK/bindings must remain equal")
    expected_collector = {
        **left,
        "source_commit": right["source_commit"],
        "source_tree_sha256": right["source_tree_sha256"],
    }
    if right != expected_collector:
        raise ValueError("Unsupported recorded bridge collector change")
    original, candidate = deepcopy(source["environment"]), deepcopy(target["environment"])
    expected_clocks = deepcopy(original["clocks"])
    if recorded:
        expected_clocks.update(
            clock_policy="recorded-scheduler-stream",
            intervention_hook="CCScheduler::update",
            step_numerator=0,
            step_denominator=1,
        )
    if candidate["clocks"] != expected_clocks:
        raise ValueError("Recorded bridge clock identity differs from the explicit transition")
    candidate["clocks"] = original["clocks"]
    candidate["adapter_binary_sha256"] = original["adapter_binary_sha256"]
    source_mods = {row["id"]: row for row in original["mods"]}
    adapter_id = left["id"]
    if (
        adapter_id not in source_mods
        or source_mods[adapter_id]["binary_sha256"] != original["adapter_binary_sha256"]
    ):
        raise ValueError("Source adapter mod identity is missing or inconsistent")
    target_adapter = next((row for row in target["environment"]["mods"] if row["id"] == adapter_id), None)
    if (
        target_adapter is None
        or target_adapter["binary_sha256"] != target["environment"]["adapter_binary_sha256"]
    ):
        raise ValueError("Target adapter mod identity is missing or inconsistent")
    for row in candidate["mods"]:
        if row["id"] == adapter_id:
            row["binary_sha256"] = source_mods[adapter_id]["binary_sha256"]
    if candidate != original:
        raise ValueError("Recorded bridge may change only adapter hashes and explicit clocks")
    for key in ("challenge", "state_fields", "layer_state_fields"):
        left_value, right_value = source[key], target[key]
        if key == "challenge":
            left_value = {name: value for name, value in left_value.items() if name != "environment_id"}
            right_value = {name: value for name, value in right_value.items() if name != "environment_id"}
        if left_value != right_value:
            raise ValueError(f"Recorded bridge identity differs: {key}")
    if native_event_signature(source["object_watches"]) != native_event_signature(target["object_watches"]):
        raise ValueError("Recorded bridge watched-object selectors differ")


def _source_schedule_and_batches(source: dict) -> tuple[list, list, list]:
    attempt = source["attempt"]
    schedulers, updates = attempt["scheduler_updates"], attempt["updates"]
    if not schedulers or any(row["parent_sequence"] is not None for row in schedulers):
        raise ValueError("Recorded replay source requires a nonempty nonnested scheduler stream")
    counts = [0] * len(schedulers)
    for row in updates:
        if row["parent_sequence"] is not None or row["scheduler_sequence"] is None:
            raise ValueError("Recorded replay source requires nonnested scheduler-associated updates")
        counts[row["scheduler_sequence"]] += 1
    schedule = [
        {
            **{
                key: row[key]
                for key in (
                    "sequence",
                    "delivered_dt_seconds",
                    "command_index_before",
                    "command_index_after",
                    "phase_before",
                    "phase_after",
                )
            },
            "update_count": count,
        }
        for row, count in zip(schedulers, counts)
    ]
    requests = [row for row in attempt["inputs"] if row["phase"] == "requested"]
    batches, consumed = [], []
    for processor in attempt["delivery_events"]:
        if processor["event"] != "GJBaseGameLayer::processQueuedButtons":
            continue
        enclosed = [
            row
            for row in requests
            if processor["wall_enter_ns"] <= row["wall_time_ns"] <= processor["wall_exit_ns"]
            and all(
                row[key] == processor[key]
                for key in ("command_index", "in_command", "update_sequence", "scheduler_sequence")
            )
        ]
        if not enclosed or not processor["in_command"]:
            raise ValueError("Source processing entry lacks enclosed in-command requested receipts")
        keys = ("player", "button", "pressed")
        if [{key: row[key] for key in keys} for row in processor["queue_before"]] != [
            {key: row[key] for key in keys} for row in enclosed
        ] or processor["queue_after"]:
            raise ValueError("Source processing queue and complete enclosed requests differ")
        consumed.extend(enclosed)
        batches.append(
            {
                "source_delivery_sequence": processor["sequence"],
                **{key: processor[key] for key in ("command_index", "update_sequence", "scheduler_sequence")},
                **processor["arguments"],
                "inputs": [
                    {"source_input_sequence": row["sequence"], **{key: row[key] for key in keys}}
                    for row in enclosed
                ],
            }
        )
    if consumed != requests:
        raise ValueError("Every source request must belong to exactly one ordered processing batch")
    inputs = [{key: row[key] for key in ("command_index", "player", "button", "pressed")} for row in requests]
    return schedule, batches, inputs


def export_recorded_replay_plan(source_path: str | Path, target_baseline_path: str | Path) -> dict:
    """Freeze all observed requests and recorded cadence for a named target build."""
    source, source_hash = read_json(source_path)
    source = load_native_capture(source_path)
    target = load_native_capture(target_baseline_path)
    _observed_source(source)
    _observed_source(target)
    if source["attempt"]["id"] == target["attempt"]["id"]:
        raise ValueError("Target baseline must be a distinct attempt")
    if any(
        row["event"] in KEYBOARD_EVENTS | TOUCH_EVENTS for row in target["attempt"]["delivery_events"]
    ) or any(row["pressed"] for row in target["attempt"]["inputs"]):
        raise ValueError("Target baseline must have no recorded UI entries or pressed input receipts")
    _environment_transition(source, target, recorded=False)
    environment = deepcopy(target["environment"])
    environment["clocks"].update(
        clock_policy="recorded-scheduler-stream",
        intervention_hook="CCScheduler::update",
        step_numerator=0,
        step_denominator=1,
    )
    schedule, batches, inputs = _source_schedule_and_batches(source)
    plan = {
        "schema_version": 2,
        "kind": "native_recorded_replay",
        "clock": "recorded_scheduler_stream",
        "level_sha256": source["challenge"]["level_sha256"],
        "environment_sha256": canonical_sha256(environment),
        "source_capture_sha256": source_hash,
        "source_environment_sha256": source["environment_sha256"],
        "target_collector": deepcopy(target["collector"]),
        "scheduler_updates": schedule,
        "processing_batches": batches,
        "inputs": inputs,
    }
    return validate_recorded_replay_plan(plan)


def _difference(left: list, right: list) -> dict:
    first = next((index for index, pair in enumerate(zip(left, right)) if pair[0] != pair[1]), None)
    if first is None and len(left) != len(right):
        first = min(len(left), len(right))
    return {
        "equal": left == right,
        "source_record_count": len(left),
        "replay_record_count": len(right),
        "first_difference": None
        if first is None
        else {
            "record_index": first,
            "source": left[first] if first < len(left) else None,
            "replay": right[first] if first < len(right) else None,
        },
    }


def _project(rows: list, excluded: set = frozenset()) -> list:
    return [
        native_event_signature({key: value for key, value in row.items() if key not in excluded})
        for row in rows
    ]


def _cleanup_interference(source: dict, replay: dict) -> dict:
    """Keep every suppression, allowing only an enclosed initial cleanup release."""
    blocked = replay["attempt"]["blocked_inputs"]
    if not blocked:
        return {
            "allowed": True,
            "status": "no_suppressed_requests",
            "record_count": 0,
            "witness": None,
            "all_original_blocked_inputs": blocked,
        }
    queued = {"button": 1, "pressed": False, "player": 1, "step": 0, "timestamp": 0}
    source_processors = [
        row
        for row in source["attempt"]["delivery_events"]
        if row["event"] == "GJBaseGameLayer::processQueuedButtons" and row["command_index"] == 1
    ]
    processors = [
        row
        for row in replay["attempt"]["delivery_events"]
        if row["event"] == "GJBaseGameLayer::processQueuedButtons" and row["command_index"] == 1
    ]
    witness = None
    if len(blocked) == len(source_processors) == len(processors) == 1:
        row, original, processor = blocked[0], source_processors[0], processors[0]
        if (
            original["queue_before"].count(queued) == 1
            and processor["queue_before"] == [queued]
            and row["command_index"] == 1
            and row["player"] == 1
            and row["button"] == 1
            and row["pressed"] is False
            and row["source"] == "unknown"
            and processor["wall_enter_ns"] <= row["wall_time_ns"] <= processor["wall_exit_ns"]
        ):
            witness = {
                "source_processing_sequence": original["sequence"],
                "replay_processing_sequence": processor["sequence"],
                "blocked_sequence": row["sequence"],
                "raw_initial_queued_release": queued,
                "blocked_receipt": row,
                "relationship_scope": "exact_initial_queue_body_and_paired_processor_enclosure_only",
            }
    return {
        "allowed": witness is not None,
        "status": "one_initial_cleanup_release_witnessed"
        if witness is not None
        else "additional_or_ambiguous_suppressed_interference",
        "record_count": len(blocked),
        "witness": witness,
        "all_original_blocked_inputs": blocked,
    }


def compare_recorded_replay(
    source_path: str | Path, plan_path: str | Path, replay_paths: Sequence[str | Path]
) -> dict:
    """Require both exact source correspondence and independent same-route repeats."""
    if isinstance(replay_paths, (str, bytes, Path)) or not 2 <= len(replay_paths) <= MAX_COMPARISON_FILES:
        raise ValueError("Recorded comparison requires two to sixteen fresh replay captures")
    source = load_native_capture(source_path)
    _, source_hash = read_json(source_path)
    _observed_source(source)
    plan, plan_hash = read_json(plan_path)
    validate_recorded_replay_plan(plan)
    if (
        plan["source_capture_sha256"] != source_hash
        or plan["source_environment_sha256"] != source["environment_sha256"]
        or plan["level_sha256"] != source["challenge"]["level_sha256"]
    ):
        raise ValueError("Recorded plan source identity differs from the supplied capture")
    schedule, batches, inputs = _source_schedule_and_batches(source)
    if any(
        plan[key] != expected
        for key, expected in (
            ("scheduler_updates", schedule),
            ("processing_batches", batches),
            ("inputs", inputs),
        )
    ):
        raise ValueError("Recorded plan is not the exact complete extraction of its bound source")
    captures = [load_native_capture(path) for path in replay_paths]
    if any(capture["schema_version"] != 6 for capture in captures):
        raise ValueError("Recorded source comparison requires schema 6 replay captures")
    for capture in captures:
        _environment_transition(source, capture, recorded=True)
        if capture["attempt"]["id"] == source["attempt"]["id"]:
            raise ValueError("Recorded replay must be distinct from its source attempt")
        if capture["attempt"]["replay_bridge"] != plan or capture["attempt"]["replay_sha256"] != plan_hash:
            raise ValueError("Replay capture differs from its supplied raw recorded plan")
    repeat = compare_native_captures(replay_paths)
    left = source["attempt"]
    comparisons = []
    for path, capture in zip(replay_paths, captures):
        right = capture["attempt"]
        streams = {
            "all_actual_requests": (
                _project(
                    [row for row in left["inputs"] if row["phase"] == "requested"], {"wall_time_ns", "source"}
                ),
                _project(
                    [row for row in right["inputs"] if row["phase"] == "requested"],
                    {"wall_time_ns", "source"},
                ),
            ),
            "all_actual_player_receipts": (
                _project(
                    [row for row in left["inputs"] if row["phase"] != "requested"], {"wall_time_ns", "source"}
                ),
                _project(
                    [row for row in right["inputs"] if row["phase"] != "requested"],
                    {"wall_time_ns", "source"},
                ),
            ),
            "all_processing_entry_contexts": (
                _project(
                    [
                        row
                        for row in left["delivery_events"]
                        if row["event"] == "GJBaseGameLayer::processQueuedButtons"
                    ],
                    {
                        "sequence",
                        "queue_before",
                        "queue_after",
                        "layer_timestamp_before",
                        "layer_timestamp_after",
                    },
                ),
                _project(
                    [
                        row
                        for row in right["delivery_events"]
                        if row["event"] == "GJBaseGameLayer::processQueuedButtons"
                    ],
                    {
                        "sequence",
                        "queue_before",
                        "queue_after",
                        "layer_timestamp_before",
                        "layer_timestamp_after",
                    },
                ),
            ),
            "selected_trajectory": (
                [
                    {key: row[key] for key in ("command_index", "state", "watched_objects")}
                    for row in left["trace"]
                ],
                [
                    {key: row[key] for key in ("command_index", "state", "watched_objects")}
                    for row in right["trace"]
                ],
            ),
            "command_arguments": (
                [
                    {key: row[key] for key in ("command_index", "dt_seconds", "is_half_tick", "is_last_tick")}
                    for row in left["trace"]
                ],
                [
                    {key: row[key] for key in ("command_index", "dt_seconds", "is_half_tick", "is_last_tick")}
                    for row in right["trace"]
                ],
            ),
            "command_phase_and_context": (
                [
                    {
                        key: row[key]
                        for key in ("command_index", "phase", "update_sequence", "scheduler_sequence")
                    }
                    for row in left["trace"]
                ],
                [
                    {
                        key: row[key]
                        for key in ("command_index", "phase", "update_sequence", "scheduler_sequence")
                    }
                    for row in right["trace"]
                ],
            ),
            "delivered_updates": (
                _project(left["updates"], {"original_dt_seconds"}),
                _project(right["updates"], {"original_dt_seconds"}),
            ),
            "delivered_scheduler_updates": (
                _project(left["scheduler_updates"], {"original_dt_seconds"}),
                _project(right["scheduler_updates"], {"original_dt_seconds"}),
            ),
            "native_phase_events": (_project(left["phase_events"]), _project(right["phase_events"])),
            "strict_mechanic_events": (_project(left["mechanic_events"]), _project(right["mechanic_events"])),
            "terminal": (
                _project([left["terminal"]], {"wall_elapsed_seconds"}),
                _project([right["terminal"]], {"wall_elapsed_seconds"}),
            ),
        }
        diagnostics = {name: _difference(*pair) for name, pair in streams.items()}
        checks = {name + "_equal": value["equal"] for name, value in diagnostics.items()}
        checks["no_replay_ui_callback_entries"] = not any(
            row["event"] in KEYBOARD_EVENTS | TOUCH_EVENTS for row in right["delivery_events"]
        )
        interference = _cleanup_interference(source, capture)
        checks["unknown_extra_input_interference_absent"] = interference["allowed"]
        comparisons.append(
            {
                "attempt_id": right["id"],
                "source_sha256": read_json(path)[1],
                "checks": checks,
                "diagnostics": diagnostics,
                "consistent": all(checks.values()),
                "source_vs_replay_delivery_diagnostics": _difference(
                    _project(left["delivery_events"]), _project(right["delivery_events"])
                ),
                "raw_timestamp_diagnostics": _difference(
                    delivery_timestamp_signature(left["delivery_events"]),
                    delivery_timestamp_signature(right["delivery_events"]),
                ),
                "original_scheduler_dt_diagnostics": _difference(
                    [row["original_dt_seconds"] for row in left["scheduler_updates"]],
                    [row["original_dt_seconds"] for row in right["scheduler_updates"]],
                ),
                "original_update_dt_diagnostics": _difference(
                    [row["original_dt_seconds"] for row in left["updates"]],
                    [row["original_dt_seconds"] for row in right["updates"]],
                ),
                "blocked_unknown_input_diagnostics": right["blocked_inputs"],
                "input_interference_qualification": interference,
                "all_original_input_receipts": right["inputs"],
                "clock_identity": capture["environment"]["clocks"],
            }
        )
    source_consistent = all(row["consistent"] for row in comparisons)
    repeated_consistent = repeat["status"] == "recorded_subset_consistent"
    return {
        "schema_version": 1,
        "kind": "native_recorded_replay_comparison",
        "protocol": "recorded-source-to-owned-processing-scheduler-v1",
        "status": "recorded_source_subset_and_repeats_consistent"
        if source_consistent and repeated_consistent
        else "recorded_source_replay_consistency_not_established",
        "source_correspondence_consistent": source_consistent,
        "same_route_repeats_consistent": repeated_consistent,
        "source_capture_sha256": source_hash,
        "plan_source_sha256": plan_hash,
        "source_attempt_id": left["id"],
        "source_capture_schema_version": 5,
        "replay_capture_schema_version": 6,
        "replay_count": len(captures),
        "plan": plan,
        "source_collector": source["collector"],
        "source_environment": source["environment"],
        "target_environment": captures[0]["environment"],
        "collector_transition": {
            "source": source["collector"],
            "target": plan["target_collector"],
            "changed_fields_allowed": ["source_commit", "source_tree_sha256"],
        },
        "comparisons": comparisons,
        "same_route_repeat_comparison": repeat,
        "source_ui_entry_observations": [
            row for row in left["delivery_events"] if row["event"] in KEYBOARD_EVENTS | TOUCH_EVENTS
        ],
        "source_input_receipts": left["inputs"],
        "normalization": [
            "Requested and PlayerObject actor receipts remain separate; sequence, channel, native return and contexts are exact.",
            "Receipt source labels, wall time, runtime object IDs and original incoming update/Scheduler dt are excluded from source equality.",
            "Original incoming update/Scheduler dt and absolute callback/queue time remain separate diagnostics; delivered cadence is exact.",
            "Source UI entries and queue snapshots are retained diagnostics; processing event ordinals differ by route while all processing contexts are compared.",
            "Every blocked request is retained; this bridge allows zero suppressions or one specifically witnessed initial cleanup release and rejects additional interference.",
        ],
        "clock_intervention": "recorded_scheduler_delivered_dt_stream_not_native_wall_cadence",
        "processing_entry_rule": "first_actual_entry_for_batch_command_must_match_context_and_arguments_no_later_rescue_no_empty_source_ordinal_claim",
        "authentication_status": "not_authenticated",
        "source_input_provenance": "unknown",
        "replay_input_provenance": "synthetic-scheduled",
        "ordinary_os_input_equivalence": "not_established",
        "human_authorship": "separate_statement_only",
        "complete_state_determinism": "not_established",
        "m1_gate": "not_established_by_file_inspection",
    }
