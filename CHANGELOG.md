# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **SeedVR2 INT8 ConvRot Upscale Models**: New `seedvr2_3b_int8` and `seedvr2_7b_int8` entries for `upscale_model`, loading checkpoints saved in ComfyUI's `int8_tensorwise` layout with the block-Hadamard ("ConvRot") rotation. Smaller and faster than the FP8 variants, and — unlike ComfyUI's native SeedVR2 nodes — they run through this pack's BlockSwap, so the 7B fits on cards that OOM natively. Measured on a 11.6 GB card at 720p: 3B without BlockSwap peaks at 5.0 GB; the 7B peaks at 6.9 / 5.2 / 5.0 GB with `blockswap_blocks` of 8 / 16 / 24. *(`core/seedvr/optimization/int8_ops.py`, `core/seedvr/core/model_loader.py`)*
  - **How it works**: Each quantized `nn.Linear` ships as an INT8 `weight` (pre-rotated `round((W @ H_blkᵀ)/s)`), an FP32 per-output-row `weight_scale`, and a `comfy_quant` tag holding the format JSON. The loader decodes those tags, swaps the matching `nn.Linear` layers for an `Int8ConvRotLinear` before applying the state dict, and dispatches to `comfy_kitchen.int8_linear`, which rotates and quantizes the activation inside the kernel — the weight is never dequantized. Requires a CUDA GPU of compute capability 7.5+; the loader says so plainly rather than failing deep in the model.
  - **Compute precision**: The non-quantized tensors (biases, norms, ada modulation, RoPE freqs) ship as FP16 and are cast to BF16 at load, putting the model on the same effective compute precision as the FP8 path instead of tripping `CompatibleDiT`'s FP16 branch.
  - **Architecture check**: The shared loader applies weights with `strict=False`, under which a checkpoint for the wrong variant would load "successfully" and render noise. INT8 checkpoints are now verified to supply every tensor the model expects before loading; the baked-in `positive_conditioning`/`negative_conditioning` embeddings they carry are ignored, since this port uses its own `pos_emb.pt`/`neg_emb.pt`.
  - **`models/diffusion_models/` is now searched**: SeedVR2 checkpoints in ComfyUI's native format land there rather than in `models/SEEDVR2/`. Both are searched, `SEEDVR2/` first; files found in the shared folder are filtered by name so unrelated checkpoints are not offered as upscalers. *(`core/seedvr/utils/constants.py`)*
  - **Local-only registry entries**: The INT8 variants have no download mirror, so a missing file now fails immediately with the list of directories to put it in, rather than surfacing later as a bare "file not found". *(`core/seedvr/utils/model_registry.py`, `core/seedvr/utils/downloads.py`)*

- **Save / Load Last Frame — Scene Continuation**: New node pair for extending a shot across queue runs. `FFMPEGASaveLastFrame` writes the trailing frame(s) of a generation into a named slot under `output/ffmpega_last_frame/<slot>/`; `FFMPEGALoadLastFrame` reads that slot back, so a later run can start where the previous one ended. Built for i2v chaining (Wan 2.2 and similar), where continuing a shot means handing the model the frame you finished on and no authored end-frame exists. *(`core/last_frame.py`, `nodes/save_last_frame_node.py`, `loadlast/load_last_frame.py`)*
  - **Tensor-first, lossless**: When `images` is connected the frame is taken straight from the IMAGE tensor and written to PNG with no h264 round-trip. Extracting from the encoded file instead bakes in compression artifacts and yuv420p chroma subsampling, which compound visibly across a chain of generations. `video_path` remains available as an ffmpeg fallback for any video on disk, and logs which source it used.
  - **Named slots**: Several independent chains coexist without cross-talk, and Save↔Load pairing is an explicit contract rather than "newest file anywhere wins". Slot names are sanitized to `[A-Za-z0-9_-]` before any path join.
  - **`frame_count` + `offset_from_end`**: Save or load a trailing batch rather than a single frame, and skip the very last frames — which on a moving shot are often the worst, being motion-blurred and softer than the rest.
  - **Deterministic overwrite**: By default a slot holds exactly `frame_count` files at fixed zero-padded names, and stale files from a longer previous run are pruned — so loading never returns a mix of two runs. `keep_history` switches to an accumulating archive instead.
  - **Cold-start handling**: `on_missing` (`fallback` / `empty` / `error`) plus a `fallback_image` input, so the first run of a chain uses your original start image rather than silently feeding a black frame into the sampler.
  - **Slot preview on both nodes**: Each node shows a thumbnail strip of whatever its slot currently holds, populated from the new `/ffmpega/last_frame/slot` route as soon as the node is placed — no queued prompt needed. Without it you would have to run the graph just to find out which frame you are about to continue from. The strip refreshes on slot rename, after execution, and on a light poll. *(`src/nodes/last_frame_ui.ts`)*
  - **Resize disclosure**: `LoadLastFrame`'s eight resize sub-widgets collapse behind its `enable_resize` toggle, matching how `LoadLastImage` already treats the same shared widget group. Hiding is display-only — values are kept and still honoured.
  - **Ordering**: `SaveLastFrame` exposes a `last_frame` IMAGE passthrough — the exact tensor written — which is the correct way to chain inside a single workflow. Two unconnected nodes have no guaranteed execution order, and node caching is decided before execution begins, so a same-graph Load would read the *previous* run's frame. A wildcard `trigger` input is provided as an explicit ordering hint.
  - **Tests**: New `tests/test_last_frame_selection.py` (torch-free index and slot-name logic) and `tests/test_last_frame.py` (round-trip, pruning, cold-start, ffmpeg tail extraction).
- **Load Last Video — `last` frame-select mode**: `frame_select_mode` gained a `last` entry that selects only the final frame, for the same continuation use case. The back-off from the end is frame-relative (`0.5 / fps`) rather than the fixed `0.01s` used by `first_last`, which at 100fps is a full frame period and would land on the second-to-last frame. *(`loadlast/load_last_video.py`)*
- **Save Video — Advanced Output Options**: `FFMPEGASaveVideo` gained a full encoding surface, so webm/ProRes/lossless output no longer requires falling back to VideoHelperSuite. All new widgets are optional, so workflows saved before them keep working unchanged. *(`nodes/save_video_node.py`, `src/nodes/save_video_node.ts`)*
  - **`show_advanced` disclosure**: every new widget sits behind one toggle, off by default, so the node's resting size is unchanged. Visibility is two-level — the toggle reveals the section, and within it any widget the chosen format cannot use collapses on its own. Hiding is display-only: values are kept and still honoured, so collapsing the section never silently changes an encode.
  - **`output_format`**: `source (no re-encode)` (default), `h264-mp4`, `h265-mp4`, `vp9-webm`, `av1-webm`, `prores-mov`, `ffv1-mkv`, `gif`, `webp`.
  - **Copy / remux / re-encode**: The default stays a plain `shutil.copy2` with no ffmpeg call at all. When only the container differs — or the source already holds exactly the codec the chosen format produces — the file is stream-copied (`-c copy`), which is lossless and near-instant. A full re-encode happens only when the codec actually has to change. An ffmpeg failure falls back to a plain copy rather than losing the render.
  - **Quality & codec**: `crf`, `encode_preset`, `bit_depth` (8/10), `audio_codec`, `audio_bitrate`, `faststart`. Irrelevant widgets collapse per format in the UI (VP9/AV1 take a deadline rather than an x264 preset; ProRes and FFV1 have fixed quality; GIF/WebP carry no audio).
  - **10-bit path**: `bit_depth=10` streams 16-bit `rgb48le` frames and encodes `yuv420p10le`, moving the 8-bit quantisation into swscale and greatly reducing banding on gradients.
  - **Playback extras**: `loop_count`, `pingpong` (image input only), `trim_to_audio`.
  - **`embed_workflow`**: Writes `prompt`/`workflow` into the container using ComfyUI's *native* convention (`-movflags use_metadata_tags`), so dragging a saved MP4 onto the canvas restores the workflow with no client-side code. Matroska/WebM additionally get a `comment` tag, since those muxers uppercase custom keys. The sidecar PNG is still written either way.
  - **`frame_output`**: `preview (64)` / `all` / `none`, making the previously silent 64-frame downsample of the `images` output explicit and skippable.
  - **`color_policy`**: see below.
- **Save Video — Frame Count in the Preview**: The info bar under the player now reads `1920×1080 | 120f @ 24fps | 5.0s | 12.3 MB`, and during playback the frame segment becomes a live playhead (`▶ 45/120f @ 24fps`), driven by `requestVideoFrameCallback` so the number matches the picture on screen. The count and rate are probed from the file that was actually written — reusing `probe_video_stats()` from `core/last_frame.py` — rather than derived from the `fps` widget or `images.shape[0]`, so `pingpong`, `loop_count` and pass-through sources all report the truth. A `<video>` element exposes neither value, so both ride along in the node's UI payload next to `file_size`; where ffprobe is unavailable the segment is simply omitted. The rVFC bookkeeping lives in a shared `attachPlayheadTracker()` that both this node and Load Video Path drive their readouts from; it reports the position, whether playback is running, and *why* the playhead moved — the last of which is what lets Load Video Path tell a seek from playback. Its pure range maths (`frameAtTime`, `rangeEndSeconds`) is covered by `src/shared/ui_helpers.test.ts`, the pack's first frontend unit test. *(`nodes/save_video_node.py`, `src/nodes/save_video_node.ts`, `src/shared/ui_helpers.ts`)*
- **Save Video — Preview Survives Tab Switches and Restarts**: The player used to empty itself the moment the graph was rebuilt — switching workflow tabs, reopening a workflow, restarting the server — and read `Waiting for execution...` again even though the file was still sitting in `output/`. It now comes back from whichever of two sources is available, because the two failure modes are genuinely different. *(`src/nodes/save_video_node.ts`, `src/ffmpega_ui.ts`)*
  - **Tab switches** go through ComfyUI's own machinery. The frontend keeps each node's last execution payload in `app.nodeOutputs`, and `ChangeTracker` snapshots that map per workflow and reassigns the whole object when you return to a tab — which fires the `onNodeOutputsUpdated` extension hook. Save Video now implements that hook and rebuilds the player from the payload, exactly as core's audio and Preview3D widgets do, and exactly why the native Save Video node never lost its video here. Nothing needs serializing for this path: the payload *is* our `ui` dict, so it already carries the file plus the frame count and rate. The walk covers subgraphs, since the map spans the whole workflow while `app.graph` is only what is on screen.
  - **Reloads and server restarts** cannot use that map — it lives in the page. For those the descriptor is also written into the node's `properties`, which LiteGraph serializes into the workflow and restores before `onConfigure` runs. This is where VideoHelperSuite's behaviour was the model but not its mechanism: VHS persists by rewriting `widgets_values` from LiteGraph's positional array into a name-keyed dict for every one of its nodes, which would change the on-disk shape of every existing FFMPEGA workflow — `properties` gets the same result without touching that format, and is already how the Load Last and Video Editor nodes persist their own state.
  - **Recovering a run from the queue history** takes the first path too, and refreshes the property from it, so a video reached that way is also good across a later reload.
  - Preview-only (`save_output = false`) saves are remembered as well: they survive a tab switch, and after a restart — when ComfyUI has cleared its temp directory — `/view` 404s, the existing `error` handler hides the player and the node collapses back to its no-preview size, the same silent failure VHS has. The timestamp is minted per URL rather than stored, so an `overwrite` run that replaces a file in place is never served from browser cache. Covered by `src/nodes/save_video_node.test.ts`, which drives the real handler through both restore paths.
- **Shared Encoding Module**: New `core/video/encode_opts.py` is the single source of truth for colour policy, the format table, ffmpeg argument construction and the tensor→bytes conversion; `core/video/metadata.py` handles container metadata. Every FFMPEGA encoder now routes through them. *(`tests/test_encode_opts.py`)*
- **SCAIL-2 Pose-Driven Character Animation**: New ComfyUI-native, in-process rebuild of the `Wan21_SCAIL2` workflow, replacing the vendored SCAIL v1 pipeline. Loads the SCAIL-2 fp8 diffusion model via `comfy.sd.load_diffusion_model`, the Wan 2.1 VAE, the UMT5 text encoder and CLIP-vision (ViT-H), applies model-only LoRAs (lightx2v distill, DPO) plus a ModelSamplingSD3 shift, tracks the driving pose video and reference image with native SAM 3.1, colorizes per-identity masks via `comfy_extras.nodes_scail.SCAIL2ColoredMask`, and samples through `comfy.samplers`. Outputs both the animation and the colored pose-video mask. Everything runs under ComfyUI's VRAM management — no subprocess. *(`core/scail2_synthesizer.py`, scail2 no-LLM mode)*
  - **25 Advanced Widgets**: `scail2_width/height/length`, `scail2_pose_extend` (pingpong/loop/hold_last/none), `scail2_steps`, `scail2_cfg`, `scail2_shift`, `scail2_seed`, `scail2_sampler`, `scail2_scheduler`, `scail2_denoise`, `scail2_replacement_mode`, `scail2_sort_by`, `scail2_object_indices`, `scail2_composite_direction`, `scail2_main_reference`, `scail2_color_match`, `scail2_blockswap_blocks`, `scail2_tiled_vae`, `scail2_subject`, `scail2_max_objects`, `scail2_detection_threshold`, `scail2_detect_interval`, `scail2_point_src_width/height`.
  - **Model Registry**: New `scail2` entry (~16 GB fp8) mirrored from `Comfy-Org/SCAIL-2`.
  - **Tests**: New `tests/test_scail2.py`.
