/**
 * Crop Selector modal.
 *
 * Full-screen modal that lets users draw / adjust a crop rectangle on a
 * video frame.  Reuses the CropOverlay class from the video editor.
 *
 * Data is stored as JSON (`{"x":N,"y":N,"w":N,"h":N}`) in the node's
 * hidden `crop_data` widget.
 *
 * Used by: LoadVideoPath, FrameExtract
 */

import { flashNode } from "@ffmpega/shared/ui_helpers";
import { CropOverlay } from "@ffmpega/videoeditor/CropOverlay";
import type { ComfyNode, ComfyWidget } from "@ffmpega/types/comfyui";

// ---- Types ----

interface CropSelectorNode extends ComfyNode {
    addWidget(
        type: string, name: string, value: unknown,
        callback: () => void, options?: { serialize?: boolean },
    ): ComfyWidget;
}

// ---- Helpers ----

/** Inject minimal veditor CSS if not already present (for standalone use). */
function ensureCropStyles(): void {
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

/** Capture a frame from a <video> at a given time and return a data-URL. */
function captureFrameAt(
    video: HTMLVideoElement,
    time: number,
): Promise<string> {
    return new Promise((resolve, reject) => {
        const onSeeked = (): void => {
            video.removeEventListener("seeked", onSeeked);
            const c = document.createElement("canvas");
            c.width = video.videoWidth;
            c.height = video.videoHeight;
            c.getContext("2d")!.drawImage(video, 0, 0);
            resolve(c.toDataURL("image/jpeg", 0.92));
        };
        video.addEventListener("seeked", onSeeked);
        video.currentTime = time;
        // Timeout fallback
        setTimeout(() => reject(new Error("Frame capture timed out")), 8000);
    });
}

// ---- Crop preview on node ----

/**
 * Apply a visual crop preview to the node's inline video preview.
 *
 * Uses CSS `object-fit: cover` + `object-position` to show only the
 * cropped region, plus a small badge showing the crop dimensions.
 * Call with `rect = null` to remove the preview.
 */
export function applyCropPreview(
    node: CropSelectorNode,
    rect: { x: number; y: number; w: number; h: number } | null,
): void {
    // Find the node's DOM element — it contains .ffmpega_preview
    const nodeEl = (node as unknown as { element?: HTMLElement }).element;
    // Try to find the preview container in the node's element tree
    const container = nodeEl?.querySelector?.(".ffmpega_preview")
        ?? document.querySelector(`[data-node-id="${node.id}"] .ffmpega_preview`);
    if (!container) return;

    const videoEl = container.querySelector("video") as HTMLVideoElement | null;
    if (!videoEl) return;

    // Remove any existing crop badge
    container.querySelector(".ffmpega-crop-badge")?.remove();

    if (!rect || rect.w <= 0 || rect.h <= 0) {
        // Clear crop preview
        videoEl.style.objectFit = "";
        videoEl.style.objectPosition = "";
        videoEl.style.transform = "";
        videoEl.style.clipPath = "";
        return;
    }

    // We need the source video dimensions to compute percentages
    const srcW = videoEl.videoWidth || 1920;
    const srcH = videoEl.videoHeight || 1080;

    // Calculate inset percentages for clip-path
    const top = (rect.y / srcH) * 100;
    const right = ((srcW - rect.x - rect.w) / srcW) * 100;
    const bottom = ((srcH - rect.y - rect.h) / srcH) * 100;
    const left = (rect.x / srcW) * 100;

    videoEl.style.clipPath = `inset(${top.toFixed(2)}% ${right.toFixed(2)}% ${bottom.toFixed(2)}% ${left.toFixed(2)}%)`;

    // Add a crop badge
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

// ---- Main export ----

/**
 * Open the crop selector modal.
 * @param node     - the ComfyUI node
 * @param videoSrc - URL to the video file (served by ComfyUI)
 */
export function openCropSelector(
    node: CropSelectorNode,
    videoSrc: string,
): void {
    ensureCropStyles();

    // Remove any existing crop selector
    document.getElementById("ffmpega-crop-selector")?.remove();

    // ── Load existing crop data ──
    let existingRect: { x: number; y: number; w: number; h: number } | null = null;
    const cdWidget = node.widgets?.find((w: ComfyWidget) => w.name === "crop_data");
    if (cdWidget?.value) {
        try {
            const parsed = JSON.parse(String(cdWidget.value));
            if (parsed && typeof parsed.x === "number") existingRect = parsed;
        } catch { /* ignore */ }
    }

    // ── Build modal ──
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

    // ── Header ──
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

    // ── Main content area (frame + controls side panel) ──
    const contentArea = document.createElement("div");
    contentArea.style.cssText = `
        display: flex; gap: 16px; align-items: flex-start;
        max-width: 95vw; max-height: 78vh;
    `;

    // ── Frame canvas area ──
    const canvasArea = document.createElement("div");
    canvasArea.style.cssText = `
        position: relative; display: flex;
        flex-direction: column; align-items: center;
    `;

    // Frame image (reference for sizing)
    const frameImg = document.createElement("img");
    frameImg.style.cssText = `
        max-width: 70vw; max-height: 68vh;
        display: block; border-radius: 4px;
        background: #000;
    `;

    // Canvas wrapper from CropOverlay will be positioned on top
    // We need a relative container
    const frameContainer = document.createElement("div");
    frameContainer.style.cssText = "position: relative; display: inline-block;";
    frameContainer.appendChild(frameImg);

    canvasArea.appendChild(frameContainer);

    // ── Frame scrubber ──
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

    // ── Side panel (CropOverlay controls) ──
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

    // ── Status bar ──
    const statusBar = document.createElement("div");
    statusBar.style.cssText = "color: #aaa; font-size: 12px; margin-top: 6px;";
    statusBar.textContent = "Loading video...";
    statusBar.setAttribute("role", "status");
    statusBar.setAttribute("aria-live", "polite");
    overlay.appendChild(statusBar);

    // ── Button bar ──
    const btnBar = document.createElement("div");
    btnBar.style.cssText = "display: flex; gap: 12px; margin-top: 12px;";

    const makeBtn = (label: string, ariaLabel: string, bg: string): HTMLButtonElement => {
        const b = document.createElement("button");
        b.innerHTML = label;
        b.setAttribute("aria-label", ariaLabel);
        b.style.cssText = `
            padding: 8px 24px; border: none; border-radius: 6px;
            font-size: 14px; cursor: pointer; color: #fff;
            background: ${bg}; font-weight: 600;
            transition: opacity 0.15s; outline: none;
        `;
        b.onmouseenter = (): void => { b.style.opacity = "0.85"; };
        b.onmouseleave = (): void => { b.style.opacity = "1"; };
        b.onfocus = (): void => { b.style.outline = "2px solid #fff"; b.style.outlineOffset = "2px"; };
        b.onblur = (): void => { b.style.outline = "none"; };
        return b;
    };

    const applyBtn = makeBtn(
        '<span aria-hidden="true">✓</span> Apply Crop',
        "Apply crop", "#2a7a2a",
    );
    const clearBtn = makeBtn("Clear", "Clear crop", "#555");
    const cancelBtn = makeBtn("Cancel", "Cancel", "#7a2a2a");
    btnBar.append(applyBtn, clearBtn, cancelBtn);
    overlay.appendChild(btnBar);

    document.body.appendChild(overlay);
    overlay.tabIndex = -1;
    overlay.focus();

    // ── Create CropOverlay ──
    let currentRect: { x: number; y: number; w: number; h: number } | null = existingRect;

    const cropOverlay = new CropOverlay({
        onCropChanged: (rect) => {
            currentRect = rect;
            if (rect) {
                statusBar.textContent =
                    `Crop: ${Math.round(rect.w)}×${Math.round(rect.h)} at (${Math.round(rect.x)}, ${Math.round(rect.y)})`;
            } else {
                statusBar.textContent = "No crop set";
            }
        },
    });

    // Mount controls into the side panel
    sidePanel.appendChild(cropOverlay.element);

    // ── Video loading ──
    const tmpVideo = document.createElement("video");
    tmpVideo.crossOrigin = "anonymous";
    tmpVideo.muted = true;
    tmpVideo.preload = "auto";
    tmpVideo.src = videoSrc;

    let videoDuration = 0;

    const onVideoReady = async (): Promise<void> => {
        videoDuration = tmpVideo.duration || 0;
        if (isFinite(videoDuration) && videoDuration > 0) {
            scrubSlider.max = String(Math.floor(videoDuration * 10));
        }

        // Capture initial frame (skip past potential black frame)
        try {
            const initialTime = Math.min(0.1, videoDuration * 0.01);
            const dataUrl = await captureFrameAt(tmpVideo, initialTime);
            frameImg.src = dataUrl;
        } catch {
            statusBar.textContent = "Failed to capture frame";
            statusBar.style.color = "#f44";
            return;
        }
    };

    // Wait for metadata, then capture first frame
    tmpVideo.addEventListener("loadedmetadata", () => {
        onVideoReady();
    }, { once: true });

    tmpVideo.addEventListener("error", () => {
        statusBar.textContent = "Failed to load video";
        statusBar.style.color = "#f44";
    }, { once: true });

    // When frame image loads, set up the crop overlay
    frameImg.onload = (): void => {
        const videoW = tmpVideo.videoWidth;
        const videoH = tmpVideo.videoHeight;

        // Size the canvas wrapper to match the displayed image size
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

        // Restore existing crop rect or auto-enable
        if (existingRect) {
            cropOverlay.setRect(existingRect);
        }

        statusBar.textContent = existingRect
            ? `Crop: ${existingRect.w}×${existingRect.h} at (${existingRect.x}, ${existingRect.y})`
            : `Video: ${videoW}×${videoH} — Enable crop in the panel →`;
    };

    // ── Frame scrubber interaction ──
    let scrubDebounce: ReturnType<typeof setTimeout> | null = null;
    scrubSlider.addEventListener("input", () => {
        const t = parseInt(scrubSlider.value, 10) / 10;
        timeLabel.textContent = `${t.toFixed(1)}s`;

        if (scrubDebounce) clearTimeout(scrubDebounce);
        scrubDebounce = setTimeout(async () => {
            try {
                const dataUrl = await captureFrameAt(tmpVideo, t);
                frameImg.src = dataUrl;
            } catch { /* ignore timeout */ }
        }, 150);
    });

    // ── Button handlers ──
    const cleanup = (): void => {
        document.removeEventListener("keydown", keyHandler);
        cropOverlay.destroy();
        tmpVideo.remove();
        overlay.remove();
    };

    applyBtn.onclick = (): void => {
        const rect = cropOverlay.getRect();
        const data = rect
            ? JSON.stringify({
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                w: Math.round(rect.w),
                h: Math.round(rect.h),
            })
            : "";

        if (cdWidget) {
            cdWidget.value = data;
        } else {
            const w = node.addWidget("text", "crop_data", data,
                () => { /* no-op */ }, { serialize: true });
            w.type = "text";
            if (w.computeSize) w.computeSize = () => [0, -4] as [number, number];
        }
        node.setDirtyCanvas(true, true);
        applyCropPreview(node, rect ? {
            x: Math.round(rect.x), y: Math.round(rect.y),
            w: Math.round(rect.w), h: Math.round(rect.h),
        } : null);
        cleanup();
        flashNode(node, "#2a7a2a");
    };

    clearBtn.onclick = (): void => {
        cropOverlay.setRect(null);
        currentRect = null;
        statusBar.textContent = "Crop cleared";
    };

    cancelBtn.onclick = cleanup;

    // Click outside to close
    overlay.addEventListener("click", (e: MouseEvent) => {
        if (e.target === overlay) cleanup();
    });
    overlay.addEventListener("contextmenu", (e: Event) => e.preventDefault());

    // ESC to close
    const keyHandler = (e: KeyboardEvent): void => {
        if (e.key === "Escape") cleanup();
    };
    document.addEventListener("keydown", keyHandler);
}
