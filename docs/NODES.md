# 🎛️ Nodes

*Part of the [ComfyUI-FFMPEGA](../README.md) documentation.*

FFMPEGA provides **14 nodes** that work together:

> [!TIP]
> **One task per run.** Instead of cramming multiple edits into a single prompt, focus each run on one editing task — then feed the output back into FFMPEGA for the next. This keeps context low and model focus high, leading to significantly better results. Chain FFMPEGA Agent → Save Video → Load Video Path → FFMPEGA Agent for multi-step workflows.

> [!WARNING]
> **Low VRAM?** Skills that load AI models (SAM3 masking, Whisper transcription, LaMa inpainting) each consume significant VRAM. On GPUs with limited memory, limit each run to **one model-loading task** — e.g. do your SAM3 removal pass first, save the result, then run Whisper subtitles as a separate pass.

<details>
<summary><b>FFMPEG Agent</b> — The main node. Translates natural language into FFMPEG commands.</summary>

<details>
<summary>Required Inputs</summary>

| Input | Type | Description |
| :--- | :--- | :--- |
| `video_path` | STRING | Absolute path to source video. Used as ffmpeg input unless `images_a` is connected. |
| `prompt` | STRING | Natural language editing instruction (e.g. *"Add cinematic letterbox"*, *"Speed up 2x"*). Not required in `manual` mode. |
| `llm_model` | DROPDOWN | AI model selection — local Ollama models or CLI tools. Select `none` for no-LLM mode. |
| `no_llm_mode` | DROPDOWN | Mode when `llm_model` is `none` — **31 modes**: `manual` (Effects Builder, default), `sam3_masking`, `transcribe`, `karaoke_subtitles`, `generate_audio`, `generate_music`, `foundation1`, `fish_speech`, `audio_inpaint`, `audio_separate`, `ace_step`, `lip_sync`, `animate_portrait`, `marigold`, `normalcrafter`, `video_depth`, `sapiens2`, `flux_klein`, `kiwi_edit`, `minimax_remover`, `dreamid_omni`, `svi`, `sharp`, `wan_animate`, `scail2`, `ai_upscale`, `rembg`, `video_matting`, `onion_skin`, `comparison`, `phyfps`. |
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
| `video_a` | STRING | File path to extra video for concat, split screen, grid, xfade. Zero memory. Auto-expands: `video_b`, `video_c`... |
| `image_path_a` | STRING | File path to image for overlay, grid, slideshow. Zero memory. Auto-expands: `image_path_b`... |
| `text_a` | STRING | Text input from FFMPEGA Text node for subtitles, overlays, watermarks. Auto-expands: `text_b`... |
| `pipeline_json` | STRING | Connect from FFMPEGA Effects Builder. In `manual` mode the pipeline is executed directly; with an LLM it provides skill hints. |
| `subtitle_path` | STRING | Direct path to a `.srt` or `.ass` subtitle file. |
| `advanced_options` | BOOLEAN | Simple/Advanced toggle — shows preview mode, CRF, encoding preset, batch processing when enabled. |
| `preview_mode` | BOOLEAN | Quick low-res preview (480p, 10s) instead of full render. |
| `save_output` | BOOLEAN | Save video + workflow PNG to output folder. |
| `output_path` | STRING | Custom output file/folder path. Empty = ComfyUI default. |
| `ollama_url` | STRING | Ollama server URL (default: `http://localhost:11434`). |
| `custom_model` | STRING | Exact Ollama model name when `llm_model` is set to `custom`. |
| `crf` | INT | Override CRF (0 = lossless, 23 = default, 51 = worst). -1 uses `quality_preset`. |
| `encoding_preset` | DROPDOWN | Override x264/x265 speed preset (`ultrafast` → `veryslow`). `auto` follows `quality_preset`. |
| `use_vision` | BOOLEAN | Embed video frames as images for vision-capable LLMs. Off = numeric color analysis only. |
| `verify_output` | BOOLEAN | Agent inspects output after rendering and auto-corrects if it doesn't match intent. |

</details>

<details>
<summary>Whisper / SAM3 Inputs</summary>

