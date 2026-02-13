"""FFMPEGA Composite skill handlers.

Auto-generated from composer.py — do not edit directly.
"""

try:
    from ...core.sanitize import sanitize_text_param
except ImportError:
    try:
        from core.sanitize import sanitize_text_param
    except ImportError:
        def sanitize_text_param(s): return s

_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".ts", ".m4v"}

def _is_video_file(path):
    """Check if a file path is a video based on its extension."""
    import os
    return os.path.splitext(path)[1].lower() in _VIDEO_EXTENSIONS

def _f_add_text(p):
    text = sanitize_text_param(str(p.get("text", "")))
    size = p.get("size", 48)
    color = sanitize_text_param(str(p.get("color", "white")))
    font = sanitize_text_param(str(p.get("font", "Sans")))
    border = p.get("border", True)
    position = p.get("position", "center")

    pos_map = {
        "center": "x=(w-text_w)/2:y=(h-text_h)/2",
        "top": "x=(w-text_w)/2:y=text_h",
        "bottom": "x=(w-text_w)/2:y=h-text_h*2",
        "top_left": "x=text_h:y=text_h",
        "top_right": "x=w-text_w-text_h:y=text_h",
        "bottom_left": "x=text_h:y=h-text_h*2",
        "bottom_right": "x=w-text_w-text_h:y=h-text_h*2",
    }
    xy = pos_map.get(position, pos_map["center"])
    border_style = ":borderw=3:bordercolor=black" if border else ""

    drawtext = (
        f"drawtext=text='{text}':fontsize={size}"
        f":fontcolor={color}:font='{font}'"
        f":{xy}{border_style}"
    )
    return [drawtext], [], []


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

    fps = 25
    # Scale all inputs to same cell size (maintain aspect ratio + pad)
    # Still images need loop+setpts to produce frames for the full duration.
    parts = []
    for i, idx in enumerate(cells):
        if idx == 0 and include_video:
            # Main video: just scale, it already has frames
            parts.append(
                f"[{idx}:v]scale={cell_w}:{cell_h}:force_original_aspect_ratio=decrease,"
                f"pad={cell_w}:{cell_h}:(ow-iw)/2:(oh-ih)/2:{bg},setsar=1[_g{i}]"
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
    width = int(p.get("width", 1920))
    height = int(p.get("height", 1080))
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
    """
    position = p.get("position", "bottom-right")
    scale = float(p.get("scale", 0.25))
    opacity = float(p.get("opacity", 1.0))
    margin = int(p.get("margin", 10))
    n = int(p.get("_extra_input_count", 0))

    if n < 1:
        return [], [], [], ""

    pos_map = {
        "top-left": f"{margin}:{margin}",
        "top-right": f"W-w-{margin}:{margin}",
        "bottom-left": f"{margin}:H-h-{margin}",
        "bottom-right": f"W-w-{margin}:H-h-{margin}",
        "center": "(W-w)/2:(H-h)/2",
    }

    # Auto-assign positions when multiple overlays
    corner_cycle = ["top-left", "top-right", "bottom-right", "bottom-left"]
    if n == 1:
        positions = [position]
    else:
        # First overlay gets the requested position, rest cycle through corners
        positions = []
        # Start cycling from the requested position
        try:
            start_idx = corner_cycle.index(position)
        except ValueError:
            start_idx = 0
        for i in range(n):
            pos = corner_cycle[(start_idx + i) % len(corner_cycle)]
            positions.append(pos)

    fc_parts = []
    for i in range(n):
        idx = i + 1  # extra inputs: [1:v], [2:v], ...
        ovl_label = f"[_ovl{i}]"

        # Scale the overlay — always preserve alpha for PNG transparency
        scale_expr = f"[{idx}:v]format=rgba,scale=iw*{scale}:ih*{scale}"
        if opacity < 1.0:
            scale_expr += f",colorchannelmixer=aa={opacity}"
        scale_expr += ovl_label
        fc_parts.append(scale_expr)

        # Chain: first overlay takes [0:v], subsequent take previous output
        xy = pos_map.get(positions[i], pos_map["bottom-right"])
        if i == 0:
            src = "[0:v]"
        else:
            src = f"[_tmp{i - 1}]"

        if i < n - 1:
            # Intermediate: label the output for next overlay
            fc_parts.append(f"{src}{ovl_label}overlay={xy}[_tmp{i}]")
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
    """
    width = int(p.get("width", 1920))
    height = int(p.get("height", 1080))
    still_dur = float(p.get("still_duration", 5.0))
    n_extra = int(p.get("_extra_input_count", 0))

    # Build segment list: main video (idx=0) + extras (idx=1,2,...)
    extra_paths = p.get("_extra_input_paths", [])
    segments = [(0, True)]  # (ffmpeg_idx, is_video)
    for i in range(n_extra):
        is_video = _is_video_file(extra_paths[i]) if i < len(extra_paths) else False
        segments.append((i + 1, is_video))

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
            # Audio is embedded in the video — just read it
            parts.append(f"[{idx}:a]aresample=44100,asetpts=PTS-STARTPTS{albl}")
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
    width = int(p.get("width", 1920))
    height = int(p.get("height", 1080))
    n_extra = int(p.get("_extra_input_count", 0))

    extra_paths = p.get("_extra_input_paths", [])
    segments = [(0, True)]
    for i in range(n_extra):
        is_video = _is_video_file(extra_paths[i]) if i < len(extra_paths) else False
        segments.append((i + 1, is_video))

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

    # Step 2: Chain xfade transitions (video)
    # xfade takes exactly 2 inputs and produces 1 output. Chain them:
    # [_xv0][_xv1] xfade → [_xf0]; [_xf0][_xv2] xfade → [_xf1]; etc.
    # The offset for each xfade is: cumulative_duration - transition_duration
    video_dur = float(p.get("_video_duration", still_dur))
    cumulative = video_dur if segments[0][1] else still_dur
    prev_label = "[_xv0]"

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
            # Last xfade: no output label (goes to default output)
            parts.append(
                f"{prev_label}{next_label}xfade=transition={transition}:"
                f"duration={trans_dur}:offset={offset}"
            )
        cumulative += still_dur - trans_dur

    # Step 3: Audio crossfade (when audio is embedded in video inputs)
    has_audio = bool(p.get("_has_embedded_audio", False))
    if has_audio:
        # Filter to only segments that actually have an audio stream
        audio_segments = []
        for i, (idx, is_video) in enumerate(segments):
            if is_video:
                audio_segments.append((i, idx))
        # Only do audio crossfade if at least 2 segments have audio
        if len(audio_segments) >= 2:
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
                        f"c1=tri:c2=tri"
                    )

    return [], [], [], ";".join(parts)


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
    """Overlay an extra image with time-based animated motion.

    The overlay image (from image_a) moves across the frame using
    eval=frame expressions in the overlay filter.

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

    # Scale the overlay image relative to main video width
    # [0:v] = main video, [1:v] = overlay image
    fc_parts = []

    # Apply opacity to overlay if < 1.0
    ovl_prep = f"[1:v]scale=iw*{scale}:ih*{scale}"
    if opacity < 1.0:
        ovl_prep += f",format=rgba,colorchannelmixer=aa={opacity}"
    ovl_prep += "[_ovl]"
    fc_parts.append(ovl_prep)

    # Build motion expression based on animation preset
    # All use overlay's eval=frame mode for per-frame position updates
    px_per_frame = max(1, int(2 * speed))

    motion_presets = {
        "scroll_right": f"x='mod(n*{px_per_frame},W)':y='H-h-20'",
        "scroll_left": f"x='W-mod(n*{px_per_frame},W+w)':y='H-h-20'",
        "scroll_up": f"x='W-w-20':y='H-mod(n*{px_per_frame},H+h)'",
        "scroll_down": f"x='W-w-20':y='mod(n*{px_per_frame},H+h)-h'",
        "float": f"x='W/2-w/2+sin(n*0.02*{speed})*W/4':y='H/2-h/2+cos(n*0.03*{speed})*H/4'",
        "bounce": f"x='abs(mod(n*{px_per_frame},2*(W-w))-(W-w))':y='abs(mod(n*{px_per_frame+1},2*(H-h))-(H-h))'",
        "slide_in": f"x='min(n*{px_per_frame},W-w-20)':y='H-h-20'",
        "slide_in_top": f"x='W/2-w/2':y='min(n*{px_per_frame}-h,20)'",
    }

    motion = motion_presets.get(animation, motion_presets["scroll_right"])
    fc_parts.append(f"[0:v][_ovl]overlay={motion}:eval=frame")

    return [], [], [], ";".join(fc_parts)


def _f_text_overlay(p):
    """Draw text on the video using ffmpeg's drawtext filter.

    Parameters:
        text:       Text to display (required)
        preset:     Style preset: title, subtitle, lower_third, caption (default "title")
        font:       Font family (default "sans")
        fontsize:   Font size in pixels (default auto based on preset)
        fontcolor:  Text color (default "white")
        borderw:    Text border/outline width (default 2)
        bordercolor: Border color (default "black")
        x:          Horizontal position expression (default auto)
        y:          Vertical position expression (default auto)
        start:      Start time in seconds (default 0)
        duration:   Display duration in seconds (0 = entire video, default 0)
        background: Background box color (default "" = none)
    """
    text = sanitize_text_param(str(p.get("text", "Hello")))
    preset = str(p.get("preset", "title")).lower()
    font = sanitize_text_param(str(p.get("font", "sans")))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))
    borderw = int(p.get("borderw", 2))
    bordercolor = sanitize_text_param(str(p.get("bordercolor", "black")))
    bg = sanitize_text_param(str(p.get("background", "")))
    start = float(p.get("start", 0))
    duration = float(p.get("duration", 0))

    # Preset defaults
    preset_config = {
        "title": {"fontsize": 72, "x": "(w-text_w)/2", "y": "(h-text_h)/2"},
        "subtitle": {"fontsize": 36, "x": "(w-text_w)/2", "y": "h-text_h-60"},
        "lower_third": {"fontsize": 32, "x": "40", "y": "h-text_h-40"},
        "caption": {"fontsize": 28, "x": "(w-text_w)/2", "y": "h-text_h-30"},
        "top": {"fontsize": 48, "x": "(w-text_w)/2", "y": "40"},
    }
    cfg = preset_config.get(preset, preset_config["title"])
    fontsize = int(p.get("fontsize", cfg["fontsize"]))
    x_pos = str(p.get("x", cfg["x"]))
    y_pos = str(p.get("y", cfg["y"]))

    # Build drawtext filter
    dt = (
        f"drawtext=text='{text}':"
        f"font='{font}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"borderw={borderw}:"
        f"bordercolor={bordercolor}:"
        f"x={x_pos}:y={y_pos}"
    )

    # Background box
    if bg:
        dt += f":box=1:boxcolor={bg}:boxborderw=8"

    # Time-based enable/disable
    if duration > 0:
        end = start + duration
        dt += f":enable='between(t,{start},{end})'"
    elif start > 0:
        dt += f":enable='gte(t,{start})'"

    return [dt], [], []


def _f_pip(p):
    """Picture-in-picture: overlay a second video in a corner."""
    position = str(p.get("position", "bottom_right")).lower()
    scale = float(p.get("scale", 0.25))
    margin = int(p.get("margin", 20))

    # Scale the overlay relative to main video
    scale_expr = f"[1:v]scale=iw*{scale}:-1[pip]"

    # Position mapping
    pos_map = {
        "bottom_right": f"main_w-overlay_w-{margin}:main_h-overlay_h-{margin}",
        "bottom_left": f"{margin}:main_h-overlay_h-{margin}",
        "top_right": f"main_w-overlay_w-{margin}:{margin}",
        "top_left": f"{margin}:{margin}",
        "center": "(main_w-overlay_w)/2:(main_h-overlay_h)/2",
    }
    xy = pos_map.get(position, pos_map["bottom_right"])

    fc = f"{scale_expr};[0:v][pip]overlay={xy}:shortest=1"
    return [], [], [], fc


def _f_burn_subtitles(p):
    """Burn/hardcode subtitles from .srt/.ass file into video."""
    path = sanitize_text_param(str(p.get("path", "subtitles.srt")))
    fontsize = int(p.get("fontsize", 24))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))

    # Map common color names to ASS &HBBGGRR format (BGR, not RGB)
    color_map = {
        "white": "&H00FFFFFF",
        "black": "&H00000000",
        "red": "&H000000FF",
        "green": "&H0000FF00",
        "blue": "&H00FF0000",
        "yellow": "&H0000FFFF",
        "cyan": "&H00FFFF00",
        "magenta": "&H00FF00FF",
    }
    ass_color = color_map.get(fontcolor.lower(), "&H00FFFFFF")

    # subtitles filter syntax
    style = f"FontSize={fontsize},PrimaryColour={ass_color}"
    vf = f"subtitles='{path}':force_style='{style}'"
    return [vf], [], []


def _f_countdown(p):
    """Animated countdown timer overlay."""
    start = int(p.get("start_from", 10))
    fontsize = int(p.get("fontsize", 96))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))
    x_pos = str(p.get("x", "(w-text_w)/2"))
    y_pos = str(p.get("y", "(h-text_h)/2"))

    dt = (
        f"drawtext=text='%{{eif\\:{start}-t\\:d}}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"x={x_pos}:y={y_pos}:"
        f"borderw=3:bordercolor=black:"
        f"enable='lte(t,{start})'"
    )
    return [dt], [], []


def _f_animated_text(p):
    """Drawtext with built-in animation presets."""
    text = sanitize_text_param(str(p.get("text", "Hello")))
    animation = str(p.get("animation", "fade_in")).lower()
    fontsize = int(p.get("fontsize", 64))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))
    start = float(p.get("start", 0))
    duration = float(p.get("duration", 3))
    end = start + duration

    base = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"borderw=2:bordercolor=black:"
        f"enable='between(t,{start},{end})':"
        f"x=(w-text_w)/2"
    )

    if animation == "fade_in":
        alpha_expr = f"alpha='if(lt(t,{start}+1),(t-{start}),1)'"
        base += f":y=(h-text_h)/2:{alpha_expr}"
    elif animation == "slide_up":
        y_expr = f"y='max(h-text_h-60-((t-{start})*100),0)'"
        base += f":{y_expr}"
    elif animation == "slide_down":
        y_expr = f"y='min((t-{start})*100,60)'"
        base += f":{y_expr}"
    elif animation == "typewriter":
        # Use text length truncation via enable
        base = (
            f"drawtext=text='{text}':"
            f"fontsize={fontsize}:"
            f"fontcolor={fontcolor}:"
            f"borderw=2:bordercolor=black:"
            f"enable='between(t,{start},{end})':"
            f"x=(w-text_w)/2:y=(h-text_h)/2"
        )
    else:  # default: centered static
        base += ":y=(h-text_h)/2"

    return [base], [], []


def _f_scrolling_text(p):
    """Vertical scrolling text (credits roll)."""
    text = sanitize_text_param(str(p.get("text", "Credits")))
    speed = int(p.get("speed", 60))
    fontsize = int(p.get("fontsize", 36))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))

    dt = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"borderw=2:bordercolor=black:"
        f"x=(w-text_w)/2:"
        f"y=h-t*{speed}"
    )
    return [dt], [], []


def _f_ticker(p):
    """Horizontal scrolling text (news ticker style)."""
    text = sanitize_text_param(str(p.get("text", "Breaking News")))
    speed = int(p.get("speed", 100))
    fontsize = int(p.get("fontsize", 32))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))
    y_pos = str(p.get("y", "h-text_h-20"))
    bg = sanitize_text_param(str(p.get("background", "black@0.6")))

    dt = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"borderw=1:bordercolor=black:"
        f"x=w-t*{speed}:"
        f"y={y_pos}"
    )
    if bg:
        dt += f":box=1:boxcolor={bg}:boxborderw=8"

    return [dt], [], []


def _f_lower_third(p):
    """Animated lower third: name plate with background bar."""
    text = sanitize_text_param(str(p.get("text", "John Doe")))
    subtext = sanitize_text_param(str(p.get("subtext", "")))
    fontsize = int(p.get("fontsize", 36))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))
    bg = sanitize_text_param(str(p.get("background", "black@0.7")))
    start = float(p.get("start", 0))
    duration = float(p.get("duration", 5))
    end = start + duration

    # Main name text
    dt_main = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"x=40:y=h-text_h-60:"
        f"box=1:boxcolor={bg}:boxborderw=12:"
        f"borderw=1:bordercolor=black:"
        f"enable='between(t,{start},{end})'"
    )

    vf = [dt_main]

    # Optional subtext (title/role)
    if subtext:
        sub_fontsize = max(fontsize - 10, 16)
        dt_sub = (
            f"drawtext=text='{subtext}':"
            f"fontsize={sub_fontsize}:"
            f"fontcolor={fontcolor}@0.8:"
            f"x=40:y=h-{sub_fontsize}-25:"
            f"box=1:boxcolor={bg}:boxborderw=8:"
            f"enable='between(t,{start},{end})'"
        )
        vf.append(dt_sub)

    return vf, [], []


def _f_typewriter_text(p):
    """Character-by-character reveal using text length + enable timing."""
    text = sanitize_text_param(str(p.get("text", "Hello World")))
    fontsize = int(p.get("fontsize", 48))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))
    speed = float(p.get("speed", 5))  # chars per second
    start = float(p.get("start", 0))
    x_pos = str(p.get("x", "(w-text_w)/2"))
    y_pos = str(p.get("y", "(h-text_h)/2"))

    # Build one drawtext per character with staggered enable times
    filters = []
    for i, ch in enumerate(text):
        if ch == ' ':
            continue  # spaces handled by positioning
        char_start = start + i / speed
        ch_safe = sanitize_text_param(ch)
        char_x = f"{x_pos}+{i}*{fontsize}*0.6"
        dt = (
            f"drawtext=text='{ch_safe}':"
            f"fontsize={fontsize}:"
            f"fontcolor={fontcolor}:"
            f"borderw=2:bordercolor=black:"
            f"x={char_x}:y={y_pos}:"
            f"enable='gte(t,{char_start})'"
        )
        filters.append(dt)

    # If no chars, return a simple drawtext
    if not filters:
        dt = (
            f"drawtext=text='{text}':"
            f"fontsize={fontsize}:"
            f"fontcolor={fontcolor}:"
            f"x={x_pos}:y={y_pos}"
        )
        filters = [dt]

    return filters, [], []


def _f_bounce_text(p):
    """Text with a bounce-in animation (drops in and settles)."""
    text = sanitize_text_param(str(p.get("text", "Hello")))
    fontsize = int(p.get("fontsize", 72))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))
    start = float(p.get("start", 0))
    duration = float(p.get("duration", 4))
    end = start + duration

    # Bounce uses abs(sin) for elastic ease
    y_expr = (
        f"y='(h-text_h)/2 - "
        f"abs(sin((t-{start})*5)*200*max(0,1-(t-{start})*2))'"
    )

    dt = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"borderw=3:bordercolor=black:"
        f"x=(w-text_w)/2:"
        f"{y_expr}:"
        f"enable='between(t,{start},{end})'"
    )
    return [dt], [], []


def _f_fade_text(p):
    """Text with smooth fade in and fade out."""
    text = sanitize_text_param(str(p.get("text", "Hello")))
    fontsize = int(p.get("fontsize", 64))
    fontcolor = sanitize_text_param(str(p.get("fontcolor", "white")))
    start = float(p.get("start", 0))
    duration = float(p.get("duration", 4))
    fade_time = float(p.get("fade_time", 1.0))
    end = start + duration

    # Alpha expression: fade in for first fade_time, full, fade out for last fade_time
    alpha = (
        f"alpha='if(lt(t,{start}+{fade_time}),(t-{start})/{fade_time},"
        f"if(gt(t,{end}-{fade_time}),({end}-t)/{fade_time},1))'"
    )

    dt = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fontcolor}:"
        f"borderw=2:bordercolor=black:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:"
        f"{alpha}:"
        f"enable='between(t,{start},{end})'"
    )
    return [dt], [], []


def _f_karaoke_text(p):
    """Color-fill text synced to time (karaoke highlight effect)."""
    text = sanitize_text_param(str(p.get("text", "Sing Along")))
    fontsize = int(p.get("fontsize", 48))
    base_color = sanitize_text_param(str(p.get("base_color", "gray")))
    fill_color = sanitize_text_param(str(p.get("fill_color", "yellow")))
    start = float(p.get("start", 0))
    duration = float(p.get("duration", 5))
    end = start + duration

    # Two drawtext layers: base (gray) underneath + fill (yellow) with progressive crop via x offset
    # The fill text is drawn starting from left, advancing rightward over the duration
    dt_base = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={base_color}:"
        f"borderw=2:bordercolor=black:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:"
        f"enable='between(t,{start},{end})'"
    )

    # Fill layer: use alpha expression that clips horizontally based on time progression
    # Progress goes from 0 to 1 over the duration, controls alpha via x position
    progress = f"(t-{start})/{duration}"
    dt_fill = (
        f"drawtext=text='{text}':"
        f"fontsize={fontsize}:"
        f"fontcolor={fill_color}:"
        f"borderw=2:bordercolor=black:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:"
        f"alpha='if(lt(x-((w-text_w)/2), text_w*{progress}), 1, 0)':"
        f"enable='between(t,{start},{end})'"
    )

    return [dt_base, dt_fill], [], []


