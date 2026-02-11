# FFMPEGA Skills Reference

A comprehensive guide to all available skills. Use these as natural language prompts — the LLM translates them into FFmpeg commands.

---

## 🎨 Visual Effects

### brightness
Adjust video brightness.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `value` | float | 0.1 | -1.0 to 1.0 |

**Example prompts:**
- "Make the video brighter"
- "Increase brightness slightly"
- "Darken the footage"

---

### contrast
Adjust video contrast.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `value` | float | 1.2 | 0.0 to 3.0 |

**Example prompts:**
- "Increase the contrast"
- "Make it more punchy"
- "Lower the contrast for a flat look"

---

### saturation
Adjust color saturation.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `value` | float | 1.3 | 0.0 to 3.0 |

**Example prompts:**
- "Make the colors more vibrant"
- "Desaturate the video"
- "Boost the saturation"

---

### hue
Shift the color hue.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `value` | int | 15 | -180 to 180 |

**Example prompts:**
- "Shift the colors to blue/teal"
- "Add a warm color shift"
- "Change the hue toward purple"

---

### sharpen
Increase image sharpness.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `amount` | float | 1.0 | 0.1 to 3.0 |

**Example prompts:**
- "Sharpen the video"
- "Make it crisper"
- "Add subtle sharpening"

---

### blur
Apply blur effect.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `radius` | int | 5 | 1 to 50 |

**Example prompts:**
- "Blur the video slightly"
- "Apply a strong blur"
- "Add a soft dreamy blur"

---

### denoise
Reduce video noise/grain.
| Parameter | Type | Default | Choices |
|-----------|------|---------|---------|
| `strength` | choice | medium | light, medium, strong |

**Example prompts:**
- "Clean up the noisy footage"
- "Remove grain from the video"
- "Denoise aggressively"

---

### vignette
Darken the edges for a cinematic focus effect.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `intensity` | float | 0.3 | 0.0 to 1.0 |

**Example prompts:**
- "Add a vignette"
- "Darken the edges"
- "Apply a strong vignette for dramatic effect"

---

### fade
Add fade in/out to black.
| Parameter | Type | Default | Choices/Range |
|-----------|------|---------|---------------|
| `type` | choice | in | in, out |
| `start` | time | 0 | seconds |
| `duration` | time | 1 | seconds |

**Example prompts:**
- "Fade in from black over 2 seconds"
- "Add a fade out at the end"
- "Fade in at the start and fade out at the end"

---

### colorbalance
Adjust color balance across shadows, midtones, highlights.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `rs` | float | 0 | -1 to 1 (red shadows) |
| `gs` | float | 0 | -1 to 1 (green shadows) |
| `bs` | float | 0 | -1 to 1 (blue shadows) |
| `rm` | float | 0 | -1 to 1 (red midtones) |
| `gm` | float | 0 | -1 to 1 (green midtones) |
| `bm` | float | 0 | -1 to 1 (blue midtones) |

**Example prompts:**
- "Make the shadows warmer"
- "Add cool blue tones to midtones"
- "Push reds into the shadows"

---

### noise
Add noise/film grain.
| Parameter | Type | Default | Range/Choices |
|-----------|------|---------|---------------|
| `amount` | int | 10 | 0 to 100 |
| `type` | choice | uniform | uniform, gaussian |

**Example prompts:**
- "Add film grain"
- "Give it a gritty texture"
- "Add heavy noise for a raw look"

---

### curves
Apply color curves preset.
| Parameter | Type | Default | Choices |
|-----------|------|---------|---------|
| `preset` | choice | increase_contrast | none, color_negative, cross_process, darker, increase_contrast, lighter, linear_contrast, medium_contrast, negative, strong_contrast, vintage |

**Example prompts:**
- "Apply a vintage color curve"
- "Cross-process the colors"
- "Apply the color negative look"

---

