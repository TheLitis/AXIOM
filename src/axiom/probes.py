"""Discrete probe maps with explicit missing, failed and repeated observations.

Finite accepted command-index samples do not certify continuous timing windows.
This layer consumes a frozen experiment and preserves backend evidence scope.
"""

from collections import Counter, deque

from .probeplan import study_sha256, validate_probe_study
from .validation import mapping, read_json, sha256, string

OUTCOMES = {"completed", "died", "runner_error", "rejected"}


def _fields(value, name, fields):
    value = mapping(value, name)
    if value.keys() != set(fields):
        raise ValueError(f"{name} requires exactly: {', '.join(sorted(fields))}")
    return value


def _synthetic_observations(study, results):
    _fields(results, "backend results", {"schema_version", "kind", "study_sha256", "backend", "attempts"})
    if type(results["schema_version"]) is not int or results["schema_version"] != 1:
        raise ValueError("Probe backend results require schema_version 1")
    if results["kind"] != "probe_backend_results" or results["study_sha256"] != study_sha256(study):
        raise ValueError("Probe backend results differ from the frozen study")
    backend = _fields(results["backend"], "backend", {"id", "origin"})
    string(backend["id"], "backend.id")
    if backend["origin"] != "synthetic":
        raise ValueError("Synthetic terminal witnesses require a synthetic backend")
    trials = {trial["id"]: trial for trial in study["trials"]}
    points = {point["id"]: point for point in study["points"]}
    attempts = results["attempts"]
    if not isinstance(attempts, list) or len(attempts) > len(trials):
        raise ValueError("Probe attempts exceed the frozen study")
    seen, executions, normalized = set(), set(), []
    for row in attempts:
        _fields(row, "backend attempt", {"trial_id", "outcome", "terminal_witness", "error"})
        trial_id = string(row["trial_id"], "trial_id")
        if trial_id not in trials or trial_id in seen:
            raise ValueError("Unknown or duplicate probe trial_id")
        seen.add(trial_id)
        if not isinstance(row["outcome"], str) or row["outcome"] not in {"completed", "died", "runner_error"}:
            raise ValueError("Invalid synthetic backend outcome")
        witness = row["terminal_witness"]
        if row["outcome"] == "runner_error":
            if witness is not None:
                raise ValueError("Runner errors cannot carry a terminal witness")
            string(row["error"], "runner_error")
            execution_id = None
        else:
            if row["error"] is not None:
                raise ValueError("A terminal witness cannot carry a runner error")
            _fields(
                witness,
                "synthetic terminal witness",
                {"kind", "start_kind", "event", "replay_file_sha256", "environment_sha256", "execution_id"},
            )
            point = points[trials[trial_id]["point_id"]]
            if (
                witness["kind"] != "synthetic-full-run-terminal"
                or witness["start_kind"] != "level_start"
                or witness["event"] != row["outcome"]
                or witness["replay_file_sha256"] != point["replay_file_sha256"]
                or witness["environment_sha256"] != study["reference"]["environment_sha256"]
            ):
                raise ValueError("Synthetic witness differs from the frozen full-start job")
            execution_id = string(witness["execution_id"], "execution_id")
            if execution_id in executions:
                raise ValueError("Synthetic execution_id cannot be reused across repetitions")
            executions.add(execution_id)
        normalized.append(
            {
                "trial_id": trial_id,
                "outcome": row["outcome"],
                "terminal_state_sha256": None,
                "native_terminal_event": None,
                "command_index": None,
                "evidence_sha256": None,
                "evidence_origin": "synthetic",
                "execution_id": execution_id,
                "error": row["error"],
            }
        )
    return {
        "schema_version": 1,
        "kind": "probe_observations",
        "study_sha256": study_sha256(study),
        "origin": "synthetic-backend",
        "authentication_status": "not_authenticated",
        "attempts": normalized,
    }


