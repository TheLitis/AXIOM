# AXIOM methodology

AXIOM asks: **How likely is a person with a specified skill profile to complete a precisely identified challenge after a specified amount of preparation?** Axiom Rating (AR) is a presentation of that forecast, not a weighted sum of difficult-looking objects.

Status: research design and offline prototype. No native Geometry Dash physics adapter, calibrated human model, or validated real-level AR is supplied by this release. Synthetic examples check software behavior; they are not measurements of players or levels.

## Three separate questions

| Layer | Quantity | Evidence required |
|---|---|---|
| Physical feasibility | Does a permitted input sequence reach the finish? | A reproducible full-run witness in the specified engine, or a formal proof in a stated abstraction |
| Execution | Probability of performing a known strategy at a specified preparation state | Feasible input regions, observations of human execution, and a calibrated controller |
| Learning | Distribution of practice time until first completion | Longitudinal practice histories, including failures and incomplete campaigns |

An unsuccessful search means **no witness found**, not **impossible**. A successful macro demonstrates existence only within its checked environment. Passing isolated sections does not establish a full-run witness. Neither result establishes human attainability.

## Identify the challenge

The unit of comparison is a level revision plus its engine, input rules, and environment. Store an exact level payload SHA-256, any original level ID, game build and executable hash, physics/update configuration, enabled mods and configurations, input policy, display/audio configuration, detail mode, and adapter version. The level name is a label, not an identity.

