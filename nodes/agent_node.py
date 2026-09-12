"""FFMPEG Agent node for ComfyUI."""

import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("ffmpega")

try:
    import torch  # type: ignore[import-not-found]
except ImportError:
    torch = None  # type: ignore[assignment]

import folder_paths  # type: ignore[import-not-found]

try:
    import comfy.samplers  # type: ignore[import-not-found]
    _svi_samplers = comfy.samplers.KSampler.SAMPLERS
    _svi_schedulers = comfy.samplers.KSampler.SCHEDULERS
except (ImportError, AttributeError):
    _svi_samplers = ["euler", "euler_ancestral", "dpmpp_2m", "dpmpp_2m_sde", "dpmpp_sde", "uni_pc"]
    _svi_schedulers = ["normal", "karras", "exponential", "sgm_uniform", "simple", "ddim_uniform", "beta"]

from . import input_resolver as _ir
from . import output_handler as _oh
from . import execution_engine as _ee
from . import nollm_modes as _nollm
from . import batch_processor as _bp
from . import pipeline_assembler as _pa
from . import agent_widgets as _agent_widgets

_IMAGE_EXTS = frozenset((".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"))


def _image_path_from_result6(result6: tuple) -> str:
    """Extract image_path from a no-LLM result 6-tuple.

    Returns the output path (index 2) if it points to an image file,
    otherwise returns an empty string.
    """
    out = result6[2] if len(result6) > 2 else ""
    if out and os.path.splitext(out)[1].lower() in _IMAGE_EXTS:
        return out
    return ""


def _get_expression_presets() -> list[str]:
    """List available expression preset names for the dropdown widget."""
    try:
        try:
            from core.expression_presets import list_expressions
        except ImportError:
            from ..core.expression_presets import list_expressions  # type: ignore
        return list_expressions()
    except Exception:
        return []


