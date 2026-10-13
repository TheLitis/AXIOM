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

The M0 offline implementation is available in v0.1.0 for its documented formats and scenarios. Current development includes an [experimental M1 observer/replay adapter](native-adapter.md) and strict capture comparison. Its complete acceptance gate remains open; M2–M5 require new engineering or data. [Final-system requirements](end-goal-requirements.md) maps the v0.1.0 baseline to the end-state contract, prerequisites and critical path.

The [initial native validation ledger](native-validation.md) retains failed exact replay comparison. The [clock investigation](clock-investigation.md) records two generated fixtures × three policies × three replay completions, with paired update observations and a native ending-phase callback. The fixed Scheduler intervention passed exact recorded-subset comparison on both fixtures; the native and fixed gameplay-update policies failed. The subsequent [fixture matrix](native-fixture-matrix.md) passed 55 attempts over 11 declared cases and eight observed mode labels: three exact completed replays per case and selected input-response controls.

A separate [mechanics matrix](native-mechanics-matrix.md) passed 56 completed attempts over 11 generated cases covering gravity inversion/return, size changes, five raw speed values and dual entry/exit. All 33 replay attempts agreed through terminal on 14 components; twelve mechanics-conditioned input-response controls passed, including separate P1 and active-P2 controls in dual. This verifies the declared constructions and recorded fields under the fixed Scheduler intervention; it does not close the complete M1 gate.

The [collision and trigger checkpoint](native-interactions.md) recorded 48 full-start attempts over 12 constructions, including 36 owned replays and six controlled variant pairs. All repeated cases agreed on 18 recorded components; 32 attempts completed and 16 died as declared. Selected native effect receipts and watched states passed the declared gates. A separate artifact audit reproduced all six variant comparisons at each of the three repetitions. The explicit delivery-context projection leaves unequal absolute native timestamps as diagnostics; it does not establish full native-time equality.

The separate 12-attempt synthetic UI study witnessed planned queue delivery and matching selected dynamics, with all four UI repeat sets agreeing on 18 components. All twelve complete cross-route input-receipt comparisons failed because UI forwarded an additional initial P1 release. This measured mismatch remains part of the result; scheduled UI callbacks do not test Windows/device arrival.

Two historical schema-4 native-clock manual attempts completed separately. The first recorded no keyboard callbacks; the restart recorded Space down/up outside command processing and their queue-to-player delivery on the next commands. The operator reported holding Space and clicking the left mouse button near the end. All additional receipts remain present; that historical schema-4 capture has no mouse-entry instrumentation, and device origin is unknown. A 54-check artifact audit reproduced the restarted observation without establishing full ordinary-input equivalence. See the [manual evidence ledger](native-interactions.md#operator-reported-manual-observations).

The later [schema-5 observation](input-observation.md) recorded all seven requested raw key codes plus S and five touch begin/end pairs, with unknown device origin and inactive-P2 effects unproven. Its separate controlled cube-flat repeat pass retains the preceding delivery-context failure.

The [recorded-replay bridge](recorded-replay.md) passed its declared source projection in three fresh full-start replays: native completion at command 4894, all 106 actual receipts and all delivered cadence/grouping matched the immutable source. All 18 same-route repeat components agreed; the preceding export rejection remains preserved. A 200-check independent artifact audit found no discrepancies. This result uses recorded Scheduler arguments and synthetic owned requests at queued-processor entry, with explicit source/target identities and interference witnesses. Continue Windows/device measurements, focus/reset/interruption tests, configuration/collider/trigger coverage, recording-overhead and native-throughput measurements before deriving timing windows. These checkpoints leave the full M1 gate open.

The [Windows input observation checkpoint](windows-input.md) implements an opt-in schema-7 contract for existing Windows messages, public Geode events and the previously recorded gameplay stages. Software validation passed 789 tests plus 83 subtests and Ruff; native compilation succeeded. Live qualification remains not established: two new-package startup attempts and an old-package control produced no exports, with all four preservation records passing per attempt. The early-exit/dialog cause is unknown and no schema-7 ingress or delivery correspondence is asserted. Candidate joins must preserve ambiguity and unmatched events, while focus-generated releases and cross-thread queueing remain distinct from physical-device evidence; no full ordinary-input or M1 gate is claimed.

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
