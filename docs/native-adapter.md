# Native adapter: M1 acceptance and operation

[Русская версия](native-adapter.ru.md) · [Architecture](architecture.md) · [Telemetry](telemetry-protocol.md) · [End-goal requirements](end-goal-requirements.md)

The first native domain is **Windows x64, Geometry Dash 2.2081, classic full-start runs, a fixed mod/configuration manifest and an explicit capture or owned-channel replay policy**. Geode 5.8.2 is the SDK target. This is a scoped integration target, not a statement that every classic mechanic or installed mod is supported.

M1 establishes capture and repeatable playback in the real game. It does not establish a calibrated human model, automatically discover every feasible route, or produce real-level AR. Compilation, installation, actual loading, captured outcomes and replay repeatability are separate evidence gates. No runtime-verification claim should be inferred from this document or a successfully built package alone.

## Compatibility and capability matrix

| Capability | M1 target / acceptance requirement | Limit |
|---|---|---|
| Game/loader identity | Exact game binary hash; runtime Geode, SDK, bindings and adapter versions | A version label alone is insufficient |
| Classic, normal full start | One reproducible short fixture, then an explicitly tested mechanics matrix | An arbitrary classic level is not automatically supported |
| Input capture | Ordered game-delivered presses/releases, player and button, hook phase and clock | Does not prove physical device arrival, latency, or human origin |
| Playback | Inject an explicitly prepared pre-hook command schedule from the genuine beginning | Translation from observed input or external replay formats is unvalidated |
| Replay channel ownership | Suppress and record every non-injector `handleButton` request while replay is active | Engine/human origin is unknown; direct player-method calls can bypass this boundary |
| Native outcomes | Engine death and final completion observation linked to the same run | Local survival or progress percentage is insufficient |
| State sampling | Declared player fields and sample phase for comparison | Player coordinates alone are not complete engine state |
| Pause/reset/quit | Abort at observed native callbacks and distinguish interruptions from completion/death | Focus loss is covered only if it invokes the observed pause callback; all focus paths remain a test gate |
| Snapshot/restore | Not part of the initial acceptance shortcut | Requires separate continuation-equivalence tests |
| Perturbation windows | Later gate after replay is validated | Finite successful samples do not prove continuous intervals |
| CBF and other input/physics mods | Separate future configurations | Do not pool with vanilla evidence |
| Platformer, other game builds or OSes | Separate future support domains | No compatibility inferred from the SDK's other bindings |
| Human calibration / AR | Outside M1 | No rating follows from a successful macro alone |

Record installed and enabled mods, plus settings that can affect input, scheduling, physics or gameplay. Begin acceptance with a controlled mod set. A detected unexpected configuration is unsupported until checked; do not remove it from the manifest merely to make an experiment appear compatible.

