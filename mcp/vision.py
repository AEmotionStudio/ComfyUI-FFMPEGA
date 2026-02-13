"""Vision utilities for FFMPEGA.

Provides frame-to-base64 encoding for API/Ollama connectors and
ffprobe-based color analysis as a fallback for non-vision models.
"""

import base64
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ffmpega")


def frames_to_base64(
    paths: list[Path | str],
    max_size: int = 512,
) -> list[dict]:
    """Convert frame image files to base64-encoded content blocks.

    Resizes images to fit within max_size pixels (preserving aspect ratio)
    to control token costs when sending to vision APIs.

    Args:
        paths: List of paths to PNG frame images.
        max_size: Maximum dimension (width or height) in pixels.

    Returns:
        List of OpenAI-compatible image content blocks:
        [{"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}]
    """
    try:
        from PIL import Image
        import io
    except ImportError:
        logger.warning(
            "Pillow not available — sending full-size frames. "
            "Install Pillow for automatic resizing: pip install Pillow"
        )
        return _frames_to_base64_raw(paths)

    blocks = []
    for p in paths:
        p = Path(p)
        if not p.exists():
            continue
        try:
            img = Image.open(p)
            # Resize if larger than max_size
            if max(img.size) > max_size:
                img.thumbnail((max_size, max_size), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            blocks.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })
        except Exception as e:
            logger.warning(f"Failed to encode frame {p}: {e}")
    return blocks


def frames_to_base64_raw_strings(
    paths: list[Path | str],
    max_size: int = 512,
) -> list[str]:
    """Convert frame images to raw base64 strings for Ollama's images format.

    Ollama expects messages with an "images" field containing a list of
    raw base64 strings (no data URI prefix).

    Args:
        paths: List of paths to PNG frame images.
        max_size: Maximum dimension in pixels.

    Returns:
        List of raw base64 strings.
    """
    try:
        from PIL import Image
        import io
    except ImportError:
        return _frames_to_base64_raw_strings_no_resize(paths)

    strings = []
    for p in paths:
        p = Path(p)
        if not p.exists():
            continue
        try:
            img = Image.open(p)
            if max(img.size) > max_size:
                img.thumbnail((max_size, max_size), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            strings.append(base64.b64encode(buf.getvalue()).decode("ascii"))
        except Exception as e:
            logger.warning(f"Failed to encode frame {p}: {e}")
    return strings


def analyze_colors_ffmpeg(
    video_path: str,
    start: float = 0.0,
    duration: float = 5.0,
) -> dict:
    """Analyze video colors using ffprobe signalstats filter.

    Provides numeric color data (luminance, chroma, saturation) that an LLM
    can use to make informed color grading decisions without vision.

    Args:
        video_path: Path to the video file.
        start: Start time in seconds.
        duration: Duration in seconds to analyze.

    Returns:
        Dictionary with color analysis results including:
        - luminance: min, max, average Y values
        - saturation: average saturation
        - color_distribution: dominant color channel info
        - recommendations: suggested adjustments
    """
    if not Path(video_path).exists():
        return {"error": f"Video not found: {video_path}"}

    # Use ffprobe with signalstats to get color metrics
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-select_streams", "v:0",
        "-show_entries",
        "frame_tags=lavfi.signalstats.YMIN,"
        "lavfi.signalstats.YMAX,"
        "lavfi.signalstats.YAVG,"
        "lavfi.signalstats.UAVG,"
        "lavfi.signalstats.VAVG,"
        "lavfi.signalstats.SATMIN,"
        "lavfi.signalstats.SATMAX,"
        "lavfi.signalstats.SATAVG,"
        "lavfi.signalstats.HUEAVG",
        "-of", "json",
        "-f", "lavfi",
        f"movie='{_escape_path(video_path)}',"
        f"trim=start={start}:duration={min(duration, 3)},"
        f"fps=1,signalstats",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            # Fallback: try simpler approach with direct ffprobe
            return _analyze_colors_simple(video_path, start, duration)

        data = json.loads(result.stdout)
        frames = data.get("frames", [])
        if not frames:
            return _analyze_colors_simple(video_path, start, duration)

        return _summarize_signal_stats(frames)

    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        logger.warning(f"signalstats analysis failed: {e}, trying simple mode")
        return _analyze_colors_simple(video_path, start, duration)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _frames_to_base64_raw(paths: list[Path | str]) -> list[dict]:
    """Encode frames without resizing (Pillow not available)."""
    blocks = []
    for p in paths:
        p = Path(p)
        if not p.exists():
            continue
        try:
            raw = p.read_bytes()
            b64 = base64.b64encode(raw).decode("ascii")
            blocks.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })
        except Exception as e:
            logger.warning(f"Failed to encode frame {p}: {e}")
    return blocks


