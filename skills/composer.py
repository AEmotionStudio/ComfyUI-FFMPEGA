"""Skill composition engine for building FFMPEG pipelines."""

from dataclasses import dataclass, field
from typing import Optional, Any
from pathlib import Path

from .registry import SkillRegistry, Skill, SkillCategory, ParameterType, get_registry
try:
    from ..core.executor.command_builder import CommandBuilder, FFMPEGCommand
    from ..core.sanitize import sanitize_text_param
except ImportError:
    from core.executor.command_builder import CommandBuilder, FFMPEGCommand
    from core.sanitize import sanitize_text_param

_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".ts", ".m4v"}


def _is_video_file(path: str) -> bool:
    """Return True if the file extension indicates a video file."""
    return Path(path).suffix.lower() in _VIDEO_EXTENSIONS



@dataclass
class PipelineStep:
    """A single step in a processing pipeline."""
    skill_name: str
    params: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    notes: Optional[str] = None


@dataclass
class Pipeline:
    """A complete processing pipeline."""
    steps: list[PipelineStep] = field(default_factory=list)
    input_path: Optional[str] = None
    output_path: Optional[str] = None
    extra_inputs: list[str] = field(default_factory=list)
    extra_audio_inputs: list[str] = field(default_factory=list)
    text_inputs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_step(
        self,
        skill_name: str,
        params: Optional[dict] = None,
        notes: Optional[str] = None,
    ) -> "Pipeline":
        """Add a step to the pipeline.

        Args:
            skill_name: Name of the skill to apply.
            params: Parameters for the skill.
            notes: Optional notes about this step.

        Returns:
            Self for chaining.
        """
        self.steps.append(PipelineStep(
            skill_name=skill_name,
            params=params or {},
            notes=notes,
        ))
        return self

    def remove_step(self, index: int) -> "Pipeline":
        """Remove a step from the pipeline.

        Args:
            index: Index of the step to remove.

        Returns:
            Self for chaining.
        """
        if 0 <= index < len(self.steps):
            self.steps.pop(index)
        return self

    def clear(self) -> "Pipeline":
        """Clear all steps from the pipeline.

        Returns:
            Self for chaining.
        """
        self.steps.clear()
        return self


