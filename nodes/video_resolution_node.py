"""FFMPEGA Video Resolution node for ComfyUI.

Model-aware width/height/length picker for video diffusion models.

Why this exists: core ``ResolutionSelector`` computes megapixels correctly but
snaps to a default ``multiple`` of 8, which is wrong for every video model here
(Wan 2.2 A14B needs 16, MiniMax H3 needs 32).  Off-grid dimensions get silently
floor-divided when the latent is built (``height // 8``, ``width // 16``), which
crops and shifts composition.  It also happily hands you 0.1 MP -> 320x320,
which is ~7x below Wan's trained 832x480 and produces garbage.

This node snaps to each model's real grid, snaps frame counts to the model's
temporal rule (Wan ``4n+1``, H3 ``17k+5``), and refuses sub-native resolutions
at queue time instead of wasting a model load.

Constraints are read from ComfyUI core:
  - Wan 2.2 A14B: comfy_extras/nodes_wan.py (step 16, latent [b,16,(L-1)//4+1,H/8,W/8])
  - Wan 2.2 TI2V-5B: comfy_extras/nodes_wan.py (step 32, latent [b,48,...,H/16,W/16])
  - MiniMax H3: comfy_extras/nodes_minimax_h3.py (step 32, 17k+5, 768*1344 area cap)
"""

import logging
import math

logger = logging.getLogger("FFMPEGA")

# ── Reuse core's MiniMax H3 helpers when available ────────────────────────
# These live in ComfyUI core and encode the model's official canvas/frame
# rules.  Guarded so the node still loads if core moves them.
try:
    from comfy_extras.nodes_minimax_h3 import (
        BASE_SHORT_EDGE as _H3_SHORT_EDGE,
    )
    from comfy_extras.nodes_minimax_h3 import (
        CANVAS_MULTIPLE as _H3_MULTIPLE,
    )
    from comfy_extras.nodes_minimax_h3 import (
        MAX_PIXELS as _H3_MAX_PIXELS,
    )
    from comfy_extras.nodes_minimax_h3 import (
        adapt_canvas as _h3_adapt_canvas,
    )
    from comfy_extras.nodes_minimax_h3 import (
        align_frame_count as _h3_align_frames,
    )

    _H3_CORE = True
except ImportError:  # pragma: no cover - exercised only outside ComfyUI
    logger.debug(
        "[FFMPEGA] comfy_extras.nodes_minimax_h3 unavailable; using local H3 fallbacks",
        exc_info=True,
    )
    _H3_CORE = False
    _H3_MULTIPLE = 32
    _H3_SHORT_EDGE = 768
    _H3_MAX_PIXELS = 768 * 1344

    def _h3_align_frames(n: int) -> int:
        """Snap up to H3's 17k+5 frame grid (mirrors core align_frame_count)."""
        while n % 17 != 5:
            n += 1
        return n

    def _h3_adapt_canvas(width: int, height: int) -> tuple[int, int]:
        """768-short-edge canvas with a 768*1344 area cap, per-axis round to 32."""
        ratio = width / height
        if ratio >= 1.0:
            nom_w, nom_h = _H3_SHORT_EDGE * ratio, float(_H3_SHORT_EDGE)
        else:
            nom_w, nom_h = float(_H3_SHORT_EDGE), _H3_SHORT_EDGE / ratio
        if nom_w * nom_h > _H3_MAX_PIXELS:
            s = math.sqrt(_H3_MAX_PIXELS / (nom_w * nom_h))
            nom_w, nom_h = nom_w * s, nom_h * s
        return (
            max(_H3_MULTIPLE, round(nom_w / _H3_MULTIPLE) * _H3_MULTIPLE),
            max(_H3_MULTIPLE, round(nom_h / _H3_MULTIPLE) * _H3_MULTIPLE),
        )


