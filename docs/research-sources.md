# Research sources and their limits

Primary sources checked on **2026-10-08**. Links support the bounded statements below; they do not validate AXIOM on Geometry Dash. Scientific results from other tasks motivate experiments rather than supplying coefficients. AXIOM currently has no empirical human calibration dataset.

## Geometry Dash tooling

| Source | What it supports | Limit for AXIOM |
|---|---|---|
| [Geode developer documentation](https://docs.geode-sdk.org/) and [functions/hooks handbook](https://docs.geode-sdk.org/handbook/vol1/chap1_3/) | Geode is a Geometry Dash mod loader/SDK, with hooks and bindings for mod development | Hook availability does not establish complete snapshots, deterministic physics, or adapter support for a particular game build |
| [Frame Window Counter repository](https://github.com/hyper-5/frame-window-counter) | The README describes window visualization, macro tooling and an L* precision calculator; it lists several replay import/export formats | Reviewed as engineering precedent; AXIOM has not run it in-game or independently verified its measurement/calibration |
| [NaNDL model, equations and FAQ](https://nandl.pages.dev/) | A window-based precision model with disclosed independence, equal-practice, symmetric-window and common-normal-error assumptions; the FAQ describes calibration of a nerve constant against a list ordering | A comparison baseline, not independent ground truth; reproducing an ordering used for calibration is not a separate validation |

No versions are recommended here. Pin and audit the actual game/SDK/mod commits when implementing an adapter. Compatibility and release details can change. AXIOM's first importer supports only its documented formats; upstream format support is not automatically inherited.

## Motor control and timing

| Primary study | Bounded result used in the design | Proposed AXIOM experiment |
|---|---|---|
| Todorov and Jordan (2002), [Optimal feedback control as a theory of motor coordination](https://www.nature.com/articles/nn963), DOI `10.1038/nn963` | A stochastic control theory explains tolerance of task-irrelevant variability and correction of task-relevant deviations | Compare jointly feasible input families with single-replay/local-window descriptions |
| Madison (2001), [Variability in isochronous tapping: higher order dependencies as a function of intertap interval](https://pubmed.ncbi.nlm.nih.gov/11318056/), DOI `10.1037//0096-1523.27.2.411` | A synchronization/continuation study reports drift and serial dependencies; tested intervals differ from many GD action sequences | Estimate player-specific residual correlations instead of assuming every action error is independent |
| Madison, Karampela, Ullén and Holm (2013), [Effects of practice on variability in an isochronous serial interval production task](https://pubmed.ncbi.nlm.nih.gov/23558155/), DOI `10.1016/j.actpsy.2013.02.010` | Practice in repeated timing experiments reduced local variability and slower drift | Measure preparation state and within-player changes across repeated GD sessions |
| Egger, Le and Jazayeri (2020), [A neural circuit model for human sensorimotor timing](https://www.nature.com/articles/s41467-020-16999-8), DOI `10.1038/s41467-020-16999-8` | A model reproduces several timing behaviors using motor planning, sensory anticipation and feedback | Separate anticipated timing from responses to unexpected cues; evaluate observation-constrained controllers |

These papers do not identify GD's fastest possible human input, validate Gaussian errors for GD, set fatigue penalties, or prove that extreme levels are humanly impossible. AXIOM's proposed mappings are inferences and require their own controlled data.

## Statistical foundations

| Source | Supported principle | AXIOM design decision |
|---|---|---|
| [Stan User's Guide: survival models](https://mc-stan.org/docs/stan-users-guide/survival.html) | Right-censored event times contribute survival probability, rather than a completed-event density at the censor time | Keep incomplete player-challenge campaigns and record quitting separately |
| [Stan User's Guide: held-out evaluation and cross-validation](https://mc-stan.org/docs/stan-users-guide/cross-validation.html) | Predictions should be assessed on held-out observations with a declared scoring rule | Freeze player/level/time splits to prevent leakage from repeated attempts and copied sections |
| [Stan User's Guide: item-response theory](https://mc-stan.org/docs/stan-users-guide/regression.html#item-response-theory-models) | Models jointly represent participant abilities and item difficulty, including identifiability constraints | Consider a hierarchical skill/challenge model; repeated practice, censoring and skill transfer require extensions |

The exact AR logarithmic scale, telemetry gates, factor registry and grouped benchmark design are AXIOM proposals. They are not formulas endorsed by these sources. The software's Kaplan-Meier baseline is descriptive and does not itself solve informative censoring or provide a trained learning model.

## Research ledger policy

New claims need a precise source or an immutable AXIOM evidence bundle, an evidence status, measured configuration, scope, and limitation. Distinguish author-reported software features, independently reproduced behavior, controlled human measurements, and hypotheses. Archive commit IDs and access dates for software claims used in releases. Avoid ranking-derived targets in independent evaluation and keep failed experiments visible.