| Input | Type | Description |
| :--- | :--- | :--- |
| `whisper_device` | DROPDOWN | Device for Whisper model: `cpu` (default, avoids VRAM pressure) or `gpu` (faster, ~3 GB VRAM). |
| `whisper_model` | DROPDOWN | Whisper model size: `large-v3` (default, most accurate), `medium`, `small`, `base`, `tiny`. |
| `sam_version` | DROPDOWN | SAM model: `sam3.1` (default, multiplex tracker — video masking runs in-process on ComfyUI's native model) or `sam3`. |
| `sam3_max_objects` | INT | Max objects SAM3 tracks per frame (1–20, default 5). Lower = less VRAM. |
| `sam3_det_threshold` | FLOAT | Minimum detection confidence for SAM3 (0.0–1.0, default 0.70). Higher = fewer objects. |
| `mask_output_type` | DROPDOWN | `black_white` (raw mask for compositing) or `colored_overlay` (SAM3-style preview). |
| `mask_points` | STRING | JSON point selection data from Load Video Path's Point Selector. Guides SAM3 with click-to-select. |

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
<summary><b>FFMPEGA Effects Builder</b> — Compose video effects visually without an LLM.</summary>

Select up to 5 skills with parameters, add raw FFmpeg filters, and use presets. Outputs a pipeline JSON that connects to the FFMPEG Agent's `pipeline_json` input.

**26 built-in presets:** 🎬 Cinematic Look, 📼 Vintage / Retro, 🔍 Privacy Blur (face), ⚡ Speed Ramp (2x), 🖤 B&W + Vignette, 📱 Social (9:16 + Quality), 🎵 Clean Audio, ✨ Glow + Saturation, 🎙️ Auto Subtitles, 🎤 Karaoke Subtitles, 🔗 Concat Videos, 🔗 Concat + Crossfade, 📺 Split Screen, 🖼️ Grid Layout, 🎞️ Slideshow, 🐢 Slow Motion (0.5x), ✂️ Trim (first 10s), 🌑 Fade In + Out, 🪞 Mirror Horizontal, 🎬 Ken Burns Zoom, 🎭 Remove Background, 🔍 AI Upscale (2x), 📹 Stabilize + Denoise, 🎬 Cinematic B&W, 📱 TikTok Ready, 🐢 Slow Motion + Fades.

| Input | Type | Description |
| :--- | :--- | :--- |
| `preset` | DROPDOWN | Quick-start preset. Auto-fills effect slots and params. Set to `none` to build your own. |
| `effect_1` | DROPDOWN | First effect. Categorized by type (🎨 Visual, ⏱️ Temporal, 📐 Spatial, 🔊 Audio, 📦 Encoding, ✨ Outcome). |
| `effect_1_params` | STRING | JSON parameters for effect 1 (e.g. `{"strength": 5}`). Auto-filled from defaults. |
| `effect_2` | DROPDOWN | Second effect (chained after effect 1). |
| `effect_2_params` | STRING | JSON parameters for effect 2. |
| `effect_3` | DROPDOWN | Third effect (chained after effect 2). |
| `effect_3_params` | STRING | JSON parameters for effect 3. |
| `effect_4` | DROPDOWN | Fourth effect (chained after effect 3). |
| `effect_4_params` | STRING | JSON parameters for effect 4. |
| `effect_5` | DROPDOWN | Fifth effect (chained after effect 4). |
| `effect_5_params` | STRING | JSON parameters for effect 5. |
| `raw_ffmpeg` | STRING | Raw FFmpeg `-vf` filter string applied after skill effects. |
| `sam3_target` | STRING | SAM3 text target — apply effects only to the masked region. Leave empty for full-frame. |
| `sam3_effect` | DROPDOWN | Effect for SAM3-detected region: `blur`, `pixelate`, `remove`, `grayscale`, `highlight`. |
| `sam_version` | DROPDOWN | SAM model for the target region: `sam3.1` (default) or `sam3`. |

| Output | Description |
| :--- | :--- |
| `pipeline_json` | JSON pipeline — connect to FFMPEG Agent's `pipeline_json` input |

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

Takes a video path (from FFMPEGA Agent or Load Video Path), copies the file to ComfyUI's output directory, and shows a preview. By default there is no re-encoding — just a file copy. Also encodes a connected IMAGE batch, and combines several sources into one comparison clip.

| Input | Type | Description |
| :--- | :--- | :--- |
| `video_path` | STRING | Path to video file (typically from FFMPEGA Agent's output). |
| `filename_prefix` | STRING | Prefix for saved filename. Supports `%date:yyyy-MM-dd%`. |
| `overwrite` | BOOLEAN | *(optional)* Overwrite existing file vs auto-increment counter. |

**Advanced output options** — all collapsed behind a single `show_advanced` toggle (off by default), so the node stays as small as it always was until you need them. All optional, so existing workflows keep the old behaviour.

| Input | Type | Description |
| :--- | :--- | :--- |
| `show_advanced` | BOOLEAN | Reveal the encoding controls below. Purely a display toggle — collapsing it never resets or ignores a value you have set. |
| `output_format` | DROPDOWN | `source (no re-encode)` (default), `h264-mp4`, `h265-mp4`, `vp9-webm`, `av1-webm`, `prores-mov`, `ffv1-mkv`, `gif`, `webp`. |
| `color_policy` | DROPDOWN | `sRGB (recommended)`, `BT.709 broadcast`, `ComfyUI native match`, `full range (pc)`. See below. |
| `crf` | INT | Quality, 0–63. Lower is better and larger. Ignored by ProRes and FFV1. |
| `encode_preset` | DROPDOWN | `ultrafast`…`veryslow`. H.264/H.265 only. |
| `bit_depth` | DROPDOWN | `8` or `10`. 10-bit greatly reduces banding on gradients. |
| `audio_codec` | DROPDOWN | `auto`, `aac`, `libopus`, `flac`, `pcm_s16le`, `copy`, `none`. |
| `audio_bitrate` | DROPDOWN | `96k`–`320k`. Ignored by lossless codecs. |
| `faststart` | BOOLEAN | Move the MP4 index to the front so it streams before fully downloading. |
| `loop_count` | INT | Extra repeats of the clip. |
| `pingpong` | BOOLEAN | Play forwards then backwards. Image input only. |
| `trim_to_audio` | BOOLEAN | End the video when the audio ends, instead of padding audio with silence. |
| `embed_workflow` | BOOLEAN | Write the workflow into the video file itself, so dragging it onto the canvas restores it. |
| `frame_output` | DROPDOWN | `preview (64)`, `all`, `none` — how many frames the `images` output carries. |

Visibility works on two levels: `show_advanced` reveals the section, and within it any widget the selected format cannot use collapses automatically (VP9 and AV1 take a deadline rather than an x264 preset, ProRes and FFV1 have fixed quality, GIF and WebP carry no audio).

**Copy, remux or re-encode.** With `output_format` on its default the node still does a plain file copy with no ffmpeg call. If only the container differs — or the source already holds exactly the codec the chosen format produces — the file is stream-copied, which is lossless and near-instant. A full re-encode happens only when the codec genuinely has to change.

**About `color_policy`.** ComfyUI IMAGE tensors are sRGB, but video wants YUV, and the choice of conversion matrix visibly changes the result. Measured on FFmpeg 8 with a pure-green frame:

| Policy | Matrix | Tags written | Notes |
| :--- | :--- | :--- | :--- |
| `sRGB (recommended)` | BT.709 (Y=172) | `tv`, `bt709`, `iec61966-2-1`, `bt709` | Honest about what the tensors are. Colour-managed players match the ComfyUI preview. |
| `BT.709 broadcast` | BT.709 (Y=172) | `tv`, `bt709`, `bt709`, `bt709` | Same pixels, transfer tagged as BT.709. What VideoHelperSuite intends. |
| `ComfyUI native match` | BT.601 (Y=144) | none | Byte-identical to `Create Video` → `Save Video`. |
| `full range (pc)` | BT.709, full range | `pc`, `bt709`, `iec61966-2-1`, `bt709` | Archival. |

If your saved videos have ever looked different from the ComfyUI preview, this is the knob. Note that ComfyUI's native path is not simply "untagged" — swscale falls back to the **BT.601** matrix there, so its pixel data genuinely differs from a BT.709 encode. The policy applies when encoding images; a copied video keeps whatever colour it already had.

**The preview outlives the session.** Switching workflow tabs, reloading the page or restarting the server brings the player and its info bar straight back — no re-running the graph to see what you already rendered. Tab switches restore from ComfyUI's own record of the last execution (the same mechanism that keeps the native preview nodes populated); reloads and restarts restore from a descriptor kept in the workflow itself. If the file has since been deleted, or it was a `save_output = false` preview and ComfyUI cleared its temp directory on boot, the player simply collapses and the node returns to its no-preview size.

</details>

<details>
<summary><b>Text Input (FFMPEGA)</b> — Flexible text input for subtitles, overlays, and watermarks.</summary>

Auto-detects whether text is SRT subtitles, a short watermark, or overlay text. Outputs JSON-encoded metadata that the FFMPEGA Agent node parses for `burn_subtitles`, `text_overlay`, or `watermark` skills.

**Right-click Presets**: 10 built-in presets with example text (SRT Subtitle Example, Cinematic Subtitles, Bold Watermark, Title Card, Social Caption, Meme Text, Lower Third, Copyright Notice, Credits Roll, Chapter Marker). Save/load/delete custom presets. "Clear Text" resets all fields to defaults.

**No-LLM Text Mode**: Connect a Text node to the Agent's `text_a` input in no-LLM manual mode (without an Effects Builder). The Agent auto-generates a text overlay or subtitle pipeline from the Text node's mode, position, font size, and color settings.

| Input | Type | Description |
| :--- | :--- | :--- |
| `text` | STRING | Text content — plain text, multi-line subtitles, or full SRT format with timestamps. |
| `auto_mode` | BOOLEAN | *(optional)* Auto-detect mode from content (default: on). |
| `mode` | DROPDOWN | *(optional)* Override mode: `subtitle`, `overlay`, `watermark`, `title_card`, `raw`. |
| `position` | DROPDOWN | *(optional)* Text placement: `center`, `top`, `bottom`, `bottom_right`, etc. `auto` = mode default. |
| `font_size` | INT | *(optional)* Font size in px (0 = auto: 24 subtitle, 48 overlay, 20 watermark). |
| `font_color` | STRING | *(optional)* Text color as hex (#RRGGBB, default: white). |
| `start_time` | FLOAT | *(optional)* Start time in seconds (default: 0). |
| `end_time` | FLOAT | *(optional)* End time in seconds (-1 = full duration). |

| Output | Description |
| :--- | :--- |
| `text_output` | JSON-encoded text with metadata — connect to `text_a`, `text_b`, etc. on the FFMPEGA Agent node |

</details>

<details>
<summary><b>Media Bridge (FFMPEGA)</b> — Bidirectional IMAGE ↔ video-path converter.</summary>

Switch between tensor-based and path-based video representations. In `images_to_path` mode, encodes an IMAGE tensor to a temp video file and releases the tensor. In `path_to_images` mode, decodes a video file path into IMAGE tensor + audio.

| Input | Type | Description |
| :--- | :--- | :--- |
| `mode` | DROPDOWN | Conversion direction: `images_to_path` or `path_to_images`. |
| `images` | IMAGE | *(optional)* Video frames — required for `images_to_path` mode. |
| `video_path` | STRING | *(optional)* Path to video file — required for `path_to_images` mode. |
| `fps` | INT | *(optional)* FPS for encoding (default: 24). Used in `images_to_path` only. |
| `audio` | AUDIO | *(optional)* Audio to mux into encoded video (`images_to_path` only). |

| Output | Description |
| :--- | :--- |
| `video_path` | File path to the temp video (`images_to_path`) or empty string |
| `images` | Decoded video frames (`path_to_images`) or empty tensor |
| `audio` | Extracted audio (`path_to_images`) or silent fallback |
| `fps` | Frames per second — always populated |
| `frame_count` | Total frame count — always populated |

</details>

<details>
<summary><b>Video Editor (FFMPEGA)</b> — Interactive NLE video editor with timeline, crop, transitions, and more.</summary>

A full-featured non-linear editor built into ComfyUI. Open the editor modal from any Video Editor node to trim, split, crop, adjust speed/volume, add text overlays, and apply transitions — all rendered through FFmpeg on export. No LLM required.

**Editing Tools:** Select, Razor (split), Delete, Crop, Speed, Volume, Text Overlay, Transitions.

**Keyboard Shortcuts:** Space (play/pause), J/K/L (shuttle), I/O (in/out), R (razor), V (select), Left/Right (frame step), `?` (shortcut overlay).

| Input | Type | Description |
| :--- | :--- | :--- |
| `video_path` | STRING | Path to source video, or connect from upstream. |
| `images` | IMAGE | *(optional)* Video frames from upstream — auto-converted to a temp video for editing. |

| Output | Description |
| :--- | :--- |
| `images` | All frames from the edited output video |
| `audio` | Audio extracted from the edited output |
| `video_path` | Path to the rendered output video |

> **Passthrough mode:** When no edits are made, the node passes the input video through unchanged — zero re-encoding overhead.

</details>

<details>
<summary><b>Load Last Image (FFMPEGA)</b> — Auto-discover and load the most recently generated image(s).</summary>

Scans ComfyUI's output/temp directories for the newest image by mtime. Supports batch loading, deduplication, grid/side-by-side outputs, diff overlays, captions, ring buffer mode for AnimateDiff, and PNG metadata passthrough.

| Input | Type | Description |
| :--- | :--- | :--- |
| `refresh_mode` | DROPDOWN | `auto` (reload every queue) or `manual` (only on trigger). |
| `batch_size` | INT | Number of recent images to load as a batch (default: 1). |
| `grid_columns` | INT | Columns in grid output layout (default: 2). |
| `grid_padding` | INT | Pixel gap between grid cells (default: 4). |
| `skip_duplicates` | BOOLEAN | Skip consecutive identical images (default: on). |
| `pin_index` | INT | Pin a specific iteration as output. 0 = disabled. |
| `diff_mode` | DROPDOWN | Diff visualization: `heatmap`, `overlay`, `side_by_side_diff`. |
| `diff_sensitivity` | FLOAT | Diff brightness multiplier (0.1–5.0, default: 1.0). |
| `show_captions` | BOOLEAN | Burn caption text onto grid/side-by-side outputs. |
| `caption_format` | STRING | Caption template with tokens: `{iteration}`, `{timestamp}`, `{seed}`, `{index}`, `{filename}`. |
| `ring_buffer_size` | INT | Fixed-size circular batch for AnimateDiff. 0 = disabled. |
| `source_folder` | STRING | *(optional)* Custom folder to scan. Empty = defaults. |
| `filename_filter` | STRING | *(optional)* Prefix filter (e.g. `ComfyUI_`). |

| Output | Description |
| :--- | :--- |
| `IMAGE` | Batched image tensor of recent images |
| `MASK` | Solid white mask |
| `GRID_IMAGE` | All batch images composed in a grid |
| `SIDE_BY_SIDE` | Most recent vs previous image |
| `DIFF_IMAGE` | Diff visualization between latest and previous |
| `width` / `height` | Image dimensions |
| `batch_count` | Number of images loaded |
| `iteration` | Execution counter |
| `metadata_prompt` / `metadata_seed` / `metadata_workflow` | PNG metadata from the most recent image |
| `RING_BUFFER_FULL` | Boolean — true when ring buffer is at capacity |

</details>

<details>
<summary><b>Load Last Video (FFMPEGA)</b> — Auto-discover and load the most recently saved video with inline preview.</summary>

Scans ComfyUI's output/temp directories for the newest video. Decodes frames (with configurable cap), extracts audio, and shows an inline preview that loads immediately without queuing. Supports manual frame selection, auto-select strategies, inline edits (trim/crop/speed), and input overrides.

| Input | Type | Description |
| :--- | :--- | :--- |
| `refresh_mode` | DROPDOWN | `auto` (reload when latest video changes) or `manual`. |
| `source_folder` | STRING | *(optional)* Custom folder to scan. Empty = defaults. |
| `filename_filter` | STRING | *(optional)* Prefix filter for filenames. |
| `max_frames` | INT | *(optional)* Max frames to decode into IMAGE tensor (0 = all). Caps memory. |
| `images` | IMAGE | *(optional)* Override: provide frames directly instead of auto-discovery. |
| `audio` | AUDIO | *(optional)* Override: provide audio directly. |
| `video_path` | STRING | *(optional)* Override: path to a specific video file. |
| `frame_select_mode` | DROPDOWN | Frame selection strategy: `manual`, `uniform_5`, `uniform_10`, `first_last`, `last`, `every_2nd`, `every_5th`, `timestamps`. |
| `auto_timestamps` | STRING | *(optional)* Comma-separated timestamps for `timestamps` mode. |
| `pause_for_selection` | BOOLEAN | *(optional)* Block execution until frames are selected (manual mode). |

| Output | Description |
| :--- | :--- |
| `IMAGE` | All decoded video frames as a batched tensor |
| `SELECTED_FRAMES` | Frames at selected/auto-selected timestamps |
| `AUDIO` | Extracted audio from the video |
| `video_path` | Absolute path to the loaded video |
| `image_paths` | Comma-separated paths to selected frame PNGs |
| `frame_count` | Total frame count |
| `fps` | Video frame rate |
| `duration` | Video duration in seconds |

</details>

<details>
<summary><b>Save Last Frame (FFMPEGA)</b> — Persist the tail of a generation to a named slot for scene continuation.</summary>

Writes the last frame(s) of a video or IMAGE batch into `output/ffmpega_last_frame/<slot>/`, so a later queue run can start the next shot from where this one ended. Built for i2v chaining (Wan 2.2 and similar), where extending a shot means handing the model the frame you finished on.

Shows a thumbnail strip of the slot's current contents as soon as the node is placed — no need to queue a prompt to see which frame you're working with.

Connect `images` whenever possible: the tensor is written straight to PNG with no h264 round-trip. Pulling the frame out of the encoded file instead bakes in compression artifacts and yuv420p chroma subsampling, which compound visibly over a chain of generations.

| Input | Type | Description |
| :--- | :--- | :--- |
| `slot_name` | STRING | Named slot to write into. Use different names to keep several chains apart (`drone_a`, `drone_b`). Sanitized to `[A-Za-z0-9_-]`. |
| `frame_count` | INT | How many trailing frames to save (default 1). |
| `offset_from_end` | INT | Skip this many frames at the very end. The literal final frame is often motion-blurred; try 1–3. |
| `keep_history` | BOOLEAN | Off (default) keeps the slot at exactly `frame_count` files with fixed names. On appends numbered files, building an archive. |
| `images` | IMAGE | *(optional)* Preferred, lossless source. Takes priority over `video_path`. |
| `video_path` | STRING | *(optional)* Fallback source — ffmpeg decodes the file's tail. |
| `filename_prefix` | STRING | *(optional)* Base filename inside the slot (default `lastframe`). |

| Output | Description |
| :--- | :--- |
| `last_frame` | The saved frame(s), oldest first — the exact tensor written, not a re-read |
| `frame_path` | Absolute path of the newest saved frame |
| `slot_name` | The sanitized slot name |
| `frame_count` | How many frames were actually written |

> **Chaining inside one workflow:** wire `last_frame` straight into the next generation rather than adding a Load Last Frame node. Two unconnected nodes have no guaranteed execution order, and ComfyUI decides node caching *before* execution starts — so the load side would read the previous run's frame.

</details>

<details>
<summary><b>Load Last Frame (FFMPEGA)</b> — Read a saved slot back to continue a scene in a later run.</summary>

Loads the frame(s) Save Last Frame wrote to a named slot. Discovery is deterministic — the slot directory comes from the slot name and files carry fixed zero-padded names, so the pairing is an explicit contract rather than an mtime race against everything else in your output folder.

Shows the same inline thumbnail strip as Save Last Frame, so you can see what the slot holds before running. The eight resize sub-widgets stay collapsed until `enable_resize` is turned on.

| Input | Type | Description |
| :--- | :--- | :--- |
| `slot_name` | STRING | Slot to read — must match Save Last Frame's `slot_name`. |
| `refresh_mode` | DROPDOWN | `auto` (reload when the slot changes) or `manual`. |
| `frame_count` | INT | How many of the slot's trailing frames to load. |
| `offset_from_end` | INT | Skip this many frames at the end of the slot. |
| `on_missing` | DROPDOWN | *(optional)* `fallback` / `empty` / `error` — what to do when the slot is empty. |
| `fallback_image` | IMAGE | *(optional)* Used when the slot is empty. |
| `source_folder` | STRING | *(optional)* Read an arbitrary folder instead of the slot (picked by mtime). |
| `filename_filter` | STRING | *(optional)* Only consider files with this prefix. |
| `mask` | MASK | *(optional)* Upstream mask pass-through. |
| `trigger` | ANY | *(optional)* Ordering hint — wire any Save Last Frame output in to force it to run first. |

| Output | Description |
| :--- | :--- |
| `IMAGE` | The loaded frame(s), oldest first |
| `MASK` | Solid white mask matching the frames |
| `image_path` | Absolute path of the newest loaded frame |
| `width` / `height` | Frame dimensions |
| `frame_count` | How many frames were loaded (0 = slot was empty) |

> **Starting a chain:** on the first run the slot is empty. Wire your original start image into `fallback_image` so run 1 and run N are the same graph with no rewiring — otherwise you get a black frame that silently poisons the generation.

</details>

<details>
<summary><b>FaceCam (FFMPEGA)</b> — Portrait video camera control with orbits, zooms, and tilts.</summary>

Portrait video generation using [FaceCam](https://github.com/weijielyu/FaceCam) (CVPR 2026). Uses 2+2 architecture: Wan2.2 14B GGUF base models + FaceCam bf16 partial checkpoints. Supports KSampler Advanced-style controls for multi-node chaining (HIGH model for trajectory, LOW model for detail refinement).

| Input | Type | Description |
| :--- | :--- | :--- |
| `image` | IMAGE | Source face image or video frame. |
| `model_high` | MODEL | Wan2.2 GGUF base model (from "Load Diffusion Model"). |
| `model_low` | MODEL | Wan2.2 GGUF base model for refinement pass. |
| `camera_preset` | DROPDOWN | Camera movement preset (orbit, zoom, tilt, etc.) with detailed tooltips. |
| `add_noise` | DROPDOWN | `enable` / `disable` — KSampler Advanced noise control. |
| `start_at_step` | INT | Step to start denoising at. |
| `end_at_step` | INT | Step to stop denoising at. |
| `return_with_leftover_noise` | DROPDOWN | `enable` / `disable` — preserve noise for chaining. |

| Output | Description |
| :--- | :--- |
| `LATENT` | Latent output for chaining to next FaceCam node |
| `images` | Decoded video frames |

</details>

<details>
<summary><b>Frame Picker (FFMPEGA)</b> — Interactive frame selection and reordering with contact-sheet grid.</summary>

Browse video frames in a contact-sheet grid, select/deselect with click (Shift+click for range, Ctrl+click for toggle), reorder via drag-and-drop. Bulk tools: Select All, Deselect All, Invert Selection, Every Nth Frame. Pause mode blocks execution until selection is applied.

| Input | Type | Description |
| :--- | :--- | :--- |
| `images` | IMAGE | *(optional)* Video frames from upstream. |
| `video_path` | STRING | *(optional)* Path to video file. |

| Output | Description |
| :--- | :--- |
| `images` | Selected frames in user-defined order |
| `video_path` | Path to temp video of selected frames |
| `frame_count` | Number of selected frames |
| `selection_json` | JSON array of selected frame indices |

</details>

<details>
<summary><b>Shader Overlay (FFMPEGA)</b> — GPU-accelerated GLSL shader effects with chaining, depth modes, and animation.</summary>

Apply up to 3 stacked GLSL shaders with per-layer animation speed, hue shift, blend mode, and opacity control. Supports depth-aware shader application (foreground focus, background focus, depth outline, atmospheric) via Video Depth Anything integration, and SAM3 object masking for targeted shader effects. 70 built-in shader presets plus random mode.

| Input | Type | Description |
| :--- | :--- | :--- |
| `images` | IMAGE | Video frames to apply shaders to. |
| `shader_1` | DROPDOWN | First shader effect (70 options + `random`). |
| `shader_2` | DROPDOWN | *(optional)* Second stacked shader. |
| `shader_3` | DROPDOWN | *(optional)* Third stacked shader. |
| `animation_speed` | FLOAT | Animation speed multiplier (0.1–5.0). |
| `blend_mode` | DROPDOWN | Blend mode for shader compositing. |
| `depth_mode` | DROPDOWN | Depth-aware application mode. |

| Output | Description |
| :--- | :--- |
| `images` | Processed video frames with shader effects |

</details>

---
