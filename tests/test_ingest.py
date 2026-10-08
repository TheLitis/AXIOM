"""Checks for preservation, explicit units and bounded untrusted imports."""

import base64
import gzip
import hashlib
import json
import tempfile
import unittest
import zlib
from pathlib import Path

from axiom.ingest import decode_level_bytes, inspect_level, inspect_replay, parse_gdr_json, parse_level_string

LEVEL = "kA2,0,kFuture,opaque;1,1,2,15.5,3,-4,999,new-field;1,8,2,30,3,0;"


def replay(**updates):
    value = {
        "version": 1.0,
        "gameVersion": 2.204,
        "description": "Synthetic format fixture; not a recorded completion.",
        "duration": 1.0,
        "bot": {"name": "AXIOM fixture", "version": "0.1"},
        "level": {"id": 0, "name": "Synthetic fixture"},
        "author": "AXIOM contributors",
        "seed": 0,
        "coins": 0,
        "ldm": False,
        "framerate": 240.0,
        "inputs": [
            {"frame": 0, "btn": 1, "2p": False, "down": True},
            {"frame": 12, "btn": 1, "2p": False, "down": False},
            {"frame": 12, "btn": 2, "2p": True, "down": True},
        ],
    }
    value.update(updates)
    return value


class LevelImportTests(unittest.TestCase):
    def test_preserves_raw_unknown_fields_and_record_order(self):
        parsed = parse_level_string(LEVEL)
        records = [parsed["settings"], *(item["properties"] for item in parsed["objects"])]
        reconstructed = (
            ";".join(",".join(part for pair in record.items() for part in pair) for record in records) + ";"
        )
        self.assertEqual(reconstructed, LEVEL)
        self.assertEqual(parsed["objects"][0]["properties"]["999"], "new-field")
        self.assertEqual(parsed["summary"]["object_id_counts"], {"1": 1, "8": 1})
        self.assertEqual(
            parsed["summary"]["editor_bounds"], {"x_min": 15.5, "x_max": 30.0, "y_min": -4.0, "y_max": 0.0}
        )

    def test_hashes_exact_source_bytes_and_decoded_bytes(self):
        data = b"\xef\xbb\xbf" + LEVEL.encode() + b"\r\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.level"
            path.write_bytes(data)
            result = inspect_level(path)
        self.assertEqual(result["source"]["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(result["decoded_sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(result["status"], "metadata_only")
        self.assertNotIn("rating", result)

    def test_compression_roundtrip_is_explicit(self):
        data = LEVEL.encode()
        for encoding, compressed in (
            ("base64-gzip", gzip.compress(data)),
            ("base64-zlib", zlib.compress(data)),
        ):
            with self.subTest(encoding=encoding):
                encoded = base64.urlsafe_b64encode(compressed)
                self.assertEqual(decode_level_bytes(encoded, encoding=encoding), data)
                self.assertEqual(
                    decode_level_bytes(b"\n" + encoded.rstrip(b"=") + b"\r\n", encoding=encoding), data
                )
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "compressed.level"
                    path.write_bytes(encoded)
                    result = inspect_level(path, encoding=encoding)
                    with self.assertRaises(ValueError):
                        inspect_level(path)
                self.assertEqual(result["decoded_sha256"], hashlib.sha256(data).hexdigest())
                self.assertEqual(result["source"]["sha256"], hashlib.sha256(encoded).hexdigest())

    def test_empty_level_and_missing_coordinates_are_metadata(self):
        self.assertEqual(parse_level_string(";")["summary"]["object_count"], 0)
        item = parse_level_string(";1,1;")
        self.assertIsNone(item["objects"][0]["x"])
        self.assertEqual(item["summary"]["objects_without_complete_coordinates"], 1)

    def test_malformed_and_nonfinite_level_data_rejected(self):
        values = [
            "",
            "1,1,2,0",
            "kA1;1,1;",
            ";1,1,2;",
            ";1,1,1,2;",
            ";1,1;;1,2;",
            ";2,0,3,0;",
            ";1,0;",
            ";1,4294967296;",
            ";1,1,2,NaN;",
            ";1,1,2,Infinity;",
            ";1,1,3,1e999;",
            ";1,1,999,-inf;",
            ";1,1,2,wrong;",
            ";1,1,2,1\x00;",
            ";1,1, 2,4;",
            ";1,1;,x;",
        ]
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_level_string(value)

    def test_size_and_record_limits(self):
        with self.assertRaises(ValueError):
            parse_level_string(LEVEL, max_objects=1)
        with self.assertRaises(ValueError):
            decode_level_bytes(b"too big", max_bytes=3)
        encoded = base64.urlsafe_b64encode(gzip.compress(b"a" * 10_000))
        with self.assertRaisesRegex(ValueError, "decoded level exceeds"):
            decode_level_bytes(encoded, encoding="base64-gzip", max_bytes=512)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.level"
            path.write_bytes(b"a" * 100)
            with self.assertRaises(ValueError):
                inspect_level(path, max_bytes=32)

    def test_corrupt_truncated_wrong_and_concatenated_compression(self):
        compressed = gzip.compress(LEVEL.encode())
        values = [
            b"*bad*",
            b"a",
            b"=AAA",
            b"Zg===",
            b"Zh==",
            base64.urlsafe_b64encode(b"not gzip"),
            base64.urlsafe_b64encode(compressed[:-2]),
            base64.urlsafe_b64encode(compressed + b"junk"),
            base64.urlsafe_b64encode(compressed + compressed),
        ]
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                decode_level_bytes(value, encoding="base64-gzip")
        with self.assertRaises(ValueError):
            decode_level_bytes(base64.urlsafe_b64encode(compressed), encoding="base64-zlib")
        with self.assertRaises(ValueError):
            decode_level_bytes(b"abc", encoding="automatic")


class ReplayImportTests(unittest.TestCase):
    def test_normalizes_buttons_players_releases_and_declared_units(self):
        original = replay()
        original["inputs"][1]["position"] = {"x": 99.0}
        original["extension"] = {"opaque": ["do not execute"]}
        parsed = parse_gdr_json(json.dumps(original))
        events = parsed["events"]
        self.assertEqual([event["action"] for event in events], ["press", "release", "press"])
        self.assertEqual([event["player"] for event in events], [1, 1, 2])
        self.assertEqual(events[1]["time_seconds"], 0.05)
        self.assertEqual(events[2]["button_name"], "left")
        self.assertEqual(events[1]["extensions"], {"position": {"x": 99.0}})
        self.assertEqual(parsed["metadata"]["extension"], original["extension"])
        # Recreate the upstream JSON representation from the normalized values.
        rebuilt = dict(parsed["metadata"])
        rebuilt["inputs"] = [
            {
                "frame": event["frame"],
                "btn": event["button"],
                "2p": event["player"] == 2,
                "down": event["action"] == "press",
                **event["extensions"],
            }
            for event in events
        ]
        self.assertEqual(rebuilt, original)

    def test_missing_framerate_remains_unknown_despite_upstream_default(self):
        original = replay()
        del original["framerate"]
        parsed = parse_gdr_json(json.dumps(original))
        self.assertIsNone(parsed["timebase"]["frames_per_second"])
        self.assertEqual(parsed["timebase"]["source"], "unknown")
        self.assertTrue(all(event["time_seconds"] is None for event in parsed["events"]))

    def test_does_not_reorder_simultaneous_or_out_of_order_events(self):
        original = replay()
        original["inputs"] = [original["inputs"][2], original["inputs"][1], original["inputs"][0]]
        parsed = parse_gdr_json(json.dumps(original))
        self.assertEqual([event["frame"] for event in parsed["events"]], [12, 12, 0])
        self.assertFalse(parsed["summary"]["ordered_by_frame"])
        self.assertEqual(parsed["events"][0]["player"], 2)

    def test_unknown_button_id_is_preserved_without_guessing(self):
        original = replay()
        original["inputs"][0]["btn"] = 99
        parsed = parse_gdr_json(json.dumps(original))
        self.assertEqual(parsed["events"][0]["button"], 99)
        self.assertEqual(parsed["events"][0]["button_name"], "unknown")

    def test_replay_file_provenance(self):
        data = json.dumps(replay(), indent=2).encode()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.gdr.json"
            path.write_bytes(data)
            result = inspect_replay(path)
        self.assertEqual(result["source"]["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(result["summary"]["event_count"], 3)

    def test_malformed_json_nonfinite_numbers_and_duplicate_keys(self):
        for text in (
            "[]",
            "{",
            '{"version":1,"version":2}',
            '{"value":NaN}',
            '{"value":1e999}',
            '{"value":"\\ud800"}',
            b"\xff\xfe",
            b"GDR\x02\x00",
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_gdr_json(text)
        duplicate_input = json.dumps(replay()).replace('"frame": 0', '"frame": 0, "frame": 1')
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_gdr_json(duplicate_input)

    def test_only_documented_gdr1_shape_and_types_are_accepted(self):
        for updates in (
            {"version": 2},
            {"version": True},
            {"framerate": 0},
            {"framerate": -1},
            {"framerate": True},
            {"duration": -1},
            {"gameVersion": "2.2"},
            {"bot": {"name": "x", "version": 1}},
            {"level": {"name": "x", "id": True}},
            {"inputs": None},
            {"ldm": 0},
        ):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                parse_gdr_json(json.dumps(replay(**updates)))
        for key in ("version", "bot", "level", "inputs"):
            original = replay()
            del original[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                parse_gdr_json(json.dumps(original))

    def test_input_types_and_ranges(self):
        for updates in (
            {"frame": -1},
            {"frame": 1.5},
            {"frame": True},
            {"frame": 1 << 32},
            {"btn": "jump"},
            {"btn": -1},
            {"2p": 1},
            {"down": "true"},
        ):
            original = replay()
            original["inputs"][0].update(updates)
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                parse_gdr_json(json.dumps(original))
        with self.assertRaisesRegex(ValueError, "nonfinite timestamp"):
            parse_gdr_json(json.dumps(replay(framerate=1e-320)))

    def test_event_size_and_nesting_limits(self):
        with self.assertRaises(ValueError):
            parse_gdr_json(json.dumps(replay()), max_events=2)
        with self.assertRaisesRegex(ValueError, "nesting"):
            parse_gdr_json("[" * 65 + "0" + "]" * 65)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.json"
            path.write_bytes(b" " * 100)
            with self.assertRaises(ValueError):
                inspect_replay(path, max_bytes=32)


if __name__ == "__main__":
    unittest.main()
