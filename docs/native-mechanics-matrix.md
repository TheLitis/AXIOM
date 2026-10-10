# Native gravity, size, speed and dual matrix

[Русская версия](native-mechanics-matrix.ru.md) · [historical mode matrix](native-fixture-matrix.md) · [adapter contract](native-adapter.md)

This study extends the selected native observations to gravity polarity, vehicle size, player speed and active dual state. Its [public catalogue](../examples/native/mechanics-matrix.json) declares 11 short, generated cube fixtures, exact raw-state sequences and responses to owned input plans. A fixture specification remains generated synthetic data; executed captures and their inspections are separate evidence.

## Confirmatory result — PENDING

Confirmation is in progress; the final verdict is pending. No confirmatory pass, final capture count, manifest digest or repeat verdict is claimed in this draft. The planned design is **56 captures, 33 repeated active replays and 12 response contrasts**: ten cases have one observation baseline, three active replays and one owned control; `dual-independent` has two controls and six captures. Every declared run requires completion. A separate schema-3 qualification of historical `cube-flat` and `ship-portal` is also pending; its ten planned completions will remain a separate ledger.

The catalogue and readers were frozen at `0b11bbdf47f53e26f2be8ef3b9a63090c877f7e1`; the confirming runner starts from evaluator revision `8f4691049270f1f8198972ffa3474d918913eb93`. The final identity will be checked against the executed manifest. The collector was compiled from `63d2524c9bdb0e24a8648ad11451eebdeeb88d1f`, with native source-tree digest `44c74f71b8064cddb98ede63c9414fa1016ebfee8cf685d87b46d73b4ae8d4ca`. Those are different component identities. The proposed package SHA-256 is `bc535ba1719ac89ac3fb7c3d1936413356453435e6c4d0d054e934b3a65753fc`; final measured identities and hashes will be checked against retained artifacts before publication.

## Recorded fields and exact values

Native capture schema 3 adds three raw fields to each sampled PlayerObject and one field to the sampled layer state. Fixture catalogue schema 2 declares requirements for these observations. The two schema numbers describe different documents.

| Observation | Raw native source | Meaning and boundary |
|---|---|---|
| `gravity_inverted` | `PlayerObject.m_isUpsideDown`, boolean | Sampled gravity polarity; no gravity magnitude or force calibration. |
| `vehicle_size` | `PlayerObject.m_vehicleSize`, float | Raw vehicle-size value; no collision-box reconstruction. |
| `player_speed` | `PlayerObject.m_playerSpeed`, float | Raw native speed setting; no measured distance/time conversion. |
| `dual_active` | `GJBaseGameLayer.m_gameState.m_isDualMode`, boolean | Sampled active dual state; distinct from a level's initial setting and P2 pointer existence. |

The catalogue preserves the values observed during construction probes. Convenient labels below abbreviate exact JSON numbers; the validator does not use rounding or tolerance.

| Label | Exact sampled value |
|---|---|
| normal size | `1` |
| mini size | `0.6000000238418579` |
| S: slow | `0.699999988079071` |
| N: normal | `0.8999999761581421` |
| F: fast | `1.100000023841858` |
| FF: faster | `1.2999999523162842` |
| FFF: fastest | `1.600000023841858` |

These decimal representations retain widened float32 observations. They are not measured speed multipliers, physical units or human difficulty scores. Numeric values cannot substitute for JSON booleans: `true` does not satisfy a required numeric `1`.

## Declared construction

Every case samples P1 as cube throughout its pre-ending interval. Only the dual case declares active P2 cube coverage. Input times use the `processCommands_call_index` clock; `130/160` means a button-1 press at command 130 and release at 160. All ordinary cases compare their active plan with an empty owned plan.

| Case | Required changing sequence | Owned input plan | Mechanics required in both response samples |
|---|---|---|---|
| `cube-reference` | Gravity false, size 1, speed N, dual false | P1 `60/90` | Normal cube, N, solo |
| `gravity-inverted` | Gravity false → true | P1 `200/230` | Gravity true, size 1, N, solo |
| `gravity-cycle` | Gravity false → true → false | P1 `200/230` | Gravity true, size 1, N, solo |
| `size-mini-cycle` | Size 1 → mini → 1 | P1 `130/160` | Gravity false, mini, N, solo |
| `speed-normal-cycle` | Speed S → N → S | P1 `200/230` | Gravity false, size 1, N, solo |
| `size-mini-speed-fast` | Size 1 → mini → 1; speed N → F → N | P1 `190/220` | Gravity false, mini, F, solo |
| `dual-independent` | Dual false → true → false; active P2 gravity true | P1 `130/160`; P2 `200/230` | Both contrasts require dual true; P1 gravity false, P2 gravity true; size 1 and N |
| `speed-slow-cycle` | Speed N → S → N | P1 `130/160` | Gravity false, size 1, S, solo |
| `speed-fast-cycle` | Speed N → F → N | P1 `130/160` | Gravity false, size 1, F, solo |
| `speed-faster-cycle` | Speed N → FF → N | P1 `130/160` | Gravity false, size 1, FF, solo |
| `speed-fastest-cycle` | Speed N → FFF → N | P1 `130/160` | Gravity false, size 1, FFF, solo |

