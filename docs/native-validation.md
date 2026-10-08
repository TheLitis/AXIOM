# Native validation evidence

[Русская версия](native-validation.ru.md) · [Adapter operation and acceptance](native-adapter.md) · [End-goal requirements](end-goal-requirements.md)

**Final validation status: native capture and input response observed; exact repeat agreement FAILED.** One observation baseline and three controlled replays completed. Delivered input matched, but callback flags, selected player states and terminal rotation did not match exactly. The smoke runner failed its repeat gate with exit code 1. M1 remains open.

The experiment runs a locally generated classic fixture inside the actual Windows x64 Geometry Dash 2.2081 engine with Geode 5.8.2. Its input plan is deliberately constructed test data, not human performance. Controlled replay uses the declared owned-input policy. Equivalence to ordinary vanilla/human delivery, complete engine determinism, measured timing windows and AR are not established by this experiment.

## Final build and run identity

| Evidence field | Final value |
|---|---|
| Run date/time and evidence directory | 2026-10-08 about 21:55 UTC / 2026-10-09 about 00:55 MSK; local `reports/native/smoke-2377b6ffa9ca434d9749e1f5f39ff257` |
| Recorded repository commit | `393ed19b8df3f8375a7023a37fde0a5ca57ea852` |
| Native source-tree SHA-256 | `c44ed6b7d0eed2cf10a7a367bc42405e5f6ffd62c18521007c6d2005e3a1fd41` |
| Build configuration, compiler and saved build log | Release x64; Visual Studio 18 2026; MSVC 19.51.36256.0; Windows SDK 10.0.26100.0; local `reports/native-build.log` |
| Package SHA-256 | `f8d37d484e026d353936c42c525675321fd42bfb3bbaf68546d4098bd9c2ad3f` |
| Loaded adapter binary SHA-256 | `c00d43203744ab26dddb7ed1ad733f0e79c899376e784b8f5c2c9ea0cf7a1269` |
| Actual game executable SHA-256 | `fc5a16c292278bc2e8e078fb1d5023c2bd658322dd72712767ea70c2dd9ec6d0` |
| Actual loader version and binary SHA-256 | 5.8.2; `61847e05d4aa416bfd4d1f4e026b5b0e66848756473b285add6233a5cc9356d2` |
| SDK commit | `2a5fd87433da47d6bf07221774f0cbb25535ae08` |
| Bindings commit | `2a8b5c489ce8b49e7061b0543aa2bc5b22570063` |
| Fixture raw level-string SHA-256 | `af8167d7ab8240a2798840a5f479f3af6144647c7bb41423e2303492b0e05558` |
| Effective input policy and attempt input source | `process-commands-pre-hook-owned-input-v1`; baseline `unknown`, repetitions `replay` |
| Environment SHA-256 | `48117ad99bf95b4b830ad53fde644ba469d397551c8fef5b0791ea002d8fd251` |
| Declared loaded mods | `axiom.native-capture` 0.1.0 and `geode.loader` 5.8.2; `configuration_complete: false` |
| Sandbox writable-path check | Runtime logs confirm `.tools/runtime/sandbox-saves`; loader update checks were skipped |
| Original loader / personal-save ledger | Original installed loader SHA-256 matches the unchanged 5.8.2 hash above; a complete personal-save before-after ledger was **not collected** |
| Runtime adapter loading/export logs | Local loader logs at 00:55:17, 00:55:25, 00:55:34 and 00:55:42 MSK; smoke log `reports/native-smoke.log` |
| Public evidence scope | Curated metrics/hash ledger in this document; raw captures, comparison and logs remain ignored local reports |

The source-tree digest identifies the native files, CMake and mod manifest compiled into the adapter; a Git commit alone does not identify uncommitted changes. The package build succeeded with SDK MSB8027 warnings about duplicate object-file names; the saved log retains them. Do not combine captures from different builds, policies or environments by rewriting their identity fields. Public JSON inspection still reports unauthenticated origin and selected fields only.

