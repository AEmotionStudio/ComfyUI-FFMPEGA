var __defProp = Object.defineProperty;
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { a as addDownloadOverlay } from "./_chunks/ui_helpers-CvUDB6-L.js";
import { a as EditTimeline, E as EditManager } from "./_chunks/EditTimeline-BeK0Y4a7.js";
const L = (inner) => `<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-0.125em">${inner}</svg>`;
const iconClapperboard = L(
  '<path d="m12.296 3.464 3.02 3.956"/><path d="M20.2 6 3 11l-.9-2.4c-.3-1.1.3-2.2 1.3-2.5l13.5-4c1.1-.3 2.2.3 2.5 1.3z"/><path d="M3 11h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="m6.18 5.276 3.1 3.899"/>'
);
const iconPlay = L(
  '<path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"/>'
);
const iconPause = L(
  '<rect x="14" y="3" width="5" height="18" rx="1"/><rect x="5" y="3" width="5" height="18" rx="1"/>'
);
const iconStepBack = L(
  '<path d="M17.971 4.285A2 2 0 0 1 21 6v12a2 2 0 0 1-3.029 1.715l-9.997-5.998a2 2 0 0 1-.003-3.432z"/><path d="M3 20V4"/>'
);
const iconStepForward = L(
  '<path d="M21 4v16"/><path d="M6.029 4.285A2 2 0 0 0 3 6v12a2 2 0 0 0 3.029 1.715l9.997-5.998a2 2 0 0 0 .003-3.432z"/>'
);
const iconCursor = L(
  '<path d="M12.586 12.586 19 19"/><path d="M3.688 3.037a.497.497 0 0 0-.651.651l6.5 15.999a.501.501 0 0 0 .947-.062l1.569-6.083a2 2 0 0 1 1.448-1.479l6.124-1.579a.5.5 0 0 0 .063-.947z"/>'
);
const iconScissors = L(
  '<circle cx="6" cy="6" r="3"/><path d="M8.12 8.12 12 12"/><path d="M20 4 8.12 15.88"/><circle cx="6" cy="18" r="3"/><path d="M14.8 14.8 20 20"/>'
);
const iconSplit = L(
  '<path d="M16 3h5v5"/><path d="M8 3H3v5"/><path d="M12 22v-8.3a4 4 0 0 0-1.172-2.872L3 3"/><path d="m15 9 6-6"/>'
);
const iconTrash = L(
  '<path d="M10 11v6"/><path d="M14 11v6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'
);
const iconCrop = L(
  '<path d="M6 2v14a2 2 0 0 0 2 2h14"/><path d="M18 22V8a2 2 0 0 0-2-2H2"/>'
);
const iconGauge = L(
  '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>'
);
const iconVolume = L(
  '<path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z"/><path d="M16 9a5 5 0 0 1 0 6"/><path d="M19.364 18.364a9 9 0 0 0 0-12.728"/>'
);
const iconMuted = L(
  '<path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z"/><line x1="22" x2="16" y1="9" y2="15"/><line x1="16" x2="22" y1="9" y2="15"/>'
);
const iconText = L(
  '<path d="M12 4v16"/><path d="M4 7V5a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v2"/><path d="M9 20h6"/>'
);
const iconUndo = L(
  '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"/>'
);
const iconRedo = L(
  '<path d="m15 14 5-5-5-5"/><path d="M20 9H9.5A5.5 5.5 0 0 0 4 14.5A5.5 5.5 0 0 0 9.5 20H13"/>'
);
const iconCheck = L('<path d="M20 6 9 17l-5-5"/>');
const iconClose = L('<path d="M18 6 6 18"/><path d="m6 6 12 12"/>');
const iconZoomIn = L(
  '<circle cx="11" cy="11" r="8"/><line x1="21" x2="16.65" y1="21" y2="16.65"/><line x1="11" x2="11" y1="8" y2="14"/><line x1="8" x2="14" y1="11" y2="11"/>'
);
const iconZoomOut = L(
  '<circle cx="11" cy="11" r="8"/><line x1="21" x2="16.65" y1="21" y2="16.65"/><line x1="8" x2="14" y1="11" y2="11"/>'
);
const iconMaximize = L(
  '<path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>'
);
const iconReset = L(
  '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>'
);
const iconFlip = L(
  '<path d="m3 7 5 5-5 5V7"/><path d="m21 7-5 5 5 5V7"/><path d="M12 20v2"/><path d="M12 14v2"/><path d="M12 8v2"/><path d="M12 2v2"/>'
);
const iconReverse = L(
  '<path d="m3 16 4 4 4-4"/><path d="M7 20V4"/><path d="m21 8-4-4-4 4"/><path d="M17 4v16"/>'
);
const iconCurve = L(
  '<circle cx="19" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><path d="M5 17A12 12 0 0 1 17 5"/>'
);
const iconFilm = L(
  '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M7 3v18"/><path d="M3 7.5h4"/><path d="M3 12h18"/><path d="M3 16.5h4"/><path d="M17 3v18"/><path d="M17 7.5h4"/><path d="M17 16.5h4"/>'
);
const iconMusic = L(
  '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>'
);
const iconBold = L(
  '<path d="M6 12h9a4 4 0 0 1 0 8H7a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h7a4 4 0 0 1 0 8"/>'
);
const iconItalic = L(
  '<line x1="19" x2="10" y1="4" y2="4"/><line x1="14" x2="5" y1="20" y2="20"/><line x1="15" x2="9" y1="4" y2="20"/>'
);
const iconAlignLeft = L(
  '<line x1="21" x2="3" y1="6" y2="6"/><line x1="15" x2="3" y1="12" y2="12"/><line x1="17" x2="3" y1="18" y2="18"/>'
);
const iconAlignCenter = L(
  '<line x1="21" x2="3" y1="6" y2="6"/><line x1="17" x2="7" y1="12" y2="12"/><line x1="19" x2="5" y1="18" y2="18"/>'
);
const iconAlignRight = L(
  '<line x1="21" x2="3" y1="6" y2="6"/><line x1="21" x2="9" y1="12" y2="12"/><line x1="21" x2="7" y1="18" y2="18"/>'
);
const iconPlus = L(
  '<path d="M5 12h14"/><path d="M12 5v14"/>'
);
const iconShuffle = L(
  '<path d="M2 18h1.4c1.3 0 2.5-.6 3.3-1.7l6.1-8.6c.7-1.1 2-1.7 3.3-1.7H22"/><path d="m18 2 4 4-4 4"/><path d="M2 6h1.9c1.5 0 2.9.9 3.6 2.2"/><path d="M22 18h-5.9c-1.3 0-2.6-.7-3.3-1.8l-.5-.8"/><path d="m18 14 4 4-4 4"/>'
);
class TransportBar {
  constructor(callbacks) {
    __publicField(this, "container");
    __publicField(this, "video", null);
    __publicField(this, "callbacks");
    __publicField(this, "timeDisplay");
    __publicField(this, "playBtn");
    __publicField(this, "shuttleSpeed", 1);
    __publicField(this, "_keyHandler", null);
    __publicField(this, "_editManager", null);
    __publicField(this, "_animFrameId", null);
    __publicField(this, "_currentSegIdx", 0);
    __publicField(this, "_seekLock", false);
    /** When a seek is pending, this holds the desired time */
    __publicField(this, "_targetTime", null);
    this.callbacks = callbacks;
    this.container = document.createElement("div");
    this.container.className = "veditor-transport";
    this.container.setAttribute("data-tool-id", "veditor-transport");
    this.container.setAttribute("aria-label", "Video transport controls");
    this.container.setAttribute("role", "toolbar");
    const stepBack = this._makeBtn(iconStepBack, "Step back 1 frame (←)", () => this._stepFrame(-1), "veditor-step-back");
    this.playBtn = this._makeBtn(iconPlay, "Play / Pause (Space or K)", () => this._togglePlay(), "veditor-play-btn");
    const stepFwd = this._makeBtn(iconStepForward, "Step forward 1 frame (→)", () => this._stepFrame(1), "veditor-step-forward");
    this.timeDisplay = document.createElement("span");
    this.timeDisplay.className = "veditor-time";
    this.timeDisplay.textContent = "00:00.00 / 00:00.00";
    this.timeDisplay.setAttribute("data-tool-id", "veditor-timecode");
    this.timeDisplay.setAttribute("aria-label", "Current time / total duration");
    this.timeDisplay.setAttribute("aria-live", "polite");
    this.container.append(stepBack, this.playBtn, stepFwd, this.timeDisplay);
    this._keyHandler = (e) => this._onKeyDown(e);
    document.addEventListener("keydown", this._keyHandler);
  }
  get element() {
    return this.container;
  }
  /** Bind the edit manager for segment-aware playback */
  setEditManager(manager) {
    this._editManager = manager;
  }
  bindVideo(video) {
    this.video = video;
    video.addEventListener("timeupdate", () => {
      if (!this._seekLock && !video.paused) {
        this._enforceSegments();
      }
      this._updateTimeDisplay();
      this.callbacks.onTimeUpdate(
        this._targetTime !== null ? this._targetTime : video.currentTime
      );
    });
    video.addEventListener("seeked", () => {
      if (this._targetTime !== null) {
        if (Math.abs(video.currentTime - this._targetTime) < 0.5) {
          this._targetTime = null;
        }
      }
      this._updateTimeDisplay();
      this.callbacks.onTimeUpdate(
        this._targetTime !== null ? this._targetTime : video.currentTime
      );
    });
    video.addEventListener("play", () => {
      this._targetTime = null;
      this.playBtn.innerHTML = iconPause;
      this.callbacks.onPlayStateChange(true);
      this._startSegmentPolling();
    });
    video.addEventListener("pause", () => {
      this.playBtn.innerHTML = iconPlay;
      this.callbacks.onPlayStateChange(false);
      this._stopSegmentPolling();
    });
    video.addEventListener("loadedmetadata", () => {
      this._updateTimeDisplay();
    });
  }
  seekTo(time) {
    if (!this.video) return;
    this._seekLock = true;
    const dur = this.video.duration;
    const maxTime = dur && isFinite(dur) ? dur : Infinity;
    const clamped = Math.max(0, Math.min(time, maxTime));
    this._targetTime = clamped;
    this.video.currentTime = clamped;
    if (typeof this.video.fastSeek === "function") {
      try {
        this.video.fastSeek(clamped);
      } catch {
      }
    }
    this._syncSegmentIndexForTime(clamped);
    this._updateTimeDisplay();
    this.callbacks.onTimeUpdate(clamped);
    requestAnimationFrame(() => {
      this._seekLock = false;
    });
  }
  /** Seek to an output-timeline position (mapped through segment order) */
  seekToOutput(outputTime) {
    if (!this.video || !this._editManager) {
      this.seekTo(outputTime);
      return;
    }
    const mgr = this._editManager;
    const segs = mgr.segments;
    let accumulated = 0;
    for (let i = 0; i < segs.length; i++) {
      const segDur = segs[i].end - segs[i].start;
      if (outputTime <= accumulated + segDur) {
        this._currentSegIdx = i;
        this.video.currentTime = segs[i].start + (outputTime - accumulated);
        return;
      }
      accumulated += segDur;
    }
    this._currentSegIdx = 0;
    if (segs.length > 0) {
      this.video.currentTime = segs[0].start;
    }
  }
  destroy() {
    if (this._keyHandler) {
      document.removeEventListener("keydown", this._keyHandler);
      this._keyHandler = null;
    }
    this._stopSegmentPolling();
    this.container.remove();
  }
  // ── Private ──────────────────────────────────────────────────
  /**
   * Figure out which segment index the current video.currentTime
   * falls in. Used after a raw seekTo() call.
   */
  _syncSegmentIndex() {
    if (!this.video || !this._editManager) return;
    this._syncSegmentIndexForTime(this.video.currentTime);
  }
  /** Sync segment index using a given time (not video.currentTime) */
  _syncSegmentIndexForTime(t) {
    if (!this._editManager) return;
    const segs = this._editManager.segments;
    const cur = segs[this._currentSegIdx];
    if (cur && t >= cur.start - 0.1 && t <= cur.end + 0.1) return;
    for (let i = 0; i < segs.length; i++) {
      if (t >= segs[i].start - 0.1 && t <= segs[i].end + 0.1) {
        this._currentSegIdx = i;
        return;
      }
    }
    let bestIdx = 0;
    let bestDist = Infinity;
    for (let i = 0; i < segs.length; i++) {
      const mid = (segs[i].start + segs[i].end) / 2;
      const dist = Math.abs(t - mid);
      if (dist < bestDist) {
        bestDist = dist;
        bestIdx = i;
      }
    }
    this._currentSegIdx = bestIdx;
  }
  /**
   * Enforce segment boundaries during playback.
   * Follows array order (non-linear): when current segment ends,
   * jump to the NEXT segment in the array regardless of source time.
   */
  _enforceSegments() {
    if (!this.video || !this._editManager) return;
    if (this._seekLock || this.video.paused) return;
    const segs = this._editManager.segments;
    if (segs.length === 0) return;
    if (this._currentSegIdx < 0 || this._currentSegIdx >= segs.length) {
      this._currentSegIdx = 0;
    }
    const seg = segs[this._currentSegIdx];
    const t = this.video.currentTime;
    if (t >= seg.end - 0.02) {
      const nextIdx = this._currentSegIdx + 1;
      if (nextIdx < segs.length) {
        this._currentSegIdx = nextIdx;
        this.video.currentTime = segs[nextIdx].start;
      } else {
        this._currentSegIdx = 0;
        if (!this.video.paused) {
          this.video.currentTime = segs[0].start;
        }
      }
      return;
    }
    if (t < seg.start - 0.05) {
      this.video.currentTime = seg.start;
    }
  }
  /**
   * rAF polling for responsive segment boundary enforcement.
   * HTML5 timeupdate fires ~4Hz; rAF gives ~60Hz.
   */
  _startSegmentPolling() {
    if (this._animFrameId !== null) return;
    const poll = () => {
      this._enforceSegments();
      this._animFrameId = requestAnimationFrame(poll);
    };
    this._animFrameId = requestAnimationFrame(poll);
  }
  _stopSegmentPolling() {
    if (this._animFrameId !== null) {
      cancelAnimationFrame(this._animFrameId);
      this._animFrameId = null;
    }
  }
  _togglePlay() {
    if (!this.video) return;
    if (this.video.paused) {
      if (this._editManager) {
        const segs = this._editManager.segments;
        if (segs.length > 0) {
          const lastSeg = segs[segs.length - 1];
          if (this.video.currentTime >= lastSeg.end - 0.02 && this._currentSegIdx >= segs.length - 1) {
            this._currentSegIdx = 0;
            this.video.currentTime = segs[0].start;
          }
        }
      }
      this.video.playbackRate = this.shuttleSpeed;
      this.video.play();
    } else {
      this.video.pause();
    }
  }
  _stepFrame(direction) {
    if (!this.video) return;
    this.video.pause();
    const fps = 30;
    const dt = direction / fps;
    let newTime = this.video.currentTime + dt;
    if (this._editManager) {
      const segs = this._editManager.segments;
      const seg = segs[this._currentSegIdx];
      if (seg) {
        if (direction > 0 && newTime >= seg.end) {
          const nextIdx = this._currentSegIdx + 1;
          if (nextIdx < segs.length) {
            this._currentSegIdx = nextIdx;
            newTime = segs[nextIdx].start;
          } else {
            newTime = seg.end - 1 / fps;
          }
        } else if (direction < 0 && newTime < seg.start) {
          const prevIdx = this._currentSegIdx - 1;
          if (prevIdx >= 0) {
            this._currentSegIdx = prevIdx;
            newTime = segs[prevIdx].end - 1 / fps;
          } else {
            newTime = seg.start;
          }
        }
      }
    }
    this.video.currentTime = Math.max(0, newTime);
  }
  _onKeyDown(e) {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
      return;
    }
    switch (e.key.toLowerCase()) {
      case "k":
        e.preventDefault();
        this._togglePlay();
        break;
      case "j":
        e.preventDefault();
        this.shuttleSpeed = Math.max(0.25, this.shuttleSpeed / 2);
        if (this.video && !this.video.paused) {
          this.video.playbackRate = this.shuttleSpeed;
        }
        break;
      case "l":
        e.preventDefault();
        this.shuttleSpeed = Math.min(4, this.shuttleSpeed * 2);
        if (this.video && !this.video.paused) {
          this.video.playbackRate = this.shuttleSpeed;
        }
        break;
      case "i":
      case "o":
      case "s":
        break;
      case " ":
        e.preventDefault();
        this._togglePlay();
        break;
    }
  }
  /**
   * Time display: shows output-relative time when edit manager is bound.
   * Computes output time by walking segments in array order up to current.
   */
  _updateTimeDisplay() {
    if (!this.video) return;
    const currentTime = this._targetTime !== null ? this._targetTime : this.video.currentTime;
    if (this._editManager) {
      const mgr = this._editManager;
      const segs = mgr.segments;
      const outputDur = mgr.getOutputDuration();
      let outputTime = 0;
      for (let i = 0; i < this._currentSegIdx && i < segs.length; i++) {
        outputTime += segs[i].end - segs[i].start;
      }
      const seg = segs[this._currentSegIdx];
      if (seg) {
        outputTime += Math.max(0, currentTime - seg.start);
        outputTime = Math.min(outputTime, outputDur);
      }
      this.timeDisplay.textContent = `${this._formatTime(outputTime)} / ${this._formatTime(outputDur)}`;
    } else {
      const current = this._formatTime(currentTime);
      const total = this._formatTime(this.video.duration || 0);
      this.timeDisplay.textContent = `${current} / ${total}`;
    }
  }
  _formatTime(seconds) {
    if (!isFinite(seconds)) return "00:00.00";
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toFixed(2).padStart(5, "0")}`;
  }
  _makeBtn(label, title, onClick, toolId) {
    const btn = document.createElement("button");
    btn.className = "veditor-btn veditor-btn-icon";
    btn.innerHTML = label;
    btn.title = title;
    if (toolId) {
      btn.setAttribute("data-tool-id", toolId);
      btn.setAttribute("aria-label", title);
    }
    btn.addEventListener("click", onClick);
    return btn;
  }
}
const HANDLE_SIZE = 10;
class CropOverlay {
  constructor(callbacks) {
    __publicField(this, "canvasWrapper");
    __publicField(this, "canvas");
    __publicField(this, "controls");
    __publicField(this, "callbacks");
    __publicField(this, "rect", null);
    __publicField(this, "videoWidth", 0);
    __publicField(this, "videoHeight", 0);
    __publicField(this, "aspectPreset", "free");
    __publicField(this, "isDragging", false);
    __publicField(this, "dragType", "none");
    __publicField(this, "dragStart", { x: 0, y: 0 });
    __publicField(this, "origRect", { x: 0, y: 0, w: 0, h: 0 });
    __publicField(this, "enabled", false);
    // Numeric input fields
    __publicField(this, "inputX");
    __publicField(this, "inputY");
    __publicField(this, "inputW");
    __publicField(this, "inputH");
    __publicField(this, "outputLabel");
    this.callbacks = callbacks;
    this.canvasWrapper = document.createElement("div");
    this.canvasWrapper.className = "veditor-crop-canvas-wrap";
    this.canvasWrapper.style.pointerEvents = "none";
    this.canvasWrapper.style.position = "absolute";
    this.canvasWrapper.style.top = "0";
    this.canvasWrapper.style.left = "0";
    this.canvasWrapper.style.width = "100%";
    this.canvasWrapper.style.height = "100%";
    this.canvas = document.createElement("canvas");
    this.canvas.className = "veditor-crop-canvas";
    this.canvas.style.pointerEvents = "auto";
    this.canvas.style.width = "100%";
    this.canvas.style.height = "100%";
    this.canvasWrapper.appendChild(this.canvas);
    this.controls = document.createElement("div");
    this.controls.className = "veditor-crop-controls";
    this.controls.setAttribute("data-tool-id", "veditor-crop-controls");
    const toggleSection = this._makeSection("Crop");
    const toggleRow = document.createElement("div");
    toggleRow.className = "veditor-control-row";
    const toggleBtn = document.createElement("button");
    toggleBtn.className = "veditor-btn veditor-toggle-btn";
    toggleBtn.innerHTML = `${iconCrop} Enable Crop`;
    toggleBtn.title = "Toggle crop";
    toggleBtn.setAttribute("data-tool-id", "veditor-crop-toggle");
    toggleBtn.setAttribute("aria-label", "Toggle crop");
    toggleBtn.addEventListener("click", () => {
      this.enabled = !this.enabled;
      toggleBtn.classList.toggle("active", this.enabled);
      if (this.enabled && !this.rect) {
        this.rect = {
          x: Math.round(this.videoWidth * 0.1),
          y: Math.round(this.videoHeight * 0.1),
          w: Math.round(this.videoWidth * 0.8),
          h: Math.round(this.videoHeight * 0.8)
        };
      }
      if (!this.enabled) {
        this.rect = null;
        this.callbacks.onCropChanged(null);
      }
      this._updateInputs();
      this.render();
    });
    toggleRow.appendChild(toggleBtn);
    toggleSection.appendChild(toggleRow);
    const presetRow = document.createElement("div");
    presetRow.className = "veditor-preset-row";
    const presets = ["free", "16:9", "9:16", "4:3", "1:1"];
    presets.forEach((p) => {
      const btn = document.createElement("button");
      btn.className = "veditor-btn veditor-preset-btn";
      if (p === this.aspectPreset) btn.classList.add("active");
      btn.textContent = p === "free" ? "Free" : p;
      btn.title = `Aspect ratio: ${p}`;
      btn.setAttribute("data-tool-id", `veditor-crop-aspect-${p.replace(":", "")}`);
      btn.setAttribute("aria-label", `Aspect ratio: ${p}`);
      btn.addEventListener("click", () => {
        this.aspectPreset = p;
        presetRow.querySelectorAll(".veditor-preset-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        if (this.rect && p !== "free") {
          this._applyAspect(p);
        }
        this._updateInputs();
        this.render();
      });
      presetRow.appendChild(btn);
    });
    const flipBtn = document.createElement("button");
    flipBtn.className = "veditor-btn veditor-preset-btn";
    flipBtn.innerHTML = `${iconFlip}`;
    flipBtn.title = "Flip aspect ratio (swap width/height)";
    flipBtn.setAttribute("data-tool-id", "veditor-crop-flip");
    flipBtn.setAttribute("aria-label", "Flip aspect ratio");
    flipBtn.addEventListener("click", () => {
      if (!this.rect) return;
      const oldW = this.rect.w;
      this.rect.w = this.rect.h;
      this.rect.h = oldW;
      this.rect.x = Math.max(0, Math.round((this.videoWidth - this.rect.w) / 2));
      this.rect.y = Math.max(0, Math.round((this.videoHeight - this.rect.h) / 2));
      if (this.rect.w > this.videoWidth) this.rect.w = this.videoWidth;
      if (this.rect.h > this.videoHeight) this.rect.h = this.videoHeight;
      this._updateInputs();
      this.render();
      this.callbacks.onCropChanged(this.rect);
    });
    presetRow.appendChild(flipBtn);
    toggleSection.appendChild(presetRow);
    const numSection = this._makeSection("Dimensions");
    const numRow1 = document.createElement("div");
    numRow1.className = "veditor-control-row";
    const xLabel = this._makeLabel("X");
    this.inputX = this._makeNumInput("veditor-crop-x", "X position", (v) => {
      if (this.rect) {
        this.rect.x = v;
        this.render();
        this.callbacks.onCropChanged(this.rect);
      }
    });
    const yLabel = this._makeLabel("Y");
    this.inputY = this._makeNumInput("veditor-crop-y", "Y position", (v) => {
      if (this.rect) {
        this.rect.y = v;
        this.render();
        this.callbacks.onCropChanged(this.rect);
      }
    });
    numRow1.append(xLabel, this.inputX, yLabel, this.inputY);
    const numRow2 = document.createElement("div");
    numRow2.className = "veditor-control-row";
    const wLabel = this._makeLabel("W");
    this.inputW = this._makeNumInput("veditor-crop-w", "Width", (v) => {
      if (this.rect) {
        this.rect.w = v;
        this.render();
        this.callbacks.onCropChanged(this.rect);
      }
    });
    const hLabel = this._makeLabel("H");
    this.inputH = this._makeNumInput("veditor-crop-h", "Height", (v) => {
      if (this.rect) {
        this.rect.h = v;
        this.render();
        this.callbacks.onCropChanged(this.rect);
      }
    });
    numRow2.append(wLabel, this.inputW, hLabel, this.inputH);
    numSection.append(numRow1, numRow2);
    const outputSection = this._makeSection("Output");
    const outputRow = document.createElement("div");
    outputRow.className = "veditor-control-row";
    this.outputLabel = document.createElement("span");
    this.outputLabel.className = "veditor-output-label";
    this.outputLabel.textContent = "No crop";
    this.outputLabel.setAttribute("data-tool-id", "veditor-crop-output");
    this.outputLabel.setAttribute("aria-label", "Output resolution");
    outputRow.appendChild(this.outputLabel);
    outputSection.appendChild(outputRow);
    const resetRow = document.createElement("div");
    resetRow.className = "veditor-control-row";
    const resetBtn = document.createElement("button");
    resetBtn.className = "veditor-btn veditor-toggle-btn";
    resetBtn.innerHTML = `${iconReset} Reset Crop`;
    resetBtn.title = "Reset crop";
    resetBtn.setAttribute("data-tool-id", "veditor-crop-reset");
    resetBtn.setAttribute("aria-label", "Reset crop");
    resetBtn.addEventListener("click", () => {
      this.rect = null;
      this.enabled = false;
      toggleBtn.classList.remove("active");
      this._updateInputs();
      this.callbacks.onCropChanged(null);
      this.render();
    });
    resetRow.appendChild(resetBtn);
    this.controls.append(toggleSection, numSection, outputSection, resetRow);
    this.canvas.addEventListener("mousedown", (e) => this._onMouseDown(e));
    document.addEventListener("mousemove", (e) => this._onMouseMove(e));
    document.addEventListener("mouseup", () => this._onMouseUp());
  }
  /** Controls element for the side panel */
  get element() {
    return this.controls;
  }
  /** Canvas overlay element for mounting on the video monitor */
  get canvasElement() {
    return this.canvasWrapper;
  }
  setVideoDimensions(width, height) {
    this.videoWidth = width;
    this.videoHeight = height;
    this.canvas.width = width;
    this.canvas.height = height;
    this._updateInputs();
    this.render();
  }
  getRect() {
    return this.rect;
  }
  setRect(rect) {
    this.rect = rect;
    this.enabled = rect !== null;
    this._updateInputs();
    this.render();
  }
  render() {
    const ctx = this.canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    if (!this.enabled || !this.rect) return;
    const { x, y, w, h } = this.rect;
    ctx.fillStyle = "rgba(0, 0, 0, 0.6)";
    ctx.fillRect(0, 0, this.canvas.width, y);
    ctx.fillRect(0, y + h, this.canvas.width, this.canvas.height - y - h);
    ctx.fillRect(0, y, x, h);
    ctx.fillRect(x + w, y, this.canvas.width - x - w, h);
    ctx.strokeStyle = "#00ddff";
    ctx.lineWidth = 2;
    ctx.strokeRect(x, y, w, h);
    ctx.strokeStyle = "rgba(255, 255, 255, 0.3)";
    ctx.lineWidth = 1;
    for (let i = 1; i < 3; i++) {
      const gx = x + w * i / 3;
      const gy = y + h * i / 3;
      ctx.beginPath();
      ctx.moveTo(gx, y);
      ctx.lineTo(gx, y + h);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(x, gy);
      ctx.lineTo(x + w, gy);
      ctx.stroke();
    }
    ctx.fillStyle = "#00ddff";
    const corners = [
      [x, y],
      [x + w, y],
      [x, y + h],
      [x + w, y + h]
    ];
    for (const [cx, cy] of corners) {
      ctx.fillRect(cx - HANDLE_SIZE / 2, cy - HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE);
    }
  }
  destroy() {
    this.canvasWrapper.remove();
    this.controls.remove();
  }
  // ── Private ──────────────────────────────────────────────────
  _updateInputs() {
    if (this.rect) {
      this.inputX.value = String(Math.round(this.rect.x));
      this.inputY.value = String(Math.round(this.rect.y));
      this.inputW.value = String(Math.round(this.rect.w));
      this.inputH.value = String(Math.round(this.rect.h));
      this.outputLabel.textContent = `Output: ${Math.round(this.rect.w)}×${Math.round(this.rect.h)}`;
    } else {
      this.inputX.value = "";
      this.inputY.value = "";
      this.inputW.value = "";
      this.inputH.value = "";
      this.outputLabel.textContent = this.videoWidth ? `Original: ${this.videoWidth}×${this.videoHeight}` : "No crop";
    }
  }
  _onMouseDown(e) {
    if (!this.enabled || !this.rect) return;
    const pos = this._canvasPos(e);
    this.dragType = this._hitTest(pos.x, pos.y);
    if (this.dragType === "none") return;
    this.isDragging = true;
    this.dragStart = pos;
    this.origRect = { ...this.rect };
    e.preventDefault();
  }
  _onMouseMove(e) {
    if (!this.isDragging || !this.rect) return;
    const pos = this._canvasPos(e);
    const dx = pos.x - this.dragStart.x;
    const dy = pos.y - this.dragStart.y;
    switch (this.dragType) {
      case "move":
        this.rect.x = Math.max(0, Math.min(this.videoWidth - this.rect.w, this.origRect.x + dx));
        this.rect.y = Math.max(0, Math.min(this.videoHeight - this.rect.h, this.origRect.y + dy));
        break;
      case "tl":
        this.rect.x = Math.max(0, this.origRect.x + dx);
        this.rect.y = Math.max(0, this.origRect.y + dy);
        this.rect.w = Math.max(20, this.origRect.w - dx);
        this.rect.h = Math.max(20, this.origRect.h - dy);
        break;
      case "tr":
        this.rect.y = Math.max(0, this.origRect.y + dy);
        this.rect.w = Math.max(20, this.origRect.w + dx);
        this.rect.h = Math.max(20, this.origRect.h - dy);
        break;
      case "bl":
        this.rect.x = Math.max(0, this.origRect.x + dx);
        this.rect.w = Math.max(20, this.origRect.w - dx);
        this.rect.h = Math.max(20, this.origRect.h + dy);
        break;
      case "br":
        this.rect.w = Math.max(20, this.origRect.w + dx);
        this.rect.h = Math.max(20, this.origRect.h + dy);
        break;
    }
    if (this.aspectPreset !== "free" && e.shiftKey) {
      this._applyAspect(this.aspectPreset);
    }
    this._updateInputs();
    this.render();
    this.callbacks.onCropChanged(this.rect);
  }
  _onMouseUp() {
    if (this.isDragging && this.rect) {
      this.callbacks.onCropChanged(this.rect);
    }
    this.isDragging = false;
    this.dragType = "none";
  }
  _hitTest(mx, my) {
    if (!this.rect) return "none";
    const { x, y, w, h } = this.rect;
    const hs = HANDLE_SIZE;
    if (Math.abs(mx - x) < hs && Math.abs(my - y) < hs) return "tl";
    if (Math.abs(mx - (x + w)) < hs && Math.abs(my - y) < hs) return "tr";
    if (Math.abs(mx - x) < hs && Math.abs(my - (y + h)) < hs) return "bl";
    if (Math.abs(mx - (x + w)) < hs && Math.abs(my - (y + h)) < hs) return "br";
    if (mx > x && mx < x + w && my > y && my < y + h) return "move";
    return "none";
  }
  _applyAspect(preset) {
    if (!this.rect) return;
    let ratio;
    switch (preset) {
      case "16:9":
        ratio = 16 / 9;
        break;
      case "9:16":
        ratio = 9 / 16;
        break;
      case "4:3":
        ratio = 4 / 3;
        break;
      case "1:1":
        ratio = 1;
        break;
      default:
        return;
    }
    this.rect.h = Math.round(this.rect.w / ratio);
    if (this.rect.h > this.videoHeight) {
      this.rect.h = this.videoHeight;
      this.rect.w = Math.round(this.rect.h * ratio);
    }
  }
  _canvasPos(e) {
    const rect = this.canvas.getBoundingClientRect();
    const scaleX = this.canvas.width / rect.width;
    const scaleY = this.canvas.height / rect.height;
    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top) * scaleY
    };
  }
  _makeSection(title) {
    const section = document.createElement("div");
    section.className = "veditor-panel-section";
    const label = document.createElement("div");
    label.className = "veditor-section-label";
    label.textContent = title;
    section.appendChild(label);
    return section;
  }
  _makeLabel(text) {
    const label = document.createElement("span");
    label.className = "veditor-control-label";
    label.textContent = text;
    return label;
  }
  _makeNumInput(toolId, label, onChange) {
    const input = document.createElement("input");
    input.type = "number";
    input.className = "veditor-input";
    input.min = "0";
    input.setAttribute("data-tool-id", toolId);
    input.setAttribute("aria-label", label);
    input.addEventListener("change", () => {
      onChange(parseInt(input.value, 10) || 0);
      this._updateInputs();
    });
    return input;
  }
}
class SpeedControl {
  constructor(callbacks) {
    __publicField(this, "container");
    __publicField(this, "callbacks");
    __publicField(this, "slider");
    __publicField(this, "speedInput");
    __publicField(this, "label");
    __publicField(this, "reverseBtn");
    __publicField(this, "curveSelect");
    __publicField(this, "interpToggle");
    __publicField(this, "currentSegment", 0);
    __publicField(this, "speedMap", /* @__PURE__ */ new Map());
    __publicField(this, "reverseMap", /* @__PURE__ */ new Map());
    __publicField(this, "curveMap", /* @__PURE__ */ new Map());
    __publicField(this, "_interpolation", false);
    this.callbacks = callbacks;
    this.container = document.createElement("div");
    this.container.className = "veditor-speed";
    this.container.setAttribute("data-tool-id", "veditor-speed-control");
    this.container.setAttribute("aria-label", "Playback speed controls");
    const speedSection = this._makeSection("Speed");
    const sliderRow = document.createElement("div");
    sliderRow.className = "veditor-control-row";
    this.slider = document.createElement("input");
    this.slider.type = "range";
    this.slider.min = "0.1";
    this.slider.max = "8";
    this.slider.step = "0.05";
    this.slider.value = "1";
    this.slider.className = "veditor-speed-slider";
    this.slider.setAttribute("data-tool-id", "veditor-speed-slider");
    this.slider.setAttribute("aria-label", "Playback speed (0.1x to 8x)");
    this.slider.addEventListener("input", () => this._onSliderChange());
    this.speedInput = document.createElement("input");
    this.speedInput.type = "number";
    this.speedInput.className = "veditor-input veditor-speed-input";
    this.speedInput.min = "0.1";
    this.speedInput.max = "8";
    this.speedInput.step = "0.05";
    this.speedInput.value = "1.00";
    this.speedInput.setAttribute("data-tool-id", "veditor-speed-input");
    this.speedInput.setAttribute("aria-label", "Speed value");
    this.speedInput.addEventListener("change", () => {
      const val = Math.max(0.1, Math.min(8, parseFloat(this.speedInput.value) || 1));
      this.slider.value = String(val);
      this._setSpeed(val);
    });
    this.label = document.createElement("span");
    this.label.className = "veditor-speed-value";
    this.label.textContent = "1.00x";
    sliderRow.append(this.slider, this.speedInput);
    const presetRow = document.createElement("div");
    presetRow.className = "veditor-preset-row";
    const presets = [0.25, 0.5, 0.75, 1, 1.5, 2, 4];
    presets.forEach((p) => {
      const btn = document.createElement("button");
      btn.className = "veditor-btn veditor-preset-btn";
      btn.textContent = `${p}x`;
      btn.title = `Set speed to ${p}x`;
      btn.setAttribute("data-tool-id", `veditor-speed-preset-${String(p).replace(".", "")}`);
      btn.setAttribute("aria-label", `Set speed to ${p}x`);
      btn.addEventListener("click", () => {
        this.slider.value = String(p);
        this.speedInput.value = p.toFixed(2);
        this._setSpeed(p);
      });
      presetRow.appendChild(btn);
    });
    speedSection.append(sliderRow, presetRow);
    const reverseSection = this._makeSection("Reverse");
    this.reverseBtn = document.createElement("button");
    this.reverseBtn.className = "veditor-btn veditor-toggle-btn";
    this.reverseBtn.innerHTML = `${iconReverse} Reversed`;
    this.reverseBtn.title = "Toggle reverse playback";
    this.reverseBtn.setAttribute("data-tool-id", "veditor-speed-reverse");
    this.reverseBtn.setAttribute("aria-label", "Toggle reverse playback");
    this.reverseBtn.setAttribute("aria-pressed", "false");
    this.reverseBtn.addEventListener("click", () => this._toggleReverse());
    reverseSection.appendChild(this.reverseBtn);
    const curveSection = this._makeSection("Speed Curve");
    const curveRow = document.createElement("div");
    curveRow.className = "veditor-control-row";
    const curveIcon = document.createElement("span");
    curveIcon.innerHTML = iconCurve;
    curveIcon.className = "veditor-control-icon";
    this.curveSelect = document.createElement("select");
    this.curveSelect.className = "veditor-select";
    this.curveSelect.setAttribute("data-tool-id", "veditor-speed-curve");
    this.curveSelect.setAttribute("aria-label", "Speed curve type");
    const curves = [
      { val: "linear", label: "Linear" },
      { val: "ease-in", label: "Ease In" },
      { val: "ease-out", label: "Ease Out" },
      { val: "ease-in-out", label: "Ease In-Out" }
    ];
    curves.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c.val;
      opt.textContent = c.label;
      this.curveSelect.appendChild(opt);
    });
    this.curveSelect.addEventListener("change", () => {
      var _a, _b;
      const curve = this.curveSelect.value;
      this.curveMap.set(this.currentSegment, curve);
      (_b = (_a = this.callbacks).onCurveChanged) == null ? void 0 : _b.call(_a, this.currentSegment, curve);
    });
    curveRow.append(curveIcon, this.curveSelect);
    curveSection.appendChild(curveRow);
    const interpSection = this._makeSection("Frame Interpolation");
    const interpRow = document.createElement("div");
    interpRow.className = "veditor-control-row";
    const interpIcon = document.createElement("span");
    interpIcon.innerHTML = iconFilm;
    interpIcon.className = "veditor-control-icon";
    const interpLabel = document.createElement("label");
    interpLabel.className = "veditor-toggle-label";
    interpLabel.textContent = "Enable smooth slow-motion";
    this.interpToggle = document.createElement("input");
    this.interpToggle.type = "checkbox";
    this.interpToggle.className = "veditor-checkbox";
    this.interpToggle.setAttribute("data-tool-id", "veditor-speed-interpolation");
    this.interpToggle.setAttribute("aria-label", "Enable frame interpolation for smooth slow-motion");
    this.interpToggle.addEventListener("change", () => {
      var _a, _b;
      this._interpolation = this.interpToggle.checked;
      (_b = (_a = this.callbacks).onInterpolationChanged) == null ? void 0 : _b.call(_a, this._interpolation);
    });
    interpRow.append(interpIcon, interpLabel, this.interpToggle);
    interpSection.appendChild(interpRow);
    this.container.append(speedSection, reverseSection, curveSection, interpSection);
  }
  get element() {
    return this.container;
  }
  /** Switch context to a different segment. */
  setActiveSegment(index) {
    this.currentSegment = index;
    const speed = this.speedMap.get(index) ?? 1;
    this.slider.value = String(speed);
    this.speedInput.value = speed.toFixed(2);
    this.label.textContent = `${speed.toFixed(2)}x`;
    const reversed = this.reverseMap.get(index) ?? false;
    this.reverseBtn.classList.toggle("active", reversed);
    this.reverseBtn.setAttribute("aria-pressed", String(reversed));
    const curve = this.curveMap.get(index) ?? "linear";
    this.curveSelect.value = curve;
  }
  /** Get the full speed map as a JSON-suitable object. */
  getSpeedMap() {
    const result = {};
    for (const [idx, speed] of this.speedMap) {
      if (Math.abs(speed - 1) > 0.01) {
        result[String(idx)] = speed;
      }
    }
    return result;
  }
  /** Load speed map from a parsed object. */
  loadSpeedMap(map) {
    this.speedMap.clear();
    for (const [key, val] of Object.entries(map)) {
      this.speedMap.set(parseInt(key, 10), val);
    }
    this.setActiveSegment(this.currentSegment);
  }
  /** Check if frame interpolation is enabled */
  get interpolation() {
    return this._interpolation;
  }
  /** Reset all speeds to 1x. */
  reset() {
    this.speedMap.clear();
    this.reverseMap.clear();
    this.curveMap.clear();
    this._interpolation = false;
    this.interpToggle.checked = false;
    this.slider.value = "1";
    this.speedInput.value = "1.00";
    this.label.textContent = "1.00x";
    this.reverseBtn.classList.remove("active");
    this.reverseBtn.setAttribute("aria-pressed", "false");
    this.curveSelect.value = "linear";
  }
  destroy() {
    this.container.remove();
  }
  // ── Private ──────────────────────────────────────────────────
  _setSpeed(speed) {
    this.speedMap.set(this.currentSegment, speed);
    this.label.textContent = `${speed.toFixed(2)}x`;
    this.callbacks.onSpeedChanged(this.currentSegment, speed);
  }
  _onSliderChange() {
    const speed = parseFloat(this.slider.value);
    this.speedInput.value = speed.toFixed(2);
    this._setSpeed(speed);
  }
  _toggleReverse() {
    var _a, _b;
    const current = this.reverseMap.get(this.currentSegment) ?? false;
    const next = !current;
    this.reverseMap.set(this.currentSegment, next);
    this.reverseBtn.classList.toggle("active", next);
    this.reverseBtn.setAttribute("aria-pressed", String(next));
    (_b = (_a = this.callbacks).onReverseChanged) == null ? void 0 : _b.call(_a, this.currentSegment, next);
  }
  _makeSection(title) {
    const section = document.createElement("div");
    section.className = "veditor-panel-section";
    const label = document.createElement("div");
    label.className = "veditor-section-label";
    label.textContent = title;
    section.appendChild(label);
    return section;
  }
}
class AudioMixer {
  constructor(callbacks) {
    __publicField(this, "container");
    __publicField(this, "callbacks");
    __publicField(this, "slider");
    __publicField(this, "label");
    __publicField(this, "muteBtn");
    __publicField(this, "fadeInSlider");
    __publicField(this, "fadeInLabel");
    __publicField(this, "fadeOutSlider");
    __publicField(this, "fadeOutLabel");
    __publicField(this, "eqSelect");
    __publicField(this, "isMuted", false);
    __publicField(this, "lastVolume", 1);
    this.callbacks = callbacks;
    this.container = document.createElement("div");
    this.container.className = "veditor-audio";
    this.container.setAttribute("data-tool-id", "veditor-audio-mixer");
    this.container.setAttribute("aria-label", "Audio controls");
    const volSection = this._makeSection("Volume");
    const volRow = document.createElement("div");
    volRow.className = "veditor-control-row";
    this.muteBtn = document.createElement("button");
    this.muteBtn.className = "veditor-btn veditor-mute-btn";
    this.muteBtn.innerHTML = iconVolume;
    this.muteBtn.title = "Mute / Unmute (M)";
    this.muteBtn.setAttribute("data-tool-id", "veditor-mute-btn");
    this.muteBtn.setAttribute("aria-label", "Mute / Unmute audio (M)");
    this.muteBtn.addEventListener("click", () => this._toggleMute());
    this.slider = document.createElement("input");
    this.slider.type = "range";
    this.slider.min = "0";
    this.slider.max = "2";
    this.slider.step = "0.05";
    this.slider.value = "1";
    this.slider.className = "veditor-volume-slider";
    this.slider.setAttribute("data-tool-id", "veditor-volume-slider");
    this.slider.setAttribute("aria-label", "Volume level (0% to 200%)");
    this.slider.addEventListener("input", () => {
      const vol = parseFloat(this.slider.value);
      this.lastVolume = vol;
      this.isMuted = vol < 0.01;
      this.muteBtn.innerHTML = this.isMuted ? iconMuted : iconVolume;
      this.label.textContent = `${Math.round(vol * 100)}%`;
      this.callbacks.onVolumeChanged(vol);
    });
    this.label = document.createElement("span");
    this.label.className = "veditor-volume-label";
    this.label.textContent = "100%";
    this.label.setAttribute("data-tool-id", "veditor-volume-label");
    volRow.append(this.muteBtn, this.slider, this.label);
    volSection.appendChild(volRow);
    const fadeInSection = this._makeSection("Fade In");
    const fadeInRow = document.createElement("div");
    fadeInRow.className = "veditor-control-row";
    this.fadeInSlider = document.createElement("input");
    this.fadeInSlider.type = "range";
    this.fadeInSlider.min = "0";
    this.fadeInSlider.max = "5";
    this.fadeInSlider.step = "0.1";
    this.fadeInSlider.value = "0";
    this.fadeInSlider.className = "veditor-fade-slider";
    this.fadeInSlider.setAttribute("data-tool-id", "veditor-fade-in-slider");
    this.fadeInSlider.setAttribute("aria-label", "Audio fade in duration (0 to 5 seconds)");
    this.fadeInSlider.addEventListener("input", () => {
      var _a, _b;
      const val = parseFloat(this.fadeInSlider.value);
      this.fadeInLabel.textContent = `${val.toFixed(1)}s`;
      (_b = (_a = this.callbacks).onFadeInChanged) == null ? void 0 : _b.call(_a, val);
    });
    this.fadeInLabel = document.createElement("span");
    this.fadeInLabel.className = "veditor-fade-label";
    this.fadeInLabel.textContent = "0.0s";
    this.fadeInLabel.setAttribute("data-tool-id", "veditor-fade-in-label");
    fadeInRow.append(this.fadeInSlider, this.fadeInLabel);
    fadeInSection.appendChild(fadeInRow);
    const fadeOutSection = this._makeSection("Fade Out");
    const fadeOutRow = document.createElement("div");
    fadeOutRow.className = "veditor-control-row";
    this.fadeOutSlider = document.createElement("input");
    this.fadeOutSlider.type = "range";
    this.fadeOutSlider.min = "0";
    this.fadeOutSlider.max = "5";
    this.fadeOutSlider.step = "0.1";
    this.fadeOutSlider.value = "0";
    this.fadeOutSlider.className = "veditor-fade-slider";
    this.fadeOutSlider.setAttribute("data-tool-id", "veditor-fade-out-slider");
    this.fadeOutSlider.setAttribute("aria-label", "Audio fade out duration (0 to 5 seconds)");
    this.fadeOutSlider.addEventListener("input", () => {
      var _a, _b;
      const val = parseFloat(this.fadeOutSlider.value);
      this.fadeOutLabel.textContent = `${val.toFixed(1)}s`;
      (_b = (_a = this.callbacks).onFadeOutChanged) == null ? void 0 : _b.call(_a, val);
    });
    this.fadeOutLabel = document.createElement("span");
    this.fadeOutLabel.className = "veditor-fade-label";
    this.fadeOutLabel.textContent = "0.0s";
    this.fadeOutLabel.setAttribute("data-tool-id", "veditor-fade-out-label");
    fadeOutRow.append(this.fadeOutSlider, this.fadeOutLabel);
    fadeOutSection.appendChild(fadeOutRow);
    const eqSection = this._makeSection("EQ Preset");
    const eqRow = document.createElement("div");
    eqRow.className = "veditor-control-row";
    const eqIcon = document.createElement("span");
    eqIcon.innerHTML = iconMusic;
    eqIcon.className = "veditor-control-icon";
    this.eqSelect = document.createElement("select");
    this.eqSelect.className = "veditor-select";
    this.eqSelect.setAttribute("data-tool-id", "veditor-eq-preset");
    this.eqSelect.setAttribute("aria-label", "Audio EQ preset");
    const eqPresets = [
      { val: "flat", label: "Flat (No EQ)" },
      { val: "voice", label: "Voice Enhancement" },
      { val: "music", label: "Music" },
      { val: "bass-boost", label: "Bass Boost" }
    ];
    eqPresets.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.val;
      opt.textContent = p.label;
      this.eqSelect.appendChild(opt);
    });
    this.eqSelect.addEventListener("change", () => {
      var _a, _b;
      (_b = (_a = this.callbacks).onEQChanged) == null ? void 0 : _b.call(_a, this.eqSelect.value);
    });
    eqRow.append(eqIcon, this.eqSelect);
    eqSection.appendChild(eqRow);
    this.container.append(volSection, fadeInSection, fadeOutSection, eqSection);
  }
  get element() {
    return this.container;
  }
  getVolume() {
    return this.isMuted ? 0 : parseFloat(this.slider.value);
  }
  setVolume(volume) {
    this.slider.value = String(volume);
    this.lastVolume = volume;
    this.isMuted = volume < 0.01;
    this.muteBtn.innerHTML = this.isMuted ? iconMuted : iconVolume;
    this.label.textContent = `${Math.round(volume * 100)}%`;
  }
  getFadeIn() {
    return parseFloat(this.fadeInSlider.value);
  }
  getFadeOut() {
    return parseFloat(this.fadeOutSlider.value);
  }
  getEQPreset() {
    return this.eqSelect.value;
  }
  destroy() {
    this.container.remove();
  }
  // ── Private ──────────────────────────────────────────────────
  _toggleMute() {
    this.isMuted = !this.isMuted;
    if (this.isMuted) {
      this.lastVolume = parseFloat(this.slider.value);
      this.slider.value = "0";
      this.muteBtn.innerHTML = iconMuted;
      this.label.textContent = "0%";
      this.callbacks.onVolumeChanged(0);
    } else {
      this.slider.value = String(this.lastVolume);
      this.muteBtn.innerHTML = iconVolume;
      this.label.textContent = `${Math.round(this.lastVolume * 100)}%`;
      this.callbacks.onVolumeChanged(this.lastVolume);
    }
  }
  _makeSection(title) {
    const section = document.createElement("div");
    section.className = "veditor-panel-section";
    const label = document.createElement("div");
    label.className = "veditor-section-label";
    label.textContent = title;
    section.appendChild(label);
    return section;
  }
}
const POSITION_PRESETS = [
  { label: "Top", x: "center", y: "top" },
  { label: "Center", x: "center", y: "center" },
  { label: "Bottom", x: "center", y: "bottom" },
  { label: "Lower Third", x: "center", y: "75%" }
];
const FONT_FAMILIES = [
  "sans-serif",
  "serif",
  "monospace",
  "Arial",
  "Helvetica",
  "Georgia",
  "Courier New",
  "Impact"
];
const TEXT_PRESETS = {
  subtitle: {
    text: "Subtitle text",
    font: "sans-serif",
    font_size: 32,
    color: "#ffffff",
    alignment: "center",
    x: "center",
    y: "bottom",
    bold: false,
    italic: false,
    backgroundColor: "#000000",
    backgroundOpacity: 0.6,
    outlineColor: null,
    outlineWidth: 0
  },
  title: {
    text: "Title Card",
    font: "serif",
    font_size: 72,
    color: "#ffffff",
    alignment: "center",
    x: "center",
    y: "center",
    bold: true,
    italic: false,
    backgroundColor: null,
    backgroundOpacity: 0,
    outlineColor: "#000000",
    outlineWidth: 3
  },
  lowerthird: {
    text: "Name or Title",
    font: "sans-serif",
    font_size: 28,
    color: "#ffffff",
    alignment: "left",
    x: "left",
    y: "75%",
    bold: true,
    italic: false,
    backgroundColor: "#1a1a2e",
    backgroundOpacity: 0.8,
    outlineColor: null,
    outlineWidth: 0
  },
  credit: {
    text: "Directed by\nYour Name",
    font: "serif",
    font_size: 42,
    color: "#ffffff",
    alignment: "center",
    x: "center",
    y: "center",
    bold: false,
    italic: true,
    backgroundColor: null,
    backgroundOpacity: 0,
    outlineColor: null,
    outlineWidth: 0
  }
};
class TextOverlayPanel {
  constructor(callbacks) {
    __publicField(this, "container");
    __publicField(this, "listEl");
    __publicField(this, "callbacks");
    __publicField(this, "overlays", []);
    this.callbacks = callbacks;
    this.container = document.createElement("div");
    this.container.className = "veditor-text-panel";
    this.container.setAttribute("data-tool-id", "veditor-text-panel");
    this.container.setAttribute("aria-label", "Text overlay editor");
    const header = document.createElement("div");
    header.className = "veditor-text-header";
    header.innerHTML = "<span>Text Overlays</span>";
    const addBtn = document.createElement("button");
    addBtn.className = "veditor-btn";
    addBtn.innerHTML = `${iconPlus} Add Text`;
    addBtn.setAttribute("data-tool-id", "veditor-text-add");
    addBtn.setAttribute("aria-label", "Add new text overlay");
    addBtn.title = "Add new text overlay";
    addBtn.addEventListener("click", () => this._addOverlay());
    header.appendChild(addBtn);
    const presetRow = document.createElement("div");
    presetRow.className = "veditor-control-row";
    presetRow.style.marginBottom = "8px";
    const presetLabel = document.createElement("span");
    presetLabel.className = "veditor-control-label";
    presetLabel.textContent = "Preset";
    const presetSelect = document.createElement("select");
    presetSelect.className = "veditor-select";
    presetSelect.setAttribute("data-tool-id", "veditor-text-preset");
    presetSelect.setAttribute("aria-label", "Text overlay preset");
    const defaultOpt = document.createElement("option");
    defaultOpt.value = "";
    defaultOpt.textContent = "Choose a preset…";
    presetSelect.appendChild(defaultOpt);
    for (const [key, preset] of Object.entries(TEXT_PRESETS)) {
      const opt = document.createElement("option");
      opt.value = key;
      opt.textContent = key === "lowerthird" ? "Lower Third" : key.charAt(0).toUpperCase() + key.slice(1);
      opt.setAttribute("data-tool-id", `veditor-text-preset-${key}`);
      presetSelect.appendChild(opt);
    }
    presetSelect.addEventListener("change", () => {
      const preset = TEXT_PRESETS[presetSelect.value];
      if (preset) {
        this._addOverlayFromPreset(preset);
        presetSelect.value = "";
      }
    });
    presetRow.append(presetLabel, presetSelect);
    this.listEl = document.createElement("div");
    this.listEl.className = "veditor-text-list";
    this.listEl.setAttribute("data-tool-id", "veditor-text-list");
    this.listEl.setAttribute("aria-label", "List of text overlays");
    this.container.append(header, presetRow, this.listEl);
  }
  get element() {
    return this.container;
  }
  getOverlays() {
    return [...this.overlays];
  }
  loadOverlays(overlays) {
    this.overlays = overlays.map((o) => ({ ...o }));
    this._renderList();
  }
  destroy() {
    this.container.remove();
  }
  // ── Private ──────────────────────────────────────────────────
  _addOverlay() {
    this.overlays.push({
      text: "Your text here",
      x: "center",
      y: "bottom",
      font_size: 48,
      color: "#ffffff",
      start_time: null,
      end_time: null,
      font: "sans-serif",
      alignment: "center",
      bold: false,
      italic: false,
      backgroundColor: null,
      backgroundOpacity: 0.6,
      outlineColor: null,
      outlineWidth: 2
    });
    this._renderList();
    this._notify();
  }
  _addOverlayFromPreset(preset) {
    const defaults = {
      text: "Your text here",
      x: "center",
      y: "bottom",
      font_size: 48,
      color: "#ffffff",
      start_time: null,
      end_time: null,
      font: "sans-serif",
      alignment: "center",
      bold: false,
      italic: false,
      backgroundColor: null,
      backgroundOpacity: 0.6,
      outlineColor: null,
      outlineWidth: 2
    };
    this.overlays.push({ ...defaults, ...preset });
    this._renderList();
    this._notify();
  }
  _removeOverlay(index) {
    this.overlays.splice(index, 1);
    this._renderList();
    this._notify();
  }
  _renderList() {
    this.listEl.innerHTML = "";
    this.overlays.forEach((ov, idx) => {
      const card = document.createElement("div");
      card.className = "veditor-text-card";
      card.setAttribute("data-tool-id", `veditor-text-card-${idx}`);
      card.setAttribute("aria-label", `Text overlay ${idx + 1}`);
      const cardHeader = document.createElement("div");
      cardHeader.className = "veditor-text-card-header";
      const cardTitle = document.createElement("span");
      cardTitle.className = "veditor-text-card-title";
      cardTitle.textContent = `Text ${idx + 1}`;
      const delBtn = document.createElement("button");
      delBtn.className = "veditor-btn veditor-text-del";
      delBtn.innerHTML = iconClose;
      delBtn.title = `Remove text overlay ${idx + 1}`;
      delBtn.setAttribute("data-tool-id", `veditor-text-del-${idx}`);
      delBtn.setAttribute("aria-label", `Remove text overlay ${idx + 1}`);
      delBtn.addEventListener("click", () => this._removeOverlay(idx));
      cardHeader.append(cardTitle, delBtn);
      const textInput = document.createElement("textarea");
      textInput.className = "veditor-text-textarea";
      textInput.value = ov.text;
      textInput.rows = 2;
      textInput.placeholder = "Enter text...";
      textInput.setAttribute("data-tool-id", `veditor-text-input-${idx}`);
      textInput.setAttribute("aria-label", `Text content for overlay ${idx + 1}`);
      textInput.addEventListener("input", () => {
        ov.text = textInput.value;
        this._notify();
      });
      const fontRow = document.createElement("div");
      fontRow.className = "veditor-control-row veditor-font-row";
      const fontSelect = this._makeSelect(
        FONT_FAMILIES,
        ov.font || "sans-serif",
        (val) => {
          ov.font = val;
          this._notify();
        },
        `veditor-text-font-${idx}`,
        "Font family"
      );
      fontSelect.className = "veditor-select veditor-font-select";
      const sizeInput = document.createElement("input");
      sizeInput.type = "number";
      sizeInput.className = "veditor-input veditor-size-input";
      sizeInput.value = String(ov.font_size);
      sizeInput.min = "8";
      sizeInput.max = "200";
      sizeInput.setAttribute("data-tool-id", `veditor-text-size-${idx}`);
      sizeInput.setAttribute("aria-label", "Font size");
      sizeInput.addEventListener("change", () => {
        ov.font_size = parseInt(sizeInput.value, 10) || 48;
        this._notify();
      });
      const colorInput = document.createElement("input");
      colorInput.type = "color";
      colorInput.value = this._nameToHex(ov.color);
      colorInput.className = "veditor-color-input";
      colorInput.setAttribute("data-tool-id", `veditor-text-color-${idx}`);
      colorInput.setAttribute("aria-label", "Text color");
      colorInput.addEventListener("change", () => {
        ov.color = colorInput.value;
        this._notify();
      });
      fontRow.append(fontSelect, sizeInput, colorInput);
      const styleRow = document.createElement("div");
      styleRow.className = "veditor-control-row veditor-style-row";
      const boldBtn = this._makeToggle(iconBold, "Bold", ov.bold, (val) => {
        ov.bold = val;
        this._notify();
      }, `veditor-text-bold-${idx}`);
      const italicBtn = this._makeToggle(iconItalic, "Italic", ov.italic, (val) => {
        ov.italic = val;
        this._notify();
      }, `veditor-text-italic-${idx}`);
      const sep = document.createElement("div");
      sep.className = "veditor-toolbar-sep";
      const alignLeftBtn = this._makeAlignBtn(iconAlignLeft, "left", ov, idx);
      const alignCenterBtn = this._makeAlignBtn(iconAlignCenter, "center", ov, idx);
      const alignRightBtn = this._makeAlignBtn(iconAlignRight, "right", ov, idx);
      styleRow.append(boldBtn, italicBtn, sep, alignLeftBtn, alignCenterBtn, alignRightBtn);
      const posRow = document.createElement("div");
      posRow.className = "veditor-control-row veditor-pos-row";
      const posLabel = document.createElement("span");
      posLabel.className = "veditor-control-label";
      posLabel.textContent = "Position";
      POSITION_PRESETS.forEach((preset) => {
        const btn = document.createElement("button");
        btn.className = "veditor-btn veditor-preset-btn";
        if (ov.x === preset.x && ov.y === preset.y) btn.classList.add("active");
        btn.textContent = preset.label;
        btn.title = `Position: ${preset.label}`;
        btn.setAttribute("data-tool-id", `veditor-text-pos-${preset.label.toLowerCase().replace(" ", "-")}-${idx}`);
        btn.setAttribute("aria-label", `Position: ${preset.label}`);
        btn.addEventListener("click", () => {
          ov.x = preset.x;
          ov.y = preset.y;
          this._renderList();
          this._notify();
        });
        posRow.appendChild(btn);
      });
      posRow.prepend(posLabel);
      const bgRow = document.createElement("div");
      bgRow.className = "veditor-control-row veditor-bg-row";
      const bgLabel = document.createElement("label");
      bgLabel.className = "veditor-toggle-label";
      const bgCheck = document.createElement("input");
      bgCheck.type = "checkbox";
      bgCheck.className = "veditor-checkbox";
      bgCheck.checked = ov.backgroundColor !== null;
      bgCheck.setAttribute("data-tool-id", `veditor-text-bg-toggle-${idx}`);
      bgCheck.setAttribute("aria-label", "Enable text background");
      bgCheck.addEventListener("change", () => {
        ov.backgroundColor = bgCheck.checked ? "#000000" : null;
        this._renderList();
        this._notify();
      });
      bgLabel.append(bgCheck, document.createTextNode(" Background"));
      const outlineLabel = document.createElement("label");
      outlineLabel.className = "veditor-toggle-label";
      const outlineCheck = document.createElement("input");
      outlineCheck.type = "checkbox";
      outlineCheck.className = "veditor-checkbox";
      outlineCheck.checked = ov.outlineColor !== null;
      outlineCheck.setAttribute("data-tool-id", `veditor-text-outline-toggle-${idx}`);
      outlineCheck.setAttribute("aria-label", "Enable text outline");
      outlineCheck.addEventListener("change", () => {
        ov.outlineColor = outlineCheck.checked ? "#000000" : null;
        this._renderList();
        this._notify();
      });
      outlineLabel.append(outlineCheck, document.createTextNode(" Outline"));
      bgRow.append(bgLabel, outlineLabel);
      if (ov.backgroundColor !== null) {
        const bgColorRow = document.createElement("div");
        bgColorRow.className = "veditor-control-row";
        const bgColorInput = document.createElement("input");
        bgColorInput.type = "color";
        bgColorInput.value = ov.backgroundColor;
        bgColorInput.className = "veditor-color-input";
        bgColorInput.setAttribute("data-tool-id", `veditor-text-bg-color-${idx}`);
        bgColorInput.addEventListener("change", () => {
          ov.backgroundColor = bgColorInput.value;
          this._notify();
        });
        const opacitySlider = document.createElement("input");
        opacitySlider.type = "range";
        opacitySlider.min = "0";
        opacitySlider.max = "1";
        opacitySlider.step = "0.05";
        opacitySlider.value = String(ov.backgroundOpacity);
        opacitySlider.className = "veditor-fade-slider";
        opacitySlider.setAttribute("data-tool-id", `veditor-text-bg-opacity-${idx}`);
        opacitySlider.setAttribute("aria-label", "Background opacity");
        opacitySlider.addEventListener("input", () => {
          ov.backgroundOpacity = parseFloat(opacitySlider.value);
          this._notify();
        });
        const opacityLabel = document.createElement("span");
        opacityLabel.className = "veditor-fade-label";
        opacityLabel.textContent = `${Math.round(ov.backgroundOpacity * 100)}%`;
        bgColorRow.append(bgColorInput, opacitySlider, opacityLabel);
        bgRow.after(bgColorRow);
        card.append(cardHeader, textInput, fontRow, styleRow, posRow, bgRow, bgColorRow);
      } else {
        card.append(cardHeader, textInput, fontRow, styleRow, posRow, bgRow);
      }
      if (ov.outlineColor !== null) {
        const outlineRow = document.createElement("div");
        outlineRow.className = "veditor-control-row";
        const outlineColorInput = document.createElement("input");
        outlineColorInput.type = "color";
        outlineColorInput.value = ov.outlineColor;
        outlineColorInput.className = "veditor-color-input";
        outlineColorInput.setAttribute("data-tool-id", `veditor-text-outline-color-${idx}`);
        outlineColorInput.addEventListener("change", () => {
          ov.outlineColor = outlineColorInput.value;
          this._notify();
        });
        const widthInput = document.createElement("input");
        widthInput.type = "number";
        widthInput.className = "veditor-input";
        widthInput.value = String(ov.outlineWidth);
        widthInput.min = "1";
        widthInput.max = "10";
        widthInput.setAttribute("data-tool-id", `veditor-text-outline-width-${idx}`);
        widthInput.setAttribute("aria-label", "Outline width");
        widthInput.addEventListener("change", () => {
          ov.outlineWidth = parseInt(widthInput.value, 10) || 2;
          this._notify();
        });
        const wLabel = document.createElement("span");
        wLabel.className = "veditor-control-label";
        wLabel.textContent = "px";
        outlineRow.append(outlineColorInput, widthInput, wLabel);
        card.appendChild(outlineRow);
      }
      const timeRow = document.createElement("div");
      timeRow.className = "veditor-control-row veditor-time-row";
      const startLabel = document.createElement("span");
      startLabel.className = "veditor-control-label";
      startLabel.textContent = "Start";
      const startInput = document.createElement("input");
      startInput.type = "number";
      startInput.className = "veditor-input veditor-time-input";
      startInput.value = ov.start_time !== null ? String(ov.start_time) : "";
      startInput.placeholder = "0.0";
      startInput.step = "0.1";
      startInput.min = "0";
      startInput.setAttribute("data-tool-id", `veditor-text-start-${idx}`);
      startInput.setAttribute("aria-label", "Start time (seconds)");
      startInput.addEventListener("change", () => {
        ov.start_time = startInput.value ? parseFloat(startInput.value) : null;
        this._notify();
      });
      const endLabel = document.createElement("span");
      endLabel.className = "veditor-control-label";
      endLabel.textContent = "End";
      const endInput = document.createElement("input");
      endInput.type = "number";
      endInput.className = "veditor-input veditor-time-input";
      endInput.value = ov.end_time !== null ? String(ov.end_time) : "";
      endInput.placeholder = "∞";
      endInput.step = "0.1";
      endInput.min = "0";
      endInput.setAttribute("data-tool-id", `veditor-text-end-${idx}`);
      endInput.setAttribute("aria-label", "End time (seconds)");
      endInput.addEventListener("change", () => {
        ov.end_time = endInput.value ? parseFloat(endInput.value) : null;
        this._notify();
      });
      const sLabel = document.createElement("span");
      sLabel.className = "veditor-time-unit";
      sLabel.textContent = "s";
      const eLabel = document.createElement("span");
      eLabel.className = "veditor-time-unit";
      eLabel.textContent = "s";
      timeRow.append(startLabel, startInput, sLabel, endLabel, endInput, eLabel);
      card.appendChild(timeRow);
      this.listEl.appendChild(card);
    });
  }
  _makeSelect(options, value, onChange, toolId, label) {
    const select = document.createElement("select");
    select.className = "veditor-select";
    select.setAttribute("data-tool-id", toolId);
    select.setAttribute("aria-label", label);
    options.forEach((opt) => {
      const o = document.createElement("option");
      o.value = opt;
      o.textContent = opt;
      if (opt === value) o.selected = true;
      select.appendChild(o);
    });
    select.addEventListener("change", () => onChange(select.value));
    return select;
  }
  _makeToggle(icon, label, active, onChange, toolId) {
    const btn = document.createElement("button");
    btn.className = "veditor-btn veditor-style-btn";
    if (active) btn.classList.add("active");
    btn.innerHTML = icon;
    btn.title = label;
    btn.setAttribute("data-tool-id", toolId);
    btn.setAttribute("aria-label", label);
    btn.setAttribute("aria-pressed", String(active));
    btn.addEventListener("click", () => {
      const next = !btn.classList.contains("active");
      btn.classList.toggle("active", next);
      btn.setAttribute("aria-pressed", String(next));
      onChange(next);
    });
    return btn;
  }
  _makeAlignBtn(icon, align, ov, idx) {
    const btn = document.createElement("button");
    btn.className = "veditor-btn veditor-style-btn";
    if (ov.alignment === align) btn.classList.add("active");
    btn.innerHTML = icon;
    btn.title = `Align ${align}`;
    btn.setAttribute("data-tool-id", `veditor-text-align-${align}-${idx}`);
    btn.setAttribute("aria-label", `Align ${align}`);
    btn.addEventListener("click", () => {
      ov.alignment = align;
      this._renderList();
      this._notify();
    });
    return btn;
  }
  _nameToHex(color) {
    const map = {
      white: "#ffffff",
      black: "#000000",
      red: "#ff0000",
      green: "#00ff00",
      blue: "#0000ff",
      yellow: "#ffff00"
    };
    return map[color.toLowerCase()] ?? color;
  }
  _notify() {
    this.callbacks.onOverlaysChanged([...this.overlays]);
  }
}
const MAX_UNDO_DEPTH = 50;
class UndoManager {
  constructor(callbacks) {
    __publicField(this, "undoStack", []);
    __publicField(this, "redoStack", []);
    __publicField(this, "callbacks");
    __publicField(this, "_keyHandler", null);
    this.callbacks = callbacks;
    this._keyHandler = (e) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "z") {
        e.preventDefault();
        if (e.shiftKey) {
          this.redo();
        } else {
          this.undo();
        }
      }
    };
    document.addEventListener("keydown", this._keyHandler);
  }
  /** Save the current state to the undo stack. */
  push(state) {
    this.undoStack.push(JSON.parse(JSON.stringify(state)));
    if (this.undoStack.length > MAX_UNDO_DEPTH) {
      this.undoStack.shift();
    }
    this.redoStack = [];
  }
  /** Undo: pop from undo stack, push current to redo. */
  undo() {
    if (this.undoStack.length < 2) return false;
    const current = this.undoStack.pop();
    this.redoStack.push(current);
    const prev = this.undoStack[this.undoStack.length - 1];
    this.callbacks.onRestore(JSON.parse(JSON.stringify(prev)));
    return true;
  }
  /** Redo: pop from redo stack, push to undo. */
  redo() {
    if (this.redoStack.length === 0) return false;
    const state = this.redoStack.pop();
    this.undoStack.push(state);
    this.callbacks.onRestore(JSON.parse(JSON.stringify(state)));
    return true;
  }
  /** Clear all history. */
  clear() {
    this.undoStack = [];
    this.redoStack = [];
  }
  get canUndo() {
    return this.undoStack.length > 1;
  }
  get canRedo() {
    return this.redoStack.length > 0;
  }
  destroy() {
    if (this._keyHandler) {
      document.removeEventListener("keydown", this._keyHandler);
      this._keyHandler = null;
    }
  }
}
class ToolsPanel {
  constructor(tabs) {
    __publicField(this, "container");
    __publicField(this, "tabBar");
    __publicField(this, "contentArea");
    __publicField(this, "tabs", []);
    __publicField(this, "tabButtons", /* @__PURE__ */ new Map());
    __publicField(this, "tabPanes", /* @__PURE__ */ new Map());
    __publicField(this, "activeTabId", "");
    this.tabs = tabs;
    this.container = document.createElement("div");
    this.container.className = "veditor-modal-tools";
    this.container.setAttribute("role", "region");
    this.container.setAttribute("aria-label", "Editing tools panel");
    this.container.setAttribute("data-tool-id", "veditor-tools-panel");
    this.tabBar = document.createElement("div");
    this.tabBar.className = "veditor-tabs";
    this.tabBar.setAttribute("role", "tablist");
    this.tabBar.setAttribute("aria-label", "Tool tabs");
    this.contentArea = document.createElement("div");
    this.contentArea.className = "veditor-tab-content";
    for (const tab of tabs) {
      const btn = document.createElement("button");
      btn.className = "veditor-tab";
      btn.innerHTML = `${tab.icon} ${tab.label}`;
      btn.setAttribute("role", "tab");
      btn.setAttribute("aria-selected", "false");
      btn.setAttribute("aria-controls", `veditor-pane-${tab.id}`);
      btn.setAttribute("data-tool-id", `veditor-tab-${tab.id}`);
      btn.setAttribute("aria-label", `${tab.label} tools`);
      btn.title = `${tab.label} tools`;
      btn.addEventListener("click", () => this.activateTab(tab.id));
      this.tabBar.appendChild(btn);
      this.tabButtons.set(tab.id, btn);
      const pane = document.createElement("div");
      pane.className = "veditor-tab-pane";
      pane.id = `veditor-pane-${tab.id}`;
      pane.setAttribute("role", "tabpanel");
      pane.setAttribute("aria-label", `${tab.label} options`);
      pane.appendChild(tab.content);
      this.contentArea.appendChild(pane);
      this.tabPanes.set(tab.id, pane);
    }
    this.container.append(this.tabBar, this.contentArea);
    if (tabs.length > 0) {
      this.activateTab(tabs[0].id);
    }
  }
  get element() {
    return this.container;
  }
  activateTab(tabId) {
    if (this.activeTabId === tabId) return;
    this.activeTabId = tabId;
    for (const [id, btn] of this.tabButtons) {
      const isActive = id === tabId;
      btn.classList.toggle("active", isActive);
      btn.setAttribute("aria-selected", String(isActive));
    }
    for (const [id, pane] of this.tabPanes) {
      pane.classList.toggle("active", id === tabId);
    }
  }
  /** Allow keyboard switching — call from modal's key handler */
  handleNumberKey(num) {
    if (num >= 1 && num <= this.tabs.length) {
      this.activateTab(this.tabs[num - 1].id);
      return true;
    }
    return false;
  }
  destroy() {
    this.container.remove();
  }
}
class EditToolbar {
  constructor(callbacks) {
    __publicField(this, "container");
    __publicField(this, "callbacks");
    __publicField(this, "currentMode", "select");
    __publicField(this, "modeButtons", /* @__PURE__ */ new Map());
    this.callbacks = callbacks;
    this.container = document.createElement("div");
    this.container.className = "veditor-modal-toolbar";
    this.container.setAttribute("role", "toolbar");
    this.container.setAttribute("aria-label", "Editing tools");
    this.container.setAttribute("data-tool-id", "veditor-edit-toolbar");
    const modeGroup = document.createElement("div");
    modeGroup.className = "veditor-toolbar-group";
    const selectBtn = this._makeToolBtn(
      iconCursor,
      "Select",
      "Select tool — click to select segments (V)",
      "veditor-tool-select",
      () => this.setMode("select")
    );
    selectBtn.classList.add("active");
    this.modeButtons.set("select", selectBtn);
    const razorBtn = this._makeToolBtn(
      iconScissors,
      "Razor",
      "Razor tool — click on timeline to cut (C)",
      "veditor-tool-razor",
      () => this.setMode("razor")
    );
    this.modeButtons.set("razor", razorBtn);
    modeGroup.append(selectBtn, razorBtn);
    const sep1 = document.createElement("div");
    sep1.className = "veditor-toolbar-sep";
    const actionGroup = document.createElement("div");
    actionGroup.className = "veditor-toolbar-group";
    const splitBtn = this._makeToolBtn(
      iconSplit,
      "Split",
      "Split at playhead (S)",
      "veditor-action-split",
      () => this.callbacks.onSplitRequested()
    );
    const deleteBtn = this._makeToolBtn(
      iconTrash,
      "Delete",
      "Delete selected segment (Delete)",
      "veditor-action-delete",
      () => this.callbacks.onDeleteRequested()
    );
    const resetBtn = this._makeToolBtn(
      iconReset,
      "Reset",
      "Reset all segments (R)",
      "veditor-action-reset",
      () => this.callbacks.onResetRequested()
    );
    actionGroup.append(splitBtn, deleteBtn, resetBtn);
    const spacer = document.createElement("div");
    spacer.className = "veditor-spacer";
    this.container.append(modeGroup, sep1, actionGroup, spacer);
  }
  get element() {
    return this.container;
  }
  get mode() {
    return this.currentMode;
  }
  setMode(mode) {
    if (this.currentMode === mode) return;
    this.currentMode = mode;
    for (const [m, btn] of this.modeButtons) {
      btn.classList.toggle("active", m === mode);
      btn.setAttribute("aria-pressed", String(m === mode));
    }
    this.callbacks.onToolChanged(mode);
  }
  /** Handle keyboard shortcuts — call from modal key handler */
  handleKey(key) {
    switch (key.toLowerCase()) {
      case "v":
        this.setMode("select");
        return true;
      case "c":
        this.setMode("razor");
        return true;
      case "s":
        this.callbacks.onSplitRequested();
        return true;
      case "r":
        this.callbacks.onResetRequested();
        return true;
      case "delete":
      case "backspace":
        this.callbacks.onDeleteRequested();
        return true;
      default:
        return false;
    }
  }
  destroy() {
    this.container.remove();
  }
  // ── Private ──────────────────────────────────────────────────
  _makeToolBtn(icon, label, tooltip, toolId, onClick) {
    const btn = document.createElement("button");
    btn.className = "veditor-tool-btn";
    btn.innerHTML = `${icon} ${label}`;
    btn.title = tooltip;
    btn.setAttribute("data-tool-id", toolId);
    btn.setAttribute("aria-label", tooltip);
    btn.setAttribute("aria-pressed", "false");
    btn.addEventListener("click", onClick);
    return btn;
  }
}
class NLETimeline {
  constructor(manager, callbacks) {
    __publicField(this, "container");
    __publicField(this, "ruler");
    __publicField(this, "tracksContainer");
    __publicField(this, "videoTrack");
    __publicField(this, "audioTrack");
    __publicField(this, "editTimeline");
    __publicField(this, "manager");
    __publicField(this, "playheadEl");
    this.manager = manager;
    this.container = document.createElement("div");
    this.container.className = "veditor-nle-timeline";
    this.container.setAttribute("data-tool-id", "veditor-timeline");
    this.container.setAttribute("aria-label", "Multi-track editing timeline");
    this.container.setAttribute("role", "region");
    this.ruler = document.createElement("div");
    this.ruler.className = "veditor-timeline-ruler";
    this.ruler.setAttribute("data-tool-id", "veditor-timeline-ruler");
    this.ruler.setAttribute("aria-label", "Timeline ruler - click to seek");
    this.ruler.style.cursor = "pointer";
    this.tracksContainer = document.createElement("div");
    this.tracksContainer.className = "veditor-timeline-tracks";
    this.videoTrack = this._createTrack("V1", "video");
    this.editTimeline = new EditTimeline(manager, callbacks);
    const canvasWrap = this.videoTrack.querySelector(".veditor-track-canvas-wrap");
    if (canvasWrap) {
      canvasWrap.appendChild(this.editTimeline.element);
    }
    this.audioTrack = this._createTrack("A1", "audio");
    const audioCanvasWrap = this.audioTrack.querySelector(".veditor-track-canvas-wrap");
    if (audioCanvasWrap) {
      const audioBar = document.createElement("div");
      audioBar.style.cssText = `
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg,
                    rgba(34, 197, 94, 0.15) 0%,
                    rgba(34, 197, 94, 0.25) 50%,
                    rgba(34, 197, 94, 0.15) 100%
                );
                border-radius: 4px;
                position: relative;
            `;
      audioBar.setAttribute("data-tool-id", "veditor-audio-track-content");
      audioBar.setAttribute("aria-label", "Audio track (visual placeholder)");
      const waveform = document.createElement("div");
      waveform.style.cssText = `
                position: absolute;
                inset: 8px 4px;
                background: repeating-linear-gradient(
                    90deg,
                    rgba(34, 197, 94, 0.4) 0px,
                    rgba(34, 197, 94, 0.1) 2px,
                    rgba(34, 197, 94, 0.3) 4px
                );
                border-radius: 2px;
                opacity: 0.6;
            `;
      audioBar.appendChild(waveform);
      audioCanvasWrap.appendChild(audioBar);
    }
    this.playheadEl = document.createElement("div");
    this.playheadEl.className = "veditor-playhead";
    this.playheadEl.style.left = "56px";
    this.playheadEl.setAttribute("data-tool-id", "veditor-playhead");
    this.playheadEl.setAttribute("aria-label", "Playhead position indicator");
    this.tracksContainer.append(this.videoTrack, this.audioTrack);
    this.container.append(this.ruler, this.tracksContainer, this.playheadEl);
    this.ruler.addEventListener("pointerdown", (e) => {
      e.stopPropagation();
      const time = this._rulerXToTime(e.clientX);
      if (time >= 0) {
        this.setPlayhead(time);
        callbacks.onPlayheadChanged(time);
      }
    });
  }
  get element() {
    return this.container;
  }
  get timeline() {
    return this.editTimeline;
  }
  setPlayhead(time) {
    this.editTimeline.setPlayhead(time);
    this._updatePlayheadPosition(time);
  }
  render() {
    this.editTimeline.render();
    this._renderRuler();
  }
  destroy() {
    this.editTimeline.destroy();
    this.container.remove();
  }
  // ── Private ──────────────────────────────────────────────────
  _createTrack(label, type) {
    const track = document.createElement("div");
    track.className = "veditor-track";
    track.setAttribute("data-tool-id", `veditor-track-${label.toLowerCase()}`);
    track.setAttribute("aria-label", `${type === "video" ? "Video" : "Audio"} track ${label}`);
    const header = document.createElement("div");
    header.className = `veditor-track-header veditor-track-header-${type}`;
    header.textContent = label;
    header.setAttribute("data-tool-id", `veditor-track-header-${label.toLowerCase()}`);
    const canvasWrap = document.createElement("div");
    canvasWrap.className = "veditor-track-canvas-wrap";
    track.append(header, canvasWrap);
    return track;
  }
  _updatePlayheadPosition(time) {
    const dur = this.manager.videoDuration;
    if (dur <= 0) return;
    const headerW = 56;
    const containerW = this.tracksContainer.clientWidth;
    const trackW = containerW - headerW;
    const x = headerW + time / dur * trackW;
    this.playheadEl.style.left = `${x}px`;
  }
  _renderRuler() {
    const dur = this.manager.videoDuration;
    if (dur <= 0) return;
    this.ruler.innerHTML = "";
    const headerW = 56;
    const containerW = this.container.clientWidth;
    const trackW = containerW - headerW;
    let interval = 1;
    if (dur > 60) interval = 10;
    else if (dur > 30) interval = 5;
    else if (dur > 10) interval = 2;
    for (let t = 0; t <= dur; t += interval) {
      const marker = document.createElement("div");
      const x = headerW + t / dur * trackW;
      marker.style.cssText = `
                position: absolute;
                left: ${x}px;
                top: 0;
                height: 100%;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: flex-end;
                padding-bottom: 2px;
            `;
      const tick = document.createElement("div");
      tick.style.cssText = `
                width: 1px;
                height: 8px;
                background: rgba(255,255,255,0.15);
            `;
      const label = document.createElement("span");
      label.style.cssText = `
                font-size: 9px;
                color: rgba(255,255,255,0.3);
                font-variant-numeric: tabular-nums;
                transform: translateX(-50%);
            `;
      const mins = Math.floor(t / 60);
      const secs = Math.floor(t % 60);
      label.textContent = `${mins}:${secs.toString().padStart(2, "0")}`;
      marker.append(label, tick);
      this.ruler.appendChild(marker);
    }
  }
  /** Map a ruler clientX to source time */
  _rulerXToTime(clientX) {
    const dur = this.manager.videoDuration;
    if (dur <= 0) return -1;
    const headerW = 56;
    const containerRect = this.container.getBoundingClientRect();
    const containerW = containerRect.width;
    const trackW = containerW - headerW;
    const x = clientX - containerRect.left - headerW;
    if (x < 0 || x > trackW) return -1;
    return x / trackW * dur;
  }
}
const MIN_ZOOM = 0.1;
const MAX_ZOOM = 8;
const ZOOM_STEP = 1.15;
class MonitorCanvas {
  constructor(video, callbacks = {}) {
    __publicField(this, "container");
    __publicField(this, "viewport");
    __publicField(this, "content");
    __publicField(this, "zoomBar");
    __publicField(this, "zoomLabel");
    __publicField(this, "callbacks");
    __publicField(this, "_zoom", 1);
    __publicField(this, "_panX", 0);
    __publicField(this, "_panY", 0);
    __publicField(this, "_isPanning", false);
    __publicField(this, "_panStartX", 0);
    __publicField(this, "_panStartY", 0);
    __publicField(this, "_panStartPanX", 0);
    __publicField(this, "_panStartPanY", 0);
    this.callbacks = callbacks;
    this.container = document.createElement("div");
    this.container.className = "veditor-monitor-canvas";
    this.container.setAttribute("data-tool-id", "veditor-monitor-canvas");
    this.container.setAttribute("aria-label", "Video preview canvas — scroll to zoom, middle-drag to pan");
    this.viewport = document.createElement("div");
    this.viewport.className = "veditor-monitor-viewport";
    this.content = document.createElement("div");
    this.content.className = "veditor-monitor-content";
    this.content.appendChild(video);
    this.viewport.appendChild(this.content);
    this.zoomBar = document.createElement("div");
    this.zoomBar.className = "veditor-zoom-bar";
    this.zoomBar.setAttribute("data-tool-id", "veditor-zoom-bar");
    this.zoomBar.setAttribute("aria-label", "Zoom controls");
    const zoomOutBtn = this._makeZoomBtn(
      iconZoomOut,
      "Zoom Out",
      "veditor-zoom-out",
      () => this.zoomBy(1 / ZOOM_STEP)
    );
    this.zoomLabel = document.createElement("span");
    this.zoomLabel.className = "veditor-zoom-label";
    this.zoomLabel.textContent = "100%";
    this.zoomLabel.setAttribute("data-tool-id", "veditor-zoom-level");
    this.zoomLabel.setAttribute("aria-label", "Current zoom level");
    this.zoomLabel.title = "Current zoom level (click for 100%)";
    this.zoomLabel.style.cursor = "pointer";
    this.zoomLabel.addEventListener("click", () => this.setZoom(1));
    const zoomInBtn = this._makeZoomBtn(
      iconZoomIn,
      "Zoom In",
      "veditor-zoom-in",
      () => this.zoomBy(ZOOM_STEP)
    );
    const fitBtn = this._makeZoomBtn(
      iconMaximize,
      "Fit to View (F)",
      "veditor-zoom-fit",
      () => this.fitToView()
    );
    this.zoomBar.append(zoomOutBtn, this.zoomLabel, zoomInBtn, fitBtn);
    this.container.append(this.viewport, this.zoomBar);
    this._setupEvents();
  }
  get element() {
    return this.container;
  }
  get zoom() {
    return this._zoom;
  }
  /** Get the content div (used for mounting crop overlay) */
  get contentElement() {
    return this.content;
  }
  // ── Public API ───────────────────────────────────────────────
  /** Set zoom level (clamped to range) */
  setZoom(level, centerX, centerY) {
    var _a, _b;
    const oldZoom = this._zoom;
    this._zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, level));
    if (centerX !== void 0 && centerY !== void 0) {
      const scale = this._zoom / oldZoom;
      this._panX = centerX - (centerX - this._panX) * scale;
      this._panY = centerY - (centerY - this._panY) * scale;
    }
    this._applyTransform();
    this._updateZoomLabel();
    (_b = (_a = this.callbacks).onZoomChanged) == null ? void 0 : _b.call(_a, Math.round(this._zoom * 100));
  }
  /** Multiply current zoom by factor */
  zoomBy(factor, centerX, centerY) {
    this.setZoom(this._zoom * factor, centerX, centerY);
  }
  /** Fit video to viewport (reset pan, calculate zoom) */
  fitToView() {
    var _a, _b;
    const vw = this.viewport.clientWidth;
    const vh = this.viewport.clientHeight;
    const cw = this.content.scrollWidth || vw;
    const ch = this.content.scrollHeight || vh;
    if (cw === 0 || ch === 0) {
      this._zoom = 1;
      this._panX = 0;
      this._panY = 0;
    } else {
      this._zoom = Math.min(vw / cw, vh / ch, 1);
      this._panX = (vw - cw * this._zoom) / 2;
      this._panY = (vh - ch * this._zoom) / 2;
    }
    this._applyTransform();
    this._updateZoomLabel();
    (_b = (_a = this.callbacks).onZoomChanged) == null ? void 0 : _b.call(_a, Math.round(this._zoom * 100));
  }
  /** Handle keyboard shortcuts — returns true if consumed */
  handleKey(key) {
    switch (key.toLowerCase()) {
      case "f":
        this.fitToView();
        return true;
      default:
        return false;
    }
  }
  destroy() {
    this.container.remove();
  }
  // ── Private ─────────────────────────────────────────────────
  _applyTransform() {
    this.content.style.transform = `translate(${this._panX}px, ${this._panY}px) scale(${this._zoom})`;
  }
  _updateZoomLabel() {
    this.zoomLabel.textContent = `${Math.round(this._zoom * 100)}%`;
  }
  _setupEvents() {
    this.viewport.addEventListener("wheel", (e) => {
      e.preventDefault();
      const rect = this.viewport.getBoundingClientRect();
      const cx = e.clientX - rect.left;
      const cy = e.clientY - rect.top;
      const factor = e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
      this.zoomBy(factor, cx, cy);
    }, { passive: false });
    this.viewport.addEventListener("dblclick", () => {
      this.fitToView();
    });
    this.viewport.addEventListener("pointerdown", (e) => {
      if (e.button === 1 || e.button === 0 && e.altKey) {
        e.preventDefault();
        this._isPanning = true;
        this._panStartX = e.clientX;
        this._panStartY = e.clientY;
        this._panStartPanX = this._panX;
        this._panStartPanY = this._panY;
        this.viewport.setPointerCapture(e.pointerId);
        this.viewport.style.cursor = "grabbing";
      }
    });
    this.viewport.addEventListener("pointermove", (e) => {
      if (!this._isPanning) return;
      this._panX = this._panStartPanX + (e.clientX - this._panStartX);
      this._panY = this._panStartPanY + (e.clientY - this._panStartY);
      this._applyTransform();
    });
    this.viewport.addEventListener("pointerup", (e) => {
      if (this._isPanning) {
        this._isPanning = false;
        this.viewport.releasePointerCapture(e.pointerId);
        this.viewport.style.cursor = "";
      }
    });
  }
  _makeZoomBtn(icon, label, toolId, onClick) {
    const btn = document.createElement("button");
    btn.className = "veditor-btn veditor-zoom-btn";
    btn.innerHTML = icon;
    btn.title = label;
    btn.setAttribute("data-tool-id", toolId);
    btn.setAttribute("aria-label", label);
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      onClick();
    });
    return btn;
  }
}
const CATEGORIES = [
  {
    title: "Transport",
    shortcuts: [
      { key: "Space", desc: "Play / Pause" },
      { key: "← →", desc: "Step back / forward" }
    ]
  },
  {
    title: "Tools",
    shortcuts: [
      { key: "V", desc: "Select tool" },
      { key: "C", desc: "Razor tool" },
      { key: "S", desc: "Split at playhead" },
      { key: "Del", desc: "Delete segment" },
      { key: "R", desc: "Reset all segments" }
    ]
  },
  {
    title: "Monitor",
    shortcuts: [
      { key: "F", desc: "Fit to view" },
      { key: "Scroll", desc: "Zoom in / out" },
      { key: "Mid-drag", desc: "Pan canvas" },
      { key: "Dbl-click", desc: "Fit to view" }
    ]
  },
  {
    title: "Panels",
    shortcuts: [
      { key: "1–5", desc: "Switch tool tabs" },
      { key: "?", desc: "Toggle this overlay" }
    ]
  },
  {
    title: "General",
    shortcuts: [
      { key: "Ctrl+Z", desc: "Undo" },
      { key: "Ctrl+Shift+Z", desc: "Redo" },
      { key: "Esc", desc: "Close editor" }
    ]
  }
];
class ShortcutOverlay {
  constructor() {
    __publicField(this, "backdrop");
    __publicField(this, "isVisible", false);
    this.backdrop = document.createElement("div");
    this.backdrop.className = "veditor-shortcuts-backdrop";
    this.backdrop.setAttribute("data-tool-id", "veditor-shortcut-overlay");
    this.backdrop.setAttribute("aria-label", "Keyboard shortcuts overlay");
    this.backdrop.style.display = "none";
    this.backdrop.addEventListener("click", (e) => {
      if (e.target === this.backdrop) this.hide();
    });
    const panel = document.createElement("div");
    panel.className = "veditor-shortcuts-panel";
    panel.addEventListener("click", (e) => e.stopPropagation());
    const header = document.createElement("div");
    header.className = "veditor-shortcuts-header";
    const title = document.createElement("h3");
    title.className = "veditor-shortcuts-title";
    title.textContent = "Keyboard Shortcuts";
    const closeBtn = document.createElement("button");
    closeBtn.className = "veditor-btn";
    closeBtn.innerHTML = iconClose;
    closeBtn.title = "Close shortcuts";
    closeBtn.setAttribute("data-tool-id", "veditor-shortcuts-close");
    closeBtn.setAttribute("aria-label", "Close shortcuts overlay");
    closeBtn.addEventListener("click", () => this.hide());
    header.append(title, closeBtn);
    const grid = document.createElement("div");
    grid.className = "veditor-shortcuts-grid";
    for (const cat of CATEGORIES) {
      const section = document.createElement("div");
      section.className = "veditor-shortcuts-section";
      const catTitle = document.createElement("div");
      catTitle.className = "veditor-shortcuts-cat";
      catTitle.textContent = cat.title;
      section.appendChild(catTitle);
      for (const sc of cat.shortcuts) {
        const row = document.createElement("div");
        row.className = "veditor-shortcut-row";
        const kbd = document.createElement("kbd");
        kbd.className = "veditor-kbd";
        kbd.textContent = sc.key;
        const desc = document.createElement("span");
        desc.className = "veditor-shortcut-desc";
        desc.textContent = sc.desc;
        row.append(kbd, desc);
        section.appendChild(row);
      }
      grid.appendChild(section);
    }
    panel.append(header, grid);
    this.backdrop.appendChild(panel);
  }
  get element() {
    return this.backdrop;
  }
  toggle() {
    if (this.isVisible) this.hide();
    else this.show();
  }
  show() {
    this.isVisible = true;
    this.backdrop.style.display = "flex";
  }
  hide() {
    this.isVisible = false;
    this.backdrop.style.display = "none";
  }
  /** Returns true if the overlay consumed the key event */
  handleKey(key) {
    if (key === "?" || key.toLowerCase() === "h" && !this.isVisible) {
      this.toggle();
      return true;
    }
    if (key === "Escape" && this.isVisible) {
      this.hide();
      return true;
    }
    return false;
  }
  destroy() {
    this.backdrop.remove();
  }
}
const TRANSITION_LABELS = {
  none: "None (Hard Cut)",
  fade: "Fade",
  dissolve: "Dissolve",
  wipeleft: "Wipe Left",
  wiperight: "Wipe Right",
  slideleft: "Slide Left",
  slideright: "Slide Right"
};
class TransitionEditor {
  constructor(manager, callbacks) {
    __publicField(this, "container");
    __publicField(this, "listEl");
    __publicField(this, "emptyMsg");
    __publicField(this, "_transitions", []);
    __publicField(this, "manager");
    __publicField(this, "callbacks");
    this.manager = manager;
    this.callbacks = callbacks;
    this.container = document.createElement("div");
    this.container.setAttribute("data-tool-id", "veditor-transitions");
    this.container.setAttribute("aria-label", "Segment transitions editor");
    this.emptyMsg = document.createElement("div");
    this.emptyMsg.className = "veditor-section-label";
    this.emptyMsg.textContent = "Split the video to add transitions between segments.";
    this.emptyMsg.style.textTransform = "none";
    this.emptyMsg.style.letterSpacing = "normal";
    this.emptyMsg.style.fontWeight = "400";
    this.emptyMsg.style.color = "var(--ve-text-dim)";
    this.listEl = document.createElement("div");
    this.listEl.className = "veditor-text-list";
    this.container.append(this.emptyMsg, this.listEl);
  }
  get element() {
    return this.container;
  }
  get transitions() {
    return this._transitions;
  }
  /** Re-render based on current segment count */
  refresh() {
    const segs = this.manager.segments;
    const cutCount = segs.length - 1;
    while (this._transitions.length < cutCount) {
      this._transitions.push({ type: "none", duration: 0.5 });
    }
    if (this._transitions.length > cutCount) {
      this._transitions.length = cutCount;
    }
    this.emptyMsg.style.display = cutCount > 0 ? "none" : "block";
    this.listEl.innerHTML = "";
    for (let i = 0; i < cutCount; i++) {
      this.listEl.appendChild(this._makeCard(i, segs[i], segs[i + 1]));
    }
  }
  _makeCard(index, segA, segB) {
    const card = document.createElement("div");
    card.className = "veditor-text-card";
    const header = document.createElement("div");
    header.className = "veditor-text-card-header";
    const title = document.createElement("span");
    title.className = "veditor-text-card-title";
    title.innerHTML = `${iconShuffle} Cut ${index + 1}`;
    const timeLabel = document.createElement("span");
    timeLabel.className = "veditor-time-unit";
    timeLabel.textContent = `${segA.end.toFixed(1)}s → ${segB.start.toFixed(1)}s`;
    header.append(title, timeLabel);
    const typeSection = this._makeSection("Type");
    const typeRow = document.createElement("div");
    typeRow.className = "veditor-control-row";
    const select = document.createElement("select");
    select.className = "veditor-select";
    select.setAttribute("data-tool-id", `veditor-transition-type-${index}`);
    select.setAttribute("aria-label", `Transition type for cut ${index + 1}`);
    for (const [value, label] of Object.entries(TRANSITION_LABELS)) {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = label;
      if (value === this._transitions[index].type) opt.selected = true;
      select.appendChild(opt);
    }
    select.addEventListener("change", () => {
      this._transitions[index].type = select.value;
      this.callbacks.onTransitionsChanged();
      durationSection.style.display = select.value === "none" ? "none" : "block";
    });
    typeRow.appendChild(select);
    typeSection.appendChild(typeRow);
    const durationSection = this._makeSection("Duration");
    durationSection.style.display = this._transitions[index].type === "none" ? "none" : "block";
    const durRow = document.createElement("div");
    durRow.className = "veditor-control-row";
    const slider = document.createElement("input");
    slider.type = "range";
    slider.className = "veditor-fade-slider";
    slider.min = "0.1";
    slider.max = "3";
    slider.step = "0.1";
    slider.value = String(this._transitions[index].duration);
    slider.setAttribute("data-tool-id", `veditor-transition-dur-${index}`);
    slider.setAttribute("aria-label", `Transition duration for cut ${index + 1}`);
    const durLabel = document.createElement("span");
    durLabel.className = "veditor-fade-label";
    durLabel.textContent = `${this._transitions[index].duration.toFixed(1)}s`;
    slider.addEventListener("input", () => {
      const val = parseFloat(slider.value);
      this._transitions[index].duration = val;
      durLabel.textContent = `${val.toFixed(1)}s`;
    });
    slider.addEventListener("change", () => {
      this.callbacks.onTransitionsChanged();
    });
    durRow.append(slider, durLabel);
    durationSection.appendChild(durRow);
    card.append(header, typeSection, durationSection);
    return card;
  }
  _makeSection(title) {
    const section = document.createElement("div");
    section.className = "veditor-panel-section";
    const label = document.createElement("div");
    label.className = "veditor-section-label";
    label.textContent = title;
    section.appendChild(label);
    return section;
  }
  destroy() {
    this.container.remove();
  }
}
const INFO_ROUTE = "/ffmpega/video_info";
const PREVIEW_ROUTE$1 = "/ffmpega/preview";
class EditorModal {
  constructor(callbacks) {
    __publicField(this, "dialog");
    __publicField(this, "panel");
    __publicField(this, "video");
    __publicField(this, "editManager");
    __publicField(this, "nleTimeline", null);
    __publicField(this, "transport");
    __publicField(this, "cropOverlay");
    __publicField(this, "speedControl");
    __publicField(this, "audioMixer");
    __publicField(this, "textPanel");
    __publicField(this, "undoManager");
    __publicField(this, "toolsPanel");
    __publicField(this, "editToolbar");
    __publicField(this, "monitorCanvas");
    __publicField(this, "shortcutOverlay");
    __publicField(this, "transitionEditor");
    __publicField(this, "callbacks");
    __publicField(this, "videoPath", "");
    __publicField(this, "_escHandler", null);
    __publicField(this, "_isOpen", false);
    __publicField(this, "_currentToolMode", "select");
    __publicField(this, "_userDragging", false);
    this.callbacks = callbacks;
    document.querySelectorAll(".veditor-modal-backdrop").forEach((d) => d.remove());
    this.dialog = document.createElement("div");
    this.dialog.className = "veditor-modal-backdrop";
    this.dialog.style.display = "none";
    this.dialog.setAttribute("data-tool-id", "veditor-modal");
    this.dialog.setAttribute("aria-label", "Video Editor");
    this.dialog.setAttribute("role", "dialog");
    this.dialog.setAttribute("aria-modal", "true");
    this.dialog.addEventListener("click", (e) => {
      if (e.target === this.dialog) this._cancel();
    });
    this.panel = document.createElement("div");
    this.panel.className = "veditor-modal-panel";
    this.panel.setAttribute("data-tool-id", "veditor-panel");
    const header = document.createElement("div");
    header.className = "veditor-modal-header";
    const titleWrap = document.createElement("div");
    titleWrap.style.display = "flex";
    titleWrap.style.alignItems = "center";
    titleWrap.style.gap = "8px";
    const title = document.createElement("h2");
    title.className = "veditor-modal-title";
    title.innerHTML = `<span class="veditor-modal-title-icon">${iconClapperboard}</span> Video Editor`;
    titleWrap.appendChild(title);
    const shortcuts = document.createElement("div");
    shortcuts.className = "veditor-header-shortcuts";
    shortcuts.innerHTML = [
      "<kbd>Space</kbd> Play",
      "<kbd>S</kbd> Split",
      "<kbd>V</kbd> Select",
      "<kbd>C</kbd> Razor",
      "<kbd>1-5</kbd> Tool Tabs",
      "<kbd>?</kbd> Shortcuts"
    ].join("  ·  ");
    const headerActions = document.createElement("div");
    headerActions.className = "veditor-header-actions";
    const undoBtn = document.createElement("button");
    undoBtn.className = "veditor-btn veditor-btn-sm";
    undoBtn.innerHTML = `${iconUndo} Undo`;
    undoBtn.title = "Undo (Ctrl+Z)";
    undoBtn.setAttribute("data-tool-id", "veditor-undo");
    undoBtn.setAttribute("aria-label", "Undo last edit (Ctrl+Z)");
    undoBtn.addEventListener("click", () => this.undoManager.undo());
    const redoBtn = document.createElement("button");
    redoBtn.className = "veditor-btn veditor-btn-sm";
    redoBtn.innerHTML = `${iconRedo} Redo`;
    redoBtn.title = "Redo (Ctrl+Shift+Z)";
    redoBtn.setAttribute("data-tool-id", "veditor-redo");
    redoBtn.setAttribute("aria-label", "Redo last edit (Ctrl+Shift+Z)");
    redoBtn.addEventListener("click", () => this.undoManager.redo());
    const cancelBtn = document.createElement("button");
    cancelBtn.className = "veditor-btn veditor-btn-sm";
    cancelBtn.textContent = "Cancel";
    cancelBtn.title = "Cancel editing (ESC)";
    cancelBtn.setAttribute("data-tool-id", "veditor-cancel");
    cancelBtn.setAttribute("aria-label", "Cancel editing and close (ESC)");
    cancelBtn.addEventListener("click", () => this._cancel());
    const applyBtn = document.createElement("button");
    applyBtn.className = "veditor-btn veditor-btn-sm veditor-btn-primary";
    applyBtn.innerHTML = `${iconCheck} Apply Edits`;
    applyBtn.title = "Apply edits and continue workflow";
    applyBtn.setAttribute("data-tool-id", "veditor-apply");
    applyBtn.setAttribute("aria-label", "Apply all edits and continue workflow");
    applyBtn.addEventListener("click", () => this._apply());
    const closeBtn = document.createElement("button");
    closeBtn.className = "veditor-modal-close";
    closeBtn.innerHTML = iconClose;
    closeBtn.title = "Close (ESC)";
    closeBtn.setAttribute("data-tool-id", "veditor-close");
    closeBtn.setAttribute("aria-label", "Close editor without saving (ESC)");
    closeBtn.addEventListener("click", () => this._cancel());
    headerActions.append(undoBtn, redoBtn, cancelBtn, applyBtn, closeBtn);
    header.append(titleWrap, shortcuts, headerActions);
    this.video = document.createElement("video");
    this.video.controls = false;
    this.video.muted = false;
    this.video.preload = "auto";
    this.video.setAttribute("data-tool-id", "veditor-video");
    this.video.setAttribute("aria-label", "Video preview");
    this.monitorCanvas = new MonitorCanvas(this.video);
    const monitor = this.monitorCanvas.element;
    monitor.setAttribute("data-tool-id", "veditor-monitor");
    monitor.setAttribute("aria-label", "Video preview monitor — scroll to zoom, middle-drag to pan, F to fit, 1 for 100%");
    const transportWrap = document.createElement("div");
    transportWrap.className = "veditor-modal-transport";
    this.editManager = new EditManager();
    this.transport = new TransportBar({
      onTimeUpdate: (time) => {
        var _a;
        if (!this._userDragging) {
          (_a = this.nleTimeline) == null ? void 0 : _a.setPlayhead(time);
        }
      },
      onPlayStateChange: () => {
      }
    });
    this.transport.setEditManager(this.editManager);
    this.transport.bindVideo(this.video);
    transportWrap.appendChild(this.transport.element);
    this.cropOverlay = new CropOverlay({
      onCropChanged: () => this._pushUndo()
    });
    this.speedControl = new SpeedControl({
      onSpeedChanged: () => this._pushUndo()
    });
    this.audioMixer = new AudioMixer({
      onVolumeChanged: (vol) => {
        this.video.volume = Math.min(1, vol);
      }
    });
    this.textPanel = new TextOverlayPanel({
      onOverlaysChanged: () => this._pushUndo()
    });
    this.transitionEditor = new TransitionEditor(this.editManager, {
      onTransitionsChanged: () => this._pushUndo()
    });
    this.toolsPanel = new ToolsPanel([
      { id: "crop", label: "Crop", icon: iconCrop, content: this.cropOverlay.element },
      { id: "speed", label: "Speed", icon: iconGauge, content: this.speedControl.element },
      { id: "audio", label: "Audio", icon: iconVolume, content: this.audioMixer.element },
      { id: "text", label: "Text", icon: iconText, content: this.textPanel.element },
      { id: "transitions", label: "Trans", icon: iconShuffle, content: this.transitionEditor.element }
    ]);
    this.monitorCanvas.contentElement.appendChild(this.cropOverlay.canvasElement);
    this.editToolbar = new EditToolbar({
      onToolChanged: (mode) => {
        this._currentToolMode = mode;
      },
      onSplitRequested: () => {
        var _a, _b;
        const playhead = ((_a = this.nleTimeline) == null ? void 0 : _a.timeline.playhead) ?? 0;
        if (this.editManager.splitAt(playhead)) {
          this._pushUndo();
          (_b = this.nleTimeline) == null ? void 0 : _b.render();
        }
      },
      onDeleteRequested: () => {
        var _a, _b;
        if (this.editManager.segments.length > 1) {
          const playhead = ((_a = this.nleTimeline) == null ? void 0 : _a.timeline.playhead) ?? 0;
          const hitSeg = this.editManager.segments.find(
            (s) => playhead >= s.start && playhead <= s.end
          );
          if (hitSeg) {
            this.editManager.removeSegment(hitSeg.id);
            this._pushUndo();
            (_b = this.nleTimeline) == null ? void 0 : _b.render();
          }
        }
      },
      onResetRequested: () => {
        var _a;
        this.editManager.reset();
        this._pushUndo();
        (_a = this.nleTimeline) == null ? void 0 : _a.render();
      }
    });
    const timelineSlot = document.createElement("div");
    timelineSlot.className = "veditor-modal-timeline";
    timelineSlot.id = "veditor-timeline-slot";
    timelineSlot.setAttribute("data-tool-id", "veditor-timeline-area");
    timelineSlot.setAttribute("aria-label", "Timeline editing area");
    this.undoManager = new UndoManager({
      onRestore: (state) => this._restoreState(state)
    });
    this.panel.append(
      header,
      monitor,
      transportWrap,
      this.toolsPanel.element,
      this.editToolbar.element,
      timelineSlot
    );
    this.shortcutOverlay = new ShortcutOverlay();
    this.dialog.appendChild(this.shortcutOverlay.element);
    this.dialog.appendChild(this.panel);
    document.body.appendChild(this.dialog);
  }
  /** Open the modal with a video path and optional initial state */
  async open(videoPath, initialState) {
    if (this._isOpen) return;
    this._isOpen = true;
    this.videoPath = videoPath;
    if (initialState) {
      this.speedControl.loadSpeedMap(initialState.speedMap);
      this.audioMixer.setVolume(initialState.volume);
      this.textPanel.loadOverlays(initialState.textOverlays);
      try {
        const crop = JSON.parse(initialState.cropRect);
        if (crop && crop.w && crop.h) this.cropOverlay.setRect(crop);
      } catch {
      }
    }
    try {
      const resp = await fetch(`${INFO_ROUTE}?path=${encodeURIComponent(videoPath)}`);
      if (resp.ok) {
        const info = await resp.json();
        this.editManager.init(info.duration || 1);
        this.cropOverlay.setVideoDimensions(info.width || 640, info.height || 480);
        if (initialState && initialState.segments.length > 0) {
          this.editManager.segments = initialState.segments.map(
            ([start, end], i) => ({
              id: `restored_${i}`,
              start,
              end
            })
          );
        }
      }
    } catch (e) {
      console.warn("[VideoEditor] Failed to fetch video info:", e);
    }
    this.video.src = `${PREVIEW_ROUTE$1}?path=${encodeURIComponent(videoPath)}`;
    this.video.load();
    this.dialog.style.display = "flex";
    this.video.addEventListener("loadeddata", () => {
      this.monitorCanvas.fitToView();
    }, { once: true });
    requestAnimationFrame(() => {
      const slot = this.panel.querySelector("#veditor-timeline-slot");
      if (slot) {
        this.nleTimeline = new NLETimeline(this.editManager, {
          onSegmentsChanged: () => {
            this._pushUndo();
            this.transitionEditor.refresh();
          },
          onPlayheadChanged: (time) => this.transport.seekTo(time),
          onTrimHandleDrag: (time) => this.transport.seekTo(time),
          onRequestSplit: () => {
          },
          onDragStart: () => {
            this._userDragging = true;
            this.video.pause();
          },
          onDragEnd: () => {
            this._userDragging = false;
          }
        });
        slot.innerHTML = "";
        slot.appendChild(this.nleTimeline.element);
        this.nleTimeline.render();
      }
    });
    this._escHandler = (e) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }
      if (e.key === "Escape") {
        this._cancel();
        return;
      }
      if (e.ctrlKey && e.key === "z" && !e.shiftKey) {
        e.preventDefault();
        this.undoManager.undo();
        return;
      }
      if (e.ctrlKey && e.key === "z" && e.shiftKey) {
        e.preventDefault();
        this.undoManager.redo();
        return;
      }
      const num = parseInt(e.key, 10);
      if (num >= 1 && num <= 5 && !e.ctrlKey && !e.altKey) {
        if (this.toolsPanel.handleNumberKey(num)) {
          e.preventDefault();
          return;
        }
      }
      if (this.shortcutOverlay.handleKey(e.key)) {
        e.preventDefault();
        return;
      }
      if (this.monitorCanvas.handleKey(e.key)) {
        e.preventDefault();
        return;
      }
      if (this.editToolbar.handleKey(e.key)) {
        e.preventDefault();
        return;
      }
    };
    document.addEventListener("keydown", this._escHandler);
    this.undoManager.push(this._getState());
  }
  /** Update callbacks — used by singleton pattern so different nodes can
   *  set their own onApply/onCancel before opening the shared modal. */
  setCallbacks(callbacks) {
    this.callbacks = callbacks;
  }
  /** Close the modal without applying */
  close() {
    if (!this._isOpen) return;
    this._isOpen = false;
    this.video.pause();
    this.video.src = "";
    if (this.nleTimeline) {
      this.nleTimeline.destroy();
      this.nleTimeline = null;
    }
    if (this._escHandler) {
      document.removeEventListener("keydown", this._escHandler);
      this._escHandler = null;
    }
    this.dialog.style.display = "none";
  }
  get isOpen() {
    return this._isOpen;
  }
  // ── Private ──────────────────────────────────────────────────────
  _getState() {
    return {
      segments: this.editManager.toJSON(),
      cropRect: JSON.stringify(this.cropOverlay.getRect() ?? {}),
      speedMap: this.speedControl.getSpeedMap(),
      volume: this.audioMixer.getVolume(),
      textOverlays: this.textPanel.getOverlays(),
      transitions: []
    };
  }
  _pushUndo() {
    this.undoManager.push(this._getState());
  }
  _restoreState(state) {
    var _a;
    this.editManager.segments = state.segments.map(([start, end], i) => ({
      id: `restored_${i}`,
      start,
      end
    }));
    (_a = this.nleTimeline) == null ? void 0 : _a.render();
    try {
      const crop = JSON.parse(state.cropRect);
      if (crop && crop.w && crop.h) {
        this.cropOverlay.setRect(crop);
      } else {
        this.cropOverlay.setRect(null);
      }
    } catch {
      this.cropOverlay.setRect(null);
    }
    this.speedControl.loadSpeedMap(state.speedMap);
    this.audioMixer.setVolume(state.volume);
    this.textPanel.loadOverlays(state.textOverlays);
  }
  _apply() {
    const state = {
      segments: this.editManager.toJSON(),
      cropRect: JSON.stringify(this.cropOverlay.getRect() ?? {}),
      speedMap: this.speedControl.getSpeedMap(),
      volume: this.audioMixer.getVolume(),
      textOverlays: this.textPanel.getOverlays(),
      transitions: []
    };
    this.close();
    this.callbacks.onApply(state);
  }
  _cancel() {
    this.close();
    this.callbacks.onCancel();
  }
}
const editorCSS = `/* ═══════════════════════════════════════════════════════════════════
 * Video Editor (FFMPEGA) — Modern NLE Theme
 *
 * Design: deep charcoal-to-navy gradient, glassmorphism panels,
 * blue/purple accents, professional NLE workspace aesthetic.
 * Agent-friendly: all interactive elements have data-tool-id,
 * aria-label and title attributes for AI agent discoverability.
 * ═══════════════════════════════════════════════════════════════════ */

