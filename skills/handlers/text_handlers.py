"""FFMPEGA Text skill handlers.

Handles all drawtext-based skills: text overlay, animated text,
scrolling text, ticker, lower third, typewriter, bounce, fade, karaoke, etc.
"""

try:
    from ...core.sanitize import (
        sanitize_text_param,
    )
except ImportError:
    from core.sanitize import (
        sanitize_text_param,
    )


def _f_add_text(p):
    text = sanitize_text_param(str(p.get("text", "")))
    size = p.get("size", 48)
    color = sanitize_text_param(str(p.get("color", "white")))
    font = sanitize_text_param(str(p.get("font", "Sans")))

    # Validate font path if it looks like a file path
    if "/" in font or "\\" in font or font.endswith((".ttf", ".otf", ".woff")):
        try:
            from ...core.sanitize import validate_path, ALLOWED_FONT_EXTENSIONS
        except ImportError:
            from core.sanitize import validate_path, ALLOWED_FONT_EXTENSIONS
        validate_path(font, ALLOWED_FONT_EXTENSIONS, must_exist=True)

    border = p.get("border", True)
    position = p.get("position", "center")

    pos_map = {
        "center": "x=(w-text_w)/2:y=(h-text_h)/2",
        "top": "x=(w-text_w)/2:y=text_h",
        "bottom": "x=(w-text_w)/2:y=h-text_h*2",
        "top_left": "x=text_h:y=text_h",
        "top_right": "x=w-text_w-text_h:y=text_h",
        "bottom_left": "x=text_h:y=h-text_h*2",
        "bottom_right": "x=w-text_w-text_h:y=h-text_h*2",
    }
    xy = pos_map.get(position, pos_map["center"])
    border_style = ":borderw=3:bordercolor=black" if border else ""

    drawtext = (
        f"drawtext=text='{text}':fontsize={size}"
        f":fontcolor={color}:font='{font}'"
        f":{xy}{border_style}"
    )
    return [drawtext], [], []