Software validation passed 183 tests and 83 subtests, Ruff checks/format checks and Python wheel/source builds. The [Windows native build](https://github.com/TheLitis/AXIOM/actions/runs/37850395564) and [Windows/Linux Python 3.11/3.14 CI](https://github.com/TheLitis/AXIOM/actions/runs/37850395573) passed at commit `47c9eb56e0e77ff01cfeecc730a018713baeeafb`. CI compilation does not execute the game or authenticate the local runtime captures.

| Retained local artifact | SHA-256 |
|---|---|
| `baseline.json` | `f0bb9e3797466cdc74161d89ee470aaff87be827cff26156c13af2a6e91c4452` |
| `replay-1.json` | `37ba856ea8fca23f0ebdbcc46429a40337e63a56cd3ea6d99ada39e9a95ca28f` |
| `replay-2.json` | `93f21c5a8d5d1d1c133fbbb7726f9d4e5b6eaa7e39e934ec296d1bd84321d3e8` |
| `replay-3.json` | `599367030823e4f0f3d629246f1436aaeb4c283d96120298815e6c4671e0eb55` |
| `replay.json` | `749d6ecb61eb53bd30d85bfbe5c23d91b58f08baec4869f1f7f39b228cfabef4` |
| `comparison.json` | `562cf9174c2a8caac47f58bfe6d6fe17af9587a18be0de5a11bde2866a7ef8ac` |

## Runtime evidence

The smoke script created one observation baseline, then three controlled repetitions using a player-1/button-1 press at command index 60 and release at 90. These are processing-call indices, not certified physics ticks or render frames. `baseline.json` is the observation baseline; the repeat comparator uses **`replay-1.json` as its comparison baseline**.

| Check | Final observation |
|---|---|
| Baseline: full start, observation source, native completion | `level_start`, `unknown`, `PlayLayer::levelComplete` at 734; 735 trace records |
| Attempted / exported / schema-valid replay repetitions | 3 / 3 / 3; each `level_start`, `replay` |
| Replay native outcome and terminal command index | All three `completed` via `PlayLayer::levelComplete` at 733 |
| Planned requests executed, including zero unexecuted tail | 2 per replay; tail 0 |
| Native player push and release callbacks | Push at 60 and release at 90, each `native_return: true` in all three replays |
| Trace / delivered-input / blocked-request counts | Per replay: 734 / 4 / 1; baseline: 735 / 2 / 0 |
| Exact delivered-input and retained-plan agreement | **PASS** across all three replays, excluding wall diagnostics |
| Exact callback-argument agreement | **FAIL**; first differing calls 89 and 126 |
| Exact selected-player-field agreement | **FAIL**; first differing calls 542 and 504 |
| Exact terminal callback/outcome/placement agreement | **PASS** across replays |
| Exact separate terminal-player-field agreement | **FAIL**; player-1 rotation differs |
| Blocked-request diagnostic agreement | Equal signature: one unknown-origin player-1/button-1 release at call 1; excluded from delivered-subset consistency |
| Final comparison status | `recorded_subset_inconsistent` |
| Smoke process exit and retained artifacts | Exit 1, repeat gate failed; all four captures, inspections, plan and comparison retained locally |

At call 61, all three replays recorded player-1 `y=107.46690368652344` and `y_velocity=10.964`; the observation baseline recorded `y=105` and velocity 0. Native callbacks and a trajectory response are observed. The counterfactual effect of suppressing other requests is not isolated by this baseline comparison. Completion alone does not establish replay fidelity, and native Boolean returns do not establish physical device arrival or independently validated input acceptance.

## Known divergence and interpretation

**Final divergence result: exact agreement failed in both comparisons against replay 1.** The prepared plan and delivered input signatures match. Callback `dt` and half flags match; `is_last_tick` differs. Selected-state differences concern player-1 x/y/rotation. No tolerance or field filter was applied.

| Pair | Callback differences | Selected player differences | Terminal player-1 rotation |
|---|---|---|---|
| Replay 1 vs 2 | First call 89; 4 `is_last_tick` differences | First call 542; 192 differing records; x/y/rotation each differ in 192 records | 538.072998046875 vs 538.2860717773438 |
| Replay 1 vs 3 | First call 126; 3 `is_last_tick` differences | First call 504; 230 differing records; y/rotation differ in 230 records, x in 226 starting at 506 | 538.072998046875 vs 538.1959228515625 |

The current rule compares callback `dt`/half/last flags, delivered input order/phases/returns, selected player fields, retained plan and separate terminal exactly. Input wall timestamps and terminal wall duration are diagnostics and are excluded. The observed flag and x/y/rotation differences remain failed exact checks. Their timing is compatible with an animation/batching hypothesis, but that cause is **not proven**; a controlled experiment must isolate it.

Even `recorded_subset_consistent` would cover only the declared fields and tested fixture. An inconsistent result means the repeat-agreement gate remains open; it does not prove that every route or level is impossible. Owned-channel replay suppression can include engine-generated requests of unknown origin. Direct player-method interference and ordinary-input equivalence remain outside the demonstrated boundary.

## Reproduce locally

Use a lawful local game installation, a supported Windows x64 compiler and PowerShell 5.1 or newer. Run from the repository root:

```powershell
uv sync --locked --extra dev
powershell -NoProfile -File .\scripts\build-native.ps1 -Jobs 4
powershell -NoProfile -File .\scripts\run-native-smoke.ps1 -GameDirectory 'C:\path\to\Geometry Dash' -Repetitions 3
powershell -NoProfile -File .\scripts\run-native-controls.ps1 -GameDirectory 'C:\path\to\Geometry Dash'
```

The smoke runner prepares an ignored test copy, rejects an already running `AXIOMSandbox` process, launches its own hidden process and stops only that process. It temporarily writes the local native replay source and restores the previous file afterward. Preparation checks ordinary test/save roots, the pinned game hash and absence of a staged loader update; the isolated loader profile disables automatic update checks. These controls do not replace the before-after personal-save ledger or prove every save access path.

Evidence is retained under a unique `reports/native/smoke-*` directory. A failed capture, missing input response, incompatible identity or inconsistent final comparison is an error; preserve the directory and runtime logs. An inconsistent `axiom native-compare` result can itself exit zero because it successfully produced a comparison; the smoke runner additionally checks the status and fails its gate.

Inspect saved files independently, substituting the actual evidence directory:

```powershell
.\.venv\Scripts\python.exe -m axiom native 'reports\native\smoke-ID\baseline.json'
.\.venv\Scripts\python.exe -m axiom native-compare 'reports\native\smoke-ID\replay-1.json' 'reports\native\smoke-ID\replay-2.json' 'reports\native\smoke-ID\replay-3.json' --json 'reports\native\smoke-ID\comparison-recheck.json'
```

Copied game binaries, proprietary assets and personal saves are not published. This repository publishes curated metrics, hashes, fixture-generation code and reproducibility commands; raw captures/comparison/logs stay in ignored local `reports/`. There is no separate public summary JSON. The published ledger permits an independent rerun but is not a substitute for independent authentication of the original private files.

## Native controls

Controls used the same adapter/loader/environment identity and are retained under local `reports/native/controls-8bbb4349d560475f9c19642834c01c01`. The controls runner exited 0.

The published controls runner was also executed successfully under PowerShell 7 and Windows PowerShell 5.1 with the same binary and control outcomes. Local logs are `reports/native-controls-public.log` and `reports/native-controls-ps5.log`; processes were cleaned up and the replay/fixture files restored.

| Control | Observed result |
|---|---|
| Generated hazard, level SHA-256 `f76afc3faf8bb328f668a2a2202600dfe17e46a9fc133f342a51dd337aeaace9` | `PlayLayer::destroyPlayer`, `died` at call 218; 219 trace records; player-1 dead, x=283.0182800292969, y=105; complete integrity, zero errors; inspector accepted |
| Replay with all-zero wrong level digest | `AXIOM::error` at call 0; one trace record; `recording_complete: false`, error `Replay level hash mismatch`; inspector rejected with exit 2 |

The retained `death.json` SHA-256 is `f0eafac416bb62cdc288b8c68fc4e8d2a4ce59344d42fcd149a3767b0ee58ca6`; `wrong-level.json` is `08aeb6db9493016e9d4a6e6584cfa3f78c08b7df27efe30a10490c787b57c74b`. These controls demonstrate one death path and one target-mismatch rejection, not the complete native rejection/mechanics matrix.

## Negative and untested gates

The final runtime results must distinguish tested rejection behavior from Python-only contract checks and entirely untested mechanics. Do not infer a native pass from a unit-test pass.

| Gate | Final status / required evidence |
|---|---|
| Native capture, full-start completion and input response | **OBSERVED** for the generated fixture and declared policy |
| Exact repeated selected-subset agreement | **FAILED** in three-replay run; M1 remains open |
| Wrong-level replay rejection inside the game | **OBSERVED** in one all-zero target-digest control |
| Wrong-environment replay rejection inside the game | **NOT_TESTED** |
| Wrong-build/loader/mod-set rejection and update drift | **NOT_ESTABLISHED** for the complete runtime matrix |
| Native death control versus completion | **OBSERVED** for one generated hazard, same-run callback and post-call trace |
| Pause, focus, reset, quit and disable controls | **NOT_ESTABLISHED**; cover actual callback paths and mark unknown starts |
| Non-injector suppression and diagnostics | **OBSERVED** for the retained call-1 request; origin unknown, not forwarded |
| Direct player-method bypass and other input/physics mods | **UNSUPPORTED / NOT_ESTABLISHED** |
| Other classic modes, triggers, dual and mechanics matrix | **UNTESTED** beyond the declared fixture |
| Platformer, other game builds or operating systems | **UNSUPPORTED** in this first domain |
| Recording overhead, throughput and scheduling resolution | **NOT_MEASURED** |
| Complete configuration and engine-state determinism | **NOT_ESTABLISHED** |
| Checkpoint restore/continuation equivalence | **NOT_IMPLEMENTED / NOT_ESTABLISHED** |
| Full-run native perturbation windows | **NOT_MEASURED** |
| Human telemetry, predictive calibration and real-level AR | **NOT_ESTABLISHED** |

The successful capture/input/control observations do not close the failed repeat gate or the untested gates above.