def _classify_point(point, rows, repetitions, *, native):
    counts = Counter(row["outcome"] for row in rows)
    if point["status"] == "invalid_schedule":
        status = "invalid_schedule"
    elif len(rows) < repetitions:
        status = "incomplete"
    elif counts["runner_error"] or counts["rejected"]:
        status = "unknown"
    elif counts["completed"] and counts["died"]:
        status = "inconsistent_repeats"
    elif (
        native
        and len(
            {
                (row["terminal_state_sha256"], row["native_terminal_event"], row["command_index"])
                for row in rows
            }
        )
        != 1
    ):
        status = "inconsistent_repeats"
    else:
        status = "accepted_sample" if counts["completed"] == repetitions else "death_sample"
    return {
        "point_id": point["id"],
        "offsets_commands": point["offsets_commands"],
        "status": status,
        "schedule_reason": point["reason"],
        "observed_repetitions": len(rows),
        "required_repetitions": 0 if point["status"] == "invalid_schedule" else repetitions,
        "counts": {key: counts[key] for key in sorted(OUTCOMES)},
        "missing_repetitions": 0 if point["status"] == "invalid_schedule" else repetitions - len(rows),
        "trial_ids": [row["trial_id"] for row in rows],
        "repeat_check_scope": "terminal_outcome_state_event_command_only"
        if native
        else "synthetic_terminal_outcome_only",
    }


def _components(points):
    """Connect accepted sampled vertices differing by exactly one command."""
    accepted = {
        tuple(point["offsets_commands"]): point["point_id"]
        for point in points
        if point["status"] == "accepted_sample"
    }
    remaining = set(accepted)
    components = []
    while remaining:
        seed = min(remaining)
        queue, members = deque([seed]), []
        remaining.remove(seed)
        while queue:
            coordinate = queue.popleft()
            members.append(coordinate)
            for axis in range(len(coordinate)):
                for step in (-1, 1):
                    neighbor = list(coordinate)
                    neighbor[axis] += step
                    neighbor = tuple(neighbor)
                    if neighbor in remaining:
                        remaining.remove(neighbor)
                        queue.append(neighbor)
        members.sort()
        components.append(
            {
                "point_ids": [accepted[coordinate] for coordinate in members],
                "offsets_commands": [list(coordinate) for coordinate in members],
                "sample_count": len(members),
            }
        )
    return components


def _slices(study, points):
    slices = []
    for index, axis in enumerate(study["spec"]["axes"]):
        rows = [
            point
            for point in points
            if all(value == 0 for j, value in enumerate(point["offsets_commands"]) if j != index)
        ]
        slices.append(
            {
                "event_index": axis["event_index"],
                "other_axis_offsets_commands": 0,
                "samples": [
                    {
                        "offset_commands": point["offsets_commands"][index],
                        "status": point["status"],
                        "point_id": point["point_id"],
                    }
                    for point in rows
                ],
                "accepted_offsets_commands": [
                    point["offsets_commands"][index] for point in rows if point["status"] == "accepted_sample"
                ],
                "interpolation": "not_performed",
            }
        )
    return slices