The exact strings and all unchanged-state requirements are in the catalogue. The shared flat fixture uses a final ordinary block at raw `(600, -15)`. Size and speed cases generally place their entry portal at `(150, 15)` and restoration at `(450, 15)`. Normal-speed coverage starts slow with `kA4,1`, then uses portals 201 and 200; a normal-speed portal placed into an already normal state would supply no changing-state evidence. The mini/fast combination places mini at `(150, 15)`, fast at `(220, 15)`, and both restorations at `(450, 15)`.

Both gravity fixtures add ceiling blocks at raw Y 165, from X 120 through 540 in steps of 30, and an inverted-gravity portal at `(150, 15)`. The cycle adds normal gravity at `(450, 135)`. These placements provide a surface for the inverted cube's later press; acceptance still depends on raw native observations. The cycle requires restoration before native ending. The inverted-only case intentionally has no restoration requirement.

The dual level sets `kA10,1`, enters dual through object 286 at `(150, 15)` and returns to solo through 287 at `(450, 15)`. Its `drop-p1` control retains the complete P2 plan, and `drop-p2` retains the complete P1 plan. Each contrast removes only the channel being examined. The P2 requirements use only active-dual samples; they make no assertion about inactive P2 before entry or after return.

Construction used two development probe sets with 33 and 10 captures, kept separately under ignored `reports/native/mechanics-probe-4aff4018d4bd4f038b778cee7c3bf85c/` and `reports/native/mechanics-followup-90005ba4f3b248249ce9e7d5049a61f1/`. The initial gravity probes completed and recorded native press/release callbacks, but established no `y`/`y_velocity` response for those plans. The retained captures motivated the ceiling and later input. Development probes selected the final requirements; they are not independent confirmatory repeats and are not pooled with the confirming matrix.

Three earlier harness attempts are also retained separately. Startup stopped before an exported capture in `reports/native/mechanics-final-0b11bbd-67b9b205788e4a4d82fd70479600fffd/` and `reports/native/mechanics-final-confirmed-37298b4dc2284ef7bb79848beb99506b/`. Preparation stopped before launch in `reports/native/mechanics-final-confirmed-137132586f5144e7ac2098e1987ed5b1/` because the existing sandbox executable remained locked. None supplied a matrix verdict, and all three four-file restoration audits passed. Preparation now skips a copy only when source/destination SHA-256 values agree; changed contents still require copying and can still report a lock error. A later single startup probe in `reports/native/startup-probe-3141448277aa4aa79cfd911d530a2681/` completed with a temporary system/display execution-state request. This does not establish the cause of the earlier startup failures and is not pooled with the confirming matrix.

## Acceptance contract

`fixture-check` requires the exact level SHA-256, a full `level_start`, the declared input mode and complete owned plan, successful matching native push/release callbacks through terminal, an explicit expected outcome and exact selected mode/mechanics sequences. An observation baseline has no scheduled owned plan and `input_source: unknown`; observed native callbacks, including cleanup releases, remain recorded. Their presence does not establish human authorship.

Mode and mechanics coverage uses trace rows where **both** native phase flags are false: `level_end_animation_started` and `has_completed_level`. Ending-animation and terminal samples cannot satisfy coverage. Each field's sequence is run-length compressed independently, retaining the exact order without adjacent duplicates. Independent field sequences do not by themselves prove that values occurred together. A null requirement declares no coverage; it is not a measured absence. Schema-1/2 native captures cannot satisfy the schema-3 mechanics gate. Active P2 coverage additionally requires actual `dual_active: true` and available P2 samples.

The three active replays must agree over the **whole recorded trace through terminal**. This check does not inherit the pre-ending coverage filter. Schema 3 compares all sampled player fields, including stored P2 values outside active dual, and retains all schema-2 observations. Its 14 exact components are:

```text
planned_inputs_equal                  recorded_inputs_equal
recorded_call_arguments_equal         recorded_player_fields_equal
terminal_callback_and_placement_equal terminal_player_fields_equal
recorded_native_phase_equal           recorded_update_context_equal
delivered_update_records_equal        delivered_scheduler_records_equal
native_phase_events_equal             terminal_phase_and_context_equal
recorded_dual_active_equal             terminal_dual_active_equal
```

The player-field comparison includes position, Y velocity, rotation, death, mode, gravity, size and speed. Layer dual is compared on every trace row and at terminal. Delivered update/Scheduler arguments, their invocation grouping and native phases remain exact. Original incoming time arguments, wall cadence and blocked unknown-origin requests remain diagnostics outside this consistency verdict; see the [clock investigation](clock-investigation.md).