### text_overlay
Add text on the video.
| Parameter | Type | Default | Choices/Range |
|-----------|------|---------|---------------|
| `text` | string | *(required)* | any text |
| `size` | int | 48 | 8 to 200 |
| `color` | string | white | color name or hex |
| `position` | choice | center | center, top, bottom, top_left, top_right, bottom_left, bottom_right |
| `font` | string | Sans | font name or path |
| `border` | bool | true | adds black outline |

**Example prompts:**
- "Add 'Subscribe!' text at the bottom in yellow"
- "Put a title 'My Video' in the center"
- "Add small red text in the top right corner"

---

### invert
Invert all colors (photo negative).
*No parameters.*

**Example prompts:**
- "Invert the colors"
- "Make it a negative"

---

### edge_detect
Apply edge detection.
| Parameter | Type | Default | Choices/Range |
|-----------|------|---------|---------------|
| `mode` | choice | canny | canny, colormix |
| `low` | float | 0.1 | 0.0 to 1.0 |
| `high` | float | 0.4 | 0.0 to 1.0 |

**Example prompts:**
- "Apply edge detection"
- "Show just the outlines"
- "Make it look like a sketch"

---

### pixelate
Pixelate/mosaic effect.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `factor` | int | 10 | 2 to 50 |

**Example prompts:**
- "Pixelate it like an 8-bit game"
- "Apply a mosaic effect"
- "Censor with heavy pixelation"

---

### gamma
Adjust gamma correction.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `value` | float | 1.2 | 0.1 to 4.0 |

**Example prompts:**
- "Brighten the midtones"
- "Adjust gamma for a filmic look"

---

### exposure
Adjust exposure (via gamma).
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `value` | float | 0.5 | -3.0 to 3.0 |

**Example prompts:**
- "Increase exposure by one stop"
- "Darken the exposure slightly"

---

### chromakey
Green screen removal.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `color` | string | 0x00FF00 | hex color |
| `similarity` | float | 0.15 | 0.01 to 0.5 |
| `blend` | float | 0.1 | 0.0 to 1.0 |

**Example prompts:**
- "Remove the green screen"
- "Chroma key out the blue background"

---

### deband
Remove color banding artifacts.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `threshold` | float | 0.02 | 0.0 to 0.1 |

**Example prompts:**
- "Remove the banding in the sky"
- "Fix color banding artifacts"

---

## ⏱️ Temporal (Time)

### trim
Cut a segment from the video.
| Parameter | Type | Default |
|-----------|------|---------|
| `start` | time | — |
| `end` | time | — |
| `duration` | time | — |

**Example prompts:**
- "Trim to the first 30 seconds"
- "Cut from 1:00 to 2:30"
- "Keep only the first 10 seconds"

---

### speed
Change playback speed (video + audio).
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `factor` | float | 2.0 | 0.1 to 10.0 |

**Example prompts:**
- "Speed it up 2x"
- "Make it slow motion (0.5x)"
- "Play at 1.5x speed"

---

### reverse
Reverse video and audio playback.
*No parameters.*

**Example prompts:**
- "Reverse the video"
- "Play it backwards"

---

### loop
Loop the video.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `count` | int | 2 | 1 to 100 |

**Example prompts:**
- "Loop it 3 times"
- "Make it repeat"

---

### fps
Change the frame rate.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `rate` | int | 30 | 1 to 120 |

**Example prompts:**
- "Convert to 24fps for a filmic look"
- "Change to 60fps"

---

## 📐 Spatial (Transform)

### resize
Resize/scale the video.
| Parameter | Type | Default |
|-----------|------|---------|
| `width` | int | 1280 |
| `height` | int | 720 |

**Example prompts:**
- "Resize to 1080p"
- "Scale down to 720p"
- "Make it 4K"

---

### crop
Crop the video.
| Parameter | Type | Default |
|-----------|------|---------|
| `width` | string | iw |
| `height` | string | ih |
| `x` | string | center |
| `y` | string | center |

**Example prompts:**
- "Crop to 16:9"
- "Crop the top and bottom"
- "Center crop to square"

---

### rotate
Rotate the video.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `angle` | int | 90 | any degrees |

