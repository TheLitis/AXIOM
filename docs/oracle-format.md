# Terminal oracle ledgers · v1

`axiom trials examples/trials.json --json reports/oracle-check.json`

Current support checks supplied ledgers; it does not execute Geometry Dash, authenticate a producer or prove replay validity. The native adapter remains a planned milestone.

The `schema_version: 1`, `kind: "oracle_trials"` ledger fixes challenge identity, engine build, exact initial-state and replay SHA256 hashes, replay event count, `full_run: true`, provenance (`synthetic` or `engine-capture`) and trial records. Each record contains a unique ID, one `offsets_ms` per replay event, `outcome` (`completed`, `died`, `error`), measured `elapsed_seconds` and a terminal-state SHA256 for completed/dead outcomes. Optional repeated challenge/initial-state descriptors must match the ledger. Segment-only records are rejected.

Identical offset vectors are compared for repeatability of both terminal outcome and state hash. A consistent set of observed repeats is necessary but insufficient for native engine validation. Errors remain unknown outcomes and are never counted as deaths. A reported completion is evidence supplied by the producer, not independent proof of physical feasibility.

Finite successful vectors do not justify interpolation to a continuous timing interval. All-failed trials do not prove the absence of a solution. The chosen grid is not a random human sample: this command never computes a human success rate, T50 or AR.

The richer proposed live capture protocol is specified in [telemetry-protocol.md](telemetry-protocol.md). Public examples are synthetic, with placeholder hashes explicitly labelled.
