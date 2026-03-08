var __defProp = Object.defineProperty;
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);
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
export {
  EditManager as E,
  EditTimeline as a,
  captureFrame as b,
  captureFrames as c,
  fmtDuration as f,
  viewUrl as v
};
