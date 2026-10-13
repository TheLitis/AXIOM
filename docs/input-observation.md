# Keyboard and gameplay touch observation

[Русская версия](input-observation.ru.md) · [Native adapter](native-adapter.md) · [Historical interaction evidence](native-interactions.md) · [Recorded replay contract](recorded-replay.md)

**Schema 5 is built and loaded; a fresh native-clock observation recorded all seven requested raw key codes and five touch begin/end pairs.** A separate controlled cube-flat repeat group passed the recorded subset, while its preceding delivery-context failure is retained. These are bounded observations, not device-origin authentication or complete input equivalence. The schema-4 interaction, synthetic UI and operator-reported manual results retain their original captures, hashes and limitations; their absent touch observations are not reconstructed.

The separate opt-in [Windows observer](windows-input.md) extends observation upstream in schema 7 with Windows-message and public Geode streams. Its implementation/tests/native build are ready, but live qualification is not established: the three retained startup attempts exported no capture. It preserves the schema-5 evidence below and does not turn UILayer-only events into authenticated Windows/device events.

## Recorded coverage

Observation is scoped to the active captured `PlayLayer`'s `UILayer`. Existing `keyDown`/`keyUp` hooks already accept every raw key code that reaches that layer; schema 5 makes those codes readable and adds paired touch callbacks. Events intercepted elsewhere, menu input and global keyboard activity are outside this scope.

| Entry | Retained observation | Interpretation |
|---|---|---|
| `UILayer::keyDown` / `keyUp` | Raw code, timestamp, callback direction and paired queue snapshots | A recorded key edge does not establish a gameplay action or a physical key edge |
| `UILayer::ccTouchBegan` | Raw touch arguments and Boolean native return | A true return does not authenticate a mouse, touchscreen or game action |
| `UILayer::ccTouchEnded` | Raw touch arguments; null native return | An observed touch end retains its native queue change |
| `UILayer::ccTouchCancelled` | Raw touch arguments; null native return | Cancellation is recorded separately and does not fabricate a release |
| `GJBaseGameLayer::processQueuedButtons` | Existing paired queue and processor context | Entry and processing can be connected only through retained evidence |

