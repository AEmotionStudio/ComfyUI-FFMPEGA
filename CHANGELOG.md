# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
