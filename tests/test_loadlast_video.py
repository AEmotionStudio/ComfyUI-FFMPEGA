"""Unit tests for ComfyUI-LoadLast video modules."""

import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

torch = __import__("pytest").importorskip("torch")
from loadlast.processing.loop import apply_loop_mode
from loadlast.processing.filmstrip import compose_filmstrip
from loadlast.processing.video_decode import VideoDecoder
from loadlast.discovery.video_filesystem import VideoFilesystemScanner, VideoEntry, SEQUENCE_PATTERN


def test_loop_modes():
    """Test loop/ping-pong frame manipulation."""
    print("Testing loop modes...")

    # 5-frame video
    frames = torch.rand(5, 32, 32, 3)

    # none
    result_none = apply_loop_mode(frames, "none")
    assert result_none.shape[0] == 5, f"none: expected 5 frames, got {result_none.shape[0]}"

    # loop: appends first frame at end
    result_loop = apply_loop_mode(frames, "loop")
    assert result_loop.shape[0] == 6, f"loop: expected 6 frames, got {result_loop.shape[0]}"
    assert torch.equal(result_loop[0], result_loop[-1]), "loop: last frame should equal first"

    # ping_pong: 5 + reverse of [1,2,3] = 5 + 3 = 8
    result_pp = apply_loop_mode(frames, "ping_pong")
    assert result_pp.shape[0] == 8, f"ping_pong: expected 8 frames, got {result_pp.shape[0]}"
    # Reversed middle should be frames[3], frames[2], frames[1]
    assert torch.equal(result_pp[5], frames[3]), "ping_pong: first reversed should be frame 3"
    assert torch.equal(result_pp[6], frames[2]), "ping_pong: second reversed should be frame 2"
    assert torch.equal(result_pp[7], frames[1]), "ping_pong: third reversed should be frame 1"

    # Single frame
    single = torch.rand(1, 32, 32, 3)
    result_single = apply_loop_mode(single, "ping_pong")
    assert result_single.shape[0] == 1, "single frame should be unchanged"

    # Two frames ping-pong: [0, 1, 0]
    two = torch.rand(2, 32, 32, 3)
    result_two = apply_loop_mode(two, "ping_pong")
    assert result_two.shape[0] == 3, f"2-frame ping_pong: expected 3, got {result_two.shape[0]}"
    assert torch.equal(result_two[2], two[0])

    print("  ✓ loop mode tests passed")


def test_subsample_indices():
    """Test VideoDecoder.subsample_indices."""
    print("Testing subsample indices...")

    indices = VideoDecoder.subsample_indices(100, 5)
    assert len(indices) == 5, f"Expected 5 indices, got {len(indices)}"
    assert indices[0] == 0, "First index should be 0"
    assert indices[-1] == 99, f"Last index should be 99, got {indices[-1]}"
    assert indices == sorted(indices), "Indices should be sorted"

    # max_frames >= total
    indices_all = VideoDecoder.subsample_indices(5, 10)
    assert indices_all == [0, 1, 2, 3, 4]

    # max_frames = 1
    indices_one = VideoDecoder.subsample_indices(10, 1)
    assert indices_one == [0]

    # max_frames = 2
    indices_two = VideoDecoder.subsample_indices(10, 2)
    assert indices_two == [0, 9]

    # Edge: total = 1
    indices_single = VideoDecoder.subsample_indices(1, 5)
    assert indices_single == [0]

    print("  ✓ subsample indices tests passed")


def test_filmstrip():
    """Test filmstrip composition."""
    print("Testing filmstrip...")

    frames = torch.rand(20, 64, 128, 3)

    strip = compose_filmstrip(frames, num_frames=5, scale=0.5, padding=4)
    assert strip.ndim == 4
    assert strip.shape[0] == 1
    assert strip.shape[3] == 3

    # Height should be ~32 (64 * 0.5)
    expected_h = 32
    assert strip.shape[1] == expected_h, f"Height: expected {expected_h}, got {strip.shape[1]}"

    # Width: 5 frames * 64px + 4 gaps * 4px = 320 + 16 = 336
    expected_w = 5 * 64 + 4 * 4
    assert strip.shape[2] == expected_w, f"Width: expected {expected_w}, got {strip.shape[2]}"

    # Single frame
    single_strip = compose_filmstrip(torch.rand(1, 64, 64, 3), num_frames=8, scale=0.5)
    assert single_strip.shape[0] == 1

    # Empty frames
    empty_strip = compose_filmstrip(torch.zeros(0, 64, 64, 3), num_frames=5)
    assert empty_strip.shape == torch.Size([1, 64, 64, 3])

    print("  ✓ filmstrip tests passed")


