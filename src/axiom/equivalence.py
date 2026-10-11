"""Bounded comparison of two declared synthetic native delivery routes.

File inspection establishes consistency of recorded subsets, not authenticity,
OS input equivalence, human authorship or the complete state of the game.
"""

import hashlib
from pathlib import Path

from .native import load_native_capture, native_event_signature


def _difference(left, right):
    first = next((index for index, pair in enumerate(zip(left, right)) if pair[0] != pair[1]), None)
    if first is None and len(left) != len(right):
        first = min(len(left), len(right))
    return {
        "equal": left == right,
        "owned_record_count": len(left),
        "ui_record_count": len(right),
        "first_difference": None
        if first is None
        else {
            "record_index": first,
            "owned": left[first] if first < len(left) else None,
            "ui": right[first] if first < len(right) else None,
        },
    }


def _projection(rows, excluded=()):
    return [
        native_event_signature({key: value for key, value in row.items() if key not in excluded})
        for row in rows
    ]


def _ui_queue_witnesses(capture):
    """Require an actual enqueue, processing receipt and enclosed native request.

    Matching command counters alone cannot demonstrate queue delivery. Keep the
    raw timestamp and step in the witness and use paired wall intervals only to
    establish order/enclosure within this capture, never across captures.
    """
    attempt = capture["attempt"]
    callbacks = [
        row for row in attempt["delivery_events"] if row["event"] in {"UILayer::keyDown", "UILayer::keyUp"}
    ]
    processors = [
        row for row in attempt["delivery_events"] if row["event"] == "GJBaseGameLayer::processQueuedButtons"
    ]
    requests = [row for row in attempt["inputs"] if row["phase"] == "requested"]
    planned = [
        row
        for row in attempt["planned_inputs"]
        if row["command_index"] <= attempt["terminal"]["command_index"]
    ]
    witnesses = []
    for intended in planned:
        matched = None
        for callback in callbacks:
            if callback["command_index"] != intended["command_index"] or not callback["in_command"]:
                continue
            if callback["event"] != ("UILayer::keyDown" if intended["pressed"] else "UILayer::keyUp"):
                continue
            if callback["arguments"]["key_code"] != 32:
                continue
            if callback["arguments"]["timestamp"] != callback["layer_timestamp_before"]:
                continue
            before, after = callback["queue_before"], callback["queue_after"]
            if len(after) != len(before) + 1 or after[:-1] != before:
                continue
            queued = after[-1]
            if any(queued[key] != intended[key] for key in ("button", "player", "pressed")):
                continue
            if queued["timestamp"] != callback["arguments"]["timestamp"]:
                continue
            for processor in processors:
                if processor["wall_enter_ns"] < callback["wall_exit_ns"]:
                    continue
                if queued not in processor["queue_before"] or queued in processor["queue_after"]:
                    continue
                request = next(
                    (
                        row
                        for row in requests
                        if processor["wall_enter_ns"] <= row["wall_time_ns"] <= processor["wall_exit_ns"]
                        and row["command_index"] == processor["command_index"]
                        and row["in_command"] == processor["in_command"]
                        and all(row[key] == intended[key] for key in ("button", "player", "pressed"))
                    ),
                    None,
                )
                if request is None:
                    continue
                matched = {
                    "callback_sequence": callback["sequence"],
                    "processing_sequence": processor["sequence"],
                    "request_sequence": request["sequence"],
                    "callback_command_index": callback["command_index"],
                    "processing_command_index": processor["command_index"],
                    "request_command_index": request["command_index"],
                    "queued_button": queued,
                    "clear_input_queue": processor["arguments"]["clear_input_queue"],
                }
                break
            if matched is not None:
                break
        witnesses.append({"planned_input": intended, "matched": matched is not None, "witness": matched})
    return {
        "all_planned_prefix_events_witnessed": bool(planned) and all(row["matched"] for row in witnesses),
        "planned_prefix_count": len(planned),
        "callback_count": len(callbacks),
        "processing_count": len(processors),
        "witnesses": witnesses,
    }


