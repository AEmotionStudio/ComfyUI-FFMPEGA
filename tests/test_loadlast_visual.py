"""Unit tests for Phase 4 visual feedback modules."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

torch = __import__("pytest").importorskip("torch")
from loadlast.processing.diff import compose_diff, _diff_to_heatmap
from loadlast.processing.captions import format_caption, render_caption


def test_diff_heatmap():
    """Test diff heatmap mode."""
    print("Testing diff heatmap...")

    a = torch.rand(32, 32, 3)
    b = torch.rand(32, 32, 3)

    result = compose_diff(a, b, mode="heatmap")
    assert result.shape == torch.Size([1, 32, 32, 3])
    assert result.min() >= 0 and result.max() <= 1

    # Identical images → no change → blue heatmap (R≈0, G≈0, B≈1)
    result_same = compose_diff(a, a, mode="heatmap")
    assert result_same[..., 0].mean() < 0.05, f"Red channel should be near-zero for identical images: {result_same[..., 0].mean():.3f}"
    assert result_same[..., 1].mean() < 0.05, f"Green channel should be near-zero: {result_same[..., 1].mean():.3f}"

    # None second image → black
    result_none = compose_diff(a, None, mode="heatmap")
    assert result_none.sum() == 0, "None b should produce black"

    print("  ✓ diff heatmap tests passed")


def test_diff_overlay():
    """Test diff overlay mode."""
    print("Testing diff overlay...")

    a = torch.ones(32, 32, 3) * 0.8
    b = torch.ones(32, 32, 3) * 0.2

    result = compose_diff(a, b, mode="overlay")
    assert result.shape == torch.Size([1, 32, 32, 3])
    assert result.min() >= 0 and result.max() <= 1

    print("  ✓ diff overlay tests passed")


def test_diff_side_by_side():
    """Test diff side-by-side-diff mode."""
    print("Testing diff side-by-side...")

    a = torch.rand(32, 32, 3)
    b = torch.rand(32, 32, 3)

    result = compose_diff(a, b, mode="side_by_side_diff")
    assert result.shape[0] == 1
    assert result.shape[1] == 32
    # Width = 3 * 32 + 2 * 4 = 104
    assert result.shape[2] == 104, f"Expected width 104, got {result.shape[2]}"
    assert result.shape[3] == 3

    print("  ✓ diff side-by-side tests passed")


def test_diff_sensitivity():
    """Test diff sensitivity multiplier."""
    print("Testing diff sensitivity...")

    a = torch.ones(16, 16, 3) * 0.5
    b = torch.ones(16, 16, 3) * 0.6  # Small difference

    low = compose_diff(a, b, mode="heatmap", sensitivity=1.0)
    high = compose_diff(a, b, mode="heatmap", sensitivity=3.0)

    # Higher sensitivity should produce brighter diff
    assert high.mean() > low.mean(), "Higher sensitivity should increase diff visibility"

    print("  ✓ diff sensitivity tests passed")


def test_diff_resize():
    """Test diff with mismatched image sizes."""
    print("Testing diff resize...")

    a = torch.rand(64, 64, 3)
    b = torch.rand(32, 48, 3)  # Different size

    result = compose_diff(a, b, mode="heatmap")
    assert result.shape == torch.Size([1, 64, 64, 3]), f"Should match image_a dims: {result.shape}"

    print("  ✓ diff resize tests passed")


def test_caption_format():
    """Test caption format tokens."""
    print("Testing caption format...")

    result = format_caption(
        "#{iteration} | {timestamp} | seed:{seed}",
        iteration=42, timestamp="12:34:56", seed="123456"
    )
    assert "#42" in result
    assert "12:34:56" in result
    assert "seed:123456" in result

    # Unknown tokens should leave template unchanged
    result_bad = format_caption("{unknown_token}", iteration=1)
    assert result_bad == "{unknown_token}"

    # All tokens
    result_all = format_caption(
        "{iteration}-{timestamp}-{seed}-{index}-{filename}",
        iteration=1, timestamp="now", seed="42", index=3, filename="test.png"
    )
    assert "1-now-42-3-test.png" == result_all

    print("  ✓ caption format tests passed")


def test_caption_render():
    """Test caption rendering onto image tensor."""
    print("Testing caption render...")

    img = torch.ones(64, 64, 3) * 0.5  # Gray image

    result = render_caption(img, "Test Caption", bar_height=20)
    assert result.shape == torch.Size([64, 64, 3])

    # Bottom bar should be darker than original
    bottom_bar = result[44:64, :, :]  # last 20 rows
    top_area = result[0:20, :, :]     # first 20 rows (unchanged)

    # The top (no caption) should still be ~0.5
    assert abs(top_area.mean().item() - 0.5) < 0.01

    # Empty caption should not modify image
    result_empty = render_caption(img, "")
    assert torch.equal(result_empty, img)

    print("  ✓ caption render tests passed")


if __name__ == "__main__":
    print("=" * 50)
    print("ComfyUI-LoadLast Visual Feedback Tests")
    print("=" * 50)
    print()

    test_diff_heatmap()
    test_diff_overlay()
    test_diff_side_by_side()
    test_diff_sensitivity()
    test_diff_resize()
    test_caption_format()
    test_caption_render()

    print()
    print("=" * 50)
    print("ALL VISUAL FEEDBACK TESTS PASSED ✓")
    print("=" * 50)
