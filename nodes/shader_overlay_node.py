"""ShaderOverlayNode — apply GPU shader effects without an LLM.

A standalone ComfyUI node that applies libplacebo GLSL shaders to video
content. Supports built-in presets and custom user-provided shaders,
with automatic FFmpeg-only fallback when GPU (Vulkan/libplacebo) is
unavailable.

Usage patterns:
- **Standalone**: Load video → ShaderOverlay → Save/Preview
- **Chained**: Stack multiple ShaderOverlay nodes for combined effects
- **With masking**: Use after SAM3 mask generation for targeted effects
"""

from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import tempfile
import time

import numpy as np
import torch

log = logging.getLogger("ffmpega.shader_node")

try:
    from ..core.bin_paths import get_ffmpeg_bin, get_ffprobe_bin
except ImportError:
    from core.bin_paths import get_ffmpeg_bin, get_ffprobe_bin  # type: ignore

# Available preset names (populated at import time)
_PRESET_CHOICES: list[str] = ["none"]

try:
    from ..core.shader_support import list_available_shaders, list_categorized_presets
except ImportError:
    try:
        from core.shader_support import list_available_shaders, list_categorized_presets
    except ImportError:
        list_available_shaders = None  # type: ignore
        list_categorized_presets = None  # type: ignore

if list_categorized_presets is not None:
    _PRESET_CHOICES = ["none"] + list_categorized_presets()
elif list_available_shaders is not None:
    _PRESET_CHOICES = ["none"] + sorted(list_available_shaders())