`fixture-response` compares two owned plans. Both captures must pass their own fixture requirements and share environment/collector identity and selected initial state. The selected target-player prefix and raw dual flag must match before the first differing scheduled input. A response requires a difference in declared `y` or `y_velocity` at a shared command index at or after that input, with the target mode, **all non-null mechanics predicates satisfied in both samples**, and both samples preceding native ending. P2 responses always require active dual in both samples. A differing trajectory only after ending, in another mechanic state or before the input change cannot pass. These fields are sampled after `processCommands`; their values at the input callback itself are not established.

A runner case passes only if every capture inspection matches, every response is `selected_response_observed`, the repeated comparison is `recorded_subset_consistent`, and every expected outcome is explicit. Exploratory `any_terminal` cannot close the gate. A structurally valid mismatch can have CLI exit code zero, so the runner consumes JSON verdicts rather than treating command success as measured agreement.

## Reproduction and preserved artifacts

Run from the repository root after the [pinned adapter setup](native-adapter.md). Building alone supplies no execution proof. The runner's default catalogue is still the historical matrix, so select the mechanics catalogue explicitly:

```powershell
uv sync --locked --extra dev
.\.venv\Scripts\python.exe -m axiom fixtures .\examples\native\mechanics-matrix.json
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-native.ps1 -Jobs 4
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-native-matrix.ps1 -GameDirectory 'C:\path\to\Geometry Dash' -MatrixPath .\examples\native\mechanics-matrix.json -Repetitions 3 -ClockPolicy fixed-scheduler-240
```

`fixed-scheduler-240` forwards float32 `1/240` to actual Scheduler callbacks throughout the guarded isolated process. It is an explicit clock intervention, not evidence of 240 wall Hz or ordinary-input equivalence. `native` and `fixed-base-60` experiments belong to separate clock domains. Use `-CaseId dual-independent` for a subset or `-OutputDirectory` for a new evidence directory. Existing output directories are preserved and rejected; repetitions are bounded to 2–16, and an existing sandbox prevents concurrent execution.

The runner records original/validated catalogue digests, evaluator commit and four analysis-file digests, actual collector/environment identity, capture and comparison digests, mechanics availability/sequences, all verdicts and response predicates/first differences. It snapshots and restores bytes and existence of the isolated fixture, replay, AXIOM settings and loader settings, launches hidden, and terminates only its owned process. This is preservation of four experiment files, not a complete personal-save ledger. Raw captures, game binaries/assets and saves stay outside Git. The same-host evidence audit checks retained artifacts; it does not establish independent external replication.

During the matrix the harness temporarily requests Windows system/display execution state, records `startup_execution_state: system_and_display_required_during_matrix`, and restores the previous thread request in `finally`. It changes neither the user's power plan nor game input. That operation is declared harness context; it does not make the otherwise incomplete capture environment exhaustive.

Existing evidence can be checked offline:

```powershell
.\.venv\Scripts\python.exe -m axiom fixture-check .\examples\native\mechanics-matrix.json .\reports\native\mechanics-<id>\gravity-cycle\replay-1.json --case gravity-cycle --run replay
.\.venv\Scripts\python.exe -m axiom fixture-response .\examples\native\mechanics-matrix.json .\reports\native\mechanics-<id>\dual-independent\drop-p2-1.json .\reports\native\mechanics-<id>\dual-independent\replay-1.json --case dual-independent --check p2-response
```

## Primary sources and remaining limits

The field types come from the [pinned Geode 2.2081 bindings](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/GeometryDash.bro#L14799-L14820), including [GJGameState dual](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/GeometryDash.bro#L8958-L8965) and [level header properties](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/GeometryDash.bro#L12637-L12650). `m_playerSpeed` participates in [native X velocity alongside another multiplier](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/inline/PlayerObject.cpp#L338-L340); it is not the entire velocity.

The GD 2.2081 solver's [pinned construction generator](https://github.com/gdsolver/gdsolver/blob/8e8d69ada86a315c71d05cc8b8fe4d369d883aa2/py/mklevel.py#L63-L69) identifies gravity 10/11 and normal/mini size 99/101; its [coordinate observations](https://github.com/gdsolver/gdsolver/blob/8e8d69ada86a315c71d05cc8b8fe4d369d883aa2/py/mklevel.py#L77-L84) describe raw Y plus 90 as world Y. The [archived gd.py ID definitions](https://github.com/nekitdev/gd.py/blob/f2c1c74bdeb55bbe8e1233ec2f04098ef043f5c8/gd/enums.py#L1185-L1219) provide dual/solo 286/287 and speed 200/201/202/203/1334. That older library is construction guidance, not a certificate of current engine behavior. AXIOM's raw native observations decide whether each declared transition and response occurred.

This study covers one selected mode, five raw speed states, two gravity polarities, two size states, one mini/fast combination and one independent-input dual cube layout. It does not cover all combinations or mechanics within those modes. The environment/configuration and selected engine state remain incomplete; hardware-input arrival, ordinary-input equivalence, overhead, interruption/reset/focus behavior, trigger/RNG coverage, checkpoint restoration and richer collisions remain open. M1 remains open. No continuous timing interval, impossibility proof, human capability limit or calibrated real-level Axiom Rating follows from a finite owned replay matrix.
