"""Bounded, provenance-preserving level and GDR 1 JSON inspection.

These functions inspect file metadata. They do not execute Geometry Dash physics
or establish that a level or replay is valid in the game.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
import zlib
from collections import Counter
from pathlib import Path
from typing import Any

MAX_BYTES = 16 * 1024 * 1024
MAX_OBJECTS = 200_000
MAX_EVENTS = 200_000
MAX_FIELDS = 2_048
MAX_JSON_DEPTH = 64
UINT32_MAX = (1 << 32) - 1
ENCODINGS = ("plain", "base64-gzip", "base64-zlib")

_INTEGER = re.compile(r"[+-]?[0-9]+\Z")
_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")
_B64 = re.compile(rb"[A-Za-z0-9_-]*={0,2}\Z")
_NONFINITE = {"nan", "+nan", "-nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}
_BUTTONS = {1: "jump", 2: "left", 3: "right"}


def _limit(value: int, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _read_bounded(path: str | Path, max_bytes: int) -> bytes:
    _limit(max_bytes, "max_bytes")
    with Path(path).open("rb") as handle:
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"input exceeds the {max_bytes}-byte limit")
    return data


def _utf8(data: bytes, context: str) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError(f"{context} must be UTF-8 text") from error


def decode_level_bytes(data: bytes, *, encoding: str = "plain", max_bytes: int = MAX_BYTES) -> bytes:
    """Decode only the caller-selected format, with a strict output bound.

    Base64 input may omit padding and contain ASCII whitespace. Gzip/zlib input
    must be one complete stream: concatenated members and trailing data are
    rejected. Official built-in levels with a removed gzip header are unsupported.
    """
    _limit(max_bytes, "max_bytes")
    if not isinstance(data, bytes):
        raise ValueError("level data must be bytes")
    if len(data) > max_bytes:
        raise ValueError(f"input exceeds the {max_bytes}-byte limit")
    if encoding not in ENCODINGS:
        raise ValueError(f"unsupported level encoding: {encoding}; choose one of {ENCODINGS}")
    if encoding == "plain":
        return data
    compact = re.sub(rb"[ \t\r\n]", b"", data)
    if not compact or not _B64.fullmatch(compact):
        raise ValueError("expected URL-safe base64 text")
    if len(compact) % 4 == 1:
        raise ValueError("invalid base64 length")
    padded = compact + b"=" * (-len(compact) % 4)
    try:
        compressed = base64.b64decode(padded, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("invalid URL-safe base64 encoding") from error
    # Reject non-canonical encodings, including surplus or misplaced padding and
    # alternate representations with non-zero pad bits.
    if base64.urlsafe_b64encode(compressed).rstrip(b"=") != compact.rstrip(b"="):
        raise ValueError("non-canonical URL-safe base64 encoding")
    if b"=" in compact and compact != base64.urlsafe_b64encode(compressed):
        raise ValueError("invalid base64 padding")
    decoder = zlib.decompressobj(31 if encoding == "base64-gzip" else 15)
    try:
        decoded = decoder.decompress(compressed, max_bytes + 1)
    except zlib.error as error:
        raise ValueError(f"invalid or corrupt {encoding} stream") from error
    if len(decoded) > max_bytes or decoder.unconsumed_tail:
        raise ValueError(f"decoded level exceeds the {max_bytes}-byte limit")
    if not decoder.eof:
        raise ValueError("truncated compressed level stream")
    if decoder.unused_data:
        raise ValueError("compressed level has trailing data or multiple streams")
    return decoded


def _properties(record: str, context: str) -> dict[str, str]:
    if not record:
        return {}
    tokens = record.split(",")
    if len(tokens) % 2:
        raise ValueError(f"{context}: expected comma-separated key/value pairs")
    if len(tokens) // 2 > MAX_FIELDS:
        raise ValueError(f"{context}: too many properties")
    result: dict[str, str] = {}
    for key, value in zip(tokens[::2], tokens[1::2]):
        if not key or key.strip() != key or any(ch.isspace() for ch in key):
            raise ValueError(f"{context}: empty or whitespace-containing property key")
        if key in result:
            raise ValueError(f"{context}: duplicate property key {key!r}")
        if value.strip().lower() in _NONFINITE:
            raise ValueError(f"{context}: nonfinite property {key!r}")
        if _DECIMAL.fullmatch(value):
            try:
                finite = math.isfinite(float(value))
            except (OverflowError, ValueError):
                finite = False
            if not finite:
                raise ValueError(f"{context}: nonfinite numeric property {key!r}")
        result[key] = value
    return result


def _coordinate(value: str, context: str) -> float:
    if not _DECIMAL.fullmatch(value):
        raise ValueError(f"{context}: expected a finite decimal coordinate")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{context}: coordinate must be finite")
    return result


def parse_level_string(
    text: str, *, max_objects: int = MAX_OBJECTS, max_bytes: int = MAX_BYTES
) -> dict[str, Any]:
    """Parse a raw inner level string, preserving every property as a string.

    The first semicolon record is the level-start settings. A single final
    semicolon is allowed. Unknown fields have no inferred meaning; only object
    IDs and optional editor X/Y coordinates are summarized.
    """
    _limit(max_objects, "max_objects")
    _limit(max_bytes, "max_bytes")
    if not isinstance(text, str):
        raise ValueError("level string must be text")
    if len(text.encode("utf-8")) > max_bytes:
        raise ValueError(f"level string exceeds the {max_bytes}-byte limit")
    clean = text.strip("\r\n")
    if any(ord(ch) < 32 for ch in clean):
        raise ValueError("level string contains control characters")
    if ";" not in clean:
        raise ValueError("level string must contain a settings/object separator ';'")
    records = clean.split(";")
    if records[-1] == "":
        records.pop()
    if len(records) - 1 > max_objects:
        raise ValueError(f"level exceeds the {max_objects}-object limit")
    settings = _properties(records[0], "settings")
    objects: list[dict[str, Any]] = []
    ids: Counter[str] = Counter()
    xs: list[float] = []
    ys: list[float] = []
    missing_coordinates = 0
    for index, record in enumerate(records[1:]):
        if not record:
            raise ValueError(f"object {index}: empty interior object record")
        props = _properties(record, f"object {index}")
        object_id = props.get("1")
        if object_id is None or not _INTEGER.fullmatch(object_id):
            raise ValueError(f"object {index}: missing or invalid object ID (key '1')")
        if len(object_id) > 20 or not 0 < int(object_id) <= UINT32_MAX:
            raise ValueError(f"object {index}: object ID must be a positive uint32")
        numeric_id = int(object_id)
        x = _coordinate(props["2"], f"object {index} X") if "2" in props else None
        y = _coordinate(props["3"], f"object {index} Y") if "3" in props else None
        if x is not None:
            xs.append(x)
        if y is not None:
            ys.append(y)
        if x is None or y is None:
            missing_coordinates += 1
        ids[str(numeric_id)] += 1
        objects.append({"index": index, "properties": props, "object_id": numeric_id, "x": x, "y": y})
    bounds = {
        "x_min": min(xs) if xs else None,
        "x_max": max(xs) if xs else None,
        "y_min": min(ys) if ys else None,
        "y_max": max(ys) if ys else None,
    }
    return {
        "settings": settings,
        "objects": objects,
        "summary": {
            "object_count": len(objects),
            "object_id_counts": dict(sorted(ids.items(), key=lambda pair: int(pair[0]))),
            "editor_bounds": bounds,
            "objects_without_complete_coordinates": missing_coordinates,
        },
    }


def inspect_level(
    path: str | Path,
    *,
    encoding: str = "plain",
    max_bytes: int = MAX_BYTES,
    max_objects: int = MAX_OBJECTS,
) -> dict[str, Any]:
    """Read a local level string and report hashes, raw fields and editor metadata."""
    data = _read_bounded(path, max_bytes)
    decoded = decode_level_bytes(data, encoding=encoding, max_bytes=max_bytes)
    result = parse_level_string(_utf8(decoded, "level"), max_objects=max_objects, max_bytes=max_bytes)
    return {
        "schema_version": 1,
        "format": "geometry-dash-inner-level-string",
        "status": "metadata_only",
        "source": {
            "path": str(Path(path).resolve()),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "encoding": encoding,
        },
        "decoded_sha256": hashlib.sha256(decoded).hexdigest(),
        "decoded_bytes": len(decoded),
        **result,
        "limitations": [
            "Editor coordinates are not collision geometry or runtime trajectories.",
            "Triggers, hitboxes, game version, input rules and completion are not simulated.",
            "No physical feasibility, human difficulty or Axiom Rating is inferred.",
        ],
    }


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON property {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON number {value!r}")


def _json_depth(text: str) -> None:
    depth = 0
    quoted = False
    escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ValueError(f"JSON nesting exceeds {MAX_JSON_DEPTH} levels")
        elif char in "]}":
            depth -= 1


def _finite_tree(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("replay contains a nonfinite number")
    if isinstance(value, str) and any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError("replay contains an unpaired Unicode surrogate")
    if isinstance(value, dict):
        for key, item in value.items():
            _finite_tree(key)
            _finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            _finite_tree(item)


def _number(value: Any, context: str, *, positive: bool = False) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{context} must be a finite number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{context} must be a finite number") from error
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        raise ValueError(f"{context} must be finite and {'positive' if positive else 'nonnegative'}")
    return result


def _integer(value: Any, context: str, *, minimum: int = 0, maximum: int = UINT32_MAX) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{context} must be an integer in [{minimum}, {maximum}]")
    return value


def _boolean(value: Any, context: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{context} must be a JSON boolean")
    return value


def parse_gdr_json(
    text: str | bytes, *, max_events: int = MAX_EVENTS, max_bytes: int = MAX_BYTES
) -> dict[str, Any]:
    """Normalize the documented GDR 1 JSON representation, preserving extensions.

    Frame indices are authoritative. Seconds are derived only from an explicitly
    supplied positive framerate. File order and simultaneous event order are kept.
    """
    _limit(max_events, "max_events")
    _limit(max_bytes, "max_bytes")
    if isinstance(text, bytes):
        if len(text) > max_bytes:
            raise ValueError(f"replay exceeds the {max_bytes}-byte limit")
        text = _utf8(text, "replay")
    if not isinstance(text, str):
        raise ValueError("replay must be UTF-8 JSON text")
    if len(text.encode("utf-8")) > max_bytes:
        raise ValueError(f"replay exceeds the {max_bytes}-byte limit")
    _json_depth(text)
    try:
        raw = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except (json.JSONDecodeError, RecursionError) as error:
        raise ValueError(f"malformed replay JSON: {error}") from error
    if not isinstance(raw, dict):
        raise ValueError("GDR 1 JSON replay must be an object")
    _finite_tree(raw)
    required = {
        "version",
        "gameVersion",
        "description",
        "duration",
        "bot",
        "level",
        "author",
        "seed",
        "coins",
        "ldm",
        "inputs",
    }
    missing = sorted(required - raw.keys())
    if missing:
        raise ValueError(f"missing GDR 1 JSON fields: {', '.join(missing)}")
    if type(raw["version"]) not in (int, float) or raw["version"] != 1:
        raise ValueError("only GDR version 1 JSON is supported; binary GDR/GDR2 is not supported")
    for key in ("author", "description"):
        if not isinstance(raw[key], str):
            raise ValueError(f"{key} must be a string")
    _number(raw["duration"], "duration")
    _number(raw["gameVersion"], "gameVersion", positive=True)
    _integer(raw["seed"], "seed", minimum=-(1 << 31), maximum=(1 << 31) - 1)
    _integer(raw["coins"], "coins")
    _boolean(raw["ldm"], "ldm")
    for key in ("bot", "level"):
        if not isinstance(raw[key], dict):
            raise ValueError(f"{key} must be an object")
        if not isinstance(raw[key].get("name"), str):
            raise ValueError(f"{key}.name must be a string")
    if not isinstance(raw["bot"].get("version"), str):
        raise ValueError("bot.version must be a string in GDR 1")
    _integer(raw["level"].get("id"), "level.id")
    if not isinstance(raw["inputs"], list):
        raise ValueError("inputs must be an array")
    if len(raw["inputs"]) > max_events:
        raise ValueError(f"replay exceeds the {max_events}-event limit")
    fps = _number(raw["framerate"], "framerate", positive=True) if "framerate" in raw else None
    events: list[dict[str, Any]] = []
    presses = 0
    players: set[int] = set()
    previous_frame = -1
    ordered = True
    for index, item in enumerate(raw["inputs"]):
        if not isinstance(item, dict):
            raise ValueError(f"input {index} must be an object")
        if {"frame", "btn", "2p", "down"} - item.keys():
            raise ValueError(f"input {index} requires frame, btn, 2p and down")
        frame = _integer(item["frame"], f"input {index}.frame")
        button = _integer(item["btn"], f"input {index}.btn", maximum=(1 << 31) - 1)
        player = 2 if _boolean(item["2p"], f"input {index}.2p") else 1
        down = _boolean(item["down"], f"input {index}.down")
        seconds = frame / fps if fps is not None else None
        if seconds is not None and not math.isfinite(seconds):
            raise ValueError(f"input {index}: framerate produces a nonfinite timestamp")
        ordered = ordered and frame >= previous_frame
        previous_frame = frame
        presses += int(down)
        players.add(player)
        events.append(
            {
                "index": index,
                "frame": frame,
                "time_seconds": seconds,
                "button": button,
                "button_name": _BUTTONS.get(button, "unknown"),
                "player": player,
                "action": "press" if down else "release",
                "extensions": {
                    key: value for key, value in item.items() if key not in {"frame", "btn", "2p", "down"}
                },
            }
        )
    limitations = [
        "A replay records one input sequence; it does not establish success or feasible timing windows.",
        "Declared framerate and metadata are unverified recording claims, not measured runtime physics.",
        "Bot extensions are retained without executing frame corrections or interpreting their units.",
    ]
    if fps is None:
        limitations.append("No framerate was supplied: timestamps remain in frames and seconds are unknown.")
    if not ordered:
        limitations.append("Events are not ordered by frame; source order was preserved.")
    return {
        "schema_version": 1,
        "format": "gdr-1-json",
        "status": "metadata_only",
        "metadata": {key: value for key, value in raw.items() if key != "inputs"},
        "timebase": {
            "unit": "frame",
            "frames_per_second": fps,
            "source": "declared_framerate" if fps is not None else "unknown",
        },
        "events": events,
        "summary": {
            "event_count": len(events),
            "press_count": presses,
            "release_count": len(events) - presses,
            "players": sorted(players),
            "last_frame": max((event["frame"] for event in events), default=None),
            "ordered_by_frame": ordered,
        },
        "limitations": limitations,
    }


def inspect_replay(
    path: str | Path, *, max_bytes: int = MAX_BYTES, max_events: int = MAX_EVENTS
) -> dict[str, Any]:
    """Inspect a local GDR 1 JSON replay; do not guess other replay formats."""
    data = _read_bounded(path, max_bytes)
    result = parse_gdr_json(data, max_events=max_events, max_bytes=max_bytes)
    return {
        **result,
        "source": {
            "path": str(Path(path).resolve()),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "encoding": "utf-8-json",
        },
    }
