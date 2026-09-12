<div align="center">

# ComfyUI-FFMPEGA

**The ultimate video editing suite for ComfyUI — edit with natural language or hands-on manual controls.**

[![ComfyUI](https://img.shields.io/badge/ComfyUI-Extension-green?style=for-the-badge)](https://github.com/comfyanonymous/ComfyUI)
[![Version](https://img.shields.io/badge/Version-2.20.0-orange?style=for-the-badge)](https://github.com/AEmotionStudio/ComfyUI-FFMPEGA/releases)
[![License](https://img.shields.io/badge/License-GPLv3-red?style=for-the-badge)](LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-3-brightgreen?style=for-the-badge&color=blue)](requirements.txt)
[![Last Commit](https://img.shields.io/github/last-commit/AEmotionStudio/ComfyUI-FFMPEGA?style=for-the-badge&label=Last%20Update&color=orange)](https://github.com/AEmotionStudio/ComfyUI-FFMPEGA/commits)
[![Activity](https://img.shields.io/github/commit-activity/m/AEmotionStudio/ComfyUI-FFMPEGA?style=for-the-badge&label=Activity&color=yellow)](https://github.com/AEmotionStudio/ComfyUI-FFMPEGA/commits)

![FFMPEGA Showcase](https://github.com/AEmotionStudio/ComfyUI-FFMPEGA/releases/download/assets-v1/Screenshot_20260219_165846.png)

*Use AI to describe edits in plain English, or take full manual control with the Effects Builder and text presets — no LLM required.*

[Features](#-features) • [Examples](docs/EXAMPLES.md) • [Installation](#-installation) • [Quick Start](#-quick-start) • [Prompt Guide](#-prompt-guide) • [Skills](docs/SKILLS.md) • [LLM Setup](docs/LLM-SETUP.md) • [Troubleshooting](#-troubleshooting) • [Contributing](#-contributing) • [Changelog](CHANGELOG.md)

</div>

---

## 🚀 What's New in v2.20.0

*See [CHANGELOG.md](CHANGELOG.md#2200---2026-09-11) for the full detail.*

*   🕺 **SCAIL-2** — pose-driven character animation, rebuilt ComfyUI-native and in-process (no subprocess). Native SAM 3.1 identity tracking, colored per-identity pose masks, 25 advanced widgets. Replaces the vendored SCAIL v1 pipeline
*   ⚡ **FlashVSR** — one-step video super-resolution with `full` / `tiny` / `tiny_long` pipelines, DiT block swap, and near-lossless spatial decode tiling
*   ♾️ **SVI 2.0 Pro** — infinite-length video generation (ICLR 2026 Oral) via iterative 81-frame Wan 2.2 I2V-A14B clips, with block swap and tiled VAE
*   🎭 **Wan-Animate** & **MatAnyone2** — ComfyUI-native Wan 2.2 Animate character animation, plus CVPR 2026 video matting with temporal coherence
*   🧍 **Meta Sapiens2** — human-centric vision: 308-keypoint pose, 29-class body-part segmentation, normals, pointmap and matting, with an fp8 5B option
*   🧊 **SHARP** & **PhyFPS** — single-image 3D Gaussian view synthesis, and physical frame-rate detection/re-timing via the Visual Chronometer
*   🖼️ **Multi-Source Comparison** — Save Video and Save Image now combine multiple inputs into one side-by-side or grid clip/image, with layout, per-panel labels and gap controls
*   📹 **FaceCam Analytic Face Mesh** — camera pose is projected from MediaPipe's canonical model instead of being detected back off a rendered proxy head, so conditioning survives past 40–50° of yaw and `orbit_left`/`orbit_right` are exact mirrors
*   🎨 **Correct Video Levels** — encoding now emits standard limited-range BT.709 instead of deprecated `yuvj420p`, fixing crushed blacks and blown highlights in players that re-expand it
*   🎬 **Advanced Save Video Output** — H.264/H.265/VP9/AV1/ProRes/FFV1/GIF/WebP, CRF, presets, 10-bit, audio codec, loop, pingpong and workflow-in-the-container metadata — while the default stays a zero-cost file copy
*   🌈 **Selectable Colour Policy** — one shared, measured colour path across every encoder, with a truthful sRGB default and an exact "match ComfyUI native" mode for A/B comparison

<details>
<summary><b>📋 Previous Releases</b></summary>

| Version | Highlights |
| :--- | :--- |
| **v2.19.0** | DreamID-Omni talking-head generation, FaceCam camera control, Fish Speech TTS, Foundation-1 music samples, Frame Picker node, 15 new GLSL shaders (70 total) |
| **v2.18.0** | Kiwi-Edit AI video editing, SAM3 + Kiwi-Edit, RTX Video Super Resolution, SeedVR AI Upscaling, FacePoke expression presets |
| **v2.17.0** | FacePoke interactive face editor, driving video reference, shader effects system, Flux Klein FP8, onion skin compositing, unified audio output mode |
| **v2.16.0** | ACE-Step AI music generation, SAM-Audio source separation, Video Editor v2 (10 panels), AudioX vocal enhancement, NormalCrafter, Video Depth Anything |
| **v2.15.0** | MiniMax-Remover, 5 new no-LLM modes, auto-VRAM tile sizing, VRAM management overhaul |
| **v2.14.0** | Video Editor NLE node with timeline, razor, crop, transitions, text overlays, keyboard shortcuts |
| **v2.13.0** | AI Background Removal (BRIA RMBG), FLUX Klein toggle, Edit FFmpeg fallback, smarter defaults |
| **v2.12.0** | AI Face Animation (LivePortrait), MMAudio in-process inference, MCP progressive disclosure, LaMa safetensors conversion |
| **v2.11.0** | MMAudio in-process migration, `generate_audio` no-LLM mode, MCP tools, CLI binary caching |
| **v2.10.0** | FLUX Klein in-process migration, interactive mask drawing UI, model output caching |
| **v2.9.1** | AI object removal & editing (FLUX Klein 4B), AI audio generation (MMAudio), AI lip sync (MuseTalk), modular architecture refactor |
| **v2.8.0** | Effects Builder node, manual no-LLM mode, text node presets, SAM3 subprocess isolation, 15+ bug fixes |
| **v2.7.0** | SAM3 auto-mask & greenscreen, LaMa inpainting, programmatic tool calling (PTC) |
| **v2.6.5** | Whisper auto-transcription, karaoke subtitles, whisper model/device controls |
| **v2.6.0** | HandlerResult contract, compose decomposition, TextInput node, PiP audio mixing, CLI retry |
| **v2.5.0** | PiP borders, Ollama VL auto-embedding, overlay animation delegation |
| **v2.4.0** | Zero-memory image paths, pipeline chaining fixes, handler module extraction |
| **v2.3.0** | Token usage tracking, LUT color grading, vision system, audio analysis |
| **v2.2.0** | 200 skills, dynamic input slots, 48 new skills across all categories |
| **v2.0.0** | Dynamic input slots, concat, xfade, split screen, animated overlays, text overlays |
| **v1.9.0** | Claude CLI, Cursor Agent CLI, Qwen CLI connectors, 50+ context menu presets |

</details>

> 📄 **See [CHANGELOG.md](CHANGELOG.md) for the complete version history.**

---

[<img src="https://img.youtube.com/vi/UV2jBzSyb-k/maxresdefault.jpg" width="100%">](https://youtu.be/UV2jBzSyb-k)
<p align="center"><i>NotebookLM Overview: Exploring the features and capabilities of ComfyUI-FFMPEGA. (Click to watch on YouTube)</i></p>

## ✨ Features

<table>
<tr>
<td width="50%">

### 🗣️ Natural Language Editing
Describe edits in plain text: *"Make it cinematic with a fade in"*, *"Speed up 2x"*, *"VHS look with grain"*. The AI agent interprets your prompt and builds the FFMPEG pipeline automatically.

</td>
<td width="50%">

### 🏗️ Manual Mode — No AI Required
Use the **Effects Builder** to visually compose up to 5 effects with parameters. Add **text overlays and subtitles** via preset-powered Text nodes. Full editing control with zero LLM dependency.

</td>
</tr>
<tr>
<td width="50%">

### 🤖 Multi-LLM Support
Works with **Ollama** (local, free) and **CLI tools** (Gemini CLI, Claude Code, Cursor Agent, Qwen Code). Use any local model — Llama 3.1, Qwen3, Mistral, and more. Or skip the LLM entirely.

</td>
<td width="50%">

### 🎨 200+ Skills
200+ video editing skills across visual effects, audio processing, spatial transforms, temporal edits, encoding, cinematic presets, vintage looks, social media, creative effects, text animations, editing & composition, audio visualization, multi-input operations, transitions, concat, split screen, and AI-powered skills (DreamID-Omni talking-head generation, FaceCam camera control, Fish Speech TTS, Foundation-1 music samples, ACE-Step music generation, SAM-Audio source separation, AudioX vocal enhancement, Whisper transcription, SAM3 masking, MiniMax-Remover object removal, MMAudio generation, MuseTalk lip sync, LivePortrait face animation, NormalCrafter surface normals, Video Depth estimation, AI Upscaling, Marigold dense vision).

</td>
</tr>
<tr>
<td width="50%">

### 🎨 Right-Click Presets
26 built-in Effects Builder presets and 10 Text node presets with example content. Save/load/delete your own custom presets. One-click clear to reset.

</td>
<td width="50%">

### ⚡ Batch & Preview
Process multiple videos with the same instruction. Generate quick low-res previews before committing to full renders. Quality presets from draft to lossless.

</td>
</tr>
</table>

---

## 🎬 Examples

Worked examples: prompts, the pipelines they produce, and the resulting output.

**→ [docs/EXAMPLES.md](docs/EXAMPLES.md)**

## 📦 Installation

### Requirements

- **ComfyUI** (latest)
- **Python 3.10+**
- **FFMPEG** installed and in PATH ([install guide](#ffmpeg-not-found))
- **Node.js 18+** (required for CLI tools: Gemini CLI, Claude CLI, Qwen CLI — [download](https://nodejs.org/))
- **Ollama** (optional, for local LLM inference — [download](https://ollama.com/download))

### Option 1: ComfyUI Manager (Recommended)
1. Open **ComfyUI Manager**
2. Search for **`ComfyUI-FFMPEGA`**
3. Click **Install**

### Option 2: Manual Install

<details>
<summary><b>Linux / macOS</b></summary>

```bash
cd /path/to/ComfyUI/custom_nodes
git clone https://github.com/AEmotionStudio/ComfyUI-FFMPEGA.git
cd ComfyUI-FFMPEGA
pip install -r requirements.txt
```

</details>

<details>
<summary><b>Windows (PowerShell)</b></summary>

```powershell
cd C:\path\to\ComfyUI\custom_nodes
git clone https://github.com/AEmotionStudio/ComfyUI-FFMPEGA.git
cd ComfyUI-FFMPEGA
pip install -r requirements.txt
```

</details>

> **Note:** Use whichever Python package manager your ComfyUI venv uses (`pip`, `uv pip`, etc.). The above commands assume `pip` is available in your ComfyUI virtual environment.

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

When using an LLM, the AI agent interprets your natural language and maps it to skills with specific parameters. Here's how to get the best results. *(For manual editing without an LLM, see the [Effects Builder](#-effects-builder) and [Text Input](#text-input-ffmpega) sections.)*

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

## 🧠 AI Models (Auto-Downloaded)

Some skills use AI models that **auto-download on first use**. You can disable automatic downloads with the `allow_model_downloads` toggle on the FFMPEG Agent node — runs requiring a missing model will fail with a clear message and a manual download link.

All models are mirrored to first-party [AEmotionStudio](https://huggingface.co/AEmotionStudio) HuggingFace repos for supply chain resilience. Downloads try the AEmotionStudio mirror first, then fall back to upstream sources.

| Model | Size | Stored In | Triggered By | Manual Download |
| :--- | :--- | :--- | :--- | :--- |
| **SAM3** (Segment Anything 3) | ~300 MB | `ComfyUI/models/SAM3/` | `auto_mask` skill, `sam3_masking` no-LLM mode, Effects Builder SAM3 target | [AEmotionStudio/sam3](https://huggingface.co/AEmotionStudio/sam3) — download `sam3.safetensors` |
| **SAM3.1** (Multiplex Tracker) | ~3.5 GB | `ComfyUI/models/SAM3.1/` | Same triggers with `sam_version = sam3.1` (default). Video masking runs **in-process** on ComfyUI's native SAM3 model (VRAM-managed, ~3 GB peak); set `FFMPEGA_SAM3_NATIVE=0` to force the legacy subprocess path | [AEmotionStudio/sam3.1](https://huggingface.co/AEmotionStudio/sam3.1) — download `sam3.1_multiplex.safetensors` |
| **Whisper** large-v3 | ~3 GB | `ComfyUI/models/whisper/` | `auto_transcribe`, `karaoke_subtitles` skills, `transcribe` / `karaoke_subtitles` no-LLM modes | [AEmotionStudio/whisper-models](https://huggingface.co/AEmotionStudio/whisper-models) |
| **Whisper** medium | ~1.5 GB | `ComfyUI/models/whisper/` | Same as above (set `whisper_model` to `medium`) | Same as above |
| **Whisper** small | ~500 MB | `ComfyUI/models/whisper/` | Same as above (set `whisper_model` to `small`) | Same as above |
| **Whisper** base | ~150 MB | `ComfyUI/models/whisper/` | Same as above (set `whisper_model` to `base`) | Same as above |
| **Whisper** tiny | ~75 MB | `ComfyUI/models/whisper/` | Same as above (set `whisper_model` to `tiny`) | Same as above |
| **LaMa** (Large Mask Inpainting) | ~195 MB | `~/.cache/torch/hub/checkpoints/` | `auto_mask:effect=remove` (legacy fallback) | [AEmotionStudio/lama-inpainting](https://huggingface.co/AEmotionStudio/lama-inpainting) — download `big-lama.safetensors` |
| **FLUX Klein 4B** (Editing/Removal) | ~15 GB (bf16) | `ComfyUI/models/flux_klein/` | `auto_mask:effect=remove`, `auto_mask:effect=edit` | [AEmotionStudio/flux-klein](https://huggingface.co/AEmotionStudio/flux-klein) |
| **MiniMax-Remover** (Object Removal) | ~2.5 GB | `ComfyUI/models/minimax_remover/` | `auto_mask:effect=remove` (when `use_minimax_remover` is On) | [AEmotionStudio/minimax-remover](https://huggingface.co/AEmotionStudio/minimax-remover) |
| **MMAudio** (Video-to-Audio) | ~5.5 GB | `ComfyUI/models/mmaudio/` | `generate_audio` skill | [AEmotionStudio/mmaudio-models](https://huggingface.co/AEmotionStudio/mmaudio-models) |
| **MuseTalk** (Lip Sync) | ~1.6 GB (fp16) | `ComfyUI/models/musetalk/` | `lip_sync` skill | [AEmotionStudio/musetalk-models](https://huggingface.co/AEmotionStudio/musetalk-models) |
| **LivePortrait** (Face Animation) | ~497 MB | `ComfyUI/models/liveportrait/` | `animate_portrait` skill, `animate_portrait` no-LLM mode | [AEmotionStudio/liveportrait-models](https://huggingface.co/AEmotionStudio/liveportrait-models) |
| **Video Depth Anything** (Temporal Depth) | ~102–670 MB | `ComfyUI/models/video_depth/` | `video_depth` no-LLM mode | [AEmotionStudio/video-depth-anything](https://huggingface.co/AEmotionStudio/video-depth-anything) |
| **Marigold** (Dense Vision) | ~2.5 GB per mode | Auto-downloaded by diffusers | `marigold` no-LLM mode (depth/normals/appearance/lighting) | [AEmotionStudio/marigold-depth-v1-1](https://huggingface.co/AEmotionStudio/marigold-depth-v1-1) |
| **AI Upscaler** (Real-ESRGAN / HAT / DAT / SwinIR) | ~17–170 MB per model | `ComfyUI/models/upscale_models/` | `ai_upscale` skill, `ai_upscale` no-LLM mode | [AEmotionStudio/ai-upscale-models](https://huggingface.co/AEmotionStudio/ai-upscale-models) |
| **BRIA RMBG** (rembg) | ~270 MB | `~/.u2net/` | `remove_background` skill | Install with `pip install 'comfyui-ffmpega[masking]'` — model auto-fetched by rembg |
| **ACE-Step 1.5** (Music Generation) | ~5 GB | `ComfyUI/models/acestep/` | `ace_step` no-LLM mode, `generate_music` skill | [AEmotionStudio/ACE-Step](https://huggingface.co/AEmotionStudio/ACE-Step) |
| **SAM-Audio** (Source Separation) | ~1.2 GB (large) / ~600 MB (fp8) | `ComfyUI/models/sam_audio/` | `audio_separate` no-LLM mode | [AEmotionStudio/sam-audio](https://huggingface.co/AEmotionStudio/sam-audio) |
| **AudioX** (Vocal Enhancement) | ~1 GB | `ComfyUI/models/audiox/` | AudioX chaining with ACE-Step | [AEmotionStudio/audiox](https://huggingface.co/AEmotionStudio/audiox) |
| **NormalCrafter** (Surface Normals) | ~2 GB | `ComfyUI/models/normalcrafter/` | `normalcrafter` no-LLM mode | [AEmotionStudio/NormalCrafter](https://huggingface.co/AEmotionStudio/NormalCrafter) |
| **Kiwi-Edit** (AI Video Editing) | ~5 GB (FP8) / ~10 GB (BF16) | `ComfyUI/models/kiwi_edit_*` | `kiwi_edit` no-LLM mode | [AEmotionStudio/Kiwi-Edit-Instruct](https://huggingface.co/AEmotionStudio/Kiwi-Edit-Instruct) |
| **DreamID-Omni** (Talking Head) ⚠️ WIP | ~12 GB (FP8) / ~23 GB (BF16) | `ComfyUI/models/dreamid_omni/` | `dreamid_omni` no-LLM mode | [AEmotionStudio/dreamid-omni](https://huggingface.co/AEmotionStudio/dreamid-omni) |
| **FaceCam** (Camera Control) | ~16.8 GB (high+low bf16) | `ComfyUI/models/diffusion_models/` | FaceCam node | [AEmotionStudio/facecam-wan2.2-14b-bf16](https://huggingface.co/AEmotionStudio/facecam-wan2.2-14b-bf16) |
| **Fish Speech S2 Pro** (TTS) | ~6.5 GB (FP8) / ~10.4 GB (BF16) | `ComfyUI/models/fish_speech/` | `fish_speech` no-LLM mode | [AEmotionStudio/fish-speech-s2-pro](https://huggingface.co/AEmotionStudio/fish-speech-s2-pro) |
| **Foundation-1** (Music Samples) | ~2 GB | `ComfyUI/models/foundation1/` | `foundation1` no-LLM mode | [AEmotionStudio/foundation1-models](https://huggingface.co/AEmotionStudio/foundation1-models) |
| **SeedVR2** (Diffusion Upscaler) | ~3.4 GB (3B INT8) / ~8.3 GB (7B INT8) + ~300 MB (VAE) | `ComfyUI/models/SEEDVR2/` or `ComfyUI/models/diffusion_models/` (both searched) | `ai_upscale` with `upscale_model = seedvr2_*`. Prefer `seedvr2_3b_int8` / `seedvr2_7b_int8`; raise `blockswap_blocks` to fit the 7B under 16 GB | [AEmotionStudio/SeedVR2-models](https://huggingface.co/AEmotionStudio/SeedVR2-models) (FP8/GGUF). INT8 ConvRot checkpoints are local-only — place `seedvr2_{3b,7b}_int8_convrot.safetensors` in either folder |
| **FlashVSR v1.1** (One-Step VSR) | ~5 GB (DiT + VAE + LQ_proj + TCDecoder) | `ComfyUI/models/FlashVSR/` | `ai_upscale` with `upscale_model = flashvsr_full` / `flashvsr_tiny` / `flashvsr_tiny_long` | [AEmotionStudio/flashvsr-models](https://huggingface.co/AEmotionStudio/flashvsr-models) — GPL-3.0 |
| **SCAIL-2** (Pose-Driven Animation) | ~16 GB (fp8) | `ComfyUI/models/diffusion_models/` | `scail2` no-LLM mode. Also needs the Wan 2.1 VAE, UMT5-XXL text encoder and `clip_vision_h` | [Comfy-Org/SCAIL-2](https://huggingface.co/Comfy-Org/SCAIL-2) — `wan2.1_14B_SCAIL_2_fp8_scaled.safetensors` |
| **SVI 2.0 Pro** (Infinite-Length Video) | ~500 MB (high + low LoRAs) | `ComfyUI/models/svi/version-2.0/` | `svi` no-LLM mode. ⚠️ Also requires the Wan 2.2 I2V-A14B base model (~28 GB) | [AEmotionStudio/svi-loras](https://huggingface.co/AEmotionStudio/svi-loras) |
| **Wan-Animate** (Character Animation) | ~18 GB (DiT) + ~2.5 GB (pose) + ~62 MB (detector) | `ComfyUI/models/wan_animate/` | `wan_animate` no-LLM mode | [Kijai/WanVideo_comfy_fp8_scaled](https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled), [Kijai/vitpose_comfy](https://huggingface.co/Kijai/vitpose_comfy) |
| **MatAnyone2** (Video Matting) | ~135 MB | `ComfyUI/models/matanyone2/` | `video_matting` no-LLM mode | [AEmotionStudio/matanyone2](https://huggingface.co/AEmotionStudio/matanyone2) — ⚠️ NTU S-Lab 1.0, non-commercial |
| **Sapiens2** (Human-Centric Vision) | ~1 GB (0.4B) – ~10 GB (5B fp16) | `ComfyUI/models/sapiens2/<task>/` | `sapiens2` no-LLM mode — pose (308 keypoints), segmentation (29 classes), normals, pointmap, matting | [AEmotionStudio/sapiens2-normal](https://huggingface.co/AEmotionStudio/sapiens2-normal) and sibling `sapiens2-*` repos |
| **SHARP** (3D Gaussian View Synthesis) | ~400 MB | `ComfyUI/models/sharp/` | `sharp` no-LLM mode | [AEmotionStudio/sharp](https://huggingface.co/AEmotionStudio/sharp) — ⚠️ Apple ML Research License, non-commercial |
| **Visual Chronometer** (PhyFPS) | ~1 GB | `ComfyUI/models/visual_chronometer/` | `phyfps` no-LLM mode | [AEmotionStudio/Visual_Chronometer](https://huggingface.co/AEmotionStudio/Visual_Chronometer) |

> [!NOTE]
> Models are only downloaded when you use the corresponding skill for the first time. Core FFmpeg editing skills (200+ of them) require **zero model downloads**.

---

## 🎛️ Nodes

Every node, input and output — the Agent node's widgets, the save/load nodes, the Video Editor and the rest.

**→ [docs/NODES.md](docs/NODES.md)**

## 🎯 Skill System

All 200+ skills by category, their parameters, and how to write your own.

**→ [docs/SKILLS.md](docs/SKILLS.md)**

## 🤖 LLM Configuration

Ollama, the four CLI connectors (Gemini CLI, Claude Code, Cursor Agent, Qwen Code), model choice and troubleshooting.

**→ [docs/LLM-SETUP.md](docs/LLM-SETUP.md)**

## 🐛 Troubleshooting

<details>
<summary><b>FFMPEG Not Found</b></summary>

Ensure FFMPEG is installed and in your system PATH:
```bash
ffmpeg -version
```

**Install FFMPEG:**

| Platform | Command / Method |
| :--- | :--- |
| **Ubuntu / Debian** | `sudo apt install ffmpeg` |
| **Arch / CachyOS** | `sudo pacman -S ffmpeg` |
| **Fedora** | `sudo dnf install ffmpeg` |
| **macOS** | `brew install ffmpeg` |
| **Windows (winget)** | `winget install Gyan.FFmpeg` |
| **Windows (choco)** | `choco install ffmpeg` |
| **Windows (scoop)** | `scoop install ffmpeg` |
| **Windows (manual)** | Download from [ffmpeg.org/download](https://ffmpeg.org/download.html), extract, and add the `bin/` folder to your system PATH |

> **Windows PATH tip:** After installing, open a **new** terminal and run `ffmpeg -version` to verify. If not found, you may need to add ffmpeg's `bin/` directory to your system PATH manually: Settings → System → About → Advanced system settings → Environment Variables → Edit `Path`.

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
ollama pull qwen2.5:8b
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

If the LLM is taking too long or you want to abort mid-request, **close the ComfyUI terminal or restart ComfyUI** instead of using the interrupt button. The interrupt button waits for the current LLM response to complete, which can take a while — closing/restarting ComfyUI kills it immediately.

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
