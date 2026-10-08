"""Route-conditional timing scenarios; this module does not simulate GD physics."""

import math
import random
import sys

from .validation import challenge_identity, finite, integer, mapping, read_json, string


def load_scenario(path):
    data, digest = read_json(path)
    if (
        type(data.get("schema_version")) is not int
        or data["schema_version"] != 1
        or data.get("kind") != "timing_scenario"
    ):
        raise ValueError("Expected schema_version 1, kind timing_scenario")
    challenge = challenge_identity(data.get("challenge"))
    provenance = mapping(data.get("provenance"), "provenance")
    if string(provenance.get("origin"), "provenance.origin") not in {
        "synthetic",
        "manual",
        "engine-measured",
    }:
        raise ValueError("provenance.origin must be synthetic, manual, or engine-measured")
    string(provenance.get("description"), "provenance.description")
    noise = mapping(data.get("noise"), "noise")
    noise = {
        "sigma_ms": finite(noise.get("sigma_ms"), "noise.sigma_ms", minimum=0, maximum=10000),
        "shift_sigma_ms": finite(
            noise.get("shift_sigma_ms", 0), "noise.shift_sigma_ms", minimum=0, maximum=10000
        ),
        "drift_sigma_ms": finite(
            noise.get("drift_sigma_ms", 0), "noise.drift_sigma_ms", minimum=0, maximum=10000
        ),
        "rho": finite(noise.get("rho", 0), "noise.rho", minimum=-1, maximum=1),
        "bias_ms": finite(noise.get("bias_ms", 0), "noise.bias_ms", minimum=-10000, maximum=10000),
    }
    routes = data.get("routes")
    if not isinstance(routes, list) or not 1 <= len(routes) <= 64:
        raise ValueError("routes must contain 1 to 64 routes")
    seen_ids = set()
    normalized = []
    for route in routes:
        route = mapping(route, "route")
        route_id = string(route.get("id"), "route.id")
        if route_id in seen_ids:
            raise ValueError("Duplicate route id")
        seen_ids.add(route_id)
        duration = finite(route.get("duration_seconds"), "duration_seconds", minimum=0, maximum=86400)
        events = route.get("events")
        if not isinstance(events, list) or not 1 <= len(events) <= 10000:
            raise ValueError("events must contain 1 to 10000 input events")
        normalized_events = []
        channels = {}
        last_time = -1
        for event in events:
            event = mapping(event, "event")
            t = finite(event.get("time_seconds"), "event.time_seconds", minimum=0, maximum=duration)
            if t < last_time:
                raise ValueError("events must be sorted by nominal time")
            last_time = t
            button = integer(event.get("button", 1), "event.button", minimum=1, maximum=3)
            player = integer(event.get("player", 1), "event.player", minimum=1, maximum=2)
            down = event.get("down")
            if not isinstance(down, bool):
                raise ValueError("event.down must be boolean")
            key = (player, button)
            if channels.get(key, False) == down:
                raise ValueError("Events must alternate press/release per channel, initially released")
            channels[key] = down
            windows = event.get("windows_ms")
            if not isinstance(windows, list) or not 1 <= len(windows) <= 128:
                raise ValueError("windows_ms must contain 1 to 128 disjoint closed intervals")
            clean_windows = []
            prev_end = -math.inf
            for window in windows:
                if not isinstance(window, list) or len(window) != 2:
                    raise ValueError("A timing interval must be [lower_ms, upper_ms]")
                lo = finite(window[0], "window lower", minimum=-10000, maximum=10000)
                hi = finite(window[1], "window upper", minimum=-10000, maximum=10000)
                if lo > hi or lo <= prev_end:
                    raise ValueError("Windows must be ordered, disjoint, and lower <= upper")
                prev_end = hi
                clean_windows.append((lo, hi))
            normalized_events.append(
                {
                    "time_seconds": t,
                    "button": button,
                    "player": player,
                    "down": down,
                    "windows_ms": clean_windows,
                }
            )
        constraints = route.get("joint_constraints", [])
        if not isinstance(constraints, list) or len(constraints) > 10000:
            raise ValueError("joint_constraints must be a list of at most 10000 items")
        clean_constraints = []
        for constraint in constraints:
            constraint = mapping(constraint, "constraint")
            terms = constraint.get("terms")
            if not isinstance(terms, list) or not 1 <= len(terms) <= len(events):
                raise ValueError("Constraint terms must be nonempty [event_index, coefficient] pairs")
            clean_terms = []
            seen_indices = set()
            for term in terms:
                if not isinstance(term, list) or len(term) != 2:
                    raise ValueError("Constraint term must be [event_index, coefficient]")
                i = integer(term[0], "event index", minimum=0, maximum=len(events) - 1)
                coefficient = finite(term[1], "coefficient", minimum=-1000, maximum=1000)
                if i in seen_indices or coefficient == 0:
                    raise ValueError("Constraint indices must be unique; coefficients nonzero")
                seen_indices.add(i)
                clean_terms.append((i, coefficient))
            lo = finite(constraint.get("lower_ms"), "constraint.lower_ms")
            hi = finite(constraint.get("upper_ms"), "constraint.upper_ms")
            if lo > hi:
                raise ValueError("Constraint lower must not exceed upper")
            clean_constraints.append({"terms": clean_terms, "lower_ms": lo, "upper_ms": hi})
        normalized.append(
            {
                "id": route_id,
                "label": string(route.get("label", route_id), "route.label"),
                "duration_seconds": duration,
                "events": normalized_events,
                "joint_constraints": clean_constraints,
            }
        )
    return {
        "challenge": challenge,
        "provenance": provenance,
        "noise": noise,
        "routes": normalized,
        "source_sha256": digest,
    }


