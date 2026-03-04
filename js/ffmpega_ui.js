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
 * @param {HTMLElement} infoEl - The info overlay element (optional, for feedback)
 */
function addVideoPreviewMenu(node, videoEl, previewContainer, previewWidget, getVideoUrl, infoEl) {
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

                        // Text feedback if infoEl is available
                        if (infoEl) {
                            // If this is our first time overriding, save the original text
                            if (!Object.prototype.hasOwnProperty.call(infoEl, '_originalText')) {
                                infoEl._originalText = infoEl.textContent;
                            }

                            const msg = "📋 Copied to clipboard!";
                            infoEl.textContent = msg;

                            // Ensure previous timeout is cleared if exists
                            if (infoEl._timeoutId) clearTimeout(infoEl._timeoutId);

                            infoEl._timeoutId = setTimeout(() => {
                                if (infoEl.textContent === msg) {
                                    // Restore original text
                                    if (Object.prototype.hasOwnProperty.call(infoEl, '_originalText')) {
                                        infoEl.textContent = infoEl._originalText;
                                        delete infoEl._originalText;
                                    }
                                }
                                infoEl._timeoutId = null;
                            }, 1000);
                        } else {
                            // Fallback if no infoEl
                            flashNode(node, "#4a7a4a");
                        }
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
                        let msg = "";

                        if (blob && navigator.clipboard?.write) {
                            await navigator.clipboard.write([
                                new ClipboardItem({ "image/png": blob })
                            ]);
                            flashNode(node, "#4a7a4a");
                            msg = "📸 Screenshot copied!";
                        } else {
                            // Fallback: download as file
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement("a");
                            a.href = url;
                            a.download = "screenshot.png";
                            a.click();
                            URL.revokeObjectURL(url);
                            flashNode(node, "#4a7a4a");
                            msg = "📸 Screenshot saved!";
                        }

                        // Text feedback if infoEl is available
                        if (infoEl && msg) {
                            // If this is our first time overriding, save the original text
                            if (!Object.prototype.hasOwnProperty.call(infoEl, '_originalText')) {
                                infoEl._originalText = infoEl.textContent;
                            }

                            infoEl.textContent = msg;

                            // Ensure previous timeout is cleared if exists
                            if (infoEl._timeoutId) clearTimeout(infoEl._timeoutId);

                            infoEl._timeoutId = setTimeout(() => {
                                if (infoEl.textContent === msg) {
                                    // Restore original text
                                    if (Object.prototype.hasOwnProperty.call(infoEl, '_originalText')) {
                                        infoEl.textContent = infoEl._originalText;
                                        delete infoEl._originalText;
                                    }
                                }
                                infoEl._timeoutId = null;
                            }, 1000);
                        } else {
                            // Fallback if no infoEl
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

/**
 * Adds a download overlay button to a video container
 * @param {HTMLElement} container - The container element (must be position:relative)
 * @param {HTMLVideoElement} videoEl - The video element
 */
function addDownloadOverlay(container, videoEl) {
    const btn = document.createElement("button");
    btn.innerHTML = `<span aria-hidden="true">💾</span>`;
    btn.title = "Save Video";
    btn.type = "button";
    btn.setAttribute("aria-label", "Save Video");
    btn.className = "ffmpega-overlay-btn";
    btn.style.cssText = `
        position: absolute;
        top: 8px;
        right: 8px;
        background: rgba(0, 0, 0, 0.6);
        color: white;
        border: none;
        padding: 0;
        margin: 0;
        border-radius: 4px;
        width: 28px;
        height: 28px;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        font-size: 16px;
        opacity: 0;
        transition: opacity 0.2s, background 0.2s;
        z-index: 10;
        pointer-events: auto;
    `;

    // Unified visibility and focus logic
    let containerHover = false;
    let btnHover = false;
    let btnFocus = false;

    const updateStyle = () => {
        const isVisible = containerHover || btnFocus || btnHover;
        const isActive = btnHover || btnFocus;
        btn.style.opacity = isVisible ? "1" : "0";
        btn.style.background = isActive ? "rgba(0, 0, 0, 0.8)" : "rgba(0, 0, 0, 0.6)";
        btn.style.boxShadow = btnFocus ? "0 0 0 2px #4a6a8a" : "none";
    };

    container.addEventListener("mouseenter", () => { containerHover = true; updateStyle(); });
    container.addEventListener("mouseleave", () => { containerHover = false; updateStyle(); });
    btn.addEventListener("mouseenter", () => { btnHover = true; updateStyle(); });
    btn.addEventListener("mouseleave", () => { btnHover = false; updateStyle(); });
    btn.addEventListener("focus", () => { btnFocus = true; updateStyle(); });
    btn.addEventListener("blur", () => { btnFocus = false; updateStyle(); });

    // Click logic
    btn.onclick = (e) => {
        e.stopPropagation();
        e.preventDefault();
        if (videoEl.src) {
            const a = document.createElement("a");
            a.href = videoEl.src;
            a.download = "video.mp4"; // Simple default
            try {
                const params = new URL(a.href, window.location.href).searchParams;
                const f = params.get("filename");
                if (f) a.download = f;
            } catch (e) { }

            document.body.appendChild(a);
            a.click();
            setTimeout(() => a.remove(), 0);

            // Feedback animation
            if (btn._timeout) clearTimeout(btn._timeout);
            btn.innerHTML = `<span aria-hidden="true">✅</span>`;
            btn.setAttribute("aria-label", "Saved!");

            btn._timeout = setTimeout(() => {
                btn.innerHTML = `<span aria-hidden="true">💾</span>`;
                btn.setAttribute("aria-label", "Save Video");
                btn._timeout = null;
            }, 1000);
        }
    };

    container.appendChild(btn);
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
                    const ollamaUrlWidget = this.widgets?.find(w => w.name === "ollama_url");
                    const verifyWidget = this.widgets?.find(w => w.name === "verify_output");
                    const visionWidget = this.widgets?.find(w => w.name === "use_vision");
                    const ptcWidget = this.widgets?.find(w => w.name === "ptc_mode");

                    function needsApiKey(model) {
                        if (!model) return false;
                        if (model === "none") return false;
                        // CLI-based models use their own auth — no api_key needed
                        if (model === "gemini-cli" || model === "claude-cli" || model === "cursor-agent" || model === "qwen-cli") return false;
                        return model.startsWith("gpt") ||
                            model.startsWith("claude") ||
                            model.startsWith("gemini") ||
                            model === "custom";
                    }

                    function updateLlmVisibility() {
                        const model = llmWidget.value;
                        const isNone = model === "none";
                        toggleWidget(customWidget, model === "custom");
                        toggleWidget(apiKeyWidget, needsApiKey(model));
                        // Hide LLM-only widgets when no model is selected
                        if (ollamaUrlWidget) toggleWidget(ollamaUrlWidget, !isNone);
                        if (verifyWidget) toggleWidget(verifyWidget, !isNone);
                        if (visionWidget) toggleWidget(visionWidget, !isNone);
                        if (ptcWidget) toggleWidget(ptcWidget, !isNone);
                        // Show no_llm_mode selector only when llm_model is 'none'
                        const noLlmModeWidget = node.widgets?.find(w => w.name === "no_llm_mode");
                        if (noLlmModeWidget) toggleWidget(noLlmModeWidget, isNone);
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

                // --- advanced_options toggle → all advanced widgets visibility ---
                const advancedWidget = this.widgets?.find(w => w.name === "advanced_options");
                const previewWidget = this.widgets?.find(w => w.name === "preview_mode");
                const crfWidget = this.widgets?.find(w => w.name === "crf");
                const encodingWidget = this.widgets?.find(w => w.name === "encoding_preset");
                const subtitleWidget = this.widgets?.find(w => w.name === "subtitle_path");
                const visionWidget = this.widgets?.find(w => w.name === "use_vision");
                const verifyWidget = this.widgets?.find(w => w.name === "verify_output");
                const whisperDevWidget = this.widgets?.find(w => w.name === "whisper_device");
                const whisperModelWidget = this.widgets?.find(w => w.name === "whisper_model");
                const sam3MaxObjWidget = this.widgets?.find(w => w.name === "sam3_max_objects");
                const sam3ThreshWidget = this.widgets?.find(w => w.name === "sam3_det_threshold");
                const maskTypeWidget = this.widgets?.find(w => w.name === "mask_output_type");
                const batchWidget = this.widgets?.find(w => w.name === "batch_mode");
                const folderWidget = this.widgets?.find(w => w.name === "video_folder");
                const patternWidget = this.widgets?.find(w => w.name === "file_pattern");
                const concurrentWidget = this.widgets?.find(w => w.name === "max_concurrent");
                const trackTokensWidget = this.widgets?.find(w => w.name === "track_tokens");
                const logUsageWidget = this.widgets?.find(w => w.name === "log_usage");
                const allowDownloadsWidget = this.widgets?.find(w => w.name === "allow_model_downloads");

                function updateAdvancedVisibility() {
                    const show = advancedWidget?.value ?? false;
                    // Rendering
                    if (previewWidget) toggleWidget(previewWidget, show);
                    if (subtitleWidget) toggleWidget(subtitleWidget, show);
                    if (crfWidget) toggleWidget(crfWidget, show);
                    if (encodingWidget) toggleWidget(encodingWidget, show);
                    // LLM behavior
                    if (visionWidget) toggleWidget(visionWidget, show);
                    if (verifyWidget) toggleWidget(verifyWidget, show);
                    // Whisper
                    if (whisperDevWidget) toggleWidget(whisperDevWidget, show);
                    if (whisperModelWidget) toggleWidget(whisperModelWidget, show);
                    // SAM3
                    if (sam3MaxObjWidget) toggleWidget(sam3MaxObjWidget, show);
                    if (sam3ThreshWidget) toggleWidget(sam3ThreshWidget, show);
                    if (maskTypeWidget) toggleWidget(maskTypeWidget, show);
                    // Batch
                    if (batchWidget) toggleWidget(batchWidget, show);
                    // Batch sub-widgets only show when BOTH advanced AND batch are on
                    const showBatch = show && batchWidget?.value;
                    if (folderWidget) toggleWidget(folderWidget, showBatch);
                    if (patternWidget) toggleWidget(patternWidget, showBatch);
                    if (concurrentWidget) toggleWidget(concurrentWidget, showBatch);
                    // Usage tracking & downloads
                    if (trackTokensWidget) toggleWidget(trackTokensWidget, show);
                    if (logUsageWidget) toggleWidget(logUsageWidget, show);
                    if (allowDownloadsWidget) toggleWidget(allowDownloadsWidget, show);
                    fitHeight();
                }

                if (advancedWidget) {
                    updateAdvancedVisibility();
                    const origAdvCb = advancedWidget.callback;
                    advancedWidget.callback = function (...args) {
                        origAdvCb?.apply(this, args);
                        updateAdvancedVisibility();
                    };
                }

                // --- batch_mode → video_folder / file_pattern / max_concurrent visibility ---
                if (batchWidget) {
                    function updateBatchVisibility() {
                        // Only show batch sub-widgets when advanced is also on
                        const showAdvanced = advancedWidget?.value ?? true;
                        const show = batchWidget.value && showAdvanced;
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
                        updateDynamicSlots(this, "video_", "STRING", ["video_path", "video_folder"]);
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

                    // DEBUG removed

                    // Pre-create any dynamic slots that were saved in the workflow
                    // before LiteGraph tries to restore their links.
                    // This ensures slots exist for link reconnection.
                    const dynamicPrefixes = [
                        { prefix: "images_", type: "IMAGE", excludes: [] },
                        { prefix: "image_", type: "IMAGE", excludes: ["images_", "image_path_"] },
                        { prefix: "audio_", type: "AUDIO", excludes: [] },
                        { prefix: "video_", type: "STRING", excludes: ["video_path", "video_folder"] },
                        { prefix: "image_path_", type: "STRING", excludes: [] },
                        { prefix: "text_", type: "STRING", excludes: [] },
                    ];

                    if (info?.inputs) {
                        const existingNames = new Set(this.inputs.map(i => i.name));

                        // Step 1: Pre-create any dynamic slots that were
                        // explicitly saved in the workflow
                        for (const saved of info.inputs) {
                            if (!existingNames.has(saved.name)) {
                                const isDynamic = dynamicPrefixes.some(({ prefix, excludes }) => {
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

                        // Step 2: For each dynamic group, if any saved slot
                        // had a link, ensure the next trailing slot exists.
                        // Unconnected trailing slots (e.g. video_b when only
                        // video_a is connected) are NOT saved in the workflow,
                        // so we must recreate them from link data.
                        for (const { prefix, type, excludes } of dynamicPrefixes) {
                            // Find the highest-lettered slot in this group that had a link
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
                            // Create the next trailing slot if needed
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

                    // After links are restored, update slots to add trailing empty slot
                    const self = this;
                    function restoreSlots() {
                        updateDynamicSlots(self, "images_", "IMAGE");
                        updateDynamicSlots(self, "image_", "IMAGE", ["images_", "image_path_"]);
                        updateDynamicSlots(self, "audio_", "AUDIO");
                        updateDynamicSlots(self, "video_", "STRING", ["video_path", "video_folder"]);
                        updateDynamicSlots(self, "image_path_", "STRING");
                        updateDynamicSlots(self, "text_", "STRING");
                        updateAdvancedVisibility();
                        fitHeight();
                    }

                    // Deferred restore to catch any links restored after
                    // this synchronous configure pass completes.
                    restoreSlots();
                    setTimeout(restoreSlots, 0);
                    setTimeout(restoreSlots, 300);
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
                                            { content: "Burn Subtitles (SRT)", callback: () => setPrompt(this, "Burn subtitles from SRT file into the video") },
                                            null, // Separator
                                            { content: "🎙️ Auto-Transcribe Subtitles", callback: () => setPrompt(this, "Auto-transcribe and burn subtitles with white text") },
                                            { content: "🎙️ Transcribe (Custom Color)", callback: () => setPrompt(this, "Auto-transcribe and burn subtitles with large yellow text at 32px") },
                                            { content: "🎙️ Karaoke Subtitles", callback: () => setPrompt(this, "Add karaoke-style word-by-word subtitles with yellow fill") }
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

        // Style FrameExtract node + live video preview
        if (nodeData.name === "FFMPEGAFrameExtract") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;

            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated?.apply(this, arguments);
                const node = this;

                this.color = "#2a4a5a";
                this.bgcolor = "#1a3a4a";

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
                videoEl.volume = 1.0;
                videoEl.setAttribute("aria-label", "Frame extraction preview");
                videoEl.style.cssText = "width:100%;display:block;";
                // Remember user's mute preference across video loads
                let userUnmuted = false;
                videoEl.addEventListener("volumechange", () => {
                    userUnmuted = !videoEl.muted;
                });
                videoEl.addEventListener("play", () => {
                    if (userUnmuted) videoEl.muted = false;
                });
                videoEl.addEventListener("loadedmetadata", () => {
                    previewWidget.aspectRatio =
                        videoEl.videoWidth / videoEl.videoHeight;
                    node.setSize([
                        node.size[0],
                        node.computeSize([node.size[0], node.size[1]])[1],
                    ]);
                    node?.graph?.setDirtyCanvas(true);
                });
                videoEl.addEventListener("error", () => {
                    previewContainer.style.display = "none";
                    infoEl.textContent = "No video loaded";
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
                infoEl.textContent = "No video loaded";
                infoEl.setAttribute("role", "status");
                infoEl.setAttribute("aria-live", "polite");

                previewContainer.appendChild(videoEl);
                previewContainer.appendChild(infoEl);

                // Add download overlay
                addDownloadOverlay(previewContainer, videoEl);

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

                // --- Live preview: watch video_path, start_time, duration ---
                let _previewDebounce = null;

                const updateLivePreview = () => {
                    const pathWidget = node.widgets?.find(w => w.name === "video_path");
                    const startWidget = node.widgets?.find(w => w.name === "start_time");
                    const durWidget = node.widgets?.find(w => w.name === "duration");

                    const videoPath = pathWidget?.value?.trim();
                    if (!videoPath) {
                        previewContainer.style.display = "none";
                        infoEl.textContent = "No video loaded";
                        node.setSize([
                            node.size[0],
                            node.computeSize([node.size[0], node.size[1]])[1],
                        ]);
                        node?.graph?.setDirtyCanvas(true);
                        return;
                    }

                    const startTime = startWidget?.value ?? 0;
                    const duration = durWidget?.value ?? 0;

                    // Build preview URL via our streaming endpoint
                    const params = new URLSearchParams({
                        path: videoPath,
                        start_time: String(startTime),
                        _t: String(Date.now()), // cache bust
                    });
                    // Only send duration if > 0 (0 = full video, server caps at 30s)
                    if (duration > 0) {
                        params.set("duration", String(duration));
                    }
                    const previewUrl = api.apiURL("/ffmpega/preview?" + params.toString());

                    previewContainer.style.display = "";
                    infoEl.textContent = "Loading preview...";
                    videoEl.src = previewUrl;

                    // Fetch video info for the info bar
                    const infoParams = new URLSearchParams({ path: videoPath });
                    fetch(api.apiURL("/ffmpega/video_info?" + infoParams.toString()))
                        .then(r => r.json())
                        .then(info => {
                            if (!info?.width) return;
                            const fpsW = node.widgets?.find(w => w.name === "fps");
                            const extractFps = fpsW?.value ?? 1;
                            const maxFramesW = node.widgets?.find(w => w.name === "max_frames");
                            const maxFrames = maxFramesW?.value ?? 100;

                            // Calculate expected frame count
                            const actualDur = Math.min(duration, info.duration - startTime);
                            const expectedFrames = Math.min(
                                Math.max(0, Math.floor(actualDur * extractFps)),
                                maxFrames,
                            );

                            const startFmt = formatTime(startTime);
                            const endFmt = formatTime(startTime + actualDur);

                            infoEl.textContent =
                                `~${expectedFrames} frames • ${info.width}×${info.height}` +
                                ` • ${startFmt}–${endFmt} @ ${extractFps}fps`;
                        })
                        .catch(() => {
                            infoEl.textContent = "Preview loaded";
                        });
                };

                // Small helper to format seconds as m:ss or ss.s
                const formatTime = (sec) => {
                    if (sec < 0) sec = 0;
                    const m = Math.floor(sec / 60);
                    const s = (sec % 60).toFixed(1);
                    return m > 0 ? `${m}:${s.padStart(4, "0")}` : `${s}s`;
                };

                const debouncedPreview = () => {
                    clearTimeout(_previewDebounce);
                    _previewDebounce = setTimeout(updateLivePreview, 600);
                };

                // Hook into widget value changes for live updates
                const watchWidgets = ["video_path", "start_time", "duration", "fps", "max_frames"];
                // Use a polling approach since LiteGraph widgets don't have
                // reliable change events for all widget types
                const widgetValues = {};
                const pollInterval = setInterval(() => {
                    if (!node.graph) {
                        clearInterval(pollInterval);
                        return;
                    }
                    let changed = false;
                    for (const name of watchWidgets) {
                        const w = node.widgets?.find(ww => ww.name === name);
                        if (w && widgetValues[name] !== w.value) {
                            widgetValues[name] = w.value;
                            changed = true;
                        }
                    }
                    if (changed) debouncedPreview();
                }, 500);

                // Initial preview load
                setTimeout(updateLivePreview, 300);

                // Handle execution results — update info with actual frame stats
                const origOnExecuted = this.onExecuted;
                this.onExecuted = function (data) {
                    origOnExecuted?.apply(this, arguments);

                    // Show the temp preview clip if available
                    if (data?.video?.[0]) {
                        const v = data.video[0];
                        const params = new URLSearchParams({
                            filename: v.filename,
                            subfolder: v.subfolder || "",
                            type: v.type || "temp",
                            timestamp: String(Date.now()),
                        });
                        previewContainer.style.display = "";
                        videoEl.src = api.apiURL("/view?" + params.toString());
                    }

                    // Update info bar with actual extraction stats
                    if (data?.frame_info?.[0]) {
                        const fi = data.frame_info[0];
                        const startFmt = formatTime(fi.start);
                        const endFmt = formatTime(fi.end);
                        const durFmt = formatTime(fi.duration);
                        infoEl.textContent =
                            `${fi.count} frames • ${fi.width}×${fi.height}` +
                            ` • ${startFmt}–${endFmt} (${durFmt})` +
                            ` • src ${fi.source_fps}fps → extract ${fi.fps}fps`;
                    }
                };

                // Clean up interval on node removal
                const origOnRemoved = this.onRemoved;
                this.onRemoved = function () {
                    clearInterval(pollInterval);
                    fileInput?.remove();
                    origOnRemoved?.apply(this, arguments);
                };

                // --- Upload button + drag-drop (same pattern as LoadVideoPath) ---
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

                const videoAccept = [
                    "video/webm", "video/mp4", "video/x-matroska",
                    "video/quicktime", "video/x-msvideo", "video/x-flv",
                    "video/x-ms-wmv", "video/mpeg", "video/3gpp",
                    "image/gif",
                ].join(",");

                const fileInput = document.createElement("input");
                Object.assign(fileInput, {
                    type: "file",
                    accept: videoAccept,
                    style: "display: none",
                });
                document.body.append(fileInput);

                const uploadBtn = document.createElement("button");
                uploadBtn.innerHTML = "Upload Video...";
                uploadBtn.setAttribute("aria-label", "Upload Video");
                uploadBtn.style.cssText = `
                    width: 100%;
                    margin-top: 4px;
                    background-color: #222;
                    color: #ccc;
                    border: 1px solid #333;
                    border-radius: 4px;
                    padding: 6px;
                    cursor: pointer;
                    font-family: monospace;
                    font-size: 12px;
                    transition: background-color 0.2s;
                `;
                let isHovered = false;
                let isFocused = false;
                const updateUploadBtn = () => {
                    if (uploadBtn.disabled) return;
                    const active = isHovered || isFocused;
                    uploadBtn.style.backgroundColor = active ? "#333" : "#222";
                    uploadBtn.style.outline = isFocused ? "2px solid #4a6a8a" : "none";
                };
                uploadBtn.onmouseenter = () => { isHovered = true; updateUploadBtn(); };
                uploadBtn.onmouseleave = () => { isHovered = false; updateUploadBtn(); };
                uploadBtn.onfocus = () => { isFocused = true; updateUploadBtn(); };
                uploadBtn.onblur = () => { isFocused = false; updateUploadBtn(); };
                uploadBtn.onclick = () => fileInput.click();
                uploadBtn.onpointerdown = (e) => e.stopPropagation();

                this.addDOMWidget("upload_button", "btn", uploadBtn, {
                    serialize: false,
                });

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
                        node.computeSize([node.size[0], node.size[1]])[1],
                    ]);
                };

                const handleUpload = async (file) => {
                    setUploadState(true, file.name);
                    const body = new FormData();
                    body.append("image", file);

                    try {
                        const resp = await fetch("/upload/image", {
                            method: "POST",
                            body: body,
                        });
                        if (resp.status !== 200) {
                            showError("Upload failed: " + resp.statusText);
                            return false;
                        }
                        const data = await resp.json();
                        const filename = data.name;

                        // Set the video_path STRING widget to the uploaded file
                        // ComfyUI stores uploads in the input directory
                        const pathWidget = node.widgets?.find(w => w.name === "video_path");
                        if (pathWidget) {
                            // Build path relative to ComfyUI input dir
                            const subfolder = data.subfolder || "";
                            const inputPath = subfolder
                                ? `input/${subfolder}/${filename}`
                                : `input/${filename}`;
                            pathWidget.value = inputPath;
                        }

                        // Trigger preview update
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
                    if (fileInput.files.length) {
                        await handleUpload(fileInput.files[0]);
                    }
                };

                // Drag-and-drop support
                this.onDragOver = (e) => {
                    if (e?.dataTransfer?.types?.includes?.("Files")) {
                        if (!uploadBtn.disabled) {
                            if (!Object.prototype.hasOwnProperty.call(uploadBtn, '_originalInnerHTML')) {
                                uploadBtn._originalInnerHTML = uploadBtn.innerHTML;
                            }
                            if (!Object.prototype.hasOwnProperty.call(uploadBtn, '_originalBorder')) {
                                uploadBtn._originalBorder = uploadBtn.style.border;
                            }
                            if (!Object.prototype.hasOwnProperty.call(uploadBtn, '_originalAriaLabel')) {
                                uploadBtn._originalAriaLabel = uploadBtn.getAttribute("aria-label");
                            }
                            uploadBtn.innerHTML = `<span aria-hidden="true">📂</span> Drop to Upload`;
                            uploadBtn.setAttribute("aria-label", "Drop to Upload");
                            uploadBtn.style.border = "1px dashed #4a6a8a";
                            uploadBtn.style.backgroundColor = "#333";

                            if (uploadBtn._dragTimeout) clearTimeout(uploadBtn._dragTimeout);
                            uploadBtn._dragTimeout = setTimeout(() => {
                                if (!uploadBtn.disabled) {
                                    if (Object.prototype.hasOwnProperty.call(uploadBtn, '_originalInnerHTML')) {
                                        uploadBtn.innerHTML = uploadBtn._originalInnerHTML;
                                        delete uploadBtn._originalInnerHTML;
                                    }
                                    if (Object.prototype.hasOwnProperty.call(uploadBtn, '_originalBorder')) {
                                        uploadBtn.style.border = uploadBtn._originalBorder;
                                        delete uploadBtn._originalBorder;
                                    }
                                    if (Object.prototype.hasOwnProperty.call(uploadBtn, '_originalAriaLabel')) {
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

                    return await handleUpload(file);
                };

                // --- Video preview context menu ---
                const getVideoUrl = () => videoEl.src || null;
                addVideoPreviewMenu(node, videoEl, previewContainer, previewWidget, getVideoUrl, infoEl);

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

                // --- Dynamic output slot visibility ---
                // Remove "images" and "audio" outputs initially.  They are
                // added back (always as a pair, to keep indices 5/6 aligned
                // with Python's RETURN_TYPES) when EITHER input is connected.
                const _syncDynamicOutputs = () => {
                    const imagesIn = node.findInputSlot("images");
                    const audioIn = node.findInputSlot("audio");

                    const anyConnected =
                        (imagesIn >= 0 && node.inputs[imagesIn].link != null) ||
                        (audioIn >= 0 && node.inputs[audioIn].link != null);

                    const imagesOut = node.findOutputSlot("images");
                    const audioOut = node.findOutputSlot("audio");
                    const hasOutputs = imagesOut >= 0 || audioOut >= 0;

                    if (anyConnected && !hasOutputs) {
                        // Add both outputs (images first → idx 5, audio → idx 6)
                        node.addOutput("images", "IMAGE");
                        node.addOutput("audio", "AUDIO");
                    } else if (!anyConnected && hasOutputs) {
                        // Remove in reverse index order to avoid shifting
                        const aIdx = node.findOutputSlot("audio");
                        if (aIdx >= 0) node.removeOutput(aIdx);
                        const iIdx = node.findOutputSlot("images");
                        if (iIdx >= 0) node.removeOutput(iIdx);
                    }

                    node.setDirtyCanvas(true, true);
                };

                // Initial state: remove both outputs (they were added by
                // ComfyUI from Python's RETURN_TYPES)
                requestAnimationFrame(() => {
                    const aIdx = node.findOutputSlot("audio");
                    if (aIdx >= 0) node.removeOutput(aIdx);
                    const iIdx = node.findOutputSlot("images");
                    if (iIdx >= 0) node.removeOutput(iIdx);
                    node.setDirtyCanvas(true, true);
                });

                // React to connection changes
                const origOnCC = this.onConnectionsChange;
                this.onConnectionsChange = function (type, slotIndex, isConnected, link, ioSlot) {
                    origOnCC?.apply(this, arguments);
                    if (type === LiteGraph.INPUT) {
                        const name = this.inputs?.[slotIndex]?.name;
                        if (name === "images" || name === "audio") {
                            _syncDynamicOutputs();
                        }
                    }
                };

                // Restore on workflow load / page refresh
                const origConfigure = this.onConfigure;
                this.onConfigure = function (data) {
                    origConfigure?.apply(this, arguments);
                    requestAnimationFrame(_syncDynamicOutputs);
                };

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

                // Playback position tracking for live frame counter
                let _srcMeta = null; // { width, height, fps, duration, frames }
                let _effAvailFrames = 0;
                let _effFps = 0;
                let _effSkipFirst = 0;
                let _effInfoText = ""; // base info text (without frame pos)

                videoEl.addEventListener("loadedmetadata", () => {
                    previewWidget.aspectRatio =
                        videoEl.videoWidth / videoEl.videoHeight;

                    // Store basic metadata from the video element
                    _srcMeta = {
                        width: videoEl.videoWidth,
                        height: videoEl.videoHeight,
                        fps: 0, // will be filled by /ffmpega/video_info
                        duration: videoEl.duration,
                        frames: 0,
                    };

                    // Fetch accurate metadata via ffprobe for fps + frame count
                    const vidWidget = node.widgets?.find(w => w.name === "video");
                    if (vidWidget?.value) {
                        const infoParams = new URLSearchParams({
                            path: "input/" + vidWidget.value,
                        });
                        fetch(api.apiURL("/ffmpega/video_info?" + infoParams.toString()))
                            .then(r => r.json())
                            .then(info => {
                                if (info?.fps) {
                                    _srcMeta.fps = info.fps;
                                    _srcMeta.frames = info.frames || Math.round(info.duration * info.fps);
                                    _srcMeta.duration = info.duration || _srcMeta.duration;
                                }
                                updateDynamicInfo();
                            })
                            .catch(() => updateDynamicInfo());
                    } else {
                        updateDynamicInfo();
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

                // --- Dynamic info bar calculation ---
                const formatTimeLV = (sec) => {
                    if (sec < 0) sec = 0;
                    const m = Math.floor(sec / 60);
                    const s = (sec % 60).toFixed(1);
                    return m > 0 ? `${m}:${s.padStart(4, "0")}` : `${s}s`;
                };

                const updateDynamicInfo = () => {
                    if (!_srcMeta) {
                        infoEl.textContent = "No video selected";
                        return;
                    }

                    const forceRate = node.widgets?.find(w => w.name === "force_rate")?.value ?? 0;
                    const skipFirst = node.widgets?.find(w => w.name === "skip_first_frames")?.value ?? 0;
                    const frameCap = node.widgets?.find(w => w.name === "frame_load_cap")?.value ?? 0;
                    const everyNth = node.widgets?.find(w => w.name === "select_every_nth")?.value ?? 1;

                    const srcFps = _srcMeta.fps || 24;
                    const srcDuration = _srcMeta.duration || 0;
                    const srcFrames = _srcMeta.frames || Math.round(srcDuration * srcFps);

                    // Effective FPS
                    const effFps = forceRate > 0 ? forceRate : srcFps;

                    // Available frames after re-sampling
                    let availFrames = forceRate > 0
                        ? Math.ceil(srcDuration * forceRate)
                        : srcFrames;

                    // Skip
                    availFrames = Math.max(0, availFrames - skipFirst);

                    // Select every Nth
                    if (everyNth > 1) {
                        availFrames = Math.max(0, Math.floor(availFrames / everyNth));
                    }

                    // Cap
                    if (frameCap > 0) {
                        availFrames = Math.min(availFrames, frameCap);
                    }

                    // Effective duration
                    const effDuration = effFps > 0 && availFrames > 0
                        ? availFrames / effFps
                        : srcDuration;

                    // Start time from skip (use effFps since skip is in forced-rate frames)
                    const startTime = effFps > 0 ? skipFirst / effFps : 0;

                    // Build info text: source → effective
                    const parts = [];
                    if (_srcMeta.width && _srcMeta.height) {
                        parts.push(`${_srcMeta.width}×${_srcMeta.height}`);
                    }

                    // FPS: show source → effective if different
                    if (forceRate > 0 && forceRate !== srcFps) {
                        parts.push(`${srcFps}fps → ${forceRate}fps`);
                    } else {
                        parts.push(`${srcFps}fps`);
                    }

                    // Frames: show effective (of source) if trimmed
                    if (availFrames !== srcFrames) {
                        parts.push(`${availFrames} frames (of ${srcFrames})`);
                    } else {
                        parts.push(`${availFrames} frames`);
                    }

                    // Duration
                    if (Math.abs(effDuration - srcDuration) > 0.1) {
                        parts.push(`${formatTimeLV(effDuration)} (of ${formatTimeLV(srcDuration)})`);
                    } else {
                        parts.push(formatTimeLV(srcDuration));
                    }

                    // Time range if skipping
                    if (startTime > 0.05) {
                        parts.push(`from ${formatTimeLV(startTime)}`);
                    }

                    infoEl.textContent = parts.join(" • ");
                    _effInfoText = infoEl.textContent;
                    _effAvailFrames = availFrames;
                    _effFps = effFps;
                    _effSkipFirst = skipFirst;
                };

                // --- Widget polling for live updates ---
                let _lvDebounce = null;
                const trimWidgets = ["force_rate", "skip_first_frames", "frame_load_cap", "select_every_nth"];
                const lvWidgetValues = {};

                // Playback range clamping
                let _playStart = 0;
                let _playEnd = Infinity;

                // Clamp playback + show live frame counter
                videoEl.addEventListener("timeupdate", () => {
                    if (_playEnd < Infinity && videoEl.currentTime >= _playEnd) {
                        videoEl.currentTime = _playStart;
                    }
                    // Update frame counter in info bar
                    if (_srcMeta?.fps > 0 && _effAvailFrames > 0 && _effInfoText) {
                        const elapsed = Math.max(0, videoEl.currentTime - _playStart);
                        const curFrame = Math.min(
                            Math.floor(elapsed * _effFps) + 1,
                            _effAvailFrames,
                        );
                        const srcFrame = curFrame + _effSkipFirst;
                        infoEl.textContent = `▶ ${curFrame}/${_effAvailFrames} (src frame ${srcFrame}) • ${_effInfoText}`;
                    }
                });

                const updatePlaybackRange = () => {
                    if (!_srcMeta || !_srcMeta.fps) return;

                    const forceRate = node.widgets?.find(w => w.name === "force_rate")?.value ?? 0;
                    const skipFirst = node.widgets?.find(w => w.name === "skip_first_frames")?.value ?? 0;
                    const frameCap = node.widgets?.find(w => w.name === "frame_load_cap")?.value ?? 0;
                    const everyNth = node.widgets?.find(w => w.name === "select_every_nth")?.value ?? 1;

                    const srcFps = _srcMeta.fps;
                    const effFps = forceRate > 0 ? forceRate : srcFps;

                    // Start time from skipped frames (use effFps since skip is in forced-rate frames)
                    _playStart = effFps > 0 ? skipFirst / effFps : 0;

                    // Calculate available frames (same math as updateDynamicInfo)
                    let availFrames = forceRate > 0
                        ? Math.ceil(_srcMeta.duration * forceRate)
                        : (_srcMeta.frames || Math.round(_srcMeta.duration * srcFps));
                    availFrames = Math.max(0, availFrames - skipFirst);
                    if (everyNth > 1) availFrames = Math.floor(availFrames / everyNth);
                    if (frameCap > 0) availFrames = Math.min(availFrames, frameCap);

                    // End time
                    if (effFps > 0 && availFrames > 0) {
                        _playEnd = _playStart + (availFrames / effFps);
                    } else {
                        _playEnd = Infinity;
                    }

                    // Clamp to video duration
                    if (isFinite(_playEnd) && _playEnd > _srcMeta.duration) {
                        _playEnd = _srcMeta.duration;
                    }

                    // Seek to start of effective range
                    if (isFinite(_playStart) && _playStart < videoEl.duration) {
                        videoEl.currentTime = _playStart;
                    }
                };

                const lvPollInterval = setInterval(() => {
                    if (!node.graph) {
                        clearInterval(lvPollInterval);
                        return;
                    }
                    let changed = false;
                    for (const name of trimWidgets) {
                        const w = node.widgets?.find(ww => ww.name === name);
                        if (w && lvWidgetValues[name] !== w.value) {
                            lvWidgetValues[name] = w.value;
                            changed = true;
                        }
                    }
                    if (changed) {
                        clearTimeout(_lvDebounce);
                        _lvDebounce = setTimeout(() => {
                            updateDynamicInfo();
                            updatePlaybackRange();
                        }, 300);
                    }
                }, 500);

                // Info overlay
                const infoEl = document.createElement("div");
                infoEl.style.cssText =
                    "padding:4px 8px;font-size:11px;color:#aaa;" +
                    "font-family:monospace;background:#111;";
                infoEl.textContent = "No video selected";
                infoEl.setAttribute("role", "status");
                infoEl.setAttribute("aria-live", "polite");

                previewContainer.appendChild(videoEl);
                previewContainer.appendChild(infoEl);

                // Add download overlay
                addDownloadOverlay(previewContainer, videoEl);

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
                        _srcMeta = null;
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

                // Create hidden file input (without onchange yet)
                const fileInput = document.createElement("input");
                Object.assign(fileInput, {
                    type: "file",
                    accept: videoAccept,
                    style: "display: none",
                });
                document.body.append(fileInput);

                // Cleanup file input and poll interval when node is removed
                const origOnRemoved = this.onRemoved;
                this.onRemoved = function () {
                    clearInterval(lvPollInterval);
                    fileInput?.remove();
                    origOnRemoved?.apply(this, arguments);
                };

                // Add upload button widget (DOM)
                const uploadBtn = document.createElement("button");
                uploadBtn.innerHTML = "Upload Video...";
                uploadBtn.setAttribute("aria-label", "Upload Video");
                uploadBtn.style.cssText = `
                    width: 100%;
                    margin-top: 4px;
                    background-color: #222;
                    color: #ccc;
                    border: 1px solid #333;
                    border-radius: 4px;
                    padding: 6px;
                    cursor: pointer;
                    font-family: monospace;
                    font-size: 12px;
                    transition: background-color 0.2s;
                `;
                // Hover and Focus effect
                let isHovered = false;
                let isFocused = false;
                const updateBtn = () => {
                    if (uploadBtn.disabled) return;
                    const active = isHovered || isFocused;
                    uploadBtn.style.backgroundColor = active ? "#333" : "#222";
                    uploadBtn.style.outline = isFocused ? "2px solid #4a6a8a" : "none";
                };
                uploadBtn.onmouseenter = () => { isHovered = true; updateBtn(); };
                uploadBtn.onmouseleave = () => { isHovered = false; updateBtn(); };
                uploadBtn.onfocus = () => { isFocused = true; updateBtn(); };
                uploadBtn.onblur = () => { isFocused = false; updateBtn(); };

                uploadBtn.onclick = (e) => {
                    // Stop propagation to prevent node selection issues on click
                    // (though usually handled by DOM widget logic)
                    fileInput.click();
                };

                // Prevent node dragging when clicking/dragging the button
                uploadBtn.onpointerdown = (e) => e.stopPropagation();

                const uploadWidget = this.addDOMWidget("upload_button", "btn", uploadBtn, {
                    serialize: false,
                });

                // Helper to set upload state
                const setUploadState = (isUploading, filename = "") => {
                    if (isUploading) {
                        uploadBtn.innerHTML = `<span aria-hidden="true">⏳</span> Uploading...`;
                        uploadBtn.setAttribute("aria-label", "Uploading Video");
                        uploadBtn.disabled = true;
                        uploadBtn.style.cursor = "wait";
                        infoEl.textContent = `Uploading ${filename}...`;
                        previewContainer.style.display = ""; // Ensure info is visible
                        videoEl.style.display = "none";      // Hide stale video
                    } else {
                        uploadBtn.innerHTML = "Upload Video...";
                        uploadBtn.setAttribute("aria-label", "Upload Video");
                        uploadBtn.disabled = false;
                        uploadBtn.style.cursor = "pointer";
                        videoEl.style.display = "block";     // Restore video visibility
                    }
                    node.setDirtyCanvas(true, true);
                    // Force resize to fit infoEl if needed
                    node.setSize([
                        node.size[0],
                        node.computeSize([node.size[0], node.size[1]])[1],
                    ]);
                };

                // Handle file upload (shared logic)
                const handleUpload = async (file) => {
                    setUploadState(true, file.name);
                    const body = new FormData();
                    body.append("image", file);

                    try {
                        const resp = await fetch("/upload/image", {
                            method: "POST",
                            body: body,
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
                            videoWidget.callback?.(filename);
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

                // Attach handlers
                fileInput.onchange = async () => {
                    if (fileInput.files.length) {
                        await handleUpload(fileInput.files[0]);
                    }
                };

                // Support drag-and-drop of video files onto the node
                this.onDragOver = (e) => {
                    if (e?.dataTransfer?.types?.includes?.("Files")) {
                        // Visual feedback on the button
                        if (!uploadBtn.disabled) {
                            if (!Object.prototype.hasOwnProperty.call(uploadBtn, '_originalInnerHTML')) {
                                uploadBtn._originalInnerHTML = uploadBtn.innerHTML;
                            }
                            if (!Object.prototype.hasOwnProperty.call(uploadBtn, '_originalBorder')) {
                                uploadBtn._originalBorder = uploadBtn.style.border;
                            }
                            if (!Object.prototype.hasOwnProperty.call(uploadBtn, '_originalAriaLabel')) {
                                uploadBtn._originalAriaLabel = uploadBtn.getAttribute("aria-label");
                            }

                            uploadBtn.innerHTML = `<span aria-hidden="true">📂</span> Drop to Upload`;
                            uploadBtn.setAttribute("aria-label", "Drop to Upload");
                            uploadBtn.style.border = "1px dashed #4a6a8a";
                            uploadBtn.style.backgroundColor = "#333";

                            // Reset after short delay (debounce)
                            if (uploadBtn._dragTimeout) clearTimeout(uploadBtn._dragTimeout);
                            uploadBtn._dragTimeout = setTimeout(() => {
                                if (!uploadBtn.disabled) {
                                    if (Object.prototype.hasOwnProperty.call(uploadBtn, '_originalInnerHTML')) {
                                        uploadBtn.innerHTML = uploadBtn._originalInnerHTML;
                                        delete uploadBtn._originalInnerHTML;
                                    }
                                    if (Object.prototype.hasOwnProperty.call(uploadBtn, '_originalBorder')) {
                                        uploadBtn.style.border = uploadBtn._originalBorder;
                                        delete uploadBtn._originalBorder;
                                    }
                                    if (Object.prototype.hasOwnProperty.call(uploadBtn, '_originalAriaLabel')) {
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

                    return await handleUpload(file);
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

                    // Update video preview if upstream video was used
                    // (backend copies upstream file to temp for /view)
                    if (data?.video?.[0]) {
                        const v = data.video[0];
                        const params = new URLSearchParams({
                            filename: v.filename,
                            subfolder: v.subfolder || "",
                            type: v.type || "input",
                            timestamp: String(Date.now()),
                        });
                        previewContainer.style.display = "";
                        videoEl.src = api.apiURL("/view?" + params.toString());
                    }

                    if (data?.video_info?.[0]) {
                        const info = data.video_info[0];
                        // Update cached metadata with accurate backend values
                        _srcMeta = {
                            width: info.source_width || _srcMeta?.width || 0,
                            height: info.source_height || _srcMeta?.height || 0,
                            fps: info.source_fps || _srcMeta?.fps || 24,
                            duration: info.source_duration || _srcMeta?.duration || 0,
                            frames: info.source_frames || _srcMeta?.frames || 0,
                        };
                        updateDynamicInfo();
                    }
                };

                // --- Video preview context menu ---
                const getVideoUrlLoad = () => videoEl.src || null;
                addVideoPreviewMenu(node, videoEl, previewContainer, previewWidget, getVideoUrlLoad, infoEl);

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
                    "overflow:hidden;display:none;position:relative;";

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
                infoEl.setAttribute("role", "status");
                infoEl.setAttribute("aria-live", "polite");

                previewContainer.appendChild(videoEl);
                previewContainer.appendChild(infoEl);

                // Add download overlay
                addDownloadOverlay(previewContainer, videoEl);

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
                addVideoPreviewMenu(node, videoEl, previewContainer, previewWidget, getVideoUrlSave, infoEl);

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
                    label.textContent = "Font Color";
                    label.style.cssText = `
                        color: #b0b0b0;
                        font: 12px Arial, sans-serif;
                        flex-shrink: 0;
                    `;

                    // Color input
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

                    // Hex display
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

                    // Focus styles
                    hexLabel.onfocus = () => { hexLabel.style.boxShadow = "0 0 0 1px #4a6a8a"; };
                    hexLabel.onblur = () => { hexLabel.style.boxShadow = "none"; };

                    // Copy handler
                    const copyHex = async () => {
                        const currentHex = colorInput.value.toUpperCase();
                        try {
                            if (navigator.clipboard) {
                                await navigator.clipboard.writeText(currentHex);
                                flashNode(node, "#4a7a4a"); // Green flash

                                // Temporary feedback
                                hexLabel.textContent = "COPIED";
                                hexLabel.style.color = "#8f8";
                                hexLabel.setAttribute("aria-label", "Copied successfully");

                                setTimeout(() => {
                                    // Only restore if still showing "COPIED"
                                    if (hexLabel.textContent === "COPIED") {
                                        hexLabel.textContent = currentHex;
                                        hexLabel.style.color = "#ccc";
                                        hexLabel.setAttribute("aria-label", "Copy color hex code");
                                    }
                                }, 800);
                            }
                        } catch (err) {
                            console.error("Failed to copy hex:", err);
                            flashNode(node, "#7a3a3a"); // Red flash
                        }
                    };

                    // Click to copy handler
                    hexLabel.onclick = copyHex;

                    // Keyboard handler (Enter or Space)
                    hexLabel.onkeydown = (e) => {
                        if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            copyHex();
                        }
                    };

                    container.appendChild(label);
                    container.appendChild(colorInput);
                    container.appendChild(hexLabel);

                    // Store refs for preset system
                    node._ffmpegaColorInput = colorInput;
                    node._ffmpegaHexLabel = hexLabel;

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

            // --- Text Preset Context Menu ---
            const BUILTIN_PRESETS = [
                {
                    name: "📄 SRT Subtitle Example",
                    auto_mode: false, mode: "subtitle",
                    position: "bottom_center", font_size: 28, font_color: "#FFFFFF",
                    text: "1\n00:00:01,000 --> 00:00:04,000\nThis is the first subtitle line.\n\n2\n00:00:05,000 --> 00:00:08,000\nAnd here is the second one.\n\n3\n00:00:09,000 --> 00:00:12,000\nEdit these timestamps to match your video!",
                },
                {
                    name: "🎬 Cinematic Subtitles",
                    auto_mode: false, mode: "subtitle",
                    position: "bottom_center", font_size: 28, font_color: "#FFFFFF",
                    text: "1\n00:00:01,000 --> 00:00:03,500\nThe world was never the same.\n\n2\n00:00:04,000 --> 00:00:07,000\nSomething had changed — forever.",
                },
                {
                    name: "💧 Bold Watermark",
                    auto_mode: false, mode: "watermark",
                    position: "bottom_right", font_size: 18, font_color: "#CCCCCC",
                    text: "© Your Name",
                },
                {
                    name: "🎯 Title Card",
                    auto_mode: false, mode: "title_card",
                    position: "center", font_size: 72, font_color: "#FFFFFF",
                    text: "YOUR TITLE HERE",
                },
                {
                    name: "📱 Social Caption",
                    auto_mode: false, mode: "subtitle",
                    position: "bottom_center", font_size: 36, font_color: "#FFE800",
                    text: "1\n00:00:00,500 --> 00:00:03,000\nWait for it... 👀\n\n2\n00:00:03,500 --> 00:00:06,000\nDid you see that?! 🔥",
                },
                {
                    name: "😂 Meme Text",
                    auto_mode: false, mode: "overlay",
                    position: "top", font_size: 48, font_color: "#FFFFFF",
                    text: "TOP TEXT GOES HERE",
                },
                {
                    name: "📐 Minimal Lower Third",
                    auto_mode: false, mode: "overlay",
                    position: "bottom_left", font_size: 22, font_color: "#DDDDDD",
                    text: "Speaker Name\nJob Title",
                },
                {
                    name: "©️ Copyright Notice",
                    auto_mode: false, mode: "watermark",
                    position: "bottom_center", font_size: 16, font_color: "#AAAAAA",
                    text: "© 2025 All Rights Reserved",
                },
                {
                    name: "🎬 Credits Roll",
                    auto_mode: false, mode: "subtitle",
                    position: "center", font_size: 32, font_color: "#FFFFFF",
                    text: "1\n00:00:01,000 --> 00:00:03,000\nDirected by\nYour Name\n\n2\n00:00:04,000 --> 00:00:06,000\nProduced by\nYour Name\n\n3\n00:00:07,000 --> 00:00:09,000\nMusic by\nArtist Name",
                },
                {
                    name: "📌 Chapter Marker",
                    auto_mode: false, mode: "overlay",
                    position: "top_left", font_size: 24, font_color: "#FFFFFF",
                    text: "Chapter 1: Introduction",
                    start_time: 0.0, end_time: 5.0,
                },
            ];

            const applyPreset = (node, preset) => {
                // Apply in priority order: auto_mode first (it may affect visibility)
                const order = ["auto_mode", "mode", "position", "font_size", "font_color", "text", "start_time", "end_time"];
                const keys = order.filter(k => k in preset);
                for (const k of Object.keys(preset)) {
                    if (k !== "name" && !keys.includes(k)) keys.push(k);
                }

                for (const key of keys) {
                    const w = node.widgets?.find(ww => ww.name === key);
                    if (!w) continue;
                    const val = preset[key];

                    // Set the widget's internal value
                    w.value = val;

                    if (key === "font_color") {
                        // Update color picker DOM elements directly
                        // (w.setValue is wrapped by DOMWidgetImpl and crashes)
                        try {
                            const ci = node._ffmpegaColorInput;
                            const hl = node._ffmpegaHexLabel;
                            if (ci && val?.startsWith?.("#")) {
                                ci.value = val;
                                if (hl) {
                                    hl.textContent = val.toUpperCase();
                                    hl.style.color = "#ccc";
                                }
                            }
                        } catch (e) { /* ignore */ }
                    } else if (w.inputEl) {
                        // ComfyUI stores textarea/input as w.inputEl
                        w.inputEl.value = val;
                        w.inputEl.dispatchEvent(new Event("input", { bubbles: true }));
                    } else if (w.element) {
                        // DOM widget — element could BE the input or contain it
                        const el = w.element;
                        const tag = el.tagName?.toLowerCase();
                        if (tag === "textarea" || tag === "input") {
                            el.value = val;
                            el.dispatchEvent(new Event("input", { bubbles: true }));
                        } else {
                            const input = el.querySelector?.("textarea, input");
                            if (input) {
                                input.value = val;
                                input.dispatchEvent(new Event("input", { bubbles: true }));
                            }
                        }
                    }
                }

                // Force visual refresh
                node.setDirtyCanvas(true, true);
                app.graph.setDirtyCanvas(true, true);
                flashNode(node, "#4a7a4a");
            };

            let _customPresets = []; // cache

            // Eagerly fetch custom presets on load
            fetch(api.apiURL("/ffmpega/text_presets"))
                .then(r => r.json())
                .then(data => { _customPresets = Array.isArray(data) ? data : []; })
                .catch(() => { _customPresets = []; });

            const saveCustomPreset = async (node) => {
                const name = prompt("Preset name:");
                if (!name?.trim()) return;

                const preset = { name: name.trim() };
                for (const key of ["auto_mode", "mode", "position", "font_size", "font_color"]) {
                    const w = node.widgets?.find(ww => ww.name === key);
                    if (w) {
                        preset[key] = typeof w.getValue === "function" ? w.getValue() : w.value;
                    }
                }

                // Replace if same name exists
                const idx = _customPresets.findIndex(p => p.name === preset.name);
                if (idx >= 0) {
                    _customPresets[idx] = preset;
                } else {
                    _customPresets.push(preset);
                }

                try {
                    await fetch(api.apiURL("/ffmpega/text_presets"), {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(_customPresets),
                    });
                    flashNode(node, "#4a7a4a");
                } catch (err) {
                    console.warn("FFMPEGA: preset save failed", err);
                    flashNode(node, "#7a4a4a");
                }
            };

            const deleteCustomPreset = async (node, presetName) => {
                const idx = _customPresets.findIndex(p => p.name === presetName);
                if (idx < 0) return;
                _customPresets.splice(idx, 1);
                try {
                    await fetch(api.apiURL("/ffmpega/text_presets"), {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(_customPresets),
                    });
                    flashNode(node, "#4a7a4a");
                } catch {
                    flashNode(node, "#7a4a4a");
                }
            };

            const origGetMenuText = nodeType.prototype.getExtraMenuOptions;
            nodeType.prototype.getExtraMenuOptions = function (_, options) {
                origGetMenuText?.apply(this, arguments);
                const self = this;

                // Build submenu items synchronously from cache
                const presetItems = [];

                // Built-in presets
                for (const p of BUILTIN_PRESETS) {
                    presetItems.push({
                        content: p.name,
                        callback: () => applyPreset(self, p),
                    });
                }

                // Custom presets
                if (_customPresets.length > 0) {
                    for (const p of _customPresets) {
                        presetItems.push({
                            content: `⭐ ${p.name}`,
                            submenu: {
                                options: [
                                    {
                                        content: "✅ Load",
                                        callback: () => applyPreset(self, p),
                                    },
                                    {
                                        content: "🗑️ Delete",
                                        callback: () => deleteCustomPreset(self, p.name),
                                    },
                                ],
                            },
                        });
                    }
                }

                options.unshift(
                    {
                        content: "💾 Save Current as Preset",
                        callback: () => saveCustomPreset(self),
                    },
                    {
                        content: "🎨 Load Preset",
                        submenu: {
                            options: presetItems,
                        },
                    },
                    {
                        content: "🧹 Clear Text",
                        callback: () => {
                            const defaults = {
                                text: "", mode: "overlay", position: "bottom_center",
                                font_size: 24, font_color: "#FFFFFF", auto_mode: true,
                            };
                            for (const [key, val] of Object.entries(defaults)) {
                                const w = self.widgets?.find(ww => ww.name === key);
                                if (!w) continue;
                                w.value = val;
                                if (key === "font_color") {
                                    try {
                                        const ci = self._ffmpegaColorInput;
                                        const hl = self._ffmpegaHexLabel;
                                        if (ci) { ci.value = val; }
                                        if (hl) { hl.textContent = val; hl.style.color = "#ccc"; }
                                    } catch { }
                                } else if (w.inputEl) {
                                    w.inputEl.value = val;
                                } else if (w.element) {
                                    const tag = w.element.tagName?.toLowerCase();
                                    if (tag === "textarea" || tag === "input") {
                                        w.element.value = val;
                                    }
                                }
                            }
                            self.setDirtyCanvas(true, true);
                            app.graph.setDirtyCanvas(true, true);
                            flashNode(self, "#4a7a4a");
                        },
                    },
                    null, // separator
                );
            };
        }

        // ------------------------------------------------------------------
        //  Point Selector popout for LoadImagePath & LoadVideoPath nodes
        // ------------------------------------------------------------------

        /** Open a modal popout where the user clicks to place positive/negative
         *  points on the image (or first video frame), OR paint a mask directly.
         *  Data is stored as JSON in the node's hidden mask_points_data widget.
         *  @param {object} node   - the ComfyUI node
         *  @param {string} imgSrc - data-URL or URL for the first frame
         *  @param {string} [videoSrc] - optional video URL for last-frame extraction
         */
        function openPointSelector(node, imgSrc, videoSrc) {
            // Remove any existing popout
            document.getElementById("ffmpega-point-selector")?.remove();

            // Existing data
            let existing = {
                points: [], labels: [], image_width: 0, image_height: 0,
            };
            const mpWidget = node.widgets?.find(w => w.name === "mask_points_data");
            if (mpWidget?.value) {
                try { existing = JSON.parse(mpWidget.value); } catch { }
            }

            // Determine initial mode
            let mode = existing.mode || "points"; // "points" or "draw"

            // Build the modal
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

            // Header bar
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

            // Canvas container
            const canvasWrap = document.createElement("div");
            canvasWrap.style.cssText = "position:relative;max-width:90vw;max-height:75vh;";
            const canvas = document.createElement("canvas");
            canvas.style.cssText = "max-width:90vw;max-height:75vh;cursor:crosshair;display:block;";
            canvasWrap.appendChild(canvas);
            overlay.appendChild(canvasWrap);

            // Brush size slider (draw mode only)
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
            sizeSlider.oninput = () => { sizeLabel.textContent = `${sizeSlider.value}px`; };
            sliderWrap.appendChild(sizeSlider);
            sliderWrap.appendChild(sizeLabel);
            overlay.appendChild(sliderWrap);

            // Status bar
            const statusBar = document.createElement("div");
            statusBar.style.cssText = "color:#aaa;font-size:12px;margin-top:6px;";
            statusBar.textContent = "Loading image...";
            statusBar.setAttribute("role", "status");
            statusBar.setAttribute("aria-live", "polite");
            overlay.appendChild(statusBar);

            // Button bar
            const btnBar = document.createElement("div");
            btnBar.style.cssText = "display:flex;gap:12px;margin-top:12px;";

            const makeBtn = (label, bg) => {
                const b = document.createElement("button");
                b.textContent = label;
                b.style.cssText = `
                    padding:8px 24px;border:none;border-radius:6px;
                    font-size:14px;cursor:pointer;color:#fff;
                    background:${bg};font-weight:600;
                    transition:opacity 0.15s;
                `;
                let isHovered = false;
                let isFocused = false;
                const update = () => {
                    const active = isHovered || isFocused;
                    b.style.opacity = active ? "0.85" : "1";
                    b.style.boxShadow = isFocused ? "0 0 0 2px #fff" : "none";
                };
                b.onmouseenter = () => { isHovered = true; update(); };
                b.onmouseleave = () => { isHovered = false; update(); };
                b.onfocus = () => { isFocused = true; update(); };
                b.onblur = () => { isFocused = false; update(); };
                return b;
            };
            const modeToggle = makeBtn("🖌 Draw", "#3a5a8a");
            const clearBtn = makeBtn("Clear All", "#555");
            const applyBtn = makeBtn("✓ Apply", "#2a7a2a");
            const cancelBtn = makeBtn("Cancel", "#7a2a2a");
            btnBar.appendChild(modeToggle);
            btnBar.appendChild(clearBtn);
            btnBar.appendChild(applyBtn);
            btnBar.appendChild(cancelBtn);
            overlay.appendChild(btnBar);
            document.body.appendChild(overlay);

            // ── State ──
            let pts = existing.points ? [...existing.points] : [];
            let lbls = existing.labels ? [...existing.labels] : [];
            let imgW = 0, imgH = 0;
            let scaleX = 1, scaleY = 1;
            const firstImg = new Image();

            // Offscreen mask canvas (full image resolution, black/white)
            const maskOff = document.createElement("canvas");
            let maskDirty = false;

            // Cached green overlay (regenerated only when mask changes)
            let _greenOverlay = null;
            let _greenOverlayDirty = true;

            // ── Mode toggle ──
            const updateModeUI = () => {
                if (mode === "points") {
                    modeToggle.textContent = "🖌 Draw";
                    modeToggle.style.background = "#3a5a8a";
                    canvas.style.cursor = "crosshair";
                    sliderWrap.style.display = "none";
                } else {
                    modeToggle.textContent = "🎯 Points";
                    modeToggle.style.background = "#5a3a8a";
                    canvas.style.cursor = "none"; // custom brush cursor
                    sliderWrap.style.display = "flex";
                }
                updateHeader();
                redraw();
            };

            modeToggle.onclick = () => {
                mode = mode === "points" ? "draw" : "points";
                updateModeUI();
            };

            // ── Redraw ──
            const redraw = () => {
                const ctx = canvas.getContext("2d");
                ctx.clearRect(0, 0, canvas.width, canvas.height);

                // Draw the image
                if (firstImg.complete && firstImg.naturalWidth > 0) {
                    ctx.drawImage(firstImg, 0, 0, canvas.width, canvas.height);
                }

                if (mode === "points") {
                    // Draw points
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
                    // Draw cached green overlay (regenerate only when dirty)
                    if (_greenOverlayDirty || !_greenOverlay) {
                        _greenOverlay = document.createElement("canvas");
                        _greenOverlay.width = canvas.width;
                        _greenOverlay.height = canvas.height;
                        const tmpCtx = _greenOverlay.getContext("2d");
                        tmpCtx.drawImage(maskOff, 0, 0, canvas.width, canvas.height);
                        const imgData = tmpCtx.getImageData(0, 0, canvas.width, canvas.height);
                        for (let i = 0; i < imgData.data.length; i += 4) {
                            if (imgData.data[i] > 128) {
                                imgData.data[i] = 0;       // R
                                imgData.data[i + 1] = 220;  // G
                                imgData.data[i + 2] = 80;   // B
                                imgData.data[i + 3] = 100;  // A
                            } else {
                                imgData.data[i + 3] = 0; // transparent
                            }
                        }
                        tmpCtx.putImageData(imgData, 0, 0);
                        _greenOverlayDirty = false;
                    }
                    ctx.drawImage(_greenOverlay, 0, 0);

                    statusBar.textContent = `Draw mode | ${imgW}×${imgH} | Brush: ${sizeSlider.value}px`;
                }
            };

            // ── Canvas sizing ──
            const fitCanvas = (w, h) => {
                imgW = w;
                imgH = h;
                const maxW = window.innerWidth * 0.9;
                const maxH = window.innerHeight * 0.75;
                let dispW = imgW, dispH = imgH;
                if (dispW > maxW) { const r = maxW / dispW; dispW *= r; dispH *= r; }
                if (dispH > maxH) { const r = maxH / dispH; dispW *= r; dispH *= r; }
                canvas.width = Math.round(dispW);
                canvas.height = Math.round(dispH);
                scaleX = imgW / canvas.width;
                scaleY = imgH / canvas.height;

                // Init offscreen mask at full image resolution
                maskOff.width = imgW;
                maskOff.height = imgH;
                const mCtx = maskOff.getContext("2d");
                mCtx.fillStyle = "#000";
                mCtx.fillRect(0, 0, imgW, imgH);

                // Restore existing mask data if present
                if (existing.mask_data && existing.mode === "draw") {
                    const maskImg = new Image();
                    maskImg.onload = () => {
                        mCtx.drawImage(maskImg, 0, 0, imgW, imgH);
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

            // ── Drawing state ──
            let isDrawing = false;
            let drawButton = -1; // 0=left(paint), 2=right(erase)
            let lastDrawX = -1, lastDrawY = -1;

            const paintOnMask = (canvasX, canvasY, erase) => {
                const mCtx = maskOff.getContext("2d");
                // Convert display coords → full-res mask coords
                const mx = canvasX * scaleX;
                const my = canvasY * scaleY;
                const brushR = parseInt(sizeSlider.value) * scaleX; // scale brush to image res

                mCtx.beginPath();
                mCtx.arc(mx, my, brushR, 0, Math.PI * 2);
                if (erase) {
                    mCtx.fillStyle = "#000";
                } else {
                    mCtx.fillStyle = "#fff";
                }
                mCtx.fill();
                maskDirty = true;

                // Incremental green overlay update — paint directly onto
                // the cached overlay instead of rebuilding all pixels.
                if (_greenOverlay) {
                    const oCtx = _greenOverlay.getContext("2d");
                    const dispBrushR = parseInt(sizeSlider.value);
                    if (erase) {
                        // Clip to circle so erase matches the circular mask
                        oCtx.save();
                        oCtx.beginPath();
                        oCtx.arc(canvasX, canvasY, dispBrushR, 0, Math.PI * 2);
                        oCtx.clip();
                        oCtx.clearRect(
                            canvasX - dispBrushR, canvasY - dispBrushR,
                            dispBrushR * 2, dispBrushR * 2,
                        );
                        oCtx.restore();
                    } else {
                        oCtx.beginPath();
                        oCtx.arc(canvasX, canvasY, dispBrushR, 0, Math.PI * 2);
                        // Alpha 100/255 ≈ 0.392 — matches full-rebuild path
                        oCtx.fillStyle = "rgba(0, 220, 80, 0.392)";
                        oCtx.fill();
                    }
                } else {
                    _greenOverlayDirty = true;
                }
            };

            const paintLine = (x1, y1, x2, y2, erase) => {
                // Interpolate between last and current for smooth strokes
                const dist = Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);
                const steps = Math.max(1, Math.floor(dist / 3));
                for (let i = 0; i <= steps; i++) {
                    const t = i / steps;
                    const x = x1 + (x2 - x1) * t;
                    const y = y1 + (y2 - y1) * t;
                    paintOnMask(x, y, erase);
                }
            };

            // ── Mouse events ──
            const getCanvasPos = (e) => {
                const rect = canvas.getBoundingClientRect();
                const cssScaleX = canvas.width / rect.width;
                const cssScaleY = canvas.height / rect.height;
                return {
                    x: (e.clientX - rect.left) * cssScaleX,
                    y: (e.clientY - rect.top) * cssScaleY,
                };
            };

            // Click handling — find if near existing point (within 20px radius)
            const HIT_RADIUS = 20;
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

                    // Draw brush cursor
                    const ctx = canvas.getContext("2d");
                    ctx.beginPath();
                    ctx.arc(pos.x, pos.y, parseInt(sizeSlider.value), 0, Math.PI * 2);
                    ctx.strokeStyle = e.button === 2 ? "rgba(255,80,80,0.7)" : "rgba(80,255,120,0.7)";
                    ctx.lineWidth = 2;
                    ctx.stroke();
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

                    // Always show brush cursor
                    const ctx = canvas.getContext("2d");
                    const brushR = parseInt(sizeSlider.value);
                    ctx.beginPath();
                    ctx.arc(pos.x, pos.y, brushR, 0, Math.PI * 2);
                    ctx.strokeStyle = isDrawing
                        ? (drawButton === 2 ? "rgba(255,80,80,0.7)" : "rgba(80,255,120,0.7)")
                        : "rgba(255,255,255,0.5)";
                    ctx.lineWidth = 2;
                    ctx.stroke();
                }
            });

            const stopDrawing = () => {
                isDrawing = false;
                drawButton = -1;
                lastDrawX = -1;
                lastDrawY = -1;
            };

            canvas.addEventListener("mouseup", stopDrawing);
            canvas.addEventListener("mouseleave", () => {
                stopDrawing();
                if (mode === "draw") redraw(); // clear cursor
            });

            // Points mode click
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

            // Click outside image/buttons to close
            overlay.addEventListener("click", (e) => {
                if (e.target === overlay) {
                    document.removeEventListener("keydown", keyHandler);
                    overlay.remove();
                }
            });
            overlay.addEventListener("contextmenu", e => e.preventDefault());

            // ── Buttons ──
            clearBtn.onclick = () => {
                if (mode === "points") {
                    pts.length = 0;
                    lbls.length = 0;
                } else {
                    // Clear mask
                    const mCtx = maskOff.getContext("2d");
                    mCtx.fillStyle = "#000";
                    mCtx.fillRect(0, 0, maskOff.width, maskOff.height);
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
                    // Export mask as base64 PNG
                    const maskDataUrl = maskOff.toDataURL("image/png");
                    const b64 = maskDataUrl.split(",")[1];
                    data = JSON.stringify({
                        mode: "draw",
                        mask_data: b64,
                        image_width: imgW,
                        image_height: imgH,
                    });
                } else {
                    data = JSON.stringify({
                        mode: "points",
                        points: pts,
                        labels: lbls,
                        image_width: imgW,
                        image_height: imgH,
                    });
                }
                // Store in hidden widget
                if (mpWidget) {
                    mpWidget.value = data;
                } else {
                    const w = node.addWidget("text", "mask_points_data", data,
                        () => { }, { serialize: true });
                    w.type = "text";
                    if (w.computeSize) w.computeSize = () => [0, -4];
                }
                node.setDirtyCanvas(true, true);
                document.removeEventListener("keydown", keyHandler);
                overlay.remove();
                flashNode(node, "#2a7a2a");
            };

            // ESC to close
            const keyHandler = (e) => {
                if (e.key === "Escape") {
                    overlay.remove();
                    document.removeEventListener("keydown", keyHandler);
                }
            };
            document.addEventListener("keydown", keyHandler);
        }

        // --- LoadImagePath: Color styling + point selector context menu ---
        if (nodeData.name === "FFMPEGALoadImagePath") {
            const origOnCreatedImg = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const result = origOnCreatedImg?.apply(this, arguments);
                const node = this;
                this.color = "#3a5a5a";
                this.bgcolor = "#2a4a4a";

                // --- Dynamic output: hide "images" output until input connected ---
                const _syncImagesOutput = () => {
                    const imagesIn = node.findInputSlot("images");
                    const connected = imagesIn >= 0
                        && node.inputs[imagesIn].link != null;
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

                // Remove on creation
                requestAnimationFrame(() => {
                    const idx = node.findOutputSlot("images");
                    if (idx >= 0) node.removeOutput(idx);
                    node.setDirtyCanvas(true, true);
                });

                // React to connection changes
                const origOnCCImg = this.onConnectionsChange;
                this.onConnectionsChange = function (type, slotIndex, isConnected, link, ioSlot) {
                    origOnCCImg?.apply(this, arguments);
                    if (type === LiteGraph.INPUT) {
                        const name = this.inputs?.[slotIndex]?.name;
                        if (name === "images") {
                            _syncImagesOutput();
                        }
                    }
                };

                // Restore on workflow load
                const origConfigureImg = this.onConfigure;
                this.onConfigure = function (data) {
                    origConfigureImg?.apply(this, arguments);
                    requestAnimationFrame(_syncImagesOutput);
                };

                // Handle execution results — update preview from upstream
                const origOnExecutedImg = this.onExecuted;
                this.onExecuted = function (data) {
                    origOnExecutedImg?.apply(this, arguments);

                    // If upstream image was used, the backend returns
                    // ui.images with type "temp" — update the native
                    // image preview widget if present
                    if (data?.images?.[0]) {
                        const img = data.images[0];
                        // ComfyUI's native image preview will pick this
                        // up automatically via the standard onExecuted
                        // mechanism, but we also update any custom
                        // preview elements if they exist
                        const imgWidgets = this.widgets?.filter(
                            w => w.name === "image_preview" || w.type === "preview",
                        );
                        if (imgWidgets?.length) {
                            const params = new URLSearchParams({
                                filename: img.filename,
                                subfolder: img.subfolder || "",
                                type: img.type || "input",
                                timestamp: String(Date.now()),
                            });
                            const src = api.apiURL("/view?" + params.toString());
                            for (const w of imgWidgets) {
                                if (w.element?.querySelector?.("img")) {
                                    w.element.querySelector("img").src = src;
                                }
                            }
                        }
                    }
                };

                return result;
            };
            const origGetMenuImg = nodeType.prototype.getExtraMenuOptions;
            nodeType.prototype.getExtraMenuOptions = function (_, options) {
                origGetMenuImg?.apply(this, arguments);
                const self = this;
                options.unshift({
                    content: "🎯 Open Point Selector",
                    callback: () => {
                        // Get the current image filename
                        const imgWidget = self.widgets?.find(w => w.name === "image");
                        const filename = imgWidget?.value;
                        if (!filename) {
                            flashNode(self, "#7a4a4a");
                            return;
                        }
                        const params = new URLSearchParams({
                            filename, type: "input",
                        });
                        const src = api.apiURL("/view?" + params.toString());
                        openPointSelector(self, src);
                    },
                }, null); // null = separator
            };
        }

        // --- LoadVideoPath: Add point selector context menu ---
        if (nodeData.name === "FFMPEGALoadVideoPath") {
            const origGetMenuVid = nodeType.prototype.getExtraMenuOptions;
            nodeType.prototype.getExtraMenuOptions = function (_, options) {
                origGetMenuVid?.apply(this, arguments);
                const self = this;
                options.unshift({
                    content: "🎯 Open Point Selector",
                    callback: () => {
                        // Get the current video filename
                        const vidWidget = self.widgets?.find(w => w.name === "video");
                        const filename = vidWidget?.value;
                        if (!filename) {
                            flashNode(self, "#7a4a4a");
                            return;
                        }
                        // Extract first frame via the server-side route
                        // (falls back to video thumbnail if route unavailable)
                        const params = new URLSearchParams({
                            filename, type: "input",
                        });
                        const src = api.apiURL("/view?" + params.toString());
                        // Use video element to grab first frame
                        const tmpVideo = document.createElement("video");
                        tmpVideo.crossOrigin = "anonymous";
                        tmpVideo.muted = true;
                        tmpVideo.preload = "auto";
                        tmpVideo.src = src;
                        tmpVideo.currentTime = 0.01; // seek past potential black frame
                        tmpVideo.addEventListener("seeked", () => {
                            clearTimeout(seekTimeout);
                            // Draw frame to canvas → data URL
                            const c = document.createElement("canvas");
                            c.width = tmpVideo.videoWidth;
                            c.height = tmpVideo.videoHeight;
                            c.getContext("2d").drawImage(tmpVideo, 0, 0);
                            const frameDataUrl = c.toDataURL("image/jpeg", 0.95);
                            openPointSelector(self, frameDataUrl, src);
                            tmpVideo.remove();
                        }, { once: true });
                        tmpVideo.addEventListener("error", () => {
                            clearTimeout(seekTimeout);
                            flashNode(self, "#7a4a4a");
                            tmpVideo.remove();
                        }, { once: true });
                        // Timeout: if seeked never fires (audio-only, invalid file),
                        // clean up after 10 seconds so the UI doesn't hang.
                        const seekTimeout = setTimeout(() => {
                            flashNode(self, "#7a4a4a");
                            tmpVideo.remove();
                        }, 10000);
                    },
                }, null);
            };
        }

        // --- FrameExtract: Add point selector context menu ---
        if (nodeData.name === "FFMPEGAFrameExtract") {
            const origGetMenuExtract = nodeType.prototype.getExtraMenuOptions;
            nodeType.prototype.getExtraMenuOptions = function (_, options) {
                origGetMenuExtract?.apply(this, arguments);
                const self = this;
                options.unshift({
                    content: "🎯 Open Point Selector",
                    callback: () => {
                        // Get the current video path
                        const pathWidget = self.widgets?.find(w => w.name === "video_path");
                        const videoPath = pathWidget?.value?.trim();
                        if (!videoPath) {
                            flashNode(self, "#7a4a4a");
                            return;
                        }
                        // Stream via /ffmpega/preview to get a playable video
                        const params = new URLSearchParams({
                            path: videoPath,
                            duration: "1",  // Only need first second
                        });
                        const src = api.apiURL("/ffmpega/preview?" + params.toString());
                        // Use video element to grab first frame
                        const tmpVideo = document.createElement("video");
                        tmpVideo.crossOrigin = "anonymous";
                        tmpVideo.muted = true;
                        tmpVideo.preload = "auto";
                        tmpVideo.src = src;
                        tmpVideo.currentTime = 0.01;
                        tmpVideo.addEventListener("seeked", () => {
                            clearTimeout(seekTimeout);
                            const c = document.createElement("canvas");
                            c.width = tmpVideo.videoWidth;
                            c.height = tmpVideo.videoHeight;
                            c.getContext("2d").drawImage(tmpVideo, 0, 0);
                            const frameDataUrl = c.toDataURL("image/jpeg", 0.95);
                            openPointSelector(self, frameDataUrl, src);
                            tmpVideo.remove();
                        }, { once: true });
                        tmpVideo.addEventListener("error", () => {
                            clearTimeout(seekTimeout);
                            flashNode(self, "#7a4a4a");
                            tmpVideo.remove();
                        }, { once: true });
                        const seekTimeout = setTimeout(() => {
                            flashNode(self, "#7a4a4a");
                            tmpVideo.remove();
                        }, 10000);
                    },
                }, null);
            };
        }

    },
});


console.log("FFMPEGA UI extensions loaded");
