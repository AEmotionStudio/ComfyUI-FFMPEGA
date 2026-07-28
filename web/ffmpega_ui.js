import { app } from "../../scripts/app.js";
import { u as updateDynamicSlots, S as SLOT_LABELS, s as setPrompt, R as RANDOM_PROMPTS, f as flashNode, h as handlePaste, c as createUploadButton, a as addDownloadOverlay, b as addVideoPreviewMenu, d as attachFileDropZone, t as toggleWidget$2, e as fitHeight, w as wireDynamicInputs } from "./_chunks/ui_helpers-DUsdyHvD.js";
import { api } from "../../scripts/api.js";
import { o as openPointSelector } from "./_chunks/point_selector-D-OvNVQE.js";
import { C as CropOverlay } from "./_chunks/CropOverlay-H6yQHaMz.js";
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
  { prefix: "audio_", type: "AUDIO", excludes: ["audio_output_mode", "audio_resample_rate"] },
  { prefix: "video_", type: "STRING", excludes: ["video_path", "video_folder", "video_depth_encoder", "video_depth_colormap"] },
  { prefix: "image_path_", type: "STRING", excludes: [] },
  { prefix: "text_", type: "STRING", excludes: [] }
];
function toggleWidget$1(widget, show) {
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
    var _a, _b, _c, _d, _e, _f, _g, _h, _i, _j, _k, _l, _m, _n, _o, _p, _q, _r, _s, _t, _u, _v, _w, _x, _y, _z, _A, _B, _C, _D, _E, _F, _G, _H, _I, _J, _K, _L;
    const result = onNodeCreated == null ? void 0 : onNodeCreated.apply(this, arguments);
    const node = this;
    this.color = "#2a3a5a";
    this.bgcolor = "#1a2a4a";
    const fitHeight2 = () => {
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
        var _a2, _b2, _c2, _d2;
        const model = llmWidget.value;
        const isNone = model === "none";
        toggleWidget$1(customWidget, model === "custom");
        toggleWidget$1(apiKeyWidget, needsApiKey(model));
        if (ollamaUrlWidget) toggleWidget$1(ollamaUrlWidget, !isNone);
        if (verifyWidget) toggleWidget$1(verifyWidget, !isNone);
        if (visionWidget) toggleWidget$1(visionWidget, !isNone);
        if (ptcWidget) toggleWidget$1(ptcWidget, !isNone);
        const ttWidget = (_a2 = node.widgets) == null ? void 0 : _a2.find((w) => w.name === "track_tokens");
        const luWidget = (_b2 = node.widgets) == null ? void 0 : _b2.find((w) => w.name === "log_usage");
        if (ttWidget) toggleWidget$1(ttWidget, !isNone);
        if (luWidget) toggleWidget$1(luWidget, !isNone);
        const noLlmModeWidget = (_c2 = node.widgets) == null ? void 0 : _c2.find((w) => w.name === "no_llm_mode");
        if (noLlmModeWidget) {
          toggleWidget$1(noLlmModeWidget, isNone);
          if (!noLlmModeWidget._cbHooked) {
            noLlmModeWidget._cbHooked = true;
            const origNoLlmCb = noLlmModeWidget.callback;
            noLlmModeWidget.callback = function(...args) {
              origNoLlmCb == null ? void 0 : origNoLlmCb.apply(this, args);
              updateNoLlmModeVisibility();
              fitHeight2();
            };
          }
        }
        updateNoLlmModeVisibility();
        fitHeight2();
        const f1StyleTransferWidget = (_d2 = node.widgets) == null ? void 0 : _d2.find((w) => w.name === "f1_style_transfer");
        if (f1StyleTransferWidget && !f1StyleTransferWidget._cbHooked) {
          f1StyleTransferWidget._cbHooked = true;
          const origF1Cb = f1StyleTransferWidget.callback;
          f1StyleTransferWidget.callback = function(...args) {
            origF1Cb == null ? void 0 : origF1Cb.apply(this, args);
            updateNoLlmModeVisibility();
            fitHeight2();
          };
        }
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
    const alwaysHidden = [
      "video_path",
      "save_output",
      "output_path",
      "preview_mode",
      "crf",
      "encoding_preset",
      "batch_mode",
      "video_folder",
      "file_pattern",
      "max_concurrent"
    ];
    for (const name of alwaysHidden) {
      const w = (_h = this.widgets) == null ? void 0 : _h.find((ww) => ww.name === name);
      if (w) toggleWidget$1(w, false);
    }
    const advancedWidget = (_i = this.widgets) == null ? void 0 : _i.find((w) => w.name === "advanced_options");
    (_j = this.widgets) == null ? void 0 : _j.find((w) => w.name === "subtitle_path");
    (_k = this.widgets) == null ? void 0 : _k.find((w) => w.name === "use_vision");
    (_l = this.widgets) == null ? void 0 : _l.find((w) => w.name === "verify_output");
    (_m = this.widgets) == null ? void 0 : _m.find((w) => w.name === "whisper_device");
    (_n = this.widgets) == null ? void 0 : _n.find((w) => w.name === "whisper_model");
    (_o = this.widgets) == null ? void 0 : _o.find((w) => w.name === "sam3_max_objects");
    (_p = this.widgets) == null ? void 0 : _p.find((w) => w.name === "sam3_det_threshold");
    (_q = this.widgets) == null ? void 0 : _q.find((w) => w.name === "mask_output_type");
    (_r = this.widgets) == null ? void 0 : _r.find((w) => w.name === "batch_mode");
    (_s = this.widgets) == null ? void 0 : _s.find((w) => w.name === "video_folder");
    (_t = this.widgets) == null ? void 0 : _t.find((w) => w.name === "file_pattern");
    (_u = this.widgets) == null ? void 0 : _u.find((w) => w.name === "max_concurrent");
    const trackTokensWidget = (_v = this.widgets) == null ? void 0 : _v.find((w) => w.name === "track_tokens");
    const logUsageWidget = (_w = this.widgets) == null ? void 0 : _w.find((w) => w.name === "log_usage");
    const allowDownloadsWidget = (_x = this.widgets) == null ? void 0 : _x.find((w) => w.name === "allow_model_downloads");
    (_y = this.widgets) == null ? void 0 : _y.find((w) => w.name === "flux_smoothing");
    (_z = this.widgets) == null ? void 0 : _z.find((w) => w.name === "audio_output_mode");
    (_A = this.widgets) == null ? void 0 : _A.find((w) => w.name === "marigold_output_type");
    (_B = this.widgets) == null ? void 0 : _B.find((w) => w.name === "video_depth_encoder");
    (_C = this.widgets) == null ? void 0 : _C.find((w) => w.name === "video_depth_colormap");
    function updateNoLlmModeVisibility() {
      var _a2, _b2, _c2, _d2, _e2, _f2, _g2, _h2, _i2, _j2, _k2, _l2, _m2, _n2, _o2, _p2, _q2, _r2, _s2, _t2, _u2, _v2, _w2, _x2, _y2, _z2, _A2, _B2, _C2, _D2, _E2, _F2, _G2, _H2, _I2, _J2, _K2, _L2, _M, _N, _O, _P, _Q, _R, _S, _T, _U, _V, _W, _X, _Y, _Z, __, _$, _aa, _ba, _ca, _da, _ea, _fa, _ga, _ha, _ia;
      const adv = (_a2 = node.widgets) == null ? void 0 : _a2.find((w) => w.name === "advanced_options");
      const showAdvanced = Boolean(adv == null ? void 0 : adv.value);
      const llm = (_b2 = node.widgets) == null ? void 0 : _b2.find((w) => w.name === "llm_model");
      const isNone = (llm == null ? void 0 : llm.value) === "none";
      const noLlmMode = (_c2 = node.widgets) == null ? void 0 : _c2.find((w) => w.name === "no_llm_mode");
      const rawMode = isNone ? String((noLlmMode == null ? void 0 : noLlmMode.value) ?? "manual") : "";
      const mode = rawMode.replace(/\s*\([^)]*\)\s*$/, "");
      const showMarigold = showAdvanced && mode === "marigold";
      const showVda = showAdvanced && mode === "video_depth";
      const showUpscale = showAdvanced && mode === "ai_upscale";
      const showRembg = showAdvanced && mode === "rembg";
      const showWhisper = showAdvanced && (mode === "transcribe" || mode === "karaoke_subtitles");
      const showAceStep = showAdvanced && mode === "ace_step";
      const showOnionSkin = showAdvanced && mode === "onion_skin";
      const showComparison = showAdvanced && mode === "comparison";
      const showSamAudio = showAdvanced && mode === "audio_separate";
      const showNormalcrafter = showAdvanced && mode === "normalcrafter";
      const showFluxKleinMode = showAdvanced && mode === "flux_klein";
      const showKiwiEdit = showAdvanced && mode === "kiwi_edit";
      const showDreamidOmni = showAdvanced && mode === "dreamid_omni";
      const showScail2 = showAdvanced && mode === "scail2";
      const showFoundation1 = showAdvanced && mode === "foundation1";
      const showFishSpeech = showAdvanced && mode === "fish_speech";
      const showSharp = showAdvanced && mode === "sharp";
      const showWanAnimate = showAdvanced && mode === "wan_animate";
      const showSapiens2 = showAdvanced && mode === "sapiens2";
      const mw = (_d2 = node.widgets) == null ? void 0 : _d2.find((w) => w.name === "marigold_output_type");
      const mc = (_e2 = node.widgets) == null ? void 0 : _e2.find((w) => w.name === "marigold_colormap");
      if (mw) toggleWidget$1(mw, showMarigold);
      if (mc) toggleWidget$1(mc, showMarigold && String(mw == null ? void 0 : mw.value) === "depth");
      const ve = (_f2 = node.widgets) == null ? void 0 : _f2.find((w) => w.name === "video_depth_encoder");
      const vc = (_g2 = node.widgets) == null ? void 0 : _g2.find((w) => w.name === "video_depth_colormap");
      if (ve) toggleWidget$1(ve, showVda);
      if (vc) toggleWidget$1(vc, showVda);
      const um = (_h2 = node.widgets) == null ? void 0 : _h2.find((w) => w.name === "upscale_model");
      const us = (_i2 = node.widgets) == null ? void 0 : _i2.find((w) => w.name === "upscale_scale");
      const sr = (_j2 = node.widgets) == null ? void 0 : _j2.find((w) => w.name === "seedvr_resolution");
      const bb = (_k2 = node.widgets) == null ? void 0 : _k2.find((w) => w.name === "blockswap_blocks");
      const fp = (_l2 = node.widgets) == null ? void 0 : _l2.find((w) => w.name === "flashvsr_processing");
      const fw = (_m2 = node.widgets) == null ? void 0 : _m2.find((w) => w.name === "flashvsr_frame_window");
      const fcf = (_n2 = node.widgets) == null ? void 0 : _n2.find((w) => w.name === "flashvsr_color_fix");
      const fdt = (_o2 = node.widgets) == null ? void 0 : _o2.find((w) => w.name === "flashvsr_decode_tile");
      const rq = (_p2 = node.widgets) == null ? void 0 : _p2.find((w) => w.name === "rtx_quality");
      if (um) toggleWidget$1(um, showUpscale);
      const modelVal = String((um == null ? void 0 : um.value) ?? "");
      const isSeedvr = showUpscale && modelVal.startsWith("seedvr2");
      const isRtxVsr = showUpscale && modelVal === "rtx_vsr";
      const isFlashvsr = showUpscale && modelVal.startsWith("flashvsr");
      const isGanModel = showUpscale && !isSeedvr && !isRtxVsr;
      if (us) toggleWidget$1(us, isGanModel || isRtxVsr || isFlashvsr);
      if (sr) toggleWidget$1(sr, isSeedvr);
      if (bb) toggleWidget$1(bb, isSeedvr || isFlashvsr);
      if (fp) toggleWidget$1(fp, isFlashvsr);
      if (fw) toggleWidget$1(fw, isFlashvsr && String(fp == null ? void 0 : fp.value) === "temporal");
      if (fcf) toggleWidget$1(fcf, isFlashvsr);
      if (fdt) toggleWidget$1(fdt, isFlashvsr);
      if (rq) toggleWidget$1(rq, isRtxVsr);
      const isDiffusionUpscaler = isSeedvr || isFlashvsr;
      const vt = (_q2 = node.widgets) == null ? void 0 : _q2.find((w) => w.name === "vae_tiling");
      const vtp = (_r2 = node.widgets) == null ? void 0 : _r2.find((w) => w.name === "vae_tile_preset");
      const vts = (_s2 = node.widgets) == null ? void 0 : _s2.find((w) => w.name === "vae_tile_size");
      const vto = (_t2 = node.widgets) == null ? void 0 : _t2.find((w) => w.name === "vae_tile_overlap");
      if (vt) toggleWidget$1(vt, isDiffusionUpscaler);
      if (vtp) toggleWidget$1(vtp, isDiffusionUpscaler && Boolean(vt == null ? void 0 : vt.value));
      const showCustomTile = isDiffusionUpscaler && Boolean(vt == null ? void 0 : vt.value) && String(vtp == null ? void 0 : vtp.value) === "custom";
      if (vts) toggleWidget$1(vts, showCustomTile);
      if (vto) toggleWidget$1(vto, showCustomTile);
      const rm = (_u2 = node.widgets) == null ? void 0 : _u2.find((w) => w.name === "rembg_model");
      const rb = (_v2 = node.widgets) == null ? void 0 : _v2.find((w) => w.name === "rembg_background");
      if (rm) toggleWidget$1(rm, showRembg);
      if (rb) toggleWidget$1(rb, showRembg);
      const wd = (_w2 = node.widgets) == null ? void 0 : _w2.find((w) => w.name === "whisper_device");
      const wm = (_x2 = node.widgets) == null ? void 0 : _x2.find((w) => w.name === "whisper_model");
      if (wd) toggleWidget$1(wd, showWhisper);
      if (wm) toggleWidget$1(wm, showWhisper);
      const sam = (_y2 = node.widgets) == null ? void 0 : _y2.find((w) => w.name === "sam_audio_model");
      if (sam) toggleWidget$1(sam, showSamAudio);
      const nc = (_z2 = node.widgets) == null ? void 0 : _z2.find((w) => w.name === "normalcrafter_max_res");
      if (nc) toggleWidget$1(nc, showNormalcrafter);
      const fluxKleinWidgetNames = [
        "flux_image_source",
        "flux_klein_steps",
        "flux_klein_guidance",
        "flux_klein_seed",
        "flux_klein_width",
        "flux_klein_height"
      ];
      for (const wn of fluxKleinWidgetNames) {
        const w = (_A2 = node.widgets) == null ? void 0 : _A2.find((w2) => w2.name === wn);
        if (w) toggleWidget$1(w, showFluxKleinMode);
      }
      const kiwiWidgetNames = [
        "kiwi_model",
        "kiwi_precision",
        "kiwi_resolution",
        "kiwi_max_frames",
        "kiwi_steps",
        "kiwi_guidance",
        "kiwi_block_swap",
        "kiwi_long_video",
        "kiwi_seed",
        "kiwi_flow_shift",
        "kiwi_task_type",
        "kiwi_scheduler"
      ];
      for (const name of kiwiWidgetNames) {
        const w = (_B2 = node.widgets) == null ? void 0 : _B2.find((ww) => ww.name === name);
        if (w) toggleWidget$1(w, showKiwiEdit);
      }
      const kiwiRes = (_C2 = node.widgets) == null ? void 0 : _C2.find((ww) => ww.name === "kiwi_resolution");
      const showKiwiCustom = showKiwiEdit && String(kiwiRes == null ? void 0 : kiwiRes.value) === "custom";
      const kw = (_D2 = node.widgets) == null ? void 0 : _D2.find((ww) => ww.name === "kiwi_width");
      const kh = (_E2 = node.widgets) == null ? void 0 : _E2.find((ww) => ww.name === "kiwi_height");
      if (kw) toggleWidget$1(kw, showKiwiCustom);
      if (kh) toggleWidget$1(kh, showKiwiCustom);
      const dreamidWidgetNames = [
        "dreamid_precision",
        "dreamid_resolution",
        "dreamid_steps",
        "dreamid_seed",
        "dreamid_solver",
        "dreamid_video_cfg",
        "dreamid_video_ref_cfg",
        "dreamid_audio_cfg",
        "dreamid_audio_ref_cfg"
      ];
      for (const name of dreamidWidgetNames) {
        const w = (_F2 = node.widgets) == null ? void 0 : _F2.find((ww) => ww.name === name);
        if (w) toggleWidget$1(w, showDreamidOmni);
      }
      const scail2WidgetNames = [
        "scail2_width",
        "scail2_height",
        "scail2_length",
        "scail2_pose_extend",
        "scail2_steps",
        "scail2_cfg",
        "scail2_shift",
        "scail2_seed",
        "scail2_sampler",
        "scail2_scheduler",
        "scail2_denoise",
        "scail2_replacement_mode",
        "scail2_sort_by",
        "scail2_object_indices",
        "scail2_subject",
        "scail2_max_objects",
        "scail2_detection_threshold",
        "scail2_detect_interval",
        "scail2_point_src_width",
        "scail2_point_src_height",
        "scail2_composite_direction",
        "scail2_main_reference",
        "scail2_color_match",
        "scail2_blockswap_blocks",
        "scail2_tiled_vae"
      ];
      for (const name of scail2WidgetNames) {
        const w = (_G2 = node.widgets) == null ? void 0 : _G2.find((ww) => ww.name === name);
        if (w) toggleWidget$1(w, showScail2);
      }
      let showNextScail2Lora = showScail2;
      for (const slot of ["a", "b", "c", "d"]) {
        const loraW = (_H2 = node.widgets) == null ? void 0 : _H2.find((ww) => ww.name === `scail2_lora_${slot}`);
        const strW = (_I2 = node.widgets) == null ? void 0 : _I2.find((ww) => ww.name === `scail2_lora_strength_${slot}`);
        if (loraW) toggleWidget$1(loraW, showNextScail2Lora);
        if (strW) toggleWidget$1(strW, showNextScail2Lora && String((loraW == null ? void 0 : loraW.value) ?? "none") !== "none");
        showNextScail2Lora = showNextScail2Lora && String((loraW == null ? void 0 : loraW.value) ?? "none") !== "none";
      }
      const showSvi = showAdvanced && mode === "svi";
      const sviWidgetNames = [
        "svi_num_clips",
        "svi_height",
        "svi_width",
        "svi_fps",
        "svi_cfg_scale",
        "svi_overlap_frames",
        "svi_seed_multiplier",
        "svi_steps",
        "svi_high_model_ratio",
        "svi_frames_per_clip",
        "svi_variant",
        "svi_model_high",
        "svi_model_low",
        "svi_lora_high",
        "svi_lora_low",
        "svi_extra_lora_high",
        "svi_extra_lora_low",
        "svi_vae",
        "svi_text_encoder",
        "svi_sampler",
        "svi_scheduler",
        "svi_blockswap_blocks",
        "svi_tiled_vae"
      ];
      for (const name of sviWidgetNames) {
        const w = (_J2 = node.widgets) == null ? void 0 : _J2.find((ww) => ww.name === name);
        if (w) toggleWidget$1(w, showSvi);
      }
      const sharpWidgetNames = [
        "sharp_trajectory",
        "sharp_num_frames",
        "sharp_max_disparity",
        "sharp_max_zoom",
        "sharp_save_ply",
        "sharp_device"
      ];
      for (const name of sharpWidgetNames) {
        const w = (_K2 = node.widgets) == null ? void 0 : _K2.find((ww) => ww.name === name);
        if (w) toggleWidget$1(w, showSharp);
      }
      const wanAnimateWidgetNames = [
        "wan_animate_mode",
        "wan_animate_steps",
        "wan_animate_guidance",
        "wan_animate_seed",
        "wan_animate_num_frames",
        "wan_animate_height",
        "wan_animate_width",
        "wan_animate_pose_strength",
        "wan_animate_face_strength"
      ];
      for (const name of wanAnimateWidgetNames) {
        const w = (_L2 = node.widgets) == null ? void 0 : _L2.find((ww) => ww.name === name);
        if (w) toggleWidget$1(w, showWanAnimate);
      }
      const wanLoraSlots = ["a", "b", "c", "d"];
      let showNextLora = showWanAnimate;
      for (const slot of wanLoraSlots) {
        const loraW = (_M = node.widgets) == null ? void 0 : _M.find((ww) => ww.name === `wan_animate_lora_${slot}`);
        const strW = (_N = node.widgets) == null ? void 0 : _N.find((ww) => ww.name === `wan_animate_lora_strength_${slot}`);
        if (loraW) toggleWidget$1(loraW, showNextLora);
        if (strW) toggleWidget$1(strW, showNextLora && String((loraW == null ? void 0 : loraW.value) ?? "none") !== "none");
        showNextLora = showNextLora && String((loraW == null ? void 0 : loraW.value) ?? "none") !== "none";
      }
      const aceWidgetNames = [
        "ace_negative_prompt",
        "ace_cover_strength",
        "ace_steps",
        "ace_cfg_scale",
        "ace_bpm",
        "ace_key",
        "ace_time_sig"
      ];
      for (const name of aceWidgetNames) {
        const w = (_O = node.widgets) == null ? void 0 : _O.find((ww) => ww.name === name);
        if (w) toggleWidget$1(w, showAceStep);
      }
      const f1WidgetNames = [
        "f1_preset",
        "f1_instrument",
        "f1_fx",
        "f1_structure",
        "f1_negative_prompt",
        "f1_bpm",
        "f1_bars",
        "f1_key",
        "f1_duration",
        "f1_steps",
        "f1_cfg_scale",
        "f1_style_transfer"
      ];
      for (const name of f1WidgetNames) {
        const w = (_P = node.widgets) == null ? void 0 : _P.find((ww) => ww.name === name);
        if (w) toggleWidget$1(w, showFoundation1);
      }
      const f1StyleWidget = (_Q = node.widgets) == null ? void 0 : _Q.find((w) => w.name === "f1_style_transfer");
      const f1NoiseWidget = (_R = node.widgets) == null ? void 0 : _R.find((w) => w.name === "f1_noise_level");
      if (f1NoiseWidget) toggleWidget$1(f1NoiseWidget, showFoundation1 && Boolean(f1StyleWidget == null ? void 0 : f1StyleWidget.value));
      const fishWidgetNames = [
        "fish_model_variant",
        "fish_voice",
        "fish_emotion",
        "fish_temperature",
        "fish_top_p",
        "fish_repetition_penalty"
      ];
      for (const name of fishWidgetNames) {
        const w = (_S = node.widgets) == null ? void 0 : _S.find((ww) => ww.name === name);
        if (w) toggleWidget$1(w, showFishSpeech);
      }
      const onionWidgetNames = ["onion_blend_mode", "onion_opacity", "onion_decay"];
      for (const name of onionWidgetNames) {
        const w = (_T = node.widgets) == null ? void 0 : _T.find((ww) => ww.name === name);
        if (w) toggleWidget$1(w, showOnionSkin);
      }
      const comparisonWidgetNames = [
        "comparison_style",
        "comparison_labels",
        "comparison_label_a",
        "comparison_label_b"
      ];
      for (const name of comparisonWidgetNames) {
        const w = (_U = node.widgets) == null ? void 0 : _U.find((ww) => ww.name === name);
        if (w) toggleWidget$1(w, showComparison);
      }
      const showPhyfps = showAdvanced && mode === "phyfps";
      const phyfpsActionW = (_V = node.widgets) == null ? void 0 : _V.find((w) => w.name === "phyfps_action");
      if (phyfpsActionW) toggleWidget$1(phyfpsActionW, showPhyfps);
      const showMatting = showAdvanced && mode === "video_matting";
      const mattingWidgetNames = [
        "matting_output",
        "matting_background",
        "matting_max_size"
      ];
      for (const name of mattingWidgetNames) {
        const w = (_W = node.widgets) == null ? void 0 : _W.find((ww) => ww.name === name);
        if (w) toggleWidget$1(w, showMatting);
      }
      const showLivePortrait = showAdvanced && mode === "animate_portrait";
      const lpWidgetNames = [
        "lp_rotate_pitch",
        "lp_rotate_yaw",
        "lp_rotate_roll",
        "lp_blink",
        "lp_eyebrow",
        "lp_wink",
        "lp_pupil_x",
        "lp_pupil_y",
        "lp_aaa",
        "lp_eee",
        "lp_woo",
        "lp_smile",
        "lp_retargeting_eyes",
        "lp_retargeting_mouth",
        "lp_crop_factor",
        "lp_expression_preset",
        "lp_save_expression",
        "lp_sample_image",
        "lp_sample_ratio",
        "lp_sample_parts"
      ];
      for (const name of lpWidgetNames) {
        const w = (_X = node.widgets) == null ? void 0 : _X.find((ww) => ww.name === name);
        if (w) toggleWidget$1(w, showLivePortrait);
      }
      const sapiens2TaskWidget = (_Y = node.widgets) == null ? void 0 : _Y.find((w) => w.name === "sapiens2_task");
      const sapiens2SizeWidget = (_Z = node.widgets) == null ? void 0 : _Z.find((w) => w.name === "sapiens2_size");
      if (sapiens2TaskWidget) toggleWidget$1(sapiens2TaskWidget, showSapiens2);
      if (sapiens2SizeWidget) toggleWidget$1(sapiens2SizeWidget, showSapiens2);
      const sapiens2Task = String((sapiens2TaskWidget == null ? void 0 : sapiens2TaskWidget.value) ?? "pose");
      const showSapiensSegAlpha = showSapiens2 && sapiens2Task === "seg";
      const showSapiensPose = showSapiens2 && sapiens2Task === "pose";
      const segAlpha = (__ = node.widgets) == null ? void 0 : __.find((w) => w.name === "sapiens2_seg_alpha");
      if (segAlpha) toggleWidget$1(segAlpha, showSapiensSegAlpha);
      for (const wName of ["sapiens2_pose_kpt_thr", "sapiens2_pose_radius", "sapiens2_pose_thickness"]) {
        const w = (_$ = node.widgets) == null ? void 0 : _$.find((ww) => ww.name === wName);
        if (w) toggleWidget$1(w, showSapiensPose);
      }
      const sam3EligibleModes = /* @__PURE__ */ new Set([
        "lip_sync",
        "animate_portrait",
        "marigold",
        "normalcrafter",
        "video_depth",
        "flux_klein",
        "kiwi_edit",
        "minimax_remover",
        "ai_upscale",
        "rembg",
        "onion_skin",
        "comparison"
      ]);
      const showUseSam3 = showAdvanced && sam3EligibleModes.has(mode);
      const useSam3Widget = (_aa = node.widgets) == null ? void 0 : _aa.find((w) => w.name === "use_sam3");
      if (useSam3Widget) toggleWidget$1(useSam3Widget, showUseSam3);
      const useSam3On = showUseSam3 && Boolean(useSam3Widget == null ? void 0 : useSam3Widget.value);
      const showSam3 = showAdvanced && (!isNone || mode === "sam3_masking" || useSam3On);
      for (const wName of ["sam3_max_objects", "sam3_det_threshold", "mask_output_type"]) {
        const w = (_ba = node.widgets) == null ? void 0 : _ba.find((ww) => ww.name === wName);
        if (w) toggleWidget$1(w, showSam3);
      }
      const showLlmToggles = showAdvanced && !isNone;
      for (const wName of ["use_flux_klein", "use_kiwi_edit", "use_minimax_remover", "use_dreamid_omni"]) {
        const w = (_ca = node.widgets) == null ? void 0 : _ca.find((ww) => ww.name === wName);
        if (w) toggleWidget$1(w, showLlmToggles);
      }
      const fluxKleinWidget = (_da = node.widgets) == null ? void 0 : _da.find((w) => w.name === "use_flux_klein");
      const fsw = (_ea = node.widgets) == null ? void 0 : _ea.find((w) => w.name === "flux_smoothing");
      if (fsw) toggleWidget$1(fsw, showLlmToggles && Boolean(fluxKleinWidget == null ? void 0 : fluxKleinWidget.value));
      const fkm = (_fa = node.widgets) == null ? void 0 : _fa.find((w) => w.name === "flux_klein_model");
      if (fkm) toggleWidget$1(fkm, showFluxKleinMode || showLlmToggles && Boolean(fluxKleinWidget == null ? void 0 : fluxKleinWidget.value));
      const _AUDIO_MODES = /* @__PURE__ */ new Set(["generate_audio", "generate_music", "foundation1", "fish_speech", "audio_inpaint", "audio_separate", "ace_step"]);
      const showAudioMode = showAdvanced && (!isNone || _AUDIO_MODES.has(mode));
      const mmw = (_ga = node.widgets) == null ? void 0 : _ga.find((w) => w.name === "audio_output_mode");
      if (mmw) toggleWidget$1(mmw, showAudioMode);
      const showResample = showAdvanced && mode === "manual";
      const arw = (_ha = node.widgets) == null ? void 0 : _ha.find((w) => w.name === "audio_resample_rate");
      if (arw) toggleWidget$1(arw, showResample);
      const showSubtitle = showAdvanced && (!isNone || mode === "manual" || mode === "transcribe" || mode === "karaoke_subtitles");
      const sw = (_ia = node.widgets) == null ? void 0 : _ia.find((w) => w.name === "subtitle_path");
      if (sw) toggleWidget$1(sw, showSubtitle);
    }
    function updateAdvancedVisibility() {
      var _a2;
      const show = Boolean(advancedWidget == null ? void 0 : advancedWidget.value);
      const llm = (_a2 = node.widgets) == null ? void 0 : _a2.find((w) => w.name === "llm_model");
      const isNone = (llm == null ? void 0 : llm.value) === "none";
      if (trackTokensWidget) toggleWidget$1(trackTokensWidget, show && !isNone);
      if (logUsageWidget) toggleWidget$1(logUsageWidget, show && !isNone);
      if (allowDownloadsWidget) toggleWidget$1(allowDownloadsWidget, show);
      updateNoLlmModeVisibility();
      fitHeight2();
    }
    if (advancedWidget) {
      updateAdvancedVisibility();
      const origAdvCb = advancedWidget.callback;
      advancedWidget.callback = function(...args) {
        origAdvCb == null ? void 0 : origAdvCb.apply(this, args);
        updateAdvancedVisibility();
      };
    }
    const fluxKleinToggle = (_D = this.widgets) == null ? void 0 : _D.find((w) => w.name === "use_flux_klein");
    if (fluxKleinToggle) {
      const origFluxCb = fluxKleinToggle.callback;
      fluxKleinToggle.callback = function(...args) {
        origFluxCb == null ? void 0 : origFluxCb.apply(this, args);
        updateAdvancedVisibility();
      };
    }
    const useSam3Toggle = (_E = this.widgets) == null ? void 0 : _E.find((w) => w.name === "use_sam3");
    if (useSam3Toggle) {
      const origSam3Cb = useSam3Toggle.callback;
      useSam3Toggle.callback = function(...args) {
        origSam3Cb == null ? void 0 : origSam3Cb.apply(this, args);
        updateAdvancedVisibility();
      };
    }
    const upscaleModelToggle = (_F = this.widgets) == null ? void 0 : _F.find((w) => w.name === "upscale_model");
    if (upscaleModelToggle) {
      const origUpscaleCb = upscaleModelToggle.callback;
      upscaleModelToggle.callback = function(...args) {
        origUpscaleCb == null ? void 0 : origUpscaleCb.apply(this, args);
        updateAdvancedVisibility();
      };
    }
    const flashvsrProcToggle = (_G = this.widgets) == null ? void 0 : _G.find((w) => w.name === "flashvsr_processing");
    if (flashvsrProcToggle) {
      const origFvCb = flashvsrProcToggle.callback;
      flashvsrProcToggle.callback = function(...args) {
        origFvCb == null ? void 0 : origFvCb.apply(this, args);
        updateAdvancedVisibility();
      };
    }
    for (const wName of ["vae_tiling", "vae_tile_preset"]) {
      const vaeTileW = (_H = this.widgets) == null ? void 0 : _H.find((w) => w.name === wName);
      if (vaeTileW) {
        const origVaeCb = vaeTileW.callback;
        vaeTileW.callback = function(...args) {
          origVaeCb == null ? void 0 : origVaeCb.apply(this, args);
          updateAdvancedVisibility();
        };
      }
    }
    const kiwiResolutionToggle = (_I = this.widgets) == null ? void 0 : _I.find((w) => w.name === "kiwi_resolution");
    if (kiwiResolutionToggle) {
      const origKiwiResCb = kiwiResolutionToggle.callback;
      kiwiResolutionToggle.callback = function(...args) {
        origKiwiResCb == null ? void 0 : origKiwiResCb.apply(this, args);
        updateAdvancedVisibility();
      };
    }
    for (const slot of ["a", "b", "c", "d"]) {
      const wanLoraSlotW = (_J = this.widgets) == null ? void 0 : _J.find((w) => w.name === `wan_animate_lora_${slot}`);
      if (wanLoraSlotW) {
        const origCb = wanLoraSlotW.callback;
        wanLoraSlotW.callback = function(...args) {
          origCb == null ? void 0 : origCb.apply(this, args);
          updateAdvancedVisibility();
        };
      }
    }
    for (const slot of ["a", "b", "c", "d"]) {
      const scail2LoraSlotW = (_K = this.widgets) == null ? void 0 : _K.find((w) => w.name === `scail2_lora_${slot}`);
      if (scail2LoraSlotW) {
        const origCb = scail2LoraSlotW.callback;
        scail2LoraSlotW.callback = function(...args) {
          origCb == null ? void 0 : origCb.apply(this, args);
          updateAdvancedVisibility();
        };
      }
    }
    const marigoldTypeWidget = (_L = this.widgets) == null ? void 0 : _L.find((w) => w.name === "marigold_output_type");
    if (marigoldTypeWidget) {
      const origMtCb = marigoldTypeWidget.callback;
      marigoldTypeWidget.callback = function(...args) {
        origMtCb == null ? void 0 : origMtCb.apply(this, args);
        updateAdvancedVisibility();
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
        fitHeight2();
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
        fitHeight2();
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
const VIDEO_ACCEPT$2 = [
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
const PASSTHROUGH_EVENTS$2 = [
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
    const { fileInput, uploadBtn, updateBtnStyle: updateUploadBtn } = createUploadButton(VIDEO_ACCEPT$2);
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
    for (const evt of PASSTHROUGH_EVENTS$2) {
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
          }, 500);
        }
        return true;
      }
      return false;
    };
    this.onDragDrop = async (e) => {
      var _a, _b, _c, _d, _e, _f;
      if (uploadBtn._dragTimeout) {
        clearTimeout(uploadBtn._dragTimeout);
        delete uploadBtn._dragTimeout;
      }
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
const MASK_WIDGETS = [
  "mask_mode",
  "mask_output_type",
  "sam_version",
  "show_mask_preview"
];
const LEGACY_SHIFTED_WIDGETS = [
  "enable_mask",
  "mask_mode",
  "mask_output_type",
  "sam_version",
  "show_mask_preview",
  "custom_width",
  "custom_height"
];
const UPLOAD_BTN_HEIGHT = 26;
const PASSTHROUGH_EVENTS$1 = [
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
    var _a, _b;
    const result = onNodeCreated == null ? void 0 : onNodeCreated.apply(this, arguments);
    const node = this;
    this.color = "#5a4a2a";
    this.bgcolor = "#4a3a1a";
    const updateMaskVisibility = () => {
      var _a2, _b2;
      const enableMask = (_a2 = node.widgets) == null ? void 0 : _a2.find((w) => w.name === "enable_mask");
      const show = Boolean(enableMask == null ? void 0 : enableMask.value);
      for (const name of MASK_WIDGETS) {
        const w = (_b2 = node.widgets) == null ? void 0 : _b2.find((ww) => ww.name === name);
        if (w) toggleWidget$2(w, show);
      }
      fitHeight(node);
    };
    const enableMaskWidget = (_a = this.widgets) == null ? void 0 : _a.find(
      (w) => w.name === "enable_mask"
    );
    if (enableMaskWidget) {
      updateMaskVisibility();
      const origMaskCb = enableMaskWidget.callback;
      enableMaskWidget.callback = function(...args) {
        origMaskCb == null ? void 0 : origMaskCb.apply(this, args);
        updateMaskVisibility();
      };
    }
    const repairLegacyWidgetShift = () => {
      const widgets = node.widgets;
      if (!widgets) return;
      const shifted = LEGACY_SHIFTED_WIDGETS.map(
        (name) => widgets.find((w) => w.name === name)
      );
      const enableMask = shifted[0];
      if (!enableMask || typeof enableMask.value !== "string") return;
      const loaded = shifted.map((w) => w == null ? void 0 : w.value);
      for (let i = shifted.length - 1; i > 0; i--) {
        const w = shifted[i];
        if (w) w.value = loaded[i - 1];
      }
      enableMask.value = String(loaded[0]) !== "none";
    };
    const origConfigure = this.onConfigure;
    this.onConfigure = function(data) {
      var _a2;
      origConfigure == null ? void 0 : origConfigure.apply(this, arguments);
      repairLegacyWidgetShift();
      if (this.widgets) {
        const staticCombos = ["mask_mode", "mask_output_type"];
        const intWidgets = ["custom_width", "custom_height"];
        for (const w of this.widgets) {
          const wType = w._origType ?? w.type;
          if (wType === "combo" && staticCombos.includes(w.name) && ((_a2 = w.options) == null ? void 0 : _a2.values)) {
            const validValues = w.options.values;
            if (validValues.length > 0 && !validValues.includes(String(w.value))) {
              w.value = validValues[0];
            }
          }
          if (intWidgets.includes(w.name)) {
            const v = w.value;
            if (v === "" || v === null || v === void 0 || isNaN(Number(v))) {
              w.value = 0;
            }
          }
        }
      }
      updateMaskVisibility();
    };
    const { fileInput, uploadBtn, updateBtnStyle: updateBtn } = createUploadButton(VIDEO_ACCEPT$1);
    document.body.append(fileInput);
    uploadBtn.style.height = `${UPLOAD_BTN_HEIGHT}px`;
    uploadBtn.style.boxSizing = "border-box";
    const uploadWidget = this.addDOMWidget("upload_button", "btn", uploadBtn, {
      serialize: false
    });
    uploadWidget.computeSize = () => [0, UPLOAD_BTN_HEIGHT];
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
    let _effEveryNth = 1;
    let _effInfoText = "";
    const infoEl = document.createElement("div");
    infoEl.style.cssText = "padding:4px 8px;font-size:11px;color:#aaa;font-family:monospace;background:#111;";
    infoEl.textContent = "No video selected";
    infoEl.setAttribute("role", "status");
    infoEl.setAttribute("aria-live", "polite");
    const setTrimLabel = (name, suffix) => {
      var _a2;
      const w = (_a2 = node.widgets) == null ? void 0 : _a2.find((ww) => ww.name === name);
      if (!w) return;
      if (suffix) {
        w.label = `${w.name} · ${suffix}`;
      } else {
        delete w.label;
      }
    };
    const clearTrimLabels = () => {
      setTrimLabel("skip_first_frames", null);
      setTrimLabel("frame_load_cap", null);
      node.setDirtyCanvas(true, true);
    };
    const updateDynamicInfo = () => {
      var _a2, _b2, _c, _d, _e, _f, _g, _h;
      if (!_srcMeta) {
        infoEl.textContent = "No video selected";
        clearTrimLabels();
        return;
      }
      const forceRate = ((_b2 = (_a2 = node.widgets) == null ? void 0 : _a2.find((w) => w.name === "force_rate")) == null ? void 0 : _b2.value) ?? 0;
      const skipFirst = ((_d = (_c = node.widgets) == null ? void 0 : _c.find((w) => w.name === "skip_first_frames")) == null ? void 0 : _d.value) ?? 0;
      const frameCap = ((_f = (_e = node.widgets) == null ? void 0 : _e.find((w) => w.name === "frame_load_cap")) == null ? void 0 : _f.value) ?? 0;
      const everyNth = ((_h = (_g = node.widgets) == null ? void 0 : _g.find((w) => w.name === "select_every_nth")) == null ? void 0 : _h.value) ?? 1;
      const srcFps = _srcMeta.fps || 24;
      const srcDuration = _srcMeta.duration || 0;
      const srcFrames = _srcMeta.frames || Math.round(srcDuration * srcFps);
      const effFps = forceRate > 0 ? forceRate : srcFps;
      const baseFrames = forceRate > 0 ? Math.ceil(srcDuration * forceRate) : srcFrames;
      const afterSkip = Math.max(0, baseFrames - skipFirst);
      const afterNth = everyNth > 1 ? Math.max(0, Math.floor(afterSkip / everyNth)) : afterSkip;
      const availFrames = frameCap > 0 ? Math.min(afterNth, frameCap) : afterNth;
      setTrimLabel("skip_first_frames", `${afterSkip} left`);
      setTrimLabel(
        "frame_load_cap",
        frameCap > 0 ? `${afterNth - availFrames} left` : `all ${afterNth}`
      );
      node.setDirtyCanvas(true, true);
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
      _effEveryNth = everyNth;
    };
    videoEl.addEventListener("loadedmetadata", () => {
      var _a2, _b2;
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
      (_b2 = node == null ? void 0 : node.graph) == null ? void 0 : _b2.setDirtyCanvas(true);
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
        const rawFrame = Math.floor(elapsed * _effFps);
        const curFrame = Math.min(
          Math.floor(rawFrame / _effEveryNth) + 1,
          _effAvailFrames
        );
        infoEl.textContent = `▶ ${curFrame}/${_effAvailFrames} • ${_effInfoText}`;
      }
    });
    const updatePlaybackRange = () => {
      var _a2, _b2, _c, _d, _e, _f, _g, _h;
      if (!_srcMeta || !_srcMeta.fps) return;
      const forceRate = ((_b2 = (_a2 = node.widgets) == null ? void 0 : _a2.find((w) => w.name === "force_rate")) == null ? void 0 : _b2.value) ?? 0;
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
    const videoWrapper = document.createElement("div");
    videoWrapper.style.cssText = "position:relative;width:100%;";
    videoWrapper.appendChild(videoEl);
    previewContainer.appendChild(videoWrapper);
    previewContainer.appendChild(infoEl);
    const maskOverlayCanvas = document.createElement("canvas");
    maskOverlayCanvas.style.cssText = "position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:2;display:none;";
    videoWrapper.appendChild(maskOverlayCanvas);
    const dropOverlay = document.createElement("div");
    dropOverlay.style.cssText = "position:absolute;inset:0;display:none;z-index:20;flex-direction:column;align-items:center;justify-content:center;gap:6px;background:rgba(74,106,138,0.18);border:2px dashed #4a6a8a;border-radius:6px;color:#cfe3f5;font-family:monospace;font-size:12px;pointer-events:none;";
    dropOverlay.innerHTML = `<span style="font-size:22px" aria-hidden="true">🎞</span><span>Drop video to load</span>`;
    previewContainer.appendChild(dropOverlay);
    let _maskOverlayVisible = false;
    let _maskOverlayDataHash = "";
    const showMaskOverlay = () => {
      if (_maskOverlayVisible) {
        maskOverlayCanvas.style.display = "block";
      }
    };
    const hideMaskOverlay = () => {
      maskOverlayCanvas.style.display = "none";
    };
    const drawMaskOverlay = (maskImg) => {
      const w = videoEl.videoWidth || maskImg.naturalWidth;
      const h = videoEl.videoHeight || maskImg.naturalHeight;
      if (!w || !h) return;
      maskOverlayCanvas.width = w;
      maskOverlayCanvas.height = h;
      const ctx = maskOverlayCanvas.getContext("2d");
      if (!ctx) return;
      ctx.clearRect(0, 0, w, h);
      ctx.drawImage(maskImg, 0, 0, w, h);
      const imgData = ctx.getImageData(0, 0, w, h);
      for (let i = 0; i < imgData.data.length; i += 4) {
        const val = imgData.data[i];
        if (val > 128) {
          imgData.data[i] = 0;
          imgData.data[i + 1] = 0;
          imgData.data[i + 2] = 0;
          imgData.data[i + 3] = 0;
        } else {
          imgData.data[i] = 0;
          imgData.data[i + 1] = 0;
          imgData.data[i + 2] = 0;
          imgData.data[i + 3] = 140;
        }
      }
      ctx.putImageData(imgData, 0, 0);
      _maskOverlayVisible = true;
      showMaskOverlay();
    };
    const refreshMaskOverlay = () => {
      var _a2, _b2, _c, _d, _e;
      const enableWidget = (_a2 = node.widgets) == null ? void 0 : _a2.find(
        (w) => w.name === "enable_mask"
      );
      const showWidget = (_b2 = node.widgets) == null ? void 0 : _b2.find(
        (w) => w.name === "show_mask_preview"
      );
      const showMask = Boolean(enableWidget == null ? void 0 : enableWidget.value) && (showWidget == null ? void 0 : showWidget.value) !== false;
      const mpWidget = (_c = node.widgets) == null ? void 0 : _c.find(
        (w) => w.name === "mask_points_data"
      );
      const maskData = (mpWidget == null ? void 0 : mpWidget.value) ? String(mpWidget.value) : "";
      if (!showMask || !maskData || maskData === "undefined") {
        _maskOverlayVisible = false;
        hideMaskOverlay();
        _maskOverlayDataHash = "";
        return;
      }
      const hash = maskData.slice(0, 100) + maskData.length;
      if (hash === _maskOverlayDataHash) return;
      _maskOverlayDataHash = hash;
      try {
        const ptData = JSON.parse(maskData);
        if (ptData.mode === "draw" && ptData.mask_data) {
          const img = new Image();
          img.onload = () => drawMaskOverlay(img);
          img.src = "data:image/png;base64," + ptData.mask_data;
        } else if (((_d = ptData.points) == null ? void 0 : _d.length) > 0 || ptData.box) {
          const vidWidget = (_e = node.widgets) == null ? void 0 : _e.find(
            (w) => w.name === "video"
          );
          if (!(vidWidget == null ? void 0 : vidWidget.value)) return;
          fetch("/ffmpega/first_frame", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              video_path: "input/" + String(vidWidget.value)
            })
          }).then((r) => r.json()).then((info) => {
            const body = {
              frame_path: info.frame_path || "",
              points: ptData.points || [],
              labels: ptData.labels || [],
              image_width: ptData.image_width || 0,
              image_height: ptData.image_height || 0,
              multi_object: ptData.mask_multi_object || false,
              edge_refine: ptData.mask_edge_refine ?? false
            };
            if (ptData.box) body.box = ptData.box;
            return fetch("/ffmpega/sam3_point_mask", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(body)
            });
          }).then((r) => r.json()).then((data) => {
            if (data.raw_mask_b64) {
              const img = new Image();
              img.onload = () => drawMaskOverlay(img);
              img.src = "data:image/png;base64," + data.raw_mask_b64;
            }
          }).catch(() => {
          });
        }
      } catch {
      }
    };
    videoEl.addEventListener("play", hideMaskOverlay);
    videoEl.addEventListener("pause", showMaskOverlay);
    videoEl.addEventListener("ended", showMaskOverlay);
    videoEl.addEventListener("loadedmetadata", () => {
      setTimeout(refreshMaskOverlay, 500);
    });
    let _maskPollHash = "";
    const maskPollInterval = setInterval(() => {
      var _a2, _b2, _c;
      if (!node.graph) {
        clearInterval(maskPollInterval);
        return;
      }
      const enableW = (_a2 = node.widgets) == null ? void 0 : _a2.find(
        (w) => w.name === "enable_mask"
      );
      const showW = (_b2 = node.widgets) == null ? void 0 : _b2.find(
        (w) => w.name === "show_mask_preview"
      );
      const mpW = (_c = node.widgets) == null ? void 0 : _c.find(
        (w) => w.name === "mask_points_data"
      );
      const pollHash = `${enableW == null ? void 0 : enableW.value}|${showW == null ? void 0 : showW.value}|${(mpW == null ? void 0 : mpW.value) ? String(mpW.value).length : 0}`;
      if (pollHash !== _maskPollHash) {
        _maskPollHash = pollHash;
        refreshMaskOverlay();
      }
    }, 1e3);
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
    const updatePreview = (filename) => {
      if (!filename) {
        previewContainer.style.display = "none";
        infoEl.textContent = "No video selected";
        _srcMeta = null;
        clearTrimLabels();
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
    const videoWidget = (_b = this.widgets) == null ? void 0 : _b.find(
      (w) => w.name === "video"
    );
    const origOnRemoved = this.onRemoved;
    this.onRemoved = function() {
      clearInterval(lvPollInterval);
      clearInterval(maskPollInterval);
      if (_dragTimer) clearTimeout(_dragTimer);
      detachPreviewDrop();
      detachButtonDrop();
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
        const resp = await api.fetchApi("/upload/image", {
          method: "POST",
          body
        });
        if (resp.status !== 200) {
          const detail = await resp.text().catch(() => "");
          console.error(
            "FFMPEGA: video upload failed",
            resp.status,
            resp.statusText,
            detail
          );
          showError(`Upload failed (${resp.status}): ${resp.statusText}`);
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
        console.error("FFMPEGA: video upload threw", err);
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
    const acceptVideoFile = (file) => {
      var _a2;
      const ext = (_a2 = file.name.split(".").pop()) == null ? void 0 : _a2.toLowerCase();
      return !!ext && VIDEO_EXTENSIONS.includes(ext);
    };
    const rejectVideoFile = (file) => {
      showError("Invalid file type: " + (file.name.split(".").pop() ?? ""));
    };
    const dropVideoFile = async (file) => {
      if (!acceptVideoFile(file)) {
        rejectVideoFile(file);
        return false;
      }
      return await handleUpload(file);
    };
    let _dragActive = false;
    let _dragBtnHTML = "";
    let _dragBtnBorder = "";
    let _dragBtnAria = null;
    let _dragTimer = null;
    const setDragActive = (active) => {
      if (_dragTimer) {
        clearTimeout(_dragTimer);
        _dragTimer = null;
      }
      if (active) {
        _dragTimer = setTimeout(() => setDragActive(false), 400);
      }
      if (active === _dragActive) return;
      if (active && uploadBtn.disabled) return;
      _dragActive = active;
      if (active) {
        _dragBtnHTML = uploadBtn.innerHTML;
        _dragBtnBorder = uploadBtn.style.border;
        _dragBtnAria = uploadBtn.getAttribute("aria-label");
        uploadBtn.innerHTML = `<span aria-hidden="true">📂</span> Drop to Upload`;
        uploadBtn.setAttribute("aria-label", "Drop to Upload");
        uploadBtn.style.border = "1px dashed #4a6a8a";
        uploadBtn.style.backgroundColor = "#333";
        dropOverlay.style.display = "flex";
      } else {
        if (!uploadBtn.disabled) {
          uploadBtn.innerHTML = _dragBtnHTML;
          uploadBtn.style.border = _dragBtnBorder;
          if (_dragBtnAria) {
            uploadBtn.setAttribute("aria-label", _dragBtnAria);
          } else {
            uploadBtn.removeAttribute("aria-label");
          }
          updateBtn();
        }
        dropOverlay.style.display = "none";
      }
    };
    const dropZoneOpts = {
      accept: acceptVideoFile,
      onDrop: dropVideoFile,
      onReject: rejectVideoFile,
      onDragStateChange: setDragActive,
      disabled: () => uploadBtn.disabled
    };
    const detachPreviewDrop = attachFileDropZone(previewContainer, dropZoneOpts);
    const detachButtonDrop = attachFileDropZone(uploadBtn, dropZoneOpts);
    this.onDragOver = (e) => {
      var _a2, _b2, _c;
      if (!((_c = (_b2 = (_a2 = e == null ? void 0 : e.dataTransfer) == null ? void 0 : _a2.types) == null ? void 0 : _b2.includes) == null ? void 0 : _c.call(_b2, "Files"))) return false;
      setDragActive(true);
      return true;
    };
    this.onDragDrop = async (e) => {
      var _a2, _b2, _c, _d, _e;
      setDragActive(false);
      if (!((_c = (_b2 = (_a2 = e == null ? void 0 : e.dataTransfer) == null ? void 0 : _a2.types) == null ? void 0 : _b2.includes) == null ? void 0 : _c.call(_b2, "Files"))) return false;
      if (uploadBtn.disabled) return true;
      const file = (_e = (_d = e.dataTransfer) == null ? void 0 : _d.files) == null ? void 0 : _e[0];
      if (!file) return false;
      return await dropVideoFile(file);
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
      var _a2, _b2;
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
      if ((_b2 = data == null ? void 0 : data.video_info) == null ? void 0 : _b2[0]) {
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
const VIDEO_ACCEPT = [
  "video/webm",
  "video/mp4",
  "video/x-matroska",
  "video/quicktime",
  "video/x-msvideo"
].join(",");
const PASSTHROUGH_EVENTS = [
  "contextmenu",
  "pointerdown",
  "mousewheel",
  "pointermove",
  "pointerup"
];
function registerLoadMaskVideoNode(nodeType, nodeData) {
  if (nodeData.name !== "FFMPEGALoadMaskVideo") return;
  const onNodeCreated = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function() {
    var _a;
    const result = onNodeCreated == null ? void 0 : onNodeCreated.apply(this, arguments);
    const node = this;
    this.color = "#3a3a5a";
    this.bgcolor = "#2a2a4a";
    const { fileInput, uploadBtn } = createUploadButton(VIDEO_ACCEPT);
    document.body.append(fileInput);
    this.addDOMWidget("upload_button", "btn", uploadBtn, { serialize: false });
    const previewContainer = document.createElement("div");
    previewContainer.className = "ffmpega_preview";
    previewContainer.style.cssText = "width:100%;background:#1a1a1a;border-radius:6px;overflow:hidden;position:relative;";
    const videoEl = document.createElement("video");
    videoEl.controls = true;
    videoEl.loop = true;
    videoEl.muted = true;
    videoEl.setAttribute("aria-label", "Mask video preview");
    videoEl.style.cssText = "width:100%;display:block;";
    const infoEl = document.createElement("div");
    infoEl.style.cssText = "padding:4px 8px;font-size:11px;color:#aaa;font-family:monospace;background:#111;";
    infoEl.textContent = "No mask video selected";
    infoEl.setAttribute("role", "status");
    videoEl.addEventListener("loadedmetadata", () => {
      var _a2;
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
      infoEl.textContent = parts.length ? parts.join(" | ") : "Loaded";
      node.setSize([
        node.size[0],
        node.computeSize([node.size[0], node.size[1]])[1]
      ]);
      (_a2 = node == null ? void 0 : node.graph) == null ? void 0 : _a2.setDirtyCanvas(true);
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
      return [width, -4];
    };
    const updatePreview = (filename) => {
      if (!filename) {
        previewContainer.style.display = "none";
        infoEl.textContent = "No mask video selected";
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
    const handleUpload = async (file) => {
      var _a2;
      const body = new FormData();
      body.append("image", file);
      try {
        const resp = await fetch("/upload/image", { method: "POST", body });
        if (resp.status !== 200) return false;
        const data = await resp.json();
        const filename = data.name;
        if (maskVideoWidget) {
          if (!maskVideoWidget.options.values.includes(filename)) {
            maskVideoWidget.options.values.push(filename);
          }
          maskVideoWidget.value = filename;
          (_a2 = maskVideoWidget.callback) == null ? void 0 : _a2.call(maskVideoWidget, filename);
        }
        updatePreview(filename);
        return true;
      } catch {
        return false;
      }
    };
    fileInput.onchange = async () => {
      var _a2;
      if ((_a2 = fileInput.files) == null ? void 0 : _a2.length) {
        await handleUpload(fileInput.files[0]);
      }
    };
    const maskVideoWidget = (_a = this.widgets) == null ? void 0 : _a.find(
      (w) => w.name === "mask_video"
    );
    if (maskVideoWidget) {
      const origCallback = maskVideoWidget.callback;
      maskVideoWidget.callback = function(value) {
        origCallback == null ? void 0 : origCallback.apply(this, arguments);
        updatePreview(value);
      };
      if (maskVideoWidget.value) {
        setTimeout(() => updatePreview(maskVideoWidget.value), 100);
      }
    }
    const origOnExecuted = this.onExecuted;
    this.onExecuted = function(data) {
      var _a2;
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
    };
    const origOnRemoved = this.onRemoved;
    this.onRemoved = function() {
      fileInput == null ? void 0 : fileInput.remove();
      origOnRemoved == null ? void 0 : origOnRemoved.apply(this, arguments);
    };
    const getVideoUrl = () => videoEl.src || null;
    addVideoPreviewMenu(node, videoEl, previewContainer, previewWidget, getVideoUrl);
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
    wireDynamicInputs(
      node,
      [
        { prefix: "video_path_", type: "STRING", excludes: [] },
        { prefix: "images_", type: "IMAGE", excludes: [] }
      ],
      [
        { name: "video_path", type: "STRING" },
        { name: "images", type: "IMAGE" }
      ]
    );
    return result;
  };
}
function registerSaveImageNode(nodeType, nodeData) {
  if (nodeData.name !== "FFMPEGASaveImage") return;
  const onNodeCreated = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function() {
    const result = onNodeCreated == null ? void 0 : onNodeCreated.apply(this, arguments);
    const node = this;
    this.color = "#2a5a3a";
    this.bgcolor = "#1a4a2a";
    wireDynamicInputs(
      node,
      [
        { prefix: "images_", type: "IMAGE", excludes: [] },
        { prefix: "image_path_", type: "STRING", excludes: [] }
      ],
      [
        { name: "images", type: "IMAGE" },
        { name: "image_path", type: "STRING" }
      ]
    );
    return result;
  };
}
const RESIZE_WIDGETS = [
  "resize_width",
  "resize_height",
  "upscale_method",
  "keep_proportion",
  "pad_color",
  "crop_position",
  "divisible_by",
  "resize_device"
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
function registerLoadImageNode(nodeType, nodeData) {
  if (nodeData.name !== "FFMPEGALoadImagePath") return;
  const origOnCreatedImg = nodeType.prototype.onNodeCreated;
  nodeType.prototype.onNodeCreated = function() {
    var _a;
    const result = origOnCreatedImg == null ? void 0 : origOnCreatedImg.apply(this, arguments);
    const node = this;
    this.color = "#3a5a5a";
    this.bgcolor = "#2a4a4a";
    const fitHeight2 = () => {
      var _a2;
      node.setSize([
        node.size[0],
        node.computeSize([node.size[0], node.size[1]])[1]
      ]);
      (_a2 = node == null ? void 0 : node.graph) == null ? void 0 : _a2.setDirtyCanvas(true);
    };
    const updateResizeVisibility = () => {
      var _a2, _b;
      const enableResize = (_a2 = node.widgets) == null ? void 0 : _a2.find((w) => w.name === "enable_resize");
      const show = Boolean(enableResize == null ? void 0 : enableResize.value);
      for (const name of RESIZE_WIDGETS) {
        const w = (_b = node.widgets) == null ? void 0 : _b.find((ww) => ww.name === name);
        if (w) toggleWidget(w, show);
      }
      fitHeight2();
    };
    const enableResizeWidget = (_a = this.widgets) == null ? void 0 : _a.find((w) => w.name === "enable_resize");
    if (enableResizeWidget) {
      updateResizeVisibility();
      const origResizeCb = enableResizeWidget.callback;
      enableResizeWidget.callback = function(...args) {
        origResizeCb == null ? void 0 : origResizeCb.apply(this, args);
        updateResizeVisibility();
      };
    }
    const origConfigureImg = this.onConfigure;
    this.onConfigure = function(data) {
      origConfigureImg == null ? void 0 : origConfigureImg.apply(this, arguments);
      updateResizeVisibility();
    };
    const origOnExecutedImg = this.onExecuted;
    this.onExecuted = function(data) {
      var _a2, _b, _c, _d;
      origOnExecutedImg == null ? void 0 : origOnExecutedImg.apply(this, arguments);
      if ((_a2 = data == null ? void 0 : data.images) == null ? void 0 : _a2[0]) {
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
        let resolvedFilename = filename;
        let subfolder = "";
        if (filename.includes("/") || filename.includes("\\")) {
          const sep = filename.includes("/") ? "/" : "\\";
          const parts = filename.split(sep);
          resolvedFilename = parts.pop();
          subfolder = parts.join(sep);
        }
        const params = new URLSearchParams({
          filename: resolvedFilename,
          type: "input",
          ...subfolder ? { subfolder } : {}
        });
        const imgSrc = api.apiURL("/view?" + params.toString());
        fetch("/ffmpega/resolve_image_path", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            filename: resolvedFilename,
            subfolder
          })
        }).then((r) => r.json()).then((data) => {
          openPointSelector(self, imgSrc, void 0, data.image_path || "");
        }).catch(() => {
          openPointSelector(self, imgSrc);
        });
      }
    }, {
      content: "🧹 Clear Mask",
      callback: () => {
        var _a, _b;
        const mpWidget = (_a = self.widgets) == null ? void 0 : _a.find((w) => w.name === "mask_points_data");
        if (mpWidget) {
          mpWidget.value = "";
        }
        (_b = self.setDirtyCanvas) == null ? void 0 : _b.call(self, true, true);
        flashNode(self, "#4a7a4a");
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
function getSkipTimeSec$1(node) {
  var _a, _b;
  const skipWidget = (_a = node.widgets) == null ? void 0 : _a.find((w) => w.name === "skip_first_frames");
  const rateWidget = (_b = node.widgets) == null ? void 0 : _b.find((w) => w.name === "force_rate");
  const skipFrames = Number(skipWidget == null ? void 0 : skipWidget.value) || 0;
  const fps = Number(rateWidget == null ? void 0 : rateWidget.value) || 0;
  if (skipFrames <= 0) return 0.01;
  return skipFrames / (fps > 0 ? fps : 30);
}
function captureFirstFrameAndOpen(node, videoSrc, startTimeSec = 0.01) {
  const tmpVideo = document.createElement("video");
  tmpVideo.crossOrigin = "anonymous";
  tmpVideo.muted = true;
  tmpVideo.preload = "auto";
  tmpVideo.src = videoSrc;
  tmpVideo.currentTime = startTimeSec;
  let videoFilePath = "";
  try {
    const u = new URL(videoSrc, window.location.origin);
    videoFilePath = u.searchParams.get("filename") || u.searchParams.get("path") || "";
  } catch {
  }
  const seekTimeout = setTimeout(() => {
    flashNode(node, "#7a4a4a");
    tmpVideo.remove();
  }, 1e4);
  tmpVideo.addEventListener("seeked", () => {
    var _a;
    clearTimeout(seekTimeout);
    const c = document.createElement("canvas");
    c.width = tmpVideo.videoWidth;
    c.height = tmpVideo.videoHeight;
    c.getContext("2d").drawImage(tmpVideo, 0, 0);
    const frameDataUrl = c.toDataURL("image/jpeg", 0.95);
    tmpVideo.remove();
    if (videoFilePath) {
      const skipWidget = (_a = node.widgets) == null ? void 0 : _a.find((w) => w.name === "skip_first_frames");
      const skipFrames = Number(skipWidget == null ? void 0 : skipWidget.value) || 0;
      fetch("/ffmpega/first_frame", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video_path: videoFilePath, skip_frames: skipFrames })
      }).then((r) => r.json()).then((data) => {
        openPointSelector(node, frameDataUrl, videoSrc, data.frame_path || "");
      }).catch(() => {
        openPointSelector(node, frameDataUrl);
      });
    } else {
      openPointSelector(node, frameDataUrl);
    }
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
          captureFirstFrameAndOpen(self, src, getSkipTimeSec$1(self));
        }
      }, {
        content: "🧹 Clear Mask",
        callback: () => {
          var _a, _b;
          const mpWidget = (_a = self.widgets) == null ? void 0 : _a.find((w) => w.name === "mask_points_data");
          if (mpWidget) {
            mpWidget.value = "";
          }
          (_b = self.setDirtyCanvas) == null ? void 0 : _b.call(self, true, true);
          flashNode(self, "#4a7a4a");
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
function openCropSelector(node, videoSrc, startTimeSec = 0) {
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
      const initialTime = startTimeSec > 0 ? startTimeSec : Math.min(0.1, videoDuration * 0.01);
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
function getSkipTimeSec(node) {
  var _a, _b;
  const skipWidget = (_a = node.widgets) == null ? void 0 : _a.find((w) => w.name === "skip_first_frames");
  const rateWidget = (_b = node.widgets) == null ? void 0 : _b.find((w) => w.name === "force_rate");
  const skipFrames = Number(skipWidget == null ? void 0 : skipWidget.value) || 0;
  const fps = Number(rateWidget == null ? void 0 : rateWidget.value) || 0;
  if (skipFrames <= 0) return 0;
  return skipFrames / (fps > 0 ? fps : 30);
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
          openCropSelector(self, src, getSkipTimeSec(self));
        }
      }, {
        content: "🧹 Clear Crop",
        callback: () => {
          var _a, _b;
          const cdWidget = (_a = self.widgets) == null ? void 0 : _a.find((w) => w.name === "crop_data");
          if (cdWidget) {
            cdWidget.value = "";
          }
          applyCropPreview(self, null);
          (_b = self.setDirtyCanvas) == null ? void 0 : _b.call(self, true, true);
          flashNode(self, "#4a7a4a");
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
      "Lightweight bridge for quick conversions without full Load/Save nodes."
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
    registerLoadMaskVideoNode(nodeType, nodeData);
    registerSaveVideoNode(nodeType, nodeData);
    registerSaveImageNode(nodeType, nodeData);
    registerLoadImageNode(nodeType, nodeData);
    registerTextInputNode(nodeType, nodeData);
    registerPointSelectorHooks(nodeType, nodeData);
    registerCropSelectorHooks(nodeType, nodeData);
  }
});
console.log("FFMPEGA UI extensions loaded");
