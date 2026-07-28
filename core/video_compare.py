"""Combine multiple videos into one side-by-side / grid comparison clip.

Used by ``SaveVideoNode`` when more than one source is connected.  Each
source is either a video file path or a ComfyUI IMAGE tensor (which is
first encoded to a temp mp4).  Panels are scaled to a common size, shorter
clips freeze on their last frame until the longest ends, and the result is
laid out with ffmpeg ``xstack`` using offsets from ``core.grid_layout``.

Reuses:
    - ``core.bin_paths``           ffmpeg / ffprobe lookup
    - ``core.grid_layout``         layout math (shared with image_compare)
    - ``core.media_converter``     IMAGE tensor -> temp mp4
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile

try:
    from .bin_paths import get_ffmpeg_bin, get_ffprobe_bin
    from .grid_layout import cell_positions, compute_grid
except ImportError:  # pragma: no cover - script/standalone import
    from core.bin_paths import get_ffmpeg_bin, get_ffprobe_bin  # type: ignore
    from core.grid_layout import cell_positions, compute_grid  # type: ignore

logger = logging.getLogger("FFMPEGA")

# Named colors accepted as-is by ffmpeg; anything else is passed through too
# (ffmpeg also accepts 0xRRGGBB / #RRGGBB), we only sanitize obvious junk.
_DEFAULT_BG = "black"


def _even(x: float) -> int:
    """Round down to the nearest positive even integer (yuv420p needs even)."""
    v = int(x) // 2 * 2
    return max(2, v)


def _sanitize_label(text: str) -> str:
    """Strip characters that break ffmpeg drawtext escaping."""
    text = re.sub(r"[:'\\%\n\r]", " ", str(text))
    return text.strip()


def _probe(path: str) -> tuple[int, int, float, bool]:
    """Return ``(width, height, duration, has_audio)`` for a media file."""
    ffprobe = get_ffprobe_bin()
    w = h = 0
    dur = 0.0
    has_audio = False
    try:
        out = subprocess.run(
            [
                ffprobe, "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height:format=duration",
                "-of", "json", path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(out.stdout or "{}")
        streams = data.get("streams") or []
        if streams:
            w = int(streams[0].get("width") or 0)
            h = int(streams[0].get("height") or 0)
        dur = float((data.get("format") or {}).get("duration") or 0.0)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("video_compare: probe failed for %s: %s", path, e)
    try:
        a = subprocess.run(
            [
                ffprobe, "-v", "error", "-select_streams", "a",
                "-show_entries", "stream=codec_type", "-of", "csv=p=0", path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        has_audio = bool(a.stdout.strip())
    except Exception:
        has_audio = False
    return w, h, dur, has_audio


def combine_videos(
    sources: list,
    layout: str = "auto",
    labels: list[str] | None = None,
    gap: int = 4,
    bg_color: str = _DEFAULT_BG,
    fps: int = 24,
) -> str | None:
    """Stack ``sources`` into one comparison mp4 and return its path.

    Args:
        sources: list whose items are video-file-path strings or IMAGE
            tensors ``(B, H, W, 3)`` float32 in ``[0, 1]``.
        layout: ``auto`` | ``horizontal`` | ``vertical`` | ``grid``.
        labels: optional per-panel captions (drawn top-center). ``None`` or
            empty disables labels. Shorter lists leave later panels unlabeled.
        gap: pixel gap between panels (filled with ``bg_color``).
        bg_color: ffmpeg color name/hex for gaps and letterbox bars.
        fps: frame rate used when encoding IMAGE-tensor sources to temp mp4.

    Returns:
        Path to a temp mp4, or ``None`` on failure / fewer than 2 panels.
    """
    bg_color = bg_color or _DEFAULT_BG
    gap = max(0, int(gap))

    # --- Materialize every source to a concrete video path ---
    paths: list[str] = []
    temp_paths: list[str] = []
    mc = None
    for src in sources:
        if isinstance(src, str):
            if src and os.path.isfile(src):
                paths.append(src)
            continue
        # Assume an IMAGE tensor
        if hasattr(src, "shape") and getattr(src, "shape", [0])[0] > 0:
            try:
                if mc is None:
                    try:
                        from .media_converter import MediaConverter
                    except ImportError:
                        from core.media_converter import MediaConverter  # type: ignore
                    mc = MediaConverter()
                p = mc.images_to_video(src, fps=fps)
                paths.append(p)
                temp_paths.append(p)
            except Exception as e:
                logger.error("video_compare: tensor encode failed: %s", e)

    n = len(paths)
    if n == 0:
        _cleanup(temp_paths)
        return None
    if n == 1:
        # Nothing to combine; hand the single path back (no temp leak: if it
        # was a tensor encode, the caller takes ownership of the temp file).
        return paths[0]

    # --- Probe every panel ---
    infos = [_probe(p) for p in paths]
    max_dur = max((info[2] for info in infos), default=0.0)

    cols, rows = compute_grid(n, layout)
    single_row = rows == 1
    single_col = cols == 1

    panels: list[str] = []        # filter chains, one per input -> [vN]
    sizes: list[tuple[int, int]] = []  # (w, h) of each rendered panel

    if single_row:
        common_h = _even(max(h for _w, h, _d, _a in infos))
        for i, (w, h, dur, _a) in enumerate(infos):
            tw = _even(w * common_h / h) if h else common_h
            chain = (
                f"[{i}:v]setpts=PTS-STARTPTS,"
                f"scale={tw}:{common_h}:flags=bilinear,setsar=1"
            )
            chain += _tpad(dur, max_dur)
            chain += _drawtext(labels, i, common_h)
            panels.append(chain + f"[v{i}]")
            sizes.append((tw, common_h))
        positions = _row_positions(sizes, gap)
    elif single_col:
        common_w = _even(max(w for w, _h, _d, _a in infos))
        for i, (w, h, dur, _a) in enumerate(infos):
            th = _even(h * common_w / w) if w else common_w
            chain = (
                f"[{i}:v]setpts=PTS-STARTPTS,"
                f"scale={common_w}:{th}:flags=bilinear,setsar=1"
            )
            chain += _tpad(dur, max_dur)
            chain += _drawtext(labels, i, th)
            panels.append(chain + f"[v{i}]")
            sizes.append((common_w, th))
        positions = _col_positions(sizes, gap)
    else:
        cell_w = _even(max(w for w, _h, _d, _a in infos))
        cell_h = _even(max(h for _w, h, _d, _a in infos))
        for i, (_w, _h, dur, _a) in enumerate(infos):
            chain = (
                f"[{i}:v]setpts=PTS-STARTPTS,"
                f"scale={cell_w}:{cell_h}:force_original_aspect_ratio=decrease:"
                f"flags=bilinear,"
                f"pad={cell_w}:{cell_h}:(ow-iw)/2:(oh-ih)/2:color={bg_color},"
                f"setsar=1"
            )
            chain += _tpad(dur, max_dur)
            chain += _drawtext(labels, i, cell_h)
            panels.append(chain + f"[v{i}]")
            sizes.append((cell_w, cell_h))
        positions = [
            f"{x}_{y}" for (x, y) in cell_positions(cols, rows, cell_w, cell_h, gap)[:n]
        ]

    layout_str = "|".join(positions)
    inputs_lbl = "".join(f"[v{i}]" for i in range(n))
    fc = (
        ";".join(panels) + ";"
        + inputs_lbl
        + f"xstack=inputs={n}:layout={layout_str}:fill={bg_color}[out]"
    )

    # --- Audio: take the first source that actually has audio ---
    audio_idx = next((i for i, (*_x, a) in enumerate(infos) if a), None)

    out_path = os.path.join(
        tempfile.mkdtemp(prefix="ffmpega_compare_"), "comparison.mp4"
    )

    def _build(with_labels: bool) -> list[str]:
        graph = fc if with_labels else _strip_drawtext(fc)
        cmd = [get_ffmpeg_bin(), "-y"]
        for p in paths:
            cmd += ["-i", p]
        cmd += ["-filter_complex", graph, "-map", "[out]"]
        if audio_idx is not None:
            cmd += ["-map", f"{audio_idx}:a", "-c:a", "aac", "-b:a", "192k"]
        cmd += [
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-pix_fmt", "yuv420p", out_path,
        ]
        return cmd

    ok = _run(_build(bool(labels)))
    if not ok and labels:
        # drawtext can fail when fontconfig/font is unavailable — retry plain.
        logger.warning("video_compare: retrying without panel labels")
        ok = _run(_build(False))

    if not ok or not os.path.isfile(out_path):
        _cleanup(temp_paths)
        return None

    _cleanup(temp_paths)
    return out_path


def _tpad(dur: float, max_dur: float) -> str:
    """Freeze-pad a panel's last frame until ``max_dur`` (or no-op)."""
    delta = max_dur - dur
    if delta > 0.05 and dur > 0:
        return f",tpad=stop_mode=clone:stop_duration={delta:.3f}"
    return ""


