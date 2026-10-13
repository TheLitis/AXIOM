"""Bounded Windows/SDK observations and explicit compatible-candidate joins.

These records expose scoped ingress and public event-bus receipts. They do not
authenticate devices or supply private RawInputQueue enqueue/pop identities.
"""

from .native import KEYBOARD_EVENTS, TOUCH_EVENTS, _bool, _context_id, _fields, _int, _phase, _queue
from .validation import finite, mapping, string

MAX_WINDOWS_MESSAGES = 2048
MAX_SDK_EVENTS = 2048
UINT16_MAX = 2**16 - 1
UINT32_MAX = 2**32 - 1
UINT64_MAX = 2**64 - 1
INT64_MIN, INT64_MAX = -(2**63), 2**63 - 1
WINDOW_ROLES = {"main", "raw"}
MAIN_MESSAGES = {6, 7, 8, 28, 130}
SDK_KEYBOARD = "Geode::KeyboardInputEvent"
SDK_MOUSE = "Geode::MouseInputEvent"
BUTTON_FLAGS = {
    "left": (0x0001, 0x0002),
    "right": (0x0004, 0x0008),
    "middle": (0x0010, 0x0020),
    "button4": (0x0040, 0x0080),
    "button5": (0x0100, 0x0200),
}


def _uint(value, name, maximum=UINT64_MAX, minimum=0):
    return _int(value, name, minimum=minimum, maximum=maximum)


