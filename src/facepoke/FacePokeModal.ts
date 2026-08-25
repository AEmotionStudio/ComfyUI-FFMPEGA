/**
 * FacePokeModal.ts — Modal for per-frame face expression editing.
 *
 * Layout (CSS Grid):
 *   header    | header
 *   canvas    | sliders
 *   filmstrip | sliders
 *   toolbar   | toolbar
 *
 * Follows the same patterns as EditorModal (Video Editor):
 * - Singleton shared across all FacePoke nodes
 * - open(videoPath, edits) / close() lifecycle
 * - Apply → callback → re-queue | Cancel → close
 * - ESC to cancel, keyboard shortcuts
 */

import { api } from "comfyui/api";
import {
    fpIconPlay, fpIconPause, fpIconSkipStart, fpIconSkipEnd,
    fpIconPrev, fpIconNext, fpIconUndo, fpIconRedo, fpIconCheck,
    fpIconClose, fpIconReset, fpIconEye, fpIconEyeOff,
    fpIconLandmarks, fpIconFace, fpIconInterpolate, fpIconPassThrough,
    fpIconScanFace, fpIconUpload, fpIconVideo, fpIconImage, fpIconRemove,
} from "./icons";

// ── Types ──────────────────────────────────────────────────

interface FaceInfo {
    idx: number;
    bbox: [number, number, number, number];
    center: [number, number];
}

interface FaceEditParams {
    rotate_pitch?: number;
    rotate_yaw?: number;
    rotate_roll?: number;
    blink?: number;
    blink_left?: number;
    blink_right?: number;
    eyebrow?: number;
    eyebrow_left?: number;
    eyebrow_right?: number;
    wink?: number;
    pupil_x?: number;
    pupil_y?: number;
    aaa?: number;
    eee?: number;
    woo?: number;
    smile?: number;
}

interface FrameEdits {
    [faceIdx: string]: FaceEditParams;
}

export interface AllEdits {
    [frameIdx: string]: FrameEdits;
}

export interface FacePokeCallbacks {
    onApply: (edits: AllEdits) => void;
    onCancel: () => void;
}

// ── Expression slider definitions ──────────────────────────

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
    { key: "smile", label: "Smile", min: -0.3, max: 1.3, step: 0.01, default: 0 },
] as const;

// ── Draggable control point definitions ────────────────────
// Positions are proportional offsets within the face bbox (0–1).
// dragMap entries: [param_key, axis ("x"|"y"), sensitivity].

interface ControlPointDef {
    id: string;
    label: string;
    /** Proportional X offset in face bbox (0=left, 1=right) */
    rx: number;
    /** Proportional Y offset in face bbox (0=top, 1=bottom) */
    ry: number;
    color: string;
    /** Maps drag axes to expression params */
    dragMap: Array<{ key: keyof FaceEditParams; axis: "x" | "y"; sensitivity: number }>;
}

const CONTROL_POINTS: ControlPointDef[] = [
    {
        id: "forehead", label: "Pitch", rx: 0.5, ry: 0.1, color: "#7c6aef",
        dragMap: [{ key: "rotate_pitch", axis: "y", sensitivity: -0.2 }],
    },
    {
        id: "left-eyebrow", label: "L Eyebrow", rx: 0.32, ry: 0.22, color: "#2ec4b6",
        dragMap: [{ key: "eyebrow_left", axis: "y", sensitivity: -0.15 }],
    },
    {
        id: "right-eyebrow", label: "R Eyebrow", rx: 0.68, ry: 0.22, color: "#2ec4b6",
        dragMap: [{ key: "eyebrow_right", axis: "y", sensitivity: -0.15 }],
    },
    {
        id: "left-eye", label: "Eye L", rx: 0.32, ry: 0.38, color: "#5bc0be",
        dragMap: [
            { key: "pupil_x", axis: "x", sensitivity: 0.1 },
            { key: "pupil_y", axis: "y", sensitivity: 0.1 },
            { key: "blink_left", axis: "y", sensitivity: -0.15 },
        ],
    },
    {
        id: "right-eye", label: "Eye R", rx: 0.68, ry: 0.38, color: "#5bc0be",
        dragMap: [
            { key: "pupil_x", axis: "x", sensitivity: 0.1 },
            { key: "pupil_y", axis: "y", sensitivity: 0.1 },
            { key: "blink_right", axis: "y", sensitivity: -0.15 },
        ],
    },
    {
        id: "wink", label: "Wink", rx: 0.15, ry: 0.38, color: "#264653",
        dragMap: [{ key: "wink", axis: "y", sensitivity: -0.15 }],
    },
    {
        id: "left-cheek", label: "Yaw", rx: 0.08, ry: 0.5, color: "#f4a261",
        dragMap: [{ key: "rotate_yaw", axis: "x", sensitivity: 0.2 }],
    },
    {
        id: "right-cheek", label: "Yaw", rx: 0.92, ry: 0.5, color: "#f4a261",
        dragMap: [{ key: "rotate_yaw", axis: "x", sensitivity: 0.2 }],
    },
    {
        id: "nose-roll", label: "Roll", rx: 0.5, ry: 0.52, color: "#e9c46a",
        dragMap: [{ key: "rotate_roll", axis: "x", sensitivity: 0.2 }],
    },
    {
        id: "mouth", label: "Mouth", rx: 0.5, ry: 0.72, color: "#e76f51",
        dragMap: [
            { key: "smile", axis: "y", sensitivity: -0.008 },
            { key: "aaa", axis: "y", sensitivity: 0.3 },
        ],
    },
    {
        id: "chin", label: "Tilt", rx: 0.5, ry: 0.95, color: "#9b5de5",
        dragMap: [{ key: "rotate_pitch", axis: "y", sensitivity: 0.2 }],
    },
];

