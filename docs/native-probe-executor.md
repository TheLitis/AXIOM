# Automatic native probe executor

[Русская версия](native-probe-executor.ru.md) · [Probe pipeline](probe-engineering.md) · [Native adapter](native-adapter.md)

`axiom probe-run` consumes a frozen `probe-export` exchange and executes its jobs sequentially through the Windows sandbox. Each attempted job gets a fresh runtime, an explicit replay, retained capture or execution error, and checkpoint files. Python validates the native terminal and identities before the result enters the discrete map.

This is an implemented execution path, developed and checked without launching Geometry Dash in this increment. Synthetic captures test the software kernel; real console processes test Windows process primitives. A qualified native measurement campaign, full M1/M2 acceptance, ordinary-input equivalence and human calibration remain open.

## Inputs and invocation

The live backend requires:

- A real, completed, full-start schema-4/5 reference declaring `native-engine-capture` provenance, `owned-pre-command` input and `fixed-scheduler-240` clocks. Its entire declared input plan must have executed. A declared origin is not independent authentication.
- The exact plain level bytes, game executable and packaged adapter DLL named by that reference. The backend rejects differing hashes. Current sandbox preparation supports the pinned Windows x64 / GD 2.2081 / Geode 5.8.2 installation.
- An AXIOM checkout containing the PowerShell worker scripts and an ordinary `.tools` directory. Pass `--workspace` explicitly, including when Python was installed from a wheel.
- A fresh output directory below that checkout, outside the source exchange. Its ordinary parent must already exist. Existing evidence is preserved; there is no implicit resume or replacement.

The paths below stand for existing local native artifacts; they are not shipped examples. Replace the game/package paths with the installed pinned game and the package matching the reference DLL hash. The public synthetic reference under `examples/probes` is deliberately refused by this live backend.

A small `reports/native/full-start-reference/probe-spec.json` can probe the first planned event:

```json
{
  "schema_version": 1,
  "kind": "native_probe_spec",
  "id": "native-first-event-grid",
  "axes": [{"event_index": 0, "offsets_commands": [-1, 0, 1]}],
  "repetitions": 3,
  "run_budget": 9
}
```

From the actual AXIOM checkout, with fresh study/exchange/output paths:

```powershell
uv sync --locked --extra dev
$workspaceRoot = (Get-Location).Path
uv run --locked axiom probe-plan `
  reports/native/full-start-reference/capture.json `
  reports/native/full-start-reference/probe-spec.json `
  --json reports/native-probe-study.json
uv run --locked axiom probe-export reports/native-probe-study.json `
  --output reports/native-probe-exchange
uv run --locked axiom probe-run reports/native-probe-exchange `
  --workspace $workspaceRoot `
  --game-directory "C:\Games\Geometry Dash" `
  --native-package "C:\local-artifacts\reference-adapter\axiom.native-capture.geode" `
  --level reports/native/full-start-reference/level.txt `
  --output reports/native-probe-run-01 `
  --timeout-seconds 90 --max-jobs 3
```

The first three scheduled jobs above are baseline repetitions. `--max-jobs 3` intentionally leaves later grid jobs unattempted; it does not establish a complete grid. Invalid shifted schedules have no job and never become native deaths. Offsets remain integer `processCommands` call indices, not physical milliseconds.

| Option | Behavior |
|---|---|
| `--timeout-seconds` | Integer 30–600; default 90. The worker owns the game/export deadline. Preparation and cleanup can add time. |
| `--max-jobs` | Integer 1–4096, capped at scheduled job count. Default: all scheduled jobs. An intentional partial budget preserves missing repetitions. |
| `--keep-going` | Continue after execution/capture errors. Failed jobs are not retried. Cancellation and input-integrity checks still apply. |

The live worker copies at most 1 MiB of plain level data and 16 MiB per replay/capture. Local-drive paths and ordinary files/ancestors are required; traversal, alternate streams and redirected input paths are refused. These are current implementation bounds.

## Execution and ownership

`axiom.probejobs.load_probe_exchange` reconstructs the full study and every generated job in exact order. The exchange contains only `jobs.json`, `study.json` and unique scheduled `plans/pNNNN.json` files. Canonical replay bytes include sorted compact UTF-8 JSON and one final LF. Study-file SHA-256, canonical study SHA-256 and replay-file hashes remain distinct.

The executor copies those exact exchange bytes into its new output directory and validates the snapshot. Both the original and retained exchange inventories are checked before each attempt and after scheduling ends. Game/package/level/worker inputs have a separate byte-hash inventory; the exact level is retained locally. These checks detect changes at the declared boundaries and do not lock all input files for the whole campaign.

For each job the backend writes `request.json` and starts a separate PowerShell worker. The worker:

