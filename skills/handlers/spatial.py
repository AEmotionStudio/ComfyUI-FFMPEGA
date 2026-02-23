"""FFMPEGA Spatial skill handlers."""

try:
    from ...core.sanitize import sanitize_text_param
except ImportError:
    from core.sanitize import sanitize_text_param

try:
    from ..handler_contract import make_result
except ImportError:
    from skills.handler_contract import make_result

def _f_resize(p):
    w = str(p.get("width", -2))
    h = str(p.get("height", -2))
    # Use -2 instead of -1 for auto-calculated dimensions so ffmpeg
    # rounds to even numbers (libx264 requires divisible-by-2).
    if w == "-1":
        w = "-2"
    if h == "-1":
        h = "-2"
    w = sanitize_text_param(w)
    h = sanitize_text_param(h)
    return make_result(vf=[f"scale={w}:{h}"])


def _f_crop(p):
    w = sanitize_text_param(str(p.get("width", "iw")))
    h = sanitize_text_param(str(p.get("height", "ih")))
    x = sanitize_text_param(str(p.get("x", "(in_w-out_w)/2")))
    y = sanitize_text_param(str(p.get("y", "(in_h-out_h)/2")))
    return make_result(vf=[f"crop={w}:{h}:{x}:{y}"])


def _f_pad(p):
    w = sanitize_text_param(str(p.get("width", "iw")))
    h = sanitize_text_param(str(p.get("height", "ih")))
    x = sanitize_text_param(str(p.get("x", "(ow-iw)/2")))
    y = sanitize_text_param(str(p.get("y", "(oh-ih)/2")))
    color = sanitize_text_param(str(p.get("color", "black")))
    return make_result(vf=[f"pad={w}:{h}:{x}:{y}:{color}"])


def _f_rotate(p):
    angle = p.get("angle", 0)
    if angle == 90:
        return make_result(vf=["transpose=1"])
    elif angle == -90 or angle == 270:
        return make_result(vf=["transpose=2"])
    elif angle == 180:
        return make_result(vf=["transpose=1,transpose=1"])
    else:
        radians = angle * 3.14159 / 180
        return make_result(vf=[f"rotate={radians}"])


