import { f as flashNode } from "./ui_helpers-Cs5gHV_9.js";
const HIT_RADIUS = 20;
function openPointSelector(node, imgSrc, _videoSrc, framePath) {
  var _a, _b;
  let _framePath = framePath || "";
  (_a = document.getElementById("ffmpega-point-selector")) == null ? void 0 : _a.remove();
  let existing = {
    points: [],
    labels: [],
    image_width: 0,
    image_height: 0
  };
  const mpWidget = (_b = node.widgets) == null ? void 0 : _b.find((w) => w.name === "mask_points_data");
  if (mpWidget == null ? void 0 : mpWidget.value) {
    try {
      existing = JSON.parse(String(mpWidget.value));
    } catch {
    }
  }
  let mode = existing.mode || "points";
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
  const exitBtn = document.createElement("button");
  exitBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="1" y1="1" x2="13" y2="13"/><line x1="13" y1="1" x2="1" y2="13"/></svg>`;
  exitBtn.setAttribute("aria-label", "Close Mask Editor");
  exitBtn.style.cssText = `
        position:absolute;top:12px;right:12px;z-index:10;
        background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.2);
        border-radius:50%;width:36px;height:36px;cursor:pointer;
        display:flex;align-items:center;justify-content:center;
        color:#ccc;font-size:18px;transition:all 0.15s;
    `;
  exitBtn.onmouseenter = () => {
    exitBtn.style.background = "rgba(255,80,80,0.3)";
    exitBtn.style.color = "#fff";
  };
  exitBtn.onmouseleave = () => {
    exitBtn.style.background = "rgba(255,255,255,0.08)";
    exitBtn.style.color = "#ccc";
  };
  exitBtn.onclick = () => {
    document.removeEventListener("keydown", keyHandler);
    overlay.remove();
  };
  overlay.appendChild(exitBtn);
  const header = document.createElement("div");
  header.style.cssText = `
        color:#eee;font-size:14px;margin-bottom:8px;
        display:flex;gap:16px;align-items:center;
    `;
  overlay.appendChild(header);
  const svgIcon = (d, size = 16) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${d}"/></svg>`;
  const ICO = {
    target: svgIcon("M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M12 11a1 1 0 1 0 0 2 1 1 0 0 0 0-2"),
    brush: svgIcon("M18.37 2.63a2.12 2.12 0 0 1 3 3L14 13l-4 1 1-4ZM9 15v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-2a2 2 0 0 1 2-2h3"),
    box: svgIcon("M3 3h18v18H3zM8 3v18M16 3v18M3 8h18M3 16h18"),
    nudge: svgIcon("M12 2l4 4h-3v4h-2V6H8zM2 12l4-4v3h4v2H6v3zM22 12l-4-4v3h-4v2h4v3zM12 22l-4-4h3v-4h2v4h3z"),
    bolt: svgIcon("M13 2L3 14h9l-1 8 10-12h-9z"),
    trash: svgIcon("M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"),
    check: svgIcon("M20 6L9 17l-5-5")
  };
  let _smartClamp = true;
  let _sam3Loading = false;
  const updateHeader = () => {
    const loadingDot = _sam3Loading ? ' <span style="color:#ff0;font-size:10px">⏳ Processing...</span>' : "";
    if (mode === "points") {
      header.innerHTML = `<span>${ICO.target} <b>Point Mode</b></span>
                <span style="color:#4f4">● Left-click = Include</span>
                <span style="color:#f44">● Right-click = Exclude</span>
                <span style="color:#888">Click existing point to remove</span>${loadingDot}`;
    } else if (mode === "box") {
      header.innerHTML = `<span>${ICO.box} <b>Box Mode</b></span>
                <span style="color:#4f4">Drag to draw bounding box around object</span>
                <span style="color:#888">Release to predict mask</span>${loadingDot}`;
    } else if (mode === "nudge") {
      header.innerHTML = `<span>${ICO.nudge} <b>Nudge Mode</b></span>
                <span style="color:#4f4">● Left-drag = Push mask out</span>
                <span style="color:#f44">● Right-drag = Push mask in</span>`;
    } else if (mode === "smart") {
      const sub = _smartClamp ? "Clamp" : "Attract";
      header.innerHTML = `<span>${ICO.bolt} <b>Smart Draw</b> (${sub})</span>
                <span style="color:#0ff">● Edge-snapping brush</span>
                <span style="color:#4f4">● Left = Paint</span>
                <span style="color:#f44">● Right = Erase</span>`;
    } else {
      header.innerHTML = `<span>${ICO.brush} <b>Draw Mode</b></span>
                <span style="color:#4f4">● Left-drag = Paint</span>
                <span style="color:#f44">● Right-drag = Erase</span>`;
    }
  };
  updateHeader();
  let _zoom = 1;
  let _panX = 0;
  let _panY = 0;
  let _isPanning = false;
  let _panStartX = 0;
  let _panStartY = 0;
  let _panStartPanX = 0;
  let _panStartPanY = 0;
  const ZOOM_MIN = 0.25;
  const ZOOM_MAX = 6;
  const ZOOM_FACTOR = 1.12;
  const canvasViewport = document.createElement("div");
  canvasViewport.style.cssText = "position:relative;width:90vw;height:75vh;overflow:hidden;border-radius:4px;background:rgba(0,0,0,0.3);cursor:default;";
  const canvasWrap = document.createElement("div");
  canvasWrap.style.cssText = "position:absolute;transform-origin:0 0;";
  const canvas = document.createElement("canvas");
  canvas.style.cssText = "cursor:crosshair;display:block;";
  canvasWrap.appendChild(canvas);
  canvasViewport.appendChild(canvasWrap);
  const applyTransform = () => {
    canvasWrap.style.transform = `translate(${_panX}px, ${_panY}px) scale(${_zoom})`;
    zoomLabel.textContent = Math.round(_zoom * 100) + "%";
  };
  const setZoom = (level, cx, cy) => {
    const oldZoom = _zoom;
    _zoom = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, level));
    if (cx !== void 0 && cy !== void 0) {
      const scale = _zoom / oldZoom;
      _panX = cx - (cx - _panX) * scale;
      _panY = cy - (cy - _panY) * scale;
    }
    applyTransform();
  };
  const fitToView = () => {
    const vw = canvasViewport.clientWidth;
    const vh = canvasViewport.clientHeight;
    const cw = canvas.width || 1;
    const ch = canvas.height || 1;
    _zoom = Math.min(vw / cw, vh / ch, 1);
    _panX = (vw - cw * _zoom) / 2;
    _panY = (vh - ch * _zoom) / 2;
    applyTransform();
  };
  const zoomBar = document.createElement("div");
  zoomBar.style.cssText = `position:absolute;bottom:8px;right:8px;z-index:5;
        display:flex;gap:4px;align-items:center;
        background:rgba(0,0,0,0.7);border-radius:6px;padding:3px 6px;
        border:1px solid rgba(255,255,255,0.15);`;
  const makeZoomBtn = (label, title) => {
    const b = document.createElement("button");
    b.innerHTML = label;
    b.title = title;
    b.style.cssText = `background:rgba(255,255,255,0.1);border:none;color:#ccc;
            cursor:pointer;font-size:16px;width:26px;height:26px;
            border-radius:4px;display:flex;align-items:center;justify-content:center;
            transition:background 0.15s;`;
    b.onmouseenter = () => {
      b.style.background = "rgba(255,255,255,0.2)";
    };
    b.onmouseleave = () => {
      b.style.background = "rgba(255,255,255,0.1)";
    };
    return b;
  };
  const zoomInBtn = makeZoomBtn("+", "Zoom In");
  const zoomOutBtn = makeZoomBtn("−", "Zoom Out");
  const zoomFitBtn = makeZoomBtn("⊡", "Fit to View (F)");
  const zoomLabel = document.createElement("span");
  zoomLabel.style.cssText = "color:#aaa;font-size:11px;min-width:36px;text-align:center;cursor:pointer;";
  zoomLabel.textContent = "100%";
  zoomLabel.title = "Click for 100%";
  zoomLabel.onclick = () => {
    _zoom = 1;
    const vw = canvasViewport.clientWidth;
    const vh = canvasViewport.clientHeight;
    _panX = (vw - canvas.width) / 2;
    _panY = (vh - canvas.height) / 2;
    applyTransform();
  };
  zoomBar.append(zoomOutBtn, zoomLabel, zoomInBtn, zoomFitBtn);
  canvasViewport.appendChild(zoomBar);
  zoomInBtn.onclick = () => {
    const vw = canvasViewport.clientWidth;
    const vh = canvasViewport.clientHeight;
    setZoom(_zoom * ZOOM_FACTOR, vw / 2, vh / 2);
  };
  zoomOutBtn.onclick = () => {
    const vw = canvasViewport.clientWidth;
    const vh = canvasViewport.clientHeight;
    setZoom(_zoom / ZOOM_FACTOR, vw / 2, vh / 2);
  };
  zoomFitBtn.onclick = () => fitToView();
  canvasViewport.addEventListener("wheel", (e) => {
    e.preventDefault();
    const rect = canvasViewport.getBoundingClientRect();
    const cx = e.clientX - rect.left;
    const cy = e.clientY - rect.top;
    const factor = e.deltaY < 0 ? ZOOM_FACTOR : 1 / ZOOM_FACTOR;
    setZoom(_zoom * factor, cx, cy);
  }, { passive: false });
  canvasViewport.addEventListener("pointerdown", (e) => {
    if (e.button === 1 || e.button === 0 && e.altKey) {
      e.preventDefault();
      _isPanning = true;
      _panStartX = e.clientX;
      _panStartY = e.clientY;
      _panStartPanX = _panX;
      _panStartPanY = _panY;
      canvasViewport.setPointerCapture(e.pointerId);
      canvasViewport.style.cursor = "grabbing";
    }
  });
  canvasViewport.addEventListener("pointermove", (e) => {
    if (!_isPanning) return;
    _panX = _panStartPanX + (e.clientX - _panStartX);
    _panY = _panStartPanY + (e.clientY - _panStartY);
    applyTransform();
  });
  canvasViewport.addEventListener("pointerup", (e) => {
    if (_isPanning) {
      _isPanning = false;
      canvasViewport.releasePointerCapture(e.pointerId);
      canvasViewport.style.cursor = "default";
    }
  });
  overlay.appendChild(canvasViewport);
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
  sizeSlider.oninput = () => {
    sizeLabel.textContent = `${sizeSlider.value}px`;
  };
  sliderWrap.appendChild(sizeSlider);
  sliderWrap.appendChild(sizeLabel);
  overlay.appendChild(sliderWrap);
  const statusBar = document.createElement("div");
  statusBar.style.cssText = "color:#aaa;font-size:12px;margin-top:6px;";
  statusBar.textContent = "Loading image...";
  statusBar.setAttribute("role", "status");
  statusBar.setAttribute("aria-live", "polite");
  overlay.appendChild(statusBar);
  const settingsPanel = document.createElement("div");
  settingsPanel.style.cssText = `
        display:flex;gap:16px;align-items:center;margin-top:8px;
        color:#ccc;font-size:12px;flex-wrap:wrap;
        padding:8px 12px;background:rgba(255,255,255,0.04);
        border:1px solid rgba(255,255,255,0.08);border-radius:6px;
    `;
  const makeSliderControl = (label, min, max, value, step, unit) => {
    const wrap = document.createElement("div");
    wrap.style.cssText = "display:flex;align-items:center;gap:4px;";
    const lbl = document.createElement("span");
    lbl.textContent = label;
    lbl.style.cssText = "font-size:11px;color:#999;white-space:nowrap;";
    const slider = document.createElement("input");
    slider.type = "range";
    slider.min = String(min);
    slider.max = String(max);
    slider.value = String(value);
    slider.step = String(step);
    slider.style.cssText = "width:80px;accent-color:#0cf;height:4px;";
    const valLabel = document.createElement("span");
    valLabel.textContent = `${value}${unit}`;
    valLabel.style.cssText = "font-size:11px;min-width:32px;font-family:monospace;";
    slider.oninput = () => {
      valLabel.textContent = `${slider.value}${unit}`;
    };
    wrap.append(lbl, slider, valLabel);
    return { wrap, slider, valLabel };
  };
  const makeToggle = (label, checked) => {
    const wrap = document.createElement("label");
    wrap.style.cssText = "display:flex;align-items:center;gap:4px;cursor:pointer;font-size:11px;color:#999;";
    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.checked = checked;
    cb.style.cssText = "accent-color:#0cf;";
    const span = document.createElement("span");
    span.textContent = label;
    wrap.append(cb, span);
    return { wrap, cb };
  };
  const expandCtrl = makeSliderControl("Expand:", -50, 50, existing.mask_expand ?? 0, 1, "px");
  const featherCtrl = makeSliderControl("Feather:", 0, 50, existing.mask_feather ?? 0, 1, "px");
  const threshCtrl = makeSliderControl("Threshold:", 0, 100, Math.round((existing.mask_threshold ?? 0.5) * 100), 5, "%");
  const invertToggle = makeToggle("Invert", existing.mask_invert ?? false);
  const multiObjToggle = makeToggle("Multi-Object", existing.mask_multi_object ?? false);
  const resetBtn = document.createElement("button");
  resetBtn.textContent = "↺ Reset";
  resetBtn.style.cssText = `
        font-size:11px;padding:3px 8px;border:1px solid rgba(255,255,255,0.15);
        border-radius:4px;background:transparent;color:#aaa;cursor:pointer;
        transition:all 0.15s;
    `;
  resetBtn.onmouseenter = () => {
    resetBtn.style.background = "rgba(255,255,255,0.08)";
    resetBtn.style.color = "#fff";
  };
  resetBtn.onmouseleave = () => {
    resetBtn.style.background = "transparent";
    resetBtn.style.color = "#aaa";
  };
  resetBtn.onclick = () => {
    expandCtrl.slider.value = "0";
    expandCtrl.valLabel.textContent = "0px";
    featherCtrl.slider.value = "0";
    featherCtrl.valLabel.textContent = "0px";
    threshCtrl.slider.value = "50";
    threshCtrl.valLabel.textContent = "50%";
    invertToggle.cb.checked = false;
    multiObjToggle.cb.checked = false;
    _greenOverlayDirty = true;
    redraw();
  };
  const edgeRefineToggle = makeToggle("Edge Refine", existing.mask_edge_refine ?? false);
  const smartClampToggle = makeToggle("Edge Clamp", true);
  smartClampToggle.wrap.style.display = "none";
  smartClampToggle.wrap.title = "Clamp = brush stops at edges; Uncheck for Attract = brush gravitates toward edges";
  settingsPanel.append(
    expandCtrl.wrap,
    featherCtrl.wrap,
    threshCtrl.wrap,
    invertToggle.wrap,
    multiObjToggle.wrap,
    edgeRefineToggle.wrap,
    smartClampToggle.wrap,
    resetBtn
  );
  overlay.appendChild(settingsPanel);
  const rebuildPointOverlay = () => {
    if (!_rawMaskImg || !_rawMaskImg.complete) return;
    _pointOverlay = document.createElement("canvas");
    _pointOverlay.width = canvas.width;
    _pointOverlay.height = canvas.height;
    const pCtx = _pointOverlay.getContext("2d");
    if (!pCtx) return;
    const expandVal = parseInt(expandCtrl.slider.value);
    const featherVal = parseInt(featherCtrl.slider.value);
    const invertVal = invertToggle.cb.checked;
    const totalBlur = (expandVal !== 0 ? Math.abs(expandVal) : 0) + featherVal;
    if (totalBlur > 0) pCtx.filter = `blur(${totalBlur}px)`;
    pCtx.drawImage(_rawMaskImg, 0, 0, canvas.width, canvas.height);
    pCtx.filter = "none";
    const pd = pCtx.getImageData(0, 0, canvas.width, canvas.height);
    let thresh = 128;
    if (expandVal > 0) thresh = Math.max(2, 128 - expandVal * 3);
    else if (expandVal < 0) thresh = Math.min(253, 128 + Math.abs(expandVal) * 3);
    for (let i = 0; i < pd.data.length; i += 4) {
      const val = pd.data[i];
      const isMasked = featherVal > 0 && expandVal === 0 ? val > 2 : val > thresh;
      const showMask = invertVal ? !isMasked : isMasked;
      if (showMask) {
        pd.data[i] = 0;
        pd.data[i + 1] = 212;
        pd.data[i + 2] = 170;
        pd.data[i + 3] = featherVal > 0 ? Math.round(Math.min(150, (invertVal ? 255 - val : val) / 255 * 150)) : 130;
      } else {
        pd.data[i] = 10;
        pd.data[i + 1] = 20;
        pd.data[i + 2] = 35;
        pd.data[i + 3] = 160;
      }
    }
    pCtx.putImageData(pd, 0, 0);
    _pointOverlayDirty = false;
  };
  const onSettingsChanged = () => {
    _greenOverlayDirty = true;
    if ((mode === "points" || mode === "box") && _rawMaskImg) {
      rebuildPointOverlay();
    }
    redraw();
  };
  const onMultiObjChanged = () => {
    _pointOverlayDirty = true;
    if (mode === "points" || mode === "box") debouncedFetchMask();
    else {
      _greenOverlayDirty = true;
      redraw();
    }
  };
  expandCtrl.slider.addEventListener("input", onSettingsChanged);
  featherCtrl.slider.addEventListener("input", onSettingsChanged);
  threshCtrl.slider.addEventListener("input", onSettingsChanged);
  invertToggle.cb.addEventListener("change", onSettingsChanged);
  multiObjToggle.cb.addEventListener("change", onMultiObjChanged);
  edgeRefineToggle.cb.addEventListener("change", () => {
    _pointOverlayDirty = true;
    debouncedFetchMask();
  });
  smartClampToggle.cb.addEventListener("change", () => {
    _smartClamp = smartClampToggle.cb.checked;
    updateHeader();
  });
  const btnBar = document.createElement("div");
  btnBar.style.cssText = "display:flex;gap:8px;margin-top:12px;flex-wrap:wrap;justify-content:center;";
  const makeBtn = (htmlLabel, ariaLabel, bg) => {
    const b = document.createElement("button");
    b.innerHTML = htmlLabel;
    if (ariaLabel) b.setAttribute("aria-label", ariaLabel);
    b.style.cssText = `
            padding:6px 14px;border:none;border-radius:6px;
            font-size:13px;cursor:pointer;color:#fff;
            background:${bg};font-weight:600;
            transition:all 0.15s;outline:none;
        `;
    b.onmouseenter = () => {
      b.style.opacity = "0.85";
    };
    b.onmouseleave = () => {
      b.style.opacity = "1";
    };
    return b;
  };
  const modePointsBtn = makeBtn(`${ICO.target} Points`, "Point Mode", "#444");
  const modeDrawBtn = makeBtn(`${ICO.brush} Draw`, "Draw Mode", "#444");
  const modeBoxBtn = makeBtn(`${ICO.box} Box`, "Box Mode", "#444");
  const modeNudgeBtn = makeBtn(`${ICO.nudge} Nudge`, "Nudge Mode", "#444");
  const modeSmartBtn = makeBtn(`${ICO.bolt} Smart`, "Smart Draw", "#444");
  const modeBtns = [modePointsBtn, modeDrawBtn, modeBoxBtn, modeNudgeBtn, modeSmartBtn];
  modeBtns.forEach((b) => {
    b.style.padding = "6px 8px";
    b.style.fontSize = "12px";
  });
  const clearBtn = makeBtn(`${ICO.trash} Clear`, "Clear All", "#555");
  const applyBtn = makeBtn(`${ICO.check} Apply`, "Apply", "#2a7a2a");
  const cancelBtn = makeBtn("Cancel", "Cancel", "#7a2a2a");
  modeBtns.forEach((b) => btnBar.appendChild(b));
  btnBar.appendChild(clearBtn);
  btnBar.appendChild(applyBtn);
  btnBar.appendChild(cancelBtn);
  overlay.appendChild(btnBar);
  overlay.tabIndex = -1;
  document.body.appendChild(overlay);
  overlay.focus();
  let pts = existing.points ? [...existing.points] : [];
  let lbls = existing.labels ? [...existing.labels] : [];
  let imgW = 0;
  let imgH = 0;
  let scaleX = 1;
  let scaleY = 1;
  const firstImg = new Image();
  const maskOff = document.createElement("canvas");
  let maskDirty = false;
  let _greenOverlay = null;
  let _greenOverlayDirty = true;
  const _MODE_COLORS = {
    points: "#3a5a8a",
    draw: "#5a3a8a",
    box: "#8a5a3a",
    nudge: "#3a8a5a",
    smart: "#3a6a8a"
  };
  const _MODE_BTNS = [
    ["points", modePointsBtn],
    ["draw", modeDrawBtn],
    ["box", modeBoxBtn],
    ["nudge", modeNudgeBtn],
    ["smart", modeSmartBtn]
  ];
  let _boxDragging = false;
  let _boxStart = null;
  let _boxEnd = null;
  let _nudgeBaked = false;
  let _rawMaskImg = null;
  let _edgeMapData = null;
  let _edgeMapLoading = false;
  let _edgeMapOff = null;
  let _pointOverlay = null;
  let _pointOverlayDirty = true;
  let _fetchTimer = null;
  const debouncedFetchMask = () => {
    if (_fetchTimer) clearTimeout(_fetchTimer);
    _fetchTimer = setTimeout(() => {
      if (mode !== "points" && mode !== "box" || pts.length === 0 && !_boxEnd) return;
      if (!_framePath) return;
      const body = { frame_path: _framePath, edge_refine: edgeRefineToggle.cb.checked };
      if (mode === "points") {
        body.points = pts;
        body.labels = lbls;
        body.multi_object = multiObjToggle.cb.checked;
      } else if (mode === "box") {
        const bs = _boxStart;
        const be = _boxEnd;
        if (bs && be) {
          body.box = [
            Math.round(Math.min(bs.x, be.x) * scaleX),
            Math.round(Math.min(bs.y, be.y) * scaleY),
            Math.round(Math.max(bs.x, be.x) * scaleX),
            Math.round(Math.max(bs.y, be.y) * scaleY)
          ];
        }
      }
      _sam3Loading = true;
      updateHeader();
      fetch("/ffmpega/sam3_point_mask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then((r) => r.json()).then((data) => {
        if (!data.mask_b64) {
          _sam3Loading = false;
          updateHeader();
          return;
        }
        if (data.raw_mask_b64) {
          const rawImg = new Image();
          rawImg.onload = () => {
            _rawMaskImg = rawImg;
          };
          rawImg.src = "data:image/png;base64," + data.raw_mask_b64;
        }
        const overlayImg = new Image();
        overlayImg.onload = () => {
          _sam3Loading = false;
          updateHeader();
          _pointOverlay = document.createElement("canvas");
          _pointOverlay.width = canvas.width;
          _pointOverlay.height = canvas.height;
          const pCtx = _pointOverlay.getContext("2d");
          if (pCtx) {
            pCtx.globalAlpha = 0.85;
            pCtx.drawImage(overlayImg, 0, 0, canvas.width, canvas.height);
            pCtx.globalAlpha = 1;
          }
          _pointOverlayDirty = false;
          redraw();
        };
        overlayImg.src = "data:image/png;base64," + data.mask_b64;
      }).catch(() => {
        _sam3Loading = false;
        updateHeader();
      });
    }, 300);
  };
  const fetchEdgeMap = () => {
    if (_edgeMapLoading || _edgeMapData) return;
    if (!_framePath) return;
    _edgeMapLoading = true;
    fetch("/ffmpega/edge_map", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ frame_path: _framePath }) }).then((r) => r.json()).then((data) => {
      if (!data.edge_b64) return;
      const img = new Image();
      img.onload = () => {
        _edgeMapOff = document.createElement("canvas");
        _edgeMapOff.width = data.width || img.naturalWidth;
        _edgeMapOff.height = data.height || img.naturalHeight;
        const eCtx = _edgeMapOff.getContext("2d");
        if (eCtx) {
          eCtx.drawImage(img, 0, 0);
          _edgeMapData = eCtx.getImageData(0, 0, _edgeMapOff.width, _edgeMapOff.height);
        }
        _edgeMapLoading = false;
        redraw();
      };
      img.src = "data:image/png;base64," + data.edge_b64;
    }).catch(() => {
      _edgeMapLoading = false;
    });
  };
  const updateModeUI = () => {
    _MODE_BTNS.forEach(([m, btn]) => {
      btn.style.background = m === mode ? _MODE_COLORS[m] : "#444";
      btn.style.opacity = m === mode ? "1" : "0.6";
    });
    sliderWrap.style.display = mode === "draw" || mode === "nudge" || mode === "smart" ? "flex" : "none";
    canvas.style.cursor = mode === "draw" || mode === "nudge" || mode === "smart" ? "none" : "crosshair";
    smartClampToggle.wrap.style.display = mode === "smart" ? "flex" : "none";
    if (mode === "smart") fetchEdgeMap();
    if (mode === "nudge" && _rawMaskImg && _rawMaskImg.complete && !_nudgeBaked) {
      const mCtx = maskOff.getContext("2d");
      if (mCtx) {
        mCtx.drawImage(_rawMaskImg, 0, 0, maskOff.width, maskOff.height);
        _nudgeBaked = true;
        maskDirty = true;
        _greenOverlayDirty = true;
      }
    }
    updateHeader();
    redraw();
  };
  _MODE_BTNS.forEach(([m, btn]) => {
    btn.onclick = () => {
      mode = m;
      updateModeUI();
    };
  });
  const _undoStack = [];
  const _redoStack = [];
  const MAX_UNDO = 30;
  const snapshotMask = () => {
    const mCtx = maskOff.getContext("2d");
    if (!mCtx || !maskOff.width || !maskOff.height) return;
    _undoStack.push(mCtx.getImageData(0, 0, maskOff.width, maskOff.height));
    if (_undoStack.length > MAX_UNDO) _undoStack.shift();
    _redoStack.length = 0;
  };
  const undoMask = () => {
    if (!_undoStack.length) return;
    const mCtx = maskOff.getContext("2d");
    if (!mCtx) return;
    _redoStack.push(mCtx.getImageData(0, 0, maskOff.width, maskOff.height));
    mCtx.putImageData(_undoStack.pop(), 0, 0);
    maskDirty = true;
    _greenOverlayDirty = true;
    redraw();
  };
  const redoMask = () => {
    if (!_redoStack.length) return;
    const mCtx = maskOff.getContext("2d");
    if (!mCtx) return;
    _undoStack.push(mCtx.getImageData(0, 0, maskOff.width, maskOff.height));
    mCtx.putImageData(_redoStack.pop(), 0, 0);
    maskDirty = true;
    _greenOverlayDirty = true;
    redraw();
  };
  const redraw = () => {
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (firstImg.complete && firstImg.naturalWidth > 0) {
      ctx.drawImage(firstImg, 0, 0, canvas.width, canvas.height);
    }
    if (mode === "points" || mode === "box") {
      if (_pointOverlay && !_pointOverlayDirty) ctx.drawImage(_pointOverlay, 0, 0);
      if (mode === "points") {
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
        const bs = _boxStart;
        const be = _boxEnd;
        if (bs && be) {
          ctx.strokeStyle = "rgba(0,200,255,0.8)";
          ctx.lineWidth = 2;
          ctx.setLineDash([6, 3]);
          ctx.strokeRect(bs.x, bs.y, be.x - bs.x, be.y - bs.y);
          ctx.setLineDash([]);
        }
        statusBar.textContent = `Box mode | ${imgW}×${imgH}`;
      }
    } else {
      if (_greenOverlayDirty || !_greenOverlay) {
        _greenOverlay = document.createElement("canvas");
        _greenOverlay.width = canvas.width;
        _greenOverlay.height = canvas.height;
        const tmpCtx = _greenOverlay.getContext("2d");
        if (tmpCtx) {
          const expandVal = parseInt(expandCtrl.slider.value);
          const featherVal = parseInt(featherCtrl.slider.value);
          const invertVal = invertToggle.cb.checked;
          const totalBlur = (expandVal !== 0 ? Math.abs(expandVal) : 0) + featherVal;
          if (totalBlur > 0) tmpCtx.filter = `blur(${totalBlur}px)`;
          tmpCtx.drawImage(maskOff, 0, 0, canvas.width, canvas.height);
          tmpCtx.filter = "none";
          const imgData = tmpCtx.getImageData(0, 0, canvas.width, canvas.height);
          let thresh = 128;
          if (expandVal > 0) thresh = Math.max(2, 128 - expandVal * 3);
          else if (expandVal < 0) thresh = Math.min(253, 128 + Math.abs(expandVal) * 3);
          for (let i = 0; i < imgData.data.length; i += 4) {
            const val = imgData.data[i];
            const isMasked = featherVal > 0 && expandVal === 0 ? val > 2 : val > thresh;
            const showGreen = invertVal ? !isMasked : isMasked;
            if (showGreen) {
              imgData.data[i] = 0;
              imgData.data[i + 1] = 220;
              imgData.data[i + 2] = 80;
              imgData.data[i + 3] = featherVal > 0 ? Math.round(Math.min(120, (invertVal ? 255 - val : val) / 255 * 120)) : 100;
            } else {
              imgData.data[i + 3] = 0;
            }
          }
          tmpCtx.putImageData(imgData, 0, 0);
        }
        _greenOverlayDirty = false;
      }
      ctx.drawImage(_greenOverlay, 0, 0);
      if (mode === "smart" && _edgeMapOff) {
        ctx.save();
        ctx.globalAlpha = 0.15;
        ctx.drawImage(_edgeMapOff, 0, 0, canvas.width, canvas.height);
        ctx.restore();
      }
      const activeSettings = [];
      const ev = parseInt(expandCtrl.slider.value);
      const fv = parseInt(featherCtrl.slider.value);
      if (ev !== 0) activeSettings.push(`${ev > 0 ? "+" : ""}${ev}px expand`);
      if (fv > 0) activeSettings.push(`${fv}px feather`);
      if (invertToggle.cb.checked) activeSettings.push("inverted");
      const settingsStr = activeSettings.length > 0 ? ` | ${activeSettings.join(", ")}` : "";
      const modeName = mode === "smart" ? `Smart (${_smartClamp ? "Clamp" : "Attract"})` : mode.charAt(0).toUpperCase() + mode.slice(1);
      statusBar.textContent = `${modeName} mode | ${imgW}×${imgH} | Brush: ${sizeSlider.value}px${settingsStr}`;
    }
  };
  const fitCanvas = (w, h) => {
    imgW = w;
    imgH = h;
    const maxW = window.innerWidth * 0.9;
    const maxH = window.innerHeight * 0.75;
    let dispW = imgW;
    let dispH = imgH;
    if (dispW > maxW) {
      const r = maxW / dispW;
      dispW *= r;
      dispH *= r;
    }
    if (dispH > maxH) {
      const r = maxH / dispH;
      dispW *= r;
      dispH *= r;
    }
    canvas.width = Math.round(dispW);
    canvas.height = Math.round(dispH);
    scaleX = imgW / canvas.width;
    scaleY = imgH / canvas.height;
    fitToView();
    maskOff.width = imgW;
    maskOff.height = imgH;
    const mCtx = maskOff.getContext("2d");
    if (mCtx) {
      mCtx.fillStyle = "#000";
      mCtx.fillRect(0, 0, imgW, imgH);
    }
    if (existing.mask_data && existing.mode === "draw") {
      const maskImg = new Image();
      maskImg.onload = () => {
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
  firstImg.onload = () => {
    fitCanvas(firstImg.naturalWidth, firstImg.naturalHeight);
    updateModeUI();
    redraw();
  };
  firstImg.onerror = () => {
    statusBar.textContent = "Failed to load image";
    statusBar.style.color = "#f44";
  };
  firstImg.crossOrigin = "anonymous";
  firstImg.src = imgSrc;
  let isDrawing = false;
  let drawButton = -1;
  let lastDrawX = -1;
  let lastDrawY = -1;
  const paintOnMask = (canvasX, canvasY, erase) => {
    const mCtx = maskOff.getContext("2d");
    if (!mCtx) return;
    const mx = canvasX * scaleX;
    const my = canvasY * scaleY;
    const brushR = parseInt(sizeSlider.value) * scaleX;
    mCtx.beginPath();
    mCtx.arc(mx, my, brushR, 0, Math.PI * 2);
    mCtx.fillStyle = erase ? "#000" : "#fff";
    mCtx.fill();
    maskDirty = true;
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
            canvasX - dispBrushR,
            canvasY - dispBrushR,
            dispBrushR * 2,
            dispBrushR * 2
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
  const paintLine = (x1, y1, x2, y2, erase) => {
    const dist = Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);
    const steps = Math.max(1, Math.floor(dist / 3));
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      const x = x1 + (x2 - x1) * t;
      const y = y1 + (y2 - y1) * t;
      paintOnMask(x, y, erase);
    }
  };
  const getCanvasPos = (e) => {
    const rect = canvas.getBoundingClientRect();
    const cssScaleX = canvas.width / rect.width;
    const cssScaleY = canvas.height / rect.height;
    return {
      x: (e.clientX - rect.left) * cssScaleX,
      y: (e.clientY - rect.top) * cssScaleY
    };
  };
  const findNearPoint = (mx, my) => {
    for (let i = 0; i < pts.length; i++) {
      const dx = pts[i][0] / scaleX - mx;
      const dy = pts[i][1] / scaleY - my;
      if (Math.sqrt(dx * dx + dy * dy) < HIT_RADIUS) return i;
    }
    return -1;
  };
  const paintOnMaskSmart = (canvasX, canvasY, erase) => {
    if (!_edgeMapData) {
      paintOnMask(canvasX, canvasY, erase);
      return;
    }
    const mCtx = maskOff.getContext("2d");
    if (!mCtx) return;
    const R = parseInt(sizeSlider.value) * scaleX;
    const cx = Math.round(canvasX * scaleX);
    const cy = Math.round(canvasY * scaleY);
    const edgeW = _edgeMapData.width;
    const fillVal = erase ? 0 : 255;
    const maskData = mCtx.getImageData(
      Math.max(0, cx - R),
      Math.max(0, cy - R),
      Math.min(maskOff.width, cx + R) - Math.max(0, cx - R),
      Math.min(maskOff.height, cy + R) - Math.max(0, cy - R)
    );
    const ox = Math.max(0, cx - R);
    const oy = Math.max(0, cy - R);
    for (let py = 0; py < maskData.height; py++) {
      for (let px = 0; px < maskData.width; px++) {
        const imgX = ox + px;
        const imgY = oy + py;
        const dx = imgX - cx;
        const dy = imgY - cy;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist > R) continue;
        if (_smartClamp) {
          let blocked = false;
          const steps = Math.max(1, Math.floor(dist / 2));
          for (let s = 0; s <= steps; s++) {
            const sx = Math.round(cx + dx * (s / steps));
            const sy = Math.round(cy + dy * (s / steps));
            if (sx >= 0 && sx < edgeW && sy >= 0 && sy < _edgeMapData.height) {
              if (_edgeMapData.data[(sy * edgeW + sx) * 4] > 128) {
                blocked = true;
                break;
              }
            }
          }
          if (blocked) continue;
        } else {
          if (imgX >= 0 && imgX < edgeW && imgY >= 0 && imgY < _edgeMapData.height) {
            const edgeVal = _edgeMapData.data[(imgY * edgeW + imgX) * 4];
            if (edgeVal > 128) {
              const idx2 = (py * maskData.width + px) * 4;
              maskData.data[idx2] = maskData.data[idx2 + 1] = maskData.data[idx2 + 2] = fillVal;
              maskData.data[idx2 + 3] = 255;
              continue;
            }
          }
        }
        const idx = (py * maskData.width + px) * 4;
        maskData.data[idx] = maskData.data[idx + 1] = maskData.data[idx + 2] = fillVal;
        maskData.data[idx + 3] = 255;
      }
    }
    mCtx.putImageData(maskData, ox, oy);
    maskDirty = true;
    _greenOverlayDirty = true;
  };
  const paintLineSmart = (x1, y1, x2, y2, erase) => {
    const dist = Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);
    const steps = Math.max(1, Math.floor(dist / 3));
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      paintOnMaskSmart(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, erase);
    }
  };
  canvas.addEventListener("mousedown", (e) => {
    if (mode === "draw" || mode === "nudge" || mode === "smart") {
      e.preventDefault();
      if (mode === "nudge" && !_nudgeBaked && _rawMaskImg && _rawMaskImg.complete) {
        snapshotMask();
        const mCtx = maskOff.getContext("2d");
        if (mCtx) {
          mCtx.drawImage(_rawMaskImg, 0, 0, maskOff.width, maskOff.height);
          _nudgeBaked = true;
          maskDirty = true;
        }
      }
      snapshotMask();
      isDrawing = true;
      drawButton = e.button;
      const pos = getCanvasPos(e);
      lastDrawX = pos.x;
      lastDrawY = pos.y;
      if (mode === "smart") paintOnMaskSmart(pos.x, pos.y, e.button === 2);
      else paintOnMask(pos.x, pos.y, e.button === 2);
      redraw();
    } else if (mode === "box") {
      e.preventDefault();
      _boxDragging = true;
      _boxStart = getCanvasPos(e);
      _boxEnd = _boxStart;
      redraw();
    }
  });
  canvas.addEventListener("mousemove", (e) => {
    if (mode === "box" && _boxDragging) {
      _boxEnd = getCanvasPos(e);
      redraw();
      return;
    }
    if (mode === "draw" || mode === "nudge" || mode === "smart") {
      const pos = getCanvasPos(e);
      if (isDrawing) {
        if (mode === "smart") paintLineSmart(lastDrawX, lastDrawY, pos.x, pos.y, drawButton === 2);
        else paintLine(lastDrawX, lastDrawY, pos.x, pos.y, drawButton === 2);
        lastDrawX = pos.x;
        lastDrawY = pos.y;
      }
      redraw();
      const ctx = canvas.getContext("2d");
      if (ctx) {
        const brushR = parseInt(sizeSlider.value);
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, brushR, 0, Math.PI * 2);
        const color = mode === "smart" ? "rgba(0,255,255," : isDrawing && drawButton === 2 ? "rgba(255,80,80," : "rgba(80,255,120,";
        ctx.strokeStyle = color + (isDrawing ? "0.7)" : "0.4)");
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    }
  });
  const stopDrawing = () => {
    if (isDrawing) {
      _greenOverlayDirty = true;
      redraw();
    }
    isDrawing = false;
    drawButton = -1;
    lastDrawX = -1;
    lastDrawY = -1;
  };
  canvas.addEventListener("mouseup", (e) => {
    if (mode === "box" && _boxDragging && _boxStart && _boxEnd) {
      _boxDragging = false;
      debouncedFetchMask();
      redraw();
      return;
    }
    stopDrawing();
  });
  canvas.addEventListener("mouseleave", () => {
    if (mode === "box") {
      _boxDragging = false;
    }
    stopDrawing();
    if (mode === "draw" || mode === "nudge" || mode === "smart") redraw();
  });
  canvas.addEventListener("click", (e) => {
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
    debouncedFetchMask();
  });
  canvas.addEventListener("contextmenu", (e) => {
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
    debouncedFetchMask();
  });
  overlay.addEventListener("contextmenu", (e) => e.preventDefault());
  clearBtn.onclick = () => {
    if (mode === "points" || mode === "box") {
      pts.length = 0;
      lbls.length = 0;
      _boxStart = null;
      _boxEnd = null;
      _pointOverlay = null;
      _pointOverlayDirty = true;
      _rawMaskImg = null;
    } else {
      const mCtx = maskOff.getContext("2d");
      if (mCtx) {
        mCtx.fillStyle = "#000";
        mCtx.fillRect(0, 0, maskOff.width, maskOff.height);
      }
      maskDirty = false;
      _greenOverlayDirty = true;
      _nudgeBaked = false;
      if (mode === "smart") {
        _edgeMapData = null;
        _edgeMapOff = null;
        _edgeMapLoading = false;
      }
    }
    _undoStack.length = 0;
    _redoStack.length = 0;
    redraw();
  };
  cancelBtn.onclick = () => {
    document.removeEventListener("keydown", keyHandler);
    overlay.remove();
  };
  applyBtn.onclick = () => {
    const common = {
      image_width: imgW,
      image_height: imgH,
      mask_expand: parseInt(expandCtrl.slider.value),
      mask_feather: parseInt(featherCtrl.slider.value),
      mask_invert: invertToggle.cb.checked,
      mask_threshold: parseInt(threshCtrl.slider.value) / 100,
      mask_multi_object: multiObjToggle.cb.checked,
      mask_edge_refine: edgeRefineToggle.cb.checked
    };
    let data;
    if ((mode === "draw" || mode === "nudge" || mode === "smart") && maskDirty) {
      const b64 = maskOff.toDataURL("image/png").split(",")[1];
      data = JSON.stringify({ mode: "draw", mask_data: b64, ...common });
    } else if (mode === "box" && _boxStart && _boxEnd) {
      const bs = _boxStart;
      const be = _boxEnd;
      data = JSON.stringify({ mode: "box", box: [
        Math.round(Math.min(bs.x, be.x) * scaleX),
        Math.round(Math.min(bs.y, be.y) * scaleY),
        Math.round(Math.max(bs.x, be.x) * scaleX),
        Math.round(Math.max(bs.y, be.y) * scaleY)
      ], points: pts, labels: lbls, ...common });
    } else {
      data = JSON.stringify({ mode: "points", points: pts, labels: lbls, ...common });
    }
    if (mpWidget) {
      mpWidget.value = data;
    } else {
      const w = node.addWidget("text", "mask_points_data", data, () => {
      }, { serialize: true });
      w.type = "text";
      if (w.computeSize) w.computeSize = () => [0, -4];
    }
    node.setDirtyCanvas(true, true);
    document.removeEventListener("keydown", keyHandler);
    overlay.remove();
    flashNode(node, "#2a7a2a");
  };
  const keyHandler = (e) => {
    if (e.key === "Escape") {
      overlay.remove();
      document.removeEventListener("keydown", keyHandler);
    }
    if (e.key === "z" && (e.ctrlKey || e.metaKey) && !e.shiftKey) {
      e.preventDefault();
      undoMask();
    }
    if (e.key === "z" && (e.ctrlKey || e.metaKey) && e.shiftKey || e.key === "y" && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      redoMask();
    }
    if (e.key === "f" && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
      e.preventDefault();
      fitToView();
    }
  };
  document.addEventListener("keydown", keyHandler);
}
export {
  openPointSelector as o
};
