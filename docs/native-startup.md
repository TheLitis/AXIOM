# Bounded native startup diagnostics

[Русская версия](native-startup.ru.md) · [Windows input](windows-input.md) · [Native adapter](native-adapter.md) · [Roadmap](roadmap.md)

**14 October 2026: startup diagnostics and observer fault checks are ready; live Windows input qualification remains open.** This checkpoint builds the adapter and examines retained files without launching Geometry Dash. It does not establish the cause of the three preceding unsuccessful starts, a completed schema-7 capture or the full M1 acceptance gate.

## What is retained

The Windows-input runner takes a bounded inventory before starting its owned game process. After exit or cleanup, it freezes a separate manifest snapshot, copies selected startup files and writes collection metadata in `startup_diagnostics`. The primary observation error, diagnostic errors and `cleanup_errors` remain separate. `process_cleanup` records whether exit was observed before cleanup, whether termination was requested and the natural exit code when available. A deadline is an explicit timeout; an exit after runner-requested termination is not relabelled as a natural exit.

The evidence bundle is a separate schema-1 format, not a gameplay capture. It includes original bytes, sizes, SHA-256 identities and read states for immediate `geode/logs/*.log`, selected text/log files in `geode/crashlogs`, `_geode_early_error.txt` and the declared runner stdout/stderr beside the supplied manifest. It does not scan game profiles or interpret arbitrary filesystem trees. Symlink/reparse paths, unstable reads and redirected ancestors are rejected; missing, empty, removed, unreadable and bounded-out sources remain explicit.

Collection limits are 64 selected log files, 256 directory entries per group, 4 MiB per file, 16 MiB total retained log bytes and 2 MiB per JSON input. Inspection retains at most 2048 marker observations. Incompleteness or unsupported text encoding is reported rather than turned into success. ANSI/CRLF and BOM UTF-16 normalization applies only to marker matching; source bytes remain unchanged.

## Reading a startup report

The inspector recognizes bounded Geode/AXIOM log messages for loader completion, adapter load/refusal, app/menu initialization entry and return, save isolation, manual readiness, fixture launch request and capture start/export. An initialization return records its bool; a scene launch request or export log is not a full-run completion witness. A missing marker means it was not observed in the retained text.

| Source relation | What the report permits |
|---|---|
| No prelaunch inventory | `retrospective_runtime_unbound`; markers are retained, with no current-attempt readiness |
| Unchanged existing runtime file | Historical marker observations only |
| Changed same-name runtime file | New bytes are retained, but log rows remain unbound to the attempt |
| New runtime file after a complete inventory taken before process start | May establish log-level manual readiness when the exact marker is present |
| Runner stdout/stderr | Diagnostic observations; they cannot establish current-attempt readiness |

Even a prospective inventory does not authenticate process membership: `authenticated_process_membership` stays false. Readiness is a log-level condition, not a proof of gameplay, physical input, complete engine state or ordinary-input equivalence. Signed Windows process exit codes retain their original value and unsigned 32-bit interpretation; neither establishes a crash cause. `cause` remains `unknown` and `m1_gate` remains `not_established`.

## Offline commands

These commands read/write diagnostic files; they do not start the game or generate input. Paths must be ordinary, outputs must be fresh, and an inspection output must sit outside the bundle directory.

```powershell
uv sync --locked --extra dev
uv run --locked axiom native-startup-baseline '.tools\runtime-new' --output 'reports\before-start-new.json'
uv run --locked axiom native-startup-collect '.tools\runtime-new' --attempt-manifest 'reports\attempt-new\startup-manifest-snapshot.json' --baseline 'reports\before-start-new.json' --output 'reports\startup-review-new'
uv run --locked axiom native-startup 'reports\startup-review-new\bundle.json' --json 'reports\startup-review-new.inspection.json'
```

Take the baseline before the declared process start; the runner does this itself for future Windows-input attempts. For an old runtime without that inventory, omit `--baseline` and retain retrospective attribution. Collection and baseline commands print metadata to stdout; `--json` is an inspection option. The Python interfaces are `snapshot_startup_logs`, `collect_startup_evidence` and `inspect_startup_evidence` in `axiom.startup`.

## Retained unsuccessful starts

The separate retrospective study preserves the three original manifests and runner outputs unchanged. The old manifests did not bind the runtime logs to their processes, so the newly retained logs cannot acquire authenticated membership retroactively. All three diagnostic inspections are complete within their declared scope, with current-attempt readiness unestablished and cause unknown.

