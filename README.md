<div align="center">

# ComfyUI-FFMPEGA

**An AI-powered FFMPEG agent node for ComfyUI — edit videos with natural language.**

[![ComfyUI](https://img.shields.io/badge/ComfyUI-Extension-green?style=for-the-badge)](https://github.com/comfyanonymous/ComfyUI)
[![Version](https://img.shields.io/badge/Version-2.5.0-orange?style=for-the-badge)](https://github.com/AEmotionStudio/ComfyUI-FFMPEGA/releases)
[![License](https://img.shields.io/badge/License-GPLv3-red?style=for-the-badge)](LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-1-brightgreen?style=for-the-badge&color=blue)](requirements.txt)

[![Last Commit](https://img.shields.io/github/last-commit/AEmotionStudio/ComfyUI-FFMPEGA?style=for-the-badge&label=Last%20Update&color=orange)](https://github.com/AEmotionStudio/ComfyUI-FFMPEGA/commits)
[![Activity](https://img.shields.io/github/commit-activity/m/AEmotionStudio/ComfyUI-FFMPEGA?style=for-the-badge&label=Activity&color=yellow)](https://github.com/AEmotionStudio/ComfyUI-FFMPEGA/commits)

*Describe what you want in plain English — the AI translates your words into precise FFMPEG commands.*

[Features](#-features) • [Installation](#-installation) • [Quick Start](#-quick-start) • [Prompt Guide](#-prompt-guide) • [Skills](#-skill-system) • [LLM Setup](#-llm-configuration) • [Troubleshooting](#-troubleshooting) • [Contributing](#-contributing) • [Changelog](CHANGELOG.md)

</div>

---

## 🚀 What's New in v2.5.0 (February 16, 2026)

**PiP Overlay Fixes, VL Model Vision & Border Support**

*   **🖼️ PiP Border Support**: `picture_in_picture` now accepts `border` and `border_color` parameters — frame your PiP overlay with a clean border.
*   **👁️ Ollama VL Auto-Embedding**: Vision-language models (e.g. `qwen3-vl`) automatically receive 3 video frames in the initial message — the model "sees" the video from the start.
*   **🔗 PiP Alias Fix**: Models using `pip`, `picture-in-picture`, or `pictureinpicture` now correctly resolve to `picture_in_picture`. Previously these were silently skipped.
*   **🎬 Multi-Input Gate Fix**: `picture_in_picture`, `pip`, and `blend` added to `MULTI_INPUT_SKILLS` — extra video inputs now correctly appear in the ffmpeg command.
*   **🔧 Ollama VL Verification**: Fixed 400 error when verifying output with Ollama VL models — now uses native Ollama image format.
*   **📝 Improved Prompts**: `extract_frames` strongly recommended for visual requests; PiP guidance added to system prompt.

<details>
<summary><b>Previous: v2.4.0 — Pipeline Chaining, Animated Overlays & Zero-Memory Image Paths</b></summary>

*   **🖼️ Zero-Memory Image Paths**: Image inputs passed as file paths instead of decoded tensors.
*   **🎯 Overlay Animation**: `overlay_image` supports `animation=bounce` and more motion presets.
*   **🔗 Pipeline Chaining Fixes**: Fixed filter graph chaining for multi-skill pipelines.
*   **🏗️ Handler Module Extraction**: Skill handlers split into `skills/handlers/` modules.
*   **🔒 Security Hardening**: Extended FFMPEG parameter sanitization.
*   **⚡ Performance**: `frames_to_tensor` pre-allocates memory.

</details>

<details>
<summary><b>Previous: v2.3.0 — Token Tracking, LUT Color Grading & Vision</b></summary>

*   **📊 Token Usage Tracking**: Opt-in `track_tokens` and `log_usage` toggles — monitor prompt/completion tokens, LLM calls, tool calls, and elapsed time.
*   **🎨 LUT Color Grading**: 8 bundled cinematic `.cube` LUT files. Drop custom LUTs into `luts/` for automatic discovery.
*   **🖼️ Vision System**: Multimodal frame analysis — the agent extracts frames and "sees" the video.
*   **🔊 Audio Analysis**: Volume (dB), EBU R128 loudness (LUFS), and silence detection.
*   **🤖 Real Token Stats**: Gemini CLI and Claude CLI return native token counts via JSON output.

</details>

<details>
<summary><b>Previous: v2.2.1 — Security Sandbox & CLI Vision</b></summary>

*   **🔒 CLI Agent Sandbox**: All CLI agents sandboxed to the custom node directory.
*   **👁️ Vision Frame Access**: CLI agents read extracted video frames. Tested: Gemini ✅, Claude ✅, Cursor ✅, Qwen ❌.
*   **📊 Gemini CLI Plans & Limits**: Free/paid tier comparison and rate limits.

</details>

<details>
<summary><b>Previous: v2.2.0 — 200 Skills & Dynamic Inputs</b></summary>

*   **🎯 200 Skills**: Expanded to **200 skills** across all categories.
*   **🔗 Dynamic Auto-Expanding Inputs**: Connect `image_a` → `image_b` appears, and so on.
*   **🎥 Concat & Transitions**: 18 smooth transition types with `xfade`.
*   **📺 Split Screen / 🎨 Animated Overlay / 📝 Text & Graphics / 🔊 Audio / ✂️ Editing / 🎆 Effects**

</details>

> 📄 **See [CHANGELOG.md](CHANGELOG.md) for the complete version history.**

---

## ✨ Features

<table>
<tr>
<td width="50%">

### 🗣️ Natural Language Editing
Describe edits in plain text: *"Make it cinematic with a fade in"*, *"Speed up 2x"*, *"VHS look with grain"*. The AI agent interprets your prompt and builds the FFMPEG pipeline automatically.

</td>
<td width="50%">

### 🤖 Multi-LLM Support
Works with **Ollama** (local, free), **OpenAI**, **Anthropic**, **Google Gemini**, and **CLI tools** (Gemini CLI, Claude Code, Cursor Agent, Qwen Code). Use any local model — Llama 3.1, Qwen3, Mistral, and more. CLI tools are auto-detected on PATH.

</td>
</tr>
<tr>
<td width="50%">

### 🎨 200 Skills
200 video editing skills across visual effects, audio processing, spatial transforms, temporal edits, encoding, cinematic presets, vintage looks, social media, creative effects, text animations, editing & composition, audio visualization, multi-input operations (grids, slideshows, overlays), transitions (xfade), concat, split screen, animated overlays, and text overlays.

</td>
<td width="50%">

### ⚡ Batch & Preview
Process multiple videos with the same instruction. Generate quick low-res previews before committing to full renders. Quality presets from draft to lossless.

</td>
</tr>
</table>

---

## 📦 Installation

### Requirements

- **ComfyUI** (latest)
- **Python 3.10+**
- **FFMPEG** installed and in PATH
- **Ollama** (optional, for local LLM inference)

### Option 1: ComfyUI Manager (Recommended)
1. Open **ComfyUI Manager**
2. Search for **`ComfyUI-FFMPEGA`**
3. Click **Install**

### Option 2: Manual Install
```bash
cd /path/to/ComfyUI/custom_nodes
git clone https://github.com/AEmotionStudio/ComfyUI-FFMPEGA.git
cd ComfyUI-FFMPEGA
uv pip install -r requirements.txt
```

Restart ComfyUI after installation.

---

## 🚀 Quick Start

1. Add an **FFMPEG Agent** node to your workflow
2. Connect a video path or use the input field
3. Enter a natural language prompt
4. Select your LLM model
5. Run the workflow

> **💡 Tip:** Right-click the FFMPEG Agent node to open the **FFMPEGA Presets** context menu — 200+ categorized effects you can apply with a single click, no prompt typing needed. Great for quick edits or discovering what's available.

### Example Prompts

| Prompt | What It Does |
| :--- | :--- |
| `"Make it cinematic with a vignette"` | Adds letterbox, color grade, and edge darkening |
| `"Speed up 2x, keep the audio pitch"` | Doubles speed with pitch-corrected audio |
| `"Make it look like old VHS footage"` | Adds noise, color shift, scan lines |
| `"Trim first 5 seconds, resize to 720p"` | Cuts intro and scales down |
| `"Underwater look with echo on audio"` | Blue tint, blur, and audio echo |
| `"Pixelate it like an 8-bit game"` | Mosaic/pixel art effect |
| `"Add 'Subscribe!' text at the bottom"` | Text overlay with positioning |
| `"Cyberpunk style with neon glow"` | High-contrast neon aesthetic |
| `"Normalize audio, compress for web"` | Loudness normalization + web optimization |
| `"Spin the video clockwise"` | Continuous animated rotation |
| `"Add camera shake"` | Random shake/earthquake effect |
| `"Fade in from black and out at the end"` | Smooth intro/outro transitions |
| `"Wipe reveal from the left"` | Directional wipe reveal animation |
| `"Make it pulse like a heartbeat"` | Rhythmic zoom breathing effect |
| `"Show audio waveform at the bottom"` | Audio visualization overlay |
| `"Arrange these images in a grid"` | Multi-image grid collage |
| `"Create a slideshow with fades"` | Image slideshow with transitions |
| `"Overlay the logo in the corner"` | Picture-in-picture / watermark |
| `"Create a side-by-side comparison"` | Video next to image in 2-column grid |
| `"Create a slideshow starting with the video"` | Video first, then image slides |
| `"Overlay images in the corners"` | Multiple images auto-placed in corners |
| `"Split screen, use audio from audio_b"` | Side-by-side video with specific audio track |
| `"Split screen, mix both audio tracks"` | Side-by-side with both audio tracks blended |

---

## 💬 Prompt Guide

The AI agent interprets your natural language and maps it to skills with specific parameters. Here's how to get the best results.

### Specifying Exact Values

You can request specific parameter values and the agent will use them directly:

| Prompt | What the Agent Does |
| :--- | :--- |
| `"Set brightness to 0.3"` | `brightness:value=0.3` |
| `"Blur with strength 20"` | `blur:radius=20` |
| `"Speed up to 3x"` | `speed:factor=3.0` |
| `"Crop to 1280x720"` | `crop:width=1280,height=720` |
| `"Deband with threshold 0.3 and range 32"` | `deband:threshold=0.3,range=32` |
| `"CRF 18, slow preset"` | `quality:crf=18,preset=slow` |
| `"Fade in for 3 seconds"` | `fade:type=in,duration=3` |

### What Works Well ✅

- **Explicit numbers**: *"brightness 0.2"*, *"speed 1.5x"*, *"CRF 20"* — the agent maps these directly
- **Named presets**: *"VHS look"*, *"cinematic style"*, *"noir"* — triggers multi-step preset pipelines
- **Chaining operations**: *"Trim first 5 seconds, resize to 720p, add vignette"* — executes in order
- **Descriptive goals**: *"Make it look warmer"*, *"Remove the green screen"* — the agent picks the right skills
- **Technical terms**: *"denoise"*, *"deband"*, *"normalize audio"* — maps to exact FFmpeg filters

### What Might Not Work as Expected ⚠️

- **Vague intensity words**: *"Make it very blurry"* or *"a little brighter"* — the agent has to guess what number "very" or "a little" means. **Tip**: use a specific value instead: *"blur with radius 15"*
- **Out-of-range values**: Parameters are auto-clamped to their valid range. If you ask for *"brightness 5.0"* it caps at the max (1.0)
- **Complex compositing**: Multi-layer effects with precise timing may need to be broken into separate passes
- **Format-dependent features**: Some effects (like transparency) require specific output formats. H.264/MP4 doesn't support alpha channels

## 🎛️ Nodes

<details>
<summary><b>FFMPEG Agent</b> — The main node, translates natural language into FFMPEG commands.</summary>

<details>
<summary>Required Inputs</summary>

| Input | Type | Description |
| :--- | :--- | :--- |
| `video_path` | STRING | Absolute path to source video. Used as ffmpeg input unless `images_a` is connected. |
| `prompt` | STRING | Natural language editing instruction (e.g. *"Add cinematic letterbox"*, *"Speed up 2x"*). |
| `llm_model` | DROPDOWN | AI model selection — local Ollama models appear first, then CLI tools (gemini-cli, claude-cli, cursor-agent, qwen-cli), then cloud APIs. |
| `quality_preset` | DROPDOWN | Output quality: `draft`, `standard`, `high`, `lossless`. |
| `seed` | INT | Change to force re-execution with the same prompt. Supports randomize control. |

</details>

<details>
<summary>Optional Inputs</summary>

| Input | Type | Description |
| :--- | :--- | :--- |
| `images_a` | IMAGE | Video frames from upstream (e.g. Load Video). Auto-expands: `images_b`, `images_c`... |
| `image_a` | IMAGE | Extra image input for multi-input skills (grid, slideshow, overlay). Auto-expands: `image_b`, `image_c`... |
| `audio_a` | AUDIO | Audio input for muxing or multi-audio workflows. Auto-expands: `audio_b`, `audio_c`... |
| `preview_mode` | BOOLEAN | Quick low-res preview (480p, 10s) instead of full render. |
| `save_output` | BOOLEAN | Save video + workflow PNG to output folder. Off when a downstream Save node handles output. |
| `output_path` | STRING | Custom output file/folder path. Empty = ComfyUI default. |
| `ollama_url` | STRING | Ollama server URL (default: `http://localhost:11434`). |
| `api_key` | STRING | API key for cloud models (GPT, Claude, Gemini). Auto-redacted from outputs. |
| `custom_model` | STRING | Exact model name when `llm_model` is set to `custom` (e.g. `gpt-5.2`, `claude-sonnet-4-6`). |
| `crf` | INT | Override CRF (0 = lossless, 23 = default, 51 = worst). Set to -1 to use `quality_preset`. |
| `encoding_preset` | DROPDOWN | Override x264/x265 speed preset (`ultrafast` → `veryslow`). `auto` follows `quality_preset`. |

</details>

<details>
<summary>Batch Processing Inputs</summary>

| Input | Type | Description |
| :--- | :--- | :--- |
| `batch_mode` | BOOLEAN | Process all matching videos in `video_folder` with the same prompt. Single LLM call. |
| `video_folder` | STRING | Folder containing videos to batch process. |
| `file_pattern` | DROPDOWN | File pattern to match (`*.mp4`, `*.mov`, `*.*`, etc.). |
| `max_concurrent` | INT | Maximum simultaneous encodes in batch mode (1–16, default 4). |

</details>

| Output | Description |
| :--- | :--- |
| `images` | All frames from the output video as a batched image tensor |
| `audio` | Audio extracted from output video (or passed through from `audio_a`) |
| `video_path` | Absolute path to the rendered output video file |
| `command_log` | The ffmpeg command(s) that were executed |
| `analysis` | LLM interpretation, pipeline steps, and warnings |

</details>

<details>
<summary><b>Frame Extract (FFMPEGA)</b> — Extract individual frames from a video as image tensors.</summary>

| Input | Type | Description |
| :--- | :--- | :--- |
| `video_path` | STRING | Absolute path to the video to extract frames from. |
| `fps` | FLOAT | Extraction rate (0.1–60.0). `1.0` = one frame per second. |
| `start_time` | FLOAT | *(optional)* Start time in seconds (default: 0). |
| `duration` | FLOAT | *(optional)* Duration to extract from, in seconds (default: 10). |
| `max_frames` | INT | *(optional)* Max frames to return (default: 100, max: 1000). |

| Output | Description |
| :--- | :--- |
| `frames` | Extracted video frames as a batched image tensor |

> **Tip:** Connect `frames` output to the FFMPEG Agent's `images_a` input to build pipelines that analyze frames before editing.

</details>

<details>
<summary><b>Load Image Path (FFMPEGA)</b> — Zero-memory image loader, outputs a file path instead of a tensor.</summary>

Outputs the image file path as a STRING instead of decoding into a ~6 MB IMAGE tensor. Connect to FFMPEGA Agent's `image_path_a` / `image_path_b` / … slots so ffmpeg reads the file directly.

| Input | Type | Description |
| :--- | :--- | :--- |
| `image` | FILE PICKER | Select an image from ComfyUI's input directory or upload a new one. |

| Output | Description |
| :--- | :--- |
| `image_path` | Absolute file path to the selected image |

</details>

<details>
<summary><b>Load Video Path (FFMPEGA)</b> — Zero-memory video input with inline preview and metadata.</summary>

Validates the video file exists and outputs the path as a STRING — loads ZERO frames into memory. Features inline video preview, metadata display (fps, duration, resolution), and VHS-style trim parameters.

| Input | Type | Description |
| :--- | :--- | :--- |
| `video` | FILE PICKER | Select or upload a video file. |
| `force_rate` | FLOAT | Override FPS (0 = use source). |
| `skip_first_frames` | INT | Frames to skip from start. |
| `frame_load_cap` | INT | Max frames to use (0 = all). |
| `select_every_nth` | INT | Select every Nth frame (1 = every frame). |

| Output | Description |
| :--- | :--- |
| `video_path` | Validated video file path |
| `frame_count` | Total usable frames after trim |
| `fps` | Effective FPS |
| `duration` | Effective duration in seconds |

</details>

<details>
<summary><b>Save Video (FFMPEGA)</b> — Zero-memory video output with inline preview.</summary>

Takes a video path (from FFMPEGA Agent or Load Video Path), copies the file to ComfyUI's output directory, and shows a preview. No re-encoding — just a file copy.

| Input | Type | Description |
| :--- | :--- | :--- |
| `video_path` | STRING | Path to video file (typically from FFMPEGA Agent's output). |
| `filename_prefix` | STRING | Prefix for saved filename. Supports `%date:yyyy-MM-dd%`. |
| `overwrite` | BOOLEAN | *(optional)* Overwrite existing file vs auto-increment counter. |

</details>

<details>
<summary><b>Video to Path (FFMPEGA)</b> — Convert IMAGE tensor to a temp video file path.</summary>

Bridge node between Load Video nodes (which output IMAGE tensors) and FFMPEGA Agent's `video_a`/`video_b`/`video_c` slots. Encodes frames to a temp video file, then releases the tensor so ComfyUI can free the memory.

| Input | Type | Description |
| :--- | :--- | :--- |
| `images` | IMAGE | Video frames from a Load Video node. |
| `fps` | INT | *(optional)* FPS for the output video (default: 24). |

| Output | Description |
| :--- | :--- |
| `video_path` | File path to the temp video |

</details>

---

## 🎯 Skill System

FFMPEGA includes a comprehensive skill system with **200 operations** organized into categories. The AI agent selects the right skills based on your prompt.

> 📄 **See [SKILLS_REFERENCE.md](SKILLS_REFERENCE.md) for the complete skill reference with all parameters and example prompts.**
>
> 🧪 **See [SKILL_TEST_PROMPTS.md](SKILL_TEST_PROMPTS.md) for ready-to-use copy-and-paste test prompts for every skill.**

<details>
<summary><b>🎨 Visual Effects (25 skills)</b></summary>

| Skill | Description |
| :--- | :--- |
| `brightness` | Adjust brightness (-1.0 to 1.0) |
| `contrast` | Adjust contrast (0.0 to 3.0) |
| `saturation` | Adjust color saturation (0.0 to 3.0) |
| `hue` | Shift color hue (-180 to 180) |
| `sharpen` | Increase sharpness |
| `blur` | Apply blur effect |
| `denoise` | Reduce noise/grain (light, medium, strong) |
| `vignette` | Darken edges for cinematic focus |
| `fade` | Fade in/out to black |
| `colorbalance` | Adjust shadows/midtones/highlights |
| `noise` | Add film grain |
| `curves` | Apply color curve presets (vintage, cross_process, etc.) |
| `text_overlay` | Add text with position, color, size, font |
| `invert` | Invert colors (photo negative) |
| `edge_detect` | Edge detection / sketch look |
| `pixelate` | Mosaic / 8-bit pixel effect |
| `gamma` | Gamma correction |
| `exposure` | Exposure adjustment |
| `chromakey` | Green screen removal |
| `deband` | Remove color banding artifacts |
| `white_balance` | Adjust color temperature (2000K–12000K) |
| `shadows_highlights` | Separately adjust shadows and highlights |
| `split_tone` | Warm highlights, cool shadows |
| `deflicker` | Remove fluorescent/timelapse flicker |
| `unsharp_mask` | Fine-grained luma/chroma sharpening |

</details>

<details>
<summary><b>⏱️ Temporal (9 skills)</b></summary>

| Skill | Description |
| :--- | :--- |
| `trim` | Cut a segment by time |
| `speed` | Change playback speed (0.1x to 10x) |
| `reverse` | Play backwards |
| `loop` | Repeat video |
| `fps` | Change frame rate (1 to 120) |
| `scene_detect` | Auto-detect scene changes |
| `silence_remove` | Remove silent segments |
| `time_remap` | Gradual speed ramp |
| `freeze_frame` | Freeze a frame at a timestamp |

</details>

<details>
<summary><b>📐 Spatial (8 skills)</b></summary>

| Skill | Description |
| :--- | :--- |
| `resize` | Scale to specific dimensions |
| `crop` | Crop video region |
| `rotate` | Rotate by degrees |
| `flip` | Mirror horizontal/vertical |
| `pad` | Add padding / letterbox |
| `aspect` | Change aspect ratio (16:9, 4:3, 1:1, 9:16, 21:9) |
| `auto_crop` | Detect and remove black borders |
| `scale_2x` | Quick upscale with algo choice (2x, 4x) |

</details>

<details>
<summary><b>🔊 Audio (26 skills)</b></summary>

| Skill | Description |
| :--- | :--- |
| `volume` | Adjust audio level |
| `normalize` | Normalize loudness |
| `fade_audio` | Audio fade in/out |
| `remove_audio` | Strip all audio |
| `extract_audio` | Extract audio only |
| `bass` / `treble` | Boost/cut frequencies |
| `pitch` | Shift pitch by semitones |
| `echo` | Add echo / reverb |
| `equalizer` | Adjust specific frequency band |
| `stereo_swap` | Swap L/R channels |
| `mono` | Convert to mono |
| `audio_speed` | Change audio speed only |
| `chorus` | Chorus thickening effect |
| `flanger` | Sweeping jet flanger |
| `lowpass` / `highpass` | Frequency filters |
| `audio_reverse` | Reverse audio track |
| `compress_audio` | Dynamic range compression |
| `noise_reduction` | Remove background noise |
| `audio_crossfade` | Smooth audio crossfade |
| `audio_delay` | Add delay/offset to audio |
| `ducking` | Audio dynamic compression |
| `dereverb` | Remove room echo/reverb |
| `split_audio` | Extract left/right channel |
| `audio_normalize_loudness` | EBU R128 loudness normalization |
| `replace_audio` | Replace original audio track |
| `audio_bitrate` | Set audio encoding bitrate |

</details>

<details>
<summary><b>📦 Encoding (13 skills)</b></summary>

| Skill | Description |
| :--- | :--- |
| `compress` | Reduce file size (light, medium, heavy) |
| `convert` | Change codec (h264, h265, vp9, av1) |
| `quality` | Set CRF and encoding preset |
| `bitrate` | Set video/audio bitrate |
| `web_optimize` | Fast-start for web streaming |
| `container` | Change format (mp4, mkv, avi, mov, webm) |
| `pixel_format` | Set pixel format (yuv420p, yuv444p, etc.) |
| `hwaccel` | Hardware acceleration (cuda, vaapi, qsv) |
| `audio_codec` | Set audio codec (aac, mp3, opus, flac) |
| `frame_rate_interpolation` | Motion-interpolated FPS conversion |
| `frame_interpolation` | Smooth slow motion via motion interpolation |
| `two_pass` | Two-pass encoding for better quality |
| `hls_package` | HLS adaptive streaming packaging |

</details>

<details>
<summary><b>🎬 Cinematic Presets (14 skills)</b></summary>

| Skill | Description |
| :--- | :--- |
| `cinematic` | Hollywood film look — teal-orange grading |
| `blockbuster` | Michael Bay style — high contrast, dramatic |
| `documentary` | Clean, natural documentary look |
| `indie_film` | Indie art-house — faded, low contrast |
| `commercial` | Bright, clean corporate video |
| `dream_sequence` | Dreamy, soft, ethereal atmosphere |
| `action` | Fast-paced action movie grading |
| `romantic` | Soft, warm romantic mood |
| `sci_fi` | Cool blue sci-fi atmosphere |
| `dark_moody` | Dark, atmospheric, moody feel |
| `color_grade` | Cinematic color grading (teal_orange, warm, cool) |
| `color_temperature` | Adjust color temperature (warm/cool) |
| `letterbox` | Cinematic widescreen letterbox bars |
| `film_grain` | Film grain texture (light, medium, heavy) |

</details>

<details>
<summary><b>📼 Vintage & Retro (9 skills)</b></summary>

| Skill | Description |
| :--- | :--- |
| `vintage` | Classic old film look (50s–90s) |
| `vhs` | VHS tape aesthetic |
| `sepia` | Classic sepia/brown tone |
| `super8` | Super 8mm film look |
| `polaroid` | Polaroid instant photo |
| `faded` | Washed-out, faded look |
| `old_tv` | CRT television aesthetic |
| `damaged_film` | Aged/weathered film |
| `noir` | Film noir — B&W, high contrast |

</details>

<details>
<summary><b>📱 Social Media (9 skills)</b></summary>

| Skill | Description |
| :--- | :--- |
| `social_vertical` | TikTok / Reels / Shorts (9:16) |
| `social_square` | Instagram feed (1:1) |
| `youtube` | YouTube optimized |
| `twitter` | Twitter/X optimized |
| `gif` | Convert to animated GIF |
| `thumbnail` | Extract thumbnail frame |
| `caption_space` | Add space for captions |
| `watermark` | Overlay logo/watermark |
| `intro_outro` | Add intro/outro segments |

</details>

<details>
<summary><b>✨ Creative Effects (14 skills)</b></summary>

| Skill | Description |
| :--- | :--- |
| `neon` | Neon glow — vibrant edges and colors |
| `horror` | Dark, desaturated, grainy horror atmosphere |
| `underwater` | Blue tint, blur, darker underwater look |
| `sunset` | Golden hour warm glow |
| `cyberpunk` | Neon tones, high contrast cyberpunk |
| `comic_book` | Bold colors, comic/pop art style |
| `miniature` | Tilt-shift toy model effect |
| `surveillance` | Security camera / CCTV look |
| `music_video` | Punchy colors, contrast, vignette |
| `anime` | Anime / cel-shaded cartoon |
| `lofi` | Lo-fi chill aesthetic |
| `thermal` | Thermal / heat vision camera |
| `posterize` | Reduce color palette / screen-print |
| `emboss` | Emboss / relief surface effect |

</details>

<details>
<summary><b>🧪 Special Effects (36 skills)</b></summary>

| Skill | Description |
| :--- | :--- |
| `meme` | Deep-fried meme aesthetic |
| `glitch` | Digital glitch / databend |
| `mirror` | Mirror / kaleidoscope effect |
| `slow_zoom` | Slow push-in zoom |
| `black_and_white` | B&W with style options |
| `day_for_night` | Simulate nighttime from daytime |
| `dreamy` | Soft, ethereal dream look |
| `hdr_look` | Simulated HDR dynamic range |
| `datamosh` | Glitch art / motion vector visualization |
| `radial_blur` | Radial / zoom blur effect |
| `grain_overlay` | Cinematic film grain with intensity control |
| `burn_subtitles` | Hardcode subtitles |
| `selective_color` | Isolate specific colors |
| `perspective` | Perspective transform |
| `lut_apply` | Apply LUT color grading |
| `lens_correction` | Fix lens distortion |
| `fill_borders` | Fill black borders |
| `deshake` | Quick stabilization |
| `deinterlace` | Remove interlacing |
| `halftone` | Newspaper dot pattern |
| `false_color` | Pseudocolor heat map |
| `frame_blend` | Temporal frame blending |
| `tilt_shift` | Tilt-shift miniature effect |
| `color_channel_swap` | Color channel remapping |
| `ghost_trail` | Temporal motion trails |
| `glow` | Bloom / soft glow effect |
| `sketch` | Pencil drawing / ink line art |
| `chromatic_aberration` | RGB channel offset / color fringing |
| `boomerang` | Looping boomerang effect |
| `ken_burns` | Slow zoom pan for photos |
| `slowmo` | Smooth slow motion |
| `stabilize` | Remove camera shake |
| `timelapse` | Dramatic speed-up for timelapse |
| `zoom` | Zoom in/out effect |
| `scroll` | Scroll video vertically/horizontally |
| `monochrome` | Monochrome with optional tint |

</details>

<details>
<summary><b>🎬 Transitions (3 skills)</b></summary>

| Skill | Description |
| :--- | :--- |
| `fade_to_black` | Fade in from + fade out to black |
| `fade_to_white` | Fade in from + fade out to white |
| `flash` | Camera flash at a specific timestamp |

</details>

<details>
<summary><b>🌀 Motion (5 skills)</b></summary>

| Skill | Description |
| :--- | :--- |
| `spin` | Continuous animated rotation |
| `shake` | Camera shake / earthquake (light, medium, heavy) |
| `pulse` | Rhythmic breathing zoom effect |
| `bounce` | Vertical bouncing animation |
| `drift` | Slow cinematic pan (left, right, up, down) |

</details>

<details>
<summary><b>🔮 Reveal Effects (3 skills)</b></summary>

| Skill | Description |
| :--- | :--- |
| `iris_reveal` | Circle expanding from center |
| `wipe` | Directional wipe from black |
| `slide_in` | Slide video in from edge |

</details>

<details>
<summary><b>🎵 Audio Visualization (1 skill)</b></summary>

| Skill | Description |
| :--- | :--- |
| `waveform` | Audio waveform overlay (line, point, cline modes) |

</details>

<details>
<summary><b>🔗 Multi-Input & Composition (10 skills)</b></summary>

| Skill | Description |
| :--- | :--- |
| `grid` | Arrange video + images in a grid layout (xstack). Auto-includes video as first cell. |
| `slideshow` | Create slideshow from images with fade transitions. Optionally starts with the main video. |
| `overlay_image` | Picture-in-picture / watermark overlay. Supports multiple overlays auto-placed in corners. Accepts `animation=bounce` for motion. |
| `concat` | Concatenate video segments sequentially. Connect multiple videos/images to join them. |
| `xfade` | Smooth transitions between segments — 18 types: fade, dissolve, wipe, pixelize, radial, etc. |
| `split_screen` | Side-by-side (horizontal) or top-bottom (vertical) multi-video layout. |
| `animated_overlay` | Moving image overlay with motion presets: scroll, float, bounce, slide. |

</details>

<details>
<summary><b>✏️ Text & Graphics (9 skills)</b></summary>

| Skill | Description |
| :--- | :--- |
| `animated_text` | Animated text overlay |
| `scrolling_text` | Scrolling credits-style text |
| `ticker` | News-style scrolling ticker bar |
| `lower_third` | Professional broadcast lower third |
| `countdown` | Countdown timer overlay |
| `typewriter_text` | Typewriter reveal effect |
| `bounce_text` | Bouncing animated text |
| `fade_text` | Text that fades in and out |
| `karaoke_text` | Karaoke-style fill text |

</details>

<details>
<summary><b>✂️ Editing & Delivery (13 skills)</b></summary>

| Skill | Description |
| :--- | :--- |
| `picture_in_picture` | PiP overlay window with optional border |
| `blend` | Blend two video inputs |
| `delogo` | Remove logo from a region |
| `remove_dup_frames` | Strip duplicate/stuttered frames |
| `mask_blur` | Blur a rectangular region for privacy |
| `extract_frames` | Export frames as image sequence |
| `jump_cut` | Auto-cut to high-energy moments |
| `beat_sync` | Sync cuts to a beat interval |
| `color_match` | Auto histogram equalization |
| `extract_subtitles` | Extract subtitle track |
| `preview_strip` | Filmstrip preview of key frames |
| `sprite_sheet` | Contact sheet of frames |

</details>

### 🧠 Agentic Tools

Beyond the 200+ editing skills, the agent has autonomous tools it calls on its own to analyze media and make better decisions. You don't invoke these directly — the agent uses them automatically based on your prompt.

<details>
<summary><b>🔍 Analysis & Discovery</b></summary>

| Tool | What It Does |
| :--- | :--- |
| `analyze_video` | Probes resolution, duration, codec, FPS, bitrate — the agent calls this to understand your source |
| `extract_frames` | Extracts PNG frames for vision models to "see" the video content |
| `analyze_colors` | Numeric color metrics (luminance, saturation, color balance) via ffprobe signalstats — guides color grading decisions without vision |
| `analyze_audio` | Numeric audio metrics (volume dB, EBU R128 loudness LUFS, silence detection) — guides audio effect decisions |
| `search_skills` | Searches skills by keyword — the agent **always** calls this to find the right skills |
| `list_luts` | Lists available LUT files for color grading — called before `lut_apply` to discover available looks |

</details>

<details>
<summary><b>🎨 LUT Color Grading System</b></summary>

8 bundled LUT files for cinematic color grading. The agent discovers these via `list_luts` and applies them with the `lut_apply` skill.

| LUT | Style |
| :--- | :--- |
| `cinematic_teal_orange` | Hollywood teal-orange grade |
| `warm_vintage` | Warm retro film look |
| `cool_scifi` | Cool blue sci-fi tone |
| `film_noir` | Classic noir — desaturated, crushed |
| `golden_hour` | Warm golden sunlight |
| `cross_process` | Cross-processed film chemistry |
| `bleach_bypass` | Bleach bypass — low saturation, high contrast |
| `neutral_clean` | Subtle clarity enhancement |

**Adding your own LUTs:** Drop `.cube` or `.3dl` files into the `luts/` folder. The agent will discover them via `list_luts` automatically. Short names auto-resolve to full paths (e.g., `cinematic_teal_orange` → `luts/cinematic_teal_orange.cube`).

</details>

<details>
<summary><b>✅ Output Verification Loop</b></summary>

When `verify_output` is enabled (default: **On**), the agent inspects its own output after execution:

1. Extracts frames from the output video
2. Runs color and/or audio analysis on the result
3. Sends analysis to the LLM with the original prompt for quality assessment
4. If the LLM detects issues, it auto-corrects the pipeline and re-executes once

This closes the feedback loop — the agent can catch and fix mistakes like wrong color grades, failed effects, or audio issues without re-queuing.

</details>

<details>
<summary><b>🧩 Custom Skills</b></summary>

Create your own skills via YAML — no Python required. Drop a `.yaml` file in `custom_skills/`, restart ComfyUI, and the agent can use it immediately.

```yaml
# custom_skills/dreamy_blur.yaml
name: dreamy_blur
description: "Soft dreamy blur with glow"
category: visual
tags: [dream, blur, soft, glow]

parameters:
  radius:
    type: int
    default: 5
    min: 1
    max: 30

ffmpeg_template: "gblur=sigma={radius},eq=brightness=0.06"
```

**Skill packs** — installable collections of related skills, optionally with Python handlers for complex logic:
```bash
cd custom_skills/
git clone https://github.com/someone/ffmpega-retro-pack retro-pack
```

Two example skills ship in `custom_skills/examples/` — `warm_glow.yaml` (template) and `film_burn.yaml` (pipeline composite).

> 📄 **See [CUSTOM_SKILLS.md](CUSTOM_SKILLS.md) for the full schema reference, skill pack structure, Python handlers, and advanced examples.**

</details>

---

## 🤖 LLM Configuration

> **Tested with:** FFMPEGA has been primarily tested using **Gemini CLI** and **Qwen3 8B** (via Ollama). Results may vary with other models.
>
> **Author's pick:** The CLI connectors (especially **Gemini CLI**) have been the most reliable option in my experience — they handle tool-calling, structured output, and long context exceptionally well. Highly recommended if you have access.

### Choosing a Model

FFMPEGA works best with models that have **strong JSON output and instruction-following abilities**. The agent sends a structured prompt and expects a valid JSON pipeline back — models with tool-calling or function-calling capabilities tend to perform best.

**Things to keep in mind:**
- **Some models work better than others** — larger models and those trained for structured output (JSON/tool-calling) produce more reliable results
- **Some models may need more retries** — if the agent fails to parse the response, try running the same prompt again. Smaller models occasionally return malformed JSON on the first try
- **Find what works best for you** — experiment with different models to find the right balance of speed, quality, and reliability for your hardware

### Ollama (Local — Free)
The default option. Runs locally, no API key needed.

```bash
# Install and start Ollama
ollama serve

# Pull a model
ollama pull qwen3:8b
```

**Recommended local models (≤30B, consumer GPU friendly):**
| Model | Size | Speed | Notes |
| :--- | :--- | :--- | :--- |
| `qwen3:8b` | 8B | ⚡ Fast | **Tested** — excellent structured output, native tool-calling |
| `qwen3-vl` | 8B | ⚡ Fast | **Tested** — multimodal vision-language model, sees video frames |
| `qwen3:14b` | 14B | ⚡ Fast | Sweet spot of speed and quality, tools + thinking tags |
| `qwen3:30b` | 30B | 🔄 Medium | Best Qwen under 30B, needs 16GB+ VRAM |
| `qwen2.5:14b` | 14B | ⚡ Fast | Top IFEval scores, strong instruction following |
| `deepseek-r1:14b` | 14B | ⚡ Fast | Reasoning model — verifies its own tool calls, very reliable |
| `mistral-nemo` | 12B | ⚡ Fast | NVIDIA + Mistral collab, 128k context, great reasoning |
| `mistral-small3.2` | 24B | 🔄 Medium | Native function calling, 128k context |
| `phi4` | 14B | ⚡ Fast | Microsoft reasoning SLM, rivals larger models in logic |
| `gemma3:12b` | 12B | ⚡ Fast | High reasoning scores, 128k context |
| `llama3.3:8b` | 8B | ⚡ Fast | Reliable tool-calling, large ecosystem |

> **Tip:** On the [Ollama library](https://ollama.com/library), look for models with a **tools** tag — this indicates native tool/function-calling support, which produces the best results with FFMPEGA.

### OpenAI
```
llm_model: gpt-5.2
api_key: your-openai-key
```

### Gemini (Google API)
```
llm_model: gemini-3-flash
api_key: your-google-ai-key
```

### Gemini CLI (Free with any Google Account)

Use the [Gemini CLI](https://github.com/google-gemini/gemini-cli) to run Gemini models without an API key. Works with any Google account.

**Install:**
```bash
pnpm add -g @google/gemini-cli
```

**Authenticate** (first time only):
```bash
gemini
```
This opens a browser to sign in with your Google account.

**Use in FFMPEGA:**
```
llm_model: gemini-cli
```

No API key is needed — authentication is handled by the CLI. Select `gemini-cli` from the model dropdown in the node.

> **Note:** The Gemini CLI runs as a subprocess and is sandboxed to the custom node directory for security. On Windows, `gemini.cmd` is also detected automatically.

#### Plans & Usage Limits

| Plan | Rate Limit | Daily Limit | Models | Cost |
| :--- | :--- | :--- | :--- | :--- |
| **Free** (Google login) | 60 req/min | 1,000 req/day | Gemini model family (Pro + Flash) | Free |
| **Free** (API key only) | 10 req/min | 250 req/day | Flash only | Free |
| **Code Assist Standard** | 120 req/min | 1,500 req/day | Gemini model family | Paid |
| **Code Assist Enterprise** | 120 req/min | 2,000 req/day | Gemini model family | Paid |
| **Google AI Pro** | Higher | Higher | Full Gemini family | $19.99/mo |

> **Tip:** Sign in with a Google account (free) for the best experience — 1,000 requests/day with access to Pro and Flash models. An unpaid API key limits you to 250/day on Flash only.

#### Available Models

The Gemini CLI auto-selects the best model, but the following are available:

| Model | Best For |
| :--- | :--- |
| Gemini 2.5 Pro | Complex reasoning, creative tasks |
| Gemini 2.5 Flash | Fast responses, high throughput |
| Gemini 2.5 Flash-Lite | Maximum speed, lowest cost |
| Gemini 3 Pro | Most capable, advanced reasoning |
| Gemini 3 Flash | Fast + capable, good balance |

> Free tier may auto-switch to Flash models when Pro quota is exhausted.

### Anthropic
```
llm_model: claude-sonnet-4-6
api_key: your-anthropic-key
```

### Claude Code CLI (Free with Anthropic Account)

Use the [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) as a local LLM backend. Uses its own authentication — no API key needed in FFMPEGA.

**Install:**
```bash
pnpm add -g @anthropic-ai/claude-code
```

**Authenticate** (first time only):
```bash
claude
```
This opens a browser to sign in with your Anthropic account.

**Use in FFMPEGA:**
```
llm_model: claude-cli
```

Auto-detected on PATH. Select `claude-cli` from the model dropdown.

### Cursor Agent CLI

Use [Cursor's CLI](https://docs.cursor.com) in agent mode as an LLM backend.

**Install:**
Open Cursor IDE → Command Palette → "Install 'cursor' command"

**Start the agent:**
```bash
agent
```

**Use in FFMPEGA:**
```
llm_model: cursor-agent
```

Auto-detected on PATH. Select `cursor-agent` from the model dropdown.

### Qwen Code CLI (Free — 2,000 requests/day)

Use [Qwen Code](https://qwenlm.github.io/qwen-code-docs/) as a free LLM backend. Powered by Qwen3-Coder with 2,000 free requests/day via OAuth — no credit card required.

**Install:**
```bash
pnpm add -g @qwen-code/qwen-code@latest
```

**Authenticate** (first time only):
```bash
qwen
```
Select "Qwen OAuth (Free)" and follow the browser prompts to sign in.

**Use in FFMPEGA:**
```
llm_model: qwen-cli
```

Auto-detected on PATH. Select `qwen-cli` from the model dropdown.

### 👁️ CLI Agent Vision Support

When [Frame Extraction](SKILLS_REFERENCE.md) is used, FFMPEGA saves extracted frames to a `_vision_frames/` directory and passes the frame paths to the CLI agent. Agents with vision support can **see and analyze the actual frame images** to make better editing decisions.

| CLI Agent | Vision Support | Notes |
| :--- | :--- | :--- |
| **Gemini CLI** | ✅ Yes | `read_file` converts images to base64 for multimodal analysis |
| **Claude Code CLI** | ✅ Yes | Native image reading and description |
| **Cursor Agent CLI** | ✅ Yes | Native image reading and description |
| **Qwen Code CLI** | ❌ Not yet | [Known issue](https://github.com/QwenLM/qwen-code/issues) — `read_file` returns raw binary instead of interpreting images. Vision is listed as a planned feature. |

> **Note:** Agents without vision support still receive the frame file paths and can use video metadata (duration, resolution, FPS) from `analyze_video` to make editing decisions. When Qwen fixes their vision support upstream, it will work automatically since the frame paths are already passed correctly.

> ⚠️ **Important:** The `_vision_frames/` directory must **not** be listed in `.gitignore` or `.git/info/exclude` — CLI agents respect these ignore patterns and will be unable to read the frames. FFMPEGA's `cleanup_vision_frames()` automatically deletes the directory after each pipeline run.

### Custom Model

Select **`custom`** from the model dropdown and type any model name in the `custom_model` field. The provider is auto-detected from the name:

| Prefix | Provider |
| :--- | :--- |
| `gpt-*` | OpenAI |
| `claude-*` | Anthropic |
| `gemini-*` | Google |
| Anything else | Ollama (local) |

This lets you use any new model immediately without waiting for a code update.

### 🔒 API Key Security

Your API keys are **automatically scrubbed** and never stored in output files:

- **Error messages** — keys are redacted before being shown in the UI (e.g. `****abcd`)
- **Workflow metadata** — ComfyUI embeds workflow data in output images/videos; FFMPEGA strips the `api_key` field from this metadata before saving
- **HTTP errors** — keys are removed from network error messages that might include auth headers
- **Debug logs** — `LLMConfig` redacts keys in all string representations

No configuration needed — this protection is always active when an API key is provided.

> ⚠️ **Safety precaution:** As with any software, always inspect your output files before sharing them publicly — in the unlikely event of a bug or edge case that bypasses the automatic scrubbing.

### 📊 Token Usage Tracking

Monitor your LLM token consumption with opt-in usage tracking. Enable via two toggles on the node:

| Toggle | Default | What It Does |
| :--- | :--- | :--- |
| `track_tokens` | Off | Prints a formatted usage summary to the console after each run |
| `log_usage` | Off | Appends a JSON entry to `usage_log.jsonl` for cumulative tracking |

**Token data sources by connector:**

| Connector | Source | Estimated? |
| :--- | :--- | :--- |
| Ollama | Native API (`prompt_eval_count` / `eval_count`) | No |
| OpenAI / Gemini API | Native API (`usage` field) | No |
| Anthropic API | Native API (`usage.input_tokens`) | No |
| **Gemini CLI** | JSON output via `-o json` | No |
| **Claude CLI** | JSON output via `--output-format json` | No |
| Other CLIs | Character-based estimation (~4 chars/token) | Yes |

When enabled, the **analysis output** includes a usage breakdown:

```
Token Usage:
  Prompt tokens:     4,200
  Completion tokens: 1,800
  Total tokens:      6,000
  LLM calls:         5
  Tool calls:        3
  Elapsed:           12.4s
```

The `usage_log.jsonl` file stores one JSON object per run for historical analysis. It is gitignored by default.

---

## 🐛 Troubleshooting

<details>
<summary><b>FFMPEG Not Found</b></summary>

Ensure FFMPEG is installed and in your system PATH:
```bash
ffmpeg -version
```
Install via package manager if missing:
```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# Arch/CachyOS
sudo pacman -S ffmpeg

# macOS
brew install ffmpeg
```

</details>

<details>
<summary><b>Ollama Connection Failed</b></summary>

Make sure Ollama is running:
```bash
ollama serve
```
If using a custom URL, set it in the node's `ollama_url` field.

</details>

<details>
<summary><b>Model Not Found</b></summary>

Pull the required model first:
```bash
ollama pull llama3.1:8b
```

</details>

<details>
<summary><b>LLM Returns Empty Response</b></summary>

This usually means:
- The model is still loading (first request after start)
- The prompt is too long for the model's context window
- Try running the same prompt again
- Try a different model

</details>

<details>
<summary><b>Parameter Validation Errors</b></summary>

FFMPEGA auto-coerces types (float→int) and clamps out-of-range values. If you still see errors, try simplifying your prompt or using a more capable model.

</details>

<details>
<summary><b>Cancelling a Running Request</b></summary>

If the LLM is taking too long or you want to abort mid-request, **close the terminal/console** running the LLM process instead of using ComfyUI's interrupt button. The interrupt button waits for the current LLM response to complete, which can take a while — closing the console kills it immediately.

</details>

---

## 🤝 Contributing

Contributions are welcome! Whether it's bug reports, new skills, or improvements — your help is appreciated.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📝 License

This project is licensed under the [GPL-3.0 License](LICENSE) — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Developed by [Æmotion Studio](https://aemotionstudio.org/)**

[![YouTube](https://img.shields.io/badge/YouTube-FF0000?style=for-the-badge&logo=youtube&logoColor=white)](https://www.youtube.com/@aemotionstudio/videos)
[![Discord](https://img.shields.io/badge/Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/UzC9353mfp)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-F16061?style=for-the-badge&logo=ko-fi&logoColor=white)](https://ko-fi.com/aemotionstudio)

</div>