The selected Windows input route forwards left-button events into touch handling; **right and middle mouse entry are not covered by these UILayer hooks**. The raw touch callback does not itself identify a device. Touch movement is also outside the added callback set. The pinned [Windows routing](https://github.com/geode-sdk/geode/blob/2a5fd87433da47d6bf07221774f0cbb25535ae08/loader/src/platform/windows/input.cpp#L537-L592) and [mouse-code conversion](https://github.com/geode-sdk/geode/blob/2a5fd87433da47d6bf07221774f0cbb25535ae08/loader/include/Geode/utils/Keyboard.hpp#L91-L122) do not justify labelling `KEY_None` as LMB or treating every mouse button as a key.

Touch arguments are exact native `touch_id`, `view_x`, `view_y` and `timestamp`. All four are null together only when the incoming touch pointer is null; partial null arguments are rejected. View coordinates are not measured physical screen coordinates, and timestamp units are uncharacterized. Every schema-5 delivery row requires `native_return`: Boolean only for touch begin and null for the supported void callbacks. The original callback is called exactly once; the active UILayer pointer is checked before reading its gameplay fields, including the shared empty cancellation binding.

## Readable raw keys and queue changes

The labels come from the pinned [Cocos `enumKeyCodes`](https://github.com/geode-sdk/geode/blob/2a5fd87433da47d6bf07221774f0cbb25535ae08/loader/include/Geode/cocos/robtop/keyboard_dispatcher/CCKeyboardDelegate.h#L29-L77), not from an authenticated Windows or hardware key stream.

| Requested key | Raw code | SDK label |
|---|---:|---|
| Space | 32 | `KEY_Space` |
| W | 87 | `KEY_W` |
| Up | 38 | `KEY_Up` |
| A | 65 | `KEY_A` |
| D | 68 | `KEY_D` |
| Left | 37 | `KEY_Left` |
| Right | 39 | `KEY_Right` |

All other recorded codes remain available with their SDK name or `Unknown Cocos key code N`. Alternate SDK arrow codes remain distinct: for example, `KEY_ArrowUp` (283) is not collapsed into `KEY_Up` (38). `MOUSE_4`/`MOUSE_5` are raw labels, not proof of a physical side button. Whether an entered key reaches a gameplay command depends on native mapping and context; an entry without an appended queue command does not prove an action.

The inspector field `input_entry_observations`, introduced in schema 5 and also available for schemas 6/7, has `scope: recorded_uilayer_callback_entries_and_paired_queue_snapshots` and `key_code_namespace: raw_cocos_enumKeyCodes`. Its ordered `keyboard_edges` and `touch_edges` retain every callback, including repeats, unknown codes and cleanup. Edges keep sequence/nesting, command/update/Scheduler context, phases, wall times, native return and before/after layer timestamps. Keyboard edges add raw code/name, callback direction and timestamp; touch edges add the exact four touch arguments. `counts` includes edge counts, event types, per-code down/up counts and null-touch count. Counts describe recorded callbacks, not hardware events or successful game actions.

`queue_prefix_retained` checks whether the entire before-queue is an exact prefix of the after-queue. If it is, `appended_queued_commands` retains the exact suffix with `queue_attribution: paired_append_snapshot_only`; an empty suffix is valid. Otherwise the appended field is null and attribution is `unavailable_nonprefix_queue_change`. This is a paired snapshot observation, not isolated causality or authenticated queue origin. The summary preserves `authentication_status: not_authenticated`, `physical_device: not_identified` and `game_action_mapping: not_inferred_from_callback_entry`.

Historical schemas 1–4 keep their strict original readers and absent fields. Schema-5 repetition uses the existing **18 components** and `native-delivery-context-v1`: cross-run comparison excludes raw absolute layer/key/queue timestamps and, separately, raw touch timestamps with uncharacterized units, while retaining their raw equality/first-difference diagnostics. Touch ID, view coordinates, native return, order and queue context remain exact comparison inputs. Within an attempt timestamps remain exact raw values. No relative-time or physical-time conversion is introduced.

The schema-5 observation extension retains `process-commands-scheduled-delivery-v2` and the legacy replay drivers; synthetic UI replay schedules only Space for player 1/button 1. That extension adds no OS input generation. The separate [recorded-replay contract](recorded-replay.md) introduces an owned processing-entry driver and recorded cadence in schema 6; three fresh replays passed its declared source correspondence and all 18 repeat components through native completion at command 4894, with the earlier export rejection retained. The source observations and measured schema-5 results below are immutable.

## Manual test recipe

From the repository root, use a lawful local game installation and the pinned build:

```powershell
uv sync --locked --extra dev
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-native.ps1 -Jobs 4
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-native-manual-input.ps1 -GameDirectory 'C:\path\to\Geometry Dash' -TimeoutSeconds 300
```

The runner opens a visible sandbox with **Start AXIOM Test**. Click it, then press and release Space, W, Up, A, D, Left and Right individually, and press/release LMB inside gameplay. Let the flat fixture finish. The new fixture places its final object at raw X=6000; the historical manual fixture at X=1800 remains a separate payload. The timeout includes menu waiting; an unstarted or interrupted experiment retains its logs rather than becoming a completed observation.

This route uses the native clock, no clock intervention, driver `none`, no source replay and an empty owned plan. Capture input source/provenance remain `unknown`. The runner requires schema 5, validates the exact level hash and copies `input_entry_observations` into `manual-result.json`. It does not require that all seven keys have appeared: a structurally valid result is not complete key coverage.

Inspect the printed evidence path with `axiom native '<evidence-directory>\capture.json' --json '<evidence-directory>\inspection.json'`. Check recorded down/up edges per code, touch edges, paired queue changes, queued processing and actual requested/player receipts. An unsupported key may be observed without a game action. Retain all extra and cleanup events. Native [focus-loss handling](https://github.com/geode-sdk/geode/blob/2a5fd87433da47d6bf07221774f0cbb25535ae08/loader/src/platform/windows/input.cpp#L687-L716) can generate key-up events, so callback direction alone does not prove a physical release.

Keep an operator statement separately from native telemetry. An assertion that the operator pressed these controls does not change raw provenance or authenticate an OS/hardware path. Local telemetry remains in ignored `reports/native` directories; inspect it before sharing. The runner restores and checks the four experiment files' original existence and bytes. No global key logger or physical input behavior change is added.

## Evidence status and limits

### Native-clock observation, 11 October 2026

The schema-5 manual harness recorded completion at command **4894**, with **106 actual input receipts (53 requested, 26 push, 27 release) and 107 delivery records**: 46 keyboard entries (23 down/23 up), 10 touch entries (5 begin/5 end) and 51 queued-processor callbacks. No touch cancellation or null touch argument was observed. All five begins returned true; those returns do not authenticate a device. Native clocks, driver `none`, empty replay plan and unknown input source/provenance are retained.

| Recorded key | Down / up | Observed paired queue append |
|---|---:|---|
| Space (32) | 4 / 4 | P1, button 1 |
| W (87) | 3 / 3 | P1, button 1 |
| Up (38) | 3 / 3 | P2, button 1 |
| A (65) | 4 / 4 | P1, button 2 |
| D (68) | 4 / 4 | P1, button 3 |
| Left (37) | 2 / 2 | P2, button 2 |
| Right (39) | 1 / 1 | P2, button 3 |
| S (83), additional | 2 / 2 | Empty suffix on all four entries |

All ten touch entries appended P1/button-1 edges matching begin/end direction. This table describes observed queue mappings in this exact fixture; it does not infer actions from key names. P2 was inactive. Twelve recorded `PlayerObject` receipts inside queued-processing intervals identify the P1 actor while the queue and requested channel label P2. Queue/request channel and actual callback actor remain separate observations; no engine cause or P2 gameplay/state effect is inferred. All extra receipts, including the initial release, remain retained. No operator-authorship statement is used to change native provenance.

### Controlled repeat checks

Two separate fixed-Scheduler cube-flat groups each recorded four completed attempts at command 734: baseline, two owned replays and skip-input control. Every capture matched its declared fixture observations. In the first group the owned pair agreed on **17/18 components** but failed `native_delivery_context_equal`: one replay retained touch begin/end at commands 360/381 and queued processing at 361/382, with the unknown-origin requests blocked by the owned policy. The matrix verdict is `declared_matrix_not_established`; matching dynamics do not override this failure.

The second group, collected separately without requested interaction, passed **18/18 components** and `declared_matrix_recorded_subset_passed`. Each capture recorded only its initial queued-processor callback and no key/touch entries. Both groups retained a selected jump response against the skip-input plan and exact four-file restoration. The second pass does not replace the first failure or qualify untested mechanics/cancellation.

The same-host artifact audits passed **132 checks for the first group and 128 for the second, zero failures**. These recompute retained records and reports; they do not independently authenticate engine execution or hardware. The corrected manual audit passed **29 structural/identity/preservation checks**, zero failures, and verified that all 106 actual receipts fall inside recorded queue-processing intervals while retaining the P1/P2 actor distinction above. The initial narrower audit remains preserved; raw capture data did not change. Software validation separately passed 688 tests plus 83 subtests and Ruff. Offline historical compatibility checked 412 results: 411 exact matches and one expected supported-version message change, not new historical native qualification.

### Provenance and retained digests

The compiled collector and evaluator source commit is `638ee55244eb1801ad7ab51e474b2e136bfdfdb7`. Native source-tree SHA-256 is `97b92fab1d50b15630e0f3e2ebb41f9298e5536473d36e6bd2c3df7d34ffba3d`; package SHA-256 is `c6220ad8e362caeef89df7910ea0257f5e2cea3b3abc99cad1609e1c899ed270`; loaded DLL SHA-256 is `11c1867370d03f8805e3c79e38ba5cbf2820ff5aa1b0018658d2fc0aa0e60aed`. The native-clock manual environment hash is `393a2b8555222c944b1fce823b8472c29a40c8d9a43b492b95be032318b07592`; both fixed-Scheduler groups use `5cda90571fc1541d01b2408638c3389473a60df54213942437bff223aa9ddda0`. These clock domains are separate.

| Retained result | SHA-256 |
|---|---|
| Manual capture | `a8721c3d671f9cdb2b75d7567b0fbaf2a32421cbbc30f298577bd2cb40460da7` |
| Manual result, 01:31:49.6634449 UTC | `86ef6a5f818dc31e2e786ab587f8cb2acc48dbff99057fbc465c196e2ef9b72e` |
| First matrix result, 01:30:10.3030354 UTC | `b89abc35ec93a19fa5172cfa7cecb29f54652016548ea9ec211f00bda277b378` |
| Second matrix result, 01:33:32.1596850 UTC | `4038c4f17cd9e50c57bdf05429b7497f7ee28bbce786a4a8eb6cdf0b94ff861a` |
| First group artifact audit | `985d580528c208c5a8b2fd216a9e3b6a17d6a70b7319e67a80b61cd69566e7f4` |
| Second group artifact audit | `3338e034938bdd76b192a83394a0dd207836b39ed6c9c31b72e5e637210a19a4` |
| Corrected manual artifact audit | `898e3c1549d9e69b7d63cce9a482da3f27ddfd76834ad3ce43858f87bd8d4c90` |

Local ignored evidence retains complete raw captures, inspections, manifests and four-file preservation records. Historical schema-4 results remain in the [interaction ledger](native-interactions.md#operator-reported-manual-observations). These results do not establish right/middle mouse or cancellation coverage, complete ordinary-input equivalence, full engine state, M1 completion, human calibration or AR.

The pinned [GD 2.2081 UILayer bindings](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/GeometryDash.bro#L20171-L20185) and [CCTouch API](https://github.com/geode-sdk/geode/blob/2a5fd87433da47d6bf07221774f0cbb25535ae08/loader/include/Geode/cocos/touch_dispatcher/CCTouch.h#L51-L92) support the selected signatures and raw fields. These primary sources specify APIs; they do not authenticate an individual capture or replace native execution evidence.
