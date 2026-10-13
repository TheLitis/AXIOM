# Windows-to-game input observations

[Русская версия](windows-input.ru.md) · [Native adapter](native-adapter.md) · [UILayer observations](input-observation.md) · [Recorded replay](recorded-replay.md) · [Roadmap](roadmap.md)

**Implementation, software checks and native build are ready; live Windows qualification is not established.** The opt-in schema-7 observer adds Windows ingress and public Geode events alongside existing UILayer, native-queue and player receipts. Two new-package startup attempts and a separate old-package startup control produced no exports. There is no completed schema-7 observation, device authentication or ordinary-input equivalence. Historical schema-5 observations and schema-6 recorded replays retain their original evidence and scope.

This route uses `windows-input: raw-dispatch-v1`, native clocks and driver `none`, without a replay plan or clock intervention. It observes the existing game process; it does not generate input, register another Raw Input receiver, change event payloads or consume Geode's private queue.

## Separate observation stages

| Stage | Recorded scope | Limit |
|---|---|---|
| Windows window ingress | Selected messages at the main game HWND and hidden `GD_RawInput` HWND; raw keyboard and mouse-button payloads | A message/read receipt does not authenticate hardware or prove delivery into gameplay |
| Public Geode events | Typed keyboard code/action/native-code/timestamp/modifier and typed mouse button/action/timestamp/modifier snapshots | Other listeners may alter or stop a mutable event; a snapshot does not prove final routing |
| UILayer entry | Existing key and touch begin/end/cancel observations on the active gameplay layer | Right/middle mouse need not become touches or game actions |
| Native processing / player | Existing queue snapshots, requested channel and actual push/release actor/native return | A P2-labelled request may reach P1; keep both observations rather than rewriting labels |

Raw keyboard and button recording is bounded to an active attempt while the main game HWND is foreground. Background and motion-only traffic contributes skip counts rather than gameplay evidence. Main-window focus messages remain separate observations. No raw device handle (`hDevice`) is retained; there is no global keyboard log, text/clipboard collection or physical-device identity claim.

## Schema-7 record

Only the explicitly selected Windows observer uses schema 7, retaining `attempt.windows_input` alongside the existing gameplay streams. Historical schemas 1–6 remain unchanged.

| Field | Contract |
|---|---|
| `enabled`, `scope`, `main_thread_id`, `windows` | `active-guarded-sandbox-attempt-foreground-raw-only`; main/raw roles with process/thread/HWND and installed status |
| `messages` | At most 2048 ordered paired WNDPROC receipts, per-thread nesting, foreground before/after, wall/input timestamps, raw message parameters and exact native LRESULT |
| `raw_input` within a message | Keyboard: kind/vkey/scan_code/flags/keyboard_message; mouse: kind/button_flags; no device handle or movement payload |
| `sdk_events` | At most 2048 public typed event snapshots, phase/context and one `queue_snapshot` at receipt; no private-queue interception |
| `integrity` | `overflow_count`, `read_error_count`, `pending_callbacks_at_snapshot`, `errors`; incomplete observations cannot establish the ledger |
| `skipped` | `background_raw_count`, `mouse_motion_count`, `unsupported_raw_count` |
| Timestamp/listener metadata | `Geode-getInputTimestamp-QPC-seconds`, `public-global-listener-receipt`, priority `INT_MIN` |

The inspector exposes `windows_input_observations`. The public global listener propagates without changing data, but may not see events stopped in an earlier key-specific port. Paired message exit can follow the native terminal during in-flight callback draining; that exit is not a newly inferred gameplay action after completion.

## Lifecycle and timing