def _f_text_overlay(p):
    """Draw text on the video using ffmpeg's drawtext filter.

    Parameters (matching skill definition):
        text:       Text to display (required)
        position:   Position: center, top, bottom, top_left, top_right,
                    bottom_left, bottom_right (default "center")
        color:      Text color name or hex (default "white")
        size:       Font size in pixels (default 48)
        font:       Font family (default "sans")
        border:     Add black border/shadow (default True)
        blink:      Blink/flash interval in seconds (0 = no blink, default 0)
        start:      Start time in seconds (default 0)
        duration:   Display duration in seconds (0 = entire video, default 0)
        background: Background box color (default "" = none)

    Legacy parameters (also accepted):
        fontcolor, fontsize, preset, borderw, bordercolor, x, y
    """
    import json as _json

    # --- Resolve text from connected text inputs ---
    text_inputs = p.get("_text_inputs", [])
    resolved_text = None
    for raw_text in text_inputs:
        try:
            meta = _json.loads(raw_text)
            if isinstance(meta, dict) and meta.get("mode") in ("overlay", "watermark", "title_card", "auto"):
                resolved_text = meta.get("text", "")
                # Text node settings override LLM defaults
                if meta.get("font_size"):
                    p["size"] = meta["font_size"]
                    p["fontsize"] = meta["font_size"]
                if meta.get("font_color"):
                    p["color"] = meta["font_color"]
                    p["fontcolor"] = meta["font_color"]
                if meta.get("position") and meta["position"] != "auto":
                    p["position"] = meta["position"]
                if meta.get("start_time", 0) > 0:
                    p["start"] = meta["start_time"]
                if meta.get("end_time", -1) > 0:
                    duration = meta["end_time"] - meta.get("start_time", 0)
                    if duration > 0:
                        p["duration"] = duration
                break
        except (_json.JSONDecodeError, TypeError):
            # Plain string — use as overlay text
            resolved_text = raw_text
            break

    text = sanitize_text_param(str(resolved_text or p.get("text", "Hello")))
    font = sanitize_text_param(str(p.get("font", "sans")))

    # Color: prefer 'color' (skill definition), fall back to 'fontcolor' (legacy)
    color = p.get("color") or p.get("font_color") or p.get("fontcolor") or "white"
    color = sanitize_text_param(str(color))

    # Size: prefer 'size' (skill definition), fall back to 'fontsize' (legacy)
    fontsize = int(p.get("size", p.get("fontsize", 48)))

    # Border
    border = p.get("border", True)
    if isinstance(border, str):
        border = border.lower() not in ("false", "0", "no", "off")
    borderw = int(p.get("borderw", 2 if border else 0))
    bordercolor = sanitize_text_param(str(p.get("bordercolor", "black")))

    bg = sanitize_text_param(str(p.get("background", "")))
    start = float(p.get("start", 0))
    duration = float(p.get("duration", 0))
    blink = float(p.get("blink", 0))

    # Margin for edge positions
    margin_x = int(p.get("margin_x", 24))
    margin_y = int(p.get("margin_y", 24))

    # Position mapping — "position" param (skill definition) takes priority,
    # then fall back to "preset" (legacy) or explicit x/y.
    position = p.get("position", "").lower()
    preset = str(p.get("preset", "")).lower()

    _POSITION_MAP = {
        "center":       ("(w-text_w)/2", "(h-text_h)/2"),
        "top":          ("(w-text_w)/2", str(margin_y)),
        "bottom":       ("(w-text_w)/2", f"h-text_h-{margin_y}"),
        "top_left":     (str(margin_x), str(margin_y)),
        "top_right":    (f"w-text_w-{margin_x}", str(margin_y)),
        "bottom_left":  (str(margin_x), f"h-text_h-{margin_y}"),
        "bottom_right": (f"w-text_w-{margin_x}", f"h-text_h-{margin_y}"),
    }
    _PRESET_MAP = {
        "title":       "center",
        "subtitle":    "bottom",
        "lower_third": "bottom_left",
        "caption":     "bottom",
        "top":         "top",
    }

    # Resolve position
    if position in _POSITION_MAP:
        x_pos, y_pos = _POSITION_MAP[position]
    elif preset in _PRESET_MAP:
        x_pos, y_pos = _POSITION_MAP[_PRESET_MAP[preset]]
    else:
        x_pos, y_pos = _POSITION_MAP["center"]

    # Allow explicit x/y override
    x_pos = sanitize_text_param(str(p.get("x", x_pos)))
    y_pos = sanitize_text_param(str(p.get("y", y_pos)))

    # Build drawtext filter
    dt = (
        f"drawtext=text='{text}':"
        f"font='{font}':"
        f"fontsize={fontsize}:"
        f"fontcolor={color}:"
        f"borderw={borderw}:"
        f"bordercolor={bordercolor}:"
        f"x={x_pos}:y={y_pos}"
    )

    # Background box
    if bg:
        dt += f":box=1:boxcolor={bg}:boxborderw=8"

    # Blink/flash effect — toggle visibility with enable expression
    if blink > 0:
        # Use lt(mod(t,interval),interval/2) to create on/off flashing
        half = blink / 2
        dt += f":enable='lt(mod(t\\,{blink})\\,{half})'"
    elif p.get("enable"):
        # LLM may pass a raw ffmpeg enable expression directly
        enable_expr = str(p["enable"]).strip("'\"")
        # Escape commas for ffmpeg filter graph
        enable_expr = enable_expr.replace(",", "\\,")
        dt += f":enable='{enable_expr}'"
    else:
        # Time-based enable/disable (no blink)
        if duration > 0:
            end = start + duration
            dt += f":enable='between(t,{start},{end})'"
        elif start > 0:
            dt += f":enable='gte(t,{start})'"

    return [dt], [], []


def _f_countdown(p):
    """Animated countdown timer overlay."""
    fontsize = int(p.get("fontsize", 96))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))
    x_pos = sanitize_text_param(str(p.get("x", "(w-text_w)/2")))
    y_pos = sanitize_text_param(str(p.get("y", "(h-text_h)/2")))
    start = int(p.get("start_from", 10))

    dt = (
        f"drawtext=text='%{{eif\\:{start}-t\\:d}}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"x={x_pos}:y={y_pos}:"
        f"borderw=3:bordercolor=black:"
        f"enable='lte(t,{start})'"
    )
    return [dt], [], []


