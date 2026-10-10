# Native collisions, trigger effects and synthetic UI delivery

[Русская версия](native-interactions.ru.md) · [mechanics checkpoint](native-mechanics-matrix.md) · [adapter contract](native-adapter.md)

This stage studies selected collision/contact state, changes to explicitly watched objects and a bounded in-engine input-delivery path. Native capture schema **4**, fixture catalogue schema **3** and the separate [delivery comparator](../src/axiom/equivalence.py) describe different contracts. They do not establish complete collision geometry, general trigger semantics, ordinary OS-input equivalence or human Axiom Rating.

## Audited interactions and recorded delivery disagreement

**The source-frozen interaction matrix, six paired variant results and confirming scheduled-UI study have been recorded and audited.** All 12 cross-route comparisons disagree on complete actual input receipts, although their six selected dynamics projections and scheduled queue-path checks agree. The audits independently recompute selected artifacts on the same host; they do not authenticate external engine execution. Manual-input qualification is not established. Construction probes and retained harness failures remain separate from the completed studies.

| Recorded domain | Result and count |
|---|---|
| Confirming matrix | 12 constructed cases, 48 valid full-start schema-4 attempts: 12 observed baselines and 36 owned replays; 32 completed and 16 died, as declared |
| Whole-trace repeats | 12 reports, each covering three replay attempts and two first-replay-relative rows: **24 comparison rows**, with all 18 components exact in every case |
| Controlled variants | All six declared pairs have `declared_variant_effect_observed`; six checks per pair, **36 study checks**; the pairs reuse the matrix's first owned replays |
| Artifact audit | All 48 captures verified; each of the six variant pairs also checked at all three repetitions: **18 offline pair comparisons**, no additional native runs |
| Preservation | All four experiment files restored by bytes and existence after the confirming matrix |
| Scheduled UI | 12 fresh native attempts across four cases: nine completed and three died; four same-route repeat reports / eight comparison rows, all 18 components exact |
| Cross-route delivery | 12 negative full-receipt verdicts against four reused owned-reference captures; six dynamics projections and the scheduled queue witness agree in all 12 |
| User-operated observation | Two separate 300-second menu timeouts, no captures or native attempts; no human-input qualification |

The matrix at `reports/native/interactions-confirmed-95d961d0a3cc452eba4f7b3b65b40cb1/` recorded status `declared_matrix_recorded_subset_passed` at `2026-10-10T22:46:41.7373194Z`. Its `matrix-result.json` SHA-256 is `73e4db79bbb2e36e8bb76b5cef32446b60965e53373ccd53b2f3ef6b1317f66a`. Its `state-preservation.json` SHA-256 is `97b1a57b714910ad5bacd5b695cf1b4afc187c5b77326957a568ab510568b843`. The case gates and whole-trace comparison reports are recorded results; they do not establish unrecorded state determinism or M1 completion.

The offline variant result at `reports/native/variants-confirmed-94ceb3cfd98d44e69473a113e65c821d/variant-result.json` recorded status `declared_variant_study_recorded_subset_passed` at `2026-10-10T22:47:20.8224443Z`; its SHA-256 is `e28000687e91728d7a0e728528c4ac8da38a2f4e822444cfdc245d67432b7eec`. This study launches no additional native attempts. Both manifests retain analysis commit `61197c6b0bc5cd550a9cedde638a8b3423306706` and evaluator file hashes, distinct from the compiled collector identity.

The same-host independent recomputation report is `reports/audit-native-interactions-confirming-result-95d961d0.json`, SHA-256 `8a6ef72199bc43b27d350a927dcc55b6db537dd40bf6c5ab182676537cdc309f`; its audit script `reports/audit-native-interactions-confirming.py` has SHA-256 `90fb4c1264102e971e1caf15881d8f94e936570047e5503ad8b3395ae31be0a7`. It records zero failures and reproduces capture integrity, identities, declared effects, whole-trace reports and all 18 offline variant comparisons. **All 24 raw absolute-delivery-timestamp diagnostic comparisons differ**, while the 18 declared comparison components agree. This supports `native-delivery-context-v1`'s bounded scope, not strict equality of absolute timestamps, external replication or complete-state determinism.