/* ── Variables ───────────────────────────────────────────────────── */

:root {
    --ve-bg-deep: #0f0f1a;
    --ve-bg-primary: #161625;
    --ve-bg-secondary: #1c1c30;
    --ve-bg-surface: #22223a;
    --ve-bg-elevated: #2a2a45;
    --ve-border: rgba(255, 255, 255, 0.06);
    --ve-border-hover: rgba(255, 255, 255, 0.12);
    --ve-border-glow: rgba(99, 102, 241, 0.3);
    --ve-text-primary: #e8e8f0;
    --ve-text-secondary: #9898b0;
    --ve-text-dim: #686880;
    --ve-accent: #6366f1;
    --ve-accent-hover: #818cf8;
    --ve-accent-glow: rgba(99, 102, 241, 0.25);
    --ve-success: #22c55e;
    --ve-success-hover: #4ade80;
    --ve-danger: #ef4444;
    --ve-danger-hover: #f87171;
    --ve-clip-video: #6366f1;
    --ve-clip-audio: #22c55e;
    --ve-playhead: #f97316;
    --ve-glass-bg: rgba(28, 28, 48, 0.75);
    --ve-glass-border: rgba(255, 255, 255, 0.08);
    --ve-glass-blur: 12px;
    --ve-radius-sm: 6px;
    --ve-radius-md: 10px;
    --ve-radius-lg: 14px;
    --ve-transition: 0.15s ease;
    --ve-font: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
}

