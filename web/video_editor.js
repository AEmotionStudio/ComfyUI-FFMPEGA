var __defProp = Object.defineProperty;
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { a as addDownloadOverlay } from "./_chunks/ui_helpers-CvUDB6-L.js";
import { E as EditManager, T as TransportBar, S as SpeedControl, a as EditToolbar, U as UndoManager, N as NLETimeline } from "./_chunks/UndoManager-DCdZdNls.js";
import { i as iconVolume, a as iconMuted, b as iconMusic, c as iconPlus, d as iconClose, e as iconBold, f as iconItalic, g as iconAlignLeft, h as iconAlignCenter, j as iconAlignRight, k as iconZoomOut, l as iconZoomIn, m as iconMaximize, n as iconShuffle, o as iconClapperboard, p as iconUndo, q as iconRedo, r as iconCheck, C as CropOverlay, s as iconCrop, t as iconGauge, u as iconText } from "./_chunks/CropOverlay-RBSIEwzt.js";
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
    if (this.overlays.length === 0) {
      const emptyMsg = document.createElement("div");
      emptyMsg.className = "veditor-text-empty-state";
      emptyMsg.textContent = 'No text overlays. Click "Add Text" or choose a preset to begin.';
      this.listEl.appendChild(emptyMsg);
      return;
    }
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

.veditor-text-empty-state {
    padding: 24px;
    text-align: center;
    color: var(--ve-text-muted);
    font-style: italic;
    font-size: 13px;
    border: 1px dashed var(--ve-border);
    border-radius: 6px;
    margin-top: 8px;
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
  node.color = "#2a5a4a";
  node.bgcolor = "#1a4a3a";
  _ensureHiddenWidgets(node);
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
        var _a2;
        editState = state;
        _syncToWidgets(node, state);
        infoEl.textContent = "Edits applied";
        previewContainer.style.display = "";
        resizeNode();
        const pauseW = (_a2 = node.widgets) == null ? void 0 : _a2.find((w) => w.name === "pause_on_input");
        if (pauseW == null ? void 0 : pauseW.value) {
          app.queuePrompt(0, 1).finally(() => _setW(node, "_edit_action", "none"));
        } else {
          _setW(node, "_edit_action", "none");
        }
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
      if ((autoW == null ? void 0 : autoW.value) && !getModal().isOpen) {
        const m = getModal();
        m.setCallbacks({
          onApply: (state) => {
            var _a3;
            editState = state;
            _syncToWidgets(node, state);
            infoEl.textContent = "Edits applied";
            previewContainer.style.display = "";
            resizeNode();
            const pauseW2 = (_a3 = node.widgets) == null ? void 0 : _a3.find((w) => w.name === "pause_on_input");
            if (pauseW2 == null ? void 0 : pauseW2.value) {
              app.queuePrompt(0, 1).finally(() => _setW(node, "_edit_action", "none"));
            } else {
              _setW(node, "_edit_action", "none");
            }
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
  if (w) {
    w.value = value;
  } else {
    if (!node.properties) node.properties = {};
    node.properties[name] = value;
  }
}
const HIDDEN_WIDGETS = [
  ["_edit_segments", "[]"],
  ["_edit_action", "none"],
  ["_crop_rect", ""],
  ["_speed_map", "{}"],
  ["_volume", "1.0"],
  ["_text_overlays", "[]"],
  ["_transitions", "[]"]
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
  try {
    const t = JSON.parse(_getW(node, "_transitions", "[]"));
    if (Array.isArray(t)) editState.transitions = t;
  } catch {
  }
}
