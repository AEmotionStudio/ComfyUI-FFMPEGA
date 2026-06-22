import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { c as cssText } from "./_chunks/loadlast-dy_0sOyd.js";
import { C as CropOverlay } from "./_chunks/CropOverlay-H6yQHaMz.js";
import { o as openPointSelector } from "./_chunks/point_selector-WUrkBg7b.js";
import { f as flashNode } from "./_chunks/ui_helpers-CvUDB6-L.js";
import { i as iconImage, a as iconGrid, b as iconColumns, c as iconInvert, d as iconWand, e as iconArrowLeftRight, f as iconSun, g as iconLayers, h as iconCrop, j as iconScaling, k as iconRotateCW, l as iconExpand, m as iconPalette, n as iconReset, o as iconCircleCheck, p as iconCheck, q as iconLock, r as iconFlip, s as iconFlipVertical, t as iconPin } from "./_chunks/icons-BOh8YpxI.js";
if (!document.getElementById("loadlast-styles")) {
  const style = document.createElement("style");
  style.id = "loadlast-styles";
  style.textContent = cssText;
  document.head.appendChild(style);
}
if (!document.getElementById("loadlast-image-styles")) {
  const style = document.createElement("style");
  style.id = "loadlast-image-styles";
  style.textContent = `
        .ll_img_preview {
            width: 100%;
            display: block;
            background: #111;
            min-height: 60px;
            object-fit: contain;
        }
        .ll_img_preview.loading {
            opacity: 0.5;
        }
        .ll_thumb img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            pointer-events: none;
        }
        .ll_pin_badge {
            position: absolute;
            top: 2px;
            right: 3px;
            background: rgba(255, 200, 0, 0.9);
            color: #000;
            font: bold 8px/1 monospace;
            padding: 1px 3px;
            border-radius: 3px;
            pointer-events: none;
            z-index: 2;
        }
        .ll_toolbar_spacer {
            flex: 1;
        }
        .ll_comparison_container {
            position: relative;
            width: 100%;
            overflow: hidden;
            cursor: col-resize;
        }
        .ll_comparison_divider {
            position: absolute;
            top: 0;
            bottom: 0;
            width: 3px;
            background: #00ddff;
            cursor: col-resize;
            z-index: 5;
            box-shadow: 0 0 6px rgba(0, 221, 255, 0.6);
        }
        .ll_comparison_divider::after {
            content: '◀ ▶';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0, 221, 255, 0.9);
            color: #000;
            font: bold 10px/1 monospace;
            padding: 4px 6px;
            border-radius: 10px;
            white-space: nowrap;
            letter-spacing: 2px;
        }
        .ll_comparison_label {
            position: absolute;
            top: 6px;
            background: rgba(0, 0, 0, 0.7);
            color: #ccc;
            font: 11px/1 monospace;
            padding: 3px 8px;
            border-radius: 4px;
            z-index: 4;
            pointer-events: none;
        }
        .ll_comparison_label.left { left: 6px; }
        .ll_comparison_label.right { right: 6px; }
        .ll_diff_controls {
            display: flex;
            gap: 4px;
            padding: 4px 8px;
            background: #111;
            border-top: 1px solid #222;
            align-items: center;
        }
        .ll_diff_btn {
            border: 1px solid #555;
            background: #222;
            color: #aaa;
            font-size: 11px;
            padding: 3px 8px;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.15s;
        }
        .ll_diff_btn:hover { background: #333; color: #fff; }
        .ll_diff_btn.active {
            background: rgba(0, 200, 255, 0.15);
            border-color: rgba(0, 200, 255, 0.4);
            color: #0cf;
        }
        /* ─── Edit mode styles ──────────────────────── */
        .ll_edit_area {
            position: relative;
            background: #111;
        }
        .ll_edit_toolbar_row {
            display: flex;
            align-items: center;
            gap: 4px;
            padding: 4px 8px;
            background: #111;
            border-top: 1px solid #222;
            flex-wrap: wrap;
        }
        .ll_edit_tool_btn {
            border: 1px solid #555;
            background: #222;
            color: #aaa;
            font-size: 11px;
            padding: 4px 8px;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.15s;
        }
        .ll_edit_tool_btn:hover { background: #333; color: #fff; }
        .ll_edit_tool_btn.active {
            background: rgba(0, 200, 255, 0.15);
            border-color: rgba(0, 200, 255, 0.4);
            color: #0cf;
        }
        .ll_edit_panel {
            padding: 6px 8px;
            background: #0f0f0f;
            border-top: 1px solid #222;
            display: none;
        }
        .ll_edit_panel.visible { display: block; }
        .ll_edit_panel_row {
            display: flex;
            align-items: center;
            gap: 6px;
            margin: 3px 0;
        }
        .ll_edit_panel_label {
            color: #888;
            font: 11px/1 monospace;
            width: 65px;
            flex-shrink: 0;
        }
        .ll_edit_panel_input {
            background: #1a1a1a;
            border: 1px solid #444;
            color: #ddd;
            font: 12px/1.2 monospace;
            padding: 3px 6px;
            border-radius: 3px;
            width: 60px;
        }
        .ll_edit_panel_input:focus {
            border-color: #0cf;
            outline: none;
        }
        .ll_edit_slider_row {
            display: flex;
            align-items: center;
            gap: 6px;
            margin: 3px 0;
        }
        .ll_edit_slider {
            flex: 1;
            height: 4px;
            accent-color: #00ddff;
            cursor: pointer;
        }
        .ll_edit_slider_val {
            color: #aaa;
            font: 11px/1 monospace;
            width: 35px;
            text-align: right;
        }
        .ll_edit_apply_btn {
            border: 1px solid #4ade80;
            background: transparent;
            color: #4ade80;
            font-size: 12px;
            padding: 5px 14px;
            border-radius: 4px;
            cursor: pointer;
            margin-left: auto;
            transition: all 0.15s;
        }
        .ll_edit_apply_btn:hover {
            background: #4ade80;
            color: #000;
        }
    `;
  document.head.appendChild(style);
}
function makeDefaultEditState() {
  return {
    crop_rect: null,
    resize: null,
    rotation: 0,
    flip: "",
    padding: null,
    brightness: 1,
    contrast: 1,
    saturation: 1
  };
}
const TOOLBAR_BUTTONS = [
  { id: "single", icon: iconImage, tip: "Single image" },
  { id: "grid", icon: iconGrid, tip: "Grid view" },
  { id: "sidebyside", icon: iconColumns, tip: "Side by side" },
  { id: "diff", icon: iconInvert, tip: "Diff view" },
  { id: "edit", icon: iconWand, tip: "Edit image" }
];
function buildViewURL(entry) {
  const params = new URLSearchParams({
    filename: entry.filename,
    subfolder: entry.subfolder,
    type: entry.type
  });
  return api.apiURL(`/view?${params.toString()}`);
}
function loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`Failed to load: ${url}`));
    img.src = url;
  });
}
const RESIZE_WIDGETS = [
  "resize_width",
  "resize_height",
  "upscale_method",
  "keep_proportion",
  "pad_color",
  "crop_position",
  "divisible_by",
  "resize_device"
];
function toggleWidget(widget, show) {
  if (!widget) return;
  if (!widget._origType) {
    widget._origType = widget.type;
    widget._origComputeSize = widget.computeSize;
  }
  if (show) {
    widget.type = widget._origType;
    widget.computeSize = widget._origComputeSize;
    widget.hidden = false;
    if (widget.element) widget.element.hidden = false;
  } else {
    widget.type = "hidden";
    widget.computeSize = () => [0, -4];
    widget.hidden = true;
    if (widget.element) widget.element.hidden = true;
  }
}
function applyResizeVisibility(node) {
  var _a, _b, _c;
  const enableResize = (_a = node.widgets) == null ? void 0 : _a.find((w) => w.name === "enable_resize");
  const show = Boolean(enableResize == null ? void 0 : enableResize.value);
  for (const name of RESIZE_WIDGETS) {
    const w = (_b = node.widgets) == null ? void 0 : _b.find((ww) => ww.name === name);
    if (w) toggleWidget(w, show);
  }
  node.setSize([node.size[0], node.computeSize([node.size[0], node.size[1]])[1]]);
  (_c = node == null ? void 0 : node.graph) == null ? void 0 : _c.setDirtyCanvas(true);
}
app.registerExtension({
  name: "LoadLast.ImagePreview",
  beforeRegisterNodeDef(nodeType, nodeData, _app) {
    if ((nodeData == null ? void 0 : nodeData.name) !== "LoadLastImage") return;
    const origCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function() {
      var _a;
      origCreated == null ? void 0 : origCreated.apply(this, arguments);
      const node = this;
      let currentMode = "single";
      let diffMode = "slider";
      let currentEntry = null;
      let allImages = [];
      let selectedIndex = -1;
      let pollTimer = null;
      let sliderPos = 0.5;
      let editState = makeDefaultEditState();
      let editTool = null;
      let editWrapper = null;
      let editCropOverlay = null;
      let editImg = null;
      node.color = "#3a5a3a";
      node.bgcolor = "#2a4a2a";
      const enableResizeWidget = (_a = node.widgets) == null ? void 0 : _a.find((w) => w.name === "enable_resize");
      if (enableResizeWidget) {
        applyResizeVisibility(node);
        const origResizeCb = enableResizeWidget.callback;
        enableResizeWidget.callback = function(...args) {
          origResizeCb == null ? void 0 : origResizeCb.apply(this, args);
          applyResizeVisibility(node);
        };
        const origResizeConfigure = node.onConfigure;
        node.onConfigure = function(...args) {
          origResizeConfigure == null ? void 0 : origResizeConfigure.apply(this, args);
          applyResizeVisibility(node);
        };
      }
      const container = document.createElement("div");
      container.className = "ll_container";
      const toolbar = document.createElement("div");
      toolbar.className = "ll_toolbar";
      const buttons = [];
      for (const def of TOOLBAR_BUTTONS) {
        const btn = document.createElement("button");
        btn.innerHTML = def.icon;
        btn.title = def.tip;
        btn.dataset.mode = def.id;
        btn.className = "ll_toolbar_btn";
        if (def.id === "single") btn.classList.add("active");
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          switchMode(def.id);
        });
        buttons.push(btn);
        toolbar.appendChild(btn);
      }
      function highlightToolbar() {
        for (const btn of buttons) {
          btn.classList.toggle("active", btn.dataset.mode === currentMode);
        }
      }
      const imgEl = document.createElement("img");
      imgEl.className = "ll_img_preview loading";
      imgEl.alt = "Image preview";
      imgEl.draggable = false;
      imgEl.onload = () => {
        imgEl.classList.remove("loading");
        if (imgEl.naturalWidth && imgEl.naturalHeight) {
          const newAR = imgEl.naturalWidth / imgEl.naturalHeight;
          if (!previewWidget.aspectRatio || Math.abs(previewWidget.aspectRatio - newAR) > 0.01) {
            previewWidget.aspectRatio = newAR;
            fitNode();
          }
        }
      };
      imgEl.onerror = () => {
        imgEl.classList.remove("loading");
      };
      const canvasEl = document.createElement("canvas");
      canvasEl.className = "ll_canvas";
      canvasEl.style.display = "none";
      canvasEl.style.width = "100%";
      canvasEl.style.cursor = "default";
      const compContainer = document.createElement("div");
      compContainer.className = "ll_comparison_container";
      compContainer.style.display = "none";
      const compCanvasA = document.createElement("canvas");
      compCanvasA.style.cssText = "width:100%;display:block;";
      const compCanvasB = document.createElement("canvas");
      compCanvasB.style.cssText = "position:absolute;top:0;left:0;width:100%;height:100%;";
      const compDivider = document.createElement("div");
      compDivider.style.cssText = "position:absolute;top:0;width:1px;height:100%;background:rgba(255,255,255,0.5);pointer-events:none;z-index:5;";
      const compLabelA = document.createElement("div");
      compLabelA.className = "ll_comparison_label left";
      compLabelA.textContent = "A (Previous)";
      const compLabelB = document.createElement("div");
      compLabelB.className = "ll_comparison_label right";
      compLabelB.textContent = "B (Latest)";
      compContainer.append(compCanvasA, compCanvasB, compDivider, compLabelA, compLabelB);
      const updateCompSlider = () => {
        const w = compContainer.offsetWidth;
        const px = Math.round(sliderPos * w);
        compDivider.style.left = `${px}px`;
        compCanvasA.style.clipPath = `inset(0 ${w - px}px 0 0)`;
        compCanvasB.style.clipPath = `inset(0 0 0 ${px}px)`;
      };
      compContainer.addEventListener("mousemove", (e) => {
        const rect = compContainer.getBoundingClientRect();
        sliderPos = Math.max(0.01, Math.min(0.99, (e.clientX - rect.left) / rect.width));
        updateCompSlider();
      });
      const diffControls = document.createElement("div");
      diffControls.className = "ll_diff_controls";
      diffControls.style.display = "none";
      const diffModes = [
        { id: "slider", label: `${iconArrowLeftRight} Slider` },
        { id: "heatmap", label: `${iconSun} Heatmap` },
        { id: "overlay", label: `${iconLayers} Overlay` }
      ];
      const diffBtns = [];
      for (const dm of diffModes) {
        const btn = document.createElement("button");
        btn.className = "ll_diff_btn";
        btn.innerHTML = dm.label;
        btn.dataset.diffMode = dm.id;
        if (dm.id === diffMode) btn.classList.add("active");
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          diffMode = dm.id;
          for (const b of diffBtns) b.classList.toggle("active", b.dataset.diffMode === diffMode);
          renderCurrentMode();
        });
        diffBtns.push(btn);
        diffControls.appendChild(btn);
      }
      const sbsControls = document.createElement("div");
      sbsControls.className = "ll_diff_controls";
      sbsControls.style.display = "none";
      const sbsLabel = document.createElement("span");
      sbsLabel.style.cssText = "color:#888;font-size:11px;";
      sbsLabel.textContent = "Hover to compare  │  A = Previous  │  B = Latest";
      sbsControls.appendChild(sbsLabel);
      const infoEl = document.createElement("div");
      infoEl.className = "ll_info";
      infoEl.textContent = "No image loaded";
      const browserStrip = document.createElement("div");
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
          scrollTrack.style.display = allImages.length > 1 ? "block" : "none";
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
        scrollThumb.classList.add("dragging");
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
          scrollThumb.classList.remove("dragging");
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
      previewWidget.computeSize = function(width) {
        if (container.style.display === "none") return [width, 0];
        let chrome = 32 + 22 + (allImages.length > 1 ? 100 : 0);
        if (currentMode === "diff" || currentMode === "sidebyside") chrome += 30;
        if (currentMode === "edit") chrome += 250;
        if (this.aspectRatio) {
          const h = (node.size[0] - 20) / this.aspectRatio;
          return [width, Math.max(h, 80) + chrome];
        }
        return [width, 80 + chrome];
      };
      container.appendChild(toolbar);
      container.appendChild(imgEl);
      container.appendChild(canvasEl);
      container.appendChild(compContainer);
      container.appendChild(sbsControls);
      container.appendChild(diffControls);
      container.appendChild(infoEl);
      const stripWrapper = document.createElement("div");
      stripWrapper.className = "ll_strip_wrapper";
      stripWrapper.appendChild(browserStrip);
      stripWrapper.appendChild(scrollTrack);
      container.appendChild(stripWrapper);
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
      function switchMode(mode) {
        if (mode !== "edit") cleanupEditMode();
        currentMode = mode;
        highlightToolbar();
        imgEl.style.display = "none";
        canvasEl.style.display = "none";
        canvasEl.height = 0;
        compContainer.style.display = "none";
        diffControls.style.display = "none";
        sbsControls.style.display = "none";
        if (mode === "single") {
          imgEl.style.display = "block";
          updatePreview();
        } else if (mode === "grid") {
          canvasEl.style.display = "block";
          renderCurrentMode();
        } else if (mode === "sidebyside") {
          canvasEl.style.display = "block";
          sbsControls.style.display = "flex";
          renderCurrentMode();
        } else if (mode === "diff") {
          diffControls.style.display = "flex";
          if (diffMode === "slider") {
            compContainer.style.display = "block";
          } else {
            canvasEl.style.display = "block";
          }
          renderCurrentMode();
        } else if (mode === "edit") {
          buildEditMode();
        }
        fitNode();
      }
      function buildEditMode() {
        cleanupEditMode();
        editState = makeDefaultEditState();
        editTool = null;
        editWrapper = document.createElement("div");
        editWrapper.className = "ll_edit_wrapper";
        const editArea = document.createElement("div");
        editArea.className = "ll_edit_area";
        editImg = document.createElement("img");
        editImg.className = "ll_img_preview";
        editImg.draggable = false;
        if (currentEntry) editImg.src = buildViewURL(currentEntry);
        editArea.appendChild(editImg);
        editCropOverlay = new CropOverlay({
          onCropChanged: (rect) => {
            editState.crop_rect = rect;
            updateEditPreview();
          }
        });
        editArea.appendChild(editCropOverlay.canvasElement);
        editCropOverlay.canvasElement.style.display = "none";
        editWrapper.appendChild(editArea);
        const toolRow = document.createElement("div");
        toolRow.className = "ll_edit_toolbar_row";
        const tools = [
          { id: "crop", icon: iconCrop, label: "Crop" },
          { id: "resize", icon: iconScaling, label: "Resize" },
          { id: "rotate", icon: iconRotateCW, label: "Transform" },
          { id: "padding", icon: iconExpand, label: "Padding" },
          { id: "color", icon: iconPalette, label: "Color" }
        ];
        const toolBtns = [];
        for (const tool of tools) {
          const btn = document.createElement("button");
          btn.className = "ll_edit_tool_btn";
          btn.innerHTML = `${tool.icon} ${tool.label}`;
          btn.dataset.tool = tool.id;
          btn.addEventListener("click", (e) => {
            e.stopPropagation();
            const newTool = editTool === tool.id ? null : tool.id;
            editTool = newTool;
            for (const b of toolBtns) b.classList.toggle("active", b.dataset.tool === editTool);
            showEditPanel(editWrapper, tool.id, editTool !== null);
          });
          toolBtns.push(btn);
          toolRow.appendChild(btn);
        }
        const editSpacer = document.createElement("div");
        editSpacer.className = "ll_toolbar_spacer";
        toolRow.appendChild(editSpacer);
        const resetAllBtn = document.createElement("button");
        resetAllBtn.className = "ll_edit_tool_btn";
        resetAllBtn.innerHTML = `${iconReset} Reset All`;
        resetAllBtn.style.cssText = "border-color:#f87171;color:#f87171;";
        resetAllBtn.title = "Reset all edit settings to defaults";
        resetAllBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          editState = makeDefaultEditState();
          buildEditMode();
          postEditState();
          fitNode();
        });
        toolRow.appendChild(resetAllBtn);
        const applyBtn = document.createElement("button");
        applyBtn.className = "ll_edit_apply_btn";
        applyBtn.innerHTML = `${iconCircleCheck} Apply Edits`;
        applyBtn.addEventListener("click", () => {
          postEditState();
          applyBtn.innerHTML = `${iconCheck} Applied!`;
          applyBtn.style.background = "#4ade80";
          applyBtn.style.color = "#000";
          setTimeout(() => {
            applyBtn.innerHTML = `${iconCircleCheck} Apply Edits`;
            applyBtn.style.background = "";
            applyBtn.style.color = "#4ade80";
          }, 1200);
        });
        toolRow.appendChild(applyBtn);
        editWrapper.appendChild(toolRow);
        buildCropPanel(editWrapper, editImg);
        buildResizePanel(editWrapper, editImg);
        buildTransformPanel(editWrapper);
        buildPaddingPanel(editWrapper);
        buildColorPanel(editWrapper);
        container.insertBefore(editWrapper, stripWrapper);
        infoEl.textContent = currentEntry ? `Edit: ${currentEntry.filename}` : "Edit mode";
      }
      function showEditPanel(wrapper, toolId, show) {
        const panels = wrapper.querySelectorAll(".ll_edit_panel");
        panels.forEach((p) => {
          const el = p;
          if (el.dataset.panel === toolId) {
            el.classList.toggle("visible", show);
          } else {
            el.classList.remove("visible");
          }
        });
        if (editCropOverlay) {
          editCropOverlay.canvasElement.style.display = toolId === "crop" && show ? "block" : "none";
        }
      }
      function buildCropPanel(wrapper, editImg2) {
        const panel = document.createElement("div");
        panel.className = "ll_edit_panel";
        panel.dataset.panel = "crop";
        const info = document.createElement("div");
        info.style.cssText = "color:#888;font:11px/1.4 monospace;padding:4px 0;";
        info.textContent = "Use the crop overlay on the image above. Select presets or drag handles.";
        panel.appendChild(info);
        if (editCropOverlay) {
          panel.appendChild(editCropOverlay.element);
          const setDims = () => {
            if (editImg2.naturalWidth && editImg2.naturalHeight) {
              editCropOverlay.setVideoDimensions(editImg2.naturalWidth, editImg2.naturalHeight);
            }
          };
          if (editImg2.complete && editImg2.naturalWidth) setDims();
          else editImg2.addEventListener("load", setDims, { once: true });
        }
        wrapper.appendChild(panel);
      }
      function buildResizePanel(wrapper, editImg2) {
        const panel = document.createElement("div");
        panel.className = "ll_edit_panel";
        panel.dataset.panel = "resize";
        const row = document.createElement("div");
        row.className = "ll_edit_panel_row";
        const wLabel = document.createElement("span");
        wLabel.className = "ll_edit_panel_label";
        wLabel.textContent = "Width";
        const wInput = document.createElement("input");
        wInput.className = "ll_edit_panel_input";
        wInput.type = "number";
        wInput.min = "1";
        wInput.placeholder = "auto";
        const hLabel = document.createElement("span");
        hLabel.className = "ll_edit_panel_label";
        hLabel.textContent = "Height";
        const hInput = document.createElement("input");
        hInput.className = "ll_edit_panel_input";
        hInput.type = "number";
        hInput.min = "1";
        hInput.placeholder = "auto";
        const lockLabel = document.createElement("label");
        lockLabel.style.cssText = "color:#888;font:11px monospace;display:flex;align-items:center;gap:3px;";
        const lockCheck = document.createElement("input");
        lockCheck.type = "checkbox";
        lockCheck.checked = true;
        lockLabel.innerHTML = `${iconLock} Lock`;
        lockLabel.prepend(lockCheck);
        const updateResize = () => {
          const w = parseInt(wInput.value) || 0;
          const h = parseInt(hInput.value) || 0;
          editState.resize = w > 0 && h > 0 ? { w, h } : null;
        };
        wInput.addEventListener("input", () => {
          if (lockCheck.checked && editImg2 && editImg2.naturalWidth && editImg2.naturalHeight) {
            const w = parseInt(wInput.value) || 0;
            if (w > 0) hInput.value = String(Math.round(w * editImg2.naturalHeight / editImg2.naturalWidth));
          }
          updateResize();
          updateEditPreview();
        });
        hInput.addEventListener("input", () => {
          if (lockCheck.checked && editImg2 && editImg2.naturalWidth && editImg2.naturalHeight) {
            const h = parseInt(hInput.value) || 0;
            if (h > 0) wInput.value = String(Math.round(h * editImg2.naturalWidth / editImg2.naturalHeight));
          }
          updateResize();
          updateEditPreview();
        });
        const presetRow = document.createElement("div");
        presetRow.className = "ll_edit_panel_row";
        const presetLabel = document.createElement("span");
        presetLabel.className = "ll_edit_panel_label";
        presetLabel.textContent = "Presets";
        presetRow.appendChild(presetLabel);
        for (const [label, scale] of [["50%", 0.5], ["75%", 0.75], ["150%", 1.5], ["200%", 2]]) {
          const btn = document.createElement("button");
          btn.className = "ll_edit_tool_btn";
          btn.textContent = label;
          btn.style.fontSize = "10px";
          btn.addEventListener("click", () => {
            if (editImg2 && editImg2.naturalWidth && editImg2.naturalHeight) {
              wInput.value = String(Math.round(editImg2.naturalWidth * scale));
              hInput.value = String(Math.round(editImg2.naturalHeight * scale));
              updateResize();
              updateEditPreview();
            }
          });
          presetRow.appendChild(btn);
        }
        row.append(wLabel, wInput, hLabel, hInput, lockLabel);
        panel.append(row, presetRow);
        wrapper.appendChild(panel);
      }
      function buildTransformPanel(wrapper) {
        const panel = document.createElement("div");
        panel.className = "ll_edit_panel";
        panel.dataset.panel = "rotate";
        const row = document.createElement("div");
        row.className = "ll_edit_panel_row";
        const rotLabel = document.createElement("span");
        rotLabel.className = "ll_edit_panel_label";
        rotLabel.textContent = "Rotate";
        row.appendChild(rotLabel);
        const rotInfo = document.createElement("span");
        rotInfo.style.cssText = "color:#aaa;font:11px monospace;margin-left:auto;";
        rotInfo.textContent = "0°";
        for (const angle of [90, 180, 270]) {
          const btn = document.createElement("button");
          btn.className = "ll_edit_tool_btn";
          btn.textContent = `${angle}°`;
          btn.addEventListener("click", () => {
            editState.rotation = editState.rotation === angle ? 0 : angle;
            rotInfo.textContent = `${editState.rotation}°`;
            row.querySelectorAll(".ll_edit_tool_btn").forEach((b) => {
              const a = parseInt(b.textContent || "0");
              b.classList.toggle("active", a === editState.rotation);
            });
            updateEditPreview();
          });
          if (editState.rotation === angle) btn.classList.add("active");
          row.appendChild(btn);
        }
        row.appendChild(rotInfo);
        const flipRow = document.createElement("div");
        flipRow.className = "ll_edit_panel_row";
        const flipLabel = document.createElement("span");
        flipLabel.className = "ll_edit_panel_label";
        flipLabel.textContent = "Flip";
        flipRow.appendChild(flipLabel);
        for (const dir of ["horizontal", "vertical"]) {
          const btn = document.createElement("button");
          btn.className = "ll_edit_tool_btn";
          btn.innerHTML = dir === "horizontal" ? `${iconFlip} Horizontal` : `${iconFlipVertical} Vertical`;
          btn.addEventListener("click", () => {
            editState.flip = editState.flip === dir ? "" : dir;
            flipRow.querySelectorAll(".ll_edit_tool_btn").forEach((b) => {
              var _a2;
              b.classList.toggle("active", ((_a2 = b.textContent) == null ? void 0 : _a2.toLowerCase().includes(editState.flip)) || false);
            });
            updateEditPreview();
          });
          flipRow.appendChild(btn);
        }
        panel.append(row, flipRow);
        wrapper.appendChild(panel);
      }
      function buildPaddingPanel(wrapper) {
        const panel = document.createElement("div");
        panel.className = "ll_edit_panel";
        panel.dataset.panel = "padding";
        const inputs = {};
        const sliders = {};
        for (const side of ["top", "right", "bottom", "left"]) {
          const row = document.createElement("div");
          row.className = "ll_edit_slider_row";
          const lbl = document.createElement("span");
          lbl.className = "ll_edit_panel_label";
          lbl.textContent = side.charAt(0).toUpperCase() + side.slice(1);
          const slider = document.createElement("input");
          slider.className = "ll_edit_slider";
          slider.type = "range";
          slider.min = "0";
          slider.max = "500";
          slider.step = "1";
          slider.value = "0";
          const inp = document.createElement("input");
          inp.className = "ll_edit_panel_input";
          inp.type = "number";
          inp.min = "0";
          inp.max = "500";
          inp.value = "0";
          inp.style.width = "55px";
          slider.addEventListener("input", () => {
            inp.value = slider.value;
            updatePadding();
          });
          inp.addEventListener("input", () => {
            slider.value = inp.value;
            updatePadding();
          });
          inputs[side] = inp;
          sliders[side] = slider;
          row.append(lbl, slider, inp);
          if (side === "top") {
            const uniLabel = document.createElement("label");
            uniLabel.style.cssText = "color:#888;font:11px monospace;display:flex;align-items:center;gap:3px;margin-left:4px;";
            const uniCheck = document.createElement("input");
            uniCheck.type = "checkbox";
            uniCheck.id = "ll_pad_uniform";
            uniLabel.append(uniCheck, "Uniform");
            row.appendChild(uniLabel);
            uniCheck.addEventListener("change", () => {
              if (uniCheck.checked) {
                const v = inputs.top.value;
                for (const s of ["right", "bottom", "left"]) {
                  inputs[s].value = v;
                  sliders[s].value = v;
                }
                updatePadding();
              }
            });
          }
          panel.appendChild(row);
        }
        const colorRow = document.createElement("div");
        colorRow.className = "ll_edit_panel_row";
        const colorLbl = document.createElement("span");
        colorLbl.className = "ll_edit_panel_label";
        colorLbl.textContent = "Color";
        const colorInput = document.createElement("input");
        colorInput.type = "color";
        colorInput.value = "#000000";
        colorInput.style.cssText = "width:40px;height:24px;border:none;cursor:pointer;";
        colorInput.addEventListener("input", updatePadding);
        colorRow.append(colorLbl, colorInput);
        panel.appendChild(colorRow);
        function updatePadding() {
          var _a2;
          const uni = (_a2 = document.getElementById("ll_pad_uniform")) == null ? void 0 : _a2.checked;
          if (uni) {
            const v = inputs.top.value;
            for (const s of ["right", "bottom", "left"]) {
              inputs[s].value = v;
              sliders[s].value = v;
            }
          }
          const t = parseInt(inputs.top.value) || 0;
          const r = parseInt(inputs.right.value) || 0;
          const b = parseInt(inputs.bottom.value) || 0;
          const l = parseInt(inputs.left.value) || 0;
          if (t > 0 || r > 0 || b > 0 || l > 0) {
            editState.padding = { top: t, right: r, bottom: b, left: l, color: colorInput.value };
          } else {
            editState.padding = null;
          }
          updateEditPreview();
        }
        wrapper.appendChild(panel);
      }
      function buildColorPanel(wrapper) {
        const panel = document.createElement("div");
        panel.className = "ll_edit_panel";
        panel.dataset.panel = "color";
        const sliders = [
          { key: "brightness", label: "Brightness", min: 0.2, max: 3, step: 0.05 },
          { key: "contrast", label: "Contrast", min: 0.2, max: 3, step: 0.05 },
          { key: "saturation", label: "Saturation", min: 0, max: 3, step: 0.05 }
        ];
        for (const s of sliders) {
          const row = document.createElement("div");
          row.className = "ll_edit_slider_row";
          const label = document.createElement("span");
          label.className = "ll_edit_panel_label";
          label.textContent = s.label;
          const slider = document.createElement("input");
          slider.className = "ll_edit_slider";
          slider.type = "range";
          slider.min = String(s.min);
          slider.max = String(s.max);
          slider.step = String(s.step);
          slider.value = "1.0";
          const val = document.createElement("span");
          val.className = "ll_edit_slider_val";
          val.textContent = "1.00";
          slider.addEventListener("input", () => {
            const v = parseFloat(slider.value);
            editState[s.key] = v;
            val.textContent = v.toFixed(2);
            updateEditPreview();
          });
          slider.addEventListener("dblclick", () => {
            slider.value = "1.0";
            editState[s.key] = 1;
            val.textContent = "1.00";
            updateEditPreview();
          });
          row.append(label, slider, val);
          panel.appendChild(row);
        }
        const resetRow = document.createElement("div");
        resetRow.className = "ll_edit_panel_row";
        const resetBtn = document.createElement("button");
        resetBtn.className = "ll_edit_tool_btn";
        resetBtn.innerHTML = `${iconReset} Reset Colors`;
        resetBtn.addEventListener("click", () => {
          editState.brightness = 1;
          editState.contrast = 1;
          editState.saturation = 1;
          panel.querySelectorAll(".ll_edit_slider").forEach((s) => {
            s.value = "1.0";
          });
          panel.querySelectorAll(".ll_edit_slider_val").forEach((v) => {
            v.textContent = "1.00";
          });
          updateEditPreview();
        });
        resetRow.appendChild(resetBtn);
        panel.appendChild(resetRow);
        wrapper.appendChild(panel);
      }
      function postEditState() {
        const edits = {};
        if (editState.crop_rect) edits.crop_rect = editState.crop_rect;
        if (editState.resize) edits.resize = editState.resize;
        if (editState.rotation) edits.rotation = editState.rotation;
        if (editState.flip) edits.flip = editState.flip;
        if (editState.padding) edits.padding = editState.padding;
        if (editState.brightness !== 1) edits.brightness = editState.brightness;
        if (editState.contrast !== 1) edits.contrast = editState.contrast;
        if (editState.saturation !== 1) edits.saturation = editState.saturation;
        fetch(api.apiURL("/loadlast/apply_image_edits"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            node_id: String(node.id),
            edits: Object.keys(edits).length > 0 ? edits : null
          })
        }).catch(() => {
        });
      }
      function updateEditPreview() {
        if (!editImg) return;
        const transforms = [];
        if (editState.rotation) transforms.push(`rotate(${editState.rotation}deg)`);
        if (editState.flip === "horizontal") transforms.push("scaleX(-1)");
        if (editState.flip === "vertical") transforms.push("scaleY(-1)");
        editImg.style.transform = transforms.length ? transforms.join(" ") : "";
        const filters = [];
        if (editState.brightness !== 1) filters.push(`brightness(${editState.brightness})`);
        if (editState.contrast !== 1) filters.push(`contrast(${editState.contrast})`);
        if (editState.saturation !== 1) filters.push(`saturate(${editState.saturation})`);
        editImg.style.filter = filters.length ? filters.join(" ") : "";
        const area = editImg.parentElement;
        if (area && editState.padding) {
          const p = editState.padding;
          const scale = Math.min(1, (area.clientWidth || 300) / (editImg.naturalWidth || 1));
          area.style.padding = `${Math.round(p.top * scale)}px ${Math.round(p.right * scale)}px ${Math.round(p.bottom * scale)}px ${Math.round(p.left * scale)}px`;
          area.style.backgroundColor = p.color || "#000";
        } else if (area) {
          area.style.padding = "";
          area.style.backgroundColor = "";
        }
      }
      function cleanupEditMode() {
        if (editCropOverlay) {
          editCropOverlay.destroy();
          editCropOverlay = null;
        }
        if (editWrapper) {
          editWrapper.remove();
          editWrapper = null;
        }
      }
      async function loadBrowserImages(count) {
        const images = [];
        const entries = allImages.slice(0, count);
        for (const entry of entries) {
          try {
            const img = await loadImage(buildViewURL(entry));
            images.push(img);
          } catch {
          }
        }
        return images;
      }
      function getComparisonIndices() {
        let sel = selectedIndex >= 0 ? selectedIndex : 0;
        if (sel >= allImages.length) sel = 0;
        const prev = Math.min(sel + 1, allImages.length - 1);
        return [prev, sel];
      }
      async function renderCurrentMode() {
        if (currentMode === "grid") {
          await renderGrid();
        } else if (currentMode === "sidebyside") {
          await renderSideBySide();
        } else if (currentMode === "diff") {
          if (diffMode === "slider") {
            await renderDiffSlider();
          } else {
            await renderDiff();
          }
        }
      }
      async function renderGrid() {
        const images = await loadBrowserImages(allImages.length);
        if (images.length === 0) return;
        const cols = Math.ceil(Math.sqrt(images.length));
        const rows = Math.ceil(images.length / cols);
        const gap = 4;
        const cellW = images[0].naturalWidth;
        const cellH = images[0].naturalHeight;
        const totalW = cols * cellW + (cols - 1) * gap;
        const totalH = rows * cellH + (rows - 1) * gap;
        canvasEl.width = totalW;
        canvasEl.height = totalH;
        const ctx = canvasEl.getContext("2d");
        if (!ctx) return;
        ctx.fillStyle = "#111";
        ctx.fillRect(0, 0, totalW, totalH);
        for (let i = 0; i < images.length; i++) {
          const col = i % cols;
          const row = Math.floor(i / cols);
          const x = col * (cellW + gap);
          const y = row * (cellH + gap);
          const img = images[i];
          const scale = Math.min(cellW / img.naturalWidth, cellH / img.naturalHeight);
          const dw = img.naturalWidth * scale;
          const dh = img.naturalHeight * scale;
          const dx = x + (cellW - dw) / 2;
          const dy = y + (cellH - dh) / 2;
          ctx.drawImage(img, dx, dy, dw, dh);
          ctx.fillStyle = "rgba(0,0,0,0.6)";
          ctx.fillRect(x, y + cellH - 16, 30, 16);
          ctx.fillStyle = "#ccc";
          ctx.font = "11px monospace";
          ctx.textAlign = "left";
          ctx.fillText(`#${i + 1}`, x + 3, y + cellH - 4);
        }
        previewWidget.aspectRatio = totalW / totalH;
        infoEl.textContent = `Grid: ${images.length} images │ ${cols}×${rows} │ ${totalW}×${totalH}`;
        fitNode();
      }
      async function renderSideBySide() {
        var _a2, _b;
        const [idxA, idxB] = getComparisonIndices();
        if (allImages.length < 2) {
          infoEl.textContent = "Side-by-Side: need at least 2 images";
          return;
        }
        let imgA, imgB;
        try {
          [imgA, imgB] = await Promise.all([
            loadImage(buildViewURL(allImages[idxA])),
            loadImage(buildViewURL(allImages[idxB]))
          ]);
        } catch {
          return;
        }
        const gap = 4;
        const cellW = Math.max(imgA.naturalWidth, imgB.naturalWidth);
        const cellH = Math.max(imgA.naturalHeight, imgB.naturalHeight);
        const totalW = cellW * 2 + gap;
        const totalH = cellH;
        canvasEl.width = totalW;
        canvasEl.height = totalH;
        const ctx = canvasEl.getContext("2d");
        if (!ctx) return;
        ctx.fillStyle = "#111";
        ctx.fillRect(0, 0, totalW, totalH);
        const sB = Math.min(cellW / imgB.naturalWidth, cellH / imgB.naturalHeight);
        const dwB = imgB.naturalWidth * sB;
        const dhB = imgB.naturalHeight * sB;
        ctx.drawImage(imgB, (cellW - dwB) / 2, (cellH - dhB) / 2, dwB, dhB);
        const sA = Math.min(cellW / imgA.naturalWidth, cellH / imgA.naturalHeight);
        const dwA = imgA.naturalWidth * sA;
        const dhA = imgA.naturalHeight * sA;
        ctx.drawImage(imgA, cellW + gap + (cellW - dwA) / 2, (cellH - dhA) / 2, dwA, dhA);
        ctx.fillStyle = "#333";
        ctx.fillRect(cellW, 0, gap, totalH);
        ctx.font = "bold 12px monospace";
        ctx.fillStyle = "rgba(0,0,0,0.6)";
        ctx.fillRect(4, 4, 90, 18);
        ctx.fillRect(cellW + gap + 4, 4, 90, 18);
        ctx.fillStyle = "#0cf";
        ctx.fillText("Selected", 8, 17);
        ctx.fillStyle = "#aaa";
        ctx.fillText("Previous", cellW + gap + 8, 17);
        previewWidget.aspectRatio = totalW / totalH;
        infoEl.textContent = `Side-by-Side │ Selected: ${((_a2 = allImages[idxB]) == null ? void 0 : _a2.filename) || "?"} │ Previous: ${((_b = allImages[idxA]) == null ? void 0 : _b.filename) || "?"}`;
        fitNode();
      }
      async function renderDiffSlider() {
        var _a2, _b;
        compContainer.style.display = "block";
        canvasEl.style.display = "none";
        const [idxA, idxB] = getComparisonIndices();
        if (allImages.length < 2) {
          infoEl.textContent = "Diff: need at least 2 images";
          return;
        }
        let imgA, imgB;
        try {
          [imgA, imgB] = await Promise.all([
            loadImage(buildViewURL(allImages[idxA])),
            loadImage(buildViewURL(allImages[idxB]))
          ]);
        } catch {
          return;
        }
        const w = Math.max(imgA.naturalWidth, imgB.naturalWidth);
        const h = Math.max(imgA.naturalHeight, imgB.naturalHeight);
        compCanvasA.width = w;
        compCanvasA.height = h;
        const ctxA = compCanvasA.getContext("2d");
        if (ctxA) {
          ctxA.fillStyle = "#111";
          ctxA.fillRect(0, 0, w, h);
          const s = Math.min(w / imgB.naturalWidth, h / imgB.naturalHeight);
          const dw = imgB.naturalWidth * s;
          const dh = imgB.naturalHeight * s;
          ctxA.drawImage(imgB, (w - dw) / 2, (h - dh) / 2, dw, dh);
        }
        compCanvasB.width = w;
        compCanvasB.height = h;
        const ctxB = compCanvasB.getContext("2d");
        if (ctxB) {
          ctxB.fillStyle = "#111";
          ctxB.fillRect(0, 0, w, h);
          const s = Math.min(w / imgA.naturalWidth, h / imgA.naturalHeight);
          const dw = imgA.naturalWidth * s;
          const dh = imgA.naturalHeight * s;
          ctxB.drawImage(imgA, (w - dw) / 2, (h - dh) / 2, dw, dh);
        }
        compLabelA.textContent = `Selected: ${((_a2 = allImages[idxB]) == null ? void 0 : _a2.filename) || ""}`;
        compLabelB.textContent = `Previous: ${((_b = allImages[idxA]) == null ? void 0 : _b.filename) || ""}`;
        previewWidget.aspectRatio = w / h;
        updateCompSlider();
        infoEl.textContent = `Diff (Slider) │ ← Selected  |  Previous →`;
        fitNode();
      }
      async function renderDiff() {
        compContainer.style.display = "none";
        canvasEl.style.display = "block";
        const [idxA, idxB] = getComparisonIndices();
        if (allImages.length < 2) {
          infoEl.textContent = "Diff: need at least 2 images";
          return;
        }
        let imgA, imgB;
        try {
          [imgA, imgB] = await Promise.all([
            loadImage(buildViewURL(allImages[idxA])),
            loadImage(buildViewURL(allImages[idxB]))
          ]);
        } catch {
          return;
        }
        const w = Math.max(imgA.naturalWidth, imgB.naturalWidth);
        const h = Math.max(imgA.naturalHeight, imgB.naturalHeight);
        const tmpA = document.createElement("canvas");
        tmpA.width = w;
        tmpA.height = h;
        const ctxTmpA = tmpA.getContext("2d");
        if (!ctxTmpA) return;
        ctxTmpA.fillStyle = "#000";
        ctxTmpA.fillRect(0, 0, w, h);
        const sA = Math.min(w / imgA.naturalWidth, h / imgA.naturalHeight);
        const dwA = imgA.naturalWidth * sA;
        const dhA = imgA.naturalHeight * sA;
        ctxTmpA.drawImage(imgA, (w - dwA) / 2, (h - dhA) / 2, dwA, dhA);
        const dataA = ctxTmpA.getImageData(0, 0, w, h);
        const tmpB = document.createElement("canvas");
        tmpB.width = w;
        tmpB.height = h;
        const ctxTmpB = tmpB.getContext("2d");
        if (!ctxTmpB) return;
        ctxTmpB.fillStyle = "#000";
        ctxTmpB.fillRect(0, 0, w, h);
        const sB = Math.min(w / imgB.naturalWidth, h / imgB.naturalHeight);
        const dwB = imgB.naturalWidth * sB;
        const dhB = imgB.naturalHeight * sB;
        ctxTmpB.drawImage(imgB, (w - dwB) / 2, (h - dhB) / 2, dwB, dhB);
        const dataB = ctxTmpB.getImageData(0, 0, w, h);
        canvasEl.width = w;
        canvasEl.height = h;
        const ctx = canvasEl.getContext("2d");
        if (!ctx) return;
        const output = ctx.createImageData(w, h);
        if (diffMode === "heatmap") {
          for (let i = 0; i < dataA.data.length; i += 4) {
            const dr = Math.abs(dataA.data[i] - dataB.data[i]);
            const dg = Math.abs(dataA.data[i + 1] - dataB.data[i + 1]);
            const db = Math.abs(dataA.data[i + 2] - dataB.data[i + 2]);
            const diff = (dr + dg + db) / 3;
            const t = Math.min(1, diff / 80);
            output.data[i] = Math.round(t * 255);
            output.data[i + 1] = Math.round(t > 0.5 ? (1 - t) * 2 * 200 : t * 2 * 200);
            output.data[i + 2] = Math.round((1 - t) * 200);
            output.data[i + 3] = 255;
          }
          infoEl.textContent = "Diff (Heatmap) │ Blue=same, Red=different";
        } else {
          for (let i = 0; i < dataA.data.length; i += 4) {
            const dr = Math.abs(dataA.data[i] - dataB.data[i]);
            const dg = Math.abs(dataA.data[i + 1] - dataB.data[i + 1]);
            const db = Math.abs(dataA.data[i + 2] - dataB.data[i + 2]);
            const diff = (dr + dg + db) / 3;
            const t = Math.min(1, diff / 40);
            output.data[i] = Math.round(dataB.data[i] * (1 - t) + 255 * t);
            output.data[i + 1] = Math.round(dataB.data[i + 1] * (1 - t));
            output.data[i + 2] = Math.round(dataB.data[i + 2] * (1 - t) + 255 * t);
            output.data[i + 3] = 255;
          }
          infoEl.textContent = "Diff (Overlay) │ Magenta = changed pixels";
        }
        ctx.putImageData(output, 0, 0);
        previewWidget.aspectRatio = w / h;
        fitNode();
      }
      function updatePreview() {
        if (!currentEntry) return;
        if (currentMode !== "single" && currentMode !== "edit") return;
        const url = buildViewURL(currentEntry);
        if (imgEl.src !== url) {
          imgEl.classList.add("loading");
          imgEl.src = url;
        }
        updateInfoBar();
      }
      function updateInfoBar() {
        var _a2;
        if (!currentEntry) {
          infoEl.textContent = "No image loaded";
          return;
        }
        const name = currentEntry.filename;
        const ext = ((_a2 = name.split(".").pop()) == null ? void 0 : _a2.toUpperCase()) || "";
        const dims = imgEl.naturalWidth && imgEl.naturalHeight ? `${imgEl.naturalWidth}×${imgEl.naturalHeight}` : "";
        const parts = [name];
        if (dims) parts.push(dims);
        if (ext) parts.push(ext);
        infoEl.textContent = parts.join(" │ ");
      }
      function populateBrowserStrip(images) {
        var _a2;
        browserStrip.innerHTML = "";
        allImages = images;
        for (let i = 0; i < images.length; i++) {
          const entry = images[i];
          const thumbEl = document.createElement("div");
          thumbEl.className = "ll_thumb";
          thumbEl.style.width = "64px";
          thumbEl.style.height = "48px";
          const img = document.createElement("img");
          img.src = buildViewURL(entry);
          img.alt = entry.filename;
          img.loading = "lazy";
          thumbEl.appendChild(img);
          const label = document.createElement("div");
          label.className = "ll_thumb_label";
          label.textContent = entry.filename.length > 12 ? "…" + entry.filename.slice(-11) : entry.filename;
          thumbEl.appendChild(label);
          if (i === selectedIndex || selectedIndex < 0 && (currentEntry == null ? void 0 : currentEntry.filename) === entry.filename) {
            thumbEl.classList.add("active");
          }
          const pinWidget = (_a2 = node.widgets) == null ? void 0 : _a2.find((w) => w.name === "pin_index");
          if (pinWidget && pinWidget.value > 0 && i === 0) {
            const badge = document.createElement("div");
            badge.className = "ll_pin_badge";
            badge.innerHTML = iconPin;
            thumbEl.appendChild(badge);
          }
          thumbEl.addEventListener("click", (e) => {
            e.stopPropagation();
            selectedIndex = i;
            currentEntry = entry;
            fetch(api.apiURL("/loadlast/select_image"), {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                node_id: String(node.id),
                entry: {
                  filename: entry.filename,
                  subfolder: entry.subfolder,
                  type: entry.type
                }
              })
            }).catch(() => {
            });
            if (currentMode === "single") {
              updatePreview();
            } else if (currentMode === "edit") {
              updatePreview();
              if (editImg) {
                editImg.src = buildViewURL(entry);
              }
            } else {
              renderCurrentMode();
            }
            highlightStrip();
          });
          browserStrip.appendChild(thumbEl);
        }
        requestAnimationFrame(() => {
          updateScrollIndicator();
        });
      }
      function highlightStrip() {
        const thumbs = browserStrip.querySelectorAll(".ll_thumb");
        thumbs.forEach((t, i) => {
          var _a2;
          t.classList.toggle(
            "active",
            i === selectedIndex || selectedIndex < 0 && (currentEntry == null ? void 0 : currentEntry.filename) === ((_a2 = allImages[i]) == null ? void 0 : _a2.filename)
          );
        });
      }
      async function pollLatest() {
        var _a2, _b, _c;
        try {
          const srcWidget = (_a2 = node.widgets) == null ? void 0 : _a2.find((w) => w.name === "source_folder");
          const prefixWidget = (_b = node.widgets) == null ? void 0 : _b.find((w) => w.name === "filename_filter");
          const source = (srcWidget == null ? void 0 : srcWidget.value) || "";
          const prefix = (prefixWidget == null ? void 0 : prefixWidget.value) || "";
          const params = new URLSearchParams();
          if (source) params.set("source", source);
          if (prefix) params.set("prefix", prefix);
          const resp = await fetch(api.apiURL(`/loadlast/latest_image?${params.toString()}`));
          if (!resp.ok) return;
          const data = await resp.json();
          if (data.found && data.filename) {
            const newEntry = {
              filename: data.filename,
              subfolder: data.subfolder || "",
              type: data.type || "output",
              mtime: data.mtime || 0
            };
            const pinWidget = (_c = node.widgets) == null ? void 0 : _c.find((w) => w.name === "pin_index");
            const isPinned = pinWidget && pinWidget.value > 0;
            if (!isPinned && selectedIndex < 0) {
              if (!currentEntry || currentEntry.filename !== newEntry.filename || currentEntry.mtime !== newEntry.mtime) {
                currentEntry = newEntry;
                if (currentMode === "single" || currentMode === "edit") {
                  updatePreview();
                }
              }
            }
          }
          const listResp = await fetch(
            api.apiURL(`/loadlast/image_list?${params.toString()}&limit=30`)
          );
          if (listResp.ok) {
            const listData = await listResp.json();
            if (listData.images && Array.isArray(listData.images)) {
              populateBrowserStrip(listData.images);
            }
          }
        } catch {
        }
      }
      pollLatest();
      pollTimer = setInterval(pollLatest, 5e3);
      const origOnExecuted = nodeType.prototype.onExecuted;
      nodeType.prototype.onExecuted = function(output) {
        origOnExecuted == null ? void 0 : origOnExecuted.apply(this, arguments);
        if ((output == null ? void 0 : output.images) && Array.isArray(output.images) && output.images.length > 0) {
          const entry = output.images[0];
          currentEntry = {
            filename: entry.filename,
            subfolder: entry.subfolder || "",
            type: entry.type || "output",
            mtime: Date.now() / 1e3
          };
          selectedIndex = -1;
          if (currentMode === "single" || currentMode === "edit") {
            updatePreview();
          }
          pollLatest();
        }
      };
      const origRemoved = nodeType.prototype.onRemoved;
      nodeType.prototype.onRemoved = function() {
        if (pollTimer) {
          clearInterval(pollTimer);
          pollTimer = null;
        }
        origRemoved == null ? void 0 : origRemoved.apply(this, arguments);
      };
    };
    const origGetMenu = nodeType.prototype.getExtraMenuOptions;
    nodeType.prototype.getExtraMenuOptions = function(_canvas, options) {
      origGetMenu == null ? void 0 : origGetMenu.apply(this, arguments);
      const self = this;
      options.unshift({
        content: "🎯 Open Mask / Point Editor",
        callback: () => {
          var _a, _b, _c;
          const preview = (_a = self.widgets) == null ? void 0 : _a.find((w) => w.name === "preview");
          const imgEl = (_c = (_b = preview == null ? void 0 : preview.element) == null ? void 0 : _b.querySelector) == null ? void 0 : _c.call(_b, "img.ll_img_preview");
          const src = imgEl == null ? void 0 : imgEl.src;
          if (!src) {
            flashNode(self, "#7a4a4a");
            return;
          }
          openPointSelector(self, src);
        }
      }, null);
    };
  }
});
