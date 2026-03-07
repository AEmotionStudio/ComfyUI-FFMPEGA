/**
 * Shared UI helper functions for FFMPEGA node extensions.
 *
 * Extracted from the monolithic ffmpega_ui.js to enable per-node modularization.
 * These are used across multiple node handlers.
 */

import { api } from "comfyui/api";
import type { ComfyNode, ComfyWidget, ComfyMenuOption } from "@ffmpega/types/comfyui";

// ---- Internal types ----

/** Node with flash-tracking state */
interface FlashableNode extends ComfyNode {
    _isFlashing?: boolean;
    _previousPrompt?: string;
}

/** Extended widget with stored originals for toggle */
interface TogglableWidget extends ComfyWidget {
    _origType?: string;
    _origComputeSize?: ComfyWidget["computeSize"];
    hidden?: boolean;
}

/** Download overlay button with timeout tracking */
interface OverlayButton extends HTMLButtonElement {
    _timeout?: ReturnType<typeof setTimeout> | null;
}

// --- Constants ---

/** Alphabet for dynamic slot naming (image_a, image_b, etc.) */
export const SLOT_LABELS = "abcdefghijklmnopqrstuvwxyz";

/** Example prompts for the "Random Example" feature */
export const RANDOM_PROMPTS: string[] = [
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
    "Apply golden hour warm glow with a slow Ken Burns zoom",
];

// --- Widget visibility ---

/**
 * Toggle a ComfyUI widget's visibility using the standard LiteGraph pattern.
 * Hidden widgets get computeSize → [0, -4] so they collapse entirely.
 */
