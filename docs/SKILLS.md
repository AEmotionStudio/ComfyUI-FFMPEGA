# 🎯 Skill System

*Part of the [ComfyUI-FFMPEGA](../README.md) documentation.*

FFMPEGA includes a comprehensive skill system with **226 operations** organized into categories. Use them in two ways: let the **AI agent** select skills from your prompt, or pick them yourself with the **Effects Builder** — no LLM needed.

> 📄 **See [SKILLS_REFERENCE.md](../SKILLS_REFERENCE.md) for the complete skill reference with all parameters and example prompts.**
>
> 🧪 **See [SKILL_TEST_PROMPTS.md](../SKILL_TEST_PROMPTS.md) for ready-to-use copy-and-paste test prompts for every skill.**

<details>
<summary><b>🎨 Visual Effects (31 skills)</b></summary>

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
| `colorkey` | Key out any arbitrary color and replace with a background |
| `colorhold` | Keep only a selected color, desaturate everything else (spot color) |
| `lumakey` | Key out regions based on brightness (luma) |
| `despill` | Remove green/blue color spill from chroma-keyed edges |
| `deband` | Remove color banding artifacts |
| `white_balance` | Adjust color temperature (2000K–12000K) |
| `shadows_highlights` | Separately adjust shadows and highlights |
| `split_tone` | Warm highlights, cool shadows |
| `deflicker` | Remove fluorescent/timelapse flicker |
| `unsharp_mask` | Fine-grained luma/chroma sharpening |
| `remove_background` | Remove backgrounds using AI (rembg) |
| `selective_color` | Isolate and adjust specific color ranges |

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
<summary><b>🔊 Audio (27 skills)</b></summary>

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
| `mix_audio` | Mix/blend audio tracks from two inputs (both audible) |
| `audio_bitrate` | Set audio encoding bitrate |

</details>

<details>
<summary><b>📦 Encoding (12 skills)</b></summary>

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
<summary><b>📱 Social Media (8 skills)</b></summary>

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
<summary><b>🔗 Multi-Input & Composition (7 skills)</b></summary>

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
<summary><b>✂️ Editing & Delivery (12 skills)</b></summary>

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

<details>
<summary><b>🤖 AI-Powered (18 skills)</b></summary>

| Skill | Description |
| :--- | :--- |
| `auto_transcribe` | Transcribe audio with Whisper AI and burn SRT subtitles |
| `karaoke_subtitles` | Word-by-word karaoke subtitles with progressive color fill (Whisper) |
| `auto_mask` | SAM3-powered object segmentation from text prompts |
| `generate_audio` | AI-generate synchronized audio/foley from video + text (MMAudio) |
| `generate_music` | AI music generation with ACE-Step 1.5 — text-to-music, style-guided covers |
| `generate_sample` | AI music sample generation with Foundation-1 — tempo-synced loops |
| `audio_inpaint` | AI audio repair and enhancement using AudioX/ACE-Step pipeline |
| `audio_separate` | AI source separation with SAM-Audio — split into vocal/drum/bass/other stems |
| `lip_sync` | AI lip sync with MuseTalk — synchronize lip movements to audio |
| `animate_portrait` | AI face animation with LivePortrait — transfer expressions from driving video |
| `fish_speech` | AI text-to-speech with Fish Audio S2 Pro — 80+ languages, voice cloning, emotion tags |
| `dreamid_omni` | ⚠️ WIP — AI talking-head video generation with identity and voice preservation (DreamID-Omni) |
| `kiwi_edit` | AI video editing with Kiwi-Edit — text-instruction and reference-image editing |
| `remove_background` | AI background removal with BRIA RMBG — 6 model choices |
| `ai_upscale` | AI super-resolution upscaling with Real-ESRGAN, HAT, DAT, or SwinIR — auto-VRAM tile sizing |
| `video_depth` | Temporal depth estimation with Video Depth Anything — consistent depth maps across frames |
| `marigold` | Dense vision analysis with Marigold — depth, normals, appearance, and lighting estimation |
| `ace_step` | AI music generation with ACE-Step 1.5 — direct no-LLM mode for quick generation |

> ⚠️ **License Notice:** The `generate_audio` skill uses [MMAudio](https://github.com/hkchengrex/MMAudio) model weights which are licensed under **CC-BY-NC 4.0** (non-commercial use only). Model weights are downloaded on first use — by downloading them you accept the [CC-BY-NC 4.0 license](https://creativecommons.org/licenses/by-nc/4.0/). The FFMPEGA code itself remains GPL-3.0.

> ⚠️ **License Notice:** The `auto_mask:effect=remove` skill (when `use_minimax_remover=On`) uses [MiniMax-Remover](https://github.com/zibojia/MiniMax-Remover) model weights which are licensed under **CC-BY-NC 4.0** (non-commercial use only). Model weights are downloaded on first use — by downloading them you accept the [CC-BY-NC 4.0 license](https://creativecommons.org/licenses/by-nc/4.0/). The vendored code is Apache 2.0.

> ⚠️ **License Notice:** Fish Speech S2 Pro is under the Fish Audio Research License — free for research/non-commercial use, commercial use requires a separate license from Fish Audio.

</details>

### 🧠 Agentic Tools

Beyond the 200+ editing skills, the agent has built-in tools for analyzing media and making better decisions. In LLM mode, the agent calls these autonomously based on your prompt. Some (like `analyze_video` and `search_skills`) are also invoked directly by internal skills, the Effects Builder, and no-LLM modes.

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
# Linux / macOS / Windows (Git Bash or PowerShell)
cd custom_skills/
git clone https://github.com/someone/ffmpega-retro-pack retro-pack
```

Two example skills ship in `custom_skills/examples/` — `warm_glow.yaml` (template) and `film_burn.yaml` (pipeline composite).

> 📄 **See [CUSTOM_SKILLS.md](../CUSTOM_SKILLS.md) for the full schema reference, skill pack structure, Python handlers, and advanced examples.**

</details>

---
