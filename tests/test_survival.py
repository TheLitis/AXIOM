"""Statistical and provenance checks for the empirical cohort path."""

import hashlib
import json
import math
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from axiom.survival import analyze_cohort, kaplan_meier, load_cohort


def cohort_with(rows: list[tuple[float, bool]]) -> dict:
    challenge = {
        "id": "synthetic-target",
        "level_sha256": "a" * 64,
        "game_version": "synthetic-test",
        "physics_version": "synthetic-test",
        "input_policy": "synthetic-policy",
        "environment_id": "synthetic-desktop",
    }
    profile = {
        "id": "test-profile",
        "skill_definition": "Synthetic fixed skills",
        "sampling_method": "Synthetic independent participants",
    }
    protocol = {
        "id": "test-protocol",
        "version": "1",
        "fixed": True,
        "time_basis": "active_hours",
        "practice_policy": "Synthetic active practice included",
        "censoring_policy": "Synthetic administratively fixed follow-up",
    }
    return {
        "schema_version": 1,
        "cohort_id": "test-cohort",
        "synthetic": True,
        "challenge": challenge,
        "profile": profile,
        "population_id": "test-population",
        "protocol": protocol,
        "observations": [
            {
                "participant_id": f"p{index}",
                "time_hours": time,
                "completed": event,
                **({} if event else {"censor_reason": "scheduled_follow_up_end"}),
            }
            for index, (time, event) in enumerate(rows)
        ],
        "reference": {
            "id": "synthetic-reference",
            "version": "1",
            "source_cohort_id": "synthetic-reference-cohort",
            "synthetic": True,
            "challenge": {**challenge, "id": "synthetic-baseline", "level_sha256": "b" * 64},
            "profile": deepcopy(profile),
            "population_id": "test-population",
            "protocol": deepcopy(protocol),
            "t50_hours": 2.0,
        },
    }


class SurvivalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "cohort.json"

    def analyze(self, document: dict, **kwargs) -> dict:
        self.path.write_text(json.dumps(document), encoding="utf-8")
        return analyze_cohort(self.path, **kwargs)

    def test_censor_only_never_manufactures_completion_or_rating(self) -> None:
        report = self.analyze(cohort_with([(1, False), (2, False), (4, False)]), bootstrap_samples=200)
        self.assertIsNone(report["t50_hours"])
        self.assertIsNone(report["rating"]["ar"])
        self.assertIsNone(report["t50_bootstrap_ci95"])
        self.assertEqual(report["cohort_summary"]["completed"], 0)
        self.assertTrue(all(point["survival"] == 1 for point in report["curve"]))
        self.assertTrue(all(point["survival_ci95"] is None for point in report["curve"]))
        self.assertEqual(report["bootstrap"]["finite_medians"], 0)

    def test_tied_event_and_censor_are_both_in_risk_set(self) -> None:
        report = self.analyze(
            cohort_with([(1, True), (1, False), (2, True), (3, False)]), bootstrap_samples=0
        )
        curve = report["curve"]
        self.assertEqual([point["at_risk"] for point in curve], [4, 2, 1])
        self.assertEqual([point["survival"] for point in curve], [0.75, 0.375, 0.375])
        self.assertEqual(curve[0]["events"], 1)
        self.assertEqual(curve[0]["censored"], 1)
        self.assertEqual(report["t50_hours"], 2)

    def test_km_median_uses_lower_crossing_and_100_points_per_doubling(self) -> None:
        report = self.analyze(cohort_with([(2, True), (4, True), (8, True), (16, True)]), bootstrap_samples=0)
        self.assertEqual(report["t50_hours"], 4)
        self.assertAlmostEqual(report["rating"]["ar"], 1100)
        self.assertEqual(report["rating"]["points_per_doubling"], 100)
        self.assertEqual(report["rating"]["status"], "provisional_empirical")
        self.assertTrue(report["rating"]["synthetic"])
        self.assertIsNone(report["rating"]["ar_ci95"])

    def test_exact_half_survival_is_a_reached_median(self) -> None:
        report = self.analyze(cohort_with([(i, True) for i in range(1, 7)]), bootstrap_samples=0)
        self.assertEqual(report["t50_hours"], 3)
        self.assertEqual(report["curve"][2]["survival"], 0.5)

    def test_loglog_greenwood_interval_and_boundary(self) -> None:
        report = self.analyze(cohort_with([(1, True), (2, True), (3, True), (4, True)]), bootstrap_samples=0)
        lower, upper = report["curve"][0]["survival_ci95"]
        self.assertAlmostEqual(lower, 0.12794691759514576)
        self.assertAlmostEqual(upper, 0.9605486422850784)
        self.assertLess(lower, 0.75)
        self.assertGreater(upper, 0.75)
        self.assertEqual(report["curve"][-1]["survival"], 0)
        self.assertIsNone(report["curve"][-1]["survival_ci95"])

    def test_bootstrap_is_seeded_and_resamples_whole_participant_rows(self) -> None:
        document = cohort_with([(1, True), (2, True), (3, True), (4, True)])
        first = self.analyze(document, bootstrap_samples=1000, seed=42)
        second = self.analyze(document, bootstrap_samples=1000, seed=42)
        self.assertEqual(first["bootstrap"], second["bootstrap"])
        self.assertEqual(first["bootstrap"]["finite_fraction"], 1)
        self.assertEqual(first["t50_bootstrap_ci95"], [1, 4])
        self.assertEqual(first["bootstrap"]["status"], "provisional_percentile_interval")
        json.dumps(first, allow_nan=False)

    def test_bootstrap_unreached_medians_are_not_discarded(self) -> None:
        report = self.analyze(cohort_with([(1, True), (2, False)]), bootstrap_samples=2000, seed=5)
        self.assertEqual(report["t50_hours"], 1)
        self.assertIsNone(report["t50_bootstrap_ci95"])
        self.assertEqual(report["bootstrap"]["status"], "insufficient_finite_medians")
        self.assertTrue(0.70 < report["bootstrap"]["finite_fraction"] < 0.80)

    def test_too_few_resamples_cannot_claim_confidence_interval(self) -> None:
        report = self.analyze(cohort_with([(1, True), (2, True)]), bootstrap_samples=199)
        self.assertEqual(report["bootstrap"]["status"], "too_few_resamples")
        self.assertIsNone(report["t50_bootstrap_ci95"])

    def test_fixed_protocol_and_reference_are_required_for_rating(self) -> None:
        document = cohort_with([(1, True), (2, True)])
        del document["reference"]
        report = self.analyze(document, bootstrap_samples=0)
        self.assertIsNone(report["rating"]["ar"])
        self.assertIn("calibration_reference_missing", report["rating"]["unavailable_reasons"])
        document["protocol"]["fixed"] = False
        report = self.analyze(document, bootstrap_samples=0)
        self.assertIn("protocol_not_fixed", report["rating"]["unavailable_reasons"])

    def test_reference_mismatch_is_rejected(self) -> None:
        for target, key, replacement in [
            ("reference", "population_id", "other"),
            ("protocol", "version", "other"),
            ("challenge", "physics_version", "other"),
            ("profile", "id", "other"),
            ("reference", "synthetic", False),
        ]:
            with self.subTest(target=target, key=key):
                document = cohort_with([(1, True)])
                section = document["reference"] if target == "reference" else document["reference"][target]
                section[key] = replacement
                with self.assertRaisesRegex(ValueError, "incompatible"):
                    self.analyze(document, bootstrap_samples=0)

    def test_row_identity_overrides_must_match(self) -> None:
        for identity in ("challenge", "profile", "protocol"):
            with self.subTest(identity=identity):
                document = cohort_with([(1, True)])
                document["observations"][0][identity] = deepcopy(document[identity])
                document["observations"][0][identity]["id"] = "another-id"
                with self.assertRaisesRegex(ValueError, "incompatible"):
                    self.analyze(document, bootstrap_samples=0)

    def test_malformed_times_and_status_are_rejected(self) -> None:
        for time in (0, -1, math.nan, math.inf, -math.inf, True, "2", 10**1000):
            with self.subTest(time=str(time)[:20]):
                with self.assertRaises(ValueError):
                    self.analyze(cohort_with([(time, True)]), bootstrap_samples=0)
        for status in (0, 1, "true", None):
            with self.subTest(status=status):
                with self.assertRaisesRegex(ValueError, "boolean"):
                    self.analyze(cohort_with([(1, status)]), bootstrap_samples=0)

    def test_duplicate_participants_and_json_keys_are_rejected(self) -> None:
        document = cohort_with([(1, True), (2, False)])
        document["observations"][1]["participant_id"] = "p0"
        with self.assertRaisesRegex(ValueError, "duplicate participant"):
            self.analyze(document, bootstrap_samples=0)
        self.path.write_text('{"schema_version": 1, "schema_version": 1}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            load_cohort(self.path)

    def test_censor_reason_is_required_and_not_allowed_on_completion(self) -> None:
        document = cohort_with([(1, False)])
        del document["observations"][0]["censor_reason"]
        with self.assertRaisesRegex(ValueError, "censor_reason is required"):
            self.analyze(document, bootstrap_samples=0)
        document = cohort_with([(1, True)])
        document["observations"][0]["censor_reason"] = "wrong"
        with self.assertRaisesRegex(ValueError, "cannot have censor_reason"):
            self.analyze(document, bootstrap_samples=0)

    def test_challenge_hash_and_zero_reference_rejected(self) -> None:
        document = cohort_with([(1, True)])
        document["challenge"]["level_sha256"] = "not-a-hash"
        with self.assertRaisesRegex(ValueError, "hexadecimal"):
            self.analyze(document, bootstrap_samples=0)
        document = cohort_with([(1, True)])
        document["reference"]["t50_hours"] = 0
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            self.analyze(document, bootstrap_samples=0)

    def test_extreme_positive_times_do_not_overflow_rating_ratio(self) -> None:
        document = cohort_with([(1e-300, True)])
        document["reference"]["t50_hours"] = 1e300
        report = self.analyze(document, bootstrap_samples=0)
        self.assertTrue(math.isfinite(report["rating"]["ar"]))
        json.dumps(report, allow_nan=False)

    def test_public_estimator_rejects_nonempty_and_bad_rows(self) -> None:
        with self.assertRaises(ValueError):
            kaplan_meier([])
        with self.assertRaises(ValueError):
            kaplan_meier([{"time_hours": 1, "completed": "yes"}])

    def test_example_is_explicitly_synthetic_and_analyzable(self) -> None:
        example = Path(__file__).resolve().parents[1] / "examples" / "cohort.json"
        report = analyze_cohort(example, bootstrap_samples=200, seed=8)
        self.assertTrue(report["synthetic"])
        self.assertEqual(report["status"], "synthetic_demonstration")
        self.assertTrue(any("SYNTHETIC DATA" in warning for warning in report["warnings"]))
        self.assertEqual(report["source_sha256"], hashlib.sha256(example.read_bytes()).hexdigest())

    def test_observation_and_bootstrap_work_are_bounded(self) -> None:
        with self.assertRaisesRegex(ValueError, "participant limit"):
            self.analyze(cohort_with([(1, True)] * 5001), bootstrap_samples=0)
        with self.assertRaisesRegex(ValueError, "workload"):
            self.analyze(cohort_with([(1, True)] * 1001), bootstrap_samples=2000)

    def test_invalid_bootstrap_options_rejected(self) -> None:
        for samples in (-1, True, 1.5, 100001):
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                self.analyze(cohort_with([(1, True)]), bootstrap_samples=samples)
        with self.assertRaisesRegex(ValueError, "seed"):
            self.analyze(cohort_with([(1, True)]), bootstrap_samples=0, seed=True)


if __name__ == "__main__":
    unittest.main()
