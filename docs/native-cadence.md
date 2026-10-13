# Native cadence diagnostics

[Русская версия](native-cadence.ru.md) · [Recorded replay](recorded-replay.md) · [Windows input](windows-input.md) · [Roadmap](roadmap.md)

`axiom native-cadence` describes the recorded command, gameplay-update and Scheduler streams in one capture. It derives counts, hook arguments, entry gaps, paired wall intervals, direct command membership and whole-row phase groups. It does not launch Geometry Dash.

```sh
axiom native-cadence examples/native/synthetic-clock-a.json --json reports/synthetic-cadence.json
axiom native-cadence path/to/your/capture.json --json reports/cadence.json
```

The first example is synthetic. Use your retained local capture for the second command. The Python API is `axiom.cadence.inspect_native_cadence(path)`. Capture schemas 1–7 use the existing strict reader; schema 1 reports unrecorded streams instead of inventing them. The output is a separate `native_cadence_diagnostics` schema-1 report, leaving existing `axiom native` output unchanged.

## Measurement contract

| Quantity | Calculation and interpretation |
|---|---|
| Command count | Trace rows after the initial state row; row zero is not a command |
| Count per declared wall second | Command or stream-row count divided by the attempt's declared terminal wall duration |
| Stream entry interval rate | `(entry count − 1) / (last entry − first entry)` in that recorded stream; an insufficient or zero span gives an explicit unavailable status |
| Entry gaps and paired durations | Empirical nearest-rank p50/p95/p99, minimum, maximum, mean and sum; no confidence interval |
| Original and delivered `dt` | Separate argument distributions, zero counts and exact inequality count; their sums are not calibrated elapsed simulation time |
| Inclusive interval sum and interval union | Reported separately within each stream, including root-only summaries; nested intervals must not be counted as disjoint work |
| Terminal clipping | Preserve full enclosing callbacks, the interval union through the declared terminal and late-exit records/tails |
| Command membership | Preserve direct trace contexts, unknown contexts, parent nesting, root command deltas and a canonical grouping hash |
| Phase buckets | Whole rows classified as `start_warmup`, `normal_pre_end`, `ending`, `crosses_phase_boundary` or `unknown` from their recorded counters/flags |

Crossing rows remain unsplit: a command's exact wall entry time is not recorded. Root command spans are inclusive, so nested spans are not added to them. Gameplay-update and Scheduler intervals overlap and must never be added together. Empty samples have null quantiles/means and zero sums. Nonfinite results and source-byte changes are rejected.

Every report retains the raw source SHA-256, capture schema, collector, exact environment/hash, clock policy, challenge, input route, terminal and supplied provenance. Each capture is analyzed separately; the command does not pool incompatible environments.

## Archived checkpoint, 13 October 2026

The existing native-clock source and its three recorded-Scheduler replays were reanalyzed from immutable files. **No new game execution occurred.** All four had 4894 command rows, 5130 gameplay-update rows and 5132 Scheduler rows. The source and replay environments remain distinct: replay explicitly intervenes in Scheduler arguments. The prior [source/repeat qualification](recorded-replay.md) remains a separate result.

| Archived capture | Declared wall duration, s | Commands / declared wall s | Scheduler entry intervals / s | p95 Scheduler entry gap, ms | Original ≠ delivered Scheduler `dt` rows |
|---|---|---|---|---|---|
| Native source | 21.4056541 | 228.631182 | 239.708084 | 4.2067 | 0 |
| Recorded replay 1 | 21.5586703 | 227.008435 | 239.183358 | 4.1907 | 273 |
| Recorded replay 2 | 21.5589623 | 227.005360 | 239.172814 | 4.1901 | 245 |
| Recorded replay 3 | 21.5096946 | 227.525313 | 239.808676 | 4.1847 | 192 |

Each Scheduler stream had a 244-row command-free prefix and one terminal command-free tail row. Its phase buckets contained 244 warmup, 4646 normal pre-end, 241 ending and one crossing row, with no unknown rows. The 5132 **delivered** Scheduler arguments matched the source exactly in each replay; incoming arguments and wall timing differed. Neither the count/wall ratio nor the entry-interval rate is render FPS. These observations do not attribute the differences to recording overhead, CPU, display, input hardware or a particular engine mechanism.

The diagnostic evaluator is commit `9478c2f753db7b022deef94744364840eb9e3e9a`; `src/axiom/cadence.py` SHA-256 is `b23d1681c74a75509e09ccf49f9f4246de9f04dd8010c9d30e4b8f6aa559e2a4`. The local study manifest freezes all six evaluator files, the runner and each source/report pair. Its SHA-256 is `ddc9ff7a1816bc604db1a8d63cd9c8e7450aca4efe8c1708b071a2048174d0d8`.

| Capture | Raw source SHA-256 | Diagnostic report SHA-256 |
|---|---|---|
| Native source | `a8721c3d671f9cdb2b75d7567b0fbaf2a32421cbbc30f298577bd2cb40460da7` | `402ed49fa850180524bf23d6f2efa1142219652cd298193a9b5817859b79829b` |
| Recorded replay 1 | `cd95b40a63724059b508d18453b091040b3e180b1265e142f5f1056747b19ca1` | `78aaf63c4912ae9d67c77b2c7cfabae91a10747ba499354b40d9f80d6c451747` |
| Recorded replay 2 | `0dbdc3fabfc32949fccabc641ae0e6dbb536994a763b502d4e84782bc45394f3` | `adbe508867c9382f4dafaf3c996a7d25036eb6a9aa67c14cdaf427361f448fee` |
| Recorded replay 3 | `d9c6f2224101720b81d1305e2f22795eb6c9bf0270ea1386e48088f65564b8ad` | `b6ba42c5b085c769b55c4f86d2d91dfcab14d486972331adce056d184ff831ae` |

A separate same-host audit used only the Python standard library, exact rational sums and an endpoint sweep for interval unions, without importing AXIOM. It passed **2496 checks with zero discrepancies**, covering all four reports, identities, statistics, phase groups, memberships, delivered argument equality and unchanged source/report bytes. Derived floating calculations allow two ULPs to accommodate different arithmetic orders; native counts, hashes, recorded fields and replay equality stay exact. This recomputation does not authenticate engine origin or independently witness execution. Audit SHA-256: `29cb5746c2b122b36a114dde4cb8d4cebb5bf8e30e00f041f759b36fa3b530f7`; audit helper: `335fdbc1288968b63fcb7ecbfe4cf9d732263ec46a27e3cfffc41d6c5ba3a2cd`.

Software validation passed **801 tests plus 83 subtests** and Ruff on 63 files. Twelve cadence tests cover nested overlap, terminal clipping, phase boundaries, argument/wall distinctions, old schemas, missing streams, source mutation and strict numeric bounds. Raw captures, local manifests and audit scripts remain outside Git.

## Remaining measurement gates

Paired duration includes engine work, other hooks, instrumentation, preemption and waits. Recording overhead needs a separately declared matched control; hardware latency needs a suitable arrival measurement; render FPS needs its own stream; maximum native throughput needs a throughput experiment. Archive-derived diagnostics establish none of these.

The [Windows startup ledger](windows-input.md#live-evidence-ledger) still has no schema-7 export or live Windows qualification. Focus/reset/interruption behavior, complete M1 acceptance, measured feasible timing regions and human-calibrated AR remain open.