# ── Model specifications ──────────────────────────────────────────────────
# One entry per model.  Everything the node does reads from here, so adding a
# model later is a single dict entry.
#
#   multiple        pixel grid both axes must land on
#   vae_spatial     VAE spatial downscale, for the token estimate
#   temporal_rule   ("mod", divisor, remainder) for the frame count
#   default_frames  the model's own default
#   buckets         known-good landscape dimensions per tier
#   floor_pixels    below this total area, output degrades badly
MODEL_SPECS: dict[str, dict] = {
    "wan22_a14b": {
        "label": "Wan 2.2 A14B (T2V / I2V)",
        "multiple": 16,
        "vae_spatial": 8,
        "temporal_rule": (4, 1),
        "default_frames": 81,
        # 720 is divisible by 16, so A14B can use a true 1280x720 — unlike the
        # 32-grid models below, which must use 704.
        "buckets": {
            "480p": (832, 480),
            "576p": (1024, 576),
            "720p": (1280, 720),
            "1080p": (1920, 1088),
        },
        "native_bucket": "480p",
        "floor_pixels": 832 * 480,
        "frame_note": "4n+1 (81 = ~5s at 16fps)",
        "trained_frames": (17, 121),
    },
    "wan22_ti2v_5b": {
        "label": "Wan 2.2 TI2V-5B",
        "multiple": 32,
        "vae_spatial": 16,
        "temporal_rule": (4, 1),
        "default_frames": 49,
        "buckets": {
            "480p": (832, 480),
            "576p": (1024, 576),
            "720p": (1280, 704),
            "1080p": (1920, 1088),
        },
        "native_bucket": "720p",
        "floor_pixels": 832 * 480,
        "frame_note": "4n+1 (49 = ~2s at 24fps)",
        "trained_frames": (17, 121),
    },
    "minimax_h3": {
        "label": "MiniMax H3 (AV)",
        "multiple": 32,
        "vae_spatial": 16,
        "temporal_rule": (17, 5),
        "default_frames": 124,
        # H3 has no resolution tiers: core's adapt_canvas() pins the short edge
        # to 768 and caps area at 768*1344, whatever you ask for.  The bucket
        # widget is ignored for this model and dimensions come from the aspect
        # ratio alone — which also means H3 cannot be driven sub-native.
        "canvas_locked": True,
        "buckets": {
            "480p": (1344, 768),
            "576p": (1344, 768),
            "720p": (1344, 768),
            "1080p": (1344, 768),
        },
        "native_bucket": "1080p",
        "floor_pixels": 768 * 768,
        "frame_note": "17k+5 (124 = ~5s at 24fps, trained 124-362)",
        "trained_frames": (124, 362),
    },
}

MODEL_TYPES = list(MODEL_SPECS.keys())
BUCKETS = ["480p", "576p", "720p", "1080p"]
SIZING_MODES = ["bucket", "megapixels"]

ASPECT_RATIOS: dict[str, tuple[int, int]] = {
    "16:9 (Widescreen)": (16, 9),
    "9:16 (Portrait)": (9, 16),
    "1:1 (Square)": (1, 1),
    "4:3 (Standard)": (4, 3),
    "3:4 (Portrait Standard)": (3, 4),
    "21:9 (Ultrawide)": (21, 9),
}


def snap_frames(frames: int, model_type: str) -> int:
    """Snap a frame count up to the model's temporal grid."""
    spec = MODEL_SPECS[model_type]
    divisor, remainder = spec["temporal_rule"]
    if divisor == 17 and remainder == 5:
        # Defer to core's implementation so we track it if it changes.
        return _h3_align_frames(max(5, frames))
    n = max(remainder, frames)
    while n % divisor != remainder % divisor:
        n += 1
    return n


def latent_frames(frames: int, model_type: str) -> int:
    """Temporal extent of the latent, for the token estimate."""
    divisor, _ = MODEL_SPECS[model_type]["temporal_rule"]
    if divisor == 17:
        return 2 if frames <= 5 else ((frames - 5) // 17) * 5 + 2
    return ((frames - 1) // 4) + 1


def latent_tokens(width: int, height: int, frames: int, model_type: str) -> int:
    """Approximate latent token count — the thing VRAM actually scales with."""
    spec = MODEL_SPECS[model_type]
    s = spec["vae_spatial"]
    return (width // s) * (height // s) * latent_frames(frames, model_type)


RATIO_TOLERANCE = 0.05


def resolve_dimensions(
    model_type: str,
    sizing: str,
    bucket: str,
    aspect_ratio: str,
    megapixels: float,
) -> tuple[int, int]:
    """Compute grid-aligned width/height for the selected model."""
    spec = MODEL_SPECS[model_type]
    mult = spec["multiple"]
    w_ratio, h_ratio = ASPECT_RATIOS[aspect_ratio]
    want = w_ratio / h_ratio

    if spec.get("canvas_locked"):
        # The model dictates its own canvas from the aspect ratio; bucket and
        # megapixels are both ignored.  Feed the ratio in at arbitrary scale.
        return _h3_adapt_canvas(round(want * 1000), 1000)

    if sizing == "bucket":
        base_w, base_h = spec["buckets"][bucket]
        base_ratio = base_w / base_h
        # Buckets are hand-picked known-good dimensions, so return them
        # untouched when the requested ratio matches — re-deriving them from
        # area would drift 832x480 to 848x480.
        if abs(want - base_ratio) <= RATIO_TOLERANCE * base_ratio:
            return base_w, base_h
        # Portrait mirror of the same bucket is equally known-good.
        if abs(want - 1 / base_ratio) <= RATIO_TOLERANCE / base_ratio:
            return base_h, base_w
        # Otherwise re-project at equal area so cost stays comparable.
        target_pixels = base_w * base_h
    else:
        target_pixels = megapixels * 1024 * 1024

    scale = math.sqrt(target_pixels / (w_ratio * h_ratio))
    width = max(mult, round(w_ratio * scale / mult) * mult)
    height = max(mult, round(h_ratio * scale / mult) * mult)
    return width, height


class VideoResolutionNode:
    """Video Resolution (FFMPEGA) — model-aware dimensions and frame count.

    Picks width/height on the target model's real pixel grid and snaps the
    frame count to its temporal rule, then refuses resolutions below the
    model's trained floor (where output turns to noise).
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model_type": (MODEL_TYPES, {
                    "default": "wan22_a14b",
                    "tooltip": (
                        "Target video model. Sets the pixel grid (Wan 2.2 A14B = 16, "
                        "TI2V-5B and MiniMax H3 = 32) and the frame rule "
                        "(Wan = 4n+1, H3 = 17k+5)."
                    ),
                }),
                "sizing": (SIZING_MODES, {
                    "default": "bucket",
                    "tooltip": (
                        "'bucket' picks a known-good resolution tier for the model — "
                        "recommended. 'megapixels' lets you set an arbitrary area, "
                        "still snapped to the model's grid."
                    ),
                }),
                "bucket": (BUCKETS, {
                    "default": "480p",
                    "tooltip": (
                        "Resolution tier, used when sizing='bucket'. For Wan 2.2, "
                        "480p (832x480) is the native trained size — 720p costs ~2.2x "
                        "the VRAM. Note 720p is 1280x704, not 1280x720: 720 is not a "
                        "multiple of 16/32 and gets silently cropped."
                    ),
                }),
                "aspect_ratio": (list(ASPECT_RATIOS.keys()), {
                    "default": "16:9 (Widescreen)",
                    "tooltip": (
                        "Output aspect ratio. Area is held constant across ratios, so "
                        "9:16 at a given bucket costs the same VRAM as 16:9."
                    ),
                }),
                "frames": ("INT", {
                    "default": 81,
                    "min": 1,
                    "max": 3600,
                    "step": 1,
                    "tooltip": (
                        "Requested frame count, snapped up to the model's grid "
                        "(Wan 4n+1, H3 17k+5). This is the better lever for VRAM: "
                        "cutting Wan 81->49 saves ~38% of latent tokens at no cost to "
                        "per-frame quality, unlike dropping below native resolution. "
                        "That only holds inside the model's trained range though — "
                        "Wan ~17-121, H3 124-362. Below it, motion breaks down and "
                        "you should lower the bucket instead. Note 81 is a Wan "
                        "default; H3 wants 124."
                    ),
                }),
            },
            "optional": {
                "megapixels": ("FLOAT", {
                    "default": 0.4,
                    "min": 0.01,
                    "max": 16.0,
                    "step": 0.01,
                    "tooltip": (
                        "Target area in megapixels, used only when sizing='megapixels'. "
                        "0.4 MP is roughly Wan's native 832x480. Values far below the "
                        "model's floor are rejected — 0.1 MP is 320x320, ~7x below "
                        "trained size, and produces garbled output."
                    ),
                }),
                "allow_below_native": ("BOOLEAN", {
                    "default": False,
                    "label_on": "Allow",
                    "label_off": "Block",
                    "tooltip": (
                        "Off by default: resolutions below the model's trained floor "
                        "are rejected before the job queues, so you don't wait on a "
                        "run that was always going to be noise. Turn on only for "
                        "deliberate experiments."
                    ),
                }),
            },
        }

    RETURN_TYPES = ("INT", "INT", "INT", "STRING")
    RETURN_NAMES = ("width", "height", "length", "info")
    OUTPUT_TOOLTIPS = (
        "Width in pixels, aligned to the model's grid.",
        "Height in pixels, aligned to the model's grid.",
        "Frame count, snapped to the model's temporal rule (Wan 4n+1, H3 17k+5).",
        "Human-readable summary: final dimensions, snapping applied, actual "
        "megapixels, and the latent-token cost relative to native.",
    )
    FUNCTION = "resolve"
    CATEGORY = "FFMPEGA"
    DESCRIPTION = (
        "Model-aware resolution and frame-count picker for Wan 2.2 and MiniMax H3. "
        "Snaps to the correct pixel grid, snaps frames to the model's temporal rule, "
        "and blocks sub-native resolutions that produce garbled output."
    )

    @classmethod
    def _check_floor(
        cls,
        model_type: str,
        sizing: str,
        bucket: str,
        aspect_ratio: str,
        megapixels: float,
        allow_below_native: bool,
    ) -> str | None:
        """Return an error message when below the model's floor, else None."""
        if allow_below_native:
            return None
        spec = MODEL_SPECS[model_type]
        width, height = resolve_dimensions(
            model_type, sizing, bucket, aspect_ratio, megapixels
        )
        if width * height >= spec["floor_pixels"]:
            return None

        native = spec["buckets"][spec["native_bucket"]]
        return (
            f"{width}x{height} ({width * height / 1048576:.2f} MP) is below "
            f"{spec['label']}'s floor of {native[0]}x{native[1]} "
            f"({spec['floor_pixels'] / 1048576:.2f} MP). Sub-native resolutions "
            f"produce garbled output — the model was never trained there. "
            f"Use bucket='{spec['native_bucket']}', or cut the frame count to save "
            f"VRAM instead (that costs no quality). Set allow_below_native=True "
            f"to override."
        )

    @classmethod
    def VALIDATE_INPUTS(
        cls,
        model_type: str = "wan22_a14b",
        sizing: str = "bucket",
        bucket: str = "480p",
        aspect_ratio: str = "16:9 (Widescreen)",
        frames: int = 81,
        megapixels: float = 0.4,
        allow_below_native: bool = False,
        **kwargs,
    ) -> bool | str:
        """Reject sub-native resolutions at queue time, not mid-run."""
        if model_type not in MODEL_SPECS:
            return f"Unknown model_type: {model_type}"
        if aspect_ratio not in ASPECT_RATIOS:
            return f"Unknown aspect_ratio: {aspect_ratio}"
        if sizing not in SIZING_MODES:
            return f"Unknown sizing mode: {sizing}"
        if sizing == "bucket" and bucket not in MODEL_SPECS[model_type]["buckets"]:
            return f"Bucket {bucket} is not defined for {model_type}"

        error = cls._check_floor(
            model_type, sizing, bucket, aspect_ratio, megapixels, allow_below_native
        )
        return error if error else True

    def resolve(
        self,
        model_type: str = "wan22_a14b",
        sizing: str = "bucket",
        bucket: str = "480p",
        aspect_ratio: str = "16:9 (Widescreen)",
        frames: int = 81,
        megapixels: float = 0.4,
        allow_below_native: bool = False,
    ) -> tuple[int, int, int, str]:
        """Resolve dimensions and frame count, and describe the result."""
        spec = MODEL_SPECS[model_type]

        # Belt and braces: VALIDATE_INPUTS already ran, but a workflow built by
        # hand or by an agent can bypass it.
        error = self._check_floor(
            model_type, sizing, bucket, aspect_ratio, megapixels, allow_below_native
        )
        if error:
            raise ValueError(error)

        width, height = resolve_dimensions(
            model_type, sizing, bucket, aspect_ratio, megapixels
        )
        snapped_frames = snap_frames(frames, model_type)

        # Cost relative to this model's native bucket at its default length.
        native_w, native_h = spec["buckets"][spec["native_bucket"]]
        native_tokens = latent_tokens(
            native_w, native_h, spec["default_frames"], model_type
        )
        tokens = latent_tokens(width, height, snapped_frames, model_type)
        ratio = tokens / native_tokens if native_tokens else 1.0

        notes = []
        if snapped_frames != frames:
            notes.append(f"frames {frames} -> {snapped_frames} ({spec['frame_note']})")
        lo, hi = spec["trained_frames"]
        if snapped_frames < lo:
            notes.append(
                f"{snapped_frames} frames is below this model's trained range "
                f"({lo}-{hi}) — motion may break down. Lower the resolution "
                f"bucket before going shorter than {lo}."
            )
        elif snapped_frames > hi:
            notes.append(
                f"{snapped_frames} frames exceeds the trained range ({lo}-{hi}) — "
                f"untested, expect drift late in the clip."
            )
        if allow_below_native and width * height < spec["floor_pixels"]:
            notes.append("BELOW NATIVE — expect degraded or garbled output")
        if spec.get("canvas_locked"):
            notes.append(
                "this model has a fixed 768-short-edge canvas; "
                "bucket and megapixels are ignored"
            )

        info = (
            f"{spec['label']}\n"
            f"{width}x{height} @ {snapped_frames} frames "
            f"({width * height / 1048576:.2f} MP, grid /{spec['multiple']})\n"
            f"latent tokens: {tokens:,} ({ratio:.0%} of native "
            f"{native_w}x{native_h}@{spec['default_frames']})"
        )
        if notes:
            info += "\n" + "\n".join(f"note: {n}" for n in notes)

        logger.debug("[FFMPEGA] VideoResolution -> %sx%s @ %s", width, height, snapped_frames)
        return (width, height, snapped_frames, info)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        """Re-run when any setting changes."""
        import hashlib

        return hashlib.md5(repr(sorted(kwargs.items())).encode()).hexdigest()