def validate_windows_input(capture: dict) -> None:
    """Validate schema-7-only records without reading Windows or a live game."""
    if capture["schema_version"] != 7:
        raise ValueError("Windows input observations require capture schema 7")
    attempt = capture["attempt"]
    data = _fields(
        attempt["windows_input"],
        "windows_input",
        {
            "enabled",
            "scope",
            "main_thread_id",
            "windows",
            "messages",
            "sdk_events",
            "integrity",
            "skipped",
            "timestamp_unit",
            "sdk_listener_phase",
            "sdk_listener_priority",
        },
    )
    if data["enabled"] is not True or data["scope"] != "active-guarded-sandbox-attempt-foreground-raw-only":
        raise ValueError("Unsupported Windows input observation scope")
    if (
        data["timestamp_unit"] != "Geode-getInputTimestamp-QPC-seconds"
        or data["sdk_listener_phase"] != "public-global-listener-receipt"
    ):
        raise ValueError("Unsupported Windows input timestamp or SDK listener phase")
    if _int(data["sdk_listener_priority"], "sdk_listener_priority", minimum=-(2**31), maximum=2**31 - 1) != -(
        2**31
    ):
        raise ValueError("Unsupported SDK listener priority")
    main_thread = _uint(data["main_thread_id"], "windows_input.main_thread_id", UINT32_MAX, 1)
    windows = data["windows"]
    if not isinstance(windows, list) or len(windows) != 2:
        raise ValueError("Windows input must declare exactly the main and raw process-owned windows")
    declarations = {}
    for row in windows:
        _fields(row, "windows_input.window", {"role", "thread_id", "process_id", "hwnd", "installed"})
        if not isinstance(row["role"], str) or row["role"] not in WINDOW_ROLES or row["role"] in declarations:
            raise ValueError("Windows input window roles must be unique main/raw")
        _uint(row["thread_id"], "window.thread_id", UINT32_MAX, 1)
        _uint(row["process_id"], "window.process_id", UINT32_MAX, 1)
        _uint(row["hwnd"], "window.hwnd", UINT64_MAX, 1)
        if row["installed"] is not True:
            raise ValueError("Windows input hooks are not fully installed")
        declarations[row["role"]] = row
    if (
        declarations["main"]["thread_id"] != main_thread
        or declarations["main"]["process_id"] != declarations["raw"]["process_id"]
        or declarations["main"]["hwnd"] == declarations["raw"]["hwnd"]
    ):
        raise ValueError("Windows input window/main-thread identities are inconsistent")
    integrity = _fields(
        data["integrity"],
        "windows_input.integrity",
        {"overflow_count", "pending_callbacks_at_snapshot", "read_error_count", "errors"},
    )
    for key in ("overflow_count", "pending_callbacks_at_snapshot", "read_error_count"):
        _uint(integrity[key], f"windows_input.integrity.{key}")
    if not isinstance(integrity["errors"], list) or len(integrity["errors"]) > 100:
        raise ValueError("Windows input integrity errors must be a bounded array")
    for value in integrity["errors"]:
        string(value, "windows_input.integrity.error")
    if any(
        integrity[key]
        for key in ("overflow_count", "pending_callbacks_at_snapshot", "read_error_count", "errors")
    ):
        raise ValueError("Windows input observation is incomplete or reports integrity errors")
    skipped = _fields(
        data["skipped"],
        "windows_input.skipped",
        {"background_raw_count", "mouse_motion_count", "unsupported_raw_count"},
    )
    for key, value in skipped.items():
        _uint(value, f"windows_input.skipped.{key}")
    terminal_limit = (attempt["terminal"]["wall_elapsed_seconds"] + 1e-6) * 1e9
    messages = data["messages"]
    if not isinstance(messages, list) or len(messages) > MAX_WINDOWS_MESSAGES:
        raise ValueError("Windows input messages must contain at most 2048 rows")
    previous_enter, stacks = -1, {}
    for index, row in enumerate(messages):
        _fields(
            row,
            "windows_input.message",
            {
                "sequence",
                "parent_sequence",
                "window_role",
                "message",
                "wparam",
                "lparam",
                "thread_id",
                "foreground_before",
                "foreground_after",
                "wall_enter_ns",
                "wall_exit_ns",
                "input_timestamp_enter",
                "input_timestamp_exit",
                "native_return",
                "raw_input",
            },
        )
        if _uint(row["sequence"], "message.sequence") != index:
            raise ValueError("Windows message sequence must be contiguous from zero")
        role = row["window_role"]
        if not isinstance(role, str) or role not in declarations:
            raise ValueError("Unknown Windows message window role")
        thread = _uint(row["thread_id"], "message.thread_id", UINT32_MAX, 1)
        if thread != declarations[role]["thread_id"]:
            raise ValueError("Windows message thread differs from its declared window")
        message = _uint(row["message"], "message.message", UINT32_MAX)
        _uint(row["wparam"], "message.wparam")
        for key in ("lparam", "native_return"):
            _int(row[key], f"message.{key}", minimum=INT64_MIN, maximum=INT64_MAX)
        for side in ("before", "after"):
            _bool(row[f"foreground_{side}"], f"message.foreground_{side}")
        enter = _uint(row["wall_enter_ns"], "message.wall_enter_ns")
        exit_time = _uint(row["wall_exit_ns"], "message.wall_exit_ns", minimum=enter)
        if enter < previous_enter or enter > terminal_limit:
            raise ValueError("Windows message entry must be ordered and no later than terminal")
        previous_enter = enter
        start = finite(row["input_timestamp_enter"], "message.input_timestamp_enter")
        finish = finite(row["input_timestamp_exit"], "message.input_timestamp_exit")
        if finish < start:
            raise ValueError("Windows message input timestamp interval is reversed")
        parent = row["parent_sequence"]
        if parent is not None:
            _uint(parent, "message.parent_sequence", index - 1)
            if messages[parent]["thread_id"] != thread:
                raise ValueError("Windows message nesting cannot cross threads")
        stack = stacks.setdefault(thread, [])
        while stack and stack[-1] != parent:
            completed = messages[stack.pop()]
            if completed["wall_exit_ns"] > enter:
                raise ValueError("Windows message same-thread siblings overlap")
        if parent is not None:
            if (
                not stack
                or enter < messages[parent]["wall_enter_ns"]
                or exit_time > messages[parent]["wall_exit_ns"]
            ):
                raise ValueError("Windows message child is outside its per-thread parent")
        stack.append(index)
        raw = row["raw_input"]
        if role == "main":
            if message not in MAIN_MESSAGES or raw is not None:
                raise ValueError("Main-window observation supports only declared lifecycle messages")
        else:
            if message != 255 or row["foreground_before"] is not True:
                raise ValueError("Raw-window observation requires foreground WM_INPUT")
            if raw is not None:
                mapping(raw, "raw_input")
                _fields(
                    raw,
                    "raw_input",
                    {"kind", "vkey", "scan_code", "flags", "keyboard_message"}
                    if raw.get("kind") == "keyboard"
                    else {"kind", "button_flags"},
                )
                if raw["kind"] == "keyboard":
                    for key in ("vkey", "scan_code", "flags"):
                        _uint(raw[key], f"raw_input.{key}", UINT16_MAX)
                    _uint(raw["keyboard_message"], "raw_input.keyboard_message", UINT32_MAX)
                elif raw["kind"] == "mouse":
                    _uint(raw["button_flags"], "raw_input.button_flags", UINT16_MAX, 1)
                else:
                    raise ValueError("Unsupported decoded raw input kind")
    events = data["sdk_events"]
    if not isinstance(events, list) or len(events) > MAX_SDK_EVENTS:
        raise ValueError("Windows input SDK events must contain at most 2048 rows")
    previous_wall, previous_command = -1, -1
    for index, row in enumerate(events):
        _fields(
            row,
            "sdk_event",
            {
                "sequence",
                "event",
                "thread_id",
                "wall_time_ns",
                "command_index",
                "in_command",
                "update_sequence",
                "scheduler_sequence",
                "phase",
                "queue_snapshot",
                "data",
            },
        )
        if (
            _uint(row["sequence"], "sdk_event.sequence") != index
            or _uint(row["thread_id"], "sdk_event.thread_id", UINT32_MAX, 1) != main_thread
        ):
            raise ValueError("SDK event sequence/thread identity is inconsistent")
        wall = _uint(row["wall_time_ns"], "sdk_event.wall_time_ns")
        command = _uint(row["command_index"], "sdk_event.command_index", attempt["terminal"]["command_index"])
        if wall < previous_wall or wall > terminal_limit or command < previous_command:
            raise ValueError("SDK events must be ordered and no later than terminal")
        previous_wall, previous_command = wall, command
        _bool(row["in_command"], "sdk_event.in_command")
        if row["in_command"] and command == 0:
            raise ValueError("SDK event cannot claim in-command context at initial counter zero")
        for key, records in (
            ("update_sequence", attempt["updates"]),
            ("scheduler_sequence", attempt["scheduler_updates"]),
        ):
            context = _context_id(row[key], f"sdk_event.{key}", records)
            if context is not None:
                enclosing = records[context]
                if not (
                    enclosing["command_index_before"] <= command <= enclosing["command_index_after"]
                    and enclosing["wall_enter_ns"] <= wall <= enclosing["wall_exit_ns"]
                ):
                    raise ValueError("SDK event is outside its recorded native context")
        _phase(row["phase"], "sdk_event.phase")
        _queue(row["queue_snapshot"], "sdk_event.queue_snapshot")
        payload = row["data"]
        if row["event"] == SDK_KEYBOARD:
            _fields(
                payload,
                "sdk_keyboard",
                {"key_code", "action", "native_code", "native_extra", "timestamp", "modifiers"},
            )
            _int(payload["key_code"], "sdk_keyboard.key_code", minimum=-(2**31), maximum=2**31 - 1)
            for key in ("native_code", "native_extra"):
                _uint(payload[key], f"sdk_keyboard.{key}")
            if not isinstance(payload["action"], str) or payload["action"] not in {
                "press",
                "release",
                "repeat",
            }:
                raise ValueError("Unsupported SDK keyboard action")
        elif row["event"] == SDK_MOUSE:
            _fields(payload, "sdk_mouse", {"button", "action", "timestamp", "modifiers"})
            if (
                not isinstance(payload["button"], str)
                or payload["button"] not in BUTTON_FLAGS
                or not isinstance(payload["action"], str)
                or payload["action"] not in {"press", "release"}
            ):
                raise ValueError("Unsupported SDK mouse button/action")
        else:
            raise ValueError("Unsupported SDK input event")
        finite(payload["timestamp"], "sdk_event.timestamp")
        _uint(payload["modifiers"], "sdk_event.modifiers", 255)
    if any(row["thread_id"] != main_thread for row in attempt["delivery_events"]):
        raise ValueError("Schema-7 delivery events must preserve the selected main thread identity")


