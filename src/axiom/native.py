"""Inspect native observer captures without authenticating their reported origin.

The collector's clock is a processCommands call index, not a physics tick. Exact
comparison covers only recorded inputs, call arguments and selected player fields.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from .validation import challenge_identity, finite, mapping, read_json, sha256, string

MAX_TRACE_RECORDS = 20_001
MAX_INPUT_RECORDS = 12_000
MAX_PLANNED_INPUTS = 4_000
MAX_COMPARISON_FILES = 16
INPUT_POLICY = "process-commands-pre-hook-owned-input-v1"
PLAYER_FIELDS = frozenset({"x", "y", "y_velocity", "rotation", "is_dead", "mode"})


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


def _player(value: Any, name: str) -> dict:
    state = _fields(value, name, PLAYER_FIELDS)
    for key in ("x", "y", "y_velocity", "rotation"):
        finite(state[key], f"{name}.{key}")
    _bool(state["is_dead"], f"{name}.is_dead")
    _text(state["mode"], f"{name}.mode")
    return state


def _load(path: str | Path) -> tuple[dict, str]:
    capture, source_sha256 = read_json(path)
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
        },
    )
    if type(capture["schema_version"]) is not int or capture["schema_version"] != 1:
        raise ValueError("native capture schema_version must be integer 1")
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
    if (
        not isinstance(fields, list)
        or len(fields) != len(PLAYER_FIELDS)
        or any(not isinstance(value, str) for value in fields)
        or set(fields) != PLAYER_FIELDS
    ):
        raise ValueError("state_fields must declare the exact supported selected player fields")
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
    if environment["input_policy"] != INPUT_POLICY:
        raise ValueError(f"Native capture input_policy must be {INPUT_POLICY}")
    _bool(environment["configuration_complete"], "environment.configuration_complete")
    clocks = _fields(
        environment["clocks"],
        "environment.clocks",
        {
            "unit",
            "dt_unit",
            "hardware_arrival",
            "render_cadence",
        },
    )
    expected_clocks = {
        "unit": "processCommands_call_index",
        "dt_unit": "seconds_as_passed_to_hook",
        "hardware_arrival": "unknown",
        "render_cadence": "not_captured",
    }
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
            "blocked_inputs",
            "trace",
            "terminal",
        },
    )
    _text(attempt["id"], "attempt.id")
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
            },
        )
        if _int(row["command_index"], f"trace[{index}].command_index") != index:
            raise ValueError("Native trace call indices must start at zero and be contiguous")
        finite(row["dt_seconds"], f"trace[{index}].dt_seconds", minimum=0, maximum=60)
        _bool(row["is_half_tick"], f"trace[{index}].is_half_tick")
        _bool(row["is_last_tick"], f"trace[{index}].is_last_tick")
        state = _fields(row["state"], f"trace[{index}].state", {"player1", "player2"})
        _player(state["player1"], f"trace[{index}].state.player1")
        if state["player2"] is not None:
            _player(state["player2"], f"trace[{index}].state.player2")
        if index == 0 and (row["dt_seconds"] != 0 or row["is_half_tick"] or row["is_last_tick"]):
            raise ValueError(
                "Initial trace must precede command processing with zero dt and false tick flags"
            )
    inputs = attempt["inputs"]
    if not isinstance(inputs, list) or len(inputs) > MAX_INPUT_RECORDS:
        raise ValueError(f"inputs must contain at most {MAX_INPUT_RECORDS} records")
    blocked = attempt["blocked_inputs"]
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
            },
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
        if attempt["input_source"] == "replay" and event["source"] != "replay":
            raise ValueError("Controlled replay recording contains an unexpected observed input")
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
        },
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
    terminal_state = _fields(terminal["state"], "terminal.state", {"player1", "player2"})
    _player(terminal_state["player1"], "terminal.state.player1")
    if terminal_state["player2"] is not None:
        _player(terminal_state["player2"], "terminal.state.player2")
    # Terminal-hook and post-process snapshots need not be equal: they are
    # intentionally captured at different points in the native call stack.
    terminal_dead = any(state is not None and state["is_dead"] for state in terminal_state.values())
    if terminal["outcome"] == "died" and not terminal_dead:
        raise ValueError("A native death requires a recorded dead player after destroyPlayer")
    if attempt["input_source"] == "replay":
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
        for row in capture["attempt"]["blocked_inputs"]
    ]


def _flat_player_fields(state: dict) -> dict:
    """Expose each selected value independently, including player presence."""
    fields = {}
    for name in ("player1", "player2"):
        player = state[name]
        fields[f"{name}.present"] = player is not None
        for key in sorted(PLAYER_FIELDS):
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


def _terminal_component_diagnostics(baseline: dict, compared: dict) -> dict:
    keys = ("outcome", "event", "command_index")
    left_callback = {key: baseline[key] for key in keys}
    right_callback = {key: compared[key] for key in keys}
    left_fields = _flat_player_fields(baseline["state"])
    right_fields = _flat_player_fields(compared["state"])
    return {
        "callback_and_placement_equal": left_callback == right_callback,
        "selected_player_fields_equal": baseline["state"] == compared["state"],
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
    }


def _summary(capture: dict, source_sha256: str) -> dict:
    warnings = [
        "The supplied file's declared native origin is not authenticated or independently verified.",
        "Recorded state covers selected player fields, not complete world/trigger/input/clock state.",
        "processCommands call indices are not certified physics ticks; dt is the hook argument.",
        "Callback return values do not measure physical input arrival, display latency or human intent.",
        "No human performance, timing windows, difficulty probability or AR is inferred.",
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
    else:
        warnings.extend(
            [
                "Replay suppresses unknown-origin non-injector handleButton requests; vanilla-input equivalence is not established.",
                "Direct PlayerObject push/release calls bypassing handleButton are not controlled by replay channel ownership.",
                "Blocked inputs were not forwarded; their effect on a counterfactual unsuppressed trajectory is not measured.",
            ]
        )
    if capture["attempt"]["terminal"]["outcome"] == "completed" and any(
        state is not None and state["is_dead"] for state in capture["attempt"]["terminal"]["state"].values()
    ):
        warnings.append(
            "A selected player dead flag is present at completion; player activity is not captured, "
            "so this flag cannot override the reported completion callback."
        )
    return {
        "schema_version": 1,
        "kind": "native_capture_inspection",
        "source_sha256": source_sha256,
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
        "attempt": {
            key: value
            for key, value in capture["attempt"].items()
            if key not in {"planned_inputs", "inputs", "blocked_inputs", "trace", "terminal"}
        },
        "terminal": capture["attempt"]["terminal"],
        "counts": {
            "input_records": len(capture["attempt"]["inputs"]),
            "blocked_input_records": len(capture["attempt"]["blocked_inputs"]),
            "state_records": len(capture["attempt"]["trace"]),
            "planned_inputs": len(capture["attempt"]["planned_inputs"]),
            "unexecuted_planned_tail": sum(
                row["command_index"] > capture["attempt"]["terminal"]["command_index"]
                for row in capture["attempt"]["planned_inputs"]
            ),
        },
        "replay_execution_status": "observed_prefix_through_terminal"
        if capture["attempt"]["input_source"] == "replay"
        else "not_a_controlled_replay",
        "recorded_input_sha256": canonical_sha256(_input_signature(capture)),
        "blocked_input_diagnostics": {
            "source": "unknown",
            "delivery_status": "not_forwarded_to_native_handleButton",
            "counterfactual_trajectory_effect": "not_measured",
            "records": capture["attempt"]["blocked_inputs"],
            "signature_sha256": canonical_sha256(_blocked_signature(capture)),
        },
        "recorded_state_sha256": canonical_sha256(capture["attempt"]["trace"]),
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
        for key in ("challenge", "environment", "environment_sha256", "collector", "provenance"):
            if capture[key] != base[key]:
                raise ValueError(f"Incompatible capture {key}")
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
    base_call_arguments = [{key: value for key, value in row.items() if key != "state"} for row in base_trace]
    base_player_fields = [_flat_player_fields(row["state"]) for row in base_trace]
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
            [{key: value for key, value in row.items() if key != "state"} for row in capture_trace],
        )
        player_fields = _trace_component_diagnostics(
            base_player_fields, [_flat_player_fields(row["state"]) for row in capture_trace]
        )
        terminal_components = _terminal_component_diagnostics(
            base["attempt"]["terminal"], capture["attempt"]["terminal"]
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
                "terminal_diagnostics": terminal_components,
                "first_different_state_call_index": first_state_difference,
                "consistent": planned_inputs_equal and inputs_equal and state_equal and terminal_equal,
            }
        )
    consistent = all(row["consistent"] for row in comparisons)
    return {
        "schema_version": 1,
        "kind": "native_capture_comparison",
        "status": "recorded_subset_consistent" if consistent else "recorded_subset_inconsistent",
        "comparison_rule": "exact_recorded_call_arguments_player_fields_inputs_and_terminal",
        "component_consistency": {
            key: all(row[key] for row in comparisons)
            for key in (
                "planned_inputs_equal",
                "recorded_inputs_equal",
                "recorded_call_arguments_equal",
                "recorded_player_fields_equal",
                "terminal_callback_and_placement_equal",
                "terminal_player_fields_equal",
            )
        },
        "authentication_status": "not_authenticated",
        "physics_status": "not_independently_verified",
        "m1_gate": "not_established_by_file_inspection",
        "complete_state_determinism": "not_established",
        "replay_execution_scope": "planned_prefix_through_native_terminal",
        "challenge": base["challenge"],
        "environment_sha256": base["environment_sha256"],
        "replay_sha256": base["attempt"]["replay_sha256"],
        "attempt_count": len(captures),
        "baseline_attempt_id": base["attempt"]["id"],
        "baseline_source_sha256": captures[0][1],
        "blocked_input_diagnostics": {
            "source": "unknown",
            "delivery_status": "not_forwarded_to_native_handleButton",
            "comparison_influence": "excluded_from_recorded_subset_consistency",
            "counterfactual_trajectory_effect": "not_measured",
            "status": "diagnostic_records_equal"
            if all(row["blocked_inputs_equal"] for row in comparisons)
            else "diagnostic_records_different",
            "attempts": [
                {
                    "attempt_id": capture["attempt"]["id"],
                    "record_count": len(capture["attempt"]["blocked_inputs"]),
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
            "Blocked unknown-origin requests were not forwarded and are diagnostic only; differences do not affect delivered subset consistency.",
            "The effect of suppressed requests on a counterfactual unsuppressed trajectory is not measured; vanilla-input equivalence is unsupported.",
            "Direct PlayerObject push/release calls bypassing handleButton are outside replay channel control.",
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