- **FlashVSR Video Super-Resolution**: New vendored FlashVSR backend with three pipelines — `flashvsr_full`, `flashvsr_tiny` and `flashvsr_tiny_long` — selectable from `upscale_model`. *(`core/flashvsr/`, `core/flashvsr_synthesizer.py`)*
  - **Block Swap**: `blockswap_blocks` drives DiSynth's `num_persistent_param_in_dit` budget, keeping DiT transformer blocks off-GPU (`-1` = auto-size from free VRAM).
  - **Processing Modes**: `flashvsr_processing` (whole / temporal / spatial), plus `flashvsr_frame_window`, `flashvsr_color_fix` and `flashvsr_decode_tile` for near-lossless spatial decode tiling that bounds TCDecoder activation memory.
- **MatAnyone2 Video Matting**: New CVPR 2026 MatAnyone2 backend for production-quality alpha mattes and foreground extraction with temporal coherence. ⚠️ NTU S-Lab License 1.0 — non-commercial research use only. *(`core/matanyone2_synthesizer.py`, video_matting no-LLM mode)*
- **SVI 2.0 Pro Infinite-Length Video**: Vendored Stable Video Infinity 2.0 Pro (ICLR 2026 Oral) — generates arbitrarily long video by iteratively producing 81-frame clips with Wan 2.2 I2V-A14B and paired high/low-noise LoRAs. *(`core/svi_synthesizer.py`, svi no-LLM mode)*
- **Wan-Animate**: New ComfyUI-native Wan 2.2 Animate synthesizer, loading the transformer via `comfy.sd.load_diffusion_model` and following the same model-lifecycle pattern as SVI. *(`core/wan_animate_synthesizer.py`, `core/wan_animate_preprocess.py`, wan_animate no-LLM mode)*
- **SHARP Single-Image 3D View Synthesis**: Wraps Apple's SHARP model to predict 3D Gaussian splat parameters from one image (<1s) and render a camera-trajectory video via gsplat. ⚠️ Apple ML Research License — non-commercial / research only. *(`core/sharp_synthesizer.py`, sharp no-LLM mode)*
- **PhyFPS / Visual Chronometer**: Predicts the *physical* frame rate implied by a video's motion using the Pulse-of-Motion Visual Chronometer model, and optionally re-times the clip to match. *(`core/phyfps_synthesizer.py`, `core/visual_chronometer/`, phyfps no-LLM mode)*
- **Meta Sapiens2 Human-Centric Vision**: New Sapiens2 backend with detector, fp8 quantization and conversion support. The `sapiens2_size` dropdown folds the precision choice into the size value (`0.4b`, `0.8b`, `1b`, `5b`, `5b (fp8)`), parsed by the new `parse_size_selector()` helper. *(`core/sapiens2/`, sapiens2 no-LLM mode)*
- **Multi-Source Comparison Output (Save Video & Save Image)**: Both save nodes now accept multiple sources via auto-growing `images_a`/`video_path_a` (and `image_path_a`) inputs and combine them into one side-by-side or grid comparison. Videos are laid out with ffmpeg `xstack`, shorter clips freezing on their last frame until the longest ends; images are composited tensor-only with no ffmpeg dependency. Shared layout math keeps both paths identical. *(`core/grid_layout.py`, `core/video_compare.py`, `core/image_compare.py`)*
  - **New Widgets**: `layout` (auto / horizontal / vertical / grid), `label_panels`, `labels`, `panel_gap`.
  - **Save Image Frontend**: New `src/nodes/save_image_node.ts` UI handler.
- **FaceCam Analytic Face Mesh**: New mesh conditioning path that poses MediaPipe's own canonical face model with the camera matrices already computed and projects it, instead of rendering a 3D Gaussian proxy head and running a face *detector* over the renders to guess the pose back. MediaPipe loses the mesh past ~40–50° of yaw — exactly the pose a camera orbit produces — so conditioning previously went blank at the extremes. Coverage is now total by construction, motion is smooth because it is an analytic function of the camera path, and `orbit_left`/`orbit_right` are exact mirrors. The canonical 468 vertices are read from the `face_landmarker` task bundle already on disk, so no vendored asset is required. *(`core/facecam_mesh.py`, new `mesh_source` widget)*
- **Shared Block-Swap Helper**: New `register_blockswap()` used by SVI, SCAIL-2 and FaceCam. Rather than a custom offload engine, it inflates `EXTRA_RESERVED_VRAM` for the duration of `prepare_sampling` so ComfyUI's own lowvram partial loader leaves that many bytes on the offload device and casts per-layer on forward — which keeps LoRA-at-cast-time and GGUF weights working, both of which a hand-rolled offload would break. *(`core/vram_utils.py`)*
- **SeedVR2 7B FP8 Mixed**: New `seedvr2_7b_fp8_mixed` upscale model — FP8 with the final transformer block (block 35) kept in FP16, eliminating the 7B-specific seam/grid artifacts of pure FP8 at the same VRAM footprint. Mirrored to `AEmotionStudio/SeedVR2-models`.
- **Native SAM 3.1 Image Tracking Helper**: New `track_images_native_sam31()` public entry point in `core/sam3_masker.py`, used by the SCAIL-2 pipeline.
- **Load Video Path — `enable_mask` Toggle**: New BOOLEAN input that collapses `mask_mode`, `mask_output_type`, `sam_version` and `show_mask_preview` behind a single switch, so nodes that never mask show four fewer rows. When off, the backend forces `mask_mode = "none"`; an upstream MASK connection still passes through. *(`nodes/load_video_path_node.py`, `src/nodes/load_video_node.ts`)*
- **Load Video Path — Frame Budget Annotations**: `skip_first_frames` and `frame_load_cap` now carry a dimmed "N left" suffix showing how many source frames remain unused (`frame_load_cap · 29 left`, or `all 54` when uncapped). Rendered through the widget's `label`, which ComfyUI already draws in the theme's secondary colour and truncates on narrow nodes.
- **Load Video Path — Node-Wide Video Drop**: A video can now be dropped anywhere on the node. ComfyUI routes graph drops through a `document` listener that dispatches to `app.dragOverNode`, which is only ever set by a `dragover` listener on the *canvas*; the node's DOM widgets sit above the canvas, so the whole preview area was dead and crossing onto it actually **cancelled** an already-valid drag. A dashed "Drop video to load" overlay now covers the preview while dragging. *(new `attachFileDropZone()` in `src/shared/ui_helpers.ts`)*
- **Native SAM 3.1 Video Backend**: SAM 3.1 video masking now runs **in-process** against ComfyUI's native SAM 3 model (`comfy_extras/nodes_sam3.py`, `comfy/ldm/sam3/`) instead of the upstream `sam3` pip package in a subprocess. The model loads as a standard `ModelPatcher`, so it participates in ComfyUI's VRAM lifecycle (`load_model_gpu`, offloading, fp16 casting) and has no CUDA-context leak — eliminating the need for a child process. Both text-prompted and point-prompted video tracking are supported, reusing ComfyUI's `forward_video`/`forward_segment`, `_extract_text_prompts`, and `unpack_masks`. The existing mirror checkpoints (`models/SAM3.1/sam3.1_multiplex.safetensors`) load natively as-is — no new download. *(`core/sam3_masker.py`)*
  - **Flag-gated with automatic fallback**: Controlled by `FFMPEGA_SAM3_NATIVE` (default on). Any load/inference error logs a warning and transparently falls back to the legacy subprocess + upstream-`sam3` path. Set `FFMPEGA_SAM3_NATIVE=0` to force the legacy path.
  - Public API of `mask_video` / `mask_video_subprocess` is unchanged — no node call sites required modification. Image masks and plain SAM 3 video are untouched.

### Changed
- **Load Video Path VRAM Handling**: When the native SAM 3.1 path is active, the node no longer force-evicts all ComfyUI models (`unload_all_models()`) before masking — ComfyUI's `load_model_gpu` offloads only what it needs to fit SAM 3.1 (~3 GB), keeping other models (DWPose, checkpoints) resident and avoiding needless reloads. The full eviction is retained for the legacy subprocess path. *(`nodes/load_video_path_node.py`)*
- **Agent Node Modes**: `no_llm_mode` expanded to **31 modes** with the addition of `svi`, `sharp`, `wan_animate`, `scail2`, `phyfps`, `onion_skin`, `comparison`, `video_matting` and `sapiens2`.
- **Video Colour Handling — Selectable Policy, Applied Everywhere**: New `color_policy` widget on Save Video, and one shared implementation behind it. Measured on FFmpeg n8.1.2 with a pure-green frame (BT.601 limited Y=145, BT.709 limited Y=173):
  - `sRGB (recommended)` — **new default**. BT.709 matrix, limited range, tagged `bt709` primaries with the honest `iec61966-2-1` transfer, because ComfyUI IMAGE tensors really are sRGB. Colour-managed players (Chrome, QuickTime, Resolve) now apply the sRGB EOTF and match the ComfyUI preview.
  - `BT.709 broadcast` — identical pixels, transfer tagged `bt709`. This is what VideoHelperSuite intends; note its `fake_trc` mechanism is a no-op on FFmpeg 8, so it is not reproduced here.
  - `ComfyUI native match` — no conversion and no tags, byte-identical to `CreateVideo` → `SaveVideo`. Native is not merely untagged: swscale falls back to the **BT.601** matrix, so the pixel data genuinely differs (Y=144 vs Y=172), which is the colour difference between the two nodes.
  - `full range (pc)` — full-range levels for archival, with the tag and the samples finally agreeing.
- **Colour Tags Now Actually Written**: `-color_primaries` and `-color_trc` passed as *output* options are silently dropped by FFmpeg 8 — the stream ends up tagged `unknown` for both, which was true of FFMPEGA **and** VideoHelperSuite. Tagging now goes through the `setparams` filter, which was verified to write all four values. Builds without `setparams` (pre-4.3) fall back to the legacy flags.
- **SVI Block Swap & Tiled VAE**: New `blockswap_blocks` (of 40 Wan 2.2 transformer blocks) and `tiled_vae` options. The text encoder is now evicted after all prompts are encoded up-front, so it no longer competes with the UNets and VAE for VRAM during sampling. *(`core/svi_synthesizer.py`)*
- **FaceCam Block Swap**: New `blockswap_blocks` widget wired through the shared `register_blockswap()` helper. *(`nodes/facecam_node.py`)*
- **Load Video Path Upload Request**: The upload now goes through `api.fetchApi()` rather than a bare `fetch("/upload/image")`, matching VideoHelperSuite. `apiURL()` resolves the route as `api_base + "/api" + route`, and `fetchApi` attaches the `Comfy-User` and auth headers that a bare fetch omits. Failures now log the HTTP status and response body to the console.
- **Upload Button Sizing**: The Upload Video button is pinned to a fixed row height. ComfyUI's `arrangeWidgets` gives every widget with a `computeSize` a fixed height and splits the node's leftover height among the rest — with no `computeSize` the button was the only flexible widget and absorbed all of it, stretching as the node grew.
- **Shared UI Helpers**: `toggleWidget()` and `fitHeight()` are now imported from `src/shared/ui_helpers.ts` by the Load Video Path node instead of being re-declared locally.

### Removed
- **SCAIL v1 Pipeline**: Deleted the vendored `core/scail/` (attention, configs, fm_solvers, lora, model_scail, pipeline, scail_utils, vae), `core/scail_pose/` (align3d, draw_pose_utils, draw_utils, nlf_render, render_torch) and `core/scail_synthesizer.py` — roughly 4,100 lines superseded by the ComfyUI-native SCAIL-2 synthesizer above.

### Fixed
- **`allow_model_downloads=False` blocked SeedVR2 even with every weight already on disk**: `_load_model` called `require_downloads_allowed("seedvr2")` unconditionally at the top, before checking whether anything actually needed fetching — so the toggle refused a download that was never required. The toggle governs downloading, not using what you already have. The gate now runs only against files that are genuinely absent, via the new `require_downloads_allowed_for_missing()` helper, and logs which weights it intends to fetch when some are missing. *(`core/seedvr_synthesizer.py`, `core/model_manager.py`)*
  - The same check-permission-before-checking-disk pattern exists at roughly 30 other call sites across the synthesizers; the new helper is there for them, but only SeedVR2 has been converted.
- **Load Video Path silently sped up every clip over 64 frames**: The node borrowed `SaveVideoNode._extract_frames` without passing a `mode`, so it inherited that method's `"preview (64)"` default and sampled each video down to 64 frames with `np.linspace`. Because the sample is spread *evenly across the whole clip* rather than truncated, the full action survived with fewer frames — so anything re-encoding those frames played faster than the source. A 121-frame / 24 fps / 5.04 s clip came out at 64 frames / 2.67 s, near enough double speed. The loader now decodes every frame; `skip_first_frames`, `frame_load_cap` and `select_every_nth` remain the only things that reduce the count. *(`nodes/load_video_path_node.py`)*
  - **The cap was invisible**: the node exposes no preview/all selector, and it still reported `frame_count` from ffprobe metadata (121) while handing over 64 images. Both outputs are now derived from the decoded tensor, and a mismatch against the metadata prediction is logged.
  - **Decoding moved into `core/media_converter.decode_video_frames()`**, shared by both nodes, so a loader no longer instantiates a save node to reach a private preview helper — the coupling that let a preview default become a load-path default. `SaveVideoNode._extract_frames` is now a thin wrapper and its `mode` argument is **required**, so the old default cannot be inherited by accident again. A test asserts the loader never mentions `SaveVideoNode`.