def _candidate_status(candidates: list) -> str:
    return (
        "no_compatible_candidate"
        if not candidates
        else "one_compatible_candidate"
        if len(candidates) == 1
        else "ambiguous_compatible_candidates"
    )


def _packet_compatible(message: dict, sdk: dict) -> bool:
    raw, payload = message["raw_input"], sdk["data"]
    if (
        raw is None
        or not message["input_timestamp_enter"] <= payload["timestamp"] <= message["input_timestamp_exit"]
        or sdk["wall_time_ns"] < message["wall_enter_ns"]
    ):
        return False
    if sdk["event"] == SDK_KEYBOARD and raw["kind"] == "keyboard":
        action = "release" if raw["flags"] & 1 or raw["keyboard_message"] == 257 else "press"
        return (
            payload["native_code"] == raw["vkey"]
            and payload["native_extra"] == raw["scan_code"]
            and ("press" if payload["action"] == "repeat" else payload["action"]) == action
        )
    if sdk["event"] == SDK_MOUSE and raw["kind"] == "mouse":
        down, up = BUTTON_FLAGS[payload["button"]]
        action = "press" if raw["button_flags"] & down else "release" if raw["button_flags"] & up else None
        return payload["action"] == action
    return False


def _delivery_compatible(event: dict, sdk: dict) -> bool:
    payload = sdk["data"]
    if (
        sdk["thread_id"] != event["thread_id"]
        or sdk["wall_time_ns"] > event["wall_enter_ns"]
        or payload["timestamp"] != event["arguments"]["timestamp"]
    ):
        return False
    if event["event"] in KEYBOARD_EVENTS and sdk["event"] == SDK_KEYBOARD:
        return payload["key_code"] == event["arguments"]["key_code"] and (payload["action"] != "release") == (
            event["event"] == "UILayer::keyDown"
        )
    if sdk["event"] == SDK_MOUSE and event["event"] in {"UILayer::ccTouchBegan", "UILayer::ccTouchEnded"}:
        return payload["button"] == "left" and payload["action"] == (
            "press" if event["event"] == "UILayer::ccTouchBegan" else "release"
        )
    return False


