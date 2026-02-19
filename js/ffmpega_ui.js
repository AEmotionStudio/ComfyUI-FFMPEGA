/**
 * FFMPEGA Custom UI Widgets for ComfyUI
 *
 * Provides enhanced UI elements for the FFMPEG Agent nodes.
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Collection of example prompts for the "Random Example" feature
const RANDOM_PROMPTS = [
    "Make it cinematic with a fade in and vignette",
    "Apply VHS effect, slow it down to 0.75x, add echo",
    "Horror style, reverse the video, add fade out",
    "Trim to first 15 seconds, make it vertical for TikTok, add text 'Follow me!' at the bottom",
    "Apply edge detection with colorful mode, boost saturation",
    "Normalize audio, compress for web, resize to 1080p",
    "Lofi style, slow down to 0.8x, muffle the audio",
    "Anime look, add text 'Episode 1' at the top",
    "Make it look like underwater footage with echo on the audio",
    "Day for night effect, add vignette, reduce noise",
    "Pixelate it, posterize with 3 levels, speed up 1.5x",
    "Cyberpunk style with strong sharpening and neon glow",
    "Surveillance look, add text 'CAM 01' in top left, resize to 720p",
    "Noir style, add fade in, slow zoom",
    "Speed up 4x, apply dreamy effect, add fade in and out",
    "Show audio waveform at the bottom with cyan color",
    "Arrange these images in a 3-column grid with gaps",
    "Create a slideshow with 4 seconds per image and fade transitions",
    "Overlay the logo image in the bottom-right corner at 20% scale",
    "Add a typewriter text 'Coming Soon' with scrolling credits",
    "Apply tilt-shift miniature effect and boost saturation",
    "Extract a thumbnail at the 5 second mark",
    "Add a news ticker that says 'Breaking News' at the bottom",
    "Cross dissolve transition between both clips with 1 second overlap",
    "Blur a face region for privacy and normalize loudness",
    "Apply datamosh glitch art effect with film grain overlay",
    "Create a sprite sheet preview of the video",
    "Replace the audio with the connected audio track",
    "Add a lower third with name 'John Smith' and title 'Director'",
    "Apply golden hour warm glow with a slow Ken Burns zoom"
];

// --- Color utility ---
// Returns black or white depending on background luminance for readable text
function _contrastColor(hex) {
    const c = hex.replace("#", "");
    const r = parseInt(c.substring(0, 2), 16);
    const g = parseInt(c.substring(2, 4), 16);
    const b = parseInt(c.substring(4, 6), 16);
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    return luminance > 0.5 ? "#000000" : "#FFFFFF";
}

// --- Dynamic input slot management ---
// When you connect image_a, image_b appears. Connect image_b → image_c appears, etc.
// Same for audio_a, audio_b, audio_c, ...
const SLOT_LABELS = "abcdefghijklmnopqrstuvwxyz";

function updateDynamicSlots(node, prefix, slotType, excludePrefix) {
    // Find all slots matching this prefix (but not excludePrefix)
    // excludePrefix can be a string or array of strings
    const excludes = excludePrefix ? (Array.isArray(excludePrefix) ? excludePrefix : [excludePrefix]) : [];
    const matchingIndices = [];
    for (let i = 0; i < node.inputs.length; i++) {
        const name = node.inputs[i].name;
        if (name.startsWith(prefix)) {
            if (excludes.some(ep => name.startsWith(ep))) continue;
            matchingIndices.push(i);
        }
    }

    if (matchingIndices.length === 0) return;

    // Find the last connected slot in this group
    let lastConnectedGroupIdx = -1;
    for (let g = matchingIndices.length - 1; g >= 0; g--) {
        const slotIdx = matchingIndices[g];
        if (node.inputs[slotIdx].link != null) {
            lastConnectedGroupIdx = g;
            break;
        }
    }

    // We want exactly (lastConnectedGroupIdx + 2) slots total for this group
    // i.e. all connected slots + one empty slot after the last connected one
    const needed = lastConnectedGroupIdx + 2;

    // Add slots if we need more
    while (matchingIndices.length < needed) {
        const letter = SLOT_LABELS[matchingIndices.length];
        if (!letter) break; // safety: max 26 slots
        const newName = `${prefix}${letter}`;
        node.addInput(newName, slotType);
        matchingIndices.push(node.inputs.length - 1);
    }

    // Remove trailing empty slots if we have too many
    // (iterate from the end, remove only if unconnected and beyond needed count)
    while (matchingIndices.length > needed && matchingIndices.length > 1) {
        const lastGroupIdx = matchingIndices.length - 1;
        const slotIdx = matchingIndices[lastGroupIdx];
        if (node.inputs[slotIdx].link != null) break; // connected, stop
        node.removeInput(slotIdx);
        matchingIndices.pop();
    }
}

/**
 * Helper function to handle clipboard paste
 * @param {object} node - The node instance
 * @param {boolean} replace - If true, replaces content (with confirm). If false, appends.
 */
function handlePaste(node, replace) {
    if (navigator.clipboard && navigator.clipboard.readText) {
        navigator.clipboard.readText()
            .then(text => {
                if (text) {
                    // Paste with blue feedback
                    setPrompt(node, text, replace, "#4a6a8a");
                }
            })
            .catch(err => {
                console.error("Failed to read clipboard", err);
                flashNode(node, "#7a4a4a");
            });
    } else {
        flashNode(node, "#7a4a4a");
    }
}

/**
 * Helper function to set prompt text on a node
 * @param {object} node - The node instance
 * @param {string} text - The text to set or append
 * @param {boolean} replace - If true, replaces the existing text. If false, appends.
 */
function setPrompt(node, text, replace = false, color = "#4a5a7a") {
    const promptWidget = node.widgets?.find(w => w.name === "prompt");
    if (promptWidget) {
        if (replace) {
            // Save history if replacing non-empty text
            if (promptWidget.value && promptWidget.value.trim() !== "") {
                node._previousPrompt = promptWidget.value;
            }
            promptWidget.value = text;
        } else {
            const currentText = promptWidget.value;
            // If prompt is empty, just set it
            if (!currentText || currentText.trim() === "") {
                promptWidget.value = text;
            }
            // If not empty, append if not already present
            else if (!currentText.includes(text)) {
                promptWidget.value = currentText.trim() + " and " + text;
            }
        }
        node.setDirtyCanvas(true, true);
        flashNode(node, color);
    }
}

/**
 * Visual feedback helper - flashes the node background
 * @param {object} node - The node instance
 * @param {string} color - The flash color (default: lighter blue-grey)
 */
function flashNode(node, color = "#4a5a7a") {
    if (!node || node._isFlashing) return;

    node._isFlashing = true;
    const originalBg = node.bgcolor;

    // Flash color
    node.bgcolor = color;
    node.setDirtyCanvas(true, true);

    setTimeout(() => {
        // Restore only if it hasn't been changed again externally (unlikely but safe)
        if (node.bgcolor === color) {
            node.bgcolor = originalBg;
        }
        node._isFlashing = false;
        node.setDirtyCanvas(true, true);
    }, 350);
}