**Example prompts:**
- "Rotate 90 degrees clockwise"
- "Rotate 180 degrees"
- "Rotate 45 degrees"

---

### flip
Flip/mirror the video.
| Parameter | Type | Default | Choices |
|-----------|------|---------|---------|
| `direction` | choice | horizontal | horizontal, vertical |

**Example prompts:**
- "Flip horizontally"
- "Mirror the video"
- "Flip upside down"

---

### pad
Add padding/letterbox.
| Parameter | Type | Default |
|-----------|------|---------|
| `width` | string | iw |
| `height` | string | ih |
| `x` | string | center |
| `y` | string | center |
| `color` | string | black |

**Example prompts:**
- "Add black bars for letterbox"
- "Pad with white borders"

---

### aspect
Change aspect ratio.
| Parameter | Type | Default | Choices |
|-----------|------|---------|---------|
| `ratio` | choice | 16:9 | 16:9, 4:3, 1:1, 9:16, 21:9 |

**Example prompts:**
- "Convert to 16:9"
- "Make it square (1:1)"
- "Convert to vertical 9:16"

---

## 🔊 Audio

### volume
Adjust audio volume.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `level` | float | 1.5 | 0.0 to 10.0 |

**Example prompts:**
- "Make it louder"
- "Reduce the volume by half"
- "Boost the audio"

---

### normalize
Normalize audio loudness.
*No parameters.*

**Example prompts:**
- "Normalize the audio"
- "Even out the volume levels"

---

### fade_audio
Fade audio in/out.
| Parameter | Type | Default | Choices/Range |
|-----------|------|---------|---------------|
| `type` | choice | in | in, out |
| `start` | time | 0 | seconds |
| `duration` | time | 1 | seconds |

**Example prompts:**
- "Fade the audio in over 3 seconds"
- "Audio fade out at the end"

---

### remove_audio
Strip all audio.
*No parameters.*

**Example prompts:**
- "Remove the audio"
- "Make it silent"
- "Strip the sound"

---

### extract_audio
Extract audio only.
*No parameters.*

**Example prompts:**
- "Extract just the audio"
- "Save only the sound"

---

### bass / treble
Boost or cut bass/treble frequencies.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `gain` | float | 6 / 4 | -20 to 20 dB |

**Example prompts:**
- "Boost the bass"
- "Add more treble"
- "Cut the low frequencies"

---

### pitch
Adjust audio pitch.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `semitones` | float | 2 | -12 to 12 |

**Example prompts:**
- "Pitch up by 2 semitones"
- "Lower the pitch"
- "Make the voice deeper"

---

### echo
Add echo/reverb.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `delay` | int | 500 | 50 to 5000 ms |
| `decay` | float | 0.5 | 0.1 to 0.9 |

**Example prompts:**
- "Add echo to the audio"
- "Apply reverb"
- "Add a long echo delay"

---

### equalizer
Adjust a specific frequency band.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `freq` | int | 1000 | 20 to 20000 Hz |
| `width` | int | 200 | 10 to 5000 Hz |
| `gain` | float | 5.0 | -20 to 20 dB |

**Example prompts:**
- "Boost bass frequencies around 100Hz"
- "Cut harsh frequencies at 3kHz"

---

### stereo_swap
Swap left and right audio channels.
*No parameters.*

**Example prompts:**
- "Swap the stereo channels"

---

### mono
Convert to mono audio.
*No parameters.*

**Example prompts:**
- "Convert audio to mono"
- "Downmix to single channel"

---

### audio_speed
Change audio speed only (not video).
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `factor` | float | 1.5 | 0.5 to 2.0 |

**Example prompts:**
- "Speed up only the audio"
- "Slow down the audio track"

---

### chorus
Add chorus effect (thickens sound).
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `depth` | float | 0.4 | 0.1 to 1.0 |

**Example prompts:**
- "Add a chorus effect"
- "Make the audio sound richer"

---

