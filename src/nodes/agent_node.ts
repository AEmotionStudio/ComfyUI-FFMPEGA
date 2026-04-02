/**
 * FFMPEGAgent node UI handler.
 *
 * Features:
 * - Dynamic widget visibility (LLM model, save_output, advanced_options, batch_mode)
 * - Dynamic input slots (auto-expand image/audio/video/text inputs)
 * - Preset context menu with 200+ preset prompts
 * - Clipboard paste/copy support
 */

import { app } from "comfyui/app";
import {
    updateDynamicSlots,
    handlePaste, setPrompt, flashNode,
    RANDOM_PROMPTS, SLOT_LABELS,
} from "@ffmpega/shared/ui_helpers";
import type {
    ComfyNodeType, ComfyNodeData, ComfyNode,
    ComfyWidget, ComfyMenuOption,
} from "@ffmpega/types/comfyui";

// ---- Type definitions ----

interface AgentNode extends ComfyNode {
    _previousPrompt?: string;
    onConnectionsChange?: (
        type: number, slotIndex: number, isConnected: boolean,
        link: unknown, ioSlot: unknown,
    ) => void;
    onConfigure?: (info: AgentSerializedInfo) => void;
}

interface AgentSerializedInfo {
    inputs?: Array<{ name: string; type: string; link?: number | null }>;
    [key: string]: unknown;
}

/** Dynamic slot group configuration */
interface DynamicPrefixConfig {
    prefix: string;
    type: string;
    excludes: string[];
}

// ---- Constants ----

const DYNAMIC_PREFIXES: DynamicPrefixConfig[] = [
    { prefix: "images_", type: "IMAGE", excludes: [] },
    { prefix: "image_", type: "IMAGE", excludes: ["images_", "image_path_"] },
    { prefix: "audio_", type: "AUDIO", excludes: ["audio_output_mode", "audio_resample_rate"] },
    { prefix: "video_", type: "STRING", excludes: ["video_path", "video_folder", "video_depth_encoder", "video_depth_colormap"] },
    { prefix: "image_path_", type: "STRING", excludes: [] },
    { prefix: "text_", type: "STRING", excludes: [] },
];

// ---- Helpers ----

/** VHS-style widget show/hide */
function toggleWidget(widget: ComfyWidget | undefined, show: boolean): void {
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
        widget.computeSize = () => [0, -4] as [number, number];
        widget.hidden = true;
        if (widget.element) widget.element.hidden = true;
    }
}

/** Check if an LLM model needs an API key */
function needsApiKey(model: unknown): boolean {
    if (!model || typeof model !== "string") return false;
    if (model === "none") return false;
    if (model === "gemini-cli" || model === "claude-cli" || model === "cursor-agent" || model === "qwen-cli") return false;
    return model.startsWith("gpt") ||
        model.startsWith("claude") ||
        model.startsWith("gemini") ||
        model === "custom";
}

// ---- Preset menu data ----

/** Build the massive preset submenu. Returns ComfyMenuOption[] */
function buildPresetMenu(node: AgentNode): ComfyMenuOption[] {
    const sp = (text: string) => setPrompt(node, text);
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
                    { content: "Action", callback: () => sp("Apply fast-paced action movie grading with high contrast") },
                ]
            },
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
                    { content: "Lo-Fi Chill", callback: () => sp("Apply a lo-fi chill aesthetic with muted tones") },
                ]
            },
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
                    { content: "Apply LUT", callback: () => sp("Apply a 3D LUT color grade from file") },
                ]
            },
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
                    { content: "Music Video", callback: () => sp("Apply punchy music video look with contrast and vignette") },
                ]
            },
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
                    { content: "🎙️ Karaoke Subtitles", callback: () => sp("Add karaoke-style word-by-word subtitles with yellow fill") },
                ]
            },
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
                    { content: "Mirror / Flip", callback: () => sp("Mirror the video horizontally") },
                ]
            },
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
                    { content: "Slide In", callback: () => sp("Slide the video in from the left edge") },
                ]
            },
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
                    { content: "Animated Overlay", callback: () => sp("Add a moving image overlay with scroll motion") },
                ]
            },
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
                    { content: "Intro / Outro", callback: () => sp("Add intro and outro segments to the video") },
                ]
            },
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
                    { content: "Frame Rate Interpolation", callback: () => sp("Interpolate frame rate to smooth 60fps") },
                ]
            },
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
                    { content: "Audio Delay", callback: () => sp("Add a delay offset to the audio track") },
                ]
            },
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
                    { content: "Concat / Join Videos", callback: () => sp("Concatenate video segments together sequentially") },
                ]
            },
        },
    ];
}