| Identity retained for the recorded matrix | Value |
|---|---|
| Compiled collector source commit | `3a868abbb05f6aab82c71cd3ab14a60b215c25b6` |
| Compiled native source-tree SHA-256 | `2cfecee375dd3deb8559ad100f28ec71e96287c3eff92ff065e3ff60f460bd0e` |
| Collector package SHA-256 | `6fe5811d98cf352eead0bc2d0dcee6acbb70914419c09eaee9376d5e5b7fe3b5` |
| Loaded collector DLL SHA-256 | `25b1f003f1f06294103be3125bd99a9c5e0248eef73c6d57814ac5c8fac268d6` |
| Environment SHA-256 | `c9627faa41f9431c7b2f7d29dae357dfd6c0a8d80afbfda060c7553755ee6d07` |
| Exact source interaction-matrix bytes SHA-256 | `52bc9c59219365d9e317de3b4f1dd4a29d365ca2bd365441c5484091c84885ec` |
| Serialized validated matrix SHA-256 | `976a3848ad705d84fa4c66afdbe21c55b11ebb000c1cc0caac6ae28a559ab2c9` |
| Exact interaction-variants bytes SHA-256 | `89bf348c6004fec3ad62c2653231b5f47c13f120011a1a7c39f7ea0957653479` |
| Effective clock/input domain | `fixed-scheduler-240` / `process-commands-scheduled-delivery-v2` |

## Confirming synthetic UI delivery result

The fresh study at `reports/native/delivery-confirmed-7d21f896afc04865ae736e276ead89de/delivery-result.json` recorded `declared_delivery_study_recorded` at `2026-10-10T22:53:30.1973193Z`; its SHA-256 is `f3c602387b9fa9fc4ef6be1f6748b7066048155f986714e477d2c2492e13b7a2`. This means the declared comparisons were recorded, not that equivalence passed. Its evaluator commit is `d5b1245bafa15fc45769c6e251f3a75bb4af7611`, distinct from matrix evaluator `61197c6b0bc5cd550a9cedde638a8b3423306706` and the compiled collector. The collector package, loaded DLL and native source-tree hashes remain those in the identity table above.

The study recorded three fresh scheduled-UI attempts for each of `raised-platform-positive`, `raised-platform-control`, `ceiling-contact-positive` and `ceiling-contact-control`: **12 new native captures**, nine completed and three died. It reused the matching matrix's first owned replay for each case as four byte-identical references; copying those references creates no new native attempts. The other eight catalogue cases have empty input plans and are explicitly excluded by `requires_nonempty_P1_button1_plan`. They supply no UI-delivery coverage.

| Cross-route check | Recorded equal / witnessed results out of 12 |
|---|---|
| Complete actual `native_input_receipts_equal` | **0 / 12** |
| Complete `process_commands_trace_equal` | 12 / 12 |
| `delivered_updates_equal` | 12 / 12 |
| `delivered_scheduler_updates_equal` | 12 / 12 |
| `native_ending_phase_events_equal` | 12 / 12 |
| `selected_mechanic_events_equal` | 12 / 12 |
| `terminal_snapshot_equal` | 12 / 12 |
| `ui_plan_queue_path_witnessed` | 12 / 12 |

All 12 comparison statuses are **`recorded_delivery_equivalence_not_established`**. Each UI capture retains six actual input-receipt rows against four in its owned reference: the additional command-1 P1 release request and player callback remain visible, with unknown origin. Both planned edges still have native UI→queue→processor→actual-input→player-callback evidence. The independent audit reconstructed **all 24 planned delivery chains** using raw within-attempt timestamps and native contexts. Matching selected dynamics does not erase the additional delivered input or establish ordinary input equivalence.

The four same-route UI repeat reports each cover three attempts and two first-attempt-relative rows: **eight comparison rows**, all 18 declared components exact. All eight raw absolute-timestamp diagnostics differ. These repeats use `native-delivery-context-v1`; they do not assert absolute timestamp equality.

The same-host independent audit is `reports/audit-native-delivery-confirming-result-7d21f896.json`, SHA-256 `e9db5705973a706953c2a5a3b7825361e9d881ddbb1d641de3705609cfa0c89a`; script `reports/audit-native-delivery-confirming.py` has SHA-256 `f8d39291485053d7db18ad48d900eaecdc6bcb09d5b9e52242812dd69e070e95`. It records zero failures, verifies the 12 new captures and four borrowed references, the frozen evaluator, all negative comparisons, repeated results and preservation, and verifies the records of 33 successful CLI invocations. Reader/comparator outputs are recomputed through their Python functions. This is independent offline recomputation on the same host, not external replication or engine-origin authentication.