/**
 * Adds video preview context menu options to a node.
 * Shared between LoadVideoPath and SaveVideo nodes.
 * @param {object} node - The node instance
 * @param {HTMLVideoElement} videoEl - The <video> element
 * @param {HTMLElement} previewContainer - The preview container div
 * @param {HTMLElement} previewWidget - The preview widget
 * @param {Function} getVideoUrl - Returns the current video URL string (or null)
 */
function addVideoPreviewMenu(node, videoEl, previewContainer, previewWidget, getVideoUrl) {
    const origGetExtraMenuOptions = node.constructor.prototype._ffmpegaOrigGetExtraMenu;
    const currentGetExtra = node.getExtraMenuOptions;

    node.getExtraMenuOptions = function (_, options) {
        currentGetExtra?.apply(this, arguments);

        const optNew = [];
        const url = getVideoUrl();
        const hasVideo = !!url && previewContainer.style.display !== "none";

        // --- Sync Preview ---
        optNew.push({
            content: "🔄 Sync Preview",
            callback: () => {
                for (const container of document.getElementsByClassName("ffmpega_preview")) {
                    for (const child of container.children) {
                        if (child.tagName === "VIDEO" && child.src) {
                            child.currentTime = 0;
                            child.play().catch(() => { });
                        }
                    }
                }
                flashNode(node, "#4a6a5a");
            }
        });

        if (hasVideo) {
            // --- Open Preview ---
            optNew.push({
                content: "🔗 Open Preview",
                callback: () => window.open(url, "_blank")
            });

            // --- Save Preview ---
            optNew.push({
                content: "💾 Save Preview",
                callback: () => {
                    const a = document.createElement("a");
                    a.href = url;
                    // Extract filename from URL params or use default
                    try {
                        const params = new URL(a.href, location.origin).searchParams;
                        a.setAttribute("download", params.get("filename") || "preview.mp4");
                    } catch {
                        a.setAttribute("download", "preview.mp4");
                    }
                    document.body.append(a);
                    a.click();
                    requestAnimationFrame(() => a.remove());
                }
            });
        }

        // --- Pause / Resume ---
        if (hasVideo) {
            const isPaused = videoEl.paused;
            optNew.push({
                content: isPaused ? "▶️ Resume Preview" : "⏸️ Pause Preview",
                callback: () => {
                    if (videoEl.paused) {
                        videoEl.play().catch(() => { });
                    } else {
                        videoEl.pause();
                    }
                }
            });
        }

        // --- Show / Hide ---
        const isHidden = previewContainer.style.display === "none";
        optNew.push({
            content: isHidden ? "👁️ Show Preview" : "🙈 Hide Preview",
            callback: () => {
                if (previewContainer.style.display === "none") {
                    previewContainer.style.display = "";
                    if (!videoEl.paused) videoEl.play().catch(() => { });
                } else {
                    videoEl.pause();
                    previewContainer.style.display = "none";
                }
                node.setSize([
                    node.size[0],
                    node.computeSize([node.size[0], node.size[1]])[1],
                ]);
                node?.graph?.setDirtyCanvas(true);
            }
        });

        // --- Mute / Unmute ---
        if (hasVideo) {
            optNew.push({
                content: videoEl.muted ? "🔊 Unmute Preview" : "🔇 Mute Preview",
                callback: () => {
                    videoEl.muted = !videoEl.muted;
                }
            });
        }

        // --- Copy Video Path ---
        if (hasVideo) {
            optNew.push({
                content: "📋 Copy Video Path",
                callback: async () => {
                    try {
                        const params = new URL(url, location.origin).searchParams;
                        const filename = params.get("filename") || url;
                        await navigator.clipboard.writeText(filename);
                        flashNode(node, "#4a7a4a");
                    } catch {
                        flashNode(node, "#7a4a4a");
                    }
                }
            });
        }

        // --- Separator before extras ---
        if (optNew.length > 0) optNew.push(null);

        // --- Playback Speed ---
        if (hasVideo) {
            optNew.push({
                content: "⏱️ Playback Speed",
                submenu: {
                    options: [
                        { content: "0.25x", callback: () => { videoEl.playbackRate = 0.25; flashNode(node, "#5a5a3a"); } },
                        { content: "0.5x", callback: () => { videoEl.playbackRate = 0.5; flashNode(node, "#5a5a3a"); } },
                        { content: "1x (Normal)", callback: () => { videoEl.playbackRate = 1.0; flashNode(node, "#5a5a3a"); } },
                        { content: "1.5x", callback: () => { videoEl.playbackRate = 1.5; flashNode(node, "#5a5a3a"); } },
                        { content: "2x", callback: () => { videoEl.playbackRate = 2.0; flashNode(node, "#5a5a3a"); } },
                    ]
                }
            });
        }

        // --- Loop On/Off ---
        if (hasVideo) {
            optNew.push({
                content: videoEl.loop ? "🔁 Loop: ON (click to disable)" : "➡️ Loop: OFF (click to enable)",
                callback: () => {
                    videoEl.loop = !videoEl.loop;
                    flashNode(node, "#5a5a3a");
                }
            });
        }

        // --- Screenshot Frame ---
        if (hasVideo && videoEl.videoWidth) {
            optNew.push({
                content: "📸 Screenshot Frame",
                callback: async () => {
                    try {
                        const canvas = document.createElement("canvas");
                        canvas.width = videoEl.videoWidth;
                        canvas.height = videoEl.videoHeight;
                        canvas.getContext("2d").drawImage(videoEl, 0, 0);
                        const blob = await new Promise(r => canvas.toBlob(r, "image/png"));
                        if (blob && navigator.clipboard?.write) {
                            await navigator.clipboard.write([
                                new ClipboardItem({ "image/png": blob })
                            ]);
                            flashNode(node, "#4a7a4a");
                        } else {
                            // Fallback: download as file
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement("a");
                            a.href = url;
                            a.download = "screenshot.png";
                            a.click();
                            URL.revokeObjectURL(url);
                            flashNode(node, "#4a7a4a");
                        }
                    } catch {
                        flashNode(node, "#7a4a4a");
                    }
                }
            });
        }

        // Prepend our options with a separator from existing options
        if (options.length > 0 && options[0] != null && optNew.length > 0) {
            optNew.push(null);
        }
        options.unshift(...optNew);
    };
}