/* ── Compact Node (on-canvas) ────────────────────────────────────── */

.veditor-node {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 4px;
    font-family: var(--ve-font);
    font-size: 12px;
    color: var(--ve-text-primary);
    box-sizing: border-box;
}

.veditor-node * {
    box-sizing: border-box;
}

.veditor-preview {
    width: 100%;
    border-radius: 4px;
    overflow: hidden;
    background: #000;
}

.veditor-btns {
    display: flex;
    gap: 3px;
}

.veditor-status {
    font-size: 10px;
    color: var(--ve-text-secondary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.4;
}

/* ── Shared Button ────────────────────────────────────────────────── */

.veditor-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    padding: 6px 12px;
    border: 1px solid var(--ve-border);
    border-radius: var(--ve-radius-sm);
    background: var(--ve-bg-elevated);
    color: var(--ve-text-primary);
    cursor: pointer;
    font-size: 12px;
    font-family: var(--ve-font);
    white-space: nowrap;
    text-align: center;
    transition: all var(--ve-transition);
    outline: none;
}

.veditor-btn:hover {
    background: var(--ve-bg-surface);
    border-color: var(--ve-border-hover);
}

.veditor-btn:active {
    transform: scale(0.97);
}

.veditor-btn:focus-visible {
    border-color: var(--ve-accent);
    box-shadow: 0 0 0 2px var(--ve-accent-glow);
}