All four experiment files were restored by bytes and existence; `state-preservation.json` SHA-256 is `f7c44cb0ac809135905547483d3ad36b946a625dd8b4bd91ff7cc0f3b3d612fa`. The temporary Windows system/display execution-state request was restored. Authentication, human authorship and ordinary OS-input equivalence remain unestablished.

## Development and retained failed attempts

The retained development directory is `reports/native/interaction-probes-f70221d06ae64c4b9be0fabc1cb5b2f2/`. A raised-platform capture completed and sampled P1 at command 219 with `y: 135`, `is_on_ground: true`, `is_on_slope: false`; its flush-platform control also completed. Slope captures supplied selected contact observations. The low-ceiling attempt died at command 150, while its high-ceiling control completed at command 734. The toggle-positive attempt completed, while its control died at command 217. These are development observations under their recorded identities, not final repeat or paired-control verdicts.

The moving-wall positive completed, but its control was **aborted by pause at command 0**. That control establishes neither the hypothesized wall death nor a completed contrast. The failed run remains retained. The initial scheduled-UI probe was also rejected by a guard. Subsequent development captures in `reports/native/interaction-probes-5ddd0f4efdf046379ccf45a4175b46c4/` supplied valid attempts for all six construction pairs; those exploratory attempts still do not establish the final confirming matrix.

Development also exposed two limits retained in the contract. Ceiling attribution comes from the parent watched `collidedWithObject` receipt, with `native_return: true` and `is_dead: false → true`; its nested `destroyPlayer` receipt has a **null object argument**. The synthetic UI route forwards an unsolicited initial P1 release at command 1 that the owned route suppresses. Selected dynamics and the scheduled queue path can agree while the complete delivered receipt streams disagree. The confirming UI study reproduced this disagreement in all 12 cross-route comparisons.

The first confirming attempt is retained at `reports/native/interactions-confirmed-ff2352d776d947bcac4d2033aafd3b81/`. It exported **33 valid schema-4 captures**: eight full cases with three exact replay repetitions each, plus the moving-wall positive baseline. The series then failed because its owned process did not exit within the **five-second cleanup deadline**. There is no final `matrix-result.json`; those captures do not constitute a passed complete matrix. All four experiment files were restored by bytes and existence. The separate completed 48-capture series used signed harness commit `61197c6b0bc5cd550a9cedde638a8b3423306706`, a 30-second exit wait and process-handle disposal, with no engine/schema/example change. The incomplete series is not pooled into its counts.

The first confirming UI preflight is retained at `reports/native/delivery-confirmed-1eb8fe917f06443493bb3738a5a17105/`. Windows PowerShell 5.1 supplied a null CLI-process `ExitCode` property despite a valid CLI output file. The wrapper recorded `delivery_study_incomplete` before preparation, game launch or input delivery; it recorded no native attempts. Its `delivery-result.json` SHA-256 is `901045c64e9f4206375a9d1bbf2f2aa4c9e6ef0db0c3fd41f5bf1077c7bd55c0`. A harness-only process-status correction preceded the separate completed UI study; no result is inferred from the failed preflight.

The user-operated attempt at `reports/native/manual-input-c1178eb947fb4e09bb6fa651dd5be011/` timed out after **300 seconds** while the menu waited for **Start AXIOM Test**. No start action or capture was recorded. All four experiment files were restored. No completed manual-input qualification or user-authorship statement follows from that timeout.

The separate fresh window at `reports/native/manual-input-ceb33822436641a884d7cab8cf3fa02f/` launched at `2026-10-10T22:54:24.3285780Z` and reached menu readiness at `2026-10-10T22:54:28Z`. It also timed out after **300 seconds**, exiting with code 1. No **Start AXIOM Test** action, capture, inspection or `manual-result.json` was recorded; this adds no native attempt. It used evaluator `d5b1245bafa15fc45769c6e251f3a75bb4af7611` and the same collector package as the completed UI study. All four experiment files were restored; its `state-preservation.json` SHA-256 is `0b0f81dddb8e91690605c2d2f38bd00645f4a7531ca91eac19bbbcea0205359b`. No user completion statement was received. The two menu timeouts remain separate from the 48 matrix and 12 UI captures; manual/human-input qualification remains open.