// ---- Registration ----

export function registerAgentNode(
    nodeType: ComfyNodeType,
    nodeData: ComfyNodeData,
): void {
    if (nodeData.name !== "FFMPEGAgent") return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;

    nodeType.prototype.onNodeCreated = function (this: AgentNode) {
        const result = onNodeCreated?.apply(this, arguments as unknown as []);
        const node = this;

        this.color = "#2a3a5a";
        this.bgcolor = "#1a2a4a";

        /** Resize node to fit visible widgets */
        const fitHeight = (): void => {
            node.setSize([
                node.size[0],
                node.computeSize([node.size[0], node.size[1]])[1],
            ]);
            node?.graph?.setDirtyCanvas(true);
        };

        // Hoisted so restoreSlots (onConfigure) can re-run it after values are restored
        let updateLlmVisibility: (() => void) | undefined;

        // --- LLM model → custom_model / api_key visibility ---
        const llmWidget = this.widgets?.find((w: ComfyWidget) => w.name === "llm_model");
        if (llmWidget) {
            const customWidget = this.widgets?.find((w: ComfyWidget) => w.name === "custom_model");
            const apiKeyWidget = this.widgets?.find((w: ComfyWidget) => w.name === "api_key");
            const ollamaUrlWidget = this.widgets?.find((w: ComfyWidget) => w.name === "ollama_url");
            const verifyWidget = this.widgets?.find((w: ComfyWidget) => w.name === "verify_output");
            const visionWidget = this.widgets?.find((w: ComfyWidget) => w.name === "use_vision");
            const ptcWidget = this.widgets?.find((w: ComfyWidget) => w.name === "ptc_mode");

            function doUpdateLlmVisibility(): void {
                const model = llmWidget!.value;
                const isNone = model === "none";
                toggleWidget(customWidget, model === "custom");
                toggleWidget(apiKeyWidget, needsApiKey(model));
                if (ollamaUrlWidget) toggleWidget(ollamaUrlWidget, !isNone);
                if (verifyWidget) toggleWidget(verifyWidget, !isNone);
                if (visionWidget) toggleWidget(visionWidget, !isNone);
                if (ptcWidget) toggleWidget(ptcWidget, !isNone);
                // track_tokens and log_usage only relevant with an LLM
                const ttWidget = node.widgets?.find((w: ComfyWidget) => w.name === "track_tokens");
                const luWidget = node.widgets?.find((w: ComfyWidget) => w.name === "log_usage");
                if (ttWidget) toggleWidget(ttWidget, !isNone);
                if (luWidget) toggleWidget(luWidget, !isNone);
                const noLlmModeWidget = node.widgets?.find((w: ComfyWidget) => w.name === "no_llm_mode");
                if (noLlmModeWidget) {
                    toggleWidget(noLlmModeWidget, isNone);
                    // Hook no_llm_mode callback for conditional sub-widget visibility
                    if (!noLlmModeWidget._cbHooked) {
                        noLlmModeWidget._cbHooked = true;
                        const origNoLlmCb = noLlmModeWidget.callback;
                        noLlmModeWidget.callback = function (...args: unknown[]) {
                            origNoLlmCb?.apply(this, args);
                            updateNoLlmModeVisibility();
                            fitHeight();
                        };
                    }
                }
                updateNoLlmModeVisibility();
                fitHeight();

                // Hook f1_style_transfer so noise_level toggles dynamically
                const f1StyleTransferWidget = node.widgets?.find((w: ComfyWidget) => w.name === "f1_style_transfer");
                if (f1StyleTransferWidget && !f1StyleTransferWidget._cbHooked) {
                    f1StyleTransferWidget._cbHooked = true;
                    const origF1Cb = f1StyleTransferWidget.callback;
                    f1StyleTransferWidget.callback = function (...args: unknown[]) {
                        origF1Cb?.apply(this, args);
                        updateNoLlmModeVisibility();
                        fitHeight();
                    };
                }
            }

            updateLlmVisibility = doUpdateLlmVisibility;
            doUpdateLlmVisibility();
            const origLlmCb = llmWidget.callback;
            llmWidget.callback = function (...args: unknown[]) {
                origLlmCb?.apply(this, args);
                doUpdateLlmVisibility();
            };
        }

        // --- Always-hidden widgets (functional but not shown) ---
        const alwaysHidden = [
            "video_path", "save_output", "output_path",
            "preview_mode", "crf", "encoding_preset",
            "batch_mode", "video_folder", "file_pattern", "max_concurrent",
        ];
        for (const name of alwaysHidden) {
            const w = this.widgets?.find((ww: ComfyWidget) => ww.name === name);
            if (w) toggleWidget(w, false);
        }

        // --- advanced_options toggle → all advanced widgets visibility ---
        const advancedWidget = this.widgets?.find((w: ComfyWidget) => w.name === "advanced_options");
        const subtitleWidget = this.widgets?.find((w: ComfyWidget) => w.name === "subtitle_path");
        const advVisionWidget = this.widgets?.find((w: ComfyWidget) => w.name === "use_vision");
        const advVerifyWidget = this.widgets?.find((w: ComfyWidget) => w.name === "verify_output");
        const whisperDevWidget = this.widgets?.find((w: ComfyWidget) => w.name === "whisper_device");
        const whisperModelWidget = this.widgets?.find((w: ComfyWidget) => w.name === "whisper_model");
        const sam3MaxObjWidget = this.widgets?.find((w: ComfyWidget) => w.name === "sam3_max_objects");
        const sam3ThreshWidget = this.widgets?.find((w: ComfyWidget) => w.name === "sam3_det_threshold");
        const maskTypeWidget = this.widgets?.find((w: ComfyWidget) => w.name === "mask_output_type");
        const batchWidget = this.widgets?.find((w: ComfyWidget) => w.name === "batch_mode");
        const folderWidget = this.widgets?.find((w: ComfyWidget) => w.name === "video_folder");
        const patternWidget = this.widgets?.find((w: ComfyWidget) => w.name === "file_pattern");
        const concurrentWidget = this.widgets?.find((w: ComfyWidget) => w.name === "max_concurrent");
        const trackTokensWidget = this.widgets?.find((w: ComfyWidget) => w.name === "track_tokens");
        const logUsageWidget = this.widgets?.find((w: ComfyWidget) => w.name === "log_usage");
        const allowDownloadsWidget = this.widgets?.find((w: ComfyWidget) => w.name === "allow_model_downloads");
        const fluxSmoothingWidget = this.widgets?.find((w: ComfyWidget) => w.name === "flux_smoothing");
        const audioOutputModeWidget = this.widgets?.find((w: ComfyWidget) => w.name === "audio_output_mode");
        const marigoldOutputWidget = this.widgets?.find((w: ComfyWidget) => w.name === "marigold_output_type");
        const vdaEncoderWidget = this.widgets?.find((w: ComfyWidget) => w.name === "video_depth_encoder");
        const vdaColormapWidget = this.widgets?.find((w: ComfyWidget) => w.name === "video_depth_colormap");

        /** Show/hide mode-specific widgets based on no_llm_mode value */
        function updateNoLlmModeVisibility(): void {
            // Use dynamic lookups to avoid temporal dead zone issues
            const adv = node.widgets?.find((w: ComfyWidget) => w.name === "advanced_options");
            const showAdvanced = Boolean(adv?.value);
            const llm = node.widgets?.find((w: ComfyWidget) => w.name === "llm_model");
            const isNone = llm?.value === "none";
            const noLlmMode = node.widgets?.find((w: ComfyWidget) => w.name === "no_llm_mode");
            const mode = isNone ? String(noLlmMode?.value ?? "manual") : "";

            // --- Mode-specific sub-widgets (only show for matching mode) ---

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
            const showScail = showAdvanced && mode === "scail";
            const showFoundation1 = showAdvanced && mode === "foundation1";
            const showFishSpeech = showAdvanced && mode === "fish_speech";
            const showSharp = showAdvanced && mode === "sharp";
            const showWanAnimate = showAdvanced && mode === "wan_animate";

            // Marigold
            const mw = node.widgets?.find((w: ComfyWidget) => w.name === "marigold_output_type");
            const mc = node.widgets?.find((w: ComfyWidget) => w.name === "marigold_colormap");
            if (mw) toggleWidget(mw, showMarigold);
            if (mc) toggleWidget(mc, showMarigold && String(mw?.value) === "depth");

            // Video Depth Anything
            const ve = node.widgets?.find((w: ComfyWidget) => w.name === "video_depth_encoder");
            const vc = node.widgets?.find((w: ComfyWidget) => w.name === "video_depth_colormap");
            if (ve) toggleWidget(ve, showVda);
            if (vc) toggleWidget(vc, showVda);

            // AI Upscale
            const um = node.widgets?.find((w: ComfyWidget) => w.name === "upscale_model");
            const us = node.widgets?.find((w: ComfyWidget) => w.name === "upscale_scale");
            const sr = node.widgets?.find((w: ComfyWidget) => w.name === "seedvr_resolution");
            const bb = node.widgets?.find((w: ComfyWidget) => w.name === "blockswap_blocks");
            const rq = node.widgets?.find((w: ComfyWidget) => w.name === "rtx_quality");
            if (um) toggleWidget(um, showUpscale);
            // Model-specific widget visibility
            const modelVal = String(um?.value ?? "");
            const isSeedvr = showUpscale && modelVal.startsWith("seedvr2");
            const isRtxVsr = showUpscale && modelVal === "rtx_vsr";
            const isGanModel = showUpscale && !isSeedvr && !isRtxVsr;
            if (us) toggleWidget(us, isGanModel || isRtxVsr);  // scale for GAN + RTX
            if (sr) toggleWidget(sr, isSeedvr);                 // resolution for SeedVR2
            if (bb) toggleWidget(bb, isSeedvr);                 // blockswap for SeedVR2
            if (rq) toggleWidget(rq, isRtxVsr);                 // quality for RTX VSR

            // Rembg
            const rm = node.widgets?.find((w: ComfyWidget) => w.name === "rembg_model");
            const rb = node.widgets?.find((w: ComfyWidget) => w.name === "rembg_background");
            if (rm) toggleWidget(rm, showRembg);
            if (rb) toggleWidget(rb, showRembg);

            // Whisper (transcribe / karaoke)
            const wd = node.widgets?.find((w: ComfyWidget) => w.name === "whisper_device");
            const wm = node.widgets?.find((w: ComfyWidget) => w.name === "whisper_model");
            if (wd) toggleWidget(wd, showWhisper);
            if (wm) toggleWidget(wm, showWhisper);

            // SAM-Audio
            const sam = node.widgets?.find((w: ComfyWidget) => w.name === "sam_audio_model");
            if (sam) toggleWidget(sam, showSamAudio);

            // NormalCrafter
            const nc = node.widgets?.find((w: ComfyWidget) => w.name === "normalcrafter_max_res");
            if (nc) toggleWidget(nc, showNormalcrafter);

            // FLUX Klein widgets
            const fluxKleinWidgetNames = [
                "flux_image_source", "flux_klein_steps", "flux_klein_guidance",
                "flux_klein_seed", "flux_klein_width", "flux_klein_height",
            ];
            for (const wn of fluxKleinWidgetNames) {
                const w = node.widgets?.find((w: ComfyWidget) => w.name === wn);
                if (w) toggleWidget(w, showFluxKleinMode);
            }

            // Kiwi-Edit widgets
            const kiwiWidgetNames = [
                "kiwi_model", "kiwi_precision", "kiwi_resolution",
                "kiwi_max_frames",
                "kiwi_steps", "kiwi_guidance", "kiwi_block_swap",
                "kiwi_long_video", "kiwi_seed", "kiwi_flow_shift",
                "kiwi_task_type", "kiwi_scheduler",
            ];
            for (const name of kiwiWidgetNames) {
                const w = node.widgets?.find((ww: ComfyWidget) => ww.name === name);
                if (w) toggleWidget(w, showKiwiEdit);
            }
            // kiwi_width / kiwi_height only visible when kiwi_resolution = "custom"
            const kiwiRes = node.widgets?.find((ww: ComfyWidget) => ww.name === "kiwi_resolution");
            const showKiwiCustom = showKiwiEdit && String(kiwiRes?.value) === "custom";
            const kw = node.widgets?.find((ww: ComfyWidget) => ww.name === "kiwi_width");
            const kh = node.widgets?.find((ww: ComfyWidget) => ww.name === "kiwi_height");
            if (kw) toggleWidget(kw, showKiwiCustom);
            if (kh) toggleWidget(kh, showKiwiCustom);

            // DreamID-Omni widgets
            const dreamidWidgetNames = [
                "dreamid_precision", "dreamid_resolution", "dreamid_steps", "dreamid_seed",
                "dreamid_solver", "dreamid_video_cfg", "dreamid_video_ref_cfg",
                "dreamid_audio_cfg", "dreamid_audio_ref_cfg",
            ];
            for (const name of dreamidWidgetNames) {
                const w = node.widgets?.find((ww: ComfyWidget) => ww.name === name);
                if (w) toggleWidget(w, showDreamidOmni);
            }

            // SCAIL pose-driven animation widgets
            const scailWidgetNames = [
                "scail_precision", "scail_steps", "scail_guidance",
                "scail_shift", "scail_solver", "scail_seed",
            ];
            for (const name of scailWidgetNames) {
                const w = node.widgets?.find((ww: ComfyWidget) => ww.name === name);
                if (w) toggleWidget(w, showScail);
            }

            // SVI 2.0 Pro (Stable Video Infinity) widgets
            const showSvi = showAdvanced && mode === "svi";
            const sviWidgetNames = [
                "svi_num_clips", "svi_height", "svi_width", "svi_fps",
                "svi_cfg_scale", "svi_overlap_frames", "svi_seed_multiplier",
                "svi_steps", "svi_high_model_ratio", "svi_frames_per_clip",
                "svi_variant", "svi_model_high", "svi_model_low",
                "svi_lora_high", "svi_lora_low",
                "svi_extra_lora_high", "svi_extra_lora_low",
                "svi_vae", "svi_text_encoder", "svi_sampler", "svi_scheduler",
            ];
            for (const name of sviWidgetNames) {
                const w = node.widgets?.find((ww: ComfyWidget) => ww.name === name);
                if (w) toggleWidget(w, showSvi);
            }

            // SHARP (3D Gaussian View Synthesis) widgets
            const sharpWidgetNames = [
                "sharp_trajectory", "sharp_num_frames", "sharp_max_disparity",
                "sharp_max_zoom", "sharp_save_ply", "sharp_device",
            ];
            for (const name of sharpWidgetNames) {
                const w = node.widgets?.find((ww: ComfyWidget) => ww.name === name);
                if (w) toggleWidget(w, showSharp);
            }

            // Wan-Animate (motion-driven character animation) widgets
            const wanAnimateWidgetNames = [
                "wan_animate_mode", "wan_animate_steps", "wan_animate_guidance",
                "wan_animate_seed", "wan_animate_num_frames",
                "wan_animate_height", "wan_animate_width",
                "wan_animate_pose_strength", "wan_animate_face_strength",
            ];
            for (const name of wanAnimateWidgetNames) {
                const w = node.widgets?.find((ww: ComfyWidget) => ww.name === name);
                if (w) toggleWidget(w, showWanAnimate);
            }
            // Dynamic LoRA slots: a always visible, b when a≠none, c when b≠none, d when c≠none
            const wanLoraSlots = ["a", "b", "c", "d"];
            let showNextLora = showWanAnimate;
            for (const slot of wanLoraSlots) {
                const loraW = node.widgets?.find((ww: ComfyWidget) => ww.name === `wan_animate_lora_${slot}`);
                const strW = node.widgets?.find((ww: ComfyWidget) => ww.name === `wan_animate_lora_strength_${slot}`);
                if (loraW) toggleWidget(loraW, showNextLora);
                if (strW) toggleWidget(strW, showNextLora && String(loraW?.value ?? "none") !== "none");
                showNextLora = showNextLora && String(loraW?.value ?? "none") !== "none";
            }

            // ACE-Step widgets
            const aceWidgetNames = [
                "ace_negative_prompt", "ace_cover_strength", "ace_steps",
                "ace_cfg_scale", "ace_bpm", "ace_key", "ace_time_sig",
            ];
            for (const name of aceWidgetNames) {
                const w = node.widgets?.find((ww: ComfyWidget) => ww.name === name);
                if (w) toggleWidget(w, showAceStep);
            }

            // Foundation-1 widgets
            const f1WidgetNames = [
                "f1_preset", "f1_instrument", "f1_fx", "f1_structure",
                "f1_negative_prompt", "f1_bpm", "f1_bars",
                "f1_key", "f1_duration", "f1_steps", "f1_cfg_scale",
                "f1_style_transfer",
            ];
            for (const name of f1WidgetNames) {
                const w = node.widgets?.find((ww: ComfyWidget) => ww.name === name);
                if (w) toggleWidget(w, showFoundation1);
            }
            // noise_level only visible when style_transfer is on
            const f1StyleWidget = node.widgets?.find((w: ComfyWidget) => w.name === "f1_style_transfer");
            const f1NoiseWidget = node.widgets?.find((w: ComfyWidget) => w.name === "f1_noise_level");
            if (f1NoiseWidget) toggleWidget(f1NoiseWidget, showFoundation1 && Boolean(f1StyleWidget?.value));

            // Fish Speech TTS widgets
            const fishWidgetNames = [
                "fish_model_variant", "fish_voice", "fish_emotion",
                "fish_temperature", "fish_top_p", "fish_repetition_penalty",
            ];
            for (const name of fishWidgetNames) {
                const w = node.widgets?.find((ww: ComfyWidget) => ww.name === name);
                if (w) toggleWidget(w, showFishSpeech);
            }

            // Onion Skin widgets
            const onionWidgetNames = ["onion_blend_mode", "onion_opacity", "onion_decay"];
            for (const name of onionWidgetNames) {
                const w = node.widgets?.find((ww: ComfyWidget) => ww.name === name);
                if (w) toggleWidget(w, showOnionSkin);
            }

            // Comparison widgets
            const comparisonWidgetNames = [
                "comparison_style", "comparison_labels",
                "comparison_label_a", "comparison_label_b",
            ];
            for (const name of comparisonWidgetNames) {
                const w = node.widgets?.find((ww: ComfyWidget) => ww.name === name);
                if (w) toggleWidget(w, showComparison);
            }

            // Video Matting widgets
            const showMatting = showAdvanced && mode === "video_matting";
            const mattingWidgetNames = [
                "matting_output", "matting_background", "matting_max_size",
            ];
            for (const name of mattingWidgetNames) {
                const w = node.widgets?.find((ww: ComfyWidget) => ww.name === name);
                if (w) toggleWidget(w, showMatting);
            }

            // LivePortrait expression controls (animate_portrait mode)
            const showLivePortrait = showAdvanced && mode === "animate_portrait";
            const lpWidgetNames = [
                "lp_rotate_pitch", "lp_rotate_yaw", "lp_rotate_roll",
                "lp_blink", "lp_eyebrow", "lp_wink",
                "lp_pupil_x", "lp_pupil_y",
                "lp_aaa", "lp_eee", "lp_woo", "lp_smile",
                "lp_retargeting_eyes", "lp_retargeting_mouth",
                "lp_crop_factor",
                "lp_expression_preset", "lp_save_expression",
                "lp_sample_image", "lp_sample_ratio", "lp_sample_parts",
            ];
            for (const name of lpWidgetNames) {
                const w = node.widgets?.find((ww: ComfyWidget) => ww.name === name);
                if (w) toggleWidget(w, showLivePortrait);
            }

            // --- Widgets that are relevant to LLM mode or specific no-LLM modes ---
            // These should hide when a no-LLM mode doesn't use them.

            // use_sam3 toggle: shown for eligible no-LLM modes
            const sam3EligibleModes = new Set([
                "lip_sync", "animate_portrait", "marigold", "normalcrafter",
                "video_depth", "flux_klein", "kiwi_edit", "minimax_remover", "ai_upscale",
                "rembg", "onion_skin", "comparison",
            ]);
            const showUseSam3 = showAdvanced && sam3EligibleModes.has(mode);
            const useSam3Widget = node.widgets?.find((w: ComfyWidget) => w.name === "use_sam3");
            if (useSam3Widget) toggleWidget(useSam3Widget, showUseSam3);
            const useSam3On = showUseSam3 && Boolean(useSam3Widget?.value);

            // SAM3 config widgets: show for sam3_masking mode, LLM mode, OR when use_sam3 is on
            const showSam3 = showAdvanced && (!isNone || mode === "sam3_masking" || useSam3On);
            for (const wName of ["sam3_max_objects", "sam3_det_threshold", "mask_output_type"]) {
                const w = node.widgets?.find((ww: ComfyWidget) => ww.name === wName);
                if (w) toggleWidget(w, showSam3);
            }

            // use_flux_klein / use_kiwi_edit / use_minimax_remover: only relevant for LLM mode
            const showLlmToggles = showAdvanced && !isNone;
            for (const wName of ["use_flux_klein", "use_kiwi_edit", "use_minimax_remover", "use_dreamid_omni"]) {
                const w = node.widgets?.find((ww: ComfyWidget) => ww.name === wName);
                if (w) toggleWidget(w, showLlmToggles);
            }
            // flux_smoothing depends on use_flux_klein being on AND visible
            const fluxKleinWidget = node.widgets?.find((w: ComfyWidget) => w.name === "use_flux_klein");
            const fsw = node.widgets?.find((w: ComfyWidget) => w.name === "flux_smoothing");
            if (fsw) toggleWidget(fsw, showLlmToggles && Boolean(fluxKleinWidget?.value));

            // audio_output_mode: for all audio-related modes + LLM mode
            const _AUDIO_MODES = new Set(["generate_audio", "generate_music", "foundation1", "fish_speech", "audio_inpaint", "audio_separate", "ace_step"]);
            const showAudioMode = showAdvanced && (!isNone || _AUDIO_MODES.has(mode));
            const mmw = node.widgets?.find((w: ComfyWidget) => w.name === "audio_output_mode");
            if (mmw) toggleWidget(mmw, showAudioMode);

            // audio_resample_rate: only for manual (effects builder) mode
            const showResample = showAdvanced && mode === "manual";
            const arw = node.widgets?.find((w: ComfyWidget) => w.name === "audio_resample_rate");
            if (arw) toggleWidget(arw, showResample);

            // subtitle_path: relevant for transcribe, karaoke, manual, AND LLM mode
            const showSubtitle = showAdvanced && (!isNone || mode === "manual" || mode === "transcribe" || mode === "karaoke_subtitles");
            const sw = node.widgets?.find((w: ComfyWidget) => w.name === "subtitle_path");
            if (sw) toggleWidget(sw, showSubtitle);
        }

        function updateAdvancedVisibility(): void {
            const show = Boolean(advancedWidget?.value);
            const llm = node.widgets?.find((w: ComfyWidget) => w.name === "llm_model");
            const isNone = llm?.value === "none";
            if (trackTokensWidget) toggleWidget(trackTokensWidget, show && !isNone);
            if (logUsageWidget) toggleWidget(logUsageWidget, show && !isNone);
            if (allowDownloadsWidget) toggleWidget(allowDownloadsWidget, show);
            // Mode-specific widgets are handled inside updateNoLlmModeVisibility
            updateNoLlmModeVisibility();
            fitHeight();
        }

        if (advancedWidget) {
            updateAdvancedVisibility();
            const origAdvCb = advancedWidget.callback;
            advancedWidget.callback = function (...args: unknown[]) {
                origAdvCb?.apply(this, args);
                updateAdvancedVisibility();
            };
        }

        // --- use_flux_klein → flux_smoothing visibility ---
        const fluxKleinToggle = this.widgets?.find((w: ComfyWidget) => w.name === "use_flux_klein");
        if (fluxKleinToggle) {
            const origFluxCb = fluxKleinToggle.callback;
            fluxKleinToggle.callback = function (...args: unknown[]) {
                origFluxCb?.apply(this, args);
                updateAdvancedVisibility();
            };
        }

        // --- use_sam3 → SAM3 sub-widget visibility ---
        const useSam3Toggle = this.widgets?.find((w: ComfyWidget) => w.name === "use_sam3");
        if (useSam3Toggle) {
            const origSam3Cb = useSam3Toggle.callback;
            useSam3Toggle.callback = function (...args: unknown[]) {
                origSam3Cb?.apply(this, args);
                updateAdvancedVisibility();
            };
        }

        // --- upscale_model → blockswap_blocks visibility ---
        const upscaleModelToggle = this.widgets?.find((w: ComfyWidget) => w.name === "upscale_model");
        if (upscaleModelToggle) {
            const origUpscaleCb = upscaleModelToggle.callback;
            upscaleModelToggle.callback = function (...args: unknown[]) {
                origUpscaleCb?.apply(this, args);
                updateAdvancedVisibility();
            };
        }

        // --- kiwi_resolution → kiwi_width / kiwi_height visibility ---
        const kiwiResolutionToggle = this.widgets?.find((w: ComfyWidget) => w.name === "kiwi_resolution");
        if (kiwiResolutionToggle) {
            const origKiwiResCb = kiwiResolutionToggle.callback;
            kiwiResolutionToggle.callback = function (...args: unknown[]) {
                origKiwiResCb?.apply(this, args);
                updateAdvancedVisibility();
            };
        }



        // --- wan_animate_lora_* → cascade next LoRA slot visibility ---
        for (const slot of ["a", "b", "c", "d"]) {
            const wanLoraSlotW = this.widgets?.find((w: ComfyWidget) => w.name === `wan_animate_lora_${slot}`);
            if (wanLoraSlotW) {
                const origCb = wanLoraSlotW.callback;
                wanLoraSlotW.callback = function (...args: unknown[]) {
                    origCb?.apply(this, args);
                    updateAdvancedVisibility();
                };
            }
        }

        // --- marigold_output_type → colormap visibility ---
        const marigoldTypeWidget = this.widgets?.find((w: ComfyWidget) => w.name === "marigold_output_type");
        if (marigoldTypeWidget) {
            const origMtCb = marigoldTypeWidget.callback;
            marigoldTypeWidget.callback = function (...args: unknown[]) {
                origMtCb?.apply(this, args);
                updateAdvancedVisibility();
            };
        }

        // batch_mode and sub-widgets are permanently hidden (see alwaysHidden)

        // --- Dynamic input slots (auto-expand) ---
        const origOnConnectionsChange = this.onConnectionsChange;
        this.onConnectionsChange = function (
            type: number, slotIndex: number,
            isConnected: boolean, link: unknown, ioSlot: unknown,
        ): void {
            origOnConnectionsChange?.apply(this, arguments as unknown as [number, number, boolean, unknown, unknown]);
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

        // --- Restore dynamic slots on workflow load ---
        const origOnConfigure = this.onConfigure;
        this.onConfigure = function (info: AgentSerializedInfo): void {
            origOnConfigure?.apply(this, arguments as unknown as [AgentSerializedInfo]);

            if (info?.inputs) {
                const existingNames = new Set(this.inputs.map(i => i.name));

                // Step 1: Pre-create dynamic slots from saved workflow
                for (const saved of info.inputs) {
                    if (!existingNames.has(saved.name)) {
                        const isDynamic = DYNAMIC_PREFIXES.some(({ prefix, excludes }) => {
                            if (!saved.name.startsWith(prefix)) return false;
                            if (excludes.some(ep => saved.name.startsWith(ep))) return false;
                            return true;
                        });
                        if (isDynamic) {
                            this.addInput(saved.name, saved.type);
                            existingNames.add(saved.name);
                        }
                    }
                }

                // Step 2: Recreate trailing slots for linked groups
                for (const { prefix, type, excludes } of DYNAMIC_PREFIXES) {
                    let maxLinkedIdx = -1;
                    for (const saved of info.inputs) {
                        if (!saved.name.startsWith(prefix)) continue;
                        if (excludes.some(ep => saved.name.startsWith(ep))) continue;
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

            // Restore widget visibility after slot pre-creation
            // (Do NOT call updateDynamicSlots here — Steps 1/2 above already
            // pre-created the correct slots from saved info. updateDynamicSlots
            // would remove trailing slots before links are resolved by ComfyUI.)
            const self = this;
            function restoreVisibility(): void {
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

    // --- Context menu presets ---
    const origGetExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
    nodeType.prototype.getExtraMenuOptions = function (
        this: AgentNode,
        _: unknown,
        options: (ComfyMenuOption | null)[],
    ): void {
        origGetExtraMenuOptions?.apply(this, arguments as unknown as [unknown, ComfyMenuOption[]]);

        // Restore option
        if (this._previousPrompt) {
            options.unshift({
                content: "↩️ Restore Previous Prompt",
                callback: () => {
                    setPrompt(this, this._previousPrompt!, true, "#4a7a4a");
                },
            });
        }

        const presetItems = buildPresetMenu(this);

        // Utility items
        presetItems.push(
            // @ts-expect-error — null separator is valid in LiteGraph menus
            null,
            {
                content: "🎲 Random Example",
                callback: () => {
                    const randomPrompt = RANDOM_PROMPTS[Math.floor(Math.random() * RANDOM_PROMPTS.length)];
                    setPrompt(this, randomPrompt, true, "#8a4a8a");
                },
            },
            {
                content: "📋 Copy Prompt",
                callback: () => {
                    const promptWidget = this.widgets?.find((w: ComfyWidget) => w.name === "prompt");
                    const text = promptWidget?.value as string | undefined;
                    if (text && navigator.clipboard) {
                        navigator.clipboard.writeText(text)
                            .then(() => flashNode(this, "#4a7a4a"))
                            .catch(() => flashNode(this, "#7a4a4a"));
                    }
                },
            },
            {
                content: "📥 Paste (Append)",
                callback: () => handlePaste(this, false),
            },
            {
                content: "📥 Paste (Replace)",
                callback: () => handlePaste(this, true),
            },
            {
                content: "🗑️ Clear Prompt",
                callback: () => {
                    const promptWidget = this.widgets?.find((w: ComfyWidget) => w.name === "prompt");
                    if (promptWidget && promptWidget.value && String(promptWidget.value).trim() !== "") {
                        this._previousPrompt = String(promptWidget.value);
                        promptWidget.value = "";
                        this.setDirtyCanvas(true, true);
                        flashNode(this, "#7a3a3a");
                    }
                },
            },
        );

        options.unshift(
            {
                content: "FFMPEGA Presets",
                submenu: {
                    options: presetItems as ComfyMenuOption[],
                },
            },
            null,
        );
    };
}