def _frames_to_base64_raw_strings_no_resize(
    paths: list[Path | str],
) -> list[str]:
    """Encode frames as raw base64 strings without resizing."""
    strings = []
    for p in paths:
        p = Path(p)
        if not p.exists():
            continue
        try:
            strings.append(base64.b64encode(p.read_bytes()).decode("ascii"))
        except Exception as e:
            logger.warning(f"Failed to encode frame {p}: {e}")
    return strings


def _escape_path(path: str) -> str:
    """Escape path for use in ffprobe lavfi filter expressions."""
    # Replace backslashes and colons for cross-platform compat
    return path.replace("\\", "/").replace(":", "\\\\:")


def _analyze_colors_simple(
    video_path: str,
    start: float = 0.0,
    duration: float = 5.0,
) -> dict:
    """Simple color analysis using ffprobe stream metadata.

    Falls back to basic video stream info when signalstats isn't available.
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-select_streams", "v:0",
        "-show_entries",
        "stream=width,height,pix_fmt,color_space,color_range,"
        "color_transfer,color_primaries,avg_frame_rate",
        "-of", "json",
        str(video_path),
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15,
        )
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        if not streams:
            return {"error": "No video stream found"}

        stream = streams[0]
        return {
            "analysis_type": "basic",
            "resolution": f"{stream.get('width', '?')}x{stream.get('height', '?')}",
            "pixel_format": stream.get("pix_fmt", "unknown"),
            "color_space": stream.get("color_space", "unknown"),
            "color_range": stream.get("color_range", "unknown"),
            "color_transfer": stream.get("color_transfer", "unknown"),
            "hint": (
                "Basic analysis only — signalstats was unavailable. "
                "Use color_space and pixel_format to guide color grading. "
                "For BT.709 content, standard adjustments work well. "
                "For BT.2020 (HDR), be conservative with adjustments."
            ),
        }
    except Exception as e:
        return {"error": f"Color analysis failed: {e}"}


def _summarize_signal_stats(frames: list[dict]) -> dict:
    """Summarize signalstats data across multiple frames."""
    y_mins, y_maxs, y_avgs = [], [], []
    u_avgs, v_avgs = [], []
    sat_mins, sat_maxs, sat_avgs = [], [], []
    hue_avgs = []

    for frame in frames:
        tags = frame.get("tags", {})
        _safe_append(y_mins, tags, "lavfi.signalstats.YMIN")
        _safe_append(y_maxs, tags, "lavfi.signalstats.YMAX")
        _safe_append(y_avgs, tags, "lavfi.signalstats.YAVG")
        _safe_append(u_avgs, tags, "lavfi.signalstats.UAVG")
        _safe_append(v_avgs, tags, "lavfi.signalstats.VAVG")
        _safe_append(sat_mins, tags, "lavfi.signalstats.SATMIN")
        _safe_append(sat_maxs, tags, "lavfi.signalstats.SATMAX")
        _safe_append(sat_avgs, tags, "lavfi.signalstats.SATAVG")
        _safe_append(hue_avgs, tags, "lavfi.signalstats.HUEAVG")

    result: dict = {"analysis_type": "signalstats", "frames_analyzed": len(frames)}

    if y_avgs:
        avg_y = sum(y_avgs) / len(y_avgs)
        result["luminance"] = {
            "min": round(min(y_mins) if y_mins else 0, 1),
            "max": round(max(y_maxs) if y_maxs else 255, 1),
            "average": round(avg_y, 1),
            "assessment": _assess_luminance(avg_y),
        }

    if sat_avgs:
        avg_sat = sum(sat_avgs) / len(sat_avgs)
        result["saturation"] = {
            "min": round(min(sat_mins) if sat_mins else 0, 1),
            "max": round(max(sat_maxs) if sat_maxs else 0, 1),
            "average": round(avg_sat, 1),
            "assessment": _assess_saturation(avg_sat),
        }

    if u_avgs and v_avgs:
        avg_u = sum(u_avgs) / len(u_avgs)
        avg_v = sum(v_avgs) / len(v_avgs)
        result["color_balance"] = {
            "u_average": round(avg_u, 1),
            "v_average": round(avg_v, 1),
            "dominant_tone": _assess_color_balance(avg_u, avg_v),
        }

    if hue_avgs:
        result["hue_average"] = round(sum(hue_avgs) / len(hue_avgs), 1)

    # Generate recommendations based on analysis
    result["recommendations"] = _generate_recommendations(result)

    result["hint"] = (
        "These are numeric color metrics from ffprobe signalstats. "
        "Y=luminance (0-255, 128=mid-gray), U/V=chroma (128=neutral), "
        "SAT=saturation (0=grayscale). Use these to guide color grading."
    )

    return result


def _safe_append(lst: list, tags: dict, key: str) -> None:
    """Safely parse and append a numeric tag value."""
    val = tags.get(key)
    if val is not None:
        try:
            lst.append(float(val))
        except (ValueError, TypeError):
            pass


def _assess_luminance(avg_y: float) -> str:
    """Assess luminance level."""
    if avg_y < 40:
        return "very dark — consider increasing brightness/exposure"
    elif avg_y < 80:
        return "dark — may benefit from brightness boost"
    elif avg_y < 130:
        return "well-exposed"
    elif avg_y < 200:
        return "bright — reduce brightness if needed"
    else:
        return "overexposed — reduce exposure/brightness"


def _assess_saturation(avg_sat: float) -> str:
    """Assess saturation level."""
    if avg_sat < 15:
        return "nearly grayscale — boost saturation for color"
    elif avg_sat < 40:
        return "low saturation — desaturated/muted look"
    elif avg_sat < 80:
        return "moderate saturation — natural look"
    elif avg_sat < 130:
        return "vivid — already colorful"
    else:
        return "oversaturated — consider reducing saturation"


def _assess_color_balance(avg_u: float, avg_v: float) -> str:
    """Assess color cast from U/V chroma channels.

    U: <128 = blue shift, >128 = yellow shift
    V: <128 = green shift, >128 = red/magenta shift
    """
    tones = []
    u_offset = avg_u - 128
    v_offset = avg_v - 128

    if abs(u_offset) < 3 and abs(v_offset) < 3:
        return "neutral — well-balanced color"

    if u_offset < -5:
        tones.append("blue")
    elif u_offset > 5:
        tones.append("yellow/warm")

    if v_offset < -5:
        tones.append("green")
    elif v_offset > 5:
        tones.append("red/magenta")

    return ", ".join(tones) + " tint" if tones else "near-neutral"


def _generate_recommendations(analysis: dict) -> list[str]:
    """Generate actionable recommendations based on color analysis."""
    recs = []

    lum = analysis.get("luminance", {})
    if lum.get("average", 128) < 60:
        recs.append("Video is dark — use brightness skill with positive value (e.g. 0.2-0.4)")
    elif lum.get("average", 128) > 200:
        recs.append("Video is overexposed — use brightness with negative value or reduce exposure")

    sat = analysis.get("saturation", {})
    if sat.get("average", 50) < 20:
        recs.append("Very low saturation — use saturation skill with value > 1.0 (e.g. 1.5-2.0)")
    elif sat.get("average", 50) > 130:
        recs.append("Oversaturated — use saturation skill with value < 1.0 (e.g. 0.6-0.8)")

    balance = analysis.get("color_balance", {})
    tone = balance.get("dominant_tone", "")
    if "blue" in tone:
        recs.append("Blue cast detected — use colorbalance to add warmth (increase rs, rm)")
    elif "yellow" in tone or "warm" in tone:
        recs.append("Warm cast detected — use colorbalance to cool (increase bs, bm)")

    if not recs:
        recs.append("Colors look well-balanced — safe to apply creative effects")

    return recs


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Audio analysis
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def analyze_audio_ffmpeg(
    video_path: str,
    start: float = 0.0,
    duration: float = 10.0,
) -> dict:
    """Analyze audio characteristics using ffprobe and ffmpeg filters.

    Provides numeric audio data (volume, loudness, frequency content) that
    an LLM can use to make informed decisions about audio effects.

    Args:
        video_path: Path to the video/audio file.
        start: Start time in seconds.
        duration: Duration in seconds to analyze.

    Returns:
        Dictionary with audio analysis including:
        - properties: codec, sample_rate, channels, bitrate
        - volume: mean/peak/RMS dB, dynamic range
        - loudness: EBU R128 integrated LUFS, range LU
        - silence: detected silent sections
        - recommendations: suggested adjustments
    """
    if not Path(video_path).exists():
        return {"error": f"File not found: {video_path}"}

    # Step 1: Check for audio stream via ffprobe
    props = _get_audio_properties(video_path)
    if not props.get("has_audio"):
        return {
            "has_audio": False,
            "hint": "No audio stream found. Use audio skills only if you plan to add audio.",
        }

    result: dict = {"has_audio": True, **props}

    # Step 2: Volume analysis via astats
    volume = _analyze_volume(video_path, start, duration)
    if volume:
        result["volume"] = volume

    # Step 3: EBU R128 loudness via loudnorm
    loudness = _analyze_loudness(video_path, start, duration)
    if loudness:
        result["loudness"] = loudness

    # Step 4: Silence detection
    silence = _detect_silence(video_path, start, duration)
    if silence:
        result["silence"] = silence

    # Step 5: Generate recommendations
    result["recommendations"] = _generate_audio_recommendations(result)

    result["hint"] = (
        "These are numeric audio metrics from ffmpeg. "
        "dB values are negative (0 dB = clipping). "
        "LUFS is the broadcast loudness standard (-23 LUFS = EBU R128). "
        "Use these to guide volume, normalize, and EQ decisions."
    )

    return result


def _get_audio_properties(video_path: str) -> dict:
    """Get basic audio stream properties via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-select_streams", "a:0",
        "-show_entries",
        "stream=codec_name,sample_rate,channels,bit_rate,channel_layout,duration",
        "-of", "json",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        if not streams:
            return {"has_audio": False}

        s = streams[0]
        bitrate = s.get("bit_rate")
        return {
            "has_audio": True,
            "codec": s.get("codec_name", "unknown"),
            "sample_rate": int(s.get("sample_rate", 0)),
            "channels": int(s.get("channels", 0)),
            "channel_layout": s.get("channel_layout", "unknown"),
            "bitrate_kbps": round(int(bitrate) / 1000) if bitrate else None,
            "duration_sec": round(float(s["duration"]), 2) if s.get("duration") else None,
        }
    except Exception as e:
        logger.warning(f"ffprobe audio properties failed: {e}")
        return {"has_audio": False}


