/**
 * Point Selector / Mask Editor modal.
 *
 * A full-screen modal that allows users to:
 *  - Place include/exclude points on an image (SAM3 point prompts)
 *  - Paint a mask directly on the image
 *
 * Data is stored as JSON in the node's hidden mask_points_data widget.
 * Used by: LoadImagePath, LoadVideoPath, FrameExtract
 */

import { flashNode } from "@ffmpega/shared/ui_helpers";
import type { ComfyNode, ComfyWidget } from "@ffmpega/types/comfyui";

// ---- Types ----

type EditorMode = "points" | "draw";

/** Persisted data shape stored in the mask_points_data widget */
interface MaskPointsData {
    points: number[][];
    labels: number[];
    image_width: number;
    image_height: number;
    mode?: EditorMode;
    mask_data?: string;
}

/** Node with optional mask widget */
interface SelectorNode extends ComfyNode {
    addWidget(
        type: string, name: string, value: unknown,
        callback: () => void, options?: { serialize?: boolean },
    ): ComfyWidget;
}

// ---- Constants ----

const HIT_RADIUS = 20;

// ---- Implementation ----

/**
 * Open the point selector / mask editor modal.
 * @param node     - the ComfyUI node
 * @param imgSrc   - data-URL or URL for the first frame
 * @param videoSrc - optional video URL for last-frame extraction
 */
export function openPointSelector(
    node: SelectorNode,
    imgSrc: string,
    _videoSrc?: string,
): void {
    // Remove any existing popout
    document.getElementById("ffmpega-point-selector")?.remove();

    // Existing data
    let existing: MaskPointsData = {
        points: [], labels: [], image_width: 0, image_height: 0,
    };
    const mpWidget = node.widgets?.find((w: ComfyWidget) => w.name === "mask_points_data");
    if (mpWidget?.value) {
        try { existing = JSON.parse(String(mpWidget.value)); } catch { /* ignore */ }
    }

    // Determine initial mode
    let mode: EditorMode = existing.mode || "points";

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

    const updateHeader = (): void => {
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
    sizeSlider.oninput = (): void => { sizeLabel.textContent = `${sizeSlider.value}px`; };
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

    const makeBtn = (htmlLabel: string, ariaLabel: string | null, bg: string): HTMLButtonElement => {
        const b = document.createElement("button");
        b.innerHTML = htmlLabel;
        if (ariaLabel) {
            b.setAttribute("aria-label", ariaLabel);
        }
        b.style.cssText = `
            padding:8px 24px;border:none;border-radius:6px;
            font-size:14px;cursor:pointer;color:#fff;
            background:${bg};font-weight:600;
            transition:opacity 0.15s;
            outline: none;
        `;
        let isHovered = false;
        let isFocused = false;
        const update = (): void => {
            const active = isHovered || isFocused;
            b.style.opacity = active ? "0.85" : "1";
            b.style.outline = isFocused ? "2px solid #fff" : "none";
            b.style.outlineOffset = isFocused ? "2px" : "0px";
        };
        b.onmouseenter = (): void => { isHovered = true; update(); };
        b.onmouseleave = (): void => { isHovered = false; update(); };
        b.onfocus = (): void => { isFocused = true; update(); };
        b.onblur = (): void => { isFocused = false; update(); };
        return b;
    };
    const modeToggle = makeBtn(`<span aria-hidden="true">🖌</span> Draw`, "Draw Mode", "#3a5a8a");
    const clearBtn = makeBtn("Clear All", "Clear All", "#555");
    const applyBtn = makeBtn(`<span aria-hidden="true">✓</span> Apply`, "Apply", "#2a7a2a");
    const cancelBtn = makeBtn("Cancel", "Cancel", "#7a2a2a");
    btnBar.appendChild(modeToggle);
    btnBar.appendChild(clearBtn);
    btnBar.appendChild(applyBtn);
    btnBar.appendChild(cancelBtn);
    overlay.appendChild(btnBar);
    document.body.appendChild(overlay);

    // ── State ──
    let pts: number[][] = existing.points ? [...existing.points] : [];
    let lbls: number[] = existing.labels ? [...existing.labels] : [];
    let imgW = 0;
    let imgH = 0;
    let scaleX = 1;
    let scaleY = 1;
    const firstImg = new Image();

    // Offscreen mask canvas (full image resolution, black/white)
    const maskOff = document.createElement("canvas");
    let maskDirty = false;

    // Cached green overlay (regenerated only when mask changes)
    let _greenOverlay: HTMLCanvasElement | null = null;
    let _greenOverlayDirty = true;

    // ── Mode toggle ──
    const updateModeUI = (): void => {
        if (mode === "points") {
            modeToggle.innerHTML = `<span aria-hidden="true">🖌</span> Draw`;
            modeToggle.setAttribute("aria-label", "Draw Mode");
            modeToggle.style.background = "#3a5a8a";
            canvas.style.cursor = "crosshair";
            sliderWrap.style.display = "none";
        } else {
            modeToggle.innerHTML = `<span aria-hidden="true">🎯</span> Points`;
            modeToggle.setAttribute("aria-label", "Point Mode");
            modeToggle.style.background = "#5a3a8a";
            canvas.style.cursor = "none"; // custom brush cursor
            sliderWrap.style.display = "flex";
        }
        updateHeader();
        redraw();
    };

    modeToggle.onclick = (): void => {
        mode = mode === "points" ? "draw" : "points";
        updateModeUI();
    };

    // ── Redraw ──
    const redraw = (): void => {
        const ctx = canvas.getContext("2d");
        if (!ctx) return;
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
                if (tmpCtx) {
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
                }
                _greenOverlayDirty = false;
            }
            ctx.drawImage(_greenOverlay, 0, 0);

            statusBar.textContent = `Draw mode | ${imgW}×${imgH} | Brush: ${sizeSlider.value}px`;
        }
    };

    // ── Canvas sizing ──
    const fitCanvas = (w: number, h: number): void => {
        imgW = w;
        imgH = h;
        const maxW = window.innerWidth * 0.9;
        const maxH = window.innerHeight * 0.75;
        let dispW = imgW;
        let dispH = imgH;
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
        if (mCtx) {
            mCtx.fillStyle = "#000";
            mCtx.fillRect(0, 0, imgW, imgH);
        }

        // Restore existing mask data if present
        if (existing.mask_data && existing.mode === "draw") {
            const maskImg = new Image();
            maskImg.onload = (): void => {
                const restoreCtx = maskOff.getContext("2d");
                if (restoreCtx) {
                    restoreCtx.drawImage(maskImg, 0, 0, imgW, imgH);
                }
                maskDirty = true;
                redraw();
            };
            maskImg.src = "data:image/png;base64," + existing.mask_data;
        }
    };

    firstImg.onload = (): void => {
        fitCanvas(firstImg.naturalWidth, firstImg.naturalHeight);
        updateModeUI();
        redraw();
    };
    firstImg.onerror = (): void => {
        statusBar.textContent = "Failed to load image";
        statusBar.style.color = "#f44";
    };
    firstImg.crossOrigin = "anonymous";
    firstImg.src = imgSrc;

    // ── Drawing state ──
    let isDrawing = false;
    let drawButton = -1; // 0=left(paint), 2=right(erase)
    let lastDrawX = -1;
    let lastDrawY = -1;

    const paintOnMask = (canvasX: number, canvasY: number, erase: boolean): void => {
        const mCtx = maskOff.getContext("2d");
        if (!mCtx) return;
        // Convert display coords → full-res mask coords
        const mx = canvasX * scaleX;
        const my = canvasY * scaleY;
        const brushR = parseInt(sizeSlider.value) * scaleX; // scale brush to image res

        mCtx.beginPath();
        mCtx.arc(mx, my, brushR, 0, Math.PI * 2);
        mCtx.fillStyle = erase ? "#000" : "#fff";
        mCtx.fill();
        maskDirty = true;

        // Incremental green overlay update
        if (_greenOverlay) {
            const oCtx = _greenOverlay.getContext("2d");
            if (oCtx) {
                const dispBrushR = parseInt(sizeSlider.value);
                if (erase) {
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
                    oCtx.fillStyle = "rgba(0, 220, 80, 0.392)";
                    oCtx.fill();
                }
            }
        } else {
            _greenOverlayDirty = true;
        }
    };

    const paintLine = (x1: number, y1: number, x2: number, y2: number, erase: boolean): void => {
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
    const getCanvasPos = (e: MouseEvent): { x: number; y: number } => {
        const rect = canvas.getBoundingClientRect();
        const cssScaleX = canvas.width / rect.width;
        const cssScaleY = canvas.height / rect.height;
        return {
            x: (e.clientX - rect.left) * cssScaleX,
            y: (e.clientY - rect.top) * cssScaleY,
        };
    };

    const findNearPoint = (mx: number, my: number): number => {
        for (let i = 0; i < pts.length; i++) {
            const dx = pts[i][0] / scaleX - mx;
            const dy = pts[i][1] / scaleY - my;
            if (Math.sqrt(dx * dx + dy * dy) < HIT_RADIUS) return i;
        }
        return -1;
    };

    canvas.addEventListener("mousedown", (e: MouseEvent): void => {
        if (mode === "draw") {
            e.preventDefault();
            isDrawing = true;
            drawButton = e.button;
            const pos = getCanvasPos(e);
            lastDrawX = pos.x;
            lastDrawY = pos.y;
            paintOnMask(pos.x, pos.y, e.button === 2);
            redraw();

            const ctx = canvas.getContext("2d");
            if (ctx) {
                ctx.beginPath();
                ctx.arc(pos.x, pos.y, parseInt(sizeSlider.value), 0, Math.PI * 2);
                ctx.strokeStyle = e.button === 2 ? "rgba(255,80,80,0.7)" : "rgba(80,255,120,0.7)";
                ctx.lineWidth = 2;
                ctx.stroke();
            }
        }
    });

    canvas.addEventListener("mousemove", (e: MouseEvent): void => {
        if (mode === "draw") {
            const pos = getCanvasPos(e);

            if (isDrawing) {
                paintLine(lastDrawX, lastDrawY, pos.x, pos.y, drawButton === 2);
                lastDrawX = pos.x;
                lastDrawY = pos.y;
                redraw();
            }

            const ctx = canvas.getContext("2d");
            if (ctx) {
                const brushR = parseInt(sizeSlider.value);
                ctx.beginPath();
                ctx.arc(pos.x, pos.y, brushR, 0, Math.PI * 2);
                ctx.strokeStyle = isDrawing
                    ? (drawButton === 2 ? "rgba(255,80,80,0.7)" : "rgba(80,255,120,0.7)")
                    : "rgba(255,255,255,0.5)";
                ctx.lineWidth = 2;
                ctx.stroke();
            }
        }
    });

    const stopDrawing = (): void => {
        if (isDrawing) {
            _greenOverlayDirty = true;
            redraw();
        }
        isDrawing = false;
        drawButton = -1;
        lastDrawX = -1;
        lastDrawY = -1;
    };

    canvas.addEventListener("mouseup", stopDrawing);
    canvas.addEventListener("mouseleave", (): void => {
        stopDrawing();
        if (mode === "draw") redraw();
    });

    // Points mode click
    canvas.addEventListener("click", (e: MouseEvent): void => {
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

    canvas.addEventListener("contextmenu", (e: MouseEvent): void => {
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
    overlay.addEventListener("click", (e: MouseEvent): void => {
        if (e.target === overlay) {
            document.removeEventListener("keydown", keyHandler);
            overlay.remove();
        }
    });
    overlay.addEventListener("contextmenu", (e: Event): void => e.preventDefault());

    // ── Buttons ──
    clearBtn.onclick = (): void => {
        if (mode === "points") {
            pts.length = 0;
            lbls.length = 0;
        } else {
            const mCtx = maskOff.getContext("2d");
            if (mCtx) {
                mCtx.fillStyle = "#000";
                mCtx.fillRect(0, 0, maskOff.width, maskOff.height);
            }
            maskDirty = false;
            _greenOverlayDirty = true;
        }
        redraw();
    };
    cancelBtn.onclick = (): void => {
        document.removeEventListener("keydown", keyHandler);
        overlay.remove();
    };

    applyBtn.onclick = (): void => {
        let data: string;
        if (mode === "draw" && maskDirty) {
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
        if (mpWidget) {
            mpWidget.value = data;
        } else {
            const w = node.addWidget("text", "mask_points_data", data,
                () => { /* no-op */ }, { serialize: true });
            w.type = "text";
            if (w.computeSize) w.computeSize = () => [0, -4] as [number, number];
        }
        node.setDirtyCanvas(true, true);
        document.removeEventListener("keydown", keyHandler);
        overlay.remove();
        flashNode(node, "#2a7a2a");
    };

    // ESC to close
    const keyHandler = (e: KeyboardEvent): void => {
        if (e.key === "Escape") {
            overlay.remove();
            document.removeEventListener("keydown", keyHandler);
        }
    };
    document.addEventListener("keydown", keyHandler);
}
