"""Pinned raw-key transformations do not guess unrecorded keyboard layouts."""

import pytest
from test_native import save
from test_windowsinput import windows_capture

from axiom.native import inspect_native_capture


@pytest.mark.parametrize(
    ("vkey", "scan", "extended", "native", "status"),
    [
        (0x11, 0x1D, 0, 0xA2, "e0_control_side"),
        (0x11, 0x1D, 2, 0xA3, "e0_control_side"),
        (0x12, 0x38, 0, 0xA4, "e0_alt_side"),
        (0x12, 0x38, 2, 0xA5, "e0_alt_side"),
        (0xA0, 0x2A, 0, 0xA0, "unchanged_raw_vkey"),
        (0xA1, 0x36, 0, 0xA1, "unchanged_raw_vkey"),
    ],
)
@pytest.mark.parametrize("action", ["press", "repeat", "release"])
def test_modifier_candidates_preserve_raw_and_sdk_namespaces(
    tmp_path, vkey, scan, extended, native, status, action
):
    data = windows_capture()
    raw = data["attempt"]["windows_input"]["messages"][0]["raw_input"]
    raw.update(vkey=vkey, scan_code=scan, flags=extended | (action == "release"))
    raw["keyboard_message"] = 257 if action == "release" else 256
    sdk = data["attempt"]["windows_input"]["sdk_events"][0]["data"]
    sdk.update(native_code=native, native_extra=scan, action=action)
    summary = inspect_native_capture(save(tmp_path, data))["windows_input_observations"]
    assert summary["protocol"] == "windows-raw-sdk-ui-compatible-candidates-v2"
    assert summary["sdk_events"][0]["compatible_windows_message_sequences"] == [0]
    assert summary["messages"][0]["raw_input"] == raw
    assert summary["sdk_events"][0]["data"] == sdk
    assert summary["raw_keyboard_normalizations"] == [
        {"message_sequence": 0, "source_vkey": vkey, "status": status, "expected_sdk_native_code": native}
    ]
    assert summary["ordinary_os_input_equivalence"] == "not_established"


@pytest.mark.parametrize(("vkey", "native"), [(0x11, 0xA3), (0x12, 0xA5), (0x11, 0x11), (0x12, 0x12)])
def test_wrong_side_or_untransformed_sdk_code_is_not_a_candidate(tmp_path, vkey, native):
    data = windows_capture()
    data["attempt"]["windows_input"]["messages"][0]["raw_input"]["vkey"] = vkey
    data["attempt"]["windows_input"]["sdk_events"][0]["data"]["native_code"] = native
    summary = inspect_native_capture(save(tmp_path, data))["windows_input_observations"]
    assert summary["sdk_events"][0]["compatible_windows_message_sequences"] == []


@pytest.mark.parametrize(
    ("vkey", "native"), [(0x10, 0xA0), (0x10, 0xA1), (0x10, 0x10), (0, 0), (0xFF, 0xFF), (0xFF, 87)]
)
def test_missing_layout_mapping_is_explicit_and_never_guessed(tmp_path, vkey, native):
    data = windows_capture()
    data["attempt"]["windows_input"]["messages"][0]["raw_input"].update(vkey=vkey, scan_code=0x2A)
    data["attempt"]["windows_input"]["sdk_events"][0]["data"].update(native_code=native, native_extra=0x2A)
    summary = inspect_native_capture(save(tmp_path, data))["windows_input_observations"]
    assert summary["sdk_events"][0]["compatible_windows_message_sequences"] == []
    mapping = summary["raw_keyboard_normalizations"][0]
    assert mapping["status"] == "keyboard_layout_mapping_not_recorded"
    assert mapping["expected_sdk_native_code"] is None


def test_normalization_keeps_same_side_ambiguity_and_timestamp_bounds(tmp_path):
    from test_windowsinput import message

    data = windows_capture()
    windows = data["attempt"]["windows_input"]
    windows["messages"].append(message(sequence=1, enter=410_000, exit_time=450_000))
    for row in windows["messages"]:
        row["raw_input"].update(vkey=0x11, scan_code=0x1D)
    windows["sdk_events"][0]["data"].update(native_code=0xA2, native_extra=0x1D)
    summary = inspect_native_capture(save(tmp_path, data))["windows_input_observations"]
    assert summary["sdk_events"][0]["compatible_windows_message_sequences"] == [0, 1]
    assert summary["sdk_events"][0]["correlation_status"] == "ambiguous_compatible_candidates"
    windows["messages"][1]["input_timestamp_enter"] = 10.06
    summary = inspect_native_capture(save(tmp_path, data))["windows_input_observations"]
    assert summary["sdk_events"][0]["compatible_windows_message_sequences"] == [0]
