"""Whisper-based audio transcription for FFMPEGA.

Provides speech-to-text transcription using OpenAI's Whisper model.
Models are stored in ComfyUI's standard models directory (ComfyUI/models/whisper/).
"""

import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field

from .sanitize import color_to_ass_bgr

logger = logging.getLogger("ffmpega")

# Module-level model cache — loaded once, reused across calls
_model = None
_model_name = None


@dataclass
class TranscriptionResult:
    """Result of a Whisper transcription."""

    segments: list[dict] = field(default_factory=list)
    """Segment-level timing: [{start, end, text}, ...]"""

    words: list[dict] = field(default_factory=list)
    """Word-level timing: [{start, end, word}, ...]"""

    language: str = ""
    """Auto-detected language code (e.g. 'en', 'ja', 'es')."""

    full_text: str = ""
    """Complete transcript as a single string."""


def _get_whisper_model_dir() -> str:
    """Get the ComfyUI models/whisper directory, creating it if needed."""
    try:
        import folder_paths  # type: ignore[import-not-found]
        model_dir = os.path.join(folder_paths.models_dir, "whisper")
    except ImportError:
        # Fallback for testing outside ComfyUI
        model_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "models", "whisper",
        )
    os.makedirs(model_dir, exist_ok=True)
    return model_dir


def _load_model(model_size: str = "large-v3", device: str = "gpu"):
    """Load or return cached Whisper model.

    Uses the model size selected by the user in the node UI.
    Device is controlled by the whisper_device node setting.

    Args:
        model_size: Whisper model to load (tiny, base, small, medium, large-v3).
        device: "gpu" (default, faster) or "cpu" (avoids VRAM pressure).

    Returns:
        Loaded whisper model.

    Raises:
        ImportError: If openai-whisper is not installed.
    """
    global _model, _model_name

    # Normalize device
    use_cpu = device.lower() == "cpu"
    cache_key = f"{model_size}_{'cpu' if use_cpu else 'gpu'}"

    if _model is not None and _model_name == cache_key:
        return _model

    # Free old model before loading a new one to avoid memory leak
    if _model is not None:
        logger.info("Freeing previous Whisper model '%s'", _model_name)
        del _model
        _model = None
        _model_name = None
        import gc
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    try:
        import whisper  # type: ignore[import-not-found]
    except ImportError:
        raise ImportError(
            "openai-whisper is required for auto-transcription. "
            "Install it with: pip install openai-whisper>=20240930"
        )

    # Check if the model file is already cached locally
    download_dir = _get_whisper_model_dir()
    _WHISPER_FILENAMES = {
        "large-v3": "large-v3.pt",
        "medium": "medium.pt",
        "small": "small.pt",
        "base": "base.pt",
        "tiny": "tiny.pt",
    }
    model_file = os.path.join(download_dir, _WHISPER_FILENAMES.get(model_size, f"{model_size}.pt"))
    # Check if model is already cached — if not, we'll wrap the load
    # with progress logging since whisper.load_model downloads internally
    needs_download = not os.path.isfile(model_file)

    if needs_download:
        # Guard: raise if downloads are disabled
        try:
            from . import model_manager
        except ImportError:
            from core import model_manager  # type: ignore
        model_manager.require_downloads_allowed("whisper")

        # Try AEmotionStudio mirror first — pre-fetch the .pt file into
        # the whisper download dir so whisper.load_model() finds it locally
        # and skips its own OpenAI CDN download.
        _mirror_filename = _WHISPER_FILENAMES.get(model_size, f"{model_size}.pt")
        _mirror_path = model_manager.try_mirror_download(
            "whisper", _mirror_filename, download_dir,
            convert_safetensors=True,
        )
        if _mirror_path:
            logger.info(
                "Whisper model '%s' pre-fetched from AEmotionStudio mirror",
                model_size,
            )
            # Re-check — file is now local, whisper.load_model will find it
            needs_download = False

    # If the file is cached locally (either pre-fetched from mirror or downloaded
    # normally), we must pass the explicit file path to whisper.load_model().
    # Passing the model name (e.g., "tiny") triggers whisper's strict SHA256 check,
    # which fails for safetensor-converted .pt files and forces a re-download.
    _load_target = model_file if not needs_download else model_size

    if use_cpu:
        # CPU mode — no VRAM needed, slower but safe for low-VRAM systems
        download_dir = _get_whisper_model_dir()
        logger.info(
            "Loading Whisper model '%s' on CPU (download dir: %s)",
            model_size, download_dir,
        )
        if needs_download:
            _model = model_manager.download_with_progress(
                "whisper",
                lambda: whisper.load_model(
                    _load_target, device="cpu", download_root=download_dir,
                ),
                extra=model_size,
            )
        else:
            _model = whisper.load_model(
                _load_target, device="cpu", download_root=download_dir,
            )
    else:
        # GPU mode — free ComfyUI VRAM first
        _free_comfyui_vram()
        download_dir = _get_whisper_model_dir()
        logger.info(
            "Loading Whisper model '%s' on GPU (download dir: %s)",
            model_size, download_dir,
        )
        if needs_download:
            _model = model_manager.download_with_progress(
                "whisper",
                lambda: whisper.load_model(
                    _load_target, download_root=download_dir,
                ),
                extra=model_size,
            )
        else:
            _model = whisper.load_model(
                _load_target, download_root=download_dir,
            )

    # When loading from a file path, whisper skips applying alignment heads.
    # We must apply them manually to ensure word-level timestamps work.
    if not needs_download and hasattr(whisper, "_ALIGNMENT_HEADS"):
        if model_size in whisper._ALIGNMENT_HEADS:
            _model.set_alignment_heads(whisper._ALIGNMENT_HEADS[model_size])

    _model_name = cache_key
    logger.info("Whisper model '%s' loaded successfully on %s", model_size, "CPU" if use_cpu else "GPU")
    return _model


