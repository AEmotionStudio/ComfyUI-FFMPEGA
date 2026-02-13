"""FFMPEGA Visual skill handlers.

Auto-generated from composer.py — do not edit directly.
"""

try:
    from ...core.sanitize import sanitize_text_param
except ImportError:
    try:
        from core.sanitize import sanitize_text_param
    except ImportError:
        def sanitize_text_param(s): return s

def _f_brightness(p):
    return [f"eq=brightness={p.get('value', 0)}"], [], []


def _f_contrast(p):
    return [f"eq=contrast={p.get('value', 1.0)}"], [], []


def _f_saturation(p):
    return [f"eq=saturation={p.get('value', 1.0)}"], [], []


def _f_hue(p):
    return [f"hue=h={p.get('value', 0)}"], [], []


def _f_sharpen(p):
    amount = p.get("amount", 1.0)
    return [f"unsharp=5:5:{amount}:5:5:0"], [], []


def _f_blur(p):
    radius = p.get("radius", 5)
    return [f"boxblur={radius}:{radius}"], [], []


def _f_denoise(p):
    strength = p.get("strength", "medium")
    m = {"light": "hqdn3d=2:2:3:3", "medium": "hqdn3d=4:3:6:4"}
    return [m.get(strength, "hqdn3d=6:4:9:6")], [], []


def _f_vignette(p):
    import math
    intensity = float(p.get("intensity", 0.3))
    # Map intensity [0,1] to angle [PI/6, PI/2] for visible vignette
    angle = (math.pi / 6) + intensity * (math.pi / 2 - math.pi / 6)
    return [f"vignette=angle={angle:.4f}"], [], []


def _f_fade(p):
    fade_type = p.get("type", "in")
    start = p.get("start", 0)
    duration = p.get("duration", 1)
    vf = []
    if fade_type == "both":
        vf.append(f"fade=t=in:st=0:d={duration}")
        vf.append(f"fade=t=out:d={duration}")
    else:
        vf.append(f"fade=t={fade_type}:st={start}:d={duration}")
    return vf, [], []


def _f_pixelate(p):
    factor = p.get("factor", 10)
    return [
        f"scale=iw/{factor}:ih/{factor},"
        f"scale=iw*{factor}:ih*{factor}:flags=neighbor"
    ], [], []


