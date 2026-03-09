var __defProp = Object.defineProperty;
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);
import { v as iconStepBack, w as iconPlay, x as iconStepForward, y as iconPause, z as iconCursor, A as iconScissors, B as iconSplit, D as iconTrash, E as iconReset, F as iconReverse, G as iconCurve, H as iconFilm } from "./CropOverlay-RBSIEwzt.js";
function captureFrame(video, time) {
  return new Promise((resolve) => {
    video.currentTime = time;
    const handler = () => {
      video.removeEventListener("seeked", handler);
      const oc = new OffscreenCanvas(video.videoWidth, video.videoHeight);
      const ctx = oc.getContext("2d");
      ctx.drawImage(video, 0, 0);
      resolve(oc);
    };
    video.addEventListener("seeked", handler);
  });
}
async function captureFrames(video, count) {
  const dur = video.duration;
  if (!dur || !isFinite(dur) || dur <= 0) return [];
  const results = [];
  for (let i = 0; i < count; i++) {
    const t = dur * i / Math.max(count - 1, 1);
    results.push(await captureFrame(video, t));
  }
  return results;
}
function viewUrl(entry) {
  const params = new URLSearchParams({
    filename: entry.filename,
    subfolder: entry.subfolder || "",
    type: entry.type || "output"
  });
  return `/view?${params.toString()}`;
}
function fmtDuration(d) {
  if (!d || !isFinite(d)) return "0:00";
  const m = Math.floor(d / 60);
  const s = Math.floor(d % 60);
  const ms = Math.floor(d % 1 * 10);
  return m > 0 ? `${m}:${s.toString().padStart(2, "0")}.${ms}` : `${s}.${ms}s`;
}
let _nextId = 0;
function genId() {
  return `seg_${++_nextId}_${Date.now()}`;
}
class EditManager {
  constructor() {
    __publicField(this, "segments", []);
    __publicField(this, "videoDuration", 0);
    __publicField(this, "node", null);
  }
  /** Bind to a ComfyUI node for widget sync */
  bind(node) {
    this.node = node;
  }
  /** Initialize with a single segment spanning the full video */
  init(duration) {
    this.videoDuration = duration;
    this.segments = [{ id: genId(), start: 0, end: duration }];
  }
  /** Add a new segment. Returns the new segment. */
  addSegment(start, end) {
    start = Math.max(0, start);
    end = Math.min(this.videoDuration, end);
    if (end <= start) {
      throw new Error(`Invalid segment: end (${end}) <= start (${start})`);
    }
    const seg = { id: genId(), start, end };
    const idx = this.segments.findIndex((s) => s.start > start);
    if (idx === -1) {
      this.segments.push(seg);
    } else {
      this.segments.splice(idx, 0, seg);
    }
    return seg;
  }
  /** Remove a segment by ID */
  removeSegment(id) {
    const idx = this.segments.findIndex((s) => s.id === id);
    if (idx === -1) return false;
    this.segments.splice(idx, 1);
    return true;
  }
  /** Split the segment containing the given timestamp into two */
  splitAt(timestamp) {
    const idx = this.segments.findIndex(
      (s) => timestamp > s.start && timestamp < s.end
    );
    if (idx === -1) return false;
    const seg = this.segments[idx];
    const left = { id: seg.id, start: seg.start, end: timestamp };
    const right = { id: genId(), start: timestamp, end: seg.end };
    this.segments.splice(idx, 1, left, right);
    return true;
  }
  /** Update a segment's start/end (e.g., from a trim handle drag) */
  updateSegment(id, start, end) {
    const seg = this.segments.find((s) => s.id === id);
    if (!seg) return false;
    start = Math.max(0, start);
    end = Math.min(this.videoDuration, end);
    if (end <= start + 0.05) return false;
    seg.start = start;
    seg.end = end;
    return true;
  }
  /** Move a segment from one position to another */
  reorderSegments(fromIdx, toIdx) {
    if (fromIdx < 0 || fromIdx >= this.segments.length) return false;
    if (toIdx < 0 || toIdx >= this.segments.length) return false;
    if (fromIdx === toIdx) return false;
    const [seg] = this.segments.splice(fromIdx, 1);
    this.segments.splice(toIdx, 0, seg);
    return true;
  }
  /** Reset to a single full-length segment */
  reset() {
    this.segments = [{ id: genId(), start: 0, end: this.videoDuration }];
  }
  /** Total output duration of all segments */
  getOutputDuration() {
    return this.segments.reduce((sum, s) => sum + (s.end - s.start), 0);
  }
  /** Serialize segments to JSON array of [start, end] pairs */
  toJSON() {
    return this.segments.map((s) => [s.start, s.end]);
  }
  /** Check if segments differ from a full unedited video */
  hasEdits() {
    if (this.segments.length !== 1) return true;
    const s = this.segments[0];
    return Math.abs(s.start) > 0.01 || Math.abs(s.end - this.videoDuration) > 0.01;
  }
  /**
   * Map output timeline position → source video timestamp.
   * Output time 0 = start of first segment, output flows continuously
   * through all segments without gaps.
   */
  outputTimeToSource(outputTime) {
    let accumulated = 0;
    for (const seg of this.segments) {
      const segDur = seg.end - seg.start;
      if (outputTime <= accumulated + segDur) {
        return seg.start + (outputTime - accumulated);
      }
      accumulated += segDur;
    }
    const last = this.segments[this.segments.length - 1];
    return last ? last.end : 0;
  }
  /**
   * Map source video timestamp → output timeline position.
   * Returns -1 if the source time is in a deleted gap.
   */
  sourceTimeToOutput(sourceTime) {
    let accumulated = 0;
    for (const seg of this.segments) {
      if (sourceTime >= seg.start && sourceTime <= seg.end) {
        return accumulated + (sourceTime - seg.start);
      }
      accumulated += seg.end - seg.start;
    }
    return -1;
  }
  /** Check if a source timestamp falls in a deleted gap */
  isInGap(sourceTime) {
    return !this.segments.some(
      (s) => sourceTime >= s.start && sourceTime <= s.end
    );
  }
  /** Sync segments to the hidden widgets on the node */
  syncToWidget() {
    var _a, _b;
    if (!this.node) return;
    const json = JSON.stringify(this.toJSON());
    const action = this.hasEdits() ? "passthrough" : "none";
    const segWidget = (_a = this.node.widgets) == null ? void 0 : _a.find((w) => w.name === "_edit_segments");
    if (segWidget) {
      segWidget.value = json;
    } else {
      if (!this.node.properties) this.node.properties = {};
      this.node.properties["_edit_segments"] = json;
    }
    const actWidget = (_b = this.node.widgets) == null ? void 0 : _b.find((w) => w.name === "_edit_action");
    if (actWidget) {
      actWidget.value = action;
    } else {
      if (!this.node.properties) this.node.properties = {};
      this.node.properties["_edit_action"] = action;
    }
  }
}
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
const TRACK_H = 48;
const TRACK_PAD = 12;
const HANDLE_W = 8;
const PLAYHEAD_W = 2;
const SEG_COLOR = "rgba(90, 170, 200, 0.5)";
const SEG_BORDER = "#5ac";
const EXCLUDED_COLOR = "rgba(30, 30, 30, 0.85)";
const EXCLUDED_STRIPE = "rgba(60, 60, 60, 0.6)";
const HANDLE_COLOR = "#fff";
const HANDLE_HOVER = "#00ddff";
const PLAYHEAD_COLOR = "#ff5555";
const TRACK_BG = "#1a1a1a";
class EditTimeline {
  constructor(manager, callbacks) {
    __publicField(this, "canvas");
    __publicField(this, "container");
    __publicField(this, "manager");
    __publicField(this, "callbacks");
    __publicField(this, "geometry", null);
    __publicField(this, "playhead", 0);
    __publicField(this, "hoveredHandle", null);
    __publicField(this, "drag", { type: "none" });
    // Bound handlers (stored so destroy() can remove the exact same reference)
    __publicField(this, "_boundMouseDown", this._onMouseDown.bind(this));
    __publicField(this, "_boundMouseMove", this._onMouseMove.bind(this));
    __publicField(this, "_boundMouseUp", this._onMouseUp.bind(this));
    __publicField(this, "_boundDblClick", this._onDoubleClick.bind(this));
    this.manager = manager;
    this.callbacks = callbacks;
    this.container = document.createElement("div");
    this.container.className = "ll_edit_timeline";
    this.canvas = document.createElement("canvas");
    this.canvas.className = "ll_edit_canvas";
    this.canvas.style.cssText = "width:100%;cursor:pointer;border-radius:4px;";
    this.container.appendChild(this.canvas);
    this._bindEvents();
  }
  get element() {
    return this.container;
  }
  /** Set the playhead position */
  setPlayhead(time) {
    this.playhead = Math.max(0, Math.min(time, this.manager.videoDuration));
    this.render();
  }
  /** Full render pass */
  render() {
    var _a;
    const dur = this.manager.videoDuration;
    if (dur <= 0) return;
    const rect = (_a = this.canvas.parentElement) == null ? void 0 : _a.getBoundingClientRect();
    const w = rect ? rect.width : 400;
    const h = TRACK_H + TRACK_PAD * 2 + 24;
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = w * dpr;
    this.canvas.height = h * dpr;
    this.canvas.style.height = `${h}px`;
    const ctx = this.canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    const trackX = TRACK_PAD;
    const trackY = TRACK_PAD;
    const trackW = w - TRACK_PAD * 2;
    const trackH = TRACK_H;
    ctx.fillStyle = "#111";
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = TRACK_BG;
    ctx.fillRect(trackX, trackY, trackW, trackH);
    ctx.strokeStyle = "#333";
    ctx.lineWidth = 1;
    ctx.strokeRect(trackX, trackY, trackW, trackH);
    const segGeos = [];
    ctx.fillStyle = EXCLUDED_COLOR;
    ctx.fillRect(trackX, trackY, trackW, trackH);
    ctx.save();
    ctx.beginPath();
    ctx.rect(trackX, trackY, trackW, trackH);
    ctx.clip();
    ctx.strokeStyle = EXCLUDED_STRIPE;
    ctx.lineWidth = 1;
    for (let x = -h; x < w + h; x += 8) {
      ctx.beginPath();
      ctx.moveTo(x, trackY);
      ctx.lineTo(x + h, trackY + trackH);
      ctx.stroke();
    }
    ctx.restore();
    for (const seg of this.manager.segments) {
      const x = trackX + seg.start / dur * trackW;
      const segW = (seg.end - seg.start) / dur * trackW;
      ctx.fillStyle = SEG_COLOR;
      ctx.fillRect(x, trackY, segW, trackH);
      ctx.strokeStyle = SEG_BORDER;
      ctx.lineWidth = 1.5;
      ctx.strokeRect(x, trackY, segW, trackH);
      if (segW > 40) {
        const label = fmtDuration(seg.end - seg.start);
        ctx.font = "10px monospace";
        ctx.fillStyle = "#ddd";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(label, x + segW / 2, trackY + trackH / 2);
      }
      const isHoveredL = this.hoveredHandle === `${seg.id}-left`;
      const isHoveredR = this.hoveredHandle === `${seg.id}-right`;
      ctx.fillStyle = isHoveredL ? HANDLE_HOVER : HANDLE_COLOR;
      ctx.fillRect(x, trackY, HANDLE_W, trackH);
      ctx.fillStyle = "#333";
      ctx.fillRect(x + 3, trackY + trackH / 2 - 6, 2, 12);
      ctx.fillStyle = isHoveredR ? HANDLE_HOVER : HANDLE_COLOR;
      ctx.fillRect(x + segW - HANDLE_W, trackY, HANDLE_W, trackH);
      ctx.fillStyle = "#333";
      ctx.fillRect(x + segW - HANDLE_W + 3, trackY + trackH / 2 - 6, 2, 12);
      segGeos.push({ id: seg.id, x, w: segW, start: seg.start, end: seg.end });
    }
    this.geometry = { trackX, trackY, trackW, trackH, duration: dur, segments: segGeos };
    const phX = trackX + this.playhead / dur * trackW;
    ctx.fillStyle = PLAYHEAD_COLOR;
    ctx.fillRect(phX - PLAYHEAD_W / 2, trackY - 4, PLAYHEAD_W, trackH + 8);
    ctx.beginPath();
    ctx.moveTo(phX - 5, trackY - 4);
    ctx.lineTo(phX + 5, trackY - 4);
    ctx.lineTo(phX, trackY + 2);
    ctx.closePath();
    ctx.fill();
    ctx.font = "10px monospace";
    ctx.fillStyle = "#666";
    ctx.textAlign = "left";
    ctx.textBaseline = "top";
    ctx.fillText("0:00", trackX, trackY + trackH + 4);
    ctx.textAlign = "right";
    ctx.fillText(fmtDuration(dur), trackX + trackW, trackY + trackH + 4);
    ctx.textAlign = "center";
    ctx.fillStyle = PLAYHEAD_COLOR;
    const phLabel = fmtDuration(this.playhead);
    ctx.fillText(phLabel, Math.max(trackX + 20, Math.min(phX, trackX + trackW - 20)), trackY + trackH + 4);
    const outDur = this.manager.getOutputDuration();
    ctx.textAlign = "center";
    ctx.fillStyle = "#5ac";
    ctx.fillText(
      `Output: ${fmtDuration(outDur)} / ${fmtDuration(dur)} (${this.manager.segments.length} segment${this.manager.segments.length !== 1 ? "s" : ""})`,
      w / 2,
      trackY + trackH + 14
    );
  }
  _bindEvents() {
    this.canvas.addEventListener("mousedown", this._boundMouseDown);
    this.canvas.addEventListener("mousemove", this._boundMouseMove);
    document.addEventListener("mouseup", this._boundMouseUp);
    this.canvas.addEventListener("dblclick", this._boundDblClick);
  }
  _canvasToTrack(clientX, clientY) {
    const rect = this.canvas.getBoundingClientRect();
    return {
      x: clientX - rect.left,
      y: clientY - rect.top
    };
  }
  _xToTime(x) {
    if (!this.geometry) return 0;
    const { trackX, trackW, duration } = this.geometry;
    return Math.max(0, Math.min(duration, (x - trackX) / trackW * duration));
  }
  _hitTest(cx, cy) {
    if (!this.geometry) return { type: "none" };
    const { trackX, trackY, trackW, trackH, duration } = this.geometry;
    if (cy < trackY - 6 || cy > trackY + trackH + 6) return { type: "none" };
    const phX = trackX + this.playhead / duration * trackW;
    if (Math.abs(cx - phX) < 6) return { type: "playhead" };
    for (const seg of this.geometry.segments) {
      if (cx >= seg.x - 2 && cx <= seg.x + HANDLE_W + 2 && cy >= trackY && cy <= trackY + trackH) {
        return { type: "handle-left", segId: seg.id };
      }
      if (cx >= seg.x + seg.w - HANDLE_W - 2 && cx <= seg.x + seg.w + 2 && cy >= trackY && cy <= trackY + trackH) {
        return { type: "handle-right", segId: seg.id };
      }
    }
    if (cx >= trackX && cx <= trackX + trackW) {
      return { type: "track" };
    }
    return { type: "none" };
  }
  _onMouseDown(e) {
    var _a, _b;
    e.stopPropagation();
    const { x, y } = this._canvasToTrack(e.clientX, e.clientY);
    const hit = this._hitTest(x, y);
    if (hit.type === "handle-left" && hit.segId) {
      const seg = this.manager.segments.find((s) => s.id === hit.segId);
      if (seg) {
        this.drag = { type: "handle-left", segId: hit.segId, startX: e.clientX, origStart: seg.start };
      }
    } else if (hit.type === "handle-right" && hit.segId) {
      const seg = this.manager.segments.find((s) => s.id === hit.segId);
      if (seg) {
        this.drag = { type: "handle-right", segId: hit.segId, startX: e.clientX, origEnd: seg.end };
      }
    } else if (hit.type === "playhead") {
      this.drag = { type: "playhead", startX: e.clientX, origTime: this.playhead };
      (_b = (_a = this.callbacks).onDragStart) == null ? void 0 : _b.call(_a);
    } else if (hit.type === "track") {
      this.playhead = this._xToTime(x);
      this.callbacks.onPlayheadChanged(this.playhead);
      this.render();
    }
  }
  _onMouseMove(e) {
    const { x, y } = this._canvasToTrack(e.clientX, e.clientY);
    if (this.drag.type === "none") {
      const hit = this._hitTest(x, y);
      if (hit.type === "handle-left" || hit.type === "handle-right") {
        this.canvas.style.cursor = "ew-resize";
        this.hoveredHandle = hit.segId ? `${hit.segId}-${hit.type === "handle-left" ? "left" : "right"}` : null;
      } else if (hit.type === "playhead") {
        this.canvas.style.cursor = "col-resize";
        this.hoveredHandle = null;
      } else {
        this.canvas.style.cursor = "pointer";
        this.hoveredHandle = null;
      }
      this.render();
      return;
    }
    if (!this.geometry) return;
    const { trackW, duration } = this.geometry;
    const drag = this.drag;
    const dx = e.clientX - drag.startX;
    const dt = dx / trackW * duration;
    if (drag.type === "handle-left") {
      const newStart = Math.max(0, drag.origStart + dt);
      const seg = this.manager.segments.find((s) => s.id === drag.segId);
      if (seg) this.manager.updateSegment(drag.segId, newStart, seg.end);
      this.callbacks.onTrimHandleDrag(newStart);
      this.render();
    } else if (drag.type === "handle-right") {
      const newEnd = Math.min(duration, drag.origEnd + dt);
      const seg = this.manager.segments.find((s) => s.id === drag.segId);
      if (seg) this.manager.updateSegment(drag.segId, seg.start, newEnd);
      this.callbacks.onTrimHandleDrag(newEnd);
      this.render();
    } else if (drag.type === "playhead") {
      this.playhead = Math.max(0, Math.min(duration, drag.origTime + dt));
      this.callbacks.onPlayheadChanged(this.playhead);
      this.render();
    }
  }
  _onMouseUp(_e) {
    var _a, _b;
    if (this.drag.type !== "none") {
      if (this.drag.type === "handle-left" || this.drag.type === "handle-right") {
        this.callbacks.onSegmentsChanged();
      }
      if (this.drag.type === "playhead") {
        (_b = (_a = this.callbacks).onDragEnd) == null ? void 0 : _b.call(_a);
      }
      this.drag = { type: "none" };
    }
  }
  _onDoubleClick(e) {
    e.stopPropagation();
    const { x, y } = this._canvasToTrack(e.clientX, e.clientY);
    if (!this.geometry) return;
    const { trackY, trackH } = this.geometry;
    if (y < trackY || y > trackY + trackH) return;
    const time = this._xToTime(x);
    if (this.manager.splitAt(time)) {
      this.callbacks.onSegmentsChanged();
      this.render();
    }
  }
  /** Cleanup event listeners */
  destroy() {
    this.canvas.removeEventListener("mousedown", this._boundMouseDown);
    this.canvas.removeEventListener("mousemove", this._boundMouseMove);
    document.removeEventListener("mouseup", this._boundMouseUp);
    this.canvas.removeEventListener("dblclick", this._boundDblClick);
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
export {
  EditManager as E,
  NLETimeline as N,
  SpeedControl as S,
  TransportBar as T,
  UndoManager as U,
  EditToolbar as a,
  captureFrame as b,
  captureFrames as c,
  fmtDuration as f,
  viewUrl as v
};
