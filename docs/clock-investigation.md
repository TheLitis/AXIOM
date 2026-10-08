# Native clock investigation

[Русская версия](clock-investigation.ru.md) · [Historical native validation](native-validation.md) · [Adapter contract](native-adapter.md)

**Measured result: three controlled replays agreed exactly on the declared recorded subset for each of two generated fixtures under `fixed-scheduler-240`.** The same study's `native` and `fixed-base-60` arms failed full subset comparison. This establishes a limited repeatability result for the identified clock intervention; M1, complete-state determinism, ordinary-input equivalence and AR remain unestablished. The earlier [schema 1 failure](native-validation.md) is a separate historical experiment and remains unchanged.

The study ended at **2026-10-08 22:31:55 UTC / 2026-10-09 01:31:55 MSK**. Local evidence is `reports/native/clock-study-f28891ebbf7d47ba92e1755b259903de`; the launcher log is `reports/native-clock-study.log`. Raw captures, comparison files and logs stay in ignored local reports. This document publishes curated results and hashes, not game files or personal telemetry.

## Question and controlled interventions

The earlier run recorded different callback grouping and late player states. The experiment asks whether controlling the game-layer update alone or the general scheduler changes repeat agreement. It observes the actual native end-animation boundary to locate differences, rather than inferring that boundary from position, percentage or elapsed time.

| Clock policy | Delivered argument | Scope |
|---|---|---|
| `native` | Original arguments unchanged | Instrumented baseline |
| `fixed-base-60` | `1.0f / 60.0f` to each actual current PlayLayer's inherited `GJBaseGameLayer::update` | Guarded sandbox; scheduler unchanged |
| `fixed-scheduler-240` | `1.0f / 240.0f` to each `CCScheduler::update` | Guarded sandbox process from plugin load, including calls before capture starts; game-layer argument unchanged |

There is one original invocation per callback. The adapter does not add an accumulator, repeat calls, override `getModifiedDelta`, change scheduler time scale, separately advance actions, correct player positions, restore checkpoints or skip the finish path. A fixed clock requires `AXIOMSandbox.exe` and the explicit sandbox launch flag. The ordinary game retains the native policy. These interventions have different clock rates and are not demonstrated to preserve wall-time speed or vanilla behavior. Their identities are included in the environment hash; comparisons are only within a compatible arm and fixture.

Each arm runs one no-replay observation baseline and three separate controlled replays. `flat` is the generated flat fixture from the historical test. `spike` adds a spike at x=150; its raw string is:

```text
kA13,0,kA15,0,kA16,0,kA14,0;1,8,2,150,3,15;1,1,2,600,3,-15;
```

The explicit plan requests player 1 jump at `processCommands` call 60 and release at call 90. It is constructed test input, not a human recording. During replay, the owned handler suppresses other `handleButton` requests and records them as unknown-origin diagnostics. It does not control direct player calls that bypass that handler. The no-replay baseline uses observation mode, so it is a response control rather than a repetition comparator. Repetition 1 is the comparison baseline for repetitions 2 and 3.

## Schema 2 and exact comparison scope

Schema 2 retains paired game-layer and scheduler entries/exits, original and delivered `dt`, nested/parent context, command indices before/after, native phase flags, and the actual `PlayLayer::playEndAnimationToPos` event. Trace and terminal rows reference their enclosing update/scheduler where observed. A callback entered before recording receives no fabricated entry. Export waits for the final post-command sample and all enclosing update/scheduler/phase callbacks to return.

The full verdict requires exact agreement of the plan and delivered input records, command arguments, selected player fields **including rotation**, native phases, delivered update/scheduler records, invocation grouping, phase events, terminal callback, placement, context and selected terminal state. No tolerance or late-state filtering is used.

Original update/scheduler `dt`, wall timestamps and blocked unknown-origin requests are **explicitly separate diagnostics**. They do not enter the delivered-subset verdict. Original scheduler `dt` and wall cadence differed even in the passing fixed-scheduler arms. Therefore `recorded_subset_consistent` does not mean byte-identical captures, identical real-time pacing or complete engine state. The reader also does not authenticate that supplied captures were independently executed.

The pre-end diagnostic conservatively uses trace rows with `command_index` **strictly less than** the one recorded false-to-true end-animation event. It keeps player fields, callback arguments, phase and grouping checks separate. This diagnostic never changes the full verdict or establishes M1. `PlayLayer::levelComplete` remains the completion callback; starting an animation is not completion evidence.

## Measured six-arm results

All 24 captures passed capture validation with `recording_complete=true`, zero dropped records and no collector errors. There were 18 completed replays, three completed flat observation baselines, and three spike observation baselines that died. Every replay contained four delivered records (request/push at 60 and request/release at 90), two planned events with no unexecuted tail, and one suppressed unknown-origin jump release at call 1. Both player callback returns were true; their meaning as hardware acceptance remains unverified.