class ShaderOverlayNode:
    """Apply GPU-accelerated shader effects to video.

    Uses FFmpeg's libplacebo filter for Vulkan-based GLSL shader
    processing. Falls back to FFmpeg filter approximations when
    GPU acceleration is unavailable.
    """

    CATEGORY = "FFMPEGA"
    FUNCTION = "process"
    OUTPUT_NODE = False

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("images", "video_path")

    @classmethod
    def INPUT_TYPES(cls):
        _RES_CHOICES = ["0.25", "0.5", "1.0", "2.0"]
        _BLEND_CHOICES = [
            "normal", "addition", "multiply",
            "screen", "overlay", "softlight",
        ]
        return {
            "required": {
                "preset": (_PRESET_CHOICES, {
                    "default": "none",
                    "tooltip": (
                        "Built-in shader preset to apply. "
                        "Select 🎲 random for a surprise."
                    ),
                }),
                "intensity": ("FLOAT", {
                    "default": 1.0,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.05,
                    "display": "slider",
                    "tooltip": (
                        "Blend intensity between original (0.0) and fully "
                        "shaded (1.0). At partial intensity, the shader "
                        "output is blended with the original frame."
                    ),
                }),
            },
            "optional": {
                "images": ("IMAGE", {
                    "tooltip": "Video frames as IMAGE tensor [N,H,W,3].",
                }),
                "video_path": ("STRING", {
                    "default": "",
                    "forceInput": True,
                    "tooltip": "Path to a video file on disk.",
                }),
                "custom_shader_path": ("STRING", {
                    "default": "",
                    "tooltip": (
                        "Path to a custom .glsl shader file. When set, "
                        "overrides the preset selection. Must be a valid "
                        "mpv/libplacebo HOOK-format GLSL file."
                    ),
                }),
                "preset_2": (_PRESET_CHOICES, {
                    "default": "none",
                    "tooltip": "Second stacked shader layer.",
                }),
                "intensity_2": ("FLOAT", {
                    "default": 1.0,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.05,
                    "display": "slider",
                    "tooltip": "Intensity for the second shader layer.",
                }),
                "preset_3": (_PRESET_CHOICES, {
                    "default": "none",
                    "tooltip": "Third stacked shader layer.",
                }),
                "intensity_3": ("FLOAT", {
                    "default": 1.0,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.05,
                    "display": "slider",
                    "tooltip": "Intensity for the third shader layer.",
                }),
                "speed": ("FLOAT", {
                    "default": 1.0,
                    "min": 0.1,
                    "max": 5.0,
                    "step": 0.1,
                    "display": "slider",
                    "tooltip": "Animation speed multiplier (1.0 = normal).",
                }),
                "hue_shift": ("FLOAT", {
                    "default": 0.0,
                    "min": 0.0,
                    "max": 360.0,
                    "step": 1.0,
                    "display": "slider",
                    "tooltip": "Post-shader hue rotation in degrees.",
                }),
                "blend_mode": (_BLEND_CHOICES, {
                    "default": "normal",
                    "tooltip": (
                        "Blend mode when intensity < 1.0. "
                        "Controls how the shader mixes with the original."
                    ),
                }),
                "phase": ("FLOAT", {
                    "default": 0.0,
                    "min": 0.0,
                    "max": 10.0,
                    "step": 0.1,
                    "tooltip": (
                        "Animation phase offset in seconds. "
                        "Starts the effect at a different point in time."
                    ),
                }),
                "shader_params": ("STRING", {
                    "default": "",
                    "placeholder": '{"key": "value"}',
                    "tooltip": (
                        "JSON parameter overrides for the shader. "
                        "Reserved for future per-shader customization."
                    ),
                }),
                "resolution_scale": (_RES_CHOICES, {
                    "default": "1.0",
                    "tooltip": (
                        "Shader processing resolution scale. "
                        "0.5 = half res (faster), 2.0 = double (quality)."
                    ),
                }),
                "mask_target": ("STRING", {
                    "default": "",
                    "placeholder": "e.g. the car, the person's face",
                    "tooltip": (
                        "SAM3 text prompt — when set, the shader is applied "
                        "only to the detected object region. Leave empty to "
                        "apply the shader to the entire frame."
                    ),
                }),
                "invert_mask": ("BOOLEAN", {
                    "default": False,
                    "label_on": "apply to background",
                    "label_off": "apply to target",
                    "tooltip": (
                        "When ON, applies the shader to everything EXCEPT "
                        "the masked target (i.e. the background)."
                    ),
                }),
                "fps": ("FLOAT", {
                    "default": 24.0,
                    "min": 1.0,
                    "max": 120.0,
                    "step": 0.01,
                    "tooltip": (
                        "Frame rate for IMAGE tensor input encoding. "
                        "Ignored when video_path is used."
                    ),
                }),
            },
        }

    @classmethod
    def IS_CHANGED(cls, preset="none", intensity=1.0,
                   custom_shader_path="", mask_target="", **kwargs):
        import random as _rnd
        m = hashlib.sha256()
        # Random mode always returns unique hash to force re-execution
        if preset == "🎲 random":
            m.update(str(_rnd.random()).encode())
            return m.hexdigest()
        m.update(preset.encode())
        m.update(str(intensity).encode())
        m.update(custom_shader_path.encode())
        m.update(mask_target.encode())
        for k in ("preset_2", "preset_3", "intensity_2", "intensity_3",
                  "speed", "hue_shift", "blend_mode", "phase",
                  "shader_params", "resolution_scale"):
            m.update(str(kwargs.get(k, "")).encode())
        return m.hexdigest()

    def process(
        self,
        preset: str = "none",
        intensity: float = 1.0,
        images=None,
        video_path: str = "",
        custom_shader_path: str = "",
        preset_2: str = "none",
        intensity_2: float = 1.0,
        preset_3: str = "none",
        intensity_3: float = 1.0,
        speed: float = 1.0,
        hue_shift: float = 0.0,
        blend_mode: str = "normal",
        phase: float = 0.0,
        shader_params: str = "",
        resolution_scale: str = "1.0",
        mask_target: str = "",
        invert_mask: bool = False,
        fps: float = 24.0,
    ):
        """Apply shader(s) and return processed frames + video path."""
        # Treat category headers as no-op
        if preset.startswith("──"):
            preset = "none"
        if preset_2.startswith("──"):
            preset_2 = "none"
        if preset_3.startswith("──"):
            preset_3 = "none"

        empty_frames = torch.zeros(1, 512, 512, 3)

        # ── Resolve input ────────────────────────────────────────────
        resolved_path = None

        if video_path and video_path.strip():
            vp = video_path.strip()
            if os.path.isfile(vp):
                resolved_path = vp
            else:
                log.warning("[ShaderOverlay] video_path not found: %s", vp)

        if resolved_path is None and images is not None:
            resolved_path = self._images_to_temp_video(images, fps)

        if resolved_path is None:
            log.info("[ShaderOverlay] No input connected")
            return (empty_frames, "")

        # ── Check if there is anything to do ──────────────────────────
        has_custom = bool(custom_shader_path and custom_shader_path.strip())
        if preset == "none" and preset_2 == "none" and preset_3 == "none" and not has_custom:
            frames = self._decode_video(resolved_path)
            return (frames, resolved_path)

        if intensity <= 0.0 and not has_custom:
            frames = self._decode_video(resolved_path)
            return (frames, resolved_path)

        # ── Import shader support ────────────────────────────────────
        try:
            try:
                from ..core.shader_support import (
                    has_libplacebo,
                    resolve_shader_path,
                    build_shader_filter,
                    get_fallback_filter,
                    pick_random_shader,
                )
            except ImportError:
                from core.shader_support import (  # type: ignore
                    has_libplacebo,
                    resolve_shader_path,
                    build_shader_filter,
                    get_fallback_filter,
                    pick_random_shader,
                )
        except ImportError:
            log.error(
                "[ShaderOverlay] shader_support module not available "
                "— cannot apply shader effects."
            )
            frames = self._decode_video(resolved_path)
            return (frames, resolved_path)

        # validate_path is optional — only needed for custom shader paths
        _validate_path = None
        try:
            try:
                from ..core.sanitize import validate_path as _validate_path
            except ImportError:
                from core.sanitize import validate_path as _validate_path  # type: ignore
        except ImportError:
            pass

        # ── Resolve random presets ────────────────────────────────────
        for _label, _val in [("preset", preset), ("preset_2", preset_2),
                             ("preset_3", preset_3)]:
            if _val == "🎲 random":
                rand_name = pick_random_shader()
                if rand_name:
                    log.info("[ShaderOverlay] 🎲 random → '%s' for %s", rand_name, _label)
                    if _label == "preset":
                        preset = rand_name
                    elif _label == "preset_2":
                        preset_2 = rand_name
                    else:
                        preset_3 = rand_name

        # ── Collect shader paths ─────────────────────────────────────
        shader_paths: list[str] = []
        preset_names: list[str] = []

        if has_custom:
            custom = custom_shader_path.strip()
            if _validate_path is not None:
                try:
                    _validate_path(custom, allowed_extensions={".glsl"})
                except Exception as e:
                    log.error("[ShaderOverlay] Invalid custom shader path: %s", e)
                    frames = self._decode_video(resolved_path)
                    return (frames, resolved_path)

            if not custom.endswith(".glsl"):
                log.error("[ShaderOverlay] Custom shader must be a .glsl file")
                frames = self._decode_video(resolved_path)
                return (frames, resolved_path)

            if not os.path.isfile(custom):
                log.error("[ShaderOverlay] Custom shader not found: %s", custom)
                frames = self._decode_video(resolved_path)
                return (frames, resolved_path)

            shader_paths.append(custom)
            preset_names.append(os.path.basename(custom).replace(".glsl", ""))
        else:
            # Primary preset
            if preset != "none":
                sp = resolve_shader_path(preset)
                if sp:
                    shader_paths.append(str(sp))
                    preset_names.append(preset)
                else:
                    log.error("[ShaderOverlay] Preset '%s' not found", preset)

        # Chained presets (2 and 3)
        for chain_preset, chain_intensity in [(preset_2, intensity_2),
                                              (preset_3, intensity_3)]:
            if chain_preset != "none" and chain_intensity > 0:
                sp = resolve_shader_path(chain_preset)
                if sp:
                    shader_paths.append(str(sp))
                    preset_names.append(chain_preset)
                else:
                    log.warning("[ShaderOverlay] Chained preset '%s' not found", chain_preset)

        if not shader_paths:
            frames = self._decode_video(resolved_path)
            return (frames, resolved_path)

        # ── Parse resolution scale ───────────────────────────────────
        try:
            res_scale = float(resolution_scale)
        except (ValueError, TypeError):
            res_scale = 1.0
        res_scale = max(0.25, min(2.0, res_scale))

        # ── Build FFmpeg command ─────────────────────────────────────
        ffmpeg = get_ffmpeg_bin()
        if not ffmpeg:
            log.error("[ShaderOverlay] FFmpeg not found")
            frames = self._decode_video(resolved_path)
            return (frames, resolved_path)

        temp_dir = tempfile.mkdtemp(prefix="ffmpega_shader_")
        output_path = os.path.join(temp_dir, "shader_output.mp4")

        display_name = "+".join(preset_names)

        if has_libplacebo():
            log.info(
                "⚡ [ShaderOverlay] Applying '%s' via libplacebo (GPU) "
                "[speed=%.1f, hue=%.0f°, blend=%s, res=%.2fx]",
                display_name, speed, hue_shift, blend_mode, res_scale,
            )
            vf_filters, fc = build_shader_filter(
                shader_paths,
                intensity=intensity,
                blend_mode=blend_mode,
                speed=speed,
                hue_shift=hue_shift,
                phase=phase,
                resolution_scale=res_scale,
            )

            if fc:
                cmd = [
                    ffmpeg, "-y", "-i", resolved_path,
                    "-filter_complex", fc,
                    "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                    "-pix_fmt", "yuv420p", "-c:a", "copy",
                    output_path,
                ]
            elif vf_filters:
                cmd = [
                    ffmpeg, "-y", "-i", resolved_path,
                    "-vf", ",".join(vf_filters),
                    "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                    "-pix_fmt", "yuv420p", "-c:a", "copy",
                    output_path,
                ]
            else:
                frames = self._decode_video(resolved_path)
                return (frames, resolved_path)
        else:
            # Fallback to FFmpeg filters (first preset only)
            fallback = get_fallback_filter(preset_names[0]) if preset_names else None
            if not fallback:
                log.warning(
                    "⚠️  [ShaderOverlay] No fallback for '%s' and libplacebo "
                    "unavailable. Install FFmpeg with Vulkan support for "
                    "GPU-accelerated shaders.",
                    display_name,
                )
                frames = self._decode_video(resolved_path)
                return (frames, resolved_path)

            log.warning(
                "⚠️  [ShaderOverlay] libplacebo not available — using FFmpeg "
                "approximation for '%s'. Quality may differ from GPU path. "
                "Install FFmpeg with --enable-libplacebo --enable-vulkan "
                "for full shader support.",
                display_name,
            )

            # Add hue shift to fallback if requested
            if hue_shift > 0:
                fallback = f"{fallback},hue=h={hue_shift:.1f}"

            if intensity >= 1.0:
                cmd = [
                    ffmpeg, "-y", "-i", resolved_path,
                    "-vf", fallback,
                    "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                    "-pix_fmt", "yuv420p", "-c:a", "copy",
                    output_path,
                ]
            else:
                fc = (
                    f"[0:v]split[orig][fx];"
                    f"[fx]{fallback}[effected];"
                    f"[orig][effected]blend=all_mode={blend_mode}"
                    f":all_opacity={intensity}"
                )
                cmd = [
                    ffmpeg, "-y", "-i", resolved_path,
                    "-filter_complex", fc,
                    "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                    "-pix_fmt", "yuv420p", "-c:a", "copy",
                    output_path,
                ]

        # ── Execute ──────────────────────────────────────────────────
        log.info("[ShaderOverlay] Running: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                log.error(
                    "[ShaderOverlay] FFmpeg failed (rc=%d): %s",
                    result.returncode, result.stderr[-500:] if result.stderr else "",
                )
                frames = self._decode_video(resolved_path)
                return (frames, resolved_path)
        except subprocess.TimeoutExpired:
            log.error("[ShaderOverlay] FFmpeg timed out after 300s")
            frames = self._decode_video(resolved_path)
            return (frames, resolved_path)

        if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
            log.error("[ShaderOverlay] Output file empty or missing")
            frames = self._decode_video(resolved_path)
            return (frames, resolved_path)

        log.info(
            "✅ [ShaderOverlay] Applied '%s' shader (intensity=%.0f%%): %s",
            display_name, intensity * 100, output_path,
        )

        # ── SAM3 masking: composite shader onto masked region only ────
        has_mask_target = bool(mask_target and mask_target.strip())
        if has_mask_target:
            output_path = self._apply_masked(
                resolved_path, output_path, mask_target.strip(),
                invert_mask, temp_dir,
            )

        frames = self._decode_video(output_path)
        return (frames, output_path)

    # ── Helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _images_to_temp_video(
        images: torch.Tensor, fps: float = 24.0,
    ) -> str | None:
        """Convert IMAGE tensor to a temp video via FFmpeg pipe."""
        try:
            ffmpeg = get_ffmpeg_bin()
            if not ffmpeg:
                return None

            temp_dir = tempfile.mkdtemp(prefix="ffmpega_shader_in_")
            temp_path = os.path.join(temp_dir, "input.mp4")

            try:
                from ..core.images_to_video import images_to_video
            except ImportError:
                from core.images_to_video import images_to_video  # type: ignore

            images_to_video(images, temp_path, fps=int(fps))
            return temp_path
        except Exception as e:
            log.warning("[ShaderOverlay] Failed to convert images: %s", e)
            return None

    @staticmethod
    def _decode_video(video_path: str) -> torch.Tensor:
        """Decode video to IMAGE tensor frames."""
        try:
            try:
                from ..loadlast.processing.video_decode import VideoDecoder
            except ImportError:
                from loadlast.processing.video_decode import VideoDecoder  # type: ignore
            decoder = VideoDecoder()
            frames, _meta = decoder.decode_file(video_path, max_frames=256)
            if frames is not None and frames.shape[0] > 0:
                return frames
        except Exception as e:
            log.debug("[ShaderOverlay] VideoDecoder fallback: %s", e)

        return torch.zeros(1, 512, 512, 3)

    @staticmethod
    def _apply_masked(
        original_path: str,
        shaded_path: str,
        mask_target: str,
        invert: bool,
        temp_dir: str,
    ) -> str:
        """Composite shaded video onto original using SAM3 mask.

        1. Run SAM3 to generate a per-object mask video
        2. Use FFmpeg to composite: where mask is white → use shaded,
           where mask is black → use original (or inverted)

        Returns the composited output path, or shaded_path on failure.
        """
        # Import SAM3
        sam3_mask_video = None
        try:
            try:
                from ..core.sam3_masker import mask_video_subprocess as _sam3
            except ImportError:
                from core.sam3_masker import mask_video_subprocess as _sam3
            sam3_mask_video = _sam3
        except ImportError:
            log.warning(
                "⚠️  [ShaderOverlay] SAM3 not available for masking — "
                "applying shader to entire frame instead. "
                "Install SAM3: pip install git+https://github.com/facebookresearch/sam3.git"
            )
            return shaded_path

        # Generate mask
        try:
            mask_path = sam3_mask_video(
                video_path=original_path,
                prompt=mask_target,
            )
        except Exception as e:
            log.error(
                "⚠️  [ShaderOverlay] SAM3 mask generation failed: %s — "
                "applying shader to entire frame",
                e,
            )
            return shaded_path

        if mask_path is None or not os.path.isfile(mask_path):
            log.warning(
                "⚠️  [ShaderOverlay] SAM3 produced no mask — "
                "applying shader to entire frame"
            )
            return shaded_path

        log.info(
            "[ShaderOverlay] SAM3 mask generated for '%s': %s",
            mask_target, mask_path,
        )

        # Composite: original + shaded + mask → output
        # mask white = target object, mask black = background
        # Default: shader on target. Inverted: shader on background.
        ffmpeg = get_ffmpeg_bin()
        masked_output = os.path.join(temp_dir, "masked_output.mp4")

        if invert:
            # Shader on background: where mask is white (target) → original
            fc = (
                f"[1:v]format=gray[mask];"
                f"[0:v][2:v][mask]maskedmerge[_vout]"
            )
        else:
            # Shader on target: where mask is white (target) → shaded
            fc = (
                f"[1:v]format=gray[mask];"
                f"[2:v][0:v][mask]maskedmerge[_vout]"
            )

        cmd = [
            ffmpeg, "-y",
            "-i", shaded_path,     # [0] shaded video
            "-i", mask_path,       # [1] mask
            "-i", original_path,   # [2] original
            "-filter_complex", fc,
            "-map", "[_vout]",
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-map", "0:a?",
            masked_output,
        ]

        log.info("[ShaderOverlay] Masked composite: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                log.error(
                    "[ShaderOverlay] Masked composite failed (rc=%d): %s",
                    result.returncode,
                    result.stderr[-500:] if result.stderr else "",
                )
                return shaded_path
        except subprocess.TimeoutExpired:
            log.error("[ShaderOverlay] Masked composite timed out")
            return shaded_path

        if os.path.isfile(masked_output) and os.path.getsize(masked_output) > 0:
            log.info(
                "✅ [ShaderOverlay] Masked shader applied to '%s': %s",
                mask_target, masked_output,
            )
            return masked_output

        return shaded_path