def summarize_probe_observations(study, observations):
    """Assemble a sampled map from already validated adapter observations."""
    validate_probe_study(study)
    _fields(
        observations,
        "probe observations",
        {"schema_version", "kind", "study_sha256", "origin", "authentication_status", "attempts"},
    )
    if (
        type(observations["schema_version"]) is not int
        or observations["schema_version"] != 1
        or observations["kind"] != "probe_observations"
        or observations["study_sha256"] != study_sha256(study)
        or not isinstance(observations["origin"], str)
        or observations["origin"] not in {"synthetic-backend", "native-capture-files"}
        or observations["authentication_status"] != "not_authenticated"
    ):
        raise ValueError("Invalid or mismatched probe observations")
    attempts = observations["attempts"]
    trials = {trial["id"]: trial for trial in study["trials"]}
    if not isinstance(attempts, list) or len(attempts) > len(trials):
        raise ValueError("Probe observations exceed the study")
    by_point = {point["id"]: [] for point in study["points"]}
    seen, executions = set(), set()
    for row in attempts:
        _fields(
            row,
            "probe observation",
            {
                "trial_id",
                "outcome",
                "terminal_state_sha256",
                "native_terminal_event",
                "command_index",
                "evidence_sha256",
                "evidence_origin",
                "execution_id",
                "error",
            },
        )
        trial_id = string(row["trial_id"], "trial_id")
        if trial_id not in trials or trial_id in seen:
            raise ValueError("Unknown or duplicate probe observation trial_id")
        seen.add(trial_id)
        if not isinstance(row["outcome"], str) or row["outcome"] not in OUTCOMES:
            raise ValueError("Unsupported probe observation outcome")
        for name in ("terminal_state_sha256", "evidence_sha256"):
            if row[name] is not None:
                sha256(row[name], name)
        if row["error"] is not None:
            string(row["error"], "observation.error")
        if row["outcome"] in {"completed", "died"}:
            execution_id = string(row["execution_id"], "observation.execution_id")
            if execution_id in executions:
                raise ValueError("A successful terminal execution cannot be reused")
            executions.add(execution_id)
            if row["error"] is not None:
                raise ValueError("Terminal observations cannot carry a runner error")
            if observations["origin"] == "native-capture-files":
                expected = (
                    "PlayLayer::levelComplete"
                    if row["outcome"] == "completed"
                    else "PlayLayer::destroyPlayer"
                )
                if (
                    row["native_terminal_event"] != expected
                    or type(row["command_index"]) is not int
                    or row["command_index"] < 0
                    or not isinstance(row["evidence_origin"], str)
                    or row["evidence_origin"] not in {"synthetic", "native-engine-capture"}
                    or row["terminal_state_sha256"] is None
                    or row["evidence_sha256"] is None
                ):
                    raise ValueError("Native terminal observation lacks the declared witness")
            elif (
                row["evidence_origin"] != "synthetic"
                or row["native_terminal_event"] is not None
                or row["command_index"] is not None
                or row["terminal_state_sha256"] is not None
                or row["evidence_sha256"] is not None
            ):
                raise ValueError("Synthetic terminal observation cannot declare native evidence")
        else:
            string(row["error"], "failed observation error")
            if any(
                row[name] is not None
                for name in (
                    "terminal_state_sha256",
                    "native_terminal_event",
                    "command_index",
                    "execution_id",
                )
            ):
                raise ValueError("Failed observations cannot carry a successful terminal witness")
        by_point[trials[trial_id]["point_id"]].append(row)
    native = observations["origin"] == "native-capture-files"
    points = [
        _classify_point(point, by_point[point["id"]], study["spec"]["repetitions"], native=native)
        for point in study["points"]
    ]
    counts = Counter(point["status"] for point in points)
    baseline = next(point for point in points if not any(point["offsets_commands"]))
    accepted = [point for point in points if point["status"] == "accepted_sample"]
    projections = [
        sorted({point["offsets_commands"][axis] for point in accepted})
        for axis in range(len(study["spec"]["axes"]))
    ]
    counterexamples = [
        {"point_id": point["point_id"], "offsets_commands": point["offsets_commands"]}
        for point in points
        if point["status"] == "death_sample"
        and all(value in projections[axis] for axis, value in enumerate(point["offsets_commands"]))
    ]
    return {
        "schema_version": 1,
        "kind": "native_probe_map",
        "protocol": study["protocol"],
        "study_sha256": study_sha256(study),
        "measurement_origin": observations["origin"],
        "reference_capture_sha256": study["reference"]["capture_sha256"],
        "challenge": study["reference"]["challenge"],
        "environment_sha256": study["reference"]["environment_sha256"],
        "clock": "processCommands_call_index",
        "clock_policy": "fixed-scheduler-240",
        "offset_unit": "command_call",
        "axes": study["spec"]["axes"],
        "grid_status": "complete_declared_grid"
        if not any(counts[name] for name in ("incomplete", "unknown", "inconsistent_repeats"))
        else "partially_observed_grid",
        "baseline_control": {
            "point_id": baseline["point_id"],
            "status": baseline["status"],
            "established": baseline["status"] == "accepted_sample",
        },
        "eligible_for_sampled_map": baseline["status"] == "accepted_sample",
        "counts": {
            "grid_points": len(points),
            "planned_trials": len(trials),
            "observed_trials": len(attempts),
            "missing_trials": len(trials) - len(attempts),
            **{
                name: counts[name]
                for name in (
                    "accepted_sample",
                    "death_sample",
                    "invalid_schedule",
                    "incomplete",
                    "unknown",
                    "inconsistent_repeats",
                )
            },
        },
        "points": points,
        "axis_slices": _slices(study, points),
        "accepted_sample_components": _components(points),
        "component_adjacency": "one_command_on_one_axis_at_an_observed_accepted_vertex",
        "marginal_accepted_projections_commands": projections,
        "observed_marginal_product_counterexamples": counterexamples,
        "attempts": attempts,
        "scope": {
            "full_start_required": True,
            "continuous_windows": "not_established",
            "between_grid_samples": "not_tested",
            "hardware_timing": "not_measured",
            "checkpoint_composition": "not_supported",
            "physical_impossibility": "not_established",
            "authentication": "not_authenticated",
            "m1_gate": "not_established",
            "m2_gate": "not_established",
            "human_calibration": "not_established",
            "real_level_ar": "not_established",
        },
    }


