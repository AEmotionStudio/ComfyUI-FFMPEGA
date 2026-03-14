"""Shader support utilities — libplacebo capability detection and fallback mapping.

Detects whether the system FFmpeg build has libplacebo + Vulkan + glslang
compiled in, discovers available .glsl shader files (built-in and user-added),
and provides FFmpeg-only fallback filters for every built-in preset.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from functools import lru_cache

try:
    from ..core.sanitize import validate_path
except ImportError:
    from core.sanitize import validate_path

log = logging.getLogger("ffmpega")

# Extensions accepted for custom shader files
ALLOWED_SHADER_EXTENSIONS = {".glsl", ".frag", ".hook"}

# ── Fallback filters ─────────────────────────────────────────────────
# When libplacebo is unavailable, each preset maps to an FFmpeg-only
# approximation.  Not pixel-accurate, but visually recognizable.

_FALLBACK_MAP: dict[str, str] = {
    "crt": "curves=preset=vintage,noise=alls=10:allf=t",
    "vhs": (
        "noise=alls=20:allf=t,"
        "colorbalance=rs=0.1:bs=-0.1,"
        "eq=saturation=0.75"
    ),
    "holographic": "hue=H=t*30:s=1.5,eq=saturation=1.5",
    "glitch": "rgbashift=rh=3:bh=-3:rv=1:bv=-1",
    "voronoi": "edgedetect=mode=colormix:high=0.3",
    "water_ripple": "lenscorrection=k1=0.15:k2=0.05",
    "night_vision": (
        "colorchannelmixer=.1:.4:.1:0:.1:.4:.1:0:.1:.4:.1,"
        "noise=alls=15:allf=t,"
        "eq=brightness=0.2"
    ),
    "force_field": (
        "edgedetect=mode=colormix:high=0.2,"
        "eq=brightness=0.15:saturation=2"
    ),
    # ── Creative GPU-only presets ─────────────────────────────────
    "plasma_burn": "hue=H=t*40:s=1.5,eq=brightness=0.1:saturation=1.5",
    "shockwave": "lenscorrection=k1=0.2:k2=0.1,eq=brightness=0.05",
    "datamosh": "rgbashift=rh=5:bh=-5:rv=2:bv=-2,noise=alls=15:allf=t",
    "crystal": (
        "lenscorrection=k1=0.1:k2=0.05,"
        "eq=saturation=1.3:brightness=0.1"
    ),
    "aurora": (
        "colorbalance=gs=0.3:bs=0.2,"
        "eq=brightness=0.05:saturation=1.3"
    ),
    "hologram_scan": (
        "colorchannelmixer=.1:.1:.8:0:.1:.1:.8:0:.2:.3:.9,"
        "noise=alls=10:allf=t"
    ),
    "portal": "lenscorrection=k1=-0.3:k2=0.1,eq=saturation=1.5",
    "circuit_board": (
        "edgedetect=mode=colormix:high=0.15,"
        "colorchannelmixer=.1:.4:.1:0:.1:.4:.1:0:.1:.4:.1"
    ),
    "dissolve": "noise=alls=25:allf=t,eq=brightness=-0.1",
    "hex_matrix": (
        "edgedetect=mode=colormix:high=0.2,"
        "colorchannelmixer=0:.2:.2:0:0:.6:.3:0:0:.3:.5"
    ),
    "liquid_metal": (
        "eq=saturation=0:contrast=1.5,"
        "curves=preset=lighter"
    ),
    "xray": (
        "negate,eq=saturation=0:brightness=0.1,"
        "colorchannelmixer=.3:.3:.4:0:.3:.3:.5:0:.4:.4:.6"
    ),
    # ── Creative effects (batch 2) ──────────────────────────────
    "cartoon": (
        "edgedetect=mode=colormix:high=0.15,"
        "eq=saturation=1.5:contrast=1.3"
    ),
    "jelly": "lenscorrection=k1=0.15:k2=0.05",
    "emboss_3d": "convolution='-2 -1 0 -1 1 1 0 1 2'",
    "infrared_predator": (
        "eq=saturation=0,pseudocolor=p=inferno,"
        "edgedetect=mode=colormix:high=0.1"
    ),
    "digital_decay": (
        "rgbashift=rh=5:bh=-5:rv=2:bv=-2,"
        "noise=alls=20:allf=t"
    ),
    "underwater": (
        "colorchannelmixer=.5:0:0:0:0:.8:.1:0:0:.1:.9:0,"
        "eq=brightness=-0.1"
    ),
    "electric_arc": (
        "edgedetect=mode=colormix:high=0.1,"
        "eq=brightness=0.15:saturation=2.5"
    ),
    "ink_wash": (
        "edgedetect=low=0.1:high=0.3:mode=colormix,"
        "negate,eq=saturation=0:brightness=0.1"
    ),
    # ── Outline shaders (pair with SAM3 masking) ────────────────
    "neon_outline": (
        "edgedetect=mode=colormix:high=0.1,"
        "eq=brightness=0.2:saturation=3"
    ),
    "fire_outline": (
        "edgedetect=mode=colormix:high=0.15,"
        "colorbalance=rs=0.5:gs=0.2:bs=-0.3,"
        "eq=brightness=0.15"
    ),
    "frost_outline": (
        "edgedetect=mode=colormix:high=0.1,"
        "colorbalance=rs=-0.2:gs=-0.1:bs=0.3,"
        "eq=brightness=0.1"
    ),
    "shadow_outline": (
        "edgedetect=mode=colormix:high=0.15,"
        "eq=brightness=-0.1:contrast=1.3"
    ),
    # ── Brought-back presets (GPU-enhanced versions) ────────────
    "oil_paint": "boxblur=3:1,eq=saturation=1.3",
    "rain": "noise=alls=8:allf=t,eq=brightness=-0.05",
    "matrix": (
        "colorchannelmixer=.1:.5:.1:0:.1:.5:.1:0:.1:.5:.1,"
        "noise=alls=10:allf=t"
    ),
    "sketch": (
        "edgedetect=low=0.1:high=0.3:mode=colormix,"
        "negate,eq=brightness=0.1"
    ),
    # ── Boundary-pushing presets (batch 3) ──────────────────────
    "pixel_sort": "rgbashift=rh=8:bh=-8,eq=contrast=1.3",
    "topographic": (
        "edgedetect=mode=colormix:high=0.1,"
        "eq=saturation=0.5:contrast=1.2"
    ),
    "stained_glass": "scale=iw/12:ih/12:flags=neighbor,scale=iw*12:ih*12:flags=neighbor,eq=saturation=1.5",
    "smoke": "gblur=sigma=5,eq=brightness=-0.1:contrast=0.8",
    "geometric_shatter": "lenscorrection=k1=0.2:k2=0.1,eq=brightness=0.05",
    "noir": (
        "eq=saturation=0:contrast=1.5,"
        "curves=preset=vintage,vignette=PI/4"
    ),
    "cyberpunk": (
        "colorbalance=rs=0.3:bs=0.3:gm=-0.2,"
        "eq=saturation=2:contrast=1.3"
    ),
    "mosaic": "scale=iw/8:ih/8:flags=neighbor,scale=iw*8:ih*8:flags=neighbor,eq=saturation=1.3",
    "lava_lamp": (
        "colorbalance=rs=0.4:gs=-0.2:bs=-0.2,"
        "gblur=sigma=5,eq=brightness=0.1"
    ),
    "vaporwave": (
        "colorbalance=rs=0.3:bs=0.4:gm=-0.3,"
        "eq=saturation=1.8:contrast=1.1"
    ),
    "supernova": (
        "colorbalance=rs=0.2:bs=0.4:gs=-0.1,"
        "eq=brightness=0.15:contrast=1.3:saturation=1.5,"
        "gblur=sigma=3"
    ),
    "fractal_loop": (
        "colorbalance=rs=0.2:gs=0.1:bs=0.3,"
        "eq=saturation=1.8:contrast=1.2:brightness=0.1"
    ),
    "kaleidoscope": (
        "colorbalance=rs=0.3:gs=0.1:bs=0.3,"
        "eq=saturation=2.0:contrast=1.4:brightness=0.15"
    ),
    "ebruli": (
        "gblur=sigma=2,"
        "colorbalance=rs=0.1:gs=0.05:bs=-0.05,"
        "eq=saturation=1.4:contrast=1.1"
    ),
    "spirals": (
        "colorbalance=rs=0.2:gs=0.2:bs=0.3,"
        "eq=saturation=2.0:contrast=1.3:brightness=0.1"
    ),
    "space_tunnel": (
        "colorbalance=rs=0.1:gs=0.1:bs=0.3,"
        "eq=saturation=1.5:contrast=1.4:brightness=-0.1"
    ),
    "singularity": (
        "colorbalance=rs=0.1:gs=0.2:bs=0.4,"
        "eq=saturation=1.6:contrast=1.5:brightness=-0.05"
    ),
    "blueprint": (
        "colorbalance=rs=-0.1:gs=0.0:bs=0.3,"
        "eq=saturation=0.8:contrast=1.6:brightness=-0.1"
    ),
    "singularity_box": (
        "colorbalance=rs=0.2:gs=0.1:bs=0.4,"
        "eq=saturation=1.8:contrast=1.5:brightness=-0.05"
    ),
}


def _get_shaders_dir() -> Path:
    """Return the built-in shaders/ directory path."""
    return Path(__file__).resolve().parent.parent / "shaders"


@lru_cache(maxsize=1)
def has_libplacebo() -> bool:
    """Check if FFmpeg has libplacebo filter support.

    Runs ``ffmpeg -filters`` once and caches the result for the
    lifetime of the process.

    Returns:
        True if libplacebo is available.
    """
    try:
        from .bin_paths import get_ffmpeg_binary
        ffmpeg = get_ffmpeg_binary()
    except (ImportError, Exception):
        ffmpeg = "ffmpeg"

    try:
        result = subprocess.run(
            [ffmpeg, "-filters"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return "libplacebo" in result.stdout
    except Exception as exc:
        log.debug("has_libplacebo: probe failed: %s", exc)
        return False


def list_available_shaders() -> list[str]:
    """Discover available .glsl shader presets.

    Returns a sorted list of shader names (without extension) found
    in the ``shaders/`` directory.  Includes both built-in and
    user-added files.
    """
    shaders_dir = _get_shaders_dir()
    if not shaders_dir.is_dir():
        return []

    names: list[str] = []
    for ext in ALLOWED_SHADER_EXTENSIONS:
        for path in shaders_dir.glob(f"*{ext}"):
            names.append(path.stem)

    return sorted(set(names))


# ── Preset categories (ordered) ────────────────────────────────────
PRESET_CATEGORIES: dict[str, list[str]] = {
    "🎬 Classic": [
        "crt", "vhs", "holographic", "glitch",
        "voronoi", "water_ripple", "night_vision", "force_field",
    ],
    "🔥 Creative": [
        "plasma_burn", "shockwave", "datamosh", "crystal",
        "aurora", "hologram_scan", "portal", "circuit_board",
        "dissolve", "hex_matrix", "liquid_metal", "xray",
    ],
    "🎨 Artistic": [
        "cartoon", "jelly", "emboss_3d", "ink_wash",
        "oil_paint", "sketch", "noir", "mosaic",
        "stained_glass", "topographic", "ebruli", "blueprint",
    ],
    "⚡ Sci-Fi & Cyber": [
        "infrared_predator", "digital_decay", "electric_arc",
        "cyberpunk", "vaporwave", "matrix", "space_tunnel", "singularity",
    ],
    "🌊 Environmental": [
        "underwater", "rain", "smoke", "lava_lamp",
    ],
    "✨ Outline (SAM3 Masking)": [
        "neon_outline", "fire_outline", "frost_outline", "shadow_outline",
    ],
    "💥 Experimental": [
        "pixel_sort", "geometric_shatter", "supernova", "fractal_loop",
        "kaleidoscope", "spirals", "singularity_box",
    ],
}


def list_categorized_presets() -> list[str]:
    """Return presets ordered by category with header labels.

    Category headers use ``── Category ──`` format. They appear in
    the ComfyUI dropdown as visual separators. The node's ``process``
    method ignores any value starting with ``──`` (treats it as
    *none*).
    """
    available = set(list_available_shaders())
    result: list[str] = ["🎲 random"]

    for header, presets in PRESET_CATEGORIES.items():
        has_any = any(p in available for p in presets)
        if not has_any:
            continue
        result.append(f"── {header} ──")
        for p in presets:
            if p in available:
                result.append(p)
                available.discard(p)

    # Any uncategorized shaders (user-added custom .glsl files)
    if available:
        result.append("── 📁 Custom ──")
        result.extend(sorted(available))

    return result


def resolve_shader_path(name_or_path: str) -> Path | None:
    """Resolve a shader name or path to a full file path.

    Accepts either:
    - A short name (e.g. "crt") → searches shaders/ directory
    - A full path (e.g. "/home/user/my_shader.glsl") → validated directly

    Returns:
        Full path to the .glsl file, or None if not found.
    """
    # If it looks like a path (contains separator), validate directly
    if "/" in name_or_path or "\\" in name_or_path:
        p = Path(name_or_path)
        if p.is_file() and p.suffix.lower() in ALLOWED_SHADER_EXTENSIONS:
            return p
        return None

    # Short name: search shaders/ directory
    shaders_dir = _get_shaders_dir()
    for ext in ALLOWED_SHADER_EXTENSIONS:
        candidate = shaders_dir / f"{name_or_path}{ext}"
        if candidate.is_file():
            return candidate

    # Fuzzy match: case-insensitive substring
    if shaders_dir.is_dir():
        lower_name = name_or_path.lower()
        for f in shaders_dir.iterdir():
            if (f.suffix.lower() in ALLOWED_SHADER_EXTENSIONS
                    and lower_name in f.stem.lower()):
                return f

    return None


def get_fallback_filter(preset: str) -> str | None:
    """Get the FFmpeg-only fallback filter for a built-in preset.

    Args:
        preset: Preset name (e.g. "crt", "vhs").

    Returns:
        FFmpeg filter string, or None if no fallback exists.
    """
    return _FALLBACK_MAP.get(preset.lower())


def escape_shader_path(path: str) -> str:
    """Escape a file path for use inside FFmpeg filter expressions."""
    for ch in ("\\", "'", ":", ";", "[", "]"):
        path = path.replace(ch, f"\\{ch}")
    return path


# ── Blend modes (FFmpeg blend filter names) ──────────────────────────

BLEND_MODES = [
    "normal", "addition", "multiply", "screen", "overlay", "softlight",
]


def pick_random_shader() -> str | None:
    """Pick a random shader preset name.

    Returns:
        A random shader name, or None if no shaders are available.
    """
    import random
    shaders = list_available_shaders()
    if not shaders:
        return None
    return random.choice(shaders)


def build_shader_filter(
    shader_path: str | list[str],
    *,
    intensity: float = 1.0,
    blend_mode: str = "normal",
    speed: float = 1.0,
    hue_shift: float = 0.0,
    phase: float = 0.0,
    resolution_scale: float = 1.0,
) -> tuple[list[str], str]:
    """Build the FFmpeg filter chain for one or more shaders.

    Args:
        shader_path: Full path(s) to .glsl file(s). A list enables chaining.
        intensity: Blend intensity 0.0–1.0 (1.0 = full effect).
        blend_mode: Blend mode when intensity < 1.0 (normal, addition,
            multiply, screen, overlay, softlight).
        speed: Animation speed multiplier (1.0 = normal).
        hue_shift: Post-shader hue rotation in degrees (0–360).
        phase: Time offset in seconds for animation start.
        resolution_scale: Scale factor for shader processing resolution.

    Returns:
        Tuple of (vf_filters, filter_complex) — one will be populated.
        For full intensity, vf_filters is used.
        For partial intensity, filter_complex blends with the original.
    """
    if intensity <= 0.0:
        return [], ""

    # Normalize to a list
    paths = shader_path if isinstance(shader_path, list) else [shader_path]
    paths = [p for p in paths if p]  # drop empties
    if not paths:
        return [], ""

    # Build the core shader filter chain
    shader_filters: list[str] = []

    # Speed: scale presentation timestamps to change frame counter
    if speed != 1.0 and speed > 0:
        shader_filters.append(f"setpts=PTS/{speed:.2f}")

    # Phase: offset timestamps for animation start
    if phase > 0:
        # Add frame offset by shifting PTS — combine with speed if both set
        fps_est = 24.0  # estimated; phase is approximate
        frame_offset = int(phase * fps_est)
        if frame_offset > 0:
            # setpts already handles speed; for phase we adjust frame count
            # via trim+setpts is too heavy; instead we'll note this is approximate
            pass  # phase is handled in the node by adjusting frame counter

    # Resolution scale: downscale before shader, upscale after
    pre_scale = ""
    post_scale = ""
    if resolution_scale != 1.0 and resolution_scale > 0:
        pre_scale = f"scale=iw*{resolution_scale:.2f}:ih*{resolution_scale:.2f}:flags=lanczos"
        post_scale = f"scale=iw/{resolution_scale:.2f}:ih/{resolution_scale:.2f}:flags=lanczos"
        shader_filters.append(pre_scale)

    # Shader(s) — chained
    for p in paths:
        escaped = escape_shader_path(p)
        shader_filters.append(f"libplacebo=custom_shader_path={escaped}")

    # Resolution scale: restore original size
    if post_scale:
        shader_filters.append(post_scale)

    # Hue shift: post-shader hue rotation
    if hue_shift > 0:
        shader_filters.append(f"hue=h={hue_shift:.1f}")

    # Validate blend mode
    if blend_mode not in BLEND_MODES:
        blend_mode = "normal"

    shader_chain = ",".join(shader_filters)

    if intensity >= 1.0:
        return shader_filters, ""
    else:
        # Blend: split → apply shader chain → blend with original
        fc = (
            f"[0:v]split[orig][fx];"
            f"[fx]{shader_chain}[shaded];"
            f"[orig][shaded]blend=all_mode={blend_mode}"
            f":all_opacity={intensity}"
        )
        return [], fc