def _f_animated_text(p):
    """Drawtext with built-in animation presets."""
    text = sanitize_text_param(str(p.get("text", "Hello")))
    animation = str(p.get("animation", "fade_in")).lower()
    fontsize = int(p.get("fontsize", 64))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))
    start = float(p.get("start", 0))
    duration = float(p.get("duration", 3))
    end = start + duration

    base = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"borderw=2:bordercolor=black:"
        f"enable='between(t,{start},{end})':"
        f"x=(w-text_w)/2"
    )

    if animation == "fade_in":
        alpha_expr = f"alpha='if(lt(t,{start}+1),(t-{start}),1)'"
        base += f":y=(h-text_h)/2:{alpha_expr}"
    elif animation == "slide_up":
        y_expr = f"y='max(h-text_h-60-((t-{start})*100),0)'"
        base += f":{y_expr}"
    elif animation == "slide_down":
        y_expr = f"y='min((t-{start})*100,60)'"
        base += f":{y_expr}"
    elif animation == "typewriter":
        # Use text length truncation via enable
        base = (
            f"drawtext=text='{text}':"
            f"fontsize={fontsize}:"
            f"fontcolor={fontcolor}:"
            f"borderw=2:bordercolor=black:"
            f"enable='between(t,{start},{end})':"
            f"x=(w-text_w)/2:y=(h-text_h)/2"
        )
    else:  # default: centered static
        base += ":y=(h-text_h)/2"

    return [base], [], []


def _f_scrolling_text(p):
    """Vertical scrolling text (credits roll)."""
    text = sanitize_text_param(str(p.get("text", "Credits")))
    speed = int(p.get("speed", 60))
    fontsize = int(p.get("fontsize", 36))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))

    dt = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"borderw=2:bordercolor=black:"
        f"x=(w-text_w)/2:"
        f"y=h-t*{speed}"
    )
    return [dt], [], []


def _f_ticker(p):
    """Horizontal scrolling text (news ticker style)."""
    text = sanitize_text_param(str(p.get("text", "Breaking News")))
    speed = int(p.get("speed", 100))
    fontsize = int(p.get("fontsize", 32))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))
    y_pos = sanitize_text_param(str(p.get("y", "h-text_h-20")))
    bg = sanitize_text_param(str(p.get("background", "black@0.6")))

    dt = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"borderw=1:bordercolor=black:"
        f"x=w-t*{speed}:"
        f"y={y_pos}"
    )
    if bg:
        dt += f":box=1:boxcolor={bg}:boxborderw=8"

    return [dt], [], []


def _f_lower_third(p):
    """Animated lower third: name plate with background bar."""
    text = sanitize_text_param(str(p.get("text", "John Doe")))
    subtext = sanitize_text_param(str(p.get("subtext", "")))
    fontsize = int(p.get("fontsize", 36))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))
    bg = sanitize_text_param(str(p.get("background", "black@0.7")))
    start = float(p.get("start", 0))
    duration = float(p.get("duration", 5))
    end = start + duration

    # Main name text
    dt_main = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"x=40:y=h-text_h-60:"
        f"box=1:boxcolor={bg}:boxborderw=12:"
        f"borderw=1:bordercolor=black:"
        f"enable='between(t,{start},{end})'"
    )

    vf = [dt_main]

    # Optional subtext (title/role)
    if subtext:
        sub_fontsize = max(fontsize - 10, 16)
        dt_sub = (
            f"drawtext=text='{subtext}':"
            f"fontsize={sub_fontsize}:"
            f"fontcolor={fontcolor}@0.8:"
            f"x=40:y=h-{sub_fontsize}-25:"
            f"box=1:boxcolor={bg}:boxborderw=8:"
            f"enable='between(t,{start},{end})'"
        )
        vf.append(dt_sub)

    return vf, [], []


