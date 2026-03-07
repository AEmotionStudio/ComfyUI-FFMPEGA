/**
 * FFMPEGATextInput node UI handler.
 *
 * Features:
 * - Color picker DOM widget (replaces STRING widget)
 * - Preset system (built-in + custom presets)
 * - Context menu with save/load/clear
 */

import { app } from "comfyui/app";
import { api } from "comfyui/api";
import { flashNode } from "@ffmpega/shared/ui_helpers";
import type {
    ComfyNodeType, ComfyNodeData, ComfyNode,
    ComfyWidget, ComfyMenuOption,
} from "@ffmpega/types/comfyui";

// ---- Type definitions ----

/** A text preset — either built-in or user-created */
interface TextPreset {
    name: string;
    auto_mode?: boolean;
    mode?: string;
    position?: string;
    font_size?: number;
    font_color?: string;
    text?: string;
    start_time?: number;
    end_time?: number;
    [key: string]: unknown;
}

/** Extended node with color picker refs */
interface TextInputNode extends ComfyNode {
    _ffmpegaColorInput?: HTMLInputElement;
    _ffmpegaHexLabel?: HTMLSpanElement;
    addDOMWidget(name: string, type: string, el: HTMLElement, opts?: Record<string, unknown>): ComfyWidget;
}

/** Extended widget with inputEl (ComfyUI textarea/input) */
interface TextWidget extends ComfyWidget {
    inputEl?: HTMLInputElement | HTMLTextAreaElement;
    getValue?: () => unknown;
}

// ---- Constants ----

const BUILTIN_PRESETS: TextPreset[] = [
    {
        name: "📄 SRT Subtitle Example",
        auto_mode: false, mode: "subtitle",
        position: "bottom_center", font_size: 28, font_color: "#FFFFFF",
        text: "1\n00:00:01,000 --> 00:00:04,000\nThis is the first subtitle line.\n\n2\n00:00:05,000 --> 00:00:08,000\nAnd here is the second one.\n\n3\n00:00:09,000 --> 00:00:12,000\nEdit these timestamps to match your video!",
    },
    {
        name: "🎬 Cinematic Subtitles",
        auto_mode: false, mode: "subtitle",
        position: "bottom_center", font_size: 28, font_color: "#FFFFFF",
        text: "1\n00:00:01,000 --> 00:00:03,500\nThe world was never the same.\n\n2\n00:00:04,000 --> 00:00:07,000\nSomething had changed — forever.",
    },
    {
        name: "💧 Bold Watermark",
        auto_mode: false, mode: "watermark",
        position: "bottom_right", font_size: 18, font_color: "#CCCCCC",
        text: "© Your Name",
    },
    {
        name: "🎯 Title Card",
        auto_mode: false, mode: "title_card",
        position: "center", font_size: 72, font_color: "#FFFFFF",
        text: "YOUR TITLE HERE",
    },
    {
        name: "📱 Social Caption",
        auto_mode: false, mode: "subtitle",
        position: "bottom_center", font_size: 36, font_color: "#FFE800",
        text: "1\n00:00:00,500 --> 00:00:03,000\nWait for it... 👀\n\n2\n00:00:03,500 --> 00:00:06,000\nDid you see that?! 🔥",
    },
    {
        name: "😂 Meme Text",
        auto_mode: false, mode: "overlay",
        position: "top", font_size: 48, font_color: "#FFFFFF",
        text: "TOP TEXT GOES HERE",
    },
    {
        name: "📐 Minimal Lower Third",
        auto_mode: false, mode: "overlay",
        position: "bottom_left", font_size: 22, font_color: "#DDDDDD",
        text: "Speaker Name\nJob Title",
    },
    {
        name: "©️ Copyright Notice",
        auto_mode: false, mode: "watermark",
        position: "bottom_center", font_size: 16, font_color: "#AAAAAA",
        text: "© 2025 All Rights Reserved",
    },
    {
        name: "🎬 Credits Roll",
        auto_mode: false, mode: "subtitle",
        position: "center", font_size: 32, font_color: "#FFFFFF",
        text: "1\n00:00:01,000 --> 00:00:03,000\nDirected by\nYour Name\n\n2\n00:00:04,000 --> 00:00:06,000\nProduced by\nYour Name\n\n3\n00:00:07,000 --> 00:00:09,000\nMusic by\nArtist Name",
    },
    {
        name: "📌 Chapter Marker",
        auto_mode: false, mode: "overlay",
        position: "top_left", font_size: 24, font_color: "#FFFFFF",
        text: "Chapter 1: Introduction",
        start_time: 0.0, end_time: 5.0,
    },
];

