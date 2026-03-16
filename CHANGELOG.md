# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.18.0] - 2026-03-16

### Added
- **Kiwi-Edit Video Editing**: New AI-powered video editing using [Kiwi-Edit](https://github.com/showlab/Kiwi-Edit) (WAN 2.2-based). Text instruction, reference image, and combined modes. Supports FP8 (~5 GB) and BF16 (~10 GB) precision with automatic model download. Long video chunked processing with crossfade stitching. *(kiwi_edit no-LLM mode)*
  - **10 Advanced Widgets**: `kiwi_model`, `kiwi_precision`, `kiwi_resolution`, `kiwi_width`, `kiwi_height`, `kiwi_max_frames`, `kiwi_steps`, `kiwi_guidance`, `kiwi_block_swap`, `kiwi_long_video` — all dynamically shown only when `no_llm_mode = kiwi_edit`.
  - **4 New Model Options**: `kiwi_seed` (reproducibility), `kiwi_flow_shift` (denoising aggressiveness 1–15), `kiwi_task_type` (override auto-detected prompt enhancement), `kiwi_scheduler` (unipc/euler/heun/dpm++ sampling).
  - **SAM3 Toggle for Kiwi-Edit**: SAM3 pre-masking now available for `kiwi_edit` mode — generate a mask with SAM3, process with Kiwi-Edit, composite back. Backend was already wired; UI toggle was missing.
  - **FP8 Conversion Script**: New `scripts/convert_kiwi_edit_fp8.py` for creating FP8 scaled model variants.
  - **Task-Type Prompt Enhancement**: 5 task templates (global_style, local_change, background_change, local_remove, local_add) with temporal consistency hints. Overridable via `kiwi_task_type` widget.
  - **Runtime Scheduler Selection**: New `_set_scheduler()` function allows switching schedulers between runs without reloading the model pipeline.
- **RTX Video Super Resolution**: New NVIDIA RTX VSR AI upscaling using Video Effects SDK (nvvfx). Hardware-accelerated on RTX Tensor Cores for near-real-time performance. Three quality modes: upscale, denoise, deblur. Requires RTX GPU + NVIDIA driver 570+. *(rtx_vsr no-LLM mode)*
- **SeedVR AI Upscaling**: New SeedVR 2 integration for high-quality video upscaling. Vendored core with diffusion pipeline, alpha upscaling, and model caching. Supports 3B and 7B model variants. *(seedvr no-LLM mode)*
- **Expression Presets for FacePoke**: New `core/expression_presets.py` with predefined facial expression parameter sets for the FacePoke interactive face editor.
- **Multi-Input Skill Handler**: New `skills/handlers/multi_input.py` for concat, grid, split screen, and multi-input operations with proper FFmpeg filter chain orchestration.
- **Kiwi-Edit Model Mirror**: Weights hosted on AEmotionStudio HuggingFace repos with mirror-first download and upstream fallback.
- **Kiwi-Edit Tests**: New `tests/test_kiwi_edit.py` with 50 tests covering constants, model manager, cleanup, no-LLM mode, prompt enhancement, and path validation.

### Changed
- **Model Registry**: Added `kiwi_edit_instruct`, `kiwi_edit_reference`, `kiwi_edit_instruct_reference`, `rtx_vsr`, and `seedvr` entries to `core/model_manager.py`.
- **VRAM Utils**: Added Kiwi-Edit, RTX VSR, and SeedVR cleanup support.
- **Conditional Widget Visibility**: `kiwi_width` and `kiwi_height` are now hidden unless `kiwi_resolution = 'custom'`. Scheduler dropdown triggers visibility refresh.
- **Version**: Bumped to 2.18.0.

### Fixed
- **Kiwi-Edit BF16 Precision**: Fixed dtype handling for BF16 model loading that previously caused errors on some GPU configurations.
- **SAM3 UI Toggle**: Fixed `kiwi_edit` mode not appearing in the SAM3-eligible modes list in the TypeScript UI, preventing the `use_sam3` toggle from showing.

---

## [2.17.0] - 2026-03-15

### Added
- **FacePoke Interactive Face Editor**: New full-featured face editing modal powered by LivePortrait. Edit facial expressions in real-time with slider controls for 16 parameters (pitch, yaw, roll, blink, eyebrow, smile, pupil, mouth shapes), per-frame editing with undo/redo, filmstrip frame scrubber with frame numbers and hover-scrolling, emotion presets (happy, sad, angry, surprised, wink, thoughtful, neutral), face landmark visualization, and Blaze Detect fallback mode. Professional SVG icon library throughout.
  - **Driving Video Reference**: Upload a driving video to transfer facial motion across all source frames. Relative motion with configurable multiplier (0.1–2.0x). Server-side keypoint extraction and caching.
  - **Reference Image Expression**: Upload a face image to transfer its expression to any frame. Configurable ratio (0–1), parts selection (all, mouth only, eyes only, rotation only), and slider edits stack on top.
  - **Face Detection Caching**: Face bounding boxes cached per-frame on first detection, reused for subsequent previews and edits. Eliminates redundant face detection when no changes have been made.
  - **Improved Paste-Back Quality**: Replaced naive 256px downscale paste-back with proper `_paste_back` function using full 512×512 model output, LANCZOS4 interpolation, and tightened blending mask (ellipse 235×250, kernel 51×51).
- **Shader Effects System**: Extensive GPU-accelerated shader overlay system with shader chaining (up to 3 layers), animation speed control, hue shift, customizable blend modes, temporal phase offset, JSON parameter overrides, resolution scaling, and random shader selection mode.
- **Multi-Input Skill Handler**: New `multi_input.py` handler for concat, grid, split screen, and other multi-input operations with proper FFmpeg filter chain orchestration.
- **Onion Skin Compositing**: Onion skin no-LLM mode now auto-detects extra video inputs and switches to composite mode, building multi-input FFmpeg `blend` filter pipelines.
- **Flux Klein FP8 Model**: New FP8 variant dropdown for Flux Klein — ~50% VRAM reduction with per-tensor scaling for quality preservation.
- **Audio Output Mode**: Generalized `audio_output_mode` parameter across all audio processing nodes (`generate_audio`, `generate_music`, `audio_inpaint`, `ace_step`, `audio_separate`) with `auto` and `save_only` options.
- **SAM3 Toggle**: New toggleable SAM3 control in the UI for easier masking workflow management.
- **Marigold Appearance Mode**: New `appearance` estimation mode for Marigold dense vision pipeline.
- **New Visual Skills**: Added `hdr_enhancement` and related visual effect skills to the skill registry.

### Changed
- **LivePortrait Expression Range**: Increased pitch/yaw/roll multipliers for much more pronounced head movement, matching KiJai's implementation. Fixed independent left/right eye and eyebrow controls.
- **FacePoke UI Polish**: Removed all emojis and replaced with professional Lucide SVG icons. Added frame count numbers to filmstrip thumbnails. Made filmstrip frames scrollable on hover. Added first/last frame jump buttons.
- **Video Editor**: Updated segment management and transport controls. Improved SAM3 toggle integration.
- **Drop Animation UX**: Increased drag-and-drop upload feedback timeout from 100ms to a longer duration for reliable visual feedback across all nodes.
- **Node Widget Visibility**: Dynamic widget visibility improvements for shader, SAM3, and audio mode controls.

### Fixed
- **FacePoke Blur**: Fixed severe blur in modified faces caused by 512→256px downscaling during paste-back. Now preserves full model resolution.
- **FacePoke Blaze Fallback**: Changed from auto-fallback (too sensitive) to manual-only toggle, preventing incorrect model selection.
- **LivePortrait Left/Right Controls**: Fixed independent eye and eyebrow controls (left/right split) that previously only worked in "both" mode.
- **Animate Portrait Tests**: Updated test assertions for new parameter signatures.
- **Audio Handler Consistency**: Aligned `audio_output_mode` parameter naming across all audio generation/processing handlers.

---

## [2.16.0] - 2026-03-13

### Added
- **ACE-Step AI Music Generation**: New ACE-Step 1.5 integration for AI-powered music generation and audio repainting directly within ComfyUI. Supports text-to-music, style-guided cover/repaint of existing audio tracks, and automatic lyrics generation via ACE-Step's 1.7B language model. *(ace_step no-LLM mode)*
  - **7 Advanced Widgets**: `ace_negative_prompt`, `ace_cover_strength`, `ace_steps`, `ace_cfg_scale`, `ace_bpm`, `ace_key`, `ace_time_sig` — all dynamically shown only when `no_llm_mode = ace_step` with advanced options enabled.
  - **Auto Lyrics Generation**: When no manual lyrics are provided via `text_a`, ACE-Step's LM auto-generates structured lyrics with section markers (`[verse]`, `[chorus]`) from the prompt.
  - **Reference Audio**: Connect any audio to `audio_a` — automatically detected and used as style reference for ACE-Step generation.
  - **BPM/Key/Time Signature Control**: User-specified musical metadata injected into the LM's chain-of-thought generation for precise control over rhythm, key, and meter.
  - **Cover/Repaint Mode**: When a video has audio but no prompt is given, ACE-Step repaints the existing audio with configurable `cover_strength` (0.0 = preserve original, 1.0 = full creative freedom).
- **SAM-Audio Source Separation**: New AI-powered audio source separation using SAM-Audio (Separate Anything in Audio). Splits audio into stems (vocals, drums, bass, other) with component-level VRAM offloading. Supports `large` and `large-fp8` variants with automatic model download. *(audio_separate no-LLM mode)*
  - **FP8 Scaled Variant**: Custom FP8 conversion of SAM-Audio large model (~50% VRAM reduction) with per-tensor scaling factors for inference quality preservation.
  - **Component Offloading**: Individual model components (encoder, separator, decoder) loaded/unloaded sequentially to minimize peak VRAM usage.
- **AudioX Vocal Enhancement**: New AudioX integration for AI-powered vocal enhancement, speech restoration, and audio quality improvement. Processes audio through a transformer-based enhancement model with automatic VRAM offloading. *(audiox no-LLM mode)*
  - **Standalone No-LLM Mode**: New `audiox` option in the `no_llm_mode` dropdown — enhance audio directly without an LLM.
  - **ACE-Step Chaining**: When both AudioX and ACE-Step are enabled, AudioX output is automatically fed to ACE-Step for one-click music upgrading.
  - **Model Mirror**: Weights hosted on [AEmotionStudio/audiox](https://huggingface.co/AEmotionStudio/audiox) with mirror-first download and upstream fallback.
- **AI Music Generation Skill (`generate_music`)**: New `generate_music` skill with handler for LLM-driven music generation via ACE-Step. Registered with 8 aliases (`make_music`, `compose_music`, `create_music`, `music_gen`, `ai_music`, `music_ai`, `compose_audio`, `make_audio`).
- **Audio Inpainting Skill (`audio_inpaint`)**: New `audio_inpaint` skill for AI-powered audio repair and enhancement using AudioX/ACE-Step pipeline.
- **Video Editor v2 — 10 New Panels**: Major NLE video editor expansion with 10 new editing panels:
  - **Color Grading Panel**: Exposure, contrast, saturation, temperature, tint, highlights, shadows, vibrance controls with real-time FFmpeg filter preview.
  - **Filters Panel**: Collection of filter presets (Warm, Cool, Vintage, Noir, Vivid, Dramatic, Pastel, Sepia, Cross Process, Bleach Bypass) with one-click application.
  - **Keyframe Editor**: Per-segment keyframe animation for speed and volume with visual keyframe tracks. Supports ease-in/out interpolation.
  - **Relight Panel**: AI-powered scene relighting using IC-Light with configurable prompt, strength, guidance scale, steps, and background modes.
  - **Transform Panel**: Scale, rotate, flip, position controls with FFmpeg filter chain generation.
  - **Compositing Panel**: Picture-in-Picture, watermark, blend modes, chroma key, vignette, and mask compositing tools.
  - **AI Compose Panel**: AI-powered composition suggestions and automatic edit generation.
  - **Captions Panel**: Text overlay and subtitle editing with position, timing, font, and style controls.
  - **Export Settings Panel**: Detailed export configuration with resolution, codec, CRF, preset, format, and audio settings.
  - **Speed Control**: Dedicated speed adjustment tool with preset buttons and custom value input.
- **NLE Audio Repaint Region**: Per-segment ACE-Step audio repaint toggle and strength control in the AudioMixer panel. Mark individual audio segments for AI repainting with adjustable strength (0–100%).
- **NormalCrafter Surface Normal Estimation**: New AI-powered surface normal estimation from video using [NormalCrafter](https://github.com/Binyr/NormalCrafter). Generates temporally consistent normal maps from monocular video with configurable max resolution. Supports SVD-based architecture with automatic model download. *(normalcrafter no-LLM mode)*
  - **`normalcrafter_max_res` Widget**: Configurable maximum resolution for NormalCrafter inference, shown only when `normalcrafter` mode is active.
  - **Model Mirror**: Weights hosted on [AEmotionStudio/NormalCrafter](https://huggingface.co/AEmotionStudio/NormalCrafter) for supply chain resilience.
- **Video Depth Anything**: New AI-powered temporal video depth estimation using [Video Depth Anything](https://github.com/DepthAnything/Video-Depth-Anything). Generates consistent depth maps from monocular video with three model variants (`vits`, `vitb`, `vitl`). Features configurable encoder selection and colormap output. *(video_depth no-LLM mode)*
  - **`video_depth_encoder` Widget**: Select model variant (small/base/large) based on VRAM/quality tradeoff, shown only when `video_depth` mode is active.
  - **`video_depth_colormap` Widget**: Choose depth visualization colormap (Spectral, Inferno, etc.).
  - **Model Mirror**: Weights hosted on [AEmotionStudio/video-depth-anything](https://huggingface.co/AEmotionStudio/video-depth-anything).
- **Dynamic Widget Visibility Improvements**: `sam_audio_model` and `normalcrafter_max_res` widgets now conditionally visible only when their respective no-LLM modes are active, reducing UI clutter.
- **Install Scripts**: New `install-all-deps.sh` and `install-all-deps.bat` for one-command installation of all optional dependencies (torchaudio, accelerate, rembg, etc.).
- **Optional Requirements**: New `requirements-optional.txt` organizing optional dependencies by feature area (ACE-Step, SAM-Audio, AudioX, IC-Light, etc.).

### Changed
- **Model Registry**: Added `sam_audio`, `sam_audio_fp8`, `audiox`, and `acestep` entries to `core/model_manager.py` with sizes, HuggingFace repos, and download instructions.
- **VRAM Utils**: Enhanced `_vram_utils.py` with SAM-Audio and ACE-Step cleanup support.
- **Video Editor Export Pipeline**: Integrated color grading, filter presets, keyframe-based speed/volume, relighting, transforms, compositing, and caption rendering into the FFmpeg export pipeline with proper filter chain orchestration.
- **Node Widget Count**: Agent node now features 7 additional ACE-Step input widgets under the advanced toggle.
- **AudioSegment Data Model**: Extended with `aceRepaint` and `aceRepaintStrength` fields for per-segment AI audio repaint marking, with full serialize/deserialize support.

### Fixed
- **ACE-Step Fallback Test**: Fixed `test_fallback_when_no_acestep` by mocking `is_available` to return `False` now that ACE-Step is installed.
- **Audio Segment Init**: All `AudioSegment` creation paths now include the new `aceRepaint` fields, preventing TypeScript compilation errors.
- **Keyframe Application**: Wired keyframe application into the export pipeline to prevent no-op keyframes.
- **Blend Compose Skip Log**: Added skip log for blend compose mode when no blend target is specified.

---

## [2.15.0] - 2026-03-09

### Added
- **MiniMax-Remover Integration**: New toggleable AI object removal powered by [MiniMax-Remover](https://github.com/zibojia/MiniMax-Remover). Purpose-built DiT model for video inpainting with 81-frame batch processing and sliding-window support for longer videos. ~2.5 GB model, significantly lighter than FLUX Klein (~15 GB). ⚠️ Model weights are CC-BY-NC-4.0 (non-commercial); code is Apache 2.0. *(PR #161)*
  - **Tiered Removal Priority**: New removal hierarchy — MiniMax-Remover (highest, when `use_minimax_remover=On`) → FLUX Klein (when `use_flux_klein=On`) → LaMa → black fill (FFmpeg). Each tier automatically falls back to the next if disabled or unavailable.
  - **`use_minimax_remover` Toggle**: New node-level boolean toggle on the FFMPEG Agent. Threaded through all pipeline paths (LLM, effects builder, batch, SAM3-only) via `_enable_minimax_remover` metadata key. Defaults to `False`.
  - **`minimax_remover` No-LLM Mode**: New `minimax_remover` option in the `no_llm_mode` dropdown — run MiniMax-Remover directly without an LLM. Uses SAM3 for mask generation with full-frame fallback.
  - **Vendored Core Components**: `pipeline_minimax_remover.py` and `transformer_minimax_remover.py` vendored into `core/minimax/` with attribution headers citing the original [MiniMax-Remover repository](https://github.com/zibojia/MiniMax-Remover) and paper.
  - **Sliding-Window Batching**: Videos exceeding 81 frames are processed in overlapping windows with configurable overlap (default 8 frames) and temporal smoothing (Gaussian/adaptive) for seamless transitions.
  - **VRAM Management**: Explicit model loading/unloading with `gc.collect()` + `torch.cuda.empty_cache()`. Other models (FLUX Klein, LaMa) are freed before loading MiniMax-Remover.
  - **Model Mirror**: Weights mirrored to [AEmotionStudio/minimax-remover](https://huggingface.co/AEmotionStudio/minimax-remover) with mirror-first download and upstream fallback.
- **AI Upscaler `tile_size` Parameter**: New `tile_size` parameter for AI upscaling — forwarded through no-LLM mode and LLM skill paths. Enables fine-grained VRAM control via configurable upscaler tile dimensions.
- **Auto-VRAM Tile Sizing**: AI upscaler automatically calculates optimal tile size based on available VRAM and model memory budget, eliminating manual tuning for different GPUs.
- **Upscaler Disk Space Pre-Check**: Disk space validation before video frame extraction prevents failures mid-render on low-storage systems.
- **Video Depth Anything License**: Added Apache 2.0 license file for the vendored Video Depth Anything module. *(commit cec11e7)*
- **5 New No-LLM Modes**: Added `ai_upscale`, `video_depth`, `flux_klein`, `minimax_remover`, and `animate_portrait` to the `no_llm_mode` dropdown — run each AI backend directly without an LLM.
- **MiniMax-Remover Tests**: New `tests/test_minimax_remover.py` with 26 tests covering constants, model manager, cleanup, no-LLM mode registration, toggle, auto_mask priority, metadata propagation, and vendored imports.

### Changed
- **Model Registry**: Added `minimax_remover` to `core/model_manager.py` with size, HuggingFace repo, license (CC-BY-NC-4.0 for weights), and manual download instructions.
- **FFmpeg Binary Path Consolidation**: Centralized all `_get_ffmpeg_bin()` and `_get_ffprobe_bin()` wrappers across `lama_inpainter.py`, `upscaler.py`, `vda_synthesizer.py`, and `marigold_synthesizer.py` into direct imports from `core/bin_paths.py`. Eliminates duplicated wrapper functions.
- **VRAM Cleanup Overhaul**: Refactored VRAM cleanup across all synthesizers — pipelines are now transferred to CPU before cleanup, only loaded modules are processed, and redundant `torch.cuda.synchronize()` / `gc.collect()` calls removed. Reduces cleanup overhead and prevents VRAM fragmentation.
- **Upscaler Image I/O**: Switched upscaler frame reading/writing from PIL to OpenCV for consistency with other synthesizers and better performance.
- **Upscaler 1-Based Frame Indexing**: Frame numbering now starts at 1 to align with ffmpeg's extraction output, ensuring correct frame ordering.
- **Visual Skill Caching**: AI-powered visual skill cache keys now include the model name, preventing stale cache hits when switching between AI backends.
- **LoadVideoPathNode Output Reorder**: Reordered `LoadVideoPathNode` outputs for more logical grouping; added `crop_data` at index 5.
- **Sidebar Docs**: Updated performance tips and widget documentation to include MiniMax-Remover.
- **CI Coverage Threshold**: Lowered from 34% to 25% to account for torch-dependent tests being skipped in CI.
- **Test Suite**: Expanded from 1,131 to **1,182 tests**, 0 failures.

### Fixed
- **VRAM Cleanup Style**: Refactored `flux_klein_editor._free_vram()` from 9 individual import+cleanup blocks to a loop-over-list pattern, matching the style used in all other synthesizers. Prevents missed modules when adding new AI backends.
- **Upscaler Audio Mux Path**: Fixed `upscale_video` audio mux using `str.replace(".mp4", ...)` which could corrupt paths containing `.mp4` in directory names or non-MP4 extensions. Now uses `Path.with_suffix()`.
- **Video Editor WAV Parsing**: Fixed `_extract_audio()` WAV `data` chunk search starting at byte 0, which could false-match metadata fields. Now starts at byte 12 (past RIFF/WAVE header).
- **Video Editor Auto-Resume**: Guarded `app.queuePrompt()` calls to only resume when `pause_on_input` is enabled, preventing unexpected re-execution when the editor is used outside the pause flow.
- **AI Upscale Temp Copy**: Eliminated redundant temp directory creation in `process_ai_upscale_only` — copies directly from upscaler output to final path.
- **Video Dimension Padding**: FFmpeg output dimensions are now padded to even values, preventing pixel misalignment errors with `libx264` on odd-resolution sources.
- **FFmpeg Framerate Compatibility**: Framerate values are now formatted as integers or two-decimal strings, fixing compatibility issues with certain ffmpeg builds that reject full-precision floats.
- **Mask Padding Robustness**: MiniMax-Remover mask padding now copies PIL Image objects before resizing, preventing mutation of shared image references.
- **Mask Fallback Resolution**: MiniMax-Remover fallback mask resolution dynamically uses the video frame size instead of a hardcoded 640×480.
- **VRAM Module Lookup**: `_vram_utils.py` now correctly handles modules loaded under ComfyUI's package structure when resolving `sys.modules` entries.
- **Video Editor Input Priority**: Changed from `images > video_path` to `video_path > images` to match `LoadVideoPathNode` behavior.
- **CI Torch Import Skips**: Added `pytest.importorskip("torch")` guards to all tests importing from `nodes.*` or `core.minimax.*`, preventing `ModuleNotFoundError` in CI environments without PyTorch.

## [2.14.0] - 2026-03-08

### Added
- **Video Editor Node**: New interactive NLE (Non-Linear Editor) node for hands-on video editing directly inside ComfyUI. Features a full-screen modal with timeline, transport controls, and editing tools — no LLM required. *(PR #155)*
  - **Timeline Editing**: Visual timeline with drag-to-select, razor tool (split at playhead), and segment deletion. Undo/redo with `Ctrl+Z` / `Ctrl+Shift+Z`.
  - **Speed Control**: Per-segment speed adjustment (0.25×–4×) with `setpts`/`atempo` filter chaining for values outside FFmpeg's native 0.5–2.0 range.
  - **Volume & Mute**: Per-segment volume control (0–200%) and mute toggle via `volume` audio filter.
  - **Crop Tool**: Interactive crop overlay with drag handles and real-time preview. Applies FFmpeg `crop` filter on export.
  - **Text Overlays**: Add positioned text with configurable font size, color, and timing via FFmpeg `drawtext` filter. Correct escaping for colons, backslashes, and special characters.
  - **Transitions**: Crossfade and dip-to-black transitions between segments using FFmpeg `xfade`/`acrossfade` filters. Configurable duration per transition.
  - **Multi-Stage Render Pipeline**: Exports through trim → speed → transitions → text overlay → crop → audio stages, with `cancel_event` threading for clean cancellation of long renders.
  - **Keyboard Shortcuts**: Space (play/pause), J/K/L (shuttle), I/O (mark in/out), Left/Right (frame step), R (razor), V (select), Delete, and more. `?` opens shortcut overlay.
- **Seekable MP4 Preview Server**: New `/ffmpega/preview` route with HTTP Range support, `mtime`-based cache keys, and LRU in-memory caching for instant video previews in the editor. *(PR #155)*
- **Shared `images_to_video` Utility**: New `core/images_to_video.py` extracts the image-tensor-to-video conversion into a reusable function, eliminating duplication across `VideoEditorNode` and `VideoToPathNode`. *(PR #155)*
- **Shared UI Helpers**: Extracted common upload, drag-and-drop, and UI utility code from `ffmpega_ui.js` into `web/ui_helpers.js` for reuse across nodes. *(PR #155)*
- **Video Editor Tests**: New `tests/test_video_editor.py` with 40+ tests covering segment parsing, speed filter building, volume filters, text overlay escaping, crop filter generation, transition building, and cache logic. *(PR #155)*

### Changed
- **TypeScript Migration**: Video Editor frontend built in TypeScript (`src/videoeditor/*.ts`) with Vite build pipeline. Compiled bundles committed to `web/` per ComfyUI extension convention. *(PR #155)*
- **Node Count**: Updated from 8 to **9 nodes** (added Video Editor).
- **Test Suite**: Expanded from 952 to **1,056 tests**, 0 failures.

---

## [2.13.0] - 2026-03-06

### Added
- **FLUX Klein Toggle (`use_flux_klein`)**: New node-level boolean toggle to enable/disable FLUX Klein 4B inference. Threaded through all 5 pipeline paths (LLM, effects builder, batch, SAM3-only, whisper-only) via `_enable_flux_klein` metadata key. Defaults to `False` for zero-VRAM baseline. *(PR #150)*
- **Edit FFmpeg Fallback (`_edit_ffmpeg_fallback`)**: When FLUX Klein is disabled, `auto_mask:effect=edit` now falls back to keyword-matched FFmpeg color/tone filters (22 keywords across 12 color + 10 tone categories) applied via `maskedmerge`. Uses word-boundary regex matching to prevent false positives. Zero VRAM. *(PR #150)*
- **AI Background Removal (`remove_background`)**: Full per-frame implementation using [BRIA RMBG](https://huggingface.co/briaai/RMBG-2.0) via `rembg`. Extracts frames with OpenCV, generates alpha masks, writes a lossless FFV1 mask video, and composites via FFmpeg `maskedmerge` or `alphamerge` (transparent mode). New `background` parameter supports `transparent` or any color name/hex for solid-color replacement. *(PR #146)*
- **Background Removal Model Choices**: Expanded `remove_background` model selection from 3 choices (`silueta`, `u2net`, `isnet`) to 6 choices (`bria-rmbg` default, `birefnet-general`, `birefnet-general-lite`, `isnet-general-use`, `u2net`, `silueta`). *(PR #146)*

### Fixed
- **FLUX Klein Cache Coherence**: Cache reuse for FLUX Klein outputs is now gated by the `_enable_flux_klein` toggle — prevents stale AI outputs from being used when the user switches to FFmpeg fallback mode. *(PR #150)*
- **`remove` Effect Fallback**: When FLUX Klein is disabled, `auto_mask:effect=remove` falls back to LaMa inpainting instead of attempting FLUX Klein inference. *(PR #150)*

### Changed
- **Resource Stewardship Defaults**: `use_vision` and `verify_output` defaults changed from `True` to `False` across `agent_node.py` and `batch_processor.py`. High-resource features are now opt-in, reducing token usage and processing time by default. *(PR #150)*
- **`import re` Cleanup**: Hoisted `import re` from function-level to module-level in `visual.py`, removing duplicate imports. *(PR #150)*
- **♿ Mask Editor Accessibility**: Mask Editor buttons (`modeToggle`, `clearBtn`, `applyBtn`, `cancelBtn`) now wrap emojis in `<span aria-hidden="true">` and set explicit `aria-label` attributes — prevents screen readers from announcing decorative icons. *(PR #148)*
- **AI-Powered Skills Count**: Updated from 6 to 7 (added `remove_background` with BRIA RMBG).
- **Model Registry**: Updated `remove_background` model entry from U²-Net (~170 MB) to BRIA RMBG (~270 MB).
- **Test Suite**: Expanded from 939 to **952 tests**, 0 failures.

---

## [2.12.0] - 2026-03-06

### Added
- **AI Face Animation (`animate_portrait`)**: New skill powered by [LivePortrait](https://github.com/KlingAIResearch/LivePortrait) — transfers facial motion from a driving video onto a source portrait. Uses appearance feature extraction, motion keypoints, stitching/retargeting, and a SPADE generator for high-quality output. Supports both image and video sources with per-frame face detection, affine crop/paste-back with elliptical Gaussian-blurred blending, relative motion mode, and configurable driving multiplier. In-process inference with automatic GPU↔CPU offloading. 7 aliases (`live_portrait`, `face_animate`, `face_animation`, `face_reenact`, `puppet`, `face_swap_video`, `motion_transfer`).
- **LivePortrait No-LLM Mode (`animate_portrait`)**: New `animate_portrait` option in the `no_llm_mode` dropdown — animates a face directly without any LLM. Source face from `video_path`/`images_a`, driving video from `video_a`. Full zero-prompt support.
- **LivePortrait Model Mirror**: 5 model weights (appearance extractor, motion extractor, warping module, SPADE generator, stitching/retargeting) converted from `.pth` to `.safetensors` and hosted on `AEmotionStudio/liveportrait-models` (~497 MB total). Mirror-first download with automatic fallback to upstream `.pth` files.
- **LivePortrait Tests**: New `tests/test_animate_portrait.py` with 30 tests covering skill registration, model manager integration, handler dispatch, aliases, synthesizer functions, and no-LLM mode wiring.
- **LaMa Safetensors Conversion**: Converted `big-lama.pt` (TorchScript JIT) to `big-lama.safetensors` (194.9 MB, 989 tensors) — eliminates pickle warnings and security flags on HuggingFace. `lama_inpainter.py` updated to prefer safetensors with graceful `.pt` fallback.

### Fixed
- **MediaPipe `mp.solutions` Crash**: `_detect_face_bbox` in LivePortrait was using the deprecated `mp.solutions.face_detection` API (removed in newer MediaPipe). Replaced with the existing `musetalk.face_detection.get_face_bbox()` which uses the Tasks API (`FaceLandmarker`).
- **LivePortrait RGB/BGR Mismatch**: Model output is RGB but canvas is BGR — added `cv2.cvtColor(out, cv2.COLOR_RGB2BGR)` in `_warp_decode` to fix discolored output.
- **LivePortrait Paste-Back Affine Transform**: Fixed broken 512→canvas affine math in `_paste_back` — was multiplying rotation/scale by 2 instead of dividing (for affine `y = (A/2)·x₅₁₂ + b`).
- **LivePortrait Box Outline**: Replaced 20px rectangular feather mask with elliptical Gaussian-blurred mask (220×240 semi-axes, 101×101 kernel) for seamless face blending.

### Changed
- **LaMa Model Registry**: Updated `model_manager.py` mirror filename from `big-lama.pt` to `big-lama.safetensors`.
- **AI-Powered Skills Count**: Updated from 5 to 6 (added `animate_portrait`).
- **Test Suite**: Expanded from 909 to **939 tests**, 0 failures.

---

## [2.11.0] - 2026-03-05

### Added
- **MMAudio In-Process Inference**: Migrated MMAudio audio generation from subprocess isolation to in-process execution with full GPU↔CPU offloading. Eliminates subprocess overhead while maintaining VRAM safety. Subprocess fallback preserved for edge cases.
- **`generate_audio` No-LLM Mode**: New `generate_audio` option in the `no_llm_mode` dropdown — synthesize audio from video content and/or text prompt directly without an LLM.
- **MCP Progressive Disclosure**: MCP tool discovery now uses progressive disclosure — `list_tools` returns summarized tool info, `get_tool_details` provides full schemas on demand. Reduces initial context window pressure. *(PR #144)*
- **MCP New Tools**: Added `validate_skill_params` and `cleanup_vision_frames` tool definitions with path-traversal guards. `analyze_video` gains input validation guard. *(PR #144)*
- **CLI Binary Resolution Caching**: All CLI connector binary lookups (`gemini`, `claude`, `cursor-agent`, `qwen`) now use `@functools.cache` — eliminates repeated `shutil.which()` calls on every invocation. *(PR #143)*

### Fixed
- **Lip Sync Filter Composition**: Fixed FFmpeg filter chain not correctly applying video filters (denoise, color correction, etc.) to the lip-synced output. Filters now correctly chain through the output labels generated by the `lip_sync` skill.
- **FLUX Klein Memory**: Optimized FLUX Klein memory usage — explicit `gc.collect()` per frame, runtime assertions in `_encode_video_from_dir`, freed `mask_np_list` after temporal smoothing pass.
- **MCP Dispatch**: Fixed `call_tool` dispatch dictionary and `detail` parameter documentation for `execute_code`. Propagated `analyze_video` in-band errors and `cleanup_vision_frames` return value. Added `video_path` to tool definition schemas. *(PR #144)*
- **FFmpeg Binary Wrappers**: Consolidated duplicate `_get_ffmpeg_bin` wrappers across modules, increased chunk timeout for large video processing.
- **CI**: Skip no-LLM-mode tests when torch is unavailable in CI environment.

### Changed
- **Focus Accessibility**: Improved focus visibility for interactive widgets across the UI — consistent focus rings and keyboard navigation. *(PR #142)*
- **MCP Architecture**: Dispatch table derived from `_tools` dict instead of separate mapping. Minor cleanups and input_examples added to schemas. *(PR #144)*
- **Test Suite**: Expanded from 799 to **909 tests**, 0 failures.

---

## [2.10.0] - 2026-03-04

### Added
- **FLUX Klein In-Process Migration**: Migrated FLUX Klein 4B from subprocess to in-process inference with managed VRAM offloading. Eliminates subprocess overhead while maintaining memory safety via explicit model loading/unloading.
- **Mask Drawing UI**: New interactive mask drawing overlay — paint masks directly on video frames for targeted AI editing (remove/edit effects). Integrates with the SAM3 and FLUX Klein pipelines.
- **Model Output Caching**: FLUX Klein caches model outputs for identical inputs — avoids redundant inference when re-processing the same frame.

### Fixed
- **Green Overlay Accumulation**: Fixed colored overlay mask accumulating across frames in multi-frame SAM3 processing.
- **`force_rate` No-Op Guard**: Added guard to prevent `force_rate=0` from triggering unnecessary re-encoding.
- **Mask Dimension Guard**: Added explicit dimension validation for masks — `assert` replaced with `raise RuntimeError` for clearer error messages.
- **Circular Erase Clipping**: Fixed circular erase tool clipping at canvas boundaries.
- **Thermal Constant Deduplication**: Removed shadowed local variables and deduplicated thermal decay constant.
- **`__init__.py` ImportError**: Fixed `ImportError` during test collection caused by missing conditional imports.

### Performance
- **FFmpeg/FFprobe Path Caching**: Cached ffmpeg and ffprobe binary path resolution in the analyzer module — avoids repeated filesystem lookups on every invocation. *(PR #139)*
- **Consolidated Path Resolution**: Unified ffmpeg/ffprobe path caching into `core/bin_paths.py` with `@functools.cache` decorator.

### Changed
- **Focus Ring Accessibility**: Improved focus ring visibility for point selector buttons — clearer keyboard navigation indicators. *(PR #138)*
- **Relative Imports**: Switched `bin_paths` module to relative imports for consistency with the rest of the codebase. Added fallback imports for `get_ffprobe_bin`.
- **Test Suite**: Expanded from 799 to **829 tests**, 0 failures.

---

## [2.9.1] - 2026-03-03

### Added
- **AI Object Removal & Editing (`auto_mask:effect=remove|edit`)**: New FLUX Klein 4B integration for AI-powered per-frame object removal and text-guided video editing. Replaces LaMa for the `remove` effect with higher-quality FLUX Klein inpainting. New `edit` effect enables text-guided changes (e.g. "change hair to red", "replace background with beach"). Uses reference-image conditioning with 4-step inference, temporal smoothing, and fixed seeding for cross-frame consistency. ~8–13 GB VRAM (fp16/bf16 with CPU offload).
- **`edit_prompt` Parameter**: New `edit_prompt` parameter on `auto_mask` skill for describing desired text-guided edits when `effect=edit`.
- **FLUX Klein Model Mirror**: fp16 `.safetensors` weights hosted on `AEmotionStudio/flux-klein`. Mirror-first download with upstream BFL fallback.
- **FLUX Klein Tests**: New `tests/test_flux_klein.py` with 16 tests covering constants, model directory, cleanup, model manager integration, and skill registration.
- **AI Audio Generation (`generate_audio`)**: New skill powered by MMAudio (CVPR 2025) — synthesizes synchronized audio/foley from video content and/or text descriptions. Supports video-to-audio, text-to-audio, and long video handling with automatic chunking and crossfade. 11 natural language aliases (`foley`, `sound_effects`, `mmaudio`, `v2a`, etc.).
- **AI Lip Sync (`lip_sync`)**: New skill powered by MuseTalk V15 — synchronizes lip movements in video with provided audio. Supports both video+audio and image+audio inputs, multi-face detection, and batch inference. Zero new pip dependencies — uses existing diffusers, transformers, and mediapipe packages. 7 aliases (`lipsync`, `dub`, `dubbing`, `sync_lips`, `talking_head`, `lip_dub`, `voice_sync`). Subprocess isolation for CUDA memory safety.
- **MMAudio Subprocess Isolation**: Audio generation runs in a subprocess to prevent CUDA memory leaks — same pattern as SAM3. Falls back to in-process generation with proper VRAM offloading if subprocess fails.
- **Native Safetensors Loading**: MMAudio synthesizer uses `comfy.utils.load_torch_file` for direct `.safetensors` loading — no more `.pth` conversion round-trip. Falls back to `safetensors.torch.load_file` or `torch.load` if ComfyUI API unavailable.
- **Memory-Efficient Model Init**: Uses `accelerate`'s `init_empty_weights()` and `set_module_tensor_to_device()` to load MMAudio, Synchformer, and CLIP models with zero-copy initialization — avoids the 3× memory spike of standard `model.load_state_dict()`.
- **Model Auto-Detection**: Detects MMAudio model variant (small/large, v1/v2) from state dict tensor shapes instead of hardcoding, enabling seamless support for multiple model versions.
- **CLIP & BigVGAN Component Loading**: Loads CLIP vision encoder (DFN5B-ViT-H-14-384) and BigVGAN v2 vocoder as separate components with controlled download paths, instead of relying on MMAudio's internal download.
- **Model Mirror Repository**: All 5 MMAudio model components hosted on `AEmotionStudio/mmaudio-models` as fp16 `.safetensors` (~5.5 GB total, 50% smaller than original fp32). Mirror-first download with upstream HuggingFace fallback.
- **MuseTalk Model Mirror**: MuseTalk UNet weights hosted on `AEmotionStudio/musetalk-models` as `.safetensors` in both fp32 (3.2 GB) and fp16 (1.6 GB). Lip sync auto-downloads the fp16 variant by default — 50% smaller. Falls back to fp32 safetensors, then upstream `.pth`.
- **Mask Points Chaining**: `SaveVideoNode` now has optional `mask_points` input/output for passing segmentation point data through the node chain. `LoadVideoPathNode` accepts upstream `mask_points` to override locally generated points.
- **LoadImagePath Node Styling**: Consistent color styling applied to `LoadImagePath` to match other FFMPEGA nodes.
- **Structured Logging (`core/logging.py`)**: New `JSONFormatter` for machine-readable logs, `get_logger()` convenience function, and `LogTimer` context manager for performance tracking. Enable via `FFMPEGA_LOG_JSON=1` env var. *(PR #136)*
- **CONTRIBUTING.md**: New contributor documentation with architecture overview, development setup, coding standards, and PR guidelines. *(PR #136)*
- **Pre-commit Hooks**: New `.pre-commit-config.yaml` with Ruff lint/format and Pyright checks. New `ruff.toml` (120-char lines, py310 target). *(PR #136)*
- **CI Workflow (`.github/workflows/ci.yml`)**: Pytest + Pyright runs on every PR/push. `publish_action.yml` updated with `needs: test` gate. `.coveragerc` and `pytest-cov` CI integration for code coverage. *(PR #130)*
- **12 Integration Tests (`tests/test_integration.py`)**: Real FFmpeg pipeline tests — single-skill (brightness, resize, volume, remove_audio, speed), multi-skill (resize+brightness, trim+resize, video+audio, full), and edge cases (empty pipeline, overwrite, pixel_format enforcement). Test video generated dynamically via ffmpeg (no binary in repo). *(PR #130)*
- **Node Chaining Tests**: New `tests/test_node_chaining.py` with comprehensive tests for mask_points pass-through, save/load node wiring, and metadata propagation.
- **Model Manager Tests**: New `tests/test_model_manager.py` with tests for mirror download, download guards, and safetensors conversion.
- **Audio Generation Tests**: New `tests/test_generate_audio.py` with 20 tests covering skill registration, handler dispatch, aliases, subprocess wiring, and model manager integration.

### Fixed
- **LaMa Cache Check Mismatch**: Added check for the `torch.hub` cache directory when verifying LaMa model availability, fixing false "not found" when model existed in the hub cache.
- **Mirror Download Test Robustness**: Mocked `require_downloads_allowed` in mirror download tests to prevent spurious failures when download guard settings differ.
- **`no_llm_mode` Default Revert**: Reverted unintentional default change in an unrelated PR to keep focused scope.
- **Audio Extraction Buffer**: Fixed buffer size bug in audio extraction pipeline.
- **Log Propagation Leak**: Prevented FFMPEGA logger messages from propagating to ComfyUI's root logger, avoiding duplicate or noisy console output.
- **Token Usage Display**: Switched token usage summary from logger to `print()` so it always appears in the console regardless of log level configuration.
- **Platform Utility Import Robustness**: `core/platform.py` utilities now import gracefully when ComfyUI modules are unavailable (e.g. standalone testing, MCP server).

### Security
- **CC-BY-NC 4.0 License Warnings**: Prominent license warnings for MMAudio model weights in 5 locations — skill description (visible to LLM agents), handler docstring, handler runtime log, model registry, and README. MMAudio model checkpoints are CC-BY-NC 4.0 (non-commercial); users must accept the license when downloading.

### Changed
- **Modular Node Architecture**: Broke up monolithic `agent_node.py` into 6 focused modules — `input_resolver.py` (input path resolution/validation), `execution_engine.py` (FFmpeg pipeline execution/retry), `output_handler.py` (frame collection/formatting), `batch_processor.py` (batch/queue processing), `nollm_modes.py` (no-LLM mode presets), and `pipeline_assembler.py` (pipeline generation/assembly). `agent_node.py` remains as a thin orchestrator. *(PRs #127, #136)*
- **Platform Abstraction (`core/platform.py`)**: Extracted all ComfyUI boundary interactions (folder paths, model loading, progress callbacks) into a single adapter module. Core logic no longer imports ComfyUI directly. *(PR #128)*
- **Pyright Type Checking**: Added `pyrightconfig.json` (Python 3.10+, basic mode), created type stubs for ComfyUI modules (`folder_paths`, `comfy.*`). Fixed 78 type errors across `core/`, `skills/`, `mcp/` — subprocess stream None-safety, Optional return types, forward references, tuple unpacking, numpy buffer protocol. *(PR #127)*
- **`_RESERVED` Hoisted**: Moved `_RESERVED` from instance-level to module-level constant; lazy-initialized logging to avoid import-time side effects.
- **Removed `_inject_effects_hints`**: Cleaned up dead method from agent_node.
- **Model Registry Updated**: `mmaudio` entry updated with accurate size (~5.5 GB), `license` field, mirror URL, and ⚠️ warning in manual instructions.
- **Safetensors Model Conversion**: Whisper models on HuggingFace mirror converted from `.pt` to `.safetensors` to avoid being flagged. LaMa kept as `.pt` (TorchScript JIT). MuseTalk UNet converted from `.pth` to `.safetensors` (fp32 + fp16). `try_mirror_download` updated to handle per-model conversion strategy.
- **AI-Powered Skills Count**: Updated from 3 to 5 in README (added `generate_audio`, `lip_sync`).
- **Point Selector Accessibility**: Added `role="dialog"`, `aria-modal="true"`, `aria-label` to point selector overlay. Status bar uses `role="status"` and `aria-live="polite"` for screen reader announcements. Decorative emojis hidden with `aria-hidden="true"`. *(PR #124)*
- **Test Suite**: Expanded from 656 to **799 tests** across 40 test files, 0 failures. New integration tests (12), structured logging coverage, and platform abstraction tests.

---

## [2.8.0] - 2026-02-28

### Added
- **FFMPEGA Effects Builder Node**: New companion node for manual effect composition — select up to 3 skills with params, combine with raw FFmpeg filters, and use presets. No LLM required. Purple-themed UI with dynamic widget visibility and auto-fill defaults.
- **Effects Builder Context Menu Presets**: Right-click the Effects Builder for quick access to all 18 built-in presets, plus save/load/delete custom presets. Includes a "Clear All Effects" reset option.
- **Text Node Presets**: Right-click the FFMPEGA Text node for 10 built-in presets (SRT Subtitle Example, Cinematic Subtitles, Bold Watermark, Title Card, Social Caption, Meme Text, Lower Third, Copyright Notice, Credits Roll, Chapter Marker) with example text content. Save/load/delete custom presets. "Clear Text" resets to defaults.
- **No-LLM Text Support**: Connect a Text node to the Agent in no-LLM manual mode (without an Effects Builder) and it auto-generates a text overlay or subtitle pipeline from the Text node's settings.
- **Manual No-LLM Mode**: New `manual` option in `no_llm_mode` dropdown (now the default) — set `llm_model` to `none` and use the Effects Builder to edit videos without any AI. Shows a clear error if no Effects Builder node is connected.
- **SAM3-Only Mode**: New no-LLM mode that uses the prompt as a SAM3 text target for object masking/removal without an LLM.
- **Whisper No-LLM Modes**: `transcribe` and `karaoke_subtitles` options in `no_llm_mode` — run Whisper speech-to-text and burn subtitles directly without an LLM. Also available as Effects Builder presets ("Auto Subtitles", "Karaoke Subtitles").
- **Effects Builder Multi-Input Support**: The Effects Builder pipeline now calls `_inject_extra_inputs()` to populate `pipeline.extra_inputs`, enabling concat, grid, split screen, xfade, overlay, and all other multi-input skills to work correctly with `video_b`, `image_b`, etc.
- **SAM3 Point Prompts**: Support for geometric point prompts passed as SAM3 boxes for precise segmentation guidance. Two-phase prompting: text VG detection + native point refinement.
- **SAM3 Progress Streaming**: Real-time SAM3 subprocess progress display in the console.
- **Save Video Overlay Button**: Accessible overlay button on video previews for quick save actions.
- **Drag-and-Drop Feedback**: Visual feedback during file drag-and-drop uploads with proper state restoration.

### Fixed
- **SAM3 Subprocess Isolation**: SAM3 video masking now runs in a separate subprocess to prevent CUDA memory leaks and improve VRAM management. Fixes persistent OOM errors on long videos.
- **SAM3 OOM Fixes**: Multiple fixes for out-of-memory errors during SAM3 processing — CPU offloading between propagation passes, frame 0 cache retention for point prompts, VG propagation scoping.
- **SAM3 Point Prompt Fixes**: Cap `max_num_objects` to 2 for point prompt mode, validate coordinates with float/int coercion, forward `mask_points` to batch mode metadata, use source image dims for coordinate mapping.
- **SAM3 Bad File Descriptor**: Fixed `Popen` bad file descriptor error in SAM3 subprocess communication.
- **SAM3 `_postprocess_output` KeyError**: Fixed KeyError when `max_num_objects` is active and fewer objects are detected than expected.
- **MCP Path Traversal** *(security)*: Fixed path traversal vulnerabilities in MCP tools — added input and output path validation.
- **Template Placeholder Crash**: Fixed unsubstituted template placeholders (e.g. `{ratio}`) causing ffmpeg crashes when parameters are dropped by validation. Now falls back to skill defaults.
- **Effects Builder Multi-Input**: Fixed concat, grid, split screen, xfade, and all multi-input skills not working in the Effects Builder. The Effects Builder path was missing the `_inject_extra_inputs()` call, so `_extra_input_count` was always 0.
- **Concat/Xfade/Slideshow Resolution**: Fixed output resolution defaulting to 1920×1080 regardless of input. Handlers now use the input video's actual resolution.
- **Dynamic Slot Root Cause**: Fixed `video_b` disappearing on page refresh — `video_path` and `video_folder` static widget inputs were polluting the `video_` dynamic slot group.
- **Effects Builder Stale Params**: Switching effects now clears the params widget, preventing stale params from leaking between effects.
- **Effects Builder Temp Cleanup**: Added cleanup for temp files created by `_inject_extra_inputs()` in the Effects Builder pipeline.
- **Drag-and-Drop State Restoration**: Correctly restores original text and border states after drag-and-drop feedback.
- **Vision Frames Cleanup**: Clear `_vision_frames` on startup and correct SAM3 import check.
- **`text_overlay` Position**: Removed position default from `text_overlay` to preserve preset positioning.
- **Tool Prompt Builder**: Filter `None` from `available_names` in tool prompt builder.
- **SaveVideo Preview Mode**: Fixed `preview_only` mode causing 404 errors — preview segments now correctly copied to ComfyUI's temp directory.
- **Frame Extractor Duration Default**: Changed default `duration` from 10s to 0 (full video), raised max to 3600s.

### Security
- **MCP Path Validation**: Input and output paths in MCP tools are now validated against path traversal attacks.
- **SkillComposer Parameter Hardening**: Secure parameter handling and updated skill schemas to prevent injection.
- **`validate_path` Directory Checks**: Enforced sensitive directory checks in `validate_path`.

### Performance
- **SAM3 VRAM Optimization**: CPU offloading, auto-stride selection, and object limits for SAM3 video masker. Suppressed noisy console output.
- **FFMPEG Pipe Buffer**: Optimized pipe buffer size for video conversion.
- **Ultrafast Temp Videos**: Temp video generation now uses `ultrafast` FFMPEG preset.
- **Frame Tensor Allocation**: Optimized video frame tensor allocation.

### Changed
- **`no_llm_mode` Default → `manual`**: Default changed from `sam3_masking` to `manual`. Users who set `llm_model=none` now get the Effects Builder path by default.
- **Empty Prompt Allowed for Manual Mode**: `manual` mode no longer requires a prompt.
- **SAM3 Last-Frame Anchoring Removed**: Simplified point prompts by removing last-frame point anchoring from SAM masker and its UI.
- **SAM3 `mask_output_type` Default**: Changed default mask output type from `colored_overlay` to `black_white`.
- **UI Focus Tracking**: Refactored focus tracking to use explicit state; enhanced focus visibility for interactive elements.

---

## [2.7.1] - 2026-02-24

### Added
- **Advanced Options Toggle**: New `advanced_options` input (default: Simple) — hides `preview_mode`, `crf`, `encoding_preset`, `video_path`, `subtitle_path`, and `batch_mode` (+ sub-widgets) behind a toggle for a cleaner node layout. Power users can enable Advanced mode to access all settings.
- **SAM3 Checkpoint Warnings**: Added format mismatch detection — logs a warning with reconversion instructions when >50% of checkpoint keys are missing (e.g. HuggingFace Transformers format vs expected original `.pt` key structure).
- **Token Log Rotation**: `usage_log.jsonl` now auto-rotates when exceeding 10 MB, trimming the oldest 50% of entries to prevent unbounded disk growth.

### Fixed
- **Dynamic Input Persistence**: Fixed dynamic input slots (e.g. `video_b` appearing when `video_a` is connected) not restoring on workflow load. Pre-creates saved slots from serialized data in `onConfigure` and uses `setTimeout` instead of `requestAnimationFrame` for reliable link restoration timing.
- **Default Value Mismatches**: Synced `process()` signature defaults with `INPUT_TYPES` for `whisper_device` and `track_tokens`.

### Changed
- **Removed `ptc_mode` Input**: PTC mode hidden from UI (not ready for public use). Defaults to `"off"` internally. Code preserved for future re-enablement.
- **Removed `sam3_device` Input**: SAM3 CPU mode hidden from UI (SAM3 does not support CPU inference). Defaults to `"gpu"` internally.
- **Whisper Default → CPU**: `whisper_device` now defaults to `"cpu"` to avoid VRAM pressure on most setups.
- **Token Tracking Default → On**: `track_tokens` now defaults to `True` so users see token usage by default.
- **Dead Code Cleanup**: Removed ~1100 lines of unreachable inlined `process` method after `return` statement in `agent_node.py`.
- **`ValidationError`**: Path validation functions in `core/sanitize.py` now raise `ValidationError` instead of `ValueError` for more specific error handling.

---

## [2.7.0] - 2026-02-24

### Added
- **SAM3 Auto-Mask & Greenscreen**: New `remove` skill powered by SAM3 (Segment Anything Model 3) for automatic object segmentation. Generates per-frame binary masks from text prompts (e.g. *"remove the person"*), then applies LaMa inpainting or black fill. New `greenscreen` skill uses SAM3 masks to replace backgrounds with solid colors or transparency (WebM output). *(PR #71)*
- **LaMa Inpainting**: New `core/lama_inpainter.py` — per-frame LaMa (Large Mask Inpainting) for AI-powered video object removal. Uses `simple-lama-inpainting` (Apache-2.0). Includes temporal Gaussian smoothing to reduce frame-to-frame flickering, and automatic temp directory cleanup. *(PR #71)*
- **Programmatic Tool Calling (PTC)**: New `execute_code` tool with sandboxed Python executor (`core/ptc_executor.py`). LLMs can write a single Python script that orchestrates multiple tool calls (search → details → build) in one pass, reducing round-trips from ~6 to 1. Three modes: `off` (classic), `auto` (both available), `on` (forced PTC only). *(PR #72)*
- **PTC Sandbox Security**: Static code analysis blocks 25+ escape vectors — dunder introspection (`__class__`, `__globals__`, `__getattribute__`), module access (`os.`, `subprocess.`), traceback frame traversal (`__traceback__`, `tb_frame`, `f_back`), dangerous builtins (`eval`, `exec`, `open`, `chr`), and dynamic attribute access. All builtins except safe ones are removed. *(PR #72)*
- **Tool Use Examples**: `input_examples` field added to all tool definitions, giving LLMs concrete usage patterns. Examples are stripped from API schemas (OpenAI, Anthropic) to avoid 400 errors but preserved for CLI connectors that embed tools as text. *(PR #72)*
- **PTC Test Suite**: New `tests/test_ptc_executor.py` with 34 tests covering sandbox security (15 escape vector tests), safe builtins, tool access, end-to-end orchestration, and vision integration. *(PR #72)*

### Security
- **Path Validation Hardening**: Case-insensitive path validation on all platforms, improved robustness of output path blocking for system directories. *(PR #69)*
- **Input Sanitization**: Expanded input sanitization for edge cases in text parameters and API key handling. *(PR #69)*
- **PTC Sandbox Hardening**: Blocked `__getattribute__`/`__setattr__`/`__delattr__` for dynamic attribute access, `chr()` for string construction bypasses, and traceback frame traversal escapes. Deep-copied tool schemas prevent mutation of global definitions. *(PR #72)*

### Performance
- **CHOICE Validation O(1)**: `SkillParameter` caches a normalized `_choice_map` in `__post_init__` — O(1) dictionary lookup instead of O(N) list iteration. *(PR #70)*
- **FFMPEG Path Escape**: Optimized `ffmpeg_escape_path` performance for common-case clean paths. *(PR #73)*

### Fixed
- **SAM3 Mask Cleanup**: Guarded `rmtree` against `None` temp directory, wrapped FPS parsing in try/except, fixed torch.cuda calls on CPU-only systems, and resolved mask dimension validation issues. *(PR #71)*
- **LaMa Import Path**: Added relative import fallback and corrected `remove_object` function import (was incorrectly `inpaint_video`). *(PR #71)*
- **PTC API Keys**: System prompt and test mocks now use correct return keys (`matches`/`match_count` instead of `skills`/`count`). *(PR #72)*
- **Regex False Positives**: PTC blocked-patterns regex uses word boundaries so strings like `"videos.mp4"` are not flagged by the `os.` pattern. *(PR #72)*
- **Forced PTC Mode**: When `ptc_mode == "on"`, tool_defs now only exposes `execute_code` — model can no longer bypass forced-PTC with classic per-tool calls. *(PR #72)*
- **CLI Tool Instructions**: Tool usage instructions now adapt to available tools — prevents contradictory "ALWAYS call search_skills" when only `execute_code` is exposed. *(PR #72)*
- **Sentinel Overlay Validation**: Added validation for `ParameterType.COLOR` and hidden `text_overlay` parameters.

### Changed
- **Shared Effect Filter Map**: Extracted duplicate effect filter mapping into a shared constant to eliminate duplication between handlers. *(PR #71)*
- **Upload Button UX**: Enhanced upload button accessibility with improved label casing and ARIA attributes. *(PR #74)*
- **Tool Schema Stripping**: `strip_nonstandard_fields()` now uses `copy.deepcopy` for nested parameters, preventing mutation of global `TOOL_DEFINITIONS`. Only applied to non-CLI connectors. *(PR #72)*
- **Test Suite**: Expanded from 516 to **656 passing tests**, 0 failures. New PTC executor tests (34), security hardening tests, and updated mock return shapes to match real API contracts.

---


## [2.6.6] - 2026-02-22

### Changed
- **Metadata Updates**: Updated author to `Æmotion Studio` in `pyproject.toml` and `__init__.py`.
- **Dependencies**: Removed `pydantic` from requirements since it's already provided by ComfyUI core.

---

## [2.6.5] - 2026-02-22

### Added
- **Whisper Auto-Transcription**: New `auto_transcribe` skill — transcribes video audio with OpenAI Whisper and burns SRT subtitles into the output. Supports single and multi-video (concat) workflows with correct cross-clip timing. *(PR #67)*
- **Karaoke Subtitles**: New `karaoke_subtitles` skill — word-by-word progressive-fill karaoke effect using Whisper word-level timestamps and ASS `\kf` tags. Configurable font size, base color, and fill color. *(PR #67)*
- **Whisper Device Control**: New `whisper_device` node setting (`gpu`/`cpu`) — allows running Whisper on CPU to avoid VRAM pressure on low-memory GPUs. *(PR #67)*
- **Whisper Model Selection**: New `whisper_model` node setting (`tiny`, `base`, `small`, `medium`, `large-v3`) — choose the model size for speed vs. accuracy tradeoff. *(PR #67)*
- **Transcription Test Suite**: New `tests/test_transcribe.py` with 18 tests covering SRT generation, ASS karaoke output, handler dispatch, skill registry entries, and model path resolution. *(PR #67)*

### Fixed
- **Publish Action Failure**: Fixed PEP 8 E702 semicolon error in `agent_node.py` that caused the Comfy Registry publish action to fail.
- **Letterbox Content Preservation**: Replaced `crop+pad` with `drawbox` for letterboxing to preserve video content instead of cropping. Correctly handles both letterbox (horizontal bars) and pillarbox (vertical bars) cases. *(PR #67)*
- **Whisper Memory Leak**: `_load_model` now frees the previous model before loading a new one, preventing GPU memory accumulation when switching model sizes. *(PR #67)*
- **Multi-Video Timestamp Desync**: Fixed `transcribe_multi_video` not advancing `time_offset` for skipped (non-existent) videos, which caused subtitle desync. *(PR #67)*
- **Xfade Transition Timing**: `transcribe_multi_video` now accepts `transition_duration` to subtract xfade overlap from timestamp offsets, keeping subtitles in sync with xfade-shortened output. *(PR #67)*
- **ASS Subtitle Escaping**: Transcribed words containing `{`, `}`, or `\` are now stripped before embedding in karaoke ASS tags, preventing rendering failures. *(PR #67)*
- **Primary Input Validation**: `_collect_video_paths` now validates the primary input's file extension, matching the check already applied to extra inputs. *(PR #67)*
- **Invalid Hex Color Rejection**: `color_to_ass_bgr` now validates hex digits before conversion — malformed colors like `#GGGGGG` fall back to the default instead of producing broken ASS strings. *(PR #67)*
- **Aspect Ratio Division by Zero**: Added validation to prevent `ZeroDivisionError` when parsing aspect ratios with zero denominators. *(PR #67)*

### Changed
- **Shared `ffmpeg_escape_path`**: Extracted duplicate `_ffmpeg_escape` functions from `subtitles.py` and `transcribe.py` into a shared `ffmpeg_escape_path()` in `core/sanitize.py`. *(PR #67)*
- **Shared `color_to_ass_bgr`**: Extracted duplicate color-to-ASS conversion from `subtitles.py`, `transcribe.py`, and `whisper_transcriber.py` into a shared `color_to_ass_bgr()` in `core/sanitize.py`. Supports named colors, 6/8-digit hex, and native ASS pass-through. *(PR #67)*
- **Shared `_run_transcription`**: Extracted duplicated transcription dispatch logic from `_f_auto_transcribe` and `_f_karaoke_subtitles` into a shared `_run_transcription()` helper. *(PR #67)*
- **Subtitle Filter Ordering**: Subtitle filters now always render last via a filter reordering pass, ensuring subtitles appear on top of letterbox bars and other effects. *(PR #67)*

---

## [2.6.4] - 2026-02-22

### Security
- **Typewriter Text DoS Prevention**: Enforced string length validation in `SkillRegistry` and added a `max_value=200` limit to the `typewriter_text` skill's text parameter to prevent resource exhaustion. *(PR #66)*

### Performance
- **PNG Compression Optimization**: `MediaConverter.save_frames_as_images` now uses `compress_level=1` (fastest) instead of the default level (6) when saving temporary frames for FFMPEG concatenation or overlays. Yields a ~25% speedup with minimal file size impact. *(PR #64)*

### Changed
- **Aria Live Status Updates**: Added `role="status"` and `aria-live="polite"` regions to UI elements in `ffmpega_ui.js` ensuring screen readers announce status changes during video uploads, processing, and color copying. Dynamically updates `aria-label` to "Copied successfully" on hex code copy. *(PR #65)*

---

## [2.6.3] - 2026-02-21

### Security
- **FFMPEG Stream Specifier Injection Fix**: `sanitize_text_param` in `core/sanitize.py` now escapes square brackets (`[` → `\[`, `]` → `\]`). Unescaped brackets in user-supplied text parameters could be interpreted as FFMPEG stream specifiers (e.g. `[0:v]`), enabling filter graph injection or causing syntax errors. Added `test_escapes_brackets` regression test. *(PR #62)*

### Performance
- **Sanitize "Check First" Optimization**: `sanitize_text_param` and `sanitize_api_key` now guard each `str.replace()` call with an `if char in text` check. Avoids unnecessary string allocations in the common case (clean text). ~2.5x speedup for `sanitize_text_param` on clean input; `sanitize_api_key` skips `redact_secret()` entirely when the key is absent. *(PR #63)*

### Changed
- **Color Picker Accessibility**: `FFMPEGATextInput` hex color label in `ffmpega_ui.js` is now keyboard-accessible — added `tabindex="0"`, `role="button"`, and `aria-label` attributes; Enter/Space trigger copy; focus indicator via `box-shadow`. `aria-label="Select font color"` added to the color input itself. *(PR #61)*

---

## [2.6.2] - 2026-02-20

### Security
- **Block Writes to System Directories**: Updated `validate_output_path` and `validate_output_file_path` in `core/sanitize.py` to block writes to critical system directories (e.g., `/usr`, `/bin`, `/etc`, `C:\Windows`). Prevents path traversal / arbitrary file overwrite targeting sensitive system files. *(PR #59)*

### Changed
- **CHOICE Validation O(1) Lookup**: `SkillParameter` now caches a `_choice_map` of normalized choices (exact, lowercase, underscore-to-hyphen variants) in `__post_init__`. `validate()` uses O(1) dictionary lookup instead of O(N) list iteration — ~15% faster for CHOICE parameters. *(PR #60)*
- **Video Upload Loading Feedback**: Refactored `FFMPEGALoadVideoPath` upload logic in `ffmpega_ui.js` — added `setUploadState` helper to toggle "Uploading…" label, consolidated click and drag-drop into a shared `handleUpload` handler, improved error handling with `try/finally` to ensure UI reset, and hides video preview during upload. *(PR #58)*

---

## [2.6.1] - 2026-02-19

### Added
- **README Hero Image**: Added a showcase screenshot to the README header, displayed below badges and above the tagline.
- **README Examples Section**: 10 before/after video examples showcasing various editing capabilities (bouncing logo, crossfade, color grading, PiP, vintage film, datamosh, cinematic teal & orange, neon glow, colorhold noir, green screen removal). Uses animated `.webp` files in HTML tables.
- **NotebookLM Overview**: Added YouTube video embed section with clickable thumbnail linking to the NotebookLM-generated overview video.
- **Traffic Stats Badges**: Added dynamic Downloads, Visitors, and Clones badges powered by `shields.io/badge/dynamic/json` — data sourced from the `badges` branch via GitHub Actions.
- **Traffic Stats Workflow**: New `.github/workflows/git_clones.yml` — runs daily, fetches clone/view/download stats via GitHub API, and pushes `traffic_stats.json` to the `badges` branch.
- **Comfy Registry Publishing**: New `.github/workflows/publish_action.yml` — auto-publishes to the Comfy Registry when `pyproject.toml` changes on `main`. Added `[tool.comfy]` section to `pyproject.toml` with `PublisherId = "aemotionstudio"`.

---

## [2.6.0] - 2026-02-18

### Added
- **TextInput Node**: New `TextInputNode` for subtitle and text overlay workflows. Auto-detects SRT vs. plain text, supports `watermark` and `subtitle` modes, and generates valid SRT from plain text with duration-aware timing splits.
- **Audio Mixing for PiP**: `picture_in_picture` skill now supports `audio_mix` parameter — blend both audio tracks together using ffmpeg's `amix` filter instead of keeping only the main video's audio.
- **CLI Retry with Backoff**: CLI connectors (Gemini CLI, Claude CLI, Cursor Agent, Qwen CLI) now retry on transient failures with exponential backoff (3 attempts, 1s → 4s delays). Covers timeout, rate-limit, and connection errors.
- **HandlerResult Contract**: New `skills/handler_contract.py` introduces a formal `HandlerResult` dataclass for all handler return types, replacing ad-hoc 3/4/5-tuples. Backward-compatible via `__iter__`, `__getitem__`, `__len__`, and `__add__` methods.
- **Orchestration Unit Tests**: 5 pure static methods extracted from `compose()` now have dedicated unit tests: `_resolve_audio_conflicts`, `_chain_filter_complex`, `_dedup_output_options`, `_resolve_overlay_inputs`, `_fold_audio_into_fc`.
- **Skill Combination Tests**: New `tests/test_skill_combinations.py` with 33 integration and unit tests covering known-fragile multi-skill pipelines (concat+volume, xfade+fade, remove_audio+volume) and orchestration helpers.
- **Handler Unit Tests**: New `tests/test_handlers_unit.py` with 58 isolated handler tests covering all handler families (spatial, temporal, audio, visual, multi-input, encoding, presets, text, subtitles).

### Fixed
- **Text Overlay Injection** *(security)*: Sanitized `enable` parameter in `text_overlay` to prevent filter injection via crafted enable expressions.
- **Path Traversal** *(security)*: Enforced `validate_output_path` check on directory-based output paths in `FFMPEGAgentNode` to prevent path traversal attacks.
- **UUID Entropy** *(security)*: Fixed weak randomness in vision frame directory IDs — now uses `uuid.uuid4()` instead of predictable naming.
- **Odd Dimension Scaling**: `resize` handler now uses `scale=-2` instead of `scale=-1` to ensure even dimensions, preventing `libx264` encoding failures with portrait videos.
- **LUT Path Escaping**: Special characters in LUT file paths are now properly escaped for ffmpeg filter usage.
- **Test Mock Leak**: Fixed `test_skills_registry_perf.py` permanently poisoning `sys.modules["skills.composer"]` with `MagicMock()`, causing `test_pipeline_has_text_inputs_field` to fail when tests ran in sequence.
- **Cursor Agent Test**: Updated `test_build_cmd` assertion to match `--trust` flag added to Cursor Agent connector.
- **Orphaned Seed Parameter**: Removed stale `seed` parameter from `grain_overlay` skill registration.
- **Subtitle Filter Escaping**: Fixed subtitle filter using shell quotes that broke `subprocess` execution.
- **amix Map Flags**: Fixed `amix` audio filter producing incorrect `-map` flags when chaining filter graphs.

### Changed
- **Compose Decomposition**: Extracted 5 orchestration methods from the 600+ line `compose()` method into testable pure static methods, reducing cyclomatic complexity.
- **All 9 Handlers → HandlerResult**: Every handler module (`audio`, `encoding`, `multi_input`, `presets`, `spatial`, `subtitles`, `temporal`, `text_handlers`, `visual`) now returns `HandlerResult` via `make_result()`.
- **Non-Blocking UX**: Replaced all blocking `alert()` / `confirm()` calls in the UI with non-blocking node status feedback.
- **Frame Extraction Optimization**: Optimized `frames_to_tensor` memory allocation and video encoding pipelines.
- **Skill Cache Optimization**: `Skill` objects now cache parameter maps for O(1) `_normalize_params` lookups.
- **Test Suite**: Expanded from 481 to **516 passing tests**, 0 failures.

---

## [2.5.0] - 2026-02-16

### Added
- **PiP Border Support**: `picture_in_picture` skill now accepts `border` (0–20px) and `border_color` (e.g. white, black, 0x333333) parameters. Uses ffmpeg's `pad` filter to frame the overlay with a colored border.
- **Ollama VL Auto-Embedding**: When using an Ollama vision-language model (e.g. `qwen3-vl`), the first 3 video frames are automatically embedded into the initial user message so the model "sees" the video from the start — no need for the agent to call `extract_frames` first.
- **PiP Skill Selection Guidance**: Agentic system prompt now includes explicit guidance for PiP/webcam overlay requests, directing models to use `picture_in_picture`.

### Fixed
- **PiP Alias Resolution**: Models using `pip`, `picture-in-picture`, or `pictureinpicture` as the skill name now correctly resolve to `picture_in_picture` via `SKILL_ALIASES`. Previously these were skipped as "Unknown skill", producing no overlay.
- **PiP/Blend Missing Input**: Added `picture_in_picture`, `pip`, and `blend` to `MULTI_INPUT_SKILLS` gate in `agent_node.py`. Without this, extra video inputs (`video_a`) were never collected, causing ffmpeg `Error binding filtergraph inputs/outputs` because `[1:v]` referenced a non-existent input.
- **Ollama VL Verification 400 Error**: Fixed Ollama VL verification sending OpenAI-format multimodal content blocks. Now correctly sends raw base64 strings in the `images` field per Ollama's API.
- **`extract_frames` Guidance**: Changed from "optional" to "STRONGLY RECOMMENDED" for visual requests in the agentic system prompt, improving VL model behavior.

---

## [2.4.0] - 2026-02-15

### Added
- **Zero-Memory Image Path Inputs**: Image paths from `image_path_a/b/c` inputs are now passed directly as file paths via `pipeline.metadata['_image_paths']` instead of being decoded into tensors. Overlay and watermark handlers reference the correct ffmpeg input index via `_image_input_indices`, keeping multi-GB images out of GPU memory.
- **Overlay Animation Support**: `overlay_image` now accepts `animation` and `animation_speed` parameters. When `animation=bounce` (or `float`, `scroll_*`, `slide_in`) is specified, the handler auto-delegates to `animated_overlay` for proper motion using `eval=frame` expressions. This catches the common LLM pattern of choosing `overlay_image` with animation params instead of `animated_overlay`.
- **Custom X/Y Expression Passthrough**: `overlay_image` detects when the LLM passes custom `x`/`y` ffmpeg expressions (e.g. time-based bounce math) and uses them directly with `eval=frame` instead of the static position map.
- **Output Format Auto-Adjustment**: Output file extensions and quality preset application are now automatically adjusted based on the skills in the pipeline.
- **UX: Paste & Replace Feedback**: Improved paste options and visual feedback in the ComfyUI node interface.

### Fixed
- **Pipeline Chaining (Xfade + Overlay)**: Fixed filter graph chaining bug where xfade's labeled outputs (`[_vout]`, `[_aout]`) were being appended instead of replaced with chaining labels (`[_pipe_0_v]`, `[_pipe_0_a]`), causing triple-label errors. Duplicate `-map` flags from handlers are now stripped when the composer manages chained graphs.
- **Image/Video Input Separation**: Image paths are no longer added to `all_frame_paths` (which feeds xfade/concat segment lists), preventing images from being incorrectly treated as video segments. Images now get their own `-i` entries after video extra inputs.
- **Overlay Input Indexing**: `overlay_image` and `animated_overlay` handlers now use `_image_input_indices` for correct ffmpeg input references instead of hardcoded indices, which broke when xfade/concat clips occupied indices 1–4.
- **FFMPEG Parameter Injection** *(security)*: Extended parameter sanitization to width/height and text/spatial skill parameters to prevent filter injection.
- **Path Validation** *(security)*: Restored path validation dropped during handler extraction refactoring.
- **Colorkey/Chromakey Deduplication**: Removed duplicate handler registrations for chroma key skills.
- **Pydantic Dependency**: Restored pydantic dependency dropped during refactoring.

### Changed
- **Handler Module Extraction**: Skill handlers extracted from monolithic `composer.py` into dedicated modules under `skills/handlers/` (composite, delivery, presets, etc.) for better maintainability.
- **Skill Alias Resolution**: Refactored alias resolution to use a class constant (`SKILL_ALIASES`) instead of inline dictionaries.
- **Performance**: `frames_to_tensor` pre-allocates memory instead of concatenating tensors incrementally.

---

## [2.3.0] - 2026-02-13

### Added
- **Token Usage Tracking**: New opt-in `track_tokens` and `log_usage` toggles on the FFMPEG Agent node. Tracks prompt tokens, completion tokens, LLM calls, tool calls, and elapsed time per run.
  - **Console summary**: When `track_tokens` is enabled, prints a formatted usage box to the console after each run.
  - **Persistent log**: When `log_usage` is enabled, appends a JSON entry to `usage_log.jsonl` for cumulative tracking across sessions.
  - **Real token stats**: Gemini CLI (`-o json`) and Claude CLI (`--output-format json`) now return native token counts instead of estimates.
  - **Fallback estimation**: Other CLI connectors (Cursor, Qwen) use character-based estimation (~4 chars/token), clearly labeled as `(estimated)`.
  - **Core module**: New `core/token_tracker.py` — `TokenTracker` class accumulates per-call usage across the agentic loop.
- **LUT Color Grading System**: 8 bundled `.cube` LUT files for cinematic color grading (`cinematic_teal_orange`, `warm_vintage`, `cool_scifi`, `film_noir`, `golden_hour`, `cross_process`, `bleach_bypass`, `neutral_clean`). Agent discovers via `list_luts` tool and applies with `lut_apply` skill. Drop custom `.cube`/`.3dl` files into `luts/` for automatic discovery.
- **Audio Analysis Tool**: New `analyze_audio` agentic tool — analyzes volume (dB), EBU R128 loudness (LUFS), and silence detection from input video. Guides audio effect decisions without manual inspection.
- **Vision System**: New `mcp/vision.py` — frame extraction and base64 encoding for multimodal LLM analysis. Supports both full image embedding (API/CLI connectors) and raw base64 strings (Ollama).
- **Agentic Tools Documentation**: New README section documenting all autonomous tools the agent uses (analyze_video, extract_frames, analyze_colors, analyze_audio, search_skills, list_luts).
- **Verification Loop Documentation**: New README section explaining the output verification loop (extract → analyze → assess → auto-correct).
- **Custom Skills Documentation**: New README section with inline YAML example for creating custom skills.

### Changed
- **Gemini CLI Connector**: Switched from `-o text` to `-o json` output format — enables structured token usage parsing alongside text content.
- **Claude CLI Connector**: Switched from `--output-format text` to `--output-format json` — enables structured token usage parsing alongside text content.
- **CLI Base Connector**: `generate()` method now populates `prompt_tokens` and `completion_tokens` via character-based estimation when native token counts are unavailable.
- **Pipeline Generator**: Agentic loop now initializes a `TokenTracker`, records usage after each LLM call, and stores the summary as `last_token_usage` on the generator instance.

---

## [2.2.1] - 2026-02-13

### Security
- **CLI Agent Sandbox**: CLI agents (Gemini, Claude, Cursor, Qwen) are now sandboxed to the custom node directory via `cwd=` in `create_subprocess_exec()`. Previously, agents inherited ComfyUI's working directory, potentially exposing the user's home directory (SSH keys, configs, other projects).

### Fixed
- **Vision Frame Accessibility**: Removed `_vision_frames/` from `.gitignore` so CLI agents can read extracted frames. CLI agents (especially Gemini CLI) respect both `.gitignore` and `.git/info/exclude` ignore patterns, which previously blocked frame access. The `cleanup_vision_frames()` function handles deletion after use.

### Added
- **Sandbox Test**: New `test_generate_sandboxes_cwd_to_node_dir` test verifying that `create_subprocess_exec` is called with `cwd=` pointing to the node directory.
- **README: CLI Vision Support**: Added documentation showing which CLI agents support vision (Gemini ✅, Claude ✅, Cursor ✅, Qwen ❌) and guidelines for `_vision_frames/` accessibility.
- **README: Gemini CLI Plans & Limits**: Added detailed free/paid tier comparison table, available models, and rate limits for Gemini CLI users.

---

## [2.2.0] - 2026-02-12

### Added
- **200 Skills**: Expanded from 152 to **200 skills** — 48 new skills across all categories:
  - **Audio** (8): `noise_reduction`, `audio_crossfade`, `audio_delay`, `ducking`, `dereverb`, `split_audio`, `audio_normalize_loudness`
  - **Temporal** (3): `scene_detect`, `silence_remove`, `time_remap`
  - **Visual** (5): `white_balance`, `shadows_highlights`, `split_tone`, `deflicker`, `unsharp_mask`
  - **Spatial** (2): `auto_crop`, `scale_2x`
  - **Encoding** (2): `audio_bitrate`, `frame_rate_interpolation`
  - **Text & Graphics** (9): `animated_text`, `scrolling_text`, `ticker`, `lower_third`, `countdown`, `typewriter_text`, `bounce_text`, `fade_text`, `karaoke_text`
  - **Editing & Composition** (9): `picture_in_picture`, `blend`, `delogo`, `remove_dup_frames`, `mask_blur`, `extract_frames`, `jump_cut`, `beat_sync`, `color_match`
  - **Effects** (4): `datamosh`, `radial_blur`, `grain_overlay`, `freeze_frame`
  - **Delivery** (2): `thumbnail` (handler-based), `extract_frames` (handler-based)
- **New `delivery.py`**: Delivery-focused skills extracted into their own outcome file.
- **New Test Files**: `test_connectors_tools.py`, `test_pipeline_generator.py`, `test_yaml_loader.py`.

### Fixed
- **10 Broken Templates**: Fixed template errors discovered during FFmpeg execution testing:
  - `silence_remove` — changed category from TEMPORAL to AUDIO for correct `-af` routing
  - `time_remap` — removed nested quotes from `setpts` expression
  - `shadows_highlights` — removed dual template+pipeline conflict
  - `mask_blur` — fixed invalid filter syntax
  - `jump_cut` — fixed `select` expression for FFmpeg compatibility
  - `beat_sync` — fixed `select` expression rounding
  - `audio_crossfade` / `ducking` — converted from multi-input to single-input templates
  - `thumbnail` / `extract_frames` — converted to handler-based for proper `-frames:v 1` and `-an` output options
  - `datamosh` — converted to handler-based, added `-flags2 +export_mvs` input flag for `codecview`

### Changed
- **Documentation**: Updated `SKILLS_REFERENCE.md` and `SKILL_TEST_PROMPTS.md` with entries for all 48 new skills.

---

## [2.1.0] - 2026-02-12

### Added
- **Input Awareness**: The LLM agent now receives a connected inputs summary showing all available video tensors, audio tracks, and images with details (frame count, duration, sample rate, FPS). Enables smarter multi-input decisions.
- **Audio Source Selection**: New `audio_source` parameter in the LLM response JSON — the agent can select a specific audio track (`audio_a`, `audio_b`, etc.) or blend all tracks (`mix`). Users can control this via prompt: *"use audio_b"*, *"mix both audio tracks"*.
- **Audio Mix Mode**: When `audio_source` is `mix` and multiple audio inputs are connected, all tracks are blended together using ffmpeg's `amix` filter. Default behavior for split screen and other multi-input skills with multiple audio sources.
- **Xfade Audio Crossfade**: Xfade transitions now include `acrossfade` for seamless audio blending between segments.

### Fixed
- **Audio Mux Replacement**: `mux_audio` now uses explicit `-map 0:v -map 1:a` flags, ensuring the selected audio track replaces any existing audio instead of adding a duplicate stream.
- **Split Screen Audio**: Fixed `_has_embedded_audio` flag being set for all multi-input skills. Now only set for concat/xfade where the filter chain reads audio directly. Split screen, grid, overlay, and similar skills now correctly receive post-render audio mux.
- **Xfade Transition Offset**: Fixed xfade not applying transitions because `offset` was hardcoded to 0 instead of being calculated from input durations.
- **Concat Audio Sync**: Improved concat audio handling — each audio track is pre-muxed into its paired video segment so the concat filter reads synchronized audio from each input.

### Changed
- **Prompt Templates**: Both single-shot and agentic system prompts now include a `## Connected Inputs` section with guidance on `audio_source` usage.
- **Skill Count**: Updated to **152 skills** across all categories.

---

## [2.0.0] - 2026-02-11

### ⚠️ Breaking Changes
- **Input Renames**: `images` → `images_a`, `audio_input` → `audio_a`. Existing workflows referencing these inputs will need reconnecting.
- **Removed Inputs**: `image_b` and `extra_images` removed — replaced by dynamic auto-expanding slots.

### Added
- **Dynamic Input Slots**: Image, video, and audio inputs now auto-expand — connect `image_a` and `image_b` appears, connect that and `image_c` appears, etc. Same for `images_a/b/c...` (video inputs) and `audio_a/b/c...`. Powered by JS `onConnectionsChange` hook.
- **Concat Skill**: Concatenate multiple video/image segments sequentially with `concat` filter. Aliases: `concatenate`, `join`.
- **Xfade Transitions**: Smooth transitions between segments with 18 effects — `fade`, `fadeblack`, `dissolve`, `wipeleft`, `wiperight`, `pixelize`, `radial`, `circlecrop`, and more. Aliases: `transition`.
- **Split Screen**: Side-by-side (`hstack`) or top-bottom (`vstack`) layout with `split_screen`. Aliases: `splitscreen`, `side_by_side`.
- **Animated Overlay**: Moving overlay image with 8 motion presets — `scroll_right`, `scroll_left`, `float`, `bounce`, `slide_in`, and more. Uses `eval=frame` expressions.
- **Text Overlay**: Draw text with `drawtext` filter and 5 style presets — `title` (centered), `subtitle`, `lower_third`, `caption`, `top`. Supports timed display, background boxes, and custom fonts.
- **Watermark Skill**: Quick watermark overlay with defaults for corner placement, low opacity, and small scale. Alias for `overlay_image`.
- **Chroma Key Skill**: Green/blue screen removal via ffmpeg `colorkey` filter with configurable similarity, blend, and background replacement. Aliases: `chroma_key`, `green_screen`.

### Changed
- **Multi-Input Collection**: Extra images/audio are now collected from `**kwargs` in alphabetical order. Video-length tensors (>10 frames) are saved as temp video instead of individual PNGs for better performance.
- **Skill Count**: **146 skills** across all categories.

---

## [1.9.0] - 2026-02-11

### Added
- **Claude Code CLI Connector**: New `claude-cli` model option — uses the locally installed Claude Code CLI (`claude -p`) for inference without an API key. Auto-detected on PATH.
- **Cursor Agent CLI Connector**: New `cursor-agent` model option — uses Cursor's `agent` binary in non-interactive mode (`agent -p`). Auto-detected on PATH.
- **Qwen Code CLI Connector**: New `qwen-cli` model option — uses the Qwen Code CLI (`qwen -p`) with free OAuth auth (2,000 requests/day). Auto-detected on PATH.
- **Expanded Context Menu Presets**: Right-click presets expanded from 4 categories / 12 items to **9 categories / 50+ items** with emoji icons — Cinematic, Vintage & Retro, Color & Look, Effects & Overlays, Transitions, Motion & Animation, Format & Social, Time & Speed, and Audio.
- **Save Output Toggle**: New `save_output` boolean input (default: off) — when disabled, output is written to a temp directory instead of ComfyUI's output folder.
- **Workflow PNG Embedding**: When `save_output` is enabled, a first-frame PNG with embedded ComfyUI workflow metadata is saved alongside the video, enabling drag-to-reload.
- **Dynamic Widget Visibility**: `custom_model`, `api_key`, and `output_path` fields now show/hide based on the selected model and save toggle.

### Changed
- **CLI Model Detection**: All CLI-based models (gemini-cli, claude-cli, cursor-agent, qwen-cli) are auto-detected at startup and only appear in the dropdown if the binary is found on PATH.
- **API Key Visibility**: CLI-based models correctly hide the `api_key` field since they use their own authentication.

---

## [1.8.0] - 2026-02-10

### Added
- **Grid Video Integration**: `grid` skill now includes the main video as the first cell (`include_video=true` by default). Creates side-by-side comparisons with video + extra images.
- **Slideshow Video Integration**: `slideshow` skill supports `include_video` param to play the main video as the first segment before image slides.
- **Multi-Overlay Support**: `overlay_image` skill now chains multiple overlays — connect `image_a` + `image_b` and each gets placed at a different corner automatically.
- **Standalone Slideshow/Grid Mode**: Slideshow and grid work without a main video — connect only `extra_images` / `image_a` / `image_b` with no video input.
- **LLM Skill Alias Resolution**: Common LLM shorthand names auto-resolve (`overlay` → `overlay_image`, `grayscale` → `monochrome`, `stabilize` → `deshake`, etc.).
- **Slideshow & Grid Prompt Examples**: Added few-shot examples and selection rules to the system prompt so LLMs pick `slideshow`/`grid` instead of `ken_burns` or other effects.

### Fixed
- **Grid xstack Resolution Mismatch**: All grid cells are now scaled to uniform cell dimensions (640×480 default) with aspect ratio preservation, fixing "Invalid argument" errors when video and images had different resolutions.
- **Grid xstack Layout Expressions**: xstack layout now uses pre-computed literal pixel values instead of arithmetic expressions, which ffmpeg doesn't support.
- **Auto-Include Video**: When a real video is connected, `include_video=true` is auto-injected into slideshow/grid steps regardless of LLM output.
- **ParameterType.BOOLEAN → BOOL**: Fixed incorrect enum value that silently prevented `grid`, `slideshow`, and `overlay_image` from registering in the skill registry.

---

## [1.7.1] - 2026-02-09

### Security
- **API Key Sanitization**: API keys are automatically stripped from all output paths:
  - `redact_secret()` and `sanitize_api_key()` utilities in `core/sanitize.py`
  - `LLMConfig.__repr__` redacts the `api_key` field
  - httpx error messages sanitized before propagation (strips headers containing keys)
  - Exceptions in `agent_node.py` scrubbed of API keys before reaching ComfyUI UI
  - Workflow metadata (PROMPT and EXTRA_PNGINFO) stripped of `api_key` before downstream Save Image/Video nodes embed it into output files

### Added
- **Sanitization Tests**: 9 new tests for `redact_secret()` and `sanitize_api_key()` (28 total in `test_sanitize.py`)

---

## [1.7.0] - 2026-02-09

### Added
- **Multi-Input Skills**: New `grid` (xstack layout), `slideshow` (concat with fade transitions), and `overlay_image` (picture-in-picture) skills — the first skills that use multiple input images.
- **Audio Waveform**: New `waveform` skill visualizes audio as an overlay using FFMPEG's `showwaves` filter with configurable mode, height, color, position, and opacity.
- **Dry-Run Validation**: FFMPEG commands are validated with `-f null -` before execution to catch errors early without wasting render time.
- **Error Feedback Loop**: When FFMPEG execution fails, the error stderr is fed back to the LLM for automatic command correction (max 2 attempts).
- **Frame Extraction**: New `save_frames_as_images()` in `media_converter.py` exports IMAGE tensor frames to individual temp PNGs for multi-input skills.
- **Pipeline Multi-Input**: Added `extra_inputs` field to `Pipeline` dataclass; `compose()` now registers extra inputs as additional `-i` flags and passes `_extra_input_count` to skill handlers.
- **Filter Complex Support**: Full `filter_complex` plumbing through `compose()`, `_skill_to_filters()`, and `_builtin_skill_filters()` — handlers return 4-tuples `(vf, af, opts, fc)`, backward-compatible with existing 3-tuple handlers.

### Changed
- **Agent Node**: Auto-detects multi-input skills in pipeline and saves frames as individual images; cleans up temp frame directories after execution.
- **Pipeline Composer**: Injects `_extra_input_count` into step params for multi-input skill handlers; registers extra inputs with `CommandBuilder`.

---

## [1.6.1] - 2026-02-09

### Fixed
- **Audio Pipeline**: Fixed audio mux re-adding audio after `remove_audio` skill; fixed audio muxing overwriting processed audio when `audio_input` is connected; fixed audio template skills being misrouted to video filters.
- **Audio Mux**: Handle audio mux gracefully when input video has no audio stream.
- **Pulse Effect**: Rewrite `pulse` zoompan filter to avoid parsing issues (`iw*2xih*2` → `iw*2:ih*2`).
- **LLM JSON Parsing**: Auto-retry JSON parsing failures with a correction prompt; agentic self-correction loop for non-JSON responses; prevent unknown skill crashes during retry.

### Added
- **Test Infrastructure**: Root `conftest.py` for standalone pytest, import-safe `__init__.py` with try/except guard, `dev` extras in `pyproject.toml` (pytest, pytest-asyncio).
- **Skill Test Prompts**: Added `SKILL_TEST_PROMPTS.md` with copy-friendly code blocks for manual testing.

### Changed
- **Pipeline Composer**: Refactored `skills/composer.py` for improved audio template handling and skill routing.
- **Agent Node**: Streamlined `nodes/agent_node.py` with cleaner model selection and processing flow.

---

## [1.6.0] - 2026-02-08

### Added
- **Transition Effects**: New `fade_to_black`, `fade_to_white`, and `flash` skills for smooth intro/outro transitions and camera flash effects.
- **Motion Effects**: New `spin` (animated rotation), `shake` (camera shake), `pulse` (breathing zoom), `bounce` (vertical bounce), and `drift` (cinematic pan) skills.
- **Reveal Effects**: New `iris_reveal` (circle expanding from center), `wipe` (directional wipe), and `slide_in` (edge entrance) skills.
- **LLMS.md**: AI-readable project summary following the `llms.txt` convention for AI coding agents.
- **Agent Skills**: Added `.agent/skills/adding-skills.md` for coding agents (Claude Code, Codex, Cursor) with step-by-step guide to adding new skills.

### Changed
- **Enhanced Fade**: The `fade` skill now supports `type=both` for simultaneous fade-in at start + fade-out at end.
- **Smarter AI Agent**: Expanded agentic system prompt from ~300 to ~800 words with:
  - 3 complete few-shot examples showing tool-call flows
  - Skill categories quick reference
  - FFMPEG domain knowledge (filter chaining rules, parameter ranges)
  - Explicit DO NOT rules to prevent common mistakes

---

## [1.5.0] - 2026-02-08

### Added
- **Image Input**: Optional `images` input on FFMPEG Agent — connect frames from Load Video Upload or any image-producing node to use as the video source instead of a file path.
- **Audio Input**: Optional `audio_input` on FFMPEG Agent — connect audio from an upstream node to mux it into the output video and pass it through on the `audio` output pin.
- **Audio Output**: New `audio` output pin on FFMPEG Agent — extracts audio from the processed video (or passes through `audio_input` when connected).
- **Tooltips**: Added descriptive tooltips to every input and output across all 6 nodes (FFMPEG Agent, Batch Processor, Batch Status, Video Preview, Video Info, Frame Extract).
- **Node Descriptions**: Added `DESCRIPTION` class attribute to all nodes for at-a-glance info in the ComfyUI node browser.

---

## [1.4.0] - 2026-02-08

### Added
- **Gemini API Support**: Added Google Gemini models (`gemini-2.0-flash`, `gemini-2.0-flash-lite`, `gemini-1.5-flash`) as LLM options.

### Fixed
- **README Badges**: Corrected license badge (GPL-3.0) and dependency count badge.

### Changed
- **Trimmed Dependencies**: Reduced `requirements.txt` from 13 to 4 packages by removing unused dependencies.

---

## [1.3.0] - 2026-02-08

### Added
- **Skills Reference**: Added comprehensive `SKILLS_REFERENCE.md` with all parameters and example prompts for every skill.
- **README Overhaul**: Reformatted README to match AEmotionStudio style with badges, tables, and collapsible sections.

---

## [1.2.0] - 2026-02-07

### Added
- **33 New Skills**: Added visual, audio, creative, and special effects skills — bringing the total to 100+.
- **Sensible Defaults**: All skill parameters now have sensible defaults so the LLM can omit optional params.
- **Fuzzy Matching**: Skill names are matched fuzzily (e.g. `"color_balance"` → `colorbalance`), improving LLM reliability.

### Fixed
- **Posterize Skill**: Replaced invalid `posterize` filter with working `lutrgb` color quantization.
- **Exposure Skill**: Replaced invalid `exposure` filter with working `curves` alternative.
- **Param Validation**: Downgraded out-of-range parameter errors to warnings — values are now auto-clamped instead of rejected.
- **Type Coercion**: LLM numeric types (float→int) are auto-coerced before validation.
- **Empty Responses**: Better error messages for empty or invalid LLM responses.

---

## [1.1.0] - 2026-02-07

### Changed
- **UI Refactor**: Moved UI code to `js/` directory and improved node widget implementations.

---

## [1.0.0] - 2026-02-07

### Added
- **Initial Release**: ComfyUI-FFMPEGA v1.0 — AI-powered video editing with natural language prompts.
- **FFMPEG Agent Node**: Core node that translates natural language into FFMPEG pipelines.
- **Video Preview Node**: Generate quick low-res previews and thumbnails.
- **Video Info Node**: Analyze and output video metadata.
- **Frame Extract Node**: Extract frames from video at configurable FPS.
- **Batch Processor Node**: Process multiple videos with the same instruction.
- **Batch Status Node**: Monitor batch processing progress.
- **Skill System**: Modular skill architecture with categories for visual, temporal, spatial, audio, encoding, cinematic, vintage, social, and creative effects.
- **Multi-LLM Support**: Ollama (local), OpenAI, and Anthropic connectors.
- **Pipeline Composer**: Automatic FFMPEG command composition from skill chains.
