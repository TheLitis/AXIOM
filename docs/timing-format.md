# Timing scenarios · v1

`axiom timing examples/timing.json --seed 42 --json reports/timing.json --html reports/timing.html`

This format describes a **supplied approximation to a route's feasible timing region**. The analyzer does not derive windows from level geometry or run the native game. Even `engine-measured` provenance is a declaration needing independent audit.

The JSON document has `schema_version: 1`, `kind: "timing_scenario"`, a challenge descriptor, provenance, noise and a nonempty array of routes. See the executable example for all fields.

Challenge identity comprises `id`, exact `level_sha256`, `game_version`, `physics_version`, `input_policy` and `environment_id`. Environment IDs must resolve to immutable hardware, display, latency, modification and detail settings in the source dataset; an arbitrary label does not demonstrate controlled conditions.

Each route contains an ID, label, duration and sorted nominal events. Events include `time_seconds`, `button` (1–3), `player` (1–2), boolean `down` and `windows_ms`. Windows are ordered, disjoint closed `[lower, upper]` intervals of **offset from nominal time**, preserving asymmetry and multiple possible bands. Every channel begins released and alternates presses/releases. The analyzer rejects perturbed events before the start, after the duration, or reversing input order on the same channel. Simultaneous events preserve nominal list order. Holding a button through the end is allowed.

Joint constraints use zero-based event indices: `terms: [[0, -1], [1, 1]], lower_ms: -3, upper_ms: 3` means `-3 <= error_1 - error_0 <= 3`. These constraints concern offsets, not nominal inter-event duration. Their conjunction with the local windows approximates a feasible region; nonlinear/native physics need an engine oracle.

The uncalibrated noise scenario is

`error_i = bias + common_shift + stationary_AR1_drift_i + independent_jitter_i`.

All sigma fields are milliseconds. Common shift has SD `shift_sigma_ms`; independent jitter has SD `sigma_ms`; drift has marginal SD `drift_sigma_ms`, correlation `rho` between consecutive **event indices** and innovation SD `drift_sigma_ms * sqrt(1-rho²)`. This does not assert physiological validity or time-based drift dynamics. The drift applies across channels in nominal event order. Each route is evaluated separately; probabilities cannot be added as though routes were independent success opportunities.

The analytic baseline clips each local interval union to the run's start/end boundaries and multiplies its probability under the same marginal variance. It ignores correlation, joint constraints and same-channel ordering. This is a diagnostic comparator, not an upper/lower bound or an implementation of NaNDL's L* scale.

Seeded Monte Carlo produces a route-conditional pass probability with a Wilson 95% interval for **simulation sampling error only**. This excludes window measurement error, finite scan resolution, uncertain noise parameters, hidden state, route discovery and human learning. Zero observed successes retain a nonzero upper bound and never imply physical impossibility. No T50 or AR is derived from a timing scenario.

Inputs are capped at 16 MiB, 64 routes, 10,000 events per route, 128 bands per event and bounded workload. Random draws are reproducible for a fixed seed, Python version, input and implementation; capture all of them for an archived run.
