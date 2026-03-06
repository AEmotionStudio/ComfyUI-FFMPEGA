# coding: utf-8
"""LivePortrait integration for AI-powered portrait animation in FFMPEGA.

Animates a source face (image or video) using motion from a driving video.
Transfers head pose, facial expressions, eye gaze, and lip movements.

Architecture follows the MuseTalk/MMAudio synthesizer pattern:
- In-process execution with GPU↔CPU model offloading
- Model download via mirror-first strategy
- Cached model state with explicit load/cleanup

Based on: https://github.com/KlingAIResearch/LivePortrait

License:
    LivePortrait code: MIT License
    Model weights: see upstream repository for details
"""

import gc
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import torch
import torch.nn.functional as F
import yaml

log = logging.getLogger("ffmpega")

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

PI = np.pi

_MIRROR_REPO = "AEmotionStudio/liveportrait-models"

# Model filenames expected on the mirror (safetensors format)
_MODEL_FILES = {
    "appearance_feature_extractor": "appearance_feature_extractor.safetensors",
    "motion_extractor": "motion_extractor.safetensors",
    "warping_module": "warping_module.safetensors",
    "spade_generator": "spade_generator.safetensors",
    "stitching_retargeting_module": "stitching_retargeting_module.safetensors",
}

# Fallback .pth filenames on upstream HF
_UPSTREAM_FILES = {
    "appearance_feature_extractor": "appearance_feature_extractor.pth",
    "motion_extractor": "motion_extractor.pth",
    "warping_module": "warping_module.pth",
    "spade_generator": "spade_generator.pth",
    "stitching_retargeting_module": "stitching_retargeting_module.pth",
}

_UPSTREAM_REPO = "KlingTeam/LivePortrait"


# ---------------------------------------------------------------------------
#  Model directory & checkpoint discovery
# ---------------------------------------------------------------------------


def _get_model_dir() -> str:
    """Return the LivePortrait model directory, creating if needed.

    Checks (in order):
    1. FFMPEGA_LIVEPORTRAIT_MODEL_DIR env var
    2. ComfyUI/models/liveportrait/ (standard convention)
    3. Extension's own models/liveportrait/ (fallback)
    """
    env_dir = os.environ.get("FFMPEGA_LIVEPORTRAIT_MODEL_DIR")
    if env_dir and os.path.isdir(env_dir):
        return env_dir

    ext_dir = Path(__file__).resolve().parent.parent
    comfy_root = ext_dir.parent.parent
    comfy_models = comfy_root / "models" / "liveportrait"
    if comfy_models.exists() or not ext_dir.name.startswith("ComfyUI"):
        comfy_models.mkdir(parents=True, exist_ok=True)
        return str(comfy_models)

    local = ext_dir / "models" / "liveportrait"
    local.mkdir(parents=True, exist_ok=True)
    return str(local)


def _find_or_download_model(model_key: str) -> str:
    """Find or download a LivePortrait model file.

    Args:
        model_key: One of the _MODEL_FILES keys.

    Returns:
        Path to the model file.
    """
    try:
        from .model_manager import (
            require_downloads_allowed,
            try_mirror_download,
            download_with_progress,
        )
    except ImportError:
        from core.model_manager import (
            require_downloads_allowed,
            try_mirror_download,
            download_with_progress,
        )

    model_dir = _get_model_dir()

    # Check for safetensors first
    st_filename = _MODEL_FILES[model_key]
    st_local = os.path.join(model_dir, st_filename)
    if os.path.isfile(st_local):
        return st_local

    # Check for legacy .pth
    pth_filename = _UPSTREAM_FILES[model_key]
    pth_local = os.path.join(model_dir, pth_filename)
    if os.path.isfile(pth_local):
        return pth_local

    require_downloads_allowed("liveportrait")

    # Try mirror (safetensors)
    mirror_path = try_mirror_download(
        "liveportrait", st_filename, model_dir,
    )
    if mirror_path and os.path.isfile(mirror_path):
        return mirror_path

    # Fallback to upstream HF (.pth)
    def _download():
        from huggingface_hub import hf_hub_download
        return hf_hub_download(
            repo_id=_UPSTREAM_REPO,
            filename=pth_filename,
            local_dir=model_dir,
        )

    path = download_with_progress(
        "liveportrait", _download, extra=pth_filename)
    return path


