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

                // Add helpful placeholder examples
                const promptWidget = this.widgets?.find(w => w.name === "prompt");
                if (promptWidget) {
                    promptWidget.placeholder =
                        "Examples:\n" +
                        "- Make it 720p and add a subtle vignette\n" +
                        "- Apply cinematic letterbox with color grading\n" +
                        "- Speed up 2x, keep audio pitch normal\n" +
                        "- Create a vintage VHS look";
                }

                return result;
            };
        }

        // Preview indicator for VideoPreview node
        if (nodeData.name === "VideoPreview") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;

            nodeType.prototype.onNodeCreated = function() {
                const result = onNodeCreated?.apply(this, arguments);

                // Add preview status indicator
                this.addCustomWidget({
                    name: "preview_status",
                    type: "text",
                    value: "Ready",
                    draw: function(ctx, node, width, y, height) {
                        ctx.fillStyle = "#666";
                        ctx.font = "12px Arial";
                        ctx.textAlign = "center";
                        ctx.fillText(this.value, width / 2, y + height / 2 + 4);
                    }
                });

                return result;
            };
        }

        // Progress display for BatchProcessor node
        if (nodeData.name === "BatchProcessor") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;

            nodeType.prototype.onNodeCreated = function() {
                const result = onNodeCreated?.apply(this, arguments);

                // Style the node differently
                this.color = "#2a5a3a";
                this.bgcolor = "#1a3a2a";

                return result;
            };
        }
    },

    // Add custom menu options
    nodeCreated(node, app) {
        if (node.comfyClass === "FFMPEGAgent") {
            // Add quick preset buttons
            const presetMenu = {
                "Quick Presets": {
                    "Cinematic": () => setPrompt(node, "Apply cinematic letterbox and color grading"),
                    "Vintage": () => setPrompt(node, "Create a vintage film look with grain"),
                    "Social Vertical": () => setPrompt(node, "Crop to vertical 9:16 for TikTok/Reels"),
                    "Compress for Web": () => setPrompt(node, "Compress for web delivery, optimize file size"),
                    "Slow Motion": () => setPrompt(node, "Create smooth slow motion at 0.5x speed"),
                }
            };

            // Store original getMenuOptions
            const origGetMenuOptions = node.getMenuOptions;

            node.getMenuOptions = function() {
                const options = origGetMenuOptions?.call(this) || [];

                options.push(null); // Separator
                options.push({
                    content: "FFMPEGA Presets",
                    submenu: {
                        options: Object.entries(presetMenu["Quick Presets"]).map(([name, fn]) => ({
                            content: name,
                            callback: fn
                        }))
                    }
                });

                return options;
            };
        }
    }
});

/**
 * Helper function to set prompt text
 */
function setPrompt(node, text) {
    const promptWidget = node.widgets?.find(w => w.name === "prompt");
    if (promptWidget) {
        promptWidget.value = text;
        node.setDirtyCanvas(true);
    }
}

/**
 * Skill browser popup (can be triggered from node context menu)
 */
class SkillBrowser {
    constructor() {
        this.skills = null;
        this.popup = null;
    }

    async loadSkills() {
        // In a real implementation, this would fetch from the backend
        this.skills = {
            temporal: ["trim", "speed", "reverse", "loop", "fps"],
            spatial: ["resize", "crop", "pad", "rotate", "flip"],
            visual: ["brightness", "contrast", "saturation", "sharpen", "blur", "vignette"],
            audio: ["volume", "normalize", "fade_audio", "remove_audio"],
            encoding: ["compress", "convert", "quality"],
            outcome: ["cinematic", "vintage", "vhs", "social_vertical", "stabilize"]
        };
    }

    show(onSelect) {
        if (!this.skills) {
            this.loadSkills();
        }

        // Create popup UI
        const popup = document.createElement("div");
        popup.className = "ffmpega-skill-browser";
        popup.innerHTML = `
            <div class="ffmpega-skill-browser-header">
                <h3>FFMPEGA Skills</h3>
                <button class="close-btn">&times;</button>
            </div>
            <div class="ffmpega-skill-browser-content">
                <input type="text" placeholder="Search skills..." class="skill-search">
                <div class="skill-categories"></div>
            </div>
        `;

        // Style
        popup.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: #1a1a2e;
            border: 1px solid #444;
            border-radius: 8px;
            padding: 16px;
            z-index: 10000;
            min-width: 400px;
            max-height: 500px;
            overflow-y: auto;
        `;

        // Close button handler
        popup.querySelector(".close-btn").onclick = () => popup.remove();

        // Populate categories
        const categoriesDiv = popup.querySelector(".skill-categories");
        if (this.skills) {
            for (const [category, skills] of Object.entries(this.skills)) {
                const catDiv = document.createElement("div");
                catDiv.innerHTML = `
                    <h4 style="color: #88f; margin: 8px 0 4px;">${category}</h4>
                    <div class="skills-list" style="display: flex; flex-wrap: wrap; gap: 4px;">
                        ${skills.map(s => `
                            <span class="skill-tag" style="
                                background: #333;
                                padding: 2px 8px;
                                border-radius: 4px;
                                cursor: pointer;
                                font-size: 12px;
                            ">${s}</span>
                        `).join("")}
                    </div>
                `;
                categoriesDiv.appendChild(catDiv);

                // Click handlers
                catDiv.querySelectorAll(".skill-tag").forEach(tag => {
                    tag.onclick = () => {
                        if (onSelect) onSelect(tag.textContent);
                        popup.remove();
                    };
                });
            }
        }

        document.body.appendChild(popup);
        this.popup = popup;
    }
}

// Export for external use
window.FFMPEGASkillBrowser = new SkillBrowser();

console.log("FFMPEGA UI extensions loaded");
