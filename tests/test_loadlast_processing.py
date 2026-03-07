"""Unit tests for ComfyUI-LoadLast processing modules."""

import sys
import os
import tempfile

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

torch = __import__("pytest").importorskip("torch")
from loadlast.processing.dedup import compute_pixel_hash, is_duplicate
from loadlast.processing.grid import compose_grid
from loadlast.processing.sidebyside import compose_side_by_side
from loadlast.processing.metadata import extract_png_metadata
from loadlast.discovery.filesystem import FilesystemScanner


def test_dedup():
    """Test pixel hash and duplicate detection."""
    print("Testing dedup...")

    # Same tensor should produce same hash
    t = torch.rand(64, 64, 3)
    h1 = compute_pixel_hash(t)
    h2 = compute_pixel_hash(t)
    assert h1 == h2, f"Same tensor should produce same hash: {h1} != {h2}"
    assert is_duplicate(h1, h2), "Same hash should be duplicate"

    # Different tensors should (almost certainly) produce different hashes
    t2 = torch.rand(64, 64, 3)
    h3 = compute_pixel_hash(t2)
    assert not is_duplicate(h1, h3), "Different images should not be duplicates"

    # Very small image
    small = torch.rand(2, 2, 3)
    h_small = compute_pixel_hash(small)
    assert isinstance(h_small, int), "Hash should be an integer"

    # Zero image
    zero = torch.zeros(32, 32, 3)
    h_zero = compute_pixel_hash(zero)
    assert isinstance(h_zero, int)

    print("  ✓ dedup tests passed")


def test_grid():
    """Test grid composition."""
    print("Testing grid...")

    # 4 images in 2x2 grid
    images = [torch.rand(32, 32, 3) for _ in range(4)]
    grid = compose_grid(images, columns=2, padding=2)
    assert grid.ndim == 4, f"Expected 4D tensor, got {grid.ndim}D"
    assert grid.shape[0] == 1, f"Batch dim should be 1, got {grid.shape[0]}"
    assert grid.shape[3] == 3, f"Channel dim should be 3, got {grid.shape[3]}"
    expected_h = 32 * 2 + 2  # 2 rows + 1 padding gap
    expected_w = 32 * 2 + 2  # 2 cols + 1 padding gap
    assert grid.shape[1] == expected_h, f"Height should be {expected_h}, got {grid.shape[1]}"
    assert grid.shape[2] == expected_w, f"Width should be {expected_w}, got {grid.shape[2]}"

    # Single image grid
    single_grid = compose_grid([images[0]], columns=2, padding=4)
    assert single_grid.shape[0] == 1
    assert single_grid.shape[1] == 32, f"Single image grid height should be 32, got {single_grid.shape[1]}"

    # Empty grid
    empty_grid = compose_grid([], columns=2)
    assert empty_grid.shape == torch.Size([1, 64, 64, 3])

    # Mixed dimensions
    mixed = [torch.rand(32, 32, 3), torch.rand(64, 48, 3)]
    mixed_grid = compose_grid(mixed, columns=2, padding=0)
    assert mixed_grid.shape[0] == 1
    # All cells should be 32x32 (matching first image)
    assert mixed_grid.shape[1] == 32
    assert mixed_grid.shape[2] == 64  # 2 columns x 32

    # Grid with border
    bordered = compose_grid(images[:2], columns=2, padding=0, border=5)
    assert bordered.shape[1] == 32 + 10  # height + 2*border
    assert bordered.shape[2] == 64 + 10  # width*2 + 2*border

    print("  ✓ grid tests passed")