def summarize_windows_input(capture: dict) -> dict:
    """Retain all raw rows and all timestamp/type-compatible candidates."""
    data = capture["attempt"]["windows_input"]
    sdk_rows, message_candidates = [], set()
    for event in data["sdk_events"]:
        candidates = [row["sequence"] for row in data["messages"] if _packet_compatible(row, event)]
        message_candidates.update(candidates)
        sdk_rows.append(
            {
                **event,
                "compatible_windows_message_sequences": candidates,
                "correlation_status": _candidate_status(candidates),
            }
        )
    delivery_rows, sdk_candidates = [], set()
    for event in capture["attempt"]["delivery_events"]:
        if event["event"] not in KEYBOARD_EVENTS | TOUCH_EVENTS:
            continue
        candidates = [row["sequence"] for row in data["sdk_events"] if _delivery_compatible(event, row)]
        sdk_candidates.update(candidates)
        delivery_rows.append(
            {
                "delivery_sequence": event["sequence"],
                "event": event["event"],
                "compatible_sdk_event_sequences": candidates,
                "correlation_status": _candidate_status(candidates),
                "candidate_windows_message_sequences": sorted(
                    {
                        candidate
                        for sequence in candidates
                        for candidate in sdk_rows[sequence]["compatible_windows_message_sequences"]
                    }
                ),
            }
        )
    return {
        "protocol": "windows-raw-sdk-ui-compatible-candidates-v1",
        "scope": data["scope"],
        "enabled": data["enabled"],
        "main_thread_id": data["main_thread_id"],
        "windows": data["windows"],
        "timestamp_unit": data["timestamp_unit"],
        "sdk_listener_phase": data["sdk_listener_phase"],
        "sdk_listener_priority": data["sdk_listener_priority"],
        "messages": data["messages"],
        "sdk_events": sdk_rows,
        "delivery_correlations": delivery_rows,
        "integrity": data["integrity"],
        "skipped": data["skipped"],
        "counts": {
            "windows_messages": len(data["messages"]),
            "sdk_events": len(sdk_rows),
            "ui_entries": len(delivery_rows),
            "sdk_without_windows_candidate": sum(
                not row["compatible_windows_message_sequences"] for row in sdk_rows
            ),
            "sdk_with_ambiguous_windows_candidates": sum(
                len(row["compatible_windows_message_sequences"]) > 1 for row in sdk_rows
            ),
            "ui_without_sdk_candidate": sum(
                not row["compatible_sdk_event_sequences"] for row in delivery_rows
            ),
            "ui_with_ambiguous_sdk_candidates": sum(
                len(row["compatible_sdk_event_sequences"]) > 1 for row in delivery_rows
            ),
        },
        "message_sequences_without_sdk_candidate": [
            row["sequence"] for row in data["messages"] if row["sequence"] not in message_candidates
        ],
        "sdk_sequences_without_ui_candidate": [
            row["sequence"] for row in sdk_rows if row["sequence"] not in sdk_candidates
        ],
        "authentication_status": "not_authenticated",
        "physical_device": "not_identified",
        "private_raw_input_queue_ownership": "not_established",
        "ordinary_os_input_equivalence": "not_established",
        "limitations": [
            "Only the process-owned main lifecycle and foreground raw-input windows are observed; skipped counters retain excluded scope.",
            "Public global listener receipts are partial event-bus coverage; a specific-key listener can stop delivery before this observer.",
            "Raw-to-SDK candidates use typed packet/action/native code and scan/button plus the packet's Geode timestamp interval, without wall-nearness matching.",
            "SDK-to-UI candidates use same thread, observed ordering and exact key/action/timestamp; they do not prove private enqueue/pop identity or final mutable dispatch result.",
            "Every unmatched and ambiguous candidate is retained; one compatible candidate is not authenticated causal ownership.",
            "Window handles, thread/process IDs, wall times and raw QPC values are scoped diagnostics, not stable cross-run identities or device authentication.",
        ],
    }
