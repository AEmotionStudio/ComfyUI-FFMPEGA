"""FFMPEGA Lip Sync skill handler.

Uses MuseTalk to synchronize lip movements in video with provided audio.
Runs in a subprocess to avoid CUDA memory leaks.

License note:
    MuseTalk code: MIT License
    SD-VAE model: CreativeML Open RAIL-M (commercial OK with restrictions)
    Whisper model: MIT License
"""

import logging

try:
    from ..handler_contract import make_result
    from ...core.sanitize import validate_video_path, ValidationError
except ImportError:
    from skills.handler_contract import make_result
    from core.sanitize import validate_video_path, ValidationError

log = logging.getLogger("ffmpega")


def _f_lip_sync(p):
    """Synchronize lip movements with audio using MuseTalk AI.

    Takes a video (or image) and an audio file, then generates a new
    video where the subject's lips are synchronized to the audio.

    Params:
        audio_path (str):   Path to the audio file for lip sync (required).
        face_index (int):   Which face to process: -1 = all faces, 0+ = specific face.
        batch_size (int):   Frames processed per batch (lower = less VRAM).
    """
    raw_audio_path = str(p.get("audio_path", ""))
    face_index = int(p.get("face_index", -1))
    batch_size = int(p.get("batch_size", 8))
    raw_video_path = p.get("_input_path", "")

    try:
        if not raw_audio_path:
            raise ValidationError("audio_path is empty")
        audio_path = validate_video_path(raw_audio_path)
    except ValidationError as e:
        log.warning(
            f"lip_sync requires a valid audio_path parameter pointing to an "
            f"existing audio file. Validation failed: {e}"
        )
        _metadata_ref = p.get("_metadata_ref")
        if _metadata_ref is not None and isinstance(_metadata_ref, dict):
            _metadata_ref["_skill_degraded"] = True
        return make_result()

    try:
        if not raw_video_path:
            raise ValidationError("video_path is empty")
        video_path = validate_video_path(raw_video_path)
    except ValidationError as e:
        log.warning(
            f"lip_sync requires a valid video input. Validation failed: {e}"
        )
        _metadata_ref = p.get("_metadata_ref")
        if _metadata_ref is not None and isinstance(_metadata_ref, dict):
            _metadata_ref["_skill_degraded"] = True
        return make_result()

    # Try to import MuseTalk synthesizer
    try:
        try:
            from ...core.musetalk_synthesizer import lip_sync_subprocess
        except ImportError:
            from core.musetalk_synthesizer import lip_sync_subprocess
        _has_musetalk = True
    except ImportError:
        _has_musetalk = False

    if not _has_musetalk:
        log.warning(
            "MuseTalk lip sync not available. This is unexpected as all "
            "dependencies should be built into ComfyUI."
        )
        _metadata_ref = p.get("_metadata_ref")
        if _metadata_ref is not None and isinstance(_metadata_ref, dict):
            _metadata_ref["_skill_degraded"] = True
        return make_result()

    # Generate lip-synced video via subprocess
    try:
        output_path = lip_sync_subprocess(
            video_path=video_path,
            audio_path=audio_path,
            batch_size=batch_size,
            face_index=face_index,
        )
    except Exception as e:
        log.error("MuseTalk lip sync failed: %s", e)
        _metadata_ref = p.get("_metadata_ref")
        if _metadata_ref is not None and isinstance(_metadata_ref, dict):
            _metadata_ref["_skill_degraded"] = True
        return make_result()

    # Store the lip-synced video path in metadata
    _metadata_ref = p.get("_metadata_ref")
    if _metadata_ref is not None and isinstance(_metadata_ref, dict):
        _metadata_ref["_lip_synced_video_path"] = output_path

    # The lip-synced video replaces the original input entirely.
    # We use -i to add it as a secondary input and map from it.
    escaped = output_path.replace("'", "'\\''").replace(":", "\\:")
    fc = (
        f"movie={escaped}[_lipsync_v];"
        f"amovie={escaped}[_lipsync_a]"
    )
    return make_result(
        fc=fc,
        opts=["-map", "[_lipsync_v]", "-map", "[_lipsync_a]"],
    )