## What schema 4 records

The [native reader](../src/axiom/native.py) retains the earlier selected player/layer fields and adds:

| Observation | Recorded scope | Limit |
|---|---|---|
| `is_on_ground`, `is_on_slope` | Raw PlayerObject booleans, jointly sampled with position, Y velocity, mode, gravity, size and speed | They do not identify a contacted object or reconstruct a collider |
| `object_watches` | Declared group selector, object ID and runtime UID | Runtime UID is diagnostic; stable selector identity is the declared group |
| `watched_objects` | Each selected object's raw X/Y, `is_group_disabled` and `is_disabled`, on trace rows and at terminal | Group state and object-disable state are different fields, neither an exhaustive collision-enabled predicate |
| `mechanic_events` | Selected paired native callbacks with arguments, actor/object identity, before/after player and watched states, phases and call contexts | Callback entry/return alone proves no applied effect |
| `delivery_events` | Selected UI and queued-button-processing callbacks, native queue snapshots and layer timestamps | The observed entry path does not authenticate an OS/device origin |
| `input_delivery` | Declared driver, provenance, entry point, injection phase and timestamp policy | Scheduled intent is distinct from the origin of every observed receipt |

Watch configuration is bounded to **eight unique group IDs**, each resolving to **exactly one actual native object** that declares the group. Missing, duplicate or ambiguous resolution fails capture. The collector retains those object references for the attempt. A platform containing five watched blocks therefore needs five different selectors; sharing one group across the platform is invalid.

Selected collision events cover declared watched object pointers; the death receipt also retains the actual object supplied to `PlayLayer::destroyPlayer`. Event streams retain entry/return nesting, command index, `in_command`, update/Scheduler membership and native phase. A void original's return is represented by `native_return: null`, without an invented success boolean. The streams are bounded; exceeding a limit cannot qualify as a complete recording.

Supported fixture effect hooks include `PlayerObject::collidedWithObject`, `PlayerObject::updateCollide`, `PlayerObject::collidedWithSlopeInternal`, `PlayLayer::destroyPlayer`, `GJBaseGameLayer::triggerMoveCommand`, `GJBaseGameLayer::toggleGroup`, `GJBaseGameLayer::toggleGroupTriggered` and `GJBaseGameLayer::spawnGroup`. Development showed that object 1049 invokes the direct `toggleGroup(int,bool)` binding; the proposed `toggleGroupTriggered` hook supplied no receipt for these fixtures and must not be counted as observed coverage. Other recorded trigger receipts can remain context without satisfying a declared effect gate. A broadphase call, candidate-object list or unsuccessful collision invocation supplies no contact proof.

Mechanic payload `dt_seconds` retains the pinned binding's **raw helper argument**. In measured slope callbacks it is `0.25`, while the fixed Scheduler receives float32 `1/240`. The field name does not establish SI seconds for a collision helper. Raw values and call order remain exact evidence; helper arguments and command windows cannot be converted into verified physical duration or continuous input windows.

## Catalogue acceptance contract

The [fixture validator](../src/axiom/fixtures.py) keeps exact level hashes, full-start/input-plan/native-receipt checks, explicit terminal outcomes and the earlier mode/mechanics sequences. Catalogue schema 3 adds `watch_groups`, `required_state_witnesses` and `required_effect_checks`. It requires native schema-4 availability for those new observations.

A **state witness** declares an actor, mode, command window, minimum sample count and joint predicates. At least one contact flag must be specified. All predicates distinct from `null` must match in the **same sampled row**; `false` and numeric zero remain requirements. Y can use an explicitly declared inclusive range; other numeric predicates retain exact values. Both native ending flags must be false. P2 witnesses additionally require sampled active dual and an available P2. These witnesses establish selected raw state in a declared interval, not continuous contact or a complete collision model.

An **effect check** declares a selected callback, command window and required count, plus a meaningful exact before→after change:

| Effect type | Mandatory evidence |
|---|---|
| Collision/contact | Identified P1/P2, a declared watched object and a changed selected player field across the paired native original; `collidedWithObject` additionally requires actual `native_return: true` |
| Death | Identified actor, declared watched object and `is_dead` changing to `true` across `destroyPlayer` |
| Group/object effect | The callback's actual target-group argument matches the declared watched target, its before value matches, and its requested after value is observed |

Each effect's before/after native phase must precede ending. Actor effects require available before/after actor samples; P2 requires active dual on both sides. Supported player changes are contact flags, death, Y or Y velocity. Watched changes are X/Y, group-disable or object-disable state. An unchanged value is invalid as an effect requirement. A state witness and an event-change requirement are separate checks; their presence alone does not imply they occurred simultaneously.

For a group effect, the after value can be observed at the paired original return or in a **strictly later command sample**, within the declared window and before ending. A same-counter trace row cannot establish that it followed the callback: trace rows have no wall timestamp. The report names `paired_native_callback` or `later_pre_ending_command_sample` and preserves the actual command/update/Scheduler contexts. Later command order does not establish isolated causal attribution or exclude intervening callbacks.

A spawn to group 202 cannot itself satisfy a target-change declaration for wall group 101. Its remote child toggle can satisfy the wall effect; the spawn dispatch and recorded nesting remain separate chain context. General delayed scheduling, remapping, loops and all child effects are outside this bounded contract.

A null death object remains null in the evidence. The ceiling fixture therefore uses the watched parent collision's successful native return and paired death-state change as its identified effect. The nested death callback records the native call but does not independently identify a ceiling object.

## Controlled constructions

The public [interaction matrix](../examples/native/interaction-matrix.json) declares the constructed strings and requirements, while the [variant study](../examples/native/interaction-variants.json) declares their controlled raw changes and paired gates. Both specifications retain generated/unverified provenance; recorded results are separate. Raw placement uses the simple prior header and a terminal marker at X600. The ceiling plan presses P1 at command 130 and releases at 140 in both variants, so the complete plan precedes the observed development death at 150.

| Domain | Controlled variants | Evidence needed beyond a passed level |
|---|---|---|
| Raised platform | Block-1 plateau at raw Y15 versus flush Y−15; same jumping plan | Joint raised grounded state and an identified native contact/change; independent repeats for both scenes |
| Ascending slope | Object 1743 at `(240,15)`, default flips/rotation, versus flush block 1 | Selected on-slope state and native slope receipt/change; flat control does not supply slope coverage |
| Ceiling | Low tagged blocks versus the same blocks above the tested jump; same plan | Watched collision returns true and changes death state; its nested null-object death receipt is retained; high control completes |
| Toggle wall | Toggle 1049 targets the wall group versus an absent group | Actual group-state transition followed by the distinct declared player outcome |
| Move wall | Move 901 applies nonzero versus zero Y offset to the same wall | Actual sampled target displacement and a completed scene/control contrast; request arguments alone cannot pass |
| Spawn/toggle chain | Spawn 1268 targets a remote spawn-only toggle versus an absent group | Retained dispatch/child context, actual wall-state change and a completed outcome contrast |

The first owned replay of each recorded variant supplies these bounded witnesses; the other two replays remain whole-trace repetition evidence:

| Pair | Recorded selected effect/response | Positive / control native outcome |
|---|---|---|
| Raised platform | Command 219: positive Y135/grounded, control Y134.23651123046875/airborne | Both completed at 734 |
| Slope ascent | Command 170: positive `is_on_slope=true`, control false; selected Y also differs | Both completed at 734 |
| Ceiling contact | Command 150: watched collision returns true, death state changes, nested death cause stays null | Died at 150 / completed at 734 |
| Toggle wall | Command 116: direct group-101 toggle changes `is_group_disabled: false → true` across its native return | Completed at 734 / died at 217 |
| Move wall | Move callback at 116; group-101 Y105→225 witnessed at strictly later sample 179 | Completed at 734 / died at 217 |
| Spawn/toggle chain | At 151: group-202 dispatch nests the remote trigger and direct group-101 toggle; group-disable changes false→true | Completed at 734 / died at 217 |

These command indices identify recorded callback/sample order. They are not verified physical durations or continuous input windows.

## Same-plan variant contract

The separate [variant comparator](../src/axiom/interactions.py) binds a schema-1 `native_fixture_variant_study` to the **exact bytes' SHA-256** of its schema-3 fixture matrix. Both references require owned replay runs with the same complete input plan, distinct level hashes, identical watched selectors and explicit terminal outcomes. The positive run must contain an applied-effect requirement. The level headers and object counts must match, and the declared `controlled_changes` list must equal **every changed raw object property**, including an added/removed property's `null` value. Unrecorded game state is not thereby proven equal.

The study requires an initial prefix starting at command 0, before its response window. Every prefix row must contain equal selected actor fields and dual state, with an available living actor, both ending flags false and all declared mode/gravity/size/speed/dual predicates satisfied. Initial watched positions can differ where the declared construction changes them. A selected-trajectory contrast requires a common response command where both living actors remain eligible and at least one declared Y/Y-velocity/contact field differs. An explicit native-terminal contrast instead requires the two declared outcomes to differ and both terminal callbacks to lie in the response window; it does not extrapolate a common post-death trace.

Additional receipt requirements match actual callback arguments, actor/watch selectors, command windows and recorded ancestor nesting. Constant-target requirements check every eligible sample in their full declared window. For the spawn scene, a group-202 dispatch can be required as an ancestor of the remote toggle's direct group-101 effect. This records the selected nested chain, not a complete dependency graph or isolated causal proof. State transitions remain mandatory through each positive fixture's own effect checks.

The six verdict components are the positive/control fixture inspections, selected initial-prefix agreement, declared response, required callback contexts and control-target requirements. Status is `declared_variant_effect_observed` only when all six pass; otherwise it is `declared_variant_effect_not_established`. The older same-level, changed-input `fixture-response` contract remains separate.

## Whole-trace repeats and delivery context

Three repeated attempts of one variant are compared over the **whole recorded trace through its terminal**, independently of the pre-ending witness filter. Schema 4 preserves the earlier 14 components and adds:

```text
native_mechanic_events_equal      native_delivery_context_equal
recorded_watched_objects_equal   terminal_watched_objects_equal
```

Raw contact flags are part of the player-field comparison. Stable watch selectors, native mechanic-event arguments, receipt contexts and paired snapshots remain exact. Runtime object UIDs and monotonic event wall timestamps are diagnostics. Original incoming update dt remains diagnostic under a clock intervention; delivered dt and grouping remain compared. A finite successful repeat set establishes consistency of that recorded subset only.

Schema-4 repeats declare **`native-delivery-context-v1`**. Native layer `m_timestamp` has an absolute value that varies across game instances, including fixed-scheduler attempts. This explicit context projection excludes only delivery `layer_timestamp_before/after`, UI callback argument `timestamp` and queued-button `timestamp` values from the cross-run context gate. It retains event order/nesting, command/update/Scheduler context, phase, key, button/pressed/player, queue step and delivered dt. It performs no relative-time conversion. The raw absolute timestamps remain in captures and in separate exact-equality/first-difference diagnostics with signature hashes. No actual input receipt is removed or weakened by this timestamp policy; native mechanic snapshots retain their strict comparison.

## Two scheduled input routes

The capture declares `process-commands-scheduled-delivery-v2` and distinguishes these routes:

| Driver | Scheduled native entry | Actual native request handling |
|---|---|---|
| `owned-pre-command` | `GJBaseGameLayer::handleButton` before the original `processCommands` | Suppresses and records non-injector requests of unknown origin; owned request/consumption receipts use source `replay` |
| `scheduled-ui-callback` | P1 Space `UILayer::keyDown/keyUp` before the original `processCommands`, with sampled layer timestamp | Preserves the native queued-button path and forwards unknown-origin requests; actual receipts use source `observed` |
| `none` | Observation, no owned scheduled plan | Actual receipts remain observed and `input_source` remains unknown |

Both scheduled routes declare synthetic replay intent. For the UI route, that declaration does **not** establish that every observed receipt came from the schedule. Extra observed requests are retained and affect delivery comparison. Blocked owned-route diagnostics are not delivered events and cannot be used to reconstruct an ordinary-input counterfactual.

The normal repeat comparator requires the same delivery identity. The separate `native-delivery-compare OWNED.json UI.json` requires two distinct complete schema-4 full-start scheduled attempts, the same challenge/environment/collector/watch identity and the same **nonempty P1/button-1 plan**. It does not relax same-route repeat checks.