.veditor-btn-accent {
    background: var(--ve-accent);
    border-color: transparent;
    color: #fff;
    font-weight: 600;
}

.veditor-btn-accent:hover {
    background: var(--ve-accent-hover);
    box-shadow: 0 0 16px var(--ve-accent-glow);
}

.veditor-btn-primary {
    background: var(--ve-success);
    border-color: transparent;
    color: #fff;
    font-weight: 600;
}

.veditor-btn-primary:hover {
    background: var(--ve-success-hover);
    box-shadow: 0 0 16px rgba(34, 197, 94, 0.25);
}

.veditor-btn-danger {
    background: transparent;
    border-color: var(--ve-danger);
    color: var(--ve-danger);
}

.veditor-btn-danger:hover {
    background: rgba(239, 68, 68, 0.1);
    color: var(--ve-danger-hover);
}

.veditor-btn-sm {
    padding: 3px 8px;
    font-size: 11px;
}

.veditor-btn-icon {
    padding: 5px 8px;
    font-size: 14px;
    min-width: 32px;
}

/* ── Modal Overlay (native <dialog>) ─────────────────────────────── */

.veditor-modal-backdrop {
    border: none;
    padding: 0;
    margin: 0;
    background: rgba(0, 0, 0, 0.7);
    backdrop-filter: blur(6px);
    max-width: none;
    max-height: none;
    z-index: 2147483647;
    position: fixed;
    inset: 0;

    width: 100vw;
    height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding-top: 30px;
    font-family: var(--ve-font);
    color: var(--ve-text-primary);
}

