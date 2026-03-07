"""Unit tests for LoadLastVideo._resolve_timestamps and related logic."""

import sys
import os
import tempfile
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

torch = __import__("pytest").importorskip("torch")
import numpy as np


# We need to test _resolve_timestamps independently. Since it's an instance
# method on LoadLastVideo, we instantiate the class minimally.
# We also mock folder_paths since it depends on ComfyUI runtime.


def _make_node():
    """Create a LoadLastVideo instance with minimal deps."""
    # Patch folder_paths before import
    import types
    mock_fp = types.ModuleType("folder_paths")
    mock_fp.get_output_directory = lambda: tempfile.mkdtemp()
    mock_fp.get_temp_directory = lambda: tempfile.mkdtemp()
    mock_fp.get_input_directory = lambda: tempfile.mkdtemp()
    sys.modules.setdefault("folder_paths", mock_fp)

    # Patch comfy.model_management
    mock_mm = types.ModuleType("comfy")
    mock_mm_inner = types.ModuleType("comfy.model_management")
    mock_mm_inner.get_torch_device = lambda: torch.device("cpu")
    mock_mm.model_management = mock_mm_inner
    sys.modules.setdefault("comfy", mock_mm)
    sys.modules.setdefault("comfy.model_management", mock_mm_inner)

    from loadlast.load_last_video import LoadLastVideo
    return LoadLastVideo()


def test_resolve_manual():
    """Manual mode returns parsed JSON timestamps."""
    print("Testing resolve_timestamps — manual...")
    node = _make_node()
    ts = node._resolve_timestamps('[1.0, 2.5, 0.5]', "manual", "", 10.0, 24.0)
    assert ts == [0.5, 1.0, 2.5], f"Expected sorted manual timestamps, got {ts}"
    print("  ✓ manual passed")


def test_resolve_manual_empty():
    """Manual mode with empty JSON returns empty list."""
    print("Testing resolve_timestamps — manual empty...")
    node = _make_node()
    ts = node._resolve_timestamps('[]', "manual", "", 10.0, 24.0)
    assert ts == [], f"Expected empty list, got {ts}"
    print("  ✓ manual empty passed")


def test_resolve_manual_invalid_json():
    """Manual mode with invalid JSON returns empty list."""
    print("Testing resolve_timestamps — manual invalid json...")
    node = _make_node()
    ts = node._resolve_timestamps('not-json', "manual", "", 10.0, 24.0)
    assert ts == [], f"Expected empty list for invalid JSON, got {ts}"
    print("  ✓ manual invalid json passed")


def test_resolve_uniform_5():
    """uniform_5 generates 5 evenly-spaced timestamps."""
    print("Testing resolve_timestamps — uniform_5...")
    node = _make_node()
    ts = node._resolve_timestamps('[]', "uniform_5", "", 10.0, 24.0)
    assert len(ts) == 5, f"Expected 5 timestamps, got {len(ts)}"
    assert ts[0] == 0.0, f"First should be 0.0, got {ts[0]}"
    assert ts[-1] == 10.0, f"Last should be 10.0, got {ts[-1]}"
    # Check spacing
    assert abs(ts[1] - 2.5) < 0.001, f"Second should be 2.5, got {ts[1]}"
    print("  ✓ uniform_5 passed")


def test_resolve_uniform_10():
    """uniform_10 generates 10 evenly-spaced timestamps."""
    print("Testing resolve_timestamps — uniform_10...")
    node = _make_node()
    ts = node._resolve_timestamps('[]', "uniform_10", "", 9.0, 30.0)
    assert len(ts) == 10, f"Expected 10 timestamps, got {len(ts)}"
    assert ts[0] == 0.0
    assert ts[-1] == 9.0
    print("  ✓ uniform_10 passed")


def test_resolve_first_last():
    """first_last generates exactly 2 timestamps."""
    print("Testing resolve_timestamps — first_last...")
    node = _make_node()
    ts = node._resolve_timestamps('[]', "first_last", "", 5.0, 24.0)
    assert len(ts) == 2, f"Expected 2 timestamps, got {len(ts)}"
    assert ts[0] == 0.0
    assert ts[1] == 4.99, f"Last should be duration-0.01, got {ts[1]}"
    print("  ✓ first_last passed")


def test_resolve_every_2nd():
    """every_2nd generates timestamps at every 2nd frame."""
    print("Testing resolve_timestamps — every_2nd...")
    node = _make_node()
    ts = node._resolve_timestamps('[]', "every_2nd", "", 1.0, 10.0)
    # step = 2/10 = 0.2s → 0, 0.2, 0.4, 0.6, 0.8, 1.0
    assert len(ts) == 6, f"Expected 6 timestamps, got {len(ts)}: {ts}"
    assert abs(ts[0]) < 0.001
    assert abs(ts[-1] - 1.0) < 0.001
    print("  ✓ every_2nd passed")


