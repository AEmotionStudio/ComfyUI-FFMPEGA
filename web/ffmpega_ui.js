import { app } from "../../scripts/app.js";
import { u as updateDynamicSlots, S as SLOT_LABELS, s as setPrompt, R as RANDOM_PROMPTS, f as flashNode, h as handlePaste, c as createUploadButton, a as addDownloadOverlay, b as addVideoPreviewMenu } from "./_chunks/ui_helpers-CvUDB6-L.js";
import { api } from "../../scripts/api.js";
import { C as CropOverlay } from "./_chunks/CropOverlay-CFlj408e.js";
const NODE_COLORS = {
  "FFMPEGAPreview": ["#3a5a3a", "#2a4a2a"],
  "FFMPEGAMediaBridge": ["#3a5a4a", "#2a4a3a"],
  "FFMPEGABatchProcessor": ["#5a3a3a", "#4a2a2a"],
  "FFMPEGAVideoInfo": ["#4a4a3a", "#3a3a2a"],
  "LoadLastImage": ["#5a4a3a", "#4a3a2a"]
};
function registerNodeStyling(nodeType, nodeData) {
  const colors = NODE_COLORS[nodeData.name];
  if (!colors) return false;
  const [color, bgcolor] = colors;
  const onNodeCreated = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function() {
    const result = onNodeCreated == null ? void 0 : onNodeCreated.apply(this, arguments);
    this.color = color;
    this.bgcolor = bgcolor;
    return result;
  };
  return true;
}
const DYNAMIC_PREFIXES = [
  { prefix: "images_", type: "IMAGE", excludes: [] },
  { prefix: "image_", type: "IMAGE", excludes: ["images_", "image_path_"] },
  { prefix: "audio_", type: "AUDIO", excludes: [] },
  { prefix: "video_", type: "STRING", excludes: ["video_path", "video_folder"] },
  { prefix: "image_path_", type: "STRING", excludes: [] },
  { prefix: "text_", type: "STRING", excludes: [] }
];
function toggleWidget(widget, show) {
  if (!widget) return;
  if (!widget._origType) {
    widget._origType = widget.type;
    widget._origComputeSize = widget.computeSize;
  }
  if (show) {
    widget.type = widget._origType;
    widget.computeSize = widget._origComputeSize;
    widget.hidden = false;
    if (widget.element) widget.element.hidden = false;
  } else {
    widget.type = "hidden";
    widget.computeSize = () => [0, -4];
    widget.hidden = true;
    if (widget.element) widget.element.hidden = true;
  }
}
function needsApiKey(model) {
  if (!model || typeof model !== "string") return false;
  if (model === "none") return false;
  if (model === "gemini-cli" || model === "claude-cli" || model === "cursor-agent" || model === "qwen-cli") return false;
  return model.startsWith("gpt") || model.startsWith("claude") || model.startsWith("gemini") || model === "custom";
}
function buildPresetMenu(node) {
  const sp = (text) => setPrompt(node, text);
  return [
    {
      content: "🎬 Cinematic & Style",
      submenu: {
        options: [
          { content: "Cinematic Letterbox", callback: () => sp("Apply cinematic letterbox and color grading") },
          { content: "Blockbuster", callback: () => sp("Apply blockbuster style with high contrast and dramatic grading") },
          { content: "Film Noir", callback: () => sp("Black and white film noir style with high contrast") },
          { content: "Dreamy / Soft Glow", callback: () => sp("Apply a dreamy soft glow effect") },
          { content: "HDR Look", callback: () => sp("Apply an HDR-style look with vivid colors and detail") },
          { content: "Teal & Orange", callback: () => sp("Apply teal and orange color grading") },
          { content: "Documentary", callback: () => sp("Apply a clean natural documentary look") },
          { content: "Indie Film", callback: () => sp("Apply an indie art-house look with faded colors") },
          { content: "Sci-Fi", callback: () => sp("Apply a cool blue sci-fi atmosphere") },
          { content: "Dark / Moody", callback: () => sp("Apply a dark atmospheric moody look") },
          { content: "Romantic", callback: () => sp("Apply a soft warm romantic mood") },
          { content: "Action", callback: () => sp("Apply fast-paced action movie grading with high contrast") }
        ]
      }
    },
    {
      content: "📼 Vintage & Retro",
      submenu: {
        options: [
          { content: "Vintage Film", callback: () => sp("Create a vintage film look with grain") },
          { content: "VHS Effect", callback: () => sp("Apply a VHS tape effect with tracking lines and distortion") },
          { content: "Sepia Tone", callback: () => sp("Apply a warm sepia tone effect") },
          { content: "Super 8mm Film", callback: () => sp("Apply a Super 8mm film look with jitter and grain") },
          { content: "Old TV / CRT", callback: () => sp("Apply an old CRT television look with scanlines") },
          { content: "Polaroid Look", callback: () => sp("Apply a polaroid photo style color treatment") },
          { content: "Faded / Washed Out", callback: () => sp("Apply a faded washed-out film look") },
          { content: "Damaged Film", callback: () => sp("Apply a damaged film effect with scratches and flicker") },
          { content: "Lo-Fi Chill", callback: () => sp("Apply a lo-fi chill aesthetic with muted tones") }
        ]
      }
    },
    {
      content: "🎨 Color & Look",
      submenu: {
        options: [
          { content: "Grayscale", callback: () => sp("Convert to black and white grayscale") },
          { content: "Boost Saturation", callback: () => sp("Increase color saturation for more vivid colors") },
          { content: "Desaturate", callback: () => sp("Desaturate colors for a muted look") },
          { content: "Invert Colors", callback: () => sp("Invert all colors to create a negative image") },
          { content: "Sharpen", callback: () => sp("Sharpen the video to enhance detail and clarity") },
          { content: "Unsharp Mask", callback: () => sp("Apply unsharp mask for fine-grained luma/chroma sharpening") },
          { content: "Blur / Soften", callback: () => sp("Apply a soft gaussian blur effect") },
          { content: "Vignette", callback: () => sp("Add a dark vignette around the edges") },
          { content: "Deband", callback: () => sp("Remove color banding artifacts") },
          { content: "White Balance", callback: () => sp("Adjust white balance to 5500K for natural daylight") },
          { content: "Shadows & Highlights", callback: () => sp("Brighten shadows and tame highlights for balanced exposure") },
          { content: "Split Tone", callback: () => sp("Apply split toning — warm highlights, cool shadows") },
          { content: "Deflicker", callback: () => sp("Remove fluorescent or timelapse flicker") },
          { content: "Color Match", callback: () => sp("Auto equalize histogram for consistent color") },
          { content: "Apply LUT", callback: () => sp("Apply a 3D LUT color grade from file") }
        ]
      }
    },
    {
      content: "✨ Creative Effects",
      submenu: {
        options: [
          { content: "Neon Glow", callback: () => sp("Apply a neon glow effect with vibrant edges") },
          { content: "Cyberpunk", callback: () => sp("Apply cyberpunk look with neon tones and high contrast") },
          { content: "Underwater", callback: () => sp("Apply an underwater look with blue tint and blur") },
          { content: "Sunset / Golden Hour", callback: () => sp("Apply a golden hour warm glow effect") },
          { content: "Comic Book", callback: () => sp("Apply bold comic book / pop art style") },
          { content: "Miniature / Tilt-Shift", callback: () => sp("Apply tilt-shift miniature toy model effect") },
          { content: "Thermal Vision", callback: () => sp("Apply thermal / heat vision camera effect") },
          { content: "Anime / Cel-Shaded", callback: () => sp("Apply anime cel-shaded cartoon look") },
          { content: "Surveillance / CCTV", callback: () => sp("Apply security camera CCTV look") },
          { content: "Datamosh / Glitch Art", callback: () => sp("Apply datamosh glitch art effect") },
          { content: "Radial Blur", callback: () => sp("Apply a radial zoom blur effect") },
          { content: "Film Grain Overlay", callback: () => sp("Add cinematic film grain overlay with intensity control") },
          { content: "Posterize", callback: () => sp("Reduce color palette for screen-print poster effect") },
          { content: "Emboss", callback: () => sp("Apply an emboss relief surface effect") },
          { content: "Pixelate / 8-Bit", callback: () => sp("Pixelate into an 8-bit retro game look") },
          { content: "Day for Night", callback: () => sp("Simulate nighttime from daytime footage") },
          { content: "Horror", callback: () => sp("Apply dark desaturated horror atmosphere with grain") },
          { content: "Music Video", callback: () => sp("Apply punchy music video look with contrast and vignette") }
        ]
      }
    },
    {
      content: "✏️ Text & Graphics",
      submenu: {
        options: [
          { content: "Text Overlay", callback: () => sp("Add text overlay that says 'Hello World' in the center") },
          { content: "Animated Text", callback: () => sp("Add animated text that says 'Welcome' with a fade-in effect") },
          { content: "Scrolling Credits", callback: () => sp("Add scrolling credits text that moves upward") },
          { content: "News Ticker", callback: () => sp("Add a scrolling news-style ticker bar at the bottom") },
          { content: "Lower Third", callback: () => sp("Add a professional broadcast lower third with name and title") },
          { content: "Countdown Timer", callback: () => sp("Add a 10-second countdown timer overlay") },
          { content: "Typewriter Text", callback: () => sp("Add typewriter reveal text effect") },
          { content: "Bounce Text", callback: () => sp("Add bouncing animated text at the top") },
          { content: "Fade Text", callback: () => sp("Add text that fades in and out") },
          { content: "Karaoke Text", callback: () => sp("Add karaoke-style progressively filled text") },
          { content: "Watermark", callback: () => sp("Add a semi-transparent watermark in the bottom-right corner") },
          { content: "Burn Subtitles (SRT)", callback: () => sp("Burn subtitles from SRT file into the video") },
          { content: "🎙️ Auto-Transcribe Subtitles", callback: () => sp("Auto-transcribe and burn subtitles with white text") },
          { content: "🎙️ Transcribe (Custom Color)", callback: () => sp("Auto-transcribe and burn subtitles with large yellow text at 32px") },
          { content: "🎙️ Karaoke Subtitles", callback: () => sp("Add karaoke-style word-by-word subtitles with yellow fill") }
        ]
      }
    },
    {
      content: "✂️ Editing & Delivery",
      submenu: {
        options: [
          { content: "Picture-in-Picture", callback: () => sp("Create a picture-in-picture layout with small video in corner") },
          { content: "Blend Two Videos", callback: () => sp("Blend two video inputs with 50% opacity") },
          { content: "Mask Blur (Privacy)", callback: () => sp("Blur a rectangular region for privacy") },
          { content: "Remove Logo", callback: () => sp("Remove a logo from the top-right region") },
          { content: "Remove Duplicates", callback: () => sp("Strip duplicate stuttered frames") },
          { content: "Jump Cut", callback: () => sp("Auto-cut to high-energy moments every 2 seconds") },
          { content: "Beat Sync", callback: () => sp("Sync cuts to a beat interval") },
          { content: "Extract Frames", callback: () => sp("Export frames as image sequence at 1 fps") },
          { content: "Thumbnail", callback: () => sp("Extract the best representative thumbnail frame") },
          { content: "Sprite Sheet", callback: () => sp("Create a 5x5 sprite sheet contact preview of the video") },
          { content: "Chroma Key (Green Screen)", callback: () => sp("Remove the green screen background using chroma key") },
          { content: "Mirror / Flip", callback: () => sp("Mirror the video horizontally") }
        ]
      }
    },
    {
      content: "🔀 Transitions & Reveals",
      submenu: {
        options: [
          { content: "Fade In from Black", callback: () => sp("Add a fade-in from black at the beginning") },
          { content: "Fade Out to Black", callback: () => sp("Add a fade-out to black at the end") },
          { content: "Fade to White", callback: () => sp("Add a fade to white transition") },
          { content: "Flash Effect", callback: () => sp("Add a bright flash transition at the midpoint") },
          { content: "Cross Dissolve (xfade)", callback: () => sp("Add a cross dissolve transition between clips") },
          { content: "Wipe Reveal", callback: () => sp("Add a directional wipe reveal from the left") },
          { content: "Iris Reveal", callback: () => sp("Add a circle expanding iris reveal from center") },
          { content: "Slide In", callback: () => sp("Slide the video in from the left edge") }
        ]
      }
    },
    {
      content: "🌀 Motion & Animation",
      submenu: {
        options: [
          { content: "Ken Burns Zoom", callback: () => sp("Apply a slow Ken Burns zoom-in effect") },
          { content: "Slow Zoom", callback: () => sp("Apply a slow push-in zoom over the duration") },
          { content: "Spin / Rotate", callback: () => sp("Slowly rotate the video continuously") },
          { content: "Camera Shake", callback: () => sp("Add a subtle camera shake effect") },
          { content: "Pulse / Breathe", callback: () => sp("Add a rhythmic zoom pulse effect") },
          { content: "Drift / Pan", callback: () => sp("Add a slow horizontal drift pan") },
          { content: "Bounce", callback: () => sp("Add a bouncing animation effect") },
          { content: "Animated Overlay", callback: () => sp("Add a moving image overlay with scroll motion") }
        ]
      }
    },
    {
      content: "📱 Format & Social",
      submenu: {
        options: [
          { content: "TikTok / Reels (9:16)", callback: () => sp("Crop to vertical 9:16 for TikTok/Reels") },
          { content: "Instagram Square (1:1)", callback: () => sp("Crop to square 1:1 format") },
          { content: "YouTube Optimize", callback: () => sp("Optimize for YouTube at 1080p with good compression") },
          { content: "Twitter / X Optimize", callback: () => sp("Optimize for Twitter/X with size limits") },
          { content: "Convert to GIF", callback: () => sp("Convert to an animated GIF") },
          { content: "Add Caption Space", callback: () => sp("Add blank space below the video for captions") },
          { content: "Compress for Web", callback: () => sp("Compress for web delivery, optimize file size") },
          { content: "Intro / Outro", callback: () => sp("Add intro and outro segments to the video") }
        ]
      }
    },
    {
      content: "⏱️ Time & Speed",
      submenu: {
        options: [
          { content: "Slow Motion (0.5x)", callback: () => sp("Create smooth slow motion at 0.5x speed") },
          { content: "Speed Up (2x)", callback: () => sp("Speed up the video 2x while keeping audio pitch") },
          { content: "Speed Up (4x)", callback: () => sp("Speed up the video 4x for time-lapse effect") },
          { content: "Reverse", callback: () => sp("Play the video in reverse") },
          { content: "Loop (3x)", callback: () => sp("Loop the video 3 times seamlessly") },
          { content: "Trim First 5 Seconds", callback: () => sp("Trim the first 5 seconds of the video") },
          { content: "Freeze Frame", callback: () => sp("Freeze a frame at the 3 second mark for 2 seconds") },
          { content: "Time Remap / Speed Ramp", callback: () => sp("Gradually ramp speed from 1x to 2x") },
          { content: "Scene Detect", callback: () => sp("Auto-detect scene changes") },
          { content: "Frame Rate Interpolation", callback: () => sp("Interpolate frame rate to smooth 60fps") }
        ]
      }
    },
    {
      content: "🔊 Audio",
      submenu: {
        options: [
          { content: "Remove Audio", callback: () => sp("Remove all audio tracks") },
          { content: "Boost Volume", callback: () => sp("Increase audio volume") },
          { content: "Normalize Audio", callback: () => sp("Normalize audio levels to consistent volume") },
          { content: "Normalize Loudness (EBU R128)", callback: () => sp("Normalize loudness to broadcast standard EBU R128") },
          { content: "Noise Reduction", callback: () => sp("Apply noise reduction to clean up the audio") },
          { content: "De-Reverb", callback: () => sp("Remove room echo and reverb from audio") },
          { content: "Fade Audio In/Out", callback: () => sp("Add audio fade-in at start and fade-out at end") },
          { content: "Audio Crossfade", callback: () => sp("Smooth crossfade between two audio tracks") },
          { content: "Extract Audio Only", callback: () => sp("Extract only the audio track as a separate output") },
          { content: "Replace Audio", callback: () => sp("Replace the video's audio with connected audio input") },
          { content: "Split Audio (L/R)", callback: () => sp("Extract just the left channel of audio") },
          { content: "Bass Boost", callback: () => sp("Boost bass frequencies for more punch") },
          { content: "Add Echo / Reverb", callback: () => sp("Add echo and reverb effect to audio") },
          { content: "Dynamic Compression", callback: () => sp("Apply dynamic range compression to audio") },
          { content: "Ducking", callback: () => sp("Apply audio ducking for voice-over clarity") },
          { content: "Audio Delay", callback: () => sp("Add a delay offset to the audio track") }
        ]
      }
    },
    {
      content: "📐 Spatial & Layout",
      submenu: {
        options: [
          { content: "Resize to 1080p", callback: () => sp("Resize to 1920x1080 maintaining aspect ratio") },
          { content: "Crop to Region", callback: () => sp("Crop to 1280x720 from center") },
          { content: "Auto Crop (Remove Borders)", callback: () => sp("Automatically detect and remove black borders") },
          { content: "Scale 2x Upscale", callback: () => sp("Upscale video by 2x with Lanczos algorithm") },
          { content: "Add Letterbox", callback: () => sp("Add black letterbox bars for 16:9 aspect ratio") },
          { content: "Rotate 90°", callback: () => sp("Rotate the video 90 degrees clockwise") },
          { content: "Split Screen", callback: () => sp("Create a side-by-side split screen layout") },
          { content: "Grid Layout", callback: () => sp("Arrange inputs in a grid layout") },
          { content: "Slideshow", callback: () => sp("Create a slideshow from images with fade transitions") },
          { content: "Concat / Join Videos", callback: () => sp("Concatenate video segments together sequentially") }
        ]
      }
    }
  ];
}
function registerAgentNode(nodeType, nodeData) {
  if (nodeData.name !== "FFMPEGAgent") return;
  const onNodeCreated = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function() {
    var _a, _b, _c, _d, _e, _f, _g, _h, _i, _j, _k, _l, _m, _n, _o, _p, _q, _r, _s, _t, _u, _v, _w, _x, _y, _z, _A, _B, _C, _D, _E, _F, _G, _H;
    const result = onNodeCreated == null ? void 0 : onNodeCreated.apply(this, arguments);
    const node = this;
    this.color = "#2a3a5a";
    this.bgcolor = "#1a2a4a";
    const fitHeight = () => {
      var _a2;
      node.setSize([
        node.size[0],
        node.computeSize([node.size[0], node.size[1]])[1]
      ]);
      (_a2 = node == null ? void 0 : node.graph) == null ? void 0 : _a2.setDirtyCanvas(true);
    };
    let updateLlmVisibility;
    const llmWidget = (_a = this.widgets) == null ? void 0 : _a.find((w) => w.name === "llm_model");
    if (llmWidget) {
      let doUpdateLlmVisibility = function() {
        var _a2;
        const model = llmWidget.value;
        const isNone = model === "none";
        toggleWidget(customWidget, model === "custom");
        toggleWidget(apiKeyWidget, needsApiKey(model));
        if (ollamaUrlWidget) toggleWidget(ollamaUrlWidget, !isNone);
        if (verifyWidget) toggleWidget(verifyWidget, !isNone);
        if (visionWidget) toggleWidget(visionWidget, !isNone);
        if (ptcWidget) toggleWidget(ptcWidget, !isNone);
        const noLlmModeWidget = (_a2 = node.widgets) == null ? void 0 : _a2.find((w) => w.name === "no_llm_mode");
        if (noLlmModeWidget) {
          toggleWidget(noLlmModeWidget, isNone);
          if (!noLlmModeWidget._cbHooked) {
            noLlmModeWidget._cbHooked = true;
            const origNoLlmCb = noLlmModeWidget.callback;
            noLlmModeWidget.callback = function(...args) {
              origNoLlmCb == null ? void 0 : origNoLlmCb.apply(this, args);
              updateNoLlmModeVisibility();
              fitHeight();
            };
          }
        }
        updateNoLlmModeVisibility();
        fitHeight();
      };
      const customWidget = (_b = this.widgets) == null ? void 0 : _b.find((w) => w.name === "custom_model");
      const apiKeyWidget = (_c = this.widgets) == null ? void 0 : _c.find((w) => w.name === "api_key");
      const ollamaUrlWidget = (_d = this.widgets) == null ? void 0 : _d.find((w) => w.name === "ollama_url");
      const verifyWidget = (_e = this.widgets) == null ? void 0 : _e.find((w) => w.name === "verify_output");
      const visionWidget = (_f = this.widgets) == null ? void 0 : _f.find((w) => w.name === "use_vision");
      const ptcWidget = (_g = this.widgets) == null ? void 0 : _g.find((w) => w.name === "ptc_mode");
      updateLlmVisibility = doUpdateLlmVisibility;
      doUpdateLlmVisibility();
      const origLlmCb = llmWidget.callback;
      llmWidget.callback = function(...args) {
        origLlmCb == null ? void 0 : origLlmCb.apply(this, args);
        doUpdateLlmVisibility();
      };
    }
    const saveWidget = (_h = this.widgets) == null ? void 0 : _h.find((w) => w.name === "save_output");
    const outputPathWidget = (_i = this.widgets) == null ? void 0 : _i.find((w) => w.name === "output_path");
    if (saveWidget && outputPathWidget) {
      let updateSaveVisibility = function() {
        toggleWidget(outputPathWidget, Boolean(saveWidget.value));
        fitHeight();
      };
      updateSaveVisibility();
      const origSaveCb = saveWidget.callback;
      saveWidget.callback = function(...args) {
        origSaveCb == null ? void 0 : origSaveCb.apply(this, args);
        updateSaveVisibility();
      };
    }
    const advancedWidget = (_j = this.widgets) == null ? void 0 : _j.find((w) => w.name === "advanced_options");
    const previewWidget = (_k = this.widgets) == null ? void 0 : _k.find((w) => w.name === "preview_mode");
    const crfWidget = (_l = this.widgets) == null ? void 0 : _l.find((w) => w.name === "crf");
    const encodingWidget = (_m = this.widgets) == null ? void 0 : _m.find((w) => w.name === "encoding_preset");
    const subtitleWidget = (_n = this.widgets) == null ? void 0 : _n.find((w) => w.name === "subtitle_path");
    (_o = this.widgets) == null ? void 0 : _o.find((w) => w.name === "use_vision");
    (_p = this.widgets) == null ? void 0 : _p.find((w) => w.name === "verify_output");
    (_q = this.widgets) == null ? void 0 : _q.find((w) => w.name === "whisper_device");
    (_r = this.widgets) == null ? void 0 : _r.find((w) => w.name === "whisper_model");
    const sam3MaxObjWidget = (_s = this.widgets) == null ? void 0 : _s.find((w) => w.name === "sam3_max_objects");
    const sam3ThreshWidget = (_t = this.widgets) == null ? void 0 : _t.find((w) => w.name === "sam3_det_threshold");
    const maskTypeWidget = (_u = this.widgets) == null ? void 0 : _u.find((w) => w.name === "mask_output_type");
    const batchWidget = (_v = this.widgets) == null ? void 0 : _v.find((w) => w.name === "batch_mode");
    const folderWidget = (_w = this.widgets) == null ? void 0 : _w.find((w) => w.name === "video_folder");
    const patternWidget = (_x = this.widgets) == null ? void 0 : _x.find((w) => w.name === "file_pattern");
    const concurrentWidget = (_y = this.widgets) == null ? void 0 : _y.find((w) => w.name === "max_concurrent");
    const trackTokensWidget = (_z = this.widgets) == null ? void 0 : _z.find((w) => w.name === "track_tokens");
    const logUsageWidget = (_A = this.widgets) == null ? void 0 : _A.find((w) => w.name === "log_usage");
    const allowDownloadsWidget = (_B = this.widgets) == null ? void 0 : _B.find((w) => w.name === "allow_model_downloads");
    const fluxSmoothingWidget = (_C = this.widgets) == null ? void 0 : _C.find((w) => w.name === "flux_smoothing");
    const mmaudioModeWidget = (_D = this.widgets) == null ? void 0 : _D.find((w) => w.name === "mmaudio_mode");
    (_E = this.widgets) == null ? void 0 : _E.find((w) => w.name === "marigold_output_type");
    (_F = this.widgets) == null ? void 0 : _F.find((w) => w.name === "video_depth_encoder");
    (_G = this.widgets) == null ? void 0 : _G.find((w) => w.name === "video_depth_colormap");
    function updateNoLlmModeVisibility() {
      var _a2, _b2, _c2, _d2, _e2, _f2, _g2, _h2, _i2, _j2, _k2, _l2;
      const adv = (_a2 = node.widgets) == null ? void 0 : _a2.find((w) => w.name === "advanced_options");
      const showAdvanced = Boolean(adv == null ? void 0 : adv.value);
      const llm = (_b2 = node.widgets) == null ? void 0 : _b2.find((w) => w.name === "llm_model");
      const isNone = (llm == null ? void 0 : llm.value) === "none";
      const noLlmMode = (_c2 = node.widgets) == null ? void 0 : _c2.find((w) => w.name === "no_llm_mode");
      const mode = isNone ? String((noLlmMode == null ? void 0 : noLlmMode.value) ?? "manual") : "";
      const showMarigold = showAdvanced && mode === "marigold";
      const showVda = showAdvanced && mode === "video_depth";
      const showUpscale = showAdvanced && mode === "ai_upscale";
      const showRembg = showAdvanced && mode === "rembg";
      const showWhisper = showAdvanced && (mode === "transcribe" || mode === "karaoke_subtitles");
      const mw = (_d2 = node.widgets) == null ? void 0 : _d2.find((w) => w.name === "marigold_output_type");
      const ve = (_e2 = node.widgets) == null ? void 0 : _e2.find((w) => w.name === "video_depth_encoder");
      const vc = (_f2 = node.widgets) == null ? void 0 : _f2.find((w) => w.name === "video_depth_colormap");
      const um = (_g2 = node.widgets) == null ? void 0 : _g2.find((w) => w.name === "upscale_model");
      const us = (_h2 = node.widgets) == null ? void 0 : _h2.find((w) => w.name === "upscale_scale");
      const rm = (_i2 = node.widgets) == null ? void 0 : _i2.find((w) => w.name === "rembg_model");
      const rb = (_j2 = node.widgets) == null ? void 0 : _j2.find((w) => w.name === "rembg_background");
      const wd = (_k2 = node.widgets) == null ? void 0 : _k2.find((w) => w.name === "whisper_device");
      const wm = (_l2 = node.widgets) == null ? void 0 : _l2.find((w) => w.name === "whisper_model");
      if (mw) toggleWidget(mw, showMarigold);
      if (ve) toggleWidget(ve, showVda);
      if (vc) toggleWidget(vc, showVda);
      if (um) toggleWidget(um, showUpscale);
      if (us) toggleWidget(us, showUpscale);
      if (rm) toggleWidget(rm, showRembg);
      if (rb) toggleWidget(rb, showRembg);
      if (wd) toggleWidget(wd, showWhisper);
      if (wm) toggleWidget(wm, showWhisper);
    }
    function updateAdvancedVisibility() {
      var _a2;
      const show = Boolean(advancedWidget == null ? void 0 : advancedWidget.value);
      if (previewWidget) toggleWidget(previewWidget, show);
      if (subtitleWidget) toggleWidget(subtitleWidget, show);
      if (crfWidget) toggleWidget(crfWidget, show);
      if (encodingWidget) toggleWidget(encodingWidget, show);
      if (sam3MaxObjWidget) toggleWidget(sam3MaxObjWidget, show);
      if (sam3ThreshWidget) toggleWidget(sam3ThreshWidget, show);
      if (maskTypeWidget) toggleWidget(maskTypeWidget, show);
      const fluxKleinWidget = (_a2 = node.widgets) == null ? void 0 : _a2.find((w) => w.name === "use_flux_klein");
      const showFlux = show && Boolean(fluxKleinWidget == null ? void 0 : fluxKleinWidget.value);
      if (fluxSmoothingWidget) toggleWidget(fluxSmoothingWidget, showFlux);
      if (mmaudioModeWidget) toggleWidget(mmaudioModeWidget, show);
      if (batchWidget) toggleWidget(batchWidget, show);
      const showBatch = show && Boolean(batchWidget == null ? void 0 : batchWidget.value);
      if (folderWidget) toggleWidget(folderWidget, showBatch);
      if (patternWidget) toggleWidget(patternWidget, showBatch);
      if (concurrentWidget) toggleWidget(concurrentWidget, showBatch);
      if (trackTokensWidget) toggleWidget(trackTokensWidget, show);
      if (logUsageWidget) toggleWidget(logUsageWidget, show);
      if (allowDownloadsWidget) toggleWidget(allowDownloadsWidget, show);
      updateNoLlmModeVisibility();
      fitHeight();
    }
    if (advancedWidget) {
      updateAdvancedVisibility();
      const origAdvCb = advancedWidget.callback;
      advancedWidget.callback = function(...args) {
        origAdvCb == null ? void 0 : origAdvCb.apply(this, args);
        updateAdvancedVisibility();
      };
    }
    const fluxKleinToggle = (_H = this.widgets) == null ? void 0 : _H.find((w) => w.name === "use_flux_klein");
    if (fluxKleinToggle) {
      const origFluxCb = fluxKleinToggle.callback;
      fluxKleinToggle.callback = function(...args) {
        origFluxCb == null ? void 0 : origFluxCb.apply(this, args);
        updateAdvancedVisibility();
      };
    }
    if (batchWidget) {
      let updateBatchVisibility = function() {
        const showAdvanced = Boolean((advancedWidget == null ? void 0 : advancedWidget.value) ?? true);
        const show = Boolean(batchWidget.value) && showAdvanced;
        if (folderWidget) toggleWidget(folderWidget, show);
        if (patternWidget) toggleWidget(patternWidget, show);
        if (concurrentWidget) toggleWidget(concurrentWidget, show);
        fitHeight();
      };
      updateBatchVisibility();
      const origBatchCb = batchWidget.callback;
      batchWidget.callback = function(...args) {
        origBatchCb == null ? void 0 : origBatchCb.apply(this, args);
        updateBatchVisibility();
      };
    }
    const origOnConnectionsChange = this.onConnectionsChange;
    this.onConnectionsChange = function(type, slotIndex, isConnected, link, ioSlot) {
      origOnConnectionsChange == null ? void 0 : origOnConnectionsChange.apply(this, arguments);
      if (type === LiteGraph.INPUT) {
        updateDynamicSlots(this, "images_", "IMAGE", []);
        updateDynamicSlots(this, "image_", "IMAGE", ["images_", "image_path_"]);
        updateDynamicSlots(this, "audio_", "AUDIO", []);
        updateDynamicSlots(this, "video_", "STRING", ["video_path", "video_folder"]);
        updateDynamicSlots(this, "image_path_", "STRING", []);
        updateDynamicSlots(this, "text_", "STRING", []);
        fitHeight();
      }
    };
    const origOnConfigure = this.onConfigure;
    this.onConfigure = function(info) {
      origOnConfigure == null ? void 0 : origOnConfigure.apply(this, arguments);
      if (info == null ? void 0 : info.inputs) {
        const existingNames = new Set(this.inputs.map((i) => i.name));
        for (const saved of info.inputs) {
          if (!existingNames.has(saved.name)) {
            const isDynamic = DYNAMIC_PREFIXES.some(({ prefix, excludes }) => {
              if (!saved.name.startsWith(prefix)) return false;
              if (excludes.some((ep) => saved.name.startsWith(ep))) return false;
              return true;
            });
            if (isDynamic) {
              this.addInput(saved.name, saved.type);
              existingNames.add(saved.name);
            }
          }
        }
        for (const { prefix, type, excludes } of DYNAMIC_PREFIXES) {
          let maxLinkedIdx = -1;
          for (const saved of info.inputs) {
            if (!saved.name.startsWith(prefix)) continue;
            if (excludes.some((ep) => saved.name.startsWith(ep))) continue;
            if (saved.link != null) {
              const letter = saved.name.slice(prefix.length);
              const idx = SLOT_LABELS.indexOf(letter);
              if (idx > maxLinkedIdx) maxLinkedIdx = idx;
            }
          }
          if (maxLinkedIdx >= 0) {
            const nextLetter = SLOT_LABELS[maxLinkedIdx + 1];
            if (nextLetter) {
              const nextName = `${prefix}${nextLetter}`;
              if (!existingNames.has(nextName)) {
                this.addInput(nextName, type);
                existingNames.add(nextName);
              }
            }
          }
        }
      }
      function restoreVisibility() {
        updateAdvancedVisibility();
        if (updateLlmVisibility) updateLlmVisibility();
        fitHeight();
      }
      restoreVisibility();
      setTimeout(restoreVisibility, 0);
      setTimeout(restoreVisibility, 300);
    };
    return result;
  };
  const origGetExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
  nodeType.prototype.getExtraMenuOptions = function(_, options) {
    origGetExtraMenuOptions == null ? void 0 : origGetExtraMenuOptions.apply(this, arguments);
    if (this._previousPrompt) {
      options.unshift({
        content: "↩️ Restore Previous Prompt",
        callback: () => {
          setPrompt(this, this._previousPrompt, true, "#4a7a4a");
        }
      });
    }
    const presetItems = buildPresetMenu(this);
    presetItems.push(
      // @ts-expect-error — null separator is valid in LiteGraph menus
      null,
      {
        content: "🎲 Random Example",
        callback: () => {
          const randomPrompt = RANDOM_PROMPTS[Math.floor(Math.random() * RANDOM_PROMPTS.length)];
          setPrompt(this, randomPrompt, true, "#8a4a8a");
        }
      },
      {
        content: "📋 Copy Prompt",
        callback: () => {
          var _a;
          const promptWidget = (_a = this.widgets) == null ? void 0 : _a.find((w) => w.name === "prompt");
          const text = promptWidget == null ? void 0 : promptWidget.value;
          if (text && navigator.clipboard) {
            navigator.clipboard.writeText(text).then(() => flashNode(this, "#4a7a4a")).catch(() => flashNode(this, "#7a4a4a"));
          }
        }
      },
      {
        content: "📥 Paste (Append)",
        callback: () => handlePaste(this, false)
      },
      {
        content: "📥 Paste (Replace)",
        callback: () => handlePaste(this, true)
      },
      {
        content: "🗑️ Clear Prompt",
        callback: () => {
          var _a;
          const promptWidget = (_a = this.widgets) == null ? void 0 : _a.find((w) => w.name === "prompt");
          if (promptWidget && promptWidget.value && String(promptWidget.value).trim() !== "") {
            this._previousPrompt = String(promptWidget.value);
            promptWidget.value = "";
            this.setDirtyCanvas(true, true);
            flashNode(this, "#7a3a3a");
          }
        }
      }
    );
    options.unshift(
      {
        content: "FFMPEGA Presets",
        submenu: {
          options: presetItems
        }
      },
      null
    );
  };
}
const VIDEO_ACCEPT$1 = [
  "video/webm",
  "video/mp4",
  "video/x-matroska",
  "video/quicktime",
  "video/x-msvideo",
  "video/x-flv",
  "video/x-ms-wmv",
  "video/mpeg",
  "video/3gpp",
  "image/gif"
].join(",");
const VIDEO_EXTENSIONS$1 = [
  "mp4",
  "avi",
  "mov",
  "mkv",
  "webm",
  "flv",
  "wmv",
  "m4v",
  "mpg",
  "mpeg",
  "ts",
  "mts",
  "gif"
];
const WATCH_WIDGETS = ["video_path", "start_time", "duration", "fps", "max_frames"];
const PASSTHROUGH_EVENTS$1 = [
  "contextmenu",
  "pointerdown",
  "mousewheel",
  "pointermove",
  "pointerup"
];
function formatTime(sec) {
  if (sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = (sec % 60).toFixed(1);
  return m > 0 ? `${m}:${s.padStart(4, "0")}` : `${s}s`;
}
function registerFrameExtractNode(nodeType, nodeData) {
  if (nodeData.name !== "FFMPEGAFrameExtract") return;
  const onNodeCreated = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function() {
    const result = onNodeCreated == null ? void 0 : onNodeCreated.apply(this, arguments);
    const node = this;
    this.color = "#2a4a5a";
    this.bgcolor = "#1a3a4a";
    const { fileInput, uploadBtn, updateBtnStyle: updateUploadBtn } = createUploadButton(VIDEO_ACCEPT$1);
    document.body.append(fileInput);
    this.addDOMWidget("upload_button", "btn", uploadBtn, {
      serialize: false
    });
    const previewContainer = document.createElement("div");
    previewContainer.className = "ffmpega_preview";
    previewContainer.style.cssText = "width:100%;background:#1a1a1a;border-radius:6px;overflow:hidden;position:relative;";
    const videoEl = document.createElement("video");
    videoEl.controls = true;
    videoEl.loop = true;
    videoEl.muted = true;
    videoEl.volume = 1;
    videoEl.setAttribute("aria-label", "Frame extraction preview");
    videoEl.style.cssText = "width:100%;display:block;";
    let userUnmuted = false;
    videoEl.addEventListener("volumechange", () => {
      userUnmuted = !videoEl.muted;
    });
    videoEl.addEventListener("play", () => {
      if (userUnmuted) videoEl.muted = false;
    });
    videoEl.addEventListener("loadedmetadata", () => {
      var _a;
      previewWidget.aspectRatio = videoEl.videoWidth / videoEl.videoHeight;
      node.setSize([
        node.size[0],
        node.computeSize([node.size[0], node.size[1]])[1]
      ]);
      (_a = node == null ? void 0 : node.graph) == null ? void 0 : _a.setDirtyCanvas(true);
    });
    const infoEl = document.createElement("div");
    infoEl.style.cssText = "padding:4px 8px;font-size:11px;color:#aaa;font-family:monospace;background:#111;";
    infoEl.textContent = "No video loaded";
    infoEl.setAttribute("role", "status");
    infoEl.setAttribute("aria-live", "polite");
    videoEl.addEventListener("error", () => {
      var _a;
      previewContainer.style.display = "none";
      infoEl.textContent = "No video loaded";
      node.setSize([
        node.size[0],
        node.computeSize([node.size[0], node.size[1]])[1]
      ]);
      (_a = node == null ? void 0 : node.graph) == null ? void 0 : _a.setDirtyCanvas(true);
    });
    previewContainer.appendChild(videoEl);
    previewContainer.appendChild(infoEl);
    addDownloadOverlay(previewContainer, videoEl);
    for (const evt of PASSTHROUGH_EVENTS$1) {
      previewContainer.addEventListener(evt, (e) => {
        e.stopPropagation();
      }, true);
    }
    const previewWidget = this.addDOMWidget(
      "videopreview",
      "preview",
      previewContainer,
      {
        serialize: false,
        hideOnZoom: false,
        getValue() {
          return previewContainer.value;
        },
        setValue(v) {
          previewContainer.value = v;
        }
      }
    );
    previewWidget.aspectRatio = null;
    previewWidget.computeSize = function(width) {
      if (this.aspectRatio && previewContainer.style.display !== "none") {
        const h = (node.size[0] - 20) / this.aspectRatio + 10;
        return [width, Math.max(h, 0) + 30];
      }
      return [width, 34];
    };
    let _previewDebounce = null;
    const updateLivePreview = () => {
      var _a, _b, _c, _d, _e;
      const pathWidget = (_a = node.widgets) == null ? void 0 : _a.find((w) => w.name === "video_path");
      const startWidget = (_b = node.widgets) == null ? void 0 : _b.find((w) => w.name === "start_time");
      const durWidget = (_c = node.widgets) == null ? void 0 : _c.find((w) => w.name === "duration");
      const videoPath = (_d = pathWidget == null ? void 0 : pathWidget.value) == null ? void 0 : _d.trim();
      if (!videoPath) {
        previewContainer.style.display = "none";
        infoEl.textContent = "No video loaded";
        node.setSize([
          node.size[0],
          node.computeSize([node.size[0], node.size[1]])[1]
        ]);
        (_e = node == null ? void 0 : node.graph) == null ? void 0 : _e.setDirtyCanvas(true);
        return;
      }
      const startTime = (startWidget == null ? void 0 : startWidget.value) ?? 0;
      const duration = (durWidget == null ? void 0 : durWidget.value) ?? 0;
      const params = new URLSearchParams({
        path: videoPath,
        start_time: String(startTime)
      });
      if (duration > 0) {
        params.set("duration", String(duration));
      }
      const previewUrl = api.apiURL("/ffmpega/preview?" + params.toString());
      previewContainer.style.display = "";
      infoEl.textContent = "Loading preview...";
      videoEl.src = previewUrl;
      const infoParams = new URLSearchParams({ path: videoPath });
      fetch(api.apiURL("/ffmpega/video_info?" + infoParams.toString())).then((r) => r.json()).then((info) => {
        var _a2, _b2;
        if (!(info == null ? void 0 : info.width)) return;
        const fpsW = (_a2 = node.widgets) == null ? void 0 : _a2.find((w) => w.name === "fps");
        const extractFps = (fpsW == null ? void 0 : fpsW.value) ?? 1;
        const maxFramesW = (_b2 = node.widgets) == null ? void 0 : _b2.find((w) => w.name === "max_frames");
        const maxFrames = (maxFramesW == null ? void 0 : maxFramesW.value) ?? 100;
        const actualDur = Math.min(duration, (info.duration ?? 0) - startTime);
        const expectedFrames = Math.min(
          Math.max(0, Math.floor(actualDur * extractFps)),
          maxFrames
        );
        const startFmt = formatTime(startTime);
        const endFmt = formatTime(startTime + actualDur);
        infoEl.textContent = `~${expectedFrames} frames • ${info.width}×${info.height} • ${startFmt}–${endFmt} @ ${extractFps}fps`;
      }).catch(() => {
        infoEl.textContent = "Preview loaded";
      });
    };
    const debouncedPreview = () => {
      if (_previewDebounce) clearTimeout(_previewDebounce);
      _previewDebounce = setTimeout(updateLivePreview, 600);
    };
    const widgetValues = {};
    const pollInterval = setInterval(() => {
      var _a;
      if (!node.graph) {
        clearInterval(pollInterval);
        return;
      }
      let changed = false;
      for (const name of WATCH_WIDGETS) {
        const w = (_a = node.widgets) == null ? void 0 : _a.find((ww) => ww.name === name);
        if (w && widgetValues[name] !== w.value) {
          widgetValues[name] = w.value;
          changed = true;
        }
      }
      if (changed) debouncedPreview();
    }, 500);
    setTimeout(updateLivePreview, 300);
    const origOnExecuted = this.onExecuted;
    this.onExecuted = function(data) {
      var _a, _b;
      origOnExecuted == null ? void 0 : origOnExecuted.apply(this, arguments);
      if ((_a = data == null ? void 0 : data.video) == null ? void 0 : _a[0]) {
        const v = data.video[0];
        const params = new URLSearchParams({
          filename: v.filename,
          subfolder: v.subfolder || "",
          type: v.type || "temp",
          timestamp: String(Date.now())
        });
        previewContainer.style.display = "";
        videoEl.src = api.apiURL("/view?" + params.toString());
      }
      if ((_b = data == null ? void 0 : data.frame_info) == null ? void 0 : _b[0]) {
        const fi = data.frame_info[0];
        const startFmt = formatTime(fi.start);
        const endFmt = formatTime(fi.end);
        const durFmt = formatTime(fi.duration);
        infoEl.textContent = `${fi.count} frames • ${fi.width}×${fi.height} • ${startFmt}–${endFmt} (${durFmt}) • src ${fi.source_fps}fps → extract ${fi.fps}fps`;
      }
    };
    const origOnRemoved = this.onRemoved;
    this.onRemoved = function() {
      clearInterval(pollInterval);
      fileInput == null ? void 0 : fileInput.remove();
      origOnRemoved == null ? void 0 : origOnRemoved.apply(this, arguments);
    };
    const showError = (msg) => {
      var _a;
      flashNode(node, "#7a4a4a");
      infoEl.textContent = msg;
      previewContainer.style.display = "";
      node.setSize([
        node.size[0],
        node.computeSize([node.size[0], node.size[1]])[1]
      ]);
      (_a = node == null ? void 0 : node.graph) == null ? void 0 : _a.setDirtyCanvas(true);
    };
    const setUploadState = (uploading, filename = "") => {
      if (uploading) {
        uploadBtn.innerHTML = `<span aria-hidden="true">⏳</span> Uploading...`;
        uploadBtn.setAttribute("aria-label", "Uploading Video");
        uploadBtn.disabled = true;
        uploadBtn.style.cursor = "wait";
        infoEl.textContent = `Uploading ${filename}...`;
        previewContainer.style.display = "";
        videoEl.style.display = "none";
      } else {
        uploadBtn.innerHTML = "Upload Video...";
        uploadBtn.setAttribute("aria-label", "Upload Video");
        uploadBtn.disabled = false;
        uploadBtn.style.cursor = "pointer";
        videoEl.style.display = "block";
      }
      node.setDirtyCanvas(true, true);
      node.setSize([
        node.size[0],
        node.computeSize([node.size[0], node.size[1]])[1]
      ]);
    };
    const handleUpload = async (file) => {
      var _a;
      setUploadState(true, file.name);
      const body = new FormData();
      body.append("image", file);
      try {
        const resp = await fetch("/upload/image", {
          method: "POST",
          body
        });
        if (resp.status !== 200) {
          showError("Upload failed: " + resp.statusText);
          return false;
        }
        const data = await resp.json();
        const filename = data.name;
        const pathWidget = (_a = node.widgets) == null ? void 0 : _a.find((w) => w.name === "video_path");
        if (pathWidget) {
          const subfolder = data.subfolder || "";
          const inputPath = subfolder ? `input/${subfolder}/${filename}` : `input/${filename}`;
          pathWidget.value = inputPath;
        }
        debouncedPreview();
        flashNode(node, "#4a7a4a");
        return true;
      } catch (err) {
        console.warn("FFMPEGA: Video upload failed", err);
        showError("Upload error: " + err);
        return false;
      } finally {
        setUploadState(false);
      }
    };
    fileInput.onchange = async () => {
      var _a;
      if ((_a = fileInput.files) == null ? void 0 : _a.length) {
        await handleUpload(fileInput.files[0]);
      }
    };
    this.onDragOver = (e) => {
      var _a, _b, _c;
      if ((_c = (_b = (_a = e == null ? void 0 : e.dataTransfer) == null ? void 0 : _a.types) == null ? void 0 : _b.includes) == null ? void 0 : _c.call(_b, "Files")) {
        if (!uploadBtn.disabled) {
          if (!Object.prototype.hasOwnProperty.call(uploadBtn, "_originalInnerHTML")) {
            uploadBtn._originalInnerHTML = uploadBtn.innerHTML;
          }
          if (!Object.prototype.hasOwnProperty.call(uploadBtn, "_originalBorder")) {
            uploadBtn._originalBorder = uploadBtn.style.border;
          }
          if (!Object.prototype.hasOwnProperty.call(uploadBtn, "_originalAriaLabel")) {
            uploadBtn._originalAriaLabel = uploadBtn.getAttribute("aria-label");
          }
          uploadBtn.innerHTML = `<span aria-hidden="true">📂</span> Drop to Upload`;
          uploadBtn.setAttribute("aria-label", "Drop to Upload");
          uploadBtn.style.border = "1px dashed #4a6a8a";
          uploadBtn.style.backgroundColor = "#333";
          if (uploadBtn._dragTimeout) clearTimeout(uploadBtn._dragTimeout);
          uploadBtn._dragTimeout = setTimeout(() => {
            if (!uploadBtn.disabled) {
              if (Object.prototype.hasOwnProperty.call(uploadBtn, "_originalInnerHTML")) {
                uploadBtn.innerHTML = uploadBtn._originalInnerHTML;
                delete uploadBtn._originalInnerHTML;
              }
              if (Object.prototype.hasOwnProperty.call(uploadBtn, "_originalBorder")) {
                uploadBtn.style.border = uploadBtn._originalBorder;
                delete uploadBtn._originalBorder;
              }
              if (Object.prototype.hasOwnProperty.call(uploadBtn, "_originalAriaLabel")) {
                if (uploadBtn._originalAriaLabel) {
                  uploadBtn.setAttribute("aria-label", uploadBtn._originalAriaLabel);
                } else {
                  uploadBtn.removeAttribute("aria-label");
                }
                delete uploadBtn._originalAriaLabel;
              }
              updateUploadBtn();
            }
          }, 100);
        }
        return true;
      }
      return false;
    };
    this.onDragDrop = async (e) => {
      var _a, _b, _c, _d, _e, _f;
      if (!((_c = (_b = (_a = e == null ? void 0 : e.dataTransfer) == null ? void 0 : _a.types) == null ? void 0 : _b.includes) == null ? void 0 : _c.call(_b, "Files"))) return false;
      const file = (_e = (_d = e.dataTransfer) == null ? void 0 : _d.files) == null ? void 0 : _e[0];
      if (!file) return false;
      const ext = (_f = file.name.split(".").pop()) == null ? void 0 : _f.toLowerCase();
      if (!ext || !VIDEO_EXTENSIONS$1.includes(ext)) {
        showError("Invalid file type: " + ext);
        return false;
      }
      return await handleUpload(file);
    };
    const getVideoUrl = () => videoEl.src || null;
    addVideoPreviewMenu(node, videoEl, previewContainer, previewWidget, getVideoUrl);
    return result;
  };
}
const VIDEO_ACCEPT = [
  "video/webm",
  "video/mp4",
  "video/x-matroska",
  "video/quicktime",
  "video/x-msvideo",
  "video/x-flv",
  "video/x-ms-wmv",
  "video/mpeg",
  "video/3gpp",
  "image/gif"
].join(",");
const VIDEO_EXTENSIONS = [
  "mp4",
  "avi",
  "mov",
  "mkv",
  "webm",
  "flv",
  "wmv",
  "m4v",
  "mpg",
  "mpeg",
  "ts",
  "mts",
  "gif"
];
const TRIM_WIDGETS = ["force_rate", "skip_first_frames", "frame_load_cap", "select_every_nth"];
const PASSTHROUGH_EVENTS = [
  "contextmenu",
  "pointerdown",
  "mousewheel",
  "pointermove",
  "pointerup"
];
function formatTimeLV(sec) {
  if (sec < 0) sec = 0;
  const m = Math.floor(sec / 60);
  const s = (sec % 60).toFixed(1);
  return m > 0 ? `${m}:${s.padStart(4, "0")}` : `${s}s`;
}
function registerLoadVideoNode(nodeType, nodeData) {
  if (nodeData.name !== "FFMPEGALoadVideoPath") return;
  const onNodeCreated = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function() {
    var _a;
    const result = onNodeCreated == null ? void 0 : onNodeCreated.apply(this, arguments);
    const node = this;
    this.color = "#5a4a2a";
    this.bgcolor = "#4a3a1a";
    const _syncDynamicOutputs = () => {
      const imagesIn = node.findInputSlot("images");
      const audioIn = node.findInputSlot("audio");
      const anyConnected = imagesIn >= 0 && node.inputs[imagesIn].link != null || audioIn >= 0 && node.inputs[audioIn].link != null;
      const imagesOut = node.findOutputSlot("images");
      const audioOut = node.findOutputSlot("audio");
      const hasOutputs = imagesOut >= 0 || audioOut >= 0;
      if (anyConnected && !hasOutputs) {
        node.addOutput("images", "IMAGE");
        node.addOutput("audio", "AUDIO");
      } else if (!anyConnected && hasOutputs) {
        const aIdx = node.findOutputSlot("audio");
        if (aIdx >= 0) node.removeOutput(aIdx);
        const iIdx = node.findOutputSlot("images");
        if (iIdx >= 0) node.removeOutput(iIdx);
      }
      node.setDirtyCanvas(true, true);
    };
    requestAnimationFrame(() => {
      const aIdx = node.findOutputSlot("audio");
      if (aIdx >= 0) node.removeOutput(aIdx);
      const iIdx = node.findOutputSlot("images");
      if (iIdx >= 0) node.removeOutput(iIdx);
      node.setDirtyCanvas(true, true);
    });
    const origOnCC = this.onConnectionsChange;
    this.onConnectionsChange = function(type, slotIndex, isConnected, link, ioSlot) {
      var _a2, _b;
      origOnCC == null ? void 0 : origOnCC.apply(this, arguments);
      if (type === LiteGraph.INPUT) {
        const name = (_b = (_a2 = this.inputs) == null ? void 0 : _a2[slotIndex]) == null ? void 0 : _b.name;
        if (name === "images" || name === "audio") {
          _syncDynamicOutputs();
        }
      }
    };
    const origConfigure = this.onConfigure;
    this.onConfigure = function(data) {
      origConfigure == null ? void 0 : origConfigure.apply(this, arguments);
      requestAnimationFrame(_syncDynamicOutputs);
    };
    const { fileInput, uploadBtn, updateBtnStyle: updateBtn } = createUploadButton(VIDEO_ACCEPT);
    document.body.append(fileInput);
    this.addDOMWidget("upload_button", "btn", uploadBtn, {
      serialize: false
    });
    const previewContainer = document.createElement("div");
    previewContainer.className = "ffmpega_preview";
    previewContainer.style.cssText = "width:100%;background:#1a1a1a;border-radius:6px;overflow:hidden;position:relative;";
    const videoEl = document.createElement("video");
    videoEl.controls = true;
    videoEl.loop = true;
    videoEl.muted = true;
    videoEl.setAttribute("aria-label", "Video preview");
    videoEl.style.cssText = "width:100%;display:block;";
    let _srcMeta = null;
    let _effAvailFrames = 0;
    let _effFps = 0;
    let _effSkipFirst = 0;
    let _effInfoText = "";
    const infoEl = document.createElement("div");
    infoEl.style.cssText = "padding:4px 8px;font-size:11px;color:#aaa;font-family:monospace;background:#111;";
    infoEl.textContent = "No video selected";
    infoEl.setAttribute("role", "status");
    infoEl.setAttribute("aria-live", "polite");
    const updateDynamicInfo = () => {
      var _a2, _b, _c, _d, _e, _f, _g, _h;
      if (!_srcMeta) {
        infoEl.textContent = "No video selected";
        return;
      }
      const forceRate = ((_b = (_a2 = node.widgets) == null ? void 0 : _a2.find((w) => w.name === "force_rate")) == null ? void 0 : _b.value) ?? 0;
      const skipFirst = ((_d = (_c = node.widgets) == null ? void 0 : _c.find((w) => w.name === "skip_first_frames")) == null ? void 0 : _d.value) ?? 0;
      const frameCap = ((_f = (_e = node.widgets) == null ? void 0 : _e.find((w) => w.name === "frame_load_cap")) == null ? void 0 : _f.value) ?? 0;
      const everyNth = ((_h = (_g = node.widgets) == null ? void 0 : _g.find((w) => w.name === "select_every_nth")) == null ? void 0 : _h.value) ?? 1;
      const srcFps = _srcMeta.fps || 24;
      const srcDuration = _srcMeta.duration || 0;
      const srcFrames = _srcMeta.frames || Math.round(srcDuration * srcFps);
      const effFps = forceRate > 0 ? forceRate : srcFps;
      let availFrames = forceRate > 0 ? Math.ceil(srcDuration * forceRate) : srcFrames;
      availFrames = Math.max(0, availFrames - skipFirst);
      if (everyNth > 1) {
        availFrames = Math.max(0, Math.floor(availFrames / everyNth));
      }
      if (frameCap > 0) {
        availFrames = Math.min(availFrames, frameCap);
      }
      const effDuration = effFps > 0 && availFrames > 0 ? availFrames / effFps : srcDuration;
      const startTime = effFps > 0 ? skipFirst / effFps : 0;
      const parts = [];
      if (_srcMeta.width && _srcMeta.height) {
        parts.push(`${_srcMeta.width}×${_srcMeta.height}`);
      }
      if (forceRate > 0 && forceRate !== srcFps) {
        parts.push(`${srcFps}fps → ${forceRate}fps`);
      } else {
        parts.push(`${srcFps}fps`);
      }
      if (availFrames !== srcFrames) {
        parts.push(`${availFrames} frames (of ${srcFrames})`);
      } else {
        parts.push(`${availFrames} frames`);
      }
      if (Math.abs(effDuration - srcDuration) > 0.1) {
        parts.push(`${formatTimeLV(effDuration)} (of ${formatTimeLV(srcDuration)})`);
      } else {
        parts.push(formatTimeLV(srcDuration));
      }
      if (startTime > 0.05) {
        parts.push(`from ${formatTimeLV(startTime)}`);
      }
      infoEl.textContent = parts.join(" • ");
      _effInfoText = infoEl.textContent;
      _effAvailFrames = availFrames;
      _effFps = effFps;
      _effSkipFirst = skipFirst;
    };
    videoEl.addEventListener("loadedmetadata", () => {
      var _a2, _b;
      previewWidget.aspectRatio = videoEl.videoWidth / videoEl.videoHeight;
      _srcMeta = {
        width: videoEl.videoWidth,
        height: videoEl.videoHeight,
        fps: 0,
        duration: videoEl.duration,
        frames: 0
      };
      const vidWidget = (_a2 = node.widgets) == null ? void 0 : _a2.find((w) => w.name === "video");
      if (vidWidget == null ? void 0 : vidWidget.value) {
        const infoParams = new URLSearchParams({
          path: "input/" + String(vidWidget.value)
        });
        fetch(api.apiURL("/ffmpega/video_info?" + infoParams.toString())).then((r) => r.json()).then((info) => {
          if ((info == null ? void 0 : info.fps) && _srcMeta) {
            _srcMeta.fps = info.fps;
            _srcMeta.frames = info.frames || Math.round((info.duration ?? 0) * info.fps);
            _srcMeta.duration = info.duration || _srcMeta.duration;
          }
          updateDynamicInfo();
        }).catch(() => updateDynamicInfo());
      } else {
        updateDynamicInfo();
      }
      node.setSize([
        node.size[0],
        node.computeSize([node.size[0], node.size[1]])[1]
      ]);
      (_b = node == null ? void 0 : node.graph) == null ? void 0 : _b.setDirtyCanvas(true);
    });
    videoEl.addEventListener("error", () => {
      var _a2;
      previewContainer.style.display = "none";
      node.setSize([
        node.size[0],
        node.computeSize([node.size[0], node.size[1]])[1]
      ]);
      (_a2 = node == null ? void 0 : node.graph) == null ? void 0 : _a2.setDirtyCanvas(true);
    });
    let _lvDebounce = null;
    const lvWidgetValues = {};
    let _playStart = 0;
    let _playEnd = Infinity;
    videoEl.addEventListener("timeupdate", () => {
      if (_playEnd < Infinity && videoEl.currentTime >= _playEnd) {
        videoEl.currentTime = _playStart;
      }
      if (_srcMeta && _srcMeta.fps > 0 && _effAvailFrames > 0 && _effInfoText) {
        const elapsed = Math.max(0, videoEl.currentTime - _playStart);
        const curFrame = Math.min(
          Math.floor(elapsed * _effFps) + 1,
          _effAvailFrames
        );
        const srcFrame = curFrame + _effSkipFirst;
        infoEl.textContent = `▶ ${curFrame}/${_effAvailFrames} (src frame ${srcFrame}) • ${_effInfoText}`;
      }
    });
    const updatePlaybackRange = () => {
      var _a2, _b, _c, _d, _e, _f, _g, _h;
      if (!_srcMeta || !_srcMeta.fps) return;
      const forceRate = ((_b = (_a2 = node.widgets) == null ? void 0 : _a2.find((w) => w.name === "force_rate")) == null ? void 0 : _b.value) ?? 0;
      const skipFirst = ((_d = (_c = node.widgets) == null ? void 0 : _c.find((w) => w.name === "skip_first_frames")) == null ? void 0 : _d.value) ?? 0;
      const frameCap = ((_f = (_e = node.widgets) == null ? void 0 : _e.find((w) => w.name === "frame_load_cap")) == null ? void 0 : _f.value) ?? 0;
      const everyNth = ((_h = (_g = node.widgets) == null ? void 0 : _g.find((w) => w.name === "select_every_nth")) == null ? void 0 : _h.value) ?? 1;
      const srcFps = _srcMeta.fps;
      const effFps = forceRate > 0 ? forceRate : srcFps;
      _playStart = effFps > 0 ? skipFirst / effFps : 0;
      let availFrames = forceRate > 0 ? Math.ceil(_srcMeta.duration * forceRate) : _srcMeta.frames || Math.round(_srcMeta.duration * srcFps);
      availFrames = Math.max(0, availFrames - skipFirst);
      if (everyNth > 1) availFrames = Math.floor(availFrames / everyNth);
      if (frameCap > 0) availFrames = Math.min(availFrames, frameCap);
      if (effFps > 0 && availFrames > 0) {
        _playEnd = _playStart + availFrames / effFps;
      } else {
        _playEnd = Infinity;
      }
      if (isFinite(_playEnd) && _playEnd > _srcMeta.duration) {
        _playEnd = _srcMeta.duration;
      }
      if (isFinite(_playStart) && _playStart < videoEl.duration) {
        videoEl.currentTime = _playStart;
      }
    };
    const lvPollInterval = setInterval(() => {
      var _a2;
      if (!node.graph) {
        clearInterval(lvPollInterval);
        return;
      }
      let changed = false;
      for (const name of TRIM_WIDGETS) {
        const w = (_a2 = node.widgets) == null ? void 0 : _a2.find((ww) => ww.name === name);
        if (w && lvWidgetValues[name] !== w.value) {
          lvWidgetValues[name] = w.value;
          changed = true;
        }
      }
      if (changed) {
        if (_lvDebounce) clearTimeout(_lvDebounce);
        _lvDebounce = setTimeout(() => {
          updateDynamicInfo();
          updatePlaybackRange();
        }, 300);
      }
    }, 500);
    previewContainer.appendChild(videoEl);
    previewContainer.appendChild(infoEl);
    addDownloadOverlay(previewContainer, videoEl);
    for (const evt of PASSTHROUGH_EVENTS) {
      previewContainer.addEventListener(evt, (e) => {
        e.stopPropagation();
      }, true);
    }
    const previewWidget = this.addDOMWidget(
      "videopreview",
      "preview",
      previewContainer,
      {
        serialize: false,
        hideOnZoom: false,
        getValue() {
          return previewContainer.value;
        },
        setValue(v) {
          previewContainer.value = v;
        }
      }
    );
    previewWidget.aspectRatio = null;
    previewWidget.computeSize = function(width) {
      if (this.aspectRatio && previewContainer.style.display !== "none") {
        const h = (node.size[0] - 20) / this.aspectRatio + 10;
        return [width, Math.max(h, 0) + 30];
      }
      return [width, 34];
    };
    const updatePreview = (filename) => {
      if (!filename) {
        previewContainer.style.display = "none";
        infoEl.textContent = "No video selected";
        _srcMeta = null;
        return;
      }
      previewContainer.style.display = "";
      const params = new URLSearchParams({
        filename,
        type: "input",
        timestamp: String(Date.now())
      });
      videoEl.src = api.apiURL("/view?" + params.toString());
      infoEl.textContent = "Loading...";
    };
    const showError = (msg) => {
      var _a2;
      flashNode(node, "#7a4a4a");
      infoEl.textContent = msg;
      previewContainer.style.display = "";
      node.setSize([
        node.size[0],
        node.computeSize([node.size[0], node.size[1]])[1]
      ]);
      (_a2 = node == null ? void 0 : node.graph) == null ? void 0 : _a2.setDirtyCanvas(true);
    };
    const videoWidget = (_a = this.widgets) == null ? void 0 : _a.find(
      (w) => w.name === "video"
    );
    const origOnRemoved = this.onRemoved;
    this.onRemoved = function() {
      clearInterval(lvPollInterval);
      fileInput == null ? void 0 : fileInput.remove();
      origOnRemoved == null ? void 0 : origOnRemoved.apply(this, arguments);
    };
    const setUploadState = (isUploading, filename = "") => {
      if (isUploading) {
        uploadBtn.innerHTML = `<span aria-hidden="true">⏳</span> Uploading...`;
        uploadBtn.setAttribute("aria-label", "Uploading Video");
        uploadBtn.disabled = true;
        uploadBtn.style.cursor = "wait";
        infoEl.textContent = `Uploading ${filename}...`;
        previewContainer.style.display = "";
        videoEl.style.display = "none";
      } else {
        uploadBtn.innerHTML = "Upload Video...";
        uploadBtn.setAttribute("aria-label", "Upload Video");
        uploadBtn.disabled = false;
        uploadBtn.style.cursor = "pointer";
        videoEl.style.display = "block";
      }
      node.setDirtyCanvas(true, true);
      node.setSize([
        node.size[0],
        node.computeSize([node.size[0], node.size[1]])[1]
      ]);
    };
    const handleUpload = async (file) => {
      var _a2;
      setUploadState(true, file.name);
      const body = new FormData();
      body.append("image", file);
      try {
        const resp = await fetch("/upload/image", {
          method: "POST",
          body
        });
        if (resp.status !== 200) {
          showError("Upload failed: " + resp.statusText);
          return false;
        }
        const data = await resp.json();
        const filename = data.name;
        if (videoWidget) {
          if (!videoWidget.options.values.includes(filename)) {
            videoWidget.options.values.push(filename);
          }
          videoWidget.value = filename;
          (_a2 = videoWidget.callback) == null ? void 0 : _a2.call(videoWidget, filename);
        }
        updatePreview(filename);
        return true;
      } catch (err) {
        console.warn("FFMPEGA: Video upload failed", err);
        showError("Upload error: " + err);
        return false;
      } finally {
        setUploadState(false);
      }
    };
    fileInput.onchange = async () => {
      var _a2;
      if ((_a2 = fileInput.files) == null ? void 0 : _a2.length) {
        await handleUpload(fileInput.files[0]);
      }
    };
    this.onDragOver = (e) => {
      var _a2, _b, _c;
      if ((_c = (_b = (_a2 = e == null ? void 0 : e.dataTransfer) == null ? void 0 : _a2.types) == null ? void 0 : _b.includes) == null ? void 0 : _c.call(_b, "Files")) {
        if (!uploadBtn.disabled) {
          if (!Object.prototype.hasOwnProperty.call(uploadBtn, "_originalInnerHTML")) {
            uploadBtn._originalInnerHTML = uploadBtn.innerHTML;
          }
          if (!Object.prototype.hasOwnProperty.call(uploadBtn, "_originalBorder")) {
            uploadBtn._originalBorder = uploadBtn.style.border;
          }
          if (!Object.prototype.hasOwnProperty.call(uploadBtn, "_originalAriaLabel")) {
            uploadBtn._originalAriaLabel = uploadBtn.getAttribute("aria-label");
          }
          uploadBtn.innerHTML = `<span aria-hidden="true">📂</span> Drop to Upload`;
          uploadBtn.setAttribute("aria-label", "Drop to Upload");
          uploadBtn.style.border = "1px dashed #4a6a8a";
          uploadBtn.style.backgroundColor = "#333";
          if (uploadBtn._dragTimeout) clearTimeout(uploadBtn._dragTimeout);
          uploadBtn._dragTimeout = setTimeout(() => {
            if (!uploadBtn.disabled) {
              if (Object.prototype.hasOwnProperty.call(uploadBtn, "_originalInnerHTML")) {
                uploadBtn.innerHTML = uploadBtn._originalInnerHTML;
                delete uploadBtn._originalInnerHTML;
              }
              if (Object.prototype.hasOwnProperty.call(uploadBtn, "_originalBorder")) {
                uploadBtn.style.border = uploadBtn._originalBorder;
                delete uploadBtn._originalBorder;
              }
              if (Object.prototype.hasOwnProperty.call(uploadBtn, "_originalAriaLabel")) {
                if (uploadBtn._originalAriaLabel) {
                  uploadBtn.setAttribute("aria-label", uploadBtn._originalAriaLabel);
                } else {
                  uploadBtn.removeAttribute("aria-label");
                }
                delete uploadBtn._originalAriaLabel;
              }
              updateBtn();
            }
          }, 100);
        }
        return true;
      }
      return false;
    };
    this.onDragDrop = async (e) => {
      var _a2, _b, _c, _d, _e, _f;
      if (!((_c = (_b = (_a2 = e == null ? void 0 : e.dataTransfer) == null ? void 0 : _a2.types) == null ? void 0 : _b.includes) == null ? void 0 : _c.call(_b, "Files"))) return false;
      const file = (_e = (_d = e.dataTransfer) == null ? void 0 : _d.files) == null ? void 0 : _e[0];
      if (!file) return false;
      const ext = (_f = file.name.split(".").pop()) == null ? void 0 : _f.toLowerCase();
      if (!ext || !VIDEO_EXTENSIONS.includes(ext)) {
        showError("Invalid file type: " + ext);
        return false;
      }
      return await handleUpload(file);
    };
    if (videoWidget) {
      const origCallback = videoWidget.callback;
      videoWidget.callback = function(value) {
        origCallback == null ? void 0 : origCallback.apply(this, arguments);
        updatePreview(value);
      };
      if (videoWidget.value) {
        setTimeout(() => updatePreview(videoWidget.value), 100);
      }
    }
    const origOnExecuted = this.onExecuted;
    this.onExecuted = function(data) {
      var _a2, _b;
      origOnExecuted == null ? void 0 : origOnExecuted.apply(this, arguments);
      if ((_a2 = data == null ? void 0 : data.video) == null ? void 0 : _a2[0]) {
        const v = data.video[0];
        const params = new URLSearchParams({
          filename: v.filename,
          subfolder: v.subfolder || "",
          type: v.type || "input",
          timestamp: String(Date.now())
        });
        previewContainer.style.display = "";
        videoEl.src = api.apiURL("/view?" + params.toString());
      }
      if ((_b = data == null ? void 0 : data.video_info) == null ? void 0 : _b[0]) {
        const info = data.video_info[0];
        _srcMeta = {
          width: info.source_width || (_srcMeta == null ? void 0 : _srcMeta.width) || 0,
          height: info.source_height || (_srcMeta == null ? void 0 : _srcMeta.height) || 0,
          fps: info.source_fps || (_srcMeta == null ? void 0 : _srcMeta.fps) || 24,
          duration: info.source_duration || (_srcMeta == null ? void 0 : _srcMeta.duration) || 0,
          frames: info.source_frames || (_srcMeta == null ? void 0 : _srcMeta.frames) || 0
        };
        updateDynamicInfo();
      }
    };
    const getVideoUrlLoad = () => videoEl.src || null;
    addVideoPreviewMenu(node, videoEl, previewContainer, previewWidget, getVideoUrlLoad);
    return result;
  };
}
function registerSaveVideoNode(nodeType, nodeData) {
  if (nodeData.name !== "FFMPEGASaveVideo") return;
  const onNodeCreated = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function() {
    const result = onNodeCreated == null ? void 0 : onNodeCreated.apply(this, arguments);
    const node = this;
    this.color = "#2a5a3a";
    this.bgcolor = "#1a4a2a";
    const previewContainer = document.createElement("div");
    previewContainer.className = "ffmpega_preview";
    previewContainer.style.cssText = "width:100%;background:#1a1a1a;border-radius:6px;overflow:hidden;display:none;position:relative;";
    const videoEl = document.createElement("video");
    videoEl.controls = true;
    videoEl.loop = true;
    videoEl.muted = true;
    videoEl.setAttribute("aria-label", "Output video preview");
    videoEl.style.cssText = "width:100%;display:block;";
    videoEl.addEventListener("loadedmetadata", () => {
      var _a;
      previewWidget.aspectRatio = videoEl.videoWidth / videoEl.videoHeight;
      const w = videoEl.videoWidth;
      const h = videoEl.videoHeight;
      const d = videoEl.duration;
      const parts = [];
      if (w && h) parts.push(`${w}×${h}`);
      if (d && isFinite(d)) {
        const m = Math.floor(d / 60);
        const s = (d % 60).toFixed(1);
        parts.push(m > 0 ? `${m}m ${s}s` : `${s}s`);
      }
      if (node._savedFileSize) {
        parts.push(node._savedFileSize);
      }
      if (parts.length) {
        infoEl.textContent = parts.join(" | ");
      }
      node.setSize([
        node.size[0],
        node.computeSize([node.size[0], node.size[1]])[1]
      ]);
      (_a = node == null ? void 0 : node.graph) == null ? void 0 : _a.setDirtyCanvas(true);
    });
    videoEl.addEventListener("error", () => {
      var _a;
      previewContainer.style.display = "none";
      node.setSize([
        node.size[0],
        node.computeSize([node.size[0], node.size[1]])[1]
      ]);
      (_a = node == null ? void 0 : node.graph) == null ? void 0 : _a.setDirtyCanvas(true);
    });
    const infoEl = document.createElement("div");
    infoEl.style.cssText = "padding:4px 8px;font-size:11px;color:#aaa;font-family:monospace;background:#111;";
    infoEl.textContent = "Waiting for execution...";
    infoEl.setAttribute("role", "status");
    infoEl.setAttribute("aria-live", "polite");
    previewContainer.appendChild(videoEl);
    previewContainer.appendChild(infoEl);
    addDownloadOverlay(previewContainer, videoEl);
    const PASSTHROUGH_EVENTS2 = [
      "contextmenu",
      "pointerdown",
      "mousewheel",
      "pointermove",
      "pointerup"
    ];
    for (const evt of PASSTHROUGH_EVENTS2) {
      previewContainer.addEventListener(evt, (e) => {
        e.stopPropagation();
      }, true);
    }
    const previewWidget = this.addDOMWidget(
      "videopreview",
      "preview",
      previewContainer,
      {
        serialize: false,
        hideOnZoom: false,
        getValue() {
          return previewContainer.value;
        },
        setValue(v) {
          previewContainer.value = v;
        }
      }
    );
    previewWidget.aspectRatio = null;
    previewWidget.computeSize = function(width) {
      if (this.aspectRatio && previewContainer.style.display !== "none") {
        const h = (node.size[0] - 20) / this.aspectRatio + 10;
        return [width, Math.max(h, 0) + 30];
      }
      return [width, -4];
    };
    const origOnExecuted = this.onExecuted;
    this.onExecuted = function(data) {
      var _a, _b;
      origOnExecuted == null ? void 0 : origOnExecuted.apply(this, arguments);
      if ((_a = data == null ? void 0 : data.video) == null ? void 0 : _a[0]) {
        const v = data.video[0];
        const params = new URLSearchParams({
          filename: v.filename,
          subfolder: v.subfolder || "",
          type: v.type || "output",
          timestamp: String(Date.now())
        });
        previewContainer.style.display = "";
        videoEl.src = api.apiURL("/view?" + params.toString());
        if ((_b = data == null ? void 0 : data.file_size) == null ? void 0 : _b[0]) {
          node._savedFileSize = data.file_size[0];
        }
        infoEl.textContent = `Saved: ${v.filename}`;
        if (node._savedFileSize) {
          infoEl.textContent += ` (${node._savedFileSize})`;
        }
      }
    };
    const getVideoUrlSave = () => videoEl.src || null;
    addVideoPreviewMenu(node, videoEl, previewContainer, previewWidget, getVideoUrlSave);
    return result;
  };
}
const HIT_RADIUS = 20;
function openPointSelector(node, imgSrc, _videoSrc) {
  var _a, _b;
  (_a = document.getElementById("ffmpega-point-selector")) == null ? void 0 : _a.remove();
  let existing = {
    points: [],
    labels: [],
    image_width: 0,
    image_height: 0
  };
  const mpWidget = (_b = node.widgets) == null ? void 0 : _b.find((w) => w.name === "mask_points_data");
  if (mpWidget == null ? void 0 : mpWidget.value) {
    try {
      existing = JSON.parse(String(mpWidget.value));
    } catch {
    }
  }
  let mode = existing.mode || "points";
  const overlay = document.createElement("div");
  overlay.id = "ffmpega-point-selector";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", "Mask Editor");
  overlay.style.cssText = `
        position:fixed;top:0;left:0;width:100vw;height:100vh;
        background:rgba(0,0,0,0.85);z-index:999999;
        display:flex;flex-direction:column;align-items:center;
        justify-content:center;font-family:sans-serif;
    `;
  const header = document.createElement("div");
  header.style.cssText = `
        color:#eee;font-size:14px;margin-bottom:8px;
        display:flex;gap:16px;align-items:center;
    `;
  overlay.appendChild(header);
  const updateHeader = () => {
    if (mode === "points") {
      header.innerHTML = `
                <span><span aria-hidden="true">🎯</span> <b>Point Mode</b></span>
                <span style="color:#4f4"><span aria-hidden="true">⬤</span> Left-click = Include</span>
                <span style="color:#f44"><span aria-hidden="true">⬤</span> Right-click = Exclude</span>
                <span style="color:#888">Click existing point to remove</span>
            `;
    } else {
      header.innerHTML = `
                <span><span aria-hidden="true">🖌</span> <b>Draw Mode</b></span>
                <span style="color:#4f4"><span aria-hidden="true">⬤</span> Left-drag = Paint</span>
                <span style="color:#f44"><span aria-hidden="true">⬤</span> Right-drag = Erase</span>
            `;
    }
  };
  updateHeader();
  const canvasWrap = document.createElement("div");
  canvasWrap.style.cssText = "position:relative;max-width:90vw;max-height:75vh;";
  const canvas = document.createElement("canvas");
  canvas.style.cssText = "max-width:90vw;max-height:75vh;cursor:crosshair;display:block;";
  canvasWrap.appendChild(canvas);
  overlay.appendChild(canvasWrap);
  const sliderWrap = document.createElement("div");
  sliderWrap.style.cssText = `
        display:flex;gap:10px;align-items:center;margin-top:6px;
        color:#ccc;font-size:13px;
    `;
  sliderWrap.innerHTML = `<span aria-hidden="true">🖌</span> Brush:`;
  const sizeSlider = document.createElement("input");
  sizeSlider.type = "range";
  sizeSlider.min = "3";
  sizeSlider.max = "80";
  sizeSlider.value = "20";
  sizeSlider.style.cssText = "width:140px;accent-color:#4fc;";
  sizeSlider.setAttribute("aria-label", "Brush Size");
  const sizeLabel = document.createElement("span");
  sizeLabel.textContent = "20px";
  sizeLabel.style.cssText = "min-width:36px;";
  sizeSlider.oninput = () => {
    sizeLabel.textContent = `${sizeSlider.value}px`;
  };
  sliderWrap.appendChild(sizeSlider);
  sliderWrap.appendChild(sizeLabel);
  overlay.appendChild(sliderWrap);
  const statusBar = document.createElement("div");
  statusBar.style.cssText = "color:#aaa;font-size:12px;margin-top:6px;";
  statusBar.textContent = "Loading image...";
  statusBar.setAttribute("role", "status");
  statusBar.setAttribute("aria-live", "polite");
  overlay.appendChild(statusBar);
  const btnBar = document.createElement("div");
  btnBar.style.cssText = "display:flex;gap:12px;margin-top:12px;";
  const makeBtn = (htmlLabel, ariaLabel, bg) => {
    const b = document.createElement("button");
    b.innerHTML = htmlLabel;
    if (ariaLabel) {
      b.setAttribute("aria-label", ariaLabel);
    }
    b.style.cssText = `
            padding:8px 24px;border:none;border-radius:6px;
            font-size:14px;cursor:pointer;color:#fff;
            background:${bg};font-weight:600;
            transition:opacity 0.15s;
            outline: none;
        `;
    let isHovered = false;
    let isFocused = false;
    const update = () => {
      const active = isHovered || isFocused;
      b.style.opacity = active ? "0.85" : "1";
      b.style.outline = isFocused ? "2px solid #fff" : "none";
      b.style.outlineOffset = isFocused ? "2px" : "0px";
    };
    b.onmouseenter = () => {
      isHovered = true;
      update();
    };
    b.onmouseleave = () => {
      isHovered = false;
      update();
    };
    b.onfocus = () => {
      isFocused = true;
      update();
    };
    b.onblur = () => {
      isFocused = false;
      update();
    };
    return b;
  };
  const modeToggle = makeBtn(`<span aria-hidden="true">🖌</span> Draw`, "Draw Mode", "#3a5a8a");
  const clearBtn = makeBtn("Clear All", "Clear All", "#555");
  const applyBtn = makeBtn(`<span aria-hidden="true">✓</span> Apply`, "Apply", "#2a7a2a");
  const cancelBtn = makeBtn("Cancel", "Cancel", "#7a2a2a");
  btnBar.appendChild(modeToggle);
  btnBar.appendChild(clearBtn);
  btnBar.appendChild(applyBtn);
  btnBar.appendChild(cancelBtn);
  overlay.appendChild(btnBar);
  overlay.tabIndex = -1;
  document.body.appendChild(overlay);
  overlay.focus();
  let pts = existing.points ? [...existing.points] : [];
  let lbls = existing.labels ? [...existing.labels] : [];
  let imgW = 0;
  let imgH = 0;
  let scaleX = 1;
  let scaleY = 1;
  const firstImg = new Image();
  const maskOff = document.createElement("canvas");
  let maskDirty = false;
  let _greenOverlay = null;
  let _greenOverlayDirty = true;
  const updateModeUI = () => {
    if (mode === "points") {
      modeToggle.innerHTML = `<span aria-hidden="true">🖌</span> Draw`;
      modeToggle.setAttribute("aria-label", "Draw Mode");
      modeToggle.style.background = "#3a5a8a";
      canvas.style.cursor = "crosshair";
      sliderWrap.style.display = "none";
    } else {
      modeToggle.innerHTML = `<span aria-hidden="true">🎯</span> Points`;
      modeToggle.setAttribute("aria-label", "Point Mode");
      modeToggle.style.background = "#5a3a8a";
      canvas.style.cursor = "none";
      sliderWrap.style.display = "flex";
    }
    updateHeader();
    redraw();
  };
  modeToggle.onclick = () => {
    mode = mode === "points" ? "draw" : "points";
    updateModeUI();
  };
  const redraw = () => {
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (firstImg.complete && firstImg.naturalWidth > 0) {
      ctx.drawImage(firstImg, 0, 0, canvas.width, canvas.height);
    }
    if (mode === "points") {
      for (let i = 0; i < pts.length; i++) {
        const px = pts[i][0] / scaleX;
        const py = pts[i][1] / scaleY;
        const isPos = lbls[i] === 1;
        ctx.beginPath();
        ctx.arc(px, py, 14, 0, Math.PI * 2);
        ctx.fillStyle = isPos ? "rgba(0,255,0,0.25)" : "rgba(255,0,0,0.25)";
        ctx.fill();
        ctx.strokeStyle = isPos ? "#0f0" : "#f00";
        ctx.lineWidth = 2.5;
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(px, py, 5, 0, Math.PI * 2);
        ctx.fillStyle = isPos ? "#0f0" : "#f00";
        ctx.fill();
        ctx.font = "bold 16px sans-serif";
        ctx.fillStyle = "#fff";
        ctx.strokeStyle = "#000";
        ctx.lineWidth = 3;
        ctx.strokeText(isPos ? "+" : "×", px + 12, py - 8);
        ctx.fillText(isPos ? "+" : "×", px + 12, py - 8);
      }
      statusBar.textContent = `${pts.length} point(s) | ${imgW}×${imgH}`;
    } else {
      if (_greenOverlayDirty || !_greenOverlay) {
        _greenOverlay = document.createElement("canvas");
        _greenOverlay.width = canvas.width;
        _greenOverlay.height = canvas.height;
        const tmpCtx = _greenOverlay.getContext("2d");
        if (tmpCtx) {
          tmpCtx.drawImage(maskOff, 0, 0, canvas.width, canvas.height);
          const imgData = tmpCtx.getImageData(0, 0, canvas.width, canvas.height);
          for (let i = 0; i < imgData.data.length; i += 4) {
            if (imgData.data[i] > 128) {
              imgData.data[i] = 0;
              imgData.data[i + 1] = 220;
              imgData.data[i + 2] = 80;
              imgData.data[i + 3] = 100;
            } else {
              imgData.data[i + 3] = 0;
            }
          }
          tmpCtx.putImageData(imgData, 0, 0);
        }
        _greenOverlayDirty = false;
      }
      ctx.drawImage(_greenOverlay, 0, 0);
      statusBar.textContent = `Draw mode | ${imgW}×${imgH} | Brush: ${sizeSlider.value}px`;
    }
  };
  const fitCanvas = (w, h) => {
    imgW = w;
    imgH = h;
    const maxW = window.innerWidth * 0.9;
    const maxH = window.innerHeight * 0.75;
    let dispW = imgW;
    let dispH = imgH;
    if (dispW > maxW) {
      const r = maxW / dispW;
      dispW *= r;
      dispH *= r;
    }
    if (dispH > maxH) {
      const r = maxH / dispH;
      dispW *= r;
      dispH *= r;
    }
    canvas.width = Math.round(dispW);
    canvas.height = Math.round(dispH);
    scaleX = imgW / canvas.width;
    scaleY = imgH / canvas.height;
    maskOff.width = imgW;
    maskOff.height = imgH;
    const mCtx = maskOff.getContext("2d");
    if (mCtx) {
      mCtx.fillStyle = "#000";
      mCtx.fillRect(0, 0, imgW, imgH);
    }
    if (existing.mask_data && existing.mode === "draw") {
      const maskImg = new Image();
      maskImg.onload = () => {
        const restoreCtx = maskOff.getContext("2d");
        if (restoreCtx) {
          restoreCtx.drawImage(maskImg, 0, 0, imgW, imgH);
        }
        maskDirty = true;
        redraw();
      };
      maskImg.src = "data:image/png;base64," + existing.mask_data;
    }
  };
  firstImg.onload = () => {
    fitCanvas(firstImg.naturalWidth, firstImg.naturalHeight);
    updateModeUI();
    redraw();
  };
  firstImg.onerror = () => {
    statusBar.textContent = "Failed to load image";
    statusBar.style.color = "#f44";
  };
  firstImg.crossOrigin = "anonymous";
  firstImg.src = imgSrc;
  let isDrawing = false;
  let drawButton = -1;
  let lastDrawX = -1;
  let lastDrawY = -1;
  const paintOnMask = (canvasX, canvasY, erase) => {
    const mCtx = maskOff.getContext("2d");
    if (!mCtx) return;
    const mx = canvasX * scaleX;
    const my = canvasY * scaleY;
    const brushR = parseInt(sizeSlider.value) * scaleX;
    mCtx.beginPath();
    mCtx.arc(mx, my, brushR, 0, Math.PI * 2);
    mCtx.fillStyle = erase ? "#000" : "#fff";
    mCtx.fill();
    maskDirty = true;
    if (_greenOverlay) {
      const oCtx = _greenOverlay.getContext("2d");
      if (oCtx) {
        const dispBrushR = parseInt(sizeSlider.value);
        if (erase) {
          oCtx.save();
          oCtx.beginPath();
          oCtx.arc(canvasX, canvasY, dispBrushR, 0, Math.PI * 2);
          oCtx.clip();
          oCtx.clearRect(
            canvasX - dispBrushR,
            canvasY - dispBrushR,
            dispBrushR * 2,
            dispBrushR * 2
          );
          oCtx.restore();
        } else {
          oCtx.beginPath();
          oCtx.arc(canvasX, canvasY, dispBrushR, 0, Math.PI * 2);
          oCtx.fillStyle = "rgba(0, 220, 80, 0.392)";
          oCtx.fill();
        }
      }
    } else {
      _greenOverlayDirty = true;
    }
  };
  const paintLine = (x1, y1, x2, y2, erase) => {
    const dist = Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);
    const steps = Math.max(1, Math.floor(dist / 3));
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      const x = x1 + (x2 - x1) * t;
      const y = y1 + (y2 - y1) * t;
      paintOnMask(x, y, erase);
    }
  };
  const getCanvasPos = (e) => {
    const rect = canvas.getBoundingClientRect();
    const cssScaleX = canvas.width / rect.width;
    const cssScaleY = canvas.height / rect.height;
    return {
      x: (e.clientX - rect.left) * cssScaleX,
      y: (e.clientY - rect.top) * cssScaleY
    };
  };
  const findNearPoint = (mx, my) => {
    for (let i = 0; i < pts.length; i++) {
      const dx = pts[i][0] / scaleX - mx;
      const dy = pts[i][1] / scaleY - my;
      if (Math.sqrt(dx * dx + dy * dy) < HIT_RADIUS) return i;
    }
    return -1;
  };
  canvas.addEventListener("mousedown", (e) => {
    if (mode === "draw") {
      e.preventDefault();
      isDrawing = true;
      drawButton = e.button;
      const pos = getCanvasPos(e);
      lastDrawX = pos.x;
      lastDrawY = pos.y;
      paintOnMask(pos.x, pos.y, e.button === 2);
      redraw();
      const ctx = canvas.getContext("2d");
      if (ctx) {
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, parseInt(sizeSlider.value), 0, Math.PI * 2);
        ctx.strokeStyle = e.button === 2 ? "rgba(255,80,80,0.7)" : "rgba(80,255,120,0.7)";
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    }
  });
  canvas.addEventListener("mousemove", (e) => {
    if (mode === "draw") {
      const pos = getCanvasPos(e);
      if (isDrawing) {
        paintLine(lastDrawX, lastDrawY, pos.x, pos.y, drawButton === 2);
        lastDrawX = pos.x;
        lastDrawY = pos.y;
        redraw();
      }
      const ctx = canvas.getContext("2d");
      if (ctx) {
        const brushR = parseInt(sizeSlider.value);
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, brushR, 0, Math.PI * 2);
        ctx.strokeStyle = isDrawing ? drawButton === 2 ? "rgba(255,80,80,0.7)" : "rgba(80,255,120,0.7)" : "rgba(255,255,255,0.5)";
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    }
  });
  const stopDrawing = () => {
    if (isDrawing) {
      _greenOverlayDirty = true;
      redraw();
    }
    isDrawing = false;
    drawButton = -1;
    lastDrawX = -1;
    lastDrawY = -1;
  };
  canvas.addEventListener("mouseup", stopDrawing);
  canvas.addEventListener("mouseleave", () => {
    stopDrawing();
    if (mode === "draw") redraw();
  });
  canvas.addEventListener("click", (e) => {
    if (mode !== "points") return;
    const pos = getCanvasPos(e);
    const hitIdx = findNearPoint(pos.x, pos.y);
    if (hitIdx >= 0) {
      pts.splice(hitIdx, 1);
      lbls.splice(hitIdx, 1);
    } else {
      pts.push([Math.round(pos.x * scaleX), Math.round(pos.y * scaleY)]);
      lbls.push(1);
    }
    redraw();
  });
  canvas.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (mode !== "points") return;
    const pos = getCanvasPos(e);
    const hitIdx = findNearPoint(pos.x, pos.y);
    if (hitIdx >= 0) {
      pts.splice(hitIdx, 1);
      lbls.splice(hitIdx, 1);
    } else {
      pts.push([Math.round(pos.x * scaleX), Math.round(pos.y * scaleY)]);
      lbls.push(0);
    }
    redraw();
  });
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) {
      document.removeEventListener("keydown", keyHandler);
      overlay.remove();
    }
  });
  overlay.addEventListener("contextmenu", (e) => e.preventDefault());
  clearBtn.onclick = () => {
    if (mode === "points") {
      pts.length = 0;
      lbls.length = 0;
    } else {
      const mCtx = maskOff.getContext("2d");
      if (mCtx) {
        mCtx.fillStyle = "#000";
        mCtx.fillRect(0, 0, maskOff.width, maskOff.height);
      }
      maskDirty = false;
      _greenOverlayDirty = true;
    }
    redraw();
  };
  cancelBtn.onclick = () => {
    document.removeEventListener("keydown", keyHandler);
    overlay.remove();
  };
  applyBtn.onclick = () => {
    let data;
    if (mode === "draw" && maskDirty) {
      const maskDataUrl = maskOff.toDataURL("image/png");
      const b64 = maskDataUrl.split(",")[1];
      data = JSON.stringify({
        mode: "draw",
        mask_data: b64,
        image_width: imgW,
        image_height: imgH
      });
    } else {
      data = JSON.stringify({
        mode: "points",
        points: pts,
        labels: lbls,
        image_width: imgW,
        image_height: imgH
      });
    }
    if (mpWidget) {
      mpWidget.value = data;
    } else {
      const w = node.addWidget(
        "text",
        "mask_points_data",
        data,
        () => {
        },
        { serialize: true }
      );
      w.type = "text";
      if (w.computeSize) w.computeSize = () => [0, -4];
    }
    node.setDirtyCanvas(true, true);
    document.removeEventListener("keydown", keyHandler);
    overlay.remove();
    flashNode(node, "#2a7a2a");
  };
  const keyHandler = (e) => {
    if (e.key === "Escape") {
      overlay.remove();
      document.removeEventListener("keydown", keyHandler);
    }
  };
  document.addEventListener("keydown", keyHandler);
}
function registerLoadImageNode(nodeType, nodeData) {
  if (nodeData.name !== "FFMPEGALoadImagePath") return;
  const origOnCreatedImg = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function() {
    const result = origOnCreatedImg == null ? void 0 : origOnCreatedImg.apply(this, arguments);
    const node = this;
    this.color = "#3a5a5a";
    this.bgcolor = "#2a4a4a";
    const _syncImagesOutput = () => {
      const imagesIn = node.findInputSlot("images");
      const connected = imagesIn >= 0 && node.inputs[imagesIn].link != null;
      const imagesOut = node.findOutputSlot("images");
      const hasOutput = imagesOut >= 0;
      if (connected && !hasOutput) {
        node.addOutput("images", "IMAGE");
      } else if (!connected && hasOutput) {
        const idx = node.findOutputSlot("images");
        if (idx >= 0) node.removeOutput(idx);
      }
      node.setDirtyCanvas(true, true);
    };
    requestAnimationFrame(() => {
      const idx = node.findOutputSlot("images");
      if (idx >= 0) node.removeOutput(idx);
      node.setDirtyCanvas(true, true);
    });
    const origOnCCImg = this.onConnectionsChange;
    this.onConnectionsChange = function(type, slotIndex, isConnected, link, ioSlot) {
      var _a, _b;
      origOnCCImg == null ? void 0 : origOnCCImg.apply(this, arguments);
      if (type === LiteGraph.INPUT) {
        const name = (_b = (_a = this.inputs) == null ? void 0 : _a[slotIndex]) == null ? void 0 : _b.name;
        if (name === "images") {
          _syncImagesOutput();
        }
      }
    };
    const origConfigureImg = this.onConfigure;
    this.onConfigure = function(data) {
      origConfigureImg == null ? void 0 : origConfigureImg.apply(this, arguments);
      requestAnimationFrame(_syncImagesOutput);
    };
    const origOnExecutedImg = this.onExecuted;
    this.onExecuted = function(data) {
      var _a, _b, _c, _d;
      origOnExecutedImg == null ? void 0 : origOnExecutedImg.apply(this, arguments);
      if ((_a = data == null ? void 0 : data.images) == null ? void 0 : _a[0]) {
        const img = data.images[0];
        const imgWidgets = (_b = this.widgets) == null ? void 0 : _b.filter(
          (w) => w.name === "image_preview" || w.type === "preview"
        );
        if (imgWidgets == null ? void 0 : imgWidgets.length) {
          const params = new URLSearchParams({
            filename: img.filename,
            subfolder: img.subfolder || "",
            type: img.type || "input",
            timestamp: String(Date.now())
          });
          const src = api.apiURL("/view?" + params.toString());
          for (const w of imgWidgets) {
            const imgEl = (_d = (_c = w.element) == null ? void 0 : _c.querySelector) == null ? void 0 : _d.call(_c, "img");
            if (imgEl) {
              imgEl.src = src;
            }
          }
        }
      }
    };
    return result;
  };
  const origGetMenuImg = nodeType.prototype.getExtraMenuOptions;
  nodeType.prototype.getExtraMenuOptions = function(_, options) {
    origGetMenuImg == null ? void 0 : origGetMenuImg.apply(this, arguments);
    const self = this;
    options.unshift({
      content: "🎯 Open Point Selector",
      callback: () => {
        var _a;
        const imgWidget = (_a = self.widgets) == null ? void 0 : _a.find(
          (w) => w.name === "image"
        );
        const filename = imgWidget == null ? void 0 : imgWidget.value;
        if (!filename) {
          flashNode(self, "#7a4a4a");
          return;
        }
        const params = new URLSearchParams({
          filename,
          type: "input"
        });
        const src = api.apiURL("/view?" + params.toString());
        openPointSelector(self, src);
      }
    }, null);
  };
}
const BUILTIN_PRESETS = [
  {
    name: "📄 SRT Subtitle Example",
    auto_mode: false,
    mode: "subtitle",
    position: "bottom_center",
    font_size: 28,
    font_color: "#FFFFFF",
    text: "1\n00:00:01,000 --> 00:00:04,000\nThis is the first subtitle line.\n\n2\n00:00:05,000 --> 00:00:08,000\nAnd here is the second one.\n\n3\n00:00:09,000 --> 00:00:12,000\nEdit these timestamps to match your video!"
  },
  {
    name: "🎬 Cinematic Subtitles",
    auto_mode: false,
    mode: "subtitle",
    position: "bottom_center",
    font_size: 28,
    font_color: "#FFFFFF",
    text: "1\n00:00:01,000 --> 00:00:03,500\nThe world was never the same.\n\n2\n00:00:04,000 --> 00:00:07,000\nSomething had changed — forever."
  },
  {
    name: "💧 Bold Watermark",
    auto_mode: false,
    mode: "watermark",
    position: "bottom_right",
    font_size: 18,
    font_color: "#CCCCCC",
    text: "© Your Name"
  },
  {
    name: "🎯 Title Card",
    auto_mode: false,
    mode: "title_card",
    position: "center",
    font_size: 72,
    font_color: "#FFFFFF",
    text: "YOUR TITLE HERE"
  },
  {
    name: "📱 Social Caption",
    auto_mode: false,
    mode: "subtitle",
    position: "bottom_center",
    font_size: 36,
    font_color: "#FFE800",
    text: "1\n00:00:00,500 --> 00:00:03,000\nWait for it... 👀\n\n2\n00:00:03,500 --> 00:00:06,000\nDid you see that?! 🔥"
  },
  {
    name: "😂 Meme Text",
    auto_mode: false,
    mode: "overlay",
    position: "top",
    font_size: 48,
    font_color: "#FFFFFF",
    text: "TOP TEXT GOES HERE"
  },
  {
    name: "📐 Minimal Lower Third",
    auto_mode: false,
    mode: "overlay",
    position: "bottom_left",
    font_size: 22,
    font_color: "#DDDDDD",
    text: "Speaker Name\nJob Title"
  },
  {
    name: "©️ Copyright Notice",
    auto_mode: false,
    mode: "watermark",
    position: "bottom_center",
    font_size: 16,
    font_color: "#AAAAAA",
    text: "© 2025 All Rights Reserved"
  },
  {
    name: "🎬 Credits Roll",
    auto_mode: false,
    mode: "subtitle",
    position: "center",
    font_size: 32,
    font_color: "#FFFFFF",
    text: "1\n00:00:01,000 --> 00:00:03,000\nDirected by\nYour Name\n\n2\n00:00:04,000 --> 00:00:06,000\nProduced by\nYour Name\n\n3\n00:00:07,000 --> 00:00:09,000\nMusic by\nArtist Name"
  },
  {
    name: "📌 Chapter Marker",
    auto_mode: false,
    mode: "overlay",
    position: "top_left",
    font_size: 24,
    font_color: "#FFFFFF",
    text: "Chapter 1: Introduction",
    start_time: 0,
    end_time: 5
  }
];
const PRESET_APPLY_ORDER = [
  "auto_mode",
  "mode",
  "position",
  "font_size",
  "font_color",
  "text",
  "start_time",
  "end_time"
];
function applyPreset(node, preset) {
  var _a, _b, _c;
  const keys = PRESET_APPLY_ORDER.filter((k) => k in preset);
  for (const k of Object.keys(preset)) {
    if (k !== "name" && !keys.includes(k)) keys.push(k);
  }
  for (const key of keys) {
    const w = (_a = node.widgets) == null ? void 0 : _a.find(
      (ww) => ww.name === key
    );
    if (!w) continue;
    const val = preset[key];
    w.value = val;
    if (key === "font_color") {
      try {
        const ci = node._ffmpegaColorInput;
        const hl = node._ffmpegaHexLabel;
        if (ci && typeof val === "string" && val.startsWith("#")) {
          ci.value = val;
          if (hl) {
            hl.textContent = val.toUpperCase();
            hl.style.color = "#ccc";
          }
        }
      } catch {
      }
    } else if (w.inputEl) {
      w.inputEl.value = String(val);
      w.inputEl.dispatchEvent(new Event("input", { bubbles: true }));
    } else if (w.element) {
      const el2 = w.element;
      const tag = (_b = el2.tagName) == null ? void 0 : _b.toLowerCase();
      if (tag === "textarea" || tag === "input") {
        el2.value = String(val);
        el2.dispatchEvent(new Event("input", { bubbles: true }));
      } else {
        const input = (_c = el2.querySelector) == null ? void 0 : _c.call(el2, "textarea, input");
        if (input) {
          input.value = String(val);
          input.dispatchEvent(new Event("input", { bubbles: true }));
        }
      }
    }
  }
  node.setDirtyCanvas(true, true);
  app.graph.setDirtyCanvas(true, true);
  flashNode(node, "#4a7a4a");
}
async function saveCustomPreset(node, customPresets) {
  var _a;
  const name = prompt("Preset name:");
  if (!(name == null ? void 0 : name.trim())) return;
  const preset = { name: name.trim() };
  for (const key of ["auto_mode", "mode", "position", "font_size", "font_color"]) {
    const w = (_a = node.widgets) == null ? void 0 : _a.find(
      (ww) => ww.name === key
    );
    if (w) {
      preset[key] = typeof w.getValue === "function" ? w.getValue() : w.value;
    }
  }
  const idx = customPresets.findIndex((p) => p.name === preset.name);
  if (idx >= 0) {
    customPresets[idx] = preset;
  } else {
    customPresets.push(preset);
  }
  try {
    await fetch(api.apiURL("/ffmpega/text_presets"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(customPresets)
    });
    flashNode(node, "#4a7a4a");
  } catch (err) {
    console.warn("FFMPEGA: preset save failed", err);
    flashNode(node, "#7a4a4a");
  }
}
async function deleteCustomPreset(node, customPresets, presetName) {
  const idx = customPresets.findIndex((p) => p.name === presetName);
  if (idx < 0) return;
  customPresets.splice(idx, 1);
  try {
    await fetch(api.apiURL("/ffmpega/text_presets"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(customPresets)
    });
    flashNode(node, "#4a7a4a");
  } catch {
    flashNode(node, "#7a4a4a");
  }
}
function registerTextInputNode(nodeType, nodeData) {
  if (nodeData.name !== "FFMPEGATextInput") return;
  const onNodeCreated = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function() {
    var _a;
    const result = onNodeCreated == null ? void 0 : onNodeCreated.apply(this, arguments);
    const node = this;
    node.color = "#3a4a5a";
    node.bgcolor = "#2a3a4a";
    const colorWidgetIdx = ((_a = node.widgets) == null ? void 0 : _a.findIndex(
      (w) => w.name === "font_color"
    )) ?? -1;
    if (colorWidgetIdx >= 0 && node.widgets) {
      const oldWidget = node.widgets[colorWidgetIdx];
      const initialColor = oldWidget.value || "#FFFFFF";
      node.widgets.splice(colorWidgetIdx, 1);
      const container = document.createElement("div");
      container.style.cssText = `
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 2px 4px;
                width: 100%;
                box-sizing: border-box;
            `;
      const label = document.createElement("span");
      label.textContent = "Font Color";
      label.style.cssText = `
                color: #b0b0b0;
                font: 12px Arial, sans-serif;
                flex-shrink: 0;
            `;
      const colorInput = document.createElement("input");
      colorInput.type = "color";
      colorInput.value = initialColor;
      colorInput.setAttribute("aria-label", "Select font color");
      colorInput.style.cssText = `
                width: 36px;
                height: 24px;
                border: 1px solid #555;
                border-radius: 4px;
                cursor: pointer;
                background: transparent;
                padding: 0;
                flex-shrink: 0;
            `;
      const hexLabel = document.createElement("span");
      hexLabel.textContent = initialColor.toUpperCase();
      hexLabel.title = "Click or Press Enter to copy hex code";
      hexLabel.setAttribute("role", "button");
      hexLabel.setAttribute("tabindex", "0");
      hexLabel.setAttribute("aria-label", "Copy color hex code");
      hexLabel.setAttribute("aria-live", "polite");
      hexLabel.style.cssText = `
                color: #ccc;
                font: 11px monospace;
                flex-grow: 1;
                text-align: right;
                cursor: pointer;
                user-select: none;
                outline: none;
                border-radius: 2px;
                padding: 2px 4px;
            `;
      hexLabel.onfocus = () => {
        hexLabel.style.outline = "1px solid #4a6a8a";
        hexLabel.style.outlineOffset = "2px";
      };
      hexLabel.onblur = () => {
        hexLabel.style.outline = "none";
        hexLabel.style.outlineOffset = "0px";
      };
      const copyHex = async () => {
        const currentHex = colorInput.value.toUpperCase();
        try {
          if (navigator.clipboard) {
            await navigator.clipboard.writeText(currentHex);
            flashNode(node, "#4a7a4a");
            hexLabel.textContent = "COPIED";
            hexLabel.style.color = "#8f8";
            hexLabel.setAttribute("aria-label", "Copied successfully");
            setTimeout(() => {
              if (hexLabel.textContent === "COPIED") {
                hexLabel.textContent = currentHex;
                hexLabel.style.color = "#ccc";
                hexLabel.setAttribute("aria-label", "Copy color hex code");
              }
            }, 800);
          }
        } catch (err) {
          console.error("Failed to copy hex:", err);
          flashNode(node, "#7a3a3a");
        }
      };
      hexLabel.onclick = copyHex;
      hexLabel.onkeydown = (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          copyHex();
        }
      };
      container.appendChild(label);
      container.appendChild(colorInput);
      container.appendChild(hexLabel);
      node._ffmpegaColorInput = colorInput;
      node._ffmpegaHexLabel = hexLabel;
      const domWidget = node.addDOMWidget("font_color", "custom", container, {
        getValue: () => colorInput.value.toUpperCase(),
        setValue: (v) => {
          if (v && typeof v === "string") {
            if (v.startsWith("#")) {
              colorInput.value = v;
              hexLabel.textContent = v.toUpperCase();
              hexLabel.style.color = "#ccc";
            }
          }
        }
      });
      domWidget.value = initialColor;
      colorInput.addEventListener("input", (e) => {
        const val = e.target.value.toUpperCase();
        domWidget.value = val;
        hexLabel.textContent = val;
        hexLabel.style.color = "#ccc";
      });
      const newIdx = node.widgets.indexOf(domWidget);
      if (newIdx >= 0 && newIdx !== colorWidgetIdx) {
        node.widgets.splice(newIdx, 1);
        node.widgets.splice(colorWidgetIdx, 0, domWidget);
      }
    }
    return result;
  };
  let _customPresets = [];
  fetch(api.apiURL("/ffmpega/text_presets")).then((r) => r.json()).then((data) => {
    _customPresets = Array.isArray(data) ? data : [];
  }).catch(() => {
    _customPresets = [];
  });
  const origGetMenuText = nodeType.prototype.getExtraMenuOptions;
  nodeType.prototype.getExtraMenuOptions = function(_, options) {
    origGetMenuText == null ? void 0 : origGetMenuText.apply(this, arguments);
    const self = this;
    const presetItems = [];
    for (const p of BUILTIN_PRESETS) {
      presetItems.push({
        content: p.name,
        callback: () => applyPreset(self, p)
      });
    }
    if (_customPresets.length > 0) {
      for (const p of _customPresets) {
        presetItems.push({
          content: `⭐ ${p.name}`,
          submenu: {
            options: [
              {
                content: "✅ Load",
                callback: () => applyPreset(self, p)
              },
              {
                content: "🗑️ Delete",
                callback: () => deleteCustomPreset(self, _customPresets, p.name)
              }
            ]
          }
        });
      }
    }
    options.unshift(
      {
        content: "💾 Save Current as Preset",
        callback: () => saveCustomPreset(self, _customPresets)
      },
      {
        content: "🎨 Load Preset",
        submenu: {
          options: presetItems
        }
      },
      {
        content: "🧹 Clear Text",
        callback: () => {
          var _a, _b;
          const defaults = {
            text: "",
            mode: "overlay",
            position: "bottom_center",
            font_size: 24,
            font_color: "#FFFFFF",
            auto_mode: true
          };
          for (const [key, val] of Object.entries(defaults)) {
            const w = (_a = self.widgets) == null ? void 0 : _a.find(
              (ww) => ww.name === key
            );
            if (!w) continue;
            w.value = val;
            if (key === "font_color") {
              try {
                const ci = self._ffmpegaColorInput;
                const hl = self._ffmpegaHexLabel;
                if (ci) {
                  ci.value = val;
                }
                if (hl) {
                  hl.textContent = val;
                  hl.style.color = "#ccc";
                }
              } catch {
              }
            } else if (w.inputEl) {
              w.inputEl.value = String(val);
            } else if (w.element) {
              const tag = (_b = w.element.tagName) == null ? void 0 : _b.toLowerCase();
              if (tag === "textarea" || tag === "input") {
                w.element.value = String(val);
              }
            }
          }
          self.setDirtyCanvas(true, true);
          app.graph.setDirtyCanvas(true, true);
          flashNode(self, "#4a7a4a");
        }
      },
      null
      // separator
    );
  };
}
function captureFirstFrameAndOpen(node, videoSrc) {
  const tmpVideo = document.createElement("video");
  tmpVideo.crossOrigin = "anonymous";
  tmpVideo.muted = true;
  tmpVideo.preload = "auto";
  tmpVideo.src = videoSrc;
  tmpVideo.currentTime = 0.01;
  const seekTimeout = setTimeout(() => {
    flashNode(node, "#7a4a4a");
    tmpVideo.remove();
  }, 1e4);
  tmpVideo.addEventListener("seeked", () => {
    clearTimeout(seekTimeout);
    const c = document.createElement("canvas");
    c.width = tmpVideo.videoWidth;
    c.height = tmpVideo.videoHeight;
    c.getContext("2d").drawImage(tmpVideo, 0, 0);
    const frameDataUrl = c.toDataURL("image/jpeg", 0.95);
    openPointSelector(node, frameDataUrl);
    tmpVideo.remove();
  }, { once: true });
  tmpVideo.addEventListener("error", () => {
    clearTimeout(seekTimeout);
    flashNode(node, "#7a4a4a");
    tmpVideo.remove();
  }, { once: true });
}
function registerPointSelectorHooks(nodeType, nodeData) {
  if (nodeData.name === "FFMPEGALoadVideoPath") {
    const origGetMenuVid = nodeType.prototype.getExtraMenuOptions;
    nodeType.prototype.getExtraMenuOptions = function(_, options) {
      origGetMenuVid == null ? void 0 : origGetMenuVid.apply(this, arguments);
      const self = this;
      options.unshift({
        content: "🎯 Open Point Selector",
        callback: () => {
          var _a;
          const vidWidget = (_a = self.widgets) == null ? void 0 : _a.find((w) => w.name === "video");
          const filename = vidWidget == null ? void 0 : vidWidget.value;
          if (!filename) {
            flashNode(self, "#7a4a4a");
            return;
          }
          const params = new URLSearchParams({ filename, type: "input" });
          const src = api.apiURL("/view?" + params.toString());
          captureFirstFrameAndOpen(self, src);
        }
      }, null);
    };
  }
  if (nodeData.name === "FFMPEGAFrameExtract") {
    const origGetMenuExtract = nodeType.prototype.getExtraMenuOptions;
    nodeType.prototype.getExtraMenuOptions = function(_, options) {
      origGetMenuExtract == null ? void 0 : origGetMenuExtract.apply(this, arguments);
      const self = this;
      options.unshift({
        content: "🎯 Open Point Selector",
        callback: () => {
          var _a, _b;
          const pathWidget = (_a = self.widgets) == null ? void 0 : _a.find((w) => w.name === "video_path");
          const videoPath = (_b = pathWidget == null ? void 0 : pathWidget.value) == null ? void 0 : _b.trim();
          if (!videoPath) {
            flashNode(self, "#7a4a4a");
            return;
          }
          const params = new URLSearchParams({
            path: videoPath,
            duration: "1"
          });
          const src = api.apiURL("/ffmpega/preview?" + params.toString());
          captureFirstFrameAndOpen(self, src);
        }
      }, null);
    };
  }
}
function ensureCropStyles() {
  if (document.getElementById("ffmpega-crop-selector-styles")) return;
  const style = document.createElement("style");
  style.id = "ffmpega-crop-selector-styles";
  style.textContent = `
        /* Minimal veditor styles for CropOverlay outside the video editor */
        .ffmpega-crop-modal .veditor-crop-controls {
            display: flex; flex-direction: column; gap: 8px;
            padding: 12px; font-family: 'Inter', 'Segoe UI', sans-serif;
            font-size: 12px; color: #ddd;
        }
        .ffmpega-crop-modal .veditor-panel-section {
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 6px; padding: 8px 10px;
            background: rgba(255,255,255,0.03);
        }
        .ffmpega-crop-modal .veditor-section-label {
            font-size: 11px; font-weight: 600;
            color: #aaa; text-transform: uppercase;
            letter-spacing: 0.5px; margin-bottom: 6px;
        }
        .ffmpega-crop-modal .veditor-control-row {
            display: flex; align-items: center; gap: 6px;
            margin-bottom: 4px;
        }
        .ffmpega-crop-modal .veditor-control-label {
            font-size: 11px; color: #999;
            white-space: nowrap; min-width: 14px;
        }
        .ffmpega-crop-modal .veditor-btn {
            padding: 4px 8px; border: 1px solid rgba(255,255,255,0.1);
            border-radius: 4px; background: transparent;
            color: #ccc; font-size: 11px; cursor: pointer;
            transition: all 0.15s;
        }
        .ffmpega-crop-modal .veditor-btn:hover {
            background: rgba(255,255,255,0.08);
            border-color: rgba(255,255,255,0.2);
        }
        .ffmpega-crop-modal .veditor-toggle-btn {
            display: inline-flex; align-items: center; gap: 4px;
            padding: 4px 10px;
        }
        .ffmpega-crop-modal .veditor-toggle-btn.active {
            background: rgba(0,200,255,0.15);
            border-color: rgba(0,200,255,0.4);
            color: #0cf;
        }
        .ffmpega-crop-modal .veditor-preset-row {
            display: flex; gap: 4px; flex-wrap: wrap;
        }
        .ffmpega-crop-modal .veditor-preset-btn {
            font-size: 10px; padding: 3px 6px;
        }
        .ffmpega-crop-modal .veditor-preset-btn.active {
            background: rgba(0,200,255,0.25);
            border-color: rgba(0,200,255,0.5);
            color: #fff;
        }
        .ffmpega-crop-modal .veditor-input {
            width: 54px; padding: 2px 4px;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 3px; background: rgba(0,0,0,0.3);
            color: #ddd; font-size: 11px;
            font-family: 'JetBrains Mono', monospace;
        }
        .ffmpega-crop-modal .veditor-input:focus {
            border-color: rgba(0,200,255,0.5);
            outline: none;
        }
        .ffmpega-crop-modal .veditor-output-label {
            font-size: 11px; color: #aaa;
        }
    `;
  document.head.appendChild(style);
}
function captureFrameAt(video, time) {
  return new Promise((resolve, reject) => {
    const onSeeked = () => {
      video.removeEventListener("seeked", onSeeked);
      const c = document.createElement("canvas");
      c.width = video.videoWidth;
      c.height = video.videoHeight;
      c.getContext("2d").drawImage(video, 0, 0);
      resolve(c.toDataURL("image/jpeg", 0.92));
    };
    video.addEventListener("seeked", onSeeked);
    video.currentTime = time;
    setTimeout(() => reject(new Error("Frame capture timed out")), 8e3);
  });
}
function applyCropPreview(node, rect) {
  var _a, _b;
  const nodeEl = node.element;
  const container = ((_a = nodeEl == null ? void 0 : nodeEl.querySelector) == null ? void 0 : _a.call(nodeEl, ".ffmpega_preview")) ?? document.querySelector(`[data-node-id="${node.id}"] .ffmpega_preview`);
  if (!container) return;
  const videoEl = container.querySelector("video");
  if (!videoEl) return;
  (_b = container.querySelector(".ffmpega-crop-badge")) == null ? void 0 : _b.remove();
  if (!rect || rect.w <= 0 || rect.h <= 0) {
    videoEl.style.objectFit = "";
    videoEl.style.objectPosition = "";
    videoEl.style.transform = "";
    videoEl.style.clipPath = "";
    return;
  }
  const srcW = videoEl.videoWidth || 1920;
  const srcH = videoEl.videoHeight || 1080;
  const top = rect.y / srcH * 100;
  const right = (srcW - rect.x - rect.w) / srcW * 100;
  const bottom = (srcH - rect.y - rect.h) / srcH * 100;
  const left = rect.x / srcW * 100;
  videoEl.style.clipPath = `inset(${top.toFixed(2)}% ${right.toFixed(2)}% ${bottom.toFixed(2)}% ${left.toFixed(2)}%)`;
  const badge = document.createElement("div");
  badge.className = "ffmpega-crop-badge";
  badge.textContent = `✂️ ${rect.w}×${rect.h}`;
  badge.style.cssText = `
        position: absolute; top: 4px; right: 4px;
        background: rgba(0,180,255,0.2); color: #0cf;
        border: 1px solid rgba(0,180,255,0.4);
        border-radius: 4px; padding: 2px 6px;
        font-size: 10px; font-family: monospace;
        pointer-events: none; z-index: 5;
    `;
  container.appendChild(badge);
}
function openCropSelector(node, videoSrc) {
  var _a, _b;
  ensureCropStyles();
  (_a = document.getElementById("ffmpega-crop-selector")) == null ? void 0 : _a.remove();
  let existingRect = null;
  const cdWidget = (_b = node.widgets) == null ? void 0 : _b.find((w) => w.name === "crop_data");
  if (cdWidget == null ? void 0 : cdWidget.value) {
    try {
      const parsed = JSON.parse(String(cdWidget.value));
      if (parsed && typeof parsed.x === "number") existingRect = parsed;
    } catch {
    }
  }
  const overlay = document.createElement("div");
  overlay.id = "ffmpega-crop-selector";
  overlay.className = "ffmpega-crop-modal";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", "Crop Selector");
  overlay.style.cssText = `
        position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
        background: rgba(0,0,0,0.88); z-index: 999999;
        display: flex; flex-direction: column; align-items: center;
        justify-content: center; font-family: 'Inter', 'Segoe UI', sans-serif;
    `;
  const header = document.createElement("div");
  header.style.cssText = `
        color: #eee; font-size: 14px; margin-bottom: 8px;
        display: flex; gap: 16px; align-items: center;
    `;
  header.innerHTML = `
        <span><span aria-hidden="true">✂️</span> <b>Crop Selector</b></span>
        <span style="color:#888">Drag corners to crop • Use presets below</span>
    `;
  overlay.appendChild(header);
  const contentArea = document.createElement("div");
  contentArea.style.cssText = `
        display: flex; gap: 16px; align-items: flex-start;
        max-width: 95vw; max-height: 78vh;
    `;
  const canvasArea = document.createElement("div");
  canvasArea.style.cssText = `
        position: relative; display: flex;
        flex-direction: column; align-items: center;
    `;
  const frameImg = document.createElement("img");
  frameImg.style.cssText = `
        max-width: 70vw; max-height: 68vh;
        display: block; border-radius: 4px;
        background: #000;
    `;
  const frameContainer = document.createElement("div");
  frameContainer.style.cssText = "position: relative; display: inline-block;";
  frameContainer.appendChild(frameImg);
  canvasArea.appendChild(frameContainer);
  const scrubberWrap = document.createElement("div");
  scrubberWrap.style.cssText = `
        display: flex; gap: 10px; align-items: center;
        margin-top: 8px; color: #ccc; font-size: 12px; width: 100%;
    `;
  const scrubLabel = document.createElement("span");
  scrubLabel.textContent = "Frame:";
  scrubLabel.style.cssText = "white-space: nowrap; min-width: 44px;";
  const scrubSlider = document.createElement("input");
  scrubSlider.type = "range";
  scrubSlider.min = "0";
  scrubSlider.max = "100";
  scrubSlider.value = "0";
  scrubSlider.step = "1";
  scrubSlider.style.cssText = `
        flex: 1; accent-color: #0cf;
        cursor: pointer; height: 6px;
    `;
  scrubSlider.setAttribute("aria-label", "Frame position");
  const timeLabel = document.createElement("span");
  timeLabel.textContent = "0.0s";
  timeLabel.style.cssText = "min-width: 50px; text-align: right; font-family: monospace;";
  scrubberWrap.append(scrubLabel, scrubSlider, timeLabel);
  canvasArea.appendChild(scrubberWrap);
  contentArea.appendChild(canvasArea);
  const sidePanel = document.createElement("div");
  sidePanel.style.cssText = `
        min-width: 200px; max-width: 240px;
        background: rgba(20,20,35,0.9);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 8px; padding: 8px;
        max-height: 68vh; overflow-y: auto;
    `;
  contentArea.appendChild(sidePanel);
  overlay.appendChild(contentArea);
  const statusBar = document.createElement("div");
  statusBar.style.cssText = "color: #aaa; font-size: 12px; margin-top: 6px;";
  statusBar.textContent = "Loading video...";
  statusBar.setAttribute("role", "status");
  statusBar.setAttribute("aria-live", "polite");
  overlay.appendChild(statusBar);
  const btnBar = document.createElement("div");
  btnBar.style.cssText = "display: flex; gap: 12px; margin-top: 12px;";
  const makeBtn = (label, ariaLabel, bg) => {
    const b = document.createElement("button");
    b.innerHTML = label;
    b.setAttribute("aria-label", ariaLabel);
    b.style.cssText = `
            padding: 8px 24px; border: none; border-radius: 6px;
            font-size: 14px; cursor: pointer; color: #fff;
            background: ${bg}; font-weight: 600;
            transition: opacity 0.15s; outline: none;
        `;
    b.onmouseenter = () => {
      b.style.opacity = "0.85";
    };
    b.onmouseleave = () => {
      b.style.opacity = "1";
    };
    b.onfocus = () => {
      b.style.outline = "2px solid #fff";
      b.style.outlineOffset = "2px";
    };
    b.onblur = () => {
      b.style.outline = "none";
    };
    return b;
  };
  const applyBtn = makeBtn(
    '<span aria-hidden="true">✓</span> Apply Crop',
    "Apply crop",
    "#2a7a2a"
  );
  const clearBtn = makeBtn("Clear", "Clear crop", "#555");
  const cancelBtn = makeBtn("Cancel", "Cancel", "#7a2a2a");
  btnBar.append(applyBtn, clearBtn, cancelBtn);
  overlay.appendChild(btnBar);
  overlay.tabIndex = -1;
  document.body.appendChild(overlay);
  overlay.focus();
  const cropOverlay = new CropOverlay({
    onCropChanged: (rect) => {
      if (rect) {
        statusBar.textContent = `Crop: ${Math.round(rect.w)}×${Math.round(rect.h)} at (${Math.round(rect.x)}, ${Math.round(rect.y)})`;
      } else {
        statusBar.textContent = "No crop set";
      }
    }
  });
  sidePanel.appendChild(cropOverlay.element);
  const tmpVideo = document.createElement("video");
  tmpVideo.crossOrigin = "anonymous";
  tmpVideo.muted = true;
  tmpVideo.preload = "auto";
  tmpVideo.src = videoSrc;
  let videoDuration = 0;
  const onVideoReady = async () => {
    videoDuration = tmpVideo.duration || 0;
    if (isFinite(videoDuration) && videoDuration > 0) {
      scrubSlider.max = String(Math.floor(videoDuration * 10));
    }
    try {
      const initialTime = Math.min(0.1, videoDuration * 0.01);
      const dataUrl = await captureFrameAt(tmpVideo, initialTime);
      frameImg.src = dataUrl;
    } catch {
      statusBar.textContent = "Failed to capture frame";
      statusBar.style.color = "#f44";
      return;
    }
  };
  tmpVideo.addEventListener("loadedmetadata", () => {
    onVideoReady();
  }, { once: true });
  tmpVideo.addEventListener("error", () => {
    statusBar.textContent = "Failed to load video";
    statusBar.style.color = "#f44";
  }, { once: true });
  frameImg.onload = () => {
    const videoW = tmpVideo.videoWidth;
    const videoH = tmpVideo.videoHeight;
    const imgRect = frameImg.getBoundingClientRect();
    const cropCanvas = cropOverlay.canvasElement;
    cropCanvas.style.position = "absolute";
    cropCanvas.style.top = "0";
    cropCanvas.style.left = "0";
    cropCanvas.style.width = imgRect.width + "px";
    cropCanvas.style.height = imgRect.height + "px";
    cropCanvas.style.pointerEvents = "auto";
    frameContainer.appendChild(cropCanvas);
    cropOverlay.setVideoDimensions(videoW, videoH);
    if (existingRect) {
      cropOverlay.setRect(existingRect);
    }
    statusBar.textContent = existingRect ? `Crop: ${existingRect.w}×${existingRect.h} at (${existingRect.x}, ${existingRect.y})` : `Video: ${videoW}×${videoH} — Enable crop in the panel →`;
  };
  let scrubDebounce = null;
  scrubSlider.addEventListener("input", () => {
    const t = parseInt(scrubSlider.value, 10) / 10;
    timeLabel.textContent = `${t.toFixed(1)}s`;
    if (scrubDebounce) clearTimeout(scrubDebounce);
    scrubDebounce = setTimeout(async () => {
      try {
        const dataUrl = await captureFrameAt(tmpVideo, t);
        frameImg.src = dataUrl;
      } catch {
      }
    }, 150);
  });
  const cleanup = () => {
    document.removeEventListener("keydown", keyHandler);
    cropOverlay.destroy();
    tmpVideo.remove();
    overlay.remove();
  };
  applyBtn.onclick = () => {
    const rect = cropOverlay.getRect();
    const data = rect ? JSON.stringify({
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      w: Math.round(rect.w),
      h: Math.round(rect.h)
    }) : "";
    if (cdWidget) {
      cdWidget.value = data;
    } else {
      const w = node.addWidget(
        "text",
        "crop_data",
        data,
        () => {
        },
        { serialize: true }
      );
      w.type = "text";
      if (w.computeSize) w.computeSize = () => [0, -4];
    }
    node.setDirtyCanvas(true, true);
    applyCropPreview(node, rect ? {
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      w: Math.round(rect.w),
      h: Math.round(rect.h)
    } : null);
    cleanup();
    flashNode(node, "#2a7a2a");
  };
  clearBtn.onclick = () => {
    cropOverlay.setRect(null);
    statusBar.textContent = "Crop cleared";
  };
  cancelBtn.onclick = cleanup;
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) cleanup();
  });
  overlay.addEventListener("contextmenu", (e) => e.preventDefault());
  const keyHandler = (e) => {
    if (e.key === "Escape") cleanup();
  };
  document.addEventListener("keydown", keyHandler);
}
function restoreCropPreview(node) {
  var _a;
  const cdWidget = (_a = node.widgets) == null ? void 0 : _a.find((w) => w.name === "crop_data");
  if (!(cdWidget == null ? void 0 : cdWidget.value)) return;
  try {
    const rect = JSON.parse(String(cdWidget.value));
    if (rect && typeof rect.x === "number") {
      applyCropPreview(node, rect);
    }
  } catch {
  }
}
function watchForVideoAndRestoreCrop(node) {
  setTimeout(() => {
    const nodeEl = node.element;
    if (!nodeEl) return;
    const videoEl = nodeEl.querySelector("video");
    if (videoEl) {
      videoEl.addEventListener("loadedmetadata", () => restoreCropPreview(node));
      if (videoEl.readyState >= 1) restoreCropPreview(node);
      return;
    }
    const observer = new MutationObserver(() => {
      const vid = nodeEl.querySelector("video");
      if (vid) {
        observer.disconnect();
        vid.addEventListener("loadedmetadata", () => restoreCropPreview(node));
        if (vid.readyState >= 1) restoreCropPreview(node);
      }
    });
    observer.observe(nodeEl, { childList: true, subtree: true });
    setTimeout(() => observer.disconnect(), 1e4);
  }, 200);
}
function registerCropSelectorHooks(nodeType, nodeData) {
  if (nodeData.name === "FFMPEGALoadVideoPath") {
    const origGetMenu = nodeType.prototype.getExtraMenuOptions;
    nodeType.prototype.getExtraMenuOptions = function(_, options) {
      origGetMenu == null ? void 0 : origGetMenu.apply(this, arguments);
      const self = this;
      options.unshift({
        content: "✂️ Open Crop Selector",
        callback: () => {
          var _a;
          const vidWidget = (_a = self.widgets) == null ? void 0 : _a.find((w) => w.name === "video");
          const filename = vidWidget == null ? void 0 : vidWidget.value;
          if (!filename) {
            flashNode(self, "#7a4a4a");
            return;
          }
          const params = new URLSearchParams({ filename, type: "input" });
          const src = api.apiURL("/view?" + params.toString());
          openCropSelector(self, src);
        }
      }, null);
    };
    const origCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function() {
      const result = origCreated == null ? void 0 : origCreated.apply(this, arguments);
      watchForVideoAndRestoreCrop(this);
      return result;
    };
  }
  if (nodeData.name === "FFMPEGAFrameExtract") {
    const origGetMenu = nodeType.prototype.getExtraMenuOptions;
    nodeType.prototype.getExtraMenuOptions = function(_, options) {
      origGetMenu == null ? void 0 : origGetMenu.apply(this, arguments);
      const self = this;
      options.unshift({
        content: "✂️ Open Crop Selector",
        callback: () => {
          var _a, _b;
          const pathWidget = (_a = self.widgets) == null ? void 0 : _a.find((w) => w.name === "video_path");
          const videoPath = (_b = pathWidget == null ? void 0 : pathWidget.value) == null ? void 0 : _b.trim();
          if (!videoPath) {
            flashNode(self, "#7a4a4a");
            return;
          }
          const params = new URLSearchParams({
            path: videoPath,
            duration: "1"
          });
          const src = api.apiURL("/ffmpega/preview?" + params.toString());
          openCropSelector(self, src);
        }
      }, null);
    };
    const origCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function() {
      const result = origCreated == null ? void 0 : origCreated.apply(this, arguments);
      watchForVideoAndRestoreCrop(this);
      return result;
    };
  }
}
const NODE_DOCS = [
  {
    type: "FFMPEGAgent",
    title: "FFMPEG Agent",
    description: "AI-powered video editor: describe edits in natural language and the agent generates and runs the FFmpeg pipeline automatically.",
    tips: [
      "Use gemini-cli or claude-cli for zero-cost local inference — no API key needed.",
      "Set llm_model to 'none' and connect an Effects Builder for manual, AI-free editing.",
      "Connect multiple videos to video_a/b/c for concat, split screen, or xfade. New slots appear automatically.",
      "Enable 'Advanced' toggle to access encoding, SAM3, Whisper, FLUX, and batch settings.",
      "Use preview_mode for quick 480p test renders before full quality.",
      "save_output is Off by default — turn it On or connect a Save Video node downstream."
    ],
    inputs: [
      { name: "prompt", info: "Natural language instruction describing the desired edit." },
      { name: "video_path", info: "Absolute path to the source video file." },
      { name: "llm_model", info: "AI model selection: CLI tools, Ollama (local), cloud APIs, or 'none' for manual mode." },
      { name: "no_llm_mode", info: "What to do when llm_model is 'none': manual, sam3_masking, transcribe, karaoke, generate_audio, lip_sync, animate_portrait, minimax_remover, flux_klein, marigold, video_depth, or ai_upscale." },
      { name: "quality_preset", info: "Output quality: draft (fast), standard (balanced), high (slow), lossless." },
      { name: "images_a", info: "Video as image frames. More slots (images_b, c, …) appear automatically." },
      { name: "audio_a", info: "Audio input. More slots appear automatically." },
      { name: "pipeline_json", info: "Connect from Effects Builder for manual effect composition." }
    ],
    relatedWorkflows: [
      "Colorgrade_Text_Overlay_Ex_v1",
      "Multi_Special_Effects_Ex_v1",
      "Simple_Colograde_Ex_v1"
    ]
  },
  {
    type: "FFMPEGAEffects",
    title: "FFMPEGA Effects Builder",
    description: "Compose video effects visually without an LLM. Select effects from categorized dropdowns, choose a preset, add raw FFmpeg filters, and target objects with SAM3.",
    tips: [
      "Right-click the node for 18+ built-in presets (Cinematic, Vintage, Social, etc.).",
      "Chain up to 3 effects — they apply in order (effect_1 → effect_2 → effect_3).",
      "Use sam3_target to apply effects only to detected objects (e.g., 'face', 'person').",
      "The raw_ffmpeg field accepts standard FFmpeg -vf syntax, applied after skill effects.",
      "Connect output to the Agent node's pipeline_json input."
    ],
    inputs: [
      { name: "preset", info: "Quick-start presets that auto-fill effects and params." },
      { name: "effect_1/2/3", info: "Effects categorized by: 🎨 Visual, ⏱️ Temporal, 📐 Spatial, 🔊 Audio, 📦 Encoding, ✨ Outcome." },
      { name: "raw_ffmpeg", info: "Raw FFmpeg video filter string, applied after skill effects." },
      { name: "sam3_target", info: "Text description of object to mask (e.g., 'the person', 'license plate')." }
    ],
    relatedWorkflows: [
      "Colorhold_VHS_Tensors_Ex_v1",
      "Datamosh_Special_Effects_VHS_Tensors_Ex_v1"
    ]
  },
  {
    type: "FFMPEGALoadVideoPath",
    title: "Load Video Path (FFMPEGA)",
    description: "Zero-memory video input with inline preview. Select or upload a video and connect to the Agent's video_a/b/c slots. Uses 0 MB regardless of video length.",
    tips: [
      "Uses ~0 MB vs ~21 GB for a standard Load Video — always prefer this for multi-video workflows.",
      "Supports VHS-style trim params: force_rate, skip_first_frames, frame_load_cap, select_every_nth.",
      "Accepts upstream video_path input for chaining from Save Video nodes.",
      "Also outputs mask_points for SAM3 guided masking via the Point Selector."
    ],
    inputs: [
      { name: "video", info: "Select or upload a video file — path only, not loaded into memory." },
      { name: "force_rate", info: "Override FPS. 0 = use source FPS." },
      { name: "skip_first_frames", info: "Number of frames to skip from the start." },
      { name: "frame_load_cap", info: "Max frames to use. 0 = all frames." }
    ]
  },
  {
    type: "FFMPEGASaveVideo",
    title: "Save Video (FFMPEGA)",
    description: "Zero-memory video output with inline preview. Copies video to output directory and saves a workflow PNG thumbnail alongside it for drag-and-drop workflow loading.",
    tips: [
      "Set save_output to 'Preview Only' to test without saving to disk.",
      "The workflow PNG saved alongside the video lets you drag it back into ComfyUI to reload the workflow.",
      "Outputs IMAGE frames and AUDIO for chaining with downstream nodes."
    ],
    inputs: [
      { name: "video_path", info: "Path from FFMPEGA Agent or Load Video Path." },
      { name: "filename_prefix", info: "Supports ComfyUI formatting like %date:yyyy-MM-dd%." },
      { name: "save_output", info: "On = save to output folder. Off = preview only." }
    ]
  },
  {
    type: "FFMPEGAFrameExtract",
    title: "Frame Extract (FFMPEGA)",
    description: "Extract individual frames and audio from a video at a specified frame rate, time range, and frame limit.",
    tips: [
      "Set fps=1 to extract one frame per second — good for thumbnails or analysis.",
      "Accepts upstream video_path from Save Video or Load Video Path nodes.",
      "max_frames caps output to prevent memory issues with long videos."
    ],
    inputs: [
      { name: "video_path", info: "Absolute path to video file." },
      { name: "fps", info: "Extraction rate. 1.0 = one frame/sec, 30 = every frame at 30fps." },
      { name: "start_time", info: "Start time in seconds." },
      { name: "duration", info: "Duration to extract. 0 = full video." },
      { name: "max_frames", info: "Maximum frames to return (default 100)." }
    ]
  },
  {
    type: "FFMPEGAMediaBridge",
    title: "Media Bridge (FFMPEGA)",
    description: "Bidirectional media switch: convert IMAGE tensors to a video file path, or decode a video path back to IMAGE + AUDIO. Lightweight alternative to full Load/Save nodes.",
    tips: [
      "images_to_path: insert between Load Video Upload and the Agent to free tensors early.",
      "path_to_images: quickly decode a video path into frames for downstream image processing.",
      "Audio is automatically extracted (path_to_images) or muxed in (images_to_path) when connected.",
      "Outputs fps and frame_count in both modes for easy downstream use."
    ],
    inputs: [
      { name: "mode", info: "images_to_path or path_to_images — pick the conversion direction." },
      { name: "images", info: "IMAGE tensor input (used in images_to_path mode)." },
      { name: "video_path", info: "Video file path input (used in path_to_images mode)." },
      { name: "fps", info: "Encoding FPS for images_to_path mode (default 24)." },
      { name: "audio", info: "Optional audio to mux into the video (images_to_path mode)." }
    ]
  },
  {
    type: "FFMPEGALoadImagePath",
    title: "Load Image Path (FFMPEGA)",
    description: "Zero-memory image loader — outputs a file path instead of an IMAGE tensor. Uses ~0 MB for any number of images.",
    tips: [
      "Uses ~0 MB vs ~6 MB per image with standard Load Image.",
      "Connect to Agent's image_path_a/b/c inputs for overlay, grid, or slideshow workflows.",
      "Supports the Point Selector for SAM3 guided masking."
    ],
    inputs: [
      { name: "image", info: "Select or upload an image from ComfyUI's input directory." }
    ]
  },
  {
    type: "FFMPEGATextInput",
    title: "FFMPEGA Text",
    description: "Flexible text input for subtitles, overlays, watermarks, and title cards with auto-mode detection.",
    tips: [
      "Paste SRT-formatted text and it auto-detects as subtitle mode.",
      "Short single-line text auto-detects as watermark, multi-line as subtitle.",
      "Right-click for 10 built-in presets (SRT Example, Bold Watermark, Title Card, etc.).",
      "Connect to Agent's text_a/b/c inputs — multiple text nodes can be connected."
    ],
    inputs: [
      { name: "text", info: "Text content — plain text, SRT subtitles, or watermark text." },
      { name: "mode", info: "auto, subtitle, overlay, watermark, title_card, or raw." },
      { name: "position", info: "auto, center, top, bottom, top_left, bottom_right, etc." },
      { name: "font_size", info: "0 = auto (24 for subtitles, 48 for overlay, 20 for watermark)." }
    ],
    relatedWorkflows: [
      "Colorgrade_Text_Overlay_Ex_v1",
      "Subtitle_Burn_Ex_v1"
    ]
  },
  {
    type: "FFMPEGAPreview",
    title: "FFMPEGA Preview",
    description: "Quick video preview node for inspecting intermediate results.",
    tips: ["Use for debugging — preview any video_path in the pipeline without saving."],
    inputs: []
  },
  {
    type: "FFMPEGAVideoInfo",
    title: "FFMPEGA Video Info",
    description: "Analyze a video and output metadata: resolution, FPS, duration, codec, and frame count.",
    tips: ["Outputs structured metadata for use in conditional or parametric workflows."],
    inputs: []
  },
  {
    type: "LoadLastImage",
    title: "Load Last Image (FFMPEGA)",
    description: "Automatically loads the most recently saved image from ComfyUI's output directory.",
    tips: ["Useful for iterative workflows — always picks up the latest result."],
    inputs: []
  },
  {
    type: "LoadLastVideo",
    title: "Load Last Video (FFMPEGA)",
    description: "Automatically loads the most recently saved video from ComfyUI's output directory.",
    tips: ["Useful for chaining workflows — process the latest output again with different effects."],
    inputs: []
  },
  {
    type: "FFMPEGAVideoEditor",
    title: "Video Editor (FFMPEGA)",
    description: "Interactive NLE (Non-Linear Editor) for hands-on video editing directly inside ComfyUI. Full-screen modal with timeline, transport controls, and editing tools — no LLM required.",
    tips: [
      "Press '?' in the editor to see all keyboard shortcuts.",
      "Use 'S' to split segments at the playhead.",
      "Speed control supports 0.25x–4x per segment.",
      "Text overlays support configurable font size, color, and timing.",
      "Transitions (crossfade, dip-to-black) are added between segments.",
      "Ctrl+Z / Ctrl+Shift+Z for undo/redo."
    ],
    inputs: [
      { name: "video_path", info: "Path to video file to edit." },
      { name: "images", info: "Video frames from upstream nodes." },
      { name: "audio", info: "Audio input for the editor." }
    ]
  }
];
const TIPS_AND_TRICKS = [
  {
    title: "Performance",
    icon: "⚡",
    tips: [
      "Use Load Video Path instead of Load Video Upload — it uses 0 MB vs ~21 GB for long videos.",
      "Use Media Bridge between Load Video Upload and the Agent to free tensors early.",
      "Set quality_preset to 'draft' for quick test renders, then switch to 'high' for final output.",
      "preview_mode renders at 480p for the first 10 seconds — great for quick checks.",
      "Run Whisper on CPU (whisper_device='cpu') if you're low on VRAM.",
      "Disable FLUX Klein (use_flux_klein=Off) to save 8–15 GB VRAM — MiniMax-Remover, LaMa + FFmpeg fallbacks work well.",
      "Enable MiniMax-Remover (use_minimax_remover=On) for high-quality video object removal (~5–8 GB VRAM). Takes priority over FLUX Klein for removal.",
      "Use file-path inputs (video_a, image_path_a) instead of tensor inputs for multi-video workflows."
    ]
  },
  {
    title: "Common Pitfalls",
    icon: "⚠️",
    tips: [
      "Don't enable save_output on both the Agent AND a downstream Save Video — you'll get duplicate files.",
      "If using cloud API models (GPT, Claude, Gemini), you need an api_key. CLI models don't need one.",
      "The Effects Builder output must connect to the Agent's pipeline_json input, not video_path.",
      "For concat/xfade, connect videos to video_a/b/c slots — not the main video_path input.",
      "SAM3 requires GPU — there is no CPU fallback for video segmentation.",
      "When chaining nodes, the video_path output is a STRING — connect it to STRING inputs only."
    ]
  },
  {
    title: "Advanced Techniques",
    icon: "🔬",
    tips: [
      "Chain an Effects Builder → Agent with llm_model='none' for precise manual control.",
      "Use no_llm_mode='sam3_masking' with a text prompt to blur/remove specific objects without AI.",
      "Connect multiple Text nodes (text_a, text_b) for multi-line subtitles or positioned overlays.",
      "Use no_llm_mode='transcribe' or 'karaoke_subtitles' for automatic speech-to-text subtitles.",
      "Batch mode processes an entire folder of videos with one LLM call — great for consistent edits.",
      "Custom LUT files (.cube/.3dl) dropped in the luts/ folder are auto-discovered by the Agent.",
      "Enable verify_output for complex edits — the Agent inspects and auto-corrects output quality.",
      "Use mask_points from Load Video Path to guide SAM3 with click-to-select instead of text prompts."
    ]
  }
];
const EDITOR_SHORTCUTS = [
  { key: "Space", action: "Play / Pause" },
  { key: "J", action: "Shuttle reverse" },
  { key: "K", action: "Pause" },
  { key: "L", action: "Shuttle forward" },
  { key: "I", action: "Mark In point" },
  { key: "O", action: "Mark Out point" },
  { key: "←", action: "Step back 1 frame" },
  { key: "→", action: "Step forward 1 frame" },
  { key: "S", action: "Split at playhead" },
  { key: "V", action: "Select tool" },
  { key: "Delete", action: "Delete selected segment" },
  { key: "Ctrl+Z", action: "Undo" },
  { key: "Ctrl+Shift+Z", action: "Redo" },
  { key: "?", action: "Show shortcut overlay" }
];
const CHANGELOG_HIGHLIGHTS = [
  {
    version: "2.14.0",
    date: "2026-03-08",
    highlights: [
      "Video Editor Node — interactive NLE for hands-on editing inside ComfyUI",
      "Seekable MP4 preview server with HTTP Range support",
      "TypeScript migration for Video Editor frontend",
      "1,056 tests, 0 failures"
    ]
  },
  {
    version: "2.13.0",
    date: "2026-03-06",
    highlights: [
      "FLUX Klein toggle — disable to save 8–15 GB VRAM",
      "Edit FFmpeg fallback with 22 keyword-matched filters",
      "AI Background Removal with BRIA RMBG (6 model choices)",
      "952 tests, 0 failures"
    ]
  },
  {
    version: "2.12.0",
    date: "2026-03-06",
    highlights: [
      "AI Face Animation (LivePortrait) with motion transfer",
      "LivePortrait no-LLM mode for direct face animation",
      "LaMa safetensors conversion for improved security",
      "939 tests, 0 failures"
    ]
  }
];
const EXAMPLE_WORKFLOWS = [
  { filename: "4x4_Video_Grid_Ex_v1", title: "4×4 Video Grid", description: "Combine 4 videos into a grid layout" },
  { filename: "Bouncing_Logo_Animation_Ex_v1", title: "Bouncing Logo Animation", description: "Animated logo overlay with bounce motion" },
  { filename: "Colorgrade_Text_Overlay_Ex_v1", title: "Color Grade + Text Overlay", description: "Apply color grading with text effects" },
  { filename: "Colorhold_VHS_Tensors_Ex_v1", title: "Color Hold + VHS Effect", description: "Isolate a color and apply VHS distortion" },
  { filename: "Datamosh_Special_Effects_VHS_Tensors_Ex_v1", title: "Datamosh + Special Effects", description: "Datamosh glitch effects with VHS overlay" },
  { filename: "Greenscreen_Remove_VHS_Tensors_Ex_v1", title: "Green Screen Removal", description: "Chroma key background removal" },
  { filename: "Multi_Special_Effects_Ex_v1", title: "Multi Special Effects", description: "Chain multiple visual effects together" },
  { filename: "PiP_Video_Overlay_Example_v1", title: "Picture-in-Picture Overlay", description: "Overlay a video on top of another" },
  { filename: "Simple_Colograde_Ex_v1", title: "Simple Color Grade", description: "Basic color grading workflow" },
  { filename: "Slideshow_Audio_Example_v1", title: "Slideshow with Audio", description: "Image slideshow with background music" },
  { filename: "Subtitle_Burn_Ex_v1", title: "Subtitle Burn-In", description: "Burn SRT subtitles into video" }
];
const EXTERNAL_LINKS = [
  { label: "GitHub Repository", url: "https://github.com/AEmotionStudio/ComfyUI-FFMPEGA", icon: "🔗" },
  { label: "Report Issues", url: "https://github.com/AEmotionStudio/ComfyUI-FFMPEGA/issues", icon: "🐛" },
  { label: "Changelog", url: "https://github.com/AEmotionStudio/ComfyUI-FFMPEGA/blob/main/CHANGELOG.md", icon: "📋" },
  { label: "Skills Reference", url: "https://github.com/AEmotionStudio/ComfyUI-FFMPEGA/blob/main/SKILLS_REFERENCE.md", icon: "📖" }
];
const SIDEBAR_CSS = `/**
 * FFMPEGA Help Sidebar — Styles
 *
 * Uses ComfyUI's PrimeVue CSS variables for consistent theming.
 * Follows the same patterns as comfyui-magnifyglass sidebar.
 */

.ffmpega-sidebar {
    display: flex;
    flex-direction: column;
    height: 100%;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 13px;
    color: var(--fg-color, #ddd);
    background: transparent;
    padding: 0;
}

/* ── Header ──────────────────────────────────────────────────── */

.ffmpega-sidebar-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-color, #333);
    background: rgba(0, 0, 0, 0.2);
}

.ffmpega-sidebar-header h2 {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
}

.ffmpega-sidebar-header .version-badge {
    font-size: 10px;
    padding: 1px 6px;
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.1);
    color: var(--descrip-text, #999);
    margin-left: auto;
}

/* ── Search ──────────────────────────────────────────────────── */

.ffmpega-search-bar {
    padding: 8px 12px;
    border-bottom: 1px solid var(--border-color, #333);
}

.ffmpega-search-input {
    width: 100%;
    padding: 6px 10px;
    border: 1px solid var(--border-color, #444);
    border-radius: 6px;
    background: rgba(0, 0, 0, 0.3);
    color: var(--fg-color, #ddd);
    font-size: 12px;
    outline: none;
    box-sizing: border-box;
    transition: border-color 0.15s;
}

.ffmpega-search-input:focus {
    border-color: var(--p-primary-color, #3b82f6);
}

.ffmpega-search-input::placeholder {
    color: var(--descrip-text, #666);
}

/* ── Content area ────────────────────────────────────────────── */

.ffmpega-sidebar-content {
    flex: 1;
    overflow-y: auto;
    padding: 4px 0;
}

/* ── Section (accordion) ─────────────────────────────────────── */

.ffmpega-section {
    margin-bottom: 2px;
}

.ffmpega-section-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 9px 14px;
    cursor: pointer;
    background: rgba(255, 255, 255, 0.03);
    border-bottom: 1px solid var(--border-color, #333);
    transition: background 0.15s;
    user-select: none;
}

.ffmpega-section-header:hover {
    background: rgba(255, 255, 255, 0.06);
}

.ffmpega-section-header:focus-visible {
    outline: 2px solid var(--p-primary-color, #3b82f6);
    outline-offset: -2px;
}

.ffmpega-section-header .chevron {
    font-size: 10px;
    transition: transform 0.2s;
    opacity: 0.5;
    flex-shrink: 0;
}

.ffmpega-section-header.collapsed .chevron {
    transform: rotate(-90deg);
}

.ffmpega-section-header .section-title {
    font-weight: 500;
    font-size: 12px;
    letter-spacing: 0.3px;
}

.ffmpega-section-header.highlighted {
    background: rgba(59, 130, 246, 0.12);
    border-left: 3px solid var(--p-primary-color, #3b82f6);
    padding-left: 11px;
}

.ffmpega-section-body {
    padding: 10px 14px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    font-size: 12px;
    line-height: 1.5;
}

.ffmpega-section-body.collapsed {
    display: none;
}

/* ── Node description ────────────────────────────────────────── */

.ffmpega-node-desc {
    color: var(--descrip-text, #aaa);
    font-size: 12px;
    line-height: 1.5;
    margin-bottom: 4px;
}

/* ── Tips list ────────────────────────────────────────────────── */

.ffmpega-tips {
    list-style: none;
    padding: 0;
    margin: 4px 0;
}

.ffmpega-tips li {
    padding: 3px 0 3px 16px;
    position: relative;
    color: var(--fg-color, #ddd);
    font-size: 11.5px;
    line-height: 1.5;
}

.ffmpega-tips li::before {
    content: "💡";
    position: absolute;
    left: 0;
    font-size: 10px;
}

/* ── Input reference ─────────────────────────────────────────── */

.ffmpega-inputs-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 11px;
    margin-top: 4px;
}

.ffmpega-inputs-table th {
    text-align: left;
    padding: 4px 6px;
    font-weight: 600;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--descrip-text, #888);
    border-bottom: 1px solid var(--border-color, #333);
}

.ffmpega-inputs-table td {
    padding: 4px 6px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    vertical-align: top;
}

.ffmpega-inputs-table td:first-child {
    font-family: monospace;
    font-size: 11px;
    color: var(--p-primary-color, #3b82f6);
    white-space: nowrap;
    font-weight: 500;
}

.ffmpega-inputs-table td:last-child {
    color: var(--descrip-text, #999);
}

/* ── Shortcuts table ─────────────────────────────────────────── */

.ffmpega-shortcuts-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
}

.ffmpega-shortcuts-table td {
    padding: 4px 8px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.ffmpega-shortcuts-table td:first-child {
    width: 40%;
}

.ffmpega-kbd {
    display: inline-block;
    padding: 2px 6px;
    background: rgba(255, 255, 255, 0.1);
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 3px;
    font-family: monospace;
    font-size: 11px;
    min-width: 20px;
    text-align: center;
}

/* ── Workflow links ──────────────────────────────────────────── */

.ffmpega-workflow-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    border-radius: 4px;
    cursor: pointer;
    transition: background 0.15s;
    text-decoration: none;
    color: var(--fg-color, #ddd);
}

.ffmpega-workflow-item:hover {
    background: rgba(255, 255, 255, 0.06);
}

.ffmpega-workflow-title {
    font-size: 12px;
    font-weight: 500;
}

.ffmpega-workflow-desc {
    font-size: 11px;
    color: var(--descrip-text, #888);
}

/* ── External links ──────────────────────────────────────────── */

.ffmpega-link-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    border-radius: 4px;
    text-decoration: none;
    color: var(--fg-color, #ddd);
    transition: background 0.15s;
    font-size: 12px;
}

.ffmpega-link-item:hover {
    background: rgba(255, 255, 255, 0.06);
    color: var(--p-primary-color, #3b82f6);
}

/* ── Changelog ───────────────────────────────────────────────── */

.ffmpega-changelog-version {
    font-weight: 600;
    font-size: 12px;
    color: var(--p-primary-color, #3b82f6);
    margin-bottom: 4px;
}

.ffmpega-changelog-date {
    font-size: 10px;
    color: var(--descrip-text, #777);
    margin-left: 6px;
    font-weight: 400;
}

.ffmpega-changelog-list {
    list-style: disc;
    padding-left: 18px;
    margin: 4px 0 8px;
}

.ffmpega-changelog-list li {
    font-size: 11.5px;
    line-height: 1.5;
    color: var(--fg-color, #ddd);
    padding: 1px 0;
}

/* ── Context badge ───────────────────────────────────────────── */

.ffmpega-context-hint {
    padding: 6px 12px;
    background: rgba(59, 130, 246, 0.08);
    border-bottom: 1px solid var(--border-color, #333);
    font-size: 11px;
    color: var(--descrip-text, #999);
    display: flex;
    align-items: center;
    gap: 6px;
}

.ffmpega-context-hint .node-name {
    color: var(--p-primary-color, #3b82f6);
    font-weight: 500;
}

/* ── Hidden by search ────────────────────────────────────────── */

.ffmpega-hidden {
    display: none !important;
}

/* ── Sub-header (section group titles) ───────────────────────── */

.ffmpega-group-title {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--descrip-text, #666);
    padding: 8px 14px 4px;
    font-weight: 600;
}
`;
let sidebarRegistered = false;
let currentHighlightedType = null;
let pollIntervalId = null;
const FFMPEGA_NODE_TYPES = new Set(NODE_DOCS.map((n) => n.type));
function loadSidebarStyles() {
  const id = "ffmpega-sidebar-styles";
  if (document.getElementById(id)) return;
  const style = document.createElement("style");
  style.id = id;
  style.textContent = SIDEBAR_CSS;
  document.head.appendChild(style);
}
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text) e.textContent = text;
  return e;
}
function makeSection(id, title, collapsed, renderBody) {
  const section = el("div", "ffmpega-section");
  section.dataset.sectionId = id;
  const header = el("div", `ffmpega-section-header${" collapsed"}`);
  header.setAttribute("tabindex", "0");
  header.setAttribute("role", "button");
  header.setAttribute("aria-expanded", String(false));
  header.innerHTML = `<span class="chevron">▼</span><span class="section-title">${title}</span>`;
  const body = el("div", `ffmpega-section-body${" collapsed"}`);
  renderBody(body);
  const toggle = () => {
    const isCollapsed = header.classList.toggle("collapsed");
    body.classList.toggle("collapsed", isCollapsed);
    header.setAttribute("aria-expanded", String(!isCollapsed));
  };
  header.addEventListener("click", toggle);
  header.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      toggle();
    }
  });
  section.appendChild(header);
  section.appendChild(body);
  return section;
}
function renderNodeDoc(body, doc) {
  body.appendChild(el("div", "ffmpega-node-desc", doc.description));
  if (doc.tips.length > 0) {
    const ul = el("ul", "ffmpega-tips");
    for (const tip of doc.tips) {
      ul.appendChild(el("li", void 0, tip));
    }
    body.appendChild(ul);
  }
  if (doc.inputs.length > 0) {
    const table = document.createElement("table");
    table.className = "ffmpega-inputs-table";
    table.innerHTML = "<thead><tr><th>Input</th><th>Info</th></tr></thead>";
    const tbody = document.createElement("tbody");
    for (const inp of doc.inputs) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${inp.name}</td><td>${inp.info}</td>`;
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    body.appendChild(table);
  }
  if (doc.relatedWorkflows && doc.relatedWorkflows.length > 0) {
    const label = el("div", "ffmpega-group-title", "RELATED WORKFLOWS");
    body.appendChild(label);
    for (const wf of doc.relatedWorkflows) {
      const info = EXAMPLE_WORKFLOWS.find((w) => w.filename === wf);
      if (info) {
        const item = el("div", "ffmpega-workflow-item");
        item.innerHTML = `<span>📂</span><div><div class="ffmpega-workflow-title">${info.title}</div></div>`;
        item.title = `Load workflow: ${info.title}`;
        body.appendChild(item);
      }
    }
  }
}
function renderSidebar(container) {
  if (container.querySelector(".ffmpega-sidebar")) return;
  container.innerHTML = "";
  const sidebar = el("div", "ffmpega-sidebar");
  const header = el("div", "ffmpega-sidebar-header");
  header.innerHTML = `<span>📖</span><h2>FFMPEGA Help</h2><span class="version-badge">v2.14</span>`;
  sidebar.appendChild(header);
  const contextHint = el("div", "ffmpega-context-hint ffmpega-hidden");
  contextHint.id = "ffmpega-context-hint";
  contextHint.innerHTML = `<span>🎯</span> Viewing: <span class="node-name" id="ffmpega-context-name"></span>`;
  sidebar.appendChild(contextHint);
  const searchBar = el("div", "ffmpega-search-bar");
  const searchInput = document.createElement("input");
  searchInput.type = "text";
  searchInput.className = "ffmpega-search-input";
  searchInput.placeholder = "Search docs…";
  searchInput.setAttribute("aria-label", "Search FFMPEGA documentation");
  searchBar.appendChild(searchInput);
  sidebar.appendChild(searchBar);
  const content = el("div", "ffmpega-sidebar-content");
  content.appendChild(el("div", "ffmpega-group-title", "NODE REFERENCE"));
  for (const doc of NODE_DOCS) {
    const section = makeSection(
      `node-${doc.type}`,
      doc.title,
      true,
      (body) => renderNodeDoc(body, doc)
    );
    section.dataset.nodeType = doc.type;
    section.dataset.searchText = [
      doc.title,
      doc.description,
      ...doc.tips,
      ...doc.inputs.map((i) => `${i.name} ${i.info}`)
    ].join(" ").toLowerCase();
    content.appendChild(section);
  }
  content.appendChild(el("div", "ffmpega-group-title", "TIPS & TRICKS"));
  for (const cat of TIPS_AND_TRICKS) {
    const section = makeSection(
      `tips-${cat.title.toLowerCase()}`,
      `${cat.icon} ${cat.title}`,
      true,
      (body) => {
        const ul = el("ul", "ffmpega-tips");
        for (const tip of cat.tips) {
          ul.appendChild(el("li", void 0, tip));
        }
        body.appendChild(ul);
      }
    );
    section.dataset.searchText = [cat.title, ...cat.tips].join(" ").toLowerCase();
    content.appendChild(section);
  }
  const shortcutsSection = makeSection(
    "shortcuts",
    "⌨️ Video Editor Shortcuts",
    true,
    (body) => {
      const table = document.createElement("table");
      table.className = "ffmpega-shortcuts-table";
      for (const sc of EDITOR_SHORTCUTS) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td><span class="ffmpega-kbd">${sc.key}</span></td><td>${sc.action}</td>`;
        table.appendChild(tr);
      }
      body.appendChild(table);
    }
  );
  shortcutsSection.dataset.searchText = [
    "shortcuts",
    "keyboard",
    "keys",
    ...EDITOR_SHORTCUTS.map((s) => `${s.key} ${s.action}`)
  ].join(" ").toLowerCase();
  content.appendChild(shortcutsSection);
  content.appendChild(el("div", "ffmpega-group-title", "EXAMPLE WORKFLOWS"));
  const workflowsSection = makeSection(
    "workflows",
    "📂 Example Workflows",
    true,
    (body) => {
      for (const wf of EXAMPLE_WORKFLOWS) {
        const item = el("div", "ffmpega-workflow-item");
        item.innerHTML = `<span>📄</span><div><div class="ffmpega-workflow-title">${wf.title}</div><div class="ffmpega-workflow-desc">${wf.description}</div></div>`;
        item.title = `Workflow: ${wf.title}`;
        body.appendChild(item);
      }
    }
  );
  workflowsSection.dataset.searchText = EXAMPLE_WORKFLOWS.map((w) => `${w.title} ${w.description}`).join(" ").toLowerCase();
  content.appendChild(workflowsSection);
  content.appendChild(el("div", "ffmpega-group-title", "WHAT'S NEW"));
  for (const entry of CHANGELOG_HIGHLIGHTS) {
    const section = makeSection(
      `changelog-${entry.version}`,
      `🆕 v${entry.version}`,
      true,
      (body) => {
        const versionLine = el("div", "ffmpega-changelog-version");
        versionLine.innerHTML = `v${entry.version}<span class="ffmpega-changelog-date">${entry.date}</span>`;
        body.appendChild(versionLine);
        const ul = el("ul", "ffmpega-changelog-list");
        for (const hl of entry.highlights) {
          ul.appendChild(el("li", void 0, hl));
        }
        body.appendChild(ul);
      }
    );
    section.dataset.searchText = [entry.version, ...entry.highlights].join(" ").toLowerCase();
    content.appendChild(section);
  }
  content.appendChild(el("div", "ffmpega-group-title", "LINKS"));
  const linksSection = makeSection(
    "links",
    "🔗 Resources & Links",
    true,
    (body) => {
      for (const link of EXTERNAL_LINKS) {
        const a = document.createElement("a");
        a.className = "ffmpega-link-item";
        a.href = link.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.innerHTML = `<span>${link.icon}</span>${link.label}`;
        body.appendChild(a);
      }
    }
  );
  linksSection.dataset.searchText = EXTERNAL_LINKS.map((l) => l.label).join(" ").toLowerCase();
  content.appendChild(linksSection);
  sidebar.appendChild(content);
  container.appendChild(sidebar);
  searchInput.addEventListener("input", () => {
    const query = searchInput.value.trim().toLowerCase();
    const sections = content.querySelectorAll(".ffmpega-section");
    const groupTitles = content.querySelectorAll(".ffmpega-group-title");
    if (!query) {
      sections.forEach((s) => s.classList.remove("ffmpega-hidden"));
      groupTitles.forEach((g) => g.classList.remove("ffmpega-hidden"));
      return;
    }
    sections.forEach((s) => {
      var _a, _b;
      const text = s.dataset.searchText || "";
      const matches = text.includes(query);
      s.classList.toggle("ffmpega-hidden", !matches);
      if (matches) {
        (_a = s.querySelector(".ffmpega-section-header")) == null ? void 0 : _a.classList.remove("collapsed");
        (_b = s.querySelector(".ffmpega-section-body")) == null ? void 0 : _b.classList.remove("collapsed");
      }
    });
    groupTitles.forEach((g) => {
      let next = g.nextElementSibling;
      let hasVisible = false;
      while (next && !next.classList.contains("ffmpega-group-title")) {
        if (next.classList.contains("ffmpega-section") && !next.classList.contains("ffmpega-hidden")) {
          hasVisible = true;
          break;
        }
        next = next.nextElementSibling;
      }
      g.classList.toggle("ffmpega-hidden", !hasVisible);
    });
  });
  loadSidebarStyles();
  startNodePolling(content);
}
function startNodePolling(content) {
  if (pollIntervalId) clearInterval(pollIntervalId);
  pollIntervalId = setInterval(() => {
    try {
      const selectedNode = getSelectedFFMPEGANode();
      const nodeType = (selectedNode == null ? void 0 : selectedNode.type) || null;
      if (nodeType === currentHighlightedType) return;
      currentHighlightedType = nodeType;
      const hint = document.getElementById("ffmpega-context-hint");
      const nameEl = document.getElementById("ffmpega-context-name");
      if (hint && nameEl) {
        if (nodeType) {
          const doc = NODE_DOCS.find((d) => d.type === nodeType);
          nameEl.textContent = (doc == null ? void 0 : doc.title) || nodeType;
          hint.classList.remove("ffmpega-hidden");
        } else {
          hint.classList.add("ffmpega-hidden");
        }
      }
      content.querySelectorAll(".ffmpega-section-header.highlighted").forEach((h) => h.classList.remove("highlighted"));
      if (!nodeType) return;
      const section = content.querySelector(
        `.ffmpega-section[data-node-type="${nodeType}"]`
      );
      if (!section) return;
      const header = section.querySelector(".ffmpega-section-header");
      const body = section.querySelector(".ffmpega-section-body");
      if (header) {
        header.classList.add("highlighted");
        header.classList.remove("collapsed");
        header.setAttribute("aria-expanded", "true");
      }
      if (body) {
        body.classList.remove("collapsed");
      }
      section.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch {
    }
  }, 500);
}
function getSelectedFFMPEGANode() {
  var _a, _b, _c;
  try {
    const graph = (_a = app) == null ? void 0 : _a.graph;
    if (!(graph == null ? void 0 : graph._nodes)) return null;
    for (const node of graph._nodes) {
      if (node && FFMPEGA_NODE_TYPES.has(node.type) && // Check if the node is selected (LiteGraph selection)
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      node.is_selected) {
        return node;
      }
    }
    const hovered = (_c = (_b = app) == null ? void 0 : _b.canvas) == null ? void 0 : _c.node_over;
    if (hovered && FFMPEGA_NODE_TYPES.has(hovered.type)) {
      return hovered;
    }
    return null;
  } catch {
    return null;
  }
}
function registerSidebar() {
  if (sidebarRegistered) return;
  if (!app.extensionManager) {
    console.warn("FFMPEGA: extensionManager not available, sidebar registration skipped");
    return;
  }
  try {
    app.extensionManager.registerSidebarTab({
      id: "ffmpega-help",
      icon: "pi pi-book",
      title: "FFMPEGA",
      tooltip: "FFMPEGA Help & Documentation",
      type: "custom",
      render: (el2) => {
        renderSidebar(el2);
      }
    });
    sidebarRegistered = true;
    console.log("FFMPEGA: Help sidebar registered");
  } catch (e) {
    console.warn("FFMPEGA: Failed to register sidebar:", e);
  }
}
function initSidebar() {
  setTimeout(() => {
    registerSidebar();
  }, 100);
}
app.registerExtension({
  name: "FFMPEGA.UI",
  async setup() {
    initSidebar();
  },
  async beforeRegisterNodeDef(nodeType, nodeData, _app) {
    if (registerNodeStyling(nodeType, nodeData)) return;
    registerAgentNode(nodeType, nodeData);
    registerFrameExtractNode(nodeType, nodeData);
    registerLoadVideoNode(nodeType, nodeData);
    registerSaveVideoNode(nodeType, nodeData);
    registerLoadImageNode(nodeType, nodeData);
    registerTextInputNode(nodeType, nodeData);
    registerPointSelectorHooks(nodeType, nodeData);
    registerCropSelectorHooks(nodeType, nodeData);
  }
});
console.log("FFMPEGA UI extensions loaded");
