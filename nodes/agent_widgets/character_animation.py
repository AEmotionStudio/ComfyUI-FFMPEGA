# coding: utf-8
"""Pose-driven character animation widgets.

Extracted verbatim from FFMPEGAgentNode.INPUT_TYPES. The text is preserved
exactly because ComfyUI restores saved workflows by widget *position* — see
tests/test_widget_order.py, which pins the emitted order.

Each function is called once per INPUT_TYPES() call, so dropdowns that read
the filesystem (LoRA lists, expression presets) stay dynamic.
"""

from __future__ import annotations

import folder_paths  # type: ignore[import-not-found]
from ._helpers import _svi_samplers
from ._helpers import _svi_schedulers


def scail2() -> dict:
    """Advanced: SCAIL-2 (native pose-driven character animation)."""
    return {
        "scail2_width": ("INT", {
            "default": 512,
            "min": 32,
            "max": 2048,
            "step": 32,
            "tooltip": "Output width in px (used in 'scail2' no_llm_mode). "
                       "Snapped to a multiple of 32.",
        }),
        "scail2_height": ("INT", {
            "default": 896,
            "min": 32,
            "max": 2048,
            "step": 32,
            "tooltip": "Output height in px (used in 'scail2' no_llm_mode). "
                       "Snapped to a multiple of 32.",
        }),
        "scail2_length": ("INT", {
            "default": 81,
            "min": 5,
            "max": 100000,
            "step": 4,
            "tooltip": "Number of frames to generate (used in 'scail2' no_llm_mode). "
                       "SCAIL-2 is trained on 81-frame chunks (4n+1); values above 81 are "
                       "generated chunk-by-chunk (extend), each anchored on the previous "
                       "chunk's tail for coherence. Limited by the driving video length.",
        }),
        "scail2_pose_extend": (["pingpong", "loop", "hold_last", "none"], {
            "default": "pingpong",
            "tooltip": "When length exceeds the driving video, how to keep guiding motion "
                       "past where the pose runs out (used in 'scail2' no_llm_mode). "
                       "'pingpong' bounces the motion forward/back (smoothest); 'loop' "
                       "repeats from the start; 'hold_last' freezes on the final pose; "
                       "'none' lets the model freely hallucinate the tail. No effect when "
                       "length ≤ driving frames.",
        }),
        "scail2_steps": ("INT", {
            "default": 6,
            "min": 1,
            "max": 100,
            "step": 1,
            "tooltip": "Diffusion sampling steps (used in 'scail2' no_llm_mode). "
                       "6 suits the distill-LoRA fast path; raise for full-step quality.",
        }),
        "scail2_cfg": ("FLOAT", {
            "default": 1.0,
            "min": 1.0,
            "max": 15.0,
            "step": 0.5,
            "tooltip": "Classifier-free guidance scale (used in 'scail2' no_llm_mode). "
                       "1.0 for the distill-LoRA fast path.",
        }),
        "scail2_shift": ("FLOAT", {
            "default": 5.0,
            "min": 0.0,
            "max": 100.0,
            "step": 0.5,
            "tooltip": "ModelSamplingSD3 shift (used in 'scail2' no_llm_mode). Default 5.0.",
        }),
        "scail2_seed": ("INT", {
            "default": 0,
            "min": 0,
            "max": 2147483647,
            "step": 1,
            "tooltip": "Random seed (used in 'scail2' no_llm_mode). 0 = first seed.",
        }),
        "scail2_sampler": (_svi_samplers, {
            "default": "euler",
            "tooltip": "Sampler (used in 'scail2' no_llm_mode). "
                       "'euler' matches the reference SCAIL-2 workflow.",
        }),
        "scail2_scheduler": (_svi_schedulers, {
            "default": "simple",
            "tooltip": "Scheduler (used in 'scail2' no_llm_mode). "
                       "'simple' matches the reference SCAIL-2 workflow.",
        }),
        "scail2_denoise": ("FLOAT", {
            "default": 1.0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.01,
            "tooltip": "Denoise strength (used in 'scail2' no_llm_mode). "
                       "1.0 = full denoise.",
        }),
        "scail2_replacement_mode": ("BOOLEAN", {
            "default": False,
            "tooltip": "Replacement vs Animation mode (used in 'scail2' no_llm_mode). "
                       "False = Animation (drive the reference character with the video's pose). "
                       "True = Replacement (swap the masked subject into the driving scene).",
        }),
        "scail2_sort_by": (["left_to_right", "area", "none"], {
            "default": "left_to_right",
            "tooltip": "Palette assignment order across the colored masks "
                       "(used in 'scail2' no_llm_mode). Keeps each identity the same "
                       "color in the reference and pose-video masks.",
        }),
        "scail2_object_indices": ("STRING", {
            "default": "",
            "tooltip": "Comma-separated subject indices to keep, e.g. '0,2' "
                       "(used in 'scail2' no_llm_mode). Empty = all detected subjects.",
        }),
        "scail2_composite_direction": (["horizontal", "vertical"], {
            "default": "horizontal",
            "tooltip": "How multiple reference images (image_b, image_c, …) are "
                       "composited into the single SCAIL-2 reference (used in 'scail2' "
                       "no_llm_mode). Only matters with 2+ references.",
        }),
        "scail2_main_reference": (["last", "first"], {
            "default": "last",
            "tooltip": "Which connected reference is the 'main' one — it's CLIP-vision "
                       "encoded, so it drives identity most strongly (used in 'scail2' "
                       "no_llm_mode). 'last' matches the workflow convention that the "
                       "last/closest reference is the strongest.",
        }),
        "scail2_color_match": ("BOOLEAN", {
            "default": False,
            "tooltip": "On long extends (length > 81), color-match each chunk to the "
                       "previous chunk's last frame (Reinhard) to stop slow exposure/hue "
                       "drift (used in 'scail2' no_llm_mode). No effect on single-chunk "
                       "(≤81-frame) runs.",
        }),
        "scail2_blockswap_blocks": ("INT", {
            "default": 0,
            "min": 0,
            "max": 40,
            "tooltip": "Wan 2.1 transformer blocks (of 40) worth of weights kept in "
                       "CPU RAM during sampling (block swap). 0 = disabled. "
                       "Higher = less VRAM, slower. Try 4-8 if you hit OOM. "
                       "Only used when no_llm_mode = 'scail2'.",
        }),
        "scail2_tiled_vae": ("BOOLEAN", {
            "default": False,
            "tooltip": "Decode video latents with tiled VAE to reduce VRAM spikes "
                       "during decode. Use if VAE decode OOMs. "
                       "Only used when no_llm_mode = 'scail2'.",
        }),
        "scail2_subject": ("STRING", {
            "default": "person",
            "tooltip": "What SAM 3.1 should segment for the mask (used in 'scail2' "
                       "no_llm_mode) — a SHORT noun like 'person', 'bear', 'dog'. "
                       "Keep this separate from the animation prompt: a full sentence "
                       "makes SAM over-detect, giving splotchy multi-colored masks. "
                       "For mixed subjects, separate with ';' (e.g. 'man; dog') — each "
                       "is detected as its own identity/color. Ignored when mask_points "
                       "are supplied.",
        }),
        "scail2_max_objects": ("INT", {
            "default": 1,
            "min": 1,
            "max": 6,
            "step": 1,
            "tooltip": "How many subjects (identities) SAM 3.1 tracks (used in 'scail2' "
                       "no_llm_mode). 1 = single character (mask is solid blue, the most "
                       "stable). Raise for multi-person; each identity gets its own color. "
                       "Auto-raised to the number of reference images you connect.",
        }),
        "scail2_detection_threshold": ("FLOAT", {
            "default": 0.5,
            "min": 0.0,
            "max": 1.0,
            "step": 0.05,
            "tooltip": "SAM 3.1 new-object detection confidence (used in 'scail2' "
                       "no_llm_mode). Higher = fewer/cleaner detections (less likely to "
                       "pick up spurious extra subjects). Matches SAM3 Video Track.",
        }),
        "scail2_detect_interval": ("INT", {
            "default": 2,
            "min": 1,
            "max": 30,
            "step": 1,
            "tooltip": "How often (in frames) SAM 3.1 re-runs detection for NEW objects "
                       "(used in 'scail2' no_llm_mode). Higher = more stable identities / "
                       "less color flicker; lower = catches subjects that appear later. "
                       "Matches SAM3 Video Track (default 2).",
        }),
        "scail2_point_src_width": ("INT", {
            "default": 0,
            "min": 0,
            "max": 8192,
            "step": 1,
            "tooltip": "Override the coordinate-space WIDTH of mask_points (used in "
                       "'scail2' no_llm_mode). 0 = auto (taken from the point selector's "
                       "image_width). Set only if your points come from a source that "
                       "doesn't report its dimensions.",
        }),
        "scail2_point_src_height": ("INT", {
            "default": 0,
            "min": 0,
            "max": 8192,
            "step": 1,
            "tooltip": "Override the coordinate-space HEIGHT of mask_points (used in "
                       "'scail2' no_llm_mode). 0 = auto (taken from the point selector's "
                       "image_height).",
        }),
        # Dynamic LoRA slots (a → d): lightx2v distill, DPO, etc.
        # Slot b appears when a ≠ "none", c when b ≠ "none", etc.
        **{f"scail2_lora_{s}": (["none"] + ([
            f for f in folder_paths.get_filename_list("loras")
        ] if hasattr(folder_paths, "get_filename_list") else []), {
            "default": "none",
            "tooltip": f"LoRA slot {s.upper()} for SCAIL-2 (used in 'scail2' no_llm_mode). "
                       "Select a LoRA file (e.g. lightx2v distill, DPO). "
                       "Selecting a value reveals the next slot.",
        }) for s in ("a", "b", "c", "d")},
        **{f"scail2_lora_strength_{s}": ("FLOAT", {
            "default": 1.0,
            "min": 0.0,
            "max": 2.0,
            "step": 0.05,
            "tooltip": f"Strength for SCAIL-2 LoRA slot {s.upper()} "
                       "(used in 'scail2' no_llm_mode). 1.0 = full strength.",
        }) for s in ("a", "b", "c", "d")},
    }