// ── Emotion presets ────────────────────────────────────────

interface EmotionPreset {
    label: string;
    params: Partial<FaceEditParams>;
}

const EMOTION_PRESETS: EmotionPreset[] = [
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
    { label: "Sleepy", params: { blink: 4, eyebrow: -3, rotate_pitch: 8, smile: -0.1 } },
];

// ── Modal class ────────────────────────────────────────────

export class FacePokeModal {
    private dialog: HTMLDivElement;
    private panel: HTMLDivElement;
    private canvasImg: HTMLImageElement;
    private canvasArea: HTMLDivElement;
    private filmstrip: HTMLDivElement;
    private sliderPanel: HTMLDivElement;
    private sliderTitle: HTMLDivElement;
    private statusEl: HTMLDivElement;
    private callbacks: FacePokeCallbacks;

    private _isOpen = false;
    private videoPath = "";
    private allEdits: AllEdits = {};
    private currentFrame = 0;
    private currentFaceIdx = 0;
    private faces: FaceInfo[] = [];
    private totalFrames = 0;
    private videoWidth = 0;
    private videoHeight = 0;
    private videoFps = 24;
    private _escHandler: ((e: KeyboardEvent) => void) | null = null;
    private _wheelHandler: ((e: WheelEvent) => void) | null = null;
    private _previewDebounce: ReturnType<typeof setTimeout> | null = null;
    private _showLandmarks = false;
    private _showMarkers = true;
    private _previewInFlight = false;
    private _playing = false;
    private _playTimer: ReturnType<typeof setTimeout> | null = null;
    private _undoStack: string[] = [];
    private _redoStack: string[] = [];
    private _useBlaze = false;
    private _faceCache: Map<number, FaceInfo[]> = new Map();

    // ── Reference driving state ──
    private _drivingId: string | null = null;
    private _drivingTotalFrames = 0;
    private _drivingMultiplier = 1.0;
    private _refKp: number[][][] | null = null;  // per-frame ref expression
    private _refRatio = 1.0;
    private _refParts = "all";

    constructor(callbacks: FacePokeCallbacks) {
        this.callbacks = callbacks;

        // Clean up stale instances
        document.querySelectorAll(".fpoke-backdrop").forEach((d) => d.remove());

        // ─── Backdrop ───
        this.dialog = document.createElement("div");
        this.dialog.className = "fpoke-backdrop";
        this.dialog.style.display = "none";
        this.dialog.setAttribute("role", "dialog");
        this.dialog.setAttribute("aria-modal", "true");
        this.dialog.setAttribute("aria-label", "Face Poke Editor");

        // ─── Panel (CSS Grid) ───
        this.panel = document.createElement("div");
        this.panel.className = "fpoke-panel";

        // ═══════════════════════════════════════════════════════
        // HEADER
        // ═══════════════════════════════════════════════════════
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

        // ═══════════════════════════════════════════════════════
        // CANVAS AREA (face editing view)
        // ═══════════════════════════════════════════════════════
        this.canvasArea = document.createElement("div");
        this.canvasArea.className = "fpoke-canvas-area";

        this.canvasImg = document.createElement("img");
        this.canvasImg.className = "fpoke-canvas";
        this.canvasImg.alt = "Frame with face overlays";
        this.canvasArea.appendChild(this.canvasImg);

        // ═══════════════════════════════════════════════════════
        // SLIDER PANEL (expression controls sidebar)
        // ═══════════════════════════════════════════════════════
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

        // Reset Frame button inside slider panel
        const resetFrameRow = document.createElement("div");
        resetFrameRow.style.cssText = "padding: 10px 0 0; display: flex; gap: 6px;";
        const resetFrameBtn = this._makeBtn(`${fpIconReset} Reset Frame`, "fpoke-btn-sm fpoke-btn-reset", () => this._resetFrame());
        const passthroughBtn = this._makeBtn(`${fpIconPassThrough} Pass Through`, "fpoke-btn-sm fpoke-btn-pass", () => this._passthrough());
        const interpolateBtn = this._makeBtn(`${fpIconInterpolate} Interpolate`, "fpoke-btn-sm fpoke-btn-interp", () => this._interpolateFrames());
        interpolateBtn.title = "Smoothly fill frames between keyframes (I)";
        resetFrameRow.append(resetFrameBtn, passthroughBtn, interpolateBtn);

        this.sliderPanel.append(sliderGroup, resetFrameRow);

        // ── Emotion presets (chip buttons) ──
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
            chip.title = Object.entries(preset.params)
                .map(([k, v]) => `${k}: ${v}`).join(", ") || "Reset to neutral";
            chip.addEventListener("click", () => this._applyPreset(preset));
            chip.onpointerdown = (e) => e.stopPropagation();
            presetGrid.appendChild(chip);
        }
        presetSection.appendChild(presetGrid);
        this.sliderPanel.appendChild(presetSection);

