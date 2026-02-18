"""FFMPEGA Multi-input skill handlers.

Handles skills that work with multiple video/image inputs:
concat, xfade, grid, slideshow, overlay, PIP, split screen, etc.
"""

try:
    from ...core.sanitize import (
        sanitize_text_param,
    )
except ImportError:
    from core.sanitize import (
        sanitize_text_param,
    )

_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".ts", ".m4v"}

def _is_video_file(path):
    """Check if a file path is a video based on its extension."""
    import os
    return os.path.splitext(path)[1].lower() in _VIDEO_EXTENSIONS


def _probe_duration(path):
    """Get the duration of a media file in seconds using ffprobe.

    Returns 0.0 on any failure (missing ffprobe, invalid file, etc.).
    """
    import shutil
    import subprocess
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return 0.0
    try:
        result = subprocess.run(
            [ffprobe_bin, "-v", "error", "-show_entries",
             "format=duration", "-of",
             "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, check=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0

def _f_grid(p):
    """Arrange multiple images in a grid using xstack filter_complex."""
    columns = int(p.get("columns", 2))
    gap = int(p.get("gap", 4))
    duration = float(p.get("duration", 5.0))
    bg = sanitize_text_param(str(p.get("background", "black")))
    include_video = str(p.get("include_video", "true")).lower() in ("true", "1", "yes")
    cell_w = int(p.get("cell_width", 640))
    cell_h = int(p.get("cell_height", 480))
    n_extra = int(p.get("_extra_input_count", 0))

    # Build list of ffmpeg input indices
    cells = []
    if include_video:
        cells.append(0)  # main video = [0:v]
    for i in range(n_extra):
        cells.append(i + 1)  # extra inputs = [1:v], [2:v], ...

    total = len(cells)
    if total < 2:
        return [], [], [], ""

    fps = int(p.get("_input_fps", 25))
    extra_paths = p.get("_extra_input_paths", [])
    # Scale all inputs to same cell size (maintain aspect ratio + pad).
    # Video inputs play normally; still images are looped for `duration`.
    parts = []
    for i, idx in enumerate(cells):
        is_video = (idx == 0) or (
            idx - 1 < len(extra_paths) and _is_video_file(extra_paths[idx - 1])
        )
        if is_video:
            # Video input: scale, it already has frames
            parts.append(
                f"[{idx}:v]scale={cell_w}:{cell_h}:force_original_aspect_ratio=decrease,"
                f"pad={cell_w}:{cell_h}:(ow-iw)/2:(oh-ih)/2:{bg},setsar=1,fps={fps}[_g{i}]"
            )
        else:
            # Still image: loop to create video frames for `duration` seconds
            n_frames = int(duration * fps)
            parts.append(
                f"[{idx}:v]loop=loop={n_frames}:size=1:start=0,"
                f"setpts=N/{fps}/TB,"
                f"scale={cell_w}:{cell_h}:force_original_aspect_ratio=decrease,"
                f"pad={cell_w}:{cell_h}:(ow-iw)/2:(oh-ih)/2:{bg},setsar=1[_g{i}]"
            )

    # Build xstack layout string — must use literal pixel values (no arithmetic)
    layout_parts = []
    for i in range(total):
        col = i % columns
        row = i // columns
        x = col * (cell_w + gap)
        y = row * (cell_h + gap)
        layout_parts.append(f"{x}_{y}")

    input_labels = "".join(f"[_g{i}]" for i in range(total))
    layout_str = "|".join(layout_parts)

    fc_parts = parts + [
        f"{input_labels}xstack=inputs={total}:layout={layout_str}:fill={bg}"
    ]

    opts = ["-t", str(duration)]
    return [], [], opts, ";".join(fc_parts)


def _f_slideshow(p):
    """Create a slideshow from multiple images using concat filter_complex."""
    dur = float(p.get("duration_per_image", 3.0))
    transition = p.get("transition", "fade")
    trans_dur = float(p.get("transition_duration", 0.5))
    width = int(p.get("width", p.get("_input_width", 1920)))
    height = int(p.get("height", p.get("_input_height", 1080)))
    include_video = str(p.get("include_video", "false")).lower() in ("true", "1", "yes")
    n_extra = int(p.get("_extra_input_count", 0))

    # Build ordered list of (ffmpeg_idx, is_video) pairs
    segments = []
    if include_video:
        segments.append((0, True))
    for i in range(n_extra):
        segments.append((i + 1, False))

    total = len(segments)
    if total < 1:
        return [], [], [], ""

    parts = []
    concat_inputs = []
    for i, (idx, is_video) in enumerate(segments):
        label = f"[_s{i}]"
        if is_video:
            # Use the main video at its natural duration, scaled to target size
            seg = (
                f"[{idx}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
            )
        else:
            # Still image: loop to create a video segment of `dur` seconds
            seg = (
                f"[{idx}:v]loop=loop={int(dur * 25)}:size=1:start=0,"
                f"setpts=N/25/TB,scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
            )
        if transition == "fade" and total > 1:
            if i > 0:
                seg += f",fade=t=in:st=0:d={trans_dur}"
            if i < total - 1:
                if is_video:
                    # Skip fade-out on video — we don't know its duration at
                    # filter-build time. The next slide's fade-in handles the
                    # visual transition. Hardcoding a time causes black frames
                    # if the video is longer, or no effect if shorter.
                    pass
                else:
                    fade_st = dur - trans_dur
                    seg += f",fade=t=out:st={fade_st}:d={trans_dur}"
        seg += label
        parts.append(seg)
        concat_inputs.append(label)

    concat_str = "".join(concat_inputs)
    parts.append(f"{concat_str}concat=n={total}:v=1:a=0")

    return [], [], [], ";".join(parts)


def _f_overlay_image(p):
    """Overlay extra input images on the main video (picture-in-picture).

    Supports multiple overlays — each extra input gets its own position.
    When `image_source` is specified (e.g. "image_a"), only that input
    is used as the overlay.

    When `animation` is specified, delegates to _f_animated_overlay which
    has proper motion presets (bounce, float, scroll, etc).
    """
    # Auto-delegate to animated_overlay when animation is requested
    animation = p.get("animation", None)
    import logging
    _log = logging.getLogger("ffmpega")
    _log.debug("[overlay_image] params keys=%s, animation=%r", list(p.keys()), animation)
    if animation and str(animation).lower() not in ("none", "static", ""):
        # Map animation_speed → speed for animated_overlay
        if "animation_speed" in p and "speed" not in p:
            p["speed"] = p["animation_speed"]
        _log.info("[overlay_image] Delegating to animated_overlay (animation=%s)", animation)
        return _f_animated_overlay(p)

    position = p.get("position", "bottom-right")
    # Normalize underscore-separated positions (LLMs often send bottom_right)
    if isinstance(position, str):
        position = position.replace("_", "-")
    scale = float(p.get("scale", 0.25))
    opacity = float(p.get("opacity", 1.0))
    margin = int(p.get("margin", 10))
    n = int(p.get("_extra_input_count", 0))
    image_source = p.get("image_source", None)

    if n < 1:
        return [], [], [], ""

    pos_map = {
        "top-left": f"{margin}:{margin}",
        "top-right": f"W-w-{margin}:{margin}",
        "bottom-left": f"{margin}:H-h-{margin}",
        "bottom-right": f"W-w-{margin}:H-h-{margin}",
        "center": "(W-w)/2:(H-h)/2",
    }

    # Determine which extra inputs to overlay
    # When _image_input_indices is set (from image_path_a/b/c...),
    # use those exact ffmpeg indices instead of the 1-4 source map.
    image_input_indices = p.get("_image_input_indices", [])

    if image_input_indices:
        # image_path inputs — use exact ffmpeg indices
        if n == 1 or len(image_input_indices) == 1:
            overlay_inputs = [(image_input_indices[0], position)]
        else:
            corner_cycle = ["top-left", "top-right", "bottom-right", "bottom-left"]
            overlay_inputs = []
            try:
                start_idx = corner_cycle.index(position)
            except ValueError:
                start_idx = 0
            for i, ffmpeg_idx in enumerate(image_input_indices):
                pos = corner_cycle[(start_idx + i) % len(corner_cycle)]
                overlay_inputs.append((ffmpeg_idx, pos))
    elif image_source and isinstance(image_source, str):
        # When image_source is specified (e.g. "image_a"), overlay only that input
        # Map image_a → index 1, image_b → index 2, etc.
        source_map = {"image_a": 1, "image_b": 2, "image_c": 3, "image_d": 4}
        target_idx = source_map.get(image_source)
        if target_idx and target_idx <= n:
            overlay_inputs = [(target_idx, position)]
        else:
            # Fallback: overlay the first extra input
            overlay_inputs = [(1, position)]
    else:
        # No specific source — overlay all extras
        # Auto-assign positions when multiple overlays
        corner_cycle = ["top-left", "top-right", "bottom-right", "bottom-left"]
        if n == 1:
            overlay_inputs = [(1, position)]
        else:
            overlay_inputs = []
            try:
                start_idx = corner_cycle.index(position)
            except ValueError:
                start_idx = 0
            for i in range(n):
                pos = corner_cycle[(start_idx + i) % len(corner_cycle)]
                overlay_inputs.append((i + 1, pos))

    # Check for custom x/y expressions (LLM sometimes passes ffmpeg
    # expressions for animation even when using overlay_image)
    custom_x = p.get("x", None)
    custom_y = p.get("y", None)
    has_custom_xy = custom_x is not None and custom_y is not None

    fc_parts = []
    for oi, (idx, pos) in enumerate(overlay_inputs):
        ovl_label = f"[_ovl{oi}]"

        # Scale the overlay — always preserve alpha for PNG transparency
        scale_expr = f"[{idx}:v]format=rgba,scale=iw*{scale}:ih*{scale}"
        if opacity < 1.0:
            scale_expr += f",colorchannelmixer=aa={opacity}"
        scale_expr += ovl_label
        fc_parts.append(scale_expr)

        # Chain: first overlay takes [0:v], subsequent take previous output
        if has_custom_xy:
            # Use custom expressions with eval=frame for animation
            xy = f"x={custom_x}:y={custom_y}:eval=frame"
        else:
            xy = pos_map.get(pos, pos_map["bottom-right"])

        if oi == 0:
            src = "[0:v]"
        else:
            src = f"[_tmp{oi - 1}]"

        if oi < len(overlay_inputs) - 1:
            # Intermediate: label the output for next overlay
            fc_parts.append(f"{src}{ovl_label}overlay={xy}[_tmp{oi}]")
        else:
            # Last overlay: no output label (becomes final output)
            fc_parts.append(f"{src}{ovl_label}overlay={xy}")

    return [], [], [], ";".join(fc_parts)


def _f_watermark(p):
    """Apply a semi-transparent watermark overlay.

    Thin wrapper around overlay_image with watermark-appropriate defaults.
    """
    # Set watermark defaults, but allow user overrides
    p.setdefault("opacity", 0.3)
    p.setdefault("scale", 0.15)
    p.setdefault("position", "bottom-right")
    p.setdefault("margin", 10)
    return _f_overlay_image(p)


def _f_concat(p):
    """Concatenate the main video with extra video/image inputs sequentially.

    Each extra input becomes a segment. Still images are looped for
    `still_duration` seconds. All segments are scaled to the same
    resolution before concatenation.

    When extra audio inputs are connected (via audio_a, audio_b, ...),
    audio is included in the concat (a=1). Segments without a matching
    audio input get silence via anullsrc.

    Parameters:
        width:          Output width (default 1920)
        height:         Output height (default 1080)
        still_duration: Seconds to display each still image (default 5)
        transition:     If specified, auto-redirect to xfade handler
    """
    # Auto-redirect to xfade when a transition is requested
    transition = p.get("transition")
    if transition and str(transition).lower() not in ("none", "cut", ""):
        return _f_xfade(p)
    width = int(p.get("width", p.get("_input_width", 1920)))
    height = int(p.get("height", p.get("_input_height", 1080)))
    still_dur = float(p.get("still_duration", 5.0))
    n_extra = int(p.get("_extra_input_count", 0))

    # Build segment list: main video (idx=0) + extras (idx=1,2,...)
    # Skip inputs reserved by other skills (e.g. overlay_image's image_source)
    exclude = p.get("_exclude_inputs", set())
    extra_paths = p.get("_extra_input_paths", [])
    segments = [(0, True)]  # (ffmpeg_idx, is_video)
    for i in range(n_extra):
        ffmpeg_idx = i + 1
        if ffmpeg_idx in exclude:
            continue  # Reserved by another skill (e.g. overlay)
        is_video = _is_video_file(extra_paths[i]) if i < len(extra_paths) else False
        segments.append((ffmpeg_idx, is_video))

    total = len(segments)
    if total < 2:
        return [], [], [], ""

    # Check if audio was pre-muxed into the video inputs
    has_audio = bool(p.get("_has_embedded_audio", False))

    fps = int(p.get("_input_fps", 25))
    parts = []
    concat_labels = []

    for i, (idx, is_video) in enumerate(segments):
        vlbl = f"[_cv{i}]"
        if is_video:
            parts.append(
                f"[{idx}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,"
                f"setpts=PTS-STARTPTS,fps={fps}{vlbl}"
            )
        else:
            n_frames = int(still_dur * fps)
            parts.append(
                f"[{idx}:v]loop=loop={n_frames}:size=1:start=0,"
                f"setpts=N/{fps}/TB,"
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1{vlbl}"
            )
        concat_labels.append(vlbl)

        if has_audio:
            albl = f"[_ca{i}]"
            if is_video:
                # Video input: read its embedded audio
                parts.append(f"[{idx}:a]aresample=44100,asetpts=PTS-STARTPTS{albl}")
            else:
                # Still image: no audio stream — generate silence
                dur = still_dur
                parts.append(
                    f"anullsrc=r=44100:cl=stereo,atrim=0:{dur},asetpts=PTS-STARTPTS{albl}"
                )
            concat_labels.append(albl)

    concat_input = "".join(concat_labels)
    if has_audio:
        parts.append(f"{concat_input}concat=n={total}:v=1:a=1")
    else:
        parts.append(f"{concat_input}concat=n={total}:v=1:a=0")

    return [], [], [], ";".join(parts)


def _f_xfade(p):
    """Concatenate segments with smooth xfade transitions between them.

    Supports transitions: fade, fadeblack, fadewhite, wipeleft, wiperight,
    wipeup, wipedown, slideleft, slideright, slideup, slidedown,
    circlecrop, rectcrop, distance, dissolve, pixelize, radial, smoothleft,
    smoothright, smoothup, smoothdown, squeezev, squeezeh.

    Parameters:
        transition: Transition type (default "fade")
        duration:   Transition duration in seconds (default 1.0)
        still_duration: Seconds to display each still image (default 4.0)
        width/height: Output resolution (default 1920x1080)
    """
    transition = sanitize_text_param(str(p.get("transition", "fade")))
    trans_dur = float(p.get("duration", 1.0))
    still_dur = float(p.get("still_duration", 4.0))
    width = int(p.get("width", p.get("_input_width", 1920)))
    height = int(p.get("height", p.get("_input_height", 1080)))
    n_extra = int(p.get("_extra_input_count", 0))

    extra_paths = p.get("_extra_input_paths", [])
    exclude = p.get("_exclude_inputs", set())
    segments = [(0, True)]
    for i in range(n_extra):
        ffmpeg_idx = i + 1
        if ffmpeg_idx in exclude:
            continue  # Reserved by another skill (e.g. overlay)
        is_video = _is_video_file(extra_paths[i]) if i < len(extra_paths) else False
        segments.append((ffmpeg_idx, is_video))

    total = len(segments)
    if total < 2:
        return [], [], [], ""

    fps = int(p.get("_input_fps", 25))
    parts = []

    # Step 1: Scale/prepare all segments
    for i, (idx, is_video) in enumerate(segments):
        lbl = f"[_xv{i}]"
        if is_video:
            parts.append(
                f"[{idx}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={fps}{lbl}"
            )
        else:
            n_frames = int(still_dur * fps)
            parts.append(
                f"[{idx}:v]loop=loop={n_frames}:size=1:start=0,"
                f"setpts=N/{fps}/TB,"
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1{lbl}"
            )

    # Build per-segment durations for accurate offset calculation.
    # Segment 0 = main video (_video_duration); segments 1+ = extra inputs.
    video_dur = float(p.get("_video_duration", still_dur))
    seg_durations = []
    for i, (idx, is_video) in enumerate(segments):
        if i == 0:
            seg_durations.append(video_dur if is_video else still_dur)
        elif is_video and idx - 1 < len(extra_paths):
            probed = _probe_duration(extra_paths[idx - 1])
            seg_durations.append(probed if probed > 0 else video_dur)
        else:
            seg_durations.append(still_dur)

    cumulative = seg_durations[0]
    prev_label = "[_xv0]"

    # Determine if we'll have audio crossfade — if so, we need explicit
    # output labels + -map flags because ffmpeg can't auto-bind two
    # unlabeled outputs.
    has_audio = bool(p.get("_has_embedded_audio", False))
    audio_segments = []
    if has_audio:
        for i, (idx, is_video) in enumerate(segments):
            if is_video:
                audio_segments.append((i, idx))
    need_map = has_audio and len(audio_segments) >= 2

    for i in range(1, total):
        next_label = f"[_xv{i}]"
        offset = max(0, cumulative - trans_dur)
        if i < total - 1:
            out_label = f"[_xf{i}]"
            parts.append(
                f"{prev_label}{next_label}xfade=transition={transition}:"
                f"duration={trans_dur}:offset={offset}{out_label}"
            )
            prev_label = out_label
        else:
            # Last xfade — label the output when audio crossfade follows
            if need_map:
                parts.append(
                    f"{prev_label}{next_label}xfade=transition={transition}:"
                    f"duration={trans_dur}:offset={offset}[_vout]"
                )
            else:
                parts.append(
                    f"{prev_label}{next_label}xfade=transition={transition}:"
                    f"duration={trans_dur}:offset={offset}"
                )
        cumulative += seg_durations[i] - trans_dur

    # Step 3: Audio crossfade (when audio is embedded in video inputs)
    opts = []
    if need_map:
        # Prepare audio streams (only for segments with audio)
        for ai, (orig_i, idx) in enumerate(audio_segments):
            parts.append(
                f"[{idx}:a]aresample=44100,asetpts=PTS-STARTPTS[_xa{ai}]"
            )

        # Chain acrossfade transitions
        n_audio = len(audio_segments)
        prev_alabel = "[_xa0]"
        for i in range(1, n_audio):
            next_alabel = f"[_xa{i}]"
            if i < n_audio - 1:
                out_alabel = f"[_xaf{i}]"
                parts.append(
                    f"{prev_alabel}{next_alabel}acrossfade=d={trans_dur}:"
                    f"c1=tri:c2=tri{out_alabel}"
                )
                prev_alabel = out_alabel
            else:
                parts.append(
                    f"{prev_alabel}{next_alabel}acrossfade=d={trans_dur}:"
                    f"c1=tri:c2=tri[_aout]"
                )

        opts = ["-map", "[_vout]", "-map", "[_aout]"]

    return [], [], opts, ";".join(parts)


def _f_split_screen(p):
    """Show videos/images side-by-side or top-to-bottom.

    Parameters:
        layout: "horizontal" (hstack) or "vertical" (vstack) (default "horizontal")
        width:  Per-cell width (default 960)
        height: Per-cell height (default 540)
        duration: Output duration in seconds for still images (default 10)
    """
    layout = str(p.get("layout", "horizontal")).lower()
    cell_w = int(p.get("width", 960))
    cell_h = int(p.get("height", 540))
    duration = float(p.get("duration", 10.0))
    n_extra = int(p.get("_extra_input_count", 0))

    cells = [0]
    for i in range(n_extra):
        cells.append(i + 1)

    total = len(cells)
    if total < 2:
        return [], [], [], ""

    fps = 25
    parts = []
    labels = []

    for i, idx in enumerate(cells):
        lbl = f"[_sp{i}]"
        extra_paths = p.get("_extra_input_paths", [])
        is_video = (idx == 0) or (idx - 1 < len(extra_paths) and _is_video_file(extra_paths[idx - 1]))
        if is_video:
            # Main video: scale, maintain aspect ratio
            parts.append(
                f"[{idx}:v]scale={cell_w}:{cell_h}:force_original_aspect_ratio=decrease,"
                f"pad={cell_w}:{cell_h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1{lbl}"
            )
        else:
            # Extra: loop still images for the duration
            n_frames = int(duration * fps)
            parts.append(
                f"[{idx}:v]loop=loop={n_frames}:size=1:start=0,"
                f"setpts=N/{fps}/TB,"
                f"scale={cell_w}:{cell_h}:force_original_aspect_ratio=decrease,"
                f"pad={cell_w}:{cell_h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1{lbl}"
            )
        labels.append(lbl)

    stack_filter = "hstack" if layout == "horizontal" else "vstack"
    label_str = "".join(labels)
    parts.append(f"{label_str}{stack_filter}=inputs={total}")

    opts = []
    if duration > 0:
        opts = ["-t", str(duration)]

    return [], [], opts, ";".join(parts)


def _f_animated_overlay(p):
    """Overlay extra images with time-based animated motion.

    Supports multiple overlay images — each gets its own motion with
    staggered speeds so they move independently.

    Parameters:
        animation:  Motion preset (default "scroll_right")
        speed:      Motion speed multiplier (default 1.0)
        scale:      Overlay size relative to video width (default 0.2)
        opacity:    Overlay opacity 0.0-1.0 (default 1.0)
    """
    animation = sanitize_text_param(str(p.get("animation", "scroll_right")))
    speed = float(p.get("speed", 1.0))
    scale = float(p.get("scale", 0.2))
    opacity = float(p.get("opacity", 1.0))
    n = int(p.get("_extra_input_count", 0))

    if n < 1:
        return [], [], [], ""

    # Determine the ffmpeg input indices for overlay images
    image_input_indices = p.get("_image_input_indices", [])
    if not image_input_indices:
        image_input_indices = [1]

    fc_parts = []

    # Scale each overlay image
    for oi, ovl_idx in enumerate(image_input_indices):
        ovl_label = f"[_ovl{oi}]"
        ovl_prep = f"[{ovl_idx}:v]scale=iw*{scale}:ih*{scale}"
        if opacity < 1.0:
            ovl_prep += f",format=rgba,colorchannelmixer=aa={opacity}"
        ovl_prep += ovl_label
        fc_parts.append(ovl_prep)

    # Build chained overlay filters — each image gets staggered motion
    for oi, _ovl_idx in enumerate(image_input_indices):
        # Stagger speed per overlay so they move independently
        px = max(1, int(2 * speed) + oi)
        py = px + 1

        motion_presets = {
            "scroll_right": f"x=mod(n*{px}\\,W):y=H-h-20",
            "scroll_left": f"x=W-mod(n*{px}\\,W+w):y=H-h-20",
            "scroll_up": f"x=W-w-20:y=H-mod(n*{px}\\,H+h)",
            "scroll_down": f"x=W-w-20:y=mod(n*{px}\\,H+h)-h",
            "float": f"x=W/2-w/2+sin(n*0.02*{speed + oi * 0.3})*W/4:y=H/2-h/2+cos(n*0.03*{speed + oi * 0.3})*H/4",
            "bounce": f"x=abs(mod(n*{px}\\,2*(W-w))-(W-w)):y=abs(mod(n*{py}\\,2*(H-h))-(H-h))",
            "slide_in": f"x=min(n*{px}\\,W-w-20):y=H-h-20",
            "slide_in_top": f"x=W/2-w/2:y=min(n*{px}-h\\,20)",
        }

        motion = motion_presets.get(animation, motion_presets["scroll_right"])
        ovl_label = f"[_ovl{oi}]"

        # Chain: first overlay takes [0:v], subsequent take previous output
        if oi == 0:
            src = "[0:v]"
        else:
            src = f"[_tmp{oi - 1}]"

        if oi < len(image_input_indices) - 1:
            # Intermediate: label the output for next overlay
            fc_parts.append(f"{src}{ovl_label}overlay={motion}:eval=frame[_tmp{oi}]")
        else:
            # Last overlay: no output label (becomes final output)
            fc_parts.append(f"{src}{ovl_label}overlay={motion}:eval=frame")

    return [], [], [], ";".join(fc_parts)


def _f_pip(p):
    """Picture-in-picture: overlay a second video in a corner."""
    position = str(p.get("position", "bottom_right")).lower()
    scale = float(p.get("scale", 0.25))
    margin = int(p.get("margin", 20))
    border = int(p.get("border", 0))
    border_color = sanitize_text_param(str(p.get("border_color", "white")))

    # Scale the overlay relative to main video
    scale_filter = f"[1:v]scale=iw*{scale}:-1"

    # Add border via pad if requested
    if border > 0:
        # pad adds border_px on each side; keep the content centered
        b = border
        scale_filter += (
            f"[_pip_scaled];"
            f"[_pip_scaled]pad="
            f"iw+{b*2}:ih+{b*2}:{b}:{b}:"
            f"color={border_color}"
        )

    scale_filter += "[pip]"

    # Position mapping
    pos_map = {
        "bottom_right": f"main_w-overlay_w-{margin}:main_h-overlay_h-{margin}",
        "bottom_left": f"{margin}:main_h-overlay_h-{margin}",
        "top_right": f"main_w-overlay_w-{margin}:{margin}",
        "top_left": f"{margin}:{margin}",
        "center": "(main_w-overlay_w)/2:(main_h-overlay_h)/2",
    }
    xy = pos_map.get(position, pos_map["bottom_right"])

    fc = f"{scale_filter};[0:v][pip]overlay={xy}:shortest=1"

    # Optional audio mixing — blend audio from both inputs
    audio_mix = p.get("audio_mix", False)
    if isinstance(audio_mix, str):
        audio_mix = audio_mix.lower() in ("true", "1", "yes")
    if audio_mix:
        fc += ";[0:a][1:a]amix=inputs=2:duration=longest:dropout_transition=2[_aout]"
        return [], [], ["-map", "[_aout]"], fc

    return [], [], [], fc
