"""Server-side waveform peak extraction via FFmpeg.

Extracts audio from a video file, downsamples to a fixed number of peak
bins, and returns normalised peak data as a Python list.  This avoids
the client having to download the entire video just to decode audio for
the timeline waveform display.

All subprocess calls are async (``asyncio.create_subprocess_exec``) so
the route handler can ``await`` directly without occupying a thread-pool
worker.
"""

from __future__ import annotations

import asyncio
import logging
import struct

from ._bin import get_ffmpeg_bin, get_ffprobe_bin

log = logging.getLogger("ffmpega.videoeditor")

# Number of peak bins for waveform display (matches client-side PEAK_COUNT)
PEAK_COUNT = 2000

# Sample rate for audio extraction — 8 kHz is enough for waveform peaks
# and keeps the raw PCM small (~duration × 8000 × 4 bytes for f32le mono).
_SAMPLE_RATE = 8000

# Max source file duration (seconds) to attempt extraction.
# A 10-minute video at 8 kHz mono f32le = ~19 MB of raw PCM — fine.
# A 60-minute video = ~115 MB — still OK but getting large.
# Cap at 30 minutes to stay safe.
_MAX_DURATION = 30 * 60

# Flat fallback returned on any failure
FLAT_WAVEFORM = {"peaks": [0.1] * PEAK_COUNT, "duration": 0.0, "sampleRate": 0}


def _flat(bin_count: int = PEAK_COUNT) -> dict:
    """Return a flat waveform fallback, respecting a custom bin count."""
    if bin_count == PEAK_COUNT:
        return dict(FLAT_WAVEFORM)  # fast path — copy the pre-built dict
    return {"peaks": [0.1] * bin_count, "duration": 0.0, "sampleRate": 0}


async def extract_waveform_peaks(
    video_path: str,
    bin_count: int = PEAK_COUNT,
) -> dict:
    """Extract normalised waveform peaks from *video_path*.

    Returns
    -------
    dict
        ``{"peaks": list[float], "duration": float, "sampleRate": int}``

    On failure returns peaks filled with 0.1 and duration/sampleRate = 0.
    """
    flat = _flat(bin_count)

    ffmpeg = get_ffmpeg_bin()
    ffprobe = get_ffprobe_bin()
    if not ffmpeg or not ffprobe:
        log.warning("[Waveform] FFmpeg/FFprobe not found")
        return flat

    # Probe duration to enforce cap
    try:
        proc = await asyncio.create_subprocess_exec(
            ffprobe, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            video_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            log.warning("[Waveform] ffprobe timed out")
            return flat

        duration = float(stdout.decode().strip()) if proc.returncode == 0 else 0.0
    except Exception:
        duration = 0.0

    if duration <= 0:
        log.warning("[Waveform] Could not determine duration")
        return flat

    if duration > _MAX_DURATION:
        log.info(
            "[Waveform] Video too long (%.0fs > %ds cap), returning flat waveform",
            duration, _MAX_DURATION,
        )
        return flat

    # Extract raw mono float32 PCM via FFmpeg
    try:
        proc = await asyncio.create_subprocess_exec(
            ffmpeg, "-v", "error",
            "-i", video_path,
            "-vn",                  # no video
            "-ac", "1",             # mono
            "-ar", str(_SAMPLE_RATE),
            "-f", "f32le",          # 32-bit float, little-endian
            "-acodec", "pcm_f32le",
            "pipe:1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            log.warning("[Waveform] FFmpeg extraction timed out")
            return flat

        if proc.returncode != 0 or not stdout:
            log.warning("[Waveform] FFmpeg extraction failed (rc=%d)", proc.returncode)
            return flat
    except Exception as e:
        log.warning("[Waveform] FFmpeg extraction error: %s", e)
        return flat

    raw = stdout
    sample_count = len(raw) // 4  # 4 bytes per float32

    if sample_count == 0:
        return flat

    # Unpack float32 samples
    samples = struct.unpack(f"<{sample_count}f", raw[:sample_count * 4])

    # Downsample to peak bins
    peaks = _downsample_peaks(samples, bin_count)

    return {
        "peaks": peaks,
        "duration": round(duration, 3),
        "sampleRate": _SAMPLE_RATE,
    }


def _downsample_peaks(samples: tuple | list, bin_count: int) -> list[float]:
    """Downsample raw audio samples to peak bins (normalised 0–1)."""
    n = len(samples)
    samples_per_bin = n // bin_count

    if samples_per_bin == 0:
        # Very short audio
        peaks = [abs(samples[i]) if i < n else 0.0 for i in range(bin_count)]
    else:
        peaks = []
        for b in range(bin_count):
            start = b * samples_per_bin
            end = min(start + samples_per_bin, n)
            mx = 0.0
            for i in range(start, end):
                a = abs(samples[i])
                if a > mx:
                    mx = a
            peaks.append(mx)

    # Normalise to 0–1
    global_max = max(peaks) if peaks else 0.0
    if global_max > 0:
        peaks = [p / global_max for p in peaks]

    return peaks
