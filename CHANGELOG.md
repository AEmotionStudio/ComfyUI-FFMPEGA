# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
