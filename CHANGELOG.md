# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
