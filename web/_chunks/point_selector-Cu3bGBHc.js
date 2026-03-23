import { f as flashNode } from "./ui_helpers-CvUDB6-L.js";
const HIT_RADIUS = 20;
function openPointSelector(node, imgSrc, _videoSrc) {
  var _a, _b;
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
  const header = document.createElement("div");
  header.style.cssText = `
        color:#eee;font-size:14px;margin-bottom:8px;
        display:flex;gap:16px;align-items:center;
    `;
  overlay.appendChild(header);
  const updateHeader = () => {
    if (mode === "points") {
      header.innerHTML = `
                <span><span aria-hidden="true">🎯</span> <b>Point Mode</b></span>
                <span style="color:#4f4"><span aria-hidden="true">⬤</span> Left-click = Include</span>
                <span style="color:#f44"><span aria-hidden="true">⬤</span> Right-click = Exclude</span>
                <span style="color:#888">Click existing point to remove</span>
            `;
    } else {
      header.innerHTML = `
                <span><span aria-hidden="true">🖌</span> <b>Draw Mode</b></span>
                <span style="color:#4f4"><span aria-hidden="true">⬤</span> Left-drag = Paint</span>
                <span style="color:#f44"><span aria-hidden="true">⬤</span> Right-drag = Erase</span>
            `;
    }
  };
  updateHeader();
  const canvasWrap = document.createElement("div");
  canvasWrap.style.cssText = "position:relative;max-width:90vw;max-height:75vh;";
  const canvas = document.createElement("canvas");
  canvas.style.cssText = "max-width:90vw;max-height:75vh;cursor:crosshair;display:block;";
  canvasWrap.appendChild(canvas);
  overlay.appendChild(canvasWrap);
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
  settingsPanel.append(
    expandCtrl.wrap,
    featherCtrl.wrap,
    threshCtrl.wrap,
    invertToggle.wrap,
    multiObjToggle.wrap,
    resetBtn
  );
  overlay.appendChild(settingsPanel);
  const onSettingsChanged = () => {
    _greenOverlayDirty = true;
    redraw();
  };
  expandCtrl.slider.addEventListener("input", onSettingsChanged);
  featherCtrl.slider.addEventListener("input", onSettingsChanged);
  threshCtrl.slider.addEventListener("input", onSettingsChanged);
  invertToggle.cb.addEventListener("change", onSettingsChanged);
  multiObjToggle.cb.addEventListener("change", onSettingsChanged);
  const btnBar = document.createElement("div");
  btnBar.style.cssText = "display:flex;gap:12px;margin-top:12px;";
  const makeBtn = (htmlLabel, ariaLabel, bg) => {
    const b = document.createElement("button");
    b.innerHTML = htmlLabel;
    if (ariaLabel) {
      b.setAttribute("aria-label", ariaLabel);
    }
    b.style.cssText = `
            padding:8px 24px;border:none;border-radius:6px;
            font-size:14px;cursor:pointer;color:#fff;
            background:${bg};font-weight:600;
            transition:opacity 0.15s;
            outline: none;
        `;
    let isHovered = false;
    let isFocused = false;
    const update = () => {
      const active = isHovered || isFocused;
      b.style.opacity = active ? "0.85" : "1";
      b.style.outline = isFocused ? "2px solid #fff" : "none";
      b.style.outlineOffset = isFocused ? "2px" : "0px";
    };
    b.onmouseenter = () => {
      isHovered = true;
      update();
    };
    b.onmouseleave = () => {
      isHovered = false;
      update();
    };
    b.onfocus = () => {
      isFocused = true;
      update();
    };
    b.onblur = () => {
      isFocused = false;
      update();
    };
    return b;
  };
  const modeToggle = makeBtn(`<span aria-hidden="true">🖌</span> Draw`, "Draw Mode", "#3a5a8a");
  const clearBtn = makeBtn("Clear All", "Clear All", "#555");
  const applyBtn = makeBtn(`<span aria-hidden="true">✓</span> Apply`, "Apply", "#2a7a2a");
  const cancelBtn = makeBtn("Cancel", "Cancel", "#7a2a2a");
  btnBar.appendChild(modeToggle);
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
  const updateModeUI = () => {
    if (mode === "points") {
      modeToggle.innerHTML = `<span aria-hidden="true">🖌</span> Draw`;
      modeToggle.setAttribute("aria-label", "Draw Mode");
      modeToggle.style.background = "#3a5a8a";
      canvas.style.cursor = "crosshair";
      sliderWrap.style.display = "none";
    } else {
      modeToggle.innerHTML = `<span aria-hidden="true">🎯</span> Points`;
      modeToggle.setAttribute("aria-label", "Point Mode");
      modeToggle.style.background = "#5a3a8a";
      canvas.style.cursor = "none";
      sliderWrap.style.display = "flex";
    }
    updateHeader();
    redraw();
  };
  modeToggle.onclick = () => {
    mode = mode === "points" ? "draw" : "points";
    updateModeUI();
  };
  const redraw = () => {
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (firstImg.complete && firstImg.naturalWidth > 0) {
      ctx.drawImage(firstImg, 0, 0, canvas.width, canvas.height);
    }
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
          if (totalBlur > 0) {
            tmpCtx.filter = `blur(${totalBlur}px)`;
          }
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
              if (featherVal > 0) {
                const alphaVal = invertVal ? 255 - val : val;
                imgData.data[i + 3] = Math.round(
                  Math.min(120, alphaVal / 255 * 120)
                );
              } else {
                imgData.data[i + 3] = 100;
              }
            } else {
              imgData.data[i + 3] = 0;
            }
          }
          tmpCtx.putImageData(imgData, 0, 0);
        }
        _greenOverlayDirty = false;
      }
      ctx.drawImage(_greenOverlay, 0, 0);
      const activeSettings = [];
      const ev = parseInt(expandCtrl.slider.value);
      const fv = parseInt(featherCtrl.slider.value);
      if (ev !== 0) activeSettings.push(`${ev > 0 ? "+" : ""}${ev}px expand`);
      if (fv > 0) activeSettings.push(`${fv}px feather`);
      if (invertToggle.cb.checked) activeSettings.push("inverted");
      const settingsStr = activeSettings.length > 0 ? ` | ${activeSettings.join(", ")}` : "";
      statusBar.textContent = `Draw mode | ${imgW}×${imgH} | Brush: ${sizeSlider.value}px${settingsStr}`;
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
  canvas.addEventListener("mousedown", (e) => {
    if (mode === "draw") {
      e.preventDefault();
      isDrawing = true;
      drawButton = e.button;
      const pos = getCanvasPos(e);
      lastDrawX = pos.x;
      lastDrawY = pos.y;
      paintOnMask(pos.x, pos.y, e.button === 2);
      redraw();
      const ctx = canvas.getContext("2d");
      if (ctx) {
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, parseInt(sizeSlider.value), 0, Math.PI * 2);
        ctx.strokeStyle = e.button === 2 ? "rgba(255,80,80,0.7)" : "rgba(80,255,120,0.7)";
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    }
  });
  canvas.addEventListener("mousemove", (e) => {
    if (mode === "draw") {
      const pos = getCanvasPos(e);
      if (isDrawing) {
        paintLine(lastDrawX, lastDrawY, pos.x, pos.y, drawButton === 2);
        lastDrawX = pos.x;
        lastDrawY = pos.y;
        redraw();
      }
      const ctx = canvas.getContext("2d");
      if (ctx) {
        const brushR = parseInt(sizeSlider.value);
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, brushR, 0, Math.PI * 2);
        ctx.strokeStyle = isDrawing ? drawButton === 2 ? "rgba(255,80,80,0.7)" : "rgba(80,255,120,0.7)" : "rgba(255,255,255,0.5)";
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
  canvas.addEventListener("mouseup", stopDrawing);
  canvas.addEventListener("mouseleave", () => {
    stopDrawing();
    if (mode === "draw") redraw();
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
  });
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) {
      document.removeEventListener("keydown", keyHandler);
      overlay.remove();
    }
  });
  overlay.addEventListener("contextmenu", (e) => e.preventDefault());
  clearBtn.onclick = () => {
    if (mode === "points") {
      pts.length = 0;
      lbls.length = 0;
    } else {
      const mCtx = maskOff.getContext("2d");
      if (mCtx) {
        mCtx.fillStyle = "#000";
        mCtx.fillRect(0, 0, maskOff.width, maskOff.height);
      }
      maskDirty = false;
      _greenOverlayDirty = true;
    }
    redraw();
  };
  cancelBtn.onclick = () => {
    document.removeEventListener("keydown", keyHandler);
    overlay.remove();
  };
  applyBtn.onclick = () => {
    let data;
    if (mode === "draw" && maskDirty) {
      const maskDataUrl = maskOff.toDataURL("image/png");
      const b64 = maskDataUrl.split(",")[1];
      data = JSON.stringify({
        mode: "draw",
        mask_data: b64,
        image_width: imgW,
        image_height: imgH,
        mask_expand: parseInt(expandCtrl.slider.value),
        mask_feather: parseInt(featherCtrl.slider.value),
        mask_invert: invertToggle.cb.checked,
        mask_threshold: parseInt(threshCtrl.slider.value) / 100,
        mask_multi_object: multiObjToggle.cb.checked
      });
    } else {
      data = JSON.stringify({
        mode: "points",
        points: pts,
        labels: lbls,
        image_width: imgW,
        image_height: imgH,
        mask_expand: parseInt(expandCtrl.slider.value),
        mask_feather: parseInt(featherCtrl.slider.value),
        mask_invert: invertToggle.cb.checked,
        mask_threshold: parseInt(threshCtrl.slider.value) / 100,
        mask_multi_object: multiObjToggle.cb.checked
      });
    }
    if (mpWidget) {
      mpWidget.value = data;
    } else {
      const w = node.addWidget(
        "text",
        "mask_points_data",
        data,
        () => {
        },
        { serialize: true }
      );
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
  };
  document.addEventListener("keydown", keyHandler);
}
export {
  openPointSelector as o
};
