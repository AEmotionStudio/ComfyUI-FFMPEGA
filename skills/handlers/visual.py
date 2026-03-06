"""FFMPEGA Visual skill handlers."""

try:
    from ...core.sanitize import sanitize_text_param, validate_path, ALLOWED_LUT_EXTENSIONS
except ImportError:
    from core.sanitize import sanitize_text_param, validate_path, ALLOWED_LUT_EXTENSIONS

from ._duration_helper import _calc_multiclip_duration

try:
    from ..handler_contract import make_result
except ImportError:
    from skills.handler_contract import make_result

def _f_brightness(p):
    return make_result(vf=[f"eq=brightness={p.get('value', 0)}"])


def _f_contrast(p):
    return make_result(vf=[f"eq=contrast={p.get('value', 1.0)}"])


def _f_saturation(p):
    return make_result(vf=[f"eq=saturation={p.get('value', 1.0)}"])


def _f_hue(p):
    return make_result(vf=[f"hue=h={p.get('value', 0)}"])


def _f_sharpen(p):
    amount = p.get("amount", 1.0)
    return make_result(vf=[f"unsharp=5:5:{amount}:5:5:0"])


def _f_blur(p):
    radius = p.get("radius", 5)
    return make_result(vf=[f"boxblur={radius}:{radius}"])


def _f_denoise(p):
    strength = p.get("strength", "medium")
    m = {"light": "hqdn3d=2:2:3:3", "medium": "hqdn3d=4:3:6:4"}
    return make_result(vf=[m.get(strength, "hqdn3d=6:4:9:6")])


def _f_vignette(p):
    import math
    intensity = float(p.get("intensity", 0.3))
    # Map intensity [0,1] to angle [PI/6, PI/2] for visible vignette
    angle = (math.pi / 6) + intensity * (math.pi / 2 - math.pi / 6)
    return make_result(vf=[f"vignette=angle={angle:.4f}"])


def _f_fade(p):
    fade_type = p.get("type", "in")
    start = float(p.get("start", 0))
    duration = float(p.get("duration", 1))

    # When fade-out start is 0 (default/unset) and we're in a multi-clip
    # pipeline, calculate correct start from total output duration so
    # fade-out happens at the END of the combined video.
    if fade_type in ("out", "both") and start == 0:
        clip_dur = float(p.get("_video_duration", 0))
        n_extra = int(p.get("_extra_input_count", 0))
        if n_extra > 0 and clip_dur > 0:
            total_dur = _calc_multiclip_duration(p, clip_dur, n_extra)
            start = max(0, total_dur - duration)

    vf = []
    if fade_type == "both":
        vf.append(f"fade=t=in:st=0:d={duration}")
        vf.append(f"fade=t=out:st={start}:d={duration}")
    else:
        vf.append(f"fade=t={fade_type}:st={start}:d={duration}")
    return make_result(vf=vf)


def _f_pixelate(p):
    factor = p.get("factor", 10)
    return make_result(vf=[
        f"scale=iw/{factor}:ih/{factor},"
        f"scale=iw*{factor}:ih*{factor}:flags=neighbor"
    ])


