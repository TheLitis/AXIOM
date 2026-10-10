"""Inspect native observer captures without authenticating their reported origin.

The collector's clock is a processCommands call index, not a physics tick. Exact
comparison covers only recorded inputs, call arguments and selected player fields.
"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any, Sequence

from .validation import challenge_identity, finite, mapping, read_json, sha256, string

MAX_TRACE_RECORDS = 20_001
MAX_INPUT_RECORDS = 12_000
MAX_PLANNED_INPUTS = 4_000
MAX_COMPARISON_FILES = 16
MAX_UPDATE_RECORDS = 20_000
MAX_PHASE_EVENTS = 256
MAX_MECHANIC_EVENTS = 4_096
MAX_DELIVERY_EVENTS = 4_096
MAX_OBJECT_WATCHES = 8
MAX_QUEUED_BUTTONS = 256
INPUT_POLICY = "process-commands-pre-hook-owned-input-v1"
INPUT_POLICY_V4 = "process-commands-scheduled-delivery-v2"
LEGACY_INPUT_POLICY = "process-commands-pre-hook-v1"
PLAYER_FIELDS = frozenset({"x", "y", "y_velocity", "rotation", "is_dead", "mode"})
PLAYER_FIELDS_V3 = PLAYER_FIELDS | {"gravity_inverted", "vehicle_size", "player_speed"}
PLAYER_FIELDS_V4 = PLAYER_FIELDS_V3 | {"is_on_ground", "is_on_slope"}
LAYER_FIELDS_V3 = frozenset({"dual_active"})
PHASE_FIELDS = frozenset({"level_end_animation_started", "has_completed_level"})


def canonical_sha256(value: Any) -> str:
    """Digest compact sorted-key UTF-8 JSON (no whitespace or nonfinite values)."""
    try:
        raw = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise ValueError("Cannot compute canonical JSON identity") from error
    return hashlib.sha256(raw).hexdigest()


def _fields(
    value: Any,
    name: str,
    required: set[str] | frozenset[str],
    optional: set[str] | frozenset[str] = frozenset(),
) -> dict:
    data = mapping(value, name)
    missing = required - data.keys()
    unexpected = data.keys() - required - optional
    if missing or unexpected:
        details = []
        if missing:
            details.append("missing " + ", ".join(sorted(missing)))
        if unexpected:
            details.append("unknown " + ", ".join(sorted(unexpected)))
        raise ValueError(f"{name}: {'; '.join(details)}")
    return data


def _int(value: Any, name: str, minimum: int = 0, maximum: int = 2**63 - 1) -> int:
    # Preserve nanosecond precision. The shared numeric validator intentionally
    # converts via float and is unsuitable for integer counters above 2**53.
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    return value


def _bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a JSON boolean")
    return value


def _text(value: Any, name: str) -> str:
    result = string(value, name)
    if result != result.strip():
        raise ValueError(f"{name} must be trimmed")
    return result


def _player(value: Any, name: str, *, extended: bool = False, contacts: bool = False) -> dict:
    state = _fields(
        value, name, PLAYER_FIELDS_V4 if contacts else PLAYER_FIELDS_V3 if extended else PLAYER_FIELDS
    )
    for key in ("x", "y", "y_velocity", "rotation"):
        finite(state[key], f"{name}.{key}")
    _bool(state["is_dead"], f"{name}.is_dead")
    _text(state["mode"], f"{name}.mode")
    if extended:
        _bool(state["gravity_inverted"], f"{name}.gravity_inverted")
        for key in ("vehicle_size", "player_speed"):
            finite(state[key], f"{name}.{key}")
    if contacts:
        for key in ("is_on_ground", "is_on_slope"):
            _bool(state[key], f"{name}.{key}")
    return state


def _state(value: Any, name: str, *, extended: bool = False, contacts: bool = False) -> dict:
    state = _fields(value, name, {"player1", "player2"} | (LAYER_FIELDS_V3 if extended else set()))
    _player(state["player1"], f"{name}.player1", extended=extended, contacts=contacts)
    if state["player2"] is not None:
        _player(state["player2"], f"{name}.player2", extended=extended, contacts=contacts)
    if extended:
        _bool(state["dual_active"], f"{name}.dual_active")
    return state


def _phase(value: Any, name: str) -> dict:
    phase = _fields(value, name, PHASE_FIELDS)
    for key, value in phase.items():
        _bool(value, f"{name}.{key}")
    return phase


def _context_id(value: Any, name: str, records: list[dict]) -> int | None:
    return None if value is None else _int(value, name, maximum=len(records) - 1)


def _float32(value: float) -> float:
    return struct.unpack("f", struct.pack("f", value))[0]


def _validate_update_stream(
    rows: Any, name: str, terminal_index: int, clocks: dict, scheduler: bool
) -> list[dict]:
    if not isinstance(rows, list) or len(rows) > MAX_UPDATE_RECORDS:
        raise ValueError(f"{name} must contain at most {MAX_UPDATE_RECORDS} paired records")
    previous_enter = -1
    previous_before = -1
    stack: list[int] = []
    for index, value in enumerate(rows):
        row = _fields(
            value,
            f"{name}[{index}]",
            {
                "sequence",
                "parent_sequence",
                "original_dt_seconds",
                "delivered_dt_seconds",
                "command_index_before",
                "command_index_after",
                "phase_before",
                "phase_after",
                "wall_enter_ns",
                "wall_exit_ns",
            }
            | (set() if scheduler else {"scheduler_sequence"}),
        )
        if _int(row["sequence"], f"{name}.sequence") != index:
            raise ValueError(f"{name} sequence must start at zero and be contiguous")
        parent = row["parent_sequence"]
        if parent is not None:
            _int(parent, f"{name}.parent_sequence", maximum=index - 1)
        original = finite(row["original_dt_seconds"], f"{name}.original_dt_seconds", minimum=0, maximum=60)
        delivered = finite(row["delivered_dt_seconds"], f"{name}.delivered_dt_seconds", minimum=0, maximum=60)
        intervention = "fixed-scheduler-240" if scheduler else "fixed-base-60"
        expected = (
            _float32(1 / clocks["step_denominator"]) if clocks["clock_policy"] == intervention else original
        )
        if delivered != expected:
            raise ValueError(f"{name} delivered dt does not match its declared clock policy")
        before = _int(row["command_index_before"], f"{name}.command_index_before", maximum=terminal_index)
        after = _int(
            row["command_index_after"], f"{name}.command_index_after", minimum=before, maximum=terminal_index
        )
        enter = _int(row["wall_enter_ns"], f"{name}.wall_enter_ns")
        exit_time = _int(row["wall_exit_ns"], f"{name}.wall_exit_ns", minimum=enter)
        if enter < previous_enter or before < previous_before:
            raise ValueError(f"{name} entry timestamps and command indices must be nondecreasing")
        previous_enter, previous_before = enter, before
        _phase(row["phase_before"], f"{name}.phase_before")
        _phase(row["phase_after"], f"{name}.phase_after")
        while stack and stack[-1] != parent:
            completed = rows[stack.pop()]
            if completed["wall_exit_ns"] > enter or completed["command_index_after"] > before:
                raise ValueError(f"{name} sibling records overlap or parent nesting is inconsistent")
        if parent is not None:
            if not stack:
                raise ValueError(f"{name} parent does not identify an enclosing entry-order record")
            enclosing = rows[parent]
            if (
                enter < enclosing["wall_enter_ns"]
                or exit_time > enclosing["wall_exit_ns"]
                or before < enclosing["command_index_before"]
                or after > enclosing["command_index_after"]
            ):
                raise ValueError(f"{name} child interval is outside its parent")
        stack.append(index)
    return rows


def _validate_rich_observations(attempt: dict, clocks: dict, terminal_wall: float) -> None:
    terminal = attempt["terminal"]
    updates = _validate_update_stream(attempt["updates"], "updates", terminal["command_index"], clocks, False)
    schedulers = _validate_update_stream(
        attempt["scheduler_updates"], "scheduler_updates", terminal["command_index"], clocks, True
    )
    # The producer opens records only while the run is nonterminal. Enclosing
    # hooks can exit after the terminal callback; their late exits are valid.
    # Use the same one-microsecond serialization allowance as the input clock.
    terminal_entry_limit = (terminal_wall + 1e-6) * 1_000_000_000
    for name, records in (("updates", updates), ("scheduler_updates", schedulers)):
        if any(row["wall_enter_ns"] > terminal_entry_limit for row in records):
            raise ValueError(f"{name} entry is after the reported terminal callback")
    for row in updates:
        scheduler = _context_id(row["scheduler_sequence"], "update.scheduler_sequence", schedulers)
        if scheduler is not None:
            enclosing = schedulers[scheduler]
            if (
                row["wall_enter_ns"] < enclosing["wall_enter_ns"]
                or row["wall_exit_ns"] > enclosing["wall_exit_ns"]
                or row["command_index_before"] < enclosing["command_index_before"]
                or row["command_index_after"] > enclosing["command_index_after"]
            ):
                raise ValueError("Update interval is outside its declared scheduler context")
    for row in [*attempt["trace"], terminal]:
        _phase(row["phase"], "native phase")
        for key, records in (("update_sequence", updates), ("scheduler_sequence", schedulers)):
            context = _context_id(row[key], key, records)
            if context is not None:
                enclosing = records[context]
                if (
                    not enclosing["command_index_before"]
                    <= row["command_index"]
                    <= enclosing["command_index_after"]
                ):
                    raise ValueError("Recorded command is outside its declared native update context")
                if row is not terminal and row["command_index"] <= enclosing["command_index_before"]:
                    raise ValueError("Trace call must follow the entry counter of its recorded native update")
                if (
                    row is terminal
                    and not enclosing["wall_enter_ns"]
                    <= (terminal_wall + 1e-6) * 1e9
                    <= enclosing["wall_exit_ns"] + 1e3
                ):
                    raise ValueError("Terminal callback timestamp is outside its enclosing native update")
    initial = attempt["trace"][0]
    if initial["update_sequence"] is not None or initial["scheduler_sequence"] is not None:
        raise ValueError("Initial native trace must not invent a recorded enclosing update context")
    events = attempt["phase_events"]
    if not isinstance(events, list) or len(events) > MAX_PHASE_EVENTS:
        raise ValueError(f"phase_events must contain at most {MAX_PHASE_EVENTS} records")
    previous_call, previous_enter = -1, -1
    for index, value in enumerate(events):
        event = _fields(
            value,
            f"phase_events[{index}]",
            {
                "sequence",
                "event",
                "command_index",
                "update_sequence",
                "scheduler_sequence",
                "phase_before",
                "phase_after",
                "wall_enter_ns",
                "wall_exit_ns",
            },
        )
        if _int(event["sequence"], "phase_event.sequence") != index:
            raise ValueError("Phase event sequence must start at zero and be contiguous")
        if event["event"] != "PlayLayer::playEndAnimationToPos":
            raise ValueError("Unsupported native phase event")
        command = _int(event["command_index"], "phase_event.command_index", maximum=terminal["command_index"])
        enter = _int(event["wall_enter_ns"], "phase_event.wall_enter_ns")
        exit_time = _int(event["wall_exit_ns"], "phase_event.wall_exit_ns", minimum=enter)
        if enter > terminal_entry_limit:
            raise ValueError("Phase event entry is after the reported terminal callback")
        if command < previous_call or enter < previous_enter:
            raise ValueError("Phase event call indices and entry timestamps must be nondecreasing")
        previous_call, previous_enter = command, enter
        _phase(event["phase_before"], "phase_event.phase_before")
        _phase(event["phase_after"], "phase_event.phase_after")
        for key, records in (("update_sequence", updates), ("scheduler_sequence", schedulers)):
            context = _context_id(event[key], f"phase_event.{key}", records)
            if context is not None:
                enclosing = records[context]
                if (
                    not enclosing["command_index_before"] <= command <= enclosing["command_index_after"]
                    or enter < enclosing["wall_enter_ns"]
                    or exit_time > enclosing["wall_exit_ns"]
                ):
                    raise ValueError("Phase event is outside its recorded enclosing context")


def _raw_int(value: Any, name: str) -> int:
    return _int(value, name, minimum=-(2**31), maximum=2**31 - 1)


def _groups(value: Any, name: str, *, remap: bool = False) -> list:
    if not isinstance(value, list) or len(value) > 64:
        raise ValueError(f"{name} must contain at most 64 values")
    for item in value:
        if remap:
            _raw_int(item, name)
        else:
            _int(item, name, minimum=1, maximum=9999)
    if not remap and value != sorted(set(value)):
        raise ValueError(f"{name} must contain sorted unique positive group IDs")
    return value


def _watched_objects(value: Any, watches: list[dict], name: str) -> list:
    if not isinstance(value, list) or len(value) != len(watches):
        raise ValueError(f"{name} must contain exactly the declared watches in order")
    for row, declaration in zip(value, watches):
        _fields(row, name, {"group_id", "x", "y", "is_group_disabled", "is_disabled"})
        if _int(row["group_id"], f"{name}.group_id", 1, 9999) != declaration["group_id"]:
            raise ValueError(f"{name} group order differs from object_watches")
        for field in ("x", "y"):
            finite(row[field], f"{name}.{field}")
        for field in ("is_group_disabled", "is_disabled"):
            _bool(row[field], f"{name}.{field}")
    return value


def _queue(value: Any, name: str) -> list:
    if not isinstance(value, list) or len(value) > MAX_QUEUED_BUTTONS:
        raise ValueError(f"{name} must contain at most {MAX_QUEUED_BUTTONS} native queue records")
    for row in value:
        _fields(row, name, {"button", "pressed", "player", "step", "timestamp"})
        _raw_int(row["button"], f"{name}.button")
        _raw_int(row["step"], f"{name}.step")
        _int(row["player"], f"{name}.player", 1, 2)
        _bool(row["pressed"], f"{name}.pressed")
        finite(row["timestamp"], f"{name}.timestamp")
    return value


def _mechanic_arguments(row: dict) -> None:
    event, args = row["event"], row["arguments"]
    keys = {
        "PlayerObject::collidedWithObject": {"dt_seconds", "rect", "skip_check"},
        "PlayerObject::updateCollide": {"direction"},
        "PlayerObject::collidedWithSlopeInternal": {"dt_seconds", "forced"},
        "PlayLayer::destroyPlayer": set(),
        "GJBaseGameLayer::triggerMoveCommand": {
            "target_group_id",
            "duration",
            "move_offset_x",
            "move_offset_y",
        },
        "GJBaseGameLayer::toggleGroupTriggered": {
            "group",
            "activate",
            "remap_keys",
            "trigger_id",
            "control_id",
        },
        "GJBaseGameLayer::toggleGroup": {"group", "activate"},
        "GJBaseGameLayer::spawnGroup": {
            "group",
            "ordered",
            "delay",
            "remap_keys",
            "trigger_id",
            "control_id",
        },
        "EffectGameObject::triggerObject": {"unique_id", "remap_keys"},
    }
    if not isinstance(event, str) or event not in keys:
        raise ValueError("Unsupported native mechanic event")
    _fields(args, "mechanic.arguments", keys[event])
    actor_event = event in {
        "PlayerObject::collidedWithObject",
        "PlayerObject::updateCollide",
        "PlayLayer::destroyPlayer",
        "PlayerObject::collidedWithSlopeInternal",
    }
    if actor_event:
        _int(row["player"], "mechanic.player", 1, 2)
    elif row["player"] is not None:
        raise ValueError("A layer/trigger mechanic event cannot declare an actor")
    if event in {
        "GJBaseGameLayer::toggleGroup",
        "GJBaseGameLayer::toggleGroupTriggered",
        "GJBaseGameLayer::spawnGroup",
    }:
        if row["object"] is not None:
            raise ValueError("Group hook events do not identify a trigger object")
    if event == "PlayerObject::collidedWithSlopeInternal" and row["object"] is None:
        raise ValueError("A watched slope callback requires its actual native object")
    if event == "PlayerObject::collidedWithObject":
        _bool(row["native_return"], "mechanic.native_return")
        finite(args["dt_seconds"], "mechanic.dt_seconds", minimum=0, maximum=60)
        rect = _fields(args["rect"], "mechanic.rect", {"x", "y", "width", "height"})
        for field, value in rect.items():
            finite(value, f"mechanic.rect.{field}")
        _bool(args["skip_check"], "mechanic.skip_check")
    elif row["native_return"] is not None:
        raise ValueError("A void mechanic hook cannot claim a native return")
    if event == "PlayerObject::updateCollide":
        _int(args["direction"], "mechanic.direction", 0, 3)
    if event == "PlayerObject::collidedWithSlopeInternal":
        finite(args["dt_seconds"], "mechanic.dt_seconds", minimum=0, maximum=60)
        _bool(args["forced"], "mechanic.forced")
    for field in ("target_group_id", "group", "trigger_id", "control_id", "unique_id"):
        if field in args:
            _raw_int(args[field], f"mechanic.{field}")
    for field in ("duration", "move_offset_x", "move_offset_y", "delay"):
        if field in args:
            finite(args[field], f"mechanic.{field}")
    for field in ("activate", "ordered"):
        if field in args:
            _bool(args[field], f"mechanic.{field}")
    if "remap_keys" in args:
        if args["remap_keys"] is None and event == "EffectGameObject::triggerObject":
            return
        _groups(args["remap_keys"], "mechanic.remap_keys", remap=True)


def _validate_paired_events(capture: dict, name: str) -> None:
    attempt, watches = capture["attempt"], capture["object_watches"]
    terminal = attempt["terminal"]
    rows = attempt[name]
    maximum = MAX_MECHANIC_EVENTS if name == "mechanic_events" else MAX_DELIVERY_EVENTS
    if not isinstance(rows, list) or len(rows) > maximum:
        raise ValueError(f"{name} must contain at most {maximum} paired records")
    common = {
        "sequence",
        "parent_sequence",
        "event",
        "command_index",
        "in_command",
        "update_sequence",
        "scheduler_sequence",
        "arguments",
        "phase_before",
        "phase_after",
        "wall_enter_ns",
        "wall_exit_ns",
    }
    extra = (
        {
            "player",
            "object",
            "state_before",
            "state_after",
            "watched_before",
            "watched_after",
            "native_return",
        }
        if name == "mechanic_events"
        else {"queue_before", "queue_after", "layer_timestamp_before", "layer_timestamp_after"}
    )
    previous_command, previous_enter = -1, -1
    stack: list[int] = []
    terminal_limit = (terminal["wall_elapsed_seconds"] + 1e-6) * 1e9
    for index, row in enumerate(rows):
        _fields(row, f"{name}[{index}]", common | extra)
        if _int(row["sequence"], f"{name}.sequence") != index:
            raise ValueError(f"{name} sequence must start at zero and be contiguous")
        command = _int(row["command_index"], f"{name}.command_index", maximum=terminal["command_index"])
        _bool(row["in_command"], f"{name}.in_command")
        if row["in_command"] and command == 0:
            raise ValueError(f"{name} cannot be in command processing at initial counter zero")
        enter = _int(row["wall_enter_ns"], f"{name}.wall_enter_ns")
        exit_time = _int(row["wall_exit_ns"], f"{name}.wall_exit_ns", minimum=enter)
        if enter > terminal_limit or enter < previous_enter or command < previous_command:
            raise ValueError(f"{name} entry must be ordered and no later than terminal")
        previous_command, previous_enter = command, enter
        for side in ("before", "after"):
            _phase(row[f"phase_{side}"], f"{name}.phase_{side}")
        parent = row["parent_sequence"]
        if parent is not None:
            _int(parent, f"{name}.parent_sequence", maximum=index - 1)
        while stack and stack[-1] != parent:
            sibling = rows[stack.pop()]
            if sibling["wall_exit_ns"] > enter:
                raise ValueError(f"{name} sibling intervals overlap or nesting is inconsistent")
        if parent is not None:
            if not stack:
                raise ValueError(f"{name} parent is not an enclosing entry-order event")
            enclosing = rows[parent]
            if enter < enclosing["wall_enter_ns"] or exit_time > enclosing["wall_exit_ns"]:
                raise ValueError(f"{name} child interval is outside its parent")
            if command != enclosing["command_index"]:
                raise ValueError(f"{name} nested event cannot invent a different command counter")
        stack.append(index)
        for key, records in (
            ("update_sequence", attempt["updates"]),
            ("scheduler_sequence", attempt["scheduler_updates"]),
        ):
            context = _context_id(row[key], f"{name}.{key}", records)
            if context is not None:
                enclosing = records[context]
                if not (
                    enclosing["command_index_before"] <= command <= enclosing["command_index_after"]
                    and enclosing["wall_enter_ns"] <= enter <= exit_time <= enclosing["wall_exit_ns"]
                ):
                    raise ValueError(f"{name} event is outside its recorded native context")
        if name == "mechanic_events":
            _mechanic_arguments(row)
            entity = row["object"]
            if entity is not None:
                _fields(entity, "mechanic.object", {"object_id", "runtime_unique_id", "group_ids"})
                for field in ("object_id", "runtime_unique_id"):
                    _raw_int(entity[field], f"mechanic.object.{field}")
                _groups(entity["group_ids"], "mechanic.object.group_ids")
            for side in ("before", "after"):
                _state(row[f"state_{side}"], f"mechanic.state_{side}", extended=True, contacts=True)
                _watched_objects(row[f"watched_{side}"], watches, f"mechanic.watched_{side}")
                if row["player"] is not None and row[f"state_{side}"][f"player{row['player']}"] is None:
                    raise ValueError("Mechanic actor is absent from its recorded state")
        else:
            event, args = row["event"], row["arguments"]
            if not isinstance(event, str):
                raise ValueError("Unsupported native delivery event")
            if event in {"UILayer::keyDown", "UILayer::keyUp"}:
                _fields(args, "delivery.arguments", {"key_code", "timestamp"})
                _raw_int(args["key_code"], "delivery.key_code")
                finite(args["timestamp"], "delivery.timestamp")
            elif event == "GJBaseGameLayer::processQueuedButtons":
                _fields(args, "delivery.arguments", {"dt_seconds", "clear_input_queue"})
                finite(args["dt_seconds"], "delivery.dt_seconds", minimum=0, maximum=60)
                _bool(args["clear_input_queue"], "delivery.clear_input_queue")
                if not row["queue_before"]:
                    raise ValueError("Recorded processQueuedButtons must have a nonempty entry queue")
            else:
                raise ValueError("Unsupported native delivery event")
            for side in ("before", "after"):
                _queue(row[f"queue_{side}"], f"delivery.queue_{side}")
                finite(row[f"layer_timestamp_{side}"], f"delivery.layer_timestamp_{side}")


def _validate_v4(capture: dict) -> None:
    attempt = capture["attempt"]
    watches = capture["object_watches"]
    if not isinstance(watches, list) or len(watches) > MAX_OBJECT_WATCHES:
        raise ValueError(f"object_watches must contain at most {MAX_OBJECT_WATCHES} declarations")
    groups = []
    for declaration in watches:
        _fields(declaration, "object_watch", {"group_id", "object_id", "runtime_unique_id"})
        groups.append(_int(declaration["group_id"], "object_watch.group_id", 1, 9999))
        for field in ("object_id", "runtime_unique_id"):
            _raw_int(declaration[field], f"object_watch.{field}")
    if len(set(groups)) != len(groups):
        raise ValueError("object_watches must contain unique positive groups")
    delivery = _fields(
        attempt["input_delivery"],
        "input_delivery",
        {"driver", "provenance", "entry_point", "injection_phase", "timestamp_policy"},
    )
    expected = {
        "none": ("unknown", None, "none", "not-applicable"),
        "owned-pre-command": (
            "synthetic-scheduled",
            "GJBaseGameLayer::handleButton",
            "processCommands-entry-before-original",
            "not-applicable",
        ),
        "scheduled-ui-callback": (
            "synthetic-scheduled",
            "UILayer::keyDown/keyUp",
            "processCommands-entry-before-original",
            "layer-m_timestamp",
        ),
    }
    driver = delivery["driver"]
    if not isinstance(driver, str) or driver not in expected:
        raise ValueError("Unsupported input_delivery driver")
    if (
        tuple(delivery[key] for key in ("provenance", "entry_point", "injection_phase", "timestamp_policy"))
        != expected[driver]
    ):
        raise ValueError("input_delivery metadata differs from its declared driver")
    if (driver == "none") != (attempt["input_source"] == "unknown"):
        raise ValueError("input_delivery driver differs from scheduled attempt provenance")
    if driver == "scheduled-ui-callback" and any(
        event["player"] != 1 or event["button"] != 1 for event in attempt["planned_inputs"]
    ):
        raise ValueError("Scheduled UI delivery supports only player1/button1")
    if driver != "owned-pre-command" and attempt["blocked_inputs"]:
        raise ValueError("Only owned-pre-command delivery suppresses native input")
    for row in [*attempt["trace"], attempt["terminal"]]:
        _watched_objects(row["watched_objects"], watches, "watched_objects")
    for event in attempt["inputs"]:
        _bool(event["in_command"], "input.in_command")
        if event["in_command"] and event["command_index"] == 0:
            raise ValueError("Input cannot be in command processing at counter zero")
        for key, rows in (
            ("update_sequence", attempt["updates"]),
            ("scheduler_sequence", attempt["scheduler_updates"]),
        ):
            context = _context_id(event[key], f"input.{key}", rows)
            if context is not None:
                enclosing = rows[context]
                if not (
                    enclosing["command_index_before"]
                    <= event["command_index"]
                    <= enclosing["command_index_after"]
                    and enclosing["wall_enter_ns"] <= event["wall_time_ns"] <= enclosing["wall_exit_ns"]
                ):
                    raise ValueError("Input receipt is outside its recorded native context")
    for name in ("mechanic_events", "delivery_events"):
        _validate_paired_events(capture, name)


def _load(path: str | Path) -> tuple[dict, str]:
    capture, source_sha256 = read_json(path)
    version = capture.get("schema_version") if isinstance(capture, dict) else None
    if type(version) is not int or version not in {1, 2, 3, 4}:
        raise ValueError("native capture schema_version must be integer 1, 2, 3 or 4")
    rich = version >= 2
    extended = version >= 3
    contacts = version == 4
    _fields(
        capture,
        "capture",
        {
            "schema_version",
            "kind",
            "provenance",
            "collector",
            "environment",
            "environment_sha256",
            "challenge",
            "attempt",
            "limitations",
            "integrity",
            "state_fields",
        }
        | ({"layer_state_fields"} if extended else set())
        | ({"object_watches"} if contacts else set()),
    )
    if capture["kind"] != "native_capture":
        raise ValueError("Expected kind native_capture")
    provenance = _fields(
        capture["provenance"],
        "provenance",
        {
            "origin",
            "independently_verified",
            "state_completeness",
        },
    )
    if _text(provenance["origin"], "provenance.origin") not in {"native-engine-capture", "synthetic"}:
        raise ValueError("provenance.origin must be native-engine-capture or synthetic")
    if provenance["independently_verified"] is not False:
        raise ValueError("A capture file cannot self-certify independent verification")
    if provenance["state_completeness"] != "selected_fields_only":
        raise ValueError("Only selected_fields_only capture state is supported")
    collector = _fields(
        capture["collector"],
        "collector",
        {
            "id",
            "version",
            "source_commit",
            "source_tree_sha256",
            "sdk_commit",
            "bindings_commit",
        },
    )
    for key, value in collector.items():
        _text(value, f"collector.{key}")
    sha256(collector["source_tree_sha256"], "collector.source_tree_sha256")
    fields = capture["state_fields"]
    player_fields = PLAYER_FIELDS_V4 if contacts else PLAYER_FIELDS_V3 if extended else PLAYER_FIELDS
    if (
        not isinstance(fields, list)
        or len(fields) != len(player_fields)
        or any(not isinstance(value, str) for value in fields)
        or set(fields) != player_fields
    ):
        raise ValueError("state_fields must declare the exact supported selected player fields")
    if extended and capture["layer_state_fields"] != ["dual_active"]:
        raise ValueError("layer_state_fields must declare exactly ['dual_active']")
    environment = _fields(
        capture["environment"],
        "environment",
        {
            "game_executable_sha256",
            "game_version",
            "geode_version",
            "adapter_binary_sha256",
            "platform",
            "mods",
            "configuration_complete",
            "input_policy",
            "clocks",
        },
    )
    for key in ("game_executable_sha256", "adapter_binary_sha256"):
        sha256(environment[key], f"environment.{key}")
    for key in ("game_version", "geode_version", "platform", "input_policy"):
        _text(environment[key], f"environment.{key}")
    if environment["platform"] != "windows-x64":
        raise ValueError("Only the windows-x64 native capture contract is supported")
    supported_policies = {INPUT_POLICY_V4} if contacts else {INPUT_POLICY, LEGACY_INPUT_POLICY}
    if environment["input_policy"] not in supported_policies:
        raise ValueError("Unsupported native capture input_policy")
    if rich and not contacts and environment["input_policy"] != INPUT_POLICY:
        raise ValueError("Schemas 2 and 3 require the owned native input policy")
    _bool(environment["configuration_complete"], "environment.configuration_complete")
    clocks = _fields(
        environment["clocks"],
        "environment.clocks",
        {
            "unit",
            "dt_unit",
            "hardware_arrival",
            "render_cadence",
        }
        | (
            {
                "clock_policy",
                "intervention_hook",
                "step_numerator",
                "step_denominator",
                "intervention_scope",
                "update_unit",
                "scheduler_unit",
            }
            if rich
            else set()
        ),
    )
    expected_clocks = {
        "unit": "processCommands_call_index",
        "dt_unit": "seconds_as_passed_to_hook",
        "hardware_arrival": "unknown",
        "render_cadence": "not_captured",
    }
    if rich:
        policy = clocks["clock_policy"]
        policies = {
            "native": ("none", 0, 1),
            "fixed-base-60": ("GJBaseGameLayer::update", 1, 60),
            "fixed-scheduler-240": ("CCScheduler::update", 1, 240),
        }
        if not isinstance(policy, str) or policy not in policies:
            raise ValueError("Unsupported native clock policy")
        hook, numerator, denominator = policies[policy]
        if (
            clocks["intervention_hook"] != hook
            or _int(clocks["step_numerator"], "step_numerator") != numerator
            or _int(clocks["step_denominator"], "step_denominator", minimum=1) != denominator
            or clocks["intervention_scope"] != "guarded-sandbox-process"
            or clocks["update_unit"] != "GJBaseGameLayer::update_call_index"
            or clocks["scheduler_unit"] != "CCScheduler::update_call_index"
        ):
            raise ValueError("Clock intervention identity is inconsistent")
        expected_clocks.update(
            {
                key: clocks[key]
                for key in (
                    "clock_policy",
                    "intervention_hook",
                    "step_numerator",
                    "step_denominator",
                    "intervention_scope",
                    "update_unit",
                    "scheduler_unit",
                )
            }
        )
    if clocks != expected_clocks:
        raise ValueError("Clock contract differs from the selected-fields native observer")
    mods = environment["mods"]
    if not isinstance(mods, list) or len(mods) > 1000:
        raise ValueError("environment.mods must be an array of at most 1000 mods")
    mod_ids: set[str] = set()
    for index, value in enumerate(mods):
        mod = _fields(value, f"environment.mods[{index}]", {"id", "version", "binary_sha256"})
        mod_id = _text(mod["id"], "mod.id")
        _text(mod["version"], "mod.version")
        sha256(mod["binary_sha256"], "mod.binary_sha256")
        if mod_id in mod_ids:
            raise ValueError("Duplicate environment mod id")
        mod_ids.add(mod_id)
    declared_environment_sha = sha256(capture["environment_sha256"], "environment_sha256")
    if canonical_sha256(environment) != declared_environment_sha:
        raise ValueError("environment_sha256 does not match the recorded environment")
    challenge = _fields(
        capture["challenge"],
        "challenge",
        {
            "id",
            "level_sha256",
            "game_version",
            "physics_version",
            "input_policy",
            "environment_id",
        },
    )
    challenge_identity(challenge)
    for key, value in challenge.items():
        _text(value, f"challenge.{key}")
    if challenge["input_policy"] != environment["input_policy"]:
        raise ValueError("Challenge input policy differs from environment")
    if challenge["game_version"] != environment["game_version"]:
        raise ValueError("Challenge game version differs from environment")
    if challenge["environment_id"] != declared_environment_sha:
        raise ValueError("challenge.environment_id must be environment_sha256")
    integrity = _fields(
        capture["integrity"],
        "integrity",
        {
            "recording_complete",
            "dropped_records",
            "errors",
        },
    )
    if integrity["recording_complete"] is not True:
        raise ValueError("Incomplete native recording is not valid terminal evidence")
    if _int(integrity["dropped_records"], "integrity.dropped_records") != 0:
        raise ValueError("Native recording contains dropped records")
    if not isinstance(integrity["errors"], list) or integrity["errors"]:
        raise ValueError("Native recording reports capture errors")
    attempt = _fields(
        capture["attempt"],
        "attempt",
        {
            "id",
            "input_source",
            "start_kind",
            "replay_sha256",
            "planned_inputs",
            "inputs",
            "trace",
            "terminal",
        }
        | ({"blocked_inputs"} if environment["input_policy"] in {INPUT_POLICY, INPUT_POLICY_V4} else set())
        | ({"updates", "scheduler_updates", "phase_events"} if rich else set())
        | ({"input_delivery", "delivery_events", "mechanic_events"} if contacts else set()),
    )
    _text(attempt["id"], "attempt.id")
    if contacts:
        _fields(
            attempt["input_delivery"],
            "input_delivery",
            {"driver", "provenance", "entry_point", "injection_phase", "timestamp_policy"},
        )
    if _text(attempt["input_source"], "attempt.input_source") not in {"replay", "unknown"}:
        raise ValueError("attempt.input_source must be replay or unknown")
    if _text(attempt["start_kind"], "attempt.start_kind") not in {
        "level_start",
        "practice",
        "start_position",
        "unknown",
    }:
        raise ValueError("Invalid attempt.start_kind")
    if attempt["input_source"] == "replay":
        sha256(attempt["replay_sha256"], "attempt.replay_sha256")
    elif attempt["replay_sha256"] is not None:
        raise ValueError("Only a replay attempt may claim a source replay SHA256")
    planned = attempt["planned_inputs"]
    if not isinstance(planned, list) or len(planned) > MAX_PLANNED_INPUTS:
        raise ValueError(f"planned_inputs must contain at most {MAX_PLANNED_INPUTS} events")
    if attempt["input_source"] != "replay" and planned:
        raise ValueError("An observed-input capture cannot claim a scheduled replay plan")
    previous_planned_call = 0
    for index, value in enumerate(planned):
        event = _fields(value, f"planned_inputs[{index}]", {"command_index", "player", "button", "pressed"})
        call = _int(
            event["command_index"], "planned_input.command_index", minimum=1, maximum=MAX_TRACE_RECORDS - 1
        )
        if call < previous_planned_call:
            raise ValueError("Planned input call indices must be nondecreasing")
        previous_planned_call = call
        _int(event["player"], "planned_input.player", minimum=1, maximum=2)
        _int(event["button"], "planned_input.button", minimum=1, maximum=3)
        _bool(event["pressed"], "planned_input.pressed")
    trace = attempt["trace"]
    if not isinstance(trace, list) or not 1 <= len(trace) <= MAX_TRACE_RECORDS:
        raise ValueError(f"trace must contain 1 to {MAX_TRACE_RECORDS} records")
    for index, value in enumerate(trace):
        row = _fields(
            value,
            f"trace[{index}]",
            {
                "command_index",
                "dt_seconds",
                "is_half_tick",
                "is_last_tick",
                "state",
            }
            | ({"phase", "update_sequence", "scheduler_sequence"} if rich else set())
            | ({"watched_objects"} if contacts else set()),
        )
        if _int(row["command_index"], f"trace[{index}].command_index") != index:
            raise ValueError("Native trace call indices must start at zero and be contiguous")
        finite(row["dt_seconds"], f"trace[{index}].dt_seconds", minimum=0, maximum=60)
        _bool(row["is_half_tick"], f"trace[{index}].is_half_tick")
        _bool(row["is_last_tick"], f"trace[{index}].is_last_tick")
        _state(row["state"], f"trace[{index}].state", extended=extended, contacts=contacts)
        if index == 0 and (row["dt_seconds"] != 0 or row["is_half_tick"] or row["is_last_tick"]):
            raise ValueError(
                "Initial trace must precede command processing with zero dt and false tick flags"
            )
    inputs = attempt["inputs"]
    if not isinstance(inputs, list) or len(inputs) > MAX_INPUT_RECORDS:
        raise ValueError(f"inputs must contain at most {MAX_INPUT_RECORDS} records")
    blocked = attempt.get("blocked_inputs", [])
    if not isinstance(blocked, list) or len(inputs) + len(blocked) > MAX_INPUT_RECORDS:
        raise ValueError(
            f"inputs and blocked_inputs together must contain at most {MAX_INPUT_RECORDS} records"
        )
    if attempt["input_source"] != "replay" and blocked:
        raise ValueError("Only a replay attempt may record suppressed blocked_inputs")
    previous_index = -1
    previous_wall_time = -1
    for index, value in enumerate(inputs):
        event = _fields(
            value,
            f"inputs[{index}]",
            {
                "sequence",
                "command_index",
                "button",
                "player",
                "pressed",
                "source",
                "phase",
                "native_return",
                "wall_time_ns",
            }
            | ({"in_command", "update_sequence", "scheduler_sequence"} if contacts else set()),
        )
        if _int(event["sequence"], "input.sequence") != index:
            raise ValueError("Input sequence must start at zero and be contiguous")
        command = _int(event["command_index"], "input.command_index", maximum=len(trace) - 1)
        if command < previous_index:
            raise ValueError("Input call indices must be nondecreasing")
        previous_index = command
        _int(event["button"], "input.button", minimum=1, maximum=3)
        _int(event["player"], "input.player", minimum=1, maximum=2)
        _bool(event["pressed"], "input.pressed")
        if _text(event["source"], "input.source") not in {"observed", "replay"}:
            raise ValueError("input.source must be observed or replay")
        if _text(event["phase"], "input.phase") not in {"requested", "push", "release"}:
            raise ValueError("Invalid input.phase")
        if event["phase"] == "push" and event["pressed"] is not True:
            raise ValueError("A push event must have pressed=true")
        if event["phase"] == "release" and event["pressed"] is not False:
            raise ValueError("A release event must have pressed=false")
        if event["phase"] == "requested":
            if event["native_return"] is not None:
                raise ValueError("Requested events cannot claim a native return")
        else:
            _bool(event["native_return"], "input.native_return")
        owned_receipts = not contacts or attempt["input_delivery"].get("driver") == "owned-pre-command"
        if attempt["input_source"] == "replay" and owned_receipts and event["source"] != "replay":
            raise ValueError("Controlled replay recording contains an unexpected observed input")
        if contacts and not owned_receipts and event["source"] != "observed":
            raise ValueError("UI/observation native receipts must preserve observed origin")
        if attempt["input_source"] == "unknown" and event["source"] != "observed":
            raise ValueError("An observed-input capture cannot claim a delivered replay input")
        wall_time = _int(event["wall_time_ns"], "input.wall_time_ns")
        if wall_time < previous_wall_time:
            raise ValueError("Input monotonic wall timestamps must be nondecreasing")
        previous_wall_time = wall_time
    previous_blocked_index = -1
    previous_blocked_wall_time = -1
    for index, value in enumerate(blocked):
        event = _fields(
            value,
            f"blocked_inputs[{index}]",
            {"sequence", "command_index", "button", "player", "pressed", "source", "wall_time_ns"},
        )
        if _int(event["sequence"], "blocked_input.sequence") != index:
            raise ValueError("Blocked input sequence must start at zero and be contiguous")
        command = _int(event["command_index"], "blocked_input.command_index", maximum=len(trace) - 1)
        if command < previous_blocked_index:
            raise ValueError("Blocked input call indices must be nondecreasing")
        previous_blocked_index = command
        # Unlike forwarded plan events, a suppressed native request may contain
        # any raw signed C++ int button. It is retained as diagnostic data only.
        _int(event["button"], "blocked_input.button", minimum=-(2**31), maximum=2**31 - 1)
        _int(event["player"], "blocked_input.player", minimum=1, maximum=2)
        _bool(event["pressed"], "blocked_input.pressed")
        if event["source"] != "unknown":
            raise ValueError("Blocked input origin must be unknown; it cannot identify human or replay input")
        wall_time = _int(event["wall_time_ns"], "blocked_input.wall_time_ns")
        if wall_time < previous_blocked_wall_time:
            raise ValueError("Blocked input monotonic wall timestamps must be nondecreasing")
        previous_blocked_wall_time = wall_time
    terminal = _fields(
        attempt["terminal"],
        "terminal",
        {
            "outcome",
            "event",
            "command_index",
            "wall_elapsed_seconds",
            "state",
        }
        | ({"phase", "update_sequence", "scheduler_sequence"} if rich else set())
        | ({"watched_objects"} if contacts else set()),
    )
    if _text(terminal["outcome"], "terminal.outcome") not in {"completed", "died"}:
        raise ValueError("Native terminal evidence requires completed or died, not aborted/error")
    required_event = (
        "PlayLayer::levelComplete" if terminal["outcome"] == "completed" else "PlayLayer::destroyPlayer"
    )
    if terminal["event"] != required_event:
        raise ValueError("Terminal outcome must come from its declared native engine callback")
    if _int(terminal["command_index"], "terminal.command_index") != len(trace) - 1:
        raise ValueError("Terminal call index must match the final recorded state")
    terminal_wall = finite(
        terminal["wall_elapsed_seconds"], "terminal.wall_elapsed_seconds", minimum=0, maximum=86400
    )
    # Integer ns and floating elapsed seconds share the same monotonic run start.
    # A one-microsecond allowance covers serialization/rounding of the diagnostic
    # double, while still rejecting events recorded after the terminal callback.
    if previous_wall_time > (terminal_wall + 1e-6) * 1_000_000_000:
        raise ValueError("Input wall timestamp is after the reported terminal callback")
    if previous_blocked_wall_time > (terminal_wall + 1e-6) * 1_000_000_000:
        raise ValueError("Blocked input wall timestamp is after the reported terminal callback")
    if rich:
        _validate_rich_observations(attempt, clocks, terminal_wall)
    terminal_state = _state(terminal["state"], "terminal.state", extended=extended, contacts=contacts)
    # Terminal-hook and post-process snapshots need not be equal: they are
    # intentionally captured at different points in the native call stack.
    terminal_dead = any(
        terminal_state[player] is not None and terminal_state[player]["is_dead"]
        for player in ("player1", "player2")
    )
    if terminal["outcome"] == "died" and not terminal_dead:
        raise ValueError("A native death requires a recorded dead player after destroyPlayer")
    if attempt["input_source"] == "replay" and (
        not contacts or attempt["input_delivery"].get("driver") == "owned-pre-command"
    ):
        expected_requests = [
            event for event in planned if event["command_index"] <= terminal["command_index"]
        ]
        actual_requests = [
            {key: event[key] for key in ("command_index", "player", "button", "pressed")}
            for event in inputs
            if event["phase"] == "requested"
        ]
        if actual_requests != expected_requests:
            raise ValueError(
                "Recorded replay requests do not match the planned prefix through the terminal call"
            )
    if contacts:
        _validate_v4(capture)
    limitations = capture["limitations"]
    if not isinstance(limitations, list) or len(limitations) > 100:
        raise ValueError("limitations must be an array of at most 100 strings")
    for limitation in limitations:
        _text(limitation, "limitation")
    return capture, source_sha256


def load_native_capture(path: str | Path) -> dict:
    """Validate a supplied terminal capture; this does not authenticate it."""
    return _load(path)[0]


def _input_signature(capture: dict) -> list[dict]:
    # Wall timestamps are capture timing diagnostics, not repeatable simulation
    # state. Preserve phase, native return, ordering and command-call placement.
    return [
        {key: value for key, value in row.items() if key != "wall_time_ns"}
        for row in capture["attempt"]["inputs"]
    ]


def _blocked_signature(capture: dict) -> list[dict]:
    # Suppressed requests can vary with native cleanup/render paths. Their
    # equality is reported separately, never included in delivered consistency.
    return [
        {key: value for key, value in row.items() if key != "wall_time_ns"}
        for row in capture["attempt"].get("blocked_inputs", [])
    ]


def _flat_player_fields(state: dict, player_fields: frozenset[str] = PLAYER_FIELDS) -> dict:
    """Expose each selected value independently, including player presence."""
    fields = {}
    for name in ("player1", "player2"):
        player = state[name]
        fields[f"{name}.present"] = player is not None
        for key in sorted(player_fields):
            fields[f"{name}.{key}"] = None if player is None else player[key]
    return fields


def _trace_component_diagnostics(baseline: list[dict], compared: list[dict]) -> dict:
    """Describe exact differences in one aligned component; no tolerance is used.

    Lists are projections of the validated contiguous trace, so row positions
    remain the original processCommands call indices, including initial row 0.
    """
    differing_common_records = 0
    first_difference = None
    field_differences = {}
    for index, (left, right) in enumerate(zip(baseline, compared)):
        if left == right:
            continue
        differing_common_records += 1
        if first_difference is None:
            first_difference = {"command_index": index, "baseline": left, "compared": right}
        for key in left:
            if left[key] == right[key]:
                continue
            if key not in field_differences:
                field_differences[key] = {
                    "differing_common_records": 0,
                    "first_different_call_index": index,
                    "baseline": left[key],
                    "compared": right[key],
                }
            field_differences[key]["differing_common_records"] += 1
    unmatched = abs(len(baseline) - len(compared))
    if first_difference is None and unmatched:
        index = min(len(baseline), len(compared))
        first_difference = {
            "command_index": index,
            "baseline": baseline[index] if index < len(baseline) else None,
            "compared": compared[index] if index < len(compared) else None,
        }
    return {
        "equal": not differing_common_records and not unmatched,
        "baseline_record_count": len(baseline),
        "compared_record_count": len(compared),
        "differing_common_records": differing_common_records,
        "unmatched_record_count": unmatched,
        "first_different_call_index": None if first_difference is None else first_difference["command_index"],
        "first_difference": first_difference,
        "field_differences": field_differences,
    }


def _terminal_component_diagnostics(
    baseline: dict, compared: dict, player_fields: frozenset[str] = PLAYER_FIELDS
) -> dict:
    keys = ("outcome", "event", "command_index")
    left_callback = {key: baseline[key] for key in keys}
    right_callback = {key: compared[key] for key in keys}
    left_fields = _flat_player_fields(baseline["state"], player_fields)
    right_fields = _flat_player_fields(compared["state"], player_fields)
    return {
        "callback_and_placement_equal": left_callback == right_callback,
        "selected_player_fields_equal": left_fields == right_fields,
        "callback_and_placement_differences": {
            key: {"baseline": left_callback[key], "compared": right_callback[key]}
            for key in keys
            if left_callback[key] != right_callback[key]
        },
        "selected_player_field_differences": {
            key: {"baseline": left_fields[key], "compared": right_fields[key]}
            for key in left_fields
            if left_fields[key] != right_fields[key]
        },
        "wall_elapsed_seconds_compared": False,
        **(
            {
                "dual_active_equal": baseline["state"]["dual_active"] == compared["state"]["dual_active"],
                "dual_active_difference": None
                if baseline["state"]["dual_active"] == compared["state"]["dual_active"]
                else {
                    "baseline": baseline["state"]["dual_active"],
                    "compared": compared["state"]["dual_active"],
                },
            }
            if "dual_active" in baseline["state"] and "dual_active" in compared["state"]
            else {}
        ),
    }


def _call_arguments(row: dict) -> dict:
    return {key: row[key] for key in ("command_index", "dt_seconds", "is_half_tick", "is_last_tick")}


def _stream_signature(rows: list[dict], *, update: bool) -> list[dict]:
    excluded = {"wall_enter_ns", "wall_exit_ns"} | ({"original_dt_seconds"} if update else set())
    return [{key: value for key, value in row.items() if key not in excluded} for row in rows]


def native_event_signature(value: Any) -> Any:
    """Project schema-4 native observations, retaining delivered native timing.

    Runtime object UIDs and monotonic wall times are diagnostics. Layer and queue
    timestamps, call placement, arguments and paired raw snapshots remain exact.
    """
    if isinstance(value, dict):
        return {
            key: native_event_signature(item)
            for key, item in value.items()
            if key not in {"runtime_unique_id", "wall_enter_ns", "wall_exit_ns"}
        }
    if isinstance(value, list):
        return [native_event_signature(item) for item in value]
    return value


def delivery_context_signature(rows: list[dict]) -> list[dict]:
    """Project validated schema-4 delivery events under a declared bounded scope.

    Absolute native timestamps vary between runs. This projection excludes their
    raw values without converting them into relative or simulated timestamps.
    Every event, native queue command, queue step and delivered dt is retained.
    It does not change the strict native mechanic-event projection.
    """
    result = native_event_signature(rows)
    for row in result:
        for key in ("layer_timestamp_before", "layer_timestamp_after"):
            row.pop(key)
        if row["event"] in {"UILayer::keyDown", "UILayer::keyUp"}:
            row["arguments"].pop("timestamp")
        for key in ("queue_before", "queue_after"):
            for queued in row[key]:
                queued.pop("timestamp")
    return result


def delivery_timestamp_signature(rows: list[dict]) -> list[dict]:
    """Retain raw native time values separately as cross-run diagnostics."""
    return [
        {
            "sequence": row["sequence"],
            "event": row["event"],
            "command_index": row["command_index"],
            "layer_timestamp_before": row["layer_timestamp_before"],
            "layer_timestamp_after": row["layer_timestamp_after"],
            "callback_timestamp": row["arguments"].get("timestamp"),
            "queue_before_timestamps": [queued["timestamp"] for queued in row["queue_before"]],
            "queue_after_timestamps": [queued["timestamp"] for queued in row["queue_after"]],
        }
        for row in rows
    ]


def _stream_difference(baseline: list[dict], compared: list[dict]) -> dict:
    first = next((i for i, (left, right) in enumerate(zip(baseline, compared)) if left != right), None)
    if first is None and len(baseline) != len(compared):
        first = min(len(baseline), len(compared))
    return {
        "equal": baseline == compared,
        "baseline_record_count": len(baseline),
        "compared_record_count": len(compared),
        "first_difference": None
        if first is None
        else {
            "sequence": first,
            "baseline": baseline[first] if first < len(baseline) else None,
            "compared": compared[first] if first < len(compared) else None,
        },
    }


def _end_boundary(attempt: dict) -> tuple[dict | None, str | None]:
    transitions = [
        event
        for event in attempt["phase_events"]
        if not event["phase_before"]["level_end_animation_started"]
        and event["phase_after"]["level_end_animation_started"]
    ]
    if len(transitions) != 1:
        return None, "no_unique_recorded_native_end_animation_transition"
    boundary = transitions[0]
    command = boundary["command_index"]
    if command == 0:
        return boundary, "no_recorded_trace_prefix_before_transition"
    if any(row["phase"]["level_end_animation_started"] for row in attempt["trace"][:command]):
        return boundary, "end_animation_flag_already_present_before_recorded_transition"
    observed = [row["phase"]["level_end_animation_started"] for row in attempt["trace"][command:]]
    first_true = next((i for i, value in enumerate(observed) if value), None)
    if first_true is None or not all(observed[first_true:]):
        return boundary, "recorded_end_animation_flag_missing_or_reverting_after_transition"
    if first_true > 1:
        return boundary, "recorded_end_animation_flag_delayed_after_transition"
    return boundary, None


def _pre_end_comparison(baseline: dict, compared: dict) -> dict:
    if baseline["schema_version"] < 2:
        return {"status": "not_recorded_schema1", "full_comparison_influence": "none"}
    left, left_reason = _end_boundary(baseline["attempt"])
    right, right_reason = _end_boundary(compared["attempt"])
    result = {
        "scope": "trace_rows_with_command_index_strictly_before_recorded_native_end_animation_event",
        "boundary_event": "PlayLayer::playEndAnimationToPos",
        "boundary_rule": "one_recorded_false_to_true_level_end_animation_started_transition",
        "full_comparison_influence": "none",
        "m1_gate": "not_established_by_prefix_comparison",
        "baseline_boundary": None if left is None else _stream_signature([left], update=False)[0],
        "compared_boundary": None if right is None else _stream_signature([right], update=False)[0],
    }
    if left_reason or right_reason:
        return {
            **result,
            "status": "not_available",
            "baseline_reason": left_reason,
            "compared_reason": right_reason,
        }
    left_trace = baseline["attempt"]["trace"][: left["command_index"]]
    right_trace = compared["attempt"]["trace"][: right["command_index"]]
    player_fields = frozenset(baseline["state_fields"])
    boundary_equal = _stream_signature([left], update=False) == _stream_signature([right], update=False)
    call_args = _trace_component_diagnostics(
        [_call_arguments(row) for row in left_trace], [_call_arguments(row) for row in right_trace]
    )
    players = _trace_component_diagnostics(
        [_flat_player_fields(row["state"], player_fields) for row in left_trace],
        [_flat_player_fields(row["state"], player_fields) for row in right_trace],
    )
    phases = _trace_component_diagnostics(
        [row["phase"] for row in left_trace], [row["phase"] for row in right_trace]
    )
    contexts = _trace_component_diagnostics(
        [{key: row[key] for key in ("update_sequence", "scheduler_sequence")} for row in left_trace],
        [{key: row[key] for key in ("update_sequence", "scheduler_sequence")} for row in right_trace],
    )
    inputs_equal = [
        row for row in _input_signature(baseline) if row["command_index"] < left["command_index"]
    ] == [row for row in _input_signature(compared) if row["command_index"] < right["command_index"]]
    dual = (
        _trace_component_diagnostics(
            [{"dual_active": row["state"]["dual_active"]} for row in left_trace],
            [{"dual_active": row["state"]["dual_active"]} for row in right_trace],
        )
        if baseline["schema_version"] >= 3
        else None
    )
    return {
        **result,
        "status": "available",
        "boundary_equal": boundary_equal,
        "recorded_inputs_equal": inputs_equal,
        "call_argument_diagnostics": call_args,
        "player_field_diagnostics": players,
        "native_phase_diagnostics": phases,
        "recorded_context_diagnostics": contexts,
        **({"dual_active_diagnostics": dual} if dual is not None else {}),
        "consistent": boundary_equal
        and inputs_equal
        and all(item["equal"] for item in (call_args, players, phases, contexts))
        and (dual is None or dual["equal"]),
    }


def _rich_comparison(baseline: dict, compared: dict) -> dict:
    if baseline["schema_version"] < 2:
        return {"status": "not_recorded_schema1"}
    a, b = baseline["attempt"], compared["attempt"]
    phase = _trace_component_diagnostics(
        [row["phase"] for row in a["trace"]], [row["phase"] for row in b["trace"]]
    )
    context = _trace_component_diagnostics(
        [{key: row[key] for key in ("update_sequence", "scheduler_sequence")} for row in a["trace"]],
        [{key: row[key] for key in ("update_sequence", "scheduler_sequence")} for row in b["trace"]],
    )
    updates = _stream_difference(
        _stream_signature(a["updates"], update=True), _stream_signature(b["updates"], update=True)
    )
    schedulers = _stream_difference(
        _stream_signature(a["scheduler_updates"], update=True),
        _stream_signature(b["scheduler_updates"], update=True),
    )
    events = _stream_difference(
        _stream_signature(a["phase_events"], update=False), _stream_signature(b["phase_events"], update=False)
    )
    terminal_keys = ("phase", "update_sequence", "scheduler_sequence")
    terminal_context = {key: a["terminal"][key] for key in terminal_keys} == {
        key: b["terminal"][key] for key in terminal_keys
    }
    original_diagnostics = {}
    for name in ("updates", "scheduler_updates"):
        original_diagnostics[name] = {
            "original_dt": _stream_difference(
                [{"original_dt_seconds": row["original_dt_seconds"]} for row in a[name]],
                [{"original_dt_seconds": row["original_dt_seconds"]} for row in b[name]],
            ),
            "wall_cadence": _stream_difference(
                [{key: row[key] for key in ("wall_enter_ns", "wall_exit_ns")} for row in a[name]],
                [{key: row[key] for key in ("wall_enter_ns", "wall_exit_ns")} for row in b[name]],
            ),
            "comparison_influence": "excluded_original_dt_and_wall_cadence",
        }
    return {
        "status": "available",
        "native_phase_diagnostics": phase,
        "recorded_context_diagnostics": context,
        "update_records": updates,
        "scheduler_records": schedulers,
        "phase_events": events,
        "terminal_phase_and_context_equal": terminal_context,
        "original_cadence_diagnostics": original_diagnostics,
        "consistent": terminal_context
        and all(item["equal"] for item in (phase, context, updates, schedulers, events)),
    }


def _summary(capture: dict, source_sha256: str) -> dict:
    warnings = [
        "The supplied file's declared native origin is not authenticated or independently verified.",
        "Recorded state covers selected player fields, not complete world/trigger/input/clock state.",
        "processCommands call indices are not certified physics ticks; dt is the hook argument.",
        "Callback return values do not measure physical input arrival, display latency or human intent.",
        "No human performance, timing windows, difficulty probability or AR is inferred.",
        "A native phase prefix is diagnostic only and cannot close M1 or replace full recorded-subset comparison.",
    ]
    if capture["schema_version"] >= 3:
        warnings[1] = (
            "Recorded state covers selected player and layer fields, not complete world/trigger/input/clock state."
        )
        warnings.append(
            "Schema 3 preserves raw gravity_inverted, vehicle_size, player_speed and dual_active; size categories, speed units and complete player lifecycle are not inferred."
        )
    if capture["schema_version"] == 4:
        warnings += [
            "Schema 4 records raw is_on_ground/is_on_slope, declared watched object fields and selected paired native callbacks; these are not a complete collider or trigger simulation.",
            "Scheduled UILayer callbacks are synthetic in-engine delivery, not OS or hardware input; observed native receipts do not authenticate queued origins.",
            "Object runtime_unique_id, wall timestamps and raw absolute delivery timestamps are cross-run diagnostics; delivery context and strict mechanic snapshots remain exact.",
        ]
    if capture["provenance"]["origin"] == "synthetic":
        warnings.insert(0, "SYNTHETIC capture fixture, not native Geometry Dash evidence.")
    if not capture["environment"]["configuration_complete"]:
        warnings.append(
            "Environment configuration is incomplete; full-environment reproducibility is unsupported."
        )
    if capture["attempt"]["start_kind"] != "level_start":
        warnings.append("This is not a declared true level start and cannot be full-start terminal evidence.")
    if capture["attempt"]["input_source"] != "replay":
        warnings.append("This is not a controlled source-replay attempt; replay repeatability is not tested.")
    elif capture["environment"]["input_policy"] == INPUT_POLICY:
        warnings.extend(
            [
                "Replay suppresses unknown-origin non-injector handleButton requests; vanilla-input equivalence is not established.",
                "Direct PlayerObject push/release calls bypassing handleButton are not controlled by replay channel ownership.",
                "Blocked inputs were not forwarded; their effect on a counterfactual unsuppressed trajectory is not measured.",
            ]
        )
    elif capture["schema_version"] == 4:
        driver = capture["attempt"]["input_delivery"]["driver"]
        warnings.append(
            "Owned scheduled delivery suppresses unknown-origin non-injector handleButton requests; suppressed requests are diagnostic only."
            if driver == "owned-pre-command"
            else "Scheduled UI delivery forwards and records observed native requests, including unsolicited requests; scheduled intent does not authenticate their origin."
        )
    else:
        warnings.append(
            "The legacy input policy does not record owned-channel suppression or blocked-input diagnostics."
        )
    if capture["attempt"]["terminal"]["outcome"] == "completed" and any(
        capture["attempt"]["terminal"]["state"][player] is not None
        and capture["attempt"]["terminal"]["state"][player]["is_dead"]
        for player in ("player1", "player2")
    ):
        warnings.append(
            "A selected player dead flag is present at completion; player activity is not captured, "
            "so this flag cannot override the reported completion callback."
            if capture["schema_version"] < 3
            else "A selected player dead flag is present at completion; raw dual_active does not describe the complete player lifecycle, so this flag cannot override the reported completion callback."
        )
    return {
        "schema_version": 1,
        "kind": "native_capture_inspection",
        "source_sha256": source_sha256,
        "capture_schema_version": capture["schema_version"],
        "status": "supplied_native_observer_evidence"
        if capture["provenance"]["origin"] == "native-engine-capture"
        else "synthetic_fixture",
        "authentication_status": "not_authenticated",
        "physics_status": "not_independently_verified",
        "m1_gate": "not_established_by_file_inspection",
        "challenge": capture["challenge"],
        "environment_sha256": capture["environment_sha256"],
        "environment": capture["environment"],
        "collector": capture["collector"],
        "provenance": capture["provenance"],
        "state_fields": capture["state_fields"],
        **({"layer_state_fields": capture["layer_state_fields"]} if capture["schema_version"] >= 3 else {}),
        "attempt": {
            key: value
            for key, value in capture["attempt"].items()
            if key
            not in {
                "planned_inputs",
                "inputs",
                "blocked_inputs",
                "trace",
                "terminal",
                "updates",
                "scheduler_updates",
                "phase_events",
                "delivery_events",
                "mechanic_events",
            }
        },
        "terminal": capture["attempt"]["terminal"],
        "counts": {
            "input_records": len(capture["attempt"]["inputs"]),
            "blocked_input_records": len(capture["attempt"].get("blocked_inputs", [])),
            "state_records": len(capture["attempt"]["trace"]),
            "planned_inputs": len(capture["attempt"]["planned_inputs"]),
            "unexecuted_planned_tail": sum(
                row["command_index"] > capture["attempt"]["terminal"]["command_index"]
                for row in capture["attempt"]["planned_inputs"]
            ),
        },
        "replay_execution_status": (
            "scheduled_intent_with_observed_native_receipts"
            if capture["schema_version"] == 4
            and capture["attempt"]["input_delivery"]["driver"] == "scheduled-ui-callback"
            else "observed_prefix_through_terminal"
            if capture["attempt"]["input_source"] == "replay"
            else "not_a_controlled_replay"
        ),
        "recorded_input_sha256": canonical_sha256(_input_signature(capture)),
        "blocked_input_diagnostics": {
            "status": "recorded" if "blocked_inputs" in capture["attempt"] else "not_recorded_legacy_policy",
            "source": "unknown",
            "delivery_status": "not_forwarded_to_native_handleButton"
            if "blocked_inputs" in capture["attempt"]
            else "not_recorded",
            "counterfactual_trajectory_effect": "not_measured",
            "records": capture["attempt"].get("blocked_inputs", []),
            "signature_sha256": canonical_sha256(_blocked_signature(capture)),
        },
        "recorded_state_sha256": canonical_sha256(capture["attempt"]["trace"]),
        "native_cadence_observations": {"status": "not_recorded_schema1"}
        if capture["schema_version"] == 1
        else {
            "status": "recorded",
            "clock_identity": capture["environment"]["clocks"],
            "original_dt_and_wall_cadence": "diagnostic_only",
            "render_cadence": "not_captured",
            "updates": capture["attempt"]["updates"],
            "scheduler_updates": capture["attempt"]["scheduler_updates"],
            "phase_events": capture["attempt"]["phase_events"],
        },
        **(
            {
                "object_watches": capture["object_watches"],
                "native_object_observations": {
                    "scope": "declared_watches_and_selected_native_callbacks",
                    "mechanic_events": capture["attempt"]["mechanic_events"],
                    "delivery_events": capture["attempt"]["delivery_events"],
                    "mechanic_event_count": len(capture["attempt"]["mechanic_events"]),
                    "delivery_event_count": len(capture["attempt"]["delivery_events"]),
                },
            }
            if capture["schema_version"] == 4
            else {}
        ),
        "reported_hook_dt_sum_seconds": sum(row["dt_seconds"] for row in capture["attempt"]["trace"]),
        "limitations": capture["limitations"],
        "warnings": warnings,
    }


def inspect_native_capture(path: str | Path) -> dict:
    """Inspect a schema-valid supplied capture, preserving its support limits."""
    return _summary(*_load(path))


def compare_native_captures(paths: Sequence[str | Path]) -> dict:
    """Compare >=2 supplied full-start attempts of the same declared replay.

    Incompatible identities are rejected. Divergent state/input/terminal traces
    produce an explicit inconsistent result instead of a reproducibility claim.
    """
    if isinstance(paths, (str, bytes, Path)) or not 2 <= len(paths) <= MAX_COMPARISON_FILES:
        raise ValueError(f"Compare requires 2 to {MAX_COMPARISON_FILES} capture paths")
    captures = [_load(path) for path in paths]
    base = captures[0][0]
    seen_ids: set[str] = set()
    for capture, _ in captures:
        for key in (
            "schema_version",
            "challenge",
            "environment",
            "environment_sha256",
            "collector",
            "provenance",
        ):
            if capture[key] != base[key]:
                raise ValueError(f"Incompatible capture {key}")
        if base["schema_version"] == 4:
            if native_event_signature(capture["object_watches"]) != native_event_signature(
                base["object_watches"]
            ):
                raise ValueError("Incompatible capture object_watches")
            if capture["attempt"]["input_delivery"] != base["attempt"]["input_delivery"]:
                raise ValueError("Repeat comparison requires the same input_delivery identity")
        attempt = capture["attempt"]
        if attempt["start_kind"] != "level_start":
            raise ValueError("Repeat comparison requires true full-start attempts")
        if attempt["input_source"] != "replay":
            raise ValueError("Repeat comparison requires controlled source-replay attempts")
        if attempt["replay_sha256"] != base["attempt"]["replay_sha256"]:
            raise ValueError("Captures declare different source replay identities")
        if attempt["id"] in seen_ids:
            raise ValueError("Duplicate attempt id cannot establish independent replay repetitions")
        seen_ids.add(attempt["id"])
    base_inputs = _input_signature(base)
    base_blocked = _blocked_signature(base)
    base_plan = base["attempt"]["planned_inputs"]
    base_trace = base["attempt"]["trace"]
    base_call_arguments = [_call_arguments(row) for row in base_trace]
    selected_player_fields = frozenset(base["state_fields"])
    base_player_fields = [_flat_player_fields(row["state"], selected_player_fields) for row in base_trace]
    base_terminal = {
        key: value for key, value in base["attempt"]["terminal"].items() if key != "wall_elapsed_seconds"
    }
    comparisons = []
    for capture, source_sha256 in captures[1:]:
        inputs_equal = _input_signature(capture) == base_inputs
        capture_blocked = _blocked_signature(capture)
        blocked_equal = capture_blocked == base_blocked
        first_blocked_difference = next(
            (
                index
                for index, (left, right) in enumerate(zip(base_blocked, capture_blocked))
                if left != right
            ),
            None,
        )
        if first_blocked_difference is None and len(capture_blocked) != len(base_blocked):
            first_blocked_difference = min(len(capture_blocked), len(base_blocked))
        planned_inputs_equal = capture["attempt"]["planned_inputs"] == base_plan
        capture_trace = capture["attempt"]["trace"]
        state_equal = capture_trace == base_trace
        call_arguments = _trace_component_diagnostics(
            base_call_arguments,
            [_call_arguments(row) for row in capture_trace],
        )
        player_fields = _trace_component_diagnostics(
            base_player_fields,
            [_flat_player_fields(row["state"], selected_player_fields) for row in capture_trace],
        )
        terminal_components = _terminal_component_diagnostics(
            base["attempt"]["terminal"], capture["attempt"]["terminal"], selected_player_fields
        )
        dual = (
            _trace_component_diagnostics(
                [{"dual_active": row["state"]["dual_active"]} for row in base_trace],
                [{"dual_active": row["state"]["dual_active"]} for row in capture_trace],
            )
            if base["schema_version"] >= 3
            else None
        )
        rich_components = _rich_comparison(base, capture)
        object_components = {}
        object_identity_diagnostics = {}
        absolute_timestamp_diagnostics = {}
        if base["schema_version"] == 4:
            object_identity_diagnostics = {
                "stable_watch_identity_equal": True,
                "runtime_unique_ids_equal": capture["object_watches"] == base["object_watches"],
                "baseline_watches": base["object_watches"],
                "compared_watches": capture["object_watches"],
                "comparison_influence": "runtime_unique_id_excluded",
            }
            object_components["mechanic_events"] = _stream_difference(
                native_event_signature(base["attempt"]["mechanic_events"]),
                native_event_signature(capture["attempt"]["mechanic_events"]),
            )
            object_components["delivery_events"] = _stream_difference(
                delivery_context_signature(base["attempt"]["delivery_events"]),
                delivery_context_signature(capture["attempt"]["delivery_events"]),
            )
            baseline_times = delivery_timestamp_signature(base["attempt"]["delivery_events"])
            compared_times = delivery_timestamp_signature(capture["attempt"]["delivery_events"])
            absolute_timestamp_diagnostics = {
                **_stream_difference(baseline_times, compared_times),
                "baseline_signature_sha256": canonical_sha256(baseline_times),
                "compared_signature_sha256": canonical_sha256(compared_times),
                "baseline_signature": baseline_times,
                "compared_signature": compared_times,
                "comparison_influence": "diagnostic_only_excluded_absolute_native_time",
            }
            object_components["watched_objects"] = _trace_component_diagnostics(
                [{"watched_objects": row["watched_objects"]} for row in base_trace],
                [{"watched_objects": row["watched_objects"]} for row in capture_trace],
            )
            object_components["terminal_watched_objects_equal"] = (
                base["attempt"]["terminal"]["watched_objects"]
                == capture["attempt"]["terminal"]["watched_objects"]
            )
        terminal_equal = {
            key: value
            for key, value in capture["attempt"]["terminal"].items()
            if key != "wall_elapsed_seconds"
        } == base_terminal
        first_state_difference = next(
            (index for index, (left, right) in enumerate(zip(base_trace, capture_trace)) if left != right),
            None,
        )
        if first_state_difference is None and len(capture_trace) != len(base_trace):
            first_state_difference = min(len(capture_trace), len(base_trace))
        comparisons.append(
            {
                "attempt_id": capture["attempt"]["id"],
                "source_sha256": source_sha256,
                "recorded_inputs_equal": inputs_equal,
                "blocked_inputs_equal": blocked_equal,
                "first_blocked_input_difference": None
                if first_blocked_difference is None
                else {
                    "sequence": first_blocked_difference,
                    "baseline": base_blocked[first_blocked_difference]
                    if first_blocked_difference < len(base_blocked)
                    else None,
                    "compared": capture_blocked[first_blocked_difference]
                    if first_blocked_difference < len(capture_blocked)
                    else None,
                },
                "planned_inputs_equal": planned_inputs_equal,
                "recorded_state_equal": state_equal,
                "recorded_call_arguments_equal": call_arguments["equal"],
                "recorded_player_fields_equal": player_fields["equal"],
                "call_argument_diagnostics": call_arguments,
                "player_field_diagnostics": player_fields,
                "terminal_equal": terminal_equal,
                "terminal_callback_and_placement_equal": terminal_components["callback_and_placement_equal"],
                "terminal_player_fields_equal": terminal_components["selected_player_fields_equal"],
                **(
                    {
                        "recorded_dual_active_equal": dual["equal"],
                        "dual_active_diagnostics": dual,
                        "terminal_dual_active_equal": terminal_components["dual_active_equal"],
                    }
                    if dual is not None
                    else {}
                ),
                "terminal_diagnostics": terminal_components,
                "rich_observation_diagnostics": rich_components,
                **({"native_object_diagnostics": object_components} if object_components else {}),
                **(
                    {"object_identity_diagnostics": object_identity_diagnostics}
                    if object_identity_diagnostics
                    else {}
                ),
                **(
                    {"delivery_absolute_timestamp_diagnostics": absolute_timestamp_diagnostics}
                    if base["schema_version"] == 4
                    else {}
                ),
                "pre_end_animation_diagnostics": _pre_end_comparison(base, capture),
                "first_different_state_call_index": first_state_difference,
                "consistent": planned_inputs_equal
                and inputs_equal
                and state_equal
                and terminal_equal
                and rich_components.get("consistent", True)
                and all(
                    value["equal"] if isinstance(value, dict) else value
                    for value in object_components.values()
                ),
            }
        )
    consistent = all(row["consistent"] for row in comparisons)
    component_consistency = {
        key: all(row[key] for row in comparisons)
        for key in (
            "planned_inputs_equal",
            "recorded_inputs_equal",
            "recorded_call_arguments_equal",
            "recorded_player_fields_equal",
            "terminal_callback_and_placement_equal",
            "terminal_player_fields_equal",
        )
    }
    if base["schema_version"] >= 2:
        for name, nested_key in (
            ("recorded_native_phase_equal", "native_phase_diagnostics"),
            ("recorded_update_context_equal", "recorded_context_diagnostics"),
            ("delivered_update_records_equal", "update_records"),
            ("delivered_scheduler_records_equal", "scheduler_records"),
            ("native_phase_events_equal", "phase_events"),
        ):
            component_consistency[name] = all(
                row["rich_observation_diagnostics"][nested_key]["equal"] for row in comparisons
            )
        component_consistency["terminal_phase_and_context_equal"] = all(
            row["rich_observation_diagnostics"]["terminal_phase_and_context_equal"] for row in comparisons
        )
    if base["schema_version"] >= 3:
        for key in ("recorded_dual_active_equal", "terminal_dual_active_equal"):
            component_consistency[key] = all(row[key] for row in comparisons)
    if base["schema_version"] == 4:
        for key, component in (
            ("native_mechanic_events_equal", "mechanic_events"),
            ("native_delivery_context_equal", "delivery_events"),
            ("recorded_watched_objects_equal", "watched_objects"),
        ):
            component_consistency[key] = all(
                row["native_object_diagnostics"][component]["equal"] for row in comparisons
            )
        component_consistency["terminal_watched_objects_equal"] = all(
            row["native_object_diagnostics"]["terminal_watched_objects_equal"] for row in comparisons
        )
    return {
        "schema_version": 1,
        "kind": "native_capture_comparison",
        "status": "recorded_subset_consistent" if consistent else "recorded_subset_inconsistent",
        "comparison_rule": "exact_recorded_call_arguments_player_fields_inputs_and_terminal",
        **(
            {
                "delivery_context_protocol": {
                    "id": "native-delivery-context-v1",
                    "scope": "exact_recorded_delivery_events_without_raw_absolute_native_time",
                    "excluded_native_time_fields": [
                        "layer_timestamp_before",
                        "layer_timestamp_after",
                        "UILayer.arguments.timestamp",
                        "queue_before[].timestamp",
                        "queue_after[].timestamp",
                    ],
                    "retained": "event_order_nesting_command_context_phase_key_queue_button_pressed_player_step_delivered_dt",
                    "raw_absolute_time_comparison": "separate_diagnostic_without_gate_influence",
                    "input_receipt_scope": "every_actual_native_receipt_through_terminal",
                    "relative_timestamp_normalization": "none",
                },
            }
            if base["schema_version"] == 4
            else {}
        ),
        "component_consistency": component_consistency,
        "authentication_status": "not_authenticated",
        "physics_status": "not_independently_verified",
        "m1_gate": "not_established_by_file_inspection",
        "complete_state_determinism": "not_established",
        "replay_execution_scope": "planned_prefix_through_native_terminal",
        "capture_schema_version": base["schema_version"],
        "clock_identity": base["environment"]["clocks"],
        "challenge": base["challenge"],
        "environment_sha256": base["environment_sha256"],
        "replay_sha256": base["attempt"]["replay_sha256"],
        "attempt_count": len(captures),
        "baseline_attempt_id": base["attempt"]["id"],
        "baseline_source_sha256": captures[0][1],
        "blocked_input_diagnostics": {
            "source": "unknown",
            "delivery_status": "not_forwarded_to_native_handleButton"
            if "blocked_inputs" in base["attempt"]
            else "not_recorded",
            "comparison_influence": "excluded_from_recorded_subset_consistency",
            "counterfactual_trajectory_effect": "not_measured",
            "status": "not_recorded_legacy_policy"
            if "blocked_inputs" not in base["attempt"]
            else (
                "diagnostic_records_equal"
                if all(row["blocked_inputs_equal"] for row in comparisons)
                else "diagnostic_records_different"
            ),
            "attempts": [
                {
                    "attempt_id": capture["attempt"]["id"],
                    "record_count": len(capture["attempt"].get("blocked_inputs", [])),
                    "signature_sha256": canonical_sha256(_blocked_signature(capture)),
                }
                for capture, _ in captures
            ],
        },
        "comparisons": comparisons,
        "warnings": [
            "Matching supplied files do not authenticate their origin or prove independent native execution.",
            "Agreement concerns only selected recorded fields, not full engine determinism or restoration.",
            "Wall timestamps are excluded; reported dt/call sequence and terminal placement are compared exactly.",
            "Call arguments, selected player fields and terminal callback/state are reported separately; all must match exactly, including rotation, for subset consistency.",
            "Schema 2 also compares delivered update/scheduler dt, recorded grouping, native phase flags/events and terminal context exactly."
            if base["schema_version"] < 3
            else "Schema 3 also compares raw player gravity/size/speed and layer dual_active through terminal, plus all schema-2 rich observations exactly.",
            "Original update/scheduler dt and wall cadence are separately reported diagnostics and do not substitute for delivered call arguments.",
            "Pre-end-animation checks use a recorded native phase transition and never override the full result or establish M1.",
            *(
                [
                    "Schema 4 also compares selected raw contact flags, watched objects, strict mechanic callbacks and the declared native-delivery-context-v1 projection through terminal.",
                    "Absolute delivery layer/callback/queue timestamps are separate raw diagnostics; all queue commands/steps, event contexts, delivered dt and actual native input receipts remain in the gate.",
                    "Runtime object UIDs and event wall times are diagnostic only; stable watch selectors, native receipt contexts and event snapshots remain exact.",
                    "Scheduled UI callbacks are in-engine synthetic delivery, not OS or hardware-input equivalence.",
                ]
                if base["schema_version"] == 4
                else []
            ),
            *(
                [
                    "Blocked unknown-origin requests were not forwarded and are diagnostic only; differences do not affect delivered subset consistency.",
                    "The effect of suppressed requests on a counterfactual unsuppressed trajectory is not measured; vanilla-input equivalence is unsupported.",
                    "Direct PlayerObject push/release calls bypassing handleButton are outside replay channel control.",
                ]
                if base["environment"]["input_policy"] == INPUT_POLICY
                or (
                    base["schema_version"] == 4
                    and base["attempt"]["input_delivery"]["driver"] == "owned-pre-command"
                )
                else [
                    "UI delivery records forwarded observed requests; suppressed-input counterfactuals and hardware equivalence are unsupported."
                ]
                if base["schema_version"] == 4
                else [
                    "The legacy input policy does not supply owned-channel suppression or blocked-input diagnostics."
                ]
            ),
            "No human ability, probability, difficulty window or AR is inferred.",
            *(
                []
                if base["environment"]["configuration_complete"]
                else [
                    "The declared environment is incomplete; complete-environment repeatability is unsupported."
                ]
            ),
        ],
    }