def _f_posterize(p):
    levels = int(p.get("levels", 4))
    step = max(1, 256 // levels)
    lut_expr = f"trunc(val/{step})*{step}"
    return [f"lutrgb=r='{lut_expr}':g='{lut_expr}':b='{lut_expr}'"], [], []


def _f_color_grade(p):
    style = p.get("style", "teal_orange")
    grades = {
        "teal_orange": "eq=saturation=1.3:contrast=1.1,hue=h=-10",
        "warm": "eq=saturation=1.15:contrast=1.05,colorbalance=rs=0.1:gs=0.05:bs=-0.1",
        "cool": "eq=saturation=1.1:contrast=1.05,colorbalance=rs=-0.1:gs=0.0:bs=0.15",
        "desaturated": "eq=saturation=0.6:contrast=1.2:brightness=0.02",
        "high_contrast": "eq=contrast=1.4:saturation=1.15:brightness=-0.05",
    }
    return [grades.get(style, grades["teal_orange"])], [], []


def _f_chromakey_simple(p):
    color = sanitize_text_param(str(p.get("color", "green")))
    # Map common names to hex
    color_map = {"green": "0x00FF00", "blue": "0x0000FF", "red": "0xFF0000"}
    color_hex = color_map.get(color.lower(), color)
    similarity = float(p.get("similarity", 0.3))
    blend = float(p.get("blend", 0.1))
    # Use filter_complex to composite keyed footage over black background.
    # colorkey produces alpha transparency which H.264/NVENC discard silently,
    # so we overlay onto black to flatten the alpha before encoding.
    fc = (
        f"[0:v]split[_ckbg][_ckfg];"
        f"[_ckbg]drawbox=x=0:y=0:w=iw:h=ih:c=black:t=fill[_ckblack];"
        f"[_ckfg]colorkey=color={color_hex}:similarity={similarity}:blend={blend}[_ckkeyed];"
        f"[_ckblack][_ckkeyed]overlay=format=auto"
    )
    return [], [], [], fc


def _f_deband(p):
    thr = float(p.get("threshold", 0.08))
    rng = int(p.get("range", 16))
    blur = 1 if p.get("blur", True) else 0
    return [f"deband=1thr={thr}:2thr={thr}:3thr={thr}:4thr={thr}:range={rng}:blur={blur}"], [], []


def _f_color_temperature(p):
    temp = int(p.get("temperature", 6500))
    mix = float(p.get("mix", 1.0))
    return [f"colortemperature=temperature={temp}:mix={mix}"], [], []


def _f_selective_color(p):
    color_range = p.get("color_range", "reds")
    c = float(p.get("cyan", 0.0))
    m = float(p.get("magenta", 0.0))
    y = float(p.get("yellow", 0.0))
    k = float(p.get("black", 0.0))
    # selectivecolor expects CMYK values as space-separated string
    return [f"selectivecolor={color_range}='{c} {m} {y} {k}'"], [], []


def _f_monochrome(p):
    preset = p.get("preset", "neutral")
    size = float(p.get("size", 1.0))
    # cb = chroma blue spot, cr = chroma red spot
    presets = {
        "neutral":    {"cb": 0.0, "cr": 0.0},
        "warm":       {"cb": -0.1, "cr": 0.2},
        "cool":       {"cb": 0.2, "cr": -0.1},
        "sepia_tone": {"cb": -0.2, "cr": 0.15},
        "blue_tone":  {"cb": 0.3, "cr": -0.05},
        "green_tone": {"cb": 0.1, "cr": -0.2},
    }
    p_vals = presets.get(preset, presets["neutral"])
    return [f"monochrome=cb={p_vals['cb']}:cr={p_vals['cr']}:size={size}"], [], []


def _f_chromatic_aberration(p):
    """RGB channel offset using rgbashift — real chromatic aberration."""
    amount = int(p.get("amount", 4))
    return [f"rgbashift=rh=-{amount}:bh={amount}:rv={amount // 2}:bv=-{amount // 2}"], [], []


def _f_sketch(p):
    """Pencil/ink line art using edgedetect filter."""
    mode = p.get("mode", "pencil")
    if mode == "color":
        return ["edgedetect=low=0.1:high=0.3:mode=colormix"], [], []
    elif mode == "ink":
        return ["edgedetect=low=0.08:high=0.4,negate"], [], []
    else:  # pencil
        return ["edgedetect=low=0.1:high=0.3,negate"], [], []


def _f_glow(p):
    """Bloom/soft glow using split → gblur → screen blend (filter_complex)."""
    radius = float(p.get("radius", 30))
    strength = float(p.get("strength", 0.4))
    strength = max(0.1, min(0.8, strength))
    fc = (
        f"split[a][b];"
        f"[b]gblur=sigma={radius}[b];"
        f"[a][b]blend=all_mode=screen:all_opacity={strength}"
    )
    return [], [], [], fc


def _f_ghost_trail(p):
    """Temporal trailing/afterimage using lagfun filter."""
    decay = float(p.get("decay", 0.97))
    decay = max(0.9, min(0.995, decay))
    return [f"lagfun=decay={decay}"], [], []


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
    return [filt], [], []


def _f_tilt_shift(p):
    """Real tilt-shift miniature effect with selective blur (filter_complex)."""
    focus = float(p.get("focus_position", 0.5))
    blur_amount = float(p.get("blur_amount", 8))
    # Sharp band is centered on focus, 30% of frame height
    low = max(0, focus - 0.15)
    high = min(1, focus + 0.15)
    fc = (
        f"split[a][b];"
        f"[b]gblur=sigma={blur_amount}[b];"
        f"[a][b]blend=all_expr='if(between(Y/H\\,{low}\\,{high})\\,A\\,B)'"
    )
    return [], [], [], fc


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
    return [filt], [], []


def _f_halftone(p):
    """Print halftone dot pattern using geq."""
    dot_size = float(p.get("dot_size", 0.3))
    freq = max(0.1, min(1.0, dot_size))
    return [
        f"format=gray,geq='if(gt(lum(X\\,Y)\\,128+127*sin(X*{freq})*sin(Y*{freq}))\\,255\\,0)'"
    ], [], []


def _f_neon_enhanced(p):
    """Neon glow with real edge detection + high-saturation blend (filter_complex)."""
    intensity = p.get("intensity", "medium")
    opacity = {"subtle": 0.3, "medium": 0.5, "strong": 0.7}.get(intensity, 0.5)
    fc = (
        f"split[a][b];"
        f"[b]edgedetect=low=0.08:high=0.3:mode=colormix,"
        f"eq=saturation=3:brightness=0.1[b];"
        f"[a][b]blend=all_mode=screen:all_opacity={opacity}"
    )
    return [], [], [], fc


def _f_thermal_enhanced(p):
    """Real thermal/heat vision using pseudocolor."""
    return [
        "pseudocolor="
        "c0='if(between(val,0,85),255,if(between(val,85,170),255,if(between(val,170,255),255,0)))':"
        "c1='if(between(val,0,85),0,if(between(val,85,170),val*3-255,if(between(val,170,255),255,0)))':"
        "c2='if(between(val,0,85),0,if(between(val,85,170),0,if(between(val,170,255),val*3-510,0)))'"
    ], [], []


def _f_comic_book_enhanced(p):
    """Comic book with real edge outline + posterization (filter_complex)."""
    style = p.get("style", "classic")
    levels = {"classic": 6, "manga": 2, "pop_art": 4}.get(style, 6)
    step = max(1, 256 // levels)
    lut_expr = f"trunc(val/{step})*{step}"
    fc = (
        f"split[a][b];"
        f"[b]edgedetect=low=0.1:high=0.4,negate[b];"
        f"[a]lutrgb=r='{lut_expr}':g='{lut_expr}':b='{lut_expr}',"
        f"eq=saturation=1.5:contrast=1.3[a];"
        f"[a][b]blend=all_mode=multiply"
    )
    return [], [], [], fc


def _f_waveform(p):
    """Audio waveform visualization using showwaves + overlay (filter_complex)."""
    mode = p.get("mode", "cline")
    height = int(p.get("height", 200))
    color = sanitize_text_param(str(p.get("color", "white")))
    position = p.get("position", "bottom")
    opacity = float(p.get("opacity", 0.8))

    # Position mapping: y-coordinate expression
    pos_map = {
        "bottom": f"main_h-{height}",
        "center": f"(main_h-{height})/2",
        "top": "0",
    }
    y_expr = pos_map.get(position, pos_map["bottom"])

    # Build filter_complex graph:
    # Generate waveform at 1920px wide, overlay handles positioning
    # [0:a] → showwaves → [wave]
    # [0:v][wave] → overlay → output
    fc = (
        f"[0:a]showwaves=s=1920x{height}:mode={mode}:colors={color},"
        f"format=yuva420p,colorchannelmixer=aa={opacity}[wave];"
        f"[0:v][wave]overlay=0:{y_expr}:shortest=1"
    )
    return [], [], [], fc


def _f_chromakey(p):
    """Remove a solid-color background (chroma key / green screen).

    Uses ffmpeg's colorkey filter to make the specified color transparent,
    then overlays the result onto a background color or leaves alpha.

    Parameters:
        color: hex color to key out (default "0x00FF00" = green)
        similarity: how close to the key color counts (0.0-1.0, default 0.3)
        blend: edge blending amount (0.0-1.0, default 0.1)
        background: replacement background color (default "black").
                     Set to "transparent" to output with alpha channel.
    """
    color = p.get("color", "0x00FF00")
    similarity = float(p.get("similarity", 0.3))
    blend = float(p.get("blend", 0.1))
    background = p.get("background", "black")

    if background == "transparent":
        # Output with alpha: just apply colorkey
        vf = [f"colorkey=color={color}:similarity={similarity}:blend={blend}"]
    else:
        # Replace keyed color with a solid background
        # Split → colorkey on one branch, color source on other, overlay
        fc = (
            f"[0:v]split[ckv][bg];"
            f"[ckv]colorkey=color={color}:similarity={similarity}:blend={blend}[keyed];"
            f"[bg]drawbox=c={background}:t=fill[solid];"
            f"[solid][keyed]overlay=format=auto"
        )
        return [], [], [], fc

    return vf, [], []


def _f_blend(p):
    """Blend/double exposure: blend two video inputs together."""
    mode = str(p.get("mode", "addition")).lower()
    opacity = float(p.get("opacity", 0.5))

    # blend modes: addition, multiply, screen, overlay, darken, lighten, etc.
    fc = f"[0:v][1:v]blend=all_mode={mode}:all_opacity={opacity}"
    return [], [], [], fc


def _f_color_match(p):
    """Match color/brightness of video to a reference using histogram equalization."""
    vf = "histeq=strength=0.5:intensity=0.5"
    return [vf], [], []


def _f_datamosh(p):
    """Datamosh/glitch art via motion vector visualization."""
    mode = p.get("mode", "pf+bf+bb")
    # codecview needs motion vectors exported from decoder
    vf = f"codecview=mv={mode}"
    return [vf], [], [], "", ["-flags2", "+export_mvs"]


def _f_mask_blur(p):
    """Blur a rectangular region of the video (privacy/censor)."""
    x = int(p.get("x", 100))
    y = int(p.get("y", 100))
    w = int(p.get("w", 200))
    h = int(p.get("h", 200))
    strength = int(p.get("strength", 20))
    # Uses filter_complex: split, crop+blur the region, overlay back
    fc = (
        f"[0:v]split[base][blur];"
        f"[blur]crop={w}:{h}:{x}:{y},boxblur={strength}[blurred];"
        f"[base][blurred]overlay={x}:{y}:shortest=1"
    )
    return [], [], [], fc


def _f_lut_apply(p):
    """Apply a color LUT with intensity blending."""
    from ...core.sanitize import sanitize_text_param, validate_path, ALLOWED_LUT_EXTENSIONS
    from pathlib import Path

    path = sanitize_text_param(str(p.get("path", "lut.cube")))
    intensity = float(p.get("intensity", 1.0))

    # Auto-resolve short names: if path has no separator, search luts/ folder
    if "/" not in path and "\\" not in path:
        # skills/handlers/visual.py -> skills/handlers -> skills -> project root
        luts_dir = Path(__file__).resolve().parent.parent.parent / "luts"
        # Try exact match first, then fuzzy
        for ext in (".cube", ".3dl", ""):
            candidate = luts_dir / f"{path}{ext}"
            if candidate.is_file():
                path = str(candidate)
                break
        else:
            # Try case-insensitive partial match
            if luts_dir.is_dir():
                for f in luts_dir.iterdir():
                    if f.suffix.lower() in (".cube", ".3dl") and path.lower() in f.stem.lower():
                        path = str(f)
                        break

    # Validate the LUT file path for security (prevent traversal, enforce extensions)
    validate_path(path, ALLOWED_LUT_EXTENSIONS, must_exist=True)

    if intensity >= 1.0:
        # Full LUT, no blending needed
        vf = f"lut3d=file='{path}'"
        return [vf], [], []
    elif intensity <= 0.0:
        # No LUT
        return [], [], []
    else:
        # Blend original with LUT-graded using filter_complex
        inv = 1.0 - intensity
        fc = (
            f"[0:v]split[orig][lut];"
            f"[lut]lut3d=file='{path}'[graded];"
            f"[orig][graded]blend=all_mode=normal:all_opacity={intensity}"
        )
        return [], [], [], fc

# ── Keying & Masking skill handlers ─────────────────────────────── #


def _f_colorkey(p):
    """Key out an arbitrary color (general-purpose version of chromakey)."""
    color = sanitize_text_param(str(p.get("color", "0x00FF00")))
    similarity = float(p.get("similarity", 0.3))
    blend = float(p.get("blend", 0.1))
    background = sanitize_text_param(str(p.get("background", "black")))

    if background == "transparent":
        vf = [f"colorkey=color={color}:similarity={similarity}:blend={blend}"]
        return vf, [], []

    fc = (
        f"[0:v]split[ckv][bg];"
        f"[ckv]colorkey=color={color}:similarity={similarity}:blend={blend}[keyed];"
        f"[bg]drawbox=c={background}:t=fill[solid];"
        f"[solid][keyed]overlay=format=auto"
    )
    return [], [], [], fc


def _f_lumakey(p):
    """Key out regions based on brightness (luma)."""
    threshold = float(p.get("threshold", 0.0))
    tolerance = float(p.get("tolerance", 0.1))
    softness = float(p.get("softness", 0.0))
    background = sanitize_text_param(str(p.get("background", "black")))

    lk = f"lumakey=threshold={threshold}:tolerance={tolerance}:softness={softness}"

    if background == "transparent":
        return [lk], [], []

    fc = (
        f"[0:v]split[lkv][bg];"
        f"[lkv]{lk}[keyed];"
        f"[bg]drawbox=c={background}:t=fill[solid];"
        f"[solid][keyed]overlay=format=auto"
    )
    return [], [], [], fc


def _f_colorhold(p):
    """Keep only a selected color, desaturate everything else (sin-city effect)."""
    color = sanitize_text_param(str(p.get("color", "0xFF0000")))
    similarity = float(p.get("similarity", 0.3))
    blend = float(p.get("blend", 0.1))
    return [f"colorhold=color={color}:similarity={similarity}:blend={blend}"], [], []


def _f_despill(p):
    """Remove green/blue color spill from chroma-keyed footage."""
    spill_type = p.get("type", "green")
    type_val = 1 if str(spill_type).lower() in ("blue", "1") else 0
    mix = float(p.get("mix", 0.5))
    expand = float(p.get("expand", 0.0))
    brightness = float(p.get("brightness", 0.0))
    return [f"despill=type={type_val}:mix={mix}:expand={expand}:brightness={brightness}"], [], []


def _f_remove_background(p):
    """Remove background using rembg (optional dependency)."""
    try:
        from rembg import remove as _rembg_remove  # noqa: F401
    except ImportError:
        import logging
        logging.getLogger("ffmpega").error(
            "rembg is not installed. Install with: "
            "pip install 'comfyui-ffmpega[masking]'"
        )
        return [], [], []

    import logging
    logging.getLogger("ffmpega").info(
        "remove_background skill requested (model=%s) — "
        "full frame pipeline coming in a follow-up PR",
        p.get("model", "silueta"),
    )
    return [], [], []

