"""Small strict validators shared by public research formats."""

import hashlib
import json
import math
import re
from pathlib import Path

MAX_JSON_BYTES = 16 * 1024 * 1024


def finite(value, name, *, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    if minimum is not None and number < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return number


def integer(value, name, *, minimum=None, maximum=None):
    number = finite(value, name, minimum=minimum, maximum=maximum)
    if not number.is_integer():
        raise ValueError(f"{name} must be an integer")
    return int(number)


def string(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 1024:
        raise ValueError(f"{name} must be a nonempty string (max 1024 characters)")
    return value


def mapping(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def sha256(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
    return value


def challenge_identity(value):
    value = mapping(value, "challenge")
    keys = ("id", "level_sha256", "game_version", "physics_version", "input_policy", "environment_id")
    result = {key: string(value.get(key), f"challenge.{key}") for key in keys}
    sha256(result["level_sha256"], "challenge.level_sha256")
    return result


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"Nonfinite JSON constant: {value}")


def _validate_tree(data):
    pending = [(data, 0)]
    while pending:
        value, depth = pending.pop()
        if depth > 64:
            raise ValueError("JSON nesting exceeds 64 levels")
        if isinstance(value, dict):
            pending.extend((key, depth + 1) for key in value)
            pending.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            pending.extend((item, depth + 1) for item in value)
        elif isinstance(value, str):
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ValueError("JSON contains an invalid Unicode surrogate") from exc
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError("JSON contains a nonfinite number")


def read_json(path):
    path = Path(path)
    with path.open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("JSON exceeds 16 MiB limit")
    try:
        data = json.loads(
            raw.decode("utf-8-sig"), object_pairs_hook=_unique_object, parse_constant=_invalid_constant
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc
    _validate_tree(data)
    return mapping(data, "document"), hashlib.sha256(raw).hexdigest()