Rendering cadence, physics cadence, input timestamp resolution, and input acceptance rules are separate variables. Record times in seconds and preserve the original tick/frame/subtick representation. A numerical frame window without its clock and sampling rules is not portable. Geode provides game hooks and mod infrastructure, but does not by itself certify reproducibility or physics correctness. [Geode documentation](https://docs.geode-sdk.org/handbook/vol1/chap1_3/)

## Feasible input regions

For engine state `s`, permitted actions `u`, and the real completion oracle `C`, define a feasible set `W(s) = {u: C(engine(s, u)) = success}`. It can have disconnected components and alternative routes. AXIOM studies three scales:

1. **Local:** shift one press or release while fixing the rest. Report asymmetric bounds, excluded regions, tested resolution, and the continuation horizon.
2. **Joint:** perturb multiple actions and retain their dependencies. An interval constraint such as `abs(error_2 - error_1) <= tolerance` behaves differently from two fixed absolute windows.
3. **Global:** join sections using reachable boundary states and verify the complete run from the genuine level start through the finish.

Local slices are not the Cartesian product of a jointly feasible set. The current offline constraint analyzer tests supplied mathematical regions; it does not discover these regions from Geometry Dash. Externally measured windows need provenance, engine identity, perturbation design, and final-oracle results. A checkpoint fixture must preserve position, velocities, input holds, modes, triggers, clocks, and other future-relevant state. A synthetic ideal checkpoint is a different experiment.

Follow perturbed actions far enough to detect delayed deaths. An input that survives its nearest obstacle is not necessarily feasible. Compare alternative strategies rather than treating the first successful replay as mandatory. Goal-compatible variability is a useful theoretical motivation for joint analysis, not empirical validation of this implementation. [Todorov and Jordan, 2002](https://www.nature.com/articles/nn963)

## Model the person and their observations

Separate the intended strategy from execution error. A physics oracle may inspect internal coordinates; a human controller may use only displayed visual/audio cues, previously learned information, permitted feedback, and its own uncertain internal estimate. Hidden exact state must not leak through features, checkpoint identifiers, or future outcomes.

A skill profile should retain differences in timing, rhythm, speed, trajectory control, memory, learning, and endurance. Preserve the joint distribution of abilities: combining different people's best individual attributes creates a fictitious person. A population distribution also differs from one player with population-average parameters.

For a first sensitivity baseline, use a seeded process such as `e_i = b + z_i`, where `b` is a run-wide timing offset and `z_i` has declared serial correlation. The implemented noise distribution is an assumption until fit to consenting players' repeated attempts. Report scale, correlation, seed, draw count, and Monte Carlo uncertainty. Serial dependencies and practice effects occur in tapping experiments; their magnitudes cannot be imported as Geometry Dash coefficients. [Madison, 2001](https://pubmed.ncbi.nlm.nih.gov/11318056/), [Madison et al., 2013](https://pubmed.ncbi.nlm.nih.gov/23558155/)

Predicted timing and response to an unexpected cue must be distinguished. A very narrow known window is not automatically a reaction-time task. [Egger, Le, and Jazayeri, 2020](https://www.nature.com/articles/s41467-020-16999-8)

Zero sampled successes establishes a sampling limit, not zero probability or impossibility. Do not turn zero into infinite difficulty. Binomial sampling intervals describe Monte Carlo uncertainty conditional on the model; they do not cover uncertainty in the human model, windows, or engine.

## Learning, survival, and missing outcomes

Define active practice time before collecting data: in-game preparation, practice attempts, full attempts, and restarts count; declared inactive breaks do not. Keep rest schedules and calendar time as additional variables. Measure the initial skill and prior familiarity; a verifier discovering a route and a player copying one follow different preparation protocols.

The observation unit for time to first completion is a **player-challenge campaign**, not an attempt. Attempt records feed that campaign; repeated campaigns from a person remain clustered. Include late entry, unknown prior practice, recording gaps, detail/input changes, and resets explicitly. Do not treat an already-practiced participant as a fresh entrant.

If a campaign ends at 40 hours without a completion, record `T > 40`, not `T = 40`. A right-censored likelihood contributes survival probability at the censoring time. [Stan survival models](https://mc-stan.org/docs/stan-users-guide/survival.html)

Kaplan-Meier is a descriptive baseline for comparable campaigns under independent censoring (possibly conditional on recorded covariates). At each distinct completion time, multiply survival by `1 - completions / at_risk`; tied completions occur before removal of observations censored at that same time. If survival never reaches 0.5, the median is **not estimable within follow-up**. Report the follow-up range and risk counts; do not extrapolate a median or call the maximum observed time a population-wide lower bound.

Quitting may depend on frustration, lack of progress, or difficulty. Record the reason and model dropout or run sensitivity analyses before interpreting a censored curve as a completion forecast. A campaign quit time is not a failed completion time. A successful-only sample cannot reconstruct typical execution errors or a population completion curve. For a late section, the denominator of section success is the number of attempts that entered it, not every level start.

## Axiom Rating

For a frozen reference population `P`, preparation protocol `Q`, technical environment `E`, and information policy `I`, define

```text
F_L(h | P,Q,E,I) = probability of first completion by h active practice hours
T50(L) = inf { h : F_L(h | P,Q,E,I) >= 0.5 }
AR(L) = 1000 + 100 * log2(T50(L) / T50(reference_challenge))
```

The zero point and 100-point step are scale conventions. A +100 AR difference means twice the predicted median practice time under the **same** reference conditions; +300 means eight times. It does not mean eight times every human requirement. AR can be negative; software must not clip the scale to make it look familiar.

No real reference level or population is established yet. Version each future reference package with its recruitment/inclusion rules, joint skill distribution, baseline familiarity, reference challenge hash, practice and information protocols, model and dataset hashes, time-unit definition, and calibration date. Changing that package creates a new scale version. Publish frozen-population ratings separately from estimates for a changing frontier population.

Report T50, its uncertainty, AR uncertainty, profile, and scope together. Propagate numerator and reference uncertainty jointly, including dependence. Do not subtract ratings made under incompatible populations or protocols. If either median is unsupported, output **not rated**. If a forecast lies outside calibration support, label extrapolation and widen or withhold its interval.

The offline prototype can make a descriptive, provisional AR transformation of supplied campaign medians, retaining synthetic flags and cohort/reference limitations. It does not turn Monte Carlo window probabilities into T50 or AR. A fixed per-attempt success probability and a fixed attempt-cycle duration would define a stationary toy scenario: they omit learning, changing fatigue, variable death times, and dropout. They cannot substitute for a learned first-completion curve.

## Factor admission and avoiding duplicate effects

[factors.csv](factors.csv) is an extensible research registry. Every row is currently proposed and unmeasured by AXIOM. A row names a candidate variable, unit, acquisition method, mechanism, and a duplication group; it assigns no difficulty weight.

Before admitting a factor, establish a reliable measurement, a causal/conditional role, calibration support, and incremental out-of-sample value. Use ablations and regularization for overlapping predictors. If fatigue already changes late-action variance, do not add a second arbitrary length penalty for the same pathway. Distinguish a descriptive feature from a causal effect or fitted coefficient.

## Validation before a public rating

Use independent-window and stationary baselines, including NaNDL-style assumptions, as explicit comparators. NaNDL discloses independent inputs, symmetric windows, equal practice and common normal timing errors; it also describes tuning a nerve constant against an existing list ordering. Agreement with that ordering is therefore not fully independent validation. [NaNDL model and FAQ](https://nandl.pages.dev/)

Freeze predictions before evaluation. Hold out players, level revisions, and future time periods; compare matched conditions and avoid leakage through a player's attempts or near-identical level copies. General held-out evaluation principles support this design, but the grouped splits are AXIOM's proposed application. [Stan cross-validation](https://mc-stan.org/docs/stan-users-guide/cross-validation.html)

Evaluate probability calibration and log/Brier scores, first-completion survival predictions, uncertainty coverage, subgroup performance, and factor ablations. Include synthetic counterexamples with identical marginal windows but different joint regions, identical sections after different prefixes, and an unnecessarily fragile replay with a robust alternative. Improvement must be demonstrated on unseen human data before claiming measured human difficulty.

Human-limit reports should say **outside measured support** or **low estimated completion probability within this budget for this measured profile**. Neither is proof that no human could ever complete a level. No GRIEF/Slaughterhouse difficulty ratio is justified by this release.