### flanger
Add flanger effect (sweeping jet sound).
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `speed` | float | 0.5 | 0.1 to 10.0 Hz |
| `depth` | float | 2.0 | 0.1 to 10.0 |

**Example prompts:**
- "Add a flanger effect"
- "Apply psychedelic audio sweep"

---

### lowpass
Low pass filter (removes highs, muffled sound).
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `freq` | int | 1000 | 100 to 20000 Hz |

**Example prompts:**
- "Muffle the audio"
- "Make it sound like it's behind a wall"
- "Apply a telephone effect"

---

### highpass
High pass filter (removes lows, thin sound).
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `freq` | int | 300 | 20 to 10000 Hz |

**Example prompts:**
- "Remove the bass rumble"
- "Make it sound tinny"

---

### audio_reverse
Reverse the audio track.
*No parameters.*

**Example prompts:**
- "Reverse the audio"
- "Play the sound backwards"

---

### compress_audio
Dynamic range compression.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `threshold` | float | -20 | -60 to 0 dB |
| `ratio` | float | 4 | 1 to 20 |

**Example prompts:**
- "Compress the audio dynamics"
- "Even out loud and quiet parts"

---

## 📦 Encoding

### compress
Compress video file size.
| Parameter | Type | Default | Choices |
|-----------|------|---------|---------|
| `preset` | choice | medium | light, medium, heavy |

**Example prompts:**
- "Compress the video"
- "Reduce file size"
- "Heavy compression for small file"

---

### convert
Convert to a different codec.
| Parameter | Type | Default | Choices |
|-----------|------|---------|---------|
| `codec` | choice | h264 | h264, h265, vp9, av1 |

**Example prompts:**
- "Convert to H.265"
- "Re-encode as VP9"
- "Convert to AV1"

---

### quality
Set video quality via CRF.
| Parameter | Type | Default | Range/Choices |
|-----------|------|---------|---------------|
| `crf` | int | 23 | 0 to 51 |
| `preset` | choice | medium | ultrafast to veryslow |

**Example prompts:**
- "Set quality to high (CRF 18)"
- "Use lossless quality"
- "Encode with slow preset for best quality"

---

### bitrate
Set specific video/audio bitrate.
| Parameter | Type | Default |
|-----------|------|---------|
| `video` | string | — |
| `audio` | string | — |

**Example prompts:**
- "Set video bitrate to 5M"
- "Set audio bitrate to 192k"

---

### web_optimize
Optimize for web streaming (faststart).
*No parameters.*

**Example prompts:**
- "Optimize for web playback"
- "Make it stream-friendly"

---

### container
Change container format.
| Parameter | Type | Default | Choices |
|-----------|------|---------|---------|
| `format` | choice | mp4 | mp4, mkv, avi, mov, webm |

**Example prompts:**
- "Convert to MKV"
- "Save as MOV"

---

### pixel_format
Set pixel format.
| Parameter | Type | Default | Choices |
|-----------|------|---------|---------|
| `format` | choice | yuv420p | yuv420p, yuv422p, yuv444p, rgb24 |

---

### hwaccel
Enable hardware acceleration.
| Parameter | Type | Default | Choices |
|-----------|------|---------|---------|
| `method` | choice | auto | auto, cuda, vaapi, qsv |

---

### audio_codec
Set audio codec.
| Parameter | Type | Default | Choices |
|-----------|------|---------|---------|
| `codec` | choice | aac | aac, mp3, opus, flac, pcm |
| `bitrate` | string | 128k | e.g. 192k, 320k |

---

## 🎬 Cinematic Presets

### cinematic
Hollywood film look with teal-orange grading and vignette.

### blockbuster
Michael Bay style — high contrast, saturated, dramatic.

### documentary
Clean, natural documentary look.

### indie_film
Indie art-house aesthetic — faded, low contrast.

### commercial
Bright, clean, corporate video look.

### dream_sequence
Dreamy, soft, ethereal atmosphere.

### action
Fast-paced action movie grading.

### romantic
Soft, warm romantic mood.