def test_resolve_every_5th():
    """every_5th generates timestamps at every 5th frame."""
    print("Testing resolve_timestamps — every_5th...")
    node = _make_node()
    ts = node._resolve_timestamps('[]', "every_5th", "", 1.0, 10.0)
    # step = 5/10 = 0.5s → 0, 0.5, 1.0
    assert len(ts) == 3, f"Expected 3 timestamps, got {len(ts)}: {ts}"
    print("  ✓ every_5th passed")


def test_resolve_timestamps_mode():
    """timestamps mode parses comma-separated string."""
    print("Testing resolve_timestamps — timestamps mode...")
    node = _make_node()
    ts = node._resolve_timestamps('[]', "timestamps", "1.5, 3.0, 0.5", 10.0, 24.0)
    assert ts == [0.5, 1.5, 3.0], f"Expected sorted parsed timestamps, got {ts}"
    print("  ✓ timestamps mode passed")


def test_resolve_timestamps_invalid():
    """timestamps mode with invalid input returns empty list."""
    print("Testing resolve_timestamps — timestamps invalid...")
    node = _make_node()
    ts = node._resolve_timestamps('[]', "timestamps", "not,a,number", 10.0, 24.0)
    assert ts == [], f"Expected empty list for invalid timestamps, got {ts}"
    print("  ✓ timestamps invalid passed")


def test_resolve_merge_manual_and_auto():
    """Manual selections are merged with auto-selected timestamps."""
    print("Testing resolve_timestamps — merge manual+auto...")
    node = _make_node()
    ts = node._resolve_timestamps('[5.0]', "timestamps", "1.0, 3.0", 10.0, 24.0)
    assert ts == [1.0, 3.0, 5.0], f"Expected merged+sorted, got {ts}"
    print("  ✓ merge manual+auto passed")


def test_resolve_dedup():
    """Duplicate timestamps are deduplicated."""
    print("Testing resolve_timestamps — dedup...")
    node = _make_node()
    ts = node._resolve_timestamps('[1.0, 1.0]', "timestamps", "1.0, 2.0", 10.0, 24.0)
    assert ts == [1.0, 2.0], f"Expected deduplicated, got {ts}"
    print("  ✓ dedup passed")


def test_resolve_zero_duration():
    """Auto modes with zero duration return only manual selections."""
    print("Testing resolve_timestamps — zero duration...")
    node = _make_node()
    ts = node._resolve_timestamps('[1.0]', "uniform_5", "", 0.0, 24.0)
    assert ts == [1.0], f"Expected only manual with zero duration, got {ts}"
    print("  ✓ zero duration passed")


def test_save_selected_frames():
    """Test _save_selected_frames_as_png saves PNGs and returns paths."""
    print("Testing _save_selected_frames_as_png...")

    # Create temp dir and patch folder_paths
    temp_dir = tempfile.mkdtemp()
    import types
    import importlib
    mock_fp = types.ModuleType("folder_paths")
    mock_fp.get_output_directory = lambda: temp_dir
    mock_fp.get_temp_directory = lambda: temp_dir
    mock_fp.get_input_directory = lambda: temp_dir
    sys.modules["folder_paths"] = mock_fp

    # Reload so module-level `folder_paths` picks up the mock
    import loadlast.load_last_video as llv_mod
    importlib.reload(llv_mod)
    LoadLastVideo = llv_mod.LoadLastVideo

    # Create 3 dummy frames (H=32, W=32, C=3)
    frames = torch.rand(3, 32, 32, 3)
    timestamps = [0.0, 1.5, 3.0]

    result = LoadLastVideo._save_selected_frames_as_png(frames, timestamps)

    paths = result.split(",")
    assert len(paths) == 3, f"Expected 3 paths, got {len(paths)}"

    for p in paths:
        assert os.path.exists(p), f"File should exist: {p}"
        assert p.endswith(".png"), f"Should be PNG: {p}"

    # Empty case
    assert LoadLastVideo._save_selected_frames_as_png(frames, []) == ""
    assert LoadLastVideo._save_selected_frames_as_png(
        torch.zeros(0, 32, 32, 3), [1.0]
    ) == ""

    # Clean up
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)
    print("  ✓ _save_selected_frames_as_png passed")


if __name__ == "__main__":
    print("=" * 50)
    print("LoadLastVideo Node Logic Tests")
    print("=" * 50)
    print()

    test_resolve_manual()
    test_resolve_manual_empty()
    test_resolve_manual_invalid_json()
    test_resolve_uniform_5()
    test_resolve_uniform_10()
    test_resolve_first_last()
    test_resolve_every_2nd()
    test_resolve_every_5th()
    test_resolve_timestamps_mode()
    test_resolve_timestamps_invalid()
    test_resolve_merge_manual_and_auto()
    test_resolve_dedup()
    test_resolve_zero_duration()
    test_save_selected_frames()

    print()
    print("=" * 50)
    print("ALL NODE LOGIC TESTS PASSED ✓")
    print("=" * 50)
