import json
import math

import pytest

from axiom.timing import _accept, analyze_scenario, load_scenario, normal_interval_probability


def scenario_data():
    return {
        "schema_version": 1,
        "kind": "timing_scenario",
        "challenge": {
            "id": "test",
            "level_sha256": "a" * 64,
            "game_version": "synthetic",
            "physics_version": "fixture-v1",
            "input_policy": "continuous-ms",
            "environment_id": "synthetic",
        },
        "provenance": {"origin": "synthetic", "description": "unit fixture"},
        "noise": {"sigma_ms": 0, "shift_sigma_ms": 5},
        "routes": [
            {
                "id": "diagonal",
                "duration_seconds": 2,
                "events": [
                    {"time_seconds": 0.5, "down": True, "windows_ms": [[-100, 100]]},
                    {"time_seconds": 1, "down": False, "windows_ms": [[-100, 100]]},
                ],
                "joint_constraints": [{"terms": [[0, -1], [1, 1]], "lower_ms": -0.1, "upper_ms": 0.1}],
            }
        ],
    }


def write(tmp_path, data):
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_gaussian_probability_and_asymmetry():
    assert normal_interval_probability([(-1, 1)], 1) == pytest.approx(0.682689492)
    assert normal_interval_probability([(0, 1)], 1) == pytest.approx(0.341344746)
    assert normal_interval_probability([(-1, 1)], 0, 2) == 0
    assert normal_interval_probability([(-1, 1)], 0, 1) == 1
    assert normal_interval_probability([(8, 9)], 1) > 0  # no normal-tail cancellation


def test_disjoint_windows():
    p = normal_interval_probability([(-2, -1), (1, 2)], 1)
    assert p == pytest.approx(0.271810244)


def test_joint_correlation_materially_changes_success(tmp_path):
    data = scenario_data()
    common = analyze_scenario(write(tmp_path, data), trials=3000, seed=9)
    data["noise"] = {"sigma_ms": 5}
    independent = analyze_scenario(write(tmp_path, data), trials=3000, seed=9)
    assert common["routes"][0]["modeled_pass_probability"] == 1
    assert independent["routes"][0]["modeled_pass_probability"] < 0.03
    assert common["ar"] is None
    assert common["physics_status"] == "not_assessed"


def test_seed_is_reproducible_and_zero_has_upper_bound(tmp_path):
    data = scenario_data()
    data["noise"] = {"sigma_ms": 1}
    data["routes"][0]["events"][0]["windows_ms"] = [[100, 101]]
    path = write(tmp_path, data)
    a = analyze_scenario(path, trials=100, seed=11)
    assert a == analyze_scenario(path, trials=100, seed=11)
    assert a["routes"][0]["successes"] == 0
    assert 0 < a["routes"][0]["monte_carlo_ci95"][1] < 0.1


def test_ordering_and_level_boundary(tmp_path):
    route = load_scenario(write(tmp_path, scenario_data()))["routes"][0]
    route["joint_constraints"] = []
    for event in route["events"]:
        event["windows_ms"] = [(-1000, 1000)]
    assert not _accept(route, [600, -600])  # release moved before press
    assert not _accept(route, [-600, 0])  # before level starts
    assert _accept(route, [0, 0])


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["noise"].update(sigma_ms=float("nan")),
        lambda d: d["noise"].update(rho=2),
        lambda d: d["routes"][0]["events"][0].update(windows_ms=[[1, -1]]),
        lambda d: d["routes"][0]["events"][0].update(windows_ms=[[-1, 1], [0, 2]]),
        lambda d: d["routes"][0]["events"][1].update(down=True),
        lambda d: d["routes"][0]["joint_constraints"][0].update(terms=[[2, 1]]),
        lambda d: d["challenge"].update(level_sha256="missing"),
        lambda d: d.update(routes=[]),
        lambda d: d.update(schema_version=True),
        lambda d: d["provenance"].update(origin=[]),
        lambda d: d["provenance"].update(extra=float("inf")),
        lambda d: d["provenance"].update(description="\ud800"),
    ],
)
def test_bad_scenarios_rejected(tmp_path, mutation):
    data = scenario_data()
    mutation(data)
    with pytest.raises(ValueError):
        load_scenario(write(tmp_path, data))


def test_boolean_and_huge_trial_counts_rejected(tmp_path):
    path = write(tmp_path, scenario_data())
    for trials in (True, 0, 1000000000, math.inf):
        with pytest.raises(ValueError):
            analyze_scenario(path, trials=trials)


def test_duplicate_json_keys_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"schema_version":1,"schema_version":2}', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate JSON"):
        load_scenario(path)


def test_workload_counts_each_constraint_term(tmp_path):
    data = scenario_data()
    route = data["routes"][0]
    route["joint_constraints"] = [{"terms": [[0, -1], [1, 1]], "lower_ms": -2, "upper_ms": 2}] * 50
    with pytest.raises(ValueError, match="workload"):
        analyze_scenario(write(tmp_path, data), trials=200000)


def test_baseline_includes_run_time_boundaries(tmp_path):
    data = scenario_data()
    data["noise"] = {"sigma_ms": 1}
    data["routes"][0]["events"] = [{"time_seconds": 0, "down": True, "windows_ms": [[-100, 100]]}]
    data["routes"][0]["joint_constraints"] = []
    report = analyze_scenario(write(tmp_path, data), trials=3000, seed=9)
    route = report["routes"][0]
    assert route["independent_marginal_probability"] == pytest.approx(0.5)
    assert route["modeled_pass_probability"] == pytest.approx(0.5, abs=0.04)