def normal_interval_probability(windows, sigma_ms, bias_ms=0):
    """Probability over a disjoint interval union, including asymmetric windows."""
    if sigma_ms == 0:
        return float(any(lo <= bias_ms <= hi for lo, hi in windows))
    scale = sigma_ms * math.sqrt(2)
    probability = 0.0
    for lo, hi in windows:
        a, b = (lo - bias_ms) / scale, (hi - bias_ms) / scale
        # erfc avoids cancellation for windows entirely in one normal tail.
        if a >= 0:
            probability += 0.5 * (math.erfc(a) - math.erfc(b))
        elif b <= 0:
            probability += 0.5 * (math.erfc(-b) - math.erfc(-a))
        else:
            probability += 0.5 * (math.erf(b) - math.erf(a))
    return min(1.0, max(0.0, probability))


def wilson_interval(successes, trials):
    z = 1.959963984540054
    p = successes / trials
    denominator = 1 + z * z / trials
    center = (p + z * z / (2 * trials)) / denominator
    width = z * math.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denominator
    return [max(0.0, center - width), min(1.0, center + width)]


def _accept(route, offsets):
    if len(offsets) != len(route["events"]) or not all(math.isfinite(x) for x in offsets):
        return False
    for event, offset in zip(route["events"], offsets):
        if not any(lo <= offset <= hi for lo, hi in event["windows_ms"]):
            return False
    # Offsets may not reverse press/release on the same button/player channel.
    channel_times = {}
    for event, offset in zip(route["events"], offsets):
        actual_time = event["time_seconds"] + offset / 1000
        if not 0 <= actual_time <= route["duration_seconds"]:
            return False
        key = (event["player"], event["button"])
        if actual_time < channel_times.get(key, -math.inf):
            return False
        channel_times[key] = actual_time
    for constraint in route["joint_constraints"]:
        value = sum(offsets[i] * coefficient for i, coefficient in constraint["terms"])
        if not constraint["lower_ms"] <= value <= constraint["upper_ms"]:
            return False
    return True