/* ── Panel (CSS Grid NLE layout) ─────────────────────────────────── */

.veditor-modal-panel {
    background: linear-gradient(160deg, var(--ve-bg-primary) 0%, var(--ve-bg-deep) 100%);
    border: 1px solid var(--ve-glass-border);
    border-radius: var(--ve-radius-lg);
    width: 82vw;
    height: 82vh;

    display: grid !important;
    grid-template-areas:
        "header   header"
        "monitor  tools"
        "transport tools"
        "toolbar  toolbar"
        "timeline timeline" !important;
    grid-template-columns: 1fr 280px !important;
    grid-template-rows: auto minmax(0, 1fr) auto auto minmax(180px, 35%) !important;

    box-shadow:
        0 0 60px rgba(0, 0, 0, 0.5),
        0 0 120px rgba(99, 102, 241, 0.05);
    overflow: hidden;
}

/* ── Header ──────────────────────────────────────────────────────── */

.veditor-modal-header {
    grid-area: header;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    border-bottom: 1px solid var(--ve-glass-border);
    position: relative;
    z-index: 100;
    background: var(--ve-glass-bg);
    backdrop-filter: blur(var(--ve-glass-blur));
}

.veditor-modal-title {
    margin: 0;
    font-size: 15px;
    font-weight: 700;
    color: #fff;
    letter-spacing: 0.3px;
}

