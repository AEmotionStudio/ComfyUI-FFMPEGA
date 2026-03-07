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
    { prefix: "audio_", type: "AUDIO", excludes: [] },
    { prefix: "video_", type: "STRING", excludes: ["video_path", "video_folder"] },
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

        // --- LLM model → custom_model / api_key visibility ---
        const llmWidget = this.widgets?.find((w: ComfyWidget) => w.name === "llm_model");
        if (llmWidget) {
            const customWidget = this.widgets?.find((w: ComfyWidget) => w.name === "custom_model");
            const apiKeyWidget = this.widgets?.find((w: ComfyWidget) => w.name === "api_key");
            const ollamaUrlWidget = this.widgets?.find((w: ComfyWidget) => w.name === "ollama_url");
            const verifyWidget = this.widgets?.find((w: ComfyWidget) => w.name === "verify_output");
            const visionWidget = this.widgets?.find((w: ComfyWidget) => w.name === "use_vision");
            const ptcWidget = this.widgets?.find((w: ComfyWidget) => w.name === "ptc_mode");

            function updateLlmVisibility(): void {
                const model = llmWidget!.value;
                const isNone = model === "none";
                toggleWidget(customWidget, model === "custom");
                toggleWidget(apiKeyWidget, needsApiKey(model));
                if (ollamaUrlWidget) toggleWidget(ollamaUrlWidget, !isNone);
                if (verifyWidget) toggleWidget(verifyWidget, !isNone);
                if (visionWidget) toggleWidget(visionWidget, !isNone);
                if (ptcWidget) toggleWidget(ptcWidget, !isNone);
                const noLlmModeWidget = node.widgets?.find((w: ComfyWidget) => w.name === "no_llm_mode");
                if (noLlmModeWidget) toggleWidget(noLlmModeWidget, isNone);
                fitHeight();
            }

            updateLlmVisibility();
            const origLlmCb = llmWidget.callback;
            llmWidget.callback = function (...args: unknown[]) {
                origLlmCb?.apply(this, args);
                updateLlmVisibility();
            };
        }

        // --- save_output → output_path visibility ---
        const saveWidget = this.widgets?.find((w: ComfyWidget) => w.name === "save_output");
        const outputPathWidget = this.widgets?.find((w: ComfyWidget) => w.name === "output_path");
        if (saveWidget && outputPathWidget) {
            function updateSaveVisibility(): void {
                toggleWidget(outputPathWidget, Boolean(saveWidget!.value));
                fitHeight();
            }

            updateSaveVisibility();
            const origSaveCb = saveWidget.callback;
            saveWidget.callback = function (...args: unknown[]) {
                origSaveCb?.apply(this, args);
                updateSaveVisibility();
            };
        }

        // --- advanced_options toggle → all advanced widgets visibility ---
        const advancedWidget = this.widgets?.find((w: ComfyWidget) => w.name === "advanced_options");
        const previewWidget = this.widgets?.find((w: ComfyWidget) => w.name === "preview_mode");
        const crfWidget = this.widgets?.find((w: ComfyWidget) => w.name === "crf");
        const encodingWidget = this.widgets?.find((w: ComfyWidget) => w.name === "encoding_preset");
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
        const mmaudioModeWidget = this.widgets?.find((w: ComfyWidget) => w.name === "mmaudio_mode");

        function updateAdvancedVisibility(): void {
            const show = Boolean(advancedWidget?.value);
            if (previewWidget) toggleWidget(previewWidget, show);
            if (subtitleWidget) toggleWidget(subtitleWidget, show);
            if (crfWidget) toggleWidget(crfWidget, show);
            if (encodingWidget) toggleWidget(encodingWidget, show);
            if (whisperDevWidget) toggleWidget(whisperDevWidget, show);
            if (whisperModelWidget) toggleWidget(whisperModelWidget, show);
            if (sam3MaxObjWidget) toggleWidget(sam3MaxObjWidget, show);
            if (sam3ThreshWidget) toggleWidget(sam3ThreshWidget, show);
            if (maskTypeWidget) toggleWidget(maskTypeWidget, show);
            if (fluxSmoothingWidget) toggleWidget(fluxSmoothingWidget, show);
            if (mmaudioModeWidget) toggleWidget(mmaudioModeWidget, show);
            if (batchWidget) toggleWidget(batchWidget, show);
            const showBatch = show && Boolean(batchWidget?.value);
            if (folderWidget) toggleWidget(folderWidget, showBatch);
            if (patternWidget) toggleWidget(patternWidget, showBatch);
            if (concurrentWidget) toggleWidget(concurrentWidget, showBatch);
            if (trackTokensWidget) toggleWidget(trackTokensWidget, show);
            if (logUsageWidget) toggleWidget(logUsageWidget, show);
            if (allowDownloadsWidget) toggleWidget(allowDownloadsWidget, show);
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

        // --- batch_mode → sub-widget visibility ---
        if (batchWidget) {
            function updateBatchVisibility(): void {
                const showAdvanced = Boolean(advancedWidget?.value ?? true);
                const show = Boolean(batchWidget!.value) && showAdvanced;
                if (folderWidget) toggleWidget(folderWidget, show);
                if (patternWidget) toggleWidget(patternWidget, show);
                if (concurrentWidget) toggleWidget(concurrentWidget, show);
                fitHeight();
            }

            updateBatchVisibility();
            const origBatchCb = batchWidget.callback;
            batchWidget.callback = function (...args: unknown[]) {
                origBatchCb?.apply(this, args);
                updateBatchVisibility();
            };
        }

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

            // Deferred slot restoration
            const self = this;
            function restoreSlots(): void {
                updateDynamicSlots(self, "images_", "IMAGE", []);
                updateDynamicSlots(self, "image_", "IMAGE", ["images_", "image_path_"]);
                updateDynamicSlots(self, "audio_", "AUDIO", []);
                updateDynamicSlots(self, "video_", "STRING", ["video_path", "video_folder"]);
                updateDynamicSlots(self, "image_path_", "STRING", []);
                updateDynamicSlots(self, "text_", "STRING", []);
                updateAdvancedVisibility();
                fitHeight();
            }

            restoreSlots();
            setTimeout(restoreSlots, 0);
            setTimeout(restoreSlots, 300);
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
