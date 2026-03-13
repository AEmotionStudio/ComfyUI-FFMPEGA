var __defProp = Object.defineProperty;
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);
import { D as iconSkipStart, E as iconStepBack, F as iconPlay, G as iconStepForward, H as iconRepeat, I as iconPause, J as iconCursor, K as iconSplit, L as iconTrash, M as iconReset, N as iconReverse, O as iconCurve, P as iconFilm, u as iconGauge } from "./CropOverlay-CFlj408e.js";
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
    __publicField(this, "loopBtn");
    __publicField(this, "shuttleSpeed", 1);
    __publicField(this, "_loopEnabled", true);
    __publicField(this, "_keyHandler", null);
    __publicField(this, "_editManager", null);
    __publicField(this, "_animFrameId", null);
    __publicField(this, "_currentSegIdx", 0);
    __publicField(this, "_seekLock", false);
    /** When a seek is pending, this holds the desired time */
    __publicField(this, "_targetTime", null);
    __publicField(this, "_transitionPreview", null);
    __publicField(this, "_transitions", []);
    __publicField(this, "_lastSegIdx", -1);
    __publicField(this, "_audioEditManager", null);
    this.callbacks = callbacks;
    this.container = document.createElement("div");
    this.container.className = "veditor-transport";
    this.container.setAttribute("data-tool-id", "veditor-transport");
    this.container.setAttribute("aria-label", "Video transport controls");
    this.container.setAttribute("role", "toolbar");
    const goStart = this._makeBtn(iconSkipStart, "Go to start (Home)", () => this._goToStart(), "veditor-go-start");
    const stepBack = this._makeBtn(iconStepBack, "Step back 1 frame (←)", () => this._stepFrame(-1), "veditor-step-back");
    this.playBtn = this._makeBtn(iconPlay, "Play / Pause (Space or K)", () => this._togglePlay(), "veditor-play-btn");
    const stepFwd = this._makeBtn(iconStepForward, "Step forward 1 frame (→)", () => this._stepFrame(1), "veditor-step-forward");
    this.timeDisplay = document.createElement("span");
    this.timeDisplay.className = "veditor-time";
    this.timeDisplay.textContent = "00:00.00 / 00:00.00";
    this.timeDisplay.setAttribute("data-tool-id", "veditor-timecode");
    this.timeDisplay.setAttribute("aria-label", "Current time / total duration");
    this.timeDisplay.setAttribute("aria-live", "polite");
    this.loopBtn = this._makeBtn(iconRepeat, "Toggle loop playback", () => this._toggleLoop(), "veditor-loop-btn");
    this.loopBtn.classList.add("active");
    this.loopBtn.setAttribute("aria-pressed", "true");
    this.container.append(goStart, stepBack, this.playBtn, stepFwd, this.timeDisplay, this.loopBtn);
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
      var _a;
      this.playBtn.innerHTML = iconPlay;
      this.callbacks.onPlayStateChange(false);
      this._stopSegmentPolling();
      (_a = this._transitionPreview) == null ? void 0 : _a.clear();
    });
    video.addEventListener("loadedmetadata", () => {
      this._updateTimeDisplay();
    });
    video.addEventListener("ended", () => {
      if (this._loopEnabled && this._editManager) {
        const segs = this._editManager.segments;
        if (segs.length > 0) {
          this._currentSegIdx = 0;
          this.video.currentTime = segs[0].start;
          this.video.play();
        }
      }
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
  /** Bind transition data for live preview */
  setTransitions(transitions) {
    this._transitions = transitions;
  }
  /** Bind the transition preview engine */
  setTransitionPreview(preview) {
    this._transitionPreview = preview;
  }
  /** Bind the audio edit manager for live volume enforcement */
  setAudioEditManager(mgr) {
    this._audioEditManager = mgr;
  }
  /** Update playback rate live (used by speed controls for preview). */
  setPlaybackRate(rate) {
    this.shuttleSpeed = rate;
    if (this.video && !this.video.paused) {
      this.video.playbackRate = rate;
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
        if (this._loopEnabled) {
          this.video.currentTime = segs[0].start;
        } else {
          this.video.pause();
          this.video.currentTime = segs[segs.length - 1].end - 0.02;
        }
      }
      return;
    }
    if (t < seg.start - 0.05) {
      this.video.currentTime = seg.start;
    }
    if (this._transitionPreview) {
      const isNewSeg = this._lastSegIdx !== this._currentSegIdx;
      this._lastSegIdx = this._currentSegIdx;
      const outTransition = this._currentSegIdx < this._transitions.length ? this._transitions[this._currentSegIdx] : null;
      const inTransition = this._currentSegIdx > 0 && this._currentSegIdx - 1 < this._transitions.length ? this._transitions[this._currentSegIdx - 1] : null;
      const timeToEnd = seg.end - t;
      const timeFromStart = t - seg.start;
      const outHalf = outTransition ? outTransition.duration / 2 : 0;
      const inHalf = inTransition ? inTransition.duration / 2 : 0;
      if (outTransition && timeToEnd <= outHalf) {
        this._transitionPreview.update(t, seg.end, seg.start, outTransition, false);
      } else if (inTransition && timeFromStart <= inHalf) {
        this._transitionPreview.update(t, seg.end, seg.start, inTransition, isNewSeg);
      } else {
        this._transitionPreview.clear();
      }
    }
    if (this._audioEditManager && this.video) {
      const vol = this._audioEditManager.getVolumeAtTime(t);
      this.video.volume = Math.min(1, Math.max(0, vol));
      this.video.muted = vol < 0.01;
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
  /** Toggle loop on/off */
  _toggleLoop() {
    this._loopEnabled = !this._loopEnabled;
    this.loopBtn.classList.toggle("active", this._loopEnabled);
    this.loopBtn.setAttribute("aria-pressed", String(this._loopEnabled));
  }
  /** Jump to start of first segment (or time 0). */
  _goToStart() {
    if (!this.video) return;
    this.video.pause();
    this._currentSegIdx = 0;
    if (this._editManager) {
      const segs = this._editManager.segments;
      if (segs.length > 0) {
        this.seekTo(segs[0].start);
        return;
      }
    }
    this.seekTo(0);
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
      case "home":
        e.preventDefault();
        this._goToStart();
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
const DEFAULT_SNAP_THRESHOLD_PX = 8;
function snapToEdges(time, edges, thresholdPx = DEFAULT_SNAP_THRESHOLD_PX, trackW = 1, duration = 1) {
  const thresholdTime = thresholdPx / trackW * duration;
  let closest = null;
  let closestDist = Infinity;
  for (const edge of edges) {
    const dist = Math.abs(time - edge);
    if (dist < thresholdTime && dist < closestDist) {
      closest = edge;
      closestDist = dist;
    }
  }
  if (closest !== null) {
    return { time: closest, snapped: true, snapTarget: closest };
  }
  return { time, snapped: false };
}
function collectEdges(segments, excludeId, excludeSide) {
  const edges = [];
  for (const seg of segments) {
    if (seg.id === excludeId) {
      if (excludeSide !== "start") edges.push(seg.start);
      if (excludeSide !== "end") edges.push(seg.end);
    } else {
      edges.push(seg.start, seg.end);
    }
  }
  edges.push(0);
  return edges;
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
    __publicField(this, "_snapping", true);
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
  /** Set snapping enabled/disabled */
  setSnapping(enabled) {
    this._snapping = enabled;
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
      let newHover = null;
      if (hit.type === "handle-left" || hit.type === "handle-right") {
        this.canvas.style.cursor = "ew-resize";
        newHover = hit.segId ? `${hit.segId}-${hit.type === "handle-left" ? "left" : "right"}` : null;
      } else if (hit.type === "playhead") {
        this.canvas.style.cursor = "col-resize";
      } else {
        this.canvas.style.cursor = "pointer";
      }
      if (newHover !== this.hoveredHandle) {
        this.hoveredHandle = newHover;
        this.render();
      }
      return;
    }
    if (!this.geometry) return;
    const { trackW, duration } = this.geometry;
    const drag = this.drag;
    const dx = e.clientX - drag.startX;
    const dt = dx / trackW * duration;
    if (drag.type === "handle-left") {
      let newStart = Math.max(0, drag.origStart + dt);
      if (this._snapping) {
        const edges = collectEdges(this.manager.segments, drag.segId, "start");
        const snap = snapToEdges(newStart, edges, 8, trackW, duration);
        newStart = snap.time;
      }
      const seg = this.manager.segments.find((s) => s.id === drag.segId);
      if (seg) this.manager.updateSegment(drag.segId, newStart, seg.end);
      this.callbacks.onTrimHandleDrag(newStart);
      this.render();
    } else if (drag.type === "handle-right") {
      let newEnd = Math.min(duration, drag.origEnd + dt);
      if (this._snapping) {
        const edges = collectEdges(this.manager.segments, drag.segId, "end");
        const snap = snapToEdges(newEnd, edges, 8, trackW, duration);
        newEnd = snap.time;
      }
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
const MIN_ZOOM = 1;
const MAX_ZOOM = 20;
const ZOOM_STEP = 1.25;
const HEADER_W = 56;
class NLETimeline {
  constructor(manager, callbacks) {
    __publicField(this, "container");
    __publicField(this, "scrollWrapper");
    __publicField(this, "scrollInner");
    __publicField(this, "ruler");
    __publicField(this, "tracksContainer");
    __publicField(this, "videoTrack");
    __publicField(this, "audioTrack");
    __publicField(this, "editTimeline");
    __publicField(this, "audioTimeline", null);
    __publicField(this, "manager");
    __publicField(this, "playheadEl");
    __publicField(this, "_snapping", true);
    __publicField(this, "_zoom", 1);
    __publicField(this, "_zoomLabel");
    this.manager = manager;
    this.container = document.createElement("div");
    this.container.className = "veditor-nle-timeline";
    this.container.setAttribute("data-tool-id", "veditor-timeline");
    this.container.setAttribute("aria-label", "Multi-track editing timeline");
    this.container.setAttribute("role", "region");
    const toolbar = document.createElement("div");
    toolbar.className = "veditor-timeline-toolbar";
    toolbar.style.cssText = "display:flex;align-items:center;justify-content:space-between;padding:2px 4px;gap:4px;flex-shrink:0;";
    const snapBtn = document.createElement("button");
    snapBtn.className = "veditor-btn veditor-snap-btn active";
    snapBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg> Snap`;
    snapBtn.title = "Toggle clip snapping (S)";
    snapBtn.setAttribute("data-tool-id", "veditor-snap-toggle");
    snapBtn.setAttribute("aria-label", "Toggle clip snapping");
    snapBtn.style.cssText = "font-size:11px;padding:2px 8px;border-radius:4px;";
    snapBtn.addEventListener("click", () => {
      var _a;
      this._snapping = !this._snapping;
      snapBtn.classList.toggle("active", this._snapping);
      this.editTimeline.setSnapping(this._snapping);
      (_a = this.audioTimeline) == null ? void 0 : _a.setSnapping(this._snapping);
    });
    const zoomGroup = document.createElement("div");
    zoomGroup.style.cssText = "display:flex;align-items:center;gap:2px;";
    const zoomOutBtn = this._makeToolbarBtn("−", "Zoom out timeline", "veditor-tl-zoom-out", () => this.setZoom(this._zoom / ZOOM_STEP));
    const zoomInBtn = this._makeToolbarBtn("+", "Zoom in timeline", "veditor-tl-zoom-in", () => this.setZoom(this._zoom * ZOOM_STEP));
    const zoomFitBtn = this._makeToolbarBtn("Fit", "Fit timeline to view", "veditor-tl-zoom-fit", () => this.setZoom(1));
    this._zoomLabel = document.createElement("span");
    this._zoomLabel.style.cssText = "font-size:10px;color:rgba(255,255,255,0.4);min-width:36px;text-align:center;font-variant-numeric:tabular-nums;";
    this._zoomLabel.textContent = "1.0×";
    zoomGroup.append(zoomOutBtn, this._zoomLabel, zoomInBtn, zoomFitBtn);
    toolbar.append(snapBtn, zoomGroup);
    this.scrollWrapper = document.createElement("div");
    this.scrollWrapper.className = "veditor-timeline-scroll";
    this.scrollWrapper.style.cssText = "flex:1;overflow-x:auto;overflow-y:hidden;min-height:0;position:relative;";
    this.scrollInner = document.createElement("div");
    this.scrollInner.className = "veditor-timeline-scroll-inner";
    this.scrollInner.style.cssText = "min-width:100%;position:relative;display:flex;flex-direction:column;";
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
    this.playheadEl = document.createElement("div");
    this.playheadEl.className = "veditor-playhead";
    this.playheadEl.style.left = `${HEADER_W}px`;
    this.playheadEl.setAttribute("data-tool-id", "veditor-playhead");
    this.playheadEl.setAttribute("aria-label", "Playhead position indicator");
    this.tracksContainer.append(this.videoTrack, this.audioTrack);
    this.scrollInner.append(this.ruler, this.tracksContainer, this.playheadEl);
    this.scrollWrapper.appendChild(this.scrollInner);
    this.container.append(toolbar, this.scrollWrapper);
    this.ruler.addEventListener("pointerdown", (e) => {
      e.stopPropagation();
      const time = this._rulerXToTime(e.clientX);
      if (time >= 0) {
        this.setPlayhead(time);
        callbacks.onPlayheadChanged(time);
      }
    });
    this.scrollWrapper.addEventListener("wheel", (e) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        const factor = e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
        const wrapperRect = this.scrollWrapper.getBoundingClientRect();
        const cursorX = e.clientX - wrapperRect.left + this.scrollWrapper.scrollLeft;
        const cursorFrac = cursorX / this.scrollInner.clientWidth;
        this.setZoom(this._zoom * factor);
        const newCursorX = cursorFrac * this.scrollInner.clientWidth;
        this.scrollWrapper.scrollLeft = newCursorX - (e.clientX - wrapperRect.left);
      }
    }, { passive: false });
  }
  get element() {
    return this.container;
  }
  get timeline() {
    return this.editTimeline;
  }
  setPlayhead(time) {
    var _a;
    this.editTimeline.setPlayhead(time);
    (_a = this.audioTimeline) == null ? void 0 : _a.setPlayhead(time);
    this._updatePlayheadPosition(time);
  }
  setZoom(zoom) {
    this._zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, zoom));
    this._zoomLabel.textContent = `${this._zoom.toFixed(1)}×`;
    const baseW = this.scrollWrapper.clientWidth;
    const innerW = Math.max(baseW, baseW * this._zoom);
    this.scrollInner.style.width = `${innerW}px`;
    this.render();
  }
  render() {
    var _a;
    this.editTimeline.render();
    (_a = this.audioTimeline) == null ? void 0 : _a.render();
    this._renderRuler();
    if (this.editTimeline.playhead > 0) {
      this._updatePlayheadPosition(this.editTimeline.playhead);
    }
  }
  /** Mount an AudioTimeline in the A1 track */
  setAudioTimeline(at) {
    this.audioTimeline = at;
    at.setSnapping(this._snapping);
    const wrap = this.audioTrack.querySelector(".veditor-track-canvas-wrap");
    if (wrap) {
      wrap.innerHTML = "";
      wrap.appendChild(at.element);
    }
  }
  /** Scroll to keep a time value visible */
  scrollToTime(time) {
    const dur = this.manager.videoDuration;
    if (dur <= 0) return;
    const innerW = this.scrollInner.clientWidth;
    const trackW = innerW - HEADER_W;
    const x = HEADER_W + time / dur * trackW;
    const wrapW = this.scrollWrapper.clientWidth;
    const scrollLeft = this.scrollWrapper.scrollLeft;
    const margin = wrapW * 0.1;
    if (x < scrollLeft + margin) {
      this.scrollWrapper.scrollLeft = Math.max(0, x - margin);
    } else if (x > scrollLeft + wrapW - margin) {
      this.scrollWrapper.scrollLeft = x - wrapW + margin;
    }
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
    const innerW = this.scrollInner.clientWidth;
    const trackW = innerW - HEADER_W;
    const x = HEADER_W + time / dur * trackW;
    this.playheadEl.style.left = `${x}px`;
  }
  _renderRuler() {
    const dur = this.manager.videoDuration;
    if (dur <= 0) return;
    this.ruler.innerHTML = "";
    const innerW = this.scrollInner.clientWidth;
    const trackW = innerW - HEADER_W;
    const pxPerSec = trackW / dur;
    let interval;
    if (pxPerSec > 100) interval = 0.5;
    else if (pxPerSec > 50) interval = 1;
    else if (pxPerSec > 20) interval = 2;
    else if (pxPerSec > 10) interval = 5;
    else if (pxPerSec > 4) interval = 10;
    else interval = 30;
    for (let t = 0; t <= dur; t += interval) {
      const marker = document.createElement("div");
      const x = HEADER_W + t / dur * trackW;
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
                white-space: nowrap;
            `;
      const mins = Math.floor(t / 60);
      const secs = Math.floor(t % 60);
      const frac = t % 1;
      if (frac > 0.01) {
        label.textContent = `${mins}:${secs.toString().padStart(2, "0")}.${Math.round(frac * 10)}`;
      } else {
        label.textContent = `${mins}:${secs.toString().padStart(2, "0")}`;
      }
      marker.append(label, tick);
      this.ruler.appendChild(marker);
    }
  }
  /** Map a ruler clientX to source time */
  _rulerXToTime(clientX) {
    const dur = this.manager.videoDuration;
    if (dur <= 0) return -1;
    const innerRect = this.scrollInner.getBoundingClientRect();
    const innerW = this.scrollInner.clientWidth;
    const trackW = innerW - HEADER_W;
    const x = clientX - innerRect.left - HEADER_W;
    if (x < 0 || x > trackW) return -1;
    return x / trackW * dur;
  }
  _makeToolbarBtn(text, title, toolId, onClick) {
    const btn = document.createElement("button");
    btn.className = "veditor-btn";
    btn.textContent = text;
    btn.title = title;
    btn.setAttribute("data-tool-id", toolId);
    btn.setAttribute("aria-label", title);
    btn.style.cssText = "font-size:11px;padding:2px 8px;border-radius:4px;min-width:24px;";
    btn.addEventListener("click", () => onClick());
    return btn;
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
    modeGroup.append(selectBtn);
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
class KeyframeTrack {
  constructor(property, min, max, defaultValue) {
    __publicField(this, "keyframes", []);
    __publicField(this, "property");
    __publicField(this, "min");
    __publicField(this, "max");
    __publicField(this, "defaultValue");
    this.property = property;
    this.min = min;
    this.max = max;
    this.defaultValue = defaultValue;
  }
  /** Add or update a keyframe at the given time. */
  addKeyframe(time, value, easing = "linear") {
    value = Math.max(this.min, Math.min(this.max, value));
    const existing = this.keyframes.findIndex((k) => Math.abs(k.time - time) < 0.01);
    if (existing >= 0) {
      this.keyframes[existing] = { time, value, easing };
    } else {
      this.keyframes.push({ time, value, easing });
    }
    this._sort();
  }
  /** Remove keyframe by index. */
  removeKeyframe(index) {
    if (index >= 0 && index < this.keyframes.length) {
      this.keyframes.splice(index, 1);
    }
  }
  /** Remove keyframe nearest to time (within tolerance). */
  removeAt(time, tolerance = 0.1) {
    const idx = this.keyframes.findIndex((k) => Math.abs(k.time - time) <= tolerance);
    if (idx >= 0) {
      this.keyframes.splice(idx, 1);
      return true;
    }
    return false;
  }
  /** Find the keyframe index nearest to `time`. -1 if none within tolerance. */
  findNearest(time, tolerance = 0.2) {
    let best = -1;
    let bestDist = Infinity;
    for (let i = 0; i < this.keyframes.length; i++) {
      const d = Math.abs(this.keyframes[i].time - time);
      if (d < bestDist && d <= tolerance) {
        bestDist = d;
        best = i;
      }
    }
    return best;
  }
  /** Get the interpolated value at time `t`. */
  valueAt(t) {
    if (this.keyframes.length === 0) return this.defaultValue;
    if (this.keyframes.length === 1) return this.keyframes[0].value;
    if (t <= this.keyframes[0].time) return this.keyframes[0].value;
    const last = this.keyframes[this.keyframes.length - 1];
    if (t >= last.time) return last.value;
    for (let i = 0; i < this.keyframes.length - 1; i++) {
      const a = this.keyframes[i];
      const b = this.keyframes[i + 1];
      if (t >= a.time && t <= b.time) {
        const duration = b.time - a.time;
        if (duration <= 0) return a.value;
        const progress = (t - a.time) / duration;
        return _interpolate(a.value, b.value, progress, a.easing);
      }
    }
    return this.defaultValue;
  }
  /** Returns true if the track has any non-default keyframes. */
  hasKeyframes() {
    return this.keyframes.length > 0;
  }
  /** Serialize to JSON. */
  toJSON() {
    return {
      keyframes: this.keyframes.map((k) => ({ ...k })),
      property: this.property,
      min: this.min,
      max: this.max,
      defaultValue: this.defaultValue
    };
  }
  /** Load from JSON. */
  fromJSON(data) {
    this.keyframes = [];
    if (data.keyframes && Array.isArray(data.keyframes)) {
      for (const k of data.keyframes) {
        if (typeof k.time === "number" && typeof k.value === "number") {
          this.addKeyframe(k.time, k.value, k.easing || "linear");
        }
      }
    }
  }
  /** Clear all keyframes. */
  clear() {
    this.keyframes = [];
  }
  _sort() {
    this.keyframes.sort((a, b) => a.time - b.time);
  }
}
function _interpolate(a, b, t, easing) {
  switch (easing) {
    case "step":
      return a;
    case "ease-in":
      t = t * t;
      break;
    case "ease-out":
      t = 1 - (1 - t) * (1 - t);
      break;
    case "ease-in-out":
      t = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
      break;
  }
  return a + (b - a) * t;
}
const LANE_HEIGHT = 60;
const DIAMOND_SIZE = 6;
const PADDING_X = 8;
const PADDING_Y = 8;
class KeyframeEditor {
  constructor(track, callbacks) {
    __publicField(this, "container");
    __publicField(this, "canvas");
    __publicField(this, "ctx");
    __publicField(this, "track");
    __publicField(this, "callbacks");
    __publicField(this, "duration", 10);
    __publicField(this, "dragging", -1);
    // index of keyframe being dragged
    __publicField(this, "hovered", -1);
    __publicField(this, "_animFrame", null);
    this.track = track;
    this.callbacks = callbacks;
    this.container = document.createElement("div");
    this.container.className = "veditor-keyframe-editor";
    this.container.setAttribute("data-tool-id", `veditor-kf-${track.property}`);
    const header = document.createElement("div");
    header.className = "veditor-kf-header";
    const label = document.createElement("span");
    label.className = "veditor-kf-label";
    label.textContent = `${track.property.charAt(0).toUpperCase() + track.property.slice(1)} Keyframes`;
    const clearBtn = document.createElement("button");
    clearBtn.className = "veditor-btn veditor-kf-clear-btn";
    clearBtn.textContent = "Clear";
    clearBtn.title = "Remove all keyframes";
    clearBtn.addEventListener("click", () => {
      this.track.clear();
      this.render();
      this.callbacks.onKeyframesChanged();
    });
    header.append(label, clearBtn);
    this.canvas = document.createElement("canvas");
    this.canvas.className = "veditor-kf-canvas";
    this.canvas.height = LANE_HEIGHT;
    this.canvas.setAttribute("aria-label", `Keyframe editor for ${track.property}`);
    this.ctx = this.canvas.getContext("2d");
    this.canvas.addEventListener("mousedown", (e) => this._onMouseDown(e));
    this.canvas.addEventListener("mousemove", (e) => this._onMouseMove(e));
    this.canvas.addEventListener("mouseup", () => this._onMouseUp());
    this.canvas.addEventListener("mouseleave", () => this._onMouseUp());
    this.canvas.addEventListener("dblclick", (e) => this._onDblClick(e));
    this.canvas.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      this._onDblClick(e);
    });
    const hint = document.createElement("div");
    hint.className = "veditor-kf-hint";
    hint.textContent = "Click to add • Drag to move • Double-click to delete";
    this.container.append(header, this.canvas, hint);
  }
  get element() {
    return this.container;
  }
  /** Set the timeline duration for time→pixel mapping. */
  setDuration(d) {
    this.duration = Math.max(0.1, d);
    this.render();
  }
  /** Resize canvas width and re-render. */
  resize(width) {
    const w = width ?? this.container.clientWidth;
    if (w > 0) {
      this.canvas.width = w;
      this.render();
    }
  }
  /** Re-render the keyframe lane. */
  render() {
    const w = this.canvas.width;
    const h = this.canvas.height;
    const ctx = this.ctx;
    if (w <= 0) return;
    ctx.clearRect(0, 0, w, h);
    const areaW = w - 2 * PADDING_X;
    const areaH = h - 2 * PADDING_Y;
    ctx.fillStyle = "rgba(30, 30, 44, 0.5)";
    ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = "rgba(255,255,255,0.05)";
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = PADDING_Y + areaH * i / 4;
      ctx.beginPath();
      ctx.moveTo(PADDING_X, y);
      ctx.lineTo(w - PADDING_X, y);
      ctx.stroke();
    }
    ctx.fillStyle = "rgba(255,255,255,0.3)";
    ctx.font = "9px monospace";
    ctx.textAlign = "left";
    ctx.fillText(String(this.track.max), 2, PADDING_Y + 8);
    ctx.fillText(String(this.track.min), 2, h - PADDING_Y);
    const defY = this._valueToY(this.track.defaultValue, areaH);
    ctx.strokeStyle = "rgba(99,102,241,0.3)";
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(PADDING_X, defY);
    ctx.lineTo(w - PADDING_X, defY);
    ctx.stroke();
    ctx.setLineDash([]);
    if (this.track.keyframes.length >= 2) {
      ctx.strokeStyle = "rgba(99,102,241,0.7)";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      const steps = Math.min(areaW, 200);
      for (let s = 0; s <= steps; s++) {
        const t = s / steps * this.duration;
        const val = this.track.valueAt(t);
        const x = this._timeToX(t, areaW);
        const y = this._valueToY(val, areaH);
        if (s === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
    }
    if (this.callbacks.getCurrentTime) {
      const ct = this.callbacks.getCurrentTime();
      const px = this._timeToX(ct, areaW);
      ctx.strokeStyle = "rgba(255,255,255,0.4)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(px, PADDING_Y);
      ctx.lineTo(px, h - PADDING_Y);
      ctx.stroke();
    }
    for (let i = 0; i < this.track.keyframes.length; i++) {
      const kf = this.track.keyframes[i];
      const x = this._timeToX(kf.time, areaW);
      const y = this._valueToY(kf.value, areaH);
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(Math.PI / 4);
      const isHovered = i === this.hovered;
      const isDragging = i === this.dragging;
      const size = isDragging ? DIAMOND_SIZE + 2 : isHovered ? DIAMOND_SIZE + 1 : DIAMOND_SIZE;
      ctx.fillStyle = isDragging ? "#818cf8" : isHovered ? "#a5b4fc" : "#6366f1";
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 1.5;
      ctx.fillRect(-size / 2, -size / 2, size, size);
      ctx.strokeRect(-size / 2, -size / 2, size, size);
      ctx.restore();
      if (isHovered) {
        ctx.fillStyle = "rgba(0,0,0,0.7)";
        const text = `${kf.value.toFixed(2)} @ ${kf.time.toFixed(1)}s`;
        const tw = ctx.measureText(text).width + 8;
        ctx.fillRect(x - tw / 2, y - 22, tw, 16);
        ctx.fillStyle = "#fff";
        ctx.font = "10px monospace";
        ctx.textAlign = "center";
        ctx.fillText(text, x, y - 10);
      }
    }
  }
  /** Get the underlying track. */
  getTrack() {
    return this.track;
  }
  destroy() {
    if (this._animFrame) cancelAnimationFrame(this._animFrame);
    this.container.remove();
  }
  // ── Private ──────────────────────────────────────────────────
  _timeToX(t, areaW) {
    return PADDING_X + t / this.duration * areaW;
  }
  _xToTime(x, areaW) {
    return Math.max(0, Math.min(this.duration, (x - PADDING_X) / areaW * this.duration));
  }
  _valueToY(v, areaH) {
    const norm = (v - this.track.min) / (this.track.max - this.track.min);
    return PADDING_Y + (1 - norm) * areaH;
  }
  _yToValue(y, areaH) {
    const norm = 1 - (y - PADDING_Y) / areaH;
    return this.track.min + norm * (this.track.max - this.track.min);
  }
  _hitTest(mx, my) {
    const areaW = this.canvas.width - 2 * PADDING_X;
    const areaH = this.canvas.height - 2 * PADDING_Y;
    for (let i = 0; i < this.track.keyframes.length; i++) {
      const kf = this.track.keyframes[i];
      const x = this._timeToX(kf.time, areaW);
      const y = this._valueToY(kf.value, areaH);
      const dist = Math.sqrt((mx - x) ** 2 + (my - y) ** 2);
      if (dist <= DIAMOND_SIZE + 4) return i;
    }
    return -1;
  }
  _onMouseDown(e) {
    const rect = this.canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const hit = this._hitTest(mx, my);
    if (hit >= 0) {
      this.dragging = hit;
    } else {
      const areaW = this.canvas.width - 2 * PADDING_X;
      const areaH = this.canvas.height - 2 * PADDING_Y;
      const t = this._xToTime(mx, areaW);
      const v = this._yToValue(my, areaH);
      this.track.addKeyframe(t, v);
      this.render();
      this.callbacks.onKeyframesChanged();
    }
  }
  _onMouseMove(e) {
    const rect = this.canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const areaW = this.canvas.width - 2 * PADDING_X;
    const areaH = this.canvas.height - 2 * PADDING_Y;
    if (this.dragging >= 0) {
      const kf = this.track.keyframes[this.dragging];
      if (kf) {
        kf.time = this._xToTime(mx, areaW);
        kf.value = Math.max(
          this.track.min,
          Math.min(this.track.max, this._yToValue(my, areaH))
        );
        this.render();
      }
    } else {
      const hit = this._hitTest(mx, my);
      if (hit !== this.hovered) {
        this.hovered = hit;
        this.canvas.style.cursor = hit >= 0 ? "pointer" : "crosshair";
        this.render();
      }
    }
  }
  _onMouseUp() {
    if (this.dragging >= 0) {
      this.dragging = -1;
      this.callbacks.onKeyframesChanged();
      this.render();
    }
  }
  _onDblClick(e) {
    const rect = this.canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const hit = this._hitTest(mx, my);
    if (hit >= 0) {
      this.track.removeKeyframe(hit);
      this.hovered = -1;
      this.render();
      this.callbacks.onKeyframesChanged();
    }
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
    __publicField(this, "keyframeTrack");
    __publicField(this, "keyframeEditor");
    __publicField(this, "kfToggle");
    __publicField(this, "kfContainer");
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
    const resetRow = document.createElement("div");
    resetRow.className = "veditor-control-row";
    const resetBtn = document.createElement("button");
    resetBtn.className = "veditor-btn veditor-toggle-btn";
    resetBtn.innerHTML = `${iconGauge} Reset Speed`;
    resetBtn.title = "Reset all speed settings to defaults";
    resetBtn.setAttribute("data-tool-id", "veditor-speed-reset");
    resetBtn.setAttribute("aria-label", "Reset speed settings");
    resetBtn.addEventListener("click", () => {
      this.reset();
      this.callbacks.onSpeedChanged(this.currentSegment, 1);
    });
    resetRow.appendChild(resetBtn);
    this.container.append(speedSection, reverseSection, curveSection, interpSection, resetRow);
    const kfSection = this._makeSection("Speed Keyframes");
    const kfToggleRow = document.createElement("div");
    kfToggleRow.className = "veditor-control-row";
    const kfLabel = document.createElement("label");
    kfLabel.className = "veditor-toggle-label";
    kfLabel.textContent = "Enable speed keyframes";
    this.kfToggle = document.createElement("input");
    this.kfToggle.type = "checkbox";
    this.kfToggle.className = "veditor-checkbox";
    this.kfToggle.setAttribute("data-tool-id", "veditor-speed-kf-toggle");
    this.kfToggle.setAttribute("aria-label", "Enable speed keyframes for ramp transitions");
    this.kfToggle.addEventListener("change", () => {
      this.kfContainer.style.display = this.kfToggle.checked ? "block" : "none";
      if (this.kfToggle.checked) {
        this.keyframeEditor.resize();
      }
    });
    kfToggleRow.append(kfLabel, this.kfToggle);
    this.keyframeTrack = new KeyframeTrack("speed", 0.1, 8, 1);
    this.keyframeEditor = new KeyframeEditor(this.keyframeTrack, {
      onKeyframesChanged: () => {
        var _a, _b;
        (_b = (_a = this.callbacks).onKeyframesChanged) == null ? void 0 : _b.call(_a);
      },
      getCurrentTime: () => {
        var _a, _b;
        return ((_b = (_a = this.callbacks).getCurrentTime) == null ? void 0 : _b.call(_a)) ?? 0;
      }
    });
    this.kfContainer = document.createElement("div");
    this.kfContainer.style.display = "none";
    this.kfContainer.appendChild(this.keyframeEditor.element);
    kfSection.append(kfToggleRow, this.kfContainer);
    this.container.appendChild(kfSection);
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
    this.keyframeTrack.clear();
    this.kfToggle.checked = false;
    this.kfContainer.style.display = "none";
    this.keyframeEditor.render();
  }
  /** Get the keyframe track data for serialization. */
  getKeyframeData() {
    if (!this.kfToggle.checked || !this.keyframeTrack.hasKeyframes()) {
      return null;
    }
    return this.keyframeTrack.toJSON();
  }
  /** Load keyframe data. */
  loadKeyframeData(data) {
    if (data && data.keyframes && data.keyframes.length > 0) {
      this.keyframeTrack.fromJSON(data);
      this.kfToggle.checked = true;
      this.kfContainer.style.display = "block";
      this.keyframeEditor.render();
    } else {
      this.keyframeTrack.clear();
      this.kfToggle.checked = false;
      this.kfContainer.style.display = "none";
    }
  }
  /** Set the timeline duration for keyframe time mapping. */
  setDuration(d) {
    this.keyframeEditor.setDuration(d);
  }
  /** Resize the keyframe editor canvas. */
  resizeKeyframes() {
    if (this.kfToggle.checked) {
      this.keyframeEditor.resize();
    }
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
  collectEdges as d,
  fmtDuration as f,
  snapToEdges as s,
  viewUrl as v
};
