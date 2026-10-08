# AXIOM roadmap

This is a gated research roadmap, not a claim that every stage is implemented. Dates and ranking targets are deliberately unset until the evidence gates are met.

| Milestone | Deliverable | Exit gate | Claim allowed |
|---|---|---|---|
| M0 — Offline laboratory | Validated local/joint constraints, reproducible correlated-noise experiments, replay/level inspection, censored survival baseline, JSON/HTML reports | Deterministic software checks; synthetic counterexamples; honest missing-data and zero-success handling; documented assumptions | Conditional calculations on supplied evidence |
| M1 — Native capture and replay | Version-specific Geode adapter, game-scoped input/events, environment manifest, state and finish oracle | Same-start replay reproducibility; full same-run completion witness; mismatches rejected; no hidden-state exposure to human controllers | A witnessed physical run in the named configuration |
| M2 — Measured feasible regions | Local and joint perturbation maps, disconnected windows, alternative strategies, reachable section boundaries | Delayed-death checks; checkpoint differential tests; joint counterexamples; complete-run reconnection | Measured robustness for checked strategies and states |
| M3 — Human calibration pilot | Consented longitudinal data; timing/learning/profile models; recruitment and practice protocol | Unseen-player and unseen-section probability predictions outperform preregistered independent-window baseline; uncertainty and subgroup checks; dropout sensitivity | Calibrated forecasts within pilot support |
| M4 — Full-level time model | Persistent state across sections; active-time first-completion forecasts; versioned reference package | Held-out levels and future campaigns; censoring/quit treatment; reference T50 supported; coverage and calibration acceptable under frozen criteria | AR with scope and uncertainty in the calibrated domain |
| M5 — Public research service | Reproducible evidence pages, versioned comparisons, data/model cards, correction process | Independent replication, provenance review, operational checks and consented releases | Public ratings with audit trails and explicit limits |

M0 is the initial implementation target. M1–M5 require new engineering or data; this repository has not established their evidence gates.

## First human benchmark

The initial scientific target is to improve section-success forecasts on new players compared with an independent-window model. Use short controlled challenges before extreme full levels. Vary one suspected mechanism where possible, balance experimental order, repeat across days, preserve failures, and measure the actual reached-state distribution.

Freeze the comparison baseline, training/validation/test groups, primary scoring rule, interval-coverage target, sample-size plan and minimum practically meaningful improvement before collecting the confirmatory test set. Publish unsuccessful results and ablations. A model with more factors must earn its complexity through predictive improvement, not a closer fit to the training set.

## Required benchmark cases

- Identical individual windows with different joint dependencies.
- Broad absolute windows with a narrow required inter-action interval.
- Asymmetric/disconnected accepted regions and press/release dependencies.
- A fragile replay when an alternative robust route exists.
- The same hard section at different positions, carrying entry state and accumulated human state.
- Delayed death after the apparent local window boundary.
- No completions, censored median, tied event/censor times, and difficulty-related quitting.
- Different display/input/physics clocks and incompatible level revisions.
- Unseen players, unseen levels, temporal drift and observations outside calibration support.

## Public release policy

Do not publish a real-level leaderboard from synthetic windows or assumed timing precision. External measurement imports may be useful without being native verified; display their origin prominently. Keep profile-specific estimates alongside population estimates. A reference-population or practice-policy change starts a new scale version; preserve previous releases instead of silently changing their meaning.

GRIEF and Slaughterhouse can be later full-system stress tests once exact revisions, permitted environments, replay witnesses and comparable campaigns are available. No ratio, Elo equivalent, or universal human-limit claim is currently established.

## How contributors can help now

Improve adapters and serialization with versioned public examples; build synthetic counterexamples; review censoring and uncertainty handling; propose a factor with a feasible measurement protocol; or design consented short-section experiments. Do not commit proprietary game binaries, unlicensed level/music assets, credentials, or identifying player records. Changes that affect rating semantics require a methodology and reference-version note.
