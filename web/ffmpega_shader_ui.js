/**
 * FFMPEGA Shader Overlay node context-menu extension.
 *
 * Features:
 * - Right-click context menu with categorized shader preset picker
 * - Custom save/load/delete for user shader presets via API
 * - Quick intensity, speed, hue shift, blend mode, resolution selectors
 * - Dynamic widget visibility (preset_2/3 expand as needed)
 * - Random shader shortcut
 * - Node theming (blue accent)
 */
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
app.registerExtension({
  name: "FFMPEGA.ShaderOverlayUI",
  async beforeRegisterNodeDef(nodeType, nodeData, _app) {
    if (nodeData.name !== "FFMPEGAShaderOverlay") return;
    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function() {
      const result = onNodeCreated == null ? void 0 : onNodeCreated.apply(this, arguments);
      this.color = "#2a3a5a";
      this.bgcolor = "#1a2a4a";
      const node = this;
      const findW = (name) => {
        var _a;
        return (_a = this.widgets) == null ? void 0 : _a.find((w) => w.name === name);
      };
      const presetW = findW("preset");
      const intensityW = findW("intensity");
      const preset2W = findW("preset_2");
      const intensity2W = findW("intensity_2");
      const preset3W = findW("preset_3");
      const intensity3W = findW("intensity_3");
      const speedW = findW("speed");
      const hueShiftW = findW("hue_shift");
      const blendModeW = findW("blend_mode");
      const phaseW = findW("phase");
      const shaderParamsW = findW("shader_params");
      const resScaleW = findW("resolution_scale");
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
      function fitHeight() {
        var _a;
        node.setSize([
          node.size[0],
          node.computeSize([node.size[0], node.size[1]])[1]
        ]);
        (_a = node == null ? void 0 : node.graph) == null ? void 0 : _a.setDirtyCanvas(true);
      }
      function isActive(w) {
        if (!w) return false;
        const v = w.value;
        return v && v !== "none" && !String(v).startsWith("\u2500\u2500");
      }
      function updateVisibility() {
        const p1Active = isActive(presetW);
        // Show preset_2 when preset_1 is active
        toggleWidget(preset2W, p1Active);
        toggleWidget(intensity2W, p1Active && isActive(preset2W));
        // Show preset_3 when preset_2 is active
        const p2Active = p1Active && isActive(preset2W);
        toggleWidget(preset3W, p2Active);
        toggleWidget(intensity3W, p2Active && isActive(preset3W));
        // Show advanced controls when any preset is active
        const anyActive = p1Active;
        toggleWidget(speedW, anyActive);
        toggleWidget(hueShiftW, anyActive);
        toggleWidget(blendModeW, anyActive);
        toggleWidget(phaseW, anyActive);
        toggleWidget(shaderParamsW, anyActive);
        toggleWidget(resScaleW, anyActive);
        fitHeight();
      }
      updateVisibility();
      // Wire callbacks for dynamic visibility
      for (const w of [presetW, preset2W, preset3W]) {
        if (w) {
          const orig = w.callback;
          w.callback = function(...args) {
            orig == null ? void 0 : orig.apply(this, args);
            updateVisibility();
          };
        }
      }
      // Re-run visibility after workflow restoration
      const origOnConfigure = node.onConfigure;
      node.onConfigure = function(info) {
        origOnConfigure == null ? void 0 : origOnConfigure.apply(this, [info]);
        updateVisibility();
      };
      return result;
    };
    // --- Custom presets ---
    let _customShaderPresets = [];
    fetch(api.apiURL("/ffmpega/shader_presets")).then((r) => r.json()).then((data) => {
      _customShaderPresets = Array.isArray(data) ? data : [];
    }).catch(() => {
      _customShaderPresets = [];
    });
    function flashNode(node, color) {
      if (!node || node._isFlashing) return;
      node._isFlashing = true;
      const orig = node.bgcolor;
      node.bgcolor = color;
      node.setDirtyCanvas(true, true);
      setTimeout(() => {
        node.bgcolor = orig;
        node._isFlashing = false;
        node.setDirtyCanvas(true, true);
      }, 300);
    }
    const origGetMenu = nodeType.prototype.getExtraMenuOptions;
    nodeType.prototype.getExtraMenuOptions = function(_, options) {
      origGetMenu == null ? void 0 : origGetMenu.apply(this, arguments);
      const self = this;
      const findW = (name) => {
        var _a;
        return (_a = self.widgets) == null ? void 0 : _a.find((w) => w.name === name);
      };
      const presetW = findW("preset");
      const intensityW = findW("intensity");
      const preset2W = findW("preset_2");
      const intensity2W = findW("intensity_2");
      const preset3W = findW("preset_3");
      const intensity3W = findW("intensity_3");
      const speedW = findW("speed");
      const hueShiftW = findW("hue_shift");
      const blendModeW = findW("blend_mode");
      const phaseW = findW("phase");
      const shaderParamsW = findW("shader_params");
      const resScaleW = findW("resolution_scale");
      const customPathW = findW("custom_shader_path");
      const sam3TargetW = findW("mask_target");
      const captureState = () => {
        var _a, _b, _c, _d, _e, _f, _g, _h, _i, _j, _k, _l;
        return {
          preset: (_a = presetW == null ? void 0 : presetW.value) != null ? _a : "none",
          intensity: (_b = intensityW == null ? void 0 : intensityW.value) != null ? _b : 1,
          preset_2: (_c = preset2W == null ? void 0 : preset2W.value) != null ? _c : "none",
          intensity_2: (_d = intensity2W == null ? void 0 : intensity2W.value) != null ? _d : 1,
          preset_3: (_e = preset3W == null ? void 0 : preset3W.value) != null ? _e : "none",
          intensity_3: (_f = intensity3W == null ? void 0 : intensity3W.value) != null ? _f : 1,
          speed: (_g = speedW == null ? void 0 : speedW.value) != null ? _g : 1,
          hue_shift: (_h = hueShiftW == null ? void 0 : hueShiftW.value) != null ? _h : 0,
          blend_mode: (_i = blendModeW == null ? void 0 : blendModeW.value) != null ? _i : "normal",
          phase: (_j = phaseW == null ? void 0 : phaseW.value) != null ? _j : 0,
          resolution_scale: (_k = resScaleW == null ? void 0 : resScaleW.value) != null ? _k : "1.0",
          custom_shader_path: (_l = customPathW == null ? void 0 : customPathW.value) != null ? _l : ""
        };
      };
      const applyState = (cfg) => {
        if (presetW && cfg.preset !== void 0) presetW.value = cfg.preset;
        if (intensityW && cfg.intensity !== void 0) intensityW.value = cfg.intensity;
        if (preset2W && cfg.preset_2 !== void 0) preset2W.value = cfg.preset_2;
        if (intensity2W && cfg.intensity_2 !== void 0) intensity2W.value = cfg.intensity_2;
        if (preset3W && cfg.preset_3 !== void 0) preset3W.value = cfg.preset_3;
        if (intensity3W && cfg.intensity_3 !== void 0) intensity3W.value = cfg.intensity_3;
        if (speedW && cfg.speed !== void 0) speedW.value = cfg.speed;
        if (hueShiftW && cfg.hue_shift !== void 0) hueShiftW.value = cfg.hue_shift;
        if (blendModeW && cfg.blend_mode !== void 0) blendModeW.value = cfg.blend_mode;
        if (phaseW && cfg.phase !== void 0) phaseW.value = cfg.phase;
        if (resScaleW && cfg.resolution_scale !== void 0) resScaleW.value = cfg.resolution_scale;
        if (customPathW && cfg.custom_shader_path !== void 0) customPathW.value = cfg.custom_shader_path;
      };
      const saveCustom = async () => {
        const name = prompt("Shader preset name:");
        if (!(name == null ? void 0 : name.trim())) return;
        const preset = { name: name.trim(), ...captureState() };
        const idx = _customShaderPresets.findIndex((p) => p.name === preset.name);
        if (idx >= 0) _customShaderPresets[idx] = preset;
        else _customShaderPresets.push(preset);
        try {
          await fetch(api.apiURL("/ffmpega/shader_presets"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(_customShaderPresets)
          });
          flashNode(self, "#4a7a4a");
        } catch {
          flashNode(self, "#7a4a4a");
        }
      };
      const deleteCustom = async (presetName) => {
        const idx = _customShaderPresets.findIndex((p) => p.name === presetName);
        if (idx < 0) return;
        _customShaderPresets.splice(idx, 1);
        try {
          await fetch(api.apiURL("/ffmpega/shader_presets"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(_customShaderPresets)
          });
          flashNode(self, "#4a7a4a");
        } catch {
          flashNode(self, "#7a4a4a");
        }
      };
      // --- Build categorized preset submenu ---
      const presetItems = [];
      const presetValues = (presetW == null ? void 0 : presetW.options) != null ? presetW.options.values || [] : [];
      const categoryMap = {};
      const categoryOrder = [];
      let currentCategory = "Other";
      for (const val of presetValues) {
        if (val === "none") continue;
        if (val.startsWith("\u2500\u2500")) {
          currentCategory = val.replace(/^\u2500\u2500\s*/, "").replace(/\s*\u2500\u2500$/, "");
          continue;
        }
        if (val === "\uD83C\uDFB2 random") {
          presetItems.push({
            content: "\uD83C\uDFB2 Random Shader",
            callback: () => {
              if (presetW) presetW.value = "\uD83C\uDFB2 random";
              flashNode(self, "#7a4a7a");
            }
          });
          continue;
        }
        if (!categoryMap[currentCategory]) {
          categoryMap[currentCategory] = [];
          categoryOrder.push(currentCategory);
        }
        categoryMap[currentCategory].push({
          content: val,
          callback: () => {
            if (presetW) presetW.value = val;
            flashNode(self, "#4a7a4a");
          }
        });
      }
      for (const cat of categoryOrder) {
        const items = categoryMap[cat];
        if (items.length === 1) {
          presetItems.push(items[0]);
        } else {
          presetItems.push({
            content: `${cat} (${items.length})`,
            submenu: { options: items }
          });
        }
      }
      // Custom presets
      if (_customShaderPresets.length > 0) {
        presetItems.push(null);
        for (const p of _customShaderPresets) {
          presetItems.push({
            content: `\u2B50 ${p.name}`,
            submenu: {
              options: [
                {
                  content: "\u2705 Load",
                  callback: () => {
                    applyState(p);
                    flashNode(self, "#4a7a4a");
                  }
                },
                {
                  content: "\uD83D\uDDD1\uFE0F Delete",
                  callback: () => deleteCustom(p.name)
                }
              ]
            }
          });
        }
      }
      // --- Quick selectors ---
      const intensityItems = [
        { label: "25%", val: 0.25 },
        { label: "50%", val: 0.5 },
        { label: "75%", val: 0.75 },
        { label: "100%", val: 1.0 }
      ].map(({ label, val }) => ({
        content: `${label}`,
        callback: () => { if (intensityW) intensityW.value = val; flashNode(self, "#4a7a4a"); }
      }));
      const speedItems = [
        { label: "0.25\u00D7 (slow-mo)", val: 0.25 },
        { label: "0.5\u00D7", val: 0.5 },
        { label: "1.0\u00D7 (normal)", val: 1.0 },
        { label: "2.0\u00D7", val: 2.0 },
        { label: "3.0\u00D7 (fast)", val: 3.0 },
        { label: "5.0\u00D7 (hyper)", val: 5.0 }
      ].map(({ label, val }) => ({
        content: label,
        callback: () => { if (speedW) speedW.value = val; flashNode(self, "#4a7a4a"); }
      }));
      const hueItems = [
        { label: "0\u00B0 (original)", val: 0 },
        { label: "60\u00B0 (warm)", val: 60 },
        { label: "120\u00B0 (green)", val: 120 },
        { label: "180\u00B0 (invert)", val: 180 },
        { label: "240\u00B0 (blue)", val: 240 },
        { label: "300\u00B0 (magenta)", val: 300 }
      ].map(({ label, val }) => ({
        content: label,
        callback: () => { if (hueShiftW) hueShiftW.value = val; flashNode(self, "#4a7a4a"); }
      }));
      const blendItems = [
        "normal", "addition", "multiply", "screen", "overlay", "softlight"
      ].map((mode) => ({
        content: mode.charAt(0).toUpperCase() + mode.slice(1),
        callback: () => { if (blendModeW) blendModeW.value = mode; flashNode(self, "#4a7a4a"); }
      }));
      const resItems = [
        { label: "0.25\u00D7 (fast)", val: "0.25" },
        { label: "0.5\u00D7 (balanced)", val: "0.5" },
        { label: "1.0\u00D7 (native)", val: "1.0" },
        { label: "2.0\u00D7 (quality)", val: "2.0" }
      ].map(({ label, val }) => ({
        content: label,
        callback: () => { if (resScaleW) resScaleW.value = val; flashNode(self, "#4a7a4a"); }
      }));
      // --- Add menu items ---
      options.unshift(
        {
          content: "\uD83D\uDCBE Save Current as Preset",
          callback: () => saveCustom()
        },
        {
          content: "\u2728 Select Shader",
          submenu: { options: presetItems }
        },
        {
          content: "\uD83D\uDD0A Intensity",
          submenu: { options: intensityItems }
        },
        {
          content: "\u23E9 Speed",
          submenu: { options: speedItems }
        },
        {
          content: "\uD83C\uDFA8 Hue Shift",
          submenu: { options: hueItems }
        },
        {
          content: "\uD83D\uDD00 Blend Mode",
          submenu: { options: blendItems }
        },
        {
          content: "\uD83D\uDCD0 Resolution",
          submenu: { options: resItems }
        },
        {
          content: "\uD83E\uDDF9 Reset All",
          callback: () => {
            if (presetW) presetW.value = "none";
            if (intensityW) intensityW.value = 1;
            if (preset2W) preset2W.value = "none";
            if (intensity2W) intensity2W.value = 1;
            if (preset3W) preset3W.value = "none";
            if (intensity3W) intensity3W.value = 1;
            if (speedW) speedW.value = 1;
            if (hueShiftW) hueShiftW.value = 0;
            if (blendModeW) blendModeW.value = "normal";
            if (phaseW) phaseW.value = 0;
            if (shaderParamsW) shaderParamsW.value = "";
            if (resScaleW) resScaleW.value = "1.0";
            if (customPathW) customPathW.value = "";
            if (sam3TargetW) sam3TargetW.value = "";
            // Trigger visibility update through preset callback
            if (presetW == null ? void 0 : presetW.callback) presetW.callback(presetW.value);
            flashNode(self, "#4a7a4a");
          }
        },
        null
      );
    };
  }
});
