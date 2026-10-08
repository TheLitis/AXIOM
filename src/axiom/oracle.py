"""Inspect full-run oracle trial ledgers without pretending to run the game."""

from collections import defaultdict

from .validation import challenge_identity, finite, integer, mapping, read_json, sha256, string


def inspect_trials(path):
    data, digest = read_json(path)
    if (
        type(data.get("schema_version")) is not int
        or data["schema_version"] != 1
        or data.get("kind") != "oracle_trials"
    ):
        raise ValueError("Expected schema_version 1, kind oracle_trials")
    challenge = challenge_identity(data.get("challenge"))
    provenance = mapping(data.get("provenance"), "provenance")
    if string(provenance.get("origin"), "provenance.origin") not in {"synthetic", "engine-capture"}:
        raise ValueError("oracle provenance.origin must be synthetic or engine-capture")
    engine_build = string(data.get("engine_build"), "engine_build")
    initial_state = sha256(data.get("initial_state_sha256"), "initial_state_sha256")
    replay = sha256(data.get("replay_sha256"), "replay_sha256")
    if data.get("full_run") is not True:
        raise ValueError("Full-run terminal oracle required; partial segment survival is insufficient")
    event_count = integer(data.get("event_count"), "event_count", minimum=1, maximum=10000)
    trials = data.get("trials")
    if not isinstance(trials, list) or not 1 <= len(trials) <= 100000:
        raise ValueError("trials must contain 1 to 100000 records")
    if event_count * len(trials) > 2_000_000:
        raise ValueError("Oracle ledger exceeds 2 million offsets")
    ids = set()
    repeats = defaultdict(list)
    counts = {"completed": 0, "died": 0, "error": 0}
    for trial in trials:
        trial = mapping(trial, "trial")
        trial_id = string(trial.get("id"), "trial.id")
        if trial_id in ids:
            raise ValueError("Duplicate trial id")
        ids.add(trial_id)
        if trial.get("challenge", challenge) != challenge:
            raise ValueError("Trial challenge identity differs from ledger")
        if trial.get("initial_state_sha256", initial_state) != initial_state:
            raise ValueError("Trial initial state differs from ledger")
        for field, expected in (
            ("replay_sha256", replay),
            ("engine_build", engine_build),
            ("full_run", True),
        ):
            if field in trial and (
                trial[field] != expected or (field == "full_run" and trial[field] is not True)
            ):
                raise ValueError(f"Trial {field} differs from ledger")
        offsets = trial.get("offsets_ms")
        if not isinstance(offsets, list) or len(offsets) != event_count:
            raise ValueError("offsets_ms must have one finite offset per replay event")
        offsets = tuple(finite(x, "offset", minimum=-10000, maximum=10000) for x in offsets)
        outcome = string(trial.get("outcome"), "trial.outcome")
        if outcome not in counts:
            raise ValueError("outcome must be completed, died, or error")
        elapsed = finite(trial.get("elapsed_seconds"), "elapsed_seconds", minimum=0, maximum=86400)
        if outcome != "error":
            sha256(trial.get("terminal_state_sha256"), "terminal_state_sha256")
            repeats[offsets].append((outcome, trial["terminal_state_sha256"], elapsed))
        counts[outcome] += 1
    repeated = [values for values in repeats.values() if len(values) > 1]
    inconsistent = sum(len(set(values)) > 1 for values in repeated)
    warnings = [
        "This is inspection of supplied evidence, not live engine verification.",
        "A successful sampled offset vector does not establish continuous timing windows.",
        "A failed search does not prove physical impossibility.",
        "Trials are selected perturbations, not a random human sample; no success probability or AR is inferred.",
    ]
    if provenance["origin"] == "synthetic":
        warnings.insert(0, "SYNTHETIC oracle fixture, not a Geometry Dash execution.")
    if counts["error"]:
        warnings.append("Engine errors remain unknown outcomes and are never counted as deaths.")
    if inconsistent:
        warnings.append(
            "Identical initial state and offsets have inconsistent reported outcomes/state hashes."
        )
    return {
        "schema_version": 1,
        "kind": "oracle_inspection",
        "source_sha256": digest,
        "challenge": challenge,
        "provenance": provenance,
        "engine_build": engine_build,
        "initial_state_sha256": initial_state,
        "replay_sha256": replay,
        "status": "supplied_evidence_only",
        "physics_status": "not_independently_verified",
        "counts": counts,
        "unique_valid_vectors": len(repeats),
        "determinism": {
            "repeated_vectors": len(repeated),
            "inconsistent_vectors": inconsistent,
            "status": "inconsistent"
            if inconsistent
            else "consistent_observed_repeats"
            if repeated
            else "not_tested",
        },
        "warnings": warnings,
    }
