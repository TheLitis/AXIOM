"""Plan bounded joint perturbations on the owned native command-input clock.

This module produces requests for later full-start executions. It neither runs
the game nor infers death, feasibility, physical timing or human difficulty.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
from copy import deepcopy
from pathlib import Path

from .native import (
    INPUT_POLICY_V4,
    MAX_PLANNED_INPUTS,
    MAX_TRACE_RECORDS,
    PLAYER_FIELDS_V4,
    canonical_sha256,
    load_native_capture,
)
from .validation import challenge_identity, mapping, read_json, sha256, string

MAX_PROBE_POINTS = 4096
MAX_PROBE_RUNS = 4096
MAX_PROBE_AXES = 3
MAX_PROBE_VALUES = 1_000_000
MAX_OFFSET = 2**63 - 1
PROBE_PROTOCOL = "full-start-owned-command-grid-v1"
_INPUT_KEYS = frozenset({"command_index", "player", "button", "pressed"})
_STUDY_KEYS = frozenset({"schema_version", "kind", "protocol", "spec", "reference", "points", "trials"})
_POINT_KEYS = frozenset({"id", "offsets_commands", "status", "reason", "replay_file_sha256"})


def _fields(value: object, name: str, keys: frozenset[str] | set[str]) -> dict:
    data = mapping(value, name)
    if data.keys() != keys:
        raise ValueError(f"{name} requires exactly: {', '.join(sorted(keys))}")
    return data


def _int(value: object, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    return value


def _text(value: object, name: str) -> str:
    text = string(value, name)
    if text != text.strip():
        raise ValueError(f"{name} must be trimmed")
    try:
        text.encode("utf-8")
    except UnicodeError as error:
        raise ValueError(f"{name} must contain valid UTF-8 text") from error
    return text


def _array(value: object, name: str, minimum: int, maximum: int) -> list:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{name} must contain {minimum} to {maximum} records")
    return value


def _inputs(value: object) -> list[dict]:
    events = _array(value, "reference.inputs", 1, MAX_PLANNED_INPUTS)
    previous = 0
    held: set[tuple[int, int]] = set()
    for index, value in enumerate(events):
        event = _fields(value, f"reference.inputs[{index}]", _INPUT_KEYS)
        command = _int(event["command_index"], "input.command_index", 1, MAX_TRACE_RECORDS - 1)
        if command < previous:
            raise ValueError("Reference inputs must preserve nondecreasing global command order")
        previous = command
        channel = (_int(event["player"], "input.player", 1, 2), _int(event["button"], "input.button", 1, 3))
        if type(event["pressed"]) is not bool:
            raise ValueError("input.pressed must be a JSON boolean")
        if event["pressed"] == (channel in held):
            raise ValueError("Reference inputs must alternate the held state of each player/button channel")
        if event["pressed"]:
            held.add(channel)
        else:
            held.remove(channel)
    return events


def _spec(value: object, input_count: int) -> tuple[dict, int]:
    spec = _fields(value, "probe spec", {"schema_version", "kind", "id", "axes", "repetitions", "run_budget"})
    if _int(spec["schema_version"], "spec.schema_version", 1, 1) != 1 or spec["kind"] != "native_probe_spec":
        raise ValueError("Expected native_probe_spec schema 1")
    if not isinstance(spec["id"], str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", spec["id"]):
        raise ValueError("spec.id must be a lowercase identifier of at most 64 characters")
    repetitions = _int(spec["repetitions"], "spec.repetitions", 2, 8)
    budget = _int(spec["run_budget"], "spec.run_budget", 1, MAX_PROBE_RUNS)
    axes = _array(spec["axes"], "spec.axes", 1, MAX_PROBE_AXES)
    seen: set[int] = set()
    lengths: list[int] = []
    for index, item in enumerate(axes):
        axis = _fields(item, f"spec.axes[{index}]", {"event_index", "offsets_commands"})
        event_index = _int(axis["event_index"], "axis.event_index", 0, input_count - 1)
        if event_index in seen:
            raise ValueError("Probe axes must refer to distinct input event indices")
        seen.add(event_index)
        offsets = _array(axis["offsets_commands"], "axis.offsets_commands", 1, MAX_PROBE_POINTS)
        previous: int | None = None
        for offset in offsets:
            _int(offset, "axis offset", -MAX_OFFSET, MAX_OFFSET)
            if previous is not None and offset <= previous:
                raise ValueError("Axis offsets must be strictly increasing integers")
            previous = offset
        if 0 not in offsets:
            raise ValueError("Each probe axis must include its zero baseline offset")
        lengths.append(len(offsets))
    count = math.prod(lengths)
    if sum(lengths) > MAX_PROBE_VALUES or count * input_count > MAX_PROBE_VALUES:
        raise ValueError("Probe input expansion exceeds the 1,000,000-value limit")
    if count > MAX_PROBE_POINTS:
        raise ValueError("Joint probe grid exceeds the 4096-point limit")
    if count * repetitions > budget:
        raise ValueError("Requested grid repetitions exceed the declared run budget")
    return spec, count


def _reference(value: object) -> dict:
    reference = _fields(
        value,
        "reference",
        {
            "capture_sha256",
            "provenance",
            "challenge",
            "environment",
            "environment_sha256",
            "collector",
            "state_fields",
            "layer_state_fields",
            "inputs",
            "inputs_sha256",
        },
    )
    sha256(reference["capture_sha256"], "reference.capture_sha256")
    provenance = _fields(
        reference["provenance"],
        "reference.provenance",
        {"origin", "independently_verified", "state_completeness"},
    )
    if provenance["origin"] not in ("synthetic", "native-engine-capture"):
        raise ValueError("Unsupported reference provenance origin")
    if provenance["independently_verified"] is not False:
        raise ValueError("A probe reference cannot self-certify independent verification")
    if provenance["state_completeness"] != "selected_fields_only":
        raise ValueError("Probe reference state is limited to selected_fields_only")
    collector = _fields(
        reference["collector"],
        "reference.collector",
        {"id", "version", "source_commit", "source_tree_sha256", "sdk_commit", "bindings_commit"},
    )
    for name, text in collector.items():
        _text(text, f"collector.{name}")
    sha256(collector["source_tree_sha256"], "collector.source_tree_sha256")
    fields = reference["state_fields"]
    if (
        not isinstance(fields, list)
        or len(fields) != len(PLAYER_FIELDS_V4)
        or any(not isinstance(item, str) for item in fields)
        or set(fields) != PLAYER_FIELDS_V4
        or reference["layer_state_fields"] != ["dual_active"]
    ):
        raise ValueError("Probe reference must retain the exact schema 4/5 selected state fields")
    environment = _fields(
        reference["environment"],
        "reference.environment",
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
    for name in ("game_executable_sha256", "adapter_binary_sha256"):
        sha256(environment[name], f"environment.{name}")
    for name in ("game_version", "geode_version", "platform", "input_policy"):
        _text(environment[name], f"environment.{name}")
    if environment["platform"] != "windows-x64" or environment["input_policy"] != INPUT_POLICY_V4:
        raise ValueError("Probe reference requires the Windows scheduled-delivery input contract")
    if type(environment["configuration_complete"]) is not bool:
        raise ValueError("environment.configuration_complete must be a JSON boolean")
    expected_clocks = {
        "unit": "processCommands_call_index",
        "dt_unit": "seconds_as_passed_to_hook",
        "hardware_arrival": "unknown",
        "render_cadence": "not_captured",
        "clock_policy": "fixed-scheduler-240",
        "intervention_hook": "CCScheduler::update",
        "step_numerator": 1,
        "step_denominator": 240,
        "intervention_scope": "guarded-sandbox-process",
        "update_unit": "GJBaseGameLayer::update_call_index",
        "scheduler_unit": "CCScheduler::update_call_index",
    }
    clocks = _fields(environment["clocks"], "environment.clocks", set(expected_clocks))
    for name, expected in expected_clocks.items():
        if type(expected) is int:
            _int(clocks[name], f"environment.clocks.{name}", expected, expected)
        elif clocks[name] != expected:
            raise ValueError("Probe reference requires the exact fixed-scheduler-240 command-clock contract")
    mods = _array(environment["mods"], "environment.mods", 0, 1000)
    seen: set[str] = set()
    for index, value in enumerate(mods):
        mod = _fields(value, f"environment.mods[{index}]", {"id", "version", "binary_sha256"})
        mod_id = _text(mod["id"], "mod.id")
        _text(mod["version"], "mod.version")
        sha256(mod["binary_sha256"], "mod.binary_sha256")
        if mod_id in seen:
            raise ValueError("Duplicate environment mod identity")
        seen.add(mod_id)
    environment_sha = sha256(reference["environment_sha256"], "reference.environment_sha256")
    if canonical_sha256(environment) != environment_sha:
        raise ValueError("Reference environment_sha256 differs from its frozen environment")
    challenge = _fields(
        reference["challenge"],
        "reference.challenge",
        {"id", "level_sha256", "game_version", "physics_version", "input_policy", "environment_id"},
    )
    challenge_identity(challenge)
    for name, text in challenge.items():
        _text(text, f"challenge.{name}")
    if (
        challenge["environment_id"] != environment_sha
        or challenge["game_version"] != environment["game_version"]
        or challenge["input_policy"] != environment["input_policy"]
    ):
        raise ValueError("Probe challenge must match the frozen environment identity")
    inputs = _inputs(reference["inputs"])
    if sha256(reference["inputs_sha256"], "reference.inputs_sha256") != canonical_sha256(inputs):
        raise ValueError("Reference inputs_sha256 differs from its frozen input schedule")
    return reference


def _point_plan(
    reference: dict, axes: list[dict], offsets: tuple[int, ...]
) -> tuple[dict | None, str | None]:
    inputs = deepcopy(reference["inputs"])
    for axis, offset in zip(axes, offsets):
        inputs[axis["event_index"]]["command_index"] += offset
    previous = 0
    for index, event in enumerate(inputs):
        command = event["command_index"]
        if not 1 <= command <= MAX_TRACE_RECORDS - 1:
            return None, f"input[{index}].command_index outside 1..{MAX_TRACE_RECORDS - 1}"
        if command < previous:
            return None, f"input[{index}].command_index reverses the retained source event order"
        previous = command
    return {
        "schema_version": 1,
        "kind": "native_replay",
        "clock": "processCommands_call_index",
        "level_sha256": reference["challenge"]["level_sha256"],
        "environment_sha256": reference["environment_sha256"],
        "inputs": inputs,
    }, None


def replay_bytes(plan: dict) -> bytes:
    """Serialize an owned replay as compact sorted UTF-8 JSON followed by LF."""
    _fields(
        plan,
        "native replay",
        {"schema_version", "kind", "clock", "level_sha256", "environment_sha256", "inputs"},
    )
    _int(plan["schema_version"], "replay.schema_version", 1, 1)
    if plan["kind"] != "native_replay" or plan["clock"] != "processCommands_call_index":
        raise ValueError("Expected command-index native_replay schema 1")
    for name in ("level_sha256", "environment_sha256"):
        sha256(plan[name], f"replay.{name}")
    _inputs(plan["inputs"])
    return (
        json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")


def _point(reference: dict, axes: list[dict], offsets: tuple[int, ...], index: int) -> dict:
    plan, reason = _point_plan(reference, axes, offsets)
    return {
        "id": f"p{index:04d}",
        "offsets_commands": list(offsets),
        "status": "scheduled" if plan is not None else "invalid_schedule",
        "reason": reason,
        "replay_file_sha256": None if plan is None else hashlib.sha256(replay_bytes(plan)).hexdigest(),
    }


def _grid(reference: dict, spec: dict) -> tuple[list[dict], list[dict]]:
    axes = spec["axes"]
    points = [
        _point(reference, axes, offsets, index)
        for index, offsets in enumerate(itertools.product(*(axis["offsets_commands"] for axis in axes)))
    ]
    ordered = [point for point in points if all(offset == 0 for offset in point["offsets_commands"])]
    ordered += [point for point in points if any(offset != 0 for offset in point["offsets_commands"])]
    trials = [
        {"id": f"{point['id']}-r{repetition}", "point_id": point["id"], "repetition": repetition}
        for point in ordered
        if point["status"] == "scheduled"
        for repetition in range(1, spec["repetitions"] + 1)
    ]
    return points, trials


def _context(value: object) -> tuple[dict, dict, dict, int]:
    study = _fields(value, "probe study", _STUDY_KEYS)
    _int(study["schema_version"], "study.schema_version", 1, 1)
    if study["kind"] != "native_probe_study" or study["protocol"] != PROBE_PROTOCOL:
        raise ValueError("Expected native_probe_study with full-start-owned-command-grid-v1 protocol")
    reference = _reference(study["reference"])
    spec, count = _spec(study["spec"], len(reference["inputs"]))
    _array(study["points"], "study.points", count, count)
    _array(study["trials"], "study.trials", 1, count * spec["repetitions"])
    return study, reference, spec, count


def validate_probe_study(value: object) -> dict:
    """Check a frozen study by reconstructing its complete grid and trial order.

    Validation cannot authenticate the original capture from the retained SHA or
    certify native execution. Creation separately qualifies the supplied source.
    """
    study, reference, spec, _ = _context(value)
    for item in study["points"]:
        point = _fields(item, "point", _POINT_KEYS)
        if not isinstance(point["id"], str) or not re.fullmatch(r"p[0-9]{4,10}", point["id"]):
            raise ValueError("point.id must identify a generated p0000-style grid point")
        coordinates = _array(
            point["offsets_commands"], "point.offsets_commands", len(spec["axes"]), len(spec["axes"])
        )
        for offset in coordinates:
            _int(offset, "point offset", -MAX_OFFSET, MAX_OFFSET)
        if point["status"] not in ("scheduled", "invalid_schedule"):
            raise ValueError("Unsupported point status")
        if point["reason"] is not None:
            _text(point["reason"], "point.reason")
        if point["replay_file_sha256"] is not None:
            sha256(point["replay_file_sha256"], "point.replay_file_sha256")
    for item in study["trials"]:
        trial = _fields(item, "trial", {"id", "point_id", "repetition"})
        for key in ("id", "point_id"):
            _text(trial[key], f"trial.{key}")
        _int(trial["repetition"], "trial.repetition", 1, spec["repetitions"])
    points, trials = _grid(reference, spec)
    if canonical_sha256(study["points"]) != canonical_sha256(points):
        raise ValueError("Probe points differ from the reconstructed command-offset grid")
    if canonical_sha256(study["trials"]) != canonical_sha256(trials):
        raise ValueError("Probe trials differ from the reconstructed baseline-first repetition schedule")
    return study


def create_probe_study(reference_path: str | Path, spec_path: str | Path) -> dict:
    """Qualify a supplied completed owned replay and freeze its requested grid."""
    source, capture_sha = read_json(reference_path)
    capture = load_native_capture(reference_path)
    if canonical_sha256(source) != canonical_sha256(capture):
        raise ValueError("Reference capture changed while its identity was being frozen")
    attempt = capture["attempt"]
    if (
        capture["schema_version"] not in {4, 5}
        or capture["environment"]["clocks"]["clock_policy"] != "fixed-scheduler-240"
        or attempt["input_source"] != "replay"
        or attempt["start_kind"] != "level_start"
        or attempt["input_delivery"]["driver"] != "owned-pre-command"
        or attempt["terminal"]["outcome"] != "completed"
    ):
        raise ValueError(
            "Probe source requires a completed full-start schema 4/5 owned-pre-command fixed-scheduler-240 replay"
        )
    inputs = _inputs(attempt["planned_inputs"])
    if any(event["command_index"] > attempt["terminal"]["command_index"] for event in inputs):
        raise ValueError("Every reference planned input must be consumed before the completed terminal")
    spec_value, _ = read_json(spec_path)
    spec, _ = _spec(spec_value, len(inputs))
    reference = {
        "capture_sha256": capture_sha,
        **{
            key: deepcopy(capture[key])
            for key in (
                "provenance",
                "challenge",
                "environment",
                "environment_sha256",
                "collector",
                "state_fields",
                "layer_state_fields",
            )
        },
        "inputs": deepcopy(inputs),
        "inputs_sha256": canonical_sha256(inputs),
    }
    _reference(reference)
    points, trials = _grid(reference, spec)
    # A hash obtained from another read must not be paired with changed source
    # bytes. Recheck after the spec and bounded grid have also been processed.
    current, current_sha = read_json(reference_path)
    if current_sha != capture_sha or canonical_sha256(current) != canonical_sha256(capture):
        raise ValueError("Reference capture changed while its identity was being frozen")
    return {
        "schema_version": 1,
        "kind": "native_probe_study",
        "protocol": PROBE_PROTOCOL,
        "spec": deepcopy(spec),
        "reference": reference,
        "points": points,
        "trials": trials,
    }


def load_probe_study(path: str | Path) -> dict:
    """Read and validate a frozen study without running its requested trials."""
    value, _ = read_json(path)
    return validate_probe_study(value)


def study_sha256(study: dict) -> str:
    """Digest the fully validated study's compact canonical JSON without LF."""
    return canonical_sha256(validate_probe_study(study))


