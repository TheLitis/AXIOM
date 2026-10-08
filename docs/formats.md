# Input formats and provenance

AXIOM's initial importers inspect local files. Their output is `metadata_only`:
no import establishes collision geometry, physical feasibility, replay success,
human ability, or Axiom Rating. Never use editor object counts as a difficulty
score. Keep each source file with its licensing and recording provenance.

## Geometry Dash inner level strings

`inspect_level(path)` accepts raw UTF-8 text. The first semicolon-separated record
is the level-start settings; subsequent records are objects. Each record contains
comma-separated key/value pairs. For example:

```text
kA2,0,kA4,1;1,1,2,15,3,15;1,8,2,45,3,15;
```

The parser preserves property order and every value as a string, including unknown
keys. It additionally reports object ID (`1`) and optional editor X/Y coordinates
(`2`, `3`). Missing coordinates remain unknown. Bounds describe the supplied
coordinates, including decoration and triggers; they are not hitboxes, level
length, a player route, or evidence of an available timing window. A versioned
runtime adapter must resolve game-specific meanings separately. The syntax and
these three field meanings are documented by the community-maintained
[GDDocs object resource](https://github.com/gd-programming/gd.docs/blob/main/docs/resources/client/level-components/level-object.md)
and [inner-string resource](https://github.com/gd-programming/gd.docs/blob/main/docs/resources/client/level-components/inner-level-string.md).
These resources are useful format references, not RobTop specifications or a
validated physics implementation.

Compression must be selected explicitly:

```python
from axiom.ingest import inspect_level

raw = inspect_level("level.txt")
gzipped = inspect_level("level.b64", encoding="base64-gzip")
zipped = inspect_level("level.b64", encoding="base64-zlib")
```

Both compressed encodings use URL-safe base64 with optional padding and ASCII
whitespace. This follows the encoding family described in
[GDDocs encoding/decoding](https://github.com/gd-programming/gd.docs/blob/main/docs/topics/levelstring_encoding_decoding.md).
AXIOM requires one complete gzip or zlib stream, rejects trailing data and
concatenated streams, and bounds decompressed output. It does not infer encoding,
read save files or `.gmd` containers, contact game servers, or restore removed
headers from built-in level resources.

`source.sha256` hashes the exact input bytes, including BOM, newlines and compressed
representation. `decoded_sha256` hashes the exact decoded bytes before text
normalization. The parsed view accepts one trailing semicolon and surrounding
CR/LF only. Identical parsed objects can therefore have different source hashes.
Neither hash incorporates game version, input policy, mods or device conditions:
a complete trial identity must record those alongside the hash.

The default source and decoded byte limits are 16 MiB. A level may contain at most
200,000 objects and 2,048 properties per record. Duplicate keys, odd key/value
counts, empty interior records, nonfinite numeric values, control characters,
invalid IDs and malformed coordinates raise `ValueError`. Unknown strings remain
opaque; composite field syntax and runtime behavior are not validated.

## GDR 1 JSON replay import

`inspect_replay(path)` imports only the upstream GDR 1 JSON representation,
usually named `.gdr.json`. The implementation follows the
[upstream serialization source pinned at commit 77bd505](https://github.com/maxnut/GDReplayFormat/blob/77bd505853541a87a12895dc23de05f6585d0515/include/gdr/gdr.hpp)
and the [GDR 1 README](https://github.com/maxnut/GDReplayFormat/blob/77bd505853541a87a12895dc23de05f6585d0515/README.md).
Required root fields are `version` (1), `gameVersion`, `description`, `duration`,
`bot`, `level`, `author`, `seed`, `coins`, `ldm`, and `inputs`. `bot` contains string
`name` and `version`; `level` contains string `name` and unsigned integer `id`.
Root extensions and per-input extensions are retained.

Each input requires exactly typed core values:

| Upstream field | Accepted value | Normalized meaning |
| --- | --- | --- |
| `frame` | Integer 0 through 2^32 − 1 | Frame index, kept exactly |
| `btn` | Nonnegative signed-32-bit integer | Button ID, kept exactly |
| `2p` | JSON boolean | `player` 1 or 2 |
| `down` | JSON boolean | `action` `press` or `release` |

Button names 1=jump, 2=left, 3=right follow the upstream PlayerButton convention;
other IDs receive `button_name: "unknown"` and retain their ID. See the
[current upstream input declaration](https://github.com/maxnut/GDReplayFormat/blob/gdr2/include/gdr/gdr.hpp).
Input order is preserved, including simultaneous events. Unordered frame indices
are flagged, not silently sorted. A release without a preceding press can belong
to a partial capture; AXIOM does not invent a preceding event.

An explicitly supplied positive `framerate` permits the declared conversion
`time_seconds = frame / framerate`. Otherwise `frames_per_second` and every
`time_seconds` are `null`. Although upstream supplies a default rate, AXIOM does
not fill missing recording evidence with that default. The conversion assumes
the declared rate remains constant. No refresh rate, latency, wall-clock duration,
subframe timestamp or human timing window is inferred. The upstream `duration`
field is retained as metadata and is not substituted for missing frame units.

Binary MessagePack GDR and newer GDR2 are unsupported. GDR2 uses a different
binary layout; see [upstream migration documentation](https://github.com/maxnut/GDReplayFormat#migrating-from-gdr-1).
Do not rename arbitrary bot JSON to GDR or translate fields by guesswork.
Bot position/frame-correction extensions are preserved but never executed;
recording one sequence does not show that the unmodified game accepted it.

Replay imports are limited to 16 MiB, 200,000 events and 64 JSON nesting levels.
Duplicate JSON keys, nonfinite numbers, unsupported versions, coercions such as
`"true"` or `1` for a boolean, and invalid core fields raise `ValueError`.

`examples/replays/synthetic.gdr.json` is an authored format fixture. It is not a
recorded real level or calibration observation. Importing it is a demonstration
of normalization and provenance only.

Sources checked on 2026-10-08. Pin any future runtime or replay adapter to a
specific version and validate it on recorded fixtures before claiming support.