| Fixture | Policy | Observation baseline | Replay terminal indices, R1 / R2 / R3 | Full recorded subset | Arm exit |
|---|---|---|---|---|---|
| flat | native | completed at 733 | 733 / 733 / 733 | inconsistent | 1 |
| flat | fixed-base-60 | completed at 1460 | 1456 / 1456 / 1452 | inconsistent | 1 |
| flat | fixed-scheduler-240 | completed at 734 | 734 / 734 / 734 | consistent | 0 |
| spike | native | died at 102 | 733 / 734 / 733 | inconsistent | 1 |
| spike | fixed-base-60 | died at 102 | 1448 / 1456 / 1456 | inconsistent | 1 |
| spike | fixed-scheduler-240 | died at 102 | 734 / 734 / 734 | consistent | 0 |

In both passing arms each replay had **735 trace rows, 977 game-layer update rows and 979 scheduler rows**. Native completion was recorded at command 734; selected terminal player-1 rotation was exactly `539.9995727539062`. All full comparison components were true. At command 61, replay player 1 had y=`107.46690368652344` and y-velocity=`10.964`; the observation baseline had y=`105` and velocity `0`. Together with the spike death/completion control, this demonstrates native input response for these fixtures. It does not measure the counterfactual effect of suppressed requests.

### End-transition evidence and remaining divergences

All 18 replays recorded `PlayLayer::playEndAnimationToPos` at command 493 with `level_end_animation_started=false` before and `true` after; `has_completed_level` remained false at that boundary. The first post-command trace with the end flag true was 494. No animation boundary was inferred from a threshold.

| Failing arm | First differing command arguments, R2 / R3 | First differing player fields, R2 / R3 | Player fields strictly before 493 |
|---|---|---|---|
| flat / native | none / 31 | 510 / 510 | equal in both comparisons |
| flat / fixed-base-60 | none / 1453 (unmatched tail) | 517 / 553 | equal in both comparisons |
| spike / native | 375 / 250 | 495 / 496 | equal in both comparisons |
| spike / fixed-base-60 | 1449 / 1449 (unmatched tails) | 509 / 513 | equal in both comparisons |

Player differences in these failing arms first appeared after the observed end-animation boundary. However, callback flags or update/scheduler context could already differ before it: only flat/native R1 versus R2 passed the complete pre-end diagnostic among the failing arms. The table does **not** establish that every recorded field agreed during gameplay. It also does not prove that the end animation alone caused the divergence: the scheduler serves other callbacks, and render cadence, complete action state and RNG are not captured. Fixed scheduler delivery made the declared subset repeat in these two fixtures; the causal explanation remains narrower than a full engine model.

### Fixed-scheduler negative controls

Two additional controls ran on the same binary and fixed-scheduler environment through **Windows PowerShell 5.1**, with runner exit 0. Local evidence is `reports/native/controls-fc31a7a3eef642eb97a03f8e1c310ed6`. These are separate from the six-arm matrix.

| Control | Native result | Reader result |
|---|---|---|
| Hazard fixture with spike at x=300, no replay | `PlayLayer::destroyPlayer`, died at command 218; 219 trace rows; player 1 dead at x=`283.0182800292969`, y=`105`; complete recording, no errors or drops | Accepted |
| Replay target hash deliberately set to 64 zeroes | `AXIOM::error` at command 0; one initial trace row; `recording_complete=false`, error `Replay level hash mismatch` | Rejected, CLI exit 2 |

The hazard fixture digest is `f76afc3faf8bb328f668a2a2202600dfe17e46a9fc133f342a51dd337aeaace9`; it differs from the matrix's x=150 spike. Control capture SHA-256 values are `664a31010fa64bba854de16519d5a872e5bfa5a3da761a3fcf0447c5a51b4b07` (death) and `3cef773b7ed53c56cda5a8dc0e44813009d5aa1f7ece0124893b7e38bd4a1b6c` (wrong target). Thus the intervention retained native death and explicit target rejection in these controls. After reader hardening, the current Python regression check passed 225 tests and 83 subtests; all 24 matrix captures were revalidated and all six comparison verdicts remained unchanged. Those checks validate reader behavior, not independent engine execution.

## Qualification after lifecycle hardening

A separate follow-up completed at **2026-10-08 22:44:21 UTC** after fixing retained-layer ownership, deferred disposal when a terminal snapshot fails, and rejection of re-entrant command recording. The stricter reader also rejects new update/phase entries after terminal while allowing enclosing callbacks to exit later. This follow-up used Windows PowerShell 5.1 and the same fixed Scheduler policy; it does not replace the original six-arm experiment.

