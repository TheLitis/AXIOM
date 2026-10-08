# Proposed native telemetry protocol

Status: **target protocol; partially covered by an experimental native adapter**. The released v0.1.0 offline prototype consumes supplied files and observations. Current development adds opt-in Windows x64 / GD 2.2081 / Geode 5.8.2 capture and command replay; its [operation and limits](native-adapter.md), [implemented capture/replay schema](../native/README.md#capture-semantics), and [clock investigation](clock-investigation.md) are separate from the broader design below. Campaign enrollment, the complete focus/latency contract, future-relevant snapshots, validated timing windows and human calibration are not implemented by that limited collector. The full M1 gate remains open; there is no background input collection.

## Consent and capture scope

Recording is opt-in and visible in the game. Capture gameplay input only while the declared play layer has focus; pause capture on focus loss and outside that scope. Never install a system-wide key logger or record password fields, chat, clipboard, unrelated applications, or raw account identifiers. Use a project-local pseudonym with an optional privately stored identity mapping. Keep capture local by default; data sharing is separately opt-in.

The player can inspect, export, and delete local records. Agree on dataset withdrawal, retention, redistribution permission and any public pseudonym before enrollment. Consent version belongs in every exported campaign. Shared traces can still be identifying through level choice or timing patterns; minimization and release review are required.

## Identity hierarchy

| Record | Stable identifiers and minimum fields |
|---|---|
| Environment | Game build/binary hash; adapter/Geode build; OS/device categories; mods and configuration hashes; physics/update rules; render cadence; input policy and resolution; measured latency method; display/audio/detail settings |
| Challenge | Original level ID/name labels; exact raw payload SHA-256 and serialization; challenge-manifest hash; information and practice policies |
| Participant | Pseudonym; consent version; initial skill/profile measurement method; prior familiarity and known prior practice; recruitment cohort |
| Campaign | Participant + challenge + protocol; fresh start or late-entry status; practice accumulated before recording; start/end; completion or censoring reason; recording gaps |
| Session | Campaign; schedule/start/end; active practice total; pauses/rest; warmup; device or strategy changes |
| Attempt | Session and monotonic sequence; start mode/checkpoint; replay hash; initial-state digest; accumulated practice; outcome; stop time; reached sections; evidence package |
| Event | Run/attempt ID; sequence; simulation time and clock representation; monotonic capture timestamp; player/button; press/release; actual engine acceptance timestamp; source |

Treat a configuration or level revision change as a new challenge or an explicit campaign transition. Do not pool it silently. Practice starts, full starts, checkpoint retries and replay automation are distinguishable modes. An automated witness is not a human completion observation.

## Time and event semantics

Use integer ticks plus explicit tick duration/subtick fields where available; preserve source precision and state seconds conversion rules. Store monotonic wall-clock capture time separately from simulation time. No assumption that render frame, physics tick, polling period and input acceptance time are identical is permitted.

Record both presses and releases, player channel, button identity, held-state transitions, ordering of simultaneous events, buffered events, and rejected/delayed inputs. Include focus loss, pause, reset, game speed and update discontinuities. If the adapter cannot observe physical device arrival or display latency, mark it unknown rather than deriving it from gameplay callbacks.

Define active practice using a versioned policy. Exclude inactive breaks but include permitted preparation, failures and restart time; preserve raw durations so alternative policies can be audited. Keep calendar/rest schedule alongside accumulated active time. Do not infer total prior practice from the visible attempt counter.

## Outcome oracle and run evidence

Outcomes are `completed`, `dead`, `aborted`, `horizon_reached`, or `unknown`. `completed` requires the actual final engine completion event in an unmodified permitted run from the required start. Preserve the observer hook, tick, level hash, attempt ID and relevant event evidence. A progress percentage, imported macro label, living player at a short horizon, or end-screen image alone does not satisfy this contract.

Store death location/cause when observable, reached-section entries, and future-relevant boundary state. Boundary snapshots include both players' position/velocity/mode/size/gravity/holds, collision state, world/object/trigger state, clocks/random state, and any additional version-specific dependencies. This list is not a proof of completeness; validate restoration against continued full runs and record missing capabilities.

Attach all identity, inputs, state digests, boundaries and outcomes to one `run_id`. A verification bundle must not assemble a successful finish from a different run or configuration. Human-controller observation data and privileged physical state are separate streams with enforced access boundaries.

## Campaign observations for survival analysis

Export one first-completion/censor record per defined player-challenge campaign, linked to its attempts and sessions. Include event flag, cumulative active time, prior practice, cohort/protocol, follow-up start/end, recording gaps and censor reason. Incomplete ongoing campaigns and participants who stop must be retained.

Distinguish administrative study end, lost contact, deliberate quitting, technical interruption, and challenge changes. Quitting can be informative censoring; a reason code does not fix that bias automatically. Unknown earlier completion or unobserved practice invalidates a simple fresh-start first-completion analysis unless handled in its model. Repeated campaigns from one participant cannot be counted as independent people.

Late-section exposure records begin when the attempt actually reaches the section. Their denominator is entrants, while full-attempt success uses genuine full starts. Store both to avoid survivor-selection mistakes.

## Quality gates before release

Validate record ordering, duplicate IDs, impossible negative durations, pressed-state consistency, completeness, clock conversions, identity mismatches and missing outcomes. Hash immutable raw files; derived datasets carry code/version and exclusion reasons. Publish a capture-quality report, failure/dropout counts, risk counts over time and model exclusions.

Run consented native replay controls and verify [architecture acceptance gates](architecture.md#native-acceptance-gates). A schema-valid file is not independently verified measurement. Public datasets should minimize identifiers and retain a clear license/consent statement. Statistical interpretation follows the [methodology](methodology.md), including informative dropout and held-out evaluation.