### sci_fi
Cool blue sci-fi atmosphere.

### dark_moody
Dark, atmospheric, moody feel.

---

## 📼 Vintage & Retro

### vintage
Classic old film look with grain and color shift (50s-90s era).

### vhs
VHS tape aesthetic with distortion.

### sepia
Classic sepia/brown tone.

### super8
Super 8mm film look.

### polaroid
Polaroid instant photo aesthetic.

### faded
Washed-out, faded look.

### old_tv
CRT television aesthetic.

### damaged_film
Aged/weathered film with heavy grain.

### noir
Film noir — black and white, high contrast, deep shadows.

---

## 📱 Social Media

### social_vertical
Optimize for TikTok / Reels / Shorts (9:16 vertical).

### social_square
Square 1:1 for Instagram feed.

### youtube
Optimize for YouTube (quality + fast start).

### twitter
Optimize for Twitter/X (max 2:20 length).

### gif
Convert to animated GIF.

### thumbnail
Extract a thumbnail frame.

### caption_space
Add blank space for captions at top/bottom.

### watermark
Overlay a logo/watermark image.

### intro_outro
Add intro and/or outro video segments.

---

## ✨ Creative Effects

### neon
Neon glow aesthetic — real edge-glow using `edgedetect` + high-saturation screen blend.

| Parameter | Type | Default | Choices |
|-----------|------|---------|---------|
| `intensity` | choice | medium | subtle, medium, strong |

### horror
Horror movie atmosphere — dark, desaturated, grainy.

### underwater
Underwater look — blue tint, blur, darker.

### sunset
Golden hour / sunset warm glow.

### cyberpunk
Cyberpunk aesthetic — neon tones, high contrast, sharp.

### comic_book
Comic book / pop art style — real edge outlines + posterized colors using `edgedetect` + `lutrgb` + `blend`.

| Parameter | Type | Default | Choices |
|-----------|------|---------|---------|
| `style` | choice | classic | classic, manga, pop_art |

### miniature
Tilt-shift miniature effect — real selective blur using `gblur` + `blend` expression. Makes scenes look like toy models.

### surveillance
Security camera / CCTV look — desaturated, grainy.

### music_video
Music video aesthetic — punchy colors, contrast, vignette.

### anime
Anime / cel-shaded cartoon style.

### lofi
Lo-fi / chill aesthetic — soft, warm, slightly degraded.

### thermal
Thermal / heat vision camera effect — real pseudocolor heat-map gradient using `pseudocolor` filter.

### posterize
Reduce color palette for a poster/screen-print look.

### emboss
Emboss / relief effect — raised surface look.

---

## 🔮 Enhanced Effects (Advanced Filters)

These effects use powerful FFMPEG filters for results that look genuinely different from basic color adjustments.

### chromatic_aberration
RGB channel offset for color fringing / glitch aesthetic using `rgbashift`.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `amount` | int | 4 | 1 to 20 |

**Example prompts:**
- "Add chromatic aberration"
- "Apply strong RGB split"
- "Add color fringing like a cheap lens"

---

### sketch
Pencil drawing / ink line art using `edgedetect` filter.
| Parameter | Type | Default | Choices |
|-----------|------|---------|---------|
| `mode` | choice | pencil | pencil, ink, color |

**Example prompts:**
- "Turn it into a pencil sketch"
- "Apply ink outline effect"
- "Show colored edges only"

---

### glow
Bloom / soft glow using `split` → `gblur` → `blend` (screen mode). Uses filter_complex.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `radius` | float | 30 | 5 to 60 |
| `strength` | float | 0.4 | 0.1 to 0.8 |

**Example prompts:**
- "Add a soft bloom glow"
- "Make it glow like a dream"
- "Apply subtle halo light effect"

---

### ghost_trail
Temporal trailing / afterimage using `lagfun` filter. Great for motion-heavy footage.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `decay` | float | 0.97 | 0.9 to 0.995 |

**Example prompts:**
- "Add ghostly motion trails"
- "Apply afterimage echo effect"
- "Make moving objects leave trails"

