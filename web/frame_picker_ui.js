var __defProp = Object.defineProperty;
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { a0 as iconFilmstrip, a as iconGrid, J as iconUndo, K as iconRedo, p as iconCheck, y as iconClose, Q as iconSkipStart, a1 as iconPrev, S as iconPlay, a2 as iconNext, a3 as iconSkipEnd, a4 as iconSelectAll, a5 as iconDeselect, c as iconInvert, n as iconReset, r as iconFlip, s as iconFlipVertical, k as iconRotateCW, Z as iconReverse, V as iconPause, a6 as iconPlusCircle } from "./_chunks/icons-BOh8YpxI.js";
class FramePickerModal {
  constructor(callbacks) {
    __publicField(this, "dialog");
    __publicField(this, "panel");
    __publicField(this, "canvasArea");
    __publicField(this, "canvasImg");
    __publicField(this, "canvasOverlay");
    __publicField(this, "filmstrip");
    __publicField(this, "gridArea");
    __publicField(this, "gridContainer");
    __publicField(this, "sidebar");
    __publicField(this, "statusEl");
    __publicField(this, "callbacks");
    __publicField(this, "_isOpen", false);
    __publicField(this, "_gridMode", false);
    __publicField(this, "videoPath", "");
    __publicField(this, "totalFrames", 0);
    __publicField(this, "videoFps", 24);
    __publicField(this, "videoWidth", 0);
    __publicField(this, "videoHeight", 0);
    // Selection state
    __publicField(this, "currentFrame", 0);
    __publicField(this, "selectedSet", /* @__PURE__ */ new Set());
    __publicField(this, "frameOrder", []);
    __publicField(this, "_displayOrder", []);
    // Visual position of ALL frames
    __publicField(this, "lastClickedFrame", -1);
    // Thumbnail cache (base64 strings)
    __publicField(this, "thumbnailCache", /* @__PURE__ */ new Map());
    // Undo/redo
    __publicField(this, "_undoStack", []);
    __publicField(this, "_redoStack", []);
    // Playback state
    __publicField(this, "_playing", false);
    __publicField(this, "_playTimer", null);
    __publicField(this, "_playIdx", 0);
    __publicField(this, "_playBtn", null);
    // Filmstrip drag state
    __publicField(this, "_filmstripDragFrame", null);
    __publicField(this, "_lastSpreadTarget", null);
    __publicField(this, "_lastSpreadSide", null);
    // Clipboard for copy/paste
    __publicField(this, "_clipboard", null);
    // Filmstrip zoom
    __publicField(this, "_thumbScale", 1);
    __publicField(this, "_zoomSlider", null);
    // Per-frame transforms {frameIdx -> {flipH, flipV, rotate}}
    __publicField(this, "_frameTransforms", /* @__PURE__ */ new Map());
    // Event handlers
    __publicField(this, "_keyHandler", null);
    __publicField(this, "_wheelHandler", null);
    // Loading state
    __publicField(this, "_loadingOverlay", null);
    __publicField(this, "_loadedThumbCount", 0);
    __publicField(this, "_totalThumbCount", 0);
    this.callbacks = callbacks;
    document.querySelectorAll(".fpick-backdrop").forEach((d) => d.remove());
    this.dialog = document.createElement("div");
    this.dialog.className = "fpick-backdrop";
    this.dialog.style.display = "none";
    this.dialog.setAttribute("role", "dialog");
    this.dialog.setAttribute("aria-modal", "true");
    this.dialog.setAttribute("aria-label", "Frame Picker");
    this.panel = document.createElement("div");
    this.panel.className = "fpick-panel";
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
    this.canvasArea = document.createElement("div");
    this.canvasArea.className = "fpick-canvas-area";
    this.canvasImg = document.createElement("img");
    this.canvasImg.className = "fpick-canvas";
    this.canvasImg.alt = "Current frame";
    this.canvasOverlay = document.createElement("div");
    this.canvasOverlay.className = "fpick-canvas-overlay";
    this.canvasArea.append(this.canvasImg, this.canvasOverlay);
    this.canvasImg.addEventListener("click", () => {
      this._toggleFrame(this.currentFrame);
    });
    this.filmstrip = document.createElement("div");
    this.filmstrip.className = "fpick-filmstrip";
    this.gridArea = document.createElement("div");
    this.gridArea.className = "fpick-grid-area";
    this.gridContainer = document.createElement("div");
    this.gridContainer.className = "fpick-grid";
    this.gridArea.appendChild(this.gridContainer);
    this.sidebar = document.createElement("div");
    this.sidebar.className = "fpick-sidebar";
    this._buildSidebar();
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
    this.panel.append(header, this.canvasArea, this.filmstrip, this.gridArea, this.sidebar, toolbar);
    this.dialog.appendChild(this.panel);
    document.body.appendChild(this.dialog);
  }
  // ── Sidebar builder ────────────────────────────────────────
  _buildSidebar() {
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
    const orderSection = document.createElement("div");
    const orderTitle = document.createElement("div");
    orderTitle.className = "fpick-section-title";
    orderTitle.textContent = "FRAME ORDER PREVIEW";
    orderSection.appendChild(orderTitle);
    const orderPreview = document.createElement("div");
    orderPreview.className = "fpick-order-preview";
    orderSection.appendChild(orderPreview);
    const helpSection = document.createElement("div");
    const helpTitle = document.createElement("div");
    helpTitle.className = "fpick-section-title";
    helpTitle.textContent = "SHORTCUTS";
    helpSection.appendChild(helpTitle);
    const shortcuts = [
      ["Space", "Toggle frame"],
      ["P", "Play/Pause"],
      ["A", "Select all"],
      ["D", "Deselect all"],
      ["I", "Invert"],
      ["G", "Grid view"],
      ["Ctrl+C", "Copy frame"],
      ["Ctrl+V", "Paste (duplicate)"],
      ["H", "Flip Horizontal"],
      ["V", "Flip Vertical"],
      ["R", "Rotate 90° CW"],
      ["Del", "Deselect"],
      ["←→", "Navigate"],
      ["Scroll", "Browse"],
      ["Drag", "Reorder frames"],
      ["Ctrl+Z/Y", "Undo/Redo"],
      ["Esc", "Cancel"]
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
  async open(videoPath, initialSelection) {
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
    this._keyHandler = (e) => this._handleKey(e);
    document.addEventListener("keydown", this._keyHandler);
    this._wheelHandler = (e) => {
      e.preventDefault();
      if (e.deltaY > 0) this._nextFrame();
      else if (e.deltaY < 0) this._prevFrame();
    };
    this.canvasArea.addEventListener("wheel", this._wheelHandler, { passive: false });
    try {
      const resp = await api.fetchApi("/framepicker/get_frames", {
        method: "POST",
        body: JSON.stringify({ node_id: "", video_path: videoPath })
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
    this.selectedSet.clear();
    if (initialSelection && initialSelection.length > 0) {
      for (const idx of initialSelection) this.selectedSet.add(idx);
      this.frameOrder = [...initialSelection];
    } else {
      for (let i = 0; i < this.totalFrames; i++) this.selectedSet.add(i);
      this.frameOrder = Array.from({ length: this.totalFrames }, (_, i) => i);
    }
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
  _showLoadingOverlay() {
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
    const spinner = document.createElement("div");
    spinner.style.cssText = `
            width: 48px; height: 48px;
            border: 3px solid rgba(99, 102, 241, 0.15);
            border-top-color: #818cf8;
            border-radius: 50%;
            animation: fpick-spin 0.8s linear infinite;
        `;
    const label = document.createElement("div");
    label.className = "fpick-loading-label";
    label.style.cssText = `
            font-size: 13px;
            color: #a0a0c0;
            font-variant-numeric: tabular-nums;
        `;
    label.textContent = `Loading 0 / ${this._totalThumbCount} frames...`;
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
    if (!document.getElementById("fpick-spin-style")) {
      const style = document.createElement("style");
      style.id = "fpick-spin-style";
      style.textContent = `@keyframes fpick-spin { to { transform: rotate(360deg); } }`;
      document.head.appendChild(style);
    }
  }
  _updateLoadingProgress() {
    this._loadedThumbCount++;
    if (!this._loadingOverlay) return;
    const pct = Math.min(100, this._loadedThumbCount / this._totalThumbCount * 100);
    const bar = this._loadingOverlay.querySelector(".fpick-loading-bar");
    const label = this._loadingOverlay.querySelector(".fpick-loading-label");
    if (bar) bar.style.width = `${pct}%`;
    if (label) label.textContent = `Loading ${this._loadedThumbCount} / ${this._totalThumbCount} frames...`;
    if (this._loadedThumbCount >= this._totalThumbCount) {
      this._loadingOverlay.style.opacity = "0";
      setTimeout(() => this._dismissLoadingOverlay(), 400);
    }
  }
  _dismissLoadingOverlay() {
    if (this._loadingOverlay) {
      this._loadingOverlay.remove();
      this._loadingOverlay = null;
    }
  }
  close() {
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
  get isOpen() {
    return this._isOpen;
  }
  setCallbacks(callbacks) {
    this.callbacks = callbacks;
  }
  // ── Canvas (large frame display) ───────────────────────────
  async _loadCanvasFrame() {
    const url = await this._fetchFrame(this.currentFrame);
    this.canvasImg.src = url;
    this._applyCanvasTransform();
    this._updateCanvasOverlay();
  }
  _applyCanvasTransform() {
    const t = this._frameTransforms.get(this.currentFrame);
    if (!t) {
      this.canvasImg.style.transform = "";
      return;
    }
    const parts = [];
    if (t.flipH) parts.push("scaleX(-1)");
    if (t.flipV) parts.push("scaleY(-1)");
    if (t.rotate) parts.push(`rotate(${t.rotate}deg)`);
    this.canvasImg.style.transform = parts.join(" ");
  }
  _updateCanvasOverlay() {
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
  async _goToFrame(idx) {
    this.currentFrame = Math.max(0, Math.min(idx, this.totalFrames - 1));
    await this._loadCanvasFrame();
    this._updateFilmstripActive();
    this._updateFrameInfo();
  }
  _prevFrame() {
    if (this.frameOrder.length === 0) return;
    const curOrderIdx = this.frameOrder.indexOf(this.currentFrame);
    if (curOrderIdx > 0) {
      this._goToFrame(this.frameOrder[curOrderIdx - 1]);
    } else if (curOrderIdx < 0) {
      const nearest = this._findNearestSelected(this.currentFrame);
      if (nearest !== null) this._goToFrame(nearest);
    }
  }
  _nextFrame() {
    if (this.frameOrder.length === 0) return;
    const curOrderIdx = this.frameOrder.indexOf(this.currentFrame);
    if (curOrderIdx >= 0 && curOrderIdx < this.frameOrder.length - 1) {
      this._goToFrame(this.frameOrder[curOrderIdx + 1]);
    } else if (curOrderIdx < 0) {
      const nearest = this._findNearestSelected(this.currentFrame);
      if (nearest !== null) this._goToFrame(nearest);
    }
  }
  // ── Filmstrip builder (matches FacePoke) ───────────────────
  _buildFilmstrip() {
    this.filmstrip.innerHTML = "";
    for (const i of this._displayOrder) {
      const orderIdx = this.frameOrder.indexOf(i);
      const orderPos = this.selectedSet.has(i) && orderIdx >= 0 ? orderIdx + 1 : null;
      const wrapper = document.createElement("div");
      wrapper.className = "fpick-thumb-wrap";
      wrapper.dataset.frameIdx = String(i);
      wrapper.draggable = true;
      if (i === this.currentFrame) wrapper.classList.add("active");
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
      this._fetchFrameThumb(i).then((url) => {
        thumb.src = url;
        this._updateLoadingProgress();
      });
      const frameNum = document.createElement("span");
      frameNum.className = "fpick-thumb-num";
      frameNum.textContent = String(i + 1);
      const selDot = document.createElement("span");
      selDot.className = "fpick-thumb-sel";
      selDot.innerHTML = this.selectedSet.has(i) ? iconCheck : iconClose;
      wrapper.append(thumb, frameNum, selDot);
      if (orderPos !== null) {
        const orderBadge = document.createElement("span");
        orderBadge.className = "fpick-thumb-order";
        orderBadge.textContent = `#${orderPos}`;
        wrapper.appendChild(orderBadge);
      }
      wrapper.addEventListener("click", (e) => {
        if (e.shiftKey && this.lastClickedFrame >= 0) {
          this._pushUndo();
          const start = Math.min(this.lastClickedFrame, i);
          const end = Math.max(this.lastClickedFrame, i);
          for (let f = start; f <= end; f++) {
            if (!this.selectedSet.has(f)) {
              this.selectedSet.add(f);
              let insertPos = this.frameOrder.length;
              for (let j = 0; j < this.frameOrder.length; j++) {
                if (this.frameOrder[j] > f) {
                  insertPos = j;
                  break;
                }
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
      wrapper.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        this._toggleFrame(i);
      });
      wrapper.addEventListener("dragstart", (e) => {
        if (!this.selectedSet.has(i)) {
          this._pushUndo();
          this.selectedSet.add(i);
          this.frameOrder.push(i);
          this._updateFilmstripSelection();
          this._updateSummary();
          this._updateSelectedCount();
        }
        this._filmstripDragFrame = i;
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", String(i));
        wrapper.classList.add("dragging");
      });
      wrapper.addEventListener("dragend", () => {
        wrapper.classList.remove("dragging");
        this._filmstripDragFrame = null;
        this._lastSpreadTarget = null;
        this._lastSpreadSide = null;
        this._clearFilmstripSpread();
      });
      wrapper.addEventListener("dragover", (e) => {
        if (this._filmstripDragFrame === null) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        const rect = wrapper.getBoundingClientRect();
        const relX = (e.clientX - rect.left) / rect.width;
        let side;
        if (relX < 0.4) side = "left";
        else if (relX > 0.6) side = "right";
        else side = this._lastSpreadSide || (relX < 0.5 ? "left" : "right");
        if (wrapper !== this._lastSpreadTarget || side !== this._lastSpreadSide) {
          this._applyFilmstripSpread(wrapper, side);
        }
      });
      wrapper.addEventListener("dragleave", () => {
      });
      wrapper.addEventListener("drop", (e) => {
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
    endZone.addEventListener("dragover", (e) => {
      if (this._filmstripDragFrame === null) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      endZone.style.borderColor = "#6366f1";
      endZone.style.background = "rgba(99, 102, 241, 0.1)";
      endZone.style.boxShadow = "0 0 16px rgba(99, 102, 241, 0.3)";
    });
    endZone.addEventListener("dragleave", () => {
      endZone.style.borderColor = "rgba(255,255,255,0.08)";
      endZone.style.background = "";
      endZone.style.boxShadow = "";
    });
    endZone.addEventListener("drop", (e) => {
      e.preventDefault();
      endZone.style.borderColor = "rgba(255,255,255,0.08)";
      endZone.style.background = "";
      endZone.style.boxShadow = "";
      const srcFrame = this._filmstripDragFrame;
      if (srcFrame === null) return;
      this._pushUndo();
      const srcIdx = this.frameOrder.indexOf(srcFrame);
      if (srcIdx >= 0) this.frameOrder.splice(srcIdx, 1);
      this.frameOrder.push(srcFrame);
      const srcDisplayIdx = this._displayOrder.indexOf(srcFrame);
      if (srcDisplayIdx >= 0) this._displayOrder.splice(srcDisplayIdx, 1);
      this._displayOrder.push(srcFrame);
      if (!this.selectedSet.has(srcFrame)) this.selectedSet.add(srcFrame);
      this._filmstripDragFrame = null;
      this._refreshAll();
      this._setStatus(`Moved frame ${srcFrame + 1} to end (position ${this.frameOrder.length})`);
    });
    this.filmstrip.appendChild(endZone);
    let scrollTimer = null;
    this.filmstrip.addEventListener("mousemove", (e) => {
      const rect = this.filmstrip.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const edgeZone = 80;
      if (scrollTimer) {
        clearInterval(scrollTimer);
        scrollTimer = null;
      }
      if (x < edgeZone) {
        const speed = 4 * (1 - x / edgeZone);
        scrollTimer = setInterval(() => {
          this.filmstrip.scrollLeft -= speed * 3;
        }, 16);
      } else if (x > rect.width - edgeZone) {
        const speed = 4 * (1 - (rect.width - x) / edgeZone);
        scrollTimer = setInterval(() => {
          this.filmstrip.scrollLeft += speed * 3;
        }, 16);
      }
    });
    this.filmstrip.addEventListener("mouseleave", () => {
      if (scrollTimer) {
        clearInterval(scrollTimer);
        scrollTimer = null;
      }
    });
  }
  _updateFilmstripActive() {
    this.filmstrip.querySelectorAll(".fpick-thumb-wrap").forEach((t) => {
      const el = t;
      el.classList.remove("active");
      if (el.dataset.frameIdx === String(this.currentFrame)) {
        el.classList.add("active");
        el.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
      }
    });
  }
  _updateFilmstripSelection() {
    this.filmstrip.querySelectorAll(".fpick-thumb-wrap").forEach((t) => {
      const el = t;
      const idx = parseInt(el.dataset.frameIdx || "0", 10);
      const selected = this.selectedSet.has(idx);
      el.classList.toggle("selected-frame", selected);
      el.classList.toggle("deselected-frame", !selected);
      const selDot = el.querySelector(".fpick-thumb-sel");
      if (selDot) selDot.innerHTML = selected ? iconCheck : iconClose;
    });
  }
  // ── Grid view (secondary — contact sheet) ──────────────────
  _buildGridView() {
    this.gridContainer.innerHTML = "";
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
      card.addEventListener("click", (e) => {
        this._handleGridClick(i, e);
      });
      card.addEventListener("dragstart", (e) => {
        if (!this.selectedSet.has(i)) {
          this._pushUndo();
          this.selectedSet.add(i);
          this.frameOrder.push(i);
        }
        this._filmstripDragFrame = i;
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", String(i));
        card.classList.add("dragging");
      });
      card.addEventListener("dragend", () => {
        card.classList.remove("dragging");
        this._filmstripDragFrame = null;
        this._lastSpreadTarget = null;
        this._lastSpreadSide = null;
        this._clearGridSpread();
      });
      card.addEventListener("dragover", (e) => {
        if (this._filmstripDragFrame === null) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        const rect = card.getBoundingClientRect();
        const relX = (e.clientX - rect.left) / rect.width;
        let side;
        if (relX < 0.4) side = "left";
        else if (relX > 0.6) side = "right";
        else side = this._lastSpreadSide || (relX < 0.5 ? "left" : "right");
        if (card !== this._lastSpreadTarget || side !== this._lastSpreadSide) {
          this._applyGridSpread(card, side);
        }
      });
      card.addEventListener("dragleave", () => {
      });
      card.addEventListener("drop", (e) => {
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
    endZone.addEventListener("dragover", (e) => {
      if (this._filmstripDragFrame === null) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
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
    endZone.addEventListener("drop", (e) => {
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
  _refreshGridView() {
    if (!this._gridMode) return;
    const cards = this.gridContainer.querySelectorAll(".fpick-grid-card");
    cards.forEach((card) => {
      const idx = parseInt(card.dataset.frame || "0", 10);
      const selected = this.selectedSet.has(idx);
      card.classList.toggle("selected", selected);
      card.classList.toggle("deselected", !selected);
      const check = card.querySelector(".fpick-grid-card-check");
      if (check) check.innerHTML = selected ? iconCheck : "";
      let orderBadge = card.querySelector(".fpick-grid-card-order");
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
  _handleGridClick(frameIdx, e) {
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
  _handleFilmstripShiftClick(frameIdx) {
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
  _doToggle(idx) {
    if (this.selectedSet.has(idx)) {
      this.selectedSet.delete(idx);
      this.frameOrder = this.frameOrder.filter((i) => i !== idx);
    } else {
      this.selectedSet.add(idx);
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
  _toggleFrame(idx) {
    this._pushUndo();
    const wasSelected = this.selectedSet.has(idx);
    this._doToggle(idx);
    this.lastClickedFrame = idx;
    if (wasSelected && this.currentFrame === idx && this.selectedSet.size > 0) {
      const nearest = this._findNearestSelected(idx);
      if (nearest !== null) {
        this._goToFrame(nearest);
      }
    }
    this._refreshAll();
  }
  _findNearestSelected(fromIdx) {
    for (let i = fromIdx + 1; i < this.totalFrames; i++) {
      if (this.selectedSet.has(i)) return i;
    }
    for (let i = fromIdx - 1; i >= 0; i--) {
      if (this.selectedSet.has(i)) return i;
    }
    return null;
  }
  _reorderFrame(srcFrame, targetFrame) {
    const srcIdx = this.frameOrder.indexOf(srcFrame);
    const tgtIdx = this.frameOrder.indexOf(targetFrame);
    if (srcIdx < 0 || tgtIdx < 0) return;
    this._pushUndo();
    this.frameOrder.splice(srcIdx, 1);
    this.frameOrder.splice(tgtIdx, 0, srcFrame);
    this._refreshAll();
  }
  _reorderFrameInFilmstrip(srcFrame, targetFrame, insertAfter) {
    const srcIdx = this.frameOrder.indexOf(srcFrame);
    if (srcIdx < 0) return;
    if (!this.selectedSet.has(targetFrame)) {
      this.selectedSet.add(targetFrame);
      this.frameOrder.push(targetFrame);
    }
    const tgtIdx = this.frameOrder.indexOf(targetFrame);
    if (tgtIdx < 0) return;
    this._pushUndo();
    this.frameOrder.splice(srcIdx, 1);
    let insertIdx = this.frameOrder.indexOf(targetFrame);
    if (insertAfter) insertIdx += 1;
    this.frameOrder.splice(insertIdx, 0, srcFrame);
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
  _applyFilmstripSpread(hoverWrapper, side) {
    if (hoverWrapper === this._lastSpreadTarget && side === this._lastSpreadSide) return;
    this._clearFilmstripSpread();
    this._lastSpreadTarget = hoverWrapper;
    this._lastSpreadSide = side;
    const thumbs = Array.from(this.filmstrip.querySelectorAll(".fpick-thumb-wrap"));
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
  _clearFilmstripSpread() {
    this.filmstrip.querySelectorAll(".spread-left, .spread-right").forEach((el) => {
      el.classList.remove("spread-left", "spread-right");
    });
  }
  // ── Grid spread-apart animation ────────────────────────────
  _applyGridSpread(hoverCard, side) {
    if (hoverCard === this._lastSpreadTarget && side === this._lastSpreadSide) return;
    this._clearGridSpread();
    this._lastSpreadTarget = hoverCard;
    this._lastSpreadSide = side;
    const cards = Array.from(this.gridContainer.querySelectorAll(".fpick-grid-card"));
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
  _clearGridSpread() {
    this.gridContainer.querySelectorAll(".grid-spread-left, .grid-spread-right, .drag-over-left, .drag-over-right").forEach((el) => {
      el.classList.remove("grid-spread-left", "grid-spread-right", "drag-over-left", "drag-over-right");
    });
  }
  // ── Selection tools ────────────────────────────────────────
  _resetAll() {
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
  _selectAll() {
    this._pushUndo();
    this.selectedSet.clear();
    this.frameOrder = [];
    for (let i = 0; i < this.totalFrames; i++) {
      this.selectedSet.add(i);
      this.frameOrder.push(i);
    }
    this._refreshAll();
  }
  _deselectAll() {
    this._pushUndo();
    this.selectedSet.clear();
    this.frameOrder = [];
    this._refreshAll();
  }
  _invertSelection() {
    this._pushUndo();
    const newSelected = /* @__PURE__ */ new Set();
    const newOrder = [];
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
  _selectEveryNth(n) {
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
  _refreshAll() {
    this._updateCanvasOverlay();
    this._buildFilmstrip();
    this._buildGridView();
    this._updateSummary();
    this._updateOrderPreview();
    this._updateSelectedCount();
  }
  _updateFrameInfo() {
    const info = document.getElementById("fpick-frame-info");
    if (info) {
      info.textContent = `${this.totalFrames} frames @ ${this.videoFps.toFixed(1)} fps — ${this.videoWidth}×${this.videoHeight}`;
    }
  }
  _updateSummary() {
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
  _updateOrderPreview() {
    const preview = this.sidebar.querySelector(".fpick-order-preview");
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
  _updateSelectedCount() {
    const el = document.getElementById("fpick-selected-count");
    if (el) el.textContent = `${this.selectedSet.size} / ${this.totalFrames} selected`;
  }
  // ── Fetch frame (full-size for canvas) ─────────────────────
  async _fetchFrame(idx) {
    const resp = await api.fetchApi("/framepicker/get_frame", {
      method: "POST",
      body: JSON.stringify({
        video_path: this.videoPath,
        frame_idx: idx,
        thumb_width: 960
      })
    });
    const blob = await resp.blob();
    return URL.createObjectURL(blob);
  }
  // ── Fetch thumbnail (small, for filmstrip + grid) ──────────
  async _fetchFrameThumb(idx) {
    const cached = this.thumbnailCache.get(idx);
    if (cached) return `data:image/jpeg;base64,${cached}`;
    const resp = await api.fetchApi("/framepicker/get_frame", {
      method: "POST",
      body: JSON.stringify({
        video_path: this.videoPath,
        frame_idx: idx,
        thumb_width: 160
      })
    });
    const blob = await resp.blob();
    const b64 = await this._blobToBase64(blob);
    this.thumbnailCache.set(idx, b64);
    return URL.createObjectURL(blob);
  }
  _blobToBase64(blob) {
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = reader.result;
        resolve(result.split(",")[1] || "");
      };
      reader.readAsDataURL(blob);
    });
  }
  // ── Undo / Redo ────────────────────────────────────────────
  _pushUndo() {
    const state = JSON.stringify({
      selected: Array.from(this.selectedSet),
      order: this.frameOrder
    });
    this._undoStack.push(state);
    if (this._undoStack.length > 50) this._undoStack.shift();
    this._redoStack = [];
  }
  _undo() {
    if (this._undoStack.length === 0) {
      this._setStatus("Nothing to undo");
      return;
    }
    const current = JSON.stringify({ selected: Array.from(this.selectedSet), order: this.frameOrder });
    this._redoStack.push(current);
    const prev = JSON.parse(this._undoStack.pop());
    this.selectedSet = new Set(prev.selected);
    this.frameOrder = prev.order;
    this._refreshAll();
    this._setStatus("Undone");
  }
  _redo() {
    if (this._redoStack.length === 0) {
      this._setStatus("Nothing to redo");
      return;
    }
    const current = JSON.stringify({ selected: Array.from(this.selectedSet), order: this.frameOrder });
    this._undoStack.push(current);
    const next = JSON.parse(this._redoStack.pop());
    this.selectedSet = new Set(next.selected);
    this.frameOrder = next.order;
    this._refreshAll();
    this._setStatus("Redone");
  }
  // ── Keyboard handler ───────────────────────────────────────
  _handleKey(e) {
    var _a, _b;
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
    if (e.key === "Escape") {
      this._cancel();
      return;
    }
    if (e.key === " ") {
      e.preventDefault();
      this._toggleFrame(this.currentFrame);
      return;
    }
    if (e.key === "p" || e.key === "P") {
      this._togglePlayback();
      return;
    }
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
    if (e.key === "Home") {
      e.preventDefault();
      this._goToFrame(this._displayOrder[0]);
      return;
    }
    if (e.key === "End") {
      e.preventDefault();
      this._goToFrame(this._displayOrder[this._displayOrder.length - 1]);
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      this._apply();
      return;
    }
    if (e.key === "+" || e.key === "=") {
      e.preventDefault();
      this._zoomStep(25);
      return;
    }
    if (e.key === "-" || e.key === "_") {
      e.preventDefault();
      this._zoomStep(-25);
      return;
    }
    if ((e.key === "a" || e.key === "A") && !e.ctrlKey && !e.metaKey) {
      this._selectAll();
      return;
    }
    if (e.key === "d" || e.key === "D") {
      this._deselectAll();
      return;
    }
    if (e.key === "i" || e.key === "I") {
      this._invertSelection();
      return;
    }
    if (e.key === "h" || e.key === "H") {
      this._flipCurrentH();
      return;
    }
    if ((e.key === "v" || e.key === "V") && !e.ctrlKey && !e.metaKey) {
      this._flipCurrentV();
      return;
    }
    if (e.key === "r" || e.key === "R") {
      this._rotateCurrentCW();
      return;
    }
    if (e.key === "g" || e.key === "G") {
      this._gridMode = !this._gridMode;
      this.panel.classList.toggle("grid-mode", this._gridMode);
      const viewBtn = this.panel.querySelector(".fpick-btn-view");
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
    if (e.key === "c" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      this._copyFrame();
      return;
    }
    if (e.key === "v" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      this._pasteFrame();
      return;
    }
    if (e.key === "z" && (e.ctrlKey || e.metaKey) && !e.shiftKey) {
      e.preventDefault();
      this._undo();
      return;
    }
    if (e.key === "y" && (e.ctrlKey || e.metaKey) || e.key === "z" && (e.ctrlKey || e.metaKey) && e.shiftKey) {
      e.preventDefault();
      this._redo();
      return;
    }
    const num = parseInt(e.key, 10);
    if (num >= 1 && num <= 9 && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
      e.preventDefault();
      const targetIdx = Math.round(num / 10 * (this._displayOrder.length - 1));
      this._goToFrame(this._displayOrder[targetIdx]);
      this._setStatus(`Jumped to ${num * 10}% (frame ${this._displayOrder[targetIdx] + 1})`);
      return;
    }
    if ((e.key === "f" || e.key === "F") && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      if (document.fullscreenElement) {
        document.exitFullscreen();
      } else {
        (_b = (_a = this.dialog).requestFullscreen) == null ? void 0 : _b.call(_a).catch(() => {
        });
      }
      return;
    }
  }
  // ── Zoom helpers ─────────────────────────────────────────────────
  _zoomStep(delta) {
    if (!this._zoomSlider) return;
    const cur = parseInt(this._zoomSlider.value, 10);
    const next = Math.max(parseInt(this._zoomSlider.min, 10), Math.min(parseInt(this._zoomSlider.max, 10), cur + delta));
    this._zoomSlider.value = String(next);
    this._zoomSlider.dispatchEvent(new Event("input"));
  }
  // ── Copy / Paste ──────────────────────────────────────────────
  _copyFrame() {
    this._clipboard = this.currentFrame;
    this._setStatus(`Copied frame ${this.currentFrame + 1} — press Ctrl+V to paste duplicate`);
  }
  _pasteFrame() {
    if (this._clipboard === null) {
      this._setStatus("Nothing copied — select a frame and press Ctrl+C first");
      return;
    }
    this._pushUndo();
    if (!this.selectedSet.has(this._clipboard)) {
      this.selectedSet.add(this._clipboard);
    }
    const currentOrderIdx = this.frameOrder.indexOf(this.currentFrame);
    const insertAt = currentOrderIdx >= 0 ? currentOrderIdx + 1 : this.frameOrder.length;
    this.frameOrder.splice(insertAt, 0, this._clipboard);
    this._refreshAll();
    this._setStatus(`Pasted frame ${this._clipboard + 1} at position ${insertAt + 1}`);
  }
  // ── Frame Transforms ─────────────────────────────────────────
  _getOrCreateTransform(idx) {
    let t = this._frameTransforms.get(idx);
    if (!t) {
      t = { flipH: false, flipV: false, rotate: 0 };
      this._frameTransforms.set(idx, t);
    }
    return t;
  }
  _flipCurrentH() {
    const t = this._getOrCreateTransform(this.currentFrame);
    t.flipH = !t.flipH;
    this._applyCanvasTransform();
    this._updateCanvasOverlay();
    this._setStatus(`Frame ${this.currentFrame + 1}: Flip H ${t.flipH ? "ON" : "OFF"}`);
  }
  _flipCurrentV() {
    const t = this._getOrCreateTransform(this.currentFrame);
    t.flipV = !t.flipV;
    this._applyCanvasTransform();
    this._updateCanvasOverlay();
    this._setStatus(`Frame ${this.currentFrame + 1}: Flip V ${t.flipV ? "ON" : "OFF"}`);
  }
  _rotateCurrentCW() {
    const t = this._getOrCreateTransform(this.currentFrame);
    t.rotate = (t.rotate + 90) % 360;
    this._applyCanvasTransform();
    this._updateCanvasOverlay();
    this._setStatus(`Frame ${this.currentFrame + 1}: Rotated ${t.rotate}°`);
  }
  _reverseOrder() {
    if (this.frameOrder.length < 2) {
      this._setStatus("Need at least 2 selected frames to reverse");
      return;
    }
    this._pushUndo();
    this.frameOrder.reverse();
    this._refreshAll();
    this._setStatus(`Reversed frame order (${this.frameOrder.length} frames)`);
  }
  _holdFrame(copies) {
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
  _getTransformLabel(idx) {
    const t = this._frameTransforms.get(idx);
    if (!t) return "";
    const parts = [];
    if (t.flipH) parts.push("FlipH");
    if (t.flipV) parts.push("FlipV");
    if (t.rotate) parts.push(`${t.rotate}°`);
    return parts.length > 0 ? ` [${parts.join(", ")}]` : "";
  }
  // ── Playback ───────────────────────────────────────────────
  _togglePlayback() {
    if (this._playing) {
      this._stopPlayback();
    } else {
      this._startPlayback();
    }
  }
  _startPlayback() {
    if (this.frameOrder.length === 0) {
      this._setStatus("No frames selected to play");
      return;
    }
    this._playing = true;
    this._playIdx = 0;
    if (this._playBtn) {
      this._playBtn.innerHTML = `${iconPause} Pause`;
      this._playBtn.classList.add("active");
    }
    this._setStatus(`▶ Playing ${this.frameOrder.length} selected frames...`);
    this._playNextFrame();
  }
  _stopPlayback() {
    this._playing = false;
    if (this._playTimer) {
      clearTimeout(this._playTimer);
      this._playTimer = null;
    }
    if (this._playBtn) {
      this._playBtn.innerHTML = `${iconPlay} Play`;
      this._playBtn.classList.remove("active");
    }
    this._setStatus("Playback stopped");
  }
  _playNextFrame() {
    if (!this._playing || this.frameOrder.length === 0) {
      this._stopPlayback();
      return;
    }
    if (this._playIdx >= this.frameOrder.length) {
      this._playIdx = 0;
    }
    const frameIdx = this.frameOrder[this._playIdx];
    this._goToFrame(frameIdx);
    this._playIdx++;
    const delayMs = 1e3 / (this.videoFps || 24);
    this._playTimer = setTimeout(() => this._playNextFrame(), delayMs);
  }
  // ── Apply / Cancel ─────────────────────────────────────────
  _apply() {
    this.close();
    const activeTransforms = /* @__PURE__ */ new Map();
    for (const [idx, t] of this._frameTransforms) {
      if (t.flipH || t.flipV || t.rotate !== 0) {
        activeTransforms.set(idx, { ...t });
      }
    }
    this.callbacks.onApply([...this.frameOrder], activeTransforms.size > 0 ? activeTransforms : void 0);
  }
  _cancel() {
    this.close();
    this.callbacks.onCancel();
  }
  // ── Helpers ─────────────────────────────────────────────────
  _setStatus(msg) {
    this.statusEl.textContent = msg;
  }
  _makeBtn(html, cls, onClick) {
    const btn = document.createElement("button");
    btn.className = `fpick-btn ${cls}`;
    btn.innerHTML = html;
    btn.addEventListener("click", onClick);
    btn.onpointerdown = (e) => e.stopPropagation();
    return btn;
  }
}
const framePickerCSS = `/* ═══════════════════════════════════════════════════════════════════
 * Frame Picker Editor (FFMPEGA)
 *
 * Shares design tokens with the FacePoke / Video Editor for consistency.
 * Layout: full-viewport modal with CSS Grid for the picker workspace.
 *
 * Primary layout: filmstrip + large canvas (matches FacePoke)
 * Secondary layout: grid view (contact-sheet toggle)
 * ═══════════════════════════════════════════════════════════════════ */

/* ── Modal Backdrop ──────────────────────────────────────────────── */

.fpick-backdrop {
    position: fixed;
    inset: 0;
    z-index: 2147483647;
    background: rgba(0, 0, 0, 0.7);
    backdrop-filter: blur(6px);
    display: flex;
    align-items: center;
    justify-content: center;
    padding-top: 30px;
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
    color: #e8e8f0;
}

/* ── Panel (CSS Grid — filmstrip mode) ───────────────────────────── */

.fpick-panel {
    background: linear-gradient(160deg, #161625 0%, #0f0f1a 100%);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
    width: 92vw;
    height: 90vh;

    /* Zoom scale — shared by filmstrip + grid */
    --fpick-thumb-scale: 1;

    display: grid;
    grid-template-areas:
        "header    header"
        "canvas    sidebar"
        "filmstrip sidebar"
        "toolbar   toolbar";
    grid-template-columns: 1fr 280px;
    grid-template-rows: auto 1fr auto auto;

    box-shadow:
        0 0 60px rgba(0, 0, 0, 0.5),
        0 0 120px rgba(34, 197, 94, 0.05);
    overflow: hidden;
}

/* Grid mode: swap canvas+filmstrip for grid area */
.fpick-panel.grid-mode {
    grid-template-areas:
        "header    header"
        "grid      sidebar"
        "toolbar   toolbar";
    grid-template-rows: auto 1fr auto;
}

.fpick-panel.grid-mode .fpick-canvas-area { display: none; }
.fpick-panel.grid-mode .fpick-filmstrip { display: none; }
.fpick-panel.grid-mode .fpick-grid-area { display: block; }

.fpick-panel:not(.grid-mode) .fpick-grid-area { display: none; }

/* ── Header ──────────────────────────────────────────────────────── */

.fpick-header {
    grid-area: header;
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 10px 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(28, 28, 48, 0.75);
    backdrop-filter: blur(12px);
}

.fpick-title {
    margin: 0;
    font-size: 15px;
    font-weight: 700;
    color: #fff;
    letter-spacing: 0.3px;
    white-space: nowrap;
}

.fpick-frame-info {
    flex: 1;
    font-size: 12px;
    color: #9898b0;
    font-variant-numeric: tabular-nums;
}

.fpick-header-actions {
    display: flex;
    align-items: center;
    gap: 6px;
}

.fpick-close {
    background: none;
    border: 1px solid transparent;
    color: #9898b0;
    font-size: 16px;
    padding: 4px 8px;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s ease;
}

.fpick-close:hover {
    background: rgba(239, 68, 68, 0.15);
    border-color: #ef4444;
    color: #ef4444;
}

/* ── Canvas Area (large frame display) ───────────────────────────── */

.fpick-canvas-area {
    grid-area: canvas;
    background: #000;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    overflow: hidden;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    min-height: 0;
}

.fpick-canvas {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    user-select: none;
}

/* Selection overlay on the canvas */
.fpick-canvas-overlay {
    position: absolute;
    bottom: 12px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 14px;
    background: rgba(0, 0, 0, 0.7);
    backdrop-filter: blur(8px);
    border-radius: 20px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    font-size: 12px;
    pointer-events: auto;
    z-index: 10;
}

.fpick-canvas-frame-num {
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: #fff;
    font-size: 14px;
}

.fpick-canvas-status {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-weight: 600;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 11px;
}

.fpick-canvas-status.selected {
    background: rgba(34, 197, 94, 0.2);
    color: #4ade80;
    border: 1px solid rgba(34, 197, 94, 0.3);
}

.fpick-canvas-status.deselected {
    background: rgba(239, 68, 68, 0.15);
    color: #f87171;
    border: 1px solid rgba(239, 68, 68, 0.25);
}

/* ── Filmstrip ───────────────────────────────────────────────────── */

.fpick-filmstrip {
    grid-area: filmstrip;
    display: flex;
    align-items: center;
    gap: 3px;
    padding: 10px 14px;
    overflow-x: auto;
    overflow-y: hidden;

    /* Track backboard — dark recessed rail */
    background:
        linear-gradient(180deg,
            rgba(8, 8, 18, 0.95) 0%,
            rgba(12, 12, 24, 0.98) 40%,
            rgba(8, 8, 18, 0.95) 100%
        );
    border-top: 1px solid rgba(255, 255, 255, 0.04);
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    box-shadow:
        inset 0 2px 8px rgba(0, 0, 0, 0.6),
        inset 0 -2px 8px rgba(0, 0, 0, 0.4);

    scrollbar-width: thin;
    scrollbar-color: #2a2a45 transparent;
    min-height: calc(64px * var(--fpick-thumb-scale) + 24px);
    position: relative;
}

/* Subtle rail grooves at top and bottom of track */
.fpick-filmstrip::before,
.fpick-filmstrip::after {
    content: "";
    position: absolute;
    left: 0;
    right: 0;
    height: 1px;
    pointer-events: none;
    z-index: 1;
}

.fpick-filmstrip::before {
    top: 3px;
    background: linear-gradient(90deg,
        transparent 0%, rgba(99, 102, 241, 0.08) 10%,
        rgba(99, 102, 241, 0.12) 50%,
        rgba(99, 102, 241, 0.08) 90%, transparent 100%
    );
}

.fpick-filmstrip::after {
    bottom: 3px;
    background: linear-gradient(90deg,
        transparent 0%, rgba(99, 102, 241, 0.06) 10%,
        rgba(99, 102, 241, 0.10) 50%,
        rgba(99, 102, 241, 0.06) 90%, transparent 100%
    );
}

.fpick-filmstrip::-webkit-scrollbar { height: 6px; }
.fpick-filmstrip::-webkit-scrollbar-track { background: transparent; }
.fpick-filmstrip::-webkit-scrollbar-thumb { background: #2a2a45; border-radius: 3px; }

.fpick-thumb-wrap {
    position: relative;
    flex-shrink: 0;
    width: calc(80px * var(--fpick-thumb-scale, 1));
    height: calc(60px * var(--fpick-thumb-scale, 1));
    border-radius: 4px;
    border: 2px solid transparent;
    cursor: pointer;
    opacity: 0.6;
    overflow: hidden;
    /* Smooth margin transitions for spread effect */
    transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
    margin: 0 0;
    z-index: 2;
}

.fpick-thumb {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
    pointer-events: none;
}

.fpick-thumb-num {
    position: absolute;
    bottom: 1px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 9px;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.85);
    background: rgba(0, 0, 0, 0.55);
    padding: 0 4px;
    border-radius: 3px;
    line-height: 14px;
    pointer-events: none;
    font-variant-numeric: tabular-nums;
}

/* Position badge (order number) on filmstrip thumbnails */
.fpick-thumb-order {
    position: absolute;
    top: 2px;
    left: 2px;
    font-size: 8px;
    font-weight: 700;
    color: #fff;
    background: rgba(99, 102, 241, 0.85);
    padding: 0 4px;
    border-radius: 8px;
    line-height: 14px;
    pointer-events: none;
    font-variant-numeric: tabular-nums;
    z-index: 3;
}

.fpick-thumb-wrap:hover {
    opacity: 0.9;
    border-color: rgba(255, 255, 255, 0.2);
}

.fpick-thumb-wrap.active {
    opacity: 1;
    border-color: #6366f1;
    box-shadow: 0 0 12px rgba(99, 102, 241, 0.3);
}

.fpick-thumb-wrap.selected-frame {
    border-color: #22c55e;
    opacity: 0.85;
}

.fpick-thumb-wrap.selected-frame.active {
    border-color: #6366f1;
    opacity: 1;
    box-shadow: 0 0 12px rgba(99, 102, 241, 0.3),
                inset 0 0 0 1px #22c55e;
}

.fpick-thumb-wrap.deselected-frame {
    opacity: 0.25;
    filter: saturate(0.2);
}

.fpick-thumb-wrap.deselected-frame:hover {
    opacity: 0.45;
    filter: saturate(0.4);
}

/* Selection indicator in filmstrip */
.fpick-thumb-sel {
    position: absolute;
    top: 2px;
    right: 2px;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    font-size: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
}

.fpick-thumb-wrap.selected-frame .fpick-thumb-sel {
    background: #22c55e;
    color: #fff;
}

.fpick-thumb-wrap.deselected-frame .fpick-thumb-sel {
    background: rgba(239, 68, 68, 0.6);
    color: #fff;
}

/* ── Filmstrip drag states ───────────────────────────────────────── */

.fpick-thumb-wrap.dragging {
    opacity: 0.2 !important;
    transform: scale(0.8);
    filter: saturate(0.2) brightness(0.5);
    transition: all 0.15s ease;
}

.fpick-thumb-wrap[draggable="true"] {
    cursor: grab;
}

.fpick-thumb-wrap[draggable="true"]:active {
    cursor: grabbing;
}

/* ── Spread-apart insertion animation (margin-based = pushes siblings) ── */

/* Left neighbour: extra right margin pushes all right-side siblings */
.fpick-thumb-wrap.spread-left {
    margin-right: 28px !important;
    transition: margin 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

/* Right neighbour: extra left margin pushes all left-side siblings */
.fpick-thumb-wrap.spread-right {
    margin-left: 28px !important;
    transition: margin 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

/* Glowing edge on the insertion side — brighter, wider, more pronounced */
.fpick-thumb-wrap.spread-left::after {
    content: "";
    position: absolute;
    top: -4px;
    right: -6px;
    width: 5px;
    height: calc(100% + 8px);
    border-radius: 0 3px 3px 0;
    background: linear-gradient(180deg, #818cf8, #6366f1, #818cf8);
    box-shadow:
        0 0 10px rgba(99, 102, 241, 0.9),
        0 0 20px rgba(99, 102, 241, 0.6),
        0 0 40px rgba(99, 102, 241, 0.3);
    animation: fpick-edge-pulse 0.6s ease-in-out infinite alternate;
    z-index: 10;
    pointer-events: none;
}

.fpick-thumb-wrap.spread-right::after {
    content: "";
    position: absolute;
    top: -4px;
    left: -6px;
    width: 5px;
    height: calc(100% + 8px);
    border-radius: 3px 0 0 3px;
    background: linear-gradient(180deg, #818cf8, #6366f1, #818cf8);
    box-shadow:
        0 0 10px rgba(99, 102, 241, 0.9),
        0 0 20px rgba(99, 102, 241, 0.6),
        0 0 40px rgba(99, 102, 241, 0.3);
    animation: fpick-edge-pulse 0.6s ease-in-out infinite alternate;
    z-index: 10;
    pointer-events: none;
}

/* Both neighbours brighten during drag */
.fpick-thumb-wrap.spread-left,
.fpick-thumb-wrap.spread-right {
    opacity: 1 !important;
    border-color: rgba(129, 140, 248, 0.5);
    z-index: 5;
}

/* Pulsing glow keyframe — more dramatic */
@keyframes fpick-edge-pulse {
    0% {
        box-shadow:
            0 0 8px rgba(99, 102, 241, 0.6),
            0 0 16px rgba(99, 102, 241, 0.3);
        opacity: 0.8;
    }
    100% {
        box-shadow:
            0 0 14px rgba(99, 102, 241, 1),
            0 0 28px rgba(99, 102, 241, 0.7),
            0 0 48px rgba(99, 102, 241, 0.25);
        opacity: 1;
    }
}

.fpick-grid-area {
    grid-area: grid;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 12px;
    background: rgba(10, 10, 20, 0.5);
    min-height: 0;
}

.fpick-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(calc(140px * var(--fpick-thumb-scale, 1)), 1fr));
    gap: 8px;
    align-content: start;
}

.fpick-grid-area::-webkit-scrollbar { width: 6px; }
.fpick-grid-area::-webkit-scrollbar-track { background: transparent; }
.fpick-grid-area::-webkit-scrollbar-thumb { background: #2a2a45; border-radius: 3px; }

/* ── Grid Thumbnail Card ─────────────────────────────────────────── */

.fpick-grid-card {
    position: relative;
    border-radius: 8px;
    border: 2px solid rgba(255, 255, 255, 0.06);
    cursor: pointer;
    transition: all 0.15s ease;
    overflow: hidden;
    background: #0a0a14;
    user-select: none;
    aspect-ratio: 16 / 9;
}

.fpick-grid-card:hover {
    border-color: rgba(255, 255, 255, 0.2);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.fpick-grid-card.selected {
    border-color: #22c55e;
    box-shadow: 0 0 12px rgba(34, 197, 94, 0.25);
}

.fpick-grid-card.deselected {
    opacity: 0.35;
    filter: saturate(0.3);
}

.fpick-grid-card.deselected:hover {
    opacity: 0.6;
    filter: saturate(0.5);
}

/* Drag states (grid) */
.fpick-grid-card.dragging {
    opacity: 0.2;
    transform: scale(0.9);
    filter: saturate(0.2) brightness(0.5);
}

/* Positional drop indicators — glowing edge on insertion side */
.fpick-grid-card.drag-over-left {
    border-left-color: #818cf8;
    border-left-width: 4px;
    box-shadow: -4px 0 16px rgba(99, 102, 241, 0.5);
}

.fpick-grid-card.drag-over-right {
    border-right-color: #818cf8;
    border-right-width: 4px;
    box-shadow: 4px 0 16px rgba(99, 102, 241, 0.5);
}

/* Grid spread-apart animation (same idea as filmstrip) */
.fpick-grid-card.grid-spread-left {
    margin-right: 24px !important;
    transition: margin 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
    position: relative;
}

.fpick-grid-card.grid-spread-left::after {
    content: "";
    position: absolute;
    top: -4px;
    right: -6px;
    width: 4px;
    height: calc(100% + 8px);
    border-radius: 0 3px 3px 0;
    background: linear-gradient(180deg, #818cf8, #6366f1, #818cf8);
    box-shadow:
        0 0 10px rgba(99, 102, 241, 0.9),
        0 0 20px rgba(99, 102, 241, 0.5);
    animation: fpick-edge-pulse 0.6s ease-in-out infinite alternate;
    z-index: 10;
    pointer-events: none;
}

.fpick-grid-card.grid-spread-right {
    margin-left: 24px !important;
    transition: margin 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
    position: relative;
}

.fpick-grid-card.grid-spread-right::after {
    content: "";
    position: absolute;
    top: -4px;
    left: -6px;
    width: 4px;
    height: calc(100% + 8px);
    border-radius: 3px 0 0 3px;
    background: linear-gradient(180deg, #818cf8, #6366f1, #818cf8);
    box-shadow:
        0 0 10px rgba(99, 102, 241, 0.9),
        0 0 20px rgba(99, 102, 241, 0.5);
    animation: fpick-edge-pulse 0.6s ease-in-out infinite alternate;
    z-index: 10;
    pointer-events: none;
}

.fpick-grid-card.grid-spread-left,
.fpick-grid-card.grid-spread-right {
    opacity: 1 !important;
    border-color: rgba(129, 140, 248, 0.4);
    z-index: 5;
}

/* Smooth return for grid cards */
.fpick-grid-card:not(.grid-spread-left):not(.grid-spread-right):not(.dragging) {
    transition: margin 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.fpick-grid-card-img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
    pointer-events: none;
}

.fpick-grid-card-badge {
    position: absolute;
    bottom: 4px;
    left: 4px;
    font-size: 10px;
    font-weight: 700;
    color: rgba(255, 255, 255, 0.9);
    background: rgba(0, 0, 0, 0.65);
    padding: 1px 6px;
    border-radius: 4px;
    line-height: 16px;
    pointer-events: none;
    font-variant-numeric: tabular-nums;
}

.fpick-grid-card-check {
    position: absolute;
    top: 4px;
    right: 4px;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    border: 2px solid rgba(255, 255, 255, 0.3);
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    transition: all 0.15s ease;
    pointer-events: none;
}

.fpick-grid-card.selected .fpick-grid-card-check {
    background: #22c55e;
    border-color: #22c55e;
    color: #fff;
}

.fpick-grid-card-order {
    position: absolute;
    top: 4px;
    left: 4px;
    font-size: 10px;
    font-weight: 700;
    color: #fff;
    background: rgba(99, 102, 241, 0.85);
    padding: 1px 6px;
    border-radius: 10px;
    line-height: 16px;
    pointer-events: none;
    font-variant-numeric: tabular-nums;
}

/* ── Sidebar ─────────────────────────────────────────────────────── */

.fpick-sidebar {
    grid-area: sidebar;
    display: flex;
    flex-direction: column;
    overflow-y: auto;
    padding: 14px;
    border-left: 1px solid rgba(255, 255, 255, 0.06);
    background: rgba(28, 28, 48, 0.6);
    gap: 16px;
    min-height: 0;
}

.fpick-sidebar::-webkit-scrollbar { width: 6px; }
.fpick-sidebar::-webkit-scrollbar-track { background: transparent; }
.fpick-sidebar::-webkit-scrollbar-thumb { background: #2a2a45; border-radius: 3px; }

.fpick-section-title {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #8888aa;
    margin-bottom: 8px;
}

.fpick-tool-group {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
}

.fpick-nth-row {
    display: flex;
    align-items: center;
    gap: 8px;
}

.fpick-nth-input {
    width: 50px;
    padding: 4px 8px;
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 6px;
    background: rgba(30, 30, 55, 0.8);
    color: #e8e8f0;
    font-size: 12px;
    text-align: center;
    outline: none;
    font-variant-numeric: tabular-nums;
}

.fpick-nth-input:focus {
    border-color: rgba(99, 102, 241, 0.5);
    box-shadow: 0 0 8px rgba(99, 102, 241, 0.2);
}

.fpick-summary {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 10px;
    background: rgba(20, 20, 40, 0.6);
    border-radius: 8px;
    border: 1px solid rgba(255, 255, 255, 0.04);
}

.fpick-summary-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12px;
}

.fpick-summary-label { color: #8888aa; }

.fpick-summary-value {
    color: #e8e8f0;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
}

.fpick-summary-value.highlight { color: #22c55e; }

/* Order preview strip */
.fpick-order-preview {
    display: flex;
    flex-wrap: wrap;
    gap: 3px;
    max-height: 200px;
    overflow-y: auto;
    padding: 8px;
    background: rgba(10, 10, 20, 0.5);
    border-radius: 6px;
    border: 1px solid rgba(255, 255, 255, 0.04);
}

.fpick-order-preview::-webkit-scrollbar { width: 4px; }
.fpick-order-preview::-webkit-scrollbar-track { background: transparent; }
.fpick-order-preview::-webkit-scrollbar-thumb { background: #2a2a45; border-radius: 2px; }

.fpick-order-item {
    width: 36px;
    height: 28px;
    border-radius: 3px;
    overflow: hidden;
    border: 1px solid rgba(34, 197, 94, 0.3);
    position: relative;
    flex-shrink: 0;
}

.fpick-order-item img {
    width: 100%;
    height: 100%;
    object-fit: cover;
}

.fpick-order-item-num {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    font-size: 7px;
    text-align: center;
    background: rgba(0, 0, 0, 0.7);
    color: #fff;
    line-height: 10px;
}

/* ── Toolbar ─────────────────────────────────────────────────────── */

.fpick-toolbar {
    grid-area: toolbar;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 16px;
    background: rgba(28, 28, 48, 0.75);
    backdrop-filter: blur(12px);
    border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.fpick-status {
    font-size: 12px;
    color: #9898b0;
}

.fpick-nav-btns {
    display: flex;
    align-items: center;
    gap: 6px;
}

.fpick-selected-count {
    font-size: 11px;
    color: #22c55e;
    font-weight: 600;
    margin-left: 12px;
}

/* ── Buttons ─────────────────────────────────────────────────────── */

.fpick-btn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 5px 10px;
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 6px;
    background: #2a2a45;
    color: #e8e8f0;
    cursor: pointer;
    font-size: 12px;
    font-family: 'Inter', system-ui, sans-serif;
    white-space: nowrap;
    transition: all 0.15s ease;
}

.fpick-btn:hover {
    background: #3a3a55;
    border-color: rgba(255, 255, 255, 0.12);
}

.fpick-btn:active { transform: scale(0.97); }

.fpick-btn-sm { padding: 3px 8px; font-size: 11px; }

.fpick-btn-apply {
    background: #22c55e;
    border-color: transparent;
    color: #fff;
    font-weight: 600;
}

.fpick-btn-apply:hover {
    background: #4ade80;
    box-shadow: 0 0 16px rgba(34, 197, 94, 0.25);
}

.fpick-btn-tool {
    background: rgba(40, 40, 70, 0.6);
    border-color: rgba(255, 255, 255, 0.12);
    color: #c8c8e0;
}

.fpick-btn-tool:hover {
    background: rgba(99, 102, 241, 0.15);
    border-color: rgba(99, 102, 241, 0.3);
    color: #e8e8f0;
}

.fpick-btn-tool:active {
    transform: scale(0.95);
    background: rgba(99, 102, 241, 0.25);
}

.fpick-btn-view {
    background: transparent;
    border-color: rgba(255, 255, 255, 0.15);
    color: #9898b0;
}

.fpick-btn-view:hover {
    background: rgba(99, 102, 241, 0.1);
    border-color: #6366f1;
    color: #e8e8f0;
}

.fpick-btn-view.active {
    background: rgba(99, 102, 241, 0.2);
    border-color: #6366f1;
    color: #818cf8;
    box-shadow: 0 0 12px rgba(99, 102, 241, 0.25);
}

.fpick-btn-reset {
    background: transparent;
    border-color: #ef4444;
    color: #ef4444;
}

.fpick-btn-reset:hover {
    background: rgba(239, 68, 68, 0.1);
    color: #f87171;
}

/* Play button active state */
.fpick-btn-play.active {
    background: rgba(99, 102, 241, 0.25);
    border-color: #6366f1;
    color: #818cf8;
    box-shadow: 0 0 10px rgba(99, 102, 241, 0.3);
}

.fpick-btn-play.active:hover {
    background: rgba(99, 102, 241, 0.35);
}


/* ── Keyboard shortcut hints ─────────────────────────────────────── */

.fpick-kbd {
    display: inline-block;
    padding: 1px 5px;
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 3px;
    background: rgba(40, 40, 60, 0.5);
    font-size: 10px;
    color: #8888aa;
    font-family: monospace;
    margin-left: 4px;
    line-height: 14px;
}

/* ── Responsive ──────────────────────────────────────────────────── */

@media (max-width: 1024px) {
    .fpick-panel {
        grid-template-areas:
            "header"
            "canvas"
            "filmstrip"
            "sidebar"
            "toolbar";
        grid-template-columns: 1fr;
        grid-template-rows: auto 1fr auto auto auto;
        width: 98vw;
        height: 95vh;
    }

    .fpick-panel.grid-mode {
        grid-template-areas:
            "header"
            "grid"
            "sidebar"
            "toolbar";
        grid-template-rows: auto 1fr auto auto;
    }

    .fpick-sidebar {
        border-left: none;
        border-top: 1px solid rgba(255, 255, 255, 0.06);
        max-height: 180px;
    }
}
`;
if (!document.querySelector("#fpick-styles")) {
  const style = document.createElement("style");
  style.id = "fpick-styles";
  style.textContent = framePickerCSS;
  document.head.appendChild(style);
}
const NODE_TYPE = "FFMPEGAFramePicker";
const PREVIEW_ROUTE = "/ffmpega/preview";
const PASSTHROUGH_EVENTS = [
  "contextmenu",
  "pointerdown",
  "mousewheel",
  "pointermove",
  "pointerup"
];
let _sharedModal = null;
function getModal() {
  if (!_sharedModal) {
    _sharedModal = new FramePickerModal({
      onApply: () => {
      },
      onCancel: () => {
      }
    });
  }
  return _sharedModal;
}
app.registerExtension({
  name: "ffmpega.framepicker",
  beforeRegisterNodeDef(nodeType, nodeData, _app) {
    if (nodeData.name !== NODE_TYPE) return;
    const origCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function() {
      const result = origCreated == null ? void 0 : origCreated.apply(this, arguments);
      _setupNode(this);
      return result;
    };
  }
});
function _setupNode(node) {
  var _a;
  node.color = "#2a4a3a";
  node.bgcolor = "#1a3a2a";
  _ensureHiddenWidgets(node);
  let currentVideoPath = "";
  let lastSelection = [];
  const resizeNode = () => {
    var _a2;
    node.setSize([
      node.size[0],
      node.computeSize([node.size[0], node.size[1]])[1]
    ]);
    (_a2 = node == null ? void 0 : node.graph) == null ? void 0 : _a2.setDirtyCanvas(true);
  };
  const fileInput = document.createElement("input");
  Object.assign(fileInput, { type: "file", accept: "video/*", style: "display:none" });
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
  let isHovered = false, isFocused = false;
  const updateBtnStyle = () => {
    if (uploadBtn.disabled) return;
    const active = isHovered || isFocused;
    uploadBtn.style.backgroundColor = active ? "#333" : "#222";
    uploadBtn.style.outline = isFocused ? "2px solid #4a8a6a" : "none";
  };
  uploadBtn.onmouseenter = () => {
    isHovered = true;
    updateBtnStyle();
  };
  uploadBtn.onmouseleave = () => {
    isHovered = false;
    updateBtnStyle();
  };
  uploadBtn.onfocus = () => {
    isFocused = true;
    updateBtnStyle();
  };
  uploadBtn.onblur = () => {
    isFocused = false;
    updateBtnStyle();
  };
  uploadBtn.onclick = () => fileInput.click();
  uploadBtn.onpointerdown = (e) => e.stopPropagation();
  node.addDOMWidget("upload_button", "btn", uploadBtn, { serialize: false });
  const previewContainer = document.createElement("div");
  previewContainer.className = "ffmpega_preview";
  previewContainer.style.cssText = "width:100%;background:#1a1a1a;border-radius:6px;overflow:hidden;position:relative;display:none;";
  const videoEl = document.createElement("video");
  videoEl.controls = true;
  videoEl.loop = true;
  videoEl.muted = true;
  videoEl.volume = 1;
  videoEl.setAttribute("aria-label", "Frame Picker video preview");
  videoEl.style.cssText = "width:100%;display:block;";
  let userUnmuted = false;
  videoEl.addEventListener("volumechange", () => {
    userUnmuted = !videoEl.muted;
  });
  videoEl.addEventListener("play", () => {
    if (userUnmuted) videoEl.muted = false;
  });
  videoEl.addEventListener("loadedmetadata", () => {
    previewWidget.aspectRatio = videoEl.videoWidth / videoEl.videoHeight;
    resizeNode();
  });
  videoEl.addEventListener("error", () => {
    previewContainer.style.display = "none";
    infoEl.textContent = "No video loaded";
    resizeNode();
  });
  const infoEl = document.createElement("div");
  infoEl.style.cssText = "padding:4px 8px;font-size:11px;color:#aaa;font-family:monospace;background:#111;";
  infoEl.textContent = "No video loaded";
  previewContainer.appendChild(videoEl);
  previewContainer.appendChild(infoEl);
  for (const evt of PASSTHROUGH_EVENTS) {
    previewContainer.addEventListener(evt, (e) => e.stopPropagation(), true);
  }
  const previewWidget = node.addDOMWidget(
    "videopreview",
    "preview",
    previewContainer,
    {
      serialize: false,
      hideOnZoom: false,
      getValue() {
        return previewContainer.value;
      },
      setValue(v) {
        previewContainer.value = v;
      }
    }
  );
  previewWidget.aspectRatio = null;
  previewWidget.computeSize = function(width) {
    if (this.aspectRatio && previewContainer.style.display !== "none") {
      const h = (node.size[0] - 20) / this.aspectRatio + 10;
      return [width, Math.max(h, 0) + 30];
    }
    return [width, -4];
  };
  const editorBtn = document.createElement("button");
  editorBtn.innerHTML = "🖼 Open Frame Picker";
  editorBtn.setAttribute("aria-label", "Open Frame Picker");
  editorBtn.style.cssText = `
        width: 100%;
        margin-top: 4px;
        background: linear-gradient(135deg, #2a4a3a, #1a3a2a);
        color: #e8f0e8;
        border: 1px solid #4a8a6a;
        border-radius: 4px;
        padding: 8px;
        cursor: pointer;
        font-family: 'Inter', system-ui, sans-serif;
        font-size: 13px;
        font-weight: 600;
        transition: all 0.2s;
    `;
  editorBtn.onmouseenter = () => {
    editorBtn.style.background = "linear-gradient(135deg, #3a5a4a, #2a4a3a)";
    editorBtn.style.borderColor = "#6aaa8a";
  };
  editorBtn.onmouseleave = () => {
    editorBtn.style.background = "linear-gradient(135deg, #2a4a3a, #1a3a2a)";
    editorBtn.style.borderColor = "#4a8a6a";
  };
  editorBtn.onpointerdown = (e) => e.stopPropagation();
  editorBtn.onclick = () => {
    if (!currentVideoPath) {
      console.warn("[FramePicker] No video path set — upload or connect a video first");
      infoEl.textContent = "⚠ No video loaded — upload or connect one first";
      infoEl.style.color = "#ef4444";
      setTimeout(() => {
        infoEl.style.color = "#aaa";
      }, 3e3);
      return;
    }
    openPicker();
  };
  node.addDOMWidget("editor_button", "btn", editorBtn, { serialize: false });
  const setUploadState = (uploading, filename = "") => {
    if (uploading) {
      uploadBtn.innerHTML = "⏳ Uploading...";
      uploadBtn.disabled = true;
      uploadBtn.style.cursor = "wait";
      infoEl.textContent = `Uploading ${filename}...`;
      previewContainer.style.display = "";
      videoEl.style.display = "none";
    } else {
      uploadBtn.innerHTML = "Upload Video...";
      uploadBtn.disabled = false;
      uploadBtn.style.cursor = "pointer";
      videoEl.style.display = "block";
    }
    node.setDirtyCanvas(true, true);
    resizeNode();
  };
  const handleUpload = async (file) => {
    var _a2;
    setUploadState(true, file.name);
    const body = new FormData();
    body.append("image", file);
    try {
      const resp = await fetch("/upload/image", { method: "POST", body });
      if (resp.status !== 200) {
        infoEl.textContent = "Upload failed: " + resp.statusText;
        return false;
      }
      const data = await resp.json();
      const subfolder = data.subfolder || "";
      const inputPath = subfolder ? `input/${subfolder}/${data.name}` : `input/${data.name}`;
      const pathW2 = (_a2 = node.widgets) == null ? void 0 : _a2.find((w) => w.name === "video_path");
      if (pathW2) pathW2.value = inputPath;
      loadPreview(inputPath);
      return true;
    } catch (e) {
      console.warn("[FramePicker] Upload error:", e);
      infoEl.textContent = "Upload error: " + e;
      return false;
    } finally {
      setUploadState(false);
    }
  };
  fileInput.onchange = async () => {
    var _a2;
    if ((_a2 = fileInput.files) == null ? void 0 : _a2.length) await handleUpload(fileInput.files[0]);
  };
  let _dragTimeout = null;
  let _origHTML = "", _origBorder = "", _hasDrag = false;
  const _revertDrag = () => {
    if (!_hasDrag) return;
    uploadBtn.innerHTML = _origHTML;
    uploadBtn.style.border = _origBorder;
    uploadBtn.style.backgroundColor = "";
    updateBtnStyle();
    _hasDrag = false;
  };
  node.onDragOver = (e) => {
    var _a2, _b, _c;
    if ((_c = (_b = (_a2 = e == null ? void 0 : e.dataTransfer) == null ? void 0 : _a2.types) == null ? void 0 : _b.includes) == null ? void 0 : _c.call(_b, "Files")) {
      if (!uploadBtn.disabled) {
        if (!_hasDrag) {
          _origHTML = uploadBtn.innerHTML;
          _origBorder = uploadBtn.style.border;
          _hasDrag = true;
        }
        uploadBtn.innerHTML = '<span aria-hidden="true">📂</span> Drop to Upload';
        uploadBtn.style.border = "1px dashed #4a8a6a";
        uploadBtn.style.backgroundColor = "#333";
        if (_dragTimeout) clearTimeout(_dragTimeout);
        _dragTimeout = setTimeout(() => {
          if (!uploadBtn.disabled) _revertDrag();
        }, 500);
      }
      return true;
    }
    return false;
  };
  node.onDragDrop = async (e) => {
    var _a2, _b;
    if (_dragTimeout) {
      clearTimeout(_dragTimeout);
      _dragTimeout = null;
    }
    _revertDrag();
    const file = (_b = (_a2 = e == null ? void 0 : e.dataTransfer) == null ? void 0 : _a2.files) == null ? void 0 : _b[0];
    if (!file || !file.type.startsWith("video/")) return false;
    return await handleUpload(file);
  };
  function loadPreview(path) {
    currentVideoPath = path;
    previewContainer.style.display = "";
    const url = api.apiURL(`${PREVIEW_ROUTE}?path=${encodeURIComponent(path)}`);
    videoEl.src = url;
    const filename = path.split("/").pop() || path;
    infoEl.textContent = filename;
  }
  const origOnExecuted = node.onExecuted;
  node.onExecuted = function(data) {
    var _a2, _b, _c;
    origOnExecuted == null ? void 0 : origOnExecuted.call(node, data);
    if ((_a2 = data == null ? void 0 : data.video_path) == null ? void 0 : _a2[0]) {
      loadPreview(data.video_path[0]);
      resizeNode();
    }
    if ((_b = data == null ? void 0 : data.framepicker_meta) == null ? void 0 : _b[0]) {
      const meta = data.framepicker_meta[0];
      currentVideoPath = meta.video_path;
      loadPreview(meta.video_path);
      resizeNode();
      const autoW = (_c = node.widgets) == null ? void 0 : _c.find((w) => w.name === "auto_open_editor");
      if ((autoW == null ? void 0 : autoW.value) && !getModal().isOpen) {
        console.log("[FramePicker] Auto-opening picker (workflow paused)");
        openPicker();
      }
    }
  };
  function openPicker() {
    const modal = getModal();
    const nodeId = String(node.id);
    modal.setCallbacks({
      onApply: async (selectedIndices, transforms) => {
        lastSelection = selectedIndices;
        if (selectedIndices.length === 0) {
          _setW(node, "_edit_action", "passthrough");
          app.queuePrompt(0, 1).finally(() => _setW(node, "_edit_action", "none"));
          return;
        }
        const transformsObj = {};
        if (transforms) {
          for (const [idx, t] of transforms) {
            transformsObj[String(idx)] = t;
          }
        }
        try {
          await api.fetchApi("/framepicker/apply_selection", {
            method: "POST",
            body: JSON.stringify({
              node_id: nodeId,
              selected_indices: selectedIndices,
              transforms: Object.keys(transformsObj).length > 0 ? transformsObj : void 0
            })
          });
        } catch (e) {
          console.error("[FramePicker] Failed to store selection:", e);
        }
        _setW(node, "_edit_action", "apply");
        app.queuePrompt(0, 1).finally(() => _setW(node, "_edit_action", "none"));
      },
      onCancel: () => {
      }
    });
    modal.open(currentVideoPath, lastSelection.length > 0 ? lastSelection : void 0);
  }
  let lastPolledPath = "";
  const pollInterval = setInterval(() => {
    var _a2;
    if (!node.graph) {
      clearInterval(pollInterval);
      return;
    }
    const pw = (_a2 = node.widgets) == null ? void 0 : _a2.find((w) => w.name === "video_path");
    const val = (pw == null ? void 0 : pw.value) ? String(pw.value).trim() : "";
    if (val && val !== lastPolledPath) {
      lastPolledPath = val;
      loadPreview(val);
    }
  }, 500);
  const pathW = (_a = node.widgets) == null ? void 0 : _a.find((w) => w.name === "video_path");
  if ((pathW == null ? void 0 : pathW.value) && String(pathW.value).trim()) {
    loadPreview(String(pathW.value).trim());
  }
  const origOnRemoved = node.onRemoved;
  node.onRemoved = function() {
    fileInput == null ? void 0 : fileInput.remove();
    clearInterval(pollInterval);
    origOnRemoved == null ? void 0 : origOnRemoved.apply(this, arguments);
  };
}
function _setW(node, name, value) {
  var _a;
  const w = (_a = node.widgets) == null ? void 0 : _a.find((w2) => w2.name === name);
  if (w) {
    w.value = value;
  } else {
    if (!node.properties) node.properties = {};
    node.properties[name] = value;
  }
}
const HIDDEN_WIDGETS = [
  ["_edit_action", "none"]
];
function _ensureHiddenWidgets(node) {
  var _a;
  for (const [name, defaultVal] of HIDDEN_WIDGETS) {
    let w = (_a = node.widgets) == null ? void 0 : _a.find((w2) => w2.name === name);
    if (!w) {
      w = node.addWidget(
        "text",
        name,
        defaultVal,
        () => {
        },
        { serialize: true }
      );
    }
    w.computeSize = () => [0, -4];
    w.draw = () => {
    };
  }
}
