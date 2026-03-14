/**
 * FFMPEGA Shader Overlay node context-menu extension.
 *
 * Features:
 * - Right-click context menu with categorized shader preset picker
 * - Custom save/load/delete for user shader presets via API
 * - Quick intensity selector (25%/50%/75%/100%)
 * - Reset to none
 * - Node theming (blue accent)
 *
 * Modelled after ffmpega_effects_ui.ts context-menu pattern.
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
    _origType?: string;
    _origComputeSize?: (width: number) => [number, number];
}

interface ComfyNode {
    widgets?: ComfyWidget[];
    size: [number, number];
    color?: string;
    bgcolor?: string;
    graph?: { setDirtyCanvas(fg: boolean, bg?: boolean): void };
    setSize(size: [number, number]): void;
    setDirtyCanvas(fg: boolean, bg: boolean): void;
    computeSize(size?: [number, number]): [number, number];
    _isFlashing?: boolean;
}

interface ShaderPresetConfig {
    name?: string;
    preset?: string;
    intensity?: number;
    custom_shader_path?: string;
    sam3_target?: string;
    [key: string]: unknown;
}

// ─── Extension ──────────────────────────────────────────────────────────

app.registerExtension({
    name: "FFMPEGA.ShaderOverlayUI",

    async beforeRegisterNodeDef(nodeType: any, nodeData: any, _app: any) {
        if (nodeData.name !== "FFMPEGAShaderOverlay") return;

        // --- Node styling ---
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (this: ComfyNode) {
            const result = onNodeCreated?.apply(this, arguments as any);
            this.color = "#2a3a5a";
            this.bgcolor = "#1a2a4a";
            return result;
        };

        // --- Custom presets (fetched eagerly) ---
        let _customShaderPresets: ShaderPresetConfig[] = [];
        fetch(api.apiURL("/ffmpega/shader_presets"))
            .then((r: Response) => r.json())
            .then((data: unknown) => { _customShaderPresets = Array.isArray(data) ? data : []; })
            .catch(() => { _customShaderPresets = []; });

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

        // --- Context menu ---
        const origGetMenu = nodeType.prototype.getExtraMenuOptions;

        nodeType.prototype.getExtraMenuOptions = function (this: ComfyNode, _: any, options: any[]) {
            origGetMenu?.apply(this, arguments as any);
            const self = this;

            // Widget helpers
            const findW = (name: string): ComfyWidget | undefined =>
                self.widgets?.find((w: ComfyWidget) => w.name === name);

            const presetW = findW("preset");
            const intensityW = findW("intensity");
            const customPathW = findW("custom_shader_path");
            const sam3TargetW = findW("sam3_target");

            // Capture current widget state
            const captureState = (): ShaderPresetConfig => ({
                preset: (presetW?.value ?? "none") as string,
                intensity: (intensityW?.value ?? 1.0) as number,
                custom_shader_path: (customPathW?.value ?? "") as string,
                sam3_target: (sam3TargetW?.value ?? "") as string,
            });

            // Apply a saved preset to widgets
            const applyState = (cfg: ShaderPresetConfig): void => {
                if (presetW && cfg.preset !== undefined) presetW.value = cfg.preset;
                if (intensityW && cfg.intensity !== undefined) intensityW.value = cfg.intensity;
                if (customPathW && cfg.custom_shader_path !== undefined) customPathW.value = cfg.custom_shader_path;
                if (sam3TargetW && cfg.sam3_target !== undefined) sam3TargetW.value = cfg.sam3_target;
            };

            // Save custom preset
            const saveCustom = async (): Promise<void> => {
                const name = prompt("Shader preset name:");
                if (!name?.trim()) return;
                const preset: ShaderPresetConfig = { name: name.trim(), ...captureState() };
                const idx = _customShaderPresets.findIndex((p) => p.name === preset.name);
                if (idx >= 0) _customShaderPresets[idx] = preset;
                else _customShaderPresets.push(preset);
                try {
                    await fetch(api.apiURL("/ffmpega/shader_presets"), {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(_customShaderPresets),
                    });
                    flashNode(self, "#4a7a4a");
                } catch { flashNode(self, "#7a4a4a"); }
            };

            // Delete custom preset
            const deleteCustom = async (presetName: string): Promise<void> => {
                const idx = _customShaderPresets.findIndex((p) => p.name === presetName);
                if (idx < 0) return;
                _customShaderPresets.splice(idx, 1);
                try {
                    await fetch(api.apiURL("/ffmpega/shader_presets"), {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(_customShaderPresets),
                    });
                    flashNode(self, "#4a7a4a");
                } catch { flashNode(self, "#7a4a4a"); }
            };

            // --- Build categorized preset submenu ---
            const presetItems: any[] = [];
            const presetValues: string[] = (presetW?.options as any)?.values || [];

            // Parse ── Category ── headers from the dropdown values
            const categoryMap: Record<string, any[]> = {};
            const categoryOrder: string[] = [];
            let currentCategory = "Other";

            for (const val of presetValues) {
                if (val === "none") continue;

                // Category header line: ── 🎬 Classic ──
                if (val.startsWith("──")) {
                    currentCategory = val.replace(/^──\s*/, "").replace(/\s*──$/, "");
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
                    },
                });
            }

            // Build categorized submenu items
            for (const cat of categoryOrder) {
                const items = categoryMap[cat];
                if (items.length === 1) {
                    presetItems.push(items[0]);
                } else {
                    presetItems.push({
                        content: `${cat} (${items.length})`,
                        submenu: { options: items },
                    });
                }
            }

            // Custom presets with load/delete submenu
            if (_customShaderPresets.length > 0) {
                presetItems.push(null); // separator
                for (const p of _customShaderPresets) {
                    presetItems.push({
                        content: `⭐ ${p.name}`,
                        submenu: {
                            options: [
                                {
                                    content: "✅ Load",
                                    callback: () => {
                                        applyState(p);
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

            // --- Quick intensity selector ---
            const intensityItems = [
                { label: "25%", val: 0.25 },
                { label: "50%", val: 0.50 },
                { label: "75%", val: 0.75 },
                { label: "100%", val: 1.00 },
            ].map(({ label, val }) => ({
                content: `🔊 ${label}`,
                callback: () => {
                    if (intensityW) intensityW.value = val;
                    flashNode(self, "#4a7a4a");
                },
            }));

            // --- Add menu items ---
            options.unshift(
                {
                    content: "💾 Save Current as Preset",
                    callback: () => saveCustom(),
                },
                {
                    content: "✨ Select Shader",
                    submenu: {
                        options: presetItems,
                    },
                },
                {
                    content: "🔊 Set Intensity",
                    submenu: {
                        options: intensityItems,
                    },
                },
                {
                    content: "🧹 Reset to None",
                    callback: () => {
                        if (presetW) presetW.value = "none";
                        if (intensityW) intensityW.value = 1.0;
                        if (customPathW) customPathW.value = "";
                        if (sam3TargetW) sam3TargetW.value = "";
                        flashNode(self, "#4a7a4a");
                    },
                },
                null, // separator
            );
        };
    },
});
