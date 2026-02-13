"""FFMPEGA Spatial skill handlers.

Auto-generated from composer.py — do not edit directly.
"""

try:
    from ...core.sanitize import sanitize_text_param
except ImportError:
    try:
        from core.sanitize import sanitize_text_param
    except ImportError:
        def sanitize_text_param(s): return s

def _f_resize(p):
    return [f"scale={p.get('width', -1)}:{p.get('height', -1)}"], [], []


def _f_crop(p):
    w = p.get("width", "iw")
    h = p.get("height", "ih")
    x = p.get("x", "(in_w-out_w)/2")
    y = p.get("y", "(in_h-out_h)/2")
    return [f"crop={w}:{h}:{x}:{y}"], [], []


def _f_pad(p):
    w = p.get("width", "iw")
    h = p.get("height", "ih")
    x = p.get("x", "(ow-iw)/2")
    y = p.get("y", "(oh-ih)/2")
    color = sanitize_text_param(str(p.get("color", "black")))
    return [f"pad={w}:{h}:{x}:{y}:{color}"], [], []


def _f_rotate(p):
    angle = p.get("angle", 0)
    if angle == 90:
        return ["transpose=1"], [], []
    elif angle == -90 or angle == 270:
        return ["transpose=2"], [], []
    elif angle == 180:
        return ["transpose=1,transpose=1"], [], []
    else:
        radians = angle * 3.14159 / 180
        return [f"rotate={radians}"], [], []


def _f_flip(p):
    d = p.get("direction", "horizontal")
    return ["hflip" if d == "horizontal" else "vflip"], [], []


