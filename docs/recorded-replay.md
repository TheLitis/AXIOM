# Recorded cadence and processing-entry replay

[Русская версия](recorded-replay.ru.md) · [Native adapter](native-adapter.md) · [Source input observations](input-observation.md) · [Roadmap](roadmap.md)

**The bounded bridge passed on 11 October 2026.** Three fresh schema-6 owned replays completed at source command 4894, matched the source on all 13 declared checks and agreed with one another on all 18 repeat components. The original schema-5 source and historical comparisons remain unchanged; the preceding rejected export is retained below.

The bridge deliberately forwards recorded Scheduler arguments and delivers synthetic `handleButton` requests at a native queued-processor entry. It does not replay Windows events, recreate UI key/touch entry or authenticate the operator or device. Reproducing recorded arguments is an explicit intervention; it is not an untouched native-clock replay or a fixed-frequency experiment.

## Immutable source

The selected source is the [schema-5 input observation](input-observation.md#native-clock-observation-11-october-2026), capture SHA-256 `a8721c3d671f9cdb2b75d7567b0fbaf2a32421cbbc30f298577bd2cb40460da7`, compiled collector commit `638ee55244eb1801ad7ab51e474b2e136bfdfdb7`. Its exact level hash is `8cbaa9dbdbdc8dabf3ac2aabc469eef83444261ebcac7b323d52a4b8b873e157`; native-clock environment hash is `393a2b8555222c944b1fce823b8472c29a40c8d9a43b492b95be032318b07592`.

| Recorded source quantity | Value |
|---|---:|
| Native completion command | 4894 |
| Ordered actual input receipts | 106: 53 requested, 26 push, 27 release |
| Queued-processor intervals enclosing those receipts | 51 |
| Scheduler rows / gameplay-update rows | 5132 / 5130 |
| Distinct original Scheduler arguments | 93; each equals its delivered argument |
| Key / touch entry observations | 46 / 10 |

Source input source/provenance remain `unknown`, with driver `none`. Its initial release is retained; only the 53 requested rows become planned requests, not all 106 receipts. The 12 actual P1 player receipts associated with raw P2 queue/request labels remain separate observations. The bridge must preserve requested channel labels and measure the resulting actor; it must not rewrite labels to manufacture P2 execution. S entries appended no command and remain source entry evidence.

The cadence includes startup and ending calls without command advancement: command 1 occurs within Scheduler sequence 244, and completion within sequence 5131. Initial unknown memberships and the terminal's null gameplay-update membership remain recorded values. No command index or callback argument is relabelled a render frame, continuous input window or independently measured physical time.

## Plan and native contract

The new plan has `schema_version: 2`, `kind: native_recorded_replay` and `clock: recorded_scheduler_stream`. Legacy schema-1 `native_replay` schedules retain their previous meaning.

| Plan field | Required meaning |
|---|---|
| `level_sha256` | Exact source and target level bytes |
| `source_capture_sha256`, `source_environment_sha256` | Immutable source provenance |
| `environment_sha256`, `target_collector` | Explicit target intervention environment and compiled collector identity; not the source environment |
| `scheduler_updates` | Full contiguous zero-based sequence, `delivered_dt_seconds`, command before/after span, update count and before/after phase |
| `processing_batches` | Source delivery sequence, command/update/Scheduler membership, processor `dt_seconds` and `clear_input_queue`, ordered requested inputs |
| `inputs` | Exact flattened batch requests: command, player, button and pressed; 53 for this source |

Each batch input retains `source_input_sequence`; each batch retains `source_delivery_sequence`. The selected source produces 5132 cadence rows and 51 batches. Native float arguments must round-trip exactly through float32. Bounds remain 20000 Scheduler/update rows, 4096 batches and 4000 planned requests; nested or unplaceable source contexts cannot be silently approximated.

The guarded `owned-processing-entry` driver calls the original `handleButton` once per scheduled request at the **first actual `processQueuedButtons` entry for the scheduled command**, before its original call. Its declared injection phase is `GJBaseGameLayer::processQueuedButtons-entry-before-original`. It checks command/update/Scheduler grouping, processor arguments and ordering; the context must match at that first entry, with no later-match rescue. Non-injector requests remain blocked diagnostics. Missing, duplicated or mismatched placement, incomplete cadence/batch consumption and identity changes cannot establish the bridge.

A separate interference gate allows zero blocked requests, or at most one suppressed command-1/P1/button-1 release with a raw native queue row containing step 0/timestamp 0 and a recorded processor-interval enclosure witness. Every additional or ambiguous unowned request fails that gate; all original rows remain retained and origin is not authenticated. Existing same-route comparisons still report blocked requests as diagnostics. No position correction, checkpoint restore or synthetic extra native processing call is part of this contract.

Clock policy `recorded-scheduler-stream` supplies the recorded arguments to `CCScheduler::update`, declared with intervention hook `CCScheduler::update` and step `0/1`; that step does not describe a constant timestep. Original incoming arguments and wall timing remain observable. Delivered cadence, grouping and phases must match the retained plan through the native terminal boundary.

Only this new mode uses `native_capture` schema **6**, with the complete plan in `attempt.replay_bridge`. Existing observation and legacy replay modes retain schema 5; historical schemas 1–5 keep strict readers and absent fields. Replay receipts have synthetic scheduled provenance even though their source is an unknown-origin observation.

## Separate comparison gates

Qualification requires an exact source/plan identity check, a fresh target-identity baseline, three distinct full-start replay captures and complete integrity through actual native completion. Each replay must consume the complete cadence and request batches. The target baseline identifies the current package/configuration; it is not another attempt to reproduce source input.

Projection `recorded-source-to-owned-processing-scheduler-v1` compares these complete ordered streams:

| Compared stream | Retained comparison scope |
|---|---|
| Requested / player receipts, separately | Sequence, command, channel/actor, button, direction, phase, native return and command/update/Scheduler membership |
| Queued-processor entries | Native event, nesting, membership, arguments, phases and return; route-specific delivery ordinal, queue snapshots and layer timestamps are excluded |
| Selected trajectory | Command index, recorded player/layer state and watched objects |
| Command arguments / context | `dt_seconds`, half/last-tick flags, phase and update/Scheduler membership |
| Delivered gameplay / Scheduler records | Complete delivered arguments, grouping and phases; original incoming arguments excluded |
| Native phase events / mechanics / terminal | Normalized ordered events and complete terminal fields except elapsed wall time |

Those eleven stream-equality checks plus absence of replay UI entry and the interference gate form the 13 source checks. Normalization excludes receipt source labels and wall timing, and normalized event signatures exclude runtime object IDs; original incoming arguments, absolute timestamps and source UI/queue streams remain diagnostics. The replay-to-replay gate separately compares three fresh captures on the existing 18-component contract under their common plan/environment. Preserve every failed attempt and first difference; agreement among repeats cannot override disagreement with the source. Neither gate establishes full UI/OS delivery equality.

All outcomes, native ending/completion boundaries, selected state, actual request/player phases and the P1/P2 actor distinction remain assessable. Successful file validation or a comparator exit code alone does not establish either gate. The ledger below records the measured statuses, identities and audit hashes.

## Reproduction

Use the pinned native build and exact local source/level files. The runner preserves evidence and creates a fresh target baseline plus three fresh owned processes:

```powershell
uv sync --locked --extra dev
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-native.ps1 -Jobs 4
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-native-recorded-replay.ps1 -GameDirectory 'C:\path\to\Geometry Dash' -SourceCapturePath 'C:\local-evidence\source-capture.json' -LevelPath 'C:\local-evidence\fixture-level.txt'
```

Optional `-RuntimeDirectory` must be a fresh directory under the workspace's `.tools`; `-OutputDirectory` must be a fresh directory within the workspace. The runner rejects active unrelated sandbox processes, freezes source/level/package/analysis/plan hashes, retains unsuccessful exports and restores the four experiment files' original existence and bytes. Its temporary system/display execution-state request is restored separately. Captures and proprietary game files remain outside Git.

The offline commands construct and compare supplied evidence; neither launches nor authenticates a game:

```powershell
axiom native-replay-plan 'C:\local-evidence\source-capture.json' 'C:\local-evidence\target-baseline.json' --json .\reports\native\replay-plan.json
axiom native-recorded-compare 'C:\local-evidence\source-capture.json' .\reports\native\replay-plan.json 'C:\local-evidence\replay-1.json' 'C:\local-evidence\replay-2.json' 'C:\local-evidence\replay-3.json' --json .\reports\native\recorded-comparison.json
```

## Qualification ledger

The confirming experiment ran at **2026-10-11 02:17:16.6337018–02:19:17.9066721 UTC**, with status `recorded_source_subset_and_repeats_consistent`.

| Measured gate | Result |
|---|---|
| Fresh target baseline | Schema 5, completed command 4893, two initial-release receipts, no UI entries; identifies the target and is not pooled with source correspondence |
| Three fresh replays | Schema 6, all completed command 4894; trace 0–4894 and all 106 actual receipts matched the source projection |
| Source / repeat gates | 13/13 source checks per replay; 18/18 repeat components, two comparisons relative to the first of three attempts |
| Cadence / placement | All 5132 Scheduler rows, 5130 gameplay rows and 51 processor contexts exact per replay |
| Interference / preservation | One witnessed suppressed initial release per replay, no other blocked requests or replay UI entries; all four original existence/byte records preserved |

The source's 12 P1 player receipts following P2-labelled requests were reproduced without changing either label. Complete delivery streams differ (107 source rows versus 51 replay processor rows), as do absolute native timestamps and incoming Scheduler arguments; these diagnostics remain retained.

The **preceding experiment**, at 02:15:17.6535996–02:15:49.1894306 UTC, remains `recorded_replay_not_established`: its valid native baseline completed command 4893 with 188 actual receipts and 199 delivery rows, including 88 keyboard and 24 touch entries. Export correctly rejected it with exit 2 (`Target baseline must have no recorded UI entries or pressed input receipts`); no plan/replay was produced, and all four files were preserved.

The compiled target collector commit is `7781df6d2f4c4aad5bd95f13c952ce6f8681c0d0`; evaluator commit is `9a6e2996a94f0b15e4275ca8de51204fd5faac66`. Native tree SHA-256 is `bdc803b009036cafa7ff53099f0acba7b7b3dbbafe5659c12a611f53e7123fe7`, package `56eb31f1d96001420f9275708b8404988d409b12cb2414e14f329425966084b7`, loaded DLL `4428b76326c744dd320bae1917b37a4616e1aba6a9097f863e7748d8564185c4`. Source identities above remain unchanged; the target native-baseline environment is `b13a3824b66d8412235c49ea1bdee3e01847ad2b05d40192d6b081652eb96cd2`, recorded-intervention environment `088076e01e625bc92b35da99d2b9512c34a481ca413471b00875d45a1be8af06`. SDK/bindings remain pinned; the allowed collector transition changes only source commit/tree.

| Retained artifact | SHA-256 |
|---|---|
| Confirming manifest | `8139c2a3e8f9f94e62d6eeab328dc5cda5e41a9819d6968279f41ce49e4dfe80` |
| Recorded plan | `8063a76b4c507d35ae1973e6ebfb4760510dc9b017e6bc0b4fbf47d9ab669364` |
| Source/repeat comparison | `4fc577471aea8fe6c150d26df6ca2e8ef0d59b8c961b5de9085e83d58e5fc1be` |
| Confirming preservation | `81ce7d9ba6f9cc430ee0b88b237cbe2967add1e2e940b35e8cb74d2b1081ff07` |
| Confirming audit: 200 checks, zero discrepancies | `9aec7e11937be3a809130486e34cbd0f7493d5eb186ec5bd2f77fc6fc716edd8` |
| Earlier rejected manifest | `a9ed2569d97ed38e39bf7b4eb869ba68e7050efe65470e157b3f6f171a9e3735` |
| Earlier preservation | `dfd8c7db6b3a9695fbcd67fdaced008bfa028be64dec56f7fe72e431e1b93039` |
| Earlier audit: 123 checks, zero discrepancies | `1d7d3a8a6cd201dc675d8af9b59929476b345013744054a2400d11dfbc33299b` |

Same-host independent audits recomputed raw JSON with standard-library helpers without AXIOM APIs and checked saved preservation records. Confirming helper SHA-256 is `e58e3300bf215234e92d81a12f04dabd232595981ce79ba44f764413be63b63a`; its report-key correction and original negative-audit helper remain retained. Artifact checks are separate from **727 software tests plus 83 subtests**, Ruff checks on 57 files and the successful native build. Raw captures remain local, outside Git.

The pinned [GD 2.2081 bindings](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/GeometryDash.bro#L7520-L7592) declare the input and queue-processing functions. API declarations and same-host artifact recomputation do not independently authenticate execution. This bounded bridge cannot establish complete engine state, ordinary-input equivalence, all classic mechanics, full M1 completion, human calibration or AR.