The UI gate requires each planned prefix event through terminal to have all of the following within its own capture: the scheduled Space callback uses the sampled layer timestamp; the callback appends exactly one matching queued button; a later native `processQueuedButtons` receipt removes that queued item; and a matching actual handleButton request lies inside that processor's paired wall interval with its observed native command/context. Equal command counters alone cannot substitute for the queue path.

The comparator evaluates seven complete recorded projections—native input receipts, processCommands trace, delivered updates, delivered Scheduler calls, native ending-phase events, selected mechanic events and terminal snapshot—plus the queue-path witness. It normalizes route-specific receipt source labels, runtime UIDs and monotonic wall timestamps, while keeping command placement, native contexts/results and every extra actual input receipt. Queue/layer timestamps remain exact evidence inside each attempt's queue-path witness; the same-route absolute-time context projection does not erase an extra input receipt. The raw records remain retained.

The development pair's extra command-1 P1 release makes full native input-receipt equality false. Its selected dynamics and witnessed scheduled deliveries establish narrower observations only. The overall disagreement must remain visible as `recorded_delivery_equivalence_not_established`; a filtered schedule-only stream cannot replace the recorded complete stream.

Its positive status is `recorded_delivery_subset_consistent`; a valid disagreement is `recorded_delivery_equivalence_not_established`. Neither status authenticates capture origin. **Scheduled UILayer calls bypass Windows, hardware and the keyboard dispatcher.** This is a synthetic in-engine transport study; it establishes no OS-input equivalence or human authorship. Manual input, focus, external arrival and ordinary native-clock operation remain separate gates.

## Reproduction and preservation

Use the [pinned native setup](native-adapter.md), a guarded isolated sandbox and a fresh output directory. The matrix runner's default catalogue remains the historical matrix; select the [interaction matrix](../examples/native/interaction-matrix.json) explicitly:

```powershell
uv sync --locked --extra dev
.\.venv\Scripts\python.exe -m axiom fixtures .\examples\native\interaction-matrix.json
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-native.ps1 -Jobs 4
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-native-matrix.ps1 -GameDirectory 'C:\path\to\Geometry Dash' -MatrixPath .\examples\native\interaction-matrix.json -Repetitions 3 -ClockPolicy fixed-scheduler-240
```

This matrix runner exercises the declared owned route. The separate [delivery-study runner](../scripts/run-native-delivery-study.ps1) uses the passed matrix's first owned replay as its hash-checked reference, collects repeated synthetic UI runs and retains the resulting agreements **and disagreements**. It selects nonempty, fully executed P1/button-1 plans; empty plans are explicitly outside this study. It must not report a receipt disagreement as whole-route equivalence. Substitute the matrix evidence directory printed by the previous runner:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-native-delivery-study.ps1 -GameDirectory 'C:\path\to\Geometry Dash' -MatrixPath .\examples\native\interaction-matrix.json -MatrixEvidenceDirectory 'C:\local-evidence\interaction-matrix' -Repetitions 3
```

Inspect the actual generated paths reported by each runner. The CLI command is `native`; there is no `native-inspect` alias. Same-plan UI pairs can be inspected offline:

```powershell
.\.venv\Scripts\python.exe -m axiom native .\reports\native\study\ui.json
.\.venv\Scripts\python.exe -m axiom native-delivery-compare .\reports\native\study\owned.json .\reports\native\study\ui.json
```

The paired variant study is evaluated separately using `fixture-variants` with the public study/matrix, both variant captures and the declared study `--case`. A valid JSON mismatch may return CLI exit zero; the structured status is the evidence gate.

The public [variant runner](../scripts/compare-native-variants.ps1) evaluates all six declared pairs offline and binds them to the passed matrix manifest. It launches no game:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\compare-native-variants.ps1 -MatrixPath .\examples\native\interaction-matrix.json -StudyPath .\examples\native\interaction-variants.json -MatrixEvidenceDirectory 'C:\local-evidence\interaction-matrix'
```

For one pair, use the CLI directly:

```powershell
.\.venv\Scripts\python.exe -m axiom fixture-variants .\examples\native\interaction-variants.json .\examples\native\interaction-matrix.json 'C:\local-evidence\interaction-matrix\raised-platform-positive\replay-1.json' 'C:\local-evidence\interaction-matrix\raised-platform-control\replay-1.json' --case raised-platform
```