def analyze_scenario(path, trials=20000, seed=0, sigma_ms=None):
    scenario = load_scenario(path)
    trials = integer(trials, "trials", minimum=1, maximum=200000)
    seed = integer(seed, "seed", minimum=0, maximum=2**53 - 1)
    workload = trials * sum(
        2 * len(route["events"])
        + sum(len(event["windows_ms"]) for event in route["events"])
        + sum(len(c["terms"]) + 1 for c in route["joint_constraints"])
        for route in scenario["routes"]
    )
    if workload > 20_000_000:
        raise ValueError("Scenario workload exceeds 20 million operations; reduce --trials")
    noise = scenario["noise"].copy()
    if sigma_ms is not None:
        noise["sigma_ms"] = finite(sigma_ms, "sigma_ms", minimum=0, maximum=10000)
    marginal_sigma = math.sqrt(
        noise["sigma_ms"] ** 2 + noise["shift_sigma_ms"] ** 2 + noise["drift_sigma_ms"] ** 2
    )
    routes = []
    for route_index, route in enumerate(scenario["routes"]):
        rng = random.Random(seed + route_index)
        marginal = []
        for event in route["events"]:
            earliest = -1000 * event["time_seconds"]
            latest = 1000 * (route["duration_seconds"] - event["time_seconds"])
            windows = [
                (max(lo, earliest), min(hi, latest))
                for lo, hi in event["windows_ms"]
                if max(lo, earliest) <= min(hi, latest)
            ]
            marginal.append(normal_interval_probability(windows, marginal_sigma, noise["bias_ms"]))
        log_p = sum(math.log(p) for p in marginal) if all(p > 0 for p in marginal) else None
        independent_p = math.exp(log_p) if log_p is not None else 0.0
        independent_sigma = noise["sigma_ms"]
        shift_sigma = noise["shift_sigma_ms"]
        drift_sigma = noise["drift_sigma_ms"]
        innovation_sigma = drift_sigma * math.sqrt(max(0, 1 - noise["rho"] ** 2))
        successes = 0
        for _ in range(trials):
            shift = rng.gauss(0, shift_sigma)
            drift = rng.gauss(0, drift_sigma)
            offsets = []
            for i in range(len(route["events"])):
                if i:
                    drift = noise["rho"] * drift + rng.gauss(0, innovation_sigma)
                offsets.append(noise["bias_ms"] + shift + drift + rng.gauss(0, independent_sigma))
            successes += _accept(route, offsets)
        presses = sum(event["down"] for event in route["events"])
        min_width = min(sum(hi - lo for lo, hi in event["windows_ms"]) for event in route["events"])
        routes.append(
            {
                "id": route["id"],
                "label": route["label"],
                "event_count": len(route["events"]),
                "press_count": presses,
                "duration_seconds": route["duration_seconds"],
                "minimum_window_union_ms": min_width,
                "joint_constraint_count": len(route["joint_constraints"]),
                "independent_marginal_probability": independent_p,
                "independent_log_probability": log_p,
                "modeled_pass_probability": successes / trials,
                "monte_carlo_ci95": wilson_interval(successes, trials),
                "successes": successes,
                "trials": trials,
                "events": route["events"],
            }
        )
    warnings = [
        "Timing scenario only: no native Geometry Dash physics was executed.",
        "Noise parameters are assumptions, not calibrated human measurements.",
        "Confidence intervals quantify Monte Carlo sampling error only, not model uncertainty.",
        "Independent baseline ignores joint constraints and input ordering; it is a comparison model.",
        "AR and human time-to-completion are not inferred from scenario probabilities.",
    ]
    if scenario["provenance"]["origin"] == "synthetic":
        warnings.insert(0, "SYNTHETIC demonstration; no real level rating.")
    if any(route["successes"] == 0 for route in routes):
        warnings.append(
            "Zero simulated successes is not proof of impossibility; see the nonzero upper bound."
        )
    return {
        "schema_version": 1,
        "kind": "timing_analysis",
        "axiom_version": "0.1.0",
        "challenge": scenario["challenge"],
        "source_sha256": scenario["source_sha256"],
        "provenance": scenario["provenance"],
        "status": "uncalibrated_scenario",
        "physics_status": "not_assessed",
        "ar": None,
        "seed": seed,
        "noise": noise,
        "python_version": sys.version.split()[0],
        "routes": routes,
        "warnings": warnings,
    }