def _analyze_volume(video_path: str, start: float, duration: float) -> Optional[dict]:
    """Analyze volume using ffmpeg volumedetect filter."""
    dur = min(duration, 30)  # Cap to avoid long analysis
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-ss", str(start), "-t", str(dur),
        "-i", str(video_path),
        "-af", "volumedetect",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
        stderr = result.stderr or ""
        mean_vol = None
        max_vol = None
        for line in stderr.split("\n"):
            if "mean_volume" in line:
                try:
                    mean_vol = float(line.split("mean_volume:")[1].strip().split(" ")[0])
                except (ValueError, IndexError):
                    pass
            elif "max_volume" in line:
                try:
                    max_vol = float(line.split("max_volume:")[1].strip().split(" ")[0])
                except (ValueError, IndexError):
                    pass

        if mean_vol is not None:
            return {
                "mean_db": round(mean_vol, 1),
                "peak_db": round(max_vol, 1) if max_vol is not None else None,
                "dynamic_range_db": (
                    round(abs(max_vol - mean_vol), 1)
                    if max_vol is not None else None
                ),
                "assessment": _assess_volume(mean_vol, max_vol or mean_vol),
            }
    except Exception as e:
        logger.warning(f"volumedetect failed: {e}")
    return None



def _analyze_loudness(video_path: str, start: float, duration: float) -> Optional[dict]:
    """Analyze EBU R128 loudness using loudnorm filter (measure-only)."""
    dur = min(duration, 30)
    cmd = [
        "ffmpeg", "-hide_banner",
        "-ss", str(start), "-t", str(dur),
        "-i", str(video_path),
        "-af", "loudnorm=print_format=json:I=-23:LRA=7:TP=-2",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
        stderr = result.stderr or ""

        # loudnorm outputs JSON at the end of stderr
        json_start = stderr.rfind("{")
        json_end = stderr.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            loudnorm_data = json.loads(stderr[json_start:json_end])
            integrated = float(loudnorm_data.get("input_i", -70))
            lra = float(loudnorm_data.get("input_lra", 0))
            tp = float(loudnorm_data.get("input_tp", 0))

            return {
                "integrated_lufs": round(integrated, 1),
                "range_lu": round(lra, 1),
                "true_peak_dbtp": round(tp, 1),
                "assessment": _assess_loudness(integrated, lra),
            }
    except Exception as e:
        logger.warning(f"loudnorm analysis failed: {e}")
    return None


def _detect_silence(video_path: str, start: float, duration: float) -> Optional[dict]:
    """Detect silent sections using silencedetect filter."""
    dur = min(duration, 60)
    cmd = [
        "ffmpeg", "-hide_banner",
        "-ss", str(start), "-t", str(dur),
        "-i", str(video_path),
        "-af", "silencedetect=noise=-40dB:d=0.5",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )
        stderr = result.stderr or ""

        silent_count = stderr.count("silence_end")
        if silent_count == 0:
            return {
                "silent_sections": 0,
                "assessment": "no silence detected",
            }
        else:
            return {
                "silent_sections": silent_count,
                "assessment": (
                    f"{silent_count} silent section(s) detected "
                    f"(threshold: -40 dB, min duration: 0.5s)"
                ),
            }
    except Exception as e:
        logger.warning(f"silencedetect failed: {e}")
    return None


def _extract_astats_value(line: str) -> Optional[float]:
    """Extract numeric value from an astats metadata line."""
    try:
        # Format: "lavfi.astats.Overall.RMS_level=-18.123456"
        parts = line.strip().split("=")
        if len(parts) >= 2:
            val = parts[-1].strip()
            if val == "-inf" or val == "inf":
                return -200.0
            return float(val)
    except (ValueError, IndexError):
        pass
    return None


def _assess_volume(mean_db: float, peak_db: float) -> str:
    """Assess volume levels."""
    if mean_db < -40:
        return "very quiet — audio is barely audible, consider normalizing"
    elif mean_db < -25:
        return "quiet — below typical levels, normalize or boost volume"
    elif mean_db < -15:
        return "moderate volume — good for most content"
    elif mean_db < -6:
        return "loud — strong audio, be careful with additional boosts"
    else:
        return "very loud — near or at clipping, reduce volume"


def _assess_loudness(lufs: float, lra: float) -> str:
    """Assess EBU R128 loudness."""
    parts = []
    if lufs < -30:
        parts.append("very quiet for broadcast")
    elif lufs < -24:
        parts.append("below EBU R128 standard (-23 LUFS)")
    elif lufs < -20:
        parts.append("near broadcast standard")
    elif lufs < -14:
        parts.append("above broadcast standard, typical for streaming")
    else:
        parts.append("very loud, may cause distortion")

    if lra > 15:
        parts.append("high dynamic range")
    elif lra > 7:
        parts.append("moderate dynamic range")
    else:
        parts.append("compressed/limited dynamic range")

    return " — ".join(parts)


def _generate_audio_recommendations(analysis: dict) -> list[str]:
    """Generate actionable audio recommendations."""
    recs = []

    vol = analysis.get("volume", {})
    mean = vol.get("mean_db", -20)
    peak = vol.get("peak_db", -5)

    if mean < -30:
        recs.append("Audio is very quiet — use normalize skill to bring to standard levels")
    elif mean > -6:
        recs.append("Audio is very loud — use volume skill with value < 1.0 to reduce")

    if peak and peak > -1:
        recs.append("Audio peaks near 0 dB (clipping risk) — use compress_audio or reduce volume")

    loud = analysis.get("loudness", {})
    lufs = loud.get("integrated_lufs", -20)
    if lufs < -28:
        recs.append("Loudness well below broadcast standards — use normalize for consistent levels")
    elif lufs > -10:
        recs.append("Loudness very high — reduce volume or apply normalization")

    silence = analysis.get("silence", {})
    if silence.get("silent_sections", 0) > 3:
        recs.append("Multiple silent sections detected — consider trimming or adding background audio")

    if not recs:
        recs.append("Audio levels look good — safe to apply effects")

    return recs

