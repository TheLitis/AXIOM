# Native collisions, trigger effects and synthetic UI delivery

[Русская версия](native-interactions.ru.md) · [mechanics checkpoint](native-mechanics-matrix.md) · [adapter contract](native-adapter.md)

This stage studies selected collision/contact state, changes to explicitly watched objects and a bounded in-engine input-delivery path. Native capture schema **4**, fixture catalogue schema **3** and the separate [delivery comparator](../src/axiom/equivalence.py) describe different contracts. They do not establish complete collision geometry, general trigger semantics, ordinary OS-input equivalence or human Axiom Rating.

## Evidence status — PENDING

**The source-frozen confirming interaction matrix and delivery study have not yet been recorded and audited in this ledger.** There is no final pass count, final package/environment identity or manual-input qualification here. Construction probes select candidates; their outcomes cannot substitute for independent confirming repetitions.

The prepared collector's signed source commit is `3a868abbb05f6aab82c71cd3ab14a60b215c25b6`; its package SHA-256 is `6fe5811d98cf352eead0bc2d0dcee6acbb70914419c09eaee9376d5e5b7fe3b5`. These are build identities awaiting confirming execution, distinct from the evaluator commit and loaded-binary/environment identities that each final run must retain.

The retained development directory is `reports/native/interaction-probes-f70221d06ae64c4b9be0fabc1cb5b2f2/`. A raised-platform capture completed and sampled P1 at command 219 with `y: 135`, `is_on_ground: true`, `is_on_slope: false`; its flush-platform control also completed. Slope captures supplied selected contact observations. The low-ceiling attempt died at command 150, while its high-ceiling control completed at command 734. The toggle-positive attempt completed, while its control died at command 217. These are development observations under their recorded identities, not final repeat or paired-control verdicts.

The moving-wall positive completed, but its control was **aborted by pause at command 0**. That control establishes neither the hypothesized wall death nor a completed contrast. The failed run remains retained. The initial scheduled-UI probe was also rejected by a guard. Subsequent development captures in `reports/native/interaction-probes-5ddd0f4efdf046379ccf45a4175b46c4/` supplied valid attempts for all six construction pairs; those exploratory attempts still do not establish the final confirming matrix.

Development also exposed two limits that must survive qualification. Ceiling attribution comes from the parent watched `collidedWithObject` receipt, with `native_return: true` and `is_dead: false → true`; its nested `destroyPlayer` receipt has a **null object argument**. The synthetic UI route forwards an unsolicited initial P1 release at command 1 that the owned route suppresses. Selected dynamics and the scheduled queue path can agree while the complete delivered receipt streams disagree. Final requirements, publication catalogue, measured identities and confirming results remain pending.

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

## Primary references and open gates

Pinned [PlayerObject declarations](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/GeometryDash.bro#L14794-L14808) supply the two raw contact flags. [GameObject group state](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/GeometryDash.bro#L6376-L6377), [positions](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/GeometryDash.bro#L6444-L6457) and [enabled-group operations](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/inline/GameObject.cpp#L490-L498) inform the selected watches. [Trigger property annotations](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/GeometryDash.bro#L4055-L4087) and [delayed spawn routing](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/inline/GJBaseGameLayer.cpp#L1203-L1205) supply construction/hook context. [UILayer's native keyboard entries](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/GeometryDash.bro#L20177-L20185) are distinct from external device arrival.

The [direct native toggle binding](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/GeometryDash.bro#L7686) is the distinct observed entry for these toggle fixtures. The [pinned GDsolver slope construction](https://github.com/gdsolver/gdsolver/blob/8e8d69ada86a315c71d05cc8b8fe4d369d883aa2/py/mklevel.py#L256-L267) and [raw/world coordinate note](https://github.com/gdsolver/gdsolver/blob/8e8d69ada86a315c71d05cc8b8fe4d369d883aa2/py/mklevel.py#L77-L91) guide candidate placement. [Archived gd.py trigger IDs](https://github.com/nekitdev/gd.py/blob/f2c1c74bdeb55bbe8e1233ec2f04098ef043f5c8/gd/enums.py#L1547-L1552) guide construction, with current behavior determined by AXIOM's native observations. They supply no automatic execution certification.

M1 remains open: environment/state completeness, broader colliders and moving geometry, trigger ordering/loops/RNG, reset/focus/pause behavior, OS/device delivery, recording overhead, throughput, checkpoint restoration and human calibration require further evidence. This bounded study supplies no continuous timing window, impossibility proof, human limit or calibrated real-level AR.
