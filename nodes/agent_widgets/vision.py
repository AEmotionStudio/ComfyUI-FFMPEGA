# coding: utf-8
"""Depth, normals and human-centric vision widgets.

Extracted verbatim from FFMPEGAgentNode.INPUT_TYPES. The text is preserved
exactly because ComfyUI restores saved workflows by widget *position* — see
tests/test_widget_order.py, which pins the emitted order.

Each function is called once per INPUT_TYPES() call, so dropdowns that read
the filesystem (LoRA lists, expression presets) stay dynamic.
"""

from __future__ import annotations



def marigold() -> dict:
    """Advanced: Marigold."""
    return {
        "marigold_output_type": (["depth", "normals", "appearance", "lighting"], {
            "default": "depth",
            "tooltip": "Marigold output type (used in 'marigold' no_llm_mode or agentic mode). "
                       "'depth' = monocular depth map. "
                       "'normals' = surface normals. "
                       "'appearance' = albedo + roughness + metallicity. "
                       "'lighting' = albedo + shading + residual.",
        }),
        "marigold_colormap": (["Spectral", "gray", "inferno", "turbo", "plasma", "magma", "viridis", "hot", "bone"], {
            "default": "Spectral",
            "tooltip": "Depth map colormap (used in 'marigold' no_llm_mode, depth output only). "
                       "'Spectral' = standard red-to-blue depth map. "
                       "'gray' = B&W depth (for ControlNet/compositing). "
                       "Others are artistic colormaps for creative visualization.",
        }),
    }

def normalcrafter() -> dict:
    """Advanced: NormalCrafter."""
    return {
        "normalcrafter_max_res": (["auto", "1024", "768", "512"], {
            "default": "auto",
            "tooltip": "NormalCrafter max resolution (used in 'normalcrafter' no_llm_mode). "
                       "'auto' = auto-detect GPU VRAM and pick the safest resolution (~12 GB → 768, ~8 GB → 512). "
                       "'1024' = highest quality (needs ~12+ GB VRAM). "
                       "'768' = balanced quality/VRAM (~8–12 GB). "
                       "'512' = lowest VRAM (~6 GB).",
        }),
    }

def video_depth() -> dict:
    """Advanced: Video Depth Anything."""
    return {
        "video_depth_encoder": (["vits", "vitb", "vitl"], {
            "default": "vits",
            "tooltip": "Video Depth Anything model size (used in 'video_depth' no_llm_mode or agentic mode). "
                       "'vits' = Small (~7 GB, fastest). "
                       "'vitb' = Base (~12 GB). "
                       "'vitl' = Large (~24 GB, best quality).",
        }),
        "video_depth_colormap": (["gray", "inferno", "turbo", "plasma", "magma", "viridis", "hot", "bone"], {
            "default": "gray",
            "tooltip": "Depth map colormap (used in 'video_depth' no_llm_mode). "
                       "'gray' = standard B&W depth (for ControlNet/compositing). "
                       "Others are artistic colormaps for creative visualization.",
        }),
    }

def sapiens2() -> dict:
    """Advanced: Sapiens2."""
    return {
        # Meta Sapiens2 (ICLR 2026) human-centric vision. Six task
        # families × four sizes. License: Meta Proprietary —
        # no surveillance/biometric/deepfake use; attribution required.
        "sapiens2_task": (["pose", "seg", "normal", "pointmap", "matting", "pretrain"], {
            "default": "pose",
            "tooltip": "Sapiens2 task (used in 'sapiens2' no_llm_mode). "
                       "'pose' = 308-keypoint top-down pose (body+face+hands+feet) — needs DETR detector (auto-downloaded). "
                       "'seg' = 29-class human body-part segmentation overlay. "
                       "'normal' = per-pixel surface normals. "
                       "'pointmap' = 3D pointmap (z-channel visualized via turbo colormap). "
                       "'matting' = human matting (alpha composited on green; 1B only). "
                       "'pretrain' = raw backbone features (PCA-visualized RGB).",
        }),
        "sapiens2_size": (["0.4b", "0.8b", "1b", "5b", "5b (fp8)"], {
            "default": "1b",
            "tooltip": "Sapiens2 model size (used in 'sapiens2' no_llm_mode). "
                       "'0.4b' = ~1–2 GB VRAM, fast. "
                       "'0.8b' = ~2–4 GB VRAM. "
                       "'1b' = ~3–6 GB VRAM, balanced (recommended default). "
                       "'5b' = ~10 GB fp16 / ~20 GB fp32 (auto-picks fp8 on RTX 40-series+), best quality. "
                       "'5b (fp8)' = quantized 5B, ~5 GB VRAM, needs fp8-capable GPU (compute cap >= 8.9, "
                       "RTX 40-series+); auto-downloads the pre-converted *_fp8.safetensors from the mirror "
                       "(dense tasks only — pose/pretrain ignore it). "
                       "Note: matting task only ships in 1B.",
        }),
        "sapiens2_seg_alpha": ("FLOAT", {
            "default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05,
            "tooltip": "Segmentation overlay opacity (0=invisible, 1=opaque). "
                       "Only used when sapiens2_task = 'seg'.",
        }),
        "sapiens2_pose_kpt_thr": ("FLOAT", {
            "default": 0.3, "min": 0.0, "max": 1.0, "step": 0.05,
            "tooltip": "Pose keypoint visualization threshold (only keypoints with score >= threshold are drawn). "
                       "Only used when sapiens2_task = 'pose'.",
        }),
        "sapiens2_pose_radius": ("INT", {
            "default": 6, "min": 1, "max": 32, "step": 1,
            "tooltip": "Keypoint marker radius in pixels. "
                       "Only used when sapiens2_task = 'pose'.",
        }),
        "sapiens2_pose_thickness": ("INT", {
            "default": 4, "min": 1, "max": 32, "step": 1,
            "tooltip": "Skeleton line thickness in pixels. "
                       "Only used when sapiens2_task = 'pose'.",
        }),
    }