def _f_flip(p):
    d = p.get("direction", "horizontal")
    return make_result(vf=["hflip" if d == "horizontal" else "vflip"])


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
    return make_result(vf=[f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale=iw*{factor}:ih*{factor}"])


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
        return make_result(vf=[
            f"scale='trunc(iw/2)*2':'trunc(ih/2)*2',"
            f"zoompan=z='min(max(zoom\\,pzoom)+{rate:.6f}\\,{1+amount})':"
            f"d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=hd720:fps=30"
        ])
    elif direction == "zoom_out":
        rate = amount / dur / 25
        return make_result(vf=[
            f"scale='trunc(iw/2)*2':'trunc(ih/2)*2',"
            f"zoompan=z='max(if(eq(on\\,1)\\,{1+amount}\\,zoom)-{rate:.6f}\\,1)':"
            f"d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=hd720:fps=30"
        ])
    elif direction == "pan_right":
        zf = 1 + amount
        return make_result(vf=[
            f"scale='trunc(iw/2)*2':'trunc(ih/2)*2',"
            f"zoompan=z='{zf}':"
            f"d=1:x='min(on*{zf-1:.4f}*iw/{dur}/25\\,(iw-iw/{zf}))':y='ih/2-(ih/zoom/2)':s=hd720:fps=30"
        ])
    elif direction == "pan_left":
        zf = 1 + amount
        return make_result(vf=[
            f"scale='trunc(iw/2)*2':'trunc(ih/2)*2',"
            f"zoompan=z='{zf}':"
            f"d=1:x='max((iw-iw/{zf})-on*{zf-1:.4f}*iw/{dur}/25\\,0)':y='ih/2-(ih/zoom/2)':s=hd720:fps=30"
        ])
    else:
        # Default to zoom_in
        rate = amount / dur / 25
        return make_result(vf=[
            f"scale='trunc(iw/2)*2':'trunc(ih/2)*2',"
            f"zoompan=z='min(max(zoom\\,pzoom)+{rate:.6f}\\,{1+amount})':"
            f"d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=hd720:fps=30"
        ])


def _f_mirror(p):
    mode = p.get("mode", "horizontal")
    if mode == "horizontal":
        return make_result(vf=["crop=iw/2:ih:0:0,split[l][r];[r]hflip[rf];[l][rf]hstack"])
    elif mode == "vertical":
        return make_result(vf=["crop=iw:ih/2:0:0,split[t][b];[b]vflip[bf];[t][bf]vstack"])
    elif mode == "quad":
        return make_result(vf=[
            "crop=iw/2:ih/2:0:0,split=4[a][b][c][d];"
            "[b]hflip[bh];[c]vflip[cv];[d]hflip,vflip[dh];"
            "[a][bh]hstack[top];[cv][dh]hstack[bot];"
            "[top][bot]vstack"
        ])
    else:
        return make_result(vf=["hflip"])


def _f_caption_space(p):
    position = p.get("position", "bottom")
    height = int(p.get("height", 200))
    color = sanitize_text_param(str(p.get("color", "black")))
    if position == "top":
        return make_result(vf=[f"pad=iw:ih+{height}:0:{height}:{color}"])
    else:
        return make_result(vf=[f"pad=iw:ih+{height}:0:0:{color}"])


def _f_lens_correction(p):
    k1 = float(p.get("k1", -0.2))
    k2 = float(p.get("k2", 0.0))
    return make_result(vf=[f"lenscorrection=k1={k1}:k2={k2}:i=bilinear"])


def _f_deinterlace(p):
    mode = p.get("mode", "send_frame")
    mode_map = {"send_frame": "0", "send_field": "1"}
    return make_result(vf=[f"yadif=mode={mode_map.get(mode, '0')}"])


def _f_frame_interpolation(p):
    fps = int(p.get("fps", 60))
    mode = p.get("mode", "mci")
    return make_result(vf=[f"minterpolate=fps={fps}:mi_mode={mode}"])


def _f_scroll(p):
    direction = p.get("direction", "up")
    speed = float(p.get("speed", 0.05))
    d = {
        "up": f"scroll=vertical=-{speed}",
        "down": f"scroll=vertical={speed}",
        "left": f"scroll=horizontal=-{speed}",
        "right": f"scroll=horizontal={speed}",
    }
    return make_result(vf=[d.get(direction, d["up"])])


def _f_aspect(p):
    ratio = p.get("ratio", "16:9")
    mode = p.get("mode", "pad")
    color = sanitize_text_param(str(p.get("color", "black")))
    # Parse ratio string like "16:9" or "2.35:1"
    parts = ratio.split(":")
    if len(parts) == 2:
        denom = float(parts[1])
        if denom == 0:
            denom = 1.0  # Prevent ZeroDivisionError
        r = float(parts[0]) / denom
    else:
        r = float(ratio) or 1.0  # Guard against zero
    if mode == "crop":
        # Crop to target aspect ratio (no bars, loses content)
        return make_result(vf=[
            f"crop=2*trunc(if(gt(iw/ih\\,{r})\\,ih*{r}\\,iw)/2)"
            f":2*trunc(if(gt(iw/ih\\,{r})\\,ih\\,iw/{r})/2)"
        ])
    elif mode == "stretch":
        # Stretch to target aspect ratio (distorts content)
        return make_result(vf=[
            f"scale=2*trunc(if(gt(iw/ih\\,{r})\\,iw\\,ih*{r})/2)"
            f":2*trunc(if(gt(iw/ih\\,{r})\\,iw/{r}\\,ih)/2)"
        ])
    else:  # pad — overlay black bars on the original frame
        # Draw opaque bars on top/bottom (letterbox) or left/right
        # (pillarbox) WITHOUT cropping any content.  The video stays
        # at its original resolution — the bars are purely cosmetic.
        #
        # For a portrait 720×1280 with r=2.35:
        #   visible height = 720/2.35 ≈ 306 → bar_h ≈ 487 each side
        #
        # For a landscape 1920×1080 with r=2.35:
        #   visible height = 1920/2.35 ≈ 817 → bar_h ≈ 131 each side
        orig_w = p.get("_input_width")
        orig_h = p.get("_input_height")
        if orig_w and orig_h:
            orig_w, orig_h = int(orig_w), int(orig_h)
            src_ar = orig_w / orig_h
            if src_ar > r:
                # Source wider than target — pillarbox (bars on sides)
                visible_w = int(orig_h * r)
                bar_w = (orig_w - visible_w) // 2
                if bar_w > 0:
                    return make_result(vf=[
                        f"drawbox=x=0:y=0:w={bar_w}:h=ih:color={color}:t=fill,"
                        f"drawbox=x=iw-{bar_w}:y=0:w={bar_w}:h=ih:color={color}:t=fill"
                    ])
                return make_result()  # no bars needed
            else:
                # Source taller than target — letterbox (bars top/bottom)
                visible_h = int(orig_w / r)
                bar_h = (orig_h - visible_h) // 2
                if bar_h > 0:
                    return make_result(vf=[
                        f"drawbox=x=0:y=0:w=iw:h={bar_h}:color={color}:t=fill,"
                        f"drawbox=x=0:y=ih-{bar_h}:w=iw:h={bar_h}:color={color}:t=fill"
                    ])
                return make_result()  # no bars needed
        else:
            # Fallback when metadata not available — use expression-based
            # drawbox.  Use if(gt(...)) to only draw the needed pair:
            # letterbox (top/bottom) when source is taller, or
            # pillarbox (left/right) when source is wider.
            bar_h = f"(ih-iw/{r})/2"  # positive when taller than target
            bar_w = f"(iw-ih*{r})/2"  # positive when wider than target
            return make_result(vf=[
                f"drawbox=x=0:y=0:w=iw:h=if(gt(ih*{r}\\,iw)\\,{bar_h}\\,0):color={color}:t=fill,"
                f"drawbox=x=0:y=ih-if(gt(ih*{r}\\,iw)\\,{bar_h}\\,0):w=iw:h=if(gt(ih*{r}\\,iw)\\,{bar_h}\\,0):color={color}:t=fill,"
                f"drawbox=x=0:y=0:w=if(gt(iw\\,ih*{r})\\,{bar_w}\\,0):h=ih:color={color}:t=fill,"
                f"drawbox=x=iw-if(gt(iw\\,ih*{r})\\,{bar_w}\\,0):y=0:w=if(gt(iw\\,ih*{r})\\,{bar_w}\\,0):h=ih:color={color}:t=fill"
            ])


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
    return make_result(vf=[f"perspective={expr}:interpolation=linear:sense=source"])


def _f_fill_borders(p):
    left = int(p.get("left", 10))
    right = int(p.get("right", 10))
    top = int(p.get("top", 10))
    bottom = int(p.get("bottom", 10))
    mode = p.get("mode", "smear")
    mode_map = {"smear": 0, "mirror": 1, "fixed": 2, "reflect": 3, "wrap": 4, "fade": 5}
    m = mode_map.get(mode, 0)
    return make_result(vf=[f"fillborders=left={left}:right={right}:top={top}:bottom={bottom}:mode={m}"])


def _f_deshake(p):
    rx = int(p.get("rx", 16))
    ry = int(p.get("ry", 16))
    edge = p.get("edge", "mirror")
    edge_map = {"blank": 0, "original": 1, "clamp": 2, "mirror": 3}
    e = edge_map.get(edge, 3)
    return make_result(vf=[f"deshake=rx={rx}:ry={ry}:edge={e}"])


def _f_frame_blend(p):
    """Temporal frame blending / motion blur using tmix."""
    frames = int(p.get("frames", 5))
    frames = max(2, min(10, frames))
    weights = " ".join(["1"] * frames)
    return make_result(vf=[f"tmix=frames={frames}:weights='{weights}'"])
