"""FFMPEGA Temporal skill handlers."""

try:
    from ..handler_contract import make_result
except ImportError:
    from skills.handler_contract import make_result

def _f_trim(p):
    input_opts = []
    output_opts = []

    start = p.get("start")
    end = p.get("end")
    duration = p.get("duration")

    try:
        # Try to parse start/end as floats for calculation (fast seek optimization)
        s_val = float(start) if start is not None else 0.0

        if start is not None:
            input_opts.extend(["-ss", str(start)])

        if end is not None:
            e_val = float(end)
            # Duration is end - start
            output_opts.extend(["-t", str(e_val - s_val)])
        elif duration is not None:
            # Duration is independent of start point
            output_opts.extend(["-t", str(duration)])

    except (ValueError, TypeError):
        # Fallback to slow seek if we can't do math (e.g. strings like "00:01:00")
        opts = []
        if start: opts.extend(["-ss", str(start)])
        if end: opts.extend(["-to", str(end)])
        if duration: opts.extend(["-t", str(duration)])
        return make_result(opts=opts)

    return make_result(opts=output_opts, io=input_opts)


def _f_speed(p):
    factor = float(p.get("factor", 1.0))

    vf = [f"setpts={1.0 / factor}*PTS"]
    af = []
    if 0.5 <= factor <= 2.0:
        af.append(f"atempo={factor}")
    elif factor < 0.5:
        remaining = factor
        while remaining < 0.5:
            af.append("atempo=0.5")
            remaining *= 2
        af.append(f"atempo={remaining}")
    else:
        remaining = factor
        while remaining > 2.0:
            af.append("atempo=2.0")
            remaining /= 2
        af.append(f"atempo={remaining}")

    return make_result(vf=vf, af=af)


def _f_reverse(p):
    return make_result(vf=["reverse"], af=["areverse"])


def _f_loop(p):
    count = int(p.get("count", 2))
    # -stream_loop N repeats the input N additional times
    return make_result(io=["-stream_loop", str(count)])


def _f_boomerang(p):
    loops = int(p.get("loops", 3))
    # Forward + reverse concatenated, then looped
    return make_result(vf=[
        f"split[fwd][rev];[rev]reverse[r];[fwd][r]concat=n=2:v=1:a=0,loop=loop={loops - 1}:size=32767"
    ])


def _f_jump_cut(p):
    """Remove silent/still segments to create a jump cut edit."""
    threshold = float(p.get("threshold", 0.03))

    # Select frames where scene change is above threshold (removes static parts)
    vf = f"select='gt(scene,{threshold})',setpts=N/FRAME_RATE/TB"
    # Audio must be removed since we're dropping frames (no audio counterpart for scene)
    return make_result(vf=[vf], opts=["-an"])


def _f_beat_sync(p):
    """Beat-synced cutting: keep frames at regular intervals."""
    threshold = float(p.get("threshold", 0.1))
    # Use select with frame interval to create rhythmic cuts
    # Higher threshold => fewer frames kept (more aggressive cut)
    interval = max(1, int(1.0 / max(threshold, 0.01)))
    vf = f"select='not(mod(n,{interval}))',setpts=N/FRAME_RATE/TB"
    return make_result(vf=[vf], opts=["-an"])