class FFMPEGAgentNode:
    """Main FFMPEG Agent node that transforms natural language prompts into video edits."""

    # Fallback models if Ollama is unreachable
    FALLBACK_OLLAMA_MODELS = [
        "qwen3:8b",
        "mistral-nemo",
        "llama3.3:8b",
    ]

    QUALITY_PRESETS = ["draft", "standard", "high", "lossless"]

    # Class-level TTL cache for Ollama model list
    _ollama_cache: list[str] | None = None
    _ollama_cache_time: float = 0.0
    _OLLAMA_CACHE_TTL: float = 30.0  # seconds

    @classmethod
    def _fetch_ollama_models(cls, base_url: str = "http://localhost:11434") -> list[str]:
        """Fetch available models from a running Ollama instance.

        Returns locally installed model names, or the fallback list
        if Ollama is unreachable.  Results are cached for 30 seconds
        to avoid redundant API calls.
        """
        now = time.monotonic()
        if cls._ollama_cache is not None and (now - cls._ollama_cache_time) < cls._OLLAMA_CACHE_TTL:
            return cls._ollama_cache

        try:
            import httpx  # type: ignore[import-not-found]
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(f"{base_url}/api/tags")
                resp.raise_for_status()
                models = [m["name"] for m in resp.json().get("models", [])]
                result = sorted(models) if models else cls.FALLBACK_OLLAMA_MODELS
        except Exception:
            result = cls.FALLBACK_OLLAMA_MODELS

        cls._ollama_cache = result
        cls._ollama_cache_time = now
        return result

    @classmethod
    def INPUT_TYPES(cls):
        """Define input types for the node."""
        ollama_models = cls._fetch_ollama_models()
        all_models = ["none"] + ollama_models + ["custom"]

        # --- CLI auto-detection -------------------------------------------
        # Use shared resolver that checks PATH + well-known user-local dirs.
        try:
            from ..core.llm.cli_utils import resolve_cli_binary
        except ImportError:
            from core.llm.cli_utils import resolve_cli_binary  # type: ignore

        cli_models: list[str] = []
        if resolve_cli_binary("gemini", "gemini.cmd"):
            cli_models.append("gemini-cli")
        if resolve_cli_binary("claude", "claude.cmd"):
            cli_models.append("claude-cli")
        if resolve_cli_binary("agent", "agent.cmd"):
            cli_models.append("cursor-agent")
        if resolve_cli_binary("qwen", "qwen.cmd"):
            cli_models.append("qwen-cli")

        # Insert all CLI models right after the Ollama models ("none" is
        # index 0) so they appear in the intended order.
        insert_pos = 1 + len(ollama_models)
        for model in cli_models:
            all_models.insert(insert_pos, model)
            insert_pos += 1

        return {
            "required": {
                "prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "Describe how you want to edit the video...",
                    "tooltip": "Natural language instruction describing the desired edit. Examples: 'Add a cinematic letterbox', 'Speed up 2x', 'Apply a vintage VHS look'.",
                }),
                "video_path": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Path to input video file",
                    "tooltip": "Absolute path to the source video file. Used as the ffmpeg input unless images are connected.",
                }),
                "llm_model": (all_models, {
                    "default": "none",
                    "tooltip": "AI model for interpreting your prompt. "
                               "CLI models (gemini-cli, claude-cli, etc.) use locally installed CLI tools — no API key needed. "
                               "Ollama models run locally via the Ollama server. "
                               "Select 'custom' to type any Ollama model name manually. "
                               "Select 'none' to skip the LLM entirely and use no_llm_mode instead (manual pipeline, SAM3, Whisper, or MMAudio).",
                }),
                "no_llm_mode": (["manual", "sam3_masking", "transcribe", "karaoke_subtitles", "generate_audio (MMAudio)", "generate_music (AudioX)", "foundation1", "fish_speech", "audio_inpaint (AudioX)", "audio_separate (SAM-Audio)", "ace_step", "lip_sync", "animate_portrait", "marigold", "normalcrafter", "video_depth", "sapiens2", "flux_klein", "kiwi_edit", "minimax_remover", "dreamid_omni", "svi", "sharp", "wan_animate", "scail2", "ai_upscale", "rembg", "video_matting", "onion_skin", "comparison", "phyfps"], {
                    "default": "manual",
                    "tooltip": "What to do when llm_model is 'none'. "
                               "'manual' runs the Effects Builder pipeline directly (no AI). "
                               "'sam3_masking' uses the prompt as a SAM3 text target. "
                               "'transcribe' runs Whisper speech-to-text and burns SRT subtitles. "
                               "'karaoke_subtitles' runs Whisper and burns word-by-word karaoke subtitles. "
                               "'generate_audio' uses MMAudio to synthesize audio from video/prompt. "
                               "'generate_music' uses AudioX to generate music from video/prompt (CC-BY-NC). "
                               "'foundation1' uses Foundation-1 to generate BPM/key-aware music loops from prompt. "
                               "'fish_speech' uses Fish Speech S2 Pro for text-to-speech with voice cloning and emotion control (80+ languages). "
                               "'audio_inpaint' uses AudioX to inpaint/complete audio (CC-BY-NC). "
                               "'audio_separate' uses SAM-Audio to isolate specific sounds from audio — prompt describes what to isolate (e.g. 'drums', 'vocals'). "
                               "'lip_sync' uses MuseTalk to sync lip movements to connected audio_a. "
                               "'animate_portrait' uses LivePortrait to animate a face — connect driving video to video_a. "
                               "'marigold' runs Marigold dense vision analysis (depth/normals/intrinsics) — choose output via marigold_output_type. "
                               "'normalcrafter' runs NormalCrafter for temporally-consistent video surface normals — choose res via normalcrafter_max_res. "
                               "'video_depth' runs Video Depth Anything for temporally-consistent depth — choose encoder via video_depth_encoder. "
                               "'sapiens2' runs Meta Sapiens2 human-centric vision — choose task via sapiens2_task (pose/seg/normal/pointmap/matting/pretrain) and model size via sapiens2_size (⚠️ Meta Proprietary license: no surveillance/biometric/deepfake use). "
                               "'flux_klein' runs FLUX Klein editing directly — prompt is the edit instruction, works on images and videos (full-frame, no mask needed). "
                               "'rembg' removes the video background using AI segmentation — choose model via rembg_model and background via rembg_background. "
                               "'video_matting' runs MatAnyone2 temporal video matting — uses SAM3 for auto-mask or connect mask to image_a. Choose output via matting_output (⚠️ non-commercial license). "
                               "'onion_skin' applies temporal ghosting (onion skin) — adjust blend mode, opacity, and trail decay in advanced options. "
                               "'svi' runs SVI 2.0 Pro (Stable Video Infinity) to generate infinite-length videos — connect reference image to image_a, prompts are newline-separated (one per clip). "
                               "'sharp' runs Apple SHARP for single-image 3D Gaussian view synthesis — connect image to image_a, renders a camera trajectory video in <1s (⚠️ research license). "
                               "'phyfps' runs Visual Chronometer to predict the physical frame rate (PhyFPS) of the video — choose action via phyfps_action. "
                               "'comparison' creates a comparison video from two inputs (before/after) — connect video_a as the 'after' video. "
                               "Styles: swipe, split, side_by_side, diagonal, circular_reveal, difference.",
                }),
                "quality_preset": (cls.QUALITY_PRESETS, {
                    "default": "standard",
                    "tooltip": "Output quality level. 'draft' is fast/low quality, 'standard' is balanced, 'high' is slow/best quality, 'lossless' preserves full quality.",
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 0xffffffffffffffff,
                    "tooltip": "Change this value to force re-execution with the same prompt. Use the randomize control to auto-increment between runs.",
                    "control_after_generate": True,
                }),
            },
            "optional": _agent_widgets.build_optional(),
            "hidden": {
                "hidden_prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
                "unique_id": "UNIQUE_ID",
            },
        }

    RETURN_TYPES = ("IMAGE", "AUDIO", "STRING", "STRING", "STRING", "STRING", "STRING", "STRING", "MASK")
    RETURN_NAMES = ("images", "audio", "video_path", "command_log", "analysis", "mask_overlay_path", "mask_points", "image_path", "mask")
    OUTPUT_TOOLTIPS = (
        "Image frames from the output video. Returns ALL frames automatically when connected to a downstream node (e.g. VHS Video Combine). Returns only a thumbnail when unconnected (zero-memory preview).",
        "Audio extracted from the output video (or passed through from audio_a) in ComfyUI AUDIO format.",
        "Absolute path to the rendered output video file.",
        "The ffmpeg command that was executed.",
        "LLM interpretation, estimated changes, pipeline steps, and any warnings.",
        "Path to a mask overlay preview video with SAM3-style colored contours. Connect to Save Video (FFMPEGA) to view the visual overlay.",
        "Pass-through of upstream mask_points JSON data for downstream nodes. Contains click coordinates and labels.",
        "Absolute path to the output image file when the node produces a single image (e.g. Flux Klein single-image edit). Empty for video outputs.",
        "Raw binary MASK tensor for downstream compositing (MatAnyone2, inpainting, etc.). Upstream mask passthrough or empty mask if no mask source.",
    )
    FUNCTION = "process"
    CATEGORY = "FFMPEGA"
    DESCRIPTION = "AI-powered video editor: describe edits in natural language and the agent generates and runs the ffmpeg pipeline automatically."
    OUTPUT_NODE = True

    def __init__(self):
        """Initialize the agent node."""
        self._analyzer = None
        self._process_manager = None
        self._registry = None
        self._composer = None
        self._preview_generator = None
        self._media_converter = None
        self._pipeline_generator = None

    @property
    def analyzer(self):
        if self._analyzer is None:
            from ..core.video.analyzer import VideoAnalyzer  # type: ignore[import-not-found]
            self._analyzer = VideoAnalyzer()
        return self._analyzer

    @property
    def process_manager(self):
        if self._process_manager is None:
            from ..core.executor.process_manager import ProcessManager  # type: ignore[import-not-found]
            self._process_manager = ProcessManager()
        return self._process_manager

    @property
    def registry(self):
        if self._registry is None:
            from ..skills.registry import get_registry  # type: ignore[import-not-found]
            self._registry = get_registry()
        return self._registry

    @property
    def composer(self):
        if self._composer is None:
            from ..skills.composer import SkillComposer  # type: ignore[import-not-found]
            self._composer = SkillComposer(self.registry)
        return self._composer

    @property
    def preview_generator(self):
        if self._preview_generator is None:
            from ..core.executor.preview import PreviewGenerator  # type: ignore[import-not-found]
            self._preview_generator = PreviewGenerator()
        return self._preview_generator

    @property
    def media_converter(self):
        if self._media_converter is None:
            from ..core.media_converter import MediaConverter  # type: ignore[import-not-found]
            self._media_converter = MediaConverter()
        return self._media_converter

    @property
    def pipeline_generator(self):
        if self._pipeline_generator is None:
            from ..core.pipeline_generator import PipelineGenerator  # type: ignore[import-not-found]
            self._pipeline_generator = PipelineGenerator(self.registry)
        return self._pipeline_generator

    # ------------------------------------------------------------------ #
    #  Private helpers extracted from process()                           #
    # ------------------------------------------------------------------ #

    def _resolve_inputs(self, video_path, images_a, image_a, image_path_a, video_a, text_a, subtitle_path, audio_a, **kwargs):
        """Delegate to input_resolver module."""
        return _ir.resolve_inputs(self.media_converter, video_path, images_a, image_a, image_path_a, video_a, text_a, subtitle_path, audio_a, **kwargs)

    def _build_connected_inputs_summary(self, images_a, _images_a_shape, video_path, audio_a, image_a, _all_video_paths, _all_image_paths, _all_text_inputs, video_metadata, **kwargs):
        """Delegate to input_resolver module."""
        return _ir.build_connected_inputs_summary(images_a, _images_a_shape, video_path, audio_a, image_a, _all_video_paths, _all_image_paths, _all_text_inputs, video_metadata, **kwargs)

    def _build_output_path(self, effective_video_path, save_output, output_path, preview_mode):
        """Delegate to output_handler module."""
        return _oh.build_output_path(effective_video_path, save_output, output_path, preview_mode)

    def _inject_extra_inputs(
        self,
        pipeline,
        effective_video_path: str,
        image_a,
        _all_image_paths: list,
        _all_video_paths: list,
        _all_text_inputs: list,
        audio_a,
        **kwargs,
    ):
        """Inject multi-input tensors/paths into the pipeline's extra_inputs.

        Handles: video tensors, image tensors, video file paths, image file
        paths. Converts tensors to temp files and releases them immediately to
        keep peak memory low. Also handles audio muxing for concat/xfade.

        Returns
        -------
        tuple of:
            effective_video_path (str),      -- may be updated by COW copy
            temp_multi_videos (list[str]),
            temp_audio_files (list[str]),
            temp_frames_dirs (set[str]),
            temp_audio_input (str | None),
        """

        temp_multi_videos = []
        temp_audio_files = []
        temp_frames_dirs = set()
        temp_audio_input = None

        # --- replace_audio: save audio_a as input [1] ---
        has_replace_audio = any(s.skill_name == "replace_audio" for s in pipeline.steps)
        if has_replace_audio and audio_a is not None:
            try:
                waveform = audio_a["waveform"]
                sample_rate = audio_a["sample_rate"]
                channels = waveform.size(1)
                audio_data = waveform.squeeze(0).transpose(0, 1).contiguous()
                audio_bytes = (audio_data * 32767.0).clamp(-32768, 32767).to(torch.int16).numpy().tobytes()
                import subprocess
                _tmp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                _tmp_wav.close()
                subprocess.run(
                    ["ffmpeg", "-y", "-f", "s16le", "-ar", str(sample_rate),
                     "-ac", str(channels), "-i", "-", _tmp_wav.name],
                    input=audio_bytes, capture_output=True,
                )
                pipeline.extra_inputs.insert(0, _tmp_wav.name)
                temp_audio_input = _tmp_wav.name
                logger.debug("Saved audio_a as temp WAV for replace_audio: %s", _tmp_wav.name)
            except Exception as e:
                logger.warning("Could not save audio_a for replace_audio: %s", e)

        # --- Multi-input frame extraction ---
        MULTI_INPUT_SKILLS = {
            "grid", "slideshow", "overlay_image", "overlay",
            "concat", "split_screen", "watermark", "chromakey",
            "xfade", "transition", "animated_overlay", "moving_overlay",
            "picture_in_picture", "pip", "blend", "onion_skin",
            "picture-in-picture", "pictureinpicture",
        }
        needs_multi_input = any(s.skill_name in MULTI_INPUT_SKILLS for s in pipeline.steps)

        if needs_multi_input:
            all_frame_paths = []

            if _all_video_paths:
                all_frame_paths.extend(_all_video_paths)
                logger.debug("File-path video inputs (zero memory): %s", _all_video_paths)

            _SEGMENT_SKILLS = {"xfade", "slideshow", "concat"}
            _OVERLAY_SKILLS = {"overlay_image", "overlay", "watermark", "animated_overlay", "moving_overlay"}
            _pipeline_skill_names = {
                self.composer.SKILL_ALIASES.get(s.skill_name, s.skill_name)
                for s in pipeline.steps
            }
            _has_overlay = bool(_pipeline_skill_names & _OVERLAY_SKILLS)
            _has_segments = bool(_pipeline_skill_names & _SEGMENT_SKILLS)
            _images_are_segments = _has_segments and not _has_overlay

            if _all_image_paths:
                if _images_are_segments:
                    all_frame_paths.extend(_all_image_paths)
                    logger.debug("Image paths routed as segments: %s", _all_image_paths)
                else:
                    pipeline.metadata["_image_paths"] = _all_image_paths
                    logger.debug("Image paths routed for overlay: %s", _all_image_paths)

            # Collect image/video tensors
            all_image_keys = []
            if image_a is not None:
                all_image_keys.append(('__image_a__', image_a))
            for k in sorted(kwargs):
                if (k.startswith("image_") and not k.startswith("images_")
                        and not k.startswith("image_path_") and kwargs[k] is not None):
                    all_image_keys.append((k, kwargs[k]))
            for k in sorted(kwargs):
                if k.startswith("images_") and kwargs[k] is not None:
                    all_image_keys.append((k, kwargs[k]))

            for ti, (tkey, tensor) in enumerate(all_image_keys):
                logger.debug("Multi-input tensor %d (%s): shape=%s", ti, tkey, tensor.shape)
                if tensor.shape[0] > 10:
                    # Match the rate of the primary source when there is one;
                    # an image batch on its own has no frame rate to inherit.
                    tmp_vid = self.media_converter.images_to_video(
                        tensor,
                        fps=_ir._source_fps(effective_video_path, _all_video_paths),
                    )
                    all_frame_paths.append(tmp_vid)
                    temp_multi_videos.append(tmp_vid)
                    try:
                        import subprocess as _sp
                        _dur = _sp.run(
                            ["ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of", "default=noprint_wrappers=1", tmp_vid],
                            capture_output=True, text=True,
                        )
                        logger.debug("Temp video %s: %s, size=%d",
                                     tmp_vid, _dur.stdout.strip(), os.path.getsize(tmp_vid))
                    except Exception:
                        pass
                else:
                    paths = self.media_converter.save_frames_as_images(tensor)
                    all_frame_paths.extend(paths)
                    if paths:
                        temp_frames_dirs.add(os.path.dirname(paths[0]))
                all_image_keys[ti] = (tkey, None)
                del tensor
                if tkey == '__image_a__':
                    image_a = None
                elif tkey in kwargs:
                    kwargs[tkey] = None

            del all_image_keys
            try:
                import torch as _torch
                if _torch.cuda.is_available():
                    _torch.cuda.empty_cache()
            except Exception:
                pass

            if all_frame_paths:
                existing = pipeline.extra_inputs or []
                pipeline.extra_inputs = existing + all_frame_paths
                pipeline.metadata["frame_count"] = len(all_frame_paths)

        # Attach text inputs
        if _all_text_inputs:
            pipeline.text_inputs = _all_text_inputs

        # Auto-set include_video for slideshow/grid.
        # A "real video" means the pipeline has at least one multi-frame input
        # (the primary video path, any extra video file paths, or a tensor with
        # enough frames to constitute a video).
        _tensor_has_many_frames = (
            image_a is not None
            and hasattr(image_a, 'shape')
            and len(image_a.shape) >= 1
            and image_a.shape[0] > 10
        )
        _extra_images_have_many_frames = any(
            v is not None
            and hasattr(v, 'shape')
            and len(v.shape) >= 1
            and v.shape[0] > 10
            for k, v in kwargs.items()
            if k.startswith("images_")
        )
        has_real_video = (
            len(_all_video_paths) > 0
            or _tensor_has_many_frames
            or _extra_images_have_many_frames
        )
        for step in pipeline.steps:
            if step.skill_name in ("slideshow", "grid"):
                step.params["include_video"] = has_real_video

        # --- Multi-audio muxing for concat/xfade ---
        if needs_multi_input:
            all_audio_dicts = []
            if audio_a is not None:
                all_audio_dicts.append(audio_a)
            for k in sorted(kwargs):
                if k.startswith("audio_") and k != "audio_a" and kwargs[k] is not None:
                    all_audio_dicts.append(kwargs[k])

            _tmpdir = tempfile.gettempdir()

            def _ensure_temp_copy(filepath: str) -> str:
                if not filepath or not os.path.isfile(filepath):
                    return filepath
                if os.path.commonpath([filepath, _tmpdir]) == _tmpdir:
                    return filepath
                ext = os.path.splitext(filepath)[1] or ".mp4"
                tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
                tmp.close()
                import shutil as _shutil
                _shutil.copy2(filepath, tmp.name)
                return tmp.name

            if all_audio_dicts or any(s.skill_name in ("concat", "xfade") for s in pipeline.steps):
                new_evp = _ensure_temp_copy(effective_video_path)
                if new_evp != effective_video_path:
                    effective_video_path = new_evp
                pipeline.extra_inputs = [_ensure_temp_copy(ep) for ep in pipeline.extra_inputs]
                pipeline.input_path = effective_video_path

            if all_audio_dicts:
                video_segments = [effective_video_path] + list(pipeline.extra_inputs)
                for ai, audio_dict in enumerate(all_audio_dicts):
                    if ai >= len(video_segments):
                        break
                    vid_path = video_segments[ai]
                    if not os.path.isfile(vid_path):
                        continue
                    if self.media_converter.has_audio_stream(vid_path):
                        continue
                    try:
                        self.media_converter.mux_audio(vid_path, audio_dict)
                    except Exception as e:
                        logger.warning("Could not mux audio %d into %s: %s", ai, vid_path, e)

            _vid_exts = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".ts", ".m4v"}
            video_segments = [
                p for p in [effective_video_path] + list(pipeline.extra_inputs)
                if p and os.path.splitext(p)[1].lower() in _vid_exts
            ]

            is_audio_filter_skill = any(s.skill_name in ("concat", "xfade") for s in pipeline.steps)
            if is_audio_filter_skill:
                for vid_path in video_segments:
                    if not os.path.isfile(vid_path):
                        continue
                    if not self.media_converter.has_audio_stream(vid_path):
                        try:
                            self.media_converter.add_silent_audio(vid_path)
                        except Exception as e:
                            logger.warning("Could not add silent audio to %s: %s", vid_path, e)
                audio_segment_count = sum(
                    1 for vp in video_segments
                    if os.path.isfile(vp) and self.media_converter.has_audio_stream(vp)
                )
                if audio_segment_count >= 2:
                    pipeline.metadata["_has_embedded_audio"] = True

        # --- Transcription audio input path ---
        _TRANSCRIBE_SKILLS = {
            "auto_transcribe", "transcribe", "speech_to_text",
            "karaoke_subtitles", "whisper", "auto_subtitle", "auto_caption",
        }
        has_transcribe_skill = any(s.skill_name in _TRANSCRIBE_SKILLS for s in pipeline.steps)
        if has_transcribe_skill and audio_a is not None:
            audio_wav_path = self._audio_dict_to_wav(audio_a)
            if audio_wav_path:
                pipeline.metadata["_audio_input_path"] = audio_wav_path
                temp_audio_files.append(audio_wav_path)
                logger.info("Transcription will use connected audio_a input: %s", audio_wav_path)

        # --- Lip sync audio input path ---
        _LIP_SYNC_SKILLS = {
            "lip_sync", "lipsync", "dub", "dubbing",
            "sync_lips", "talking_head", "lip_dub", "voice_sync",
        }
        has_lip_sync_skill = any(s.skill_name in _LIP_SYNC_SKILLS for s in pipeline.steps)
        if has_lip_sync_skill and audio_a is not None:
            audio_wav_path = self._audio_dict_to_wav(audio_a)
            if audio_wav_path:
                for step in pipeline.steps:
                    if step.skill_name in _LIP_SYNC_SKILLS:
                        step.params["audio_path"] = audio_wav_path
                temp_audio_files.append(audio_wav_path)
                logger.info("Lip sync will use connected audio_a input: %s", audio_wav_path)

        return (
            effective_video_path,
            temp_multi_videos,
            temp_audio_files,
            temp_frames_dirs,
            temp_audio_input,
        )

    async def _execute_pipeline(self, pipeline, command, connector, prompt, metadata_str, connected_inputs_str, effective_video_path, output_path, quality_preset, crf, encoding_preset, preview_mode, verify_output, use_vision, ptc_mode, video_metadata, _all_text_inputs):
        """Delegate to execution_engine module."""
        return await _ee.execute_pipeline(
            pipeline=pipeline, command=command, connector=connector,
            composer=self.composer, process_manager=self.process_manager,
            pipeline_generator=self.pipeline_generator,
            prompt=prompt, metadata_str=metadata_str,
            connected_inputs_str=connected_inputs_str,
            effective_video_path=effective_video_path, output_path=output_path,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset, preview_mode=preview_mode,
            verify_output=verify_output, use_vision=use_vision,
            ptc_mode=ptc_mode, video_metadata=video_metadata,
            _all_text_inputs=_all_text_inputs,
        )

    def _handle_audio_output(self, command, pipeline, audio_a, audio_source, audio_mode, output_path, **kwargs):
        """Delegate to output_handler module."""
        return _oh.handle_audio_output(command, pipeline, self.media_converter, audio_a, audio_source, audio_mode, output_path, **kwargs)

    def _collect_frame_output(self, output_path, unique_id, hidden_prompt, removes_audio, resample_rate=None):
        """Delegate to output_handler module."""
        return _oh.collect_frame_output(self.media_converter, output_path, unique_id, hidden_prompt, removes_audio, resample_rate=resample_rate)

    # ------------------------------------------------------------------ #
    #  Main entry point                                                   #
    # ------------------------------------------------------------------ #

    async def process(
        self,
        video_path: str,
        prompt: str,
        llm_model: str,
        quality_preset: str,
        seed: int = 0,
        no_llm_mode: str = "manual",
        images_a: Optional[torch.Tensor] = None,
        image_a: Optional[torch.Tensor] = None,
        audio_a: Optional[dict] = None,
        video_a: str = "",
        image_path_a: str = "",
        text_a: str = "",
        pipeline_json: str = "",
        advanced_options: bool = False,
        subtitle_path: str = "",
        preview_mode: bool = False,
        save_output: bool = False,
        output_path: str = "",
        ollama_url: str = "http://localhost:11434",
        custom_model: str = "",
        crf: int = -1,
        encoding_preset: str = "auto",
        use_vision: bool = False,
        ptc_mode: str = "off",
        verify_output: bool = False,
        whisper_device: str = "cpu",
        whisper_model: str = "large-v3",
        sam3_device: str = "gpu",
        sam3_max_objects: int = 5,
        sam3_det_threshold: float = 0.7,
        mask_points: str = "",
        mask=None,
        crop_data: str = "",
        use_flux_klein: bool = False,
        flux_klein_model: str = "4b",
        use_kiwi_edit: bool = False,
        use_minimax_remover: bool = False,
        use_dreamid_omni: bool = False,
        flux_smoothing: str = "none",
        audio_output_mode: str = "auto",
        audio_resample_rate: str = "off",
        ace_negative_prompt: str = "",
        ace_cover_strength: float = 0.5,
        ace_steps: int = 8,
        ace_cfg_scale: float = 7.0,
        ace_bpm: str = "",
        ace_key: str = "",
        ace_time_sig: str = "",
        f1_preset: str = "none",
        f1_instrument: str = "none",
        f1_fx: str = "none",
        f1_structure: str = "none",
        f1_negative_prompt: str = "",
        f1_bpm: str = "auto",
        f1_bars: str = "auto",
        f1_key: str = "",
        f1_duration: float = 0.0,
        f1_steps: int = 100,
        f1_cfg_scale: float = 7.0,
        f1_style_transfer: bool = False,
        f1_noise_level: float = 0.7,
        batch_mode: bool = False,
        video_folder: str = "",
        file_pattern: str = "*.mp4",
        max_concurrent: int = 4,
        track_tokens: bool = True,
        log_usage: bool = False,
        allow_model_downloads: bool = True,
        fish_model_variant: str = "bf16",
        fish_voice: str = "",
        fish_emotion: str = "(none)",
        fish_temperature: float = 0.8,
        fish_top_p: float = 0.8,
        fish_repetition_penalty: float = 1.1,
        **kwargs,  # hidden: prompt (PROMPT dict), extra_pnginfo (EXTRA_PNGINFO)
    ) -> tuple[torch.Tensor, dict, str, str, str, str, str, torch.Tensor]:
        """Process the video based on the natural language prompt.

        Args:
            video_path: Path to input video.
            prompt: Natural language editing instruction.
            llm_model: LLM model to use.
            quality_preset: Output quality preset.
            images_a: First video input as IMAGE tensor from upstream nodes.
            audio_a: Optional input AUDIO dict from upstream nodes.
            preview_mode: Generate preview instead of full render.
            output_path: Custom output path.
            ollama_url: Ollama server URL.
            crf: Override CRF value (-1 = use preset).
            encoding_preset: Override encoding preset ("auto" = use preset).

        Returns:
            Tuple of (images_tensor, audio, output_video_path, command_log, analysis).
        """
        from ..skills.composer import Pipeline  # type: ignore[import-not-found]

        # --- Normalize no_llm_mode: dropdown labels carry a cosmetic model-name
        # suffix, e.g. "generate_audio (MMAudio)". Strip the trailing " (...)" so
        # dispatch comparisons below (and old workflows saving bare names) match.
        import re
        no_llm_mode = re.sub(r"\s*\([^)]*\)\s*$", "", str(no_llm_mode)).strip()

        # --- Apply model-download permission flag ---
        try:
            from ..core import model_manager  # type: ignore[import-not-found]
        except ImportError:
            from core import model_manager  # type: ignore
        model_manager.set_downloads_allowed(allow_model_downloads)

        # Mask pass-through: upstream mask or empty fallback
        empty_mask = mask if mask is not None else torch.zeros(1, 64, 64, dtype=torch.float32)

        # --- Inject FFMPEGA Effects Builder pipeline if provided ---
        # Save the raw prompt BEFORE injecting effects hints — the hint
        # text appended by inject_effects_hints corrupts SAM3's text-based
        # grounding detector (it can't parse multi-line hint blocks).
        _raw_prompt = prompt
        if pipeline_json and pipeline_json.strip():
            prompt = _nollm.inject_effects_hints(prompt, pipeline_json)

        # --- Batch mode ---
        if batch_mode:
            result6 = await self._process_batch(
                video_folder=video_folder,
                file_pattern=file_pattern,
                prompt=prompt,
                llm_model=llm_model,
                quality_preset=quality_preset,
                ollama_url=ollama_url,
                custom_model=custom_model,
                crf=crf,
                encoding_preset=encoding_preset,
                max_concurrent=max_concurrent,
                save_output=save_output,
                output_path=output_path,
                use_vision=use_vision,
                verify_output=verify_output,
                ptc_mode=ptc_mode,
                sam3_max_objects=sam3_max_objects,
                sam3_det_threshold=sam3_det_threshold,
                mask_points=mask_points,
                use_flux_klein=use_flux_klein,
                flux_klein_model=flux_klein_model,
                use_kiwi_edit=use_kiwi_edit,
                use_minimax_remover=use_minimax_remover,
                flux_smoothing=flux_smoothing,
                pipeline_json=pipeline_json,
            )
            return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)

        # --- Foundation-1 (audio-only, no video resolution needed) ---
        if no_llm_mode == "foundation1":
            result6 = await self._process_foundation1_only(
                prompt=prompt,
                audio_output_mode=audio_output_mode,
                effective_video_path=video_path or "",
                video_metadata=None,
                save_output=save_output,
                output_path=output_path,
                preview_mode=preview_mode,
                quality_preset=quality_preset,
                crf=crf,
                encoding_preset=encoding_preset,
                temp_video_from_images=None,
                temp_video_with_audio=None,
                f1_preset=f1_preset,
                f1_instrument=f1_instrument,
                f1_fx=f1_fx,
                f1_structure=f1_structure,
                f1_negative_prompt=f1_negative_prompt,
                f1_bpm=f1_bpm,
                f1_bars=f1_bars,
                f1_key=f1_key,
                f1_duration=f1_duration,
                f1_steps=f1_steps,
                f1_cfg_scale=f1_cfg_scale,
                f1_style_transfer=f1_style_transfer,
                f1_noise_level=f1_noise_level,
                audio_a=audio_a,
                **kwargs,
            )
            return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)

        # --- Fish Speech TTS (audio-only, no video resolution needed) ---
        if no_llm_mode == "fish_speech":
            result6 = await self._process_fish_speech_only(
                prompt=prompt,
                audio_output_mode=audio_output_mode,
                effective_video_path=video_path or "",
                video_metadata=None,
                save_output=save_output,
                output_path=output_path,
                preview_mode=preview_mode,
                quality_preset=quality_preset,
                crf=crf,
                encoding_preset=encoding_preset,
                temp_video_from_images=None,
                temp_video_with_audio=None,
                fish_model_variant=fish_model_variant,
                fish_voice=fish_voice,
                fish_emotion=fish_emotion,
                fish_temperature=fish_temperature,
                fish_top_p=fish_top_p,
                fish_repetition_penalty=fish_repetition_penalty,
                audio_a=audio_a,
                **kwargs,
            )
            return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)

        # --- Resolve inputs ---
        (
            effective_video_path,
            temp_video_from_images,
            temp_video_with_audio,
            _all_video_paths,
            _all_image_paths,
            _all_text_inputs,
            _images_a_shape,
        ) = self._resolve_inputs(
            video_path=video_path,
            images_a=images_a,
            image_a=image_a,
            image_path_a=image_path_a,
            video_a=video_a,
            text_a=text_a,
            subtitle_path=subtitle_path,
            audio_a=audio_a,
            **kwargs,
        )
        images_a = None

        # --- Apply crop if crop_data is provided ---
        if crop_data and crop_data.strip():
            try:
                from ..videoeditor.processing.crop import apply_crop
                import tempfile as _crop_tmp
                _crop_out = _crop_tmp.NamedTemporaryFile(
                    suffix=".mp4", delete=False,
                )
                _crop_out.close()
                cropped = apply_crop(
                    effective_video_path, crop_data, _crop_out.name,
                )
                if cropped != effective_video_path:
                    logger.info(
                        "Applied crop %s → %s", crop_data.strip(), cropped,
                    )
                    effective_video_path = cropped
                else:
                    # Crop wasn't applied (e.g. invalid rect), clean up
                    try:
                        os.unlink(_crop_out.name)
                    except OSError:
                        pass
            except Exception as e:
                logger.warning("Could not apply crop_data: %s", e)

        if not prompt.strip():
            # manual + whisper + lip_sync modes don't need a prompt
            if llm_model != "none" or no_llm_mode not in ("manual", "transcribe", "karaoke_subtitles", "generate_audio", "generate_music", "foundation1", "fish_speech", "audio_inpaint", "audio_separate", "ace_step", "lip_sync", "animate_portrait", "marigold", "normalcrafter", "video_depth", "kiwi_edit", "minimax_remover", "dreamid_omni", "svi", "sharp", "scail2", "ai_upscale", "rembg", "video_matting", "onion_skin"):
                raise ValueError("Prompt cannot be empty")

        # --- Analyze input video ---
        video_metadata = self.analyzer.analyze(effective_video_path)
        metadata_str = video_metadata.to_analysis_string()

        # ================================================================== #
        #  No-LLM mode — bypass pipeline generation entirely                #
        # ================================================================== #
        if llm_model == "none":
            # Effects Builder connected → execute its pipeline directly
            # When sam3_masking mode is active, wrap visual effects as
            # auto_mask steps so they apply to the SAM3-masked region.
            if pipeline_json and pipeline_json.strip():
                _effective_pipeline_json = pipeline_json
                if no_llm_mode == "sam3_masking":
                    _effective_pipeline_json = _nollm.merge_sam3_into_effects_pipeline(
                        pipeline_json, _raw_prompt,
                    )
                    logger.info(
                        "SAM3 masking + Effects Builder: merged pipeline for target '%s'",
                        _raw_prompt.strip(),
                    )
                result6 = await self._process_effects_pipeline(
                    pipeline_json=_effective_pipeline_json,
                    prompt=prompt,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    whisper_device=whisper_device,
                    whisper_model=whisper_model,
                    sam3_device=sam3_device,
                    sam3_max_objects=sam3_max_objects,
                    sam3_det_threshold=sam3_det_threshold,
                    mask_points=mask_points,
                    use_flux_klein=use_flux_klein,
                    flux_klein_model=flux_klein_model,
                    use_kiwi_edit=use_kiwi_edit,
                    use_minimax_remover=use_minimax_remover,
                    use_dreamid_omni=use_dreamid_omni,
                    flux_smoothing=flux_smoothing,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    image_a=image_a,
                    audio_a=audio_a,
                    _all_video_paths=_all_video_paths,
                    _all_image_paths=_all_image_paths,
                    _all_text_inputs=_all_text_inputs,
                    audio_resample_rate=audio_resample_rate,
                    **kwargs,
                )
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # Whisper-only mode (transcribe or karaoke)
            if no_llm_mode in ("transcribe", "karaoke_subtitles"):
                result6 = await self._process_whisper_only(
                    mode=no_llm_mode,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    whisper_device=whisper_device,
                    whisper_model=whisper_model,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # SAM3-only mode (prompt = text target)
            if no_llm_mode == "sam3_masking":
                result6 = await self._process_sam3_only(
                    prompt=prompt,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    sam3_device=sam3_device,
                    sam3_max_objects=sam3_max_objects,
                    sam3_det_threshold=sam3_det_threshold,
                    mask_points=mask_points,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # MMAudio-only mode (generate_audio from video/prompt)
            if no_llm_mode == "generate_audio":
                result6 = await self._process_mmaudio_only(
                    prompt=prompt,
                    audio_output_mode=audio_output_mode,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # AudioX music-only mode (generate_music from video/prompt)
            if no_llm_mode == "generate_music":
                result6 = await self._process_audiox_music_only(
                    prompt=prompt,
                    audio_output_mode=audio_output_mode,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # AudioX inpaint-only mode (audio_inpaint from video audio)
            if no_llm_mode == "audio_inpaint":
                result6 = await self._process_audiox_inpaint_only(
                    prompt=prompt,
                    audio_output_mode=audio_output_mode,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # ACE-Step music generation mode
            if no_llm_mode == "ace_step":
                result6 = await self._process_ace_step_only(
                    prompt=prompt,
                    audio_output_mode=audio_output_mode,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    text_a=text_a,
                    audio_a=audio_a,
                    ace_negative_prompt=ace_negative_prompt,
                    ace_cover_strength=ace_cover_strength,
                    ace_steps=ace_steps,
                    ace_cfg_scale=ace_cfg_scale,
                    ace_bpm=ace_bpm,
                    ace_key=ace_key,
                    ace_time_sig=ace_time_sig,
                    **kwargs,
                )
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # SAM-Audio separation mode (isolate sounds from audio)
            if no_llm_mode == "audio_separate":
                result6 = await self._process_sam_audio_separate(
                    prompt=prompt,
                    audio_output_mode=audio_output_mode,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)

            # ── SAM3 Pre-Masking for No-LLM Modes ──────────────────
            # When use_sam3 is on and we have a prompt, pre-generate a
            # SAM3 mask before the mode runs. After the mode produces
            # its output, we composite via maskedmerge.
            _SAM3_ELIGIBLE_MODES = {
                "lip_sync", "animate_portrait", "marigold", "normalcrafter",
                "video_depth", "flux_klein", "kiwi_edit", "minimax_remover",
                "ai_upscale", "rembg", "video_matting", "onion_skin", "comparison",
            }
            _use_sam3 = bool(kwargs.pop("use_sam3", False))
            _sam3_mask_path = None
            if _use_sam3 and no_llm_mode in _SAM3_ELIGIBLE_MODES and _raw_prompt.strip():
                _sam3_mask_path = _nollm.sam3_premask(
                    video_path=effective_video_path,
                    prompt=_raw_prompt,
                    sam3_device=sam3_device,
                    sam3_max_objects=sam3_max_objects,
                    sam3_det_threshold=sam3_det_threshold,
                )
                if _sam3_mask_path:
                    logger.info(
                        "SAM3 pre-mask: will composite %s output over original",
                        no_llm_mode,
                    )

            # Lip sync mode (MuseTalk from connected audio_a)
            if no_llm_mode == "lip_sync":
                result6 = await self._process_lip_sync_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    audio_a=audio_a,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # Animate portrait mode (LivePortrait from connected video_a)
            if no_llm_mode == "animate_portrait":
                # video_a is the driving video
                driving_video = _all_video_paths[0] if _all_video_paths else ""

                # Pop expression params from kwargs
                _lp_vals = {
                    "lp_rotate_pitch": float(kwargs.pop("lp_rotate_pitch", 0.0)),
                    "lp_rotate_yaw": float(kwargs.pop("lp_rotate_yaw", 0.0)),
                    "lp_rotate_roll": float(kwargs.pop("lp_rotate_roll", 0.0)),
                    "lp_blink": float(kwargs.pop("lp_blink", 0.0)),
                    "lp_eyebrow": float(kwargs.pop("lp_eyebrow", 0.0)),
                    "lp_wink": float(kwargs.pop("lp_wink", 0.0)),
                    "lp_pupil_x": float(kwargs.pop("lp_pupil_x", 0.0)),
                    "lp_pupil_y": float(kwargs.pop("lp_pupil_y", 0.0)),
                    "lp_aaa": float(kwargs.pop("lp_aaa", 0.0)),
                    "lp_eee": float(kwargs.pop("lp_eee", 0.0)),
                    "lp_woo": float(kwargs.pop("lp_woo", 0.0)),
                    "lp_smile": float(kwargs.pop("lp_smile", 0.0)),
                    "lp_retargeting_eyes": float(kwargs.pop("lp_retargeting_eyes", 1.0)),
                    "lp_retargeting_mouth": float(kwargs.pop("lp_retargeting_mouth", 1.0)),
                    "lp_crop_factor": float(kwargs.pop("lp_crop_factor", 1.6)),
                }
                _lp_preset = str(kwargs.pop("lp_expression_preset", "none"))
                _lp_save = str(kwargs.pop("lp_save_expression", "")).strip()

                # Load preset (overrides slider values)
                if _lp_preset and _lp_preset != "none":
                    try:
                        try:
                            from core.expression_presets import load_expression
                        except ImportError:
                            from ..core.expression_presets import load_expression  # type: ignore
                        preset_data = load_expression(_lp_preset)
                        if preset_data:
                            logger.info("[animate_portrait] Loading preset '%s'", _lp_preset)
                            for key, val in preset_data.items():
                                lp_key = f"lp_{key}" if not key.startswith("lp_") else key
                                if lp_key in _lp_vals:
                                    _lp_vals[lp_key] = float(val)
                    except Exception as e:
                        logger.warning("[animate_portrait] Preset load failed: %s", e)

                # Save current values as preset (if name provided)
                if _lp_save:
                    try:
                        try:
                            from core.expression_presets import save_expression
                        except ImportError:
                            from ..core.expression_presets import save_expression  # type: ignore
                        # Strip lp_ prefix for storage
                        save_data = {k.removeprefix("lp_"): v for k, v in _lp_vals.items()}
                        save_expression(_lp_save, save_data)
                        logger.info("[animate_portrait] Saved preset '%s'", _lp_save)
                    except Exception as e:
                        logger.warning("[animate_portrait] Preset save failed: %s", e)

                result6 = await self._process_animate_portrait_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    driving_video=driving_video,
                    **_lp_vals,
                    lp_sample_image=str(kwargs.pop("lp_sample_image", "")),
                    lp_sample_ratio=float(kwargs.pop("lp_sample_ratio", 1.0)),
                    lp_sample_parts=str(kwargs.pop("lp_sample_parts", "all")),
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # Marigold mode (dense vision analysis)
            if no_llm_mode == "marigold":
                result6 = await self._process_marigold_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    marigold_output_type=kwargs.pop("marigold_output_type", "depth"),
                    marigold_colormap=kwargs.pop("marigold_colormap", "Spectral"),
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # Sapiens2 mode (Meta human-centric vision)
            if no_llm_mode == "sapiens2":
                result6 = await self._process_sapiens2_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    sapiens2_task=kwargs.pop("sapiens2_task", "pose"),
                    sapiens2_size=kwargs.pop("sapiens2_size", "1b"),
                    sapiens2_precision=kwargs.pop("sapiens2_precision", "auto"),
                    sapiens2_seg_alpha=kwargs.pop("sapiens2_seg_alpha", 0.5),
                    sapiens2_pose_kpt_thr=kwargs.pop("sapiens2_pose_kpt_thr", 0.3),
                    sapiens2_pose_radius=kwargs.pop("sapiens2_pose_radius", 6),
                    sapiens2_pose_thickness=kwargs.pop("sapiens2_pose_thickness", 4),
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # NormalCrafter mode (temporally consistent video normals)
            if no_llm_mode == "normalcrafter":
                result6 = await self._process_normalcrafter_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    normalcrafter_max_res=kwargs.pop("normalcrafter_max_res", "auto"),
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # Video Depth Anything mode (temporal depth estimation)
            if no_llm_mode == "video_depth":
                result6 = await self._process_video_depth_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    video_depth_encoder=kwargs.pop("video_depth_encoder", "vits"),
                    video_depth_colormap=kwargs.pop("video_depth_colormap", "gray"),
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # MiniMax-Remover mode
            if no_llm_mode == "minimax_remover":
                result6 = await self._process_minimax_remover_only(
                    prompt=prompt,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # FLUX Klein mode
            if no_llm_mode == "flux_klein":
                result6 = await self._process_flux_klein_only(
                    prompt=prompt,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    flux_smoothing=flux_smoothing,
                    flux_klein_model=flux_klein_model,
                    image_a=image_a,
                    _all_image_paths=_all_image_paths,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # Kiwi-Edit mode (native video editing via instruction/reference)
            if no_llm_mode == "kiwi_edit":
                result6 = await self._process_kiwi_edit_only(
                    prompt=prompt,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    image_a=image_a,
                    _all_image_paths=_all_image_paths,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # DreamID-Omni mode (identity-preserving talking-head generation)
            if no_llm_mode == "dreamid_omni":
                result6 = await _nollm.process_dreamid_omni_only(
                    prompt=prompt,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    image_a=image_a,
                    audio_a=audio_a,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # SVI mode (infinite-length video generation)
            if no_llm_mode == "svi":
                result6 = await self._process_svi_only(
                    prompt=prompt,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    image_a=image_a,
                    image_path_a=image_path_a,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # SHARP mode (single-image 3D Gaussian view synthesis)
            if no_llm_mode == "sharp":
                result6 = await self._process_sharp_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    image_a=image_a,
                    image_path_a=image_path_a,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # Wan-Animate mode (video-driven character animation)
            if no_llm_mode == "wan_animate":
                result6 = await self._process_wan_animate_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    image_a=image_a,
                    image_path_a=image_path_a,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # SCAIL-2 mode (native pose-driven character animation)
            if no_llm_mode == "scail2":
                result6 = await self._process_scail2_only(
                    prompt=prompt,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    image_a=image_a,
                    image_path_a=image_path_a,
                    mask_points=mask_points,
                    **kwargs,
                )
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # AI Upscale mode (spandrel-based super-resolution)
            if no_llm_mode == "ai_upscale":
                result6 = await self._process_ai_upscale_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    upscale_model=kwargs.pop("upscale_model", "realesrgan_x4plus"),
                    upscale_scale=int(kwargs.pop("upscale_scale", "4")),
                    tile_size=int(kwargs.pop("tile_size", "512")),
                    blockswap_blocks=int(kwargs.pop("blockswap_blocks", 0)),
                    seedvr_resolution=int(kwargs.pop("seedvr_resolution", "1080")),
                    rtx_quality=kwargs.pop("rtx_quality", "ULTRA"),
                    vae_tiling=bool(kwargs.pop("vae_tiling", True)),
                    vae_tile_preset=kwargs.pop("vae_tile_preset", "auto"),
                    vae_tile_size=int(kwargs.pop("vae_tile_size", 512)),
                    vae_tile_overlap=int(kwargs.pop("vae_tile_overlap", 64)),
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # Rembg background removal mode
            if no_llm_mode == "rembg":
                result6 = await self._process_rembg_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    rembg_model=kwargs.pop("rembg_model", "bria-rmbg"),
                    rembg_background=kwargs.pop("rembg_background", "transparent"),
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    _all_image_paths=_all_image_paths,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # Video Matting mode (MatAnyone2)
            if no_llm_mode == "video_matting":
                result6 = await self._process_video_matting_only(
                    prompt=_raw_prompt,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    matting_output=kwargs.pop("matting_output", "foreground"),
                    matting_background=kwargs.pop("matting_background", "green"),
                    matting_max_size=int(kwargs.pop("matting_max_size", 0)),
                    mask_output_type=kwargs.pop("mask_output_type", "black_white"),
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    image_a=image_a,
                    image_path_a=image_path_a,
                    video_path=video_path,
                    **kwargs,
                )
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # Onion Skin mode (temporal ghosting / composite)
            if no_llm_mode == "onion_skin":
                result6 = await self._process_onion_skin_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    onion_blend_mode=kwargs.pop("onion_blend_mode", "screen"),
                    onion_opacity=float(kwargs.pop("onion_opacity", 0.5)),
                    onion_decay=float(kwargs.pop("onion_decay", 0.97)),
                    _all_video_paths=_all_video_paths,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # PhyFPS mode (Visual Chronometer physical FPS analysis)
            if no_llm_mode == "phyfps":
                result6 = await self._process_phyfps_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    phyfps_action=kwargs.pop("phyfps_action", "analyze_only"),
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # Comparison mode (A/B video comparison)
            if no_llm_mode == "comparison":
                result6 = await self._process_comparison_only(
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    comparison_style=kwargs.pop("comparison_style", "swipe"),
                    comparison_labels=str(kwargs.pop("comparison_labels", "false")).lower() in ("true", "1", "yes"),
                    comparison_label_a=kwargs.pop("comparison_label_a", "Before"),
                    comparison_label_b=kwargs.pop("comparison_label_b", "After"),
                    _all_video_paths=_all_video_paths,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    **kwargs,
                )
                if _sam3_mask_path and result6[2]:
                    _nollm.sam3_composite(effective_video_path, result6[2], _sam3_mask_path, result6[2])
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # Text inputs connected → build a text overlay pipeline
            if _all_text_inputs:
                # Auto-generate a pipeline from text inputs
                text_steps = []
                for raw in _all_text_inputs:
                    try:
                        meta = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        meta = {"text": raw, "mode": "overlay"}
                    mode = meta.get("mode", "overlay")
                    if mode in ("subtitle",):
                        text_steps.append({
                            "skill": "burn_subtitles",
                            "params": {"path": "text_a"},
                        })
                    else:
                        text_steps.append({
                            "skill": "text_overlay",
                            "params": {
                                "text": meta.get("text", raw if isinstance(raw, str) else ""),
                                "position": meta.get("position", "center"),
                                "font_size": meta.get("font_size", 48),
                                "font_color": meta.get("font_color", "white"),
                            },
                        })
                if not text_steps:
                    text_steps = [{"skill": "text_overlay", "params": {"text": _all_text_inputs[0]}}]

                synth_pipeline = json.dumps({"steps": text_steps})
                logger.info("No-LLM: auto-generated text pipeline from %d text input(s)", len(_all_text_inputs))
                result6 = await self._process_effects_pipeline(
                    pipeline_json=synth_pipeline,
                    prompt=prompt,
                    effective_video_path=effective_video_path,
                    video_metadata=video_metadata,
                    save_output=save_output,
                    output_path=output_path,
                    preview_mode=preview_mode,
                    quality_preset=quality_preset,
                    crf=crf,
                    encoding_preset=encoding_preset,
                    whisper_device=whisper_device,
                    whisper_model=whisper_model,
                    sam3_device=sam3_device,
                    sam3_max_objects=sam3_max_objects,
                    sam3_det_threshold=sam3_det_threshold,
                    mask_points=mask_points,
                    use_flux_klein=use_flux_klein,
                    flux_klein_model=flux_klein_model,
                    use_kiwi_edit=use_kiwi_edit,
                    use_minimax_remover=use_minimax_remover,
                    use_dreamid_omni=use_dreamid_omni,
                    flux_smoothing=flux_smoothing,
                    temp_video_from_images=temp_video_from_images,
                    temp_video_with_audio=temp_video_with_audio,
                    image_a=image_a,
                    audio_a=audio_a,
                    _all_video_paths=_all_video_paths,
                    _all_image_paths=_all_image_paths,
                    _all_text_inputs=_all_text_inputs,
                    audio_resample_rate=audio_resample_rate,
                    **kwargs,
                )
                return result6 + (mask_points or "", _image_path_from_result6(result6), empty_mask)
            # manual mode without Effects Builder or text
            raise RuntimeError(
                "No-LLM 'manual' mode requires an Effects Builder node or "
                "FFMPEGA Text node. Connect one to the pipeline_json or "
                "text_a input, or switch no_llm_mode to 'sam3_masking', "
                "'transcribe', 'karaoke_subtitles', 'generate_audio', 'generate_music', 'generate_sample', 'fish_speech', 'audio_inpaint', 'audio_separate', 'ace_step', 'lip_sync', 'marigold', 'normalcrafter', 'video_depth', 'flux_klein', 'kiwi_edit', 'minimax_remover', or 'ai_upscale'."
            )
        # --- Build connected-inputs context string ---
        connected_inputs_str = self._build_connected_inputs_summary(
            images_a=images_a,
            _images_a_shape=_images_a_shape,
            video_path=video_path,
            audio_a=audio_a,
            image_a=image_a,
            _all_video_paths=_all_video_paths,
            _all_image_paths=_all_image_paths,
            _all_text_inputs=_all_text_inputs,
            video_metadata=video_metadata,
            **kwargs,
        )

        # --- Generate pipeline spec via LLM ---
        spec, connector = await _pa.generate_pipeline_spec(
            pipeline_generator=self.pipeline_generator,
            prompt=prompt,
            metadata_str=metadata_str,
            connected_inputs_str=connected_inputs_str,
            effective_video_path=effective_video_path,
            llm_model=llm_model,
            custom_model=custom_model,
            ollama_url=ollama_url,
            use_vision=use_vision,
            ptc_mode=ptc_mode,
        )

        # --- Build output path ---
        output_path, temp_render_dir = self._build_output_path(
            effective_video_path=effective_video_path,
            save_output=save_output,
            output_path=output_path,
            preview_mode=preview_mode,
        )

        # --- Assemble pipeline from LLM spec ---
        (
            pipeline, output_path, interpretation, warnings,
            estimated_changes, audio_source, audio_mode,
        ) = _pa.assemble_pipeline(
            Pipeline=Pipeline,
            spec=spec,
            effective_video_path=effective_video_path,
            output_path=output_path,
            video_metadata=video_metadata,
            quality_preset=quality_preset,
            crf=crf,
            encoding_preset=encoding_preset,
            whisper_device=whisper_device,
            whisper_model=whisper_model,
            sam3_device=sam3_device,
            sam3_max_objects=sam3_max_objects,
            sam3_det_threshold=sam3_det_threshold,
            mask_points=mask_points,
            use_flux_klein=use_flux_klein,
            flux_klein_model=flux_klein_model,
            use_kiwi_edit=use_kiwi_edit,
            use_minimax_remover=use_minimax_remover,
            flux_smoothing=flux_smoothing,
            audio_output_mode=audio_output_mode,
            composer=self.composer,
        )

        # --- Inject extra inputs (multi-input, audio muxing, etc.) ---
        (
            effective_video_path,
            temp_multi_videos,
            temp_audio_files,
            temp_frames_dirs,
            temp_audio_input,
        ) = self._inject_extra_inputs(
            pipeline=pipeline,
            effective_video_path=effective_video_path,
            image_a=image_a,
            _all_image_paths=_all_image_paths,
            _all_video_paths=_all_video_paths,
            _all_text_inputs=_all_text_inputs,
            audio_a=audio_a,
            **kwargs,
        )
        pipeline.input_path = effective_video_path

        # --- Compose command ---
        command = self.composer.compose(pipeline)

        # --- Movie-override: skill produced a pre-built video (VDA, Marigold) ---
        movie_override = pipeline.metadata.get("_movie_override")
        if movie_override and os.path.isfile(movie_override):
            import shutil
            shutil.copy2(movie_override, output_path)
            cmd_log = f"cp {movie_override} → {output_path}"
            unique_id = str(kwargs.get("unique_id", ""))
            hidden_prompt = kwargs.get("hidden_prompt") or {}
            try:
                from .nollm_modes import collect_frame_output
            except ImportError:
                from nodes.nollm_modes import collect_frame_output
            images_tensor, audio_out = collect_frame_output(
                media_converter=self.media_converter,
                output_path=output_path,
                unique_id=unique_id,
                hidden_prompt=hidden_prompt,
                removes_audio=True,
            )
            analysis = f"AI Skill produced video: {os.path.basename(movie_override)}"
            if hasattr(connector, 'close'):
                await connector.close()
            return (images_tensor, audio_out, output_path, cmd_log, analysis, "", mask_points or "", "", empty_mask)

        # --- Execute ---
        result, pipeline, command = await self._execute_pipeline(
            pipeline=pipeline,
            command=command,
            connector=connector,
            prompt=prompt,
            metadata_str=metadata_str,
            connected_inputs_str=connected_inputs_str,
            effective_video_path=effective_video_path,
            output_path=output_path,
            quality_preset=quality_preset,
            crf=crf,
            encoding_preset=encoding_preset,
            preview_mode=preview_mode,
            verify_output=verify_output,
            use_vision=use_vision,
            ptc_mode=ptc_mode,
            video_metadata=video_metadata,
            _all_text_inputs=_all_text_inputs,
        )

        # Close LLM connector
        if hasattr(connector, 'close'):
            await connector.close()  # type: ignore[union-attr]

        # Debug probe output duration
        try:
            import subprocess as _sp
            _probe = _sp.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1", output_path],
                capture_output=True, text=True
            )
            logger.debug("Output duration BEFORE audio mux: %s", _probe.stdout.strip())
        except Exception:
            pass

        # --- Build analysis string ---
        analysis = _oh.build_analysis_string(
            interpretation=interpretation,
            estimated_changes=estimated_changes,
            warnings=warnings,
            composer=self.composer,
            pipeline=pipeline,
            pipeline_generator=self.pipeline_generator,
            track_tokens=track_tokens,
            log_usage=log_usage,
            prompt=prompt,
        )

        # --- Handle audio output ---
        self._handle_audio_output(
            command=command,
            pipeline=pipeline,
            audio_a=audio_a,
            audio_source=audio_source,
            audio_mode=audio_mode,
            output_path=output_path,
            **kwargs,
        )
        removes_audio = "-an" in command.output_options

        # --- Collect frame/audio output ---
        unique_id = str(kwargs.get("unique_id", ""))
        hidden_prompt = kwargs.get("hidden_prompt") or {}
        images_tensor, audio_out = self._collect_frame_output(
            output_path=output_path,
            unique_id=unique_id,
            hidden_prompt=hidden_prompt,
            removes_audio=removes_audio,
            resample_rate=int(audio_resample_rate) if audio_resample_rate and audio_resample_rate != "off" else None,
        )

        hidden_extra_pnginfo = kwargs.get("extra_pnginfo")

        # --- Save first-frame workflow PNG ---
        if save_output and images_tensor is not None and images_tensor.shape[0] > 0:
            png_path = str(Path(output_path).with_suffix(".png"))
            self._save_workflow_png(
                images_tensor[0],
                png_path,
                hidden_prompt,
                hidden_extra_pnginfo,
            )

        # --- Generate mask output (must run BEFORE temp cleanup) ---
        mask_overlay_path = _oh.generate_mask_output(
            pipeline=pipeline,
            effective_video_path=effective_video_path,
            mask_output_type=kwargs.get("mask_output_type", "colored_overlay"),
        )

        # --- Cleanup temp files ---
        _oh.cleanup_temp_files(
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            temp_audio_input=temp_audio_input,
            temp_multi_videos=temp_multi_videos,
            temp_audio_files=temp_audio_files,
            temp_frames_dirs=temp_frames_dirs,
            temp_render_dir=temp_render_dir,
            save_output=save_output,
        )

        return (images_tensor, audio_out, output_path, command.to_string(), analysis, mask_overlay_path, mask_points or "", "", empty_mask)

    # ------------------------------------------------------------------ #
    #  Effects Builder support                                             #
    # ------------------------------------------------------------------ #

    async def _process_effects_pipeline(self, pipeline_json, prompt, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, whisper_device="cpu", whisper_model="large-v3", sam3_device="gpu", sam3_max_objects=5, sam3_det_threshold=0.7, mask_points="", use_flux_klein=False, flux_klein_model="4b", use_kiwi_edit=False, use_minimax_remover=False, use_dreamid_omni=False, flux_smoothing="none", temp_video_from_images=None, temp_video_with_audio=None, image_a=None, audio_a=None, _all_video_paths=None, _all_image_paths=None, _all_text_inputs=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_effects_pipeline(
            composer=self.composer, process_manager=self.process_manager,
            media_converter=self.media_converter,
            pipeline_json=pipeline_json, prompt=prompt,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            whisper_device=whisper_device, whisper_model=whisper_model,
            sam3_device=sam3_device, sam3_max_objects=sam3_max_objects,
            sam3_det_threshold=sam3_det_threshold, mask_points=mask_points,
            use_flux_klein=use_flux_klein,
            flux_klein_model=flux_klein_model,
            use_kiwi_edit=use_kiwi_edit,
            use_minimax_remover=use_minimax_remover,
            use_dreamid_omni=use_dreamid_omni,
            flux_smoothing=flux_smoothing,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            image_a=image_a, audio_a=audio_a,
            _all_video_paths=_all_video_paths,
            _all_image_paths=_all_image_paths,
            _all_text_inputs=_all_text_inputs,
            _inject_extra_inputs_fn=self._inject_extra_inputs,
            **kwargs,
        )
    # ------------------------------------------------------------------ #
    #  SAM3-only mode (no LLM)                                            #
    # ------------------------------------------------------------------ #

    async def _process_sam3_only(self, prompt, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, sam3_device, sam3_max_objects, sam3_det_threshold, mask_points, temp_video_from_images, temp_video_with_audio, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_sam3_only(
            media_converter=self.media_converter,
            prompt=prompt, effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset, sam3_device=sam3_device,
            sam3_max_objects=sam3_max_objects,
            sam3_det_threshold=sam3_det_threshold,
            mask_points=mask_points,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )
    # ------------------------------------------------------------------ #
    #  Whisper-only mode (no LLM)                                         #
    # ------------------------------------------------------------------ #

    async def _process_whisper_only(self, mode, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, whisper_device="cpu", whisper_model="large-v3", temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_whisper_only(
            media_converter=self.media_converter,
            mode=mode, effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            whisper_device=whisper_device, whisper_model=whisper_model,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )
    # ------------------------------------------------------------------ #
    #  MMAudio-only mode (no LLM)                                         #
    # ------------------------------------------------------------------ #

    async def _process_mmaudio_only(self, prompt, audio_output_mode, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_mmaudio_only(
            media_converter=self.media_converter,
            prompt=prompt, audio_output_mode=audio_output_mode,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  AudioX music-only mode (no LLM)                                    #
    # ------------------------------------------------------------------ #

    async def _process_audiox_music_only(self, prompt, audio_output_mode, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_audiox_music_only(
            media_converter=self.media_converter,
            prompt=prompt, audio_output_mode=audio_output_mode,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Foundation-1 sample-only mode (no LLM)                              #
    # ------------------------------------------------------------------ #

    async def _process_foundation1_only(self, prompt, audio_output_mode, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_foundation1_only(
            media_converter=self.media_converter,
            prompt=prompt, audio_output_mode=audio_output_mode,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Fish Speech TTS mode (no LLM)                                       #
    # ------------------------------------------------------------------ #

    async def _process_fish_speech_only(self, prompt, audio_output_mode, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_fish_speech_only(
            media_converter=self.media_converter,
            prompt=prompt, audio_output_mode=audio_output_mode,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #

    async def _process_ace_step_only(self, prompt, audio_output_mode, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_ace_step_only(
            media_converter=self.media_converter,
            prompt=prompt, audio_output_mode=audio_output_mode,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  AudioX inpaint-only mode (no LLM)                                  #
    # ------------------------------------------------------------------ #

    async def _process_audiox_inpaint_only(self, prompt, audio_output_mode, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_audiox_inpaint_only(
            media_converter=self.media_converter,
            prompt=prompt, audio_output_mode=audio_output_mode,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    async def _process_sam_audio_separate(self, prompt, audio_output_mode, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_sam_audio_separate(
            media_converter=self.media_converter,
            prompt=prompt, audio_output_mode=audio_output_mode,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Lip sync mode (no LLM)                                             #
    # ------------------------------------------------------------------ #

    async def _process_lip_sync_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, audio_a=None, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_lip_sync_only(
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            audio_a=audio_a,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Animate portrait mode (no LLM)                                     #
    # ------------------------------------------------------------------ #

    async def _process_animate_portrait_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, driving_video="", lp_rotate_pitch=0.0, lp_rotate_yaw=0.0, lp_rotate_roll=0.0, lp_blink=0.0, lp_eyebrow=0.0, lp_wink=0.0, lp_pupil_x=0.0, lp_pupil_y=0.0, lp_aaa=0.0, lp_eee=0.0, lp_woo=0.0, lp_smile=0.0, lp_retargeting_eyes=1.0, lp_retargeting_mouth=1.0, lp_crop_factor=1.6, lp_sample_image="", lp_sample_ratio=1.0, lp_sample_parts="all", temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_animate_portrait_only(
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            driving_video=driving_video,
            lp_rotate_pitch=lp_rotate_pitch,
            lp_rotate_yaw=lp_rotate_yaw,
            lp_rotate_roll=lp_rotate_roll,
            lp_blink=lp_blink,
            lp_eyebrow=lp_eyebrow,
            lp_wink=lp_wink,
            lp_pupil_x=lp_pupil_x,
            lp_pupil_y=lp_pupil_y,
            lp_aaa=lp_aaa,
            lp_eee=lp_eee,
            lp_woo=lp_woo,
            lp_smile=lp_smile,
            lp_retargeting_eyes=lp_retargeting_eyes,
            lp_retargeting_mouth=lp_retargeting_mouth,
            lp_crop_factor=lp_crop_factor,
            lp_sample_image=lp_sample_image,
            lp_sample_ratio=lp_sample_ratio,
            lp_sample_parts=lp_sample_parts,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Marigold mode (no LLM)                                             #
    # ------------------------------------------------------------------ #

    async def _process_marigold_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, marigold_output_type="depth", marigold_colormap="Spectral", temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_marigold_only(
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            marigold_output_type=marigold_output_type,
            marigold_colormap=marigold_colormap,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Sapiens2 mode (no LLM)                                             #
    # ------------------------------------------------------------------ #

    async def _process_sapiens2_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, sapiens2_task="pose", sapiens2_size="1b", sapiens2_precision="auto", sapiens2_seg_alpha=0.5, sapiens2_pose_kpt_thr=0.3, sapiens2_pose_radius=6, sapiens2_pose_thickness=4, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_sapiens2_only(
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            sapiens2_task=sapiens2_task,
            sapiens2_size=sapiens2_size,
            sapiens2_precision=sapiens2_precision,
            sapiens2_seg_alpha=sapiens2_seg_alpha,
            sapiens2_pose_kpt_thr=sapiens2_pose_kpt_thr,
            sapiens2_pose_radius=sapiens2_pose_radius,
            sapiens2_pose_thickness=sapiens2_pose_thickness,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  NormalCrafter mode (no LLM)                                        #
    # ------------------------------------------------------------------ #

    async def _process_normalcrafter_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, normalcrafter_max_res="auto", temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_normalcrafter_only(
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            normalcrafter_max_res=normalcrafter_max_res,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Video Depth mode (no LLM)                                          #
    # ------------------------------------------------------------------ #

    async def _process_video_depth_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, video_depth_encoder="vits", video_depth_colormap="gray", temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_video_depth_only(
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            video_depth_encoder=video_depth_encoder,
            video_depth_colormap=video_depth_colormap,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  AI Upscale mode (no LLM)                                            #
    # ------------------------------------------------------------------ #

    async def _process_ai_upscale_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, upscale_model="realesrgan_x4plus", upscale_scale=4, tile_size=512, blockswap_blocks=0, seedvr_resolution=1080, rtx_quality="ULTRA", temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_ai_upscale_only(
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            upscale_model=upscale_model,
            upscale_scale=upscale_scale,
            tile_size=tile_size,
            blockswap_blocks=blockswap_blocks,
            seedvr_resolution=seedvr_resolution,
            rtx_quality=rtx_quality,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  MiniMax-Remover mode (no LLM)                                       #
    # ------------------------------------------------------------------ #

    async def _process_minimax_remover_only(self, prompt, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_minimax_remover_only(
            media_converter=self.media_converter,
            prompt=prompt,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  SVI 2.0 Pro mode (no LLM)                                           #
    # ------------------------------------------------------------------ #

    async def _process_svi_only(self, prompt, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, image_a=None, image_path_a=None, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_svi_only(
            prompt=prompt,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            image_a=image_a,
            image_path_a=image_path_a,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  FLUX Klein mode (no LLM)                                            #
    # ------------------------------------------------------------------ #

    async def _process_flux_klein_only(self, prompt, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, flux_smoothing="none", image_a=None, _all_image_paths=None, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_flux_klein_only(
            media_converter=self.media_converter,
            prompt=prompt,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            flux_smoothing=flux_smoothing,
            image_a=image_a,
            _all_image_paths=_all_image_paths,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Kiwi-Edit mode (no LLM)                                              #
    # ------------------------------------------------------------------ #

    async def _process_kiwi_edit_only(self, prompt, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, image_a=None, _all_image_paths=None, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_kiwi_edit_only(
            media_converter=self.media_converter,
            prompt=prompt,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            image_a=image_a,
            _all_image_paths=_all_image_paths,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Rembg background removal mode (no LLM)                              #
    # ------------------------------------------------------------------ #

    async def _process_rembg_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, rembg_model="bria-rmbg", rembg_background="transparent", temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_rembg_only(
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            rembg_model=rembg_model,
            rembg_background=rembg_background,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Video Matting mode (no LLM) — MatAnyone2                            #
    # ------------------------------------------------------------------ #

    async def _process_video_matting_only(self, prompt, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, matting_output="foreground", matting_background="green", matting_max_size=0, mask_output_type="black_white", temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_video_matting_only(
            media_converter=self.media_converter,
            prompt=prompt,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            matting_output=matting_output,
            matting_background=matting_background,
            matting_max_size=matting_max_size,
            mask_output_type=mask_output_type,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    # ------------------------------------------------------------------ #
    #  Onion Skin mode (no LLM)                                            #
    # ------------------------------------------------------------------ #

    async def _process_onion_skin_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, onion_blend_mode="screen", onion_opacity=0.5, onion_decay=0.97, _all_video_paths=None, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_onion_skin_only(
            composer=self.composer,
            process_manager=self.process_manager,
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            onion_blend_mode=onion_blend_mode,
            onion_opacity=onion_opacity,
            onion_decay=onion_decay,
            _all_video_paths=_all_video_paths,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    async def _process_phyfps_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, phyfps_action="analyze_only", temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_phyfps_only(
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            phyfps_action=phyfps_action,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    async def _process_comparison_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, comparison_style="swipe", comparison_labels=False, comparison_label_a="Before", comparison_label_b="After", _all_video_paths=None, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_comparison_only(
            composer=self.composer,
            process_manager=self.process_manager,
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            comparison_style=comparison_style,
            comparison_labels=comparison_labels,
            comparison_label_a=comparison_label_a,
            comparison_label_b=comparison_label_b,
            _all_video_paths=_all_video_paths,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    async def _verify_output(self, connector, output_path, prompt, pipeline, effective_video_path, use_vision):
        """Delegate to execution_engine module."""
        return await _ee._verify_output(
            connector=connector, output_path=output_path,
            prompt=prompt, pipeline=pipeline,
            effective_video_path=effective_video_path,
            use_vision=use_vision,
            composer=self.composer,
            process_manager=self.process_manager,
            pipeline_generator=self.pipeline_generator,
        )
    @staticmethod
    def _audio_dict_to_wav(audio: dict) -> Optional[str]:
        """Delegate to output_handler module."""
        return _oh.audio_dict_to_wav(audio)

    @staticmethod
    def _probe_duration(video_path: str) -> float:
        """Delegate to output_handler module."""
        return _oh.probe_duration(video_path)

    @staticmethod
    def _extract_thumbnail_frame(video_path: str) -> torch.Tensor:
        """Delegate to output_handler module."""
        return _oh.extract_thumbnail_frame(video_path)

    @staticmethod
    def _save_workflow_png(first_frame, png_path, prompt, extra_pnginfo, extra_info=None):
        """Delegate to output_handler module."""
        return _oh.save_workflow_png(first_frame, png_path, prompt, extra_pnginfo, extra_info)

    async def _process_batch(self, video_folder, file_pattern, prompt, llm_model, quality_preset, ollama_url, custom_model, crf, encoding_preset, max_concurrent, save_output, output_path, use_vision=False, verify_output=False, ptc_mode="off", sam3_max_objects=5, sam3_det_threshold=0.7, mask_points="", pipeline_json="", use_flux_klein=False, flux_klein_model="4b", use_minimax_remover=False, flux_smoothing="none"):
        """Delegate to batch_processor module."""
        return await _bp.process_batch(
            analyzer=self.analyzer, composer=self.composer,
            process_manager=self.process_manager,
            pipeline_generator=self.pipeline_generator,
            media_converter=self.media_converter,
            video_folder=video_folder, file_pattern=file_pattern,
            prompt=prompt, llm_model=llm_model,
            quality_preset=quality_preset, ollama_url=ollama_url,
            custom_model=custom_model,
            crf=crf, encoding_preset=encoding_preset,
            max_concurrent=max_concurrent, save_output=save_output,
            output_path=output_path, use_vision=use_vision,
            verify_output=verify_output, ptc_mode=ptc_mode,
            sam3_max_objects=sam3_max_objects,
            sam3_det_threshold=sam3_det_threshold,
            mask_points=mask_points, pipeline_json=pipeline_json,
            use_flux_klein=use_flux_klein,
            flux_klein_model=flux_klein_model,
            use_minimax_remover=use_minimax_remover,
            flux_smoothing=flux_smoothing,
        )

    # ------------------------------------------------------------------ #
    #  SHARP mode (no LLM)                                                 #
    # ------------------------------------------------------------------ #

    async def _process_sharp_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, image_a=None, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate to nollm_modes module."""
        return await _nollm.process_sharp_only(
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            image_a=image_a,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    async def _process_wan_animate_only(self, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, image_a=None, image_path_a=None, temp_video_from_images=None, temp_video_with_audio=None, **kwargs):
        """Delegate Wan-Animate to nollm_modes module."""
        return await _nollm.process_wan_animate_only(
            media_converter=self.media_converter,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            image_a=image_a,
            image_path_a=image_path_a,
            temp_video_from_images=temp_video_from_images,
            temp_video_with_audio=temp_video_with_audio,
            **kwargs,
        )

    async def _process_scail2_only(self, prompt, effective_video_path, video_metadata, save_output, output_path, preview_mode, quality_preset, crf, encoding_preset, image_a=None, image_path_a=None, mask_points="", **kwargs):
        """Delegate native SCAIL-2 animation to the nollm_modes module."""
        return await _nollm.process_scail2_only(
            prompt=prompt,
            effective_video_path=effective_video_path,
            video_metadata=video_metadata, save_output=save_output,
            output_path=output_path, preview_mode=preview_mode,
            quality_preset=quality_preset, crf=crf,
            encoding_preset=encoding_preset,
            image_a=image_a,
            image_path_a=image_path_a,
            mask_points=mask_points,
            **kwargs,
        )

    @classmethod
    def IS_CHANGED(cls, video_path, prompt, seed=0, **kwargs):
        """Determine if the node needs to re-execute."""
        return f"{video_path}:{prompt}:{seed}"