.veditor-modal-title-icon {
    opacity: 0.7;
    margin-right: 4px;
}

.veditor-header-shortcuts {
    font-size: 11px;
    color: var(--ve-text-dim);
    flex: 1;
}

.veditor-header-shortcuts kbd {
    display: inline-block;
    padding: 1px 5px;
    border: 1px solid var(--ve-border);
    border-radius: 3px;
    background: var(--ve-bg-elevated);
    font-family: var(--ve-font);
    font-size: 10px;
    color: var(--ve-text-secondary);
    margin: 0 2px;
}

.veditor-header-actions {
    display: flex;
    align-items: center;
    gap: 6px;
}

.veditor-btn,
.veditor-tool-btn,
.veditor-tab,
.veditor-modal-close {
    cursor: pointer;
    position: relative;
}

/* Ensure SVGs inside buttons don't intercept clicks */
.veditor-btn svg,
.veditor-tool-btn svg,
.veditor-tab svg,
.veditor-modal-close svg {
    pointer-events: none;
}

.veditor-modal-close {
    background: none;
    border: 1px solid transparent;
    color: var(--ve-text-secondary);
    font-size: 16px;
    padding: 4px 8px;
    border-radius: var(--ve-radius-sm);
    transition: all var(--ve-transition);
}

.veditor-modal-close:hover {
    background: rgba(239, 68, 68, 0.15);
    border-color: var(--ve-danger);
    color: var(--ve-danger);
}

