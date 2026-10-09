# Native fixture matrix

[Русская версия](native-fixture-matrix.ru.md) · [Catalogue](../examples/native/fixture-matrix.json) · [Clock investigation](clock-investigation.md) · [Adapter contract](native-adapter.md)

**Measured result: all 11 declared cases passed their selected-observation, full-repeat and owned-input response gates under `fixed-scheduler-240`.** The 55 executed attempts include 33 repeated replays; each case's three repetitions agreed on all 12 components of the whole recorded-subset comparison. M1, complete-state determinism, ordinary-input equivalence and real-level AR remain open.

The generated catalogue defines 11 cases, nine distinct level payloads and eight selected mode labels. It extends the earlier two-fixture clock experiment with separate input schedules, portal transitions and controls that omit the scheduled input. Encoding a portal or finishing a level cannot satisfy a missing transition or input-response requirement. The catalogue remains `generated_synthetic` with `native_verification: not_recorded`: executed evidence belongs in a separate result manifest, never in a provenance upgrade to the generated specification.

## Executed evidence

The primary matrix ended at **2026-10-09 00:10:28 UTC / 03:10:28 MSK**, with runner exit 0 and `declared_matrix_recorded_subset_passed`. Local evidence is `reports/native/matrix-final-d02172f-20261008/`; the launcher log is `reports/native-matrix-final.log`. There were 53 completions and two deaths: the spike's observation baseline and owned empty-plan control both died at command 102. All 33 active replays completed at command 734. All 55 captures had `recording_complete=true`, zero dropped records and no collector errors; their recorded file digests were checked against the manifest.

| Case | Replay terminal indices, R1 / R2 / R3 | First qualifying response command | Full recorded subset |
|---|---|---|---|
| cube-flat | 734 / 734 / 734 | 60 | consistent, 12/12 |
| cube-spike | 734 / 734 / 734 | 60 | consistent, 12/12 |
| cube-multi-jump | 734 / 734 / 734 | 60 | consistent, 12/12 |
| cube-long-hold | 734 / 734 / 734 | 60 | consistent, 12/12 |
| ship-portal | 734 / 734 / 734 | 131 | consistent, 12/12 |
| ball-portal | 734 / 734 / 734 | 130 | consistent, 12/12 |
| ufo-portal | 734 / 734 / 734 | 131 | consistent, 12/12 |
| wave-portal | 734 / 734 / 734 | 131 | consistent, 12/12 |
| robot-portal | 734 / 734 / 734 | 130 | consistent, 12/12 |
| spider-portal | 734 / 734 / 734 | 130 | consistent, 12/12 |
| swing-portal | 734 / 734 / 734 | 131 | consistent, 12/12 |

All observed mode sequences matched the declarations below. Every response contrast passed both fixture inspections, identity/initial-state/prefix checks and the required shared pre-ending mode check. For example, cube response first differed in `y_velocity` at command 60; spider response first differed in `y` and `y_velocity` at command 130. These observations do not identify hardware timing, hidden state or mode at the input callback.

| Primary matrix identity | Value |
|---|---|
| Result manifest SHA-256 | `57ab118ac29513ab0d1189a1075b7790f2ba8dbf717a5273251af21e1f338c02` |
| Original and validated catalogue SHA-256 | `d4c96260710ec9dc6a23ab7c7ee59ab04dc3077cc7e9b66d20987ac45e697fc5` |
| Evaluator commit | `d02172f77605ff2c2967bcc0aa0d628a57b53c3a` |
| Compiled collector source commit | `de33070f0a62e9576e9aca3d7a86301e6992a7fb` |
| Native source-tree SHA-256 | `de3fd3c1325fe7aac7c5ec33f8e0a4690bb8f37cab6de307e90a357180f23db4` |
| Package SHA-256 | `a670a7e05141500dc195731fd4db4e8ed3b24582ae260f3c02fab8e09eb71bb0` |
| Loaded adapter SHA-256 | `18c651ff3a83c862b308ec45f5d69d355ea15b44d7b0aea842717c447e92a8b0` |
| Environment SHA-256, identical across 55 captures | `eb5b3b0e58393d2146d75f4cca3377092032e17d7c266a31014ae39927dace47` |
| GD 2.2081 executable SHA-256 | `fc5a16c292278bc2e8e078fb1d5023c2bd658322dd72712767ea70c2dd9ec6d0` |
| Geode 5.8.2 loader SHA-256 | `61847e05d4aa416bfd4d1f4e026b5b0e66848756473b285add6233a5cc9356d2` |
| SDK / bindings commits | `2a5fd87433da47d6bf07221774f0cbb25535ae08` / `2a8b5c489ce8b49e7061b0543aa2bc5b22570063` |
| Windows PowerShell 5.1 preservation audit SHA-256 | `00539e488fa41b8e6e274be4d3e7c0b6d697d9596890775e130e357748d85397` |