## User-operated native-clock observation

The separate [manual-input runner](../scripts/run-native-manual-input.ps1) launches a visible guarded sandbox and waits for the person to click **Start AXIOM Test**, then press and release Space while the fixture runs:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-native-manual-input.ps1 -GameDirectory 'C:\path\to\Geometry Dash' -TimeoutSeconds 180
```

This route supplies no replay schedule or synthetic OS input. The collector must report clock policy `native`, driver `none`, delivery provenance `unknown` and `input_source: unknown`. Native callbacks and queue receipts can show what reached the selected engine entries. A separate user statement can describe who operated the test; that statement does not change the capture's unknown provenance or authenticate hardware origin. A timeout, abort, empty receipt stream or valid observation without a user statement cannot establish a completed human-input qualification. Manual observations have their own challenge and environment identity and are not pooled with fixed-scheduler paired results. **No manual observation has yet been qualified in this ledger.**

## Preserving attempts

Consume structured verdicts and integrity checks rather than CLI exit zero alone. Retain failed preparations, pauses and mismatches as separate evidence. A reused evidence output directory is rejected and preserved; an active sandbox process prevents concurrent execution. Fixed-scheduler-240 remains an explicit clock intervention, with separate `native` and `fixed-base-60` domains.

The runner snapshots and restores the bytes and existence of four isolated experiment files: fixture, replay, AXIOM settings and loader settings. Its temporary Windows execution-state request and restoration are harness context, not exhaustive environment capture. Raw captures, runtime binaries/resources and personal saves remain outside Git. Older schema-1/2/3 reader paths and historical results remain separate; new contact/target/UI observations cannot be inferred for old captures.

A separate **offline compatibility audit** retained 344 equal normalized output/rejection comparisons against baseline commit `8b8dbcc3d215ddd2e6dff25d127829f387a6bb52`, including 41 historical capture files in their separate domains. It ran the current readers at commit `520bfe889d058ecc037eb57b6f7cc70a0f3e4d64`. Compact sorted-key JSON normalization removed no warning/diagnostic fields. The local report is `reports/audit-legacy-schema-outputs-result.json`, SHA-256 `edbcd245d73f2cbc932fa3ae744c0dad1a03d85614941da0686fa8613226b23a`. These are API/file-compatibility comparisons, not new native runs, unit-test totals, schema-4 qualification or external replication.

## Primary references and open gates

Pinned [PlayerObject declarations](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/GeometryDash.bro#L14794-L14808) supply the two raw contact flags. [GameObject group state](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/GeometryDash.bro#L6376-L6377), [positions](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/GeometryDash.bro#L6444-L6457) and [enabled-group operations](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/inline/GameObject.cpp#L490-L498) inform the selected watches. [Trigger property annotations](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/GeometryDash.bro#L4055-L4087) and [delayed spawn routing](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/inline/GJBaseGameLayer.cpp#L1203-L1205) supply construction/hook context. [UILayer's native keyboard entries](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/GeometryDash.bro#L20177-L20185) are distinct from external device arrival.

The [direct native toggle binding](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/GeometryDash.bro#L7686) is the distinct observed entry for these toggle fixtures. The [pinned GDsolver slope construction](https://github.com/gdsolver/gdsolver/blob/8e8d69ada86a315c71d05cc8b8fe4d369d883aa2/py/mklevel.py#L256-L267) and [raw/world coordinate note](https://github.com/gdsolver/gdsolver/blob/8e8d69ada86a315c71d05cc8b8fe4d369d883aa2/py/mklevel.py#L77-L91) guide candidate placement. [Archived gd.py trigger IDs](https://github.com/nekitdev/gd.py/blob/f2c1c74bdeb55bbe8e1233ec2f04098ef043f5c8/gd/enums.py#L1547-L1552) guide construction, with current behavior determined by AXIOM's native observations. They supply no automatic execution certification.

M1 remains open: environment/state completeness, broader colliders and moving geometry, trigger ordering/loops/RNG, reset/focus/pause behavior, OS/device delivery, recording overhead, throughput, checkpoint restoration and human calibration require further evidence. This bounded study supplies no continuous timing window, impossibility proof, human limit or calibrated real-level AR.
