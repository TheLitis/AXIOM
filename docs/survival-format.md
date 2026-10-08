# First-completion cohort format, version 1

This path estimates the distribution of **active hours to first completion** for a defined player population under one declared protocol. It measures a population-dependent empirical outcome. It does not establish physical feasibility, a theoretical human limit, or a universal level difficulty. [`examples/cohort.json`](../examples/cohort.json) contains entirely synthetic records, invented identities and calibration values. Its numbers must never be attributed to real levels or players.

The public Python API is `analyze_cohort(path, bootstrap_samples=1000, seed=0) -> dict`. `load_cohort(path)` validates the input; `kaplan_meier(observations)` accepts a nonempty sequence of validated time/status rows and returns `curve` and `t50_hours`. Analysis reports are JSON serializable with `allow_nan=False` and include `source_sha256` of the exact input bytes. The shared JSON loader limits inputs to 16 MiB and rejects duplicate keys. A cohort is limited to 5000 observations. Invalid fields and incompatible identities raise `ValueError`; filesystem failures retain their normal Python exceptions.

## Required identity and protocol

| Field | Required content |
| --- | --- |
| `schema_version` | Integer `1`, not a boolean. |
| `cohort_id` | Unique nonempty cohort identifier. |
| `synthetic` | JSON boolean; synthetic data remain visibly synthetic in every report and rating object. |
| `challenge` | Object with `id`, `level_sha256`, `game_version`, `physics_version`, `input_policy`, `environment_id`. Every field is a nonempty trimmed string; SHA256 is exactly 64 lowercase hexadecimal digits. |
| `profile` | Object with `id`, `skill_definition`, `sampling_method`, all nonempty strings. Describe eligibility, baseline skills and recruitment explicitly; identifier equality does not prove representative recruitment. |
| `population_id` | Versioned reference population identity, including eligibility criteria. |
| `protocol` | Object with `id`, `version`, `fixed`, `time_basis`, `practice_policy`, `censoring_policy`. `fixed` is a boolean; `time_basis` is exactly `active_hours`; other fields are nonempty strings. |
| `observations` | Nonempty array with one row per participant. |

Optional top-level fields are `notes` (nonempty string) and `reference` (calibration object below). Unknown fields and duplicate JSON keys are rejected. Declared hashes and policy IDs preserve reported identity; this loader cannot verify which build or settings were actually used. The artifact bytes, settings, input treatment and experiment provenance need independent collection and audit.

Choose a protocol before enrollment. Specify the clock start, active practice accounting, breaks, external learning, hardware, accepted inputs, first-completion evidence and follow-up plan. Clock start should cover first exposure and all counted learning; selecting players only after extensive undocumented prior practice changes the target outcome. The challenge's `environment_id` must identify the immutable hardware/settings manifest rather than a vague machine category. `practice_policy` and `censoring_policy` should identify a versioned public protocol, not merely assert comparability. Current validation checks equality of declared text and IDs; it does not enforce these policies in a game runtime.

## Participant rows and censoring

Every row contains `participant_id`, `time_hours`, and `completed`. `participant_id` must be unique, nonempty and trimmed. Times must be finite positive JSON numbers, never booleans, strings, zero or negative values. A zero-time participant needs an explicit later schema/design decision rather than an ambiguous zero-hour event. The only accepted status type is a JSON boolean.

- For `completed: true`, `time_hours` is active time through verified first completion. A `censor_reason` is prohibited.
- For `completed: false`, `time_hours` is active follow-up accrued without observed first completion. A nonempty `censor_reason` is required. This is **right censoring**, never a successful completion or a completion at the follow-up time.

Optional repeated `challenge`, `profile`, `protocol`, and `population_id` fields must match the shared cohort identity exactly. This detects an explicitly incompatible merged row. Omitted fields inherit the shared descriptor; their omission is no proof that the participant used it. Changing level bytes, game/physics versions, input policy, environment, population or protocol requires a separate cohort.

Kaplan–Meier assumes independent censoring conditional on the defined population. Leaving because a level is frustrating, stopping because progress is slow, or submitting only successful players can violate that assumption. The file stores censor reasons but does not correct informative dropout, survivorship bias, delayed entry, repeated correlated players, skill changes, or unobserved prior learning. Address those in the study design or a separately validated statistical model. Participation without consent and collection of private player identifiers are not implied by this format; use pseudonyms in public examples.

## Estimator and uncertainty

At each distinct observed time `t`, let `n` be the number still at risk just before `t`, `d` the number completing at `t`, and `c` the number censored at `t`. The estimator updates `S(t) = S(t-) * (1 - d/n)` and then removes `d + c` participants. Events and censorings tied at the same time are both in the denominator: events occur first for risk bookkeeping. A censor-only time leaves survival unchanged. `S(t)` estimates the probability that first completion time exceeds `t`; completion probability is `1-S(t)`.

