var __defProp = Object.defineProperty;
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);
import { api } from "../../scripts/api.js";
import { app } from "../../scripts/app.js";
import { E as EditManager, f as fmtDuration, a as EditTimeline, c as captureFrames, b as captureFrame, v as viewUrl } from "./_chunks/EditTimeline-BeK0Y4a7.js";
const VIEW_MODES = {
  PLAYBACK: "playback",
  GRID: "grid",
  SIDE_BY_SIDE: "sidebyside",
  FILMSTRIP: "filmstrip",
  SELECTED: "selected",
  EDIT: "edit"
};
const ZOOM_LEVELS = [1, 0.5, 0.2, 0.1];
const ZOOM_LABELS = ["1 fps", "2 fps", "5 fps", "10 fps"];
const FRAMES_PER_PAGE = 4;
const TOOLBAR_BUTTONS = [
  {
    id: VIEW_MODES.PLAYBACK,
    icon: '<svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor"><polygon points="3,1 12,7 3,13"/></svg>',
    tip: "Playback"
  },
  {
    id: VIEW_MODES.GRID,
    icon: '<svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor"><rect x="1" y="1" width="3" height="3" rx="0.5"/><rect x="5.5" y="1" width="3" height="3" rx="0.5"/><rect x="10" y="1" width="3" height="3" rx="0.5"/><rect x="1" y="5.5" width="3" height="3" rx="0.5"/><rect x="5.5" y="5.5" width="3" height="3" rx="0.5"/><rect x="10" y="5.5" width="3" height="3" rx="0.5"/><rect x="1" y="10" width="3" height="3" rx="0.5"/><rect x="5.5" y="10" width="3" height="3" rx="0.5"/><rect x="10" y="10" width="3" height="3" rx="0.5"/></svg>',
    tip: "Grid (3×3)"
  },
  {
    id: VIEW_MODES.SIDE_BY_SIDE,
    icon: '<svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor"><rect x="1" y="1" width="5" height="12" rx="1"/><rect x="8" y="1" width="5" height="12" rx="1"/></svg>',
    tip: "Side by Side"
  },
  {
    id: VIEW_MODES.FILMSTRIP,
    icon: '<svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor"><rect x="0" y="0" width="14" height="14" rx="1" opacity="0.3"/><rect x="1" y="3" width="3" height="8" rx="0.5"/><rect x="5.5" y="3" width="3" height="8" rx="0.5"/><rect x="10" y="3" width="3" height="8" rx="0.5"/><rect x="1.5" y="0.5" width="1" height="1.5" rx="0.3"/><rect x="4" y="0.5" width="1" height="1.5" rx="0.3"/><rect x="6.5" y="0.5" width="1" height="1.5" rx="0.3"/><rect x="9" y="0.5" width="1" height="1.5" rx="0.3"/><rect x="11.5" y="0.5" width="1" height="1.5" rx="0.3"/><rect x="1.5" y="12" width="1" height="1.5" rx="0.3"/><rect x="4" y="12" width="1" height="1.5" rx="0.3"/><rect x="6.5" y="12" width="1" height="1.5" rx="0.3"/><rect x="9" y="12" width="1" height="1.5" rx="0.3"/><rect x="11.5" y="12" width="1" height="1.5" rx="0.3"/></svg>',
    tip: "Filmstrip"
  },
  {
    id: VIEW_MODES.SELECTED,
    icon: '<svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor"><path d="M7 1 L9 5.5 L13.5 5.5 L10 8.5 L11.5 13 L7 10.5 L2.5 13 L4 8.5 L0.5 5.5 L5 5.5 Z"/></svg>',
    tip: "Selected Frames"
  },
  {
    id: VIEW_MODES.EDIT,
    icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/></svg>',
    tip: "Edit Video ✂️"
  }
];
class SelectionManager {
  constructor() {
    __publicField(this, "selections", /* @__PURE__ */ new Map());
    __publicField(this, "node", null);
    for (const mode of Object.values(VIEW_MODES)) {
      this.selections.set(mode, /* @__PURE__ */ new Set());
    }
  }
  /** Bind to a ComfyUI node for widget sync */
  bind(node) {
    this.node = node;
  }
  /** Get the selection set for a mode */
  get(mode) {
    return this.selections.get(mode) ?? /* @__PURE__ */ new Set();
  }
  /** Toggle a timestamp in a mode's selection. Returns true if added. */
  toggle(mode, timestamp) {
    const set = this.get(mode);
    const key = Math.round(timestamp * 1e3) / 1e3;
    if (set.has(key)) {
      set.delete(key);
      return false;
    }
    set.add(key);
    return true;
  }
  /** Clear all selections for a mode */
  clearMode(mode) {
    this.get(mode).clear();
  }
  /** Clear ALL selections across all modes */
  clearAll() {
    for (const set of this.selections.values()) {
      set.clear();
    }
  }
  /** Get total selected count across all modes */
  totalCount() {
    let count = 0;
    for (const set of this.selections.values()) {
      count += set.size;
    }
    return count;
  }
  /** Get all unique timestamps across all modes, sorted */
  allTimestamps() {
    const all = /* @__PURE__ */ new Set();
    for (const set of this.selections.values()) {
      for (const t of set) all.add(t);
    }
    return Array.from(all).sort((a, b) => a - b);
  }
  /** Get all timestamps with their source mode(s) */
  allTimestampsWithSource() {
    const result = /* @__PURE__ */ new Map();
    for (const [mode, set] of this.selections.entries()) {
      if (mode === VIEW_MODES.SELECTED) continue;
      for (const t of set) {
        const existing = result.get(t) ?? [];
        existing.push(mode);
        result.set(t, existing);
      }
    }
    return result;
  }
  /** Sync selections to the hidden _selected_timestamps widget */
  syncToWidget() {
    var _a;
    if (!this.node) return;
    const sorted = this.allTimestamps();
    const json = JSON.stringify(sorted);
    const w = (_a = this.node.widgets) == null ? void 0 : _a.find((w2) => w2.name === "_selected_timestamps");
    if (w) {
      w.value = json;
    } else {
      if (!this.node.properties) this.node.properties = {};
      this.node.properties["_selected_timestamps"] = json;
    }
  }
  /** Get entries iterator for rendering */
  entries() {
    return this.selections.entries();
  }
}
function hitTestFrame(geometry, cx, cy) {
  if (!geometry) return null;
  switch (geometry.mode) {
    case VIEW_MODES.GRID:
      return hitTestGrid(geometry, cx, cy);
    case VIEW_MODES.FILMSTRIP:
      return hitTestFilmstrip(geometry, cx);
    case VIEW_MODES.SIDE_BY_SIDE:
      return hitTestSideBySide(geometry, cx);
    default:
      return null;
  }
}
function hitTestGrid(g, cx, cy) {
  const col = Math.floor(cx / g.cellW);
  const row = Math.floor(cy / g.cellH);
  if (col < 0 || col >= g.cols || row < 0 || row >= g.rows) return null;
  const idx = row * g.cols + col;
  if (idx >= g.count) return null;
  return g.timestamps[idx] ?? null;
}
function hitTestFilmstrip(g, cx, _cy) {
  const fw = g.frameWidth + g.gap;
  const idx = Math.floor(cx / fw);
  if (idx < 0 || idx >= g.count) return null;
  return g.timestamps[idx] ?? null;
}
function hitTestSideBySide(g, cx, _cy) {
  const halfW = g.videoWidth;
  if (cx < halfW) return g.timestamps[0] ?? null;
  if (cx > halfW + g.gap) return g.timestamps[1] ?? null;
  return null;
}
const OVERLAY_COLOR = "rgba(0, 221, 255, 0.25)";
const BORDER_COLOR = "#00ddff";
const BORDER_WIDTH = 3;
function drawSelectionOverlay(canvas, geometry, selectedTimestamps) {
  if (!geometry) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  switch (geometry.mode) {
    case VIEW_MODES.GRID:
      drawGridOverlay(ctx, geometry, selectedTimestamps);
      break;
    case VIEW_MODES.FILMSTRIP:
      drawFilmstripOverlay(ctx, geometry, selectedTimestamps);
      break;
    case VIEW_MODES.SIDE_BY_SIDE:
      drawSideBySideOverlay(ctx, geometry, selectedTimestamps);
      break;
  }
}
function drawGridOverlay(ctx, g, sel) {
  for (let i = 0; i < g.count; i++) {
    const key = Math.round(g.timestamps[i] * 1e3) / 1e3;
    if (!sel.has(key)) continue;
    const col = i % g.cols;
    const row = Math.floor(i / g.cols);
    const x = col * g.cellW;
    const y = row * g.cellH;
    drawFrameOverlay(ctx, x, y, g.cellW, g.cellH);
  }
}
function drawFilmstripOverlay(ctx, g, sel) {
  for (let i = 0; i < g.count; i++) {
    const key = Math.round(g.timestamps[i] * 1e3) / 1e3;
    if (!sel.has(key)) continue;
    const x = i * (g.frameWidth + g.gap);
    drawFrameOverlay(ctx, x, 0, g.frameWidth, g.frameHeight);
  }
}
function drawSideBySideOverlay(ctx, g, sel) {
  for (let i = 0; i < g.timestamps.length; i++) {
    const key = Math.round(g.timestamps[i] * 1e3) / 1e3;
    if (!sel.has(key)) continue;
    const x = i === 0 ? 0 : g.videoWidth + g.gap;
    const canvasHeight = ctx.canvas.height;
    drawFrameOverlay(ctx, x, 0, g.videoWidth, canvasHeight);
  }
}
function drawFrameOverlay(ctx, x, y, w, h) {
  ctx.strokeStyle = BORDER_COLOR;
  ctx.lineWidth = BORDER_WIDTH;
  ctx.strokeRect(x + 1, y + 1, w - 2, h - 2);
  ctx.fillStyle = OVERLAY_COLOR;
  ctx.fillRect(x, y, w, h);
  drawCheckmark(ctx, x + w - 24, y + 6, 14);
}
function drawCheckmark(ctx, x, y, size) {
  ctx.save();
  ctx.strokeStyle = "#fff";
  ctx.lineWidth = 2.5;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.beginPath();
  ctx.moveTo(x, y + size * 0.5);
  ctx.lineTo(x + size * 0.35, y + size * 0.8);
  ctx.lineTo(x + size, y + size * 0.15);
  ctx.stroke();
  ctx.restore();
}
const cssText = "/**\n * LoadLast Video Preview — Stylesheet\n *\n * Extracted from inline styles in video_preview.ts.\n * Dynamic styles (visibility toggles, computed positions) remain inline.\n */\n\n/* ─── Container ──────────────────────────────────────── */\n.ll_container {\n    display: flex;\n    flex-direction: column;\n    background: #0d0d0d;\n    border-radius: 8px;\n    overflow: hidden;\n    min-height: 60px;\n    position: relative;\n}\n\n/* ─── Toolbar ────────────────────────────────────────── */\n.ll_toolbar {\n    display: flex;\n    align-items: center;\n    gap: 3px;\n    padding: 4px 6px;\n    background: #111;\n    border-bottom: 1px solid #222;\n    flex-shrink: 0;\n}\n\n.ll_toolbar_btn {\n    border: 1px solid transparent;\n    background: transparent;\n    color: #777;\n    font-size: 14px;\n    padding: 4px 8px;\n    border-radius: 4px;\n    cursor: pointer;\n    transition: all 0.15s;\n    display: flex;\n    align-items: center;\n    justify-content: center;\n}\n\n.ll_toolbar_btn.active {\n    color: #fff;\n    background: #333;\n    border-color: #555;\n}\n\n.ll_clear_btn {\n    margin-left: auto;\n    border: 1px solid transparent;\n    background: transparent;\n    color: #777;\n    font-size: 11px;\n    padding: 3px 6px;\n    border-radius: 3px;\n    cursor: pointer;\n    transition: all 0.15s;\n    display: flex;\n    align-items: center;\n}\n\n/* ─── Selection badge ────────────────────────────────── */\n.ll_sel_badge {\n    position: absolute;\n    top: 6px;\n    right: 8px;\n    z-index: 20;\n    background: rgba(0, 221, 255, 0.85);\n    color: #000;\n    font: bold 11px/1 monospace;\n    padding: 3px 8px;\n    border-radius: 10px;\n    cursor: pointer;\n    display: none;\n    text-shadow: none;\n    user-select: none;\n    transition: background 0.15s;\n}\n\n.ll_sel_badge:hover {\n    background: rgba(255, 80, 80, 0.9);\n}\n\n/* ─── Marker bar ─────────────────────────────────────── */\n.ll_marker_bar {\n    position: relative;\n    height: 10px;\n    background: #1a1a1a;\n    border-radius: 2px;\n    margin: 0 4px 2px 4px;\n    display: none;\n    border: 1px solid #333;\n    flex-shrink: 0;\n}\n\n.ll_marker_tick {\n    position: absolute;\n    top: 1px;\n    width: 3px;\n    height: 8px;\n    background: #00ddff;\n    border-radius: 1px;\n}\n\n/* ─── Video / Canvas ─────────────────────────────────── */\n.ll_video {\n    width: 100%;\n    display: block;\n}\n\n.ll_canvas {\n    width: 100%;\n    display: none;\n    cursor: crosshair;\n}\n\n/* ─── Info bar ───────────────────────────────────────── */\n.ll_info {\n    padding: 4px 8px;\n    font: 11px/1.4 monospace;\n    color: #888;\n    background: #0a0a0a;\n    border-top: 1px solid #222;\n    white-space: nowrap;\n    overflow: hidden;\n    text-overflow: ellipsis;\n    flex-shrink: 0;\n}\n\n/* ─── Browser strip ──────────────────────────────────── */\n.ll_strip_wrapper {\n    background: #0a0a0a;\n}\n\n.ll_browser_strip {\n    display: flex;\n    gap: 4px;\n    padding: 4px 6px;\n    overflow-x: auto;\n    background: #0a0a0a;\n    flex-shrink: 0;\n    scrollbar-width: none;\n}\n\n.ll_browser_strip::-webkit-scrollbar {\n    display: none;\n}\n\n/* ─── Scroll track ───────────────────────────────────── */\n.ll_scroll_track {\n    height: 10px;\n    background: #222;\n    margin: 2px 6px 6px;\n    border-radius: 5px;\n    position: relative;\n    cursor: pointer;\n    border: 1px solid #333;\n}\n\n.ll_scroll_thumb {\n    height: 100%;\n    background: #5ac;\n    border-radius: 5px;\n    position: absolute;\n    top: 0;\n    min-width: 20px;\n    cursor: grab;\n    transition: background 0.15s;\n}\n\n.ll_scroll_thumb:hover {\n    background: #7cd;\n}\n\n.ll_scroll_thumb.dragging {\n    cursor: grabbing;\n    background: #bbb;\n}\n\n/* ─── Flash overlay ──────────────────────────────────── */\n.ll_flash_overlay {\n    position: absolute;\n    top: 0;\n    left: 0;\n    right: 0;\n    bottom: 0;\n    pointer-events: none;\n    z-index: 10;\n    opacity: 0;\n    border: 4px solid #00ddff;\n    border-radius: 4px;\n    transition: opacity 0.1s ease-in;\n}\n\n/* ─── Filmstrip controls ─────────────────────────────── */\n.ll_filmstrip_ctrl {\n    display: flex;\n    flex-direction: column;\n    gap: 4px;\n    padding: 6px 8px;\n    background: #111;\n    border-top: 1px solid #222;\n}\n\n.ll_filmstrip_row {\n    display: flex;\n    align-items: center;\n    gap: 4px;\n    justify-content: center;\n}\n\n.ll_filmstrip_btn {\n    border: 1px solid #555;\n    background: #222;\n    color: #aaa;\n    font-size: 12px;\n    padding: 3px 10px;\n    border-radius: 4px;\n    cursor: pointer;\n    transition: all 0.15s;\n}\n\n.ll_filmstrip_btn:hover {\n    background: #333;\n    color: #fff;\n}\n\n/* ─── Scrubber ───────────────────────────────────────── */\n.ll_scrubber {\n    display: flex;\n    align-items: center;\n    gap: 6px;\n    padding: 0 4px;\n}\n\n.ll_scrubber_range {\n    flex: 1;\n    height: 4px;\n    accent-color: #00ddff;\n    cursor: pointer;\n}\n\n.ll_scrubber_dot {\n    width: 6px;\n    height: 6px;\n    border-radius: 50%;\n    background: #555;\n    flex-shrink: 0;\n}\n\n/* ─── Browser thumbnails ─────────────────────────────── */\n.ll_thumb {\n    flex-shrink: 0;\n    border-radius: 4px;\n    overflow: hidden;\n    cursor: pointer;\n    border: 2px solid transparent;\n    transition: border-color 0.15s;\n    position: relative;\n}\n\n.ll_thumb.active {\n    border-color: #00ddff;\n}\n\n.ll_thumb:hover {\n    border-color: #555;\n}\n\n.ll_thumb video {\n    width: 100%;\n    height: 100%;\n    object-fit: cover;\n    pointer-events: none;\n}\n\n.ll_thumb_label {\n    position: absolute;\n    bottom: 0;\n    left: 0;\n    right: 0;\n    background: rgba(0, 0, 0, 0.7);\n    color: #ccc;\n    font: 9px/1.3 monospace;\n    padding: 1px 3px;\n    text-align: center;\n    overflow: hidden;\n    text-overflow: ellipsis;\n    white-space: nowrap;\n}\n\n/* ─── Edit Mode Wrapper (self-contained, dynamically inserted) ─── */\n.ll_edit_wrapper {\n    display: flex;\n    flex-direction: column;\n    background: #0d0d0d;\n}\n\n.ll_edit_wrapper .ll_video {\n    width: 100%;\n    display: block;\n}\n\n/* Transport bar: play/pause + time display */\n.ll_edit_transport {\n    display: flex;\n    align-items: center;\n    gap: 10px;\n    padding: 6px 10px;\n    background: #111;\n    border-top: 1px solid #333;\n}\n\n.ll_edit_play_btn {\n    width: 32px;\n    height: 28px;\n    border: 1px solid #555;\n    background: #1a2a3a;\n    color: #7ad;\n    font-size: 14px;\n    border-radius: 4px;\n    cursor: pointer;\n    display: flex;\n    align-items: center;\n    justify-content: center;\n    transition: all 0.15s;\n}\n\n.ll_edit_play_btn:hover {\n    background: #2a3a5a;\n    border-color: #7ad;\n    color: #adf;\n}\n\n.ll_edit_time_display {\n    font: 12px/1 monospace;\n    color: #7ad;\n    letter-spacing: 0.5px;\n}\n\n/* Black overlay for deleted regions */\n.ll_edit_black_overlay {\n    position: absolute;\n    top: 0;\n    left: 0;\n    right: 0;\n    bottom: 0;\n    background: #000;\n    pointer-events: none;\n    display: none;\n}\n\n/* Video area (relative for overlay positioning) */\n.ll_edit_video_area {\n    position: relative;\n}\n\n/* Timeline */\n.ll_edit_timeline {\n    padding: 4px 0;\n    background: #111;\n    border-top: 1px solid #222;\n}\n\n.ll_edit_canvas {\n    display: block;\n}\n\n/* Timeline toolbar with split/reset buttons */\n.ll_edit_toolbar {\n    display: flex;\n    align-items: center;\n    gap: 4px;\n    padding: 6px 8px;\n    justify-content: center;\n}\n\n.ll_edit_btn {\n    border: 1px solid #555;\n    background: #222;\n    color: #aaa;\n    font-size: 11px;\n    padding: 4px 10px;\n    border-radius: 4px;\n    cursor: pointer;\n    transition: all 0.15s;\n}\n\n.ll_edit_btn:hover {\n    background: #333;\n    color: #fff;\n}";
if (!document.getElementById("loadlast-styles")) {
  const style = document.createElement("style");
  style.id = "loadlast-styles";
  style.textContent = cssText;
  document.head.appendChild(style);
}
app.registerExtension({
  name: "LoadLast.VideoPreview",
  beforeRegisterNodeDef(nodeType, nodeData, _app) {
    if ((nodeData == null ? void 0 : nodeData.name) !== "LoadLastVideo") return;
    const origCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      var _a;
      origCreated == null ? void 0 : origCreated.apply(this, arguments);
      const node = this;
      const selections = new SelectionManager();
      selections.bind(node);
      let currentMode = VIEW_MODES.PLAYBACK;
      let modeGeometry = null;
      let lastFilename = "";
      const editMgr = new EditManager();
      editMgr.bind(node);
      let editTimeline = null;
      let editWrapper = null;
      let editPlaybackRaf = null;
      let editPlaying = false;
      let editOutputTime = 0;
      let editPlayBtn = null;
      let editTimeDisplay = null;
      let editBlackOverlay = null;
      let filmstripZoom = 0;
      let filmstripPage = 0;
      node.color = "#3a3a5a";
      node.bgcolor = "#2a2a4a";
      const container = document.createElement("div");
      container.className = "ll_container";
      container.tabIndex = 0;
      const toolbar = document.createElement("div");
      toolbar.className = "ll_toolbar";
      const buttons = [];
      for (const def of TOOLBAR_BUTTONS) {
        const btn = document.createElement("button");
        btn.innerHTML = def.icon;
        btn.title = def.tip;
        btn.dataset.mode = def.id;
        btn.className = "ll_toolbar_btn";
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          switchMode(def.id);
        });
        buttons.push(btn);
        toolbar.appendChild(btn);
      }
      const clearBtn = document.createElement("button");
      clearBtn.innerHTML = '<svg width="11" height="11" viewBox="0 0 11 11" fill="currentColor"><path d="M1.5 0.5 L5.5 4.5 L9.5 0.5 L10.5 1.5 L6.5 5.5 L10.5 9.5 L9.5 10.5 L5.5 6.5 L1.5 10.5 L0.5 9.5 L4.5 5.5 L0.5 1.5 Z"/></svg>';
      clearBtn.title = "Clear selection";
      clearBtn.className = "ll_clear_btn";
      clearBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        selections.clearMode(currentMode);
        updateSelectionUI();
        if (currentMode !== VIEW_MODES.PLAYBACK) renderCurrentMode();
        else drawSelectionOverlay(canvasEl, modeGeometry, selections.get(currentMode));
      });
      toolbar.appendChild(clearBtn);
      const selBadge = document.createElement("div");
      selBadge.className = "ll_sel_badge";
      selBadge.addEventListener("click", (e) => {
        e.stopPropagation();
        selections.clearAll();
        updateSelectionUI();
        if (currentMode !== VIEW_MODES.PLAYBACK) renderCurrentMode();
        else drawSelectionOverlay(canvasEl, modeGeometry, selections.get(currentMode));
      });
      container.appendChild(selBadge);
      function updateSelBadge() {
        const total = selections.totalCount();
        if (total > 0) {
          selBadge.innerHTML = `${total} sel <svg width="8" height="8" viewBox="0 0 8 8" fill="#000" style="vertical-align:middle;margin-left:3px;opacity:0.6"><path d="M1 0 L4 3 L7 0 L8 1 L5 4 L8 7 L7 8 L4 5 L1 8 L0 7 L3 4 L0 1 Z"/></svg>`;
          selBadge.style.display = "block";
        } else {
          selBadge.style.display = "none";
        }
      }
      function highlightToolbar() {
        for (const btn of buttons) {
          const active = btn.dataset.mode === currentMode;
          btn.classList.toggle("active", active);
        }
        const selCount = selections.totalCount();
        clearBtn.style.display = selCount > 0 ? "block" : "none";
        updateSelBadge();
      }
      function updateSelectionUI() {
        selections.syncToWidget();
        updatePlaybackMarkers();
        const modeCount = selections.get(currentMode).size;
        const totalCount = selections.totalCount();
        const extra = modeCount > 0 ? ` │ ${modeCount} selected` : "";
        const totalExtra = totalCount > 0 ? ` │ ${totalCount} total ` : "";
        infoEl.textContent = (infoEl.textContent || "").split("│")[0].trim() + extra + totalExtra;
        highlightToolbar();
      }
      const markerBar = document.createElement("div");
      markerBar.className = "loadlast_marker_bar";
      markerBar.className = "ll_marker_bar";
      function updatePlaybackMarkers() {
        const dur = videoEl.duration;
        markerBar.innerHTML = "";
        const allTs = selections.allTimestamps();
        if (allTs.length === 0 || !dur || !isFinite(dur)) {
          markerBar.style.display = "none";
          return;
        }
        markerBar.style.display = "block";
        for (const t of allTs) {
          const pct = t / dur * 100;
          if (pct < 0 || pct > 100) continue;
          const tick = document.createElement("div");
          tick.className = "ll_marker_tick";
          tick.style.left = `calc(${pct.toFixed(2)}% - 1px)`;
          tick.title = fmtDuration(t);
          markerBar.appendChild(tick);
        }
      }
      const videoEl = document.createElement("video");
      videoEl.controls = true;
      videoEl.loop = true;
      videoEl.muted = true;
      videoEl.autoplay = true;
      videoEl.setAttribute("aria-label", "Last video preview");
      videoEl.className = "ll_video";
      const canvasEl = document.createElement("canvas");
      canvasEl.className = "ll_canvas";
      canvasEl.addEventListener("click", (e) => {
        if (!modeGeometry) return;
        e.stopPropagation();
        const rect = canvasEl.getBoundingClientRect();
        const scaleX = canvasEl.width / rect.width;
        const scaleY = canvasEl.height / rect.height;
        const cx = (e.clientX - rect.left) * scaleX;
        const cy = (e.clientY - rect.top) * scaleY;
        const ts = hitTestFrame(modeGeometry, cx, cy);
        if (ts === null) return;
        selections.toggle(currentMode, ts);
        updateSelectionUI();
        renderCurrentMode();
      });
      const infoEl = document.createElement("div");
      infoEl.className = "ll_info";
      const browserStrip = document.createElement("div");
      browserStrip.className = "loadlast_browser_strip";
      browserStrip.className = "ll_browser_strip";
      const scrollTrack = document.createElement("div");
      scrollTrack.className = "ll_scroll_track";
      const scrollThumb = document.createElement("div");
      scrollThumb.className = "ll_scroll_thumb";
      scrollTrack.appendChild(scrollThumb);
      function updateScrollIndicator() {
        const sw = browserStrip.scrollWidth;
        const cw = browserStrip.clientWidth;
        if (sw <= cw) {
          scrollTrack.style.display = allVideos.length > 1 ? "block" : "none";
          scrollThumb.style.width = "100%";
          scrollThumb.style.left = "0px";
          scrollThumb.style.opacity = "0.3";
          return;
        }
        scrollTrack.style.display = "block";
        scrollThumb.style.opacity = "1";
        const trackW = scrollTrack.clientWidth;
        const ratio = cw / sw;
        const thumbW = Math.max(20, trackW * ratio);
        scrollThumb.style.width = `${thumbW}px`;
        const scrollRange = sw - cw;
        const thumbRange = trackW - thumbW;
        const pos = scrollRange > 0 ? browserStrip.scrollLeft / scrollRange * thumbRange : 0;
        scrollThumb.style.left = `${pos}px`;
      }
      browserStrip.addEventListener("scroll", updateScrollIndicator);
      browserStrip.addEventListener("wheel", (e) => {
        if (e.deltaY !== 0) {
          e.preventDefault();
          browserStrip.scrollLeft += e.deltaY;
        }
      }, { passive: false });
      scrollThumb.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        scrollThumb.style.cursor = "grabbing";
        scrollThumb.style.background = "#bbb";
        const startX = e.clientX;
        const startScroll = browserStrip.scrollLeft;
        const trackW = scrollTrack.clientWidth;
        const thumbW = scrollThumb.offsetWidth;
        const scrollRange = browserStrip.scrollWidth - browserStrip.clientWidth;
        const onMove = (ev) => {
          const dx = ev.clientX - startX;
          const scrollDelta = trackW - thumbW > 0 ? dx / (trackW - thumbW) * scrollRange : 0;
          browserStrip.scrollLeft = startScroll + scrollDelta;
        };
        const onUp = () => {
          scrollThumb.style.cursor = "grab";
          scrollThumb.style.background = "#5ac";
          document.removeEventListener("mousemove", onMove);
          document.removeEventListener("mouseup", onUp);
        };
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
      });
      scrollTrack.addEventListener("mousedown", (e) => {
        if (e.target === scrollThumb) return;
        e.preventDefault();
        const rect = scrollTrack.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        const trackW = rect.width;
        const scrollRange = browserStrip.scrollWidth - browserStrip.clientWidth;
        browserStrip.scrollLeft = clickX / trackW * scrollRange;
      });
      const previewWidget = node.addDOMWidget("preview", "custom", container, {
        serialize: false,
        hideOnZoom: false,
        getValue() {
          return "";
        },
        setValue() {
        }
      });
      previewWidget.aspectRatio = null;
      previewWidget.computeSize = function (width) {
        if (container.style.display === "none") return [width, 0];
        let chrome = 32 + 22 + 14 + (allVideos.length > 1 ? 100 : 0);
        if (currentMode === VIEW_MODES.FILMSTRIP) chrome += 50;
        if (currentMode === VIEW_MODES.EDIT) chrome += 180;
        if (this.aspectRatio) {
          const h = (node.size[0] - 20) / this.aspectRatio;
          return [width, Math.max(h, 80) + chrome];
        }
        return [width, 80 + chrome];
      };
      container.appendChild(toolbar);
      container.appendChild(videoEl);
      container.appendChild(markerBar);
      container.appendChild(canvasEl);
      container.appendChild(infoEl);
      const stripWrapper = document.createElement("div");
      stripWrapper.className = "ll_strip_wrapper";
      stripWrapper.appendChild(browserStrip);
      stripWrapper.appendChild(scrollTrack);
      container.appendChild(stripWrapper);
      async function switchMode(mode) {
        var _a2;
        currentMode = mode;
        highlightToolbar();
        if (mode !== VIEW_MODES.EDIT) {
          cleanupEditMode();
        }
        if (mode === VIEW_MODES.PLAYBACK) {
          modeGeometry = null;
          canvasEl.style.display = "none";
          canvasEl.height = 0;
          videoEl.style.display = "block";
          videoEl.play().catch(() => {
          });
          const sel = selections.get(VIEW_MODES.PLAYBACK);
          const selInfo = sel.size ? ` │ ${sel.size} selected` : "";
          infoEl.textContent = buildInfoText() + selInfo;
        } else if (mode === VIEW_MODES.EDIT) {
          canvasEl.style.display = "none";
          canvasEl.height = 0;
          videoEl.controls = false;
          videoEl.pause();
          editWrapper = document.createElement("div");
          editWrapper.className = "ll_edit_wrapper";
          const videoArea = document.createElement("div");
          videoArea.className = "ll_edit_video_area";
          videoEl.style.display = "block";
          videoArea.appendChild(videoEl);
          editBlackOverlay = document.createElement("div");
          editBlackOverlay.className = "ll_edit_black_overlay";
          videoArea.appendChild(editBlackOverlay);
          editWrapper.appendChild(videoArea);
          const transport = document.createElement("div");
          transport.className = "ll_edit_transport";
          editPlayBtn = document.createElement("button");
          editPlayBtn.className = "ll_edit_play_btn";
          editPlayBtn.textContent = "▶";
          editPlayBtn.title = "Play edited clip";
          editPlayBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            if (editPlaying) {
              stopEditPlayback();
            } else {
              startEditPlayback();
            }
          });
          transport.appendChild(editPlayBtn);
          editTimeDisplay = document.createElement("span");
          editTimeDisplay.className = "ll_edit_time_display";
          editTimeDisplay.textContent = "0:00 / 0:00";
          transport.appendChild(editTimeDisplay);
          editWrapper.appendChild(transport);
          const dur = videoEl.duration;
          if (dur && isFinite(dur)) {
            editMgr.init(dur);
            editOutputTime = 0;
            updateEditTimeDisplay();
            editTimeline = new EditTimeline(editMgr, {
              onSegmentsChanged: () => {
                editMgr.syncToWidget();
                updateEditPreview();
                updateEditInfo();
                updateEditTimeDisplay();
              },
              onPlayheadChanged: (time) => {
                videoEl.currentTime = time;
                if (editBlackOverlay) {
                  editBlackOverlay.style.display = editMgr.isInGap(time) ? "block" : "none";
                }
                editOutputTime = Math.max(0, editMgr.sourceTimeToOutput(time));
                updateEditTimeDisplay();
              },
              onTrimHandleDrag: (time) => {
                videoEl.currentTime = time;
                if (editBlackOverlay) editBlackOverlay.style.display = "none";
                editOutputTime = Math.max(0, editMgr.sourceTimeToOutput(time));
                updateEditTimeDisplay();
              },
              onRequestSplit: () => {
              }
            });
            editWrapper.appendChild(editTimeline.element);
            videoEl.currentTime = ((_a2 = editMgr.segments[0]) == null ? void 0 : _a2.start) ?? 0;
            requestAnimationFrame(() => {
              editTimeline == null ? void 0 : editTimeline.render();
            });
          }
          container.insertBefore(editWrapper, stripWrapper);
          updateEditInfo();
        } else {
          videoEl.pause();
          videoEl.style.display = "none";
          canvasEl.style.display = "block";
          await renderCurrentMode();
        }
        if (mode !== VIEW_MODES.FILMSTRIP) {
          const oldCtrl = container.querySelector(".filmstrip_controls");
          if (oldCtrl) oldCtrl.remove();
        }
        fitNode();
      }
      function cleanupEditMode() {
        stopEditPlayback();
        if (editTimeline) {
          editTimeline = null;
        }
        if (editWrapper) {
          videoEl.style.display = "none";
          videoEl.controls = true;
          container.insertBefore(videoEl, stripWrapper);
          editWrapper.remove();
          editWrapper = null;
        }
        editPlayBtn = null;
        editTimeDisplay = null;
        editBlackOverlay = null;
      }
      function updateEditInfo() {
        if (!editMgr.hasEdits()) {
          infoEl.textContent = buildInfoText() + " │ ✂️ Edit mode (no changes)";
        } else {
          const outDur = fmtDuration(editMgr.getOutputDuration());
          const segs = editMgr.segments.length;
          infoEl.textContent = `✂️ Edit: ${outDur} output │ ${segs} segment${segs !== 1 ? "s" : ""}`;
        }
      }
      function updateEditPreview() {
        const srcTime = videoEl.currentTime;
        const inGap = editMgr.isInGap(srcTime);
        if (editBlackOverlay) {
          editBlackOverlay.style.display = inGap ? "block" : "none";
        }
        if (inGap && editMgr.segments.length > 0) {
          const nextSeg = editMgr.segments.find((s) => s.start >= srcTime);
          if (nextSeg) {
            videoEl.currentTime = nextSeg.start;
          } else {
            videoEl.currentTime = editMgr.segments[0].start;
          }
          if (editBlackOverlay) editBlackOverlay.style.display = "none";
        }
        editOutputTime = Math.max(0, editMgr.sourceTimeToOutput(videoEl.currentTime));
      }
      function updateEditTimeDisplay() {
        if (!editTimeDisplay) return;
        const pos = fmtDuration(editOutputTime);
        const total = fmtDuration(editMgr.getOutputDuration());
        editTimeDisplay.textContent = `${pos} / ${total}`;
      }
      function startEditPlayback() {
        if (editPlaying) return;
        editPlaying = true;
        if (editPlayBtn) editPlayBtn.textContent = "⏸";
        let lastFrameTime = performance.now();
        function editLoop(now) {
          if (!editPlaying) return;
          const dt = (now - lastFrameTime) / 1e3;
          lastFrameTime = now;
          editOutputTime += dt;
          const totalDur = editMgr.getOutputDuration();
          if (editOutputTime >= totalDur) {
            editOutputTime = 0;
          }
          const srcTime = editMgr.outputTimeToSource(editOutputTime);
          videoEl.currentTime = srcTime;
          if (editBlackOverlay) editBlackOverlay.style.display = "none";
          if (editTimeline) {
            editTimeline.playhead = srcTime;
            editTimeline.render();
          }
          updateEditTimeDisplay();
          editPlaybackRaf = requestAnimationFrame(editLoop);
        }
        videoEl.pause();
        editPlaybackRaf = requestAnimationFrame(editLoop);
      }
      function stopEditPlayback() {
        editPlaying = false;
        if (editPlayBtn) editPlayBtn.textContent = "▶";
        if (editPlaybackRaf !== null) {
          cancelAnimationFrame(editPlaybackRaf);
          editPlaybackRaf = null;
        }
      }
      container.addEventListener("keydown", (e) => {
        if (currentMode !== VIEW_MODES.FILMSTRIP) return;
        const dur = videoEl.duration;
        if (!dur || !isFinite(dur)) return;
        const interval = ZOOM_LEVELS[filmstripZoom];
        const totalFrames = Math.max(1, Math.floor(dur / interval));
        const totalPages = Math.ceil(totalFrames / FRAMES_PER_PAGE);
        if (e.key === "ArrowRight") {
          e.stopPropagation();
          e.preventDefault();
          if (e.shiftKey) {
            const nextStart = filmstripPage * FRAMES_PER_PAGE + 1;
            filmstripPage = Math.min(Math.floor(nextStart / FRAMES_PER_PAGE), totalPages - 1);
          } else {
            if (filmstripPage < totalPages - 1) filmstripPage++;
          }
          renderCurrentMode();
        } else if (e.key === "ArrowLeft") {
          e.stopPropagation();
          e.preventDefault();
          if (e.shiftKey) {
            const prevStart = filmstripPage * FRAMES_PER_PAGE - 1;
            filmstripPage = Math.max(Math.floor(prevStart / FRAMES_PER_PAGE), 0);
          } else {
            if (filmstripPage > 0) filmstripPage--;
          }
          renderCurrentMode();
        }
      });
      const flashOverlay = document.createElement("div");
      flashOverlay.className = "ll_flash_overlay";
      container.appendChild(flashOverlay);
      function flashSelection(added) {
        flashOverlay.style.borderColor = added ? "#00ddff" : "#ff4444";
        flashOverlay.style.opacity = "1";
        setTimeout(() => {
          flashOverlay.style.transition = "opacity 0.4s ease-out";
          flashOverlay.style.opacity = "0";
          setTimeout(() => {
            flashOverlay.style.transition = "opacity 0.1s ease-in";
          }, 400);
        }, 100);
      }
      videoEl.addEventListener("click", (e) => {
        if (currentMode !== VIEW_MODES.PLAYBACK) return;
        if (!videoEl.paused) return;
        e.stopPropagation();
        const ts = Math.round(videoEl.currentTime * 1e3) / 1e3;
        const added = selections.toggle(VIEW_MODES.PLAYBACK, ts);
        flashSelection(added);
        updateSelectionUI();
      }, true);
      async function renderCurrentMode() {
        const vw = videoEl.videoWidth;
        const vh = videoEl.videoHeight;
        if (!vw || !vh) return;
        if (currentMode === VIEW_MODES.GRID) {
          infoEl.textContent = "Capturing grid frames...";
          const cols = 3, rows = 3, count = cols * rows;
          const frames = await captureFrames(videoEl, count);
          if (!frames.length) {
            infoEl.textContent = "Could not capture frames";
            return;
          }
          const cellW = Math.round(300 * (vw / vh));
          const cellH = 300;
          canvasEl.width = cellW * cols;
          canvasEl.height = cellH * rows;
          const ctx = canvasEl.getContext("2d");
          ctx.fillStyle = "#000";
          ctx.fillRect(0, 0, canvasEl.width, canvasEl.height);
          const dur = videoEl.duration;
          for (let i = 0; i < frames.length; i++) {
            const col = i % cols;
            const row = Math.floor(i / cols);
            const x = col * cellW;
            const y = row * cellH;
            ctx.drawImage(frames[i], 0, 0, vw, vh, x, y, cellW, cellH);
            const t = dur * i / Math.max(count - 1, 1);
            const label = fmtDuration(t);
            ctx.font = "bold 11px monospace";
            ctx.fillStyle = "rgba(0,0,0,0.7)";
            ctx.fillRect(x + 2, y + 2, ctx.measureText(label).width + 8, 16);
            ctx.fillStyle = "#ccc";
            ctx.textBaseline = "top";
            ctx.fillText(label, x + 5, y + 4);
          }
          previewWidget.aspectRatio = canvasEl.width / canvasEl.height;
          modeGeometry = {
            mode: VIEW_MODES.GRID,
            cols,
            rows,
            count,
            cellW,
            cellH,
            timestamps: Array.from(
              { length: count },
              (_, i) => Math.round(dur * i / Math.max(count - 1, 1) * 1e3) / 1e3
            )
          };
          const gSelCount = selections.get(VIEW_MODES.GRID).size;
          infoEl.textContent = `Grid: ${count} frames │ ${fmtDuration(dur)}` + (gSelCount ? ` │ ${gSelCount} selected` : "");
          drawSelectionOverlay(canvasEl, modeGeometry, selections.get(VIEW_MODES.GRID));
          fitNode();
        } else if (currentMode === VIEW_MODES.SIDE_BY_SIDE) {
          infoEl.textContent = "Capturing comparison frames...";
          const dur = videoEl.duration;
          const firstFrame = await captureFrame(videoEl, 0);
          const lastFrame = await captureFrame(videoEl, Math.max(dur - 0.1, 0));
          const h = 300;
          const w = Math.round(h * (vw / vh));
          const gap = 4;
          canvasEl.width = w * 2 + gap;
          canvasEl.height = h;
          const ctx = canvasEl.getContext("2d");
          ctx.fillStyle = "#000";
          ctx.fillRect(0, 0, canvasEl.width, canvasEl.height);
          ctx.drawImage(firstFrame, 0, 0, vw, vh, 0, 0, w, h);
          ctx.drawImage(lastFrame, 0, 0, vw, vh, w + gap, 0, w, h);
          ctx.font = "bold 11px monospace";
          ctx.textBaseline = "top";
          for (const [label, x] of [["FIRST", 4], ["LAST", w + gap + 4]]) {
            ctx.fillStyle = "rgba(0,0,0,0.7)";
            ctx.fillRect(x, 4, ctx.measureText(label).width + 8, 16);
            ctx.fillStyle = "#ccc";
            ctx.fillText(label, x + 4, 6);
          }
          previewWidget.aspectRatio = canvasEl.width / canvasEl.height;
          const ts0 = 0;
          const ts1 = Math.round(Math.max(dur - 0.1, 0) * 1e3) / 1e3;
          modeGeometry = {
            mode: VIEW_MODES.SIDE_BY_SIDE,
            videoWidth: w,
            gap,
            timestamps: [ts0, ts1]
          };
          const sSelCount = selections.get(VIEW_MODES.SIDE_BY_SIDE).size;
          infoEl.textContent = `Side by Side │ ${fmtDuration(dur)}` + (sSelCount ? ` │ ${sSelCount} selected` : "");
          drawSelectionOverlay(canvasEl, modeGeometry, selections.get(VIEW_MODES.SIDE_BY_SIDE));
          fitNode();
        } else if (currentMode === VIEW_MODES.FILMSTRIP) {
          const dur = videoEl.duration;
          if (!dur || !isFinite(dur)) return;
          const interval = ZOOM_LEVELS[filmstripZoom];
          const totalFrames = Math.max(1, Math.floor(dur / interval));
          const totalPages = Math.ceil(totalFrames / FRAMES_PER_PAGE);
          filmstripPage = Math.max(0, Math.min(filmstripPage, totalPages - 1));
          const startIdx = filmstripPage * FRAMES_PER_PAGE;
          const endIdx = Math.min(startIdx + FRAMES_PER_PAGE, totalFrames);
          const pageCount = endIdx - startIdx;
          infoEl.textContent = `Capturing frames ${startIdx + 1}–${endIdx} of ${totalFrames}...`;
          const pageFrames = [];
          const pageTimestamps = [];
          for (let i = startIdx; i < endIdx; i++) {
            const t = Math.min(i * interval, dur - 0.01);
            pageTimestamps.push(Math.round(t * 1e3) / 1e3);
            pageFrames.push(await captureFrame(videoEl, t));
          }
          const fh = 200;
          const fw = Math.round(fh * (vw / vh));
          const gap = 3;
          canvasEl.width = (fw + gap) * pageCount - gap;
          canvasEl.height = fh;
          const ctx = canvasEl.getContext("2d");
          ctx.fillStyle = "#000";
          ctx.fillRect(0, 0, canvasEl.width, canvasEl.height);
          for (let i = 0; i < pageFrames.length; i++) {
            const x = i * (fw + gap);
            ctx.drawImage(pageFrames[i], 0, 0, vw, vh, x, 0, fw, fh);
            const label = fmtDuration(pageTimestamps[i]);
            ctx.font = "bold 11px monospace";
            ctx.textBaseline = "top";
            ctx.fillStyle = "rgba(0,0,0,0.75)";
            const tw = ctx.measureText(label).width;
            ctx.fillRect(x + 3, 3, tw + 8, 18);
            ctx.fillStyle = "#eee";
            ctx.fillText(label, x + 7, 6);
            const frameNum = `#${startIdx + i + 1}`;
            ctx.font = "bold 10px monospace";
            ctx.textBaseline = "bottom";
            ctx.fillStyle = "rgba(0,0,0,0.75)";
            const fnw = ctx.measureText(frameNum).width;
            ctx.fillRect(x + 3, fh - 18, fnw + 8, 16);
            ctx.fillStyle = "#aaa";
            ctx.fillText(frameNum, x + 7, fh - 4);
          }
          previewWidget.aspectRatio = canvasEl.width / canvasEl.height;
          modeGeometry = {
            mode: VIEW_MODES.FILMSTRIP,
            frameWidth: fw,
            frameHeight: fh,
            gap,
            count: pageCount,
            timestamps: pageTimestamps
          };
          drawSelectionOverlay(canvasEl, modeGeometry, selections.get(VIEW_MODES.FILMSTRIP));
          const oldCtrl = container.querySelector(".filmstrip_controls");
          if (oldCtrl) oldCtrl.remove();
          const ctrl = document.createElement("div");
          ctrl.className = "filmstrip_controls ll_filmstrip_ctrl";
          const row1 = document.createElement("div");
          row1.className = "ll_filmstrip_row";
          row1.style.cssText = "font-size:11px;font-family:monospace;color:#999;";
          const makeBtn = (text, tip, onClick) => {
            const b = document.createElement("button");
            b.textContent = text;
            b.title = tip;
            b.className = "ll_filmstrip_btn";
            b.addEventListener("click", (e) => {
              e.stopPropagation();
              onClick();
            });
            return b;
          };
          const prevBtn = makeBtn("◀", "Previous page", () => {
            if (filmstripPage > 0) {
              filmstripPage--;
              renderCurrentMode();
            }
          });
          const nextBtn = makeBtn("▶", "Next page", () => {
            if (filmstripPage < totalPages - 1) {
              filmstripPage++;
              renderCurrentMode();
            }
          });
          const zoomOutBtn = makeBtn("➖", "Zoom out (sparser)", () => {
            if (filmstripZoom > 0) {
              filmstripZoom--;
              filmstripPage = 0;
              renderCurrentMode();
            }
          });
          const zoomInBtn = makeBtn("➕", "Zoom in (denser)", () => {
            if (filmstripZoom < ZOOM_LEVELS.length - 1) {
              filmstripZoom++;
              filmstripPage = 0;
              renderCurrentMode();
            }
          });
          row1.append(prevBtn, nextBtn);
          const sep1 = document.createElement("span");
          sep1.textContent = "│";
          sep1.style.color = "#444";
          row1.append(sep1);
          row1.append(zoomOutBtn, zoomInBtn);
          const zoomLabel = document.createElement("span");
          zoomLabel.textContent = ZOOM_LABELS[filmstripZoom];
          zoomLabel.style.color = "#5ac";
          row1.append(zoomLabel);
          const sep2 = document.createElement("span");
          sep2.textContent = "│";
          sep2.style.color = "#444";
          row1.append(sep2);
          const counter = document.createElement("span");
          counter.textContent = `Frames ${startIdx + 1}–${endIdx} of ${totalFrames}`;
          row1.append(counter);
          const fSelCount = selections.get(VIEW_MODES.FILMSTRIP).size;
          if (fSelCount > 0) {
            const selLabel = document.createElement("span");
            selLabel.textContent = `│ ${fSelCount} selected`;
            selLabel.style.color = "#5ac";
            row1.append(selLabel);
          }
          ctrl.appendChild(row1);
          const scrubber = document.createElement("div");
          scrubber.className = "ll_scrubber";
          scrubber.style.cssText = "position:relative;height:16px;background:#1a1a1a;border-radius:3px;cursor:pointer;border:1px solid #333;";
          const rangeStart = startIdx * interval / dur;
          const rangeEnd = endIdx * interval / dur;
          const rangeEl = document.createElement("div");
          rangeEl.style.cssText = `position:absolute;top:0;bottom:0;left:${(rangeStart * 100).toFixed(2)}%;width:${((rangeEnd - rangeStart) * 100).toFixed(2)}%;background:rgba(90,170,200,0.3);border-radius:3px;`;
          scrubber.appendChild(rangeEl);
          for (const t of selections.allTimestamps()) {
            const pct = t / dur * 100;
            if (pct < 0 || pct > 100) continue;
            const dot = document.createElement("div");
            dot.className = "ll_marker_tick";
            dot.style.cssText = `top:3px;width:4px;height:10px;left:calc(${pct.toFixed(2)}% - 2px);`;
            scrubber.appendChild(dot);
          }
          scrubber.addEventListener("mousedown", (e) => {
            e.stopPropagation();
            const rect = scrubber.getBoundingClientRect();
            const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
            const targetTime = ratio * dur;
            const targetIdx = Math.floor(targetTime / interval);
            filmstripPage = Math.floor(targetIdx / FRAMES_PER_PAGE);
            renderCurrentMode();
          });
          ctrl.appendChild(scrubber);
          container.insertBefore(ctrl, stripWrapper);
          infoEl.textContent = `Filmstrip: ${ZOOM_LABELS[filmstripZoom]} │ pg ${filmstripPage + 1}/${totalPages} │ ${fmtDuration(dur)}`;
          fitNode();
        } else if (currentMode === VIEW_MODES.SELECTED) {
          const allTs = selections.allTimestampsWithSource();
          if (allTs.size === 0) {
            canvasEl.width = 400;
            canvasEl.height = 100;
            const ctx2 = canvasEl.getContext("2d");
            ctx2.fillStyle = "#111";
            ctx2.fillRect(0, 0, 400, 100);
            ctx2.font = "13px monospace";
            ctx2.fillStyle = "#555";
            ctx2.textAlign = "center";
            ctx2.textBaseline = "middle";
            ctx2.fillText("No frames selected. Click frames in other modes.", 200, 50);
            previewWidget.aspectRatio = 4;
            modeGeometry = null;
            infoEl.textContent = "Selected: 0 frames";
            fitNode();
            return;
          }
          const sorted = Array.from(allTs.entries()).sort((a, b) => a[0] - b[0]);
          infoEl.textContent = `Capturing ${sorted.length} selected frames...`;
          const galFrames = [];
          for (const [ts] of sorted) {
            galFrames.push(await captureFrame(videoEl, ts));
          }
          const galCols = sorted.length <= 2 ? sorted.length : sorted.length <= 4 ? 2 : 3;
          const galRows = Math.ceil(sorted.length / galCols);
          const cellH = 180;
          const cellW = Math.round(cellH * (vw / vh));
          const galGap = 4;
          canvasEl.width = galCols * (cellW + galGap) - galGap;
          canvasEl.height = galRows * (cellH + galGap) - galGap;
          const ctx = canvasEl.getContext("2d");
          ctx.fillStyle = "#111";
          ctx.fillRect(0, 0, canvasEl.width, canvasEl.height);
          const modeIcons = {
            playback: "▶",
            grid: "📊",
            sidebyside: "↔",
            filmstrip: "🎞"
          };
          for (let i = 0; i < galFrames.length; i++) {
            const col = i % galCols;
            const row = Math.floor(i / galCols);
            const x = col * (cellW + galGap);
            const y = row * (cellH + galGap);
            ctx.drawImage(galFrames[i], 0, 0, vw, vh, x, y, cellW, cellH);
            ctx.strokeStyle = "#00ddff";
            ctx.lineWidth = 2;
            ctx.strokeRect(x + 1, y + 1, cellW - 2, cellH - 2);
            const label = fmtDuration(sorted[i][0]);
            ctx.font = "bold 11px monospace";
            ctx.textBaseline = "top";
            ctx.fillStyle = "rgba(0,0,0,0.8)";
            const tw = ctx.measureText(label).width;
            ctx.fillRect(x + 3, y + 3, tw + 8, 16);
            ctx.fillStyle = "#00ddff";
            ctx.fillText(label, x + 7, y + 5);
            const modes = sorted[i][1];
            const badge = modes.map((m) => modeIcons[m] || m).join("");
            ctx.font = "10px monospace";
            ctx.textBaseline = "bottom";
            ctx.fillStyle = "rgba(0,0,0,0.8)";
            const bw = ctx.measureText(badge).width;
            ctx.fillRect(x + cellW - bw - 10, y + cellH - 18, bw + 8, 16);
            ctx.fillStyle = "#aaa";
            ctx.fillText(badge, x + cellW - bw - 6, y + cellH - 4);
          }
          previewWidget.aspectRatio = canvasEl.width / canvasEl.height;
          modeGeometry = null;
          infoEl.textContent = `Selected: ${sorted.length} frames`;
          fitNode();
        }
      }
      function buildInfoText() {
        const parts = [];
        if (videoEl.videoWidth && videoEl.videoHeight)
          parts.push(`${videoEl.videoWidth}×${videoEl.videoHeight}`);
        const d = fmtDuration(videoEl.duration);
        if (d) parts.push(d);
        if (lastFilename) parts.push(lastFilename);
        return parts.join(" │ ") || "Video loaded";
      }
      function fitNode() {
        var _a2, _b, _c;
        const sz = (_a2 = previewWidget.computeSize) == null ? void 0 : _a2.call(previewWidget, node.size[0]);
        if (sz) {
          node.size[1] = sz[1] + 40;
          (_b = node.onResize) == null ? void 0 : _b.call(node, node.size);
          node.setDirtyCanvas(true, true);
          (_c = node.graph) == null ? void 0 : _c.setDirtyCanvas(true, true);
        }
      }
      let allVideos = [];
      async function fetchLatestVideo() {
        try {
          const resp = await api.fetchApi("/loadlast/latest_video");
          const data = await resp.json();
          if (data.found) {
            const entry = {
              filename: data.filename,
              subfolder: data.subfolder || "",
              type: data.type || "output",
              format: data.format || ""
            };
            loadVideo(entry);
            fetchVideoList();
          }
        } catch (e) {
          console.warn("[LoadLast] Failed to fetch latest video:", e);
        }
      }
      function loadVideo(entry) {
        const url = viewUrl(entry);
        if (videoEl.src !== location.origin + url) {
          videoEl.src = url;
          lastFilename = entry.filename;
          infoEl.textContent = `Loading ${entry.filename}...`;
        }
      }
      async function fetchVideoList() {
        try {
          const resp = await api.fetchApi("/loadlast/video_list");
          const data = await resp.json();
          if (data.videos) {
            allVideos = data.videos;
            renderBrowserStrip();
            updateScrollIndicator();
          }
        } catch (e) {
          console.warn("[LoadLast] Failed to fetch video list:", e);
        }
      }
      function renderBrowserStrip() {
        browserStrip.innerHTML = "";
        if (allVideos.length <= 1) {
          stripWrapper.style.display = "none";
          return;
        }
        stripWrapper.style.display = "block";
        for (const entry of allVideos) {
          const thumb = document.createElement("div");
          thumb.className = "ll_thumb";
          thumb.style.cssText = "width:80px;height:60px;";
          const active = entry.filename === lastFilename;
          if (active) thumb.classList.add("active");
          const vid = document.createElement("video");
          vid.src = viewUrl(entry);
          vid.muted = true;
          vid.preload = "metadata";
          vid.className = "ll_thumb video";
          thumb.appendChild(vid);
          const label = document.createElement("div");
          label.className = "ll_thumb_label";
          label.textContent = entry.filename;
          label.title = entry.filename;
          thumb.appendChild(label);
          thumb.addEventListener("click", (e) => {
            e.stopPropagation();
            loadVideo(entry);
            renderBrowserStrip();
          });
          browserStrip.appendChild(thumb);
        }
      }
      videoEl.addEventListener("loadedmetadata", () => {
        previewWidget.aspectRatio = videoEl.videoWidth / videoEl.videoHeight;
        infoEl.textContent = buildInfoText();
        fitNode();
        if (currentMode !== VIEW_MODES.PLAYBACK) {
          renderCurrentMode();
        }
        updatePlaybackMarkers();
      });
      const refreshWidget = (_a = node.widgets) == null ? void 0 : _a.find((w) => w.name === "refresh_mode");
      if ((refreshWidget == null ? void 0 : refreshWidget.value) === "auto" || !refreshWidget) {
        fetchLatestVideo();
      }
      api.addEventListener("executed", (data) => {
        var _a2, _b, _c, _d, _e, _f;
        if (((_c = (_b = (_a2 = data == null ? void 0 : data.detail) == null ? void 0 : _a2.output) == null ? void 0 : _b.gifs) == null ? void 0 : _c.length) > 0) {
          fetchLatestVideo();
        } else if (((_f = (_e = (_d = data == null ? void 0 : data.detail) == null ? void 0 : _d.output) == null ? void 0 : _e.video) == null ? void 0 : _f.length) > 0) {
          fetchLatestVideo();
        }
      });
      const origGetExtra = node.constructor.prototype.getExtraMenuOptions;
      node.getExtraMenuOptions = function (_, options) {
        origGetExtra == null ? void 0 : origGetExtra.apply(this, arguments);
        const optNew = [];
        const hasVideo = !!videoEl.src && container.style.display !== "none";
        function flashBg(color = "#4a5a7a") {
          const orig = node.bgcolor;
          node.bgcolor = color;
          node.setDirtyCanvas(true, true);
          setTimeout(() => {
            if (node.bgcolor === color) node.bgcolor = orig;
            node.setDirtyCanvas(true, true);
          }, 350);
        }
        if (hasVideo) {
          optNew.push({
            content: "🔗 Open Preview",
            callback: () => window.open(videoEl.src, "_blank")
          });
          optNew.push({
            content: "💾 Save Video",
            callback: () => {
              const a = document.createElement("a");
              a.href = videoEl.src;
              try {
                const params = new URL(a.href, location.origin).searchParams;
                a.download = params.get("filename") || "video.mp4";
              } catch {
                a.download = "video.mp4";
              }
              document.body.append(a);
              a.click();
              requestAnimationFrame(() => a.remove());
            }
          });
          optNew.push({
            content: videoEl.paused ? "▶️ Resume" : "⏸️ Pause",
            callback: () => {
              if (videoEl.paused) videoEl.play().catch(() => {
              });
              else videoEl.pause();
            }
          });
          optNew.push({
            content: videoEl.muted ? "🔊 Unmute" : "🔇 Mute",
            callback: () => {
              videoEl.muted = !videoEl.muted;
            }
          });
          optNew.push({
            content: "⏱️ Playback Speed",
            submenu: {
              options: [
                {
                  content: "0.25x", callback: () => {
                    videoEl.playbackRate = 0.25;
                    flashBg("#5a5a3a");
                  }
                },
                {
                  content: "0.5x", callback: () => {
                    videoEl.playbackRate = 0.5;
                    flashBg("#5a5a3a");
                  }
                },
                {
                  content: "1x (Normal)", callback: () => {
                    videoEl.playbackRate = 1;
                    flashBg("#5a5a3a");
                  }
                },
                {
                  content: "1.5x", callback: () => {
                    videoEl.playbackRate = 1.5;
                    flashBg("#5a5a3a");
                  }
                },
                {
                  content: "2x", callback: () => {
                    videoEl.playbackRate = 2;
                    flashBg("#5a5a3a");
                  }
                }
              ]
            }
          });
          optNew.push({
            content: videoEl.loop ? "🔁 Loop: ON" : "➡️ Loop: OFF",
            callback: () => {
              videoEl.loop = !videoEl.loop;
              flashBg("#5a5a3a");
            }
          });
          optNew.push({
            content: "📋 Copy Video Path",
            callback: async () => {
              try {
                const params = new URL(videoEl.src, location.origin).searchParams;
                const filename = params.get("filename") || videoEl.src;
                await navigator.clipboard.writeText(filename);
                flashBg("#4a7a4a");
                infoEl.textContent = "📋 Copied!";
                setTimeout(() => {
                  infoEl.textContent = buildInfoText();
                }, 1200);
              } catch {
                flashBg("#7a4a4a");
              }
            }
          });
          if (videoEl.videoWidth) {
            optNew.push({
              content: "📸 Screenshot Frame",
              callback: async () => {
                var _a2;
                try {
                  const c = document.createElement("canvas");
                  c.width = videoEl.videoWidth;
                  c.height = videoEl.videoHeight;
                  c.getContext("2d").drawImage(videoEl, 0, 0);
                  const blob = await new Promise((r) => c.toBlob(r, "image/png"));
                  if (blob && ((_a2 = navigator.clipboard) == null ? void 0 : _a2.write)) {
                    await navigator.clipboard.write([
                      new ClipboardItem({ "image/png": blob })
                    ]);
                    flashBg("#4a7a4a");
                    infoEl.textContent = "📸 Copied to clipboard!";
                  } else if (blob) {
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement("a");
                    a.href = url;
                    a.download = "screenshot.png";
                    a.click();
                    URL.revokeObjectURL(url);
                    flashBg("#4a7a4a");
                    infoEl.textContent = "📸 Saved!";
                  }
                  setTimeout(() => {
                    infoEl.textContent = buildInfoText();
                  }, 1200);
                } catch {
                  flashBg("#7a4a4a");
                }
              }
            });
          }
        }
        optNew.push({
          content: container.style.display === "none" ? "👁️ Show Preview" : "🙈 Hide Preview",
          callback: () => {
            if (container.style.display === "none") {
              container.style.display = "";
              if (!videoEl.paused) videoEl.play().catch(() => {
              });
            } else {
              videoEl.pause();
              container.style.display = "none";
            }
            fitNode();
          }
        });
        optNew.push(null);
        const totalSel = selections.totalCount();
        if (currentMode !== VIEW_MODES.PLAYBACK && videoEl.duration > 0) {
          optNew.push({
            content: "✅ Select All Visible Frames",
            callback: () => {
              if (!modeGeometry) return;
              const frames = modeGeometry.timestamps;
              if (frames) {
                for (const ts of frames) {
                  const set = selections.get(currentMode);
                  const key = Math.round(ts * 1e3) / 1e3;
                  set.add(key);
                }
                updateSelectionUI();
                renderCurrentMode();
                flashBg("#4a7a4a");
              }
            }
          });
        }
        if (totalSel > 0) {
          optNew.push({
            content: `🗑️ Clear All Selections (${totalSel})`,
            callback: () => {
              selections.clearAll();
              updateSelectionUI();
              if (currentMode !== VIEW_MODES.PLAYBACK) renderCurrentMode();
              else drawSelectionOverlay(canvasEl, modeGeometry, selections.get(currentMode));
              flashBg("#5a4a3a");
            }
          });
        }
        if (totalSel > 0) {
          optNew.push({
            content: "📋 Copy Selected Timestamps",
            callback: async () => {
              const ts = selections.allTimestamps();
              const text = ts.map((t) => t.toFixed(3)).join(", ");
              try {
                await navigator.clipboard.writeText(text);
                flashBg("#4a7a4a");
                infoEl.textContent = `📋 ${ts.length} timestamps copied!`;
                setTimeout(() => {
                  infoEl.textContent = buildInfoText();
                }, 1200);
              } catch {
                flashBg("#7a4a4a");
              }
            }
          });
        }
        optNew.push({
          content: "🎨 View Mode",
          submenu: {
            options: [
              {
                content: `${currentMode === VIEW_MODES.PLAYBACK ? "● " : ""}Playback`, callback: () => {
                  switchMode(VIEW_MODES.PLAYBACK);
                }
              },
              {
                content: `${currentMode === VIEW_MODES.GRID ? "● " : ""}Grid`, callback: () => {
                  switchMode(VIEW_MODES.GRID);
                }
              },
              {
                content: `${currentMode === VIEW_MODES.SIDE_BY_SIDE ? "● " : ""}Side by Side`, callback: () => {
                  switchMode(VIEW_MODES.SIDE_BY_SIDE);
                }
              },
              {
                content: `${currentMode === VIEW_MODES.FILMSTRIP ? "● " : ""}Filmstrip`, callback: () => {
                  switchMode(VIEW_MODES.FILMSTRIP);
                }
              },
              {
                content: `${currentMode === VIEW_MODES.SELECTED ? "● " : ""}Selected`, callback: () => {
                  switchMode(VIEW_MODES.SELECTED);
                }
              }
            ]
          }
        });
        if (options.length > 0 && options[0] != null && optNew.length > 0) {
          optNew.push(null);
        }
        options.unshift(...optNew);
      };
      highlightToolbar();
    };
  }
});