The manifest also retains evaluator file SHA-256 values: `src/axiom/fixtures.py` = `8a380621ff66d48f332d03541b8f30aa7d3de703d6eb6ad7bba45c18eda72da2`; `src/axiom/native.py` = `fe56524f0328d840193c0b916421e03441c85564ed6fb6b550d58f70eb4e69b6`; `src/axiom/cli.py` = `186ce72d2968a39c9f1f734d67c2698c88bf56624ac4e8cf0ae9d3d7213fee0d`; runner = `1bbafc5eb0b70361a6375cc6a1a41e426470ea5b90c122d1f19407a1d1398d6f`. It records all 55 capture and 11 comparison digests. The collector identity describes the already built package, while evaluator identity describes the code that checked it; they must not be silently equated. The environment lists AXIOM 0.1.0 and Geode 5.8.2 only, with `configuration_complete=false`, hardware arrival unknown and render cadence not captured.

Windows PowerShell 5.1 completed the full matrix. The before/after audit confirms unchanged bytes and existence for the four declared experiment files. Local software validation passed 298 tests and 83 subtests, Ruff and formatting of 42 files. [Windows native CI](https://github.com/TheLitis/AXIOM/actions/runs/37862973488) compiled evaluator/source commit `d02172f`; compilation in CI does not execute the game or authenticate local captures.

The earlier first mode probe (`reports/native/mode-probe-bccd96ee434f40f3ae8c33c34a6caeee/`) stopped after an outdated editable-install path produced `No module named axiom`; its capture remains retained. A first cube integration (`reports/native/matrix-0e0bcebc127c48d5bbbe0365f30d2949/`) reported `declared_matrix_not_established`: an erroneous baseline-empty-events expectation rejected observed release callbacks, although its three replay comparisons and owned response contrast passed. The baseline contract was corrected to retain unknown-origin observed callbacks, and the full 55-attempt matrix was run afresh. These harness failures remain separate evidence; none is a failure hidden inside the final matrix, and the full-repeat comparator was not weakened.

### Separate qualification after rebuilding

A fresh cache build, selected by the package marker at `.tools/native-build-5c3b2a6d41fdb0bf`, was qualified separately on `cube-flat`. It ended at **2026-10-09 00:11:38 UTC / 03:11:38 MSK** in `reports/native/matrix-rebuilt-d02172f-20261009/`, exit 0. Five captures completed at command 734: one baseline, three owned replays and one empty owned control. All fixture checks, all 12 repeat components and the selected response check passed; the four experiment files were preserved. The relocated legacy cache remained unchanged.

| Rebuilt cube-only qualification | Value |
|---|---|
| Result manifest SHA-256 | `7ec2c8d9aa5d7337961be9a28c5297b517a93b7927cea02767ffdfa3f9585f80` |
| Compiled collector source commit | `d02172f77605ff2c2967bcc0aa0d628a57b53c3a` |
| Native source-tree SHA-256 | `de3fd3c1325fe7aac7c5ec33f8e0a4690bb8f37cab6de307e90a357180f23db4` |
| Rebuilt package SHA-256 | `5f396680a968dcf3ddaf87f280107c83908865cdea20f0339735edbb7a64d479` |
| Loaded rebuilt adapter SHA-256 | `bb006e1aa27eec3ae90774f55a9b98341e8b74dfa91fb745c12cc31be8b7096c` |
| Rebuilt environment SHA-256 | `8810f6db2327d78a0e30ccd25f4c419c44ea4c168e623aa6885e781e4e3eb402` |
| Cube repeat comparison SHA-256 | `cb193271f654d83303f039554adb1af284b63a00871dad8d6085c09eae18df57` |

The native source-tree digest is unchanged, but compiled provenance, package/DLL hashes and environment identity differ. These five captures are not pooled with the primary 55, and this qualification does not establish the other ten cases for the rebuilt binary. A further artifact audit passed 1,329 assertions for the primary matrix and 150 for this qualification, checking hashes, identities, modes, input plans, state prefixes and recorded verdicts. It ran on the same host and is reader/consistency verification, not an independent external reproduction of engine execution.

## Declared cases

Every case starts as a classic cube run from the genuine beginning. The first four cases use two payloads with different input plans. Seven additional payloads place the target-mode portal at raw coordinates `(150, 15)`, a cube portal at `(300, 15)` and the endpoint block at `(600, -15)`. Exact UTF-8 strings and their SHA-256 digests are in the catalogue.

| Case | Repeated plan: player 1, button 1 | Required pre-ending mode sequence in repeated replay | Observation baseline and empty-plan control |
|---|---|---|---|
| `cube-flat` | Press 60, release 90 | cube | cube; completed |
| `cube-spike` | Press 60, release 90 | cube | cube; died |
| `cube-multi-jump` | Press/release 60/90, 220/250, 380/410 | cube | cube; completed |
| `cube-long-hold` | Press 60, release 300 | cube | cube; completed |
| `ship-portal` | Press 130, release 160 | cube → ship → cube | cube → ship → cube; completed |
| `ball-portal` | Press 130, release 160 | cube → ball | cube → ball → cube; completed |
| `ufo-portal` | Press 130, release 160 | cube → ufo → cube | cube → ufo → cube; completed |
| `wave-portal` | Press 130, release 160 | cube → wave → cube | cube → wave → cube; completed |
| `robot-portal` | Press 130, release 160 | cube → robot → cube | cube → robot → cube; completed |
| `spider-portal` | Press 130, release 160 | cube → spider | cube → spider → cube; completed |
| `swing-portal` | Press 130, release 160 | cube → swing | cube → swing → cube; completed |

All repeated plans require `completed`. Numbers in the plan column are `processCommands` call indices, not assumed rendered frames, wall-time intervals or independently verified physics ticks. The multi-jump case checks its complete three-pair schedule and selected response; it does not separately infer that each press caused a jump. Likewise, long hold is a scheduled held interval, not a calibrated model of automatic jumping.

For ball, spider and swing, the active replay's declared trajectory misses the return portal. Its required sequence therefore ends in the target mode. These cases do **not** claim a return cycle in the repeated replay. The no-input trajectories separately require the return to cube. Terminal or finish-animation mode changes cannot repair a missing pre-ending transition.

## What closes a case gate

The default runner collects five separate full-start attempts per case: one observation baseline, three repetitions of the owned-input plan and one owned-input replay with an empty plan. For the complete catalogue, this schedules 55 attempts. The baseline has no scheduled owned plan, forwards observed input and retains its callbacks under the `unknown` input source, including possible native cleanup releases. It does not infer that an observed event came from a person. The empty-plan control runs the same owned handler policy as the active replay. These runs answer different questions and are not interchangeable repetition baselines.

Each capture must pass the native structure/integrity reader and match the requested effective clock policy. The fixture inspector additionally requires the exact level digest, `level_start`, input mode and plan, complete execution of the plan, the specified terminal outcome and successful native player push/release records for every scheduled event. A `requested` input record alone is insufficient. A true native callback return is a recorded return value, not proof of hardware arrival or complete game input semantics.

Mode requirements compare exact run-length sequences of the selected mode label after each `processCommands` call. Only schema-2 trace rows with both raw native phase flags false enter this check: `level_end_animation_started` and `has_completed_level`. Ending-animation and terminal samples are excluded. Schema 1 cannot establish this coverage. A null player-2 requirement means no P2 coverage is claimed; a player pointer alone does not establish an active dual mode.

The three repeated replays must pass `native-compare` over the **whole recorded run through the terminal callback**. The earlier exact contract remains: inputs and plans, command arguments and flags, selected player fields including rotation, native phases, delivered update and Scheduler records, invocation grouping, phase events and terminal placement/context/state. Pre-ending mode coverage never shortens this repeat comparison. Original incoming update arguments, wall timings and blocked unknown-origin requests remain separate diagnostics, as documented in the [clock investigation](clock-investigation.md).

Each case also compares the empty owned plan with the active owned plan. Both captures must satisfy their respective fixture requirements and share the environment and collector identity, selected initial state and selected player-state prefix before the first differing scheduled input. At a shared command index at or after that input, **both** sampled players must still have the declared target mode and both samples must precede the native ending. A difference in `y` or `y_velocity` then establishes `selected_response_observed`. A difference only after ending, in the wrong mode or before the input change cannot pass. These are selected-state observations; they do not establish equality of hidden engine state or mode at the input callback itself.

A runner case passes only when all its observation checks, full-repeat comparison and response checks pass and all expected outcomes are explicit. The exploratory `any_terminal` option is valid for investigation but cannot close the runner's case gate. Missing effects, unexpected modes and failed comparisons remain recorded failures.

## Local operation

Run from the repository root using a lawful local GD installation. Follow the [adapter's pinned build and sandbox procedure](native-adapter.md) first; a successful build does not launch or validate the game. The matrix uses the existing schema-2 adapter without changing its native fields.

```powershell
uv sync --locked --extra dev
.\.venv\Scripts\python.exe -m axiom fixtures .\examples\native\fixture-matrix.json
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build-native.ps1 -Jobs 4
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run-native-matrix.ps1 -GameDirectory 'C:\path\to\Geometry Dash' -Repetitions 3
```

The matrix defaults to `fixed-scheduler-240`: float32 `1/240` is forwarded once to each actual Scheduler callback throughout the guarded sandbox process. This is an explicit clock intervention, not a claim that the process runs at 240 wall Hz or preserves ordinary gameplay. `native` and `fixed-base-60` can be selected for separate experiments; their results must not be pooled with the fixed-Scheduler domain.

Use `-CaseId ship-portal` for a single case, `-MatrixPath` for a different validated catalogue, or `-OutputDirectory` for a new evidence directory. A selected subset establishes only its own cases. Repetitions are bounded to 2–16. An existing output directory is rejected and preserved; a running sandbox prevents a concurrent experiment. New default output goes under ignored `reports/native/matrix-<id>/`.

The runner preserves baseline/replay/control captures, their native and fixture inspections, the actual replay plans, full comparison results and response contrasts. `matrix-result.json` records effective clock policy, both the original and validated catalogue digests, evaluator commit and file digests, native collector/environment identity, capture/comparison digests, each observed mode sequence and each verdict. Evaluator provenance and the collector's compiled source identity describe different components. Read the JSON statuses: `fixture-check` and `fixture-response` can exit successfully after producing a valid **mismatch** result. CLI success alone is not a case pass.

Before preparation the runner snapshots bytes and existence of the isolated fixture, replay and AXIOM/loader settings. Its `finally` restores them, including on failure. It launches hidden and terminates only the process it owns. This preservation covers those local experiment files; it is not a full personal-save before/after ledger. Raw captures, reports, proprietary binaries/assets and saves remain outside Git. Public documentation may publish curated results and identities after the executed evidence is checked.

Offline inspection of an existing evidence directory requires no game launch:

```powershell
.\.venv\Scripts\python.exe -m axiom fixture-check .\examples\native\fixture-matrix.json .\reports\native\matrix-<id>\ship-portal\replay-1.json --case ship-portal --run replay
.\.venv\Scripts\python.exe -m axiom fixture-response .\examples\native\fixture-matrix.json .\reports\native\matrix-<id>\ship-portal\skip-input-1.json .\reports\native\matrix-<id>\ship-portal\replay-1.json --case ship-portal --check ship-response
```

## Sources and boundaries

The mode portal IDs come from the GD 2.2081 solver's [pinned calibration generator](https://github.com/gdsolver/gdsolver/blob/8e8d69ada86a315c71d05cc8b8fe4d369d883aa2/py/mklevel.py#L63-L74): cube 12, ship 13, ball 47, UFO 111, wave 660, robot 745, spider 1331 and swing 1933. Its [coordinate observations](https://github.com/gdsolver/gdsolver/blob/8e8d69ada86a315c71d05cc8b8fe4d369d883aa2/py/mklevel.py#L77-L84) describe raw level Y plus 90 as engine-world Y. These references guide construction; AXIOM's actual native observations decide whether its declared sequence occurred. A source comment or object ID cannot certify an untested fixture.

The adapter derives its selected mode from the raw PlayerObject flags in the [pinned 2.2081 bindings](https://github.com/geode-sdk/bindings/blob/2a8b5c489ce8b49e7061b0543aa2bc5b22570063/bindings/2.2081/GeometryDash.bro#L14799-L14820). Those labels do not measure gravity polarity, vehicle size, speed, collision geometry or active dual state. Eight observed labels on small constructed levels do not establish support for every mechanic in those modes. This finite matrix does not provide a reliability estimate for untested levels or configurations.

M1 remains open for ordinary-input equivalence, complete configuration/state coverage, pause/focus/reset/interruption behavior, RNG and triggers, size/speed/gravity/dual combinations, collision-rich levels, overhead and checkpoint restoration. Continuous timing windows and human learning/performance calibration remain later gates. A completed macro and an observed response do not prove physical impossibility of another route, a human limit or a real-level Axiom Rating.
