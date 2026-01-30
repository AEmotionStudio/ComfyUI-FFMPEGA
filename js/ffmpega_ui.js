/**
 * FFMPEGA Custom UI Widgets for ComfyUI
 *
 * Provides enhanced UI elements for the FFMPEG Agent nodes.
 */

import { app } from "../../scripts/app.js";

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
                                    content: "Cinematic",
                                    callback: () => setPrompt(this, "Apply cinematic letterbox and color grading")
                                },
                                {
                                    content: "Vintage",
                                    callback: () => setPrompt(this, "Create a vintage film look with grain")
                                },
                                {
                                    content: "Social Vertical (9:16)",
                                    callback: () => setPrompt(this, "Crop to vertical 9:16 for TikTok/Reels")
                                },
                                {
                                    content: "Compress for Web",
                                    callback: () => setPrompt(this, "Compress for web delivery, optimize file size")
                                },
                                {
                                    content: "Slow Motion (0.5x)",
                                    callback: () => setPrompt(this, "Create smooth slow motion at 0.5x speed")
                                },
                                {
                                    content: "Speed Up (2x)",
                                    callback: () => setPrompt(this, "Speed up the video 2x while keeping audio pitch")
                                },
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
 */
function setPrompt(node, text) {
    const promptWidget = node.widgets?.find(w => w.name === "prompt");
    if (promptWidget) {
        promptWidget.value = text;
        node.setDirtyCanvas(true, true);
    }
}

console.log("FFMPEGA UI extensions loaded");
