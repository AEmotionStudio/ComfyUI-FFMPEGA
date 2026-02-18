"""FFMPEGA Audio skill handlers."""

try:
    from ..handler_contract import make_result
except ImportError:
    from skills.handler_contract import make_result

def _f_volume(p):
    return make_result(af=[f"volume={p.get('level', 1.0)}"])


def _f_normalize(p):
    return make_result(af=["loudnorm"])


def _f_fade_audio(p):
    fade_type = p.get("type", "in")
    start = p.get("start", 0)
    duration = p.get("duration", 1)
    return make_result(af=[f"afade=t={fade_type}:st={start}:d={duration}"])


def _f_remove_audio(p):
    return make_result(opts=["-an"])


def _f_extract_audio(p):
    return make_result(opts=["-vn", "-c:a", "copy"])


def _f_replace_audio(p):
    """Replace video's audio track with audio from second input."""
    # Return output options directly to avoid -map deduplication
    return make_result(opts=["-map", "0:v", "-map", "1:a", "-shortest"])


def _f_audio_crossfade(p):
    """Crossfade between two audio inputs."""
    duration = float(p.get("duration", 2.0))
    curve = p.get("curve", "tri")
    # acrossfade requires two audio inputs via filter_complex
    fc = f"[0:a][1:a]acrossfade=d={duration}:c1={curve}:c2={curve}"
    return make_result(fc=fc)


def _f_mix_audio(p):
    """Mix/blend audio from two inputs together using amix."""
    duration = str(p.get("duration", "longest")).lower()
    if duration not in ("longest", "shortest", "first"):
        duration = "longest"
    weights = str(p.get("weights", "1 1")).strip()
    dropout = float(p.get("dropout_transition", 2))
    fc = (
        f"[0:a][1:a]amix=inputs=2"
        f":duration={duration}"
        f":dropout_transition={dropout}"
        f":weights={weights}"
    )
    return make_result(fc=fc)