- **Save Video's `images` output defaulted to a 64-frame preview**: same sampler, same consequence one node downstream — wiring that output anywhere re-encoded a time-compressed clip. `frame_output` now defaults to `all`; `preview (64)` stays selectable, its tooltip says plainly that it compresses time, and it logs whenever it actually drops frames. *(`nodes/save_video_node.py`)*
- **Save Video could not express NTSC frame rates**: `fps` was `INT` with `min: 1`, so 23.976 and 29.97 were unreachable. It is now `FLOAT` (matching VHS's `floatOrInt`), and the compose path no longer truncates it with `int()`. The tooltip also states when the widget applies — a pass-through file under `source (no re-encode)` keeps its own rate, and a mismatch there is now warned about rather than silently ignored. *(`nodes/save_video_node.py`, `core/video_compare.py`)*
- **Agent intermediates were hardcoded to 24 fps**: `images_to_video()` was called without an `fps` in two places, so a frames-in run stamped its temp video — and therefore the agent's `video_path` output — at 24 fps regardless of the real source rate. Frame *count* was preserved, so an images→images chain still landed correctly, but path-first wiring of 30/60 fps footage did not. The rate is now taken from the connected source video when there is one, and only falls back to 24 for a bare image batch, which genuinely has no frame rate. *(`nodes/input_resolver.py`, `nodes/agent_node.py`)*
- **LoadLast video decoder broken on ffmpeg 8+**: `VideoDecoder._decode_frames_ffmpeg` passed `-vsync vfr`, which ffmpeg 8 removed outright (`-fps_mode` replaced it in 5.1). Every dense decode failed with `Unrecognized option 'vsync'`, and callers that swallow that error — the Shader Overlay node among them — quietly returned a 512×512 zero tensor instead of the video. The decoder now uses `-fps_mode vfr` and retries with `-vsync` only when ffmpeg reports the option as unknown, the same dance `core/last_frame.py` already does. *(`loadlast/processing/video_decode.py`)*
- **SeedVR2 `seedvr2_7b_fp8_mixed` unreachable from the skill layer**: The variant was in the node dropdown but missing from `skills/handlers/upscale.py` and the `ai_upscale` skill's `choices`, so agent- and skill-driven upscales rejected it as an invalid model. All four model lists now agree, and a test asserts they stay that way. *(`skills/handlers/upscale.py`, `skills/category/ai_visual.py`)*
- **Load Video Path Scrubber Snapping Back**: Dragging the preview scrubber past the trim range's out-point jumped the playhead to the in-point, paused or not — with `frame_load_cap` set (81 frames of a 30 s clip ends the range around 3 s) nearly the whole scrubber was unreachable, and the "📏 Jump: Middle / End" menu items were silently undone the moment they landed. The range clamp lived in a `timeupdate` listener, which also fires while seeking and never checked whether the video was playing. It now loops back only when playback runs off the out-point on its own: seeks are never reversed, and playing on from a spot the user deliberately parked past the out-point is left alone. *(`src/nodes/load_video_node.ts`)*
  - **Out-point ignored `select_every_nth`**: the range used `availFrames / effFps`, but 60 frames taken every 2nd are spread across 120 source frames — playback was cut off halfway. Now via the shared `rangeEndSeconds()`.
  - **Playhead yanked on unrelated edits**: any change to a trim widget re-seeked to the in-point, and the widget-poll cache started empty, so a spurious "everything changed" pass seeked to 0 about 800 ms after the node appeared. The seek now happens only when the in-point actually moves, and the cache is seeded from the widgets.
- **Load Video Path Frame Counter Never Appeared**: The live counter was gated on `_srcMeta.fps > 0`, set only if the `/ffmpega/video_info` probe returned an fps, while the info bar beside it fell back to `_srcMeta.fps || 24` — so whenever that probe failed or lagged, the bar rendered "24fps" happily and the counter stayed hidden forever. Both now share the one fallback. The readout also gained the `f` unit and stopped duplicating the frame total already in the bar: given a playhead, that segment *becomes* the playhead and moves to the front (`▶ 45/81f (of 120) • 1920×1080 • 30fps • …`). It tracks paused scrubbing too, since the frame you are parked on is the number `skip_first_frames` needs. *(`src/nodes/load_video_node.ts`)*
- **SAM 3.1 Video OOM / Hang**: Fixed the multiplex video point-tracking path appearing to hang for ~7.5 minutes before failing on 12 GB GPUs. The root cause of the high memory was the inference running without `torch.inference_mode()`, so autograd retained every 1008×1008 activation, pushing peak VRAM to ~10–11.5 GB (OOM on an RTX 4070). Running the native model under `inference_mode` drops peak to **~3 GB**, matching the model's advertised footprint. Point and text video tracking now complete in seconds on the same hardware that previously OOM'd.
- **Crushed Blacks / Blown Highlights in Encoded Video**: Fixed levels being re-expanded by players that normalise the deprecated `yuvj420p` full-range output to `yuv420p`. See the colour-range change above. *(`core/media_converter.py`)*
- **Full-Range Tag on Limited-Range Video**: Three encoders tagged their output `-color_range pc` while swscale wrote limited-range samples, so players re-expanded levels that were never compressed — crushing blacks and blowing highlights. All now use the shared policy. *(`nodes/nollm_modes.py` `_encode_frames_to_video` and the SHARP renderer, `core/svi_synthesizer.py`)*
- **Untagged / Mismatched Colour in the Remaining Encoders**: `core/images_to_video.py` (Video Editor, Shader Overlay, FacePoke, Load Last Video) wrote untagged BT.601, disagreeing with everything else in the pack. Now routed through the shared policy. *(`core/images_to_video.py`)*
- **Out-of-Gamut Frames Wrapping to Black**: `core/images_to_video.py` converted frames with an unclamped `(x * 255).astype(uint8)`, so Wan's slightly out-of-range VAE output wrapped around instead of clipping — a value of 1.004 became black. Conversion now clamps.
- **Frame Brightness Off by 1/255**: The tensor→bytes cast truncated rather than rounded, sending 0.999 to 254 and darkening every frame very slightly. Now rounds half-up, matching VideoHelperSuite. *(`core/video/encode_opts.py`)*
- **Colour Step Between Comparison Panels**: `xstack` does not reconcile inputs with different (or missing) colour tags, so a BT.601 clip beside a BT.709 one showed a visible seam. Each panel is now converted to BT.709 and the stacked result is tagged to match. *(`core/video_compare.py`)*
- **Audio Silently Dropped on Non-MP4 Output**: `mux_audio` always wrote its temp output as `.mp4` and always encoded AAC, so `-c:v copy` of a VP9 stream failed — and the failure was swallowed by a bare `except: pass`, yielding a silent video with no explanation. The temp container now follows the source, the codec is selectable, and failures are logged. *(`core/media_converter.py`)*
- **`audio_mode="replace"` Silently Ignored**: `nodes/output_handler.py` passed a mode `mux_audio` never defined, which fell through to `trim`. `replace` is now an explicit alias.
- **AUDIO Input Dropped When Encoding Images**: Connecting AUDIO to Save Video alongside an IMAGE batch produced a silent file, because the encode path never muxed it. The audio is now muxed in, honouring `trim_to_audio`. *(`nodes/save_video_node.py`)*
- **Load Video Path Legacy Workflow Values**: Inserting `enable_mask` mid-list would have shifted every later widget value by one in workflows saved before it existed (ComfyUI restores `widgets_values` positionally), landing `mask_mode` on the toggle, `mask_output_type` on `mask_mode`, and so on. `onConfigure` now detects the shift — a string in the BOOLEAN `enable_mask` is the tell — and slides the seven affected values back into place. Workflows predating `mask_mode` entirely fall short of that index, keep their defaults, and correctly skip the repair. *(`src/nodes/load_video_node.ts`)*
- **Stale Mask Overlay**: The Load Video Path preview no longer renders a leftover mask overlay when `enable_mask` is off but a saved `show_mask_preview` was `true`.

## [2.19.0] - 2026-03-21

### Added
- **DreamID-Omni (WIP)**: Identity-preserving talking-head video generation with speech. Takes a face image, reference audio, and text prompt to generate video of a person speaking with identity and voice preserved. Full vendored Alibaba DreamID-Omni framework with Wan2.2 Video VAE, MMAudio Audio VAE, T5 text encoder, and Fusion DiT. *(dreamid_omni no-LLM mode)*
  - ⚠️ Marked as **Work In Progress** — quality may be poor on low-VRAM GPUs due to aggressive memory optimizations.
  - **FP8 Native Matmul**: Patched 732 Linear layers for hardware-accelerated FP8 computation (`torch._scaled_mm`) with BF16 fallback for non-aligned dimensions.
  - **Sequential Layer Offloading**: 40 DiT block pairs offload CPU↔GPU per step (~1-2 GiB peak vs ~12 GiB full model).
  - **T5 Unload After Encoding**: Frees ~10 GB system RAM after text encoding, reloads on next generation.
  - **Streaming VAE Decode**: Decoded frames move to CPU immediately; feat_map cache offloads to CPU between frames. Prevents OOM during video decode on 12 GB GPUs.
  - **SageAttention Fallback**: Cascade: Flash Attention 3 → Flash Attention 2 → SageAttention → PyTorch SDPA.
  - **FP8 Conversion Script**: New `scripts/convert_dreamid_omni_precision.py` for creating FP8 model variants.
  - **10 Advanced Widgets**: `dreamid_precision`, `dreamid_resolution`, `dreamid_steps`, `dreamid_seed`, `dreamid_solver`, `dreamid_video_cfg`, `dreamid_video_ref_cfg`, `dreamid_audio_cfg`, `dreamid_audio_ref_cfg`, `dreamid_negative_prompt` — all dynamically shown only when `no_llm_mode = dreamid_omni`.
- **FaceCam Node**: New standalone portrait video camera control node powered by [FaceCam](https://github.com/weijielyu/FaceCam) (CVPR 2026). Uses 2+2 architecture: Wan2.2 14B GGUF base models + FaceCam bf16 partial checkpoints (self-attention + patch_embedding layers). Supports camera orbit, zoom, tilt presets with KSampler Advanced-style controls (add_noise, start/end step, return_with_leftover_noise) for multi-node chaining. Auto-downloads from AEmotionStudio/facecam-wan2.2-14b-bf16.
  - **Camera Presets**: Professional camera movement presets with detailed tooltips explaining each non-intuitive preset name.
  - **Auto Model Loading**: FaceCam HIGH and LOW models auto-load by default.
  - **Optional Auto-Download**: Configurable auto-download from HuggingFace with toggle control.
  - **Shard Merge Script**: New `scripts/merge_facecam_shards.py` for merging multi-shard model downloads.
- **Fish Speech TTS**: New Fish Audio S2 Pro integration for AI-powered text-to-speech with fine-grained prosody and emotion control. Supports 80+ languages, long-form TTS with sentence-aware chunking, voice cloning from 10-30s reference audio, inline emotion/prosody tags (`[whisper]`, `[excited]`, etc.), and multi-speaker mode. FP8 inference for ~12 GB VRAM on RTX 4070+. *(fish_speech no-LLM mode)*
- **Foundation-1 Music Samples**: New Foundation-1 integration for AI-powered music sample generation. Generates production-ready musical loops using Foundation-1 (fine-tuned on stable-audio-open-1.0). Supports text-to-sample with tempo-sync, key awareness, built-in presets for common instruments, and style transfer with configurable noise level. *(foundation1 no-LLM mode)*
- **Frame Picker Node**: New interactive frame selection and reordering node. Browse video frames via contact-sheet grid, select/deselect with click/shift+click/ctrl+click, reorder via drag-and-drop, bulk tools (Select All, Deselect All, Invert, Every Nth). Full TypeScript UI with filmstrip preview.
- **Load Last Image Node**: New node for loading the most recently generated image. Updated CSS and preview functionality.
- **Depth Shader Bridge**: New `core/depth_shader_bridge.py` — orchestrates Video Depth Anything depth prepass with SAM3 mask composition for depth-aware shader application. 5 depth modes: foreground_focus, background_focus, depth_outline, atmospheric, full_depth.
- **15 New GLSL Shaders**: `anime_glow`, `anime_pro`, `chromatic_prism`, `comic_book`, `depth_fog`, `depth_watercolor`, `focus_pull`, `neon_wireframe`, `pop_art`, `relief_sculpt`, `retro_dither`, `toon_3d`, `watercolor`, `watercolor_bleed`, `woodcut`. Total shader count: **70 shaders**.
- **Generate Sample Handler**: New `skills/handlers/generate_sample.py` for Foundation-1 music sample generation via LLM skill pipeline.
- **DreamID-Omni Technical Documentation**: New `docs/DREAMID_OMNI_STATUS.md` — comprehensive guide covering all 7 problems solved, solutions, current quality issues, performance numbers, and remaining work.
- **DreamID-Omni Tests**: New `tests/test_dreamid_omni.py` with 43 tests covering attention fallback cascade, FP8 matmul alignment, synthesizer wiring, no-LLM mode, model manager, and VRAM management.
- **FaceCam Tests**: New `tests/test_facecam.py` covering model detection, auto-download, preset loading, and node chaining.
- **Fish Speech Tests**: New `tests/test_fish_speech_synthesizer.py` covering model loading, voice cloning, TTS generation, and VRAM management.
- **Foundation-1 Tests**: New `tests/test_foundation1_synthesizer.py` covering model loading, sample generation, presets, and style transfer.
- **Frame Picker Tests**: New `tests/test_frame_picker.py` covering frame selection, reordering, bulk operations, and UI integration.
- **Depth Shader Tests**: New `tests/test_depth_shader.py` covering depth mode selection, VDA integration, and mask composition.

### Changed
- **Model Registry**: Added `dreamid_omni`, `dreamid_omni_fp8`, `facecam_high`, `facecam_low`, `fish_speech`, and `foundation1` entries to `core/model_manager.py` with sizes, HuggingFace repos, and download instructions.
- **VRAM Utils**: Added DreamID-Omni, FaceCam, Fish Speech, and Foundation-1 cleanup support.
- **Node Count**: Updated from 9 to **12 nodes** (added FaceCam, Frame Picker, Load Last Image).
- **Effects Node**: Expanded to 5 effect slots with parameter help in the UI.
- **Shader Overlay Node**: Enhanced with depth-aware shader modes and SAM3 mask integration.
- **Video Editor**: Shader panel integration, improved transport bar, audio timeline enhancements, and edit toolbar icons overhaul.
- **Install Script**: Updated `install.py` with dependencies for DreamID-Omni, FaceCam, Fish Speech, and Foundation-1.
- **SeedVR**: Updated model loader, GGUF ops, and model registry configuration.
- **Text Overlay Rendering**: Improved line break handling, Y-axis positioning, and newline character support.
- **Split Screen Output**: Output dimensions now match the largest input video instead of downscaling to fixed height.
- **Audio Processing**: Fixed sample rate mismatch for MP3 encoding and 1-second audio truncation when using audio-only effects.
- **Vite Config**: Updated build configuration for new Frame Picker and Load Last Image entry points.
- **Test Suite**: Expanded from 1,182 to **1,877 tests**, 0 failures.

### Fixed
- **DreamID-Omni OOM**: Multiple VAE decode OOM fixes — streaming frame decode, feat_map cache offloading, FP16 VAE activation, T5 model RAM unloading.
- **FP8 Matmul Alignment**: Fixed `RuntimeError: mat2 shape must be divisible by 16` in FP8 models — falls back to BF16 for non-aligned dimensions (e.g., audio Head with `out_dim=20`).
- **Flash Attention Assertion**: Replaced hard assertion `assert FLASH_ATTN_2_AVAILABLE` with SageAttention/SDPA fallback cascade.
- **Text Overlay Line Breaks**: Fixed newline characters rendering as rectangle glyphs; corrected Y-axis positioning for multi-line text.
- **Split Screen Dimensions**: Fixed output video downscaling to fixed 540px height; now uses largest input video dimensions.
- **Audio Sample Rate**: Fixed sample rate mismatch causing MP3 encoding failures with user-controlled resample option.
- **Audio Truncation**: Fixed 1-second audio truncation when processing audio-only effects by correcting dummy video handling.
- **Kiwi-Edit Synthesizer**: Fixed model cleanup and resource management.
- **NormalCrafter Synthesizer**: Fixed resource cleanup and model offloading.
- **Handler Imports**: Updated `skills/handlers/__init__.py` with new handler registrations.
- **Multi-Input Handler**: Improved split screen output dimension calculation for mismatched aspect ratios.
- **Upscale Handler**: Enhanced resource management and error handling.

---

## [2.18.0] - 2026-03-16

### Added
- **Kiwi-Edit Video Editing**: New AI-powered video editing using [Kiwi-Edit](https://github.com/showlab/Kiwi-Edit) (WAN 2.2-based). Text instruction, reference image, and combined modes. Supports FP8 (~5 GB) and BF16 (~10 GB) precision with automatic model download. Long video chunked processing with crossfade stitching. *(kiwi_edit no-LLM mode)*
  - **10 Advanced Widgets**: `kiwi_model`, `kiwi_precision`, `kiwi_resolution`, `kiwi_width`, `kiwi_height`, `kiwi_max_frames`, `kiwi_steps`, `kiwi_guidance`, `kiwi_block_swap`, `kiwi_long_video` — all dynamically shown only when `no_llm_mode = kiwi_edit`.
  - **4 New Model Options**: `kiwi_seed` (reproducibility), `kiwi_flow_shift` (denoising aggressiveness 1–15), `kiwi_task_type` (override auto-detected prompt enhancement), `kiwi_scheduler` (unipc/euler/heun/dpm++ sampling).
  - **SAM3 Toggle for Kiwi-Edit**: SAM3 pre-masking now available for `kiwi_edit` mode — generate a mask with SAM3, process with Kiwi-Edit, composite back. Backend was already wired; UI toggle was missing.
  - **FP8 Conversion Script**: New `scripts/convert_kiwi_edit_fp8.py` for creating FP8 scaled model variants.
  - **Task-Type Prompt Enhancement**: 5 task templates (global_style, local_change, background_change, local_remove, local_add) with temporal consistency hints. Overridable via `kiwi_task_type` widget.
  - **Runtime Scheduler Selection**: New `_set_scheduler()` function allows switching schedulers between runs without reloading the model pipeline.
- **RTX Video Super Resolution**: New NVIDIA RTX VSR AI upscaling using Video Effects SDK (nvvfx). Hardware-accelerated on RTX Tensor Cores for near-real-time performance. Three quality modes: upscale, denoise, deblur. Requires RTX GPU + NVIDIA driver 570+. *(rtx_vsr no-LLM mode)*
- **SeedVR AI Upscaling**: New SeedVR 2 integration for high-quality video upscaling. Vendored core with diffusion pipeline, alpha upscaling, and model caching. Supports 3B and 7B model variants. *(seedvr no-LLM mode)*
- **Expression Presets for FacePoke**: New `core/expression_presets.py` with predefined facial expression parameter sets for the FacePoke interactive face editor.
- **Multi-Input Skill Handler**: New `skills/handlers/multi_input.py` for concat, grid, split screen, and multi-input operations with proper FFmpeg filter chain orchestration.
- **Kiwi-Edit Model Mirror**: Weights hosted on AEmotionStudio HuggingFace repos with mirror-first download and upstream fallback.
- **Kiwi-Edit Tests**: New `tests/test_kiwi_edit.py` with 50 tests covering constants, model manager, cleanup, no-LLM mode, prompt enhancement, and path validation.

### Changed
- **Model Registry**: Added `kiwi_edit_instruct`, `kiwi_edit_reference`, `kiwi_edit_instruct_reference`, `rtx_vsr`, and `seedvr` entries to `core/model_manager.py`.
- **VRAM Utils**: Added Kiwi-Edit, RTX VSR, and SeedVR cleanup support.
- **Conditional Widget Visibility**: `kiwi_width` and `kiwi_height` are now hidden unless `kiwi_resolution = 'custom'`. Scheduler dropdown triggers visibility refresh.
- **Version**: Bumped to 2.18.0.

### Fixed
- **Kiwi-Edit BF16 Precision**: Fixed dtype handling for BF16 model loading that previously caused errors on some GPU configurations.
- **SAM3 UI Toggle**: Fixed `kiwi_edit` mode not appearing in the SAM3-eligible modes list in the TypeScript UI, preventing the `use_sam3` toggle from showing.

---

## [2.17.0] - 2026-03-15

### Added
- **FacePoke Interactive Face Editor**: New full-featured face editing modal powered by LivePortrait. Edit facial expressions in real-time with slider controls for 16 parameters (pitch, yaw, roll, blink, eyebrow, smile, pupil, mouth shapes), per-frame editing with undo/redo, filmstrip frame scrubber with frame numbers and hover-scrolling, emotion presets (happy, sad, angry, surprised, wink, thoughtful, neutral), face landmark visualization, and Blaze Detect fallback mode. Professional SVG icon library throughout.
  - **Driving Video Reference**: Upload a driving video to transfer facial motion across all source frames. Relative motion with configurable multiplier (0.1–2.0x). Server-side keypoint extraction and caching.
  - **Reference Image Expression**: Upload a face image to transfer its expression to any frame. Configurable ratio (0–1), parts selection (all, mouth only, eyes only, rotation only), and slider edits stack on top.
  - **Face Detection Caching**: Face bounding boxes cached per-frame on first detection, reused for subsequent previews and edits. Eliminates redundant face detection when no changes have been made.
  - **Improved Paste-Back Quality**: Replaced naive 256px downscale paste-back with proper `_paste_back` function using full 512×512 model output, LANCZOS4 interpolation, and tightened blending mask (ellipse 235×250, kernel 51×51).
- **Shader Effects System**: Extensive GPU-accelerated shader overlay system with shader chaining (up to 3 layers), animation speed control, hue shift, customizable blend modes, temporal phase offset, JSON parameter overrides, resolution scaling, and random shader selection mode.
- **Multi-Input Skill Handler**: New `multi_input.py` handler for concat, grid, split screen, and other multi-input operations with proper FFmpeg filter chain orchestration.
- **Onion Skin Compositing**: Onion skin no-LLM mode now auto-detects extra video inputs and switches to composite mode, building multi-input FFmpeg `blend` filter pipelines.
- **Flux Klein FP8 Model**: New FP8 variant dropdown for Flux Klein — ~50% VRAM reduction with per-tensor scaling for quality preservation.
- **Audio Output Mode**: Generalized `audio_output_mode` parameter across all audio processing nodes (`generate_audio`, `generate_music`, `audio_inpaint`, `ace_step`, `audio_separate`) with `auto` and `save_only` options.
- **SAM3 Toggle**: New toggleable SAM3 control in the UI for easier masking workflow management.
- **Marigold Appearance Mode**: New `appearance` estimation mode for Marigold dense vision pipeline.
- **New Visual Skills**: Added `hdr_enhancement` and related visual effect skills to the skill registry.

### Changed
- **LivePortrait Expression Range**: Increased pitch/yaw/roll multipliers for much more pronounced head movement, matching KiJai's implementation. Fixed independent left/right eye and eyebrow controls.
- **FacePoke UI Polish**: Removed all emojis and replaced with professional Lucide SVG icons. Added frame count numbers to filmstrip thumbnails. Made filmstrip frames scrollable on hover. Added first/last frame jump buttons.
- **Video Editor**: Updated segment management and transport controls. Improved SAM3 toggle integration.
- **Drop Animation UX**: Increased drag-and-drop upload feedback timeout from 100ms to a longer duration for reliable visual feedback across all nodes.
- **Node Widget Visibility**: Dynamic widget visibility improvements for shader, SAM3, and audio mode controls.

### Fixed
- **FacePoke Blur**: Fixed severe blur in modified faces caused by 512→256px downscaling during paste-back. Now preserves full model resolution.
- **FacePoke Blaze Fallback**: Changed from auto-fallback (too sensitive) to manual-only toggle, preventing incorrect model selection.
- **LivePortrait Left/Right Controls**: Fixed independent eye and eyebrow controls (left/right split) that previously only worked in "both" mode.
- **Animate Portrait Tests**: Updated test assertions for new parameter signatures.
- **Audio Handler Consistency**: Aligned `audio_output_mode` parameter naming across all audio generation/processing handlers.

---

## [2.16.0] - 2026-03-13

### Added
- **ACE-Step AI Music Generation**: New ACE-Step 1.5 integration for AI-powered music generation and audio repainting directly within ComfyUI. Supports text-to-music, style-guided cover/repaint of existing audio tracks, and automatic lyrics generation via ACE-Step's 1.7B language model. *(ace_step no-LLM mode)*
  - **7 Advanced Widgets**: `ace_negative_prompt`, `ace_cover_strength`, `ace_steps`, `ace_cfg_scale`, `ace_bpm`, `ace_key`, `ace_time_sig` — all dynamically shown only when `no_llm_mode = ace_step` with advanced options enabled.
  - **Auto Lyrics Generation**: When no manual lyrics are provided via `text_a`, ACE-Step's LM auto-generates structured lyrics with section markers (`[verse]`, `[chorus]`) from the prompt.
  - **Reference Audio**: Connect any audio to `audio_a` — automatically detected and used as style reference for ACE-Step generation.
  - **BPM/Key/Time Signature Control**: User-specified musical metadata injected into the LM's chain-of-thought generation for precise control over rhythm, key, and meter.
  - **Cover/Repaint Mode**: When a video has audio but no prompt is given, ACE-Step repaints the existing audio with configurable `cover_strength` (0.0 = preserve original, 1.0 = full creative freedom).
- **SAM-Audio Source Separation**: New AI-powered audio source separation using SAM-Audio (Separate Anything in Audio). Splits audio into stems (vocals, drums, bass, other) with component-level VRAM offloading. Supports `large` and `large-fp8` variants with automatic model download. *(audio_separate no-LLM mode)*
  - **FP8 Scaled Variant**: Custom FP8 conversion of SAM-Audio large model (~50% VRAM reduction) with per-tensor scaling factors for inference quality preservation.
  - **Component Offloading**: Individual model components (encoder, separator, decoder) loaded/unloaded sequentially to minimize peak VRAM usage.
- **AudioX Vocal Enhancement**: New AudioX integration for AI-powered vocal enhancement, speech restoration, and audio quality improvement. Processes audio through a transformer-based enhancement model with automatic VRAM offloading. *(audiox no-LLM mode)*
  - **Standalone No-LLM Mode**: New `audiox` option in the `no_llm_mode` dropdown — enhance audio directly without an LLM.
  - **ACE-Step Chaining**: When both AudioX and ACE-Step are enabled, AudioX output is automatically fed to ACE-Step for one-click music upgrading.
  - **Model Mirror**: Weights hosted on [AEmotionStudio/audiox](https://huggingface.co/AEmotionStudio/audiox) with mirror-first download and upstream fallback.
- **AI Music Generation Skill (`generate_music`)**: New `generate_music` skill with handler for LLM-driven music generation via ACE-Step. Registered with 8 aliases (`make_music`, `compose_music`, `create_music`, `music_gen`, `ai_music`, `music_ai`, `compose_audio`, `make_audio`).
- **Audio Inpainting Skill (`audio_inpaint`)**: New `audio_inpaint` skill for AI-powered audio repair and enhancement using AudioX/ACE-Step pipeline.
- **Video Editor v2 — 10 New Panels**: Major NLE video editor expansion with 10 new editing panels:
  - **Color Grading Panel**: Exposure, contrast, saturation, temperature, tint, highlights, shadows, vibrance controls with real-time FFmpeg filter preview.
  - **Filters Panel**: Collection of filter presets (Warm, Cool, Vintage, Noir, Vivid, Dramatic, Pastel, Sepia, Cross Process, Bleach Bypass) with one-click application.
  - **Keyframe Editor**: Per-segment keyframe animation for speed and volume with visual keyframe tracks. Supports ease-in/out interpolation.
  - **Relight Panel**: AI-powered scene relighting using IC-Light with configurable prompt, strength, guidance scale, steps, and background modes.
  - **Transform Panel**: Scale, rotate, flip, position controls with FFmpeg filter chain generation.
  - **Compositing Panel**: Picture-in-Picture, watermark, blend modes, chroma key, vignette, and mask compositing tools.
  - **AI Compose Panel**: AI-powered composition suggestions and automatic edit generation.
  - **Captions Panel**: Text overlay and subtitle editing with position, timing, font, and style controls.
  - **Export Settings Panel**: Detailed export configuration with resolution, codec, CRF, preset, format, and audio settings.
  - **Speed Control**: Dedicated speed adjustment tool with preset buttons and custom value input.
- **NLE Audio Repaint Region**: Per-segment ACE-Step audio repaint toggle and strength control in the AudioMixer panel. Mark individual audio segments for AI repainting with adjustable strength (0–100%).
- **NormalCrafter Surface Normal Estimation**: New AI-powered surface normal estimation from video using [NormalCrafter](https://github.com/Binyr/NormalCrafter). Generates temporally consistent normal maps from monocular video with configurable max resolution. Supports SVD-based architecture with automatic model download. *(normalcrafter no-LLM mode)*
  - **`normalcrafter_max_res` Widget**: Configurable maximum resolution for NormalCrafter inference, shown only when `normalcrafter` mode is active.
  - **Model Mirror**: Weights hosted on [AEmotionStudio/NormalCrafter](https://huggingface.co/AEmotionStudio/NormalCrafter) for supply chain resilience.
- **Video Depth Anything**: New AI-powered temporal video depth estimation using [Video Depth Anything](https://github.com/DepthAnything/Video-Depth-Anything). Generates consistent depth maps from monocular video with three model variants (`vits`, `vitb`, `vitl`). Features configurable encoder selection and colormap output. *(video_depth no-LLM mode)*
  - **`video_depth_encoder` Widget**: Select model variant (small/base/large) based on VRAM/quality tradeoff, shown only when `video_depth` mode is active.
  - **`video_depth_colormap` Widget**: Choose depth visualization colormap (Spectral, Inferno, etc.).
  - **Model Mirror**: Weights hosted on [AEmotionStudio/video-depth-anything](https://huggingface.co/AEmotionStudio/video-depth-anything).
- **Dynamic Widget Visibility Improvements**: `sam_audio_model` and `normalcrafter_max_res` widgets now conditionally visible only when their respective no-LLM modes are active, reducing UI clutter.
- **Install Scripts**: New `install-all-deps.sh` and `install-all-deps.bat` for one-command installation of all optional dependencies (torchaudio, accelerate, rembg, etc.).
- **Optional Requirements**: New `requirements-optional.txt` organizing optional dependencies by feature area (ACE-Step, SAM-Audio, AudioX, IC-Light, etc.).

### Changed
- **Model Registry**: Added `sam_audio`, `sam_audio_fp8`, `audiox`, and `acestep` entries to `core/model_manager.py` with sizes, HuggingFace repos, and download instructions.
- **VRAM Utils**: Enhanced `_vram_utils.py` with SAM-Audio and ACE-Step cleanup support.
- **Video Editor Export Pipeline**: Integrated color grading, filter presets, keyframe-based speed/volume, relighting, transforms, compositing, and caption rendering into the FFmpeg export pipeline with proper filter chain orchestration.
- **Node Widget Count**: Agent node now features 7 additional ACE-Step input widgets under the advanced toggle.
- **AudioSegment Data Model**: Extended with `aceRepaint` and `aceRepaintStrength` fields for per-segment AI audio repaint marking, with full serialize/deserialize support.

### Fixed
- **ACE-Step Fallback Test**: Fixed `test_fallback_when_no_acestep` by mocking `is_available` to return `False` now that ACE-Step is installed.
- **Audio Segment Init**: All `AudioSegment` creation paths now include the new `aceRepaint` fields, preventing TypeScript compilation errors.
- **Keyframe Application**: Wired keyframe application into the export pipeline to prevent no-op keyframes.
- **Blend Compose Skip Log**: Added skip log for blend compose mode when no blend target is specified.

---

## [2.15.0] - 2026-03-09

### Added
- **MiniMax-Remover Integration**: New toggleable AI object removal powered by [MiniMax-Remover](https://github.com/zibojia/MiniMax-Remover). Purpose-built DiT model for video inpainting with 81-frame batch processing and sliding-window support for longer videos. ~2.5 GB model, significantly lighter than FLUX Klein (~15 GB). ⚠️ Model weights are CC-BY-NC-4.0 (non-commercial); code is Apache 2.0. *(PR #161)*
  - **Tiered Removal Priority**: New removal hierarchy — MiniMax-Remover (highest, when `use_minimax_remover=On`) → FLUX Klein (when `use_flux_klein=On`) → LaMa → black fill (FFmpeg). Each tier automatically falls back to the next if disabled or unavailable.
  - **`use_minimax_remover` Toggle**: New node-level boolean toggle on the FFMPEG Agent. Threaded through all pipeline paths (LLM, effects builder, batch, SAM3-only) via `_enable_minimax_remover` metadata key. Defaults to `False`.
  - **`minimax_remover` No-LLM Mode**: New `minimax_remover` option in the `no_llm_mode` dropdown — run MiniMax-Remover directly without an LLM. Uses SAM3 for mask generation with full-frame fallback.
  - **Vendored Core Components**: `pipeline_minimax_remover.py` and `transformer_minimax_remover.py` vendored into `core/minimax/` with attribution headers citing the original [MiniMax-Remover repository](https://github.com/zibojia/MiniMax-Remover) and paper.
  - **Sliding-Window Batching**: Videos exceeding 81 frames are processed in overlapping windows with configurable overlap (default 8 frames) and temporal smoothing (Gaussian/adaptive) for seamless transitions.
  - **VRAM Management**: Explicit model loading/unloading with `gc.collect()` + `torch.cuda.empty_cache()`. Other models (FLUX Klein, LaMa) are freed before loading MiniMax-Remover.
  - **Model Mirror**: Weights mirrored to [AEmotionStudio/minimax-remover](https://huggingface.co/AEmotionStudio/minimax-remover) with mirror-first download and upstream fallback.
- **AI Upscaler `tile_size` Parameter**: New `tile_size` parameter for AI upscaling — forwarded through no-LLM mode and LLM skill paths. Enables fine-grained VRAM control via configurable upscaler tile dimensions.
- **Auto-VRAM Tile Sizing**: AI upscaler automatically calculates optimal tile size based on available VRAM and model memory budget, eliminating manual tuning for different GPUs.
- **Upscaler Disk Space Pre-Check**: Disk space validation before video frame extraction prevents failures mid-render on low-storage systems.
- **Video Depth Anything License**: Added Apache 2.0 license file for the vendored Video Depth Anything module. *(commit cec11e7)*
- **5 New No-LLM Modes**: Added `ai_upscale`, `video_depth`, `flux_klein`, `minimax_remover`, and `animate_portrait` to the `no_llm_mode` dropdown — run each AI backend directly without an LLM.
- **MiniMax-Remover Tests**: New `tests/test_minimax_remover.py` with 26 tests covering constants, model manager, cleanup, no-LLM mode registration, toggle, auto_mask priority, metadata propagation, and vendored imports.

### Changed
- **Model Registry**: Added `minimax_remover` to `core/model_manager.py` with size, HuggingFace repo, license (CC-BY-NC-4.0 for weights), and manual download instructions.
- **FFmpeg Binary Path Consolidation**: Centralized all `_get_ffmpeg_bin()` and `_get_ffprobe_bin()` wrappers across `lama_inpainter.py`, `upscaler.py`, `vda_synthesizer.py`, and `marigold_synthesizer.py` into direct imports from `core/bin_paths.py`. Eliminates duplicated wrapper functions.
- **VRAM Cleanup Overhaul**: Refactored VRAM cleanup across all synthesizers — pipelines are now transferred to CPU before cleanup, only loaded modules are processed, and redundant `torch.cuda.synchronize()` / `gc.collect()` calls removed. Reduces cleanup overhead and prevents VRAM fragmentation.
- **Upscaler Image I/O**: Switched upscaler frame reading/writing from PIL to OpenCV for consistency with other synthesizers and better performance.
- **Upscaler 1-Based Frame Indexing**: Frame numbering now starts at 1 to align with ffmpeg's extraction output, ensuring correct frame ordering.
- **Visual Skill Caching**: AI-powered visual skill cache keys now include the model name, preventing stale cache hits when switching between AI backends.
- **LoadVideoPathNode Output Reorder**: Reordered `LoadVideoPathNode` outputs for more logical grouping; added `crop_data` at index 5.
- **Sidebar Docs**: Updated performance tips and widget documentation to include MiniMax-Remover.
- **CI Coverage Threshold**: Lowered from 34% to 25% to account for torch-dependent tests being skipped in CI.
- **Test Suite**: Expanded from 1,131 to **1,182 tests**, 0 failures.

### Fixed
- **VRAM Cleanup Style**: Refactored `flux_klein_editor._free_vram()` from 9 individual import+cleanup blocks to a loop-over-list pattern, matching the style used in all other synthesizers. Prevents missed modules when adding new AI backends.
- **Upscaler Audio Mux Path**: Fixed `upscale_video` audio mux using `str.replace(".mp4", ...)` which could corrupt paths containing `.mp4` in directory names or non-MP4 extensions. Now uses `Path.with_suffix()`.
- **Video Editor WAV Parsing**: Fixed `_extract_audio()` WAV `data` chunk search starting at byte 0, which could false-match metadata fields. Now starts at byte 12 (past RIFF/WAVE header).
- **Video Editor Auto-Resume**: Guarded `app.queuePrompt()` calls to only resume when `pause_on_input` is enabled, preventing unexpected re-execution when the editor is used outside the pause flow.
- **AI Upscale Temp Copy**: Eliminated redundant temp directory creation in `process_ai_upscale_only` — copies directly from upscaler output to final path.
- **Video Dimension Padding**: FFmpeg output dimensions are now padded to even values, preventing pixel misalignment errors with `libx264` on odd-resolution sources.
- **FFmpeg Framerate Compatibility**: Framerate values are now formatted as integers or two-decimal strings, fixing compatibility issues with certain ffmpeg builds that reject full-precision floats.
- **Mask Padding Robustness**: MiniMax-Remover mask padding now copies PIL Image objects before resizing, preventing mutation of shared image references.
- **Mask Fallback Resolution**: MiniMax-Remover fallback mask resolution dynamically uses the video frame size instead of a hardcoded 640×480.
- **VRAM Module Lookup**: `_vram_utils.py` now correctly handles modules loaded under ComfyUI's package structure when resolving `sys.modules` entries.
- **Video Editor Input Priority**: Changed from `images > video_path` to `video_path > images` to match `LoadVideoPathNode` behavior.
- **CI Torch Import Skips**: Added `pytest.importorskip("torch")` guards to all tests importing from `nodes.*` or `core.minimax.*`, preventing `ModuleNotFoundError` in CI environments without PyTorch.

## [2.14.0] - 2026-03-08

### Added
- **Video Editor Node**: New interactive NLE (Non-Linear Editor) node for hands-on video editing directly inside ComfyUI. Features a full-screen modal with timeline, transport controls, and editing tools — no LLM required. *(PR #155)*
  - **Timeline Editing**: Visual timeline with drag-to-select, razor tool (split at playhead), and segment deletion. Undo/redo with `Ctrl+Z` / `Ctrl+Shift+Z`.
  - **Speed Control**: Per-segment speed adjustment (0.25×–4×) with `setpts`/`atempo` filter chaining for values outside FFmpeg's native 0.5–2.0 range.
  - **Volume & Mute**: Per-segment volume control (0–200%) and mute toggle via `volume` audio filter.
  - **Crop Tool**: Interactive crop overlay with drag handles and real-time preview. Applies FFmpeg `crop` filter on export.
  - **Text Overlays**: Add positioned text with configurable font size, color, and timing via FFmpeg `drawtext` filter. Correct escaping for colons, backslashes, and special characters.
  - **Transitions**: Crossfade and dip-to-black transitions between segments using FFmpeg `xfade`/`acrossfade` filters. Configurable duration per transition.
  - **Multi-Stage Render Pipeline**: Exports through trim → speed → transitions → text overlay → crop → audio stages, with `cancel_event` threading for clean cancellation of long renders.
  - **Keyboard Shortcuts**: Space (play/pause), J/K/L (shuttle), I/O (mark in/out), Left/Right (frame step), R (razor), V (select), Delete, and more. `?` opens shortcut overlay.
- **Seekable MP4 Preview Server**: New `/ffmpega/preview` route with HTTP Range support, `mtime`-based cache keys, and LRU in-memory caching for instant video previews in the editor. *(PR #155)*
- **Shared `images_to_video` Utility**: New `core/images_to_video.py` extracts the image-tensor-to-video conversion into a reusable function, eliminating duplication across `VideoEditorNode` and `VideoToPathNode`. *(PR #155)*
- **Shared UI Helpers**: Extracted common upload, drag-and-drop, and UI utility code from `ffmpega_ui.js` into `web/ui_helpers.js` for reuse across nodes. *(PR #155)*
- **Video Editor Tests**: New `tests/test_video_editor.py` with 40+ tests covering segment parsing, speed filter building, volume filters, text overlay escaping, crop filter generation, transition building, and cache logic. *(PR #155)*

### Changed
- **TypeScript Migration**: Video Editor frontend built in TypeScript (`src/videoeditor/*.ts`) with Vite build pipeline. Compiled bundles committed to `web/` per ComfyUI extension convention. *(PR #155)*
- **Node Count**: Updated from 8 to **9 nodes** (added Video Editor).
- **Test Suite**: Expanded from 952 to **1,056 tests**, 0 failures.

---

## [2.13.0] - 2026-03-06

### Added
- **FLUX Klein Toggle (`use_flux_klein`)**: New node-level boolean toggle to enable/disable FLUX Klein 4B inference. Threaded through all 5 pipeline paths (LLM, effects builder, batch, SAM3-only, whisper-only) via `_enable_flux_klein` metadata key. Defaults to `False` for zero-VRAM baseline. *(PR #150)*
- **Edit FFmpeg Fallback (`_edit_ffmpeg_fallback`)**: When FLUX Klein is disabled, `auto_mask:effect=edit` now falls back to keyword-matched FFmpeg color/tone filters (22 keywords across 12 color + 10 tone categories) applied via `maskedmerge`. Uses word-boundary regex matching to prevent false positives. Zero VRAM. *(PR #150)*
- **AI Background Removal (`remove_background`)**: Full per-frame implementation using [BRIA RMBG](https://huggingface.co/briaai/RMBG-2.0) via `rembg`. Extracts frames with OpenCV, generates alpha masks, writes a lossless FFV1 mask video, and composites via FFmpeg `maskedmerge` or `alphamerge` (transparent mode). New `background` parameter supports `transparent` or any color name/hex for solid-color replacement. *(PR #146)*
- **Background Removal Model Choices**: Expanded `remove_background` model selection from 3 choices (`silueta`, `u2net`, `isnet`) to 6 choices (`bria-rmbg` default, `birefnet-general`, `birefnet-general-lite`, `isnet-general-use`, `u2net`, `silueta`). *(PR #146)*

### Fixed
- **FLUX Klein Cache Coherence**: Cache reuse for FLUX Klein outputs is now gated by the `_enable_flux_klein` toggle — prevents stale AI outputs from being used when the user switches to FFmpeg fallback mode. *(PR #150)*
- **`remove` Effect Fallback**: When FLUX Klein is disabled, `auto_mask:effect=remove` falls back to LaMa inpainting instead of attempting FLUX Klein inference. *(PR #150)*

### Changed
- **Resource Stewardship Defaults**: `use_vision` and `verify_output` defaults changed from `True` to `False` across `agent_node.py` and `batch_processor.py`. High-resource features are now opt-in, reducing token usage and processing time by default. *(PR #150)*
- **`import re` Cleanup**: Hoisted `import re` from function-level to module-level in `visual.py`, removing duplicate imports. *(PR #150)*
- **♿ Mask Editor Accessibility**: Mask Editor buttons (`modeToggle`, `clearBtn`, `applyBtn`, `cancelBtn`) now wrap emojis in `<span aria-hidden="true">` and set explicit `aria-label` attributes — prevents screen readers from announcing decorative icons. *(PR #148)*
- **AI-Powered Skills Count**: Updated from 6 to 7 (added `remove_background` with BRIA RMBG).
- **Model Registry**: Updated `remove_background` model entry from U²-Net (~170 MB) to BRIA RMBG (~270 MB).
- **Test Suite**: Expanded from 939 to **952 tests**, 0 failures.

---

## [2.12.0] - 2026-03-06

### Added
- **AI Face Animation (`animate_portrait`)**: New skill powered by [LivePortrait](https://github.com/KlingAIResearch/LivePortrait) — transfers facial motion from a driving video onto a source portrait. Uses appearance feature extraction, motion keypoints, stitching/retargeting, and a SPADE generator for high-quality output. Supports both image and video sources with per-frame face detection, affine crop/paste-back with elliptical Gaussian-blurred blending, relative motion mode, and configurable driving multiplier. In-process inference with automatic GPU↔CPU offloading. 7 aliases (`live_portrait`, `face_animate`, `face_animation`, `face_reenact`, `puppet`, `face_swap_video`, `motion_transfer`).
- **LivePortrait No-LLM Mode (`animate_portrait`)**: New `animate_portrait` option in the `no_llm_mode` dropdown — animates a face directly without any LLM. Source face from `video_path`/`images_a`, driving video from `video_a`. Full zero-prompt support.
- **LivePortrait Model Mirror**: 5 model weights (appearance extractor, motion extractor, warping module, SPADE generator, stitching/retargeting) converted from `.pth` to `.safetensors` and hosted on `AEmotionStudio/liveportrait-models` (~497 MB total). Mirror-first download with automatic fallback to upstream `.pth` files.
- **LivePortrait Tests**: New `tests/test_animate_portrait.py` with 30 tests covering skill registration, model manager integration, handler dispatch, aliases, synthesizer functions, and no-LLM mode wiring.
- **LaMa Safetensors Conversion**: Converted `big-lama.pt` (TorchScript JIT) to `big-lama.safetensors` (194.9 MB, 989 tensors) — eliminates pickle warnings and security flags on HuggingFace. `lama_inpainter.py` updated to prefer safetensors with graceful `.pt` fallback.

### Fixed
- **MediaPipe `mp.solutions` Crash**: `_detect_face_bbox` in LivePortrait was using the deprecated `mp.solutions.face_detection` API (removed in newer MediaPipe). Replaced with the existing `musetalk.face_detection.get_face_bbox()` which uses the Tasks API (`FaceLandmarker`).
- **LivePortrait RGB/BGR Mismatch**: Model output is RGB but canvas is BGR — added `cv2.cvtColor(out, cv2.COLOR_RGB2BGR)` in `_warp_decode` to fix discolored output.
- **LivePortrait Paste-Back Affine Transform**: Fixed broken 512→canvas affine math in `_paste_back` — was multiplying rotation/scale by 2 instead of dividing (for affine `y = (A/2)·x₅₁₂ + b`).
- **LivePortrait Box Outline**: Replaced 20px rectangular feather mask with elliptical Gaussian-blurred mask (220×240 semi-axes, 101×101 kernel) for seamless face blending.

### Changed
- **LaMa Model Registry**: Updated `model_manager.py` mirror filename from `big-lama.pt` to `big-lama.safetensors`.
- **AI-Powered Skills Count**: Updated from 5 to 6 (added `animate_portrait`).
- **Test Suite**: Expanded from 909 to **939 tests**, 0 failures.

---

## [2.11.0] - 2026-03-05

### Added
- **MMAudio In-Process Inference**: Migrated MMAudio audio generation from subprocess isolation to in-process execution with full GPU↔CPU offloading. Eliminates subprocess overhead while maintaining VRAM safety. Subprocess fallback preserved for edge cases.
- **`generate_audio` No-LLM Mode**: New `generate_audio` option in the `no_llm_mode` dropdown — synthesize audio from video content and/or text prompt directly without an LLM.
- **MCP Progressive Disclosure**: MCP tool discovery now uses progressive disclosure — `list_tools` returns summarized tool info, `get_tool_details` provides full schemas on demand. Reduces initial context window pressure. *(PR #144)*
- **MCP New Tools**: Added `validate_skill_params` and `cleanup_vision_frames` tool definitions with path-traversal guards. `analyze_video` gains input validation guard. *(PR #144)*
- **CLI Binary Resolution Caching**: All CLI connector binary lookups (`gemini`, `claude`, `cursor-agent`, `qwen`) now use `@functools.cache` — eliminates repeated `shutil.which()` calls on every invocation. *(PR #143)*

### Fixed
- **Lip Sync Filter Composition**: Fixed FFmpeg filter chain not correctly applying video filters (denoise, color correction, etc.) to the lip-synced output. Filters now correctly chain through the output labels generated by the `lip_sync` skill.
- **FLUX Klein Memory**: Optimized FLUX Klein memory usage — explicit `gc.collect()` per frame, runtime assertions in `_encode_video_from_dir`, freed `mask_np_list` after temporal smoothing pass.
- **MCP Dispatch**: Fixed `call_tool` dispatch dictionary and `detail` parameter documentation for `execute_code`. Propagated `analyze_video` in-band errors and `cleanup_vision_frames` return value. Added `video_path` to tool definition schemas. *(PR #144)*
- **FFmpeg Binary Wrappers**: Consolidated duplicate `_get_ffmpeg_bin` wrappers across modules, increased chunk timeout for large video processing.
- **CI**: Skip no-LLM-mode tests when torch is unavailable in CI environment.

### Changed
- **Focus Accessibility**: Improved focus visibility for interactive widgets across the UI — consistent focus rings and keyboard navigation. *(PR #142)*
- **MCP Architecture**: Dispatch table derived from `_tools` dict instead of separate mapping. Minor cleanups and input_examples added to schemas. *(PR #144)*
- **Test Suite**: Expanded from 799 to **909 tests**, 0 failures.

---

## [2.10.0] - 2026-03-04

### Added
- **FLUX Klein In-Process Migration**: Migrated FLUX Klein 4B from subprocess to in-process inference with managed VRAM offloading. Eliminates subprocess overhead while maintaining memory safety via explicit model loading/unloading.
- **Mask Drawing UI**: New interactive mask drawing overlay — paint masks directly on video frames for targeted AI editing (remove/edit effects). Integrates with the SAM3 and FLUX Klein pipelines.
- **Model Output Caching**: FLUX Klein caches model outputs for identical inputs — avoids redundant inference when re-processing the same frame.

### Fixed
- **Green Overlay Accumulation**: Fixed colored overlay mask accumulating across frames in multi-frame SAM3 processing.
- **`force_rate` No-Op Guard**: Added guard to prevent `force_rate=0` from triggering unnecessary re-encoding.
- **Mask Dimension Guard**: Added explicit dimension validation for masks — `assert` replaced with `raise RuntimeError` for clearer error messages.
- **Circular Erase Clipping**: Fixed circular erase tool clipping at canvas boundaries.
- **Thermal Constant Deduplication**: Removed shadowed local variables and deduplicated thermal decay constant.
- **`__init__.py` ImportError**: Fixed `ImportError` during test collection caused by missing conditional imports.

### Performance
- **FFmpeg/FFprobe Path Caching**: Cached ffmpeg and ffprobe binary path resolution in the analyzer module — avoids repeated filesystem lookups on every invocation. *(PR #139)*
- **Consolidated Path Resolution**: Unified ffmpeg/ffprobe path caching into `core/bin_paths.py` with `@functools.cache` decorator.

### Changed
- **Focus Ring Accessibility**: Improved focus ring visibility for point selector buttons — clearer keyboard navigation indicators. *(PR #138)*
- **Relative Imports**: Switched `bin_paths` module to relative imports for consistency with the rest of the codebase. Added fallback imports for `get_ffprobe_bin`.
- **Test Suite**: Expanded from 799 to **829 tests**, 0 failures.

---

## [2.9.1] - 2026-03-03

### Added
- **AI Object Removal & Editing (`auto_mask:effect=remove|edit`)**: New FLUX Klein 4B integration for AI-powered per-frame object removal and text-guided video editing. Replaces LaMa for the `remove` effect with higher-quality FLUX Klein inpainting. New `edit` effect enables text-guided changes (e.g. "change hair to red", "replace background with beach"). Uses reference-image conditioning with 4-step inference, temporal smoothing, and fixed seeding for cross-frame consistency. ~8–13 GB VRAM (fp16/bf16 with CPU offload).
- **`edit_prompt` Parameter**: New `edit_prompt` parameter on `auto_mask` skill for describing desired text-guided edits when `effect=edit`.
- **FLUX Klein Model Mirror**: fp16 `.safetensors` weights hosted on `AEmotionStudio/flux-klein`. Mirror-first download with upstream BFL fallback.
- **FLUX Klein Tests**: New `tests/test_flux_klein.py` with 16 tests covering constants, model directory, cleanup, model manager integration, and skill registration.
- **AI Audio Generation (`generate_audio`)**: New skill powered by MMAudio (CVPR 2025) — synthesizes synchronized audio/foley from video content and/or text descriptions. Supports video-to-audio, text-to-audio, and long video handling with automatic chunking and crossfade. 11 natural language aliases (`foley`, `sound_effects`, `mmaudio`, `v2a`, etc.).
- **AI Lip Sync (`lip_sync`)**: New skill powered by MuseTalk V15 — synchronizes lip movements in video with provided audio. Supports both video+audio and image+audio inputs, multi-face detection, and batch inference. Zero new pip dependencies — uses existing diffusers, transformers, and mediapipe packages. 7 aliases (`lipsync`, `dub`, `dubbing`, `sync_lips`, `talking_head`, `lip_dub`, `voice_sync`). Subprocess isolation for CUDA memory safety.
- **MMAudio Subprocess Isolation**: Audio generation runs in a subprocess to prevent CUDA memory leaks — same pattern as SAM3. Falls back to in-process generation with proper VRAM offloading if subprocess fails.
- **Native Safetensors Loading**: MMAudio synthesizer uses `comfy.utils.load_torch_file` for direct `.safetensors` loading — no more `.pth` conversion round-trip. Falls back to `safetensors.torch.load_file` or `torch.load` if ComfyUI API unavailable.
- **Memory-Efficient Model Init**: Uses `accelerate`'s `init_empty_weights()` and `set_module_tensor_to_device()` to load MMAudio, Synchformer, and CLIP models with zero-copy initialization — avoids the 3× memory spike of standard `model.load_state_dict()`.
- **Model Auto-Detection**: Detects MMAudio model variant (small/large, v1/v2) from state dict tensor shapes instead of hardcoding, enabling seamless support for multiple model versions.
- **CLIP & BigVGAN Component Loading**: Loads CLIP vision encoder (DFN5B-ViT-H-14-384) and BigVGAN v2 vocoder as separate components with controlled download paths, instead of relying on MMAudio's internal download.
- **Model Mirror Repository**: All 5 MMAudio model components hosted on `AEmotionStudio/mmaudio-models` as fp16 `.safetensors` (~5.5 GB total, 50% smaller than original fp32). Mirror-first download with upstream HuggingFace fallback.
- **MuseTalk Model Mirror**: MuseTalk UNet weights hosted on `AEmotionStudio/musetalk-models` as `.safetensors` in both fp32 (3.2 GB) and fp16 (1.6 GB). Lip sync auto-downloads the fp16 variant by default — 50% smaller. Falls back to fp32 safetensors, then upstream `.pth`.
- **Mask Points Chaining**: `SaveVideoNode` now has optional `mask_points` input/output for passing segmentation point data through the node chain. `LoadVideoPathNode` accepts upstream `mask_points` to override locally generated points.
- **LoadImagePath Node Styling**: Consistent color styling applied to `LoadImagePath` to match other FFMPEGA nodes.
- **Structured Logging (`core/logging.py`)**: New `JSONFormatter` for machine-readable logs, `get_logger()` convenience function, and `LogTimer` context manager for performance tracking. Enable via `FFMPEGA_LOG_JSON=1` env var. *(PR #136)*
- **CONTRIBUTING.md**: New contributor documentation with architecture overview, development setup, coding standards, and PR guidelines. *(PR #136)*
- **Pre-commit Hooks**: New `.pre-commit-config.yaml` with Ruff lint/format and Pyright checks. New `ruff.toml` (120-char lines, py310 target). *(PR #136)*
- **CI Workflow (`.github/workflows/ci.yml`)**: Pytest + Pyright runs on every PR/push. `publish_action.yml` updated with `needs: test` gate. `.coveragerc` and `pytest-cov` CI integration for code coverage. *(PR #130)*
- **12 Integration Tests (`tests/test_integration.py`)**: Real FFmpeg pipeline tests — single-skill (brightness, resize, volume, remove_audio, speed), multi-skill (resize+brightness, trim+resize, video+audio, full), and edge cases (empty pipeline, overwrite, pixel_format enforcement). Test video generated dynamically via ffmpeg (no binary in repo). *(PR #130)*
- **Node Chaining Tests**: New `tests/test_node_chaining.py` with comprehensive tests for mask_points pass-through, save/load node wiring, and metadata propagation.
- **Model Manager Tests**: New `tests/test_model_manager.py` with tests for mirror download, download guards, and safetensors conversion.
- **Audio Generation Tests**: New `tests/test_generate_audio.py` with 20 tests covering skill registration, handler dispatch, aliases, subprocess wiring, and model manager integration.

### Fixed
- **LaMa Cache Check Mismatch**: Added check for the `torch.hub` cache directory when verifying LaMa model availability, fixing false "not found" when model existed in the hub cache.
- **Mirror Download Test Robustness**: Mocked `require_downloads_allowed` in mirror download tests to prevent spurious failures when download guard settings differ.
- **`no_llm_mode` Default Revert**: Reverted unintentional default change in an unrelated PR to keep focused scope.
- **Audio Extraction Buffer**: Fixed buffer size bug in audio extraction pipeline.
- **Log Propagation Leak**: Prevented FFMPEGA logger messages from propagating to ComfyUI's root logger, avoiding duplicate or noisy console output.
- **Token Usage Display**: Switched token usage summary from logger to `print()` so it always appears in the console regardless of log level configuration.
- **Platform Utility Import Robustness**: `core/platform.py` utilities now import gracefully when ComfyUI modules are unavailable (e.g. standalone testing, MCP server).

### Security
- **CC-BY-NC 4.0 License Warnings**: Prominent license warnings for MMAudio model weights in 5 locations — skill description (visible to LLM agents), handler docstring, handler runtime log, model registry, and README. MMAudio model checkpoints are CC-BY-NC 4.0 (non-commercial); users must accept the license when downloading.

### Changed
- **Modular Node Architecture**: Broke up monolithic `agent_node.py` into 6 focused modules — `input_resolver.py` (input path resolution/validation), `execution_engine.py` (FFmpeg pipeline execution/retry), `output_handler.py` (frame collection/formatting), `batch_processor.py` (batch/queue processing), `nollm_modes.py` (no-LLM mode presets), and `pipeline_assembler.py` (pipeline generation/assembly). `agent_node.py` remains as a thin orchestrator. *(PRs #127, #136)*
- **Platform Abstraction (`core/platform.py`)**: Extracted all ComfyUI boundary interactions (folder paths, model loading, progress callbacks) into a single adapter module. Core logic no longer imports ComfyUI directly. *(PR #128)*
- **Pyright Type Checking**: Added `pyrightconfig.json` (Python 3.10+, basic mode), created type stubs for ComfyUI modules (`folder_paths`, `comfy.*`). Fixed 78 type errors across `core/`, `skills/`, `mcp/` — subprocess stream None-safety, Optional return types, forward references, tuple unpacking, numpy buffer protocol. *(PR #127)*
- **`_RESERVED` Hoisted**: Moved `_RESERVED` from instance-level to module-level constant; lazy-initialized logging to avoid import-time side effects.
- **Removed `_inject_effects_hints`**: Cleaned up dead method from agent_node.
- **Model Registry Updated**: `mmaudio` entry updated with accurate size (~5.5 GB), `license` field, mirror URL, and ⚠️ warning in manual instructions.
- **Safetensors Model Conversion**: Whisper models on HuggingFace mirror converted from `.pt` to `.safetensors` to avoid being flagged. LaMa kept as `.pt` (TorchScript JIT). MuseTalk UNet converted from `.pth` to `.safetensors` (fp32 + fp16). `try_mirror_download` updated to handle per-model conversion strategy.
- **AI-Powered Skills Count**: Updated from 3 to 5 in README (added `generate_audio`, `lip_sync`).
- **Point Selector Accessibility**: Added `role="dialog"`, `aria-modal="true"`, `aria-label` to point selector overlay. Status bar uses `role="status"` and `aria-live="polite"` for screen reader announcements. Decorative emojis hidden with `aria-hidden="true"`. *(PR #124)*
- **Test Suite**: Expanded from 656 to **799 tests** across 40 test files, 0 failures. New integration tests (12), structured logging coverage, and platform abstraction tests.

---

## [2.8.0] - 2026-02-28

### Added
- **FFMPEGA Effects Builder Node**: New companion node for manual effect composition — select up to 3 skills with params, combine with raw FFmpeg filters, and use presets. No LLM required. Purple-themed UI with dynamic widget visibility and auto-fill defaults.
- **Effects Builder Context Menu Presets**: Right-click the Effects Builder for quick access to all 18 built-in presets, plus save/load/delete custom presets. Includes a "Clear All Effects" reset option.
- **Text Node Presets**: Right-click the FFMPEGA Text node for 10 built-in presets (SRT Subtitle Example, Cinematic Subtitles, Bold Watermark, Title Card, Social Caption, Meme Text, Lower Third, Copyright Notice, Credits Roll, Chapter Marker) with example text content. Save/load/delete custom presets. "Clear Text" resets to defaults.
- **No-LLM Text Support**: Connect a Text node to the Agent in no-LLM manual mode (without an Effects Builder) and it auto-generates a text overlay or subtitle pipeline from the Text node's settings.
- **Manual No-LLM Mode**: New `manual` option in `no_llm_mode` dropdown (now the default) — set `llm_model` to `none` and use the Effects Builder to edit videos without any AI. Shows a clear error if no Effects Builder node is connected.
- **SAM3-Only Mode**: New no-LLM mode that uses the prompt as a SAM3 text target for object masking/removal without an LLM.
- **Whisper No-LLM Modes**: `transcribe` and `karaoke_subtitles` options in `no_llm_mode` — run Whisper speech-to-text and burn subtitles directly without an LLM. Also available as Effects Builder presets ("Auto Subtitles", "Karaoke Subtitles").
- **Effects Builder Multi-Input Support**: The Effects Builder pipeline now calls `_inject_extra_inputs()` to populate `pipeline.extra_inputs`, enabling concat, grid, split screen, xfade, overlay, and all other multi-input skills to work correctly with `video_b`, `image_b`, etc.
- **SAM3 Point Prompts**: Support for geometric point prompts passed as SAM3 boxes for precise segmentation guidance. Two-phase prompting: text VG detection + native point refinement.
- **SAM3 Progress Streaming**: Real-time SAM3 subprocess progress display in the console.
- **Save Video Overlay Button**: Accessible overlay button on video previews for quick save actions.
- **Drag-and-Drop Feedback**: Visual feedback during file drag-and-drop uploads with proper state restoration.

### Fixed
- **SAM3 Subprocess Isolation**: SAM3 video masking now runs in a separate subprocess to prevent CUDA memory leaks and improve VRAM management. Fixes persistent OOM errors on long videos.
- **SAM3 OOM Fixes**: Multiple fixes for out-of-memory errors during SAM3 processing — CPU offloading between propagation passes, frame 0 cache retention for point prompts, VG propagation scoping.
- **SAM3 Point Prompt Fixes**: Cap `max_num_objects` to 2 for point prompt mode, validate coordinates with float/int coercion, forward `mask_points` to batch mode metadata, use source image dims for coordinate mapping.
- **SAM3 Bad File Descriptor**: Fixed `Popen` bad file descriptor error in SAM3 subprocess communication.
- **SAM3 `_postprocess_output` KeyError**: Fixed KeyError when `max_num_objects` is active and fewer objects are detected than expected.
- **MCP Path Traversal** *(security)*: Fixed path traversal vulnerabilities in MCP tools — added input and output path validation.
- **Template Placeholder Crash**: Fixed unsubstituted template placeholders (e.g. `{ratio}`) causing ffmpeg crashes when parameters are dropped by validation. Now falls back to skill defaults.
- **Effects Builder Multi-Input**: Fixed concat, grid, split screen, xfade, and all multi-input skills not working in the Effects Builder. The Effects Builder path was missing the `_inject_extra_inputs()` call, so `_extra_input_count` was always 0.
- **Concat/Xfade/Slideshow Resolution**: Fixed output resolution defaulting to 1920×1080 regardless of input. Handlers now use the input video's actual resolution.
- **Dynamic Slot Root Cause**: Fixed `video_b` disappearing on page refresh — `video_path` and `video_folder` static widget inputs were polluting the `video_` dynamic slot group.
- **Effects Builder Stale Params**: Switching effects now clears the params widget, preventing stale params from leaking between effects.
- **Effects Builder Temp Cleanup**: Added cleanup for temp files created by `_inject_extra_inputs()` in the Effects Builder pipeline.
- **Drag-and-Drop State Restoration**: Correctly restores original text and border states after drag-and-drop feedback.
- **Vision Frames Cleanup**: Clear `_vision_frames` on startup and correct SAM3 import check.
- **`text_overlay` Position**: Removed position default from `text_overlay` to preserve preset positioning.
- **Tool Prompt Builder**: Filter `None` from `available_names` in tool prompt builder.
- **SaveVideo Preview Mode**: Fixed `preview_only` mode causing 404 errors — preview segments now correctly copied to ComfyUI's temp directory.
- **Frame Extractor Duration Default**: Changed default `duration` from 10s to 0 (full video), raised max to 3600s.

### Security
- **MCP Path Validation**: Input and output paths in MCP tools are now validated against path traversal attacks.
- **SkillComposer Parameter Hardening**: Secure parameter handling and updated skill schemas to prevent injection.
- **`validate_path` Directory Checks**: Enforced sensitive directory checks in `validate_path`.

### Performance
- **SAM3 VRAM Optimization**: CPU offloading, auto-stride selection, and object limits for SAM3 video masker. Suppressed noisy console output.
- **FFMPEG Pipe Buffer**: Optimized pipe buffer size for video conversion.
- **Ultrafast Temp Videos**: Temp video generation now uses `ultrafast` FFMPEG preset.
- **Frame Tensor Allocation**: Optimized video frame tensor allocation.

### Changed
- **`no_llm_mode` Default → `manual`**: Default changed from `sam3_masking` to `manual`. Users who set `llm_model=none` now get the Effects Builder path by default.
- **Empty Prompt Allowed for Manual Mode**: `manual` mode no longer requires a prompt.
- **SAM3 Last-Frame Anchoring Removed**: Simplified point prompts by removing last-frame point anchoring from SAM masker and its UI.
- **SAM3 `mask_output_type` Default**: Changed default mask output type from `colored_overlay` to `black_white`.
- **UI Focus Tracking**: Refactored focus tracking to use explicit state; enhanced focus visibility for interactive elements.

---

## [2.7.1] - 2026-02-24

### Added
- **Advanced Options Toggle**: New `advanced_options` input (default: Simple) — hides `preview_mode`, `crf`, `encoding_preset`, `video_path`, `subtitle_path`, and `batch_mode` (+ sub-widgets) behind a toggle for a cleaner node layout. Power users can enable Advanced mode to access all settings.
- **SAM3 Checkpoint Warnings**: Added format mismatch detection — logs a warning with reconversion instructions when >50% of checkpoint keys are missing (e.g. HuggingFace Transformers format vs expected original `.pt` key structure).
- **Token Log Rotation**: `usage_log.jsonl` now auto-rotates when exceeding 10 MB, trimming the oldest 50% of entries to prevent unbounded disk growth.

### Fixed
- **Dynamic Input Persistence**: Fixed dynamic input slots (e.g. `video_b` appearing when `video_a` is connected) not restoring on workflow load. Pre-creates saved slots from serialized data in `onConfigure` and uses `setTimeout` instead of `requestAnimationFrame` for reliable link restoration timing.
- **Default Value Mismatches**: Synced `process()` signature defaults with `INPUT_TYPES` for `whisper_device` and `track_tokens`.

### Changed
- **Removed `ptc_mode` Input**: PTC mode hidden from UI (not ready for public use). Defaults to `"off"` internally. Code preserved for future re-enablement.
- **Removed `sam3_device` Input**: SAM3 CPU mode hidden from UI (SAM3 does not support CPU inference). Defaults to `"gpu"` internally.
- **Whisper Default → CPU**: `whisper_device` now defaults to `"cpu"` to avoid VRAM pressure on most setups.
- **Token Tracking Default → On**: `track_tokens` now defaults to `True` so users see token usage by default.
- **Dead Code Cleanup**: Removed ~1100 lines of unreachable inlined `process` method after `return` statement in `agent_node.py`.
- **`ValidationError`**: Path validation functions in `core/sanitize.py` now raise `ValidationError` instead of `ValueError` for more specific error handling.

---

## [2.7.0] - 2026-02-24

### Added
- **SAM3 Auto-Mask & Greenscreen**: New `remove` skill powered by SAM3 (Segment Anything Model 3) for automatic object segmentation. Generates per-frame binary masks from text prompts (e.g. *"remove the person"*), then applies LaMa inpainting or black fill. New `greenscreen` skill uses SAM3 masks to replace backgrounds with solid colors or transparency (WebM output). *(PR #71)*
- **LaMa Inpainting**: New `core/lama_inpainter.py` — per-frame LaMa (Large Mask Inpainting) for AI-powered video object removal. Uses `simple-lama-inpainting` (Apache-2.0). Includes temporal Gaussian smoothing to reduce frame-to-frame flickering, and automatic temp directory cleanup. *(PR #71)*
- **Programmatic Tool Calling (PTC)**: New `execute_code` tool with sandboxed Python executor (`core/ptc_executor.py`). LLMs can write a single Python script that orchestrates multiple tool calls (search → details → build) in one pass, reducing round-trips from ~6 to 1. Three modes: `off` (classic), `auto` (both available), `on` (forced PTC only). *(PR #72)*
- **PTC Sandbox Security**: Static code analysis blocks 25+ escape vectors — dunder introspection (`__class__`, `__globals__`, `__getattribute__`), module access (`os.`, `subprocess.`), traceback frame traversal (`__traceback__`, `tb_frame`, `f_back`), dangerous builtins (`eval`, `exec`, `open`, `chr`), and dynamic attribute access. All builtins except safe ones are removed. *(PR #72)*
- **Tool Use Examples**: `input_examples` field added to all tool definitions, giving LLMs concrete usage patterns. Examples are stripped from API schemas (OpenAI, Anthropic) to avoid 400 errors but preserved for CLI connectors that embed tools as text. *(PR #72)*
- **PTC Test Suite**: New `tests/test_ptc_executor.py` with 34 tests covering sandbox security (15 escape vector tests), safe builtins, tool access, end-to-end orchestration, and vision integration. *(PR #72)*

### Security
- **Path Validation Hardening**: Case-insensitive path validation on all platforms, improved robustness of output path blocking for system directories. *(PR #69)*
- **Input Sanitization**: Expanded input sanitization for edge cases in text parameters and API key handling. *(PR #69)*
- **PTC Sandbox Hardening**: Blocked `__getattribute__`/`__setattr__`/`__delattr__` for dynamic attribute access, `chr()` for string construction bypasses, and traceback frame traversal escapes. Deep-copied tool schemas prevent mutation of global definitions. *(PR #72)*

### Performance
- **CHOICE Validation O(1)**: `SkillParameter` caches a normalized `_choice_map` in `__post_init__` — O(1) dictionary lookup instead of O(N) list iteration. *(PR #70)*
- **FFMPEG Path Escape**: Optimized `ffmpeg_escape_path` performance for common-case clean paths. *(PR #73)*

### Fixed
- **SAM3 Mask Cleanup**: Guarded `rmtree` against `None` temp directory, wrapped FPS parsing in try/except, fixed torch.cuda calls on CPU-only systems, and resolved mask dimension validation issues. *(PR #71)*
- **LaMa Import Path**: Added relative import fallback and corrected `remove_object` function import (was incorrectly `inpaint_video`). *(PR #71)*
- **PTC API Keys**: System prompt and test mocks now use correct return keys (`matches`/`match_count` instead of `skills`/`count`). *(PR #72)*
- **Regex False Positives**: PTC blocked-patterns regex uses word boundaries so strings like `"videos.mp4"` are not flagged by the `os.` pattern. *(PR #72)*
- **Forced PTC Mode**: When `ptc_mode == "on"`, tool_defs now only exposes `execute_code` — model can no longer bypass forced-PTC with classic per-tool calls. *(PR #72)*
- **CLI Tool Instructions**: Tool usage instructions now adapt to available tools — prevents contradictory "ALWAYS call search_skills" when only `execute_code` is exposed. *(PR #72)*
- **Sentinel Overlay Validation**: Added validation for `ParameterType.COLOR` and hidden `text_overlay` parameters.

### Changed
- **Shared Effect Filter Map**: Extracted duplicate effect filter mapping into a shared constant to eliminate duplication between handlers. *(PR #71)*
- **Upload Button UX**: Enhanced upload button accessibility with improved label casing and ARIA attributes. *(PR #74)*
- **Tool Schema Stripping**: `strip_nonstandard_fields()` now uses `copy.deepcopy` for nested parameters, preventing mutation of global `TOOL_DEFINITIONS`. Only applied to non-CLI connectors. *(PR #72)*
- **Test Suite**: Expanded from 516 to **656 passing tests**, 0 failures. New PTC executor tests (34), security hardening tests, and updated mock return shapes to match real API contracts.

---


## [2.6.6] - 2026-02-22

### Changed
- **Metadata Updates**: Updated author to `Æmotion Studio` in `pyproject.toml` and `__init__.py`.
- **Dependencies**: Removed `pydantic` from requirements since it's already provided by ComfyUI core.

---

## [2.6.5] - 2026-02-22

### Added
- **Whisper Auto-Transcription**: New `auto_transcribe` skill — transcribes video audio with OpenAI Whisper and burns SRT subtitles into the output. Supports single and multi-video (concat) workflows with correct cross-clip timing. *(PR #67)*
- **Karaoke Subtitles**: New `karaoke_subtitles` skill — word-by-word progressive-fill karaoke effect using Whisper word-level timestamps and ASS `\kf` tags. Configurable font size, base color, and fill color. *(PR #67)*
- **Whisper Device Control**: New `whisper_device` node setting (`gpu`/`cpu`) — allows running Whisper on CPU to avoid VRAM pressure on low-memory GPUs. *(PR #67)*
- **Whisper Model Selection**: New `whisper_model` node setting (`tiny`, `base`, `small`, `medium`, `large-v3`) — choose the model size for speed vs. accuracy tradeoff. *(PR #67)*
- **Transcription Test Suite**: New `tests/test_transcribe.py` with 18 tests covering SRT generation, ASS karaoke output, handler dispatch, skill registry entries, and model path resolution. *(PR #67)*

### Fixed
- **Publish Action Failure**: Fixed PEP 8 E702 semicolon error in `agent_node.py` that caused the Comfy Registry publish action to fail.
- **Letterbox Content Preservation**: Replaced `crop+pad` with `drawbox` for letterboxing to preserve video content instead of cropping. Correctly handles both letterbox (horizontal bars) and pillarbox (vertical bars) cases. *(PR #67)*
- **Whisper Memory Leak**: `_load_model` now frees the previous model before loading a new one, preventing GPU memory accumulation when switching model sizes. *(PR #67)*
- **Multi-Video Timestamp Desync**: Fixed `transcribe_multi_video` not advancing `time_offset` for skipped (non-existent) videos, which caused subtitle desync. *(PR #67)*
- **Xfade Transition Timing**: `transcribe_multi_video` now accepts `transition_duration` to subtract xfade overlap from timestamp offsets, keeping subtitles in sync with xfade-shortened output. *(PR #67)*
- **ASS Subtitle Escaping**: Transcribed words containing `{`, `}`, or `\` are now stripped before embedding in karaoke ASS tags, preventing rendering failures. *(PR #67)*
- **Primary Input Validation**: `_collect_video_paths` now validates the primary input's file extension, matching the check already applied to extra inputs. *(PR #67)*
- **Invalid Hex Color Rejection**: `color_to_ass_bgr` now validates hex digits before conversion — malformed colors like `#GGGGGG` fall back to the default instead of producing broken ASS strings. *(PR #67)*
- **Aspect Ratio Division by Zero**: Added validation to prevent `ZeroDivisionError` when parsing aspect ratios with zero denominators. *(PR #67)*

### Changed
- **Shared `ffmpeg_escape_path`**: Extracted duplicate `_ffmpeg_escape` functions from `subtitles.py` and `transcribe.py` into a shared `ffmpeg_escape_path()` in `core/sanitize.py`. *(PR #67)*
- **Shared `color_to_ass_bgr`**: Extracted duplicate color-to-ASS conversion from `subtitles.py`, `transcribe.py`, and `whisper_transcriber.py` into a shared `color_to_ass_bgr()` in `core/sanitize.py`. Supports named colors, 6/8-digit hex, and native ASS pass-through. *(PR #67)*
- **Shared `_run_transcription`**: Extracted duplicated transcription dispatch logic from `_f_auto_transcribe` and `_f_karaoke_subtitles` into a shared `_run_transcription()` helper. *(PR #67)*
- **Subtitle Filter Ordering**: Subtitle filters now always render last via a filter reordering pass, ensuring subtitles appear on top of letterbox bars and other effects. *(PR #67)*

---

## [2.6.4] - 2026-02-22

### Security
- **Typewriter Text DoS Prevention**: Enforced string length validation in `SkillRegistry` and added a `max_value=200` limit to the `typewriter_text` skill's text parameter to prevent resource exhaustion. *(PR #66)*

### Performance
- **PNG Compression Optimization**: `MediaConverter.save_frames_as_images` now uses `compress_level=1` (fastest) instead of the default level (6) when saving temporary frames for FFMPEG concatenation or overlays. Yields a ~25% speedup with minimal file size impact. *(PR #64)*

### Changed
- **Aria Live Status Updates**: Added `role="status"` and `aria-live="polite"` regions to UI elements in `ffmpega_ui.js` ensuring screen readers announce status changes during video uploads, processing, and color copying. Dynamically updates `aria-label` to "Copied successfully" on hex code copy. *(PR #65)*

---

## [2.6.3] - 2026-02-21

### Security
- **FFMPEG Stream Specifier Injection Fix**: `sanitize_text_param` in `core/sanitize.py` now escapes square brackets (`[` → `\[`, `]` → `\]`). Unescaped brackets in user-supplied text parameters could be interpreted as FFMPEG stream specifiers (e.g. `[0:v]`), enabling filter graph injection or causing syntax errors. Added `test_escapes_brackets` regression test. *(PR #62)*

### Performance
- **Sanitize "Check First" Optimization**: `sanitize_text_param` and `sanitize_api_key` now guard each `str.replace()` call with an `if char in text` check. Avoids unnecessary string allocations in the common case (clean text). ~2.5x speedup for `sanitize_text_param` on clean input; `sanitize_api_key` skips `redact_secret()` entirely when the key is absent. *(PR #63)*

### Changed
- **Color Picker Accessibility**: `FFMPEGATextInput` hex color label in `ffmpega_ui.js` is now keyboard-accessible — added `tabindex="0"`, `role="button"`, and `aria-label` attributes; Enter/Space trigger copy; focus indicator via `box-shadow`. `aria-label="Select font color"` added to the color input itself. *(PR #61)*

---

## [2.6.2] - 2026-02-20

### Security
- **Block Writes to System Directories**: Updated `validate_output_path` and `validate_output_file_path` in `core/sanitize.py` to block writes to critical system directories (e.g., `/usr`, `/bin`, `/etc`, `C:\Windows`). Prevents path traversal / arbitrary file overwrite targeting sensitive system files. *(PR #59)*

### Changed
- **CHOICE Validation O(1) Lookup**: `SkillParameter` now caches a `_choice_map` of normalized choices (exact, lowercase, underscore-to-hyphen variants) in `__post_init__`. `validate()` uses O(1) dictionary lookup instead of O(N) list iteration — ~15% faster for CHOICE parameters. *(PR #60)*
- **Video Upload Loading Feedback**: Refactored `FFMPEGALoadVideoPath` upload logic in `ffmpega_ui.js` — added `setUploadState` helper to toggle "Uploading…" label, consolidated click and drag-drop into a shared `handleUpload` handler, improved error handling with `try/finally` to ensure UI reset, and hides video preview during upload. *(PR #58)*

---

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
