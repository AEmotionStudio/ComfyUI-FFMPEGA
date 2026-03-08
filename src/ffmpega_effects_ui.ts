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
 *
 * Faithful port of ffmpega_effects_ui.js with full type annotations.
 */

import { app } from "comfyui/app";
import { api } from "comfyui/api";

// ─── Types ──────────────────────────────────────────────────────────────

interface ComfyWidget {
    name: string;
    type: string;
    value: any;
    options?: Record<string, any>;
    element?: HTMLElement;
    hidden?: boolean;
    callback?: (...args: any[]) => void;
    computeSize?: (width: number) => [number, number];
    draw?: (...args: any[]) => void;
    _origType?: string;
    _origComputeSize?: (width: number) => [number, number];
}

interface ComfyNode {
    widgets?: ComfyWidget[];
    size: [number, number];
    color?: string;
    bgcolor?: string;
    properties?: Record<string, unknown>;
    graph?: { setDirtyCanvas(fg: boolean, bg?: boolean): void };
    setSize(size: [number, number]): void;
    setDirtyCanvas(fg: boolean, bg: boolean): void;
    computeSize(size?: [number, number]): [number, number];
    _isFlashing?: boolean;
    _ffmpegaApplyCustomPreset?: (cfg: PresetConfig) => void;
    _ffmpegaApplyPreset?: (name: string) => void;
    _ffmpegaStripCategory?: (name: string) => string;
}

interface PresetConfig {
    name?: string;
    effect_1?: string;
    effect_1_params?: string | Record<string, unknown>;
    effect_2?: string;
    effect_2_params?: string | Record<string, unknown>;
    effect_3?: string;
    effect_3_params?: string | Record<string, unknown>;
    sam3_target?: string;
    sam3_effect?: string;
    raw_ffmpeg?: string;
    [key: string]: unknown;
}

// ─── Extension ──────────────────────────────────────────────────────────

