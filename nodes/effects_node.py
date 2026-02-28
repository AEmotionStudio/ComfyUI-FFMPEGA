"""FFMPEGA Effects Builder node for ComfyUI.

Provides a visual interface for composing FFmpeg effects without an LLM.
Outputs a pipeline JSON string that connects to the FFMPEGAgent node.

Supports three usage patterns:
- **Standalone** (llm_model=none): pipeline is executed directly
- **LLM Hint**: selected effects are injected as hints into the LLM prompt
- **Raw FFmpeg**: user types raw filter strings that pass through directly
"""

import json
import logging
from typing import Any

logger = logging.getLogger("FFMPEGA")

# Category display labels (emoji + name)
_CAT_LABELS = {
    "visual":   "🎨 Visual",
    "temporal":  "⏱️ Temporal",
    "spatial":   "📐 Spatial",
    "audio":     "🔊 Audio",
    "encoding":  "📦 Encoding",
    "outcome":   "✨ Outcome",
}

# ------------------------------------------------------------------ #
#  Presets: curated effect combos for one-click setups               #
# ------------------------------------------------------------------ #

# Each preset maps to a dict with effect slots + params.
# The JS reads _PRESETS_JSON to auto-populate widgets on selection.
_PRESETS = {
    "none": {},
    "🎬 Cinematic Look": {
        "effect_1": "letterbox",
        "effect_1_params": {"ratio": "2.39:1"},
        "effect_2": "vignette",
        "effect_2_params": {},
        "effect_3": "color_grade",
        "effect_3_params": {"style": "teal_orange"},
    },
    "📼 Vintage / Retro": {
        "effect_1": "vintage",
        "effect_1_params": {},
        "effect_2": "film_grain",
        "effect_2_params": {"intensity": "medium"},
        "effect_3": "none",
        "effect_3_params": {},
    },
    "🔍 Privacy Blur (face)": {
        "effect_1": "none",
        "effect_1_params": {},
        "sam3_target": "face",
        "sam3_effect": "blur",
    },
    "⚡ Speed Ramp (2x)": {
        "effect_1": "speed",
        "effect_1_params": {"factor": 2.0},
        "effect_2": "none",
        "effect_2_params": {},
    },
    "🖤 B&W + Vignette": {
        "effect_1": "black_and_white",
        "effect_1_params": {},
        "effect_2": "vignette",
        "effect_2_params": {},
    },
    "📱 Social (9:16 + Quality)": {
        "effect_1": "aspect",
        "effect_1_params": {"ratio": "9:16", "mode": "crop"},
        "effect_2": "quality",
        "effect_2_params": {"crf": 18, "preset": "slow"},
    },
    "🎵 Clean Audio": {
        "effect_1": "noise_reduction",
        "effect_1_params": {},
        "effect_2": "normalize",
        "effect_2_params": {},
    },
    "✨ Glow + Saturation": {
        "effect_1": "glow",
        "effect_1_params": {},
        "effect_2": "saturation",
        "effect_2_params": {"amount": 1.4},
    },
}

_PRESET_NAMES = list(_PRESETS.keys())


def _get_skill_data() -> tuple[list[str], dict[str, str], dict[str, str]]:
    """Return (dropdown_names, param_help_map, param_defaults_map).

    ``dropdown_names`` — categorized list for the dropdown, e.g.
    ``["none", "🎨 Visual/blur", ...]``.

    ``param_help_map`` — maps raw skill name to a one-line help string
    describing its parameters.

    ``param_defaults_map`` — maps raw skill name to a JSON string of
    default parameter values, e.g.  ``"blur": '{"strength": 5}'``.
    """
    try:
        from ..skills.registry import get_registry, SkillCategory
    except ImportError:
        from skills.registry import get_registry, SkillCategory

    registry = get_registry()

    ordered_cats = [
        SkillCategory.VISUAL,
        SkillCategory.TEMPORAL,
        SkillCategory.SPATIAL,
        SkillCategory.AUDIO,
        SkillCategory.ENCODING,
        SkillCategory.OUTCOME,
    ]

    seen: set[str] = set()
    names: list[str] = ["none"]
    param_help: dict[str, str] = {}
    param_defaults: dict[str, str] = {}

    for cat in ordered_cats:
        label = _CAT_LABELS.get(cat.value, cat.value)
        skills = registry.list_by_category(cat)
        cat_names = sorted(set(s.name for s in skills))

        for skill_name in cat_names:
            if skill_name in seen:
                continue
            seen.add(skill_name)
            names.append(f"{label}/{skill_name}")

            # Build param help string + defaults dict
            skill_obj = registry.get(skill_name)
            if skill_obj and skill_obj.parameters:
                help_parts = []
                defaults_dict = {}
                for p in skill_obj.parameters:
                    default_str = f", default={p.default}" if p.default is not None else ""
                    req_str = "" if p.required else ", optional"
                    help_parts.append(f"{p.name} ({p.type.value}{default_str}{req_str})")
                    if p.default is not None:
                        defaults_dict[p.name] = p.default
                param_help[skill_name] = "; ".join(help_parts)
                if defaults_dict:
                    param_defaults[skill_name] = json.dumps(defaults_dict)
            else:
                param_help[skill_name] = "no parameters"

    return names, param_help, param_defaults