def wan_animate() -> dict:
    """Advanced: Wan-Animate."""
    return {
        "wan_animate_mode": (["animate", "replace"], {
            "default": "animate",
            "tooltip": "Wan-Animate mode (used in 'wan_animate' no_llm_mode). "
                       "'animate' = transfer motion to reference character. "
                       "'replace' = replace person in driving video with reference character.",
        }),
        "wan_animate_steps": ("INT", {
            "default": 20,
            "min": 1,
            "max": 100,
            "tooltip": "Number of denoising steps (used in 'wan_animate' no_llm_mode). "
                       "Higher = better quality but slower. 15-30 typical.",
        }),
        "wan_animate_guidance": ("FLOAT", {
            "default": 1.0,
            "min": 0.0,
            "max": 20.0,
            "step": 0.5,
            "tooltip": "Classifier-free guidance scale (used in 'wan_animate' no_llm_mode). "
                       "1.0 = no guidance (fastest). Higher = more prompt adherence.",
        }),
        "wan_animate_seed": ("INT", {
            "default": 42,
            "min": 0,
            "max": 2147483647,
            "tooltip": "Random seed for reproducibility (used in 'wan_animate' no_llm_mode).",
        }),
        "wan_animate_num_frames": ("INT", {
            "default": 81,
            "min": 5,
            "max": 161,
            "step": 4,
            "tooltip": "Number of output frames (used in 'wan_animate' no_llm_mode). "
                       "Must be 4n+1 for Wan 2.2 (e.g. 33, 49, 81, 121). "
                       "If fewer driving frames exist, uses the driving frame count.",
        }),
        "wan_animate_height": ("INT", {
            "default": 480,
            "min": 128,
            "max": 1080,
            "step": 16,
            "tooltip": "Output height in pixels (used in 'wan_animate' no_llm_mode). "
                       "Must be divisible by 16.",
        }),
        "wan_animate_width": ("INT", {
            "default": 832,
            "min": 128,
            "max": 1920,
            "step": 16,
            "tooltip": "Output width in pixels (used in 'wan_animate' no_llm_mode). "
                       "Must be divisible by 16.",
        }),
        "wan_animate_pose_strength": ("FLOAT", {
            "default": 1.0,
            "min": 0.0,
            "max": 2.0,
            "step": 0.05,
            "tooltip": "Pose conditioning strength (used in 'wan_animate' no_llm_mode). "
                       "1.0 = normal. Higher = stronger pose adherence.",
        }),
        "wan_animate_face_strength": ("FLOAT", {
            "default": 1.0,
            "min": 0.0,
            "max": 2.0,
            "step": 0.05,
            "tooltip": "Face conditioning strength (used in 'wan_animate' no_llm_mode). "
                       "1.0 = normal. Higher = stronger face identity preservation.",
        }),
        # Dynamic LoRA slots (a → d), each with a strength slider.
        # Slot b appears when slot a ≠ "none", c when b ≠ "none", etc.
        **{f"wan_animate_lora_{s}": (["none"] + ([
            f for f in folder_paths.get_filename_list("loras")
        ] if hasattr(folder_paths, "get_filename_list") else []), {
            "default": "none",
            "tooltip": f"LoRA slot {s.upper()} for Wan-Animate (used in 'wan_animate' no_llm_mode). "
                       "Select a LoRA file. Selecting a value reveals the next slot.",
        }) for s in ("a", "b", "c", "d")},
        **{f"wan_animate_lora_strength_{s}": ("FLOAT", {
            "default": 1.0,
            "min": 0.0,
            "max": 2.0,
            "step": 0.05,
            "tooltip": f"Strength for LoRA slot {s.upper()} (used in 'wan_animate' no_llm_mode). "
                       "1.0 = full strength.",
        }) for s in ("a", "b", "c", "d")},
    }