class SkillComposer:
    """Composes skills into executable FFMPEG pipelines."""

    # Common aliases LLMs tend to use
    SKILL_ALIASES = {
        "overlay": "overlay_image",
        "pip": "picture_in_picture",
        "picture-in-picture": "picture_in_picture",
        "pictureinpicture": "picture_in_picture",
        "stabilize": "deshake",
        "grayscale": "monochrome",
        "greyscale": "monochrome",
        "black_and_white": "monochrome",
        "bw": "monochrome",
        "concatenate": "concat",
        "join": "concat",
        "transition": "xfade",
        "splitscreen": "split_screen",
        "side_by_side": "split_screen",
        "moving_overlay": "animated_overlay",
        "chroma_key": "chromakey",
        "green_screen": "chromakey",
        "luma_key": "lumakey",
        "color_hold": "colorhold",
        "sin_city": "colorhold",
        "color_key": "colorkey",
        "de_spill": "despill",
        "color_spill": "despill",
        "remove_bg": "remove_background",
        "background_removal": "remove_background",
        "text": "text_overlay",
        "drawtext": "text_overlay",
        "title": "text_overlay",
        "subtitle": "text_overlay",
        "caption": "text_overlay",
        "audio_mix": "mix_audio",
        "blend_audio": "mix_audio",
        "combine_audio": "mix_audio",
    }

    def __init__(self, registry: Optional[SkillRegistry] = None):
        """Initialize the composer.

        Args:
            registry: Skill registry to use. Uses global registry if not provided.
        """
        self.registry = registry or get_registry()

    def compose(self, pipeline: Pipeline) -> FFMPEGCommand:
        """Compose a pipeline into an FFMPEG command.

        Args:
            pipeline: Pipeline to compose.

        Returns:
            FFMPEGCommand ready for execution.

        Raises:
            ValueError: If pipeline is invalid.
        """
        if not pipeline.input_path:
            raise ValueError("Pipeline must have an input path")
        if not pipeline.output_path:
            raise ValueError("Pipeline must have an output path")

        builder = CommandBuilder()
        builder.input(pipeline.input_path)

        # Register extra inputs for multi-input skills (grid, slideshow, overlay)
        for extra in pipeline.extra_inputs:
            builder.input(extra)

        # Register image_path inputs as separate -i entries AFTER extra_inputs
        # so they don't inflate _extra_input_count (which xfade/concat use
        # to determine segment count).  Their ffmpeg indices start after
        # input[0] + extra_inputs.
        _image_paths = pipeline.metadata.get("_image_paths", [])
        _image_input_start = 1 + len(pipeline.extra_inputs)  # 0=main, 1..N=extras
        for img_path in _image_paths:
            builder.input(img_path)

        # Process each step
        video_filters = []
        audio_filters = []
        output_options = []
        complex_filters = []  # filter_complex strings from multi-stream skills

        # Pre-scan for skills that handle audio internally (xfade, concat)
        # so we can skip redundant audio_crossfade steps the LLM may add.
        _audio_embedded_skills = {"xfade", "concat"}
        step_names = {
            self.SKILL_ALIASES.get(s.skill_name, s.skill_name)
            for s in pipeline.steps if s.enabled
        }
        has_audio_embedding_skill = bool(step_names & _audio_embedded_skills)
        _overlay_seen = False  # Track first overlay step to dedup duplicates
        _xfade_transition_dur = None  # Captured from xfade steps for fade_to_black
        _xfade_still_dur = None  # still_duration from xfade for fade_to_black

        for step in pipeline.steps:
            if not step.enabled:
                continue

            # Resolve common aliases LLMs tend to use
            resolved_name = self.SKILL_ALIASES.get(step.skill_name, step.skill_name)
            skill = self.registry.get(resolved_name)
            if skill:
                step.skill_name = resolved_name  # update for debug output
            if not skill:
                import logging
                logging.getLogger("ffmpega").warning(
                    f"Skipping unknown skill '{step.skill_name}' — "
                    "not found in registry"
                )
                continue

            # Skip audio_crossfade when xfade/concat already handles audio
            # internally — LLMs sometimes add both, causing duplicate filters.
            if resolved_name == "audio_crossfade" and has_audio_embedding_skill:
                import logging
                logging.getLogger("ffmpega").info(
                    "Skipping redundant audio_crossfade — "
                    "xfade/concat already handles audio crossfade"
                )
                continue

            # Deduplicate overlay steps: when _image_paths provides multiple
            # images, the handler already processes ALL of them in one call.
            # LLMs often emit one overlay_image per image — skip duplicates.
            _overlay_names = {"overlay_image", "overlay", "animated_overlay", "moving_overlay"}
            if resolved_name in _overlay_names and _image_paths:
                if _overlay_seen:
                    import logging
                    logging.getLogger("ffmpega").info(
                        "Skipping duplicate %s step — all %d images "
                        "already handled by first overlay call",
                        resolved_name, len(_image_paths),
                    )
                    continue
                _overlay_seen = True

            # Capture xfade transition duration and still_duration for fade_to_black
            if resolved_name == "xfade" and _xfade_transition_dur is None:
                _xfade_transition_dur = float(step.params.get("duration", 1.0))
                _xfade_still_dur = float(step.params.get("still_duration", 4.0))

            # Resolve parameter aliases before filling defaults — so
            # "bitrate=128k" is resolved to "kbps=128" before the
            # default-fill loop checks whether "kbps" is present.
            step.params = self._normalize_params(skill, step.params)

            # ⚡ Perf: Single-pass parameter processing — merges default fill,
            # type coercion, range clamping, CHOICE normalization, and
            # validation into one iteration over skill.parameters instead
            # of four separate loops.  Reduces iterations by ~75%.
            for param in skill.parameters:
                name = param.name

                # 1. Fill defaults for missing params
                if name not in step.params:
                    if param.default is not None:
                        step.params[name] = param.default
                    continue  # No value to coerce/clamp/validate

                val = step.params[name]

                # 2. Type coercion (LLMs return imprecise types)
                if param.type == ParameterType.INT:
                    try:
                        val = int(float(val))
                    except (ValueError, TypeError):
                        pass
                elif param.type == ParameterType.FLOAT:
                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        pass
                elif param.type == ParameterType.BOOL:
                    if isinstance(val, str):
                        val = val.lower() in ("true", "1", "yes")

                # 3. Range clamp
                if param.type in (ParameterType.INT, ParameterType.FLOAT):
                    if isinstance(val, (int, float)):
                        if param.min_value is not None and val < param.min_value:
                            val = type(val)(param.min_value)
                        if param.max_value is not None and val > param.max_value:
                            val = type(val)(param.max_value)

                step.params[name] = val

                # 4. Normalize CHOICE values: LLMs often send underscores
                # where hyphens are expected (bottom_right → bottom-right)
                if (param.type == ParameterType.CHOICE
                        and isinstance(val, str)
                        and param.choices
                        and val not in param.choices):
                    normalized = val.replace("_", "-")
                    if normalized in param.choices:
                        step.params[name] = normalized
                        val = normalized

                # 5. Validate & drop invalid params to prevent injection
                p_valid, p_err = param.validate(val)
                if p_err and isinstance(p_err, str) and p_err.startswith("__autocorrect__:"):
                    # Apply auto-corrected value (e.g. fuzzy CHOICE match)
                    correction = p_err.split(":", 1)[1]
                    corr_name, corrected_value = correction.split("=", 1)
                    step.params[corr_name] = corrected_value
                elif not p_valid:
                    import logging
                    logging.getLogger("ffmpega").warning(
                        f"Security/Validation: Dropping invalid parameter '{name}' "
                        f"value '{val}' for skill '{step.skill_name}'. Using default."
                    )
                    del step.params[name]

            # Inject multi-input metadata for handlers that need it
            if pipeline.extra_inputs:
                step.params["_extra_input_count"] = len(pipeline.extra_inputs)
                step.params["_extra_input_paths"] = pipeline.extra_inputs
            if pipeline.text_inputs:
                step.params["_text_inputs"] = pipeline.text_inputs
            if pipeline.metadata.get("_has_embedded_audio"):
                step.params["_has_embedded_audio"] = True
            if "_input_fps" in pipeline.metadata:
                step.params["_input_fps"] = pipeline.metadata["_input_fps"]
            if "_video_duration" in pipeline.metadata:
                step.params["_video_duration"] = pipeline.metadata["_video_duration"]
            if "_input_width" in pipeline.metadata:
                step.params["_input_width"] = pipeline.metadata["_input_width"]
            if "_input_height" in pipeline.metadata:
                step.params["_input_height"] = pipeline.metadata["_input_height"]
            # Propagate xfade transition duration and still_duration so
            # fade_to_black can calculate the correct total output duration.
            if _xfade_transition_dur is not None:
                step.params["_xfade_duration"] = _xfade_transition_dur
            if _xfade_still_dur is not None:
                step.params["_still_duration"] = _xfade_still_dur

            # Inject image_path indices for overlay/animated_overlay handlers
            # These are separate from extra_inputs (which xfade/concat use)
            if _image_paths and resolved_name in (
                "overlay_image", "overlay", "watermark",
                "animated_overlay", "moving_overlay",
            ):
                # Tell overlay handlers about image_path inputs
                step.params["_image_input_indices"] = list(
                    range(_image_input_start, _image_input_start + len(_image_paths))
                )
                step.params["_image_paths"] = _image_paths
                # Bump extra_input_count so overlay knows about these inputs
                current = step.params.get("_extra_input_count", 0)
                step.params["_extra_input_count"] = current + len(_image_paths)

            # When concat/xfade runs alongside overlay_image, exclude
            # overlay-reserved inputs from concatenation.
            #
            # Two image input patterns exist:
            #   (a) Zero-memory path: images come via _image_paths and are
            #       added as ffmpeg inputs AFTER extra_inputs, starting
            #       at _image_input_start.
            #   (b) Legacy path: images are mixed into extra_inputs
            #       (e.g. /logo.png at extra_inputs[0] → ffmpeg idx 1).
            if resolved_name in ("concat", "xfade", "slideshow"):
                exclude = set()

                if _image_paths:
                    # --- Pattern (a): zero-memory image_path inputs ---
                    _source_idx_map = {}
                    _source_names = ["image_a", "image_b", "image_c", "image_d"]
                    for si, src_name in enumerate(_source_names):
                        if si < len(_image_paths):
                            _source_idx_map[src_name] = _image_input_start + si

                    for other in pipeline.steps:
                        other_name = self.SKILL_ALIASES.get(other.skill_name, other.skill_name)
                        if other_name == "overlay_image":
                            src = other.params.get("image_source")
                            if src and src in _source_idx_map:
                                exclude.add(_source_idx_map[src])
                            else:
                                # Auto-infer first image input
                                other.params["image_source"] = _source_names[0]
                                exclude.add(_image_input_start)
                        elif other_name == "animated_overlay":
                            for img_idx in range(
                                _image_input_start,
                                _image_input_start + len(_image_paths),
                            ):
                                exclude.add(img_idx)
                else:
                    # --- Pattern (b): images mixed into extra_inputs ---
                    _source_idx_map = {
                        "image_a": 1, "image_b": 2, "image_c": 3, "image_d": 4,
                    }
                    _idx_source_map = {v: k for k, v in _source_idx_map.items()}

                    for other in pipeline.steps:
                        other_name = self.SKILL_ALIASES.get(other.skill_name, other.skill_name)
                        if other_name == "overlay_image":
                            src = other.params.get("image_source")
                            if src and src in _source_idx_map:
                                exclude.add(_source_idx_map[src])
                            elif not src and pipeline.extra_inputs:
                                for ei, path in enumerate(pipeline.extra_inputs):
                                    if not _is_video_file(path):
                                        inferred_idx = ei + 1
                                        inferred_src = _idx_source_map.get(
                                            inferred_idx, "image_a"
                                        )
                                        other.params["image_source"] = inferred_src
                                        exclude.add(inferred_idx)
                                        break
                        elif other_name == "animated_overlay":
                            # Scan extra_inputs for the first non-video file
                            if pipeline.extra_inputs:
                                for ei, path in enumerate(pipeline.extra_inputs):
                                    if not _is_video_file(path):
                                        exclude.add(ei + 1)
                                        break

                if exclude:
                    step.params["_exclude_inputs"] = exclude

            # Get filters/options for this skill
            vf, af, opts, fc, input_opts = self._skill_to_filters(skill, step.params)
            video_filters.extend(vf)
            audio_filters.extend(af)
            output_options.extend(opts)
            if fc:
                complex_filters.append(fc)
            if input_opts:
                # Add input options to the main input (index 0)
                builder.add_input_options(pipeline.input_path, input_opts)

        # Resolve conflict between -an and audio filters (-af).
        # • `remove_audio` is an explicit user intent — it always wins,
        #   so we clear any audio filters.
        # • Skills like beat_sync/jump_cut emit -an *defensively* because
        #   frame-selection may desync audio.  If the pipeline also has
        #   explicit audio skills (bass, echo, …), the user clearly
        #   intends to keep audio, so we drop the defensive -an.
        if "-an" in output_options:
            if "remove_audio" in step_names:
                # Explicit removal — always honour, drop any audio filters
                audio_filters.clear()
            elif audio_filters:
                # Defensive -an from beat_sync etc. — audio filters win
                output_options = [o for o in output_options if o != "-an"]
            else:
                audio_filters.clear()  # truly strip audio

        # Apply filter_complex if any skill needs multi-stream processing
        if complex_filters:
            # Detect whether any skill produces audio inside filter_complex
            # (concat with a=1, xfade with audio crossfade).
            _audio_producing_skills = {"xfade", "concat"}
            audio_in_fc = bool(
                step_names & _audio_producing_skills
                and pipeline.metadata.get("_has_embedded_audio", False)
            )

            # Determine up-front whether we need to fold audio filters
            # into the filter_complex graph (when concat/xfade produce
            # audio inside filter_complex, -af would conflict).
            need_audio_fold = audio_in_fc and bool(audio_filters)

            # Chain multiple filter_complex blocks: when one skill's output
            # feeds into the next (e.g. concat → overlay), label the first
            # graph's output and replace [0:v] in subsequent graphs.
            #
            # When the first skill produces audio (concat a=1, xfade),
            # its filter produces TWO output pads (video + audio).
            # We label both: [_pipe_N_v][_pipe_N_a] so subsequent skills
            # chain from the video pad, and audio filters can be appended
            # to the audio pad.
            _fc_audio_label = None  # Track the audio output label

            if len(complex_filters) > 1:
                chained = []
                for ci, fc_block in enumerate(complex_filters):
                    is_last = (ci == len(complex_filters) - 1)

                    # Detect if this block produces audio (contains concat a=1,
                    # acrossfade from xfade, or amix from PiP audio mixing)
                    block_has_audio = audio_in_fc and ci == 0 and (
                        "a=1" in fc_block or "acrossfade" in fc_block
                        or "amix" in fc_block
                    )

                    if ci == 0:
                        if block_has_audio:
                            # Dual labels: video + audio output pads
                            v_label = f"[_pipe_{ci}_v]"
                            a_label = f"[_pipe_{ci}_a]"
                            # xfade/concat handlers already produce [_vout]
                            # and [_aout] labels — REPLACE them with our
                            # chaining labels instead of appending new ones.
                            rewired_block = fc_block
                            if "[_vout]" in rewired_block:
                                rewired_block = rewired_block.replace("[_vout]", v_label)
                            if "[_aout]" in rewired_block:
                                rewired_block = rewired_block.replace("[_aout]", a_label)
                            if rewired_block != fc_block:
                                # Labels were replaced — use the rewired block
                                chained.append(rewired_block)
                            else:
                                # No existing labels — append ours
                                chained.append(fc_block + v_label + a_label)
                            _fc_audio_label = a_label
                            # Strip handler's -map opts — we handle
                            # mapping for chained graphs ourselves.
                            _strip = {"[_vout]", "[_aout]"}
                            new_opts = []
                            skip_next = False
                            for oi, o in enumerate(output_options):
                                if skip_next:
                                    skip_next = False
                                    continue
                                if o == "-map" and oi + 1 < len(output_options) and output_options[oi + 1] in _strip:
                                    skip_next = True
                                    continue
                                new_opts.append(o)
                            output_options = new_opts
                        else:
                            pipe_label = f"[_pipe_{ci}]"
                            chained.append(fc_block + pipe_label)
                    elif not is_last:
                        # Middle graphs: consume previous pipe, label output
                        if _fc_audio_label:
                            prev_label = f"[_pipe_{ci - 1}_v]"
                        else:
                            prev_label = f"[_pipe_{ci - 1}]"
                        pipe_label = f"[_pipe_{ci}]"
                        rewired = fc_block.replace("[0:v]", prev_label)
                        chained.append(rewired + pipe_label)
                    else:
                        # Last graph: consume previous pipe
                        if _fc_audio_label and ci == 1:
                            prev_label = f"[_pipe_{ci - 1}_v]"
                        elif ci > 0:
                            prev_label = f"[_pipe_{ci - 1}]"
                        else:
                            prev_label = "[0:v]"
                        rewired = fc_block.replace("[0:v]", prev_label)
                        if _fc_audio_label:
                            # Concat/xfade produced a labeled audio pad;
                            # we MUST label the final video output so
                            # both pads can be -mapped.
                            chained.append(rewired + "[_vfinal]")
                        else:
                            chained.append(rewired)
                fc_graph = ";".join(chained)
            else:
                fc_graph = complex_filters[0]
                # Single filter_complex block that produces audio
                if audio_in_fc and ("a=1" in fc_graph or "acrossfade" in fc_graph):
                    if need_audio_fold:
                        # Replace existing labels — xfade/concat handlers
                        # already produce [_vout] and [_aout] labels.  We
                        # must replace them rather than append, otherwise
                        # the acrossfade filter ends up with multiple
                        # output labels (invalid ffmpeg syntax).
                        if "[_vout]" in fc_graph:
                            fc_graph = fc_graph.replace("[_vout]", "[_vfinal]")
                        else:
                            fc_graph += "[_vfinal]"
                        if "[_aout]" in fc_graph:
                            fc_graph = fc_graph.replace("[_aout]", "[_aout_pre]")
                        else:
                            fc_graph += "[_aout_pre]"
                        _fc_audio_label = "[_aout_pre]"

            # Multi-input skills (xfade, concat, split_screen, grid, slideshow)
            # handle their own scaling. Drop simple scale/pad video filters
            # to avoid double-scaling when the LLM adds a redundant resize.
            _self_scaling_skills = {
                "xfade", "concat", "split_screen", "grid", "slideshow",
            }
            if step_names & _self_scaling_skills:
                video_filters = [
                    f for f in video_filters
                    if not f.startswith("scale=") and not f.startswith("pad=")
                ]

            # Merge simple video filters into the filter_complex graph.
            # When xfade/concat is present, fade filters must go AFTER the
            # concat chain output (not before it on [0:v]), otherwise fade-out
            # only affects the first clip instead of the final result.
            _concat_skills = {"xfade", "concat"}
            _has_concat = bool(step_names & _concat_skills)

            if _has_concat and video_filters:
                # ALL video filters go post-xfade so they apply to the
                # combined output, not just the first (dummy) segment.
                pre_filters = []
                post_filters = list(video_filters)
            else:
                pre_filters = video_filters
                post_filters = []

            if pre_filters:
                vf_chain = ",".join(pre_filters)
                if "[0:v]" in fc_graph:
                    # Prepend simple filters before the complex graph
                    fc_graph = f"[0:v]{vf_chain}[_pre];" + fc_graph.replace("[0:v]", "[_pre]")
                elif "[_vout]" in fc_graph:
                    # Graph produces a labeled video output (xfade/concat) —
                    # chain filters from it so they apply to the combined
                    # output, not to a disconnected input stream.
                    fc_graph = fc_graph.replace("[_vout]", "[_vout_pre]")
                    fc_graph += f";[_vout_pre]{vf_chain}[_vout]"
                elif _has_concat:
                    # xfade/concat has an unlabeled output — add a label
                    # so we can chain from it, then apply the filters.
                    fc_graph += f"[_vout_pre];[_vout_pre]{vf_chain}[_vout]"
                else:
                    # Graph doesn't use [0:v] (e.g. grid/slideshow) —
                    # apply video filters as a separate unlabeled chain
                    fc_graph += f";[0:v]{vf_chain}"

            if post_filters:
                # Append fade filters after the final video output label
                fade_chain = ",".join(post_filters)
                if "[_vfinal]" in fc_graph:
                    fc_graph = fc_graph.replace("[_vfinal]", "[_vfade_pre]")
                    fc_graph += f";[_vfade_pre]{fade_chain}[_vfinal]"
                elif "[_vout]" in fc_graph:
                    fc_graph = fc_graph.replace("[_vout]", "[_vfade_pre]")
                    fc_graph += f";[_vfade_pre]{fade_chain}[_vout]"
                elif _has_concat:
                    # xfade/concat has an unlabeled output — add a label
                    # so we can chain fade from it.
                    fc_graph += f"[_vfade_pre];[_vfade_pre]{fade_chain}[_vout]"

            # Handle audio filters with filter_complex:
            # When audio-producing skills (concat/xfade) embed audio in the
            # filter graph, we MUST fold audio filters into the graph —
            # -af cannot coexist with filter_complex audio output.
            if _fc_audio_label and audio_filters:
                af_chain = ",".join(audio_filters)
                fc_graph += f";{_fc_audio_label}{af_chain}[_aout]"
                audio_filters = []  # Don't also emit -af
                # Add -map flags to route the correct output streams
                output_options.extend(["-map", "[_vfinal]", "-map", "[_aout]"])
            elif _fc_audio_label and "[_vfinal]" in fc_graph:
                # Concat/xfade produced audio but no audio filters to fold.
                # We still need -map to consume both labeled pads.
                output_options.extend(["-map", "[_vfinal]", "-map", _fc_audio_label])
            elif "[0:a]" in fc_graph and audio_filters:
                # Non-audio-producing filter_complex that consumes [0:a]
                # (e.g. waveform) — fold audio filters into graph
                af_chain = ",".join(audio_filters)
                fc_graph += f";[0:a]{af_chain}"
                audio_filters = []  # Don't also emit -af

            # When filter_complex produces a labeled [_vout] but no -map
            # has been added (no audio crossfade), we need to explicitly
            # map it so ffmpeg routes the video output correctly.
            # Audio is handled by the post-processing mux step, not here.
            if "[_vout]" in fc_graph and "-map" not in output_options:
                output_options.extend(["-map", "[_vout]"])

            builder.complex_filter(fc_graph)
            # Audio filters go via -af when not consumed by filter_complex
            for af in audio_filters:
                builder.af(af)
        else:
            # When replace_audio is present WITH audio filters, -af would
            # apply to input 0's audio (original), not input 1's (the
            # replacement).  Route [1:a] through filter_complex instead.
            # NOTE: -vf and -filter_complex CANNOT coexist, so when we
            # use filter_complex for audio, we must also fold video filters
            # into the graph.
            if "replace_audio" in step_names and audio_filters:
                fc_parts = []
                # Fold video filters into filter_complex
                if video_filters:
                    vf_chain = ",".join(video_filters)
                    fc_parts.append(f"[0:v]{vf_chain}[_vout]")
                # Fold audio filters into filter_complex
                af_chain = ",".join(audio_filters)
                fc_parts.append(f"[1:a]{af_chain}[_aout]")
                builder.complex_filter(";".join(fc_parts))

                # Replace -map 0:v / -map 1:a with labeled output pads
                new_opts = []
                i = 0
                while i < len(output_options):
                    if (output_options[i] == "-map"
                            and i + 1 < len(output_options)):
                        target = output_options[i + 1]
                        if target == "1:a":
                            new_opts.extend(["-map", "[_aout]"])
                            i += 2
                            continue
                        elif target == "0:v" and video_filters:
                            new_opts.extend(["-map", "[_vout]"])
                            i += 2
                            continue
                    new_opts.append(output_options[i])
                    i += 1
                output_options = new_opts
            else:
                # Simple path — no filter_complex conflict
                for vf in video_filters:
                    builder.vf(vf)
                for af in audio_filters:
                    builder.af(af)

        # Apply output options — deduplicate key-value flags like -c:v, -crf,
        # -preset etc.  When multiple skills emit the same flag (e.g. two
        # quality steps) FFMPEG can error on the duplicates.
        # Strategy: last writer wins for any flag starting with '-'.
        seen_flags: dict[str, int] = {}  # flag -> index in deduped list
        deduped_opts: list[str] = []
        i = 0
        while i < len(output_options):
            opt = output_options[i]
            if opt.startswith("-") and i + 1 < len(output_options) and not output_options[i + 1].startswith("-"):
                # Key-value pair like "-c:v libx264" or "-crf 23"
                flag, val = opt, output_options[i + 1]
                # -map intentionally allows duplicates (e.g. -map 0:v -map 1:a)
                if flag == "-map" or flag not in seen_flags:
                    seen_flags[flag] = len(deduped_opts)
                    deduped_opts.extend([flag, val])
                else:
                    # Replace the earlier occurrence
                    idx = seen_flags[flag]
                    deduped_opts[idx + 1] = val  # update value
                i += 2
            else:
                # Standalone flag like "-an" or "-y"
                if opt not in seen_flags:
                    seen_flags[opt] = len(deduped_opts)
                    deduped_opts.append(opt)
                i += 1

        builder.output_options(*deduped_opts)
        builder.output(pipeline.output_path)

        return builder.build()

    def _normalize_params(
        self,
        skill: Skill,
        params: dict,
    ) -> dict:
        """Resolve parameter aliases and strip unit suffixes.

        - Maps alias names (e.g. ``bitrate``) to the canonical parameter
          name (e.g. ``kbps``) using ``SkillParameter.aliases``.
        - Strips trailing unit suffixes like ``k`` / ``K`` / ``M`` from
          strings when the canonical parameter is INT or FLOAT.
        """
        # Use cached mappings from skill object
        alias_map = skill._alias_map
        param_map = skill._param_map

        normalized: dict[str, object] = {}
        for key, value in params.items():
            resolved_key = alias_map.get(key, key)
            # Strip unit suffixes for numeric parameters
            if resolved_key in param_map:
                p = param_map[resolved_key]
                if isinstance(value, str):
                    cleaned = value.rstrip("kKmM")
                    if p.type == ParameterType.INT:
                        try:
                            value = int(cleaned)
                        except ValueError:
                            pass
                    elif p.type == ParameterType.FLOAT:
                        try:
                            value = float(cleaned)
                        except ValueError:
                            pass
            normalized[resolved_key] = value
        return normalized

    def _skill_to_filters(
        self,
        skill: Skill,
        params: dict,
    ) -> tuple[list[str], list[str], list[str], str, list[str]]:
        """Convert a skill invocation to FFMPEG filters.

        Args:
            skill: Skill to convert.
            params: Parameters for the skill.

        Returns:
            Tuple of (video_filters, audio_filters, output_options, filter_complex, input_options).
            filter_complex is an empty string if not needed.
        """
        # Note: _normalize_params is already called in compose() before
        # reaching here, so we skip it to avoid redundant processing.

        video_filters = []
        audio_filters = []
        output_options = []
        input_options = []
        filter_complex = ""

        # If skill has a template, use it
        if skill.ffmpeg_template:
            template = skill.ffmpeg_template
            for key, value in params.items():
                val_str = str(value)
                if isinstance(value, str):
                    val_str = sanitize_text_param(val_str)
                template = template.replace(f"{{{key}}}", val_str)

            # Determine if it's a video filter, audio filter, or output option
            if template.startswith("-"):
                output_options.extend(template.split())
            elif skill.category == SkillCategory.AUDIO:
                audio_filters.append(template)
            else:
                video_filters.append(template)

        # If skill has a pipeline, recursively compose
        elif skill.pipeline:
            for step_str in skill.pipeline:
                # Substitute {placeholder} values from parent params
                for key, value in params.items():
                    step_str = step_str.replace(f"{{{key}}}", str(value))

                # Parse step string (format: "skill_name:param1=val1,param2=val2")
                if ":" in step_str:
                    sub_skill_name, params_str = step_str.split(":", 1)
                    sub_params = {}
                    for p in params_str.split(","):
                        if "=" in p:
                            k, v = p.split("=", 1)
                            sub_params[k] = v
                else:
                    sub_skill_name = step_str
                    sub_params = {}

                sub_skill = self.registry.get(sub_skill_name)
                if sub_skill:
                    vf, af, opts, fc, io = self._skill_to_filters(sub_skill, sub_params)
                    video_filters.extend(vf)
                    audio_filters.extend(af)
                    output_options.extend(opts)
                    input_options.extend(io)
                    if fc:
                        filter_complex = fc if not filter_complex else f"{filter_complex};{fc}"

        # Handle specific skill types
        else:
            # Check for custom Python handler from skill packs first
            custom_handlers = getattr(self.registry, "_custom_handlers", {})
            handler = custom_handlers.get(skill.name)
            if handler is not None:
                result = handler(params)
                if len(result) == 5:
                    vf, af, opts, fc, io = result
                elif len(result) == 4:
                    vf, af, opts, fc = result
                    io = []
                else:
                    vf, af, opts = result
                    fc, io = "", []
            else:
                vf, af, opts, fc, io = self._builtin_skill_filters(skill.name, params)
            video_filters.extend(vf)
            audio_filters.extend(af)
            output_options.extend(opts)
            input_options.extend(io)
            if fc:
                filter_complex = fc

        return video_filters, audio_filters, output_options, filter_complex, input_options

    def validate_pipeline(self, pipeline: Pipeline) -> tuple[bool, list[str]]:
        """Validate a pipeline before execution.

        Args:
            pipeline: Pipeline to validate.

        Returns:
            Tuple of (is_valid, list of error messages).
        """
        errors = []

        if not pipeline.input_path:
            errors.append("No input path specified")
        elif not Path(pipeline.input_path).exists():
            errors.append(f"Input file not found: {pipeline.input_path}")

        if not pipeline.output_path:
            errors.append("No output path specified")
        elif not Path(pipeline.output_path).parent.exists():
            errors.append(f"Output directory not found: {Path(pipeline.output_path).parent}")

        for i, step in enumerate(pipeline.steps):
            if not step.enabled:
                continue

            skill = self.registry.get(step.skill_name)
            if not skill:
                errors.append(f"Step {i}: Unknown skill '{step.skill_name}'")
                continue

            is_valid, param_errors = skill.validate_params(step.params)
            if not is_valid:
                for err in param_errors:
                    errors.append(f"Step {i} ({step.skill_name}): {err}")

        return len(errors) == 0, errors

    def explain_pipeline(self, pipeline: Pipeline) -> str:
        """Generate a human-readable explanation of a pipeline.

        Args:
            pipeline: Pipeline to explain.

        Returns:
            Explanation string.
        """
        lines = ["Pipeline explanation:\n"]

        for i, step in enumerate(pipeline.steps):
            status = "" if step.enabled else " (disabled)"
            skill = self.registry.get(step.skill_name)

            if skill:
                lines.append(f"{i+1}. {skill.name}{status}")
                lines.append(f"   {skill.description}")
                if step.params:
                    params_str = ", ".join(f"{k}={v}" for k, v in step.params.items())
                    lines.append(f"   Parameters: {params_str}")
                if step.notes:
                    lines.append(f"   Notes: {step.notes}")
            else:
                lines.append(f"{i+1}. Unknown skill: {step.skill_name}{status}")

            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    #  Dispatch table for built-in skill filters                           #
    # ------------------------------------------------------------------ #

    def _builtin_skill_filters(
        self,
        skill_name: str,
        params: dict,
    ) -> tuple[list[str], list[str], list[str], str, list[str]]:
        """Generate filters for built-in skills using dispatch table.

        Args:
            skill_name: Name of the skill.
            params: Parameters.

        Returns:
            Tuple of (video_filters, audio_filters, output_options, filter_complex, input_options).
        """
        handler = _get_dispatch().get(skill_name)
        if handler is None:
            return [], [], [], "", []
        result = handler(params)
        # Handlers may return 3-tuple, 4-tuple, or 5-tuple
        if len(result) == 5:
            return result
        if len(result) == 4:
            return result + ([],)
        vf, af, opts = result
        return vf, af, opts, "", []