def _f_posterize(p):
    levels = int(p.get("levels", 4))
    step = max(1, 256 // levels)
    lut_expr = f"trunc(val/{step})*{step}"
    return make_result(vf=[f"lutrgb=r='{lut_expr}':g='{lut_expr}':b='{lut_expr}'"])


def _f_color_grade(p):
    style = p.get("style", "teal_orange")
    grades = {
        "teal_orange": "eq=saturation=1.3:contrast=1.1,hue=h=-10",
        "warm": "eq=saturation=1.15:contrast=1.05,colorbalance=rs=0.1:gs=0.05:bs=-0.1",
        "cool": "eq=saturation=1.1:contrast=1.05,colorbalance=rs=-0.1:gs=0.0:bs=0.15",
        "desaturated": "eq=saturation=0.6:contrast=1.2:brightness=0.02",
        "high_contrast": "eq=contrast=1.4:saturation=1.15:brightness=-0.05",
    }
    return make_result(vf=[grades.get(style, grades["teal_orange"])])


def _f_chromakey_simple(p):
    color = sanitize_text_param(str(p.get("color", "green")))
    # Map common names to hex
    color_map = {"green": "0x00FF00", "blue": "0x0000FF", "red": "0xFF0000"}
    color_hex = color_map.get(color.lower(), color)
    similarity = float(p.get("similarity", 0.3))
    blend = float(p.get("blend", 0.1))
    # Use filter_complex to composite keyed footage over black background.
    fc = (
        f"[0:v]split[_ckbg][_ckfg];"
        f"[_ckbg]drawbox=x=0:y=0:w=iw:h=ih:c=black:t=fill[_ckblack];"
        f"[_ckfg]colorkey=color={color_hex}:similarity={similarity}:blend={blend}[_ckkeyed];"
        f"[_ckblack][_ckkeyed]overlay=format=auto"
    )
    return make_result(fc=fc)


def _f_deband(p):
    thr = float(p.get("threshold", 0.08))
    rng = int(p.get("range", 16))
    blur = 1 if p.get("blur", True) else 0
    return make_result(vf=[f"deband=1thr={thr}:2thr={thr}:3thr={thr}:4thr={thr}:range={rng}:blur={blur}"])


def _f_color_temperature(p):
    temp = int(p.get("temperature", 6500))
    mix = float(p.get("mix", 1.0))
    return make_result(vf=[f"colortemperature=temperature={temp}:mix={mix}"])


def _f_selective_color(p):
    color_range = p.get("color_range", "reds")
    c = float(p.get("cyan", 0.0))
    m = float(p.get("magenta", 0.0))
    y = float(p.get("yellow", 0.0))
    k = float(p.get("black", 0.0))
    return make_result(vf=[f"selectivecolor={color_range}='{c} {m} {y} {k}'"])


def _f_monochrome(p):
    preset = p.get("preset", "neutral")
    size = float(p.get("size", 1.0))
    presets = {
        "neutral":    {"cb": 0.0, "cr": 0.0},
        "warm":       {"cb": -0.1, "cr": 0.2},
        "cool":       {"cb": 0.2, "cr": -0.1},
        "sepia_tone": {"cb": -0.2, "cr": 0.15},
        "blue_tone":  {"cb": 0.3, "cr": -0.05},
        "green_tone": {"cb": 0.1, "cr": -0.2},
    }
    p_vals = presets.get(preset, presets["neutral"])
    return make_result(vf=[f"monochrome=cb={p_vals['cb']}:cr={p_vals['cr']}:size={size}"])


def _f_chromatic_aberration(p):
    """RGB channel offset using rgbashift — real chromatic aberration."""
    amount = int(p.get("amount", 4))
    return make_result(vf=[f"rgbashift=rh=-{amount}:bh={amount}:rv={amount // 2}:bv=-{amount // 2}"])


def _f_sketch(p):
    """Pencil/ink line art using edgedetect filter."""
    mode = p.get("mode", "pencil")
    if mode == "color":
        return make_result(vf=["edgedetect=low=0.1:high=0.3:mode=colormix"])
    elif mode == "ink":
        return make_result(vf=["edgedetect=low=0.08:high=0.4,negate"])
    else:  # pencil
        return make_result(vf=["edgedetect=low=0.1:high=0.3,negate"])


def _f_glow(p):
    """Bloom/soft glow using split → gblur → screen blend (filter_complex)."""
    radius = float(p.get("radius", 30))
    strength = float(p.get("strength", 0.4))
    strength = max(0.1, min(0.8, strength))
    fc = (
        f"[0:v]split[a][b];"
        f"[b]gblur=sigma={radius}[b];"
        f"[a][b]blend=all_mode=screen:all_opacity={strength}"
    )
    return make_result(fc=fc)


def _f_ghost_trail(p):
    """Temporal trailing/afterimage using lagfun filter."""
    decay = float(p.get("decay", 0.97))
    decay = max(0.9, min(0.995, decay))
    return make_result(vf=[f"lagfun=decay={decay}"])


def _f_color_channel_swap(p):
    """Dramatic color remapping using colorchannelmixer."""
    preset = p.get("preset", "swap_rb")
    presets = {
        "swap_rb": "colorchannelmixer=rr=0:rg=0:rb=1:br=1:bg=0:bb=0",
        "swap_rg": "colorchannelmixer=rr=0:rg=1:rb=0:gr=1:gg=0:gb=0",
        "swap_gb": "colorchannelmixer=gg=0:gb=1:bg=1:bb=0",
        "nightvision": "colorchannelmixer=rr=0.2:rg=0.7:rb=0.1:gr=0.2:gg=0.7:gb=0.1:br=0.1:bg=0.1:bb=0.1",
        "matrix": "colorchannelmixer=rr=0:rg=1:rb=0:gr=0:gg=1:gb=0:br=0:bg=1:bb=0",
    }
    filt = presets.get(preset, presets["swap_rb"])
    return make_result(vf=[filt])


def _f_tilt_shift(p):
    """Real tilt-shift miniature effect with selective blur (filter_complex)."""
    focus = float(p.get("focus_position", 0.5))
    blur_amount = float(p.get("blur_amount", 8))
    # Sharp band is centered on focus, 30% of frame height
    low = max(0, focus - 0.15)
    high = min(1, focus + 0.15)
    fc = (
        f"[0:v]split[a][b];"
        f"[b]gblur=sigma={blur_amount}[b];"
        f"[a][b]blend=all_expr='if(between(Y/H\\,{low}\\,{high})\\,A\\,B)'"
    )
    return make_result(fc=fc)


def _f_false_color(p):
    """Pseudocolor / heat map using pseudocolor filter."""
    palette = p.get("palette", "heat")
    palettes = {
        "heat": (
            "pseudocolor="
            "c0='if(between(val,0,85),255,if(between(val,85,170),255,if(between(val,170,255),255,0)))':"
            "c1='if(between(val,0,85),0,if(between(val,85,170),val-85,if(between(val,170,255),255,0)))':"
            "c2='if(between(val,0,85),0,if(between(val,85,170),0,if(between(val,170,255),val-170,0)))'"
        ),
        "electric": (
            "pseudocolor="
            "c0='if(lt(val,128),val*2,255)':"
            "c1='if(lt(val,128),0,val-128)':"
            "c2='if(lt(val,128),255-val*2,0)'"
        ),
        "blues": (
            "pseudocolor="
            "c0='val/3':"
            "c1='val/2':"
            "c2='val'"
        ),
        "rainbow": (
            "pseudocolor="
            "c0='if(lt(val,85),255-val*3,if(lt(val,170),0,val*3-510))':"
            "c1='if(lt(val,85),val*3,if(lt(val,170),255,765-val*3))':"
            "c2='if(lt(val,85),0,if(lt(val,170),val*3-255,255))'"
        ),
    }
    filt = palettes.get(palette, palettes["heat"])
    return make_result(vf=[filt])


def _f_halftone(p):
    """Print halftone dot pattern using geq."""
    dot_size = float(p.get("dot_size", 0.3))
    freq = max(0.1, min(1.0, dot_size))
    return make_result(vf=[
        f"format=gray,geq='if(gt(lum(X\\,Y)\\,128+127*sin(X*{freq})*sin(Y*{freq}))\\,255\\,0)'"
    ])


def _f_neon_enhanced(p):
    """Neon glow with real edge detection + high-saturation blend (filter_complex)."""
    intensity = p.get("intensity", "medium")
    opacity = {"subtle": 0.3, "medium": 0.5, "strong": 0.7}.get(intensity, 0.5)
    fc = (
        f"[0:v]split[a][b];"
        f"[b]edgedetect=low=0.08:high=0.3:mode=colormix,"
        f"eq=saturation=3:brightness=0.1[b];"
        f"[a][b]blend=all_mode=screen:all_opacity={opacity}"
    )
    return make_result(fc=fc)


# Shared thermal pseudocolor expression — used by both _f_thermal_enhanced
# and _effect_filter_map (auto_mask thermal effect).  Single source of truth.
_THERMAL_PSEUDOCOLOR = (
    "pseudocolor="
    "c0='if(between(val,0,85),255,if(between(val,85,170),255,if(between(val,170,255),255,0)))':"
    "c1='if(between(val,0,85),0,if(between(val,85,170),val*3-255,if(between(val,170,255),255,0)))':"
    "c2='if(between(val,0,85),0,if(between(val,85,170),0,if(between(val,170,255),val*3-510,0)))'"
)


def _f_thermal_enhanced(p):
    """Real thermal/heat vision using pseudocolor."""
    return make_result(vf=[_THERMAL_PSEUDOCOLOR])


# ── Edit-fallback keyword → FFmpeg filter maps ──────────────────────
# Used by _edit_ffmpeg_fallback() when FLUX Klein is disabled.
# Hoisted to module level so they're built once, not per-call.

# colorbalance options: rs/gs/bs (shadows), rm/gm/bm (midtones), rh/gh/bh (highlights)
_EDIT_COLOR_MAP = {
    "red":    "colorbalance=rs=0.6:rm=0.6:rh=0.6",
    "blue":   "colorbalance=bs=0.6:bm=0.6:bh=0.6",
    "green":  "colorbalance=gs=0.6:gm=0.6:gh=0.6",
    "yellow": "colorbalance=rs=0.4:gs=0.4:rm=0.4:gm=0.4:rh=0.4:gh=0.4",
    "orange": "colorbalance=rs=0.5:gs=0.2:rm=0.5:gm=0.2:rh=0.5:gh=0.2",
    "purple": "colorbalance=rs=0.4:bs=0.4:rm=0.4:bm=0.4:rh=0.4:bh=0.4",
    "pink":   "colorbalance=rs=0.5:bs=0.2:rm=0.5:bm=0.2:rh=0.5:bh=0.2",
    "blonde": "colorbalance=rs=0.3:gs=0.2:rm=0.3:gm=0.2:rh=0.3:gh=0.2",
    "white":  "eq=brightness=0.4:saturation=0.1",
    "black":  "eq=brightness=-0.4:saturation=0.1",
    "chrome": "eq=brightness=0.15:saturation=0.0:contrast=1.3",
    "gold":   "colorbalance=rs=0.4:gs=0.3:rm=0.4:gm=0.3:rh=0.3:gh=0.2",
}

_EDIT_TONE_MAP = {
    "bright":    "eq=brightness=0.2:saturation=1.1",
    "dark":      "eq=brightness=-0.2:saturation=0.9",
    "warm":      "colortemperature=temperature=6500",
    "cool":      "colortemperature=temperature=3500",
    "vibrant":   "eq=saturation=2.0",
    "cinematic": "eq=saturation=0.7:contrast=1.2:brightness=-0.05",
    "vintage":   "eq=saturation=0.6:contrast=1.1,colorbalance=rs=0.15:gs=0.05:bs=-0.1",
    "sepia":     "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131",
    "neon":      "eq=saturation=3.0:brightness=0.1",
    "thermal":   _THERMAL_PSEUDOCOLOR,
}


def _f_comic_book_enhanced(p):
    """Comic book with real edge outline + posterization (filter_complex)."""
    style = p.get("style", "classic")
    levels = {"classic": 6, "manga": 2, "pop_art": 4}.get(style, 6)
    step = max(1, 256 // levels)
    lut_expr = f"trunc(val/{step})*{step}"
    fc = (
        f"[0:v]split[a][b];"
        f"[b]edgedetect=low=0.1:high=0.4,negate[b];"
        f"[a]lutrgb=r='{lut_expr}':g='{lut_expr}':b='{lut_expr}',"
        f"eq=saturation=1.5:contrast=1.3[a];"
        f"[a][b]blend=all_mode=multiply"
    )
    return make_result(fc=fc)


def _f_waveform(p):
    """Audio waveform visualization using showwaves + overlay (filter_complex)."""
    mode = p.get("mode", "cline")
    height = int(p.get("height", 200))
    color = sanitize_text_param(str(p.get("color", "white")))
    position = p.get("position", "bottom")
    opacity = float(p.get("opacity", 0.8))

    pos_map = {
        "bottom": f"main_h-{height}",
        "center": f"(main_h-{height})/2",
        "top": "0",
    }
    y_expr = pos_map.get(position, pos_map["bottom"])

    fc = (
        f"[0:a]showwaves=s=1920x{height}:mode={mode}:colors={color},"
        f"format=yuva420p,colorchannelmixer=aa={opacity}[wave];"
        f"[0:v][wave]overlay=0:{y_expr}:shortest=1"
    )
    return make_result(fc=fc)


def _colorkey_impl(color, similarity, blend, background):
    """Shared colorkey implementation for chromakey and colorkey skills."""
    color = sanitize_text_param(str(color))
    similarity = float(similarity)
    blend = float(blend)
    background = sanitize_text_param(str(background))

    if background == "transparent":
        vf = [f"colorkey=color={color}:similarity={similarity}:blend={blend}"]
        return make_result(vf=vf)

    fc = (
        f"[0:v]split[ckv][bg];"
        f"[ckv]colorkey=color={color}:similarity={similarity}:blend={blend}[keyed];"
        f"[bg]drawbox=c={background}:t=fill[solid];"
        f"[solid][keyed]overlay=format=auto"
    )
    return make_result(fc=fc)


def _f_chromakey(p):
    """Remove a solid-color background (chroma key / green screen)."""
    return _colorkey_impl(
        p.get("color", "0x00FF00"),
        p.get("similarity", 0.3),
        p.get("blend", 0.1),
        p.get("background", "black"),
    )


def _f_blend(p):
    """Blend/double exposure: blend two video inputs together."""
    mode = str(p.get("mode", "addition")).lower()
    opacity = float(p.get("opacity", 0.5))
    fc = f"[0:v][1:v]blend=all_mode={mode}:all_opacity={opacity}"
    return make_result(fc=fc)


def _f_color_match(p):
    """Match color/brightness of video to a reference using histogram equalization."""
    vf = "histeq=strength=0.5:intensity=0.5"
    return make_result(vf=[vf])


def _f_datamosh(p):
    """Datamosh/glitch art via motion vector visualization."""
    mode = p.get("mode", "pf+bf+bb")
    vf = f"codecview=mv={mode}"
    return make_result(vf=[vf], io=["-flags2", "+export_mvs"])


def _f_mask_blur(p):
    """Blur a rectangular region of the video (privacy/censor)."""
    x = int(p.get("x", 100))
    y = int(p.get("y", 100))
    w = int(p.get("w", 200))
    h = int(p.get("h", 200))
    strength = int(p.get("strength", 20))
    fc = (
        f"[0:v]split[base][blur];"
        f"[blur]crop={w}:{h}:{x}:{y},boxblur={strength}[blurred];"
        f"[base][blurred]overlay={x}:{y}:shortest=1"
    )
    return make_result(fc=fc)


def _escape_filter_path(path: str) -> str:
    """Escape a file path for use inside ffmpeg filter expressions."""
    for ch in ("\\", "'", ":", ";", "[", "]"):
        path = path.replace(ch, f"\\{ch}")
    return path


def _f_lut_apply(p):
    """Apply a color LUT with intensity blending."""
    from pathlib import Path

    path = sanitize_text_param(str(p.get("path", "lut.cube")))
    intensity = float(p.get("intensity", 1.0))

    # Auto-resolve short names: if path has no separator, search luts/ folder
    if "/" not in path and "\\" not in path:
        luts_dir = Path(__file__).resolve().parent.parent.parent / "luts"
        for ext in (".cube", ".3dl", ""):
            candidate = luts_dir / f"{path}{ext}"
            if candidate.is_file():
                path = str(candidate)
                break
        else:
            if luts_dir.is_dir():
                for f in luts_dir.iterdir():
                    if f.suffix.lower() in (".cube", ".3dl") and path.lower() in f.stem.lower():
                        path = str(f)
                        break

    validate_path(path, ALLOWED_LUT_EXTENSIONS, must_exist=True)
    escaped = _escape_filter_path(path)

    if intensity >= 1.0:
        vf = f"lut3d=file={escaped}"
        return make_result(vf=[vf])
    elif intensity <= 0.0:
        return make_result()
    else:
        inv = 1.0 - intensity
        fc = (
            f"[0:v]split[orig][lut];"
            f"[lut]lut3d=file={escaped}[graded];"
            f"[orig][graded]blend=all_mode=normal:all_opacity={intensity}"
        )
        return make_result(fc=fc)

# ── Keying & Masking skill handlers ─────────────────────────────── #


def _f_colorkey(p):
    """Key out an arbitrary color (general-purpose version of chromakey)."""
    return _colorkey_impl(
        p.get("color", "0x00FF00"),
        p.get("similarity", 0.3),
        p.get("blend", 0.1),
        p.get("background", "black"),
    )


def _f_lumakey(p):
    """Key out regions based on brightness (luma)."""
    threshold = float(p.get("threshold", 0.0))
    tolerance = float(p.get("tolerance", 0.1))
    softness = float(p.get("softness", 0.0))
    background = sanitize_text_param(str(p.get("background", "black")))

    lk = f"lumakey=threshold={threshold}:tolerance={tolerance}:softness={softness}"

    if background == "transparent":
        return make_result(vf=[lk])

    fc = (
        f"[0:v]split[lkv][bg];"
        f"[lkv]{lk}[keyed];"
        f"[bg]drawbox=c={background}:t=fill[solid];"
        f"[solid][keyed]overlay=format=auto"
    )
    return make_result(fc=fc)


def _f_colorhold(p):
    """Keep only a selected color, desaturate everything else (sin-city effect)."""
    color = sanitize_text_param(str(p.get("color", "0xFF0000")))
    similarity = float(p.get("similarity", 0.3))
    blend = float(p.get("blend", 0.1))
    return make_result(vf=[f"colorhold=color={color}:similarity={similarity}:blend={blend}"])


def _f_despill(p):
    """Remove green/blue color spill from chroma-keyed footage."""
    spill_type = p.get("type", "green")
    type_val = 1 if str(spill_type).lower() in ("blue", "1") else 0
    mix = float(p.get("mix", 0.5))
    expand = float(p.get("expand", 0.0))
    brightness = float(p.get("brightness", 0.0))
    return make_result(vf=[f"despill=type={type_val}:mix={mix}:expand={expand}:brightness={brightness}"])


def _f_remove_background(p):
    """Remove background using rembg (optional dependency).

    Pipeline:
    1. Extract frames from the input video via cv2
    2. Run rembg per-frame to produce alpha masks
    3. Write masks to a temp grayscale video (lossless FFV1)
    4. Return FFmpeg filter_complex that composites via maskedmerge
       or alphamerge (transparent mode)
    """
    import logging
    log = logging.getLogger("ffmpega")

    try:
        from rembg import remove as rembg_remove, new_session  # noqa: F401
    except ImportError:
        log.error(
            "rembg is not installed. Install with: "
            "pip install 'comfyui-ffmpega[masking]'"
        )
        return make_result()

    model_name = str(p.get("model", "bria-rmbg"))
    background = sanitize_text_param(str(p.get("background", "transparent")).lower())
    video_path = p.get("_input_path", "")

    if not video_path:
        log.error("remove_background: no _input_path provided")
        return make_result()

    import os
    if not os.path.isfile(video_path):
        log.error("remove_background: input file not found: %s", video_path)
        return make_result()

    # ── Generate mask video ──────────────────────────────────────
    try:
        import cv2
        import numpy as np
        import tempfile
        from PIL import Image

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            log.error("remove_background: cannot open video: %s", video_path)
            return make_result()

        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        log.info(
            "remove_background: processing %d frames (%dx%d @ %.1f fps) "
            "with model=%s",
            total_frames, width, height, fps, model_name,
        )

        # Create session once for efficiency (avoids re-loading model)
        session = new_session(model_name)

        # Write mask to a temp file (lossless FFV1 in MKV container)
        mask_fd = tempfile.NamedTemporaryFile(
            suffix="_rembg_mask.mkv", delete=False,
        )
        mask_path = mask_fd.name
        mask_fd.close()

        fourcc = cv2.VideoWriter_fourcc(*"FFV1")
        writer = cv2.VideoWriter(mask_path, fourcc, fps, (width, height), False)
        if not writer.isOpened():
            log.error("remove_background: cannot create mask writer")
            cap.release()
            return make_result()

        frame_idx = 0
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # Convert BGR → RGB → PIL
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb)

                # Run rembg — returns RGBA PIL image
                result = rembg_remove(pil_img, session=session)

                # Extract alpha channel as grayscale mask
                result_np = np.array(result)
                if result_np.shape[2] == 4:
                    alpha = result_np[:, :, 3]
                else:
                    # Fallback: convert to grayscale if no alpha
                    alpha = cv2.cvtColor(result_np, cv2.COLOR_RGB2GRAY)

                writer.write(alpha)
                frame_idx += 1

                if frame_idx % 30 == 0:
                    log.info(
                        "remove_background: %d/%d frames processed",
                        frame_idx, total_frames,
                    )
        finally:
            cap.release()
            writer.release()

        log.info(
            "remove_background: mask video complete (%d frames): %s",
            frame_idx, mask_path,
        )

    except Exception as e:
        log.error("remove_background: frame processing failed: %s", e)
        # Clean up orphaned temp mask file on failure
        try:
            import os as _os
            if mask_path and _os.path.isfile(mask_path):
                _os.unlink(mask_path)
        except Exception:
            pass
        return make_result()

    # Store mask path in metadata for downstream cleanup (consistent
    # with auto_mask handler).  The mask file must survive until ffmpeg
    # finishes encoding, so we can't delete it eagerly here.
    _metadata_ref = p.get("_metadata_ref")
    if isinstance(_metadata_ref, dict):
        _metadata_ref["_mask_video_path"] = mask_path

    # ── Build FFmpeg composite ───────────────────────────────────
    if background == "transparent":
        escaped = _escape_filter_path(mask_path)
        fc = (
            f"movie={escaped},format=gray[alpha];"
            f"[0:v][alpha]alphamerge,format=yuva420p"
        )
        return make_result(
            fc=fc,
            opts=[
                "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                "-auto-alt-ref", "0", "-f", "webm",
            ],
        )

    # Solid color background — map to the appropriate effect
    if background == "green":
        effect = "greenscreen"
    else:
        # Arbitrary solid color: inject a custom drawbox fill into the
        # effect map so _build_mask_fc composites it correctly.
        effect = f"drawbox=c={background}:t=fill"
    return _build_mask_fc(mask_path, effect, 50, True)


# ── SAM3 Auto-Mask handler ────────────────────────────────────────── #


def _f_auto_mask(p):
    """Apply an effect to SAM3-detected objects using text prompts.

    This handler uses a two-pass approach:
    1. SAM3 generates per-object masks from text descriptions
    2. FFmpeg applies the chosen effect only to the masked region

    When SAM3 is not available, falls back to a full-frame effect
    with a warning so the pipeline doesn't break.

    Params:
        target (str):       Text prompt describing what to mask (e.g. "the face").
        effect (str):       One of blur, pixelate, remove, grayscale, highlight.
        strength (int):     Effect intensity 1–100 (default 50).
        invert (bool):      Invert mask — apply effect to background instead.
    """
    import logging
    import os
    log = logging.getLogger("ffmpega")

    target = str(p.get("target", "the subject"))
    effect = str(p.get("effect", "blur")).lower()
    strength = int(p.get("strength", 50))
    invert = bool(p.get("invert", False))
    video_path = p.get("_input_path", "")

    # ── Cache: reuse model outputs from a previous compose() pass ────
    # When ffmpeg fails and the execution engine retries with a corrected
    # pipeline, compose() is called again.  SAM3 + FLUX Klein outputs are
    # expensive (minutes of GPU time), so reuse them if they still exist.
    _metadata_ref = p.get("_metadata_ref")
    _cached_mask = (
        _metadata_ref.get("_mask_video_path")
        if isinstance(_metadata_ref, dict) else None
    )
    # FLUX Klein outputs are cached per-prompt so two auto_mask calls
    # with different edit prompts (e.g. "chrome skin" vs "thermal") don't
    # collide.  The cache dict maps prompt → output_path.
    _flux_cache = (
        _metadata_ref.get("_flux_klein_outputs", {})
        if isinstance(_metadata_ref, dict) else {}
    )
    _cache_key = str(p.get("edit_prompt", effect))

    mask_path = None  # will be set by cache hit or SAM3 generation

    if _cached_mask and os.path.isfile(_cached_mask):
        log.info("auto_mask: reusing cached mask from previous run: %s", _cached_mask)
        # FLUX Klein outputs (remove/edit) are self-contained videos
        _cached_flux = _flux_cache.get(_cache_key)
        if effect in ("remove", "edit") and _cached_flux and os.path.isfile(_cached_flux):
            log.info("auto_mask: reusing cached FLUX Klein output: %s", _cached_flux)
            escaped = _escape_filter_path(_cached_flux)
            fc = f"movie={escaped}[inp];[inp]format=yuv420p[_vout]"
            return make_result(fc=fc)
        # For non-FLUX effects, rebuild the ffmpeg filter with the cached mask
        if effect not in ("remove", "edit"):
            return _build_mask_fc(_cached_mask, effect, strength, invert)
        # Mask exists but no cached FLUX output for this prompt —
        # reuse the cached mask for the new FLUX edit (skip SAM3).
        mask_path = _cached_mask
    else:
        # No cache hit — run SAM3 to generate the mask
        sam3_device = str(p.get("_sam3_device", "gpu")).lower()
        sam3_max_objects = int(p.get("_sam3_max_objects", 5))
        sam3_det_threshold = float(p.get("_sam3_det_threshold", 0.7))

        # Parse point prompt data (from the JS point selector)
        mask_points_json = p.get("_mask_points", "")
        point_coords = None
        point_labels = None
        point_src_w = 0
        point_src_h = 0
        if mask_points_json:
            import json as _json
            try:
                pt_data = _json.loads(mask_points_json)
                if isinstance(pt_data, dict):
                    point_coords = pt_data.get("points")
                    point_labels = pt_data.get("labels")
                    point_src_w = int(pt_data.get("image_width", 0))
                    point_src_h = int(pt_data.get("image_height", 0))
                    if point_coords and point_labels:
                        log.info("auto_mask: using %d point prompt(s) (src %dx%d)",
                                 len(point_coords), point_src_w, point_src_h)
            except (ValueError, TypeError) as exc:
                log.warning("Failed to parse mask_points JSON: %s", exc)

        # Try to load SAM3
        try:
            from ...core.sam3_masker import mask_video_subprocess as sam3_mask_video  # noqa: F811
            _has_sam3 = True
        except ImportError:
            try:
                from core.sam3_masker import mask_video_subprocess as sam3_mask_video  # noqa: F811
                _has_sam3 = True
            except ImportError:
                _has_sam3 = False

        if not _has_sam3:
            log.warning(
                "SAM3 not available for auto_mask — falling back to full-frame "
                "effect. Install with: pip install git+https://github.com/facebookresearch/sam3.git"
            )
            _metadata_ref = p.get("_metadata_ref")
            if _metadata_ref is not None and isinstance(_metadata_ref, dict):
                _metadata_ref["_skill_degraded"] = True
            return _auto_mask_fallback(effect, strength)

        # Generate mask video using SAM3 with text + optional point prompts
        # Runs in a subprocess to avoid CUDA memory leaks (~1.5 GB/run).
        try:
            mask_path = sam3_mask_video(
                video_path=video_path,
                prompt=target,
                device=sam3_device,
                max_objects=sam3_max_objects,
                det_threshold=sam3_det_threshold,
                points=point_coords,
                labels=point_labels,
                point_src_width=point_src_w,
                point_src_height=point_src_h,
            )
        except Exception as e:
            log.error("SAM3 mask generation failed: %s — falling back", e)
            _metadata_ref = p.get("_metadata_ref")
            if _metadata_ref is not None and isinstance(_metadata_ref, dict):
                _metadata_ref["_skill_degraded"] = True
            return _auto_mask_fallback(effect, strength)

    if mask_path is None:
        raise RuntimeError("mask_path must be set by cache or SAM3")

    # Store mask path in metadata so agent_node can generate overlay
    _metadata_ref = p.get("_metadata_ref")
    if _metadata_ref is not None and isinstance(_metadata_ref, dict):
        _metadata_ref["_mask_video_path"] = mask_path

    # Whether FLUX Klein is enabled (off by default to save VRAM)
    _enable_flux_klein = bool(p.get("_enable_flux_klein", False))

    # Temporal smoothing mode for FLUX Klein effects (node-level toggle)
    smoothing = str(p.get("_flux_smoothing", p.get("smoothing", "none")))
    if smoothing not in ("none", "gaussian", "adaptive"):
        smoothing = "none"

    # Special handling for "remove" — use FLUX Klein AI inpainting (if enabled)
    # or fall back to LaMa inpainting
    if effect == "remove":
        if _enable_flux_klein:
            try:
                try:
                    from ...core.flux_klein_editor import remove_object
                except ImportError:
                    from core.flux_klein_editor import remove_object
                inpainted_path = remove_object(
                    video_path=video_path,
                    mask_video_path=mask_path,
                    smoothing=smoothing,
                )
                log.info("FLUX Klein removal complete: %s", inpainted_path)
                if _metadata_ref is not None and isinstance(_metadata_ref, dict):
                    _metadata_ref.setdefault("_flux_klein_outputs", {})[_cache_key] = inpainted_path
                escaped = _escape_filter_path(inpainted_path)
                fc = f"movie={escaped}[inp];[inp]format=yuv420p[_vout]"
                return make_result(fc=fc)
            except Exception as e:
                log.error("FLUX Klein removal failed: %s", e)
                try:
                    try:
                        from ...core.flux_klein_editor import cleanup as _fk_cleanup
                    except ImportError:
                        from core.flux_klein_editor import cleanup as _fk_cleanup
                    _fk_cleanup()
                except Exception:
                    pass
                raise
        else:
            # FLUX Klein disabled — fall back to LaMa inpainting
            log.info("FLUX Klein disabled — using LaMa for object removal")
            try:
                try:
                    from ...core.lama_inpainter import remove_object as lama_remove
                except ImportError:
                    from core.lama_inpainter import remove_object as lama_remove
                inpainted_path = lama_remove(
                    video_path=video_path,
                    mask_video_path=mask_path,
                )
                log.info("LaMa removal complete: %s", inpainted_path)
                escaped = _escape_filter_path(inpainted_path)
                fc = f"movie={escaped}[inp];[inp]format=yuv420p[_vout]"
                return make_result(fc=fc)
            except Exception as e:
                log.error("LaMa removal failed: %s — falling back to black fill", e)
                return _build_mask_fc(mask_path, "remove", strength, invert)

    # Special handling for "edit" — use FLUX Klein text-guided editing (if enabled)
    # or fall back to FFmpeg filter approximation
    if effect == "edit":
        edit_prompt = str(p.get("edit_prompt", ""))
        if not edit_prompt:
            raise ValueError(
                "auto_mask effect='edit' requires an 'edit_prompt' parameter "
                "describing the desired change (e.g. 'change hair to blonde')"
            )
        if _enable_flux_klein:
            try:
                try:
                    from ...core.flux_klein_editor import edit_video
                except ImportError:
                    from core.flux_klein_editor import edit_video
                edited_path = edit_video(
                    video_path=video_path,
                    mask_video_path=mask_path,
                    prompt=edit_prompt,
                    smoothing=smoothing,
                )
                log.info("FLUX Klein edit complete: %s", edited_path)
                if _metadata_ref is not None and isinstance(_metadata_ref, dict):
                    _metadata_ref.setdefault("_flux_klein_outputs", {})[_cache_key] = edited_path
                escaped = _escape_filter_path(edited_path)
                fc = f"movie={escaped}[inp];[inp]format=yuv420p[_vout]"
                return make_result(fc=fc)
            except Exception as e:
                log.error("FLUX Klein edit failed: %s", e)
                try:
                    try:
                        from ...core.flux_klein_editor import cleanup as _fk_cleanup
                    except ImportError:
                        from core.flux_klein_editor import cleanup as _fk_cleanup
                    _fk_cleanup()
                except Exception:
                    pass
                raise
        else:
            # FLUX Klein disabled — fall back to FFmpeg filter approximation
            log.info(
                "FLUX Klein disabled — using FFmpeg filter fallback for edit: %s",
                edit_prompt,
            )
            return _edit_ffmpeg_fallback(edit_prompt, strength, mask_path, invert)

    # Build FFmpeg filter_complex that uses the mask
    return _build_mask_fc(mask_path, effect, strength, invert)


def _edit_ffmpeg_fallback(edit_prompt: str, strength: int, mask_path: str, invert: bool):
    """Lightweight FFmpeg filter fallback for auto_mask effect='edit'.

    Maps keywords in the edit prompt to FFmpeg color/brightness/saturation
    filters applied to the masked region.  Not AI-quality, but functional
    for simple color fills, tinting, and brightness adjustments — and uses
    zero VRAM.

    Called when use_flux_klein is OFF (the default).
    """
    import logging
    import re
    log = logging.getLogger("ffmpega")

    prompt_lower = edit_prompt.lower()

    # Find matching filter from prompt keywords (word-boundary match
    # to avoid false positives like "sacred" matching "red").
    fx_filter = None

    # Check color keywords first (more specific)
    for keyword, filt in _EDIT_COLOR_MAP.items():
        if re.search(r'\b' + re.escape(keyword) + r'\b', prompt_lower):
            fx_filter = filt
            log.info("edit fallback: matched color keyword '%s' → %s", keyword, filt)
            break

    # Then check tonal keywords
    if fx_filter is None:
        for keyword, filt in _EDIT_TONE_MAP.items():
            if re.search(r'\b' + re.escape(keyword) + r'\b', prompt_lower):
                fx_filter = filt
                log.info("edit fallback: matched tone keyword '%s' → %s", keyword, filt)
                break

    # Default: boost saturation + slight warm tint (generic "editing" look)
    if fx_filter is None:
        fx_filter = "eq=saturation=1.3:brightness=0.05"
        log.warning(
            "edit fallback: no keyword match for '%s' — using default "
            "saturation/brightness boost. Enable FLUX Klein for AI-quality edits.",
            edit_prompt,
        )

    return _build_mask_fc(mask_path, fx_filter, strength, invert)


def _effect_filter_map(strength: int) -> dict:
    """Shared effect-to-FFmpeg-filter mapping for auto_mask."""
    return {
        "blur": f"boxblur={max(1, strength // 5)}",
        "pixelate": f"scale=iw/{max(2, strength // 10)}:ih/{max(2, strength // 10)},"
                    f"scale=iw*{max(2, strength // 10)}:ih*{max(2, strength // 10)}:flags=neighbor,"
                    f"scale=iw:ih",
        "grayscale": "colorchannelmixer=.3:.4:.3:0:.3:.4:.3:0:.3:.4:.3",
        "highlight": f"eq=brightness={min(0.5, strength / 200.0)}:saturation=1.5",
        "remove": "drawbox=c=black:t=fill",
        "greenscreen": "drawbox=c=#00FF00:t=fill",
        "thermal": _THERMAL_PSEUDOCOLOR,
    }


def _auto_mask_fallback(effect: str, strength: int):
    """Full-frame fallback when SAM3 is unavailable."""
    effect_filters = _effect_filter_map(strength)
    if effect == "transparent":
        # Transparent fallback: output fully transparent frame via WebM
        return make_result(
            vf=["format=yuva420p,colorchannelmixer=aa=0"],
            opts=["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                  "-auto-alt-ref", "0", "-f", "webm"],
        )
    filt = effect_filters.get(effect, effect_filters["blur"])
    return make_result(vf=[filt])


def _build_mask_fc(mask_path: str, effect: str, strength: int, invert: bool):
    """Build a filter_complex that applies an effect using a mask video.

    Approach:
    - Input 0:v = original video
    - Input mask  = grayscale mask video (loaded via movie filter)
    - Split original into [base] and [fx]
    - Apply effect to [fx]
    - Use maskedmerge to combine: mask selects where effect shows

    Special effects:
    - greenscreen: fills masked area with chroma green (#00FF00)
    - transparent: outputs video with alpha channel (WebM VP9)
    """
    # Escape path for ffmpeg filter expressions
    mask_path = _escape_filter_path(mask_path)

    # --- Transparent effect: embed alpha channel ---
    if effect == "transparent":
        if invert:
            # Keep target visible, make background transparent
            fc = (
                f"movie={mask_path},format=gray[alpha];"
                f"[0:v][alpha]alphamerge,format=yuva420p"
            )
        else:
            # Make target transparent, keep background
            fc = (
                f"movie={mask_path},format=gray,negate[alpha];"
                f"[0:v][alpha]alphamerge,format=yuva420p"
            )
        return make_result(
            fc=fc,
            opts=["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                  "-auto-alt-ref", "0", "-f", "webm"],
        )

    # --- Standard effects (including greenscreen) ---
    effect_map = _effect_filter_map(strength)
    # If effect is a raw FFmpeg filter string (contains '='), use it
    # directly.  This supports arbitrary solid-color fills from
    # remove_background (e.g. "drawbox=c=white:t=fill").
    if effect in effect_map:
        fx_filter = effect_map[effect]
    elif "=" in effect:
        fx_filter = effect
    else:
        fx_filter = effect_map["blur"]

    # Build the filter graph
    if invert:
        fc = (
            f"movie={mask_path}[mask];"
            f"[0:v]split[base][fx];"
            f"[fx]{fx_filter}[effected];"
            f"[mask]format=gray[gmask];"
            f"[effected][base][gmask]maskedmerge"
        )
    else:
        fc = (
            f"movie={mask_path}[mask];"
            f"[0:v]split[base][fx];"
            f"[fx]{fx_filter}[effected];"
            f"[mask]format=gray[gmask];"
            f"[base][effected][gmask]maskedmerge"
        )

    return make_result(fc=fc)