# Cache at module level (recomputed per ComfyUI session)
_CACHED_SKILL_DATA: tuple[list[str], dict[str, str], dict[str, str]] | None = None


def _get_skills_cached() -> tuple[list[str], dict[str, str], dict[str, str]]:
    """Return cached (names, param_help, param_defaults)."""
    global _CACHED_SKILL_DATA
    if _CACHED_SKILL_DATA is None:
        _CACHED_SKILL_DATA = _get_skill_data()
    return _CACHED_SKILL_DATA


def _find_categorized_name(skill_name: str, skills_list: list[str]) -> str:
    """Find the full categorized name for a raw skill name.

    ``"blur"`` + ``["none", "🎨 Visual/blur", ...]`` → ``"🎨 Visual/blur"``
    """
    if skill_name == "none":
        return "none"
    suffix = f"/{skill_name}"
    for s in skills_list:
        if s.endswith(suffix):
            return s
    return "none"


class FFMPEGAEffectsNode:
    """FFMPEGA Effects Builder — compose video effects visually.

    Outputs a JSON pipeline that connects to the FFMPEGA Agent node.
    The agent uses this pipeline directly (when llm_model="none") or
    as skill hints for LLM models.
    """

    SAM3_EFFECTS = ["none", "blur", "pixelate", "remove", "grayscale", "highlight"]

    @classmethod
    def INPUT_TYPES(cls):
        skills, param_help, param_defaults = _get_skills_cached()

        # Build a compact param reference for the tooltip
        param_examples = []
        for name in ("blur", "brightness", "saturation", "speed", "trim"):
            if name in param_help:
                param_examples.append(f"  {name}: {param_help[name]}")
        param_ref = "\n".join(param_examples[:5])

        param_tooltip = (
            "JSON parameters for this effect. Examples:\n"
            f"{param_ref}\n\n"
            "Hover over the effect dropdown for full parameter details."
        )

        # Serialize preset data + param defaults for the JS UI
        _presets_json = json.dumps({
            n: {k: (json.dumps(v) if isinstance(v, dict) else v)
                for k, v in cfg.items()}
            for n, cfg in _PRESETS.items()
            if n != "none"
        })
        _defaults_json = json.dumps(param_defaults)

        return {
            "required": {
                "preset": (_PRESET_NAMES, {
                    "default": "none",
                    "tooltip": (
                        "Quick-start presets. Selecting a preset auto-fills the "
                        "effect slots and params below. You can then tweak them. "
                        "Set to 'none' to build your own combo."
                    ),
                }),
                "effect_1": (skills, {
                    "default": "none",
                    "tooltip": (
                        "First effect to apply. Categories: "
                        "🎨 Visual, ⏱️ Temporal, 📐 Spatial, 🔊 Audio, "
                        "📦 Encoding, ✨ Outcome. Set to 'none' to skip."
                    ),
                }),
            },
            "optional": {
                "effect_1_params": ("STRING", {
                    "default": "",
                    "placeholder": '{"strength": 5}',
                    "tooltip": param_tooltip,
                }),
                "effect_2": (skills, {
                    "default": "none",
                    "tooltip": "Second effect (chained after effect 1).",
                }),
                "effect_2_params": ("STRING", {
                    "default": "",
                    "placeholder": '{"amount": 1.5}',
                    "tooltip": param_tooltip,
                }),
                "effect_3": (skills, {
                    "default": "none",
                    "tooltip": "Third effect (chained after effect 2).",
                }),
                "effect_3_params": ("STRING", {
                    "default": "",
                    "placeholder": '{"factor": 2.0}',
                    "tooltip": param_tooltip,
                }),
                "raw_ffmpeg": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": (
                        "Optional: raw FFmpeg filters\n"
                        "e.g. boxblur=5,eq=brightness=0.1\n"
                        "Applied after skill effects."
                    ),
                    "tooltip": (
                        "Raw FFmpeg video filter string. Applied after any "
                        "skill-based effects. Use standard FFmpeg -vf syntax."
                    ),
                }),
                "sam3_target": ("STRING", {
                    "default": "",
                    "placeholder": "e.g. the person, license plate",
                    "tooltip": (
                        "SAM3 text target. When set, effects are applied only to "
                        "the masked region (e.g. blur just the person's face). "
                        "Leave empty to apply effects to the entire frame."
                    ),
                }),
                "sam3_effect": (cls.SAM3_EFFECTS, {
                    "default": "blur",
                    "tooltip": (
                        "What effect to apply to the SAM3-detected region. "
                        "'none' outputs the raw mask without any effect."
                    ),
                }),
                # Hidden data for JS — serialized preset/defaults info
                "_presets_json": ("STRING", {
                    "default": _presets_json,
                    "multiline": False,
                    "tooltip": "Internal: preset data for auto-fill (hidden by JS).",
                }),
                "_defaults_json": ("STRING", {
                    "default": _defaults_json,
                    "multiline": False,
                    "tooltip": "Internal: param defaults data (hidden by JS).",
                }),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("pipeline_json",)
    OUTPUT_TOOLTIPS = (
        "JSON pipeline specification. Connect to the FFMPEGA Agent node's "
        "pipeline_json input.",
    )
    FUNCTION = "build_pipeline"
    CATEGORY = "FFMPEGA"
    DESCRIPTION = (
        "Compose video effects visually without an LLM. "
        "Select effects from categorized dropdowns, choose a preset, "
        "add raw FFmpeg filters, and target objects with SAM3. "
        "Connect the output to the FFMPEGA Agent node."
    )

    @staticmethod
    def _strip_category(name: str) -> str:
        """Strip category prefix from categorized skill names.

        ``"🎨 Visual/blur"`` → ``"blur"``
        ``"none"`` → ``"none"``
        """
        if "/" in name:
            return name.rsplit("/", 1)[-1]
        return name

    def build_pipeline(
        self,
        preset: str = "none",
        effect_1: str = "none",
        effect_1_params: str = "",
        effect_2: str = "none",
        effect_2_params: str = "",
        effect_3: str = "none",
        effect_3_params: str = "",
        raw_ffmpeg: str = "",
        sam3_target: str = "",
        sam3_effect: str = "blur",
        _presets_json: str = "",
        _defaults_json: str = "",
    ) -> tuple[str]:
        """Build the pipeline JSON from user selections."""
        pipeline_steps: list[dict[str, Any]] = []

        # --- Parse effect slots ---
        for raw_name, params_str in [
            (effect_1, effect_1_params),
            (effect_2, effect_2_params),
            (effect_3, effect_3_params),
        ]:
            effect_name = self._strip_category(raw_name)
            if not effect_name or effect_name == "none":
                continue

            params: dict[str, Any] = {}
            if params_str and params_str.strip():
                try:
                    parsed = json.loads(params_str.strip())
                    if isinstance(parsed, dict):
                        params = parsed
                    else:
                        logger.warning(
                            "Effects Builder: params for '%s' must be a JSON "
                            "object, got %s — ignoring",
                            effect_name, type(parsed).__name__,
                        )
                except json.JSONDecodeError as e:
                    logger.warning(
                        "Effects Builder: invalid JSON for '%s' params: %s — ignoring",
                        effect_name, e,
                    )

            pipeline_steps.append({
                "skill": effect_name,
                "params": params,
            })

        # --- SAM3 integration ---
        sam3_config = None
        if sam3_target and sam3_target.strip():
            sam3_config = {
                "target": sam3_target.strip(),
                "effect": sam3_effect if sam3_effect != "none" else "blur",
            }
            # If SAM3 is set and no other effects, add the auto_mask as
            # a pipeline step so the agent knows to run SAM3
            if sam3_effect != "none":
                # Inject auto_mask with the SAM3 target + selected effect
                pipeline_steps.insert(0, {
                    "skill": "auto_mask",
                    "params": {
                        "target": sam3_target.strip(),
                        "effect": sam3_effect,
                    },
                })

        # --- Determine mode ---
        has_skills = len(pipeline_steps) > 0
        has_raw = bool(raw_ffmpeg and raw_ffmpeg.strip())

        if has_skills and has_raw:
            mode = "hybrid"
        elif has_raw:
            mode = "raw"
        elif has_skills:
            mode = "skills"
        else:
            mode = "empty"

        # --- Build output ---
        output = {
            "effects_mode": mode,
            "pipeline": pipeline_steps,
            "raw_ffmpeg": raw_ffmpeg.strip() if has_raw else "",
            "sam3": sam3_config,
        }

        result = json.dumps(output, indent=2)
        logger.debug("Effects Builder output: %s", result)

        return (result,)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        """Re-run when any setting changes."""
        import hashlib
        key = json.dumps(kwargs, sort_keys=True, default=str)
        return hashlib.md5(key.encode()).hexdigest()