def _free_comfyui_vram():
    """Ask ComfyUI to unload cached models from GPU VRAM.

    This frees space for Whisper's large-v3 model (~3 GB).
    ComfyUI will automatically reload its models when needed later.
    """
    try:
        import comfy.model_management as mm  # type: ignore[import-not-found]
        mm.unload_all_models()
        mm.soft_empty_cache()
        logger.info("Freed ComfyUI GPU VRAM for Whisper model loading")
    except (ImportError, AttributeError, Exception) as e:
        logger.debug("Could not free ComfyUI VRAM (non-fatal): %s", e)


def _extract_audio_wav(video_path: str) -> str:
    """Extract audio from video as 16kHz mono WAV (Whisper's expected format).

    Args:
        video_path: Path to input video file.

    Returns:
        Path to temporary WAV file.

    Raises:
        RuntimeError: If ffmpeg extraction fails.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vn",                   # No video
        "-acodec", "pcm_s16le",  # 16-bit PCM
        "-ar", "16000",          # 16kHz (Whisper's sample rate)
        "-ac", "1",              # Mono
        tmp.name,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg audio extraction failed: {result.stderr[:500]}"
            )
    except Exception:
        # Clean up on failure
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        raise

    return tmp.name


def transcribe_audio(
    video_path: str,
    model_size: str = "large-v3",
    language: str | None = None,
    device: str = "gpu",
) -> TranscriptionResult:
    """Transcribe audio from a video file using Whisper.

    Args:
        video_path: Path to input video file.
        model_size: Whisper model size (tiny, base, small, medium, large-v3).
        language: Optional language code (e.g. 'en'). None = auto-detect.
        device: "gpu" or "cpu" for Whisper model placement.

    Returns:
        TranscriptionResult with segments, words, language, and full text.
    """
    model = _load_model(model_size, device=device)

    # Extract audio to temp WAV
    wav_path = _extract_audio_wav(video_path)
    try:
        logger.info("Transcribing audio from: %s", video_path)

        options = {"word_timestamps": True}
        if language:
            options["language"] = language

        result = model.transcribe(wav_path, **options)

        # Extract segments
        segments = []
        words = []
        for seg in result.get("segments", []):
            segments.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"].strip(),
            })
            # Extract word-level timestamps
            for word_info in seg.get("words", []):
                words.append({
                    "start": word_info["start"],
                    "end": word_info["end"],
                    "word": word_info["word"].strip(),
                })

        detected_lang = result.get("language", "en")
        full_text = result.get("text", "").strip()

        logger.info(
            "Transcription complete: %d segments, %d words, language=%s",
            len(segments), len(words), detected_lang,
        )

        return TranscriptionResult(
            segments=segments,
            words=words,
            language=detected_lang,
            full_text=full_text,
        )
    finally:
        # Always clean up temp WAV
        if os.path.exists(wav_path):
            os.unlink(wav_path)


def _get_video_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe.

    Args:
        video_path: Path to video file.

    Returns:
        Duration in seconds, or 0.0 on failure.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        return float(result.stdout.strip())
    except (ValueError, subprocess.TimeoutExpired, Exception) as e:
        logger.warning("Could not get duration for %s: %s", video_path, e)
        return 0.0


def transcribe_multi_video(
    video_paths: list[str],
    model_size: str = "large-v3",
    language: str | None = None,
    device: str = "gpu",
    transition_duration: float = 0.0,
) -> TranscriptionResult:
    """Transcribe multiple videos and merge results with correct timing.

    Each video is transcribed independently, then timestamps are offset
    by the cumulative duration of preceding videos so the final result
    represents the full concatenated timeline.

    Args:
        video_paths: List of video file paths in concat order.
        model_size: Whisper model size (always forced to large-v3).
        language: Optional language code. None = auto-detect.
        device: "gpu" or "cpu" for Whisper model placement.
        transition_duration: Overlap duration per xfade transition (seconds).
            Subtracted from time_offset between videos to keep subtitles
            in sync with the xfade-shortened output.

    Returns:
        Merged TranscriptionResult spanning all videos.
    """
    if not video_paths:
        return TranscriptionResult()

    if len(video_paths) == 1:
        return transcribe_audio(video_paths[0], model_size, language, device=device)

    all_segments: list[dict] = []
    all_words: list[dict] = []
    all_text_parts: list[str] = []
    detected_lang = ""
    time_offset = 0.0

    for i, vpath in enumerate(video_paths):
        if not vpath or not os.path.isfile(vpath):
            logger.warning("Skipping non-existent video: %s", vpath)
            # Do NOT advance time_offset for skipped videos —
            # they contribute no content to the timeline.
            continue

        logger.info(
            "Transcribing video %d/%d: %s (offset: %.2fs)",
            i + 1, len(video_paths), os.path.basename(vpath), time_offset,
        )

        result = transcribe_audio(vpath, model_size, language, device=device)

        # Offset all timestamps by cumulative duration
        for seg in result.segments:
            all_segments.append({
                "start": seg["start"] + time_offset,
                "end": seg["end"] + time_offset,
                "text": seg["text"],
            })

        for word in result.words:
            all_words.append({
                "start": word["start"] + time_offset,
                "end": word["end"] + time_offset,
                "word": word["word"],
            })

        if result.full_text:
            all_text_parts.append(result.full_text)

        if not detected_lang and result.language:
            detected_lang = result.language

        # Advance offset by this video's duration, minus xfade overlap
        duration = _get_video_duration(vpath)
        time_offset += duration - transition_duration

    logger.info(
        "Multi-video transcription complete: %d segments, %d words across %d videos",
        len(all_segments), len(all_words), len(video_paths),
    )

    return TranscriptionResult(
        segments=all_segments,
        words=all_words,
        language=detected_lang or "en",
        full_text=" ".join(all_text_parts),
    )


def segments_to_srt(segments: list[dict]) -> str:
    """Convert segment-level timing to SRT subtitle format.

    Args:
        segments: List of {start, end, text} dicts.

    Returns:
        SRT-formatted string.
    """
    if not segments:
        return ""

    srt_blocks = []
    for i, seg in enumerate(segments, 1):
        start = seg["start"]
        end = seg["end"]
        text = seg["text"]

        start_ts = _seconds_to_srt_timestamp(start)
        end_ts = _seconds_to_srt_timestamp(end)

        srt_blocks.append(f"{i}\n{start_ts} --> {end_ts}\n{text}\n")

    return "\n".join(srt_blocks)


def _seconds_to_srt_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    ms = int((s % 1) * 1000)
    return f"{h:02d}:{m:02d}:{int(s):02d},{ms:03d}"


def words_to_karaoke_ass(
    words: list[dict],
    fontsize: int = 48,
    base_color: str = "white",
    fill_color: str = "yellow",
) -> str:
    r"""Convert word-level timestamps to ASS subtitle with karaoke timing.

    Uses ASS \kf (fill) tags for progressive word-by-word color fill,
    which is the standard karaoke effect in subtitle renderers.

    Args:
        words: List of {start, end, word} dicts with timing.
        fontsize: Font size in pixels.
        base_color: Base text color (unhighlighted).
        fill_color: Fill/highlight color for active words.

    Returns:
        ASS-formatted subtitle string.
    """
    if not words:
        return ""

    ass_base = color_to_ass_bgr(base_color)
    ass_fill = color_to_ass_bgr(fill_color)

    # ASS header
    header = (
        "[Script Info]\n"
        "Title: FFMPEGA Karaoke\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1920\n"
        "PlayResY: 1080\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Karaoke,Arial,{fontsize},{ass_fill},{ass_base},"
        f"&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,2,20,20,40,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
    )

    # Group words into lines (by sentence boundaries or ~8 words per line)
    lines = _group_words_into_lines(words, max_words_per_line=8)

    events = []
    for line_words in lines:
        if not line_words:
            continue

        line_start = line_words[0]["start"]
        line_end = line_words[-1]["end"]

        start_ts = _seconds_to_ass_timestamp(line_start)
        end_ts = _seconds_to_ass_timestamp(line_end)

        # Build karaoke tags: \kf<duration_cs> before each word
        # \kf = fill effect (progressive), duration in centiseconds
        karaoke_text = ""
        for w in line_words:
            duration_cs = int((w["end"] - w["start"]) * 100)
            duration_cs = max(duration_cs, 1)  # Minimum 1 centisecond
            # Escape ASS special characters in transcribed words
            word_text = w['word'].replace('\\', '').replace('{', '').replace('}', '')
            karaoke_text += f"{{\\kf{duration_cs}}}{word_text} "

        karaoke_text = karaoke_text.rstrip()

        events.append(
            f"Dialogue: 0,{start_ts},{end_ts},Karaoke,,0,0,0,,"
            f"{karaoke_text}"
        )

    return header + "\n".join(events) + "\n"


def _group_words_into_lines(
    words: list[dict],
    max_words_per_line: int = 8,
) -> list[list[dict]]:
    """Group words into subtitle lines based on timing gaps and word count.

    Splits on:
    - Gaps > 1.0 second between words (natural pauses)
    - Maximum words per line reached
    """
    if not words:
        return []

    lines: list[list[dict]] = []
    current_line: list[dict] = []

    for i, word in enumerate(words):
        # Start new line on large gap or max words
        if current_line:
            gap = word["start"] - current_line[-1]["end"]
            if gap > 1.0 or len(current_line) >= max_words_per_line:
                lines.append(current_line)
                current_line = []

        current_line.append(word)

    if current_line:
        lines.append(current_line)

    return lines


def _seconds_to_ass_timestamp(seconds: float) -> str:
    """Convert seconds to ASS timestamp format (H:MM:SS.cc)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    cs = int((s % 1) * 100)
    return f"{h}:{m:02d}:{int(s):02d}.{cs:02d}"