def _f_zoom(p):
    factor = float(p.get("factor", 1.5))
    x = p.get("x", "center")
    y = p.get("y", "center")
    # Static zoom via crop then scale back to original dimensions
    crop_w = f"iw/{factor}"
    crop_h = f"ih/{factor}"
    if x == "center":
        crop_x = f"(iw-iw/{factor})/2"
    else:
        crop_x = f"iw*{float(x)}-iw/{factor}/2"
    if y == "center":
        crop_y = f"(ih-ih/{factor})/2"
    else:
        crop_y = f"ih*{float(y)}-ih/{factor}/2"
    return [f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale=iw*{factor}:ih*{factor}"], [], []


def _f_ken_burns(p):
    direction = p.get("direction", "zoom_in")
    amount = float(p.get("amount", 0.3))
    dur = float(p.get("duration", 5))
    # Use FFmpeg's native zoompan with d=1 (one output frame per input frame)
    # so it works correctly for video input.  zoompan internally crops a
    # region of iw/z × ih/z at position (x, y) and scales it to the output
    # size — exactly the Ken Burns zoom+pan effect.
    # NOTE: zoompan requires an explicit output size (s=) because it defaults
    # to hd720; we normalise to even dims first and pass the size through.
    if direction == "zoom_in":
        # z ramps from 1 → (1+amount) over dur seconds using pzoom
        rate = amount / dur / 25  # per-frame increment at ~25fps
        return [
            f"scale='trunc(iw/2)*2':'trunc(ih/2)*2',"
            f"zoompan=z='min(max(zoom\\,pzoom)+{rate:.6f}\\,{1+amount})':"
            f"d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=hd720:fps=30"
        ], [], []
    elif direction == "zoom_out":
        # z starts at (1+amount) and holds (zoompan starts zoomed)
        # then we reverse by starting high and decreasing
        rate = amount / dur / 25
        return [
            f"scale='trunc(iw/2)*2':'trunc(ih/2)*2',"
            f"zoompan=z='max(if(eq(on\\,1)\\,{1+amount}\\,zoom)-{rate:.6f}\\,1)':"
            f"d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=hd720:fps=30"
        ], [], []
    elif direction == "pan_right":
        zf = 1 + amount
        return [
            f"scale='trunc(iw/2)*2':'trunc(ih/2)*2',"
            f"zoompan=z='{zf}':"
            f"d=1:x='min(on*{zf-1:.4f}*iw/{dur}/25\\,(iw-iw/{zf}))':y='ih/2-(ih/zoom/2)':s=hd720:fps=30"
        ], [], []
    elif direction == "pan_left":
        zf = 1 + amount
        return [
            f"scale='trunc(iw/2)*2':'trunc(ih/2)*2',"
            f"zoompan=z='{zf}':"
            f"d=1:x='max((iw-iw/{zf})-on*{zf-1:.4f}*iw/{dur}/25\\,0)':y='ih/2-(ih/zoom/2)':s=hd720:fps=30"
        ], [], []
    else:
        # Default to zoom_in
        rate = amount / dur / 25
        return [
            f"scale='trunc(iw/2)*2':'trunc(ih/2)*2',"
            f"zoompan=z='min(max(zoom\\,pzoom)+{rate:.6f}\\,{1+amount})':"
            f"d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=hd720:fps=30"
        ], [], []


def _f_mirror(p):
    mode = p.get("mode", "horizontal")
    if mode == "horizontal":
        return ["crop=iw/2:ih:0:0,split[l][r];[r]hflip[rf];[l][rf]hstack"], [], []
    elif mode == "vertical":
        return ["crop=iw:ih/2:0:0,split[t][b];[b]vflip[bf];[t][bf]vstack"], [], []
    elif mode == "quad":
        return [
            "crop=iw/2:ih/2:0:0,split=4[a][b][c][d];"
            "[b]hflip[bh];[c]vflip[cv];[d]hflip,vflip[dh];"
            "[a][bh]hstack[top];[cv][dh]hstack[bot];"
            "[top][bot]vstack"
        ], [], []
    else:
        return ["hflip"], [], []


def _f_caption_space(p):
    position = p.get("position", "bottom")
    height = int(p.get("height", 200))
    color = sanitize_text_param(str(p.get("color", "black")))
    if position == "top":
        return [f"pad=iw:ih+{height}:0:{height}:{color}"], [], []
    else:
        return [f"pad=iw:ih+{height}:0:0:{color}"], [], []


def _f_lens_correction(p):
    k1 = float(p.get("k1", -0.2))
    k2 = float(p.get("k2", 0.0))
    return [f"lenscorrection=k1={k1}:k2={k2}:i=bilinear"], [], []


def _f_deinterlace(p):
    mode = p.get("mode", "send_frame")
    mode_map = {"send_frame": "0", "send_field": "1"}
    return [f"yadif=mode={mode_map.get(mode, '0')}"], [], []


def _f_frame_interpolation(p):
    fps = int(p.get("fps", 60))
    mode = p.get("mode", "mci")
    return [f"minterpolate=fps={fps}:mi_mode={mode}"], [], []


def _f_scroll(p):
    direction = p.get("direction", "up")
    speed = float(p.get("speed", 0.05))
    d = {
        "up": f"scroll=vertical=-{speed}",
        "down": f"scroll=vertical={speed}",
        "left": f"scroll=horizontal=-{speed}",
        "right": f"scroll=horizontal={speed}",
    }
    return [d.get(direction, d["up"])], [], []


def _f_aspect(p):
    ratio = p.get("ratio", "16:9")
    mode = p.get("mode", "pad")
    color = sanitize_text_param(str(p.get("color", "black")))
    # Parse ratio string like "16:9" or "2.35:1"
    parts = ratio.split(":")
    if len(parts) == 2:
        r = float(parts[0]) / float(parts[1])
    else:
        r = float(ratio)
    if mode == "crop":
        return [f"crop=if(gt(iw/ih\\,{r})\\,ih*{r}\\,iw):if(gt(iw/ih\\,{r})\\,ih\\,iw/{r})"], [], []
    elif mode == "stretch":
        return [f"scale=if(gt(iw/ih\\,{r})\\,iw\\,ih*{r}):if(gt(iw/ih\\,{r})\\,iw/{r}\\,ih)"], [], []
    else:  # pad
        return [f"pad=if(gt(iw/ih\\,{r})\\,iw\\,ih*{r}):if(gt(iw/ih\\,{r})\\,iw/{r}\\,ih):(ow-iw)/2:(oh-ih)/2:{color}"], [], []


def _f_perspective(p):
    preset = p.get("preset", "tilt_forward")
    strength = float(p.get("strength", 0.3))
    # s is the pixel offset proportional to strength (max ~25% of dimension)
    presets = {
        "tilt_forward":  "x0=0+{s}:y0=0:x1=W-{s}:y1=0:x2=0:y2=H:x3=W:y3=H",
        "tilt_back":     "x0=0:y0=0:x1=W:y1=0:x2=0+{s}:y2=H:x3=W-{s}:y3=H",
        "lean_left":     "x0=0:y0=0+{s}:x1=W:y1=0:x2=0:y2=H:x3=W:y3=H-{s}",
        "lean_right":    "x0=0:y0=0:x1=W:y1=0+{s}:x2=0:y2=H-{s}:x3=W:y3=H",
    }
    tmpl = presets.get(preset, presets["tilt_forward"])
    # Convert strength 0-1 to pixel expression: strength * W/4 (max 25% offset)
    s = f"W*{strength}/4"
    expr = tmpl.replace("{s}", s)
    return [f"perspective={expr}:interpolation=linear:sense=source"], [], []


def _f_fill_borders(p):
    left = int(p.get("left", 10))
    right = int(p.get("right", 10))
    top = int(p.get("top", 10))
    bottom = int(p.get("bottom", 10))
    mode = p.get("mode", "smear")
    mode_map = {"smear": 0, "mirror": 1, "fixed": 2, "reflect": 3, "wrap": 4, "fade": 5}
    m = mode_map.get(mode, 0)
    return [f"fillborders=left={left}:right={right}:top={top}:bottom={bottom}:mode={m}"], [], []


def _f_deshake(p):
    rx = int(p.get("rx", 16))
    ry = int(p.get("ry", 16))
    edge = p.get("edge", "mirror")
    edge_map = {"blank": 0, "original": 1, "clamp": 2, "mirror": 3}
    e = edge_map.get(edge, 3)
    return [f"deshake=rx={rx}:ry={ry}:edge={e}"], [], []


def _f_frame_blend(p):
    """Temporal frame blending / motion blur using tmix."""
    frames = int(p.get("frames", 5))
    frames = max(2, min(10, frames))
    weights = " ".join(["1"] * frames)
    return [f"tmix=frames={frames}:weights='{weights}'"], [], []