Both fixtures again passed all comparison components across three replays, each completing at command 734 with 735 trace, 977 gameplay-update and 979 Scheduler rows. The spike observation baseline died; the additional death control died at 218 and wrong-level replay failed at 0 with inspector exit 2. All four experiment files retained their exact previous bytes and existence after the runs. Failure/reset/re-entrant-command branches were reviewed independently but were not fault-injected.

Local evidence: `reports/native/qualification-744a2e5da3bf4c7fa423fe63b60fd1b0`; controls: `reports/native/controls-83f388a910f04b7bbc776ee3bfea1e9c`. The loaded DLL hash matches the DLL extracted from the package, and the native source digest was independently recomputed from the build inputs.

| Follow-up identity / evidence | SHA-256 or commit |
|---|---|
| Collector source commit | `de33070f0a62e9576e9aca3d7a86301e6992a7fb` |
| Native source-tree digest | `de3fd3c1325fe7aac7c5ec33f8e0a4690bb8f37cab6de307e90a357180f23db4` |
| Package / loaded adapter | `a670a7e05141500dc195731fd4db4e8ed3b24582ae260f3c02fab8e09eb71bb0` / `18c651ff3a83c862b308ec45f5d69d355ea15b44d7b0aea842717c447e92a8b0` |
| Fixed Scheduler environment | `eb5b3b0e58393d2146d75f4cca3377092032e17d7c266a31014ae39927dace47` |
| Qualification manifest | `522fd1f2e83f5fe61c790423a1cbd5d0feeb29cccff9b11fb17984ff4c6ff8a6` |
| Flat / spike comparison | `3bad8b02d78df9eeb59f3680eaa24b078744a6f4863c818db5ff5ab6bf8a8744` / `9e0ef56b2f3513c616b101dd6374c2a12e11383c527cdd4202900e5489f24ec1` |
| Death / wrong-level capture | `131fa2dfeeecedcb9157ac7c30ab350fcc06f29c4ef3c93cb7ef2779ef161ebe` / `0686d4ecb15f2701d1dff0b376f924acfcfe2cee039833e7df8afa7c736fb5cf` |

## Original study identity and evidence hashes

| Identity | Recorded value |
|---|---|
| Collector source commit | `3090bae97604f1621b03bf23358122229e17e2af` |
| Native source-tree SHA-256 | `a6204feef26fd2117d72e34c3997a526d763db9923aab86d221f245e74eae63c` |
| Package SHA-256 | `d1a289d006e1f81c29156692672ddcce7c0523340f94b73823fe6d4b4264b0e2` |
| Loaded adapter SHA-256 | `e9cdc4b143840b9c7967c4c0d4cc596468eab47d164334098e4e87b10fef8405` |
| GD 2.2081 executable SHA-256 | `fc5a16c292278bc2e8e078fb1d5023c2bd658322dd72712767ea70c2dd9ec6d0` |
| Geode 5.8.2 loader SHA-256 | `61847e05d4aa416bfd4d1f4e026b5b0e66848756473b285add6233a5cc9356d2` |
| SDK commit | `2a5fd87433da47d6bf07221774f0cbb25535ae08` |
| Bindings commit | `2a8b5c489ce8b49e7061b0543aa2bc5b22570063` |
| Flat fixture SHA-256 | `af8167d7ab8240a2798840a5f479f3af6144647c7bb41423e2303492b0e05558` |
| Spike fixture SHA-256 | `2b773cf937c91791c9f4d8340e129d7d9e40059c787c018bfd414544c2b82806` |
| Input / physics identities | `process-commands-pre-hook-owned-input-v1` / `native-2.2081-uncharacterized` |
| Native / fixed-base / fixed-scheduler environment SHA-256 | `53ba206f533d912512dab9f078a0e7f5fe4ecfb5c77ab25debd12e935d22795c` / `cc18eb010a2dec6b7d669a6079cc7e42510b12e96a702b5d379dc5d660a9a9a5` / `5eb3a0e3719e971ea23762b8055aba4533c4d153e90bca950753596746b70737` |

| Local evidence | SHA-256 |
|---|---|
| `study.json` | `0c9fb57ef72f7a7c37de0f73abd82f128819cd9511e46f76b08a47e56be627fc` |
| `flat-native/comparison.json` | `519652fc4187349cedc3cad6b5f550d116af94dc3921235efa4e4498821b69c7` |
| `flat-fixed-base-60/comparison.json` | `3a8e7686480241f794a80495daf0db6dbb07914f50c85204e237738c253b6987` |
| `flat-fixed-scheduler-240/comparison.json` | `e9a3ebd88953559721dc7c3acfa56c70c74424e563182aa9675a59a289040e94` |
| `spike-native/comparison.json` | `5472bb302c2eb841542d9c6bb476e2518ca6a6a7f0f2074cdaafd82cfc5b8908` |
| `spike-fixed-base-60/comparison.json` | `13276dbf0b7c31c39091899658d248cfa6b3cd6c2b28badfcdc03191724f2cb1` |
| `spike-fixed-scheduler-240/comparison.json` | `f33257263e009b73e286579b717992973e4f2bae932215798e86840e59241c42` |

