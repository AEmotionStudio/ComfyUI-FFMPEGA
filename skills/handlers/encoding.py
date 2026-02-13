"""FFMPEGA Encoding skill handlers.

Auto-generated from composer.py — do not edit directly.
"""

def _f_compress(p):
    preset = p.get("preset", "medium")
    crf_map = {"light": 20, "medium": 23, "heavy": 28}
    crf = crf_map.get(preset, 23)
    return [], [], ["-c:v", "libx264", "-crf", str(crf), "-preset", "medium"]


def _f_convert(p):
    codec = p.get("codec", "h264")
    codec_map = {"h264": "libx264", "h265": "libx265", "vp9": "libvpx-vp9", "av1": "libaom-av1"}
    return [], [], ["-c:v", codec_map.get(codec, "libx264")]


def _f_bitrate(p):
    opts = []
    if p.get("video"):
        opts.extend(["-b:v", p["video"]])
    if p.get("audio"):
        opts.extend(["-b:a", p["audio"]])
    return [], [], opts


def _f_quality(p):
    crf = p.get("crf", 23)
    preset = p.get("preset", "medium")
    return [], [], ["-c:v", "libx264", "-crf", str(crf), "-preset", preset]


def _f_gif(p):
    width = int(p.get("width", 480))
    fps = int(p.get("fps", 15))
    # GIF conversion requires split + palettegen + paletteuse filtergraph
    return [
        f"fps={fps},scale={width}:-1:flags=lanczos,"
        f"split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
    ], [], []


def _f_container(p):
    fmt = p.get("format", "mp4")
    return [], [], ["-f", fmt]


def _f_two_pass(p):
    bitrate = p.get("target_bitrate", "4M")
    return [], [], ["-b:v", bitrate]


def _f_audio_codec(p):
    codec = p.get("codec", "aac")
    bitrate = p.get("bitrate", "128k")
    if codec == "copy":
        return [], [], ["-c:a", "copy"]
    return [], [], ["-c:a", codec, "-b:a", bitrate]


def _f_hwaccel(p):
    accel_type = p.get("type", "auto")
    return [], [], [], "", ["-hwaccel", accel_type]


def _f_thumbnail(p):
    """Extract best representative frame as image."""
    width = int(p.get("width", 0))
    time = float(p.get("time", 0))
    scale = f",scale={width}:-1" if width > 0 else ""
    input_opts = []
    if time > 0:
        # Seek to specific time instead of auto-detecting
        input_opts = ["-ss", str(time)]
        vf = f"null{scale}" if scale else ""
    else:
        vf = f"thumbnail{scale}"
    vf_list = [vf] if vf else []
    return vf_list, [], ["-frames:v", "1", "-an"], "", input_opts


def _f_extract_frames(p):
    """Export frames as image sequence."""
    rate = float(p.get("rate", 1.0))
    vf = f"fps={rate}"
    return [vf], [], ["-an"]