# ====================================================================== #
#  Dispatch table — built lazily to avoid circular imports               #
# ====================================================================== #

_SKILL_DISPATCH: dict | None = None


def _get_dispatch() -> dict:
    """Return the skill dispatch table, building it on first access."""
    global _SKILL_DISPATCH
    if _SKILL_DISPATCH is not None:
        return _SKILL_DISPATCH

    from .handlers import (  # noqa: F401
        # temporal
        _f_trim, _f_speed, _f_reverse, _f_loop, _f_boomerang,
        _f_jump_cut, _f_beat_sync,
        # spatial
        _f_resize, _f_crop, _f_pad, _f_rotate, _f_flip, _f_zoom,
        _f_ken_burns, _f_mirror, _f_caption_space, _f_lens_correction,
        _f_deinterlace, _f_frame_interpolation, _f_scroll, _f_aspect,
        _f_perspective, _f_fill_borders, _f_deshake, _f_frame_blend,
        # visual
        _f_brightness, _f_contrast, _f_saturation, _f_hue,
        _f_sharpen, _f_blur, _f_denoise, _f_vignette, _f_fade,
        _f_pixelate, _f_posterize, _f_color_grade, _f_chromakey_simple,
        _f_deband, _f_color_temperature, _f_selective_color, _f_monochrome,
        _f_chromatic_aberration, _f_sketch, _f_glow, _f_ghost_trail,
        _f_color_channel_swap, _f_tilt_shift, _f_false_color, _f_halftone,
        _f_neon_enhanced, _f_thermal_enhanced, _f_comic_book_enhanced,
        _f_waveform, _f_chromakey, _f_colorkey, _f_lumakey, _f_colorhold,
        _f_despill, _f_remove_background, _f_blend, _f_color_match,
        _f_datamosh, _f_mask_blur, _f_lut_apply,
        # audio
        _f_volume, _f_normalize, _f_fade_audio, _f_remove_audio,
        _f_extract_audio, _f_replace_audio, _f_audio_crossfade, _f_mix_audio,
        # encoding
        _f_compress, _f_convert, _f_bitrate, _f_quality, _f_gif,
        _f_container, _f_two_pass, _f_audio_codec, _f_hwaccel,
        _f_thumbnail, _f_extract_frames,
        # composite
        _f_add_text, _f_grid, _f_slideshow, _f_overlay_image, _f_watermark,
        _f_concat, _f_xfade, _f_split_screen, _f_animated_overlay,
        _f_text_overlay, _f_pip, _f_burn_subtitles, _f_countdown,
        _f_animated_text, _f_scrolling_text, _f_ticker, _f_lower_third,
        _f_typewriter_text, _f_bounce_text, _f_fade_text, _f_karaoke_text,
        # presets
        _f_fade_to_black, _f_fade_to_white, _f_flash,
        _f_spin, _f_shake, _f_pulse, _f_bounce, _f_drift,
        _f_iris_reveal, _f_wipe, _f_slide_in,
    )

    _SKILL_DISPATCH = {
        # Temporal
        "trim": _f_trim,
        "speed": _f_speed,
        "reverse": _f_reverse,
        "loop": _f_loop,
        "boomerang": _f_boomerang,
        "jump_cut": _f_jump_cut,
        "beat_sync": _f_beat_sync,
        # Spatial
        "resize": _f_resize,
        "crop": _f_crop,
        "pad": _f_pad,
        "rotate": _f_rotate,
        "flip": _f_flip,
        "zoom": _f_zoom,
        "ken_burns": _f_ken_burns,
        "mirror": _f_mirror,
        "caption_space": _f_caption_space,
        "lens_correction": _f_lens_correction,
        "deinterlace": _f_deinterlace,
        "frame_interpolation": _f_frame_interpolation,
        "scroll": _f_scroll,
        "aspect": _f_aspect,
        "perspective": _f_perspective,
        "fill_borders": _f_fill_borders,
        "deshake": _f_deshake,
        "frame_blend": _f_frame_blend,
        # Visual
        "brightness": _f_brightness,
        "contrast": _f_contrast,
        "saturation": _f_saturation,
        "hue": _f_hue,
        "sharpen": _f_sharpen,
        "blur": _f_blur,
        "denoise": _f_denoise,
        "vignette": _f_vignette,
        "fade": _f_fade,
        "pixelate": _f_pixelate,
        "posterize": _f_posterize,
        "color_grade": _f_color_grade,
        "deband": _f_deband,
        "color_temperature": _f_color_temperature,
        "selective_color": _f_selective_color,
        "monochrome": _f_monochrome,
        "chromatic_aberration": _f_chromatic_aberration,
        "sketch": _f_sketch,
        "glow": _f_glow,
        "ghost_trail": _f_ghost_trail,
        "color_channel_swap": _f_color_channel_swap,
        "tilt_shift": _f_tilt_shift,
        "false_color": _f_false_color,
        "halftone": _f_halftone,
        "neon": _f_neon_enhanced,
        "thermal": _f_thermal_enhanced,
        "comic_book": _f_comic_book_enhanced,
        "waveform": _f_waveform,
        "datamosh": _f_datamosh,
        "mask_blur": _f_mask_blur,
        "lut_apply": _f_lut_apply,
        "color_match": _f_color_match,
        "blend": _f_blend,
        "double_exposure": _f_blend,
        # Audio
        "volume": _f_volume,
        "normalize": _f_normalize,
        "fade_audio": _f_fade_audio,
        "remove_audio": _f_remove_audio,
        "extract_audio": _f_extract_audio,
        "replace_audio": _f_replace_audio,
        "audio_crossfade": _f_audio_crossfade,
        # Encoding
        "compress": _f_compress,
        "convert": _f_convert,
        "bitrate": _f_bitrate,
        "quality": _f_quality,
        "gif": _f_gif,
        "container": _f_container,
        "two_pass": _f_two_pass,
        "audio_codec": _f_audio_codec,
        "hwaccel": _f_hwaccel,
        "thumbnail": _f_thumbnail,
        "extract_frames": _f_extract_frames,
        "mix_audio": _f_mix_audio,
        "audio_mix": _f_mix_audio,
        "blend_audio": _f_mix_audio,
        "combine_audio": _f_mix_audio,
        # Composite / Overlay
        "text_overlay": _f_text_overlay,
        "add_text": _f_add_text,
        "text": _f_text_overlay,
        "drawtext": _f_text_overlay,
        "title": _f_text_overlay,
        "subtitle": _f_text_overlay,
        "caption": _f_text_overlay,
        "grid": _f_grid,
        "slideshow": _f_slideshow,
        "overlay_image": _f_overlay_image,
        "overlay": _f_overlay_image,
        "watermark": _f_watermark,
        "concat": _f_concat,
        "concatenate": _f_concat,
        "join": _f_concat,
        "xfade": _f_xfade,
        "transition": _f_xfade,
        "split_screen": _f_split_screen,
        "splitscreen": _f_split_screen,
        "side_by_side": _f_split_screen,
        "animated_overlay": _f_animated_overlay,
        "moving_overlay": _f_animated_overlay,
        "picture_in_picture": _f_pip,
        "pip": _f_pip,
        "burn_subtitles": _f_burn_subtitles,
        "hardcode_subtitles": _f_burn_subtitles,
        "countdown": _f_countdown,
        "timer": _f_countdown,
        "animated_text": _f_animated_text,
        "scrolling_text": _f_scrolling_text,
        "credits_roll": _f_scrolling_text,
        "vertical_scroll": _f_scrolling_text,
        "ticker": _f_ticker,
        "horizontal_scroll": _f_ticker,
        "news_ticker": _f_ticker,
        "lower_third": _f_lower_third,
        "name_plate": _f_lower_third,
        "typewriter_text": _f_typewriter_text,
        "typewriter": _f_typewriter_text,
        "bounce_text": _f_bounce_text,
        "fade_text": _f_fade_text,
        "karaoke_text": _f_karaoke_text,
        "karaoke": _f_karaoke_text,
        # Keying / Masking
        "chromakey": _f_chromakey,
        "chroma_key": _f_chromakey,
        "chroma_key_simple": _f_chromakey_simple,
        "green_screen": _f_chromakey,
        "colorkey": _f_colorkey,
        "color_key": _f_colorkey,
        "lumakey": _f_lumakey,
        "luma_key": _f_lumakey,
        "colorhold": _f_colorhold,
        "color_hold": _f_colorhold,
        "despill": _f_despill,
        "de_spill": _f_despill,
        "remove_background": _f_remove_background,
        "remove_bg": _f_remove_background,
        "background_removal": _f_remove_background,
        # Presets / Transitions
        "fade_to_black": _f_fade_to_black,
        "fade_to_white": _f_fade_to_white,
        "flash": _f_flash,
        "spin": _f_spin,
        "shake": _f_shake,
        "pulse": _f_pulse,
        "bounce": _f_bounce,
        "drift": _f_drift,
        "iris_reveal": _f_iris_reveal,
        "wipe": _f_wipe,
        "slide_in": _f_slide_in,
    }
    return _SKILL_DISPATCH

