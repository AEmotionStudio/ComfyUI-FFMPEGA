/**
 * FFMPEGA Custom UI Widgets for ComfyUI
 *
 * Provides enhanced UI elements for the FFMPEG Agent nodes.
 */

import { app } from "../../scripts/app.js";

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
    "Overlay the logo image in the bottom-right corner at 20% scale"
];

// --- Dynamic input slot management ---
// When you connect image_a, image_b appears. Connect image_b → image_c appears, etc.
// Same for audio_a, audio_b, audio_c, ...
const SLOT_LABELS = "abcdefghijklmnopqrstuvwxyz";

function updateDynamicSlots(node, prefix, slotType, excludePrefix) {
    // Find all slots matching this prefix (but not excludePrefix)
    const matchingIndices = [];
    for (let i = 0; i < node.inputs.length; i++) {
        const name = node.inputs[i].name;
        if (name.startsWith(prefix)) {
            if (excludePrefix && name.startsWith(excludePrefix)) continue;
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
                    } else {
                        widget.type = "hidden";
                        widget.computeSize = () => [0, -4];
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

                // --- Dynamic input slots (auto-expand) ---
                // Connect image_a → image_b appears. Connect image_b → image_c appears.
                // Same for audio_a → audio_b → audio_c, etc.
                const origOnConnectionsChange = this.onConnectionsChange;
                this.onConnectionsChange = function (type, slotIndex, isConnected, link, ioSlot) {
                    origOnConnectionsChange?.apply(this, arguments);
                    if (type === LiteGraph.INPUT) {
                        updateDynamicSlots(this, "images_", "IMAGE");
                        updateDynamicSlots(this, "image_", "IMAGE", "images_");
                        updateDynamicSlots(this, "audio_", "AUDIO");
                        fitHeight();
                    }
                };

                return result;
            };

            // Add context menu presets
            const origGetExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
            nodeType.prototype.getExtraMenuOptions = function (_, options) {
                origGetExtraMenuOptions?.apply(this, arguments);

                options.unshift(
                    {
                        content: "FFMPEGA Presets",
                        submenu: {
                            options: [
                                {
                                    content: "🎬 Cinematic & Style",
                                    submenu: {
                                        options: [
                                            {
                                                content: "Cinematic Letterbox",
                                                callback: () => setPrompt(this, "Apply cinematic letterbox and color grading")
                                            },
                                            {
                                                content: "Film Noir",
                                                callback: () => setPrompt(this, "Black and white film noir style with high contrast")
                                            },
                                            {
                                                content: "Dreamy / Soft Glow",
                                                callback: () => setPrompt(this, "Apply a dreamy soft glow effect")
                                            },
                                            {
                                                content: "HDR Look",
                                                callback: () => setPrompt(this, "Apply an HDR-style look with vivid colors and detail")
                                            },
                                            {
                                                content: "Teal & Orange",
                                                callback: () => setPrompt(this, "Apply teal and orange color grading")
                                            }
                                        ]
                                    }
                                },
                                {
                                    content: "📼 Vintage & Retro",
                                    submenu: {
                                        options: [
                                            {
                                                content: "Vintage Film",
                                                callback: () => setPrompt(this, "Create a vintage film look with grain")
                                            },
                                            {
                                                content: "VHS Effect",
                                                callback: () => setPrompt(this, "Apply a VHS tape effect with tracking lines and distortion")
                                            },
                                            {
                                                content: "Sepia Tone",
                                                callback: () => setPrompt(this, "Apply a warm sepia tone effect")
                                            },
                                            {
                                                content: "Super 8mm Film",
                                                callback: () => setPrompt(this, "Apply a Super 8mm film look with jitter and grain")
                                            },
                                            {
                                                content: "Old TV / CRT",
                                                callback: () => setPrompt(this, "Apply an old CRT television look with scanlines")
                                            },
                                            {
                                                content: "Polaroid Look",
                                                callback: () => setPrompt(this, "Apply a polaroid photo style color treatment")
                                            },
                                            {
                                                content: "Faded / Washed Out",
                                                callback: () => setPrompt(this, "Apply a faded washed-out film look")
                                            },
                                            {
                                                content: "Damaged Film",
                                                callback: () => setPrompt(this, "Apply a damaged film effect with scratches and flicker")
                                            }
                                        ]
                                    }
                                },
                                {
                                    content: "🎨 Color & Look",
                                    submenu: {
                                        options: [
                                            {
                                                content: "Grayscale",
                                                callback: () => setPrompt(this, "Convert to black and white grayscale")
                                            },
                                            {
                                                content: "Boost Saturation",
                                                callback: () => setPrompt(this, "Increase color saturation for more vivid colors")
                                            },
                                            {
                                                content: "Desaturate",
                                                callback: () => setPrompt(this, "Desaturate colors for a muted look")
                                            },
                                            {
                                                content: "Invert Colors",
                                                callback: () => setPrompt(this, "Invert all colors to create a negative image")
                                            },
                                            {
                                                content: "Sharpen",
                                                callback: () => setPrompt(this, "Sharpen the video to enhance detail and clarity")
                                            },
                                            {
                                                content: "Blur / Soften",
                                                callback: () => setPrompt(this, "Apply a soft gaussian blur effect")
                                            },
                                            {
                                                content: "Vignette",
                                                callback: () => setPrompt(this, "Add a dark vignette around the edges")
                                            },
                                            {
                                                content: "Deband",
                                                callback: () => setPrompt(this, "Remove color banding artifacts")
                                            }
                                        ]
                                    }
                                },
                                {
                                    content: "✨ Effects & Overlays",
                                    submenu: {
                                        options: [
                                            {
                                                content: "Text Overlay",
                                                callback: () => setPrompt(this, "Add text overlay that says 'Hello World' in the center")
                                            },
                                            {
                                                content: "Watermark",
                                                callback: () => setPrompt(this, "Add a semi-transparent watermark in the bottom-right corner")
                                            },
                                            {
                                                content: "Picture-in-Picture",
                                                callback: () => setPrompt(this, "Create a picture-in-picture layout with small video in corner")
                                            },
                                            {
                                                content: "Chroma Key (Green Screen)",
                                                callback: () => setPrompt(this, "Remove the green screen background using chroma key")
                                            },
                                            {
                                                content: "Add Film Grain",
                                                callback: () => setPrompt(this, "Add subtle film grain noise overlay")
                                            },
                                            {
                                                content: "Mirror / Flip",
                                                callback: () => setPrompt(this, "Mirror the video horizontally")
                                            }
                                        ]
                                    }
                                },
                                {
                                    content: "🔀 Transitions",
                                    submenu: {
                                        options: [
                                            {
                                                content: "Fade In from Black",
                                                callback: () => setPrompt(this, "Add a fade-in from black at the beginning")
                                            },
                                            {
                                                content: "Fade Out to Black",
                                                callback: () => setPrompt(this, "Add a fade-out to black at the end")
                                            },
                                            {
                                                content: "Fade to White",
                                                callback: () => setPrompt(this, "Add a fade to white transition")
                                            },
                                            {
                                                content: "Flash Effect",
                                                callback: () => setPrompt(this, "Add a bright flash transition at the midpoint")
                                            },
                                            {
                                                content: "Cross Dissolve",
                                                callback: () => setPrompt(this, "Add a cross dissolve transition between clips")
                                            }
                                        ]
                                    }
                                },
                                {
                                    content: "🌀 Motion & Animation",
                                    submenu: {
                                        options: [
                                            {
                                                content: "Ken Burns Zoom",
                                                callback: () => setPrompt(this, "Apply a slow Ken Burns zoom-in effect")
                                            },
                                            {
                                                content: "Spin / Rotate",
                                                callback: () => setPrompt(this, "Slowly rotate the video continuously")
                                            },
                                            {
                                                content: "Camera Shake",
                                                callback: () => setPrompt(this, "Add a subtle camera shake effect")
                                            },
                                            {
                                                content: "Pulse / Breathe",
                                                callback: () => setPrompt(this, "Add a rhythmic zoom pulse effect")
                                            },
                                            {
                                                content: "Drift / Pan",
                                                callback: () => setPrompt(this, "Add a slow horizontal drift pan")
                                            },
                                            {
                                                content: "Bounce",
                                                callback: () => setPrompt(this, "Add a bouncing animation effect")
                                            }
                                        ]
                                    }
                                },
                                {
                                    content: "📱 Format & Social",
                                    submenu: {
                                        options: [
                                            {
                                                content: "TikTok / Reels (9:16)",
                                                callback: () => setPrompt(this, "Crop to vertical 9:16 for TikTok/Reels")
                                            },
                                            {
                                                content: "Instagram Square (1:1)",
                                                callback: () => setPrompt(this, "Crop to square 1:1 format")
                                            },
                                            {
                                                content: "YouTube Optimize",
                                                callback: () => setPrompt(this, "Optimize for YouTube at 1080p with good compression")
                                            },
                                            {
                                                content: "Twitter / X Optimize",
                                                callback: () => setPrompt(this, "Optimize for Twitter/X with size limits")
                                            },
                                            {
                                                content: "Convert to GIF",
                                                callback: () => setPrompt(this, "Convert to an animated GIF")
                                            },
                                            {
                                                content: "Add Caption Space",
                                                callback: () => setPrompt(this, "Add blank space below the video for captions")
                                            },
                                            {
                                                content: "Compress for Web",
                                                callback: () => setPrompt(this, "Compress for web delivery, optimize file size")
                                            }
                                        ]
                                    }
                                },
                                {
                                    content: "⏱️ Time & Speed",
                                    submenu: {
                                        options: [
                                            {
                                                content: "Slow Motion (0.5x)",
                                                callback: () => setPrompt(this, "Create smooth slow motion at 0.5x speed")
                                            },
                                            {
                                                content: "Speed Up (2x)",
                                                callback: () => setPrompt(this, "Speed up the video 2x while keeping audio pitch")
                                            },
                                            {
                                                content: "Speed Up (4x)",
                                                callback: () => setPrompt(this, "Speed up the video 4x for time-lapse effect")
                                            },
                                            {
                                                content: "Reverse",
                                                callback: () => setPrompt(this, "Play the video in reverse")
                                            },
                                            {
                                                content: "Stabilize",
                                                callback: () => setPrompt(this, "Stabilize shaky footage")
                                            },
                                            {
                                                content: "Loop (3x)",
                                                callback: () => setPrompt(this, "Loop the video 3 times seamlessly")
                                            },
                                            {
                                                content: "Trim First 5 Seconds",
                                                callback: () => setPrompt(this, "Trim the first 5 seconds of the video")
                                            }
                                        ]
                                    }
                                },
                                {
                                    content: "🔊 Audio",
                                    submenu: {
                                        options: [
                                            {
                                                content: "Remove Audio",
                                                callback: () => setPrompt(this, "Remove all audio tracks")
                                            },
                                            {
                                                content: "Boost Volume",
                                                callback: () => setPrompt(this, "Increase audio volume")
                                            },
                                            {
                                                content: "Normalize Audio",
                                                callback: () => setPrompt(this, "Normalize audio levels to consistent volume")
                                            },
                                            {
                                                content: "Reduce Noise",
                                                callback: () => setPrompt(this, "Apply noise reduction to clean up the audio")
                                            },
                                            {
                                                content: "Fade Audio In/Out",
                                                callback: () => setPrompt(this, "Add audio fade-in at start and fade-out at end")
                                            },
                                            {
                                                content: "Extract Audio Only",
                                                callback: () => setPrompt(this, "Extract only the audio track as a separate output")
                                            }
                                        ]
                                    }
                                },
                                null, // Separator
                                {
                                    content: "🎲 Random Example",
                                    callback: () => {
                                        const promptWidget = this.widgets?.find(w => w.name === "prompt");
                                        if (promptWidget && promptWidget.value && promptWidget.value.trim() !== "") {
                                            // Simple confirmation using browser API
                                            if (!confirm("Replace current prompt with a random example?")) {
                                                return;
                                            }
                                        }
                                        const randomPrompt = RANDOM_PROMPTS[Math.floor(Math.random() * RANDOM_PROMPTS.length)];
                                        setPrompt(this, randomPrompt, true);
                                    }
                                },
                                {
                                    content: "🗑️ Clear Prompt",
                                    callback: () => {
                                        const promptWidget = this.widgets?.find(w => w.name === "prompt");
                                        if (promptWidget && promptWidget.value && promptWidget.value.trim() !== "") {
                                            if (!confirm("Are you sure you want to clear the prompt?")) {
                                                return;
                                            }
                                            promptWidget.value = "";
                                            this.setDirtyCanvas(true, true);
                                            flashNode(this);
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
    },
});

/**
 * Helper function to set prompt text on a node
 * @param {object} node - The node instance
 * @param {string} text - The text to set or append
 * @param {boolean} replace - If true, replaces the existing text. If false, appends.
 */
function setPrompt(node, text, replace = false) {
    const promptWidget = node.widgets?.find(w => w.name === "prompt");
    if (promptWidget) {
        if (replace) {
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
        flashNode(node);
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
    }, 200);
}

console.log("FFMPEGA UI extensions loaded");
