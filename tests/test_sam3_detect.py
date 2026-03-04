"""Unit tests for the SAM3 point-prompt detection feature.

Tests cover:
- mask_image_with_points() graceful failure when SAM3 is not installed
- mask_image_with_points() return type when SAM3 is mocked
- Coordinate normalisation and pixel-space conversion
- processor.set_image → model.predict_inst flow
- Cleanup endpoint
"""

import io
import os
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest

# PyTorch import can fail — guard torch-dependent tests
try:
    import torch  # noqa: F401
    _has_torch = True
except (ImportError, RuntimeError):
    _has_torch = False


# --- Helper: create a tiny test image on disk ---

@pytest.fixture
def tiny_image(tmp_path):
    """Create a small 4×4 PNG image for testing."""
    from PIL import Image
    img = Image.new("RGB", (4, 4), color=(128, 64, 32))
    path = str(tmp_path / "test_img.png")
    img.save(path, format="PNG")
    return path


def _make_mock_model_and_processor(masks=None, scores=None):
    """Create mocked SAM3 model + processor.

    The model's predict_inst returns the given masks/scores.
    The processor's set_image returns a fake inference_state dict.
    """
    if masks is None:
        masks = np.ones((1, 4, 4), dtype=bool)
    if scores is None:
        scores = np.array([0.9])

    mock_model = MagicMock()
    mock_model.inst_interactive_predictor = MagicMock()  # not None → predictor exists
    mock_model.predict_inst.return_value = (masks, scores, np.zeros_like(masks))

    mock_processor = MagicMock()
    mock_processor.set_image.return_value = {
        "original_height": 4,
        "original_width": 4,
        "backbone_out": {"sam2_backbone_out": {}},
    }
    return mock_model, mock_processor


# --- mask_image_with_points tests ---