def point_replay(study: dict, point: dict | str) -> dict:
    """Reconstruct one scheduled point, validating its context and local record.

    Use load_probe_study/validate_probe_study once before processing a whole
    study. This function checks only the chosen point, avoiding repeated grid
    expansion for every trial. Tied events keep the original source order.
    """
    study, reference, spec, count = _context(study)
    point_id = point if isinstance(point, str) else _fields(point, "point", _POINT_KEYS)["id"]
    if not isinstance(point_id, str) or not re.fullmatch(r"p[0-9]{4,10}", point_id):
        raise ValueError("point.id must identify a generated p0000-style grid point")
    index = int(point_id[1:])
    _int(index, "point index", 0, count - 1)
    if point_id != f"p{index:04d}":
        raise ValueError("point.id is not in canonical generated form")
    remainder, coordinates = index, []
    for axis in reversed(spec["axes"]):
        remainder, position = divmod(remainder, len(axis["offsets_commands"]))
        coordinates.append(axis["offsets_commands"][position])
    offsets = tuple(reversed(coordinates))
    expected = _point(reference, spec["axes"], offsets, index)
    stored = _fields(study["points"][index], "point", _POINT_KEYS)
    if canonical_sha256(stored) != canonical_sha256(expected) or (
        isinstance(point, dict) and canonical_sha256(point) != canonical_sha256(expected)
    ):
        raise ValueError("Chosen point differs from its reconstructed command-offset record")
    plan, reason = _point_plan(reference, spec["axes"], offsets)
    if plan is None:
        raise ValueError(f"Cannot replay an invalid_schedule point: {reason}")
    return plan