---

### color_channel_swap
Dramatic color remapping by swapping/mixing color channels using `colorchannelmixer`.
| Parameter | Type | Default | Choices |
|-----------|------|---------|---------|
| `preset` | choice | swap_rb | swap_rb, swap_rg, swap_gb, nightvision, matrix |

**Example prompts:**
- "Swap the red and blue channels for a surreal look"
- "Apply matrix green effect"
- "Make it look like night vision"

---

### tilt_shift
Real tilt-shift miniature with selective blur using `gblur` + `blend` expression.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `focus_position` | float | 0.5 | 0.1 to 0.9 |
| `blur_amount` | float | 8 | 2 to 20 |

**Example prompts:**
- "Apply tilt-shift to make it look like a toy"
- "Add selective blur with focus on the top third"
- "Make the scene look miniature"

---

### frame_blend
Temporal frame blending for dreamy motion blur using `tmix` filter.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `frames` | int | 5 | 2 to 10 |

**Example prompts:**
- "Blend frames for motion blur"
- "Apply long-exposure look"
- "Make it dreamy with frame blending"

---

### false_color
Pseudocolor / false-color mapping (heat map, rainbow, etc.) using `pseudocolor` filter.
| Parameter | Type | Default | Choices |
|-----------|------|---------|---------|
| `palette` | choice | heat | heat, rainbow, blues, electric |

**Example prompts:**
- "Apply heat map false color"
- "Make it look like a thermal scanner"
- "Apply rainbow pseudocolor"

---

### halftone
Newspaper/screen-print halftone dot pattern using `geq` filter.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `dot_size` | float | 0.3 | 0.1 to 1.0 |

**Example prompts:**
- "Apply halftone newspaper dots"
- "Make it look like a print"
- "Apply Ben Day dot pattern"

---

## 🧪 Special Effects (Outcome)

### meme
Deep-fried meme aesthetic — over-saturated, over-sharpened, noisy.

### glitch
Digital glitch / databend effect.

### mirror
Mirror/kaleidoscope effect (horizontal, vertical, or quad).

### slow_zoom
Slow push-in zoom effect.

### black_and_white
Convert to B&W with style options (classic, high contrast, sepia).

### day_for_night
Simulate night-time from daytime footage.

### dreamy
Soft, ethereal, dreamy look.

### hdr_look
Simulated HDR dynamic range.

---

## 🎵 Audio Visualization

### waveform
Visualize audio as a waveform overlay on the video (uses filter_complex with `showwaves`).
| Parameter | Type | Default | Choices/Range |
|-----------|------|---------|---------------|
| `mode` | choice | cline | line, point, p2p, cline |
| `height` | int | 200 | 50 to 600 px |
| `color` | string | white | color name or hex |
| `position` | choice | bottom | bottom, center, top |
| `opacity` | float | 0.8 | 0.0 to 1.0 |

**Example prompts:**
- "Show audio waveform at the bottom"
- "Add a cyan waveform in the center"
- "Display a tall semi-transparent audio visualization"

---

## 🖼️ Multi-Input (Images → Video)

> [!NOTE]
> These skills use multiple input images from `extra_images`, `image_a`, and/or `image_b`.
> **Standalone mode**: Slideshow and grid work without a main video — just connect extra images.
> When a video IS connected, it's automatically included as the first cell/slide.

### grid
Arrange video + images in a grid layout (uses `xstack` filter). Auto-includes the main video as the first cell.
| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `columns` | int | 2 | 1 to 6 |
| `gap` | int | 4 | 0 to 20 px |
| `duration` | float | 5.0 | 1 to 60 seconds |
| `background` | string | black | color name or hex |
| `include_video` | bool | true | include main video as first cell |
| `cell_width` | int | 640 | cell width in pixels |
| `cell_height` | int | 480 | cell height in pixels |

**Example prompts:**
- "Arrange images in a 2-column grid"
- "Create a side-by-side comparison"
- "Make a 3-column mosaic with gaps"
- "Make a collage on a white background"