def _get_model_config() -> dict:
    """Load the model architecture configuration."""
    config_path = Path(__file__).resolve().parent / "liveportrait" / "models.yaml"
    with open(config_path, "r") as f:
        return yaml.load(f, Loader=yaml.SafeLoader)


# ---------------------------------------------------------------------------
#  Camera / pose helpers (inlined from LivePortrait utils)
# ---------------------------------------------------------------------------


def headpose_pred_to_degree(pred):
    """Convert binned head pose prediction to degrees.

    Args:
        pred: (bs, 66) softmax bins or (bs, 1) direct degree.
    """
    if pred.ndim > 1 and pred.shape[1] == 66:
        device = pred.device
        idx_tensor = torch.FloatTensor(list(range(66))).to(device)
        pred = F.softmax(pred, dim=1)
        degree = torch.sum(pred * idx_tensor, axis=1) * 3 - 97.5
        return degree
    return pred


def get_rotation_matrix(pitch_, yaw_, roll_):
    """Build a 3D rotation matrix from Euler angles (degrees)."""
    pitch = pitch_ / 180 * PI
    yaw = yaw_ / 180 * PI
    roll = roll_ / 180 * PI

    device = pitch.device

    if pitch.ndim == 1:
        pitch = pitch.unsqueeze(1)
    if yaw.ndim == 1:
        yaw = yaw.unsqueeze(1)
    if roll.ndim == 1:
        roll = roll.unsqueeze(1)

    bs = pitch.shape[0]
    ones = torch.ones([bs, 1]).to(device)
    zeros = torch.zeros([bs, 1]).to(device)
    x, y, z = pitch, yaw, roll

    rot_x = torch.cat([
        ones, zeros, zeros,
        zeros, torch.cos(x), -torch.sin(x),
        zeros, torch.sin(x), torch.cos(x),
    ], dim=1).reshape([bs, 3, 3])

    rot_y = torch.cat([
        torch.cos(y), zeros, torch.sin(y),
        zeros, ones, zeros,
        -torch.sin(y), zeros, torch.cos(y),
    ], dim=1).reshape([bs, 3, 3])

    rot_z = torch.cat([
        torch.cos(z), -torch.sin(z), zeros,
        torch.sin(z), torch.cos(z), zeros,
        zeros, zeros, ones,
    ], dim=1).reshape([bs, 3, 3])

    rot = rot_z @ rot_y @ rot_x
    return rot.permute(0, 2, 1)


def concat_feat(kp_source, kp_driving):
    """Concatenate source and driving keypoints for stitching network.

    Args:
        kp_source: (bs, k, 3) or (bs, N)
        kp_driving: (bs, k, 3) or (bs, N)

    Returns:
        (bs, 2k*3) or (bs, 2N)
    """
    bs = kp_source.shape[0]
    feat = torch.cat([
        kp_source.view(bs, -1),
        kp_driving.view(bs, -1),
    ], dim=1)
    return feat


# ---------------------------------------------------------------------------
#  VRAM management
# ---------------------------------------------------------------------------

_freeing_vram = False


def _free_vram():
    """Free all GPU VRAM before loading LivePortrait models.

    Follows the MMAudio/MuseTalk pattern:
    1. Tell ComfyUI to unload ALL cached models from GPU
    2. Free MMAudio models if loaded
    3. Free MuseTalk models if loaded
    4. Free SAM3 models if loaded
    5. Free FLUX Klein pipeline if loaded
    6. Empty CUDA cache + gc.collect
    """
    global _freeing_vram
    if _freeing_vram:
        return
    _freeing_vram = True
    try:
        try:
            from .platform import free_comfyui_vram
        except ImportError:
            from core.platform import free_comfyui_vram
        free_comfyui_vram()

        # Free MMAudio if loaded
        try:
            try:
                from . import mmaudio_synthesizer
            except ImportError:
                from core import mmaudio_synthesizer  # type: ignore
            mmaudio_synthesizer.cleanup()
        except Exception:
            pass

        # Free MuseTalk if loaded
        try:
            try:
                from . import musetalk_synthesizer
            except ImportError:
                from core import musetalk_synthesizer  # type: ignore
            musetalk_synthesizer.cleanup()
        except Exception:
            pass

        # Free SAM3 if loaded
        try:
            try:
                from . import sam3_masker
            except ImportError:
                from core import sam3_masker  # type: ignore
            sam3_masker.cleanup()
        except Exception:
            pass

        # Free FLUX Klein if loaded
        try:
            try:
                from . import flux_klein_editor
            except ImportError:
                from core import flux_klein_editor  # type: ignore
            flux_klein_editor.cleanup()
        except Exception:
            pass

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()
    finally:
        _freeing_vram = False


