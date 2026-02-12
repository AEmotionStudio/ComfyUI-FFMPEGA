# FFMPEGA Advanced Test Prompts

Real-world video editing scenarios to test FFMPEGA as a practical video editor replacement.
Each prompt chains multiple skills together — paste directly into the node.

---

## 🎬 YouTube / Content Creator Workflows

### Polished Upload
```
Trim the first 3 seconds, resize to 1920x1080, normalize the audio loudness, add a fade in from black for 1 second, and compress for web streaming
```

### Thumbnail + Preview
```
Extract a thumbnail at the 5 second mark, resize to 1280x720
```

### Vertical Clip for Shorts
```
Trim from 10 to 25 seconds, make it vertical 9:16 for TikTok, speed up slightly to 1.2x, add text "Watch the full video!" at the bottom
```

### Picture-in-Picture Facecam
```
Overlay the connected image as a small picture-in-picture in the bottom right corner at 25% scale with a slight border
```

### Intro Sequence
```
Fade in from black over 2 seconds, add text "Episode 12" centered in a large font, then fade the text out after 3 seconds, add a vignette
```

---

## 🎞️ Professional Color Grading

### Cinematic Grade
```
Apply cinematic color grading, add letterbox bars for 2.39:1 aspect ratio, boost contrast to 1.3, add subtle vignette, reduce saturation slightly to 0.85
```

### Day-for-Night Conversion
```
Convert this daytime footage to look like nighttime, lower brightness to -0.3, shift hue toward blue, add a vignette, reduce noise
```

### Documentary Look
```
Apply documentary style, denoise with medium strength, normalize audio, set quality to high with CRF 18
```

### Match Multiple Clips
```
Color match via histogram equalization, normalize loudness to broadcast standard, resize to 1080p, compress with CRF 20
```

### Golden Hour Warmth
```
Apply sunset golden hour look, slightly boost saturation to 1.2, add a slow Ken Burns zoom, fade in for 1.5 seconds
```

---

## ✂️ Real Editing Tasks

### Remove Dead Air
```
Remove all silent pauses from this podcast recording and normalize the audio
```

### Jump Cut Style
```
Auto jump-cut to high-energy moments, speed up 1.1x, add a slight shake effect
```

### Clean Up AI-Generated Video
```
Denoise with strong strength, deband with threshold 0.3, sharpen lightly, set quality to high
```

### Stabilize Shaky Footage
```
Stabilize the video, crop slightly to remove black edges, sharpen with strength 1.2, normalize audio
```

### Trim and Export Segment
```
Trim from 1:30 to 2:45, convert to h265, set CRF to 20 with slow preset, optimize for web
```

---

## 📱 Social Media & Delivery

### Instagram Reel
```
Make it square 1:1, trim to first 30 seconds, add text "Link in bio" at the bottom, boost saturation to 1.3, compress for web
```

### Twitter/X Post
```
Optimize for Twitter, trim to 15 seconds, resize to 720p, add a watermark in the bottom right, compress to reduce file size
```

### YouTube Upload
```
Optimize for YouTube, normalize loudness, set quality to high with CRF 18, convert to h264, add web optimization
```

### Animated GIF Preview
```
Trim to the first 4 seconds, resize to 480 wide, speed up 1.5x, convert to GIF
```

### Multi-Platform Export
```
Resize to 1080p, normalize audio, compress with CRF 22, optimize for web streaming, set pixel format to yuv420p
```

---

## 🔗 Multi-Input Compositions

### Side-by-Side Comparison
```
Create a side-by-side split screen with both videos, add text "Before" on the left and "After" on the right
```

### Concat with Transitions
```
Concatenate both videos with a cross dissolve transition lasting 1.5 seconds
```

### Photo Slideshow
```
Create a slideshow from these images with 3 seconds per image and fade transitions between them, add background music from the audio input
```

### Grid Collage
```
Arrange all connected images in a 2-column grid with small gaps between them
```

### Logo Watermark on All Clips
```
Concatenate all video segments, overlay the logo in the bottom right at 15% scale, normalize audio, compress for web
```

---

## 🎵 Audio-Focused Workflows

### Podcast Cleanup
```
Remove background noise, normalize loudness to broadcast standard, compress the audio dynamics, convert to mono, set audio bitrate to 128k
```

### Music Video Look
```
Apply music video style with punchy colors, sync cuts to the beat every 4 seconds, add a vignette, boost bass
```

### Replace Audio Track
```
Replace the video's audio with the connected audio input, normalize loudness, add a 0.5 second audio fade in and fade out
```

### Voice Recording Cleanup
```
Remove reverb, reduce background noise, normalize loudness, compress dynamics, boost treble slightly
```

### Audio Visualization
```
Show the audio waveform at the bottom of the video in cyan color with line mode, add a slight vignette
```

---

## 🎨 Creative & Stylistic

### VHS Nostalgia
```
Apply VHS effect, add film grain, slow down to 0.9x, overlay text "REC" in the top left in red, add audio echo
```

### Cyberpunk Edit
```
Apply cyberpunk style, add neon glow, radial blur at low strength, speed up 1.3x, add text "SYSTEM ONLINE" at the top in cyan
```

### Horror Atmosphere
```
Apply horror style, darken with brightness -0.2, add film grain, reverse the audio, slow down to 0.7x, add a fade out to black
```

### Retro 8-Bit Game
```
Pixelate with block size 8, posterize with 4 levels, speed up 1.5x, boost saturation to 2.0, loop 3 times
```

### Film Noir
```
Convert to black and white, increase contrast to 1.5, add strong vignette, add film grain, apply noir style
```

### Dreamy Timelapse
```
Speed up 8x, apply dreamy effect, add a slow zoom, fade in from white, fade out to black
```

---

## 🧪 Edge Cases & Stress Tests

### Maximum Chain
```
Trim first 5 seconds, resize to 720p, speed up 2x, apply cinematic style, add vignette, normalize audio, add text "Test" at the bottom, compress for web, convert to h265, set CRF 22
```

### Conflicting Effects
```
Apply both VHS and cinematic style, speed up 2x but also add slow motion
```

### Extreme Speed
```
Speed up 10x, reverse, loop 5 times, convert to GIF
```

### All Audio Effects
```
Normalize loudness, add echo, boost bass, add treble, compress audio dynamics, convert to mono
```

### Format Conversion Pipeline
```
Convert to h265, set CRF 18 with slow preset, optimize for web, change container to mkv, set pixel format to yuv420p, set audio codec to opus
```

### Minimal Input
```
Make it better
```

### Ambiguous Creative Direction
```
Make this look more professional and engaging for social media
```

---

## 🎬 Production Workflows

### Rough Cut Assembly
```
Concatenate all connected video segments together, add 1 second cross dissolve transitions between each, normalize audio across all clips
```

### Lower Third Graphics
```
Add a lower third with name "Sarah Johnson" and title "Lead Designer", have it appear 2 seconds in with a fade
```

### Countdown Intro
```
Add a 5 second countdown timer, then fade to the main video, add text "Starting Soon" below the countdown
```

### Privacy Blur
```
Blur the center region of the video for privacy, add text "Content Redacted" over the blurred area
```

### Broadcast Ready
```
Resize to 1920x1080, set frame rate to 29.97fps, normalize loudness to -23 LUFS, set quality to high, convert to h264, optimize for web
```

### Archive / Preservation
```
Convert to lossless quality, preserve original resolution, extract audio as separate track
```