        // ── Reference Image Section (per-frame) ──
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
                const file = input.files?.[0];
                if (!file) return;
                const reader = new FileReader();
                reader.onload = () => this._loadRefImage(reader.result as string);
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

        // Ratio slider
        const ratioRow = document.createElement("div");
        ratioRow.className = "fpoke-slider-row";
        const ratioLabel = document.createElement("span");
        ratioLabel.className = "fpoke-slider-label";
        ratioLabel.textContent = "Ratio";
        const ratioInput = document.createElement("input");
        ratioInput.type = "range";
        ratioInput.className = "fpoke-slider-input";
        ratioInput.min = "0"; ratioInput.max = "1"; ratioInput.step = "0.05";
        ratioInput.value = "1"; ratioInput.id = "fpoke-ref-ratio";
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

        // Parts dropdown
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
            o.value = opt; o.textContent = opt.replace("_", " ");
            partsSelect.appendChild(o);
        }
        partsSelect.addEventListener("change", () => {
            this._refParts = partsSelect.value;
            if (this._refKp) this._requestRefPreview();
        });
        partsRow.append(partsLabel, partsSelect);
        refSection.appendChild(partsRow);

        this.sliderPanel.appendChild(refSection);

        // ── Driving Video Section (below reference, applies to all frames) ──
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
                const file = input.files?.[0];
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

        // Multiplier slider
        const mulRow = document.createElement("div");
        mulRow.className = "fpoke-slider-row";
        const mulLabel = document.createElement("span");
        mulLabel.className = "fpoke-slider-label";
        mulLabel.textContent = "Multiplier";
        const mulInput = document.createElement("input");
        mulInput.type = "range";
        mulInput.className = "fpoke-slider-input";
        mulInput.min = "0.1"; mulInput.max = "2"; mulInput.step = "0.05";
        mulInput.value = "1"; mulInput.id = "fpoke-drv-multiplier";
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

        // ═══════════════════════════════════════════════════════
        // FILMSTRIP (frame scrubber)
        // ═══════════════════════════════════════════════════════
        this.filmstrip = document.createElement("div");
        this.filmstrip.className = "fpoke-filmstrip";

        // ═══════════════════════════════════════════════════════
        // TOOLBAR / STATUS
        // ═══════════════════════════════════════════════════════
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

        // ═══════════════════════════════════════════════════════
        // ASSEMBLE
        // ═══════════════════════════════════════════════════════
        this.panel.append(header, this.canvasArea, this.sliderPanel, this.filmstrip, toolbar);
        this.dialog.appendChild(this.panel);
        document.body.appendChild(this.dialog);
        console.log("[FacePoke] Modal constructor complete, dialog appended to body");
    }

    // ── Public API ─────────────────────────────────────────────

    async open(videoPath: string, initialEdits?: AllEdits): Promise<void> {
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

        // ── Show dialog IMMEDIATELY (before any async work) ──
        this._setStatus("Loading video...");
        this.dialog.style.display = "flex";
        console.log("[FacePoke] Dialog display set to flex");

        // Keyboard handler (register immediately so ESC works)
        this._escHandler = (e: KeyboardEvent) => {
            if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
            if (e.key === "Escape") { this._cancel(); return; }
            if (e.key === "ArrowLeft") { e.preventDefault(); this._prevFrame(); return; }
            if (e.key === "ArrowRight") { e.preventDefault(); this._nextFrame(); return; }
            if (e.key === "Home") { e.preventDefault(); this._selectFrame(0); return; }
            if (e.key === "End") { e.preventDefault(); this._selectFrame(Math.max(0, this.totalFrames - 1)); return; }
            if (e.key === "r" || e.key === "R") { this._resetFrame(); return; }
            if (e.key === "l" || e.key === "L") {
                this._showLandmarks = !this._showLandmarks;
                const lBtn = this.panel.querySelector(".fpoke-btn-landmark") as HTMLElement;
                if (lBtn) {
                    lBtn.classList.toggle("active", this._showLandmarks);
                    lBtn.innerHTML = this._showLandmarks ? `${fpIconLandmarks} Landmarks ${fpIconCheck}` : `${fpIconLandmarks} Landmarks`;
                }
                this._loadCanvasFrame();
                return;
            }
            if (e.key === "m" || e.key === "M") {
                this._showMarkers = !this._showMarkers;
                const mBtn = this.panel.querySelector(".fpoke-btn-markers") as HTMLElement;
                if (mBtn) {
                    mBtn.classList.toggle("active", this._showMarkers);
                    mBtn.innerHTML = this._showMarkers ? `${fpIconEye} Markers` : `${fpIconEyeOff} Markers`;
                }
                if (this._showMarkers) this._renderFaceOverlays();
                else this.canvasArea.querySelectorAll(".fpoke-face-overlay, .fpoke-ctrl-point").forEach((el) => el.remove());
                return;
            }
            if (e.key === "i" || e.key === "I") { this._interpolateFrames(); return; }
            if (e.key === " ") { e.preventDefault(); this._togglePlayback(); return; }
            // Undo/Redo
            if (e.key === "z" && (e.ctrlKey || e.metaKey) && !e.shiftKey) { e.preventDefault(); this._undo(); return; }
            if ((e.key === "y" && (e.ctrlKey || e.metaKey)) || (e.key === "z" && (e.ctrlKey || e.metaKey) && e.shiftKey)) { e.preventDefault(); this._redo(); return; }
        };
        document.addEventListener("keydown", this._escHandler);

        // Middle-wheel frame scroll
        this._wheelHandler = (e: WheelEvent) => {
            e.preventDefault();
            if (e.deltaY > 0) this._nextFrame();
            else if (e.deltaY < 0) this._prevFrame();
        };
        this.canvasArea.addEventListener("wheel", this._wheelHandler, { passive: false });

        // ── Async work (failures won't hide the modal) ──
        try {
            const resp = await api.fetchApi("/facepoke/get_frames", {
                method: "POST",
                body: JSON.stringify({ node_id: "", video_path: videoPath }),
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

    close(): void {
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

    get isOpen(): boolean { return this._isOpen; }

    setCallbacks(callbacks: FacePokeCallbacks): void {
        this.callbacks = callbacks;
    }

    // ── Frame navigation ───────────────────────────────────────

    private async _selectFrame(frameIdx: number): Promise<void> {
        this.currentFrame = frameIdx;
        this.currentFaceIdx = 0;
        this._updateFrameInfo();
        this._updateFilmstripActive(frameIdx);
        await this._loadCanvasFrame();

        // Use cached face data if available
        if (this._faceCache.has(frameIdx)) {
            this.faces = this._faceCache.get(frameIdx)!;
        } else {
            // Detect faces
            try {
                const resp = await api.fetchApi("/facepoke/detect_faces", {
                    method: "POST",
                    body: JSON.stringify({
                        video_path: this.videoPath,
                        frame_idx: frameIdx,
                        use_blaze: this._useBlaze,
                    }),
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

    private _prevFrame(): void {
        if (this.currentFrame > 0) this._selectFrame(this.currentFrame - 1);
    }

    private _nextFrame(): void {
        if (this.currentFrame < this.totalFrames - 1) this._selectFrame(this.currentFrame + 1);
    }

    // ── Canvas ─────────────────────────────────────────────────

    private async _loadCanvasFrame(): Promise<void> {
        // If driving video or reference image is active, use ref preview
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
                // Fall back to regular frame
                const url = await this._fetchFrame(this.currentFrame);
                this.canvasImg.src = url;
                this._setStatus("⚠ Landmarks unavailable — showing raw frame");
            }
        } else {
            const url = await this._fetchFrame(this.currentFrame);
            this.canvasImg.src = url;
        }
    }

    private _renderFaceOverlays(): void {
        // Remove old overlays + control points
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

                // Click to select face
                ov.addEventListener("click", (e) => {
                    e.stopPropagation();
                    this.currentFaceIdx = face.idx;
                    this._renderFaceOverlays();
                    this._loadSliders();
                    this.sliderTitle.textContent = `Expression Controls — Face ${face.idx + 1}`;
                });

                this.canvasArea.appendChild(ov);

                // Add draggable control points (only for selected face)
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

    private _setupControlPointDrag(dot: HTMLElement, face: FaceInfo, cp: ControlPointDef): void {
        let dragging = false;
        let startX = 0, startY = 0;
        let startVals: Record<string, number> = {};

        dot.addEventListener("mousedown", (e: MouseEvent) => {
            e.preventDefault();
            e.stopPropagation();
            dragging = true;
            startX = e.clientX;
            startY = e.clientY;
            dot.classList.add("active");

            // Capture current values for all mapped params
            const fe = this.allEdits[String(this.currentFrame)]?.[String(face.idx)] || {};
            startVals = {};
            for (const m of cp.dragMap) {
                startVals[m.key] = Number((fe as any)[m.key] || 0);
            }
        });

        const onMove = (e: MouseEvent) => {
            if (!dragging) return;
            const dx = e.clientX - startX;
            const dy = e.clientY - startY;

            this._ensureEdits(this.currentFrame, face.idx);
            const edits = this.allEdits[String(this.currentFrame)][String(face.idx)];

            for (const m of cp.dragMap) {
                const delta = m.axis === "x" ? dx : dy;
                const newVal = (startVals[m.key] || 0) + delta * m.sensitivity;
                (edits as any)[m.key] = Math.round(newVal * 100) / 100;
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

    private _onSliderChange(): void {
        this._pushUndo();
        this._ensureEdits(this.currentFrame, this.currentFaceIdx);
        for (const s of SLIDERS) {
            const input = document.getElementById(`fpoke-sl-${s.key}`) as HTMLInputElement | null;
            if (input) {
                (this.allEdits[String(this.currentFrame)][String(this.currentFaceIdx)] as any)[s.key] = Number(input.value);
            }
        }
        this._markThumbEdited(this.currentFrame);
        this._updateEditedCount();
        this._setStatus("Generating preview...");
        this._requestPreview();
    }

    private _loadSliders(): void {
        const fe = this.allEdits[String(this.currentFrame)]?.[String(this.currentFaceIdx)] || {};
        for (const s of SLIDERS) {
            const input = document.getElementById(`fpoke-sl-${s.key}`) as HTMLInputElement | null;
            const valEl = document.getElementById(`fpoke-sv-${s.key}`);
            if (input) {
                const val = Number((fe as any)[s.key] ?? s.default);
                input.value = String(val);
                if (valEl) valEl.textContent = val.toFixed(s.step < 1 ? 2 : 0);
            }
        }
    }

    // ── Filmstrip ──────────────────────────────────────────────

    private _buildFilmstrip(): void {
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
            this._fetchFrame(i).then((url) => { thumb.src = url; });

            const frameNum = document.createElement("span");
            frameNum.className = "fpoke-thumb-num";
            frameNum.textContent = String(i + 1);

            wrapper.append(thumb, frameNum);
            wrapper.addEventListener("click", () => this._selectFrame(i));
            this.filmstrip.appendChild(wrapper);
        }

        // Scroll-on-hover: scrolls filmstrip when hovering edges
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

    private _updateFilmstripActive(frameIdx: number): void {
        this.filmstrip.querySelectorAll(".fpoke-thumb-wrap").forEach((t) => {
            t.classList.remove("active");
            if ((t as HTMLElement).dataset.frameIdx === String(frameIdx)) {
                t.classList.add("active");
                t.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
            }
        });
    }

    private _markThumbEdited(frameIdx: number): void {
        const thumb = this.filmstrip.querySelector(`[data-frame-idx="${frameIdx}"]`);
        if (thumb) thumb.classList.add("edited");
    }

    private _updateFilmstripMarkers(): void {
        this.filmstrip.querySelectorAll(".fpoke-thumb-wrap").forEach((t) => {
            const idx = (t as HTMLElement).dataset.frameIdx;
            if (idx && this.allEdits[idx]) {
                t.classList.add("edited");
            } else {
                t.classList.remove("edited");
            }
        });
    }

    // ── Preview ────────────────────────────────────────────────

    private _requestPreview(): void {
        if (this._previewDebounce) clearTimeout(this._previewDebounce);
        this._previewDebounce = setTimeout(() => this._doPreview(), 50);
    }

    private async _doPreview(): Promise<void> {
        const frameEdits = this.allEdits[String(this.currentFrame)];
        if (!frameEdits) return;
        if (this._previewInFlight) return;  // Skip if already processing
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

    private _resetFrame(): void {
        this._pushUndo();
        delete this.allEdits[String(this.currentFrame)];
        this._loadSliders();
        this._loadCanvasFrame();
        this._updateFilmstripMarkers();
        this._updateEditedCount();
        this._setStatus(`Frame ${this.currentFrame + 1} reset`);
    }

    private _applyPreset(preset: EmotionPreset): void {
        this._pushUndo();
        const fi = this.currentFrame;
        const face = this.currentFaceIdx;
        // Reset first, then apply preset values
        this._ensureEdits(fi, face);
        // Clear existing params
        const edits = this.allEdits[String(fi)][String(face)];
        for (const key of Object.keys(edits)) {
            delete (edits as any)[key];
        }
        // Apply preset params
        for (const [key, val] of Object.entries(preset.params)) {
            (edits as any)[key] = val;
        }
        this._loadSliders();
        this._updateFilmstripMarkers();
        this._updateEditedCount();
        this._requestPreview();
        this._setStatus(`Applied "${preset.label}" preset`);
    }

    // ── Undo / Redo ────────────────────────────────────────────

    private _pushUndo(): void {
        this._undoStack.push(JSON.stringify(this.allEdits));
        if (this._undoStack.length > 50) this._undoStack.shift();
        this._redoStack = []; // clear redo on new edit
    }

    private _undo(): void {
        if (this._undoStack.length === 0) {
            this._setStatus("Nothing to undo");
            return;
        }
        this._redoStack.push(JSON.stringify(this.allEdits));
        this.allEdits = JSON.parse(this._undoStack.pop()!);
        this._loadSliders();
        this._loadCanvasFrame();
        this._updateFilmstripMarkers();
        this._updateEditedCount();
        this._setStatus("Undo applied");
    }

    private _redo(): void {
        if (this._redoStack.length === 0) {
            this._setStatus("Nothing to redo");
            return;
        }
        this._undoStack.push(JSON.stringify(this.allEdits));
        this.allEdits = JSON.parse(this._redoStack.pop()!);
        this._loadSliders();
        this._loadCanvasFrame();
        this._updateFilmstripMarkers();
        this._updateEditedCount();
        this._setStatus("Redo applied");
    }

    // ── Keyframe Interpolation ─────────────────────────────────

    private _interpolateFrames(): void {
        // Collect keyframes (frames that have edits) sorted by index
        const keyframeIndices = Object.keys(this.allEdits)
            .map(Number)
            .filter((k) => !isNaN(k) && this.allEdits[String(k)] && Object.keys(this.allEdits[String(k)]).length > 0)
            .sort((a, b) => a - b);

        if (keyframeIndices.length < 2) {
            this._setStatus("⚠ Need at least 2 edited frames to interpolate");
            return;
        }

        // Smoothstep easing: t*t*(3-2*t)
        const smoothstep = (t: number) => t * t * (3 - 2 * t);

        // All expression param keys
        const paramKeys: (keyof FaceEditParams)[] = [
            "rotate_pitch", "rotate_yaw", "rotate_roll",
            "blink", "blink_left", "blink_right",
            "eyebrow", "eyebrow_left", "eyebrow_right",
            "wink", "pupil_x", "pupil_y",
            "aaa", "eee", "woo", "smile",
        ];

        let generated = 0;

        // Collect all face indices across all keyframes
        const allFaceIndices = new Set<string>();
        for (const ki of keyframeIndices) {
            for (const fi of Object.keys(this.allEdits[String(ki)])) {
                allFaceIndices.add(fi);
            }
        }

        // Interpolate between each adjacent pair of keyframes
        for (let i = 0; i < keyframeIndices.length - 1; i++) {
            const fA = keyframeIndices[i];
            const fB = keyframeIndices[i + 1];
            const span = fB - fA;
            if (span <= 1) continue; // adjacent frames, nothing to fill

            for (let frame = fA + 1; frame < fB; frame++) {
                const t = smoothstep((frame - fA) / span);

                if (!this.allEdits[String(frame)]) this.allEdits[String(frame)] = {};

                for (const faceIdx of allFaceIndices) {
                    const paramsA = this.allEdits[String(fA)]?.[faceIdx] || {};
                    const paramsB = this.allEdits[String(fB)]?.[faceIdx] || {};

                    if (!this.allEdits[String(frame)][faceIdx]) {
                        this.allEdits[String(frame)][faceIdx] = {};
                    }

                    for (const key of paramKeys) {
                        const vA = Number((paramsA as any)[key] || 0);
                        const vB = Number((paramsB as any)[key] || 0);
                        if (vA === 0 && vB === 0) continue;
                        const interpolated = vA + (vB - vA) * t;
                        (this.allEdits[String(frame)][faceIdx] as any)[key] =
                            Math.round(interpolated * 1000) / 1000;
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

    private _togglePlayback(): void {
        if (this._playing) {
            this._stopPlayback();
        } else {
            this._startPlayback();
        }
    }

    private _startPlayback(): void {
        this._playing = true;
        const btn = document.getElementById("fpoke-play-btn");
        if (btn) {
            btn.innerHTML = `${fpIconPause} Pause`;
            btn.classList.add("active");
        }
        this._setStatus("Playing...");
        this._playStep();
    }

    private _stopPlayback(): void {
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

    private async _playStep(): Promise<void> {
        if (!this._playing) return;

        const frameIdx = this.currentFrame;
        this._updateFrameInfo();
        this._updateFilmstripActive(frameIdx);

        // Fetch the right image for this frame
        try {
            const frameEdits = this.allEdits[String(frameIdx)];
            let url: string;
            if (frameEdits && Object.keys(frameEdits).length > 0) {
                url = await this._fetchPreview(frameIdx, frameEdits);
            } else {
                url = await this._fetchFrame(frameIdx);
            }
            if (!this._playing) return; // stopped while fetching
            this.canvasImg.src = url;
            this._setStatus(`Playing — Frame ${frameIdx + 1} / ${this.totalFrames}`);
        } catch {
            // Skip errored frames
        }

        // Advance to next frame
        const nextFrame = frameIdx + 1;
        if (nextFrame >= this.totalFrames) {
            this._stopPlayback();
            this._setStatus("Playback complete");
            return;
        }
        this.currentFrame = nextFrame;

        // Schedule next frame at video FPS
        const delay = Math.max(1000 / this.videoFps, 30); // min 30ms
        this._playTimer = setTimeout(() => this._playStep(), delay);
    }

    private _apply(): void {
        // Clean zero-edits
        const clean: AllEdits = {};
        for (const [fi, fe] of Object.entries(this.allEdits)) {
            const cf: FrameEdits = {};
            for (const [face, params] of Object.entries(fe)) {
                const nz = Object.entries(params).filter(([, v]) => v !== 0);
                if (nz.length) cf[face] = Object.fromEntries(nz) as FaceEditParams;
            }
            if (Object.keys(cf).length) clean[fi] = cf;
        }

        this.close();
        this.callbacks.onApply(clean);
    }

    private _cancel(): void {
        this.close();
        this.callbacks.onCancel();
    }

    private _passthrough(): void {
        this.close();
        this.callbacks.onApply({});
    }

    // ── Helpers ─────────────────────────────────────────────────

    private _ensureEdits(fi: number, face: number): void {
        if (!this.allEdits[String(fi)]) this.allEdits[String(fi)] = {};
        if (!this.allEdits[String(fi)][String(face)]) this.allEdits[String(fi)][String(face)] = {};
    }

    private _updateFrameInfo(): void {
        const el = document.getElementById("fpoke-frame-info");
        if (el) {
            el.textContent = `Frame ${this.currentFrame + 1} / ${this.totalFrames} · ` +
                `${this.videoWidth}×${this.videoHeight} · ${this.videoFps.toFixed(1)} FPS`;
        }
    }

    private _updateEditedCount(): void {
        const el = document.getElementById("fpoke-edited-count");
        const count = Object.keys(this.allEdits).filter(
            (k) => this.allEdits[k] && Object.keys(this.allEdits[k]).length > 0,
        ).length;
        if (el) el.textContent = `${count} frame${count !== 1 ? "s" : ""} edited`;
    }

    // ── Reference Image Methods ─────────────────────────────────────

    private async _loadRefImage(dataUrl: string): Promise<void> {
        this._setStatus("Extracting reference expression...");
        try {
            const resp = await api.fetchApi("/facepoke/extract_ref_expression", {
                method: "POST",
                body: JSON.stringify({
                    image_data: dataUrl,
                    crop_factor: 1.6,
                }),
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

    private async _uploadDrivingVideo(file: File): Promise<void> {
        this._setStatus("Uploading driving video...");
        try {
            // Upload via ComfyUI upload API
            const formData = new FormData();
            formData.append("image", file, file.name);
            formData.append("subfolder", "facepoke_driving");
            formData.append("type", "input");
            const uploadResp = await api.fetchApi("/upload/image", {
                method: "POST",
                body: formData,
            });
            const uploadData = await uploadResp.json();
            if (!uploadData.name) {
                this._setStatus("Driving video upload failed");
                return;
            }

            const uploadedPath = uploadData.subfolder
                ? `${uploadData.subfolder}/${uploadData.name}`
                : uploadData.name;

            this._setStatus("Extracting driving keypoints... This may take a moment.");
            const info = document.getElementById("fpoke-drv-info");
            if (info) info.textContent = "Extracting...";

            const resp = await api.fetchApi("/facepoke/extract_driving", {
                method: "POST",
                body: JSON.stringify({
                    video_path: uploadedPath,
                    crop_factor: 1.6,
                }),
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

    private _requestRefPreview(): void {
        if (this._previewDebounce) clearTimeout(this._previewDebounce);
        this._previewDebounce = setTimeout(async () => {
            if (this._previewInFlight) return;
            this._previewInFlight = true;
            this._setStatus("Generating reference preview...");

            try {
                // Build slider edits for current frame/face
                const frameKey = String(this.currentFrame);
                const faceKey = String(this.currentFaceIdx);
                const sliderEdits = this.allEdits[frameKey]?.[faceKey] ?? null;

                // Get cached bboxes
                const cachedFaces = this._faceCache.get(this.currentFrame);
                const cachedBboxes = cachedFaces?.map((f) => f.bbox) ?? null;

                const body: Record<string, unknown> = {
                    video_path: this.videoPath,
                    frame_idx: this.currentFrame,
                    face_idx: this.currentFaceIdx,
                    use_blaze: this._useBlaze,
                    cached_bboxes: cachedBboxes,
                };

                // Add driving video data
                if (this._drivingId) {
                    // Map source frame to driving frame (1:1 mapping, clamped)
                    const drvFrame = Math.min(
                        this.currentFrame,
                        this._drivingTotalFrames - 1
                    );
                    body.driving_id = this._drivingId;
                    body.driving_frame = drvFrame;
                    body.multiplier = this._drivingMultiplier;
                }

                // Add reference image data
                if (this._refKp) {
                    body.ref_kp = this._refKp;
                    body.ratio = this._refRatio;
                    body.parts = this._refParts;
                }

                // Add slider edits on top
                if (sliderEdits && Object.keys(sliderEdits).length > 0) {
                    body.slider_edits = sliderEdits;
                }

                const resp = await api.fetchApi("/facepoke/apply_ref_preview", {
                    method: "POST",
                    body: JSON.stringify(body),
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

    private async _applyDrivingToAll(): Promise<void> {
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
            // Store driving reference as special meta keys
            (this.allEdits[key][faceKey] as Record<string, unknown>)._driving_id = this._drivingId;
            (this.allEdits[key][faceKey] as Record<string, unknown>)._driving_frame = i;
            (this.allEdits[key][faceKey] as Record<string, unknown>)._driving_multiplier = this._drivingMultiplier;
        }

        this._updateEditedCount();
        this._updateFilmstripMarkers();
        this._setStatus(`Applied driving motion to ${maxFrame} frames`);
        this._requestRefPreview();
    }

    private _setStatus(msg: string): void {
        this.statusEl.textContent = msg;
    }

    private _makeBtn(html: string, cls: string, onClick: () => void): HTMLButtonElement {
        const btn = document.createElement("button");
        btn.className = `fpoke-btn ${cls}`;
        btn.innerHTML = html;
        btn.addEventListener("click", onClick);
        btn.onpointerdown = (e) => e.stopPropagation();
        return btn;
    }

    // ── API calls ──────────────────────────────────────────────

    private async _fetchFrame(idx: number): Promise<string> {
        const resp = await api.fetchApi("/facepoke/get_frame", {
            method: "POST",
            body: JSON.stringify({ video_path: this.videoPath, frame_idx: idx }),
        });
        const blob = await resp.blob();
        return URL.createObjectURL(blob);
    }

    private async _fetchPreview(idx: number, edits: FrameEdits): Promise<string> {
        // Send cached face bboxes to avoid re-detection on backend
        const cachedFaces = this._faceCache.get(idx);
        const cachedBboxes = cachedFaces?.map((f) => f.bbox) ?? null;

        const resp = await api.fetchApi("/facepoke/preview", {
            method: "POST",
            body: JSON.stringify({
                video_path: this.videoPath, frame_idx: idx, face_edits: edits,
                use_blaze: this._useBlaze,
                cached_bboxes: cachedBboxes,
            }),
        });
        if (!resp.ok) {
            const errText = await resp.text();
            throw new Error(`Preview API error ${resp.status}: ${errText}`);
        }
        const blob = await resp.blob();
        return URL.createObjectURL(blob);
    }

    private async _fetchFrameWithLandmarks(idx: number): Promise<string> {
        const resp = await api.fetchApi("/facepoke/get_frame_with_landmarks", {
            method: "POST",
            body: JSON.stringify({
                video_path: this.videoPath,
                frame_idx: idx,
                selected_face: this.currentFaceIdx,
            }),
        });
        if (!resp.ok) {
            throw new Error(`Landmark API error: ${resp.status}`);
        }
        const blob = await resp.blob();
        return URL.createObjectURL(blob);
    }
}