/* ── Monitor Area ────────────────────────────────────────────────── */

/* ── Infinite Canvas (Monitor) ───────────────────────────────────── */

.veditor-monitor-canvas {
    grid-area: monitor;
    background: #000;
    position: relative;
    min-height: 0;
    border-bottom: 1px solid var(--ve-border);
    overflow: hidden;
}

.veditor-monitor-viewport {
    width: 100%;
    height: 100%;
    overflow: hidden;
    cursor: default;
    position: relative;
}

.veditor-monitor-content {
    transform-origin: 0 0;
    will-change: transform;
    position: absolute;
    top: 0;
    left: 0;
}

.veditor-monitor-content video {
    display: block;
    max-width: none;
    max-height: none;
    width: 100%;
    height: auto;
}

/* ── Zoom Bar ────────────────────────────────────────────────────── */

.veditor-zoom-bar {
    position: absolute;
    bottom: 8px;
    left: 8px;
    display: flex;
    align-items: center;
    gap: 2px;
    background: rgba(0, 0, 0, 0.65);
    backdrop-filter: blur(6px);
    border: 1px solid var(--ve-glass-border);
    border-radius: var(--ve-radius-sm);
    padding: 2px 4px;
    z-index: 10;
}

.veditor-zoom-btn {
    padding: 3px 5px;
    font-size: 13px;
    color: var(--ve-text-secondary);
    transition: color 0.15s;
}

.veditor-zoom-btn:hover {
    color: #fff;
}

.veditor-zoom-label {
    font-size: 11px;
    font-family: var(--ve-font);
    color: var(--ve-text-secondary);
    min-width: 36px;
    text-align: center;
    user-select: none;
}

/* ── Transport Bar ───────────────────────────────────────────────── */

.veditor-modal-transport {
    grid-area: transport;
    border-bottom: 1px solid var(--ve-border);
}

.veditor-transport {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 6px 12px;
    background: var(--ve-glass-bg);
    backdrop-filter: blur(var(--ve-glass-blur));
}

.veditor-time {
    font-size: 13px;
    font-variant-numeric: tabular-nums;
    color: var(--ve-text-secondary);
    padding: 0 8px;
    letter-spacing: 0.5px;
    user-select: none;
}

/* ── Tools Panel (tabbed sidebar) ────────────────────────────────── */

.veditor-modal-tools {
    grid-area: tools;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    min-height: 0;
    border-left: 1px solid var(--ve-border);
    background: var(--ve-glass-bg);
    backdrop-filter: blur(var(--ve-glass-blur));
}

.veditor-tabs {
    display: flex;
    border-bottom: 1px solid var(--ve-border);
    flex-shrink: 0;
}

.veditor-tab {
    flex: 1;
    padding: 8px 4px;
    border: none;
    background: transparent;
    color: var(--ve-text-secondary);
    font-family: var(--ve-font);
    font-size: 11px;
    font-weight: 500;
    cursor: pointer;
    transition: all var(--ve-transition);
    text-align: center;
    border-bottom: 2px solid transparent;
    outline: none;
}

.veditor-tab:hover {
    color: var(--ve-text-primary);
    background: rgba(255, 255, 255, 0.03);
}

.veditor-tab.active {
    color: var(--ve-accent);
    border-bottom-color: var(--ve-accent);
    background: rgba(99, 102, 241, 0.06);
}

.veditor-tab:focus-visible {
    box-shadow: inset 0 0 0 2px var(--ve-accent-glow);
}

.veditor-tab-content {
    flex: 1;
    overflow-y: auto;
    padding: 12px;
}

.veditor-tab-pane {
    display: none;
}

.veditor-tab-pane.active {
    display: block;
}

/* Scrollbar in tools panel */
.veditor-tab-content::-webkit-scrollbar {
    width: 6px;
}

.veditor-tab-content::-webkit-scrollbar-track {
    background: transparent;
}

.veditor-tab-content::-webkit-scrollbar-thumb {
    background: var(--ve-bg-elevated);
    border-radius: 3px;
}

/* ── Tool Sections (inside tabs) ─────────────────────────────────── */

.veditor-modal-section {
    border: 1px solid var(--ve-border);
    border-radius: var(--ve-radius-md);
    padding: 10px 12px;
    background: rgba(255, 255, 255, 0.02);
    margin-bottom: 10px;
}

.veditor-modal-section:last-child {
    margin-bottom: 0;
}

