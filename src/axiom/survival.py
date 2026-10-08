"""Empirical first-completion analysis, with explicit right censoring.

This module does not simulate Geometry Dash or measure a human performance limit.
All estimates are conditional on the supplied cohort, protocol and provenance.
"""

from __future__ import annotations

import math
import random
import re
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
from statistics import NormalDist
from typing import Any, Sequence

from .validation import read_json

SCHEMA_VERSION = 1
RATING_MODEL = "axiom-ar-log2-v0"
CHALLENGE_FIELDS = frozenset(
    {"id", "level_sha256", "game_version", "physics_version", "input_policy", "environment_id"}
)
PROFILE_FIELDS = frozenset({"id", "skill_definition", "sampling_method"})
PROTOCOL_FIELDS = frozenset({"id", "version", "fixed", "time_basis", "practice_policy", "censoring_policy"})
MIN_BOOTSTRAP_SAMPLES = 200
MAX_OBSERVATIONS = 5000
MAX_BOOTSTRAP_WORK = 2_000_000
CONFIDENCE_LEVEL = 0.95


def _object(
    value: Any,
    location: str,
    required: set[str] | frozenset[str],
    optional: set[str] | frozenset[str] = frozenset(),
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{location} must be an object")
    missing = required - value.keys()
    unknown = value.keys() - required - optional
    if missing:
        raise ValueError(f"{location} missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"{location} unknown fields: {', '.join(sorted(unknown))}")
    return value


def _string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > 1024:
        raise ValueError(f"{location} must be a nonempty, trimmed string (max 1024 characters)")
    return value


def _positive_number(value: Any, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{location} must be a finite number greater than zero")
    try:
        number = float(value)
    except (ValueError, OverflowError) as error:
        raise ValueError(f"{location} must be a finite number greater than zero") from error
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{location} must be a finite number greater than zero")
    return number


def _boolean(value: Any, location: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{location} must be a JSON boolean")
    return value


def _challenge(value: Any, location: str) -> dict[str, Any]:
    descriptor = _object(value, location, CHALLENGE_FIELDS)
    for key in CHALLENGE_FIELDS:
        _string(descriptor[key], f"{location}.{key}")
    if not re.fullmatch(r"[0-9a-f]{64}", descriptor["level_sha256"]):
        raise ValueError(f"{location}.level_sha256 must be 64 lowercase hexadecimal digits")
    return descriptor


def _profile(value: Any, location: str) -> dict[str, Any]:
    descriptor = _object(value, location, PROFILE_FIELDS)
    for key in PROFILE_FIELDS:
        _string(descriptor[key], f"{location}.{key}")
    return descriptor


def _protocol(value: Any, location: str) -> dict[str, Any]:
    descriptor = _object(value, location, PROTOCOL_FIELDS)
    for key in PROTOCOL_FIELDS - {"fixed"}:
        _string(descriptor[key], f"{location}.{key}")
    _boolean(descriptor["fixed"], f"{location}.fixed")
    if descriptor["time_basis"] != "active_hours":
        raise ValueError(f"{location}.time_basis must be active_hours")
    return descriptor


def _load_cohort(path: str | Path) -> tuple[dict[str, Any], str]:
    """Load and validate a version 1 cohort; raise ValueError on incompatibility.

    Shared identities apply to every row. Optional repeated identity fields are
    checked, so accidentally merging another challenge or protocol is rejected.
    SHA256 is a declared identity, not independent proof that a level was played.
    """
    cohort, source_sha256 = read_json(path)
    _object(
        cohort,
        "cohort",
        {
            "schema_version",
            "cohort_id",
            "synthetic",
            "challenge",
            "profile",
            "population_id",
            "protocol",
            "observations",
        },
        {"reference", "notes"},
    )
    if type(cohort["schema_version"]) is not int or cohort["schema_version"] != SCHEMA_VERSION:
        raise ValueError("cohort.schema_version must be integer 1")
    _string(cohort["cohort_id"], "cohort.cohort_id")
    _string(cohort["population_id"], "cohort.population_id")
    _boolean(cohort["synthetic"], "cohort.synthetic")
    challenge = _challenge(cohort["challenge"], "cohort.challenge")
    profile = _profile(cohort["profile"], "cohort.profile")
    protocol = _protocol(cohort["protocol"], "cohort.protocol")
    if "notes" in cohort:
        _string(cohort["notes"], "cohort.notes")
    observations = cohort["observations"]
    if not isinstance(observations, list) or not observations:
        raise ValueError("cohort.observations must be a nonempty array")
    if len(observations) > MAX_OBSERVATIONS:
        raise ValueError(f"cohort.observations exceeds {MAX_OBSERVATIONS} participant limit")
    participants: set[str] = set()
    for index, raw in enumerate(observations):
        location = f"cohort.observations[{index}]"
        row = _object(
            raw,
            location,
            {"participant_id", "time_hours", "completed"},
            {
                "censor_reason",
                "challenge",
                "profile",
                "protocol",
                "population_id",
            },
        )
        participant = _string(row["participant_id"], f"{location}.participant_id")
        if participant in participants:
            raise ValueError(f"duplicate participant_id: {participant}")
        participants.add(participant)
        row["time_hours"] = _positive_number(row["time_hours"], f"{location}.time_hours")
        completed = _boolean(row["completed"], f"{location}.completed")
        if not completed and "censor_reason" not in row:
            raise ValueError(f"{location}.censor_reason is required for a censored row")
        if completed and "censor_reason" in row:
            raise ValueError(f"{location}: completed rows cannot have censor_reason")
        if "censor_reason" in row:
            _string(row["censor_reason"], f"{location}.censor_reason")
        for key, identity, validator in (
            ("challenge", challenge, _challenge),
            ("profile", profile, _profile),
            ("protocol", protocol, _protocol),
        ):
            if key in row and validator(row[key], f"{location}.{key}") != identity:
                raise ValueError(f"{location}.{key} is incompatible with the cohort")
        if "population_id" in row:
            _string(row["population_id"], f"{location}.population_id")
            if row["population_id"] != cohort["population_id"]:
                raise ValueError(f"{location}.population_id is incompatible with the cohort")

    if "reference" in cohort:
        reference = _object(
            cohort["reference"],
            "cohort.reference",
            {
                "id",
                "version",
                "source_cohort_id",
                "synthetic",
                "challenge",
                "profile",
                "population_id",
                "protocol",
                "t50_hours",
            },
        )
        for key in ("id", "version", "source_cohort_id", "population_id"):
            _string(reference[key], f"cohort.reference.{key}")
        reference["t50_hours"] = _positive_number(reference["t50_hours"], "cohort.reference.t50_hours")
        _boolean(reference["synthetic"], "cohort.reference.synthetic")
        if reference["synthetic"] != cohort["synthetic"]:
            raise ValueError("reference synthetic provenance is incompatible with the cohort")
        if reference["population_id"] != cohort["population_id"]:
            raise ValueError("reference population_id is incompatible with the cohort")
        if _profile(reference["profile"], "cohort.reference.profile") != profile:
            raise ValueError("reference profile is incompatible with the cohort")
        if _protocol(reference["protocol"], "cohort.reference.protocol") != protocol:
            raise ValueError("reference protocol is incompatible with the cohort")
        reference_challenge = _challenge(reference["challenge"], "cohort.reference.challenge")
        for key in CHALLENGE_FIELDS - {"id", "level_sha256"}:
            if reference_challenge[key] != challenge[key]:
                raise ValueError(f"reference challenge.{key} is incompatible with the cohort")
    return cohort, source_sha256


def load_cohort(path: str | Path) -> dict[str, Any]:
    """Load a valid version 1 cohort, rejecting malformed/incompatible input."""
    return _load_cohort(path)[0]


def _loglog_interval(survival: float, greenwood_sum: float) -> list[float] | None:
    # The log-log transform is undefined at S=0 and S=1. Returning null avoids
    # showing zero-width boundary intervals as evidence of certainty.
    if not 0.0 < survival < 1.0:
        return None
    log_survival = math.log(survival)
    center = math.log(-log_survival)
    error = NormalDist().inv_cdf(0.975) * math.sqrt(greenwood_sum) / abs(log_survival)

    def inverse(value: float) -> float:
        # Avoid exp overflow; its limit gives a survival probability of zero.
        return 0.0 if value > math.log(745.0) else math.exp(-math.exp(value))

    return [inverse(center + error), inverse(center - error)]


def kaplan_meier(observations: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Estimate S(t)=P(first completion time > t) for validated observations.

    At tied times, both completed and censored players are in the risk set;
    completions act first and then all tied rows leave the risk set.
    """
    if not observations:
        raise ValueError("Kaplan-Meier requires at least one observation")
    grouped: dict[float, list[int]] = defaultdict(lambda: [0, 0])
    for row in observations:
        time = _positive_number(row.get("time_hours"), "observation.time_hours")
        completed = _boolean(row.get("completed"), "observation.completed")
        grouped[time][0 if completed else 1] += 1
    at_risk = len(observations)
    survival_fraction = Fraction(1)
    greenwood_sum = 0.0
    median: float | None = None
    curve: list[dict[str, Any]] = []
    for time, (events, censored) in sorted(grouped.items()):
        if events:
            survival_fraction *= Fraction(at_risk - events, at_risk)
            if events < at_risk:
                greenwood_sum += events / (at_risk * (at_risk - events))
            if median is None and survival_fraction <= Fraction(1, 2):
                median = time
        survival = float(survival_fraction)
        interval = _loglog_interval(survival, greenwood_sum)
        curve.append(
            {
                "time_hours": time,
                "at_risk": at_risk,
                "events": events,
                "censored": censored,
                "survival": survival,
                "completion_probability": 1.0 - survival,
                "survival_ci95": interval,
                "survival_ci_status": "pointwise_loglog_greenwood" if interval else "boundary_undefined",
            }
        )
        at_risk -= events + censored
    return {"curve": curve, "t50_hours": median}


def _median_only(observations: Sequence[dict[str, Any]]) -> float | None:
    # Bootstrap rows may repeat the same participant because resampling the
    # whole independent unit, including censoring, is the intended operation.
    grouped: dict[float, list[int]] = defaultdict(lambda: [0, 0])
    for row in observations:
        grouped[row["time_hours"]][0 if row["completed"] else 1] += 1
    at_risk = len(observations)
    survival = Fraction(1)
    for time, (events, censored) in sorted(grouped.items()):
        if events:
            survival *= Fraction(at_risk - events, at_risk)
            if survival <= Fraction(1, 2):
                return time
        at_risk -= events + censored
    return None


def _bootstrap(
    observations: Sequence[dict[str, Any]], samples: int, seed: int, observed_median: float | None
) -> dict[str, Any]:
    if type(samples) is not int or not 0 <= samples <= 100_000:
        raise ValueError("bootstrap_samples must be an integer between 0 and 100000")
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    if samples * len(observations) > MAX_BOOTSTRAP_WORK:
        raise ValueError("bootstrap workload exceeds 2000000 participant draws; reduce bootstrap_samples")
    result: dict[str, Any] = {
        "method": "participant_percentile_nearest_rank_extended_distribution",
        "confidence_level": CONFIDENCE_LEVEL,
        "samples": samples,
        "seed": seed,
        "finite_medians": 0,
        "finite_fraction": None,
        "t50_ci95_hours": None,
        "status": "disabled" if samples == 0 else "pending",
    }
    if samples == 0:
        return result
    rng = random.Random(seed)
    medians = []
    count = len(observations)
    for _ in range(samples):
        sample = [observations[rng.randrange(count)] for _ in range(count)]
        median = _median_only(sample)
        medians.append(math.inf if median is None else median)
    medians.sort()
    finite = sum(math.isfinite(median) for median in medians)
    result["finite_medians"] = finite
    result["finite_fraction"] = finite / samples
    if observed_median is None:
        result["status"] = "observed_t50_unreached"
    elif samples < MIN_BOOTSTRAP_SAMPLES:
        result["status"] = "too_few_resamples"
    else:
        lower = medians[max(0, math.ceil(0.025 * samples) - 1)]
        upper = medians[max(0, math.ceil(0.975 * samples) - 1)]
        # The full bootstrap distribution contains infinite/unreached medians.
        # Never form a seemingly finite CI by discarding those draws.
        if not math.isfinite(upper) or finite / samples < 0.975:
            result["status"] = "insufficient_finite_medians"
        else:
            result["t50_ci95_hours"] = [lower, upper]
            result["status"] = "provisional_percentile_interval"
    return result


def analyze_cohort(path: str | Path, bootstrap_samples: int = 1000, seed: int = 0) -> dict[str, Any]:
    """Return a JSON-safe report; all available AR results remain provisional."""
    cohort, source_sha256 = _load_cohort(path)
    observations = cohort["observations"]
    estimate = kaplan_meier(observations)
    median = estimate["t50_hours"]
    bootstrap = _bootstrap(observations, bootstrap_samples, seed, median)
    completed = sum(row["completed"] for row in observations)
    warnings = [
        "Empirical cohort estimates are not proof of physical feasibility or a human performance limit.",
        "Independent censoring and representative participant sampling are assumptions, not verified by this file.",
        "Pointwise survival confidence intervals are not simultaneous bands, T50 intervals, or AR intervals.",
    ]
    if cohort["synthetic"]:
        warnings.append(
            "SYNTHETIC DATA: these numbers demonstrate the pipeline and are not Geometry Dash measurements."
        )
    if len(observations) < 30:
        warnings.append("Small cohort: asymptotic and bootstrap intervals may have poor coverage.")
    if median is None:
        warnings.append("Observed T50 was not reached; no tail extrapolation or AR is reported.")
    if bootstrap["status"] not in {"disabled", "provisional_percentile_interval"}:
        warnings.append(f"No finite T50 bootstrap interval: {bootstrap['status']}.")
    if bootstrap["status"] == "provisional_percentile_interval":
        warnings.append(
            "The T50 bootstrap interval is provisional; it excludes calibration error, selection bias and model uncertainty."
        )

    reference = cohort.get("reference")
    reasons = []
    if not cohort["protocol"]["fixed"]:
        reasons.append("protocol_not_fixed")
    if reference is None:
        reasons.append("calibration_reference_missing")
    if median is None:
        reasons.append("observed_t50_unreached")
    rating: dict[str, Any] = {
        "model": RATING_MODEL,
        "formula": "1000 + 100 * log2(T50_hours / reference_T50_hours)",
        "points_per_doubling": 100,
        "ar": None,
        "status": "unavailable" if reasons else "provisional_empirical",
        "synthetic": cohort["synthetic"],
        "unavailable_reasons": reasons,
        "reference": reference,
        "ar_ci95": None,
        "uncertainty_status": "calibration_and_model_uncertainty_not_estimated",
    }
    if not reasons:
        # Subtraction of logs avoids overflow/underflow in the time ratio.
        rating["ar"] = 1000 + 100 * (math.log2(median) - math.log2(reference["t50_hours"]))
        warnings.append(
            "AR uses a fixed declared calibration T50; its source and uncertainty were not independently verified."
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "analysis": "kaplan_meier_first_completion_v0",
        "cohort_id": cohort["cohort_id"],
        "source_sha256": source_sha256,
        "synthetic": cohort["synthetic"],
        "status": "synthetic_demonstration" if cohort["synthetic"] else "provisional_empirical",
        "challenge": cohort["challenge"],
        "profile": cohort["profile"],
        "population_id": cohort["population_id"],
        "protocol": cohort["protocol"],
        "cohort_summary": {
            "participants": len(observations),
            "completed": completed,
            "censored": len(observations) - completed,
            "last_observed_time_hours": max(row["time_hours"] for row in observations),
        },
        **estimate,
        "t50_status": "observed_km_median" if median is not None else "unreached",
        "bootstrap": bootstrap,
        "t50_bootstrap_ci95": bootstrap["t50_ci95_hours"],
        "rating": rating,
        "warnings": warnings,
    }
