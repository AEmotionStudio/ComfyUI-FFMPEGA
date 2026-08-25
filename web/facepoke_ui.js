var __defProp = Object.defineProperty;
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
const L = (inner) => `<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-0.125em">${inner}</svg>`;
const fpIconPlay = L(
  '<path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"/>'
);
const fpIconPause = L(
  '<rect x="14" y="3" width="5" height="18" rx="1"/><rect x="5" y="3" width="5" height="18" rx="1"/>'
);
const fpIconSkipStart = L(
  '<path d="M19 20 9 12l10-8z"/><line x1="5" x2="5" y1="19" y2="5"/>'
);
const fpIconSkipEnd = L(
  '<path d="M5 4l10 8-10 8z"/><line x1="19" x2="19" y1="5" y2="19"/>'
);
const fpIconPrev = L('<path d="m15 18-6-6 6-6"/>');
const fpIconNext = L('<path d="m9 18 6-6-6-6"/>');
const fpIconUndo = L(
  '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"/>'
);
const fpIconRedo = L(
  '<path d="m15 14 5-5-5-5"/><path d="M20 9H9.5A5.5 5.5 0 0 0 4 14.5A5.5 5.5 0 0 0 9.5 20H13"/>'
);
const fpIconCheck = L('<path d="M20 6 9 17l-5-5"/>');
const fpIconClose = L('<path d="M18 6 6 18"/><path d="m6 6 12 12"/>');
const fpIconReset = L(
  '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>'
);
const fpIconEye = L(
  '<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>'
);
const fpIconEyeOff = L(
  '<path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"/><path d="M14.084 14.158a3 3 0 0 1-4.242-4.242"/><path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"/><path d="m2 2 20 20"/>'
);
const fpIconLandmarks = L(
  '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><circle cx="12" cy="12" r="3"/><path d="m16 16-1.9-1.9"/>'
);
const fpIconFace = L(
  '<path d="M10 11h.01"/><path d="M14 6h.01"/><path d="M18 6h.01"/><path d="M6.5 13.1h.01"/><path d="M22 5c0 9-4 12-6 12s-6-3-6-12c0-2 2-3 6-3s6 1 6 3"/><path d="M17.4 9.9c-.8.8-2 .8-2.8 0"/><path d="M10.1 7.1C9 7.2 7.7 7.7 6 8.6c-3.5 2-4.7 3.9-3.7 5.6 4.5 7.8 9.5 8.4 11.2 7.4.9-.5 1.9-2.1 1.9-4.7"/><path d="M9.1 16.5c.3-1.1 1.4-1.7 2.4-1.4"/>'
);
const fpIconInterpolate = L(
  '<circle cx="19" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><path d="M5 17A12 12 0 0 1 17 5"/>'
);
const fpIconPassThrough = L(
  '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>'
);
const fpIconScanFace = L(
  '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><path d="M9 9h.01"/><path d="M15 9h.01"/>'
);
const fpIconVideo = L(
  '<path d="m16 13 5.223 3.482a.5.5 0 0 0 .777-.416v-8.132a.5.5 0 0 0-.777-.416L16 11"/><rect x="2" y="6" width="14" height="12" rx="2"/>'
);
const fpIconImage = L(
  '<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>'
);
const fpIconRemove = L(
  '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>'
);
const SLIDERS = [
  { key: "rotate_pitch", label: "Pitch", min: -20, max: 20, step: 0.5, default: 0 },
  { key: "rotate_yaw", label: "Yaw", min: -20, max: 20, step: 0.5, default: 0 },
  { key: "rotate_roll", label: "Roll", min: -20, max: 20, step: 0.5, default: 0 },
  { key: "blink", label: "Blink (Both)", min: -20, max: 5, step: 0.5, default: 0 },
  { key: "blink_left", label: "Blink Left", min: -20, max: 5, step: 0.5, default: 0 },
  { key: "blink_right", label: "Blink Right", min: -20, max: 5, step: 0.5, default: 0 },
  { key: "eyebrow", label: "Eyebrow (Both)", min: -10, max: 15, step: 0.5, default: 0 },
  { key: "eyebrow_left", label: "Eyebrow Left", min: -10, max: 15, step: 0.5, default: 0 },
  { key: "eyebrow_right", label: "Eyebrow Right", min: -10, max: 15, step: 0.5, default: 0 },
  { key: "wink", label: "Wink", min: 0, max: 25, step: 0.5, default: 0 },
  { key: "pupil_x", label: "Pupil X", min: -15, max: 15, step: 0.5, default: 0 },
  { key: "pupil_y", label: "Pupil Y", min: -15, max: 15, step: 0.5, default: 0 },
  { key: "aaa", label: "Open Mouth", min: -30, max: 120, step: 1, default: 0 },
  { key: "eee", label: "Eee", min: -20, max: 15, step: 0.5, default: 0 },
  { key: "woo", label: "Woo", min: -20, max: 15, step: 0.5, default: 0 },
  { key: "smile", label: "Smile", min: -0.3, max: 1.3, step: 0.01, default: 0 }
];
const CONTROL_POINTS = [
  {
    id: "forehead",
    label: "Pitch",
    rx: 0.5,
    ry: 0.1,
    color: "#7c6aef",
    dragMap: [{ key: "rotate_pitch", axis: "y", sensitivity: -0.2 }]
  },
  {
    id: "left-eyebrow",
    label: "L Eyebrow",
    rx: 0.32,
    ry: 0.22,
    color: "#2ec4b6",
    dragMap: [{ key: "eyebrow_left", axis: "y", sensitivity: -0.15 }]
  },
  {
    id: "right-eyebrow",
    label: "R Eyebrow",
    rx: 0.68,
    ry: 0.22,
    color: "#2ec4b6",
    dragMap: [{ key: "eyebrow_right", axis: "y", sensitivity: -0.15 }]
  },
  {
    id: "left-eye",
    label: "Eye L",
    rx: 0.32,
    ry: 0.38,
    color: "#5bc0be",
    dragMap: [
      { key: "pupil_x", axis: "x", sensitivity: 0.1 },
      { key: "pupil_y", axis: "y", sensitivity: 0.1 },
      { key: "blink_left", axis: "y", sensitivity: -0.15 }
    ]
  },
  {
    id: "right-eye",
    label: "Eye R",
    rx: 0.68,
    ry: 0.38,
    color: "#5bc0be",
    dragMap: [
      { key: "pupil_x", axis: "x", sensitivity: 0.1 },
      { key: "pupil_y", axis: "y", sensitivity: 0.1 },
      { key: "blink_right", axis: "y", sensitivity: -0.15 }
    ]
  },
  {
    id: "wink",
    label: "Wink",
    rx: 0.15,
    ry: 0.38,
    color: "#264653",
    dragMap: [{ key: "wink", axis: "y", sensitivity: -0.15 }]
  },
  {
    id: "left-cheek",
    label: "Yaw",
    rx: 0.08,
    ry: 0.5,
    color: "#f4a261",
    dragMap: [{ key: "rotate_yaw", axis: "x", sensitivity: 0.2 }]
  },
  {
    id: "right-cheek",
    label: "Yaw",
    rx: 0.92,
    ry: 0.5,
    color: "#f4a261",
    dragMap: [{ key: "rotate_yaw", axis: "x", sensitivity: 0.2 }]
  },
  {
    id: "nose-roll",
    label: "Roll",
    rx: 0.5,
    ry: 0.52,
    color: "#e9c46a",
    dragMap: [{ key: "rotate_roll", axis: "x", sensitivity: 0.2 }]
  },
  {
    id: "mouth",
    label: "Mouth",
    rx: 0.5,
    ry: 0.72,
    color: "#e76f51",
    dragMap: [
      { key: "smile", axis: "y", sensitivity: -8e-3 },
      { key: "aaa", axis: "y", sensitivity: 0.3 }
    ]
  },
  {
    id: "chin",
    label: "Tilt",
    rx: 0.5,
    ry: 0.95,
    color: "#9b5de5",
    dragMap: [{ key: "rotate_pitch", axis: "y", sensitivity: 0.2 }]
  }
];
const EMOTION_PRESETS = [
  { label: "Happy", params: { smile: 0.8, eyebrow: 3, blink: -2 } },
  { label: "Big Smile", params: { smile: 1.2, eyebrow: 5, eee: -5, blink: -3 } },
  { label: "Surprised", params: { aaa: 60, eyebrow: 12, blink: -5, rotate_pitch: -3 } },
  { label: "Sad", params: { smile: -0.2, eyebrow: -5, rotate_pitch: 5, blink: 2 } },
  { label: "Angry", params: { eyebrow: -8, smile: -0.15, eee: 3, rotate_pitch: 3 } },
  { label: "Neutral", params: {} },
  { label: "Wink", params: { wink: 15, smile: 0.5 } },
  { label: "Worried", params: { eyebrow: -4, aaa: 10, blink: 1, rotate_pitch: 2 } },
  { label: "Shocked", params: { aaa: 90, eyebrow: 15, blink: -8, rotate_pitch: -5 } },
  { label: "Smirk", params: { smile: 0.4, wink: 8, eyebrow_right: 5, rotate_yaw: -3 } },
  { label: "Thinking", params: { eyebrow_left: 8, pupil_x: 8, pupil_y: -5, rotate_yaw: 5, rotate_pitch: -2 } },
  { label: "Sleepy", params: { blink: 4, eyebrow: -3, rotate_pitch: 8, smile: -0.1 } }
];
class FacePokeModal {
  constructor(callbacks) {
    __publicField(this, "dialog");
    __publicField(this, "panel");
    __publicField(this, "canvasImg");
    __publicField(this, "canvasArea");
    __publicField(this, "filmstrip");
    __publicField(this, "sliderPanel");
    __publicField(this, "sliderTitle");
    __publicField(this, "statusEl");
    __publicField(this, "callbacks");
    __publicField(this, "_isOpen", false);
    __publicField(this, "videoPath", "");
    __publicField(this, "allEdits", {});
    __publicField(this, "currentFrame", 0);
    __publicField(this, "currentFaceIdx", 0);
    __publicField(this, "faces", []);
    __publicField(this, "totalFrames", 0);
    __publicField(this, "videoWidth", 0);
    __publicField(this, "videoHeight", 0);
    __publicField(this, "videoFps", 24);
    __publicField(this, "_escHandler", null);
    __publicField(this, "_wheelHandler", null);
    __publicField(this, "_previewDebounce", null);
    __publicField(this, "_showLandmarks", false);
    __publicField(this, "_showMarkers", true);
    __publicField(this, "_previewInFlight", false);
    __publicField(this, "_playing", false);
    __publicField(this, "_playTimer", null);
    __publicField(this, "_undoStack", []);
    __publicField(this, "_redoStack", []);
    __publicField(this, "_useBlaze", false);
    __publicField(this, "_faceCache", /* @__PURE__ */ new Map());
    // ── Reference driving state ──
    __publicField(this, "_drivingId", null);
    __publicField(this, "_drivingTotalFrames", 0);
    __publicField(this, "_drivingMultiplier", 1);
    __publicField(this, "_refKp", null);
    // per-frame ref expression
    __publicField(this, "_refRatio", 1);
    __publicField(this, "_refParts", "all");
    this.callbacks = callbacks;
    document.querySelectorAll(".fpoke-backdrop").forEach((d) => d.remove());
    this.dialog = document.createElement("div");
    this.dialog.className = "fpoke-backdrop";
    this.dialog.style.display = "none";
    this.dialog.setAttribute("role", "dialog");
    this.dialog.setAttribute("aria-modal", "true");
    this.dialog.setAttribute("aria-label", "Face Poke Editor");
    this.panel = document.createElement("div");
    this.panel.className = "fpoke-panel";
    const header = document.createElement("div");
    header.className = "fpoke-header";
    const title = document.createElement("h2");
    title.className = "fpoke-title";
    title.innerHTML = `${fpIconFace} Face Poke Editor`;
    const frameInfo = document.createElement("span");
    frameInfo.className = "fpoke-frame-info";
    frameInfo.id = "fpoke-frame-info";
    frameInfo.textContent = "No video loaded";
    const headerActions = document.createElement("div");
    headerActions.className = "fpoke-header-actions";
    const resetAllBtn = this._makeBtn(`${fpIconReset} Reset All`, "fpoke-btn-sm", () => {
      this.allEdits = {};
      this._loadSliders();
      this._updateFilmstripMarkers();
      this._loadCanvasFrame();
      this._setStatus("All edits cleared");
    });
    const cancelBtn = this._makeBtn("Cancel", "fpoke-btn-sm", () => this._cancel());
    cancelBtn.title = "Cancel (ESC)";
    const applyBtn = this._makeBtn(`${fpIconCheck} Apply Edits`, "fpoke-btn-sm fpoke-btn-apply", () => this._apply());
    applyBtn.title = "Apply edits and rebuild video";
    const closeBtn = document.createElement("button");
    closeBtn.className = "fpoke-close";
    closeBtn.innerHTML = fpIconClose;
    closeBtn.title = "Close (ESC)";
    closeBtn.addEventListener("click", () => this._cancel());
    const landmarkBtn = this._makeBtn(`${fpIconLandmarks} Landmarks`, "fpoke-btn-sm fpoke-btn-landmark", () => {
      this._showLandmarks = !this._showLandmarks;
      landmarkBtn.classList.toggle("active", this._showLandmarks);
      landmarkBtn.innerHTML = this._showLandmarks ? `${fpIconLandmarks} Landmarks ${fpIconCheck}` : `${fpIconLandmarks} Landmarks`;
      this._loadCanvasFrame();
    });
    landmarkBtn.title = "Toggle face landmarks overlay (L)";
    const markersBtn = this._makeBtn(`${fpIconEye} Markers`, "fpoke-btn-sm fpoke-btn-markers active", () => {
      this._showMarkers = !this._showMarkers;
      markersBtn.classList.toggle("active", this._showMarkers);
      markersBtn.innerHTML = this._showMarkers ? `${fpIconEye} Markers` : `${fpIconEyeOff} Markers`;
      if (this._showMarkers) this._renderFaceOverlays();
      else this.canvasArea.querySelectorAll(".fpoke-face-overlay, .fpoke-ctrl-point").forEach((el) => el.remove());
    });
    markersBtn.title = "Toggle face markers / control points (M)";
    const undoBtn = this._makeBtn(`${fpIconUndo} Undo`, "fpoke-btn-sm", () => this._undo());
    undoBtn.title = "Undo (Ctrl+Z)";
    undoBtn.id = "fpoke-undo-btn";
    const redoBtn = this._makeBtn(`${fpIconRedo} Redo`, "fpoke-btn-sm", () => this._redo());
    redoBtn.title = "Redo (Ctrl+Y)";
    redoBtn.id = "fpoke-redo-btn";
    const playBtn = this._makeBtn(`${fpIconPlay} Play`, "fpoke-btn-sm fpoke-btn-play", () => this._togglePlayback());
    playBtn.title = "Play/pause preview (Space)";
    playBtn.id = "fpoke-play-btn";
    const blazeBtn = this._makeBtn(`${fpIconScanFace} Blaze`, "fpoke-btn-sm fpoke-btn-blaze", () => {
      this._useBlaze = !this._useBlaze;
      blazeBtn.classList.toggle("active", this._useBlaze);
      blazeBtn.innerHTML = this._useBlaze ? `${fpIconScanFace} Blaze ${fpIconCheck}` : `${fpIconScanFace} Blaze`;
      this._faceCache.clear();
      this._selectFrame(this.currentFrame);
    });
    blazeBtn.title = "Enable blazeface fallback for small/distant faces";
    headerActions.append(undoBtn, redoBtn, playBtn, landmarkBtn, markersBtn, blazeBtn, resetAllBtn, cancelBtn, applyBtn, closeBtn);
    header.append(title, frameInfo, headerActions);
    this.canvasArea = document.createElement("div");
    this.canvasArea.className = "fpoke-canvas-area";
    this.canvasImg = document.createElement("img");
    this.canvasImg.className = "fpoke-canvas";
    this.canvasImg.alt = "Frame with face overlays";
    this.canvasArea.appendChild(this.canvasImg);
    this.sliderPanel = document.createElement("div");
    this.sliderPanel.className = "fpoke-sliders";
    this.sliderTitle = document.createElement("div");
    this.sliderTitle.className = "fpoke-slider-title";
    this.sliderTitle.textContent = "Expression Controls — Face 1";
    this.sliderPanel.appendChild(this.sliderTitle);
    const sliderGroup = document.createElement("div");
    sliderGroup.className = "fpoke-slider-group";
    for (const s of SLIDERS) {
      const row = document.createElement("div");
      row.className = "fpoke-slider-row";
      const label = document.createElement("span");
      label.className = "fpoke-slider-label";
      label.textContent = s.label;
      const input = document.createElement("input");
      input.type = "range";
      input.className = "fpoke-slider-input";
      input.min = String(s.min);
      input.max = String(s.max);
      input.step = String(s.step);
      input.value = String(s.default);
      input.id = `fpoke-sl-${s.key}`;
      const valEl = document.createElement("span");
      valEl.className = "fpoke-slider-value";
      valEl.textContent = String(s.default);
      valEl.id = `fpoke-sv-${s.key}`;
      input.addEventListener("input", () => {
        valEl.textContent = Number(input.value).toFixed(s.step < 1 ? 2 : 0);
        this._onSliderChange();
      });
      row.append(label, input, valEl);
      sliderGroup.appendChild(row);
    }
    const resetFrameRow = document.createElement("div");
    resetFrameRow.style.cssText = "padding: 10px 0 0; display: flex; gap: 6px;";
    const resetFrameBtn = this._makeBtn(`${fpIconReset} Reset Frame`, "fpoke-btn-sm fpoke-btn-reset", () => this._resetFrame());
    const passthroughBtn = this._makeBtn(`${fpIconPassThrough} Pass Through`, "fpoke-btn-sm fpoke-btn-pass", () => this._passthrough());
    const interpolateBtn = this._makeBtn(`${fpIconInterpolate} Interpolate`, "fpoke-btn-sm fpoke-btn-interp", () => this._interpolateFrames());
    interpolateBtn.title = "Smoothly fill frames between keyframes (I)";
    resetFrameRow.append(resetFrameBtn, passthroughBtn, interpolateBtn);
    this.sliderPanel.append(sliderGroup, resetFrameRow);
    const presetSection = document.createElement("div");
    presetSection.className = "fpoke-preset-section";
    const presetLabel = document.createElement("div");
    presetLabel.className = "fpoke-preset-label";
    presetLabel.textContent = "EMOTION PRESETS";
    presetSection.appendChild(presetLabel);
    const presetGrid = document.createElement("div");
    presetGrid.className = "fpoke-preset-grid";
    for (const preset of EMOTION_PRESETS) {
      const chip = document.createElement("button");
      chip.className = "fpoke-preset-chip";
      chip.textContent = preset.label;
      chip.title = Object.entries(preset.params).map(([k, v]) => `${k}: ${v}`).join(", ") || "Reset to neutral";
      chip.addEventListener("click", () => this._applyPreset(preset));
      chip.onpointerdown = (e) => e.stopPropagation();
      presetGrid.appendChild(chip);
    }
    presetSection.appendChild(presetGrid);
    this.sliderPanel.appendChild(presetSection);
    const refSection = document.createElement("div");
    refSection.className = "fpoke-ref-section";
    refSection.id = "fpoke-ref-section";
    const refLabel = document.createElement("div");
    refLabel.className = "fpoke-preset-label";
    refLabel.textContent = "REFERENCE IMAGE";
    refSection.appendChild(refLabel);
    const refRow = document.createElement("div");
    refRow.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;";
    const refUploadBtn = this._makeBtn(`${fpIconImage} Load Ref Image`, "fpoke-btn-sm", () => {
      const input = document.createElement("input");
      input.type = "file";
      input.accept = "image/*";
      input.onchange = () => {
        var _a;
        const file = (_a = input.files) == null ? void 0 : _a[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => this._loadRefImage(reader.result);
        reader.readAsDataURL(file);
      };
      input.click();
    });
    refUploadBtn.title = "Upload a face image to transfer its expression to this frame";
    const refClearBtn = this._makeBtn(`${fpIconRemove} Clear`, "fpoke-btn-sm fpoke-btn-reset", () => {
      this._refKp = null;
      const info = document.getElementById("fpoke-ref-info");
      if (info) info.textContent = "No reference loaded";
      this._loadCanvasFrame();
    });
    const refInfo = document.createElement("span");
    refInfo.className = "fpoke-edited-count";
    refInfo.id = "fpoke-ref-info";
    refInfo.textContent = "No reference loaded";
    refRow.append(refUploadBtn, refClearBtn, refInfo);
    refSection.appendChild(refRow);
    const ratioRow = document.createElement("div");
    ratioRow.className = "fpoke-slider-row";
    const ratioLabel = document.createElement("span");
    ratioLabel.className = "fpoke-slider-label";
    ratioLabel.textContent = "Ratio";
    const ratioInput = document.createElement("input");
    ratioInput.type = "range";
    ratioInput.className = "fpoke-slider-input";
    ratioInput.min = "0";
    ratioInput.max = "1";
    ratioInput.step = "0.05";
    ratioInput.value = "1";
    ratioInput.id = "fpoke-ref-ratio";
    const ratioVal = document.createElement("span");
    ratioVal.className = "fpoke-slider-value";
    ratioVal.textContent = "1.00";
    ratioInput.addEventListener("input", () => {
      this._refRatio = parseFloat(ratioInput.value);
      ratioVal.textContent = this._refRatio.toFixed(2);
      if (this._refKp) this._requestRefPreview();
    });
    ratioRow.append(ratioLabel, ratioInput, ratioVal);
    refSection.appendChild(ratioRow);
    const partsRow = document.createElement("div");
    partsRow.style.cssText = "display:flex;gap:6px;align-items:center;padding:4px 0;";
    const partsLabel = document.createElement("span");
    partsLabel.className = "fpoke-slider-label";
    partsLabel.textContent = "Parts";
    const partsSelect = document.createElement("select");
    partsSelect.className = "fpoke-select";
    partsSelect.id = "fpoke-ref-parts";
    for (const opt of ["all", "mouth_only", "eyes_only", "rotation_only"]) {
      const o = document.createElement("option");
      o.value = opt;
      o.textContent = opt.replace("_", " ");
      partsSelect.appendChild(o);
    }
    partsSelect.addEventListener("change", () => {
      this._refParts = partsSelect.value;
      if (this._refKp) this._requestRefPreview();
    });
    partsRow.append(partsLabel, partsSelect);
    refSection.appendChild(partsRow);
    this.sliderPanel.appendChild(refSection);
    const drvSection = document.createElement("div");
    drvSection.className = "fpoke-ref-section";
    drvSection.id = "fpoke-drv-section";
    const drvLabel = document.createElement("div");
    drvLabel.className = "fpoke-preset-label";
    drvLabel.textContent = "DRIVING VIDEO";
    drvSection.appendChild(drvLabel);
    const drvRow = document.createElement("div");
    drvRow.style.cssText = "display:flex;gap:6px;align-items:center;flex-wrap:wrap;";
    const drvUploadBtn = this._makeBtn(`${fpIconVideo} Load Driving Video`, "fpoke-btn-sm", () => {
      const input = document.createElement("input");
      input.type = "file";
      input.accept = "video/*";
      input.onchange = () => {
        var _a;
        const file = (_a = input.files) == null ? void 0 : _a[0];
        if (!file) return;
        this._uploadDrivingVideo(file);
      };
      input.click();
    });
    drvUploadBtn.title = "Upload a driving video to transfer motion across all frames";
    const drvClearBtn = this._makeBtn(`${fpIconRemove} Clear`, "fpoke-btn-sm fpoke-btn-reset", () => {
      this._drivingId = null;
      this._drivingTotalFrames = 0;
      const info = document.getElementById("fpoke-drv-info");
      if (info) info.textContent = "No driving video";
      this._loadCanvasFrame();
    });
    const drvApplyBtn = this._makeBtn(`${fpIconCheck} Apply to All`, "fpoke-btn-sm fpoke-btn-apply", () => {
      this._applyDrivingToAll();
    });
    drvApplyBtn.title = "Map driving video motion to all source frames";
    drvApplyBtn.id = "fpoke-drv-apply";
    const drvInfo = document.createElement("span");
    drvInfo.className = "fpoke-edited-count";
    drvInfo.id = "fpoke-drv-info";
    drvInfo.textContent = "No driving video";
    drvRow.append(drvUploadBtn, drvClearBtn, drvApplyBtn, drvInfo);
    drvSection.appendChild(drvRow);
    const mulRow = document.createElement("div");
    mulRow.className = "fpoke-slider-row";
    const mulLabel = document.createElement("span");
    mulLabel.className = "fpoke-slider-label";
    mulLabel.textContent = "Multiplier";
    const mulInput = document.createElement("input");
    mulInput.type = "range";
    mulInput.className = "fpoke-slider-input";
    mulInput.min = "0.1";
    mulInput.max = "2";
    mulInput.step = "0.05";
    mulInput.value = "1";
    mulInput.id = "fpoke-drv-multiplier";
    const mulVal = document.createElement("span");
    mulVal.className = "fpoke-slider-value";
    mulVal.textContent = "1.00";
    mulInput.addEventListener("input", () => {
      this._drivingMultiplier = parseFloat(mulInput.value);
      mulVal.textContent = this._drivingMultiplier.toFixed(2);
      if (this._drivingId) this._requestRefPreview();
    });
    mulRow.append(mulLabel, mulInput, mulVal);
    drvSection.appendChild(mulRow);
    this.sliderPanel.appendChild(drvSection);
    this.filmstrip = document.createElement("div");
    this.filmstrip.className = "fpoke-filmstrip";
    const toolbar = document.createElement("div");
    toolbar.className = "fpoke-toolbar";
    this.statusEl = document.createElement("div");
    this.statusEl.className = "fpoke-status";
    this.statusEl.textContent = "Drag faces or adjust sliders, then Apply Edits";
    const navBtns = document.createElement("div");
    navBtns.className = "fpoke-nav-btns";
    const firstBtn = this._makeBtn(fpIconSkipStart, "fpoke-btn-sm", () => this._selectFrame(0));
    firstBtn.title = "First frame (Home)";
    const prevBtn = this._makeBtn(`${fpIconPrev} Prev`, "fpoke-btn-sm", () => this._prevFrame());
    prevBtn.title = "Previous frame (←)";
    const nextBtn = this._makeBtn(`Next ${fpIconNext}`, "fpoke-btn-sm", () => this._nextFrame());
    nextBtn.title = "Next frame (→)";
    const lastBtn = this._makeBtn(fpIconSkipEnd, "fpoke-btn-sm", () => this._selectFrame(Math.max(0, this.totalFrames - 1)));
    lastBtn.title = "Last frame (End)";
    const editedCount = document.createElement("span");
    editedCount.className = "fpoke-edited-count";
    editedCount.id = "fpoke-edited-count";
    editedCount.textContent = "0 frames edited";
    navBtns.append(firstBtn, prevBtn, nextBtn, lastBtn, editedCount);
    toolbar.append(this.statusEl, navBtns);
    this.panel.append(header, this.canvasArea, this.sliderPanel, this.filmstrip, toolbar);
    this.dialog.appendChild(this.panel);
    document.body.appendChild(this.dialog);
    console.log("[FacePoke] Modal constructor complete, dialog appended to body");
  }
  // ── Public API ─────────────────────────────────────────────
  async open(videoPath, initialEdits) {
    console.log("[FacePoke] Modal.open() called, _isOpen:", this._isOpen, "path:", videoPath);
    if (this._isOpen) {
      console.warn("[FacePoke] Modal already open, ignoring");
      return;
    }
    this._isOpen = true;
    this.videoPath = videoPath;
    this.allEdits = initialEdits ? JSON.parse(JSON.stringify(initialEdits)) : {};
    this.currentFrame = 0;
    this.currentFaceIdx = 0;
    this._faceCache.clear();
    this._setStatus("Loading video...");
    this.dialog.style.display = "flex";
    console.log("[FacePoke] Dialog display set to flex");
    this._escHandler = (e) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "Escape") {
        this._cancel();
        return;
      }
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        this._prevFrame();
        return;
      }
      if (e.key === "ArrowRight") {
        e.preventDefault();
        this._nextFrame();
        return;
      }
      if (e.key === "Home") {
        e.preventDefault();
        this._selectFrame(0);
        return;
      }
      if (e.key === "End") {
        e.preventDefault();
        this._selectFrame(Math.max(0, this.totalFrames - 1));
        return;
      }
      if (e.key === "r" || e.key === "R") {
        this._resetFrame();
        return;
      }
      if (e.key === "l" || e.key === "L") {
        this._showLandmarks = !this._showLandmarks;
        const lBtn = this.panel.querySelector(".fpoke-btn-landmark");
        if (lBtn) {
          lBtn.classList.toggle("active", this._showLandmarks);
          lBtn.innerHTML = this._showLandmarks ? `${fpIconLandmarks} Landmarks ${fpIconCheck}` : `${fpIconLandmarks} Landmarks`;
        }
        this._loadCanvasFrame();
        return;
      }
      if (e.key === "m" || e.key === "M") {
        this._showMarkers = !this._showMarkers;
        const mBtn = this.panel.querySelector(".fpoke-btn-markers");
        if (mBtn) {
          mBtn.classList.toggle("active", this._showMarkers);
          mBtn.innerHTML = this._showMarkers ? `${fpIconEye} Markers` : `${fpIconEyeOff} Markers`;
        }
        if (this._showMarkers) this._renderFaceOverlays();
        else this.canvasArea.querySelectorAll(".fpoke-face-overlay, .fpoke-ctrl-point").forEach((el) => el.remove());
        return;
      }
      if (e.key === "i" || e.key === "I") {
        this._interpolateFrames();
        return;
      }
      if (e.key === " ") {
        e.preventDefault();
        this._togglePlayback();
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
    };
    document.addEventListener("keydown", this._escHandler);
    this._wheelHandler = (e) => {
      e.preventDefault();
      if (e.deltaY > 0) this._nextFrame();
      else if (e.deltaY < 0) this._prevFrame();
    };
    this.canvasArea.addEventListener("wheel", this._wheelHandler, { passive: false });
    try {
      const resp = await api.fetchApi("/facepoke/get_frames", {
        method: "POST",
        body: JSON.stringify({ node_id: "", video_path: videoPath })
      });
      if (resp.ok) {
        const meta = await resp.json();
        this.totalFrames = meta.total_frames || 1;
        this.videoWidth = meta.width || 640;
        this.videoHeight = meta.height || 480;
        this.videoFps = meta.fps || 24;
        console.log("[FacePoke] Video meta loaded:", this.totalFrames, "frames");
      } else {
        const errText = await resp.text();
        console.warn("[FacePoke] get_frames API error:", resp.status, errText);
        this.totalFrames = 1;
      }
    } catch (err) {
      console.error("[FacePoke] Failed to fetch video metadata:", err);
      this.totalFrames = 1;
    }
    this._updateFrameInfo();
    this._buildFilmstrip();
    this._updateEditedCount();
    try {
      await this._selectFrame(0);
      this._setStatus("Drag faces or adjust sliders, then Apply Edits");
    } catch (err) {
      console.error("[FacePoke] Failed to load initial frame:", err);
      this._setStatus("⚠ Failed to load frame — check console for details");
    }
  }
  close() {
    if (!this._isOpen) return;
    this._isOpen = false;
    if (this._escHandler) {
      document.removeEventListener("keydown", this._escHandler);
      this._escHandler = null;
    }
    if (this._wheelHandler) {
      this.canvasArea.removeEventListener("wheel", this._wheelHandler);
      this._wheelHandler = null;
    }
    if (this._previewDebounce) clearTimeout(this._previewDebounce);
    this._undoStack = [];
    this._redoStack = [];
    this._faceCache.clear();
    this.dialog.style.display = "none";
  }
  get isOpen() {
    return this._isOpen;
  }
  setCallbacks(callbacks) {
    this.callbacks = callbacks;
  }
  // ── Frame navigation ───────────────────────────────────────
  async _selectFrame(frameIdx) {
    this.currentFrame = frameIdx;
    this.currentFaceIdx = 0;
    this._updateFrameInfo();
    this._updateFilmstripActive(frameIdx);
    await this._loadCanvasFrame();
    if (this._faceCache.has(frameIdx)) {
      this.faces = this._faceCache.get(frameIdx);
    } else {
      try {
        const resp = await api.fetchApi("/facepoke/detect_faces", {
          method: "POST",
          body: JSON.stringify({
            video_path: this.videoPath,
            frame_idx: frameIdx,
            use_blaze: this._useBlaze
          })
        });
        const data = await resp.json();
        this.faces = data.faces || [];
        this._faceCache.set(frameIdx, this.faces);
      } catch {
        this.faces = [];
      }
    }
    this._renderFaceOverlays();
    this._loadSliders();
    this.sliderTitle.textContent = `Expression Controls — Face ${this.currentFaceIdx + 1}`;
  }
  _prevFrame() {
    if (this.currentFrame > 0) this._selectFrame(this.currentFrame - 1);
  }
  _nextFrame() {
    if (this.currentFrame < this.totalFrames - 1) this._selectFrame(this.currentFrame + 1);
  }
  // ── Canvas ─────────────────────────────────────────────────
  async _loadCanvasFrame() {
    if (this._drivingId || this._refKp) {
      this._requestRefPreview();
      return;
    }
    const frameEdits = this.allEdits[String(this.currentFrame)];
    if (frameEdits && Object.keys(frameEdits).length > 0) {
      this._setStatus("Generating preview...");
      try {
        const url = await this._fetchPreview(this.currentFrame, frameEdits);
        this.canvasImg.src = url;
        this._setStatus(`Frame ${this.currentFrame + 1} — preview updated`);
      } catch {
        this._setStatus("⚠ Preview generation failed — check console");
      }
    } else if (this._showLandmarks) {
      this._setStatus("Loading landmarks...");
      try {
        const url = await this._fetchFrameWithLandmarks(this.currentFrame);
        this.canvasImg.src = url;
        this._setStatus("Drag faces or adjust sliders, then Apply Edits");
      } catch {
        const url = await this._fetchFrame(this.currentFrame);
        this.canvasImg.src = url;
        this._setStatus("⚠ Landmarks unavailable — showing raw frame");
      }
    } else {
      const url = await this._fetchFrame(this.currentFrame);
      this.canvasImg.src = url;
    }
  }
  _renderFaceOverlays() {
    this.canvasArea.querySelectorAll(".fpoke-face-overlay, .fpoke-ctrl-point").forEach((el) => el.remove());
    if (!this._showMarkers) return;
    const addOverlays = () => {
      const dw = this.canvasImg.clientWidth;
      const dh = this.canvasImg.clientHeight;
      if (!dw || !dh) return;
      const sx = dw / this.videoWidth;
      const sy = dh / this.videoHeight;
      const cr = this.canvasImg.getBoundingClientRect();
      const pr = this.canvasArea.getBoundingClientRect();
      const ox = cr.left - pr.left;
      const oy = cr.top - pr.top;
      for (const face of this.faces) {
        const [x1, y1, x2, y2] = face.bbox;
        const faceW = (x2 - x1) * sx;
        const faceH = (y2 - y1) * sy;
        const faceLeft = ox + x1 * sx;
        const faceTop = oy + y1 * sy;
        const ov = document.createElement("div");
        ov.className = "fpoke-face-overlay";
        if (face.idx === this.currentFaceIdx) ov.classList.add("active");
        ov.style.left = `${faceLeft}px`;
        ov.style.top = `${faceTop}px`;
        ov.style.width = `${faceW}px`;
        ov.style.height = `${faceH}px`;
        const lbl = document.createElement("div");
        lbl.className = "fpoke-face-label";
        lbl.textContent = `Face ${face.idx + 1}`;
        ov.appendChild(lbl);
        ov.addEventListener("click", (e) => {
          e.stopPropagation();
          this.currentFaceIdx = face.idx;
          this._renderFaceOverlays();
          this._loadSliders();
          this.sliderTitle.textContent = `Expression Controls — Face ${face.idx + 1}`;
        });
        this.canvasArea.appendChild(ov);
        if (face.idx === this.currentFaceIdx) {
          for (const cp of CONTROL_POINTS) {
            const dot = document.createElement("div");
            dot.className = "fpoke-ctrl-point";
            dot.title = cp.label;
            dot.style.left = `${faceLeft + faceW * cp.rx}px`;
            dot.style.top = `${faceTop + faceH * cp.ry}px`;
            dot.style.setProperty("--cp-color", cp.color);
            this._setupControlPointDrag(dot, face, cp);
            this.canvasArea.appendChild(dot);
          }
        }
      }
    };
    if (this.canvasImg.complete) addOverlays();
    else this.canvasImg.addEventListener("load", addOverlays, { once: true });
  }
  _setupControlPointDrag(dot, face, cp) {
    let dragging = false;
    let startX = 0, startY = 0;
    let startVals = {};
    dot.addEventListener("mousedown", (e) => {
      var _a;
      e.preventDefault();
      e.stopPropagation();
      dragging = true;
      startX = e.clientX;
      startY = e.clientY;
      dot.classList.add("active");
      const fe = ((_a = this.allEdits[String(this.currentFrame)]) == null ? void 0 : _a[String(face.idx)]) || {};
      startVals = {};
      for (const m of cp.dragMap) {
        startVals[m.key] = Number(fe[m.key] || 0);
      }
    });
    const onMove = (e) => {
      if (!dragging) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      this._ensureEdits(this.currentFrame, face.idx);
      const edits = this.allEdits[String(this.currentFrame)][String(face.idx)];
      for (const m of cp.dragMap) {
        const delta = m.axis === "x" ? dx : dy;
        const newVal = (startVals[m.key] || 0) + delta * m.sensitivity;
        edits[m.key] = Math.round(newVal * 100) / 100;
      }
      if (face.idx === this.currentFaceIdx) this._loadSliders();
      this._markThumbEdited(this.currentFrame);
      this._updateEditedCount();
      this._requestPreview();
    };
    const onUp = () => {
      if (dragging) {
        dragging = false;
        dot.classList.remove("active");
      }
    };
    dot.addEventListener("mousemove", onMove);
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }
  // ── Sliders ────────────────────────────────────────────────
  _onSliderChange() {
    this._pushUndo();
    this._ensureEdits(this.currentFrame, this.currentFaceIdx);
    for (const s of SLIDERS) {
      const input = document.getElementById(`fpoke-sl-${s.key}`);
      if (input) {
        this.allEdits[String(this.currentFrame)][String(this.currentFaceIdx)][s.key] = Number(input.value);
      }
    }
    this._markThumbEdited(this.currentFrame);
    this._updateEditedCount();
    this._setStatus("Generating preview...");
    this._requestPreview();
  }
  _loadSliders() {
    var _a;
    const fe = ((_a = this.allEdits[String(this.currentFrame)]) == null ? void 0 : _a[String(this.currentFaceIdx)]) || {};
    for (const s of SLIDERS) {
      const input = document.getElementById(`fpoke-sl-${s.key}`);
      const valEl = document.getElementById(`fpoke-sv-${s.key}`);
      if (input) {
        const val = Number(fe[s.key] ?? s.default);
        input.value = String(val);
        if (valEl) valEl.textContent = val.toFixed(s.step < 1 ? 2 : 0);
      }
    }
  }
  // ── Filmstrip ──────────────────────────────────────────────
  _buildFilmstrip() {
    this.filmstrip.innerHTML = "";
    const maxThumbs = Math.min(this.totalFrames, 150);
    const step = Math.max(1, Math.floor(this.totalFrames / maxThumbs));
    for (let i = 0; i < this.totalFrames; i += step) {
      const wrapper = document.createElement("div");
      wrapper.className = "fpoke-thumb-wrap";
      wrapper.dataset.frameIdx = String(i);
      if (i === 0) wrapper.classList.add("active");
      if (this.allEdits[String(i)]) wrapper.classList.add("edited");
      const thumb = document.createElement("img");
      thumb.className = "fpoke-thumb";
      thumb.alt = `Frame ${i + 1}`;
      thumb.width = 80;
      thumb.height = 60;
      thumb.loading = "lazy";
      this._fetchFrame(i).then((url) => {
        thumb.src = url;
      });
      const frameNum = document.createElement("span");
      frameNum.className = "fpoke-thumb-num";
      frameNum.textContent = String(i + 1);
      wrapper.append(thumb, frameNum);
      wrapper.addEventListener("click", () => this._selectFrame(i));
      this.filmstrip.appendChild(wrapper);
    }
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
  _updateFilmstripActive(frameIdx) {
    this.filmstrip.querySelectorAll(".fpoke-thumb-wrap").forEach((t) => {
      t.classList.remove("active");
      if (t.dataset.frameIdx === String(frameIdx)) {
        t.classList.add("active");
        t.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
      }
    });
  }
  _markThumbEdited(frameIdx) {
    const thumb = this.filmstrip.querySelector(`[data-frame-idx="${frameIdx}"]`);
    if (thumb) thumb.classList.add("edited");
  }
  _updateFilmstripMarkers() {
    this.filmstrip.querySelectorAll(".fpoke-thumb-wrap").forEach((t) => {
      const idx = t.dataset.frameIdx;
      if (idx && this.allEdits[idx]) {
        t.classList.add("edited");
      } else {
        t.classList.remove("edited");
      }
    });
  }
  // ── Preview ────────────────────────────────────────────────
  _requestPreview() {
    if (this._previewDebounce) clearTimeout(this._previewDebounce);
    this._previewDebounce = setTimeout(() => this._doPreview(), 50);
  }
  async _doPreview() {
    const frameEdits = this.allEdits[String(this.currentFrame)];
    if (!frameEdits) return;
    if (this._previewInFlight) return;
    this._previewInFlight = true;
    try {
      const url = await this._fetchPreview(this.currentFrame, frameEdits);
      this.canvasImg.src = url;
      this._setStatus(`Frame ${this.currentFrame + 1} — preview updated`);
    } catch (err) {
      console.warn("[FacePoke] Preview failed:", err);
      this._setStatus("⚠ Preview error — models may not be loaded");
    } finally {
      this._previewInFlight = false;
    }
  }
  // ── Actions ────────────────────────────────────────────────
  _resetFrame() {
    this._pushUndo();
    delete this.allEdits[String(this.currentFrame)];
    this._loadSliders();
    this._loadCanvasFrame();
    this._updateFilmstripMarkers();
    this._updateEditedCount();
    this._setStatus(`Frame ${this.currentFrame + 1} reset`);
  }
  _applyPreset(preset) {
    this._pushUndo();
    const fi = this.currentFrame;
    const face = this.currentFaceIdx;
    this._ensureEdits(fi, face);
    const edits = this.allEdits[String(fi)][String(face)];
    for (const key of Object.keys(edits)) {
      delete edits[key];
    }
    for (const [key, val] of Object.entries(preset.params)) {
      edits[key] = val;
    }
    this._loadSliders();
    this._updateFilmstripMarkers();
    this._updateEditedCount();
    this._requestPreview();
    this._setStatus(`Applied "${preset.label}" preset`);
  }
  // ── Undo / Redo ────────────────────────────────────────────
  _pushUndo() {
    this._undoStack.push(JSON.stringify(this.allEdits));
    if (this._undoStack.length > 50) this._undoStack.shift();
    this._redoStack = [];
  }
  _undo() {
    if (this._undoStack.length === 0) {
      this._setStatus("Nothing to undo");
      return;
    }
    this._redoStack.push(JSON.stringify(this.allEdits));
    this.allEdits = JSON.parse(this._undoStack.pop());
    this._loadSliders();
    this._loadCanvasFrame();
    this._updateFilmstripMarkers();
    this._updateEditedCount();
    this._setStatus("Undo applied");
  }
  _redo() {
    if (this._redoStack.length === 0) {
      this._setStatus("Nothing to redo");
      return;
    }
    this._undoStack.push(JSON.stringify(this.allEdits));
    this.allEdits = JSON.parse(this._redoStack.pop());
    this._loadSliders();
    this._loadCanvasFrame();
    this._updateFilmstripMarkers();
    this._updateEditedCount();
    this._setStatus("Redo applied");
  }
  // ── Keyframe Interpolation ─────────────────────────────────
  _interpolateFrames() {
    var _a, _b;
    const keyframeIndices = Object.keys(this.allEdits).map(Number).filter((k) => !isNaN(k) && this.allEdits[String(k)] && Object.keys(this.allEdits[String(k)]).length > 0).sort((a, b) => a - b);
    if (keyframeIndices.length < 2) {
      this._setStatus("⚠ Need at least 2 edited frames to interpolate");
      return;
    }
    const smoothstep = (t) => t * t * (3 - 2 * t);
    const paramKeys = [
      "rotate_pitch",
      "rotate_yaw",
      "rotate_roll",
      "blink",
      "blink_left",
      "blink_right",
      "eyebrow",
      "eyebrow_left",
      "eyebrow_right",
      "wink",
      "pupil_x",
      "pupil_y",
      "aaa",
      "eee",
      "woo",
      "smile"
    ];
    let generated = 0;
    const allFaceIndices = /* @__PURE__ */ new Set();
    for (const ki of keyframeIndices) {
      for (const fi of Object.keys(this.allEdits[String(ki)])) {
        allFaceIndices.add(fi);
      }
    }
    for (let i = 0; i < keyframeIndices.length - 1; i++) {
      const fA = keyframeIndices[i];
      const fB = keyframeIndices[i + 1];
      const span = fB - fA;
      if (span <= 1) continue;
      for (let frame = fA + 1; frame < fB; frame++) {
        const t = smoothstep((frame - fA) / span);
        if (!this.allEdits[String(frame)]) this.allEdits[String(frame)] = {};
        for (const faceIdx of allFaceIndices) {
          const paramsA = ((_a = this.allEdits[String(fA)]) == null ? void 0 : _a[faceIdx]) || {};
          const paramsB = ((_b = this.allEdits[String(fB)]) == null ? void 0 : _b[faceIdx]) || {};
          if (!this.allEdits[String(frame)][faceIdx]) {
            this.allEdits[String(frame)][faceIdx] = {};
          }
          for (const key of paramKeys) {
            const vA = Number(paramsA[key] || 0);
            const vB = Number(paramsB[key] || 0);
            if (vA === 0 && vB === 0) continue;
            const interpolated = vA + (vB - vA) * t;
            this.allEdits[String(frame)][faceIdx][key] = Math.round(interpolated * 1e3) / 1e3;
          }
        }
        generated++;
      }
    }
    this._updateFilmstripMarkers();
    this._updateEditedCount();
    this._loadCanvasFrame();
    this._setStatus(`Interpolated ${generated} frames between ${keyframeIndices.length} keyframes`);
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
    this._playing = true;
    const btn = document.getElementById("fpoke-play-btn");
    if (btn) {
      btn.innerHTML = `${fpIconPause} Pause`;
      btn.classList.add("active");
    }
    this._setStatus("Playing...");
    this._playStep();
  }
  _stopPlayback() {
    this._playing = false;
    if (this._playTimer) {
      clearTimeout(this._playTimer);
      this._playTimer = null;
    }
    const btn = document.getElementById("fpoke-play-btn");
    if (btn) {
      btn.innerHTML = `${fpIconPlay} Play`;
      btn.classList.remove("active");
    }
    this._setStatus(`Paused at frame ${this.currentFrame + 1}`);
  }
  async _playStep() {
    if (!this._playing) return;
    const frameIdx = this.currentFrame;
    this._updateFrameInfo();
    this._updateFilmstripActive(frameIdx);
    try {
      const frameEdits = this.allEdits[String(frameIdx)];
      let url;
      if (frameEdits && Object.keys(frameEdits).length > 0) {
        url = await this._fetchPreview(frameIdx, frameEdits);
      } else {
        url = await this._fetchFrame(frameIdx);
      }
      if (!this._playing) return;
      this.canvasImg.src = url;
      this._setStatus(`Playing — Frame ${frameIdx + 1} / ${this.totalFrames}`);
    } catch {
    }
    const nextFrame = frameIdx + 1;
    if (nextFrame >= this.totalFrames) {
      this._stopPlayback();
      this._setStatus("Playback complete");
      return;
    }
    this.currentFrame = nextFrame;
    const delay = Math.max(1e3 / this.videoFps, 30);
    this._playTimer = setTimeout(() => this._playStep(), delay);
  }
  _apply() {
    const clean = {};
    for (const [fi, fe] of Object.entries(this.allEdits)) {
      const cf = {};
      for (const [face, params] of Object.entries(fe)) {
        const nz = Object.entries(params).filter(([, v]) => v !== 0);
        if (nz.length) cf[face] = Object.fromEntries(nz);
      }
      if (Object.keys(cf).length) clean[fi] = cf;
    }
    this.close();
    this.callbacks.onApply(clean);
  }
  _cancel() {
    this.close();
    this.callbacks.onCancel();
  }
  _passthrough() {
    this.close();
    this.callbacks.onApply({});
  }
  // ── Helpers ─────────────────────────────────────────────────
  _ensureEdits(fi, face) {
    if (!this.allEdits[String(fi)]) this.allEdits[String(fi)] = {};
    if (!this.allEdits[String(fi)][String(face)]) this.allEdits[String(fi)][String(face)] = {};
  }
  _updateFrameInfo() {
    const el = document.getElementById("fpoke-frame-info");
    if (el) {
      el.textContent = `Frame ${this.currentFrame + 1} / ${this.totalFrames} · ${this.videoWidth}×${this.videoHeight} · ${this.videoFps.toFixed(1)} FPS`;
    }
  }
  _updateEditedCount() {
    const el = document.getElementById("fpoke-edited-count");
    const count = Object.keys(this.allEdits).filter(
      (k) => this.allEdits[k] && Object.keys(this.allEdits[k]).length > 0
    ).length;
    if (el) el.textContent = `${count} frame${count !== 1 ? "s" : ""} edited`;
  }
  // ── Reference Image Methods ─────────────────────────────────────
  async _loadRefImage(dataUrl) {
    this._setStatus("Extracting reference expression...");
    try {
      const resp = await api.fetchApi("/facepoke/extract_ref_expression", {
        method: "POST",
        body: JSON.stringify({
          image_data: dataUrl,
          crop_factor: 1.6
        })
      });
      const data = await resp.json();
      if (data.error) {
        this._setStatus(`Reference error: ${data.error}`);
        return;
      }
      this._refKp = data.ref_kp;
      const info = document.getElementById("fpoke-ref-info");
      if (info) info.textContent = "Reference loaded";
      this._setStatus("Reference expression extracted — preview updating");
      this._requestRefPreview();
    } catch (e) {
      this._setStatus(`Reference extraction failed: ${e}`);
    }
  }
  async _uploadDrivingVideo(file) {
    this._setStatus("Uploading driving video...");
    try {
      const formData = new FormData();
      formData.append("image", file, file.name);
      formData.append("subfolder", "facepoke_driving");
      formData.append("type", "input");
      const uploadResp = await api.fetchApi("/upload/image", {
        method: "POST",
        body: formData
      });
      const uploadData = await uploadResp.json();
      if (!uploadData.name) {
        this._setStatus("Driving video upload failed");
        return;
      }
      const uploadedPath = uploadData.subfolder ? `${uploadData.subfolder}/${uploadData.name}` : uploadData.name;
      this._setStatus("Extracting driving keypoints... This may take a moment.");
      const info = document.getElementById("fpoke-drv-info");
      if (info) info.textContent = "Extracting...";
      const resp = await api.fetchApi("/facepoke/extract_driving", {
        method: "POST",
        body: JSON.stringify({
          video_path: uploadedPath,
          crop_factor: 1.6
        })
      });
      const data = await resp.json();
      if (data.error) {
        this._setStatus(`Driving extraction error: ${data.error}`);
        if (info) info.textContent = "Extraction failed";
        return;
      }
      this._drivingId = data.driving_id;
      this._drivingTotalFrames = data.total_frames;
      if (info) info.textContent = `${data.total_frames} frames (${data.faces_found} faces)`;
      this._setStatus(`Driving video loaded: ${data.total_frames} frames`);
      this._requestRefPreview();
    } catch (e) {
      this._setStatus(`Driving video upload failed: ${e}`);
    }
  }
  _requestRefPreview() {
    if (this._previewDebounce) clearTimeout(this._previewDebounce);
    this._previewDebounce = setTimeout(async () => {
      var _a;
      if (this._previewInFlight) return;
      this._previewInFlight = true;
      this._setStatus("Generating reference preview...");
      try {
        const frameKey = String(this.currentFrame);
        const faceKey = String(this.currentFaceIdx);
        const sliderEdits = ((_a = this.allEdits[frameKey]) == null ? void 0 : _a[faceKey]) ?? null;
        const cachedFaces = this._faceCache.get(this.currentFrame);
        const cachedBboxes = (cachedFaces == null ? void 0 : cachedFaces.map((f) => f.bbox)) ?? null;
        const body = {
          video_path: this.videoPath,
          frame_idx: this.currentFrame,
          face_idx: this.currentFaceIdx,
          use_blaze: this._useBlaze,
          cached_bboxes: cachedBboxes
        };
        if (this._drivingId) {
          const drvFrame = Math.min(
            this.currentFrame,
            this._drivingTotalFrames - 1
          );
          body.driving_id = this._drivingId;
          body.driving_frame = drvFrame;
          body.multiplier = this._drivingMultiplier;
        }
        if (this._refKp) {
          body.ref_kp = this._refKp;
          body.ratio = this._refRatio;
          body.parts = this._refParts;
        }
        if (sliderEdits && Object.keys(sliderEdits).length > 0) {
          body.slider_edits = sliderEdits;
        }
        const resp = await api.fetchApi("/facepoke/apply_ref_preview", {
          method: "POST",
          body: JSON.stringify(body)
        });
        if (!resp.ok) {
          const errText = await resp.text();
          throw new Error(`Preview API error ${resp.status}: ${errText}`);
        }
        const blob = await resp.blob();
        this.canvasImg.src = URL.createObjectURL(blob);
        this._setStatus(`Frame ${this.currentFrame + 1} — reference preview`);
      } catch (e) {
        this._setStatus(`Reference preview failed: ${e}`);
      } finally {
        this._previewInFlight = false;
      }
    }, 200);
  }
  async _applyDrivingToAll() {
    if (!this._drivingId) {
      this._setStatus("No driving video loaded");
      return;
    }
    this._pushUndo();
    const maxFrame = Math.min(this.totalFrames, this._drivingTotalFrames);
    for (let i = 0; i < maxFrame; i++) {
      const key = String(i);
      if (!this.allEdits[key]) this.allEdits[key] = {};
      const faceKey = String(this.currentFaceIdx);
      if (!this.allEdits[key][faceKey]) this.allEdits[key][faceKey] = {};
      this.allEdits[key][faceKey]._driving_id = this._drivingId;
      this.allEdits[key][faceKey]._driving_frame = i;
      this.allEdits[key][faceKey]._driving_multiplier = this._drivingMultiplier;
    }
    this._updateEditedCount();
    this._updateFilmstripMarkers();
    this._setStatus(`Applied driving motion to ${maxFrame} frames`);
    this._requestRefPreview();
  }
  _setStatus(msg) {
    this.statusEl.textContent = msg;
  }
  _makeBtn(html, cls, onClick) {
    const btn = document.createElement("button");
    btn.className = `fpoke-btn ${cls}`;
    btn.innerHTML = html;
    btn.addEventListener("click", onClick);
    btn.onpointerdown = (e) => e.stopPropagation();
    return btn;
  }
  // ── API calls ──────────────────────────────────────────────
  async _fetchFrame(idx) {
    const resp = await api.fetchApi("/facepoke/get_frame", {
      method: "POST",
      body: JSON.stringify({ video_path: this.videoPath, frame_idx: idx })
    });
    const blob = await resp.blob();
    return URL.createObjectURL(blob);
  }
  async _fetchPreview(idx, edits) {
    const cachedFaces = this._faceCache.get(idx);
    const cachedBboxes = (cachedFaces == null ? void 0 : cachedFaces.map((f) => f.bbox)) ?? null;
    const resp = await api.fetchApi("/facepoke/preview", {
      method: "POST",
      body: JSON.stringify({
        video_path: this.videoPath,
        frame_idx: idx,
        face_edits: edits,
        use_blaze: this._useBlaze,
        cached_bboxes: cachedBboxes
      })
    });
    if (!resp.ok) {
      const errText = await resp.text();
      throw new Error(`Preview API error ${resp.status}: ${errText}`);
    }
    const blob = await resp.blob();
    return URL.createObjectURL(blob);
  }
  async _fetchFrameWithLandmarks(idx) {
    const resp = await api.fetchApi("/facepoke/get_frame_with_landmarks", {
      method: "POST",
      body: JSON.stringify({
        video_path: this.videoPath,
        frame_idx: idx,
        selected_face: this.currentFaceIdx
      })
    });
    if (!resp.ok) {
      throw new Error(`Landmark API error: ${resp.status}`);
    }
    const blob = await resp.blob();
    return URL.createObjectURL(blob);
  }
}
const facepokeCSS = `/* ═══════════════════════════════════════════════════════════════════
 * Face Poke Editor (FFMPEGA)
 *
 * Shares design tokens with the Video Editor (--ve-*) for consistency.
 * Layout: full-viewport modal with CSS Grid for the editing workspace.
 * ═══════════════════════════════════════════════════════════════════ */

/* ── Modal Backdrop ──────────────────────────────────────────────── */

.fpoke-backdrop {
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

/* ── Panel (CSS Grid) ────────────────────────────────────────────── */

.fpoke-panel {
    background: linear-gradient(160deg, #161625 0%, #0f0f1a 100%);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
    width: 92vw;
    height: 90vh;

    display: grid;
    grid-template-areas:
        "header    header"
        "canvas    sliders"
        "filmstrip sliders"
        "toolbar   toolbar";
    grid-template-columns: 1fr 320px;
    grid-template-rows: auto 1fr auto auto;

    box-shadow:
        0 0 60px rgba(0, 0, 0, 0.5),
        0 0 120px rgba(99, 102, 241, 0.05);
    overflow: hidden;
}

/* ── Header ──────────────────────────────────────────────────────── */

.fpoke-header {
    grid-area: header;
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 10px 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(28, 28, 48, 0.75);
    backdrop-filter: blur(12px);
}

.fpoke-title {
    margin: 0;
    font-size: 15px;
    font-weight: 700;
    color: #fff;
    letter-spacing: 0.3px;
    white-space: nowrap;
}

.fpoke-frame-info {
    flex: 1;
    font-size: 12px;
    color: #9898b0;
    font-variant-numeric: tabular-nums;
}

.fpoke-header-actions {
    display: flex;
    align-items: center;
    gap: 6px;
}

.fpoke-blaze-row {
    grid-column: 1 / -1;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 0 4px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
}

.fpoke-btn-blaze {
    font-size: 11px;
    opacity: 0.7;
}

.fpoke-btn-blaze.active {
    opacity: 1;
    background: rgba(251, 191, 36, 0.15);
    border-color: #fbbf24;
    color: #fbbf24;
}

.fpoke-close {
    background: none;
    border: 1px solid transparent;
    color: #9898b0;
    font-size: 16px;
    padding: 4px 8px;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.15s ease;
}

.fpoke-close:hover {
    background: rgba(239, 68, 68, 0.15);
    border-color: #ef4444;
    color: #ef4444;
}

/* ── Canvas Area ─────────────────────────────────────────────────── */

.fpoke-canvas-area {
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

.fpoke-canvas {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    cursor: crosshair;
    user-select: none;
}

/* ── Face Overlays ───────────────────────────────────────────────── */

.fpoke-face-overlay {
    position: absolute;
    border: 2px solid rgba(99, 102, 241, 0.6);
    border-radius: 8px;
    cursor: grab;
    transition: all 0.2s ease;
    z-index: 10;
    background: rgba(99, 102, 241, 0.05);
}

.fpoke-face-overlay:hover {
    border-color: #818cf8;
    background: rgba(99, 102, 241, 0.12);
    box-shadow: 0 0 20px rgba(99, 102, 241, 0.3);
}

.fpoke-face-overlay.active {
    border-color: #6366f1;
    border-width: 2px;
    border-style: solid;
    background: rgba(99, 102, 241, 0.15);
    box-shadow:
        0 0 20px rgba(99, 102, 241, 0.35),
        0 0 40px rgba(99, 102, 241, 0.15),
        inset 0 0 20px rgba(99, 102, 241, 0.08);
    animation: fpoke-pulse 2s ease-in-out infinite;
}

@keyframes fpoke-pulse {
    0%, 100% { box-shadow: 0 0 20px rgba(99, 102, 241, 0.35), 0 0 40px rgba(99, 102, 241, 0.15); }
    50% { box-shadow: 0 0 30px rgba(99, 102, 241, 0.5), 0 0 60px rgba(99, 102, 241, 0.25); }
}

.fpoke-face-label {
    position: absolute;
    top: -22px;
    left: 4px;
    font-size: 10px;
    font-weight: 600;
    color: #fff;
    background: rgba(99, 102, 241, 0.85);
    padding: 2px 8px;
    border-radius: 4px;
    pointer-events: none;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
    letter-spacing: 0.3px;
}

/* ── Draggable Control Points ────────────────────────────────────── */

.fpoke-ctrl-point {
    position: absolute;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--cp-color, #7c6aef);
    border: 2px solid rgba(255, 255, 255, 0.8);
    cursor: grab;
    z-index: 20;
    transform: translate(-50%, -50%);
    transition: all 0.15s ease;
    box-shadow:
        0 0 8px color-mix(in srgb, var(--cp-color, #7c6aef) 60%, transparent),
        0 0 16px color-mix(in srgb, var(--cp-color, #7c6aef) 30%, transparent);
}

.fpoke-ctrl-point:hover {
    width: 20px;
    height: 20px;
    box-shadow:
        0 0 12px color-mix(in srgb, var(--cp-color, #7c6aef) 80%, transparent),
        0 0 24px color-mix(in srgb, var(--cp-color, #7c6aef) 40%, transparent);
}

.fpoke-ctrl-point:hover::after {
    content: attr(title);
    position: absolute;
    top: -24px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 10px;
    font-weight: 600;
    color: #fff;
    background: rgba(0, 0, 0, 0.8);
    padding: 2px 6px;
    border-radius: 3px;
    white-space: nowrap;
    pointer-events: none;
}

.fpoke-ctrl-point.active {
    cursor: grabbing;
    width: 22px;
    height: 22px;
    border-color: #fff;
    box-shadow:
        0 0 16px color-mix(in srgb, var(--cp-color, #7c6aef) 90%, transparent),
        0 0 32px color-mix(in srgb, var(--cp-color, #7c6aef) 50%, transparent),
        0 0 48px color-mix(in srgb, var(--cp-color, #7c6aef) 25%, transparent);
}

/* ── Landmark toggle button ──────────────────────────────────────── */

.fpoke-btn-landmark {
    background: transparent;
    border-color: rgba(255, 255, 255, 0.15);
    color: #9898b0;
}

.fpoke-btn-landmark:hover {
    background: rgba(99, 102, 241, 0.1);
    border-color: #6366f1;
    color: #e8e8f0;
}

.fpoke-btn-landmark.active {
    background: rgba(99, 102, 241, 0.2);
    border-color: #6366f1;
    color: #818cf8;
    box-shadow: 0 0 12px rgba(99, 102, 241, 0.25);
}

/* ── Play button ─────────────────────────────────────────────────── */

.fpoke-btn-play {
    background: transparent;
    border-color: rgba(34, 197, 94, 0.3);
    color: #4ade80;
}

.fpoke-btn-play:hover {
    background: rgba(34, 197, 94, 0.1);
    border-color: #22c55e;
}

.fpoke-btn-play.active {
    background: rgba(34, 197, 94, 0.2);
    border-color: #22c55e;
    color: #4ade80;
    box-shadow: 0 0 12px rgba(34, 197, 94, 0.3);
    animation: fpoke-pulse-play 1.5s ease-in-out infinite;
}

@keyframes fpoke-pulse-play {
    0%, 100% { box-shadow: 0 0 12px rgba(34, 197, 94, 0.3); }
    50% { box-shadow: 0 0 20px rgba(34, 197, 94, 0.5); }
}

/* ── Interpolate button ──────────────────────────────────────────── */

.fpoke-btn-interp {
    background: rgba(168, 85, 247, 0.1);
    border-color: rgba(168, 85, 247, 0.3);
    color: #c084fc;
}

.fpoke-btn-interp:hover {
    background: rgba(168, 85, 247, 0.2);
    border-color: #a855f7;
    color: #d8b4fe;
    box-shadow: 0 0 12px rgba(168, 85, 247, 0.25);
}

/* ── Slider Panel (sidebar) ──────────────────────────────────────── */

.fpoke-sliders {
    grid-area: sliders;
    display: flex;
    flex-direction: column;
    overflow-y: auto;
    padding: 12px;
    border-left: 1px solid rgba(255, 255, 255, 0.06);
    background: rgba(28, 28, 48, 0.6);
    min-height: 0;
}

/* ── Emotion Presets ─────────────────────────────────────────────── */

.fpoke-preset-section {
    padding: 10px 0 6px;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
    margin-top: 8px;
}

.fpoke-preset-label {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #8888aa;
    margin-bottom: 8px;
}

.fpoke-preset-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
}

.fpoke-preset-chip {
    font-size: 11px;
    padding: 4px 10px;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 14px;
    background: rgba(40, 40, 70, 0.6);
    color: #c8c8e0;
    cursor: pointer;
    transition: all 0.2s;
    white-space: nowrap;
}

.fpoke-preset-chip:hover {
    background: rgba(99, 102, 241, 0.2);
    border-color: rgba(99, 102, 241, 0.4);
    color: #e8e8f0;
    box-shadow: 0 0 10px rgba(99, 102, 241, 0.2);
    transform: translateY(-1px);
}

.fpoke-preset-chip:active {
    transform: scale(0.95);
    background: rgba(99, 102, 241, 0.3);
}

/* ── Reference / Driving Sections ── */
.fpoke-ref-section {
    padding: 10px 0 6px 0;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
    margin-top: 8px;
}

.fpoke-select {
    font-size: 11px;
    padding: 4px 8px;
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 6px;
    background: rgba(30, 30, 55, 0.8);
    color: #c8c8e0;
    cursor: pointer;
    outline: none;
}
.fpoke-select:focus {
    border-color: rgba(99, 102, 241, 0.5);
}

.fpoke-slider-title {
    font-size: 11px;
    font-weight: 600;
    color: #9898b0;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.fpoke-slider-group {
    display: flex;
    flex-direction: column;
    gap: 4px;
    flex: 1;
}

.fpoke-slider-row {
    display: flex;
    align-items: center;
    gap: 8px;
}

.fpoke-slider-label {
    font-size: 11px;
    color: #9898b0;
    min-width: 72px;
    white-space: nowrap;
}

.fpoke-slider-input {
    flex: 1;
    height: 4px;
    -webkit-appearance: none;
    appearance: none;
    background: rgba(255, 255, 255, 0.06);
    border-radius: 2px;
    outline: none;
    cursor: pointer;
}

.fpoke-slider-input::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: #6366f1;
    cursor: pointer;
    border: none;
    transition: transform 0.1s;
}

.fpoke-slider-input::-webkit-slider-thumb:hover {
    transform: scale(1.2);
}

.fpoke-slider-input::-moz-range-thumb {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: #6366f1;
    cursor: pointer;
    border: none;
}

.fpoke-slider-value {
    font-size: 11px;
    color: #e8e8f0;
    min-width: 42px;
    text-align: right;
    font-variant-numeric: tabular-nums;
}

/* Scrollbar */
.fpoke-sliders::-webkit-scrollbar { width: 6px; }
.fpoke-sliders::-webkit-scrollbar-track { background: transparent; }
.fpoke-sliders::-webkit-scrollbar-thumb { background: #2a2a45; border-radius: 3px; }

/* ── Filmstrip ───────────────────────────────────────────────────── */

.fpoke-filmstrip {
    grid-area: filmstrip;
    display: flex;
    gap: 2px;
    padding: 8px 12px;
    overflow-x: auto;
    overflow-y: hidden;
    background: rgba(15, 15, 26, 0.9);
    border-top: 1px solid rgba(255, 255, 255, 0.06);
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    scrollbar-width: thin;
    scrollbar-color: #2a2a45 transparent;
    max-height: 90px;
}

.fpoke-filmstrip::-webkit-scrollbar { height: 6px; }
.fpoke-filmstrip::-webkit-scrollbar-track { background: transparent; }
.fpoke-filmstrip::-webkit-scrollbar-thumb { background: #2a2a45; border-radius: 3px; }

.fpoke-thumb-wrap {
    position: relative;
    flex-shrink: 0;
    width: 80px;
    height: 60px;
    border-radius: 4px;
    border: 2px solid transparent;
    cursor: pointer;
    opacity: 0.6;
    transition: all 0.15s ease;
    overflow: hidden;
}

.fpoke-thumb {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
}

.fpoke-thumb-num {
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

.fpoke-thumb-wrap:hover {
    opacity: 0.9;
    border-color: rgba(255, 255, 255, 0.2);
}

.fpoke-thumb-wrap.active {
    opacity: 1;
    border-color: #6366f1;
    box-shadow: 0 0 12px rgba(99, 102, 241, 0.3);
}

.fpoke-thumb-wrap.edited {
    border-color: #22c55e;
    opacity: 0.85;
}

.fpoke-thumb-wrap.edited.active {
    border-color: #6366f1;
    opacity: 1;
    box-shadow: 0 0 12px rgba(99, 102, 241, 0.3),
                inset 0 0 0 1px #22c55e;
}

/* ── Toolbar ─────────────────────────────────────────────────────── */

.fpoke-toolbar {
    grid-area: toolbar;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 16px;
    background: rgba(28, 28, 48, 0.75);
    backdrop-filter: blur(12px);
    border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.fpoke-status {
    font-size: 12px;
    color: #9898b0;
}

.fpoke-nav-btns {
    display: flex;
    align-items: center;
    gap: 6px;
}

.fpoke-edited-count {
    font-size: 11px;
    color: #22c55e;
    font-weight: 600;
    margin-left: 12px;
}

/* ── Buttons ─────────────────────────────────────────────────────── */

.fpoke-btn {
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

.fpoke-btn:hover {
    background: #3a3a55;
    border-color: rgba(255, 255, 255, 0.12);
}

.fpoke-btn:active { transform: scale(0.97); }

.fpoke-btn-sm { padding: 3px 8px; font-size: 11px; }

.fpoke-btn-apply {
    background: #22c55e;
    border-color: transparent;
    color: #fff;
    font-weight: 600;
}

.fpoke-btn-apply:hover {
    background: #4ade80;
    box-shadow: 0 0 16px rgba(34, 197, 94, 0.25);
}

.fpoke-btn-reset {
    background: transparent;
    border-color: #ef4444;
    color: #ef4444;
}

.fpoke-btn-reset:hover {
    background: rgba(239, 68, 68, 0.1);
    color: #f87171;
}

.fpoke-btn-pass {
    background: transparent;
    border-color: #6366f1;
    color: #6366f1;
}

.fpoke-btn-pass:hover {
    background: rgba(99, 102, 241, 0.1);
}

/* ── Responsive ──────────────────────────────────────────────────── */

@media (max-width: 1024px) {
    .fpoke-panel {
        grid-template-areas:
            "header"
            "canvas"
            "sliders"
            "filmstrip"
            "toolbar";
        grid-template-columns: 1fr;
        grid-template-rows: auto 1fr auto auto auto;
        width: 98vw;
        height: 95vh;
    }

    .fpoke-sliders {
        border-left: none;
        border-top: 1px solid rgba(255, 255, 255, 0.06);
        max-height: 200px;
    }
}
`;
if (!document.querySelector("#fpoke-styles")) {
  const style = document.createElement("style");
  style.id = "fpoke-styles";
  style.textContent = facepokeCSS;
  document.head.appendChild(style);
}
const NODE_TYPE = "FFMPEGAFacePoke";
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
    _sharedModal = new FacePokeModal({
      onApply: () => {
      },
      onCancel: () => {
      }
    });
  }
  return _sharedModal;
}
app.registerExtension({
  name: "ffmpega.facepoke",
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
  node.color = "#2a3a5a";
  node.bgcolor = "#1a2a4a";
  _ensureHiddenWidgets(node);
  let currentVideoPath = "";
  let lastEdits = {};
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
    uploadBtn.style.outline = isFocused ? "2px solid #4a6a8a" : "none";
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
  videoEl.setAttribute("aria-label", "FacePoke video preview");
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
  editorBtn.innerHTML = "🎭 Open Face Editor";
  editorBtn.setAttribute("aria-label", "Open Face Poke Editor");
  editorBtn.style.cssText = `
        width: 100%;
        margin-top: 4px;
        background: linear-gradient(135deg, #2a3a5a, #1a2a4a);
        color: #e8e8f0;
        border: 1px solid #4a6a8a;
        border-radius: 4px;
        padding: 8px;
        cursor: pointer;
        font-family: 'Inter', system-ui, sans-serif;
        font-size: 13px;
        font-weight: 600;
        transition: all 0.2s;
    `;
  editorBtn.onmouseenter = () => {
    editorBtn.style.background = "linear-gradient(135deg, #3a4a6a, #2a3a5a)";
    editorBtn.style.borderColor = "#6a8aaa";
  };
  editorBtn.onmouseleave = () => {
    editorBtn.style.background = "linear-gradient(135deg, #2a3a5a, #1a2a4a)";
    editorBtn.style.borderColor = "#4a6a8a";
  };
  editorBtn.onpointerdown = (e) => e.stopPropagation();
  editorBtn.onclick = () => {
    if (!currentVideoPath) {
      console.warn("[FacePoke] No video path set — upload or connect a video first");
      infoEl.textContent = "⚠ No video loaded — upload or connect one first";
      infoEl.style.color = "#ef4444";
      setTimeout(() => {
        infoEl.style.color = "#aaa";
      }, 3e3);
      return;
    }
    console.log("[FacePoke] Opening editor with path:", currentVideoPath);
    openEditor();
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
      console.warn("[FacePoke] Upload error:", e);
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
        uploadBtn.style.border = "1px dashed #4a6a8a";
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
    if ((_b = data == null ? void 0 : data.facepoke_meta) == null ? void 0 : _b[0]) {
      const fpMeta = data.facepoke_meta[0];
      currentVideoPath = fpMeta.video_path;
      loadPreview(fpMeta.video_path);
      resizeNode();
      try {
        lastEdits = fpMeta.edit_data ? JSON.parse(fpMeta.edit_data) : {};
      } catch {
        lastEdits = {};
      }
      const autoW = (_c = node.widgets) == null ? void 0 : _c.find((w) => w.name === "auto_open_editor");
      if ((autoW == null ? void 0 : autoW.value) && !getModal().isOpen) {
        console.log("[FacePoke] Auto-opening editor (workflow paused)");
        openEditor();
      }
    }
  };
  function openEditor() {
    const modal = getModal();
    const nodeId = String(node.id);
    modal.setCallbacks({
      onApply: async (edits) => {
        lastEdits = edits;
        if (Object.keys(edits).length === 0) {
          _setW(node, "_edit_action", "passthrough");
          app.queuePrompt(0, 1).finally(() => _setW(node, "_edit_action", "none"));
          return;
        }
        try {
          await api.fetchApi("/facepoke/apply_edits", {
            method: "POST",
            body: JSON.stringify({ node_id: nodeId, edits })
          });
        } catch (e) {
          console.error("[FacePoke] Failed to store edits:", e);
        }
        _setW(node, "_edit_action", "apply");
        app.queuePrompt(0, 1).finally(() => _setW(node, "_edit_action", "none"));
      },
      onCancel: () => {
      }
    });
    modal.open(currentVideoPath, lastEdits);
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