/** Priority order for applying preset widget values */
const PRESET_APPLY_ORDER = [
    "auto_mode", "mode", "position", "font_size", "font_color",
    "text", "start_time", "end_time",
] as const;

// ---- Helpers ----

/**
 * Apply a preset to a TextInput node's widgets.
 */
function applyPreset(node: TextInputNode, preset: TextPreset): void {
    // Build ordered key list: priority order first, then remaining keys
    const keys = (PRESET_APPLY_ORDER as readonly string[]).filter(k => k in preset);
    for (const k of Object.keys(preset)) {
        if (k !== "name" && !keys.includes(k)) keys.push(k);
    }

    for (const key of keys) {
        const w = node.widgets?.find(
            (ww: ComfyWidget) => ww.name === key,
        ) as TextWidget | undefined;
        if (!w) continue;
        const val = preset[key];

        // Set the widget's internal value
        w.value = val;

        if (key === "font_color") {
            // Update color picker DOM elements directly
            // (w.setValue is wrapped by DOMWidgetImpl and crashes)
            try {
                const ci = node._ffmpegaColorInput;
                const hl = node._ffmpegaHexLabel;
                if (ci && typeof val === "string" && val.startsWith("#")) {
                    ci.value = val;
                    if (hl) {
                        hl.textContent = val.toUpperCase();
                        hl.style.color = "#ccc";
                    }
                }
            } catch { /* ignore */ }
        } else if (w.inputEl) {
            // ComfyUI stores textarea/input as w.inputEl
            (w.inputEl as HTMLInputElement).value = String(val);
            w.inputEl.dispatchEvent(new Event("input", { bubbles: true }));
        } else if (w.element) {
            // DOM widget — element could BE the input or contain it
            const el = w.element;
            const tag = el.tagName?.toLowerCase();
            if (tag === "textarea" || tag === "input") {
                (el as HTMLInputElement).value = String(val);
                el.dispatchEvent(new Event("input", { bubbles: true }));
            } else {
                const input = el.querySelector?.("textarea, input") as HTMLInputElement | null;
                if (input) {
                    input.value = String(val);
                    input.dispatchEvent(new Event("input", { bubbles: true }));
                }
            }
        }
    }

    // Force visual refresh
    node.setDirtyCanvas(true, true);
    app.graph.setDirtyCanvas(true, true);
    flashNode(node, "#4a7a4a");
}

/**
 * Save current widget values as a custom preset.
 */
async function saveCustomPreset(
    node: TextInputNode,
    customPresets: TextPreset[],
): Promise<void> {
    const name = prompt("Preset name:");
    if (!name?.trim()) return;

    const preset: TextPreset = { name: name.trim() };
    for (const key of ["auto_mode", "mode", "position", "font_size", "font_color"] as const) {
        const w = node.widgets?.find(
            (ww: ComfyWidget) => ww.name === key,
        ) as TextWidget | undefined;
        if (w) {
            preset[key] = typeof w.getValue === "function" ? w.getValue() : w.value;
        }
    }

    // Replace if same name exists
    const idx = customPresets.findIndex(p => p.name === preset.name);
    if (idx >= 0) {
        customPresets[idx] = preset;
    } else {
        customPresets.push(preset);
    }

    try {
        await fetch(api.apiURL("/ffmpega/text_presets"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(customPresets),
        });
        flashNode(node, "#4a7a4a");
    } catch (err) {
        console.warn("FFMPEGA: preset save failed", err);
        flashNode(node, "#7a4a4a");
    }
}

/**
 * Delete a custom preset by name.
 */
async function deleteCustomPreset(
    node: TextInputNode,
    customPresets: TextPreset[],
    presetName: string,
): Promise<void> {
    const idx = customPresets.findIndex(p => p.name === presetName);
    if (idx < 0) return;
    customPresets.splice(idx, 1);
    try {
        await fetch(api.apiURL("/ffmpega/text_presets"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(customPresets),
        });
        flashNode(node, "#4a7a4a");
    } catch {
        flashNode(node, "#7a4a4a");
    }
}