| Old attempt | Retained marker observations | Loader log SHA-256 |
|---|---|---|
| First new package | Loader completion, adapter load, explicit guard refusal | `c1aa47e34995ba6a80f8493661b3eae1c17f4bc5d6f4ebac68e1e6583e5223bc` |
| Second new package | Loader completion and adapter load | `e2e6b3b99a20807461b372eff6c925ac61d4d6edf7901ce0881f67038ad9d91d` |
| Old-package control | No retained startup markers | No loader log retained |

The first two logs have 11,566 and 11,480 bytes respectively. Neither retains save-isolation, manual-ready, fixture-launch or capture markers. The study index SHA-256 is `6969cf27d14de751193f4858999a6370367b2b1c3dd87ef0000335ddb7dc202e`. A same-host standard-library-only audit passed **79 byte/identity/marker checks with zero discrepancies**, without importing AXIOM or executing the game. Its report SHA-256 is `d791ab72bb88af132cf08cc9b1d4b5df334adead09f1e55316712e974a6e5eda`. These are archived-file checks, not independent engine execution.

The caption “Attention” cannot identify a startup cause. The pinned Geode source has two distinct prompts: [Alt+Shift clean mode](https://github.com/geode-sdk/geode/blob/2a5fd87433da47d6bf07221774f0cbb25535ae08/loader/src/platform/windows/main.cpp#L154-L168) before `geodeEntry`, and [Shift safe mode](https://github.com/geode-sdk/geode/blob/2a5fd87433da47d6bf07221774f0cbb25535ae08/loader/src/load.cpp#L85-L100) before logger setup. Neither the dialog body nor relevant key state was retained for the old control. The two newer logs reach loader completion; their exits are not explained by waiting at these earlier prompts. No guard bypass or modifier/input intervention is part of this checkpoint.

## Software validation and compiled identity

The production Windows observer now reports coverage loss when a retained main/raw window is destroyed or its installed hook is lost, and validates ownership before reusing a hook. Historical successful attach declarations remain distinct from live coverage; normal detach does not falsify them. [Candidate protocol v2](windows-input.md#association-contract) accounts for pinned Control/Alt side conversion while leaving unrecorded keyboard-layout mapping unresolved.

The native fault harness compiles the production observer with real matjson and fake Windows/Geode surfaces. Its corrected pre-fix baseline exposed **5 failures in 20 scenarios / 81 checks**; the final harness passed **23 scenarios / 112 checks**. It checks forwarding/return/last-error preservation, attachment and rollback, nesting, raw-read failures, bounds, exclusions, chain replacement, callback draining and lost-window rejection. It does not run a real Windows message loop or the game.

Startup tests passed **50 tests, with 2 symlink tests skipped** because creation privileges were unavailable. A real Windows junction rejection test passed. Four separate console-process checks passed for fast exit 0, exit 2 with stderr, preservation of existing output paths and outside-workspace rejection. The full suite passed **880 tests and 83 subtests, with those 2 skips**; Ruff passed on 70 Python files. Windows CI runs the console checks, and native CI builds the adapter and runs the fault harness without game execution.

| Identity | Value |
|---|---|
| Observer fix commit | `0f89513d72e675ca654a8698b6b23687eb138621` |
| Candidate normalization commit | `9aa5b245f26c40a4025eb8a9dd48375488e7dcf1` |
| Startup evaluator and compiled source commit | `547d5c12a8331a0c32d076b7237b03f5a1b9e064` |
| Native source-tree SHA-256 | `61573083daf5cac28cac0ad5a2093b85e8c657e4503c97895c7428516e072d62` |
| Compiled package SHA-256 | `ce933f4c25c49771c93e15c49b25f8b6cd4f50fd91c7aec7a46e8e4cd7f87b45` |
| Packaged DLL SHA-256 | `1040a5b6e55274132e774b1749b6c734fecdfee05d15b581465f1f0ebf9b765f` |
| Native fault result SHA-256 | `6ef56c876dd47c55634a0698d20edb6dcd3c3d491156d774c8d3e4f740c01999` |

The source-tree identity uses ordinal relative `native/src/*.cpp`/`*.hpp` paths recursively, followed by `CMakeLists.txt` and `mod.json`, hashing each `path:SHA-256\n` record. The compiled identity does not include the later documentation commit. Native packages, logs, captures and audit reports remain ignored local artifacts.

**Still required for M1:** a fresh native-clock schema-7 run with retained startup phases, window/ingress witnesses, typed/UI/queue/player correspondence, integrity and terminal checks, followed by declared focus/reset/interruption and configuration/collider/trigger coverage. This checkpoint has no new native execution and does not establish timing windows, human forecasts or AR.