---

### slideshow
Create a slideshow from images with fade transitions. Optionally starts with the main video.
| Parameter | Type | Default | Choices/Range |
|-----------|------|---------|---------------|
| `duration_per_image` | float | 3.0 | 0.5 to 30 seconds |
| `transition` | choice | fade | none, fade |
| `transition_duration` | float | 0.5 | 0.1 to 3.0 seconds |
| `width` | int | 1920 | -1 to 3840 |
| `height` | int | 1080 | -1 to 2160 |
| `include_video` | bool | false | include main video as first segment |

**Example prompts:**
- "Create a slideshow with fade transitions"
- "Create a slideshow starting with the video"
- "Make a photo slideshow, 5 seconds per image"
- "Create a presentation with 1-second transitions"

---

### overlay_image
Overlay images on the video (picture-in-picture / watermark). Supports multiple overlays — each auto-placed at a different corner.
| Parameter | Type | Default | Choices/Range |
|-----------|------|---------|---------------|
| `position` | choice | bottom-right | top-left, top-right, bottom-left, bottom-right, center |
| `scale` | float | 0.25 | 0.05 to 0.8 |
| `opacity` | float | 1.0 | 0.0 to 1.0 |
| `margin` | int | 10 | 0 to 100 px |

**Example prompts:**
- "Add a logo watermark in the bottom-right"
- "Overlay an image at 15% in the top-left"
- "Put a semi-transparent image in the center"
- "Overlay images in the corners at 20% scale" *(multi-overlay — connect image_a + image_b)*

---

## 💡 Example Prompt Combos

Here are some multi-skill prompt ideas you can try:

| Goal | Prompt |
|------|--------|
| Cinematic short | "Make it cinematic with a fade in and vignette" |
| Retro music video | "Apply VHS effect, slow it down to 0.75x, add echo" |
| Horror trailer | "Horror style, reverse the video, add fade out" |
| Social media clip | "Trim to first 15 seconds, make it vertical for TikTok, add text 'Follow me!' at the bottom" |
| Artistic | "Apply edge detection with colorful mode, boost saturation" |
| Professional | "Normalize audio, compress for web, resize to 1080p" |
| Lo-fi chill | "Lofi style, slow down to 0.8x, muffle the audio" |
| Anime style | "Anime look, add text 'Episode 1' at the top" |
| Underwater scene | "Make it look like underwater footage with echo on the audio" |
| Night scene | "Day for night effect, add vignette, reduce noise" |
| 8-bit retro | "Pixelate it, posterize with 3 levels, speed up 1.5x" |
| Neon cyberpunk | "Cyberpunk style with strong sharpening and neon glow" |
| Security cam | "Surveillance look, add text 'CAM 01' in top left, resize to 720p" |
| Film noir | "Noir style, add fade in, slow zoom" |
| Dreamy timelapse | "Speed up 4x, apply dreamy effect, add fade in and out" |
| Music visualizer | "Show audio waveform at the bottom with cyan color" |
| Photo collage | "Arrange these images in a 3-column grid with gaps" |
| Side by side | "Create a side-by-side comparison" |
| Photo slideshow | "Create a slideshow with 4 seconds per image and fade transitions" |
| Video + slides | "Create a slideshow starting with the video" |
| Branded video | "Overlay the logo image in the bottom-right corner at 20% scale" |
| Multi-watermark | "Overlay images in the corners at 15% scale" |
| Ghost music video | "Ghost trail effect, slow motion, chromatic aberration" |
| Sketch art | "Pencil sketch with glow overlay" |
| Retro print | "Halftone dots, sepia tone, add film grain" |
| Dreamy bloom | "Glow effect with frame blending and slow zoom" |
| Glitch art | "Chromatic aberration, color channel swap, pixelate" |
| Night ops | "Night vision color swap, add noise, surveillance text" |
| Thermal cam | "False color heat map with timestamp text" |
| Miniature city | "Tilt-shift with high saturation and timelapse" |

