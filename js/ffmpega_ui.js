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

// Register FFMPEGA extensions
app.registerExtension({
    name: "FFMPEGA.UI",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        // Enhanced prompt input for FFMPEGAgent node
        if (nodeData.name === "FFMPEGAgent") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;

            nodeType.prototype.onNodeCreated = function() {
                const result = onNodeCreated?.apply(this, arguments);

                // Style the node
                this.color = "#2a3a5a";
                this.bgcolor = "#1a2a4a";

                return result;
            };

            // Add context menu presets
            const origGetExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
            nodeType.prototype.getExtraMenuOptions = function(_, options) {
                origGetExtraMenuOptions?.apply(this, arguments);

                options.unshift(
                    {
                        content: "FFMPEGA Presets",
                        submenu: {
                            options: [
                                {
                                    content: "Cinematic & Style",
                                    submenu: {
                                        options: [
                                            {
                                                content: "Cinematic",
                                                callback: () => setPrompt(this, "Apply cinematic letterbox and color grading")
                                            },
                                            {
                                                content: "Vintage",
                                                callback: () => setPrompt(this, "Create a vintage film look with grain")
                                            },
                                            {
                                                content: "Noir",
                                                callback: () => setPrompt(this, "Black and white film noir style with high contrast")
                                            }
                                        ]
                                    }
                                },
                                {
                                    content: "Format & Social",
                                    submenu: {
                                        options: [
                                            {
                                                content: "Social Vertical (9:16)",
                                                callback: () => setPrompt(this, "Crop to vertical 9:16 for TikTok/Reels")
                                            },
                                            {
                                                content: "Instagram Square (1:1)",
                                                callback: () => setPrompt(this, "Crop to square 1:1 format")
                                            },
                                            {
                                                content: "Compress for Web",
                                                callback: () => setPrompt(this, "Compress for web delivery, optimize file size")
                                            }
                                        ]
                                    }
                                },
                                {
                                    content: "Time & Motion",
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
                                                content: "Reverse",
                                                callback: () => setPrompt(this, "Play the video in reverse")
                                            },
                                            {
                                                content: "Stabilize",
                                                callback: () => setPrompt(this, "Stabilize shaky footage")
                                            }
                                        ]
                                    }
                                },
                                {
                                    content: "Audio",
                                    submenu: {
                                        options: [
                                            {
                                                content: "Remove Audio",
                                                callback: () => setPrompt(this, "Remove all audio tracks")
                                            },
                                            {
                                                content: "Boost Volume",
                                                callback: () => setPrompt(this, "Increase audio volume")
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
                                    content: "Clear Prompt",
                                    callback: () => {
                                        const promptWidget = this.widgets?.find(w => w.name === "prompt");
                                        if (promptWidget && promptWidget.value && promptWidget.value.trim() !== "") {
                                            if (!confirm("Are you sure you want to clear the prompt?")) {
                                                return;
                                            }
                                            promptWidget.value = "";
                                            this.setDirtyCanvas(true, true);
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

            nodeType.prototype.onNodeCreated = function() {
                const result = onNodeCreated?.apply(this, arguments);

                this.color = "#3a5a3a";
                this.bgcolor = "#2a4a2a";

                return result;
            };
        }

        // Style BatchProcessor node
        if (nodeData.name === "FFMPEGABatchProcessor") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;

            nodeType.prototype.onNodeCreated = function() {
                const result = onNodeCreated?.apply(this, arguments);

                this.color = "#5a3a3a";
                this.bgcolor = "#4a2a2a";

                return result;
            };
        }

        // Style VideoInfo node
        if (nodeData.name === "FFMPEGAVideoInfo") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;

            nodeType.prototype.onNodeCreated = function() {
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
    }
}

console.log("FFMPEGA UI extensions loaded");
