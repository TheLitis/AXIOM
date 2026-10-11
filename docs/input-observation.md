# Keyboard and gameplay touch observation

[Русская версия](input-observation.ru.md) · [Native adapter](native-adapter.md) · [Historical interaction evidence](native-interactions.md)

**Schema 5 is implemented; fresh native verification is pending.** This contract expands gameplay entry observation and its readable inspector summary. It does not establish that a new manual test has recorded every requested key. The schema-4 interaction, synthetic UI and operator-reported manual results retain their original captures, hashes and limitations; their absent touch observations are not reconstructed.

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

The schema-5-only inspector field `input_entry_observations` has `scope: recorded_uilayer_callback_entries_and_paired_queue_snapshots` and `key_code_namespace: raw_cocos_enumKeyCodes`. Its ordered `keyboard_edges` and `touch_edges` retain every callback, including repeats, unknown codes and cleanup. Edges keep sequence/nesting, command/update/Scheduler context, phases, wall times, native return and before/after layer timestamps. Keyboard edges add raw code/name, callback direction and timestamp; touch edges add the exact four touch arguments. `counts` includes edge counts, event types, per-code down/up counts and null-touch count. Counts describe recorded callbacks, not hardware events or successful game actions.

`queue_prefix_retained` checks whether the entire before-queue is an exact prefix of the after-queue. If it is, `appended_queued_commands` retains the exact suffix with `queue_attribution: paired_append_snapshot_only`; an empty suffix is valid. Otherwise the appended field is null and attribution is `unavailable_nonprefix_queue_change`. This is a paired snapshot observation, not isolated causality or authenticated queue origin. The summary preserves `authentication_status: not_authenticated`, `physical_device: not_identified` and `game_action_mapping: not_inferred_from_callback_entry`.

Historical schemas 1–4 keep their strict original readers and absent fields. Schema-5 repetition uses the existing **18 components** and `native-delivery-context-v1`: Cross-run comparison excludes raw absolute layer/key/queue timestamps and, separately, raw touch timestamps with uncharacterized units, while retaining their raw equality/first-difference diagnostics. Touch ID, view coordinates, native return, order and queue context remain exact comparison inputs. Within an attempt timestamps remain exact raw values. No relative-time or physical-time conversion is introduced.

The input policy remains `process-commands-scheduled-delivery-v2`. Owned replay is unchanged; synthetic UI replay still schedules only Space for player 1/button 1. The new observations do not add keyboard injection, OS input generation or new replay mappings.

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

New schema-5 native loading, manual key/touch coverage and outcome evidence remain **pending**. Historical schema-4 results are in the [interaction ledger](native-interactions.md#operator-reported-manual-observations). Successful parsing, compilation or a paired queue append cannot establish complete ordinary-input equivalence, full engine state, M1 completion, human calibration or AR.

The pinned [GD 2.2081 UILayer bindings](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/GeometryDash.bro#L20171-L20185) and [CCTouch API](https://github.com/geode-sdk/geode/blob/2a5fd87433da47d6bf07221774f0cbb25535ae08/loader/include/Geode/cocos/touch_dispatcher/CCTouch.h#L51-L92) support the selected signatures and raw fields. These primary sources specify APIs; they do not authenticate an individual capture or replace native execution evidence.