def analyze_probe_results(study_path, results_path):
    """Load a synthetic backend ledger or hash-bound native capture references."""
    study, study_digest = read_json(study_path)
    validate_probe_study(study)
    results, digest = read_json(results_path)
    if results.get("kind") == "native_probe_results":
        from .probeadapter import inspect_native_probe_results

        observations = inspect_native_probe_results(study_path, results_path)
    else:
        observations = _synthetic_observations(study, results)
    report = summarize_probe_observations(study, observations)
    if read_json(study_path)[1] != study_digest or read_json(results_path)[1] != digest:
        raise ValueError("Probe study or result bytes changed during map construction")
    report["study_file_sha256"] = study_digest
    report["results_file_sha256"] = digest
    return report


def synthetic_probe_demo(reference_path, spec_path, output_directory):
    """Run an explicit disconnected diagonal truth fixture, with no game calls."""
    from .probeplan import create_probe_study
    from .proberun import (
        SyntheticProbeBackend,
        materialize_probe_study,
        prepare_probe_directory,
        run_probe_backend,
        write_probe_json,
    )

    study = create_probe_study(reference_path, spec_path)
    if len(study["spec"]["axes"]) != 2:
        raise ValueError("The synthetic diagonal demo requires exactly two axes")
    output = prepare_probe_directory(output_directory)
    study_path = output / "study.json"
    write_probe_json(study_path, study)
    materialize_probe_study(study_path, output / "exchange")
    backend = SyntheticProbeBackend(
        study, lambda offsets: offsets[0] == offsets[1] and offsets[0] in {-2, 0, 2}
    )
    results_path = output / "results.json"
    run_probe_backend(study_path, backend, results_path)
    report = analyze_probe_results(study_path, results_path)
    report_path = output / "map.json"
    write_probe_json(report_path, report)
    return {
        "kind": "synthetic_probe_demo",
        "study_path": str(study_path),
        "results_path": str(results_path),
        "map_path": str(report_path),
        "counts": report["counts"],
        "backend": "disconnected_diagonal_synthetic_truth",
        "new_native_execution": False,
    }