1. Acquires an exclusive lease for the shared isolated `%LOCALAPPDATA%\AXIOMSandbox` profile. An existing sandbox process or another lease owner causes refusal.
2. Snapshots four experiment files before preparation and creates a new runtime under checkout `.tools`. The profile is shared between jobs under the lease; it is not recreated per job.
3. Copies the exact level and replay, checks prepared hashes and starts `AXIOMSandbox.exe` with the explicit full-start replay, owned-input and fixed-Scheduler flags.
4. Creates the game suspended, assigns it to the owned Windows Job Object before resuming, and keeps its process handle. The worker does not kill processes selected by name or a reused PID.
5. Waits for one new stable capture within its game deadline, copies its bytes, then closes the export interval through owned cleanup. A second export, changed source capture or changed pre-existing capture invalidates the result.
6. Records exit state before cleanup separately from requested termination; terminates its owned game and Job, waits up to 30 seconds for the Job's active process count to reach zero, including descendants, then closes the Job. It restores/verifies each experiment file independently before releasing the profile lease. Drain failure remains an explicit cleanup error.

The four files are runtime `fixture-level.txt`, profile `axiom.native-capture/replay.json`, profile `axiom.native-capture/settings.json` and profile `geode.loader/settings.json`. Restoration preserves bytes and prior absence. Failure on one file does not suppress attempts on the remaining files. Any cleanup/preservation failure becomes an execution error. This scope is four experiment files, not a backup of every save or machine setting.

The worker supplies scheduled in-game input, with no Windows/device-input injection. Native death is a valid terminal observation; process exit, timeout, cancellation, missing capture and cleanup failure do not become deaths or completions.

## Cancellation and retained outputs

Ctrl+C during the native worker wait requests cooperative cancellation through attempt-local `cancel.request.json`. Python keeps waiting while the worker runs its owned cleanup and restoration. It does not force-kill the PowerShell worker before `finally`. If signaling fails, the worker's game deadline remains the backstop. Ctrl+C between jobs can interrupt file publication: only already-published checkpoints are guaranteed, not a new final report. The generic synchronous Python `CaptureBackend.run` or synthetic callback interface has no automatic deadline for arbitrary callback code.

The output contains:

| Path | Purpose |
|---|---|
| `exchange/` | Frozen source exchange bytes and their file inventory |
| `backend-inputs.json`, `level.txt` | Live backend input hashes and exact retained level, when preparation reaches publication |
| `attempts/<trial_id>/request.json` | Hash-bound worker request |
| `attempts/<trial_id>/attempt.json` | Worker capture descriptor/error, timeout, exit-before-cleanup and four preservation records |
| `attempts/<trial_id>/capture.json` | Unchanged retained capture, when one was copied; retention alone does not mean acceptance |
| `attempts/<trial_id>/executor-observation.json` | Capture validation or explicit execution error |
| `attempts/<trial_id>/*.stdout.txt`, `*.stderr.txt` | Separate worker/game console evidence |
| `check-NNNN.json` | Per-capture importer manifest |
| `results-NNNN.json` | Fresh cumulative checkpoint after each attempted job |
| `results.json` | Final `native_probe_results` manifest, including a partial batch |
| `map.json` | Discrete repeated-sample map, when construction succeeds |
| `executor.json` | Scheduling, errors, counts, artifact hashes and execution scope |

Python checkpoints use atomic no-replacement publication. Exceptions, malformed captures, reused capture hashes/attempt IDs and mismatching reference identities remain errors or rejections. Unattempted jobs stay missing. A backend preparation failure after the exchange snapshot retains `preflight_error`, all-missing results/map and an execution report, without calling any job. A final map-construction failure still preserves `executor.json` with `map_path=null`, `map_sha256=null` and an explicit `map_error`.

Launch accounting is evidence-qualified: `native_launch_attempts` is a confirmed lower bound; `native_launch_uncertain_attempts` counts worker invocations without valid final launch metadata. `new_native_execution` is `true` if any launch is confirmed, `null` if no launch is confirmed and an unresolved invocation remains, and otherwise `false`. A lost worker result cannot establish that the game never ran.

The CLI returns `0` after an error-free batch or intentional job budget, `2` for execution/capture/preflight/integrity/map errors, and `130` when final `stop_reason` is `cancelled`. `--keep-going` does not turn a batch containing errors into exit `0`. Earlier checkpoints remain available if a later publication fails.

## Software checks and remaining qualification

```powershell
uv run --locked pytest tests/test_probejobs.py tests/test_nativeprobe.py tests/test_probeadapter.py tests/test_probes.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/test-native-probe-process.ps1
uv run --locked ruff check .
uv run --locked ruff format --check .
```

The Windows process checks run real console processes and filesystem-only preservation cases. Capture-producing backend tests use explicitly synthetic capture fixtures. This engineering increment includes no live GD execution or measured physical timing windows. A native campaign must still qualify full-start repeatability, controls, delayed failures and supported configurations. Discrete samples do not close M1/M2 or establish human timing probabilities, impossibility or real-level AR.