.veditor-modal-section-title {
    margin: 0 0 8px 0;
    font-size: 11px;
    font-weight: 600;
    color: var(--ve-text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* ── Panel Sections ──────────────────────────────────────────────── */

.veditor-panel-section {
    margin-bottom: 12px;
    padding-bottom: 10px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.veditor-panel-section:last-child {
    border-bottom: none;
    margin-bottom: 0;
    padding-bottom: 0;
}

.veditor-section-label {
    font-size: 10px;
    font-weight: 600;
    color: var(--ve-text-dim);
    text-transform: uppercase;
    letter-spacing: 0.6px;
    margin-bottom: 6px;
}

.veditor-control-row {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 4px;
}

.veditor-control-row:last-child {
    margin-bottom: 0;
}

.veditor-control-label {
    font-size: 11px;
    color: var(--ve-text-secondary);
    white-space: nowrap;
    min-width: 32px;
}

.veditor-control-icon {
    display: inline-flex;
    align-items: center;
    color: var(--ve-text-dim);
    font-size: 14px;
    flex-shrink: 0;
}

/* ── Form Controls ───────────────────────────────────────────────── */

.veditor-input {
    background: var(--ve-bg-deep);
    border: 1px solid var(--ve-border);
    border-radius: var(--ve-radius-sm);
    color: var(--ve-text-primary);
    font-family: var(--ve-font);
    font-size: 12px;
    padding: 4px 6px;
    width: 56px;
    outline: none;
    transition: border-color var(--ve-transition);
}

.veditor-input:focus {
    border-color: var(--ve-accent);
}

.veditor-select {
    background: var(--ve-bg-deep);
    border: 1px solid var(--ve-border);
    border-radius: var(--ve-radius-sm);
    color: var(--ve-text-primary);
    font-family: var(--ve-font);
    font-size: 12px;
    padding: 4px 6px;
    outline: none;
    cursor: pointer;
    flex: 1;
    transition: border-color var(--ve-transition);
}

.veditor-select:focus {
    border-color: var(--ve-accent);
}

.veditor-checkbox {
    accent-color: var(--ve-accent);
    cursor: pointer;
}

.veditor-toggle-label {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 11px;
    color: var(--ve-text-secondary);
    cursor: pointer;
    white-space: nowrap;
}

.veditor-toggle-btn {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
    border: 1px solid var(--ve-border);
    border-radius: var(--ve-radius-sm);
    background: transparent;
    color: var(--ve-text-secondary);
    font-family: var(--ve-font);
    font-size: 12px;
    cursor: pointer;
    transition: all var(--ve-transition);
}

.veditor-toggle-btn:hover {
    background: rgba(255, 255, 255, 0.05);
}

.veditor-toggle-btn.active {
    background: var(--ve-accent);
    color: #fff;
    border-color: var(--ve-accent);
}

/* ── Preset Buttons ──────────────────────────────────────────────── */

.veditor-preset-row {
    display: flex;
    gap: 3px;
    flex-wrap: wrap;
}

.veditor-preset-btn {
    padding: 3px 8px;
    font-size: 11px;
    border: 1px solid var(--ve-border);
    border-radius: var(--ve-radius-sm);
    background: transparent;
    color: var(--ve-text-secondary);
    cursor: pointer;
    font-family: var(--ve-font);
    transition: all var(--ve-transition);
}

.veditor-preset-btn:hover {
    background: rgba(255, 255, 255, 0.05);
    color: var(--ve-text-primary);
}

.veditor-preset-btn.active {
    background: var(--ve-accent);
    color: #fff;
    border-color: var(--ve-accent);
}

/* ── Color Input ─────────────────────────────────────────────────── */

.veditor-color-input {
    width: 28px;
    height: 24px;
    border: 1px solid var(--ve-border);
    border-radius: var(--ve-radius-sm);
    background: transparent;
    cursor: pointer;
    padding: 1px;
    flex-shrink: 0;
}

/* ── Fade / Range Sliders ────────────────────────────────────────── */

.veditor-fade-slider,
.veditor-speed-slider,
.veditor-volume-slider {
    flex: 1;
    height: 4px;
    -webkit-appearance: none;
    appearance: none;
    background: var(--ve-border);
    border-radius: 2px;
    outline: none;
    cursor: pointer;
}

.veditor-fade-slider::-webkit-slider-thumb,
.veditor-speed-slider::-webkit-slider-thumb,
.veditor-volume-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: var(--ve-accent);
    cursor: pointer;
    border: none;
}

.veditor-fade-label {
    font-size: 11px;
    color: var(--ve-text-secondary);
    min-width: 32px;
    text-align: right;
}

/* ── Text Overlay Cards ──────────────────────────────────────────── */

.veditor-text-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
    font-size: 11px;
    font-weight: 600;
    color: var(--ve-text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.6px;
}

.veditor-text-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.veditor-text-card {
    border: 1px solid var(--ve-border);
    border-radius: var(--ve-radius-md);
    padding: 8px 10px;
    background: rgba(255, 255, 255, 0.02);
}

.veditor-text-card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 6px;
}

.veditor-text-card-title {
    font-size: 11px;
    font-weight: 600;
    color: var(--ve-text-secondary);
}

.veditor-text-del {
    padding: 2px 4px;
    font-size: 11px;
    color: var(--ve-text-dim);
}

.veditor-text-del:hover {
    color: #ef5555;
}

.veditor-text-textarea {
    width: 100%;
    background: var(--ve-bg-deep);
    border: 1px solid var(--ve-border);
    border-radius: var(--ve-radius-sm);
    color: var(--ve-text-primary);
    font-family: var(--ve-font);
    font-size: 12px;
    padding: 6px 8px;
    resize: vertical;
    outline: none;
    margin-bottom: 6px;
    box-sizing: border-box;
}

.veditor-text-textarea:focus {
    border-color: var(--ve-accent);
}

/* Font row */
.veditor-font-row {
    margin-bottom: 6px;
}

.veditor-font-select {
    flex: 1;
    min-width: 0;
}

.veditor-size-input {
    width: 48px;
}

/* Style buttons */
.veditor-style-row {
    margin-bottom: 6px;
}

.veditor-style-btn {
    padding: 3px 6px;
    font-size: 13px;
    border: 1px solid var(--ve-border);
    border-radius: var(--ve-radius-sm);
    background: transparent;
    color: var(--ve-text-secondary);
    cursor: pointer;
    transition: all var(--ve-transition);
}

.veditor-style-btn:hover {
    background: rgba(255, 255, 255, 0.05);
}

.veditor-style-btn.active {
    background: var(--ve-accent);
    color: #fff;
    border-color: var(--ve-accent);
}

/* Position & timing rows */
.veditor-pos-row {
    margin-bottom: 6px;
    flex-wrap: wrap;
}

.veditor-bg-row {
    margin-bottom: 6px;
}

.veditor-time-row {
    margin-top: 6px;
}

.veditor-time-input {
    width: 56px;
}

.veditor-time-unit {
    font-size: 11px;
    color: var(--ve-text-dim);
}

/* Speed panel specific */
.veditor-speed-input {
    width: 56px;
}

.veditor-speed-value {
    font-size: 12px;
    color: var(--ve-text-secondary);
    min-width: 40px;
    text-align: center;
}

/* ── Edit Toolbar ────────────────────────────────────────────────── */

.veditor-modal-toolbar {
    grid-area: toolbar;
    display: flex;
    align-items: center;
    gap: 2px;
    padding: 4px 12px;
    border-bottom: 1px solid var(--ve-border);
    background: var(--ve-bg-secondary);
}

.veditor-toolbar-group {
    display: flex;
    align-items: center;
    gap: 2px;
}

.veditor-toolbar-sep {
    width: 1px;
    height: 20px;
    background: var(--ve-border);
    margin: 0 6px;
}

.veditor-tool-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 4px;
    padding: 4px 10px;
    border: 1px solid transparent;
    border-radius: var(--ve-radius-sm);
    background: transparent;
    color: var(--ve-text-secondary);
    cursor: pointer;
    font-size: 12px;
    font-family: var(--ve-font);
    white-space: nowrap;
    transition: all var(--ve-transition);
    outline: none;
}

.veditor-tool-btn:hover {
    background: rgba(255, 255, 255, 0.05);
    color: var(--ve-text-primary);
}

.veditor-tool-btn:focus-visible {
    border-color: var(--ve-accent);
    box-shadow: 0 0 0 2px var(--ve-accent-glow);
}

.veditor-tool-btn.active {
    background: var(--ve-accent);
    color: #fff;
    border-color: transparent;
}

.veditor-tool-btn.active:hover {
    background: var(--ve-accent-hover);
}

/* ── Timeline Area ───────────────────────────────────────────────── */

.veditor-modal-timeline {
    grid-area: timeline;
    overflow: hidden;
    background: var(--ve-bg-deep);
    position: relative;
}

.veditor-nle-timeline {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
}

/* Timeline ruler (time markers) */
.veditor-timeline-ruler {
    height: 24px;
    background: var(--ve-bg-secondary);
    border-bottom: 1px solid var(--ve-border);
    flex-shrink: 0;
    position: relative;
}

/* Track container */
.veditor-timeline-tracks {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow-y: auto;
    min-height: 0;
}

/* Individual track lane */
.veditor-track {
    display: flex;
    min-height: 48px;
    border-bottom: 1px solid var(--ve-border);
}

.veditor-track-header {
    width: 56px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    padding: 4px;
    background: var(--ve-bg-secondary);
    border-right: 1px solid var(--ve-border);
    font-size: 11px;
    font-weight: 600;
    color: var(--ve-text-secondary);
    user-select: none;
}

.veditor-track-header-video {
    color: var(--ve-clip-video);
}

.veditor-track-header-audio {
    color: var(--ve-clip-audio);
}

.veditor-track-canvas-wrap {
    flex: 1;
    position: relative;
    min-width: 0;
}

.veditor-track-canvas-wrap canvas {
    display: block;
    width: 100%;
    height: 100%;
}

/* Playhead line */
.veditor-playhead {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 2px;
    background: var(--ve-playhead);
    pointer-events: none;
    z-index: 10;
    box-shadow: 0 0 6px rgba(249, 115, 22, 0.4);
}

.veditor-playhead::before {
    content: '';
    position: absolute;
    top: -2px;
    left: -4px;
    width: 0;
    height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid var(--ve-playhead);
}

/* ── Footer / Status Bar ─────────────────────────────────────────── */

.veditor-modal-footer {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    border-top: 1px solid var(--ve-border);
    background: var(--ve-glass-bg);
    backdrop-filter: blur(var(--ve-glass-blur));
    flex-shrink: 0;
}

/* ── Utility Classes ─────────────────────────────────────────────── */

.veditor-spacer {
    flex: 1;
}

.veditor-kbd-hint {
    font-size: 10px;
    color: var(--ve-text-dim);
    opacity: 0.6;
    margin-left: 2px;
}

/* ── Animations ──────────────────────────────────────────────────── */

@keyframes veditor-fade-in {
    from {
        opacity: 0;
        transform: scale(0.98);
    }

    to {
        opacity: 1;
        transform: scale(1);
    }
}

.veditor-modal-panel {
    animation: veditor-fade-in 0.2s ease-out;
}

/* ── Responsive (for smaller viewports) ──────────────────────────── */

@media (max-width: 900px) {
    .veditor-modal-panel {
        grid-template-areas:
            "header"
            "monitor"
            "transport"
            "tools"
            "toolbar"
            "timeline";
        grid-template-columns: 1fr;
        grid-template-rows: auto 1fr auto auto auto minmax(120px, 30%);
        width: 100vw;
        height: 100vh;
        border-radius: 0;
    }

    .veditor-modal-tools {
        border-left: none;
        border-top: 1px solid var(--ve-border);
        max-height: 200px;
    }
}

/* ── Keyboard Shortcuts Overlay ──────────────────────────────────── */

.veditor-shortcuts-backdrop {
    position: fixed;
    inset: 0;
    z-index: 100001;
    background: rgba(0, 0, 0, 0.6);
    backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
}

.veditor-shortcuts-panel {
    background: var(--ve-bg-secondary);
    border: 1px solid var(--ve-border);
    border-radius: var(--ve-radius-lg);
    padding: 20px 24px;
    max-width: 520px;
    width: 90%;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.veditor-shortcuts-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--ve-border);
}

.veditor-shortcuts-title {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
    color: var(--ve-text-primary);
}

.veditor-shortcuts-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
}

.veditor-shortcuts-section {
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.veditor-shortcuts-cat {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: var(--ve-accent);
    margin-bottom: 2px;
}

.veditor-shortcut-row {
    display: flex;
    align-items: center;
    gap: 8px;
}

.veditor-kbd {
    display: inline-block;
    min-width: 28px;
    padding: 2px 6px;
    font-size: 11px;
    font-family: var(--ve-font);
    background: var(--ve-bg-deep);
    border: 1px solid var(--ve-border);
    border-radius: 4px;
    color: var(--ve-text-primary);
    text-align: center;
}

.veditor-shortcut-desc {
    font-size: 12px;
    color: var(--ve-text-secondary);
}

/* ── Output Resolution Label ─────────────────────────────────────── */

.veditor-output-label {
    font-size: 12px;
    color: var(--ve-text-secondary);
    font-variant-numeric: tabular-nums;
}`;
if (!document.querySelector("#veditor-styles")) {
  const style = document.createElement("style");
  style.id = "veditor-styles";
  style.textContent = editorCSS;
  document.head.appendChild(style);
}
const NODE_TYPE = "FFMPEGAVideoEditor";
const PREVIEW_ROUTE = "/ffmpega/preview";
let _sharedModal = null;
function getModal() {
  if (!_sharedModal) {
    _sharedModal = new EditorModal({
      onApply: () => {
      },
      onCancel: () => {
      }
    });
  }
  return _sharedModal;
}
const PASSTHROUGH_EVENTS = [
  "contextmenu",
  "pointerdown",
  "mousewheel",
  "pointermove",
  "pointerup"
];
app.registerExtension({
  name: "ffmpega.videoeditor",
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
  node.color = "#2a4a5a";
  node.bgcolor = "#1a3a4a";
  let videoPath = "";
  let editState = {
    segments: [],
    cropRect: "",
    speedMap: {},
    volume: 1,
    textOverlays: [],
    transitions: []
  };
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
  const editorBtn = document.createElement("button");
  editorBtn.innerHTML = "Open Editor";
  editorBtn.style.cssText = `
        width: 100%;
        margin-top: 2px;
        background-color: #2a4a7a;
        color: #fff;
        border: 1px solid #3a5a9b;
        border-radius: 4px;
        padding: 6px;
        cursor: pointer;
        font-family: monospace;
        font-size: 12px;
        font-weight: 600;
        transition: background-color 0.2s;
    `;
  editorBtn.onmouseenter = () => {
    editorBtn.style.backgroundColor = "#3a5a9b";
  };
  editorBtn.onmouseleave = () => {
    editorBtn.style.backgroundColor = "#2a4a7a";
  };
  editorBtn.onclick = () => {
    if (!videoPath) {
      infoEl.textContent = "Load a video first";
      previewContainer.style.display = "";
      resizeNode();
      return;
    }
    const m = getModal();
    m.setCallbacks({
      onApply: (state) => {
        editState = state;
        _syncToWidgets(node, state);
        infoEl.textContent = "Edits applied";
        previewContainer.style.display = "";
        resizeNode();
      },
      onCancel: () => {
      }
    });
    m.open(videoPath, editState);
  };
  editorBtn.onpointerdown = (e) => e.stopPropagation();
  node.addDOMWidget("editor_button", "btn", editorBtn, { serialize: false });
  const previewContainer = document.createElement("div");
  previewContainer.className = "ffmpega_preview";
  previewContainer.style.cssText = "width:100%;background:#1a1a1a;border-radius:6px;overflow:hidden;position:relative;display:none;";
  const videoEl = document.createElement("video");
  videoEl.controls = true;
  videoEl.loop = true;
  videoEl.muted = true;
  videoEl.volume = 1;
  videoEl.setAttribute("aria-label", "Video editor preview");
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
  addDownloadOverlay(previewContainer, videoEl);
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
      console.warn("[VideoEditor] Upload error:", e);
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
  node.onDragOver = (e) => {
    var _a2, _b, _c;
    if ((_c = (_b = (_a2 = e == null ? void 0 : e.dataTransfer) == null ? void 0 : _a2.types) == null ? void 0 : _b.includes) == null ? void 0 : _c.call(_b, "Files")) return true;
    return false;
  };
  node.onDragDrop = async (e) => {
    var _a2, _b;
    const file = (_b = (_a2 = e == null ? void 0 : e.dataTransfer) == null ? void 0 : _a2.files) == null ? void 0 : _b[0];
    if (!file || !file.type.startsWith("video/")) return false;
    return await handleUpload(file);
  };
  const origOnRemoved = node.onRemoved;
  node.onRemoved = function() {
    fileInput == null ? void 0 : fileInput.remove();
    clearInterval(pollInterval);
    origOnRemoved == null ? void 0 : origOnRemoved.apply(this, arguments);
  };
  function loadPreview(path) {
    videoPath = path;
    previewContainer.style.display = "";
    const url = api.apiURL(`${PREVIEW_ROUTE}?path=${encodeURIComponent(path)}`);
    videoEl.src = url;
    const filename = path.split("/").pop() || path;
    infoEl.textContent = filename;
  }
  const origOnExecuted = node.onExecuted;
  node.onExecuted = function(data) {
    var _a2, _b;
    origOnExecuted == null ? void 0 : origOnExecuted.call(node, data);
    if ((_a2 = data == null ? void 0 : data.video_path) == null ? void 0 : _a2[0]) {
      loadPreview(data.video_path[0]);
      resizeNode();
      const autoW = (_b = node.widgets) == null ? void 0 : _b.find((w) => w.name === "auto_open_editor");
      if ((autoW == null ? void 0 : autoW.value) === true && !getModal().isOpen) {
        const m = getModal();
        m.setCallbacks({
          onApply: (state) => {
            editState = state;
            _syncToWidgets(node, state);
            infoEl.textContent = "Edits applied";
            previewContainer.style.display = "";
            resizeNode();
          },
          onCancel: () => {
          }
        });
        m.open(videoPath, editState);
      }
    }
  };
  const pathW = (_a = node.widgets) == null ? void 0 : _a.find((w) => w.name === "video_path");
  if ((pathW == null ? void 0 : pathW.value) && String(pathW.value).trim()) {
    loadPreview(String(pathW.value).trim());
  }
  let lastPath = "";
  const pollInterval = setInterval(() => {
    var _a2;
    if (!node.graph) {
      clearInterval(pollInterval);
      return;
    }
    const pw = (_a2 = node.widgets) == null ? void 0 : _a2.find((w) => w.name === "video_path");
    const val = (pw == null ? void 0 : pw.value) ? String(pw.value).trim() : "";
    if (val && val !== lastPath) {
      lastPath = val;
      loadPreview(val);
    }
  }, 500);
  _loadStateFromWidgets(node, editState);
}
function _syncToWidgets(node, state) {
  _setW(node, "_edit_segments", JSON.stringify(state.segments));
  _setW(node, "_crop_rect", state.cropRect);
  _setW(node, "_speed_map", JSON.stringify(state.speedMap));
  _setW(node, "_volume", state.volume);
  _setW(node, "_text_overlays", JSON.stringify(state.textOverlays));
  _setW(node, "_transitions", JSON.stringify(state.transitions));
  _setW(node, "_edit_action", "passthrough");
}
function _setW(node, name, value) {
  var _a;
  const w = (_a = node.widgets) == null ? void 0 : _a.find((w2) => w2.name === name);
  if (w) w.value = value;
  else {
    if (!node.properties) node.properties = {};
    node.properties[name] = value;
  }
}
function _getW(node, name, fb = "") {
  var _a, _b;
  const w = (_a = node.widgets) == null ? void 0 : _a.find((w2) => w2.name === name);
  if (w) return String(w.value ?? fb);
  return String(((_b = node.properties) == null ? void 0 : _b[name]) ?? fb);
}
function _loadStateFromWidgets(node, editState) {
  try {
    const s = JSON.parse(_getW(node, "_edit_segments", "[]"));
    if (Array.isArray(s)) editState.segments = s;
  } catch {
  }
  try {
    const m = JSON.parse(_getW(node, "_speed_map", "{}"));
    if (typeof m === "object") editState.speedMap = m;
  } catch {
  }
  try {
    const v = parseFloat(_getW(node, "_volume", "1.0"));
    if (!isNaN(v)) editState.volume = v;
  } catch {
  }
  try {
    const o = JSON.parse(_getW(node, "_text_overlays", "[]"));
    if (Array.isArray(o)) editState.textOverlays = o;
  } catch {
  }
  editState.cropRect = _getW(node, "_crop_rect", "");
}