// ---- Registration ----

/**
 * Register FFMPEGATextInput node UI.
 */
export function registerTextInputNode(
    nodeType: ComfyNodeType,
    nodeData: ComfyNodeData,
): void {
    if (nodeData.name !== "FFMPEGATextInput") return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;

    nodeType.prototype.onNodeCreated = function (this: TextInputNode) {
        const result = onNodeCreated?.apply(this, arguments as unknown as []);
        const node = this;

        // Style the node
        node.color = "#3a4a5a";
        node.bgcolor = "#2a3a4a";

        // Find and replace the font_color STRING widget with a color picker
        const colorWidgetIdx = node.widgets?.findIndex(
            (w: ComfyWidget) => w.name === "font_color",
        ) ?? -1;
        if (colorWidgetIdx >= 0 && node.widgets) {
            const oldWidget = node.widgets[colorWidgetIdx];
            const initialColor = (oldWidget.value as string) || "#FFFFFF";

            // Remove the old STRING widget
            node.widgets.splice(colorWidgetIdx, 1);

            // Create DOM container
            const container = document.createElement("div");
            container.style.cssText = `
                display: flex;
                align-items: center;
                gap: 8px;
                padding: 2px 4px;
                width: 100%;
                box-sizing: border-box;
            `;

            // Label
            const label = document.createElement("span");
            label.textContent = "Font Color";
            label.style.cssText = `
                color: #b0b0b0;
                font: 12px Arial, sans-serif;
                flex-shrink: 0;
            `;

            // Color input
            const colorInput = document.createElement("input");
            colorInput.type = "color";
            colorInput.value = initialColor;
            colorInput.setAttribute("aria-label", "Select font color");
            colorInput.style.cssText = `
                width: 36px;
                height: 24px;
                border: 1px solid #555;
                border-radius: 4px;
                cursor: pointer;
                background: transparent;
                padding: 0;
                flex-shrink: 0;
            `;

            // Hex display
            const hexLabel = document.createElement("span");
            hexLabel.textContent = initialColor.toUpperCase();
            hexLabel.title = "Click or Press Enter to copy hex code";
            hexLabel.setAttribute("role", "button");
            hexLabel.setAttribute("tabindex", "0");
            hexLabel.setAttribute("aria-label", "Copy color hex code");
            hexLabel.setAttribute("aria-live", "polite");
            hexLabel.style.cssText = `
                color: #ccc;
                font: 11px monospace;
                flex-grow: 1;
                text-align: right;
                cursor: pointer;
                user-select: none;
                outline: none;
                border-radius: 2px;
                padding: 2px 4px;
            `;

            // Focus styles
            hexLabel.onfocus = (): void => {
                hexLabel.style.outline = "1px solid #4a6a8a";
                hexLabel.style.outlineOffset = "2px";
            };
            hexLabel.onblur = (): void => {
                hexLabel.style.outline = "none";
                hexLabel.style.outlineOffset = "0px";
            };

            // Copy handler
            const copyHex = async (): Promise<void> => {
                const currentHex = colorInput.value.toUpperCase();
                try {
                    if (navigator.clipboard) {
                        await navigator.clipboard.writeText(currentHex);
                        flashNode(node, "#4a7a4a");

                        hexLabel.textContent = "COPIED";
                        hexLabel.style.color = "#8f8";
                        hexLabel.setAttribute("aria-label", "Copied successfully");

                        setTimeout(() => {
                            if (hexLabel.textContent === "COPIED") {
                                hexLabel.textContent = currentHex;
                                hexLabel.style.color = "#ccc";
                                hexLabel.setAttribute("aria-label", "Copy color hex code");
                            }
                        }, 800);
                    }
                } catch (err) {
                    console.error("Failed to copy hex:", err);
                    flashNode(node, "#7a3a3a");
                }
            };

            hexLabel.onclick = copyHex;
            hexLabel.onkeydown = (e: KeyboardEvent): void => {
                if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    copyHex();
                }
            };

            container.appendChild(label);
            container.appendChild(colorInput);
            container.appendChild(hexLabel);

            // Store refs for preset system
            node._ffmpegaColorInput = colorInput;
            node._ffmpegaHexLabel = hexLabel;

            // Add as DOM widget
            const domWidget = node.addDOMWidget("font_color", "custom", container, {
                getValue: () => colorInput.value.toUpperCase(),
                setValue: (v: unknown) => {
                    if (v && typeof v === "string") {
                        if (v.startsWith("#")) {
                            colorInput.value = v;
                            hexLabel.textContent = v.toUpperCase();
                            hexLabel.style.color = "#ccc";
                        }
                    }
                },
            });
            domWidget.value = initialColor;

            colorInput.addEventListener("input", (e: Event) => {
                const val = (e.target as HTMLInputElement).value.toUpperCase();
                domWidget.value = val;
                hexLabel.textContent = val;
                hexLabel.style.color = "#ccc";
            });

            // Move widget to the correct position
            const newIdx = node.widgets.indexOf(domWidget);
            if (newIdx >= 0 && newIdx !== colorWidgetIdx) {
                node.widgets.splice(newIdx, 1);
                node.widgets.splice(colorWidgetIdx, 0, domWidget);
            }
        }

        return result;
    };

    // --- Text Preset Context Menu ---
    let _customPresets: TextPreset[] = [];

    // Eagerly fetch custom presets on load
    fetch(api.apiURL("/ffmpega/text_presets"))
        .then(r => r.json())
        .then((data: unknown) => {
            _customPresets = Array.isArray(data) ? data as TextPreset[] : [];
        })
        .catch(() => { _customPresets = []; });

    const origGetMenuText = nodeType.prototype.getExtraMenuOptions;
    nodeType.prototype.getExtraMenuOptions = function (
        this: TextInputNode,
        _: unknown,
        options: (ComfyMenuOption | null)[],
    ): void {
        origGetMenuText?.apply(this, arguments as unknown as [unknown, ComfyMenuOption[]]);
        const self = this;

        // Build submenu items synchronously from cache
        const presetItems: ComfyMenuOption[] = [];

        for (const p of BUILTIN_PRESETS) {
            presetItems.push({
                content: p.name,
                callback: () => applyPreset(self, p),
            });
        }

        if (_customPresets.length > 0) {
            for (const p of _customPresets) {
                presetItems.push({
                    content: `⭐ ${p.name}`,
                    submenu: {
                        options: [
                            {
                                content: "✅ Load",
                                callback: () => applyPreset(self, p),
                            },
                            {
                                content: "🗑️ Delete",
                                callback: () => deleteCustomPreset(self, _customPresets, p.name),
                            },
                        ],
                    },
                });
            }
        }

        options.unshift(
            {
                content: "💾 Save Current as Preset",
                callback: () => saveCustomPreset(self, _customPresets),
            },
            {
                content: "🎨 Load Preset",
                submenu: {
                    options: presetItems,
                },
            },
            {
                content: "🧹 Clear Text",
                callback: () => {
                    const defaults: Record<string, unknown> = {
                        text: "", mode: "overlay", position: "bottom_center",
                        font_size: 24, font_color: "#FFFFFF", auto_mode: true,
                    };
                    for (const [key, val] of Object.entries(defaults)) {
                        const w = self.widgets?.find(
                            (ww: ComfyWidget) => ww.name === key,
                        ) as TextWidget | undefined;
                        if (!w) continue;
                        w.value = val;
                        if (key === "font_color") {
                            try {
                                const ci = self._ffmpegaColorInput;
                                const hl = self._ffmpegaHexLabel;
                                if (ci) { ci.value = val as string; }
                                if (hl) {
                                    hl.textContent = val as string;
                                    hl.style.color = "#ccc";
                                }
                            } catch { /* ignore */ }
                        } else if (w.inputEl) {
                            (w.inputEl as HTMLInputElement).value = String(val);
                        } else if (w.element) {
                            const tag = w.element.tagName?.toLowerCase();
                            if (tag === "textarea" || tag === "input") {
                                (w.element as HTMLInputElement).value = String(val);
                            }
                        }
                    }
                    self.setDirtyCanvas(true, true);
                    app.graph.setDirtyCanvas(true, true);
                    flashNode(self, "#4a7a4a");
                },
            },
            null, // separator
        );
    };
}
