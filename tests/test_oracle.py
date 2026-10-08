import json

import pytest

from axiom.oracle import inspect_trials


def ledger():
    return {
        "schema_version": 1,
        "kind": "oracle_trials",
        "challenge": {
            "id": "test",
            "level_sha256": "a" * 64,
            "game_version": "synthetic",
            "physics_version": "fixture-v1",
            "input_policy": "test",
            "environment_id": "test",
        },
        "provenance": {"origin": "synthetic"},
        "engine_build": "fixture",
        "initial_state_sha256": "b" * 64,
        "replay_sha256": "c" * 64,
        "event_count": 2,
        "full_run": True,
        "trials": [
            {
                "id": "1",
                "offsets_ms": [0, 0],
                "outcome": "completed",
                "elapsed_seconds": 2,
                "terminal_state_sha256": "d" * 64,
            },
            {
                "id": "2",
                "offsets_ms": [0, 0],
                "outcome": "completed",
                "elapsed_seconds": 2,
                "terminal_state_sha256": "d" * 64,
            },
        ],
    }


def inspect(tmp_path, data):
    path = tmp_path / "trials.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return inspect_trials(path)


def test_determinism_and_errors(tmp_path):
    data = ledger()
    assert inspect(tmp_path, data)["determinism"]["status"] == "consistent_observed_repeats"
    data["trials"][1]["outcome"] = "died"
    assert inspect(tmp_path, data)["determinism"]["status"] == "inconsistent"
    data["trials"][1]["outcome"] = "error"
    result = inspect(tmp_path, data)
    assert result["counts"] == {"completed": 1, "died": 0, "error": 1}
    assert result["determinism"]["status"] == "not_tested"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(full_run=False),
        lambda d: d["trials"][0].update(initial_state_sha256="f" * 64),
        lambda d: d["trials"][0].update(offsets_ms=[0]),
        lambda d: d["trials"][0].update(terminal_state_sha256="unknown"),
        lambda d: d["trials"][1].update(id="1"),
        lambda d: d.update(schema_version=True),
        lambda d: d["provenance"].update(origin=[]),
        lambda d: d["trials"][0].update(outcome=[]),
        lambda d: d["trials"][0].update(replay_sha256="f" * 64),
        lambda d: d["trials"][0].update(engine_build="wrong"),
        lambda d: d["trials"][0].update(full_run=False),
    ],
)
def test_invalid_ledgers_rejected(tmp_path, mutation):
    with pytest.raises(ValueError):
        inspect(tmp_path, mutation_data(mutation))


def mutation_data(mutation):
    data = ledger()
    mutation(data)
    return data


def test_elapsed_time_is_part_of_repeatability(tmp_path):
    data = ledger()
    data["trials"][1]["elapsed_seconds"] = 20
    assert inspect(tmp_path, data)["determinism"]["status"] == "inconsistent"