def compare_native_delivery(owned_path: str | Path, ui_path: str | Path) -> dict:
    """Compare full-start captures of one plan delivered through two entry points.

    This intentionally does not relax the existing same-route repeat comparator.
    Nonempty P1 space-button plans are the only supported UI-driver domain.
    """
    paths = [Path(owned_path), Path(ui_path)]
    owned, ui = [load_native_capture(path) for path in paths]
    if any(capture["schema_version"] not in {4, 5} for capture in (owned, ui)):
        raise ValueError("Delivery comparison requires schema 4 or 5 captures")
    if owned["schema_version"] != ui["schema_version"]:
        raise ValueError("Delivery comparison requires the same capture schema_version")
    if owned["attempt"]["id"] == ui["attempt"]["id"]:
        raise ValueError("Delivery comparison requires distinct attempts")
    for capture, driver in ((owned, "owned-pre-command"), (ui, "scheduled-ui-callback")):
        attempt = capture["attempt"]
        if attempt["start_kind"] != "level_start" or attempt["input_source"] != "replay":
            raise ValueError("Delivery comparison requires declared full-start synthetic replay attempts")
        if attempt["input_delivery"]["driver"] != driver:
            raise ValueError(f"Expected input delivery driver {driver}")
    for key in ("challenge", "environment", "collector", "state_fields", "layer_state_fields"):
        if owned[key] != ui[key]:
            raise ValueError(f"Incompatible delivery comparison identity: {key}")
    if native_event_signature(owned["object_watches"]) != native_event_signature(ui["object_watches"]):
        raise ValueError("Incompatible delivery comparison object watches")
    plan = owned["attempt"]["planned_inputs"]
    if plan != ui["attempt"]["planned_inputs"]:
        raise ValueError("Delivery comparison requires the same declared logical input plan")
    if not plan or any(row["player"] != 1 or row["button"] != 1 for row in plan):
        raise ValueError("Delivery comparison requires a nonempty P1 button-1 plan")
    left, right = owned["attempt"], ui["attempt"]
    streams = {
        "native_input_receipts": (
            _projection(left["inputs"], {"wall_time_ns", "source"}),
            _projection(right["inputs"], {"wall_time_ns", "source"}),
        ),
        "process_commands_trace": (_projection(left["trace"]), _projection(right["trace"])),
        "delivered_updates": (
            _projection(left["updates"], {"original_dt_seconds"}),
            _projection(right["updates"], {"original_dt_seconds"}),
        ),
        "delivered_scheduler_updates": (
            _projection(left["scheduler_updates"], {"original_dt_seconds"}),
            _projection(right["scheduler_updates"], {"original_dt_seconds"}),
        ),
        "native_ending_phase_events": (_projection(left["phase_events"]), _projection(right["phase_events"])),
        "selected_mechanic_events": (
            _projection(left["mechanic_events"]),
            _projection(right["mechanic_events"]),
        ),
        "terminal_snapshot": (
            _projection([left["terminal"]], {"wall_elapsed_seconds"}),
            _projection([right["terminal"]], {"wall_elapsed_seconds"}),
        ),
    }
    diagnostics = {name: _difference(*pair) for name, pair in streams.items()}
    queue = _ui_queue_witnesses(ui)
    checks = {name + "_equal": value["equal"] for name, value in diagnostics.items()}
    checks["ui_plan_queue_path_witnessed"] = queue["all_planned_prefix_events_witnessed"]
    consistent = all(checks.values())
    return {
        "schema_version": 1,
        "kind": "native_delivery_comparison",
        "protocol": "synthetic-owned-vs-ui-queue-p1-button1-v1",
        "status": "recorded_delivery_subset_consistent"
        if consistent
        else "recorded_delivery_equivalence_not_established",
        "checks": checks,
        "diagnostics": diagnostics,
        "ui_queue_path": queue,
        "captures": [
            {
                "role": role,
                "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "attempt_id": capture["attempt"]["id"],
                "input_delivery": capture["attempt"]["input_delivery"],
                "origin": capture["provenance"]["origin"],
                "replay_sha256": capture["attempt"]["replay_sha256"],
            }
            for role, path, capture in zip(("owned", "ui"), paths, (owned, ui))
        ],
        "challenge": owned["challenge"],
        "collector": owned["collector"],
        "object_watch_identity": native_event_signature(owned["object_watches"]),
        "planned_inputs": plan,
        "suppressed_request_diagnostics": {
            "owned": _projection(left["blocked_inputs"], {"wall_time_ns"}),
            "ui": _projection(right["blocked_inputs"], {"wall_time_ns"}),
            "included_in_delivered_consistency": False,
            "all_actual_input_receipts_included": True,
        },
        "normalization": [
            "Receipt source labels differ by declared route; raw source labels remain in captures.",
            "Runtime object UIDs and monotonic wall times are excluded from cross-capture equality.",
            "Original update dt is diagnostic under a clock intervention; delivered dt is compared.",
            "Command indices, contexts, queue timestamps, native results and extra actual receipts are retained.",
        ],
        "ordinary_os_input_equivalence": "not_established",
        "human_authorship": "not_established",
        "m1_gate": "not_established_by_file_inspection",
        "limitations": [
            "This compares supplied records and does not authenticate their origin.",
            "UILayer callbacks scheduled at processCommands entry bypass Windows, devices and the dispatcher.",
            "Selected hooks, player fields and watched objects do not constitute complete game state.",
            "Fixed scheduler timing is an experimental intervention, not unmodified ordinary play.",
        ],
    }