The environment declares Windows x64, AXIOM 0.1.0 and Geode 5.8.2, with `configuration_complete=false`. Hashes identify the recorded artifacts; they do not authenticate execution or enumerate all settings. New builds and runs can have different collector/binary hashes and must retain their own ledger.

## Reproduce and interpret exit status

From the repository root, replace `<GD directory>` with a legally installed directory containing the pinned game and loader. Build and run the entire matrix:

```powershell
uv sync --locked --extra dev
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-native.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run-native-clock-study.ps1 -GameDirectory "<GD directory>" -Repetitions 3
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run-native-controls.ps1 -GameDirectory "<GD directory>" -ClockPolicy fixed-scheduler-240
```

`-ExecutionPolicy Bypass` applies to the launched process, not the machine policy. PowerShell 7 can run the scripts with `pwsh`. Individual reproduction is available through `scripts/run-native-smoke.ps1` with `-ClockPolicy native|fixed-base-60|fixed-scheduler-240`, `-Fixture flat|spike`, and an optional new `-OutputDirectory`. Inspect captures with `axiom native`; compare compatible replay files with `axiom native-compare`.

An individual smoke returns 1 when the recorded subset is inconsistent, preserving its comparison. The study accepts those expected measured failures, records all six arms, and gates **only** the two fixed-scheduler cases. Its successful exit is not an assertion that every arm passed. Missing comparison files, invalid captures, incompatible identities, unexpected exits and timeouts remain failures. Original `dt` and wall cadence stay visible in every comparison.

The scripts reject an already running sandbox, launch hidden owned processes and stop only their own processes. Before preparation they snapshot the existence and exact bytes of the isolated fixture, replay file, AXIOM settings and loader settings; nested/outer `finally` restores them. This is local experiment-state preservation, not a complete before/after ledger of personal saves. Writable-path guards and ignored sandbox directories remain required.

## Primary-source rationale and open gates

The pinned [Geode scheduler header](https://github.com/geode-sdk/geode/blob/2a5fd87433da47d6bf07221774f0cbb25535ae08/loader/include/Geode/cocos/CCScheduler.h#L128-L193) documents scheduled callbacks and their time scale; [interval actions](https://github.com/geode-sdk/geode/blob/2a5fd87433da47d6bf07221774f0cbb25535ae08/loader/include/Geode/cocos/actions/CCActionInterval.h#L44-L101) have elapsed time and `step(dt)`. The [2.2081 bindings](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/GeometryDash.bro#L7495) identify the actual hook signatures, including a **double** return for `getModifiedDelta`. These declarations guide instrumentation; they do not expose the whole proprietary engine.

Archived xdBot 2.4.1 targets 2.2074: its [TPS bypass](https://github.com/ZiLko/xdBot/blob/16ef8e86d3a295119583a1c236be7a9aab7568e4/src/hacks/tps_bypass.cpp) changes game-layer timing, while its [renderer](https://github.com/ZiLko/xdBot/blob/16ef8e86d3a295119583a1c236be7a9aab7568e4/src/renderer/renderer.cpp#L116-L141) separately advances the scheduler. Optional [frame fixes](https://github.com/ZiLko/xdBot/blob/16ef8e86d3a295119583a1c236be7a9aab7568e4/src/main.cpp#L351-L377) write position and rotation, so replay success with such corrections is not raw determinism evidence. The 2.2081 [gdsolver author describes scheduler-driven ending behavior](https://github.com/gdsolver/gdsolver/blob/8e8d69ada86a315c71d05cc8b8fe4d369d883aa2/src/mod/hooks_gamelayer.cpp#L1611-L1651); that observation motivated a test, not an assumed explanation of AXIOM's earlier failure. The [official Eclipse catalogue](https://api.geode-sdk.org/v1/mods/eclipse.eclipse-menu) declares 1.9.4 support for 2.2081, but its linked upstream returned 404 during this investigation; the available older fork cannot establish the current replay algorithm.

The next gates remain open: repeated tests on more fixtures and game modes; pause/focus/reset/interruption controls; RNG and trigger behavior; complete environment and state coverage; ordinary-input fidelity; checkpoint restoration; validated timing-window measurements; and human learning/performance calibration. Three repeats on two simple fixtures do not establish a probability of failure, a universal determinism result or any real-level difficulty rating.
