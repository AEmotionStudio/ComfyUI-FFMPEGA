import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

/**
 * FFMPEGA Effects Builder node UI extensions.
 *
 * Features:
 * - Preset auto-populate: selecting a preset fills effect slots + params
 * - Param auto-fill: selecting an effect fills params with registry defaults
 * - Dynamic widget visibility: effect_2/3 expand as needed
 * - SAM3 fields show contextually
 * - Internal widgets (_presets_json, _defaults_json) are hidden
 * - Context menu presets with custom save/load/delete
 */

app.registerExtension({
    name: "FFMPEGA.EffectsUI",

    async beforeRegisterNodeDef(nodeType, nodeData, _app) {
        if (nodeData.name !== "FFMPEGAEffects") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;

        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated?.apply(this, arguments);

            // Node styling — purple theme
            this.color = "#3a2a5a";
            this.bgcolor = "#2a1a4a";

            const node = this;

            // --- Widget references ---
            const findW = (name) => this.widgets?.find(w => w.name === name);

            const presetW = findW("preset");
            const effect1 = findW("effect_1");
            const params1 = findW("effect_1_params");
            const effect2 = findW("effect_2");
            const params2 = findW("effect_2_params");
            const effect3 = findW("effect_3");
            const params3 = findW("effect_3_params");
            const rawFfmpeg = findW("raw_ffmpeg");
            const sam3Target = findW("sam3_target");
            const sam3Effect = findW("sam3_effect");
            const presetsJsonW = findW("_presets_json");
            const defaultsJsonW = findW("_defaults_json");

            // --- Parse hidden data ---
            let presetData = {};
            let defaultsData = {};
            try {
                if (presetsJsonW?.value) presetData = JSON.parse(presetsJsonW.value);
            } catch (e) { console.warn("FFMPEGA Effects: failed to parse presets", e); }
            try {
                if (defaultsJsonW?.value) defaultsData = JSON.parse(defaultsJsonW.value);
            } catch (e) { console.warn("FFMPEGA Effects: failed to parse defaults", e); }

            // --- Show/hide helpers ---
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
                node.setSize([
                    node.size[0],
                    node.computeSize([node.size[0], node.size[1]])[1]
                ]);
                node?.graph?.setDirtyCanvas(true);
            }

            function stripCategory(name) {
                if (!name) return "none";
                const idx = name.lastIndexOf("/");
                return idx >= 0 ? name.slice(idx + 1) : name;
            }

            function hasEffect(widget) {
                return widget?.value && stripCategory(widget.value) !== "none";
            }

            /**
             * Find the full categorized dropdown entry for a raw skill name.
             * "blur" → "🎨 Visual/blur"
             */
            function findCategorized(skillName, effectWidget) {
                if (!skillName || skillName === "none") return "none";
                const suffix = "/" + skillName;
                const options = effectWidget?.options?.values || [];
                for (const opt of options) {
                    if (opt.endsWith(suffix)) return opt;
                }
                return "none";
            }

            /**
             * Update param placeholder to show skill name context.
             */
            function updateParamPlaceholder(effectWidget, paramWidget) {
                if (!effectWidget || !paramWidget) return;
                const skill = stripCategory(effectWidget.value);
                if (!skill || skill === "none") {
                    paramWidget.options = paramWidget.options || {};
                    paramWidget.options.placeholder = '{"key": "value"}';
                    return;
                }
                paramWidget.options = paramWidget.options || {};
                paramWidget.options.placeholder = `${skill} params (JSON)`;
            }

            // --- Hide internal widgets ---
            toggleWidget(presetsJsonW, false);
            toggleWidget(defaultsJsonW, false);

            // --- Preset auto-populate ---
            function applyPreset(presetName) {
                if (!presetName || presetName === "none") return;
                const cfg = presetData[presetName];
                if (!cfg) return;

                // Map: widget name → [effectWidget, paramsWidget]
                const slots = [
                    ["effect_1", effect1, "effect_1_params", params1],
                    ["effect_2", effect2, "effect_2_params", params2],
                    ["effect_3", effect3, "effect_3_params", params3],
                ];

                for (const [eName, eW, pName, pW] of slots) {
                    if (cfg[eName] !== undefined && eW) {
                        const catName = findCategorized(cfg[eName], eW);
                        eW.value = catName;
                    }
                    if (cfg[pName] !== undefined && pW) {
                        const v = cfg[pName];
                        // v may be a JSON string or already a string
                        pW.value = typeof v === "string" ? v : JSON.stringify(v);
                    }
                }

                // SAM3 fields
                if (cfg.sam3_target !== undefined && sam3Target) {
                    sam3Target.value = cfg.sam3_target;
                }
                if (cfg.sam3_effect !== undefined && sam3Effect) {
                    sam3Effect.value = cfg.sam3_effect;
                }

                updateVisibility();
            }

            /**
             * Apply a custom preset (same shape as presetData entries).
             */
            function applyCustomPreset(cfg) {
                if (!cfg) return;
                const slots = [
                    ["effect_1", effect1, "effect_1_params", params1],
                    ["effect_2", effect2, "effect_2_params", params2],
                    ["effect_3", effect3, "effect_3_params", params3],
                ];
                for (const [eName, eW, pName, pW] of slots) {
                    if (cfg[eName] !== undefined && eW) {
                        const catName = findCategorized(cfg[eName], eW);
                        eW.value = catName;
                    } else if (eW) {
                        eW.value = "none";
                    }
                    if (cfg[pName] !== undefined && pW) {
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

            // --- Auto-fill param defaults when effect changes ---
            function autoFillDefaults(effectWidget, paramWidget) {
                if (!effectWidget || !paramWidget) return;
                const skill = stripCategory(effectWidget.value);
                // Only auto-fill if param field is empty (don't overwrite user input)
                if (paramWidget.value && paramWidget.value.trim()) return;
                if (skill && skill !== "none" && defaultsData[skill]) {
                    paramWidget.value = defaultsData[skill];
                }
            }

            // --- Dynamic visibility ---
            function updateVisibility() {
                const e1Active = hasEffect(effect1);
                const e2Active = hasEffect(effect2);
                const e3Active = hasEffect(effect3);

                toggleWidget(params1, e1Active);
                updateParamPlaceholder(effect1, params1);

                toggleWidget(effect2, e1Active);
                toggleWidget(params2, e1Active && e2Active);
                updateParamPlaceholder(effect2, params2);

                toggleWidget(effect3, e1Active && e2Active);
                toggleWidget(params3, e1Active && e2Active && e3Active);
                updateParamPlaceholder(effect3, params3);

                const hasSam3 = sam3Target?.value && sam3Target.value.trim();
                toggleWidget(sam3Effect, !!hasSam3);

                fitHeight();
            }

            // Initial state
            updateVisibility();

            // --- Wire callbacks ---
            // Preset dropdown
            if (presetW) {
                const origPreset = presetW.callback;
                presetW.callback = function (...args) {
                    origPreset?.apply(this, args);
                    applyPreset(presetW.value);
                };
            }

            // Effect dropdowns — update visibility + clear stale params + auto-fill
            for (const [eW, pW] of [[effect1, params1], [effect2, params2], [effect3, params3]]) {
                if (eW) {
                    const orig = eW.callback;
                    let prevSkill = stripCategory(eW.value);
                    eW.callback = function (...args) {
                        orig?.apply(this, args);
                        const newSkill = stripCategory(eW.value);
                        // Clear params when switching to a different effect
                        if (newSkill !== prevSkill && pW) {
                            pW.value = "";
                        }
                        prevSkill = newSkill;
                        autoFillDefaults(eW, pW);
                        updateVisibility();
                    };
                }
            }

            // SAM3 target
            if (sam3Target) {
                const origDraw = sam3Target.draw;
                let lastVal = sam3Target.value;
                sam3Target.draw = function (...args) {
                    origDraw?.apply(this, args);
                    if (sam3Target.value !== lastVal) {
                        lastVal = sam3Target.value;
                        updateVisibility();
                    }
                };
            }

            // --- Store functions on node for context menu access ---
            node._ffmpegaApplyCustomPreset = applyCustomPreset;
            node._ffmpegaApplyPreset = applyPreset;
            node._ffmpegaStripCategory = stripCategory;

            return result;
        };

        // --- Context Menu Presets ---
        let _customEffectsPresets = [];

        // Eagerly fetch custom presets
        fetch(api.apiURL("/ffmpega/effects_presets"))
            .then(r => r.json())
            .then(data => { _customEffectsPresets = Array.isArray(data) ? data : []; })
            .catch(() => { _customEffectsPresets = []; });

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
        nodeType.prototype.getExtraMenuOptions = function (_, options) {
            origGetMenu?.apply(this, arguments);
            const self = this;

            // Capture current state as a preset config
            const captureState = () => {
                const strip = self._ffmpegaStripCategory || ((n) => n);
                const cfg = {};
                const slots = ["effect_1", "effect_2", "effect_3"];
                const paramSlots = ["effect_1_params", "effect_2_params", "effect_3_params"];
                for (let i = 0; i < slots.length; i++) {
                    const eW = self.widgets?.find(w => w.name === slots[i]);
                    const pW = self.widgets?.find(w => w.name === paramSlots[i]);
                    if (eW) cfg[slots[i]] = strip(eW.value);
                    if (pW && pW.value?.trim()) {
                        try {
                            cfg[paramSlots[i]] = JSON.parse(pW.value);
                        } catch {
                            cfg[paramSlots[i]] = pW.value;
                        }
                    }
                }
                const sam3 = self.widgets?.find(w => w.name === "sam3_target");
                const sam3e = self.widgets?.find(w => w.name === "sam3_effect");
                if (sam3?.value?.trim()) cfg.sam3_target = sam3.value;
                if (sam3e?.value) cfg.sam3_effect = sam3e.value;
                const raw = self.widgets?.find(w => w.name === "raw_ffmpeg");
                if (raw?.value?.trim()) cfg.raw_ffmpeg = raw.value;
                return cfg;
            };

            const saveCustom = async () => {
                const name = prompt("Preset name:");
                if (!name?.trim()) return;
                const preset = { name: name.trim(), ...captureState() };
                const idx = _customEffectsPresets.findIndex(p => p.name === preset.name);
                if (idx >= 0) _customEffectsPresets[idx] = preset;
                else _customEffectsPresets.push(preset);
                try {
                    await fetch(api.apiURL("/ffmpega/effects_presets"), {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(_customEffectsPresets),
                    });
                    flashNode(self, "#4a7a4a");
                } catch { flashNode(self, "#7a4a4a"); }
            };

            const deleteCustom = async (presetName) => {
                const idx = _customEffectsPresets.findIndex(p => p.name === presetName);
                if (idx < 0) return;
                _customEffectsPresets.splice(idx, 1);
                try {
                    await fetch(api.apiURL("/ffmpega/effects_presets"), {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(_customEffectsPresets),
                    });
                    flashNode(self, "#4a7a4a");
                } catch { flashNode(self, "#7a4a4a"); }
            };

            // Build preset submenu items
            const presetItems = [];

            // Built-in presets (from Python _PRESETS via dropdown)
            const presetW = self.widgets?.find(w => w.name === "preset");
            const presetNames = presetW?.options?.values || [];
            for (const pName of presetNames) {
                if (pName === "none") continue;
                presetItems.push({
                    content: pName,
                    callback: () => {
                        if (presetW) presetW.value = pName;
                        self._ffmpegaApplyPreset?.(pName);
                        flashNode(self, "#4a7a4a");
                    },
                });
            }

            // Custom presets
            if (_customEffectsPresets.length > 0) {
                for (const p of _customEffectsPresets) {
                    presetItems.push({
                        content: `⭐ ${p.name}`,
                        submenu: {
                            options: [
                                {
                                    content: "✅ Load",
                                    callback: () => {
                                        self._ffmpegaApplyCustomPreset?.(p);
                                        flashNode(self, "#4a7a4a");
                                    },
                                },
                                {
                                    content: "🗑️ Delete",
                                    callback: () => deleteCustom(p.name),
                                },
                            ],
                        },
                    });
                }
            }

            options.unshift(
                {
                    content: "💾 Save Current as Preset",
                    callback: () => saveCustom(),
                },
                {
                    content: "🎨 Load Preset",
                    submenu: {
                        options: presetItems,
                    },
                },
                {
                    content: "🧹 Clear All Effects",
                    callback: () => {
                        // Reset all effect slots + params + SAM3 + raw
                        for (const name of ["effect_1", "effect_2", "effect_3"]) {
                            const w = self.widgets?.find(ww => ww.name === name);
                            if (w) w.value = "none";
                        }
                        for (const name of ["effect_1_params", "effect_2_params", "effect_3_params", "raw_ffmpeg", "sam3_target"]) {
                            const w = self.widgets?.find(ww => ww.name === name);
                            if (w) w.value = "";
                        }
                        const sam3e = self.widgets?.find(ww => ww.name === "sam3_effect");
                        if (sam3e) sam3e.value = "blur";
                        const pw = self.widgets?.find(ww => ww.name === "preset");
                        if (pw) pw.value = "none";
                        // Trigger visibility update
                        self._ffmpegaApplyCustomPreset?.({});
                        flashNode(self, "#4a7a4a");
                    },
                },
                null, // separator
            );
        };
    },
});