def test_sidebyside():
    """Test side-by-side composition."""
    print("Testing side-by-side...")

    a = torch.rand(32, 32, 3)
    b = torch.rand(32, 32, 3)

    # Two images
    sbs = compose_side_by_side(a, b, padding=4)
    assert sbs.ndim == 4
    assert sbs.shape[0] == 1
    assert sbs.shape[1] == 32
    assert sbs.shape[2] == 32 + 4 + 32  # w_a + padding + w_b
    assert sbs.shape[3] == 3

    # Single image (b is None)
    sbs_single = compose_side_by_side(a, None, padding=4)
    assert sbs_single.shape[1] == 32
    assert sbs_single.shape[2] == 32 + 4 + 32  # Still full width, right side is bg

    # Different heights
    tall_b = torch.rand(64, 48, 3)
    sbs_mixed = compose_side_by_side(a, tall_b, padding=2)
    assert sbs_mixed.shape[1] == 32  # Should match a's height

    print("  ✓ side-by-side tests passed")


def test_metadata():
    """Test metadata extraction."""
    print("Testing metadata...")

    # Non-PNG file should return empty strings
    result = extract_png_metadata("/tmp/nonexistent.jpg")
    assert result['prompt'] == ''
    assert result['seed'] == ''
    assert result['workflow'] == ''

    # Create a test PNG with metadata
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo
    import json

    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        temp_path = f.name

    try:
        img = Image.new('RGB', (64, 64), color='red')
        meta = PngInfo()

        prompt_data = {
            "1": {
                "class_type": "CLIPTextEncode",
                "inputs": {"text": "a beautiful sunset"}
            },
            "2": {
                "class_type": "KSampler",
                "inputs": {"seed": 42}
            },
        }
        meta.add_text("prompt", json.dumps(prompt_data))
        meta.add_text("workflow", '{"version": 1}')

        img.save(temp_path, pnginfo=meta)

        result = extract_png_metadata(temp_path)
        assert result['prompt'] == 'a beautiful sunset', f"Expected prompt, got: {result['prompt']}"
        assert result['seed'] == '42', f"Expected seed '42', got: {result['seed']}"
        assert result['workflow'] == '{"version": 1}'
    finally:
        os.unlink(temp_path)

    print("  ✓ metadata tests passed")


def test_filesystem_scanner():
    """Test filesystem scanner."""
    print("Testing filesystem scanner...")

    scanner = FilesystemScanner()

    # Scan empty/nonexistent dir
    result = scanner.scan(["/tmp/nonexistent_dir_xyz"], n=5)
    assert result == [], "Should return empty for nonexistent dir"

    # Create temp dir with test images
    with tempfile.TemporaryDirectory() as tmpdir:
        from PIL import Image
        import time

        # Create 3 test images with slight time gaps
        for i in range(3):
            img = Image.new('RGB', (32, 32), color=(i * 80, 0, 0))
            path = os.path.join(tmpdir, f"test_{i:04d}.png")
            img.save(path)
            # Ensure different mtimes
            os.utime(path, (time.time() + i, time.time() + i))

        # Scan should find them sorted by mtime
        paths = scanner.scan([tmpdir], n=10)
        assert len(paths) == 3, f"Expected 3 images, got {len(paths)}"
        # Most recent should be first
        assert "test_0002" in paths[0], f"Most recent should be first: {paths[0]}"

        # With n=1
        paths_one = scanner.scan([tmpdir], n=1)
        assert len(paths_one) == 1

        # With filename filter
        paths_filtered = scanner.scan([tmpdir], n=10, filename_filter="test_0001")
        assert len(paths_filtered) == 1

        # Load image
        tensor, meta = scanner.load_image(paths[0])
        assert tensor.shape == torch.Size([32, 32, 3])
        assert tensor.dtype == torch.float32
        assert tensor.min() >= 0.0 and tensor.max() <= 1.0

    print("  ✓ filesystem scanner tests passed")


if __name__ == "__main__":
    print("=" * 50)
    print("ComfyUI-LoadLast Unit Tests")
    print("=" * 50)
    print()

    test_dedup()
    test_grid()
    test_sidebyside()
    test_metadata()
    test_filesystem_scanner()

    print()
    print("=" * 50)
    print("ALL TESTS PASSED ✓")
    print("=" * 50)
