<div align="center">

# ComfyUI-FFMPEGA

**An AI-powered FFMPEG agent node for ComfyUI — edit videos with natural language.**

[![ComfyUI](https://img.shields.io/badge/ComfyUI-Extension-green?style=for-the-badge)](https://github.com/comfyanonymous/ComfyUI)
[![Version](https://img.shields.io/badge/Version-1.6.1-orange?style=for-the-badge)](https://github.com/AEmotionStudio/ComfyUI-FFMPEGA/releases)
[![License](https://img.shields.io/badge/License-GPLv3-red?style=for-the-badge)](LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-4-brightgreen?style=for-the-badge&color=blue)](requirements.txt)

[![Last Commit](https://img.shields.io/github/last-commit/AEmotionStudio/ComfyUI-FFMPEGA?style=for-the-badge&label=Last%20Update&color=orange)](https://github.com/AEmotionStudio/ComfyUI-FFMPEGA/commits)
[![Activity](https://img.shields.io/github/commit-activity/m/AEmotionStudio/ComfyUI-FFMPEGA?style=for-the-badge&label=Activity&color=yellow)](https://github.com/AEmotionStudio/ComfyUI-FFMPEGA/commits)

*Describe what you want in plain English — the AI translates your words into precise FFMPEG commands.*

[Features](#-features) • [Installation](#-installation) • [Quick Start](#-quick-start) • [Skills](#-skill-system) • [LLM Setup](#-llm-configuration) • [Troubleshooting](#-troubleshooting) • [Contributing](#-contributing) • [Changelog](CHANGELOG.md)

</div>

---

## 🚀 What's New in v1.6.1 (February 9, 2026)

**Audio Fixes + LLM Reliability + Test Suite**

*   **🔊 Audio Pipeline Fixes**: Fixed audio mux re-adding audio after `remove_audio`, fixed audio overwriting when `audio_input` is connected, and fixed audio template skill misrouting.
*   **🧠 Smarter LLM Retry**: Auto-retry JSON parsing failures with a correction prompt and self-correction loop for non-JSON responses.
*   **🧪 Test Suite**: Added test infrastructure with `conftest.py`, import-safe `__init__.py`, and `dev` extras — run with `uv run --extra dev pytest`.
*   **🌀 Pulse Fix**: Rewrote `pulse` zoompan filter to resolve parsing issues.
*   **📄 Skill Test Prompts**: Added `SKILL_TEST_PROMPTS.md` with copy-friendly test prompts for every skill category.

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
Works with **Ollama** (local, free), **OpenAI** (GPT-4o), and **Anthropic** (Claude). Use any local model — Llama 3.1, Qwen3, Mistral, and more. No API keys required for local models.

</td>
</tr>
<tr>
<td width="50%">

### 🎨 100+ Skills
Over 100 video editing skills across visual effects, audio processing, spatial transforms, temporal edits, encoding settings, cinematic presets, vintage looks, social media optimization, and creative effects.

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
pip install -r requirements.txt
```

Restart ComfyUI after installation.

---

## 🚀 Quick Start

1. Add an **FFMPEG Agent** node to your workflow
2. Connect a video path or use the input field
3. Enter a natural language prompt
4. Select your LLM model
5. Run the workflow

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

---

## 🎛️ Nodes

### FFMPEG Agent
The main node — translates natural language into FFMPEG commands.

| Input | Description |
| :--- | :--- |
| `video_path` | Path to input video (used unless `images` is connected) |
| `prompt` | Natural language editing instruction |
| `llm_model` | Model selection (Ollama / OpenAI / Anthropic / Gemini) |
| `quality_preset` | Output quality: draft, standard, high, lossless |
| `images` | *(optional)* Image frames from an upstream node |
| `audio_input` | *(optional)* Audio from an upstream node |
| `preview_mode` | Quick preview instead of full render |
| `output_path` | Custom output path (optional) |
| `ollama_url` | Ollama server URL (default: `http://localhost:11434`) |
| `api_key` | API key for cloud LLM providers |

| Output | Description |
| :--- | :--- |
| `images` | Video frames as image tensor |
| `audio` | Audio extracted or passed through |
| `video_path` | Path to processed video |
| `command_log` | FFMPEG commands that were executed |
| `analysis` | Agent's interpretation of your prompt |

---

## 🎯 Skill System

FFMPEGA includes a comprehensive skill system with **115+ operations** organized into categories. The AI agent selects the right skills based on your prompt.

> 📄 **See [SKILLS_REFERENCE.md](SKILLS_REFERENCE.md) for the complete skill reference with all parameters and example prompts.**

<details>
<summary><b>🎨 Visual Effects (17 skills)</b></summary>

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

</details>

<details>
<summary><b>⏱️ Temporal (5 skills)</b></summary>

| Skill | Description |
| :--- | :--- |
| `trim` | Cut a segment by time |
| `speed` | Change playback speed (0.1x to 10x) |
| `reverse` | Play backwards |
| `loop` | Repeat video |
| `fps` | Change frame rate (1 to 120) |

</details>

<details>
<summary><b>📐 Spatial (6 skills)</b></summary>

| Skill | Description |
| :--- | :--- |
| `resize` | Scale to specific dimensions |
| `crop` | Crop video region |
| `rotate` | Rotate by degrees |
| `flip` | Mirror horizontal/vertical |
| `pad` | Add padding / letterbox |
| `aspect` | Change aspect ratio (16:9, 4:3, 1:1, 9:16, 21:9) |

</details>

<details>
<summary><b>🔊 Audio (16 skills)</b></summary>

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

</details>

<details>
<summary><b>📦 Encoding (9 skills)</b></summary>

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

</details>

<details>
<summary><b>🎬 Cinematic Presets (10 skills)</b></summary>

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
<summary><b>🧪 Special Effects (8 skills)</b></summary>

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

---

## 🤖 LLM Configuration

### Ollama (Local — Free)
The default option. Runs locally, no API key needed.

```bash
# Install and start Ollama
ollama serve

# Pull a model
ollama pull llama3.1:8b
```

**Recommended local models:**
| Model | Speed | Quality | Notes |
| :--- | :--- | :--- | :--- |
| `llama3.1:8b` | ⚡ Fast | Good | Best balance for most users |
| `qwen3:8b` | ⚡ Fast | Good | Strong JSON output |
| `llama3.1:70b` | 🐢 Slow | Excellent | Best quality, needs GPU RAM |
| `mistral:7b` | ⚡ Fast | Good | Fast alternative |

### OpenAI
```
llm_model: gpt-4o-mini
api_key: your-openai-key
```

### Gemini (Google)
```
llm_model: gemini-2.0-flash
api_key: your-google-ai-key
```

Available models: `gemini-2.0-flash`, `gemini-2.0-flash-lite`, `gemini-1.5-flash`

### Anthropic
```
llm_model: claude-3-5-haiku-20241022
api_key: your-anthropic-key
```

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

---

## 📁 Project Structure

```
ComfyUI-FFMPEGA/
├── __init__.py              # ComfyUI entry point
├── nodes/                   # ComfyUI node definitions
│   ├── agent_node.py        # FFMPEG Agent main node
│   ├── preview_node.py      # Preview and info nodes
│   └── batch_node.py        # Batch processing nodes
├── core/                    # Core functionality
│   ├── llm/                 # LLM connectors (Ollama, OpenAI, Anthropic)
│   ├── executor/            # FFMPEG command building & execution
│   └── video/               # Video analysis & formats
├── skills/                  # Skill system
│   ├── registry.py          # Skill registration & validation
│   ├── composer.py          # Pipeline composition engine
│   ├── category/            # Low-level skills (temporal, spatial, visual, audio, encoding)
│   └── outcome/             # High-level skills (cinematic, vintage, social, creative, effects)
├── prompts/                 # LLM prompt templates
├── mcp/                     # MCP server for programmatic access
├── js/                      # Custom ComfyUI UI widgets
├── SKILLS_REFERENCE.md      # Complete skill reference
└── tests/                   # Test suite
```

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