def _drawtext(labels, i: int, panel_h: int) -> str:
    if not labels or i >= len(labels):
        return ""
    text = _sanitize_label(labels[i])
    if not text:
        return ""
    fontsize = max(14, int(panel_h // 18))
    pad = max(4, fontsize // 3)
    return (
        f",drawtext=text='{text}':x=(w-text_w)/2:y={pad}:"
        f"fontsize={fontsize}:fontcolor=white:box=1:"
        f"boxcolor=black@0.5:boxborderw={pad}"
    )


def _strip_drawtext(graph: str) -> str:
    """Remove any ``,drawtext=...`` segments (used as a fallback)."""
    return re.sub(r",drawtext=[^\[;]*", "", graph)


def _row_positions(sizes: list[tuple[int, int]], gap: int) -> list[str]:
    positions = []
    x = 0
    for w, _h in sizes:
        positions.append(f"{x}_0")
        x += w + gap
    return positions


def _col_positions(sizes: list[tuple[int, int]], gap: int) -> list[str]:
    positions = []
    y = 0
    for _w, h in sizes:
        positions.append(f"0_{y}")
        y += h + gap
    return positions


def _run(cmd: list[str]) -> bool:
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if res.returncode != 0:
            logger.error(
                "video_compare: ffmpeg failed (rc=%d): %s",
                res.returncode, (res.stderr or "")[-500:],
            )
            return False
        return True
    except Exception as e:  # pragma: no cover - defensive
        logger.error("video_compare: ffmpeg error: %s", e)
        return False


def _cleanup(paths: list[str]) -> None:
    for p in paths:
        try:
            if p and os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass
