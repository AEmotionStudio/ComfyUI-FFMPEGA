/**
 * FramePickerModal.ts — Modal for interactive frame selection & reordering.
 *
 * Primary layout (CSS Grid — matches FacePoke):
 *   header    | header
 *   canvas    | sidebar
 *   filmstrip | sidebar
 *   toolbar   | toolbar
 *
 * Secondary layout (grid mode — toggle via button):
 *   header    | header
 *   grid-view | sidebar
 *   toolbar   | toolbar
 *
 * Middle-mouse scroll on canvas navigates frames (same as FacePoke).
 */

import { api } from "comfyui/api";
import {
    iconGrid, iconFilmstrip, iconCheck, iconClose,
    iconSelectAll, iconDeselect, iconInvert,
    iconUndo, iconRedo, iconSkipStart, iconSkipEnd,
    iconPrev, iconNext, iconPlay, iconPause,
    iconFlip, iconFlipVertical, iconRotateCW,
    iconReverse, iconReset, iconCopy, iconPaste,
    iconCircleCheck, iconCircleX, iconPlusCircle,
} from "../videoeditor/icons";

// ── Types ──────────────────────────────────────────────────────

export interface FramePickerCallbacks {
    onApply: (selectedIndices: number[], transforms?: Map<number, { flipH: boolean; flipV: boolean; rotate: number }>) => void;
    onCancel: () => void;
}

// ── Modal class ────────────────────────────────────────────────

export class FramePickerModal {
    private dialog: HTMLDivElement;
    private panel: HTMLDivElement;
    private canvasArea: HTMLDivElement;
    private canvasImg: HTMLImageElement;
    private canvasOverlay: HTMLDivElement;
    private filmstrip: HTMLDivElement;
    private gridArea: HTMLDivElement;
    private gridContainer: HTMLDivElement;
    private sidebar: HTMLDivElement;
    private statusEl: HTMLDivElement;
    private callbacks: FramePickerCallbacks;

    private _isOpen = false;
    private _gridMode = false;
    private videoPath = "";
    private totalFrames = 0;
    private videoFps = 24;
    private videoWidth = 0;
    private videoHeight = 0;

    // Selection state
    private currentFrame = 0;
    private selectedSet: Set<number> = new Set();
    private frameOrder: number[] = [];
    private _displayOrder: number[] = [];  // Visual position of ALL frames
    private lastClickedFrame = -1;

    // Thumbnail cache (base64 strings)
    private thumbnailCache: Map<number, string> = new Map();

    // Undo/redo
    private _undoStack: string[] = [];
    private _redoStack: string[] = [];

    // Playback state
    private _playing = false;
    private _playTimer: ReturnType<typeof setTimeout> | null = null;
    private _playIdx = 0;
    private _playBtn: HTMLButtonElement | null = null;

    // Filmstrip drag state
    private _filmstripDragFrame: number | null = null;
    private _lastSpreadTarget: HTMLElement | null = null;
    private _lastSpreadSide: "left" | "right" | null = null;

    // Clipboard for copy/paste
    private _clipboard: number | null = null;

    // Filmstrip zoom
    private _thumbScale = 1.0;
    private _zoomSlider: HTMLInputElement | null = null;

    // Per-frame transforms {frameIdx -> {flipH, flipV, rotate}}
    private _frameTransforms: Map<number, { flipH: boolean; flipV: boolean; rotate: number }> = new Map();

    // Event handlers
    private _keyHandler: ((e: KeyboardEvent) => void) | null = null;
    private _wheelHandler: ((e: WheelEvent) => void) | null = null;

    // Loading state
    private _loadingOverlay: HTMLDivElement | null = null;
    private _loadedThumbCount = 0;
    private _totalThumbCount = 0;

    constructor(callbacks: FramePickerCallbacks) {
        this.callbacks = callbacks;

        document.querySelectorAll(".fpick-backdrop").forEach((d) => d.remove());

        // ─── Backdrop ───
        this.dialog = document.createElement("div");
        this.dialog.className = "fpick-backdrop";
        this.dialog.style.display = "none";
        this.dialog.setAttribute("role", "dialog");
        this.dialog.setAttribute("aria-modal", "true");
        this.dialog.setAttribute("aria-label", "Frame Picker");

        // ─── Panel ───
        this.panel = document.createElement("div");
        this.panel.className = "fpick-panel";

        // ═══════════════════════════════════════════════════════
        // HEADER
        // ═══════════════════════════════════════════════════════
        const header = document.createElement("div");
        header.className = "fpick-header";

        const title = document.createElement("h2");
        title.className = "fpick-title";
        title.innerHTML = `${iconFilmstrip} Frame Picker`;

        const frameInfo = document.createElement("span");
        frameInfo.className = "fpick-frame-info";
        frameInfo.id = "fpick-frame-info";
        frameInfo.textContent = "No video loaded";

        const headerActions = document.createElement("div");
        headerActions.className = "fpick-header-actions";

        // View toggle
        const viewToggle = this._makeBtn(`${iconGrid} Grid`, "fpick-btn-sm fpick-btn-view", () => {
            this._gridMode = !this._gridMode;
            this.panel.classList.toggle("grid-mode", this._gridMode);
            viewToggle.classList.toggle("active", this._gridMode);
            viewToggle.innerHTML = this._gridMode ? `${iconFilmstrip} Filmstrip` : `${iconGrid} Grid`;
            if (this._gridMode) this._buildGridView();
        });
        viewToggle.title = "Toggle grid view (G)";

        const undoBtn = this._makeBtn(`${iconUndo}`, "fpick-btn-sm", () => this._undo());
        undoBtn.title = "Undo (Ctrl+Z)";
        const redoBtn = this._makeBtn(`${iconRedo}`, "fpick-btn-sm", () => this._redo());
        redoBtn.title = "Redo (Ctrl+Y)";

        const cancelBtn = this._makeBtn("Cancel", "fpick-btn-sm", () => this._cancel());
        cancelBtn.title = "Cancel (ESC)";

        const applyBtn = this._makeBtn(`${iconCheck} Apply`, "fpick-btn-sm fpick-btn-apply", () => this._apply());
        applyBtn.title = "Apply selection and pass frames downstream";

        const closeBtn = document.createElement("button");
        closeBtn.className = "fpick-close";
        closeBtn.innerHTML = iconClose;
        closeBtn.title = "Close (ESC)";
        closeBtn.addEventListener("click", () => this._cancel());

        headerActions.append(viewToggle, undoBtn, redoBtn, cancelBtn, applyBtn, closeBtn);
        header.append(title, frameInfo, headerActions);

        // ═══════════════════════════════════════════════════════
        // CANVAS AREA (large frame display — primary mode)
        // ═══════════════════════════════════════════════════════
        this.canvasArea = document.createElement("div");
        this.canvasArea.className = "fpick-canvas-area";

        this.canvasImg = document.createElement("img");
        this.canvasImg.className = "fpick-canvas";
        this.canvasImg.alt = "Current frame";

        // Overlay showing frame number + selected/deselected status
        this.canvasOverlay = document.createElement("div");
        this.canvasOverlay.className = "fpick-canvas-overlay";

        this.canvasArea.append(this.canvasImg, this.canvasOverlay);

        // Click canvas to toggle selection
        this.canvasImg.addEventListener("click", () => {
            this._toggleFrame(this.currentFrame);
        });

        // ═══════════════════════════════════════════════════════
        // FILMSTRIP (frame scrubber — primary mode)
        // ═══════════════════════════════════════════════════════
        this.filmstrip = document.createElement("div");
        this.filmstrip.className = "fpick-filmstrip";

        // ═══════════════════════════════════════════════════════
        // GRID AREA (secondary mode — hidden by default)
        // ═══════════════════════════════════════════════════════
        this.gridArea = document.createElement("div");
        this.gridArea.className = "fpick-grid-area";

        this.gridContainer = document.createElement("div");
        this.gridContainer.className = "fpick-grid";
        this.gridArea.appendChild(this.gridContainer);

        // ═══════════════════════════════════════════════════════
        // SIDEBAR
        // ═══════════════════════════════════════════════════════
        this.sidebar = document.createElement("div");
        this.sidebar.className = "fpick-sidebar";
        this._buildSidebar();

        // ═══════════════════════════════════════════════════════
        // TOOLBAR
        // ═══════════════════════════════════════════════════════
        const toolbar = document.createElement("div");
        toolbar.className = "fpick-toolbar";

        this.statusEl = document.createElement("div");
        this.statusEl.className = "fpick-status";
        this.statusEl.textContent = "Select frames to keep, then Apply";

        const navBtns = document.createElement("div");
        navBtns.className = "fpick-nav-btns";

        const firstBtn = this._makeBtn(iconSkipStart, "fpick-btn-sm", () => this._goToFrame(0));
        firstBtn.title = "First frame (Home)";
        const prevBtn = this._makeBtn(`${iconPrev} Prev`, "fpick-btn-sm", () => this._prevFrame());
        prevBtn.title = "Previous frame (←)";

        this._playBtn = this._makeBtn(`${iconPlay} Play`, "fpick-btn-sm fpick-btn-play", () => this._togglePlayback());
        this._playBtn.title = "Play selected frames (P)";

        const nextBtn = this._makeBtn(`Next ${iconNext}`, "fpick-btn-sm", () => this._nextFrame());
        nextBtn.title = "Next frame (→)";
        const lastBtn = this._makeBtn(iconSkipEnd, "fpick-btn-sm", () => this._goToFrame(Math.max(0, this.totalFrames - 1)));
        lastBtn.title = "Last frame (End)";

        const selectedCount = document.createElement("span");
        selectedCount.className = "fpick-selected-count";
        selectedCount.id = "fpick-selected-count";
        selectedCount.textContent = "0 / 0 selected";

        // Zoom slider for filmstrip
        const zoomGroup = document.createElement("div");
        zoomGroup.className = "fpick-zoom-group";
        zoomGroup.style.cssText = "display:flex;align-items:center;gap:5px;margin-left:12px;";

        const zoomLabel = document.createElement("span");
        zoomLabel.style.cssText = "font-size:10px;color:#8888aa;white-space:nowrap;";
        zoomLabel.textContent = "Zoom";

        const zoomSlider = document.createElement("input");
        zoomSlider.type = "range";
        zoomSlider.min = "50";
        zoomSlider.max = "250";
        zoomSlider.value = "100";
        zoomSlider.className = "fpick-zoom-slider";
        zoomSlider.title = "Filmstrip thumbnail size";
        zoomSlider.style.cssText = "width:80px;accent-color:#6366f1;cursor:pointer;";
        zoomSlider.onpointerdown = (e) => e.stopPropagation();
        this._zoomSlider = zoomSlider;
        zoomSlider.addEventListener("input", () => {
            this._thumbScale = parseInt(zoomSlider.value, 10) / 100;
            this.panel.style.setProperty("--fpick-thumb-scale", String(this._thumbScale));
        });

        const zoomValue = document.createElement("span");
        zoomValue.style.cssText = "font-size:10px;color:#8888aa;min-width:28px;text-align:right;font-variant-numeric:tabular-nums;";
        zoomValue.textContent = "100%";
        zoomSlider.addEventListener("input", () => {
            zoomValue.textContent = `${zoomSlider.value}%`;
        });

        zoomGroup.append(zoomLabel, zoomSlider, zoomValue);

        navBtns.append(firstBtn, prevBtn, this._playBtn, nextBtn, lastBtn, selectedCount, zoomGroup);
        toolbar.append(this.statusEl, navBtns);

        // ═══════════════════════════════════════════════════════
        // ASSEMBLE
        // ═══════════════════════════════════════════════════════
        this.panel.append(header, this.canvasArea, this.filmstrip, this.gridArea, this.sidebar, toolbar);
        this.dialog.appendChild(this.panel);
        document.body.appendChild(this.dialog);
    }

    // ── Sidebar builder ────────────────────────────────────────

    private _buildSidebar(): void {
        // Selection Tools
        const toolSection = document.createElement("div");
        const toolTitle = document.createElement("div");
        toolTitle.className = "fpick-section-title";
        toolTitle.textContent = "SELECTION TOOLS";
        toolSection.appendChild(toolTitle);

        const toolGroup = document.createElement("div");
        toolGroup.className = "fpick-tool-group";

        const selectAllBtn = this._makeBtn(`${iconSelectAll} Select All`, "fpick-btn-sm fpick-btn-tool", () => this._selectAll());
        selectAllBtn.title = "Select all frames (A)";
        const deselectBtn = this._makeBtn(`${iconDeselect} Deselect All`, "fpick-btn-sm fpick-btn-tool", () => this._deselectAll());
        deselectBtn.title = "Deselect all frames (D)";
        const invertBtn = this._makeBtn(`${iconInvert} Invert`, "fpick-btn-sm fpick-btn-tool", () => this._invertSelection());
        invertBtn.title = "Invert selection (I)";
        const resetBtn = this._makeBtn(`${iconReset} Reset All`, "fpick-btn-sm fpick-btn-reset", () => this._resetAll());
        resetBtn.title = "Reset to original order with all frames selected";

        toolGroup.append(selectAllBtn, deselectBtn, invertBtn, resetBtn);
        toolSection.appendChild(toolGroup);

        // Transform Tools
        const transformSection = document.createElement("div");
        const transformTitle = document.createElement("div");
        transformTitle.className = "fpick-section-title";
        transformTitle.textContent = "FRAME TRANSFORMS";
        transformSection.appendChild(transformTitle);

        const transformGroup = document.createElement("div");
        transformGroup.className = "fpick-tool-group";

        const flipHBtn = this._makeBtn(`${iconFlip} Flip H`, "fpick-btn-sm fpick-btn-tool", () => this._flipCurrentH());
        flipHBtn.title = "Flip current frame horizontally (H)";
        const flipVBtn = this._makeBtn(`${iconFlipVertical} Flip V`, "fpick-btn-sm fpick-btn-tool", () => this._flipCurrentV());
        flipVBtn.title = "Flip current frame vertically (V)";
        const rotateCWBtn = this._makeBtn(`${iconRotateCW} Rotate 90°`, "fpick-btn-sm fpick-btn-tool", () => this._rotateCurrentCW());
        rotateCWBtn.title = "Rotate current frame 90° clockwise (R)";
        const reverseBtn = this._makeBtn(`${iconReverse} Reverse Order`, "fpick-btn-sm fpick-btn-tool", () => this._reverseOrder());
        reverseBtn.title = "Reverse the entire frame order";
        const holdBtn = this._makeBtn(`${iconPause} Hold Frame ×3`, "fpick-btn-sm fpick-btn-tool", () => this._holdFrame(3));
        holdBtn.title = "Duplicate current frame 3 times (extend duration)";

        transformGroup.append(flipHBtn, flipVBtn, rotateCWBtn, reverseBtn, holdBtn);
        transformSection.appendChild(transformGroup);

        // Every Nth Frame
        const nthSection = document.createElement("div");
        const nthTitle = document.createElement("div");
        nthTitle.className = "fpick-section-title";
        nthTitle.textContent = "EVERY Nth FRAME";
        nthSection.appendChild(nthTitle);

        const nthRow = document.createElement("div");
        nthRow.className = "fpick-nth-row";

        const nthLabel = document.createElement("span");
        nthLabel.style.cssText = "font-size:12px;color:#9898b0;";
        nthLabel.textContent = "Keep every";

        const nthInput = document.createElement("input");
        nthInput.type = "number";
        nthInput.className = "fpick-nth-input";
        nthInput.value = "2";
        nthInput.min = "2";
        nthInput.max = "100";
        nthInput.id = "fpick-nth-input";
        nthInput.onpointerdown = (e) => e.stopPropagation();

        const nthSuffix = document.createElement("span");
        nthSuffix.style.cssText = "font-size:12px;color:#9898b0;";
        nthSuffix.textContent = "frame";

        const nthApply = this._makeBtn("Apply", "fpick-btn-sm fpick-btn-tool", () => {
            const n = parseInt(nthInput.value, 10);
            if (n >= 2) this._selectEveryNth(n);
        });

        nthRow.append(nthLabel, nthInput, nthSuffix, nthApply);
        nthSection.appendChild(nthRow);

        // Summary
        const summarySection = document.createElement("div");
        const summaryTitle = document.createElement("div");
        summaryTitle.className = "fpick-section-title";
        summaryTitle.textContent = "SELECTION SUMMARY";
        summarySection.appendChild(summaryTitle);

        const summary = document.createElement("div");
        summary.className = "fpick-summary";
        summary.innerHTML = `
            <div class="fpick-summary-row"><span class="fpick-summary-label">Total frames</span><span class="fpick-summary-value" id="fpick-total">0</span></div>
            <div class="fpick-summary-row"><span class="fpick-summary-label">Selected</span><span class="fpick-summary-value highlight" id="fpick-sel-count">0</span></div>
            <div class="fpick-summary-row"><span class="fpick-summary-label">Removed</span><span class="fpick-summary-value" id="fpick-rem-count" style="color:#ef4444">0</span></div>
            <div class="fpick-summary-row"><span class="fpick-summary-label">Duration</span><span class="fpick-summary-value" id="fpick-duration">0.00s</span></div>
        `;
        summarySection.appendChild(summary);

        // Order Preview
        const orderSection = document.createElement("div");
        const orderTitle = document.createElement("div");
        orderTitle.className = "fpick-section-title";
        orderTitle.textContent = "FRAME ORDER PREVIEW";
        orderSection.appendChild(orderTitle);

        const orderPreview = document.createElement("div");
        orderPreview.className = "fpick-order-preview";
        orderSection.appendChild(orderPreview);

        // Shortcuts
        const helpSection = document.createElement("div");
        const helpTitle = document.createElement("div");
        helpTitle.className = "fpick-section-title";
        helpTitle.textContent = "SHORTCUTS";
        helpSection.appendChild(helpTitle);

        const shortcuts = [
            ["Space", "Toggle frame"], ["P", "Play/Pause"], ["A", "Select all"],
            ["D", "Deselect all"], ["I", "Invert"], ["G", "Grid view"],
            ["Ctrl+C", "Copy frame"], ["Ctrl+V", "Paste (duplicate)"],
            ["H", "Flip Horizontal"], ["V", "Flip Vertical"], ["R", "Rotate 90° CW"],
            ["Del", "Deselect"], ["←→", "Navigate"], ["Scroll", "Browse"],
            ["Drag", "Reorder frames"], ["Ctrl+Z/Y", "Undo/Redo"], ["Esc", "Cancel"],
        ];
        const helpGrid = document.createElement("div");
        helpGrid.style.cssText = "display:flex;flex-direction:column;gap:3px;";
        for (const [key, desc] of shortcuts) {
            const row = document.createElement("div");
            row.style.cssText = "display:flex;align-items:center;gap:6px;font-size:11px;color:#8888aa;";
            row.innerHTML = `<span class="fpick-kbd">${key}</span> ${desc}`;
            helpGrid.appendChild(row);
        }
        helpSection.appendChild(helpGrid);

        this.sidebar.append(toolSection, transformSection, nthSection, summarySection, orderSection, helpSection);
    }

    // ── Public API ─────────────────────────────────────────────

    async open(videoPath: string, initialSelection?: number[]): Promise<void> {
        if (this._isOpen) return;
        this._isOpen = true;
        this.videoPath = videoPath;
        this.thumbnailCache.clear();
        this.currentFrame = 0;
        this.lastClickedFrame = -1;
        this._undoStack = [];
        this._redoStack = [];
        this._gridMode = false;
        this.panel.classList.remove("grid-mode");

        this.dialog.style.display = "flex";
        this._setStatus("Loading video...");

        // Keyboard handler
        this._keyHandler = (e: KeyboardEvent) => this._handleKey(e);
        document.addEventListener("keydown", this._keyHandler);

        // Middle-mouse wheel on canvas → navigate frames
        this._wheelHandler = (e: WheelEvent) => {
            e.preventDefault();
            if (e.deltaY > 0) this._nextFrame();
            else if (e.deltaY < 0) this._prevFrame();
        };
        this.canvasArea.addEventListener("wheel", this._wheelHandler, { passive: false });

        // Fetch metadata
        try {
            const resp = await api.fetchApi("/framepicker/get_frames", {
                method: "POST",
                body: JSON.stringify({ node_id: "", video_path: videoPath }),
            });
            if (resp.ok) {
                const meta = await resp.json();
                this.totalFrames = meta.total_frames || 1;
                this.videoWidth = meta.width || 640;
                this.videoHeight = meta.height || 480;
                this.videoFps = meta.fps || 24;
            } else {
                this.totalFrames = 1;
            }
        } catch {
            this.totalFrames = 1;
        }

        // Initialize selection — default all selected
        this.selectedSet.clear();
        if (initialSelection && initialSelection.length > 0) {
            for (const idx of initialSelection) this.selectedSet.add(idx);
            this.frameOrder = [...initialSelection];
        } else {
            for (let i = 0; i < this.totalFrames; i++) this.selectedSet.add(i);
            this.frameOrder = Array.from({ length: this.totalFrames }, (_, i) => i);
        }
        // Display order: all frames in sequential order initially
        this._displayOrder = Array.from({ length: this.totalFrames }, (_, i) => i);

        this._updateFrameInfo();
        this._showLoadingOverlay();
        this._buildFilmstrip();
        await this._goToFrame(0);
        this._updateSummary();
        this._updateOrderPreview();
        this._setStatus("Click frame or Space to toggle, scroll to browse, then Apply");
    }

    // ── Loading overlay ─────────────────────────────────────

    private _showLoadingOverlay(): void {
        // Remove any existing
        this._dismissLoadingOverlay();
        this._loadedThumbCount = 0;
        this._totalThumbCount = this.totalFrames;

        const overlay = document.createElement("div");
        overlay.className = "fpick-loading-overlay";
        overlay.style.cssText = `
            position: absolute;
            inset: 0;
            z-index: 1000;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 16px;
            background: rgba(10, 10, 18, 0.92);
            backdrop-filter: blur(12px);
            transition: opacity 0.4s ease;
        `;

        // Spinner ring
        const spinner = document.createElement("div");
        spinner.style.cssText = `
            width: 48px; height: 48px;
            border: 3px solid rgba(99, 102, 241, 0.15);
            border-top-color: #818cf8;
            border-radius: 50%;
            animation: fpick-spin 0.8s linear infinite;
        `;

        // Progress text
        const label = document.createElement("div");
        label.className = "fpick-loading-label";
        label.style.cssText = `
            font-size: 13px;
            color: #a0a0c0;
            font-variant-numeric: tabular-nums;
        `;
        label.textContent = `Loading 0 / ${this._totalThumbCount} frames...`;

        // Progress bar track
        const barTrack = document.createElement("div");
        barTrack.style.cssText = `
            width: 240px; height: 4px;
            background: rgba(255,255,255,0.06);
            border-radius: 2px;
            overflow: hidden;
        `;
        const barFill = document.createElement("div");
        barFill.className = "fpick-loading-bar";
        barFill.style.cssText = `
            height: 100%; width: 0%;
            background: linear-gradient(90deg, #6366f1, #818cf8);
            border-radius: 2px;
            transition: width 0.15s ease;
        `;
        barTrack.appendChild(barFill);

        overlay.append(spinner, label, barTrack);
        this.dialog.style.position = "relative";
        this.dialog.appendChild(overlay);
        this._loadingOverlay = overlay;

        // Inject keyframe if not already present
        if (!document.getElementById("fpick-spin-style")) {
            const style = document.createElement("style");
            style.id = "fpick-spin-style";
            style.textContent = `@keyframes fpick-spin { to { transform: rotate(360deg); } }`;
            document.head.appendChild(style);
        }
    }

    private _updateLoadingProgress(): void {
        this._loadedThumbCount++;
        if (!this._loadingOverlay) return;

        const pct = Math.min(100, (this._loadedThumbCount / this._totalThumbCount) * 100);
        const bar = this._loadingOverlay.querySelector(".fpick-loading-bar") as HTMLDivElement | null;
        const label = this._loadingOverlay.querySelector(".fpick-loading-label") as HTMLDivElement | null;

        if (bar) bar.style.width = `${pct}%`;
        if (label) label.textContent = `Loading ${this._loadedThumbCount} / ${this._totalThumbCount} frames...`;

        if (this._loadedThumbCount >= this._totalThumbCount) {
            // Fade out then remove
            this._loadingOverlay.style.opacity = "0";
            setTimeout(() => this._dismissLoadingOverlay(), 400);
        }
    }

    private _dismissLoadingOverlay(): void {
        if (this._loadingOverlay) {
            this._loadingOverlay.remove();
            this._loadingOverlay = null;
        }
    }

    close(): void {
        if (!this._isOpen) return;
        this._isOpen = false;
        this._stopPlayback();
        if (this._keyHandler) {
            document.removeEventListener("keydown", this._keyHandler);
            this._keyHandler = null;
        }
        if (this._wheelHandler) {
            this.canvasArea.removeEventListener("wheel", this._wheelHandler);
            this._wheelHandler = null;
        }
        this._undoStack = [];
        this._redoStack = [];
        this._dismissLoadingOverlay();
        this.dialog.style.display = "none";
    }

    get isOpen(): boolean { return this._isOpen; }

    setCallbacks(callbacks: FramePickerCallbacks): void {
        this.callbacks = callbacks;
    }

    // ── Canvas (large frame display) ───────────────────────────

    private async _loadCanvasFrame(): Promise<void> {
        const url = await this._fetchFrame(this.currentFrame);
        this.canvasImg.src = url;
        this._applyCanvasTransform();
        this._updateCanvasOverlay();
    }

    private _applyCanvasTransform(): void {
        const t = this._frameTransforms.get(this.currentFrame);
        if (!t) {
            this.canvasImg.style.transform = "";
            return;
        }
        const parts: string[] = [];
        if (t.flipH) parts.push("scaleX(-1)");
        if (t.flipV) parts.push("scaleY(-1)");
        if (t.rotate) parts.push(`rotate(${t.rotate}deg)`);
        this.canvasImg.style.transform = parts.join(" ");
    }

    private _updateCanvasOverlay(): void {
        const isSelected = this.selectedSet.has(this.currentFrame);
        const orderIdx = this.frameOrder.indexOf(this.currentFrame);
        const transformLabel = this._getTransformLabel(this.currentFrame);
        this.canvasOverlay.innerHTML = `
            <span class="fpick-canvas-frame-num">Frame ${this.currentFrame + 1} / ${this.totalFrames}${transformLabel}</span>
            <span class="fpick-canvas-status ${isSelected ? "selected" : "deselected"}">
                ${isSelected ? `${iconCheck} Selected (#${orderIdx + 1})` : `${iconClose} Removed`}
            </span>
        `;
    }

    // ── Frame navigation ───────────────────────────────────────

    private async _goToFrame(idx: number): Promise<void> {
        this.currentFrame = Math.max(0, Math.min(idx, this.totalFrames - 1));
        await this._loadCanvasFrame();
        this._updateFilmstripActive();
        this._updateFrameInfo();
    }

    private _prevFrame(): void {
        if (this.frameOrder.length === 0) return;
        // Find current position in frameOrder
        const curOrderIdx = this.frameOrder.indexOf(this.currentFrame);
        if (curOrderIdx > 0) {
            // Go to previous frame in the user's ordered sequence
            this._goToFrame(this.frameOrder[curOrderIdx - 1]);
        } else if (curOrderIdx < 0) {
            // Current frame is deselected — jump to nearest selected (backward)
            const nearest = this._findNearestSelected(this.currentFrame);
            if (nearest !== null) this._goToFrame(nearest);
        }
        // If curOrderIdx === 0, already at first — do nothing
    }

    private _nextFrame(): void {
        if (this.frameOrder.length === 0) return;
        const curOrderIdx = this.frameOrder.indexOf(this.currentFrame);
        if (curOrderIdx >= 0 && curOrderIdx < this.frameOrder.length - 1) {
            // Go to next frame in the user's ordered sequence
            this._goToFrame(this.frameOrder[curOrderIdx + 1]);
        } else if (curOrderIdx < 0) {
            // Current frame is deselected — jump to nearest selected (forward)
            const nearest = this._findNearestSelected(this.currentFrame);
            if (nearest !== null) this._goToFrame(nearest);
        }
        // If at last frame in order — do nothing
    }

    // ── Filmstrip builder (matches FacePoke) ───────────────────

    private _buildFilmstrip(): void {
        this.filmstrip.innerHTML = "";

        // Show ALL frames in _displayOrder — deselected stay in place, drag-drop moves them
        for (const i of this._displayOrder) {
            const orderIdx = this.frameOrder.indexOf(i);
            const orderPos = this.selectedSet.has(i) && orderIdx >= 0 ? orderIdx + 1 : null;
            const wrapper = document.createElement("div");
            wrapper.className = "fpick-thumb-wrap";
            wrapper.dataset.frameIdx = String(i);
            wrapper.draggable = true;
            if (i === this.currentFrame) wrapper.classList.add("active");

            // Selection class
            if (this.selectedSet.has(i)) {
                wrapper.classList.add("selected-frame");
            } else {
                wrapper.classList.add("deselected-frame");
            }

            const thumb = document.createElement("img");
            thumb.className = "fpick-thumb";
            thumb.alt = `Frame ${i + 1}`;
            thumb.width = 80;
            thumb.height = 60;
            thumb.loading = "lazy";

            // Fetch thumbnail and update loading progress
            this._fetchFrameThumb(i).then((url) => {
                thumb.src = url;
                this._updateLoadingProgress();
            });

            const frameNum = document.createElement("span");
            frameNum.className = "fpick-thumb-num";
            frameNum.textContent = String(i + 1);

            // Selection indicator dot
            const selDot = document.createElement("span");
            selDot.className = "fpick-thumb-sel";
            selDot.innerHTML = this.selectedSet.has(i) ? iconCheck : iconClose;

            wrapper.append(thumb, frameNum, selDot);

            // Position badge (only for selected frames)
            if (orderPos !== null) {
                const orderBadge = document.createElement("span");
                orderBadge.className = "fpick-thumb-order";
                orderBadge.textContent = `#${orderPos}`;
                wrapper.appendChild(orderBadge);
            }

            // Click → toggle selection, Shift+Click → range select
            wrapper.addEventListener("click", (e: MouseEvent) => {
                if (e.shiftKey && this.lastClickedFrame >= 0) {
                    // Range select from last clicked to this frame
                    this._pushUndo();
                    const start = Math.min(this.lastClickedFrame, i);
                    const end = Math.max(this.lastClickedFrame, i);
                    for (let f = start; f <= end; f++) {
                        if (!this.selectedSet.has(f)) {
                            this.selectedSet.add(f);
                            // Insert at sorted position
                            let insertPos = this.frameOrder.length;
                            for (let j = 0; j < this.frameOrder.length; j++) {
                                if (this.frameOrder[j] > f) { insertPos = j; break; }
                            }
                            this.frameOrder.splice(insertPos, 0, f);
                        }
                    }
                    this.lastClickedFrame = i;
                    this._refreshAll();
                } else {
                    this._toggleFrame(i);
                }
            });

            // Right-click → toggle selection
            wrapper.addEventListener("contextmenu", (e: MouseEvent) => {
                e.preventDefault();
                this._toggleFrame(i);
            });

            // ── Filmstrip drag-to-reorder ──
            wrapper.addEventListener("dragstart", (e: DragEvent) => {
                // Auto-select if not already selected
                if (!this.selectedSet.has(i)) {
                    this._pushUndo();
                    this.selectedSet.add(i);
                    this.frameOrder.push(i);
                    this._updateFilmstripSelection();
                    this._updateSummary();
                    this._updateSelectedCount();
                }
                this._filmstripDragFrame = i;
                e.dataTransfer!.effectAllowed = "move";
                e.dataTransfer!.setData("text/plain", String(i));
                wrapper.classList.add("dragging");
            });

            wrapper.addEventListener("dragend", () => {
                wrapper.classList.remove("dragging");
                this._filmstripDragFrame = null;
                this._lastSpreadTarget = null;
                this._lastSpreadSide = null;
                this._clearFilmstripSpread();
            });

            wrapper.addEventListener("dragover", (e: DragEvent) => {
                if (this._filmstripDragFrame === null) return;
                e.preventDefault();
                e.dataTransfer!.dropEffect = "move";
                const rect = wrapper.getBoundingClientRect();
                const relX = (e.clientX - rect.left) / rect.width;
                // Dead zone in center 40-60% to prevent flickering
                let side: "left" | "right";
                if (relX < 0.4) side = "left";
                else if (relX > 0.6) side = "right";
                else side = this._lastSpreadSide || (relX < 0.5 ? "left" : "right");
                if (wrapper !== this._lastSpreadTarget || side !== this._lastSpreadSide) {
                    this._applyFilmstripSpread(wrapper, side);
                }
            });

            wrapper.addEventListener("dragleave", () => {
                // Only clear if leaving the filmstrip entirely, not just between children
                // The dragover on the next element will update state
            });

            wrapper.addEventListener("drop", (e: DragEvent) => {
                e.preventDefault();
                this._clearFilmstripSpread();
                const srcFrame = this._filmstripDragFrame;
                if (srcFrame === null || srcFrame === i) return;

                const rect = wrapper.getBoundingClientRect();
                const midX = rect.left + rect.width / 2;
                const dropAfter = e.clientX >= midX;

                this._reorderFrameInFilmstrip(srcFrame, i, dropAfter);
                this._filmstripDragFrame = null;
            });

            this.filmstrip.appendChild(wrapper);
        }

        // ── End drop zone (allows dropping after the last frame) ──
        const endZone = document.createElement("div");
        endZone.className = "fpick-thumb-end-zone";
        endZone.style.cssText = `
            flex-shrink: 0;
            width: 40px;
            min-height: 60px;
            border-radius: 4px;
            border: 2px dashed rgba(255,255,255,0.08);
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
        `;

        endZone.addEventListener("dragover", (e: DragEvent) => {
            if (this._filmstripDragFrame === null) return;
            e.preventDefault();
            e.dataTransfer!.dropEffect = "move";
            endZone.style.borderColor = "#6366f1";
            endZone.style.background = "rgba(99, 102, 241, 0.1)";
            endZone.style.boxShadow = "0 0 16px rgba(99, 102, 241, 0.3)";
        });
        endZone.addEventListener("dragleave", () => {
            endZone.style.borderColor = "rgba(255,255,255,0.08)";
            endZone.style.background = "";
            endZone.style.boxShadow = "";
        });
        endZone.addEventListener("drop", (e: DragEvent) => {
            e.preventDefault();
            endZone.style.borderColor = "rgba(255,255,255,0.08)";
            endZone.style.background = "";
            endZone.style.boxShadow = "";
            const srcFrame = this._filmstripDragFrame;
            if (srcFrame === null) return;

            this._pushUndo();
            // Remove from current position
            const srcIdx = this.frameOrder.indexOf(srcFrame);
            if (srcIdx >= 0) this.frameOrder.splice(srcIdx, 1);
            // Append at end
            this.frameOrder.push(srcFrame);
            // Update display order
            const srcDisplayIdx = this._displayOrder.indexOf(srcFrame);
            if (srcDisplayIdx >= 0) this._displayOrder.splice(srcDisplayIdx, 1);
            this._displayOrder.push(srcFrame);
            if (!this.selectedSet.has(srcFrame)) this.selectedSet.add(srcFrame);
            this._filmstripDragFrame = null;
            this._refreshAll();
            this._setStatus(`Moved frame ${srcFrame + 1} to end (position ${this.frameOrder.length})`);
        });

        this.filmstrip.appendChild(endZone);

        // Scroll-on-hover edges (same as FacePoke)
        let scrollTimer: ReturnType<typeof setInterval> | null = null;
        this.filmstrip.addEventListener("mousemove", (e: MouseEvent) => {
            const rect = this.filmstrip.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const edgeZone = 80;
            if (scrollTimer) { clearInterval(scrollTimer); scrollTimer = null; }
            if (x < edgeZone) {
                const speed = 4 * (1 - x / edgeZone);
                scrollTimer = setInterval(() => { this.filmstrip.scrollLeft -= speed * 3; }, 16);
            } else if (x > rect.width - edgeZone) {
                const speed = 4 * (1 - (rect.width - x) / edgeZone);
                scrollTimer = setInterval(() => { this.filmstrip.scrollLeft += speed * 3; }, 16);
            }
        });
        this.filmstrip.addEventListener("mouseleave", () => {
            if (scrollTimer) { clearInterval(scrollTimer); scrollTimer = null; }
        });
    }

    private _updateFilmstripActive(): void {
        this.filmstrip.querySelectorAll(".fpick-thumb-wrap").forEach((t) => {
            const el = t as HTMLDivElement;
            el.classList.remove("active");
            if (el.dataset.frameIdx === String(this.currentFrame)) {
                el.classList.add("active");
                el.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
            }
        });
    }

    private _updateFilmstripSelection(): void {
        this.filmstrip.querySelectorAll(".fpick-thumb-wrap").forEach((t) => {
            const el = t as HTMLDivElement;
            const idx = parseInt(el.dataset.frameIdx || "0", 10);
            const selected = this.selectedSet.has(idx);
            el.classList.toggle("selected-frame", selected);
            el.classList.toggle("deselected-frame", !selected);
            const selDot = el.querySelector(".fpick-thumb-sel");
            if (selDot) selDot.innerHTML = selected ? iconCheck : iconClose;
        });
    }

    // ── Grid view (secondary — contact sheet) ──────────────────

    private _buildGridView(): void {
        this.gridContainer.innerHTML = "";

        // Show ALL frames in _displayOrder — deselected stay in place, drag-drop moves them
        for (const i of this._displayOrder) {
            const orderIdx = this.frameOrder.indexOf(i);
            const orderPos = this.selectedSet.has(i) && orderIdx >= 0 ? orderIdx + 1 : null;
            const card = document.createElement("div");
            card.className = "fpick-grid-card";
            card.dataset.frame = String(i);
            card.draggable = true;

            if (this.selectedSet.has(i)) {
                card.classList.add("selected");
            } else {
                card.classList.add("deselected");
            }

            const img = document.createElement("img");
            img.className = "fpick-grid-card-img";
            img.alt = `Frame ${i}`;
            img.loading = "lazy";

            const cached = this.thumbnailCache.get(i);
            if (cached) {
                img.src = `data:image/jpeg;base64,${cached}`;
            } else {
                img.style.backgroundColor = "#1a1a2e";
                this._fetchFrameThumb(i).then((url) => {
                    img.src = url;
                    img.style.backgroundColor = "";
                });
            }

            const badge = document.createElement("div");
            badge.className = "fpick-grid-card-badge";
            badge.textContent = String(i + 1);

            const check = document.createElement("div");
            check.className = "fpick-grid-card-check";
            check.innerHTML = this.selectedSet.has(i) ? iconCheck : "";

            if (orderPos !== null) {
                const orderBadge = document.createElement("div");
                orderBadge.className = "fpick-grid-card-order";
                orderBadge.textContent = `#${orderPos}`;
                card.appendChild(orderBadge);
            }

            card.append(img, badge, check);

            card.addEventListener("click", (e: MouseEvent) => {
                this._handleGridClick(i, e);
            });

            // Drag-to-reorder (same positional system as filmstrip)
            card.addEventListener("dragstart", (e: DragEvent) => {
                // Auto-select if not already selected
                if (!this.selectedSet.has(i)) {
                    this._pushUndo();
                    this.selectedSet.add(i);
                    this.frameOrder.push(i);
                }
                this._filmstripDragFrame = i;
                e.dataTransfer!.effectAllowed = "move";
                e.dataTransfer!.setData("text/plain", String(i));
                card.classList.add("dragging");
            });

            card.addEventListener("dragend", () => {
                card.classList.remove("dragging");
                this._filmstripDragFrame = null;
                this._lastSpreadTarget = null;
                this._lastSpreadSide = null;
                this._clearGridSpread();
            });

            card.addEventListener("dragover", (e: DragEvent) => {
                if (this._filmstripDragFrame === null) return;
                e.preventDefault();
                e.dataTransfer!.dropEffect = "move";
                const rect = card.getBoundingClientRect();
                const relX = (e.clientX - rect.left) / rect.width;
                // Dead zone in center 40-60% to prevent flickering
                let side: "left" | "right";
                if (relX < 0.4) side = "left";
                else if (relX > 0.6) side = "right";
                else side = this._lastSpreadSide || (relX < 0.5 ? "left" : "right");
                if (card !== this._lastSpreadTarget || side !== this._lastSpreadSide) {
                    this._applyGridSpread(card, side);
                }
            });

            card.addEventListener("dragleave", () => {
                // Don't clear here — let the next dragover on the next element update state
            });

            card.addEventListener("drop", (e: DragEvent) => {
                e.preventDefault();
                this._clearGridSpread();
                const srcFrame = this._filmstripDragFrame;
                if (srcFrame === null || srcFrame === i) return;

                const rect = card.getBoundingClientRect();
                const midX = rect.left + rect.width / 2;
                const dropAfter = e.clientX >= midX;

                this._reorderFrameInFilmstrip(srcFrame, i, dropAfter);
                this._filmstripDragFrame = null;
            });

            this.gridContainer.appendChild(card);
        }

        // End drop zone (allows dropping after last card)
        const endZone = document.createElement("div");
        endZone.className = "fpick-grid-card";
        endZone.style.cssText = `
            display: flex;
            align-items: center;
            justify-content: center;
            border: 2px dashed rgba(255,255,255,0.08);
            background: transparent;
            min-height: 80px;
            font-size: 11px;
            color: rgba(255,255,255,0.15);
            transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
            cursor: default;
        `;
        endZone.innerHTML = iconPlusCircle;
        endZone.draggable = false;

        endZone.addEventListener("dragover", (e: DragEvent) => {
            if (this._filmstripDragFrame === null) return;
            e.preventDefault();
            e.dataTransfer!.dropEffect = "move";
            endZone.style.borderColor = "#6366f1";
            endZone.style.background = "rgba(99, 102, 241, 0.08)";
            endZone.style.boxShadow = "0 0 16px rgba(99, 102, 241, 0.3)";
            endZone.style.color = "#818cf8";
        });
        endZone.addEventListener("dragleave", () => {
            endZone.style.borderColor = "rgba(255,255,255,0.08)";
            endZone.style.background = "transparent";
            endZone.style.boxShadow = "";
            endZone.style.color = "rgba(255,255,255,0.15)";
        });
        endZone.addEventListener("drop", (e: DragEvent) => {
            e.preventDefault();
            endZone.style.borderColor = "rgba(255,255,255,0.08)";
            endZone.style.background = "transparent";
            endZone.style.boxShadow = "";
            endZone.style.color = "rgba(255,255,255,0.15)";
            const srcFrame = this._filmstripDragFrame;
            if (srcFrame === null) return;

            this._pushUndo();
            const srcIdx = this.frameOrder.indexOf(srcFrame);
            if (srcIdx >= 0) this.frameOrder.splice(srcIdx, 1);
            this.frameOrder.push(srcFrame);
            // Update display order
            const srcDisplayIdx = this._displayOrder.indexOf(srcFrame);
            if (srcDisplayIdx >= 0) this._displayOrder.splice(srcDisplayIdx, 1);
            this._displayOrder.push(srcFrame);
            if (!this.selectedSet.has(srcFrame)) this.selectedSet.add(srcFrame);
            this._filmstripDragFrame = null;
            this._refreshAll();
            this._setStatus(`Moved frame ${srcFrame + 1} to end (position ${this.frameOrder.length})`);
        });

        this.gridContainer.appendChild(endZone);
    }

    private _refreshGridView(): void {
        if (!this._gridMode) return;
        const cards = this.gridContainer.querySelectorAll(".fpick-grid-card") as NodeListOf<HTMLDivElement>;
        cards.forEach((card) => {
            const idx = parseInt(card.dataset.frame || "0", 10);
            const selected = this.selectedSet.has(idx);
            card.classList.toggle("selected", selected);
            card.classList.toggle("deselected", !selected);
            const check = card.querySelector(".fpick-grid-card-check");
            if (check) check.innerHTML = selected ? iconCheck : "";

            let orderBadge = card.querySelector(".fpick-grid-card-order") as HTMLDivElement | null;
            const orderIdx = this.frameOrder.indexOf(idx);
            if (selected && orderIdx >= 0) {
                if (!orderBadge) {
                    orderBadge = document.createElement("div");
                    orderBadge.className = "fpick-grid-card-order";
                    card.appendChild(orderBadge);
                }
                orderBadge.textContent = String(orderIdx + 1);
            } else if (orderBadge) {
                orderBadge.remove();
            }
        });
    }

    // ── Click handlers ─────────────────────────────────────────

    private _handleGridClick(frameIdx: number, e: MouseEvent): void {
        this._pushUndo();

        if (e.shiftKey && this.lastClickedFrame >= 0) {
            const start = Math.min(this.lastClickedFrame, frameIdx);
            const end = Math.max(this.lastClickedFrame, frameIdx);
            for (let i = start; i <= end; i++) {
                this.selectedSet.add(i);
                if (!this.frameOrder.includes(i)) this.frameOrder.push(i);
            }
        } else if (e.ctrlKey || e.metaKey) {
            this._doToggle(frameIdx);
        } else {
            this._doToggle(frameIdx);
        }

        this.lastClickedFrame = frameIdx;
        this._refreshAll();
    }

    private _handleFilmstripShiftClick(frameIdx: number): void {
        if (this.lastClickedFrame < 0) {
            this._goToFrame(frameIdx);
            return;
        }
        this._pushUndo();
        const start = Math.min(this.lastClickedFrame, frameIdx);
        const end = Math.max(this.lastClickedFrame, frameIdx);
        for (let i = start; i <= end; i++) {
            this.selectedSet.add(i);
            if (!this.frameOrder.includes(i)) this.frameOrder.push(i);
        }
        this.lastClickedFrame = frameIdx;
        this._goToFrame(frameIdx);
        this._refreshAll();
    }

    // ── Toggle / reorder ───────────────────────────────────────

    private _doToggle(idx: number): void {
        if (this.selectedSet.has(idx)) {
            this.selectedSet.delete(idx);
            this.frameOrder = this.frameOrder.filter((i) => i !== idx);
        } else {
            this.selectedSet.add(idx);
            // Insert at correct sorted position (maintain natural order among selected)
            let insertPos = this.frameOrder.length;
            for (let i = 0; i < this.frameOrder.length; i++) {
                if (this.frameOrder[i] > idx) {
                    insertPos = i;
                    break;
                }
            }
            this.frameOrder.splice(insertPos, 0, idx);
        }
    }

    private _toggleFrame(idx: number): void {
        this._pushUndo();
        const wasSelected = this.selectedSet.has(idx);
        this._doToggle(idx);
        this.lastClickedFrame = idx;

        // If deselected and this is the current canvas frame, skip to nearest selected
        if (wasSelected && this.currentFrame === idx && this.selectedSet.size > 0) {
            const nearest = this._findNearestSelected(idx);
            if (nearest !== null) {
                this._goToFrame(nearest);
            }
        }
        this._refreshAll();
    }

    private _findNearestSelected(fromIdx: number): number | null {
        // Search forward first, then backward
        for (let i = fromIdx + 1; i < this.totalFrames; i++) {
            if (this.selectedSet.has(i)) return i;
        }
        for (let i = fromIdx - 1; i >= 0; i--) {
            if (this.selectedSet.has(i)) return i;
        }
        return null;
    }

    private _reorderFrame(srcFrame: number, targetFrame: number): void {
        const srcIdx = this.frameOrder.indexOf(srcFrame);
        const tgtIdx = this.frameOrder.indexOf(targetFrame);
        if (srcIdx < 0 || tgtIdx < 0) return;
        this._pushUndo();
        this.frameOrder.splice(srcIdx, 1);
        this.frameOrder.splice(tgtIdx, 0, srcFrame);
        this._refreshAll();
    }

    private _reorderFrameInFilmstrip(srcFrame: number, targetFrame: number, insertAfter: boolean): void {
        const srcIdx = this.frameOrder.indexOf(srcFrame);
        if (srcIdx < 0) return;

        // If target isn't in frameOrder yet, auto-select it
        if (!this.selectedSet.has(targetFrame)) {
            this.selectedSet.add(targetFrame);
            this.frameOrder.push(targetFrame);
        }

        const tgtIdx = this.frameOrder.indexOf(targetFrame);
        if (tgtIdx < 0) return;

        this._pushUndo();

        // Update frameOrder (output sequence)
        this.frameOrder.splice(srcIdx, 1);
        let insertIdx = this.frameOrder.indexOf(targetFrame);
        if (insertAfter) insertIdx += 1;
        this.frameOrder.splice(insertIdx, 0, srcFrame);

        // Update displayOrder (visual position)
        const srcDisplayIdx = this._displayOrder.indexOf(srcFrame);
        const tgtDisplayIdx = this._displayOrder.indexOf(targetFrame);
        if (srcDisplayIdx >= 0 && tgtDisplayIdx >= 0) {
            this._displayOrder.splice(srcDisplayIdx, 1);
            let visualInsertIdx = this._displayOrder.indexOf(targetFrame);
            if (insertAfter) visualInsertIdx += 1;
            this._displayOrder.splice(visualInsertIdx, 0, srcFrame);
        }

        this._refreshAll();
        this._goToFrame(srcFrame);
        this._setStatus(`Moved frame ${srcFrame + 1} to position ${insertIdx + 1}`);
    }

    // ── Filmstrip spread-apart animation ────────────────────────

    private _applyFilmstripSpread(hoverWrapper: HTMLElement, side: "left" | "right"): void {
        // Skip if same target+side (prevents flicker)
        if (hoverWrapper === this._lastSpreadTarget && side === this._lastSpreadSide) return;
        this._clearFilmstripSpread();
        this._lastSpreadTarget = hoverWrapper;
        this._lastSpreadSide = side;

        const thumbs = Array.from(this.filmstrip.querySelectorAll(".fpick-thumb-wrap")) as HTMLElement[];
        const idx = thumbs.indexOf(hoverWrapper);
        if (idx < 0) return;

        if (side === "left") {
            hoverWrapper.classList.add("spread-right");
            if (idx > 0) thumbs[idx - 1].classList.add("spread-left");
        } else {
            hoverWrapper.classList.add("spread-left");
            if (idx < thumbs.length - 1) thumbs[idx + 1].classList.add("spread-right");
        }
    }

    private _clearFilmstripSpread(): void {
        this.filmstrip.querySelectorAll(".spread-left, .spread-right").forEach((el) => {
            el.classList.remove("spread-left", "spread-right");
        });
    }

    // ── Grid spread-apart animation ────────────────────────────

    private _applyGridSpread(hoverCard: HTMLElement, side: "left" | "right"): void {
        // Skip if same target+side (prevents flicker)
        if (hoverCard === this._lastSpreadTarget && side === this._lastSpreadSide) return;
        this._clearGridSpread();
        this._lastSpreadTarget = hoverCard;
        this._lastSpreadSide = side;

        const cards = Array.from(this.gridContainer.querySelectorAll(".fpick-grid-card")) as HTMLElement[];
        const idx = cards.indexOf(hoverCard);
        if (idx < 0) return;

        if (side === "left") {
            hoverCard.classList.add("grid-spread-right");
            if (idx > 0) cards[idx - 1].classList.add("grid-spread-left");
        } else {
            hoverCard.classList.add("grid-spread-left");
            if (idx < cards.length - 1) cards[idx + 1].classList.add("grid-spread-right");
        }
    }

    private _clearGridSpread(): void {
        this.gridContainer.querySelectorAll(".grid-spread-left, .grid-spread-right, .drag-over-left, .drag-over-right").forEach((el) => {
            el.classList.remove("grid-spread-left", "grid-spread-right", "drag-over-left", "drag-over-right");
        });
    }

    // ── Selection tools ────────────────────────────────────────

    private _resetAll(): void {
        this._pushUndo();
        this.selectedSet.clear();
        this.frameOrder = [];
        this._displayOrder = [];
        for (let i = 0; i < this.totalFrames; i++) {
            this.selectedSet.add(i);
            this.frameOrder.push(i);
            this._displayOrder.push(i);
        }
        this._refreshAll();
        this._setStatus("Reset to original order — all frames selected");
    }

    private _selectAll(): void {
        this._pushUndo();
        this.selectedSet.clear();
        this.frameOrder = [];
        for (let i = 0; i < this.totalFrames; i++) {
            this.selectedSet.add(i);
            this.frameOrder.push(i);
        }
        this._refreshAll();
    }

    private _deselectAll(): void {
        this._pushUndo();
        this.selectedSet.clear();
        this.frameOrder = [];
        this._refreshAll();
    }

    private _invertSelection(): void {
        this._pushUndo();
        const newSelected = new Set<number>();
        const newOrder: number[] = [];
        for (let i = 0; i < this.totalFrames; i++) {
            if (!this.selectedSet.has(i)) {
                newSelected.add(i);
                newOrder.push(i);
            }
        }
        this.selectedSet = newSelected;
        this.frameOrder = newOrder;
        this._refreshAll();
    }

    private _selectEveryNth(n: number): void {
        this._pushUndo();
        this.selectedSet.clear();
        this.frameOrder = [];
        for (let i = 0; i < this.totalFrames; i += n) {
            this.selectedSet.add(i);
            this.frameOrder.push(i);
        }
        this._refreshAll();
        this._setStatus(`Selected every ${n}${n === 2 ? "nd" : n === 3 ? "rd" : "th"} frame (${this.selectedSet.size} frames)`);
    }

    // ── Refresh all UI ─────────────────────────────────────────

    private _refreshAll(): void {
        this._updateCanvasOverlay();
        this._buildFilmstrip(); // Full rebuild to reflect order + positions
        this._buildGridView();  // Full rebuild so frames physically reorder
        this._updateSummary();
        this._updateOrderPreview();
        this._updateSelectedCount();
    }

    private _updateFrameInfo(): void {
        const info = document.getElementById("fpick-frame-info");
        if (info) {
            info.textContent = `${this.totalFrames} frames @ ${this.videoFps.toFixed(1)} fps — ${this.videoWidth}×${this.videoHeight}`;
        }
    }

    private _updateSummary(): void {
        const totalEl = document.getElementById("fpick-total");
        const selEl = document.getElementById("fpick-sel-count");
        const remEl = document.getElementById("fpick-rem-count");
        const durEl = document.getElementById("fpick-duration");

        if (totalEl) totalEl.textContent = String(this.totalFrames);
        if (selEl) selEl.textContent = String(this.selectedSet.size);
        if (remEl) remEl.textContent = String(this.totalFrames - this.selectedSet.size);
        if (durEl) {
            const outputFrames = this.frameOrder.length;
            const dur = outputFrames / (this.videoFps || 24);
            durEl.textContent = `${dur.toFixed(2)}s (${outputFrames} frames)`;
        }
    }

    private _updateOrderPreview(): void {
        const preview = this.sidebar.querySelector(".fpick-order-preview") as HTMLDivElement | null;
        if (!preview) return;

        preview.innerHTML = "";
        const shown = this.frameOrder.slice(0, 100);
        for (const idx of shown) {
            const item = document.createElement("div");
            item.className = "fpick-order-item";

            const img = document.createElement("img");
            const cached = this.thumbnailCache.get(idx);
            if (cached) img.src = `data:image/jpeg;base64,${cached}`;
            img.alt = `Frame ${idx}`;

            const num = document.createElement("div");
            num.className = "fpick-order-item-num";
            num.textContent = String(idx);

            item.append(img, num);
            preview.appendChild(item);
        }

        if (this.frameOrder.length > 100) {
            const more = document.createElement("div");
            more.style.cssText = "font-size:10px;color:#8888aa;padding:4px;";
            more.textContent = `+${this.frameOrder.length - 100} more`;
            preview.appendChild(more);
        }
    }

    private _updateSelectedCount(): void {
        const el = document.getElementById("fpick-selected-count");
        if (el) el.textContent = `${this.selectedSet.size} / ${this.totalFrames} selected`;
    }

    // ── Fetch frame (full-size for canvas) ─────────────────────

    private async _fetchFrame(idx: number): Promise<string> {
        const resp = await api.fetchApi("/framepicker/get_frame", {
            method: "POST",
            body: JSON.stringify({
                video_path: this.videoPath,
                frame_idx: idx,
                thumb_width: 960,
            }),
        });
        const blob = await resp.blob();
        return URL.createObjectURL(blob);
    }

    // ── Fetch thumbnail (small, for filmstrip + grid) ──────────

    private async _fetchFrameThumb(idx: number): Promise<string> {
        // Check cache first
        const cached = this.thumbnailCache.get(idx);
        if (cached) return `data:image/jpeg;base64,${cached}`;

        const resp = await api.fetchApi("/framepicker/get_frame", {
            method: "POST",
            body: JSON.stringify({
                video_path: this.videoPath,
                frame_idx: idx,
                thumb_width: 160,
            }),
        });
        const blob = await resp.blob();
        // Store in cache as base64
        const b64 = await this._blobToBase64(blob);
        this.thumbnailCache.set(idx, b64);
        return URL.createObjectURL(blob);
    }

    private _blobToBase64(blob: Blob): Promise<string> {
        return new Promise((resolve) => {
            const reader = new FileReader();
            reader.onload = () => {
                const result = reader.result as string;
                resolve(result.split(",")[1] || "");
            };
            reader.readAsDataURL(blob);
        });
    }

    // ── Undo / Redo ────────────────────────────────────────────

    private _pushUndo(): void {
        const state = JSON.stringify({
            selected: Array.from(this.selectedSet),
            order: this.frameOrder,
        });
        this._undoStack.push(state);
        if (this._undoStack.length > 50) this._undoStack.shift();
        this._redoStack = [];
    }

    private _undo(): void {
        if (this._undoStack.length === 0) { this._setStatus("Nothing to undo"); return; }
        const current = JSON.stringify({ selected: Array.from(this.selectedSet), order: this.frameOrder });
        this._redoStack.push(current);
        const prev = JSON.parse(this._undoStack.pop()!);
        this.selectedSet = new Set(prev.selected);
        this.frameOrder = prev.order;
        this._refreshAll();
        this._setStatus("Undone");
    }

    private _redo(): void {
        if (this._redoStack.length === 0) { this._setStatus("Nothing to redo"); return; }
        const current = JSON.stringify({ selected: Array.from(this.selectedSet), order: this.frameOrder });
        this._undoStack.push(current);
        const next = JSON.parse(this._redoStack.pop()!);
        this.selectedSet = new Set(next.selected);
        this.frameOrder = next.order;
        this._refreshAll();
        this._setStatus("Redone");
    }

    // ── Keyboard handler ───────────────────────────────────────

    private _handleKey(e: KeyboardEvent): void {
        if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

        if (e.key === "Escape") { this._cancel(); return; }
        if (e.key === " ") { e.preventDefault(); this._toggleFrame(this.currentFrame); return; }
        if (e.key === "p" || e.key === "P") { this._togglePlayback(); return; }

        // Arrow keys: browse ALL frames (non-destructive, includes deselected)
        if (e.key === "ArrowRight") {
            e.preventDefault();
            const step = e.shiftKey ? 10 : 1;
            const curDisplayIdx = this._displayOrder.indexOf(this.currentFrame);
            const nextIdx = Math.min(curDisplayIdx + step, this._displayOrder.length - 1);
            this._goToFrame(this._displayOrder[nextIdx]);
            return;
        }
        if (e.key === "ArrowLeft") {
            e.preventDefault();
            const step = e.shiftKey ? 10 : 1;
            const curDisplayIdx = this._displayOrder.indexOf(this.currentFrame);
            const prevIdx = Math.max(curDisplayIdx - step, 0);
            this._goToFrame(this._displayOrder[prevIdx]);
            return;
        }
        if (e.key === "Home") { e.preventDefault(); this._goToFrame(this._displayOrder[0]); return; }
        if (e.key === "End") { e.preventDefault(); this._goToFrame(this._displayOrder[this._displayOrder.length - 1]); return; }
        if (e.key === "Enter") { e.preventDefault(); this._apply(); return; }
        if (e.key === "+" || e.key === "=") { e.preventDefault(); this._zoomStep(25); return; }
        if (e.key === "-" || e.key === "_") { e.preventDefault(); this._zoomStep(-25); return; }

        if ((e.key === "a" || e.key === "A") && !e.ctrlKey && !e.metaKey) { this._selectAll(); return; }
        if (e.key === "d" || e.key === "D") { this._deselectAll(); return; }
        if (e.key === "i" || e.key === "I") { this._invertSelection(); return; }
        if (e.key === "h" || e.key === "H") { this._flipCurrentH(); return; }
        if ((e.key === "v" || e.key === "V") && !e.ctrlKey && !e.metaKey) { this._flipCurrentV(); return; }
        if (e.key === "r" || e.key === "R") { this._rotateCurrentCW(); return; }
        if (e.key === "g" || e.key === "G") {
            this._gridMode = !this._gridMode;
            this.panel.classList.toggle("grid-mode", this._gridMode);
            const viewBtn = this.panel.querySelector(".fpick-btn-view") as HTMLElement;
            if (viewBtn) {
                viewBtn.classList.toggle("active", this._gridMode);
                viewBtn.innerHTML = this._gridMode ? `${iconFilmstrip} Filmstrip` : `${iconGrid} Grid`;
            }
            if (this._gridMode) this._buildGridView();
            return;
        }

        if (e.key === "Delete" || e.key === "Backspace") {
            e.preventDefault();
            if (this.selectedSet.has(this.currentFrame)) {
                this._toggleFrame(this.currentFrame);
            }
            return;
        }

        // Copy/Paste
        if (e.key === "c" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); this._copyFrame(); return; }
        if (e.key === "v" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); this._pasteFrame(); return; }

        if (e.key === "z" && (e.ctrlKey || e.metaKey) && !e.shiftKey) { e.preventDefault(); this._undo(); return; }
        if ((e.key === "y" && (e.ctrlKey || e.metaKey)) || (e.key === "z" && (e.ctrlKey || e.metaKey) && e.shiftKey)) {
            e.preventDefault(); this._redo(); return;
        }

        // Number keys 1-9: jump to 10%..90% of frames
        const num = parseInt(e.key, 10);
        if (num >= 1 && num <= 9 && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
            e.preventDefault();
            const targetIdx = Math.round((num / 10) * (this._displayOrder.length - 1));
            this._goToFrame(this._displayOrder[targetIdx]);
            this._setStatus(`Jumped to ${num * 10}% (frame ${this._displayOrder[targetIdx] + 1})`);
            return;
        }

        // F: toggle fullscreen
        if ((e.key === "f" || e.key === "F") && !e.ctrlKey && !e.metaKey) {
            e.preventDefault();
            if (document.fullscreenElement) {
                document.exitFullscreen();
            } else {
                this.dialog.requestFullscreen?.().catch(() => {});
            }
            return;
        }
    }

    // ── Zoom helpers ─────────────────────────────────────────────────

    private _zoomStep(delta: number): void {
        if (!this._zoomSlider) return;
        const cur = parseInt(this._zoomSlider.value, 10);
        const next = Math.max(parseInt(this._zoomSlider.min, 10), Math.min(parseInt(this._zoomSlider.max, 10), cur + delta));
        this._zoomSlider.value = String(next);
        this._zoomSlider.dispatchEvent(new Event("input"));
    }

    // ── Copy / Paste ──────────────────────────────────────────────

    private _copyFrame(): void {
        this._clipboard = this.currentFrame;
        this._setStatus(`Copied frame ${this.currentFrame + 1} — press Ctrl+V to paste duplicate`);
    }

    private _pasteFrame(): void {
        if (this._clipboard === null) {
            this._setStatus("Nothing copied — select a frame and press Ctrl+C first");
            return;
        }

        this._pushUndo();

        // Ensure the source frame is selected
        if (!this.selectedSet.has(this._clipboard)) {
            this.selectedSet.add(this._clipboard);
        }

        // Insert after the current frame's position in frameOrder, or at the end
        const currentOrderIdx = this.frameOrder.indexOf(this.currentFrame);
        const insertAt = currentOrderIdx >= 0 ? currentOrderIdx + 1 : this.frameOrder.length;

        // Duplicate: same frame index appears again in the order
        this.frameOrder.splice(insertAt, 0, this._clipboard);

        this._refreshAll();
        this._setStatus(`Pasted frame ${this._clipboard + 1} at position ${insertAt + 1}`);
    }

    // ── Frame Transforms ─────────────────────────────────────────

    private _getOrCreateTransform(idx: number): { flipH: boolean; flipV: boolean; rotate: number } {
        let t = this._frameTransforms.get(idx);
        if (!t) {
            t = { flipH: false, flipV: false, rotate: 0 };
            this._frameTransforms.set(idx, t);
        }
        return t;
    }

    private _flipCurrentH(): void {
        const t = this._getOrCreateTransform(this.currentFrame);
        t.flipH = !t.flipH;
        this._applyCanvasTransform();
        this._updateCanvasOverlay();
        this._setStatus(`Frame ${this.currentFrame + 1}: Flip H ${t.flipH ? "ON" : "OFF"}`);
    }

    private _flipCurrentV(): void {
        const t = this._getOrCreateTransform(this.currentFrame);
        t.flipV = !t.flipV;
        this._applyCanvasTransform();
        this._updateCanvasOverlay();
        this._setStatus(`Frame ${this.currentFrame + 1}: Flip V ${t.flipV ? "ON" : "OFF"}`);
    }

    private _rotateCurrentCW(): void {
        const t = this._getOrCreateTransform(this.currentFrame);
        t.rotate = (t.rotate + 90) % 360;
        this._applyCanvasTransform();
        this._updateCanvasOverlay();
        this._setStatus(`Frame ${this.currentFrame + 1}: Rotated ${t.rotate}°`);
    }

    private _reverseOrder(): void {
        if (this.frameOrder.length < 2) {
            this._setStatus("Need at least 2 selected frames to reverse");
            return;
        }
        this._pushUndo();
        this.frameOrder.reverse();
        this._refreshAll();
        this._setStatus(`Reversed frame order (${this.frameOrder.length} frames)`);
    }

    private _holdFrame(copies: number): void {
        if (!this.selectedSet.has(this.currentFrame)) {
            this._setStatus("Select the frame first before holding");
            return;
        }
        this._pushUndo();
        const currentOrderIdx = this.frameOrder.indexOf(this.currentFrame);
        if (currentOrderIdx < 0) return;
        const dupes = Array(copies).fill(this.currentFrame);
        this.frameOrder.splice(currentOrderIdx + 1, 0, ...dupes);
        this._refreshAll();
        this._setStatus(`Held frame ${this.currentFrame + 1} ×${copies + 1}`);
    }

    private _getTransformLabel(idx: number): string {
        const t = this._frameTransforms.get(idx);
        if (!t) return "";
        const parts: string[] = [];
        if (t.flipH) parts.push("FlipH");
        if (t.flipV) parts.push("FlipV");
        if (t.rotate) parts.push(`${t.rotate}°`);
        return parts.length > 0 ? ` [${parts.join(", ")}]` : "";
    }

    // ── Playback ───────────────────────────────────────────────

    private _togglePlayback(): void {
        if (this._playing) {
            this._stopPlayback();
        } else {
            this._startPlayback();
        }
    }

    private _startPlayback(): void {
        if (this.frameOrder.length === 0) {
            this._setStatus("No frames selected to play");
            return;
        }
        this._playing = true;
        this._playIdx = 0;

        // Update button
        if (this._playBtn) {
            this._playBtn.innerHTML = `${iconPause} Pause`;
            this._playBtn.classList.add("active");
        }

        this._setStatus(`▶ Playing ${this.frameOrder.length} selected frames...`);
        this._playNextFrame();
    }

    private _stopPlayback(): void {
        this._playing = false;
        if (this._playTimer) {
            clearTimeout(this._playTimer);
            this._playTimer = null;
        }

        // Update button
        if (this._playBtn) {
            this._playBtn.innerHTML = `${iconPlay} Play`;
            this._playBtn.classList.remove("active");
        }

        this._setStatus("Playback stopped");
    }

    private _playNextFrame(): void {
        if (!this._playing || this.frameOrder.length === 0) {
            this._stopPlayback();
            return;
        }

        // Loop: wrap around to start
        if (this._playIdx >= this.frameOrder.length) {
            this._playIdx = 0;
        }

        const frameIdx = this.frameOrder[this._playIdx];
        this._goToFrame(frameIdx);
        this._playIdx++;

        const delayMs = 1000 / (this.videoFps || 24);
        this._playTimer = setTimeout(() => this._playNextFrame(), delayMs);
    }

    // ── Apply / Cancel ─────────────────────────────────────────

    private _apply(): void {
        this.close();
        // Pass transforms that have actual changes
        const activeTransforms = new Map<number, { flipH: boolean; flipV: boolean; rotate: number }>();
        for (const [idx, t] of this._frameTransforms) {
            if (t.flipH || t.flipV || t.rotate !== 0) {
                activeTransforms.set(idx, { ...t });
            }
        }
        this.callbacks.onApply([...this.frameOrder], activeTransforms.size > 0 ? activeTransforms : undefined);
    }

    private _cancel(): void {
        this.close();
        this.callbacks.onCancel();
    }

    // ── Helpers ─────────────────────────────────────────────────

    private _setStatus(msg: string): void {
        this.statusEl.textContent = msg;
    }

    private _makeBtn(html: string, cls: string, onClick: () => void): HTMLButtonElement {
        const btn = document.createElement("button");
        btn.className = `fpick-btn ${cls}`;
        btn.innerHTML = html;
        btn.addEventListener("click", onClick);
        btn.onpointerdown = (e) => e.stopPropagation();
        return btn;
    }
}