The [pinned official SDK build configuration](https://github.com/geode-sdk/geode/blob/2a5fd87433da47d6bf07221774f0cbb25535ae08/CMakeLists.txt) targets GD 2.2081 and requires a recent compiler (Clang 19+ or MSVC 19.44+). It fetches a mutable bindings branch by default; the AXIOM build script overrides that with a pinned checkout. Actual runtime compatibility still requires the gates below.

| Build dependency | Pinned identity |
|---|---|
| Geode SDK 5.8.2 | `2a5fd87433da47d6bf07221774f0cbb25535ae08` |
| Geode bindings | `2a8b5c489ce8b49e7061b0543aa2bc5b22570063` |
| Geode CLI | 3.9.0, downloaded archive SHA-256 checked by the script |

The MSVC build also applies one narrowly scoped link alias for `CCFileUtilsWin32::getPathForFilename`: the pinned SDK header declares it public, while its Windows x64 cocos import symbol has protected access decoration. The signature is otherwise identical. The alias supplies the sandbox subclass's vtable reference without modifying the SDK; it is not a general fix for a different ABI, platform or SDK version. Archive link diagnostics and still perform the writable-path runtime gate. [Pinned declaration](https://github.com/geode-sdk/geode/blob/2a5fd87433da47d6bf07221774f0cbb25535ae08/loader/include/Geode/cocos/platform/win32/CCFileUtilsWin32.h)

From a PowerShell terminal at the repository root:

```powershell
powershell -File .\scripts\build-native.ps1 -Jobs 4
$nativePackage = Join-Path (Get-Location).Path (Get-Content -LiteralPath .\.tools\native-package-path.txt -Raw)
Get-FileHash -LiteralPath $nativePackage -Algorithm SHA256
```

The script bootstraps dependencies under ignored `.tools`, uses installed Visual Studio x64 C++ tools and CMake, and normally builds under `native/build`. If that cache belongs to a previous workspace location, it preserves the cache and package and selects a deterministic `.tools/native-build-<hash>` directory. A conflicting selected cache is rejected. Only a successful build with a nonempty package writes `.tools/native-package-path.txt`; sandbox preparation resolves this contained relative path, while an explicit `-NativePackage` overrides it. If no marker exists, preparation uses the original `native/build` package. Existing dependency checkouts with a different commit or tracked edits are preserved and rejected. Build, installation and game launch are separate operations. Use an isolated game/save environment for first acceptance; do not install or launch against personal saves merely to test a package.

## Controls, sandbox and local files

The mod ID is `axiom.native-capture`. **Enable local capture** (`capture-enabled`) and **Enable AXIOM command replay** (`replay-enabled`) both default to false. Enabling starts recording at the next successful `PlayLayer::init` or reset. Disabling the effective option aborts on the next command-processing call; a true launch flag keeps that option enabled even if its setting is false. Equivalent explicit launch arguments are `--geode:axiom.native-capture.capture=true` and `--geode:axiom.native-capture.replay=true`. An `AXIOM CAPTURE`/`AXIOM REPLAY` HUD label and loader log announce active recording. Playback reads the fixed local file `replay.json` from this mod's save directory; exports go into its `captures/` directory. There is no upload.

The current input policy is `process-commands-pre-hook-owned-input-v1`. Ordinary capture observes and forwards input. During active controlled replay, only each one-shot injector request enters the original `handleButton`; all other requests are recorded as blocked diagnostics and not forwarded, including native cleanup requests. The origin of a blocked request is unknown: it may be engine-generated or live input. A direct call to player push/release can bypass this handler boundary and remains an unsupported contamination path. This is an explicit experimental input policy; equivalence to ordinary unmodified input delivery has not been established.

For the repository's pinned game binary, prepare the ignored test copy using the actual local installation path:

```powershell
powershell -File .\scripts\prepare-native-sandbox.ps1 -GameDirectory 'C:\path\to\Geometry Dash'
```

Preparation copies local binaries, installs the package only into `.tools/runtime/geode/mods`, junctions installed `Resources`, and creates a transient fixture payload. It does not launch the game or copy personal saves. An unexpected game hash, resource junction or sandbox mod set is rejected. Do not distribute this test copy or its proprietary assets.

The isolated `AXIOMSandbox` loader profile has `auto-check-updates: false`; preparation rejects a pending `.tools/runtime/geode/update` because it could replace the pinned loader on the next launch. A disabled update check does not undo a previously staged update. Recheck runtime loader version and binary hashes on every repetition, including after restarts; changing only the displayed SDK version cannot restore a changed runtime.

Before a launch, establish that personal save paths are isolated and preserve a before/after save ledger. Confirm that test runtime/save roots are fresh normal directories, not symlinks/junctions into personal data; canonical-path equality alone would not reject a redirected test save directory. The deliberate `Resources` junction is for installed assets and must not be used as a save location. Then, from the repository root:

```powershell
$sandboxExe = Join-Path (Get-Location).Path '.tools\runtime\AXIOMSandbox.exe'
Start-Process -FilePath $sandboxExe -WorkingDirectory (Split-Path -Parent $sandboxExe) -ArgumentList '--geode:axiom-sandbox=true' -WindowStyle Hidden
```

The helper is inert unless both the executable name `AXIOMSandbox.exe` and the explicit sandbox argument match. It checks the engine writable path before creating an unsaved fixture, then enables capture. This is a loading/oracle smoke fixture; it does not test meaningful button playback, all save access paths, or every mechanic.

Automated experiments prepare this test copy and terminate only the processes they start:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-native-clock-study.ps1 -GameDirectory 'C:\path\to\Geometry Dash' -Repetitions 3
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-native-smoke.ps1 -GameDirectory 'C:\path\to\Geometry Dash' -Fixture spike -ClockPolicy fixed-scheduler-240 -Repetitions 3
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-native-controls.ps1 -GameDirectory 'C:\path\to\Geometry Dash' -ClockPolicy fixed-scheduler-240
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-native-matrix.ps1 -GameDirectory 'C:\path\to\Geometry Dash' -Repetitions 3
```

The smoke script requires the complete press/release plan and native player callbacks, then fails if exact repeat comparison differs. The controls script requires native death on a generated spike fixture and rejection of a wrong-level replay. The clock study retains six cases, including inconsistent results, and requires both fixed Scheduler cases to pass. Each script preserves local evidence and restores the previous fixture, replay and sandbox mod/loader settings by bytes and existence, including after an experiment failure. A supplied smoke output directory must not already exist. `-ExecutionPolicy Bypass` applies only to that PowerShell process. See the [initial ledger](native-validation.md) and [executed clock investigation](clock-investigation.md) for actual results and remaining gates.

The [fixture matrix](native-fixture-matrix.md) declares generated payloads, exact input plans, pre-ending mode sequences and expected outcomes separately from captured evidence. Its runner compares the entire recorded replay through terminal across repetitions and checks selected input response against an empty owned-input control. The `fixtures`, `fixture-check` and `fixture-response` commands validate supplied files without running or authenticating the engine. A structurally valid mismatch result can have CLI exit 0; the runner reads the JSON verdict before closing a case gate.

Two save locations must be distinguished. The helper redirects engine `CCFileUtils` writable paths to `.tools/runtime/sandbox-saves`. Geode independently derives its save root from the executable filename: normally `%LOCALAPPDATA%\AXIOMSandbox`. Thus the mod's capture directory is normally `%LOCALAPPDATA%\AXIOMSandbox\geode\mods\axiom.native-capture\captures` and its replay source is the adjacent `replay.json`. If AppData directory creation fails, Geode falls back to the executable directory; inspect the runtime log/path instead of assuming the usual location. [Pinned Windows save-root implementation](https://github.com/geode-sdk/geode/blob/2a5fd87433da47d6bf07221774f0cbb25535ae08/loader/src/platform/windows/util.cpp), [mod save path](https://github.com/geode-sdk/geode/blob/2a5fd87433da47d6bf07221774f0cbb25535ae08/loader/src/loader/ModImpl.cpp)

## Clocks and hook order

Keep these measurements separate:

| Clock / observation | Meaning |
|---|---|
| Input hook timestamp | When the adapter observes delivery to a declared game input function |
| Command-processing callback index | The sequence of the hooked processing calls, with preserved `dt` and half/last-call flags |
| Gameplay/Scheduler update sequences | Paired entry/exit records with nesting, original and delivered `dt`, command bounds and native phase flags |
| Raw callback `dt` sum | Sum of the supplied callback arguments; no independently established simulation-time interpretation |
| Monotonic wall time | Capture duration and scheduling/recording overhead |
| Render/presentation time | Unknown unless independently observed |
| Hardware arrival / device-to-photon latency | Unknown unless measured through a separate acquisition method |

The pinned 2.2081 [bindings](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/GeometryDash.bro) expose `handleButton(bool down, int button, bool isPlayer1)` and `processCommands(float dt, bool isHalfTick, bool isLastTick)`. A command callback is not automatically a visual frame or a fixed 240-Hz physics tick. The boolean channel parameter means player 1 when true. Preserve callback flags, original event order and the exact observation/injection phase.

The launch argument `--geode:axiom.native-capture.clock-policy=<policy>` selects an explicit clock policy:

| Policy | Forwarded update argument |
|---|---|
| `native` (default) | Original argument unchanged |
| `fixed-base-60` | Float32 `1/60` once per original `GJBaseGameLayer::update` call on the initializing/current PlayLayer |
| `fixed-scheduler-240` | Float32 `1/240` once per original `CCScheduler::update` call throughout the guarded sandbox process, including before recording starts |

Non-native policies require `AXIOMSandbox.exe` and the explicit sandbox argument. They change the declared experiment environment; neither policy asserts a measured wall frequency or equivalence to ordinary gameplay. There is no accumulator, extra update call, manual ActionManager advancement, position/rotation correction or checkpoint restoration. The manifest identifies policy, hook, rational step and scope; original arguments and wall cadence remain observable. See the [clock investigation](clock-investigation.md) for the tested domain.

Calling the original input function does not independently prove that the physical device event arrived then, or that a later game stage accepted every request. Label the capture as hook-delivered input unless acceptance/rejection/buffering is separately observed. Input events generated by playback are not human observations.

Geode [hook priorities](https://github.com/geode-sdk/docs/blob/main/tutorials/hookpriority.md) distinguish code before and after the original call. Publish the actual stage used by this adapter. Moving the original call into a later task can re-enter the hook; use an explicit replay guard and synchronous ordering. Hook priority changes or an additional input mod create a newly measured configuration.

## Operator workflow

1. Preserve the exact short level and the supported environment manifest. Use a lawful game installation and local output directory. Keep game binaries, saves and private captures outside Git.
2. Build with `scripts/build-native.ps1` and record the package hash. Generic Geode build commands can install through a CLI profile; AXIOM's packaging must disable that behavior so installation is an explicit separate step. [Official packaging implementation](https://github.com/geode-sdk/geode/blob/2a5fd87433da47d6bf07221774f0cbb25535ae08/cmake/GeodeFile.cmake)
3. Restart the game after installation. Confirm actual adapter loading using the loader log and adapter status; a copied file or enabled checkbox is not sufficient. Inspect the manifest for the current game and loaded-mod configuration.
4. Opt in to capture. Start a normal classic run from the true beginning, with released initial controls. Record a complete attempt, including genuine completion/death or a clearly marked interruption. Repeat after a clean full reset.
5. Inspect the capture locally before sharing it. Check exact payload identity, clocks, initial state, ordered presses/releases, sampled states and terminal outcome. Unknown fields remain unknown; do not substitute nominal frame rates or invented acceptance times.
6. Prepare an AXIOM native replay schedule for the same genuine beginning, using the exact level/environment hashes and explicit pre-hook indices. Capture it at least twice with replay enabled; reject identity/configuration mismatch. Retain non-injector blocked-request diagnostics and check for unsupported direct player-method interference. Pause, focus loss, quit, unexpected reset or changed environment must abort or invalidate the comparison; verify which focus paths actually reach the pause hook.
7. Repeat using the same declared comparison settings. Retain every attempted run and report failures, divergent results and sample coverage. A completion only closes the witness gate for the run/configuration in its evidence package.
8. Only after repeatability passes, perform scheduling-resolution and timing perturbation experiments, always continuing to the final oracle. Human collection and AR remain later stages.

Observed capture is not currently convertible into faithful playback. A requested event between calls has the latest entered call's index, while replay index `n` injects before call `n`. Direct copying shifts its phase. M1 accepts only deliberately prepared native schedules; neither GDR import nor observed-event conversion establishes this clock.

The local `replay.json` format is:

```json
{
  "schema_version": 1,
  "kind": "native_replay",
  "clock": "processCommands_call_index",
  "level_sha256": "<64 lowercase hex characters>",
  "environment_sha256": "<64 lowercase hex characters>",
  "inputs": [
    {"command_index": 20, "player": 1, "button": 1, "pressed": true},
    {"command_index": 30, "player": 1, "button": 1, "pressed": false}
  ]
}
```

These indices illustrate the format, not a verified route. Events use integer indices 1–20,000, player 1–2, button 1–3, Boolean `pressed`, and array order for equal-index events. At most 4,000 planned events are supported; an empty plan is valid for an automatic fixture. Only documented fields are accepted; duplicate keys, nesting above 64 and source files above 16 MiB are rejected. A native death/completion can end before the plan's future events: the validator reports the unexecuted tail and evaluates only the executed prefix through that terminal.

## Capture schema and comparison

The current native record is schema 2, `kind: native_capture`, with one `attempt` per file. The inspector also accepts schema 1 without fabricating its absent update/phase observations; older input policies without a blocked-request stream remain explicitly marked as not recorded. Provenance is declared `native-engine-capture` with `independently_verified: false`; capture origin is not authenticated by parsing JSON. The level hash identifies the exact bytes held in `GJGameLevel::m_levelString`, not inferred collision geometry. The collector's source-tree digest identifies the compiled native sources, CMake and mod manifest even when a Git commit predates local edits. The environment has a recursive sorted-key compact UTF-8 JSON hash and `configuration_complete: false`. Selected player-state fields are recorded with `state_completeness: selected_fields_only`, not a restorable snapshot.

The trace begins at command index 0 after initialization/reset, then retains contiguous command-processing calls with `dt_seconds`, `is_half_tick` and `is_last_tick`. Initial trace timing is zero. Command indices advance before the original callback; regular sampled states are taken after it. The terminal `levelComplete`/`destroyPlayer` snapshot is separate: it may differ from the final post-processing sample and must be compared separately. Export waits for enclosing command/update/Scheduler/ending-phase hooks to return.

Schema 2 adds `attempt.updates`, `attempt.scheduler_updates` and `attempt.phase_events`. Paired update records retain entry/exit command bounds, nesting, original/delivered `dt`, raw ending/completion flags and wall timestamps. Trace and terminal samples retain the enclosing update/Scheduler sequence; calls already in progress when recording begins have unknown membership. Paired `PlayLayer::playEndAnimationToPos` observations supply the native ending transition, without guessing a percentage or coordinate boundary. Limits are 20,000 commands, 20,000 rows per update stream, 256 phase events and 16 MiB per source file. Missing/truncated records invalidate terminal evidence.

Delivered `inputs` preserve the requested `handleButton` phase and observed player push/release callback phases, including the native return value where available. Sources are observed/replay, while an attempt's origin is unknown/replay; observed delivery alone does not attest that a human generated it. `attempt.blocked_inputs` is separate, always present and empty for observation capture. Each blocked diagnostic has its own contiguous sequence, command index, player, raw signed-int32 button, pressed state, `source: unknown` and monotonic wall timestamp. It has no delivered phase or native return because the original handler is not called. Delivered plus blocked records share a 12,000-record limit. Initial start kinds distinguish `level_start`, `practice`, `start_position` and `unknown`. A second player pointer can exist while inactive; player activity is not captured and its fields alone must not override the native terminal callback.

Python provides `inspect_native_capture(path)` and `compare_native_captures([path_a, path_b, ...])` in `axiom.native`. Inspection is structurally bounded supplied evidence. Full-start comparison requires matching challenge/environment/collector identities, an exact source replay hash and retained plan, distinct attempt IDs, contiguous trace through terminal and complete integrity with zero dropped records or errors. Practice/start-position captures cannot satisfy that comparison. Its successful status is **`recorded_subset_consistent`**, not complete determinism or M1 certification. Compare x/y, y velocity, rotation, mode and death fields only as the recorded subset; unrecorded world/trigger state remains unchecked.

With the Python package installed, inspect a local capture and compare two to sixteen controlled repetitions:

```powershell
axiom native 'C:\local-evidence\capture-a.json' --json .\reports\native\inspection.json
axiom native-compare 'C:\local-evidence\replay-a.json' 'C:\local-evidence\replay-b.json' --json .\reports\native\comparison.json
```

The comparison is exact for raw command callback arguments, selected states including rotation, delivered input phases/order/native return values, retained plan, terminal placement/state, raw native phases, update contexts, delivered update/Scheduler rows and native phase events. Original incoming update arguments and wall timestamps remain separate diagnostics; delivered arguments still decide equality. In `native` mode delivered equals original, so its variable arguments still participate. Blocked-request differences are also reported separately. A matching subset does not assert byte-identical files or an identical full request stream. `pre_end_animation_diagnostics` uses the actual recorded native callback boundary; prefix agreement cannot override failed whole-run comparison. The reported callback `dt` sum must not be relabelled verified simulation time. Aborted/error or incomplete captures are rejected as terminal evidence; preserve their local files and logs as failed attempts.

## Executable first-checkpoint checklist

Use this checklist as a release/evidence ledger; unexecuted items remain unchecked. A build result alone must not check the runtime rows.

- [ ] Save game, loader, SDK, bindings, adapter and configuration hashes in the run manifest.
- [ ] Build the package; archive compiler/configuration/log, source commit and package SHA-256.
- [ ] Observe the adapter loaded inside the exact game build; archive its runtime handshake/log.
- [ ] Export one real native run from the true normal-mode start to the actual engine completion event.
- [ ] Export a death/control run and an interrupted run; verify they are not reported as completions.
- [ ] Include a nontrivial fixture with both a press and a release. An automatic zero-input fixture may test loading/oracle behavior but cannot validate input playback.
- [ ] Check input player/button/order, declared hook clock and phase, raw callback timing, initial holds and terminal event lineage.
- [ ] Execute the prepared plan from the true beginning; require exact agreement of declared sampled states, callback arguments, input phases/order and terminal. Retain wall duration only as a diagnostic; report any unexecuted plan tail.
- [ ] Repeat over an explicitly recorded count and fixture/configuration matrix; publish divergence and errors rather than only successful repeats.
- [ ] Test wrong-level/wrong-build/wrong-input configuration rejection, non-injector suppression/diagnostics and unsupported direct player-method contamination paths.
- [ ] Test pause, focus loss, reset, quit and settings changes; no stale capture may masquerade as a new full-start run. Document paths that the current callbacks do not observe.
- [ ] Measure recording overhead and native replay throughput against a declared control, retaining clock/discontinuity observations.
- [ ] Publish the tested capability matrix, untested mechanics and unsupported modifications.
- [ ] Keep a locally reproducible evidence report; share only consented, licensed and reviewed files.

Checkpoint restoration is a separate gate: capture a reachable boundary from a real prefix, restore it, and compare its entire continuation against the uninterrupted run. Carry world/trigger/clocks/held inputs and every other future-relevant state; incomplete snapshots must not be used to manufacture full-level witnesses.

## Privacy and interpretation

Capture is local, opt-in and game-scoped. Game input hooks are not a system-wide keyboard recorder. Do not collect account credentials, private chat, clipboard or unrelated applications. No upload is needed for acceptance. Review level payloads, names, mod metadata and traces before public release; they can contain private or identifying information. See the [telemetry protocol](telemetry-protocol.md) for consent and retention requirements.

Native instrumentation can produce real-engine evidence, but a submitted file does not automatically authenticate its origin. Structural file validation, same-run completion evidence, observed replay consistency and independent replication remain distinct. A controlled-replay completion is scoped to its owned-channel policy; it does not establish an equivalent ordinary human/vanilla execution. A finite passing suite does not prove universal determinism, a failed search does not prove impossibility, and no M1 output measures a human limit or calibrated AR.