`t50_hours` is the first event time at which estimated survival is at or below `0.5`, including an exact plateau at `0.5`. This is the **lower crossing** convention, explicitly fixed for AXIOM; it is not the arithmetic median of successful players' times and does not interpolate between steps. If the curve never reaches `0.5`, output is `null` and `t50_status` is `unreached`. The implementation performs survival products and crossing comparisons as exact rational numbers before converting curve values to floats. No tail or completion-time extrapolation is used.

Curve points include `time_hours`, `at_risk`, `events`, `censored`, `survival`, `completion_probability`, `survival_ci95`, and `survival_ci_status`. For `0<S<1`, Greenwood uses `G = sum d/[n*(n-d)]` and the log-log standard error is `sqrt(G)/abs(log(S))`. With `z = Phi^-1(0.975)`, the 95% pointwise bounds are `exp(-exp(log(-log(S)) +/- z*SE))`, ordered as lower and upper. At `S=0` and `S=1`, the transform is undefined, so bounds are `null` with `boundary_undefined`. This avoids pretending a degenerate boundary estimate is certain. Intervals are asymptotic and may have poor small-sample coverage.

These bounds are **pointwise survival intervals**, not simultaneous curve bands, T50 intervals, or AR intervals. The report explicitly warns about this distinction.

The optional bootstrap resamples whole participant rows with replacement using Python's local `random.Random(seed)`. It preserves paired completion status and follow-up time; a participant is the independent resampling unit. Every resample gets a KM median. An unreached median remains positive infinity internally rather than being silently dropped. A finite percentile T50 interval is reported only when the original median is reached, at least 200 resamples were requested, at least 97.5% of resample medians are finite, and the full-distribution 97.5th percentile is finite. Percentiles use nearest ranks `ceil(p*B)` in the ordered **full** bootstrap distribution. Otherwise the interval is `null`, with status and a warning. JSON never contains infinity.

`bootstrap_samples=0` disables the bootstrap; integers through 100000 are supported. Work is bounded by `bootstrap_samples * participant_count <= 2000000`; larger workloads raise `ValueError` with an instruction to reduce the resample count. Default settings are 1000 resamples and seed 0. Results reproduce for the same input, Python runtime and seed; report the runtime along with research artifacts. This interval is provisional, discrete and potentially inaccurate for small samples or heavy censoring. It cannot cover selection bias, informative censoring, correlated participants, calibration uncertainty or uncertainty about the model. A singleton can produce a degenerate bootstrap interval, so all small cohorts remain explicitly warned and provisional.

## Calibration and provisional AR

An optional `reference` requires `id`, `version`, `source_cohort_id`, `synthetic`, `challenge`, `profile`, `population_id`, `protocol`, and positive finite `t50_hours`. Its profile, population and full protocol must match the target cohort. Reference game version, physics version, input policy and environment must match; its level ID and SHA256 may differ because it is a distinct baseline challenge. Synthetic and nonsynthetic evidence cannot be mixed. Incompatible references are rejected rather than producing a rating.

AR is available only when the protocol is declared fixed, a compatible reference exists, and the observed KM median has been reached:

`AR = 1000 + 100 * log2(T50_hours / reference_T50_hours)`

The reference median maps to 1000 AR; doubling active-hours T50 adds 100 AR. This is a proposed display transform (`axiom-ar-log2-v0`), not Elo, a validated universal difficulty law, or a claim about harder real levels. Comparable ratings require the same population/profile, protocol and calibration identity/version. Negative values are mathematically possible and are not clamped. Subtracting base-2 logarithms avoids numeric ratio overflow/underflow.

Every available rating remains `provisional_empirical`; synthetic ratings additionally carry `synthetic: true` and the whole report is `synthetic_demonstration`. Missing fixed protocol, reference or median yields `ar: null` with explicit reasons. The reference T50 is a declared scalar whose original cohort and uncertainty have not been independently verified by this module. Accordingly `rating.ar_ci95` is always `null`. Neither the pointwise survival interval nor the T50 bootstrap interval is mislabeled as a rating interval. Establishing a real AR interval requires propagating target and reference uncertainty under a justified dependence and calibration model.

## Method sources

- [NIST: Kaplan–Meier plot](https://itl.nist.gov/div898/software/dataplot/refman1/auxillar/kaplan.htm), for the unmodified product-limit estimator and censoring indicator. AXIOM uses the unmodified estimator, not NIST Dataplot's optional modified plot.
- [NIST: right censoring](https://itl.nist.gov/div898/handbook/apr/section1/apr131.htm), for the interpretation of an unobserved event after a known follow-up time.
- [SAS: LIFETEST computational formulas](https://support.sas.com/documentation/cdl/en/statug/63347/HTML/default/statug_lifetest_sect013.htm), for Greenwood variance and transformed pointwise confidence limits.
- [SAS: LIFETEST interval options](https://support.sas.com/documentation/cdl/en/statug/68162/HTML/default/statug_lifetest_syntax01.htm), for the distinction between pointwise limits and simultaneous confidence bands.

The AR transform, protocol gates, lower-crossing convention and conservative bootstrap reporting rule are AXIOM design choices. These sources do not validate AXIOM on Geometry Dash.
