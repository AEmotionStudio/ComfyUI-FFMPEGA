import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
app.registerExtension({
  name: "FFMPEGA.EffectsUI",
  async beforeRegisterNodeDef(nodeType, nodeData, _app) {
    if (nodeData.name !== "FFMPEGAEffects") return;
    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function() {
      const result = onNodeCreated == null ? void 0 : onNodeCreated.apply(this, arguments);
      this.color = "#3a2a5a";
      this.bgcolor = "#2a1a4a";
      const node = this;
      const findW = (name) => {
        var _a;
        return (_a = this.widgets) == null ? void 0 : _a.find((w) => w.name === name);
      };
      const presetW = findW("preset");
      const effect1 = findW("effect_1");
      const params1 = findW("effect_1_params");
      const effect2 = findW("effect_2");
      const params2 = findW("effect_2_params");
      const effect3 = findW("effect_3");
      const params3 = findW("effect_3_params");
      const effect4 = findW("effect_4");
      const params4 = findW("effect_4_params");
      const effect5 = findW("effect_5");
      const params5 = findW("effect_5_params");
      const rawFfmpeg = findW("raw_ffmpeg");
      const sam3Target = findW("sam3_target");
      const sam3Effect = findW("sam3_effect");
      const presetsJsonW = findW("_presets_json");
      const defaultsJsonW = findW("_defaults_json");
      const paramHelpJsonW = findW("_param_help_json");
      let presetData = {};
      let defaultsData = {};
      let paramHelpData = {};
      try {
        if (presetsJsonW == null ? void 0 : presetsJsonW.value) presetData = JSON.parse(presetsJsonW.value);
      } catch (e) {
        console.warn("FFMPEGA Effects: failed to parse presets", e);
      }
      try {
        if (defaultsJsonW == null ? void 0 : defaultsJsonW.value) defaultsData = JSON.parse(defaultsJsonW.value);
      } catch (e) {
        console.warn("FFMPEGA Effects: failed to parse defaults", e);
      }
      try {
        if (paramHelpJsonW == null ? void 0 : paramHelpJsonW.value) paramHelpData = JSON.parse(paramHelpJsonW.value);
      } catch (e) {
        console.warn("FFMPEGA Effects: failed to parse param help", e);
      }
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
      function stripCategory(name) {
        if (!name) return "none";
        const idx = name.lastIndexOf("/");
        return idx >= 0 ? name.slice(idx + 1) : name;
      }
      function hasEffect(widget) {
        return !!(widget == null ? void 0 : widget.value) && stripCategory(widget.value) !== "none";
      }
      function findCategorized(skillName, effectWidget) {
        var _a;
        if (!skillName || skillName === "none") return "none";
        const suffix = "/" + skillName;
        const options = ((_a = effectWidget == null ? void 0 : effectWidget.options) == null ? void 0 : _a.values) || [];
        for (const opt of options) {
          if (opt.endsWith(suffix)) return opt;
        }
        return "none";
      }
      function updateParamPlaceholder(effectWidget, paramWidget) {
        if (!effectWidget || !paramWidget) return;
        const skill = stripCategory(effectWidget.value);
        if (!skill || skill === "none") {
          paramWidget.options = paramWidget.options || {};
          paramWidget.options.placeholder = '{"key": "value"}';
          return;
        }
        paramWidget.options = paramWidget.options || {};
        const helpStr = paramHelpData[skill];
        if (helpStr && helpStr !== "no parameters") {
          paramWidget.options.placeholder = `${skill}: ${helpStr}`;
        } else {
          paramWidget.options.placeholder = `${skill} params (JSON)`;
        }
      }
      toggleWidget(presetsJsonW, false);
      toggleWidget(defaultsJsonW, false);
      toggleWidget(paramHelpJsonW, false);
      function applyPreset(presetName) {
        if (!presetName || presetName === "none") return;
        const cfg = presetData[presetName];
        if (!cfg) return;
        const slots = [
          ["effect_1", effect1, "effect_1_params", params1],
          ["effect_2", effect2, "effect_2_params", params2],
          ["effect_3", effect3, "effect_3_params", params3],
          ["effect_4", effect4, "effect_4_params", params4],
          ["effect_5", effect5, "effect_5_params", params5]
        ];
        for (const [eName, eW, pName, pW] of slots) {
          if (cfg[eName] !== void 0 && eW) {
            const catName = findCategorized(cfg[eName], eW);
            eW.value = catName;
          }
          if (cfg[pName] !== void 0 && pW) {
            const v = cfg[pName];
            pW.value = typeof v === "string" ? v : JSON.stringify(v);
          }
        }
        if (cfg.sam3_target !== void 0 && sam3Target) {
          sam3Target.value = cfg.sam3_target;
        }
        if (cfg.sam3_effect !== void 0 && sam3Effect) {
          sam3Effect.value = cfg.sam3_effect;
        }
        updateVisibility();
      }
      function applyCustomPreset(cfg) {
        if (!cfg) return;
        const slots = [
          ["effect_1", effect1, "effect_1_params", params1],
          ["effect_2", effect2, "effect_2_params", params2],
          ["effect_3", effect3, "effect_3_params", params3],
          ["effect_4", effect4, "effect_4_params", params4],
          ["effect_5", effect5, "effect_5_params", params5]
        ];
        for (const [eName, eW, pName, pW] of slots) {
          if (cfg[eName] !== void 0 && eW) {
            const catName = findCategorized(cfg[eName], eW);
            eW.value = catName;
          } else if (eW) {
            eW.value = "none";
          }
          if (cfg[pName] !== void 0 && pW) {
            const v = cfg[pName];
            pW.value = typeof v === "string" ? v : JSON.stringify(v);
          } else if (pW) {
            pW.value = "";
          }
        }
        if (sam3Target) sam3Target.value = cfg.sam3_target || "";
        if (sam3Effect) sam3Effect.value = cfg.sam3_effect || "blur";
        if (rawFfmpeg && cfg.raw_ffmpeg) rawFfmpeg.value = cfg.raw_ffmpeg;
        updateVisibility();
      }
      function autoFillDefaults(effectWidget, paramWidget) {
        if (!effectWidget || !paramWidget) return;
        const skill = stripCategory(effectWidget.value);
        if (paramWidget.value && paramWidget.value.trim()) return;
        if (skill && skill !== "none" && defaultsData[skill]) {
          paramWidget.value = defaultsData[skill];
        }
      }
      function updateVisibility() {
        const e1Active = hasEffect(effect1);
        const e2Active = hasEffect(effect2);
        const e3Active = hasEffect(effect3);
        const e4Active = hasEffect(effect4);
        const e5Active = hasEffect(effect5);
        toggleWidget(params1, e1Active);
        updateParamPlaceholder(effect1, params1);
        toggleWidget(effect2, e1Active);
        toggleWidget(params2, e1Active && e2Active);
        updateParamPlaceholder(effect2, params2);
        toggleWidget(effect3, e1Active && e2Active);
        toggleWidget(params3, e1Active && e2Active && e3Active);
        updateParamPlaceholder(effect3, params3);
        toggleWidget(effect4, e1Active && e2Active && e3Active);
        toggleWidget(params4, e1Active && e2Active && e3Active && e4Active);
        updateParamPlaceholder(effect4, params4);
        toggleWidget(effect5, e1Active && e2Active && e3Active && e4Active);
        toggleWidget(params5, e1Active && e2Active && e3Active && e4Active && e5Active);
        updateParamPlaceholder(effect5, params5);
        const hasSam3 = (sam3Target == null ? void 0 : sam3Target.value) && sam3Target.value.trim();
        toggleWidget(sam3Effect, !!hasSam3);
        fitHeight();
      }
      updateVisibility();
      if (presetW) {
        const origPreset = presetW.callback;
        presetW.callback = function(...args) {
          origPreset == null ? void 0 : origPreset.apply(this, args);
          applyPreset(presetW.value);
        };
      }
      for (const [eW, pW] of [
        [effect1, params1],
        [effect2, params2],
        [effect3, params3],
        [effect4, params4],
        [effect5, params5]
      ]) {
        if (eW) {
          const orig = eW.callback;
          let prevSkill = stripCategory(eW.value);
          eW.callback = function(...args) {
            orig == null ? void 0 : orig.apply(this, args);
            const newSkill = stripCategory(eW.value);
            if (newSkill !== prevSkill && pW) {
              pW.value = "";
            }
            prevSkill = newSkill;
            autoFillDefaults(eW, pW);
            updateVisibility();
          };
        }
      }
      if (sam3Target) {
        const origDraw = sam3Target.draw;
        let lastVal = sam3Target.value;
        sam3Target.draw = function(...args) {
          origDraw == null ? void 0 : origDraw.apply(this, args);
          if (sam3Target.value !== lastVal) {
            lastVal = sam3Target.value;
            updateVisibility();
          }
        };
      }
      node._ffmpegaApplyCustomPreset = applyCustomPreset;
      node._ffmpegaApplyPreset = applyPreset;
      node._ffmpegaStripCategory = stripCategory;
      const origOnConfigure = node.onConfigure;
      node.onConfigure = function(info) {
        origOnConfigure == null ? void 0 : origOnConfigure.apply(this, [info]);
        updateVisibility();
      };
      return result;
    };
    let _customEffectsPresets = [];
    fetch(api.apiURL("/ffmpega/effects_presets")).then((r) => r.json()).then((data) => {
      _customEffectsPresets = Array.isArray(data) ? data : [];
    }).catch(() => {
      _customEffectsPresets = [];
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
      var _a, _b;
      origGetMenu == null ? void 0 : origGetMenu.apply(this, arguments);
      const self = this;
      const captureState = () => {
        var _a2, _b2, _c, _d, _e, _f, _g, _h;
        const strip = self._ffmpegaStripCategory || ((n) => n);
        const cfg = {};
        const slots = ["effect_1", "effect_2", "effect_3", "effect_4", "effect_5"];
        const paramSlots = ["effect_1_params", "effect_2_params", "effect_3_params", "effect_4_params", "effect_5_params"];
        for (let i = 0; i < slots.length; i++) {
          const eW = (_a2 = self.widgets) == null ? void 0 : _a2.find((w) => w.name === slots[i]);
          const pW = (_b2 = self.widgets) == null ? void 0 : _b2.find((w) => w.name === paramSlots[i]);
          if (eW) cfg[slots[i]] = strip(eW.value);
          if (pW && ((_c = pW.value) == null ? void 0 : _c.trim())) {
            try {
              cfg[paramSlots[i]] = JSON.parse(pW.value);
            } catch {
              cfg[paramSlots[i]] = pW.value;
            }
          }
        }
        const sam3 = (_d = self.widgets) == null ? void 0 : _d.find((w) => w.name === "sam3_target");
        const sam3e = (_e = self.widgets) == null ? void 0 : _e.find((w) => w.name === "sam3_effect");
        if ((_f = sam3 == null ? void 0 : sam3.value) == null ? void 0 : _f.trim()) cfg.sam3_target = sam3.value;
        if (sam3e == null ? void 0 : sam3e.value) cfg.sam3_effect = sam3e.value;
        const raw = (_g = self.widgets) == null ? void 0 : _g.find((w) => w.name === "raw_ffmpeg");
        if ((_h = raw == null ? void 0 : raw.value) == null ? void 0 : _h.trim()) cfg.raw_ffmpeg = raw.value;
        return cfg;
      };
      const saveCustom = async () => {
        const name = prompt("Preset name:");
        if (!(name == null ? void 0 : name.trim())) return;
        const preset = { name: name.trim(), ...captureState() };
        const idx = _customEffectsPresets.findIndex((p) => p.name === preset.name);
        if (idx >= 0) {
          if (!confirm(`Preset "${preset.name}" already exists. Overwrite?`)) return;
          _customEffectsPresets[idx] = preset;
        } else {
          _customEffectsPresets.push(preset);
        }
        try {
          await fetch(api.apiURL("/ffmpega/effects_presets"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(_customEffectsPresets)
          });
          flashNode(self, "#4a7a4a");
        } catch {
          flashNode(self, "#7a4a4a");
        }
      };
      const deleteCustom = async (presetName) => {
        const idx = _customEffectsPresets.findIndex((p) => p.name === presetName);
        if (idx < 0) return;
        if (!confirm(`Are you sure you want to delete the preset "${presetName}"?`)) return;
        _customEffectsPresets.splice(idx, 1);
        try {
          await fetch(api.apiURL("/ffmpega/effects_presets"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(_customEffectsPresets)
          });
          flashNode(self, "#4a7a4a");
        } catch {
          flashNode(self, "#7a4a4a");
        }
      };
      const presetItems = [];
      const presetW = (_a = self.widgets) == null ? void 0 : _a.find((w) => w.name === "preset");
      const presetNames = ((_b = presetW == null ? void 0 : presetW.options) == null ? void 0 : _b.values) || [];
      const categoryMap = {};
      const categoryOrder = [];
      for (const pName of presetNames) {
        if (pName === "none") continue;
        const match = pName.match(/^(\S+)\s/);
        const cat = match ? match[1] : "Other";
        if (!categoryMap[cat]) {
          categoryMap[cat] = [];
          categoryOrder.push(cat);
        }
        categoryMap[cat].push({
          content: pName,
          callback: () => {
            var _a2;
            if (presetW) presetW.value = pName;
            (_a2 = self._ffmpegaApplyPreset) == null ? void 0 : _a2.call(self, pName);
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
      if (_customEffectsPresets.length > 0) {
        for (const p of _customEffectsPresets) {
          presetItems.push({
            content: `⭐ ${p.name}`,
            submenu: {
              options: [
                {
                  content: "✅ Load",
                  callback: () => {
                    var _a2;
                    (_a2 = self._ffmpegaApplyCustomPreset) == null ? void 0 : _a2.call(self, p);
                    flashNode(self, "#4a7a4a");
                  }
                },
                {
                  content: "🗑️ Delete",
                  callback: () => deleteCustom(p.name)
                }
              ]
            }
          });
        }
      }
      options.unshift(
        {
          content: "💾 Save Current as Preset",
          callback: () => saveCustom()
        },
        {
          content: "🎨 Load Preset",
          submenu: {
            options: presetItems
          }
        },
        {
          content: "🧹 Clear All Effects",
          callback: () => {
            var _a2, _b2, _c, _d, _e;
            for (const name of ["effect_1", "effect_2", "effect_3", "effect_4", "effect_5"]) {
              const w = (_a2 = self.widgets) == null ? void 0 : _a2.find((ww) => ww.name === name);
              if (w) w.value = "none";
            }
            for (const name of ["effect_1_params", "effect_2_params", "effect_3_params", "effect_4_params", "effect_5_params", "raw_ffmpeg", "sam3_target"]) {
              const w = (_b2 = self.widgets) == null ? void 0 : _b2.find((ww) => ww.name === name);
              if (w) w.value = "";
            }
            const sam3e = (_c = self.widgets) == null ? void 0 : _c.find((ww) => ww.name === "sam3_effect");
            if (sam3e) sam3e.value = "blur";
            const pw = (_d = self.widgets) == null ? void 0 : _d.find((ww) => ww.name === "preset");
            if (pw) pw.value = "none";
            for (const name of ["effect_1", "effect_2", "effect_3", "effect_4", "effect_5"]) {
              const w = (_e = self.widgets) == null ? void 0 : _e.find((ww) => ww.name === name);
              if (w == null ? void 0 : w.callback) w.callback(w.value);
            }
            flashNode(self, "#4a7a4a");
          }
        },
        null
        // separator
      );
    };
  }
});