class TestMaskImageWithPoints:
    """Tests for core.sam3_masker.mask_image_with_points."""

    def test_empty_points_returns_png(self, tiny_image):
        """Should return valid PNG bytes when given no points."""
        from core.sam3_masker import mask_image_with_points

        mock_model, mock_processor = _make_mock_model_and_processor()

        with patch("core.sam3_masker.load_image_model", return_value=(mock_model, mock_processor)):
            result = mask_image_with_points(
                image_path=tiny_image,
                points=[],
                labels=[],
            )

        assert isinstance(result, bytes)
        assert len(result) > 0
        assert result[:4] == b"\x89PNG"
        # predict_inst should NOT be called (no points → early return)
        mock_model.predict_inst.assert_not_called()

    def test_invalid_points_returns_empty_mask(self, tiny_image):
        """Points with bad format should be skipped, returning empty mask."""
        from core.sam3_masker import mask_image_with_points

        mock_model, mock_processor = _make_mock_model_and_processor()

        with patch("core.sam3_masker.load_image_model", return_value=(mock_model, mock_processor)):
            result = mask_image_with_points(
                image_path=tiny_image,
                points=["bad", None, 42],
                labels=[1, 0, 1],
            )

        assert isinstance(result, bytes)
        assert result[:4] == b"\x89PNG"

    @pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
    def test_valid_positive_point_returns_mask(self, tiny_image):
        """A positive point should produce a valid mask via predict_inst."""
        from core.sam3_masker import mask_image_with_points

        mock_model, mock_processor = _make_mock_model_and_processor(
            masks=np.ones((3, 4, 4), dtype=bool),  # multimask=True → 3 masks
            scores=np.array([0.7, 0.9, 0.5]),
        )

        with patch("core.sam3_masker.load_image_model", return_value=(mock_model, mock_processor)):
            result = mask_image_with_points(
                image_path=tiny_image,
                points=[[2, 2]],
                labels=[1],
            )

        assert isinstance(result, bytes)
        assert result[:4] == b"\x89PNG"

        # Verify processor.set_image was called (computes backbone features)
        mock_processor.set_image.assert_called_once()

        # Verify model.predict_inst was called with correct kwargs
        mock_model.predict_inst.assert_called_once()
        call_args = mock_model.predict_inst.call_args
        pred_kwargs = call_args[1]
        assert pred_kwargs["multimask_output"] is True  # single point → multimask
        np.testing.assert_array_equal(pred_kwargs["point_labels"], np.array([1]))

        # The mask should have white pixels
        from PIL import Image
        mask_img = Image.open(io.BytesIO(result)).convert("L")
        mask_arr = np.array(mask_img)
        assert mask_arr.max() == 255

    @pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
    def test_negative_point_passed_as_label_zero(self, tiny_image):
        """A negative point should have label=0 in point_labels array."""
        from core.sam3_masker import mask_image_with_points

        mock_model, mock_processor = _make_mock_model_and_processor()

        with patch("core.sam3_masker.load_image_model", return_value=(mock_model, mock_processor)):
            mask_image_with_points(
                image_path=tiny_image,
                points=[[2, 2]],
                labels=[0],
            )

        pred_kwargs = mock_model.predict_inst.call_args[1]
        np.testing.assert_array_equal(pred_kwargs["point_labels"], np.array([0]))

    @pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
    def test_multiple_points_single_predict_call(self, tiny_image):
        """Multiple points → single predict_inst() call with all coords."""
        from core.sam3_masker import mask_image_with_points

        mock_model, mock_processor = _make_mock_model_and_processor()

        with patch("core.sam3_masker.load_image_model", return_value=(mock_model, mock_processor)):
            mask_image_with_points(
                image_path=tiny_image,
                points=[[1, 1], [3, 3], [2, 2]],
                labels=[1, 1, 0],
            )

        # All points in a single predict_inst() call
        assert mock_model.predict_inst.call_count == 1
        pred_kwargs = mock_model.predict_inst.call_args[1]
        assert pred_kwargs["point_coords"].shape == (3, 2)
        np.testing.assert_array_equal(pred_kwargs["point_labels"], np.array([1, 1, 0]))
        # Multiple points → multimask_output=False
        assert pred_kwargs["multimask_output"] is False

    def test_point_normalisation_to_pixel_coords(self, tiny_image):
        """Points should be scaled from canvas coords to image pixel coords."""
        from core.sam3_masker import mask_image_with_points

        mock_model, mock_processor = _make_mock_model_and_processor()

        with patch("core.sam3_masker.load_image_model", return_value=(mock_model, mock_processor)):
            mask_image_with_points(
                image_path=tiny_image,
                points=[[200, 100]],
                labels=[1],
                image_width=400,
                image_height=200,
            )

        # Canvas (200,100) on 400×200 canvas → ratio (0.5, 0.5)
        # Image is 4×4, so pixel coords = (0.5*4, 0.5*4) = (2.0, 2.0)
        pred_kwargs = mock_model.predict_inst.call_args[1]
        coords = pred_kwargs["point_coords"]
        assert abs(coords[0][0] - 2.0) < 0.01
        assert abs(coords[0][1] - 2.0) < 0.01

    @pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
    def test_inference_state_passed_to_predict_inst(self, tiny_image):
        """The inference_state from processor.set_image should be passed to predict_inst."""
        from core.sam3_masker import mask_image_with_points

        mock_model, mock_processor = _make_mock_model_and_processor()
        fake_state = {"original_height": 4, "original_width": 4, "backbone_out": {}}
        mock_processor.set_image.return_value = fake_state

        with patch("core.sam3_masker.load_image_model", return_value=(mock_model, mock_processor)):
            mask_image_with_points(
                image_path=tiny_image,
                points=[[2, 2]],
                labels=[1],
            )

        # First positional arg to predict_inst should be inference_state
        call_args = mock_model.predict_inst.call_args
        assert call_args[0][0] is fake_state

    @pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
    def test_multimask_selects_highest_score(self, tiny_image):
        """With a single point, multimask_output=True and highest-scoring mask is picked."""
        from core.sam3_masker import mask_image_with_points

        # 3 masks: only the second one (idx=1) has any True pixels
        masks = np.zeros((3, 4, 4), dtype=bool)
        masks[1, :, :] = True
        scores = np.array([0.5, 0.95, 0.3])

        mock_model, mock_processor = _make_mock_model_and_processor(masks=masks, scores=scores)

        with patch("core.sam3_masker.load_image_model", return_value=(mock_model, mock_processor)):
            result = mask_image_with_points(
                image_path=tiny_image,
                points=[[2, 2]],
                labels=[1],
            )

        from PIL import Image
        mask_img = Image.open(io.BytesIO(result)).convert("L")
        mask_arr = np.array(mask_img)
        assert mask_arr.max() == 255

    @pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
    def test_no_predictor_returns_empty_mask(self, tiny_image):
        """When inst_interactive_predictor is None, should return empty mask."""
        from core.sam3_masker import mask_image_with_points

        mock_model = MagicMock()
        mock_model.inst_interactive_predictor = None
        mock_processor = MagicMock()

        with patch("core.sam3_masker.load_image_model", return_value=(mock_model, mock_processor)):
            result = mask_image_with_points(
                image_path=tiny_image,
                points=[[2, 2]],
                labels=[1],
            )

        assert isinstance(result, bytes)
        assert result[:4] == b"\x89PNG"
        from PIL import Image
        mask_img = Image.open(io.BytesIO(result)).convert("L")
        mask_arr = np.array(mask_img)
        assert mask_arr.max() == 0


# --- Cleanup test ---

class TestSAM3Cleanup:
    """Test the cleanup function."""

    @pytest.mark.skipif(not _has_torch, reason="PyTorch not available")
    def test_cleanup_resets_state(self):
        """cleanup() should reset all cached models."""
        import core.sam3_masker as sm
        sm._image_model = "fake"
        sm._image_processor = "fake"
        sm._video_model = "fake"
        sm.cleanup()
        assert sm._image_model is None
        assert sm._image_processor is None
        assert sm._video_model is None