export function toggleWidget(widget: TogglableWidget | undefined, show: boolean): void {
    if (!widget) return;
    if (!widget._origType) {
        widget._origType = widget.type;
        widget._origComputeSize = widget.computeSize;
    }
    if (show) {
        widget.type = widget._origType!;
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

/**
 * Resize a node to fit its content height.
 */
export function fitHeight(node: ComfyNode): void {
    node.setSize([
        node.size[0],
        node.computeSize([node.size[0], node.size[1]])[1],
    ]);
    node?.graph?.setDirtyCanvas(true);
}

// --- Dynamic input slots ---

/**
 * Manage dynamic input slots (image_a → image_b → image_c, etc.)
 * When you connect image_a, image_b appears. Connect image_b → image_c appears.
 */
export function updateDynamicSlots(
    node: ComfyNode,
    prefix: string,
    slotType: string,
    excludePrefix: string[] | string = [],
): void {
    const excludes = Array.isArray(excludePrefix) ? excludePrefix : [excludePrefix];
    const matchingIndices: number[] = [];
    for (let i = 0; i < node.inputs.length; i++) {
        const name = node.inputs[i].name;
        if (name.startsWith(prefix)) {
            if (excludes.some(ep => name.startsWith(ep))) continue;
            matchingIndices.push(i);
        }
    }

    if (matchingIndices.length === 0) return;

    let lastConnectedGroupIdx = -1;
    for (let g = matchingIndices.length - 1; g >= 0; g--) {
        const slotIdx = matchingIndices[g];
        if (node.inputs[slotIdx].link != null) {
            lastConnectedGroupIdx = g;
            break;
        }
    }

    const needed = lastConnectedGroupIdx + 2;

    while (matchingIndices.length < needed) {
        const letter = SLOT_LABELS[matchingIndices.length];
        if (!letter) break;
        const newName = `${prefix}${letter}`;
        node.addInput(newName, slotType);
        matchingIndices.push(node.inputs.length - 1);
    }

    while (matchingIndices.length > needed && matchingIndices.length > 1) {
        const lastGroupIdx = matchingIndices.length - 1;
        const slotIdx = matchingIndices[lastGroupIdx];
        if (node.inputs[slotIdx].link != null) break;
        node.removeInput(slotIdx);
        matchingIndices.pop();
    }
}

// --- Prompt helpers ---

/**
 * Handle clipboard paste into a node's prompt widget.
 */
export function handlePaste(node: FlashableNode, replace: boolean): void {
    if (navigator.clipboard && navigator.clipboard.readText) {
        navigator.clipboard.readText()
            .then(text => {
                if (text) {
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
 * Set prompt text on a node (replace or append).
 */
export function setPrompt(
    node: FlashableNode,
    text: string,
    replace = false,
    color = "#4a5a7a",
): void {
    const promptWidget = node.widgets?.find((w: ComfyWidget) => w.name === "prompt");
    if (promptWidget) {
        if (replace) {
            if (promptWidget.value && String(promptWidget.value).trim() !== "") {
                node._previousPrompt = String(promptWidget.value);
            }
            promptWidget.value = text;
        } else {
            const currentText = String(promptWidget.value ?? "");
            if (!currentText || currentText.trim() === "") {
                promptWidget.value = text;
            } else if (!currentText.includes(text)) {
                promptWidget.value = currentText.trim() + " and " + text;
            }
        }
        node.setDirtyCanvas(true, true);
        flashNode(node, color);
    }
}

// --- Visual feedback ---

/**
 * Flash the node background for visual feedback.
 */
export function flashNode(node: FlashableNode, color = "#4a5a7a"): void {
    if (!node || node._isFlashing) return;

    node._isFlashing = true;
    const originalBg = node.bgcolor;

    node.bgcolor = color;
    node.setDirtyCanvas(true, true);

    setTimeout(() => {
        if (node.bgcolor === color) {
            node.bgcolor = originalBg;
        }
        node._isFlashing = false;
        node.setDirtyCanvas(true, true);
    }, 350);
}

// --- Video preview context menu ---

/**
 * Adds video preview context menu options to a node.
 * Shared between LoadVideoPath, FrameExtract, and SaveVideo nodes.
 */
export function addVideoPreviewMenu(
    node: ComfyNode,
    videoEl: HTMLVideoElement,
    previewContainer: HTMLElement,
    _previewWidget: ComfyWidget,
    getVideoUrl: () => string | null,
    infoEl: HTMLElement,
): void {
    const currentGetExtra = node.getExtraMenuOptions;

    node.getExtraMenuOptions = function (
        _canvas: unknown,
        options: (ComfyMenuOption | null)[],
    ): void {
        currentGetExtra?.apply(this, arguments as unknown as [unknown, (ComfyMenuOption | null)[]]);

        const optNew: (ComfyMenuOption | null)[] = [];
        const url = getVideoUrl();
        const hasVideo = !!url && previewContainer.style.display !== "none";

        // --- Sync Preview ---
        optNew.push({
            content: "🔄 Sync Preview",
            callback: () => {
                const videos = previewContainer.querySelectorAll("video");
                videos.forEach((v: HTMLVideoElement) => {
                    if (v.src) {
                        const oldSrc = v.src;
                        v.src = "";
                        v.src = oldSrc;
                        v.play().catch(() => { /* ignore */ });
                    }
                });
                flashNode(node, "#4a7a4a");
            },
        });

        if (hasVideo) {
            optNew.push(
                {
                    content: "🗒 Copy Video URL",
                    callback: () => {
                        navigator.clipboard.writeText(url!).catch(() => { /* ignore */ });
                        flashNode(node, "#4a5a7a");
                    },
                },
                {
                    content: "📏 Jump: Start",
                    callback: () => {
                        videoEl.currentTime = 0;
                        videoEl.play().catch(() => { /* ignore */ });
                        flashNode(node, "#4a5a7a");
                    },
                },
                {
                    content: "📏 Jump: Middle",
                    callback: () => {
                        const dur = videoEl.duration;
                        if (dur && isFinite(dur)) {
                            videoEl.currentTime = dur / 2;
                        }
                        flashNode(node, "#4a5a7a");
                    },
                },
                {
                    content: "📏 Jump: End",
                    callback: () => {
                        const dur = videoEl.duration;
                        if (dur && isFinite(dur)) {
                            videoEl.currentTime = Math.max(dur - 0.5, 0);
                        }
                        flashNode(node, "#4a5a7a");
                    },
                },
            );

            // --- Snapshot submenu ---
            optNew.push({
                content: "📸 Snapshot",
                submenu: {
                    options: [
                        {
                            content: "Copy Frame to Clipboard",
                            callback: async () => {
                                try {
                                    const c = document.createElement("canvas");
                                    c.width = videoEl.videoWidth;
                                    c.height = videoEl.videoHeight;
                                    const ctx = c.getContext("2d");
                                    if (!ctx) throw new Error("Canvas 2D context unavailable");
                                    ctx.drawImage(videoEl, 0, 0);
                                    const blob = await new Promise<Blob | null>(r => c.toBlob(r, "image/png"));
                                    if (!blob) throw new Error("toBlob returned null");
                                    await navigator.clipboard.write([
                                        new ClipboardItem({ "image/png": blob }),
                                    ]);
                                    flashNode(node, "#4a7a4a");
                                } catch (e) {
                                    console.error("Snapshot failed:", e);
                                    flashNode(node, "#7a4a4a");
                                }
                            },
                        },
                        {
                            content: "Download Frame as PNG",
                            callback: () => {
                                try {
                                    const c = document.createElement("canvas");
                                    c.width = videoEl.videoWidth;
                                    c.height = videoEl.videoHeight;
                                    const ctx = c.getContext("2d");
                                    if (!ctx) throw new Error("Canvas 2D context unavailable");
                                    ctx.drawImage(videoEl, 0, 0);
                                    const a = document.createElement("a");
                                    a.href = c.toDataURL("image/png");
                                    a.download = "frame.png";
                                    document.body.appendChild(a);
                                    a.click();
                                    setTimeout(() => a.remove(), 0);
                                    flashNode(node, "#4a7a4a");
                                } catch (e) {
                                    console.error("Download failed:", e);
                                    flashNode(node, "#7a4a4a");
                                }
                            },
                        },
                    ],
                },
            });

            // --- Speed submenu ---
            optNew.push({
                content: "⚡ Playback Speed",
                submenu: {
                    options: [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 4].map(s => ({
                        content: `${s}×`,
                        callback: () => {
                            videoEl.playbackRate = s;
                            flashNode(node, "#4a5a7a");
                        },
                    })),
                },
            });

            // --- Analysis submenu ---
            optNew.push({
                content: "📊 Video Info",
                submenu: {
                    options: [
                        {
                            content: "Copy Full Info",
                            callback: () => {
                                const dur = videoEl.duration;
                                const line = [
                                    `URL: ${url}`,
                                    `Resolution: ${videoEl.videoWidth}×${videoEl.videoHeight}`,
                                    `Duration: ${dur ? dur.toFixed(2) + "s" : "N/A"}`,
                                    `Current Time: ${videoEl.currentTime.toFixed(2)}s`,
                                    `Playback Rate: ${videoEl.playbackRate}×`,
                                    `Muted: ${videoEl.muted}`,
                                    `Loop: ${videoEl.loop}`,
                                ].join("\n");
                                navigator.clipboard.writeText(line).catch(() => { /* ignore */ });
                                flashNode(node, "#4a5a7a");
                            },
                        },
                    ],
                },
            });

            // --- Download ---
            optNew.push({
                content: "💾 Download Video",
                callback: () => {
                    const a = document.createElement("a");
                    a.href = url!;
                    a.download = "video.mp4";
                    try {
                        const params = new URL(a.href, window.location.href).searchParams;
                        const f = params.get("filename");
                        if (f) a.download = f;
                    } catch { /* ignore */ }
                    document.body.appendChild(a);
                    a.click();
                    setTimeout(() => a.remove(), 0);
                    flashNode(node, "#4a7a4a");
                },
            });
        }

        // Insert before existing items
        options.unshift(...optNew, null);
    };
}

// --- Download overlay ---

/**
 * Adds a download overlay button to a video container.
 */
export function addDownloadOverlay(
    container: HTMLElement,
    videoEl: HTMLVideoElement,
): void {
    const btn = document.createElement("button") as OverlayButton;
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

    let containerHover = false;
    let btnHover = false;
    let btnFocus = false;

    const updateStyle = (): void => {
        const isVisible = containerHover || btnFocus || btnHover;
        const isActive = btnHover || btnFocus;
        btn.style.opacity = isVisible ? "1" : "0";
        btn.style.background = isActive ? "rgba(0, 0, 0, 0.8)" : "rgba(0, 0, 0, 0.6)";
        btn.style.outline = btnFocus ? "2px solid #4a6a8a" : "none";
        btn.style.outlineOffset = btnFocus ? "2px" : "0px";
    };

    container.addEventListener("mouseenter", () => { containerHover = true; updateStyle(); });
    container.addEventListener("mouseleave", () => { containerHover = false; updateStyle(); });
    btn.addEventListener("mouseenter", () => { btnHover = true; updateStyle(); });
    btn.addEventListener("mouseleave", () => { btnHover = false; updateStyle(); });
    btn.addEventListener("focus", () => { btnFocus = true; updateStyle(); });
    btn.addEventListener("blur", () => { btnFocus = false; updateStyle(); });

    btn.onclick = (e: MouseEvent): void => {
        e.stopPropagation();
        e.preventDefault();
        if (videoEl.src) {
            const a = document.createElement("a");
            a.href = videoEl.src;
            a.download = "video.mp4";
            try {
                const params = new URL(a.href, window.location.href).searchParams;
                const f = params.get("filename");
                if (f) a.download = f;
            } catch { /* ignore */ }

            document.body.appendChild(a);
            a.click();
            setTimeout(() => a.remove(), 0);

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