The pinned [Geode Windows route](https://github.com/geode-sdk/geode/blob/2a5fd87433da47d6bf07221774f0cbb25535ae08/loader/src/platform/windows/input.cpp#L660-L715) finds `GD_RawInput` asynchronously on a different thread. Windows subclass helpers [cannot be used across threads](https://learn.microsoft.com/en-us/windows/win32/api/commctrl/nf-commctrl-removewindowsubclass). Same-process WNDPROC chaining through [`SetWindowLongPtrW`](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowlongptrw) is a separate mechanism: retain the prior procedure, forward each message once and record attach/detach failure or chain replacement. Do not infer safe lifetime from a discovered HWND alone.

[`GetRawInputData`](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getrawinputdata) reads the packet referenced by `WM_INPUT`; preserve read status and raw flags before forwarding. AXIOM must not replace the existing [Raw Input registration](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerrawinputdevices): one receiving window per device class is selected within a process. Windows packet fields and Cocos key codes remain different namespaces. Keyboard break/extended flags, repeated downs and combined mouse-button flags are retained as observed; they are not deduplicated into presumed physical actions.

[`GetMessageTime`](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getmessagetime) describes the creation time of the last retrieved queue message in wrapping milliseconds; this contract does not record that value. Geode's pinned [`getInputTimestamp`](https://github.com/geode-sdk/geode/blob/2a5fd87433da47d6bf07221774f0cbb25535ae08/loader/src/platform/windows/util.cpp#L445-L455) samples QPC/frequency when input is packaged. Recorded observer wall timing, Geode timestamp, raw touch timestamp and command/update/Scheduler membership remain separately labelled. None is promoted to a measured hardware-arrival time, continuous input window or authenticated latency.

Geode transfers raw events through a private mutex queue and pumps them later; it can clear that queue when the main window is not foreground. Its focus callback can produce key-up events internally. These source paths mean that a dispatcher release does not require a corresponding recorded Windows break, and temporal proximity does not establish nesting across threads.

## Association contract

Protocol `windows-raw-sdk-ui-compatible-candidates-v1` retains **candidates**. Raw-Windows-to-Geode compatibility requires matching native key/scan/direction or mouse-button flags and a Geode timestamp inside the recorded message's exact `input_timestamp_enter`/`input_timestamp_exit` interval, without a wall-nearness tolerance. A repeated key down remains distinct in the SDK snapshot but matches a raw down. Geode-to-UILayer compatibility requires the same thread, observed ordering and exact key/direction/timestamp; mouse candidates require a left-button press/release matching touch begin/end.

The report preserves `no_compatible_candidate`, `one_compatible_candidate` and `ambiguous_compatible_candidates`, every raw record and unmatched sequences. An unmatched lifecycle message is not declared a dropped key. A unique candidate remains an observed association under that rule, without hardware authentication or proof that every intermediate queue step was captured.

Typed right/middle mouse events are independently observable; their absence from UILayer or gameplay is not repaired by inventing touch/player receipts. Cancellation is preserved as cancellation, not a fabricated release. Focus loss, pause, reset and early exit remain distinct outcomes; a focus-change observation alone is not a completed focus-recovery qualification. Pause seals the active observation at its recorded abort boundary, so later focus-generated releases may be outside the capture. Release associations are reported only for callbacks actually retained.

## Manual procedure

Use the locally installed, pinned game and a fresh isolated runtime/evidence directory:

```powershell
uv sync --locked --extra dev
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-native.ps1 -Jobs 4
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-native-windows-input.ps1 -GameDirectory 'C:\path\to\Geometry Dash' -TimeoutSeconds 600
```

The runner explicitly enables capture with `--geode:axiom.native-capture.capture` and selects an isolated sandbox and `windows-input=raw-dispatch-v1`; the default also selects `sandbox-manual`. Optional `-NativePackage` selects an explicit package; optional `-AutomaticStart` omits menu waiting and starts the fixture without generating human input. Optional runtime must be fresh under workspace `.tools`, and evidence output must be fresh within the workspace. These options do not turn subsequent observations into authenticated operator actions. The manual procedure is a future gate requiring an available operator; no completed manual Windows observation is recorded at this checkpoint.

1. Wait for readiness and use **Start AXIOM Test** unless automatic start was explicitly selected.
2. During gameplay, press/release Space, W, Up, A, D, Left and Right separately; use S as an additional observed code.
3. Hold one key long enough to permit repeat messages, then release it. Keep every repeat and release rather than expecting one down/up pair.
4. Inside gameplay, press/release left, right and middle mouse buttons separately. Extra buttons are optional and must be reported as tested only if observed.
5. Let the fixture finish. Keep any operator statement separate from the native data; it does not change recorded provenance.

Do focus/pause/reset experiments in separately declared attempts, preserving the interruption rather than combining it with a successful completion. The timeout includes menu waiting. The runner retains unsuccessful starts and inspections, freezes source/package/level/evaluator identities, and restores the original existence and bytes of the four experiment files. Captures stay in ignored local evidence; game files and private telemetry are not published in Git.

## Live evidence ledger

**13 October 2026: implementation/build READY; native Windows LIVE_NOT_ESTABLISHED.** Software validation passed **789 tests plus 83 subtests**, and Ruff passed on 61 files. Native compilation/package creation succeeded. A separate offline compatibility audit passed 25 checks over 14 historical schema-1–6 captures, with eight saved inspection outputs also unchanged; this is reader compatibility, not new native execution.

The compiled collector commit is `bb3222cbb873b28ece853f49bc96d22870783a18`; native tree SHA-256 is `5c066e5ab06cf798ed00d7c1e53b95b9d82779bdc63f0b9b598d184ee4d0658f`, package `d87e86d8a3a66de81a487ebbf7682f7c28456c6a6685787e260507db5aea93fc` and **packaged DLL** `b28b7eb4d20410f81abc877259001701c000d35121769d9c2a81ebb29de1305d`. These identify the build, not a schema-7 capture or successfully installed observer hooks. The final runner/evaluator commit is `d7fc5f8efe2781e0a63af7f0f7d4ce75d9a57cba`; the first two attempts retain their earlier evaluator identities below.

| Retained startup attempt | Result / evaluator commit | Manifest / preservation SHA-256 |
|---|---|---|
| First new package, 03:59:57–04:00:05 UTC | Capture flag absent; loader log records explicit observer guard refusal, then early exit; zero exports. `a2afa471bb478341d66f9639a6511a637180b404` | `0bb87ac80ac864eac9af38e4a514cdd1dcc22adc73b43833d521a96955406faa` / `2f1afbd23b484c1573006dd851e9aa7b5810b0b22f8c31bbfea28f6af969135e` |
| Second new package, 04:02:32–04:02:36 UTC | Explicit capture flag fixed; still exited before menu readiness/export; zero exports. `b194a6b000b557a8e2bce41d58ba37be0e8327b1` | `653a6c3bf2f16599331b597e215ccec8cf0a7e12a44c8d2f2a5c5c00d1cf3cb9` / `dba6dfbc884437584f075bf14d86439bdc8e6f3a10e828408f9dcfad41a6374a` |
| Old-package automatic startup control, 04:04:19–04:05:26 UTC | Timed out after the 60-second observation window; zero exports. `d7fc5f8efe2781e0a63af7f0f7d4ce75d9a57cba` | `008e425823a9e34f1d4b451a68ad26df19449fe9ab2eaba49e1b1582cd99eedf` / `0da3b9af02e39314b5f6088b5086b9f87eb9a7b5e06a0ee59e5773feb8f98713` |

All three manifests remain `observation_not_established`, with no capture inspection or native terminal result; all four saved file-preservation records passed in each attempt. The old control selected historical package `56eb31f1d96001420f9275708b8404988d409b12cb2414e14f329425966084b7`/DLL `4428b76326c744dd320bae1917b37a4616e1aba6a9097f863e7748d8564185c4`. Its manifest's tree hash freezes the current workspace, not that old DLL's compiled sources. Startup/exit or dialog cause remains unknown; these attempts do not establish an observer-caused failure or any human/hardware input result.

A same-host independent standard-library audit passed **139 saved-artifact checks, zero discrepancies**, verifying the three negative manifests, package/DLL hashes and preservation-record consistency without AXIOM APIs, game launches or profile reads. Audit report SHA-256 is `8a1c66f7f63eb5d88faa7eb359465756587ae229697bae26282e60502e61145c`, helper `2073da9e439f814b67fa7e9b65bb21e7c296fca1fa457e5192dbf0e415a45cd9`. The historical compatibility audit SHA-256 is `b10cb77fc52012808c28a85a6ebdd565b06b18f739e3bb9baeeeb73e75611b66`. Artifact checks do not independently authenticate engine execution or current machine state.

**Still open:** a fresh schema-7 native-clock capture, installed-hook/ingress witnesses, message/typed/UI/queue/player counts and association verdicts, skip/error/focus records and native terminal integrity. There are no schema-7 observed key/button associations to publish. Future manual qualification and focus-recovery checks remain separate gates.

Full ordinary-input equivalence, device/human authentication, complete engine state, general focus/reset recovery, full M1 and calibrated AR remain outside this checkpoint.
