import { app } from "../../scripts/app.js";

/**
 * FFMPEGA Effects Builder node UI extensions.
 *
 * Features:
 * - Preset auto-populate: selecting a preset fills effect slots + params
 * - Param auto-fill: selecting an effect fills params with registry defaults
 * - Dynamic widget visibility: effect_2/3 expand as needed
 * - SAM3 fields show contextually
 * - Internal widgets (_presets_json, _defaults_json) are hidden
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

            // Effect dropdowns — update visibility + auto-fill
            for (const [eW, pW] of [[effect1, params1], [effect2, params2], [effect3, params3]]) {
                if (eW) {
                    const orig = eW.callback;
                    eW.callback = function (...args) {
                        orig?.apply(this, args);
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

            return result;
        };
    },
});