def _get_device() -> torch.device:
    """Get the best available device."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _get_offload_device():
    """Get the ComfyUI offload device (CPU), or fallback to 'cpu'."""
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        return mm.unet_offload_device()
    except ImportError:
        return torch.device("cpu")


# ---------------------------------------------------------------------------
#  Model loading helpers
# ---------------------------------------------------------------------------


def _load_state_dict(path: str, device: str = "cpu") -> dict:
    """Load state dict from either .safetensors or .pth file."""
    if path.endswith(".safetensors"):
        from safetensors.torch import load_file
        return load_file(path, device=device)
    else:
        # weights_only=False needed because upstream .pth files contain
        # nested OrderedDicts (e.g. stitching_retargeting_module)
        state_dict = torch.load(path, map_location=device, weights_only=False)
        # Handle nested checkpoint formats
        if isinstance(state_dict, dict):
            if "model" in state_dict:
                state_dict = state_dict["model"]
            elif "state_dict" in state_dict:
                state_dict = state_dict["state_dict"]
        # Remove 'module.' prefix from DDP keys (for non-nested dicts)
        from collections import OrderedDict
        cleaned = OrderedDict()
        for k, v in state_dict.items():
            if isinstance(v, torch.Tensor):
                cleaned[k.replace("module.", "")] = v
            else:
                # Preserve nested dicts (e.g. stitching sub-networks)
                cleaned[k] = v
        return cleaned


def _instantiate_model(model_type: str, config: dict, state_dict: dict,
                       device) -> torch.nn.Module:
    """Instantiate a model from config and state dict."""
    from .liveportrait.appearance_feature_extractor import (
        AppearanceFeatureExtractor,
    )
    from .liveportrait.motion_extractor import MotionExtractor
    from .liveportrait.warping_network import WarpingNetwork
    from .liveportrait.spade_generator import SPADEDecoder
    from .liveportrait.stitching_retargeting_network import (
        StitchingRetargetingNetwork,
    )

    model_params = config["model_params"][f"{model_type}_params"]

    if model_type == "appearance_feature_extractor":
        model = AppearanceFeatureExtractor(**model_params)
    elif model_type == "motion_extractor":
        model = MotionExtractor(**model_params)
    elif model_type == "warping_module":
        model = WarpingNetwork(**model_params)
    elif model_type == "spade_generator":
        model = SPADEDecoder(**model_params)
    elif model_type == "stitching_retargeting_module":
        # Special: contains stitching + lip + eye sub-networks
        sr_config = config["model_params"][
            "stitching_retargeting_module_params"]
        stitcher = StitchingRetargetingNetwork(**sr_config["stitching"])
        lip_rt = StitchingRetargetingNetwork(**sr_config["lip"])
        eye_rt = StitchingRetargetingNetwork(**sr_config["eye"])

        # Handle two checkpoint formats:
        # 1. Safetensors (flat): stitching.mlp.0.weight, retarget_lip.*, etc.
        # 2. Upstream .pth (nested): retarget_shoulder={module.mlp.*},
        #    retarget_mouth={module.mlp.*}, retarget_eye={module.mlp.*}
        from collections import OrderedDict

        if "retarget_shoulder" in state_dict and isinstance(
            state_dict["retarget_shoulder"], dict
        ):
            # .pth nested format — load each sub-dict directly
            def _strip_module(sd):
                return OrderedDict(
                    (k.replace("module.", ""), v)
                    for k, v in sd.items()
                    if isinstance(v, torch.Tensor)
                )

            stitcher.load_state_dict(
                _strip_module(state_dict["retarget_shoulder"]), strict=False)
            lip_rt.load_state_dict(
                _strip_module(state_dict["retarget_mouth"]), strict=False)
            eye_rt.load_state_dict(
                _strip_module(state_dict["retarget_eye"]), strict=False)
        else:
            # Safetensors flat format — split by prefix
            s_sd, l_sd, e_sd = {}, {}, {}
            for k, v in state_dict.items():
                if k.startswith("retarget_lip."):
                    l_sd[k.replace("retarget_lip.", "")] = v
                elif k.startswith("retarget_eye."):
                    e_sd[k.replace("retarget_eye.", "")] = v
                elif k.startswith("stitching."):
                    s_sd[k.replace("stitching.", "")] = v
                else:
                    # Try without prefix (some checkpoints)
                    s_sd[k] = v

            stitcher.load_state_dict(s_sd, strict=False)
            lip_rt.load_state_dict(l_sd, strict=False)
            eye_rt.load_state_dict(e_sd, strict=False)

        module_dict = {
            "stitching": stitcher.to(device).eval(),
            "lip": lip_rt.to(device).eval(),
            "eye": eye_rt.to(device).eval(),
        }
        return module_dict  # type: ignore
    else:
        raise ValueError(f"Unknown model type: {model_type}")

    model.load_state_dict(state_dict, strict=False)
    model = model.to(device).eval()
    model.requires_grad_(False)
    return model


# ---------------------------------------------------------------------------
#  Cached model state (in-process offloading)
# ---------------------------------------------------------------------------

_models: Optional[dict] = None


def load_models() -> dict:
    """Load and cache all LivePortrait models.

    On first call, downloads models if needed, frees VRAM from other
    AI models, and loads all 5 components. Subsequent calls return cached.

    Returns:
        Dict with keys: appearance_feature_extractor, motion_extractor,
        warping_module, spade_generator, stitching_retargeting_module,
        device, offload_device.
    """
    global _models
    if _models is not None:
        return _models

    device = _get_device()
    offload_device = _get_offload_device()
    config = _get_model_config()

    # Resolve model paths (downloads if needed)
    paths = {
        key: _find_or_download_model(key)
        for key in _MODEL_FILES
    }

    # Free VRAM from other models
    _free_vram()

    log.info("[LivePortrait] Loading models (offload_device=%s)...",
             offload_device)

    loaded = {}
    for model_type, path in paths.items():
        log.info("[LivePortrait] Loading %s from %s", model_type, path)
        state_dict = _load_state_dict(path, device="cpu")
        model = _instantiate_model(
            model_type, config, state_dict, offload_device)
        loaded[model_type] = model

    log.info("[LivePortrait] All models loaded and cached "
             "(offloaded to %s)", offload_device)

    _models = {
        **loaded,
        "device": device,
        "offload_device": offload_device,
    }
    return _models


def cleanup() -> None:
    """Free GPU memory and clear cached LivePortrait models."""
    global _models
    if _models is None:
        return

    models = _models
    _models = None

    try:
        offload = models["offload_device"]
        for key in _MODEL_FILES:
            obj = models.get(key)
            if obj is None:
                continue
            if isinstance(obj, dict):
                # stitching_retargeting_module is a dict of sub-networks
                for sub in obj.values():
                    if hasattr(sub, "to"):
                        try:
                            sub.to(offload)
                        except Exception:
                            pass
            elif hasattr(obj, "to"):
                try:
                    obj.to(offload)
                except Exception:
                    pass
    except Exception:
        pass
    del models

    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    gc.collect()
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        mm.soft_empty_cache()
    except (ImportError, AttributeError):
        pass
    log.info("[LivePortrait] Models unloaded")


# ---------------------------------------------------------------------------
#  Face detection (MediaPipe)
# ---------------------------------------------------------------------------


def _detect_face_bbox(image: np.ndarray) -> Optional[tuple]:
    """Detect the largest face bounding box using MediaPipe.

    Uses the shared FaceLandmarker from musetalk.face_detection (Tasks API)
    which is already proven to work in this project.

    Args:
        image: BGR uint8 image.

    Returns:
        (x1, y1, x2, y2) or None if no face found.
    """
    try:
        try:
            from .musetalk.face_detection import get_face_bbox
        except ImportError:
            from core.musetalk.face_detection import get_face_bbox  # type: ignore
    except ImportError:
        log.warning("[LivePortrait] face_detection module not available")
        return None

    bboxes = get_face_bbox(image)
    if not bboxes:
        return None

    # Pick the largest bbox
    best = max(bboxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
    return best


def _crop_face(image: np.ndarray, bbox: tuple,
               expand: float = 1.6) -> tuple:
    """Crop and expand face region for LivePortrait processing.

    Args:
        image: BGR uint8 image.
        bbox: (x1, y1, x2, y2) face bounding box.
        expand: Expansion factor around the face center.

    Returns:
        (crop_256, crop_matrix) where crop_256 is 256x256 BGR uint8
        and crop_matrix is the affine transform matrix for paste-back.
    """
    h, w = image.shape[:2]
    x1, y1, x2, y2 = bbox

    # Center and size
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    face_w = x2 - x1
    face_h = y2 - y1
    size = max(face_w, face_h) * expand

    # Crop region (may exceed image bounds — handled by warpAffine)
    half = size / 2
    src_pts = np.float32([
        [cx - half, cy - half],
        [cx + half, cy - half],
        [cx - half, cy + half],
    ])
    dst_pts = np.float32([
        [0, 0],
        [256, 0],
        [0, 256],
    ])

    M = cv2.getAffineTransform(src_pts, dst_pts)
    crop = cv2.warpAffine(
        image, M, (256, 256),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_REPLICATE,
    )

    M_inv = cv2.getAffineTransform(dst_pts, src_pts)
    return crop, M, M_inv


def _paste_back(canvas: np.ndarray, crop_512: np.ndarray,
                M_inv: np.ndarray) -> np.ndarray:
    """Paste the generated face back into the full frame with blending.

    Uses an elliptical Gaussian-blurred mask for seamless blending
    (no visible box outline).

    Args:
        canvas: Full-size BGR frame to paste onto.
        crop_512: Generated face, 512x512 BGR uint8.
        M_inv: Inverse affine transform from 256-crop space to canvas space.

    Returns:
        Blended full-size BGR frame.
    """
    h, w = canvas.shape[:2]

    # M_inv maps 256-space → canvas-space.
    # crop_512 is in 512-space (2x upscale from the model).
    # For affine y = A·x + b, substituting x_512 = 2·x_256:
    #   y = A·(x_512/2) + b = (A/2)·x_512 + b
    # So: divide the 2x2 rotation/scale part by 2, keep translation.
    M_inv_512 = M_inv.copy()
    M_inv_512[:, :2] = M_inv[:, :2] / 2.0  # scale A by 0.5
    # translation (column 2) stays unchanged

    warped = cv2.warpAffine(
        crop_512, M_inv_512, (w, h),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )

    # Create an elliptical mask with heavy Gaussian blur for seamless edges.
    # This eliminates the visible box outline that a rectangular feather creates.
    mask = np.zeros((512, 512), dtype=np.float32)
    center = (256, 256)
    axes = (220, 240)  # slightly taller than wide to cover forehead/chin
    cv2.ellipse(mask, center, axes, 0, 0, 360, 1.0, -1)  # filled ellipse
    # Heavy Gaussian blur for soft falloff (kernel must be odd)
    mask = cv2.GaussianBlur(mask, (101, 101), 0)
    mask = mask[:, :, None]  # HxWx1

    mask_warped = cv2.warpAffine(
        mask, M_inv_512, (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    if mask_warped.ndim == 2:
        mask_warped = mask_warped[:, :, None]

    # Alpha blend
    result = (
        mask_warped * warped.astype(np.float32)
        + (1 - mask_warped) * canvas.astype(np.float32)
    )
    return np.clip(result, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
#  Core inference helpers
# ---------------------------------------------------------------------------


def _prepare_source(img: np.ndarray, device) -> torch.Tensor:
    """Prepare a 256x256 face crop for model input.

    Args:
        img: HxWx3 uint8 BGR image (should be 256x256).
        device: Target device.

    Returns:
        1x3x256x256 float tensor, normalized to [0, 1].
    """
    if img.shape[:2] != (256, 256):
        img = cv2.resize(img, (256, 256), interpolation=cv2.INTER_LANCZOS4)
    x = img[np.newaxis].astype(np.float32) / 255.0
    x = np.clip(x, 0, 1)
    x = torch.from_numpy(x).permute(0, 3, 1, 2)  # 1xHxWx3 → 1x3xHxW
    return x.to(device)


def _get_kp_info(motion_extractor, x: torch.Tensor) -> dict:
    """Extract keypoint info from a face image.

    Args:
        motion_extractor: The motion extractor model.
        x: 1x3x256x256 float tensor.

    Returns:
        Dict with keys: pitch, yaw, roll, t, exp, scale, kp
        (all refined to degrees and reshaped).
    """
    with torch.no_grad():
        kp_info = motion_extractor(x)
        for k, v in kp_info.items():
            if isinstance(v, torch.Tensor):
                kp_info[k] = v.float()

    bs = kp_info['kp'].shape[0]
    kp_info['pitch'] = headpose_pred_to_degree(kp_info['pitch'])[:, None]
    kp_info['yaw'] = headpose_pred_to_degree(kp_info['yaw'])[:, None]
    kp_info['roll'] = headpose_pred_to_degree(kp_info['roll'])[:, None]
    kp_info['kp'] = kp_info['kp'].reshape(bs, -1, 3)
    kp_info['exp'] = kp_info['exp'].reshape(bs, -1, 3)

    return kp_info


def _transform_keypoint(kp_info: dict) -> torch.Tensor:
    """Transform keypoints with pose, shift, and expression deformation.

    Implements Equation 2: s * (R * x_c,s + exp) + t

    Args:
        kp_info: Dict from _get_kp_info.

    Returns:
        Transformed keypoints (bs, num_kp, 3).
    """
    kp = kp_info['kp']
    # pitch/yaw/roll are already in degrees from _get_kp_info
    pitch = kp_info['pitch']
    yaw = kp_info['yaw']
    roll = kp_info['roll']
    t, exp = kp_info['t'], kp_info['exp']
    scale = kp_info['scale']

    bs = kp.shape[0]
    num_kp = kp.shape[1] if kp.ndim == 3 else kp.shape[1] // 3

    rot_mat = get_rotation_matrix(pitch, yaw, roll)

    kp_transformed = kp.view(bs, num_kp, 3) @ rot_mat + exp.view(bs, num_kp, 3)
    kp_transformed *= scale[..., None]
    kp_transformed[:, :, 0:2] += t[:, None, 0:2]

    return kp_transformed


def _do_stitching(stitching_module, kp_source: torch.Tensor,
                  kp_driving: torch.Tensor) -> torch.Tensor:
    """Apply stitching to driving keypoints.

    Args:
        stitching_module: The stitching network (or None).
        kp_source: (bs, num_kp, 3)
        kp_driving: (bs, num_kp, 3)

    Returns:
        Adjusted kp_driving (bs, num_kp, 3).
    """
    if stitching_module is None:
        return kp_driving

    bs, num_kp = kp_source.shape[:2]
    kp_driving_new = kp_driving.clone()

    feat = concat_feat(kp_source, kp_driving_new)
    with torch.no_grad():
        delta = stitching_module(feat)

    delta_exp = delta[..., :3 * num_kp].reshape(bs, num_kp, 3)
    delta_tx_ty = delta[..., 3 * num_kp:3 * num_kp + 2].reshape(bs, 1, 2)

    kp_driving_new += delta_exp
    kp_driving_new[..., :2] += delta_tx_ty

    return kp_driving_new


def _warp_decode(warping_module, spade_generator, feature_3d: torch.Tensor,
                 kp_source: torch.Tensor,
                 kp_driving: torch.Tensor) -> np.ndarray:
    """Warp features and decode to output image.

    Args:
        warping_module: The warping network.
        spade_generator: The SPADE decoder.
        feature_3d: Source appearance features.
        kp_source: Source keypoints.
        kp_driving: Driving keypoints.

    Returns:
        Output image as HxWx3 uint8 BGR numpy array.
    """
    with torch.no_grad():
        ret_dct = warping_module(
            feature_3d, kp_source=kp_source, kp_driving=kp_driving)
        ret_dct['out'] = spade_generator(feature=ret_dct['out'])

        for k, v in ret_dct.items():
            if isinstance(v, torch.Tensor):
                ret_dct[k] = v.float()

    out = ret_dct['out']
    out = np.transpose(out.data.cpu().numpy(), [0, 2, 3, 1])  # 1xHxWx3 (RGB)
    out = np.clip(out * 255, 0, 255).astype(np.uint8)
    # Model outputs RGB — convert to BGR for OpenCV consistency
    return cv2.cvtColor(out[0], cv2.COLOR_RGB2BGR)


# ---------------------------------------------------------------------------
#  Core inference
# ---------------------------------------------------------------------------


@torch.no_grad()
def animate_portrait(
    source_path: str,
    driving_path: str,
    output_dir: Optional[str] = None,
    driving_multiplier: float = 1.0,
    relative_motion: bool = True,
) -> str:
    """Animate a portrait using motion from a driving video.

    Uses cached in-process models with GPU↔CPU offloading.
    Models are loaded on first call and cached for reuse.

    Args:
        source_path: Path to source image or video.
        driving_path: Path to driving video.
        output_dir: Output directory (uses temp dir if None).
        driving_multiplier: Scale factor for driving motion.
        relative_motion: If True, use relative motion transfer
            (subtract driving frame 0, add delta).

    Returns:
        Path to the output animated video file.
    """
    # ── Determine output path ──
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="ffmpega_liveportrait_")
    os.makedirs(output_dir, exist_ok=True)

    base = os.path.splitext(os.path.basename(source_path))[0]
    drv_base = os.path.splitext(os.path.basename(driving_path))[0]
    output_path = os.path.join(
        output_dir, f"{base}_{drv_base}_animated.mp4")

    # ── Load or reuse cached models ──
    models = load_models()
    afe = models["appearance_feature_extractor"]
    me = models["motion_extractor"]
    wm = models["warping_module"]
    sg = models["spade_generator"]
    srm = models["stitching_retargeting_module"]
    device = models["device"]
    offload_device = models["offload_device"]

    # Move models to GPU for inference
    log.info("[LivePortrait] Moving models to %s for inference", device)
    afe.to(device)
    me.to(device)
    wm.to(device)
    sg.to(device)
    if isinstance(srm, dict):
        for sub in srm.values():
            sub.to(device)

    try:
        # ── Read source ──
        log.info("[LivePortrait] Reading source: %s", source_path)
        ext = os.path.splitext(source_path)[1].lower()
        is_image = ext in (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff",
                           ".webp")

        if is_image:
            source_frame = cv2.imread(source_path)
            if source_frame is None:
                raise RuntimeError(
                    f"Failed to read source image: {source_path}")
        else:
            cap = cv2.VideoCapture(source_path)
            ret, source_frame = cap.read()
            cap.release()
            if not ret:
                raise RuntimeError(
                    f"Failed to read source video: {source_path}")

        # ── Detect and crop source face ──
        src_bbox = _detect_face_bbox(source_frame)
        if src_bbox is None:
            raise RuntimeError("No face detected in source")

        src_crop_256, src_M, src_M_inv = _crop_face(source_frame, src_bbox)

        # Convert BGR → RGB for model input
        src_rgb = cv2.cvtColor(src_crop_256, cv2.COLOR_BGR2RGB)
        src_tensor = _prepare_source(src_rgb, device)

        # ── Extract source features ──
        log.info("[LivePortrait] Extracting source features...")
        source_feature_3d = afe(src_tensor).float()
        source_kp_info = _get_kp_info(me, src_tensor)
        source_kp = _transform_keypoint(source_kp_info)

        # ── Read driving video ──
        log.info("[LivePortrait] Reading driving video: %s", driving_path)
        drv_cap = cv2.VideoCapture(driving_path)
        drv_fps = drv_cap.get(cv2.CAP_PROP_FPS) or 25.0
        drv_total = int(drv_cap.get(cv2.CAP_PROP_FRAME_COUNT))
        log.info("[LivePortrait] Driving video: %d frames at %.1f FPS",
                 drv_total, drv_fps)

        # ── Process driving frames ──
        result_frames = []
        driving_kp_0 = None  # First frame keypoints for relative motion

        frame_idx = 0
        while True:
            ret, drv_frame = drv_cap.read()
            if not ret:
                break

            # Detect face in driving frame
            drv_bbox = _detect_face_bbox(drv_frame)
            if drv_bbox is None:
                # No face in this driving frame — use source as-is
                result_frames.append(source_frame.copy())
                frame_idx += 1
                continue

            drv_crop_256, _, _ = _crop_face(drv_frame, drv_bbox)
            drv_rgb = cv2.cvtColor(drv_crop_256, cv2.COLOR_BGR2RGB)
            drv_tensor = _prepare_source(drv_rgb, device)

            # Extract driving motion
            driving_kp_info = _get_kp_info(me, drv_tensor)
            driving_kp = _transform_keypoint(driving_kp_info)

            if relative_motion:
                if driving_kp_0 is None:
                    driving_kp_0 = driving_kp.clone()

                # Relative motion: x_d = x_s + (x_d,i - x_d,0) * multiplier
                delta = (driving_kp - driving_kp_0) * driving_multiplier
                kp_driving = source_kp + delta
            else:
                kp_driving = driving_kp * driving_multiplier

            # Stitching
            stitching_net = srm["stitching"] if isinstance(srm, dict) else None
            kp_driving = _do_stitching(stitching_net, source_kp, kp_driving)

            # Warp + decode → 512x512 output (due to upscale=2)
            out_img = _warp_decode(
                wm, sg, source_feature_3d, source_kp, kp_driving)

            # Paste back into source frame
            result = _paste_back(source_frame.copy(), out_img, src_M_inv)
            result_frames.append(result)

            if frame_idx % 50 == 0:
                log.info("[LivePortrait] Processed %d/%d frames",
                         frame_idx + 1, drv_total)
            frame_idx += 1

        drv_cap.release()

        if not result_frames:
            raise RuntimeError("No frames generated")

        # ── Write output video ──
        log.info("[LivePortrait] Writing output video (%d frames)...",
                 len(result_frames))
        temp_video = os.path.join(output_dir, "_temp_animated.mp4")

        h, w = result_frames[0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # type: ignore[attr-defined]
        writer = cv2.VideoWriter(temp_video, fourcc, drv_fps, (w, h))

        for frame in result_frames:
            writer.write(frame)
        writer.release()

        # Re-encode with ffmpeg for compatibility + copy audio from driving
        cmd = [
            "ffmpeg", "-y", "-v", "warning",
            "-i", temp_video,
            "-i", driving_path,
            "-c:v", "libx264",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-map", "0:v:0",
            "-map", "1:a:0?",
            "-c:a", "aac",
            "-shortest",
            output_path,
        ]
        subprocess.run(cmd, check=True)

        # Clean up temp
        if os.path.isfile(temp_video):
            os.remove(temp_video)

        log.info("[LivePortrait] Animated video saved to %s", output_path)
        return output_path

    finally:
        # ── Offload models back to CPU ──
        log.info("[LivePortrait] Offloading models to %s", offload_device)
        try:
            afe.to(offload_device)
            me.to(offload_device)
            wm.to(offload_device)
            sg.to(offload_device)
            if isinstance(srm, dict):
                for sub in srm.values():
                    sub.to(offload_device)
        except Exception:
            pass
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        try:
            import comfy.model_management as mm  # type: ignore[import-not-found]
            mm.soft_empty_cache()
        except (ImportError, AttributeError):
            pass
