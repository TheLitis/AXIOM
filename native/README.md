# AXIOM native adapter — M1

This opt-in Geode mod records native callbacks and a small player-state subset on
Windows x64 / Geometry Dash 2.2081 / Geode 5.8.2. It does not calculate AR, prove
complete engine determinism, infer collision geometry or estimate human limits.
Build success and a loaded DLL do not establish gameplay capture or replay fidelity.

Build from the repository root with `scripts/build-native.ps1`. The script and
CMake pin SDK commit `2a5fd87433da47d6bf07221774f0cbb25535ae08` and bindings
commit `2a8b5c489ce8b49e7061b0543aa2bc5b22570063`. Packaging uses
`setup_geode_mod(... DONT_INSTALL)`; building does not install into the game.

## Controls and local files

Both **Enable local capture** and **Enable AXIOM command replay** default to false.
Enabling either starts recording at the next successful `PlayLayer::init` or reset.
An on-screen AXIOM indicator and Geode log announce active recording. Pause,
death, finish, quit and reset terminate the attempt. Exports are local JSON files
under this mod's save directory, in `captures/`; there is no network upload.

Equivalent explicit launch flags are
`--geode:axiom.native-capture.capture=true` and
`--geode:axiom.native-capture.replay=true`. They are read at attempt start. Replay
reads the fixed file `replay.json` in this mod's save directory. It requires a
classic level, a full start and exact recorded level/environment digests. Practice,
start-position, platformer and built-in replay starts are ineligible for replay.

Use an isolated game/save profile for engine fixtures. The optional
`src/SandboxFixture.cpp` smoke-test helper also requires an executable named
`AXIOMSandbox.exe` and `--geode:axiom-sandbox=true`; its save redirect and fixture
launcher are inert without both conditions. A writable-path check guards fixture
creation. This helper is a smoke test, not evidence that every save access path is
isolated; the launch procedure must establish that separately.

## Capture semantics

Each `native_capture` document has schema version 1 and one `attempt`. It includes
the exact SHA-256 of bytes held in `GJGameLevel::m_levelString`, executable, adapter
and loaded mod binaries; pinned collector source/SDK/bindings identities;
environment identity; selected state fields; trace integrity; and native terminal
callbacks. No local paths, account identifiers or level description are exported.
The collector's source-tree digest identifies the compiled native source files,
CMake and mod manifest even when the Git commit predates local edits.

The environment digest uses compact JSON with recursively sorted object keys and
UTF-8 strings. Binary hashes identify recorded files; the mod inventory and hash
do not capture every game/mod setting. `configuration_complete` is therefore false.

`command_index=0` is the initial selected-state sample after initialization/reset.
Each `GJBaseGameLayer::processCommands` entry increments the index, and a sample
is taken after its original call. `dt_seconds`, `is_half_tick` and `is_last_tick`
are exactly the arguments supplied to that hook. This clock is not demonstrated
to equal render frames, physical input arrival or all engine simulation steps.
The zero sample uses `dt_seconds=0` and false flags as a declared initialization
sentinel. Calls observed during initialization mark the start as unknown.

`handleButton` records a **requested** event before its original call. Player
`pushButton`/`releaseButton` record the callback and returned Boolean after the
original call. The return value has no independently demonstrated meaning of
physical input acceptance. Both phases are retained instead of deduplicated.
Input indices count command entries already observed. A request arriving between
calls has the previous call's index; replay index `n` instead injects before call
`n`. Directly copying observed indices into a replay plan is therefore unsupported.
M1 provides only explicitly prepared pre-hook replay schedules, with no validated
translation from observed or GDR events. Recorded wall-time values are diagnostics
and must be excluded from repeat comparisons. Unauthenticated observed input has
`input_source="unknown"`.

Replay injects only requested inputs through `handleButton` before specified
command calls. It uses no position corrections, checkpoint restores or fabricated
frame-to-second conversion. During replay, non-injector `handleButton` requests
are suppressed and retained separately in `attempt.blocked_inputs`, with unknown
origin. A one-shot permission forwards each scheduled request. This owns the
handler channel, including engine cleanup requests; equivalence to ordinary
vanilla or human delivery is unverified. Direct player push/release calls bypassing
this handler are not controlled. The plan and exact replay-file digest are
retained; repeated trace/outcome checks cover only this declared policy.

The scheduler calls the qualified native binding
`GJBaseGameLayer::handleButton`, which enters Geode's registered handler before
the one-shot permission is consumed. Calling the modified C++ wrapper directly
can enter that wrapper twice and block the scheduled request before the original
engine function runs. This is the same dispatch issue described in Geode's
[modify tutorial](https://github.com/geode-sdk/docs/blob/main/tutorials/modify.md#accidentally-not-using-the-correct-function).
Actual `PlayerObject` callbacks and a changed trajectory must be checked in the
native fixture; recorded requested events alone do not establish input response.

Terminal state is sampled after the original `levelComplete` or `destroyPlayer`
callback. Death requires the player `m_isDead` field after that callback. A terminal
inside a command call is exported only after the final post-command trace sample.
These two state samples can differ because they occur at different hook boundaries.
Aborts use the corresponding pause/quit/reset callback; collector errors use
`AXIOM::error`. Exceptions, overflow and dropped records invalidate integrity.
The exporter uses a temporary file followed by rename; output failures produce a
log error and no claimed complete artifact. Capture is limited to 20,000 command
calls, 12,000 delivered plus blocked input records and a 16 MiB export.

State fields are `x`, `y`, `y_velocity`, `rotation`, `is_dead` and a mode label for
each player pointer. They exclude trigger, checkpoint, object, RNG, collision,
audio, render and other engine state. Equality of this subset is only equality of
the recorded subset. A second player pointer can exist while inactive.

## AXIOM command replay JSON

This is an AXIOM-specific scheduling format, not GDR and not a claimed physics
frame format. Copy both digests from a compatible native capture. Events are
ordered by command index; equal-index order is their order in the array.
Indices start at 1. Zero events are valid for an automatic fixture.

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

Only the documented fields are accepted. Button numbers 1–3, player numbers 1–2,
integer indices 1–20,000, Boolean press states and at most 4,000 planned events are
supported. Duplicate keys, unordered events, wrong target hashes, nesting above
64 and input files above 16 MiB are rejected. M1 intentionally does not convert
external replay formats into this uncharacterized native hook clock.

API definitions come from the pinned
[Geode SDK](https://github.com/geode-sdk/geode/tree/2a5fd87433da47d6bf07221774f0cbb25535ae08),
[2.2081 bindings](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/GeometryDash.bro)
and [matjson 3.3.0](https://github.com/geode-sdk/json/blob/v3.3.0/include/matjson.hpp).
Bindings establish hook and field declarations, not runtime behavior validation.
