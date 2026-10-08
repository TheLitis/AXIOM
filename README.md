<p align="center"><strong>AXIOM</strong><br>Geometry Dash Difficulty Model<br><em>Difficulty that can be explained.</em></p>

[![CI](https://github.com/TheLitis/AXIOM/actions/workflows/ci.yml/badge.svg)](https://github.com/TheLitis/AXIOM/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-79efd0.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-86b4ff.svg)](pyproject.toml)

[Русская версия](README.ru.md) · [Final-system requirements](docs/end-goal-requirements.md) · [Methodology](docs/methodology.md) · [Architecture](docs/architecture.md) · [Roadmap](docs/roadmap.md)

AXIOM is an open research project for measuring Geometry Dash difficulty through reproducible game evidence, human execution and learning. **Axiom Rating (AR)** is the proposed presentation scale; the model and its evidence come first.

The central question is: *What is the probability that a player with a specified skill profile completes this exact challenge after a specified amount of practice, under specified technical conditions?*

## Current status: offline laboratory and experimental native observer

The released v0.1.0 is a dependency-free Python laboratory with an interactive offline report. Current development adds an experimental, opt-in Windows x64 / GD 2.2081 / Geode 5.8.2 observer and command-call replay. **Human difficulty remains uncalibrated and the complete M1 acceptance gate remains open.** Native origin declared in an imported file is not authenticated by the Python inspector. There are no established AR scores for real levels, no GRIEF/Slaughterhouse difficulty ratio, and no claim of a universal human limit.

The [initial native validation ledger](docs/native-validation.md) retains the failed replay comparison. The subsequent [clock investigation](docs/clock-investigation.md) tested two generated fixtures under three clock policies, with three replay completions per case. Exact agreement of all compared fields passed for both fixtures under the explicitly declared fixed Scheduler intervention; the native and fixed gameplay-update policies still diverged. This establishes repeatability of the recorded subset in that experimental environment. Raw captures and game binaries stay local.

| Available now | Evidence and limits |
|---|---|
| Raw level-string inspection | Exact source/decoded hashes, settings, object IDs, positions and unknown keys; no collider or trigger simulation |
| GDR 1 JSON replay inspection | Press/release, button/player and explicit timebase; missing framerate stays unknown; binary GDR/GDR2 unsupported |
| Local and joint timing scenarios | Asymmetric/disjoint windows, input ordering, alternative routes and linear dependencies supplied by the user |
| Correlated-noise experiments | Seeded Gaussian jitter, common shift, stationary AR(1) drift; declared assumptions, not measured human abilities |
| Censored first-completion statistics | Kaplan–Meier curve, supported T50, conservative participant bootstrap, compatible provisional AR |
| Supplied terminal-oracle ledger checks | Exact manifest consistency and observed repeatability; does not run/authenticate the engine |
| Experimental native capture and replay | Version-specific Geode source, local opt-in capture, binary manifests, death/finish/ending-phase callbacks, paired gameplay/Scheduler updates and selected player fields; incomplete configuration/state coverage |
| Native capture inspection/comparison | Strict integrity and identity checks; exact comparison of recorded replay subsets; files alone do not establish complete engine determinism |
| Portable HTML and JSON | Interactive route selection, window/first-completion plots, source identity and interpretation limits; works offline |
| Research framework | 64 proposed factors, telemetry design, baseline comparisons and a gated implementation roadmap |

## Run it

Python 3.11+ is sufficient. No game, API key, network connection or scientific package is required for analysis.

```sh
git clone https://github.com/TheLitis/AXIOM.git
cd AXIOM
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux / macOS: source .venv/bin/activate
python -m pip install -e .
axiom demo
```

Open `reports/demo/index.html`. **Every demo input, participant time and reported rating is synthetic.** Timing probabilities and cohort T50 are separate calculations; the demo does not calibrate one from the other.

If you use [uv](https://docs.astral.sh/uv/), `uv sync --locked --extra dev` followed by `uv run --locked axiom demo` uses the committed dependency lock.

```sh
axiom level examples/level.txt --json reports/level.json
axiom replay examples/replays/synthetic.gdr.json --json reports/replay.json
axiom timing examples/timing.json --trials 20000 --seed 42 --html reports/timing.html
axiom cohort examples/cohort.json --bootstrap 1000 --seed 42 --html reports/cohort.html
axiom trials examples/trials.json --json reports/trials.json
axiom native examples/native/synthetic-capture-a.json --json reports/native.json
axiom native-compare examples/native/synthetic-capture-a.json examples/native/synthetic-capture-b.json --json reports/native-comparison.json
axiom native-compare examples/native/synthetic-clock-a.json examples/native/synthetic-clock-b.json --json reports/native-clock-comparison.json
```

All commands validate input; unknown evidence remains unknown. The native examples above are synthetic schema fixtures. See [import formats](docs/formats.md), [timing scenarios](docs/timing-format.md), [cohorts](docs/survival-format.md), [oracle ledgers](docs/oracle-format.md) and [native operation and acceptance](docs/native-adapter.md). Building the native mod requires a separate compiler/SDK setup; Python analysis remains dependency-free.

## What AR means

For a fixed population, starting skill profile, practice protocol and technical environment, let T50 be the active practice time by which estimated first-completion probability reaches 50%.

`AR = 1000 + 100 × log₂(T50 / reference T50)`

| Difference | Median practice time ratio |
|---|---|
| +100 AR | 2× |
| +200 AR | 4× |
| +300 AR | 8× |

This is a proposed scale, not Elo and not a universally objective multiplicative difficulty. Changing the reference population or protocol changes the scale version. Missing/unsupported T50 or incompatible calibration never becomes an invented numeric rating. The current empirical path is descriptive and provisional; reference/model uncertainty has not been estimated, so it does not publish an AR confidence interval.

Physical feasibility, execution difficulty and learning difficulty remain separate. A replay or a finite set of failed search trials cannot establish all three. The [methodology](docs/methodology.md) explains dependencies, human information limits, selection/censoring bias, section boundaries, uncertainty and held-out validation.

## Next scientific milestone

Extend the two-fixture clock result across a declared mechanics matrix; test ordinary-input equivalence, complete environment coverage, interruptions, recording overhead and measured throughput. Establish the supported replay domain before deriving timing windows. Then test whether a calibrated section-success model improves predictions on unseen players against an independent-window baseline.

Native integration is experimental; automatic window discovery, perception/learning models and real-level leaderboards remain **planned work**, with acceptance gates in the [roadmap](docs/roadmap.md). Geode, Frame Window Counter, NaNDL and the statistical/motor-control literature are prior work, documented with primary references in [research sources](docs/research-sources.md).

## Contribute

```sh
uv sync --locked --extra dev
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m build
```

CI runs checks and the synthetic demo on Windows and Linux with Python 3.11 and 3.14. See [CONTRIBUTING.md](CONTRIBUTING.md) for evidence expectations and development guidance. Public datasets must be consented and licensed; game binaries, music, private save files and identifiable player histories do not belong in this repository.

AXIOM is an independent community research project, unaffiliated with RobTop Games. Geometry Dash is the property of its respective rights holders. Project code and documentation are available under the [MIT license](LICENSE); third-party assets retain their own rights.