def test_sequence_pattern():
    """Test the regex pattern for image sequence detection."""
    print("Testing sequence pattern...")

    # Should match
    match1 = SEQUENCE_PATTERN.match("render_001.png")
    assert match1, "Should match render_001.png"
    assert match1.group(1) == "render", f"Prefix should be 'render', got '{match1.group(1)}'"
    assert match1.group(2) == "001", f"Number should be '001', got '{match1.group(2)}'"

    match2 = SEQUENCE_PATTERN.match("frame-0042.jpg")
    assert match2, "Should match frame-0042.jpg"
    assert match2.group(1) == "frame"
    assert match2.group(2) == "0042"

    match3 = SEQUENCE_PATTERN.match("my_video_00100.webp")
    assert match3, "Should match my_video_00100.webp"
    assert match3.group(1) == "my_video"
    assert match3.group(2) == "00100"

    # Should not match (fewer than 3 digits)
    match_no = SEQUENCE_PATTERN.match("img_01.png")
    assert not match_no, "Should not match 2-digit numbers"

    print("  ✓ sequence pattern tests passed")


def test_video_scanner():
    """Test video filesystem scanner with image sequences."""
    print("Testing video scanner...")

    scanner = VideoFilesystemScanner()

    # Empty dir scan
    result = scanner.scan(["/tmp/nonexistent_xyz123"], n=5)
    assert result == []

    # Create temp dir with image sequence
    with tempfile.TemporaryDirectory() as tmpdir:
        from PIL import Image
        import time

        # Create a 5-frame image sequence
        for i in range(5):
            img = Image.new('RGB', (32, 32), color=(i * 50, 0, 0))
            path = os.path.join(tmpdir, f"render_{i:04d}.png")
            img.save(path)
            os.utime(path, (time.time() + i, time.time() + i))

        entries = scanner.scan([tmpdir], n=10)

        # Should detect the sequence
        seq_entries = [e for e in entries if e.source_type == "sequence"]
        assert len(seq_entries) == 1, f"Expected 1 sequence, got {len(seq_entries)}"

        seq = seq_entries[0]
        assert len(seq.frame_paths) == 5, f"Expected 5 frames, got {len(seq.frame_paths)}"
        assert "render_0000" in seq.frame_paths[0]

    print("  ✓ video scanner tests passed")


def test_decode_gif():
    """Test GIF decoding (if PIL supports it)."""
    print("Testing GIF decoding...")

    # Create a simple animated GIF
    from PIL import Image

    with tempfile.NamedTemporaryFile(suffix='.gif', delete=False) as f:
        gif_path = f.name

    try:
        # Create 3-frame GIF
        frames_pil = []
        for i in range(3):
            img = Image.new('RGB', (32, 32), color=(i * 80, 0, 0))
            frames_pil.append(img)

        frames_pil[0].save(
            gif_path,
            save_all=True,
            append_images=frames_pil[1:],
            duration=100,
            loop=0,
        )

        decoder = VideoDecoder()
        frames, metadata = decoder.decode_gif(gif_path)

        assert frames.ndim == 4, f"Expected 4D tensor, got {frames.ndim}D"
        assert frames.shape[0] == 3, f"Expected 3 frames, got {frames.shape[0]}"
        assert frames.shape[1] == 32
        assert frames.shape[2] == 32
        assert frames.shape[3] == 3
        assert metadata["fps"] == 10, f"Expected 10 fps, got {metadata['fps']}"
        assert metadata["source_frame_count"] == 3
    finally:
        os.unlink(gif_path)

    print("  ✓ GIF decoding tests passed")


def test_decode_sequence():
    """Test image sequence decoding."""
    print("Testing sequence decoding...")

    with tempfile.TemporaryDirectory() as tmpdir:
        from PIL import Image

        # Create 5-frame sequence
        paths = []
        for i in range(5):
            img = Image.new('RGB', (48, 32), color=(i * 50, 100, 0))
            path = os.path.join(tmpdir, f"frame_{i:04d}.png")
            img.save(path)
            paths.append(path)

        decoder = VideoDecoder()
        frames, metadata = decoder.decode_sequence(paths, default_fps=30)

        assert frames.shape == torch.Size([5, 32, 48, 3])
        assert metadata["fps"] == 30
        assert metadata["source_frame_count"] == 5
        assert metadata["width"] == 48
        assert metadata["height"] == 32

        # With subsampling
        frames_sub, _ = decoder.decode_sequence(paths, max_frames=3, default_fps=24)
        assert frames_sub.shape[0] == 3, f"Subsampled: expected 3, got {frames_sub.shape[0]}"

        # With frame range
        frames_range, _ = decoder.decode_sequence(
            paths, start_frame=1, end_frame=3, default_fps=24
        )
        assert frames_range.shape[0] == 3

    print("  ✓ sequence decoding tests passed")


if __name__ == "__main__":
    print("=" * 50)
    print("ComfyUI-LoadLast Video Unit Tests")
    print("=" * 50)
    print()

    test_loop_modes()
    test_subsample_indices()
    test_filmstrip()
    test_sequence_pattern()
    test_video_scanner()
    test_decode_gif()
    test_decode_sequence()

    print()
    print("=" * 50)
    print("ALL VIDEO TESTS PASSED ✓")
    print("=" * 50)