app.registerExtension({
    name: "FFMPEGA.EffectsUI",

    async beforeRegisterNodeDef(nodeType: any, nodeData: any, _app: any) {
        if (nodeData.name !== "FFMPEGAEffects") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;

        nodeType.prototype.onNodeCreated = function (this: ComfyNode) {
            const result = onNodeCreated?.apply(this, arguments as any);

            // Node styling — purple theme
            this.color = "#3a2a5a";
            this.bgcolor = "#2a1a4a";

            const node = this;

            // --- Widget references ---
            const findW = (name: string): ComfyWidget | undefined =>
                this.widgets?.find((w: ComfyWidget) => w.name === name);

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
            let presetData: Record<string, PresetConfig> = {};
            let defaultsData: Record<string, string> = {};
            try {
                if (presetsJsonW?.value) presetData = JSON.parse(presetsJsonW.value as string);
            } catch (e) { console.warn("FFMPEGA Effects: failed to parse presets", e); }
            try {
                if (defaultsJsonW?.value) defaultsData = JSON.parse(defaultsJsonW.value as string);
            } catch (e) { console.warn("FFMPEGA Effects: failed to parse defaults", e); }

            // --- Show/hide helpers ---
            function toggleWidget(widget: ComfyWidget | undefined, show: boolean): void {
                if (!widget) return;
                if (!widget._origType) {
                    widget._origType = widget.type;
                    widget._origComputeSize = widget.computeSize;
                }
                if (show) {
                    widget.type = widget._origType!;
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

            function fitHeight(): void {
                node.setSize([
                    node.size[0],
                    node.computeSize([node.size[0], node.size[1]])[1]
                ]);
                node?.graph?.setDirtyCanvas(true);
            }

            function stripCategory(name: string): string {
                if (!name) return "none";
                const idx = name.lastIndexOf("/");
                return idx >= 0 ? name.slice(idx + 1) : name;
            }

            function hasEffect(widget: ComfyWidget | undefined): boolean {
                return !!(widget?.value) && stripCategory(widget.value as string) !== "none";
            }

            /**
             * Find the full categorized dropdown entry for a raw skill name.
             * "blur" → "🎨 Visual/blur"
             */
            function findCategorized(skillName: string, effectWidget: ComfyWidget | undefined): string {
                if (!skillName || skillName === "none") return "none";
                const suffix = "/" + skillName;
                const options = (effectWidget?.options as any)?.values || [];
                for (const opt of options) {
                    if (opt.endsWith(suffix)) return opt;
                }
                return "none";
            }

            /**
             * Update param placeholder to show skill name context.
             */
            function updateParamPlaceholder(effectWidget: ComfyWidget | undefined, paramWidget: ComfyWidget | undefined): void {
                if (!effectWidget || !paramWidget) return;
                const skill = stripCategory(effectWidget.value as string);
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
            function applyPreset(presetName: string): void {
                if (!presetName || presetName === "none") return;
                const cfg = presetData[presetName];
                if (!cfg) return;

                // Map: widget name → [effectWidget, paramsWidget]
                const slots: [string, ComfyWidget | undefined, string, ComfyWidget | undefined][] = [
                    ["effect_1", effect1, "effect_1_params", params1],
                    ["effect_2", effect2, "effect_2_params", params2],
                    ["effect_3", effect3, "effect_3_params", params3],
                ];

                for (const [eName, eW, pName, pW] of slots) {
                    if (cfg[eName] !== undefined && eW) {
                        const catName = findCategorized(cfg[eName] as string, eW);
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
            function applyCustomPreset(cfg: PresetConfig): void {
                if (!cfg) return;
                const slots: [string, ComfyWidget | undefined, string, ComfyWidget | undefined][] = [
                    ["effect_1", effect1, "effect_1_params", params1],
                    ["effect_2", effect2, "effect_2_params", params2],
                    ["effect_3", effect3, "effect_3_params", params3],
                ];
                for (const [eName, eW, pName, pW] of slots) {
                    if (cfg[eName] !== undefined && eW) {
                        const catName = findCategorized(cfg[eName] as string, eW);
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
            function autoFillDefaults(effectWidget: ComfyWidget | undefined, paramWidget: ComfyWidget | undefined): void {
                if (!effectWidget || !paramWidget) return;
                const skill = stripCategory(effectWidget.value as string);
                // Only auto-fill if param field is empty (don't overwrite user input)
                if (paramWidget.value && (paramWidget.value as string).trim()) return;
                if (skill && skill !== "none" && defaultsData[skill]) {
                    paramWidget.value = defaultsData[skill];
                }
            }

            // --- Dynamic visibility ---
            function updateVisibility(): void {
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

                const hasSam3 = sam3Target?.value && (sam3Target.value as string).trim();
                toggleWidget(sam3Effect, !!hasSam3);

                fitHeight();
            }

            // Initial state
            updateVisibility();

            // --- Wire callbacks ---
            // Preset dropdown
            if (presetW) {
                const origPreset = presetW.callback;
                presetW.callback = function (...args: any[]) {
                    origPreset?.apply(this, args);
                    applyPreset(presetW.value as string);
                };
            }

            // Effect dropdowns — update visibility + clear stale params + auto-fill
            for (const [eW, pW] of [[effect1, params1], [effect2, params2], [effect3, params3]] as const) {
                if (eW) {
                    const orig = eW.callback;
                    let prevSkill = stripCategory(eW.value as string);
                    eW.callback = function (...args: any[]) {
                        orig?.apply(this, args);
                        const newSkill = stripCategory(eW.value as string);
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
                sam3Target.draw = function (...args: any[]) {
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
        let _customEffectsPresets: PresetConfig[] = [];

        // Eagerly fetch custom presets
        fetch(api.apiURL("/ffmpega/effects_presets"))
            .then((r: Response) => r.json())
            .then((data: unknown) => { _customEffectsPresets = Array.isArray(data) ? data : []; })
            .catch(() => { _customEffectsPresets = []; });

        function flashNode(node: ComfyNode, color: string): void {
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
        nodeType.prototype.getExtraMenuOptions = function (this: ComfyNode, _: any, options: any[]) {
            origGetMenu?.apply(this, arguments as any);
            const self = this;

            // Capture current state as a preset config
            const captureState = (): PresetConfig => {
                const strip = self._ffmpegaStripCategory || ((n: string) => n);
                const cfg: PresetConfig = {};
                const slots = ["effect_1", "effect_2", "effect_3"];
                const paramSlots = ["effect_1_params", "effect_2_params", "effect_3_params"];
                for (let i = 0; i < slots.length; i++) {
                    const eW = self.widgets?.find((w: ComfyWidget) => w.name === slots[i]);
                    const pW = self.widgets?.find((w: ComfyWidget) => w.name === paramSlots[i]);
                    if (eW) cfg[slots[i]] = strip(eW.value as string);
                    if (pW && (pW.value as string)?.trim()) {
                        try {
                            cfg[paramSlots[i]] = JSON.parse(pW.value as string);
                        } catch {
                            cfg[paramSlots[i]] = pW.value as string;
                        }
                    }
                }
                const sam3 = self.widgets?.find((w: ComfyWidget) => w.name === "sam3_target");
                const sam3e = self.widgets?.find((w: ComfyWidget) => w.name === "sam3_effect");
                if ((sam3?.value as string)?.trim()) cfg.sam3_target = sam3!.value as string;
                if (sam3e?.value) cfg.sam3_effect = sam3e.value as string;
                const raw = self.widgets?.find((w: ComfyWidget) => w.name === "raw_ffmpeg");
                if ((raw?.value as string)?.trim()) cfg.raw_ffmpeg = raw!.value as string;
                return cfg;
            };

            const saveCustom = async (): Promise<void> => {
                const name = prompt("Preset name:");
                if (!name?.trim()) return;
                const preset: PresetConfig = { name: name.trim(), ...captureState() };
                const idx = _customEffectsPresets.findIndex((p: PresetConfig) => p.name === preset.name);
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

            const deleteCustom = async (presetName: string): Promise<void> => {
                const idx = _customEffectsPresets.findIndex((p: PresetConfig) => p.name === presetName);
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
            const presetItems: any[] = [];

            // Built-in presets (from Python _PRESETS via dropdown)
            const presetW = self.widgets?.find((w: ComfyWidget) => w.name === "preset");
            const presetNames: string[] = (presetW?.options as any)?.values || [];
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
                                    callback: () => deleteCustom(p.name!),
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
                            const w = self.widgets?.find((ww: ComfyWidget) => ww.name === name);
                            if (w) w.value = "none";
                        }
                        for (const name of ["effect_1_params", "effect_2_params", "effect_3_params", "raw_ffmpeg", "sam3_target"]) {
                            const w = self.widgets?.find((ww: ComfyWidget) => ww.name === name);
                            if (w) w.value = "";
                        }
                        const sam3e = self.widgets?.find((ww: ComfyWidget) => ww.name === "sam3_effect");
                        if (sam3e) sam3e.value = "blur";
                        const pw = self.widgets?.find((ww: ComfyWidget) => ww.name === "preset");
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