// Register FFMPEGA extensions
app.registerExtension({
    name: "FFMPEGA.UI",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        // Enhanced prompt input for FFMPEGAgent node
        if (nodeData.name === "FFMPEGAgent") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;

            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated?.apply(this, arguments);

                // Style the node
                this.color = "#2a3a5a";
                this.bgcolor = "#1a2a4a";

                // --- Dynamic widget visibility ---
                // Uses the standard LiteGraph widget hiding pattern (VHS-style):
                // hidden widgets get computeSize → [0, -4] so they collapse
                // entirely and the node resizes cleanly.
                const node = this;

                // Reusable show/hide for any widget
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

                function fitHeight() {
                    node.setSize([
                        node.size[0],
                        node.computeSize([node.size[0], node.size[1]])[1]
                    ]);
                    node?.graph?.setDirtyCanvas(true);
                }

                // --- LLM model → custom_model / api_key visibility ---
                const llmWidget = this.widgets?.find(w => w.name === "llm_model");
                if (llmWidget) {
                    const customWidget = this.widgets?.find(w => w.name === "custom_model");
                    const apiKeyWidget = this.widgets?.find(w => w.name === "api_key");

                    function needsApiKey(model) {
                        if (!model) return false;
                        // CLI-based models use their own auth — no api_key needed
                        if (model === "gemini-cli" || model === "claude-cli" || model === "cursor-agent" || model === "qwen-cli") return false;
                        return model.startsWith("gpt") ||
                            model.startsWith("claude") ||
                            model.startsWith("gemini") ||
                            model === "custom";
                    }

                    function updateLlmVisibility() {
                        const model = llmWidget.value;
                        toggleWidget(customWidget, model === "custom");
                        toggleWidget(apiKeyWidget, needsApiKey(model));
                        fitHeight();
                    }

                    updateLlmVisibility();
                    const origLlmCb = llmWidget.callback;
                    llmWidget.callback = function (...args) {
                        origLlmCb?.apply(this, args);
                        updateLlmVisibility();
                    };
                }

                // --- save_output → output_path visibility ---
                const saveWidget = this.widgets?.find(w => w.name === "save_output");
                const outputPathWidget = this.widgets?.find(w => w.name === "output_path");
                if (saveWidget && outputPathWidget) {
                    function updateSaveVisibility() {
                        toggleWidget(outputPathWidget, saveWidget.value);
                        fitHeight();
                    }

                    updateSaveVisibility();
                    const origSaveCb = saveWidget.callback;
                    saveWidget.callback = function (...args) {
                        origSaveCb?.apply(this, args);
                        updateSaveVisibility();
                    };
                }

                // --- batch_mode → video_folder / file_pattern / max_concurrent visibility ---
                const batchWidget = this.widgets?.find(w => w.name === "batch_mode");
                const folderWidget = this.widgets?.find(w => w.name === "video_folder");
                const patternWidget = this.widgets?.find(w => w.name === "file_pattern");
                const concurrentWidget = this.widgets?.find(w => w.name === "max_concurrent");
                if (batchWidget) {
                    function updateBatchVisibility() {
                        const show = batchWidget.value;
                        if (folderWidget) toggleWidget(folderWidget, show);
                        if (patternWidget) toggleWidget(patternWidget, show);
                        if (concurrentWidget) toggleWidget(concurrentWidget, show);
                        fitHeight();
                    }

                    updateBatchVisibility();
                    const origBatchCb = batchWidget.callback;
                    batchWidget.callback = function (...args) {
                        origBatchCb?.apply(this, args);
                        updateBatchVisibility();
                    };
                }

                // --- Dynamic input slots (auto-expand) ---
                // Connect image_a → image_b appears. Connect image_b → image_c appears.
                // Same for audio_a → audio_b → audio_c, video_a → video_b, etc.
                const origOnConnectionsChange = this.onConnectionsChange;
                this.onConnectionsChange = function (type, slotIndex, isConnected, link, ioSlot) {
                    origOnConnectionsChange?.apply(this, arguments);
                    if (type === LiteGraph.INPUT) {
                        updateDynamicSlots(this, "images_", "IMAGE");
                        updateDynamicSlots(this, "image_", "IMAGE", ["images_", "image_path_"]);
                        updateDynamicSlots(this, "audio_", "AUDIO");
                        updateDynamicSlots(this, "video_", "STRING");
                        updateDynamicSlots(this, "image_path_", "STRING");
                        updateDynamicSlots(this, "text_", "STRING");
                        fitHeight();
                    }
                };

                // --- Restore dynamic slots on workflow load / page refresh ---
                // onConfigure fires when the node is deserialized from a saved
                // workflow.  onConnectionsChange does NOT fire for pre-existing
                // links, so without this the "next empty" slot (e.g. video_b)
                // would be missing until the user manually reconnects.
                const origOnConfigure = this.onConfigure;
                this.onConfigure = function (info) {
                    origOnConfigure?.apply(this, arguments);
                    // Defer until links are fully restored by LiteGraph
                    requestAnimationFrame(() => {
                        updateDynamicSlots(this, "images_", "IMAGE");
                        updateDynamicSlots(this, "image_", "IMAGE", ["images_", "image_path_"]);
                        updateDynamicSlots(this, "audio_", "AUDIO");
                        updateDynamicSlots(this, "video_", "STRING");
                        updateDynamicSlots(this, "image_path_", "STRING");
                        updateDynamicSlots(this, "text_", "STRING");
                        fitHeight();
                    });
                };

                return result;
            };

            // Add context menu presets
            const origGetExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
            nodeType.prototype.getExtraMenuOptions = function (_, options) {
                origGetExtraMenuOptions?.apply(this, arguments);

                // Add Restore option if history exists
                if (this._previousPrompt) {
                    options.unshift({
                        content: "↩️ Restore Previous Prompt",
                        callback: () => {
                            // Restore and swap (toggle)
                            setPrompt(this, this._previousPrompt, true, "#4a7a4a");
                        }
                    });
                }

                options.unshift(
                    {
                        content: "FFMPEGA Presets",
                        submenu: {
                            options: [
                                {
                                    content: "🎬 Cinematic & Style",
                                    submenu: {
                                        options: [
                                            { content: "Cinematic Letterbox", callback: () => setPrompt(this, "Apply cinematic letterbox and color grading") },
                                            { content: "Blockbuster", callback: () => setPrompt(this, "Apply blockbuster style with high contrast and dramatic grading") },
                                            { content: "Film Noir", callback: () => setPrompt(this, "Black and white film noir style with high contrast") },
                                            { content: "Dreamy / Soft Glow", callback: () => setPrompt(this, "Apply a dreamy soft glow effect") },
                                            { content: "HDR Look", callback: () => setPrompt(this, "Apply an HDR-style look with vivid colors and detail") },
                                            { content: "Teal & Orange", callback: () => setPrompt(this, "Apply teal and orange color grading") },
                                            { content: "Documentary", callback: () => setPrompt(this, "Apply a clean natural documentary look") },
                                            { content: "Indie Film", callback: () => setPrompt(this, "Apply an indie art-house look with faded colors") },
                                            { content: "Sci-Fi", callback: () => setPrompt(this, "Apply a cool blue sci-fi atmosphere") },
                                            { content: "Dark / Moody", callback: () => setPrompt(this, "Apply a dark atmospheric moody look") },
                                            { content: "Romantic", callback: () => setPrompt(this, "Apply a soft warm romantic mood") },
                                            { content: "Action", callback: () => setPrompt(this, "Apply fast-paced action movie grading with high contrast") }
                                        ]
                                    }
                                },
                                {
                                    content: "📼 Vintage & Retro",
                                    submenu: {
                                        options: [
                                            { content: "Vintage Film", callback: () => setPrompt(this, "Create a vintage film look with grain") },
                                            { content: "VHS Effect", callback: () => setPrompt(this, "Apply a VHS tape effect with tracking lines and distortion") },
                                            { content: "Sepia Tone", callback: () => setPrompt(this, "Apply a warm sepia tone effect") },
                                            { content: "Super 8mm Film", callback: () => setPrompt(this, "Apply a Super 8mm film look with jitter and grain") },
                                            { content: "Old TV / CRT", callback: () => setPrompt(this, "Apply an old CRT television look with scanlines") },
                                            { content: "Polaroid Look", callback: () => setPrompt(this, "Apply a polaroid photo style color treatment") },
                                            { content: "Faded / Washed Out", callback: () => setPrompt(this, "Apply a faded washed-out film look") },
                                            { content: "Damaged Film", callback: () => setPrompt(this, "Apply a damaged film effect with scratches and flicker") },
                                            { content: "Lo-Fi Chill", callback: () => setPrompt(this, "Apply a lo-fi chill aesthetic with muted tones") }
                                        ]
                                    }
                                },
                                {
                                    content: "🎨 Color & Look",
                                    submenu: {
                                        options: [
                                            { content: "Grayscale", callback: () => setPrompt(this, "Convert to black and white grayscale") },
                                            { content: "Boost Saturation", callback: () => setPrompt(this, "Increase color saturation for more vivid colors") },
                                            { content: "Desaturate", callback: () => setPrompt(this, "Desaturate colors for a muted look") },
                                            { content: "Invert Colors", callback: () => setPrompt(this, "Invert all colors to create a negative image") },
                                            { content: "Sharpen", callback: () => setPrompt(this, "Sharpen the video to enhance detail and clarity") },
                                            { content: "Unsharp Mask", callback: () => setPrompt(this, "Apply unsharp mask for fine-grained luma/chroma sharpening") },
                                            { content: "Blur / Soften", callback: () => setPrompt(this, "Apply a soft gaussian blur effect") },
                                            { content: "Vignette", callback: () => setPrompt(this, "Add a dark vignette around the edges") },
                                            { content: "Deband", callback: () => setPrompt(this, "Remove color banding artifacts") },
                                            { content: "White Balance", callback: () => setPrompt(this, "Adjust white balance to 5500K for natural daylight") },
                                            { content: "Shadows & Highlights", callback: () => setPrompt(this, "Brighten shadows and tame highlights for balanced exposure") },
                                            { content: "Split Tone", callback: () => setPrompt(this, "Apply split toning — warm highlights, cool shadows") },
                                            { content: "Deflicker", callback: () => setPrompt(this, "Remove fluorescent or timelapse flicker") },
                                            { content: "Color Match", callback: () => setPrompt(this, "Auto equalize histogram for consistent color") },
                                            { content: "Apply LUT", callback: () => setPrompt(this, "Apply a 3D LUT color grade from file") }
                                        ]
                                    }
                                },
                                {
                                    content: "✨ Creative Effects",
                                    submenu: {
                                        options: [
                                            { content: "Neon Glow", callback: () => setPrompt(this, "Apply a neon glow effect with vibrant edges") },
                                            { content: "Cyberpunk", callback: () => setPrompt(this, "Apply cyberpunk look with neon tones and high contrast") },
                                            { content: "Underwater", callback: () => setPrompt(this, "Apply an underwater look with blue tint and blur") },
                                            { content: "Sunset / Golden Hour", callback: () => setPrompt(this, "Apply a golden hour warm glow effect") },
                                            { content: "Comic Book", callback: () => setPrompt(this, "Apply bold comic book / pop art style") },
                                            { content: "Miniature / Tilt-Shift", callback: () => setPrompt(this, "Apply tilt-shift miniature toy model effect") },
                                            { content: "Thermal Vision", callback: () => setPrompt(this, "Apply thermal / heat vision camera effect") },
                                            { content: "Anime / Cel-Shaded", callback: () => setPrompt(this, "Apply anime cel-shaded cartoon look") },
                                            { content: "Surveillance / CCTV", callback: () => setPrompt(this, "Apply security camera CCTV look") },
                                            { content: "Datamosh / Glitch Art", callback: () => setPrompt(this, "Apply datamosh glitch art effect") },
                                            { content: "Radial Blur", callback: () => setPrompt(this, "Apply a radial zoom blur effect") },
                                            { content: "Film Grain Overlay", callback: () => setPrompt(this, "Add cinematic film grain overlay with intensity control") },
                                            { content: "Posterize", callback: () => setPrompt(this, "Reduce color palette for screen-print poster effect") },
                                            { content: "Emboss", callback: () => setPrompt(this, "Apply an emboss relief surface effect") },
                                            { content: "Pixelate / 8-Bit", callback: () => setPrompt(this, "Pixelate into an 8-bit retro game look") },
                                            { content: "Day for Night", callback: () => setPrompt(this, "Simulate nighttime from daytime footage") },
                                            { content: "Horror", callback: () => setPrompt(this, "Apply dark desaturated horror atmosphere with grain") },
                                            { content: "Music Video", callback: () => setPrompt(this, "Apply punchy music video look with contrast and vignette") }
                                        ]
                                    }
                                },
                                {
                                    content: "✏️ Text & Graphics",
                                    submenu: {
                                        options: [
                                            { content: "Text Overlay", callback: () => setPrompt(this, "Add text overlay that says 'Hello World' in the center") },
                                            { content: "Animated Text", callback: () => setPrompt(this, "Add animated text that says 'Welcome' with a fade-in effect") },
                                            { content: "Scrolling Credits", callback: () => setPrompt(this, "Add scrolling credits text that moves upward") },
                                            { content: "News Ticker", callback: () => setPrompt(this, "Add a scrolling news-style ticker bar at the bottom") },
                                            { content: "Lower Third", callback: () => setPrompt(this, "Add a professional broadcast lower third with name and title") },
                                            { content: "Countdown Timer", callback: () => setPrompt(this, "Add a 10-second countdown timer overlay") },
                                            { content: "Typewriter Text", callback: () => setPrompt(this, "Add typewriter reveal text effect") },
                                            { content: "Bounce Text", callback: () => setPrompt(this, "Add bouncing animated text at the top") },
                                            { content: "Fade Text", callback: () => setPrompt(this, "Add text that fades in and out") },
                                            { content: "Karaoke Text", callback: () => setPrompt(this, "Add karaoke-style progressively filled text") },
                                            { content: "Watermark", callback: () => setPrompt(this, "Add a semi-transparent watermark in the bottom-right corner") },
                                            { content: "Burn Subtitles", callback: () => setPrompt(this, "Burn subtitles from SRT file into the video") }
                                        ]
                                    }
                                },
                                {
                                    content: "✂️ Editing & Delivery",
                                    submenu: {
                                        options: [
                                            { content: "Picture-in-Picture", callback: () => setPrompt(this, "Create a picture-in-picture layout with small video in corner") },
                                            { content: "Blend Two Videos", callback: () => setPrompt(this, "Blend two video inputs with 50% opacity") },
                                            { content: "Mask Blur (Privacy)", callback: () => setPrompt(this, "Blur a rectangular region for privacy") },
                                            { content: "Remove Logo", callback: () => setPrompt(this, "Remove a logo from the top-right region") },
                                            { content: "Remove Duplicates", callback: () => setPrompt(this, "Strip duplicate stuttered frames") },
                                            { content: "Jump Cut", callback: () => setPrompt(this, "Auto-cut to high-energy moments every 2 seconds") },
                                            { content: "Beat Sync", callback: () => setPrompt(this, "Sync cuts to a beat interval") },
                                            { content: "Extract Frames", callback: () => setPrompt(this, "Export frames as image sequence at 1 fps") },
                                            { content: "Thumbnail", callback: () => setPrompt(this, "Extract the best representative thumbnail frame") },
                                            { content: "Sprite Sheet", callback: () => setPrompt(this, "Create a 5x5 sprite sheet contact preview of the video") },
                                            { content: "Chroma Key (Green Screen)", callback: () => setPrompt(this, "Remove the green screen background using chroma key") },
                                            { content: "Mirror / Flip", callback: () => setPrompt(this, "Mirror the video horizontally") }
                                        ]
                                    }
                                },
                                {
                                    content: "🔀 Transitions & Reveals",
                                    submenu: {
                                        options: [
                                            { content: "Fade In from Black", callback: () => setPrompt(this, "Add a fade-in from black at the beginning") },
                                            { content: "Fade Out to Black", callback: () => setPrompt(this, "Add a fade-out to black at the end") },
                                            { content: "Fade to White", callback: () => setPrompt(this, "Add a fade to white transition") },
                                            { content: "Flash Effect", callback: () => setPrompt(this, "Add a bright flash transition at the midpoint") },
                                            { content: "Cross Dissolve (xfade)", callback: () => setPrompt(this, "Add a cross dissolve transition between clips") },
                                            { content: "Wipe Reveal", callback: () => setPrompt(this, "Add a directional wipe reveal from the left") },
                                            { content: "Iris Reveal", callback: () => setPrompt(this, "Add a circle expanding iris reveal from center") },
                                            { content: "Slide In", callback: () => setPrompt(this, "Slide the video in from the left edge") }
                                        ]
                                    }
                                },
                                {
                                    content: "🌀 Motion & Animation",
                                    submenu: {
                                        options: [
                                            { content: "Ken Burns Zoom", callback: () => setPrompt(this, "Apply a slow Ken Burns zoom-in effect") },
                                            { content: "Slow Zoom", callback: () => setPrompt(this, "Apply a slow push-in zoom over the duration") },
                                            { content: "Spin / Rotate", callback: () => setPrompt(this, "Slowly rotate the video continuously") },
                                            { content: "Camera Shake", callback: () => setPrompt(this, "Add a subtle camera shake effect") },
                                            { content: "Pulse / Breathe", callback: () => setPrompt(this, "Add a rhythmic zoom pulse effect") },
                                            { content: "Drift / Pan", callback: () => setPrompt(this, "Add a slow horizontal drift pan") },
                                            { content: "Bounce", callback: () => setPrompt(this, "Add a bouncing animation effect") },
                                            { content: "Animated Overlay", callback: () => setPrompt(this, "Add a moving image overlay with scroll motion") }
                                        ]
                                    }
                                },
                                {
                                    content: "📱 Format & Social",
                                    submenu: {
                                        options: [
                                            { content: "TikTok / Reels (9:16)", callback: () => setPrompt(this, "Crop to vertical 9:16 for TikTok/Reels") },
                                            { content: "Instagram Square (1:1)", callback: () => setPrompt(this, "Crop to square 1:1 format") },
                                            { content: "YouTube Optimize", callback: () => setPrompt(this, "Optimize for YouTube at 1080p with good compression") },
                                            { content: "Twitter / X Optimize", callback: () => setPrompt(this, "Optimize for Twitter/X with size limits") },
                                            { content: "Convert to GIF", callback: () => setPrompt(this, "Convert to an animated GIF") },
                                            { content: "Add Caption Space", callback: () => setPrompt(this, "Add blank space below the video for captions") },
                                            { content: "Compress for Web", callback: () => setPrompt(this, "Compress for web delivery, optimize file size") },
                                            { content: "Intro / Outro", callback: () => setPrompt(this, "Add intro and outro segments to the video") }
                                        ]
                                    }
                                },
                                {
                                    content: "⏱️ Time & Speed",
                                    submenu: {
                                        options: [
                                            { content: "Slow Motion (0.5x)", callback: () => setPrompt(this, "Create smooth slow motion at 0.5x speed") },
                                            { content: "Speed Up (2x)", callback: () => setPrompt(this, "Speed up the video 2x while keeping audio pitch") },
                                            { content: "Speed Up (4x)", callback: () => setPrompt(this, "Speed up the video 4x for time-lapse effect") },
                                            { content: "Reverse", callback: () => setPrompt(this, "Play the video in reverse") },
                                            { content: "Loop (3x)", callback: () => setPrompt(this, "Loop the video 3 times seamlessly") },
                                            { content: "Trim First 5 Seconds", callback: () => setPrompt(this, "Trim the first 5 seconds of the video") },
                                            { content: "Freeze Frame", callback: () => setPrompt(this, "Freeze a frame at the 3 second mark for 2 seconds") },
                                            { content: "Time Remap / Speed Ramp", callback: () => setPrompt(this, "Gradually ramp speed from 1x to 2x") },
                                            { content: "Scene Detect", callback: () => setPrompt(this, "Auto-detect scene changes") },
                                            { content: "Frame Rate Interpolation", callback: () => setPrompt(this, "Interpolate frame rate to smooth 60fps") }
                                        ]
                                    }
                                },
                                {
                                    content: "🔊 Audio",
                                    submenu: {
                                        options: [
                                            { content: "Remove Audio", callback: () => setPrompt(this, "Remove all audio tracks") },
                                            { content: "Boost Volume", callback: () => setPrompt(this, "Increase audio volume") },
                                            { content: "Normalize Audio", callback: () => setPrompt(this, "Normalize audio levels to consistent volume") },
                                            { content: "Normalize Loudness (EBU R128)", callback: () => setPrompt(this, "Normalize loudness to broadcast standard EBU R128") },
                                            { content: "Noise Reduction", callback: () => setPrompt(this, "Apply noise reduction to clean up the audio") },
                                            { content: "De-Reverb", callback: () => setPrompt(this, "Remove room echo and reverb from audio") },
                                            { content: "Fade Audio In/Out", callback: () => setPrompt(this, "Add audio fade-in at start and fade-out at end") },
                                            { content: "Audio Crossfade", callback: () => setPrompt(this, "Smooth crossfade between two audio tracks") },
                                            { content: "Extract Audio Only", callback: () => setPrompt(this, "Extract only the audio track as a separate output") },
                                            { content: "Replace Audio", callback: () => setPrompt(this, "Replace the video's audio with connected audio input") },
                                            { content: "Split Audio (L/R)", callback: () => setPrompt(this, "Extract just the left channel of audio") },
                                            { content: "Bass Boost", callback: () => setPrompt(this, "Boost bass frequencies for more punch") },
                                            { content: "Add Echo / Reverb", callback: () => setPrompt(this, "Add echo and reverb effect to audio") },
                                            { content: "Dynamic Compression", callback: () => setPrompt(this, "Apply dynamic range compression to audio") },
                                            { content: "Ducking", callback: () => setPrompt(this, "Apply audio ducking for voice-over clarity") },
                                            { content: "Audio Delay", callback: () => setPrompt(this, "Add a delay offset to the audio track") }
                                        ]
                                    }
                                },
                                {
                                    content: "📐 Spatial & Layout",
                                    submenu: {
                                        options: [
                                            { content: "Resize to 1080p", callback: () => setPrompt(this, "Resize to 1920x1080 maintaining aspect ratio") },
                                            { content: "Crop to Region", callback: () => setPrompt(this, "Crop to 1280x720 from center") },
                                            { content: "Auto Crop (Remove Borders)", callback: () => setPrompt(this, "Automatically detect and remove black borders") },
                                            { content: "Scale 2x Upscale", callback: () => setPrompt(this, "Upscale video by 2x with Lanczos algorithm") },
                                            { content: "Add Letterbox", callback: () => setPrompt(this, "Add black letterbox bars for 16:9 aspect ratio") },
                                            { content: "Rotate 90°", callback: () => setPrompt(this, "Rotate the video 90 degrees clockwise") },
                                            { content: "Split Screen", callback: () => setPrompt(this, "Create a side-by-side split screen layout") },
                                            { content: "Grid Layout", callback: () => setPrompt(this, "Arrange inputs in a grid layout") },
                                            { content: "Slideshow", callback: () => setPrompt(this, "Create a slideshow from images with fade transitions") },
                                            { content: "Concat / Join Videos", callback: () => setPrompt(this, "Concatenate video segments together sequentially") }
                                        ]
                                    }
                                },
                                null, // Separator
                                {
                                    content: "🎲 Random Example",
                                    callback: () => {
                                        const randomPrompt = RANDOM_PROMPTS[Math.floor(Math.random() * RANDOM_PROMPTS.length)];
                                        // Use purple magic color
                                        setPrompt(this, randomPrompt, true, "#8a4a8a");
                                    }
                                },
                                {
                                    content: "📋 Copy Prompt",
                                    callback: () => {
                                        const promptWidget = this.widgets?.find(w => w.name === "prompt");
                                        const text = promptWidget?.value;
                                        if (text && navigator.clipboard) {
                                            navigator.clipboard.writeText(text)
                                                .then(() => flashNode(this, "#4a7a4a"))
                                                .catch(() => flashNode(this, "#7a4a4a"));
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
                                        const promptWidget = this.widgets?.find(w => w.name === "prompt");
                                        if (promptWidget && promptWidget.value && promptWidget.value.trim() !== "") {
                                            this._previousPrompt = promptWidget.value; // Save history
                                            promptWidget.value = "";
                                            this.setDirtyCanvas(true, true);
                                            flashNode(this, "#7a3a3a");
                                        }
                                    }
                                }
                            ]
                        }
                    },
                    null // Separator
                );
            };
        }

        // Style VideoPreview node
        if (nodeData.name === "FFMPEGAPreview") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;

            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated?.apply(this, arguments);

                this.color = "#3a5a3a";
                this.bgcolor = "#2a4a2a";

                return result;
            };
        }

        // Style VideoToPath node
        if (nodeData.name === "FFMPEGAVideoToPath") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;

            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated?.apply(this, arguments);

                this.color = "#3a5a5a";
                this.bgcolor = "#2a4a4a";

                return result;
            };
        }

        // Style LoadVideoPath node + video preview + custom upload widget
        if (nodeData.name === "FFMPEGALoadVideoPath") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;

            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated?.apply(this, arguments);
                const node = this;

                this.color = "#5a4a2a";
                this.bgcolor = "#4a3a1a";

                // --- Video preview DOM widget ---
                const previewContainer = document.createElement("div");
                previewContainer.className = "ffmpega_preview";
                previewContainer.style.cssText =
                    "width:100%;background:#1a1a1a;border-radius:6px;" +
                    "overflow:hidden;position:relative;";

                const videoEl = document.createElement("video");
                videoEl.controls = true;
                videoEl.loop = true;
                videoEl.muted = true;
                videoEl.setAttribute("aria-label", "Video preview");
                videoEl.style.cssText = "width:100%;display:block;";
                videoEl.addEventListener("loadedmetadata", () => {
                    previewWidget.aspectRatio =
                        videoEl.videoWidth / videoEl.videoHeight;
                    // Populate info bar with client-side video metadata
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
                    if (parts.length) {
                        infoEl.textContent = parts.join(" | ");
                    }
                    node.setSize([
                        node.size[0],
                        node.computeSize([node.size[0], node.size[1]])[1],
                    ]);
                    node?.graph?.setDirtyCanvas(true);
                });
                videoEl.addEventListener("error", () => {
                    previewContainer.style.display = "none";
                    node.setSize([
                        node.size[0],
                        node.computeSize([node.size[0], node.size[1]])[1],
                    ]);
                    node?.graph?.setDirtyCanvas(true);
                });

                // Info overlay
                const infoEl = document.createElement("div");
                infoEl.style.cssText =
                    "padding:4px 8px;font-size:11px;color:#aaa;" +
                    "font-family:monospace;background:#111;";
                infoEl.textContent = "No video selected";

                previewContainer.appendChild(videoEl);
                previewContainer.appendChild(infoEl);

                // Prevent canvas events from going through the preview
                for (const evt of [
                    "contextmenu", "pointerdown", "mousewheel",
                    "pointermove", "pointerup",
                ]) {
                    previewContainer.addEventListener(evt, (e) => {
                        e.stopPropagation();
                    }, true);
                }

                const previewWidget = this.addDOMWidget(
                    "videopreview", "preview", previewContainer,
                    {
                        serialize: false,
                        hideOnZoom: false,
                        getValue() { return previewContainer.value; },
                        setValue(v) { previewContainer.value = v; },
                    }
                );
                previewWidget.aspectRatio = null;
                previewWidget.computeSize = function (width) {
                    if (this.aspectRatio && previewContainer.style.display !== "none") {
                        const h = (node.size[0] - 20) / this.aspectRatio + 10;
                        return [width, Math.max(h, 0) + 30]; // +30 for info bar
                    }
                    return [width, 34]; // Just info bar
                };

                // Function to update preview from filename
                const updatePreview = (filename) => {
                    if (!filename) {
                        previewContainer.style.display = "none";
                        infoEl.textContent = "No video selected";
                        return;
                    }
                    previewContainer.style.display = "";
                    const params = new URLSearchParams({
                        filename: filename,
                        type: "input",
                        timestamp: Date.now(),
                    });
                    videoEl.src = api.apiURL("/view?" + params.toString());
                    infoEl.textContent = "Loading...";
                };

                // --- Custom video upload widget (based on VHS pattern) ---
                // Helper to show errors without blocking alerts
                const showError = (msg) => {
                    flashNode(node, "#7a4a4a");
                    infoEl.textContent = msg;
                    previewContainer.style.display = "";
                    node.setSize([
                        node.size[0],
                        node.computeSize([node.size[0], node.size[1]])[1],
                    ]);
                    node?.graph?.setDirtyCanvas(true);
                };

                const videoWidget = this.widgets?.find(w => w.name === "video");
                const videoAccept = [
                    "video/webm", "video/mp4", "video/x-matroska",
                    "video/quicktime", "video/x-msvideo", "video/x-flv",
                    "video/x-ms-wmv", "video/mpeg", "video/3gpp",
                    "image/gif",
                ].join(",");

                // Create hidden file input
                const fileInput = document.createElement("input");
                Object.assign(fileInput, {
                    type: "file",
                    accept: videoAccept,
                    style: "display: none",
                    onchange: async () => {
                        if (!fileInput.files.length) return;
                        const file = fileInput.files[0];

                        const body = new FormData();
                        body.append("image", file);

                        try {
                            const resp = await fetch("/upload/image", {
                                method: "POST",
                                body: body,
                            });
                            if (resp.status !== 200) {
                                showError("Upload failed: " + resp.statusText);
                                return;
                            }
                            const data = await resp.json();
                            const filename = data.name;

                            if (videoWidget) {
                                if (!videoWidget.options.values.includes(filename)) {
                                    videoWidget.options.values.push(filename);
                                }
                                videoWidget.value = filename;
                                videoWidget.callback?.(filename);
                            }
                            updatePreview(filename);
                        } catch (err) {
                            showError("Upload error: " + err);
                        }
                    },
                });
                document.body.append(fileInput);

                // Cleanup file input when node is removed
                const origOnRemoved = this.onRemoved;
                this.onRemoved = function () {
                    fileInput?.remove();
                    origOnRemoved?.apply(this, arguments);
                };

                // Add upload button widget
                const uploadWidget = this.addWidget(
                    "button",
                    "choose video to upload",
                    "image",
                    () => {
                        app.canvas.node_widget = null;
                        fileInput.click();
                    }
                );
                uploadWidget.options = uploadWidget.options || {};
                uploadWidget.options.serialize = false;

                // Support drag-and-drop of video files onto the node
                this.onDragOver = (e) => {
                    return !!e?.dataTransfer?.types?.includes?.("Files");
                };
                this.onDragDrop = async (e) => {
                    if (!e?.dataTransfer?.types?.includes?.("Files")) return false;
                    const file = e.dataTransfer?.files?.[0];
                    if (!file) return false;

                    const ext = file.name.split(".").pop()?.toLowerCase();
                    const videoExts = [
                        "mp4", "avi", "mov", "mkv", "webm", "flv",
                        "wmv", "m4v", "mpg", "mpeg", "ts", "mts", "gif",
                    ];
                    if (!videoExts.includes(ext)) {
                        showError("Invalid file type: " + ext);
                        return false;
                    }

                    const body = new FormData();
                    body.append("image", file);

                    try {
                        const resp = await fetch("/upload/image", {
                            method: "POST",
                            body: body,
                        });
                        if (resp.status !== 200) {
                            console.warn("FFMPEGA: Upload rejected", resp.status, resp.statusText);
                            showError("Upload rejected: " + resp.statusText);
                            return false;
                        }
                        const data = await resp.json();
                        const filename = data.name;

                        if (videoWidget) {
                            if (!videoWidget.options.values.includes(filename)) {
                                videoWidget.options.values.push(filename);
                            }
                            videoWidget.value = filename;
                            videoWidget.callback?.(filename);
                        }
                        updatePreview(filename);
                        return true;
                    } catch (err) {
                        console.warn("FFMPEGA: Video upload failed", err);
                        showError("Upload failed: " + err);
                        return false;
                    }
                };

                // Watch for dropdown selection changes → update preview
                if (videoWidget) {
                    const origCallback = videoWidget.callback;
                    videoWidget.callback = function (value) {
                        origCallback?.apply(this, arguments);
                        updatePreview(value);
                    };
                    // Initial preview load if a video is already selected
                    if (videoWidget.value) {
                        setTimeout(() => updatePreview(videoWidget.value), 100);
                    }
                }

                // Handle execution results (metadata from Python backend)
                const origOnExecuted = this.onExecuted;
                this.onExecuted = function (data) {
                    origOnExecuted?.apply(this, arguments);
                    if (data?.video_info?.[0]) {
                        const info = data.video_info[0];
                        const parts = [];
                        if (info.source_width && info.source_height) {
                            parts.push(`${info.source_width}×${info.source_height}`);
                        }
                        if (info.effective_fps) {
                            parts.push(`${info.effective_fps} fps`);
                        }
                        if (info.effective_frames) {
                            parts.push(`${info.effective_frames} frames`);
                        }
                        if (info.effective_duration) {
                            const d = info.effective_duration;
                            const m = Math.floor(d / 60);
                            const s = (d % 60).toFixed(1);
                            parts.push(m > 0 ? `${m}m ${s}s` : `${s}s`);
                        }
                        infoEl.textContent = parts.join(" | ") || "No info";
                        // Show source vs effective if trim is applied
                        if (info.source_frames !== info.effective_frames) {
                            infoEl.textContent += ` (of ${info.source_frames})`;
                        }
                    }
                };

                // --- Video preview context menu ---
                const getVideoUrlLoad = () => videoEl.src || null;
                addVideoPreviewMenu(node, videoEl, previewContainer, previewWidget, getVideoUrlLoad);

                return result;
            };
        }

        // Style SaveVideo node + video preview
        if (nodeData.name === "FFMPEGASaveVideo") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;

            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated?.apply(this, arguments);
                const node = this;

                this.color = "#2a5a3a";
                this.bgcolor = "#1a4a2a";

                // --- Video preview DOM widget ---
                const previewContainer = document.createElement("div");
                previewContainer.className = "ffmpega_preview";
                previewContainer.style.cssText =
                    "width:100%;background:#1a1a1a;border-radius:6px;" +
                    "overflow:hidden;display:none;";

                const videoEl = document.createElement("video");
                videoEl.controls = true;
                videoEl.loop = true;
                videoEl.muted = true;
                videoEl.setAttribute("aria-label", "Output video preview");
                videoEl.style.cssText = "width:100%;display:block;";
                videoEl.addEventListener("loadedmetadata", () => {
                    previewWidget.aspectRatio =
                        videoEl.videoWidth / videoEl.videoHeight;
                    // Update info bar with video metadata
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
                        node.computeSize([node.size[0], node.size[1]])[1],
                    ]);
                    node?.graph?.setDirtyCanvas(true);
                });
                videoEl.addEventListener("error", () => {
                    previewContainer.style.display = "none";
                    node.setSize([
                        node.size[0],
                        node.computeSize([node.size[0], node.size[1]])[1],
                    ]);
                    node?.graph?.setDirtyCanvas(true);
                });

                const infoEl = document.createElement("div");
                infoEl.style.cssText =
                    "padding:4px 8px;font-size:11px;color:#aaa;" +
                    "font-family:monospace;background:#111;";
                infoEl.textContent = "Waiting for execution...";

                previewContainer.appendChild(videoEl);
                previewContainer.appendChild(infoEl);

                // Prevent canvas events from going through the preview
                for (const evt of [
                    "contextmenu", "pointerdown", "mousewheel",
                    "pointermove", "pointerup",
                ]) {
                    previewContainer.addEventListener(evt, (e) => {
                        e.stopPropagation();
                    }, true);
                }

                const previewWidget = this.addDOMWidget(
                    "videopreview", "preview", previewContainer,
                    {
                        serialize: false,
                        hideOnZoom: false,
                        getValue() { return previewContainer.value; },
                        setValue(v) { previewContainer.value = v; },
                    }
                );
                previewWidget.aspectRatio = null;
                previewWidget.computeSize = function (width) {
                    if (this.aspectRatio && previewContainer.style.display !== "none") {
                        const h = (node.size[0] - 20) / this.aspectRatio + 10;
                        return [width, Math.max(h, 0) + 30];
                    }
                    return [width, -4]; // Hidden until first execution
                };

                // Handle execution results — show preview of saved video
                const origOnExecuted = this.onExecuted;
                this.onExecuted = function (data) {
                    origOnExecuted?.apply(this, arguments);
                    if (data?.video?.[0]) {
                        const v = data.video[0];
                        const params = new URLSearchParams({
                            filename: v.filename,
                            subfolder: v.subfolder || "",
                            type: v.type || "output",
                            timestamp: Date.now(),
                        });
                        previewContainer.style.display = "";
                        videoEl.src = api.apiURL("/view?" + params.toString());

                        // Store file size for info bar
                        if (data?.file_size?.[0]) {
                            node._savedFileSize = data.file_size[0];
                        }

                        infoEl.textContent = `Saved: ${v.filename}`;
                        if (node._savedFileSize) {
                            infoEl.textContent += ` (${node._savedFileSize})`;
                        }
                    }
                };

                // --- Video preview context menu ---
                const getVideoUrlSave = () => videoEl.src || null;
                addVideoPreviewMenu(node, videoEl, previewContainer, previewWidget, getVideoUrlSave);

                return result;
            };
        }

        // Style BatchProcessor node
        if (nodeData.name === "FFMPEGABatchProcessor") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;

            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated?.apply(this, arguments);

                this.color = "#5a3a3a";
                this.bgcolor = "#4a2a2a";

                return result;
            };
        }

        // Style VideoInfo node
        if (nodeData.name === "FFMPEGAVideoInfo") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;

            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated?.apply(this, arguments);

                this.color = "#4a4a3a";
                this.bgcolor = "#3a3a2a";

                return result;
            };
        }
        // Style and enhance FFMPEGATextInput node with color picker
        if (nodeData.name === "FFMPEGATextInput") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;

            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated?.apply(this, arguments);
                const node = this;

                // Style the node
                node.color = "#3a4a5a";
                node.bgcolor = "#2a3a4a";

                // Find and replace the font_color STRING widget with a color picker
                const colorWidgetIdx = node.widgets?.findIndex(w => w.name === "font_color");
                if (colorWidgetIdx !== undefined && colorWidgetIdx >= 0) {
                    const oldWidget = node.widgets[colorWidgetIdx];
                    const initialColor = oldWidget.value || "#FFFFFF";

                    // Remove the old STRING widget
                    node.widgets.splice(colorWidgetIdx, 1);

                    // Create DOM container
                    const container = document.createElement("div");
                    container.style.cssText = `
                        display: flex;
                        align-items: center;
                        gap: 8px;
                        padding: 2px 4px;
                        width: 100%;
                        box-sizing: border-box;
                    `;

                    // Label
                    const label = document.createElement("span");
                    label.textContent = "font_color";
                    label.style.cssText = `
                        color: #b0b0b0;
                        font: 12px Arial, sans-serif;
                        flex-shrink: 0;
                    `;

                    // Color input
                    const colorInput = document.createElement("input");
                    colorInput.type = "color";
                    colorInput.value = initialColor;
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

                    // Hex display
                    const hexLabel = document.createElement("span");
                    hexLabel.textContent = initialColor.toUpperCase();
                    hexLabel.title = "Click to copy hex code";
                    hexLabel.style.cssText = `
                        color: #ccc;
                        font: 11px monospace;
                        flex-grow: 1;
                        text-align: right;
                        cursor: pointer;
                        user-select: none;
                    `;

                    // Click to copy handler
                    hexLabel.onclick = async () => {
                        const currentHex = colorInput.value.toUpperCase();
                        try {
                            if (navigator.clipboard) {
                                await navigator.clipboard.writeText(currentHex);
                                flashNode(node, "#4a7a4a"); // Green flash

                                // Temporary feedback
                                hexLabel.textContent = "COPIED";
                                hexLabel.style.color = "#8f8";

                                setTimeout(() => {
                                    // Only restore if still showing "COPIED"
                                    if (hexLabel.textContent === "COPIED") {
                                        hexLabel.textContent = currentHex;
                                        hexLabel.style.color = "#ccc";
                                    }
                                }, 800);
                            }
                        } catch (err) {
                            console.error("Failed to copy hex:", err);
                            flashNode(node, "#7a3a3a"); // Red flash
                        }
                    };

                    container.appendChild(label);
                    container.appendChild(colorInput);
                    container.appendChild(hexLabel);

                    // Add as DOM widget
                    const domWidget = node.addDOMWidget("font_color", "custom", container, {
                        getValue: () => colorInput.value.toUpperCase(),
                        setValue: (v) => {
                            if (v && typeof v === "string") {
                                // Handle both hex (#FFFFFF) and named colors
                                if (v.startsWith("#")) {
                                    colorInput.value = v;
                                    hexLabel.textContent = v.toUpperCase();
                                    hexLabel.style.color = "#ccc"; // Reset color
                                }
                            }
                        },
                    });
                    domWidget.value = initialColor;

                    colorInput.addEventListener("input", (e) => {
                        const val = e.target.value.toUpperCase();
                        domWidget.value = val;
                        hexLabel.textContent = val;
                        hexLabel.style.color = "#ccc"; // Reset color if dragging during feedback
                    });

                    // Move widget to the correct position
                    const newIdx = node.widgets.indexOf(domWidget);
                    if (newIdx >= 0 && newIdx !== colorWidgetIdx) {
                        node.widgets.splice(newIdx, 1);
                        node.widgets.splice(colorWidgetIdx, 0, domWidget);
                    }
                }

                return result;
            };
        }

    },
});


console.log("FFMPEGA UI extensions loaded");
