"""FFMPEGA Presets skill handlers.

Auto-generated from composer.py — do not edit directly.
"""

def _f_fade_to_black(p):
    in_dur = float(p.get("in_duration", 1.0))
    out_dur = float(p.get("out_duration", 1.0))
    vf = []
    if in_dur > 0:
        vf.append(f"fade=t=in:st=0:d={in_dur}")
    if out_dur > 0:
        vf.append(f"fade=t=out:d={out_dur}")
    return vf, [], []


def _f_fade_to_white(p):
    in_dur = float(p.get("in_duration", 1.0))
    out_dur = float(p.get("out_duration", 1.0))
    vf = []
    if in_dur > 0:
        vf.append(f"fade=t=in:st=0:d={in_dur}:c=white")
    if out_dur > 0:
        vf.append(f"fade=t=out:d={out_dur}:c=white")
    return vf, [], []


def _f_flash(p):
    t = float(p.get("time", 0))
    duration = float(p.get("duration", 0.3))
    mid = t + duration / 2
    return [
        f"fade=t=out:st={t}:d={duration/2}:c=white,"
        f"fade=t=in:st={mid}:d={duration/2}:c=white"
    ], [], []


def _f_spin(p):
    speed = float(p.get("speed", 90.0))
    direction = p.get("direction", "cw")
    rad_per_sec = speed * 3.14159 / 180
    if direction == "ccw":
        rad_per_sec = -rad_per_sec
    return [f"rotate={rad_per_sec}*t:fillcolor=black"], [], []


def _f_shake(p):
    intensity = p.get("intensity", "medium")
    shake_map = {"light": 5, "medium": 12, "heavy": 25}
    amount = shake_map.get(intensity, 12)
    return [
        f"crop=iw-{amount*2}:ih-{amount*2}"
        f":{amount}+{amount}*random(1)"
        f":{amount}+{amount}*random(2),"
        f"scale=iw+{amount*2}:ih+{amount*2}"
    ], [], []


def _f_pulse(p):
    rate = float(p.get("rate", 1.0))
    amount = float(p.get("amount", 0.05))
    margin = int(amount * 100) + 10
    offset_expr = f"{margin}+{margin}*{amount}*10*sin(2*PI*{rate}*t)"
    return [
        f"pad=iw+{margin*2}:ih+{margin*2}:{margin}:{margin}:color=black",
        f"crop=iw-{margin*2}:ih-{margin*2}:'{offset_expr}':'{offset_expr}'",
    ], [], []


def _f_bounce(p):
    height = int(p.get("height", 30))
    speed = float(p.get("speed", 2.0))
    return [
        f"pad=iw:ih+{height*2}:(ow-iw)/2:{height}:black,"
        f"crop=iw:ih-{height*2}:0:{height}*abs(sin({speed}*PI*t))"
    ], [], []


def _f_drift(p):
    direction = p.get("direction", "right")
    amount = int(p.get("amount", 50))
    # Speed in px/sec: cover `amount` pixels over ~10s (configurable via amount)
    speed = max(1, amount // 10) if amount > 10 else amount
    d = {
        "right": (
            f"pad=iw+{amount}:ih:0:0:black,"
            f"crop=iw-{amount}:ih:min({speed}*t\\,{amount}):0"
        ),
        "left": (
            f"pad=iw+{amount}:ih:{amount}:0:black,"
            f"crop=iw-{amount}:ih:max({amount}-{speed}*t\\,0):0"
        ),
        "down": (
            f"pad=iw:ih+{amount}:0:0:black,"
            f"crop=iw:ih-{amount}:0:min({speed}*t\\,{amount})"
        ),
        "up": (
            f"pad=iw:ih+{amount}:0:{amount}:black,"
            f"crop=iw:ih-{amount}:0:max({amount}-{speed}*t\\,0)"
        ),
    }
    return [d.get(direction, d["right"])], [], []


def _f_iris_reveal(p):
    duration = float(p.get("duration", 2.0))
    return [
        f"geq="
        f"lum='if(lte(sqrt(pow(X-W/2,2)+pow(Y-H/2,2)),sqrt(pow(W/2,2)+pow(H/2,2))*min(T/{duration},1)),lum(X,Y),0)'"
        f":cb='if(lte(sqrt(pow(X-W/2,2)+pow(Y-H/2,2)),sqrt(pow(W/2,2)+pow(H/2,2))*min(T/{duration},1)),cb(X,Y),128)'"
        f":cr='if(lte(sqrt(pow(X-W/2,2)+pow(Y-H/2,2)),sqrt(pow(W/2,2)+pow(H/2,2))*min(T/{duration},1)),cr(X,Y),128)'"
    ], [], []


def _f_wipe(p):
    direction = p.get("direction", "left")
    duration = float(p.get("duration", 1.5))
    cond_map = {
        "left": f"lte(X,W*min(T/{duration},1))",
        "right": f"gte(X,W*(1-min(T/{duration},1)))",
        "down": f"lte(Y,H*min(T/{duration},1))",
        "up": f"gte(Y,H*(1-min(T/{duration},1)))",
    }
    cond = cond_map.get(direction, cond_map["left"])
    return [
        f"geq="
        f"lum='if({cond},lum(X,Y),0)'"
        f":cb='if({cond},cb(X,Y),128)'"
        f":cr='if({cond},cr(X,Y),128)'"
    ], [], []


def _f_slide_in(p):
    direction = p.get("direction", "left")
    duration = float(p.get("duration", 1.0))
    d = {
        "left": (
            f"pad=iw*2:ih:iw:0:black,"
            f"crop=iw/2:ih:iw/2*min(t/{duration}\\,1):0"
        ),
        "right": (
            f"pad=iw*2:ih:0:0:black,"
            f"crop=iw/2:ih:iw/2*(1-min(t/{duration}\\,1)):0"
        ),
        "down": (
            f"pad=iw:ih*2:0:ih:black,"
            f"crop=iw:ih/2:0:ih/2*min(t/{duration}\\,1)"
        ),
        "up": (
            f"pad=iw:ih*2:0:0:black,"
            f"crop=iw:ih/2:0:ih/2*(1-min(t/{duration}\\,1))"
        ),
    }
    return [d.get(direction, d["left"])], [], []


