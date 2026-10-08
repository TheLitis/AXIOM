# Contributing to AXIOM

AXIOM welcomes engineering, statistics, motor-control research and player input. Begin with an issue explaining the intended result, evidence and acceptance criterion. Small changes can be submitted directly.

## Development

Use Python 3.11+ and `uv sync --locked --extra dev`. Run `uv run --locked pytest -q`, `uv run --locked ruff check .`, `uv run --locked ruff format --check .` and `uv run --locked axiom demo`. The analysis package has no runtime dependencies. Pin/justify any proposed runtime dependency.

Keep changes proportionate and scoped. Tests should establish meaningful invariants: correlated vs independent failures, censoring, units, identity mismatch, input order or uncertainty boundaries. Include malformed-file tests for import changes. Formatting and spelling edits do not require new tests.

## Evidence requirements

- Keep raw source identity, challenge version, environment, protocol and provenance attached to every result.
- Clearly distinguish synthetic, supplied measurements, independently verified engine evidence and calibrated human predictions.
- Never map assumed click noise to a real human AR, infer impossibility from failed search, or replace an unreached median with a guessed tail.
- Factor additions require an operational measurement and a planned validation; coefficients need calibration or an explicit sensitivity label.
- A rating-semantic change needs a model/reference version and migration explanation.
- Native adapters need same-start replay, completion-oracle and state-continuation evidence for their supported game build.
- Publish consented and licensed data only. Use pseudonymous IDs; keep identity mappings, private telemetry, credentials and save files outside Git.

Discuss limitations plainly. A negative result or a failed replication can be more valuable than a larger leaderboard.