def _f_typewriter_text(p):
    """Character-by-character typewriter text reveal using progressive prefixes.

    Creates one drawtext per prefix length — each shows progressively more
    characters and is enabled only during its time window.  This avoids the
    per-character positioning issues and keeps the text properly aligned.
    """
    text = sanitize_text_param(str(p.get("text", "Hello World")))
    fontsize = int(p.get("size", p.get("fontsize", 48)))
    fontcolor = p.get("color") or p.get("font_color") or p.get("fontcolor") or "white"
    fontcolor = sanitize_text_param(str(fontcolor))
    speed = float(p.get("speed", 5))  # chars per second
    start = float(p.get("start", 0))
    font = sanitize_text_param(str(p.get("font", "sans")))
    borderw = int(p.get("borderw", 2))
    bordercolor = sanitize_text_param(str(p.get("bordercolor", "black")))

    # Position (same logic as text_overlay)
    margin_x, margin_y = 24, 24
    position = p.get("position", "center").lower()
    _POS = {
        "center":       ("(w-text_w)/2", "(h-text_h)/2"),
        "top":          ("(w-text_w)/2", str(margin_y)),
        "bottom":       ("(w-text_w)/2", f"h-text_h-{margin_y}"),
        "top_left":     (str(margin_x), str(margin_y)),
        "top_right":    (f"w-text_w-{margin_x}", str(margin_y)),
        "bottom_left":  (str(margin_x), f"h-text_h-{margin_y}"),
        "bottom_right": (f"w-text_w-{margin_x}", f"h-text_h-{margin_y}"),
    }
    x_pos, y_pos = _POS.get(position, _POS["center"])
    x_pos = sanitize_text_param(str(p.get("x", x_pos)))
    y_pos = sanitize_text_param(str(p.get("y", y_pos)))

    # Build progressive prefix drawtexts.
    # Each prefix is shown during its time window: [char_start, next_char_start).
    # The final complete text stays on screen indefinitely.
    filters = []
    chars = list(text)
    total = len(chars)

    if total == 0:
        return [f"drawtext=text='':fontsize={fontsize}:fontcolor={fontcolor}:x={x_pos}:y={y_pos}"], [], []

    for n in range(1, total + 1):
        prefix = sanitize_text_param(text[:n])
        t_start = start + (n - 1) / speed

        dt = (
            f"drawtext=text='{prefix}':"
            f"font='{font}':"
            f"fontsize={fontsize}:"
            f"fontcolor={fontcolor}:"
            f"borderw={borderw}:bordercolor={bordercolor}:"
            f"x={x_pos}:y={y_pos}"
        )

        if n < total:
            # Show this prefix only until the next character appears
            t_end = start + n / speed
            dt += f":enable='between(t\\,{t_start:.4f}\\,{t_end:.4f})'"
        else:
            # Final complete text — stays visible from its start time onward
            dt += f":enable='gte(t\\,{t_start:.4f})'"

        filters.append(dt)

    return filters, [], []


def _f_bounce_text(p):
    """Text with a bounce-in animation (drops in and settles)."""
    text = sanitize_text_param(str(p.get("text", "Hello")))
    fontsize = int(p.get("fontsize", 72))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))
    start = float(p.get("start", 0))
    duration = float(p.get("duration", 4))
    end = start + duration

    # Bounce uses abs(sin) for elastic ease
    y_expr = (
        f"y='(h-text_h)/2 - "
        f"abs(sin((t-{start})*5)*200*max(0,1-(t-{start})*2))'"
    )

    dt = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"borderw=3:bordercolor=black:"
        f"x=(w-text_w)/2:"
        f"{y_expr}:"
        f"enable='between(t,{start},{end})'"
    )
    return [dt], [], []


def _f_fade_text(p):
    """Text with smooth fade in and fade out."""
    text = sanitize_text_param(str(p.get("text", "Hello")))
    fontsize = int(p.get("fontsize", 64))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))
    start = float(p.get("start", 0))
    duration = float(p.get("duration", 4))
    fade_time = float(p.get("fade_time", 1.0))
    end = start + duration

    # Alpha expression: fade in for first fade_time, full, fade out for last fade_time
    alpha = (
        f"alpha='if(lt(t,{start}+{fade_time}),(t-{start})/{fade_time},"
        f"if(gt(t,{end}-{fade_time}),({end}-t)/{fade_time},1))'"
    )

    dt = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"borderw=2:bordercolor=black:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:"
        f"{alpha}:"
        f"enable='between(t,{start},{end})'"
    )
    return [dt], [], []


def _f_karaoke_text(p):
    """Color-fill text synced to time (karaoke highlight effect)."""
    text = sanitize_text_param(str(p.get("text", "Sing Along")))
    fontsize = int(p.get("fontsize", 48))
    base_color = sanitize_text_param(str(p.get("base_color", "gray")))
    fill_color = sanitize_text_param(str(p.get("fill_color", "yellow")))
    start = float(p.get("start", 0))
    duration = float(p.get("duration", 5))
    end = start + duration

    # Two drawtext layers: base (gray) underneath + fill (yellow) with progressive crop via x offset
    # The fill text is drawn starting from left, advancing rightward over the duration
    dt_base = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={base_color}:"
        f"borderw=2:bordercolor=black:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:"
        f"enable='between(t,{start},{end})'"
    )

    # Fill layer: use alpha expression that clips horizontally based on time progression
    # Progress goes from 0 to 1 over the duration, controls alpha via x position
    progress = f"(t-{start})/{duration}"
    dt_fill = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fill_color}:"
        f"borderw=2:bordercolor=black:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:"
        f"alpha='if(lt(x-((w-text_w)/2), text_w*{progress}), 1, 0)':"
        f"enable='between(t,{start},{end})'"
    )

    return [dt_base, dt_fill], [], []
