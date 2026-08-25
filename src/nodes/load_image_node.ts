/**
 * FFMPEGALoadImagePath node UI handler.
 *
 * Features:
 * - Dynamic output slot (images) — hidden until input connected
 * - Upstream image preview on execution
 * - Point selector context menu (resolves image path for SAM3)
 */

import { api } from "comfyui/api";
import { flashNode } from "@ffmpega/shared/ui_helpers";
import { openPointSelector } from "@ffmpega/shared/point_selector";
import type {
    ComfyNodeType, ComfyNodeData, ComfyNode,
    ComfyWidget, ComfyMenuOption,
} from "@ffmpega/types/comfyui";

/** Extended node with output/input slot management methods */
interface LoadImageNode extends ComfyNode {
    findInputSlot(name: string): number;
    findOutputSlot(name: string): number;
    addOutput(name: string, type: string): void;
    removeOutput(index: number): void;
    onConnectionsChange?: (
        type: number, slotIndex: number, isConnected: boolean,
        link: unknown, ioSlot: unknown,
    ) => void;
    onConfigure?: (data: unknown) => void;
    onExecuted?: (data: LoadImageExecutionData) => void;
}

interface LoadImageExecutionData {
    images?: Array<{ filename: string; subfolder?: string; type?: string }>;
}

/** Resize sub-widgets gated behind the enable_resize toggle. */
const RESIZE_WIDGETS = [
    "resize_width", "resize_height", "upscale_method", "keep_proportion",
    "pad_color", "crop_position", "divisible_by", "resize_device",
] as const;

/** VHS-style widget show/hide (mirrors the helper in agent_node.ts). */
function toggleWidget(widget: ComfyWidget | undefined, show: boolean): void {
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
        widget.computeSize = () => [0, -4] as [number, number];
        widget.hidden = true;
        if (widget.element) widget.element.hidden = true;
    }
}

/**
 * Register FFMPEGALoadImagePath node UI.
 */
export function registerLoadImageNode(
    nodeType: ComfyNodeType,
    nodeData: ComfyNodeData,
): void {
    if (nodeData.name !== "FFMPEGALoadImagePath") return;

    const origOnCreatedImg = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function (this: LoadImageNode) {
        const result = origOnCreatedImg?.apply(this, arguments as unknown as []);
        const node = this;
        this.color = "#3a5a5a";
        this.bgcolor = "#2a4a4a";

        // --- enable_resize toggle → resize sub-widget visibility ---
        const fitHeight = (): void => {
            node.setSize([
                node.size[0],
                node.computeSize([node.size[0], node.size[1]])[1],
            ]);
            node?.graph?.setDirtyCanvas(true);
        };

        const updateResizeVisibility = (): void => {
            const enableResize = node.widgets?.find((w: ComfyWidget) => w.name === "enable_resize");
            const show = Boolean(enableResize?.value);
            for (const name of RESIZE_WIDGETS) {
                const w = node.widgets?.find((ww: ComfyWidget) => ww.name === name);
                if (w) toggleWidget(w, show);
            }
            fitHeight();
        };

        const enableResizeWidget = this.widgets?.find((w: ComfyWidget) => w.name === "enable_resize");
        if (enableResizeWidget) {
            updateResizeVisibility();
            const origResizeCb = enableResizeWidget.callback;
            enableResizeWidget.callback = function (...args: unknown[]) {
                origResizeCb?.apply(this, args);
                updateResizeVisibility();
            };
        }

        // Restore on workflow load
        const origConfigureImg = this.onConfigure;
        this.onConfigure = function (data: unknown): void {
            origConfigureImg?.apply(this, arguments as unknown as [unknown]);
            // Re-apply visibility after saved widget values are restored
            updateResizeVisibility();
        };

        // Handle execution results — update preview from upstream
        const origOnExecutedImg = this.onExecuted;
        this.onExecuted = function (data: LoadImageExecutionData): void {
            origOnExecutedImg?.apply(this, arguments as unknown as [LoadImageExecutionData]);

            if (data?.images?.[0]) {
                const img = data.images[0];
                const imgWidgets = this.widgets?.filter(
                    (w: ComfyWidget) => w.name === "image_preview" || w.type === "preview",
                );
                if (imgWidgets?.length) {
                    const params = new URLSearchParams({
                        filename: img.filename,
                        subfolder: img.subfolder || "",
                        type: img.type || "input",
                        timestamp: String(Date.now()),
                    });
                    const src = api.apiURL("/view?" + params.toString());
                    for (const w of imgWidgets) {
                        const imgEl = w.element?.querySelector?.("img") as HTMLImageElement | null;
                        if (imgEl) {
                            imgEl.src = src;
                        }
                    }
                }
            }
        };

        return result;
    };

    // --- Point selector context menu ---
    const origGetMenuImg = nodeType.prototype.getExtraMenuOptions;
    nodeType.prototype.getExtraMenuOptions = function (
        this: LoadImageNode,
        _: unknown,
        options: (ComfyMenuOption | null)[],
    ): void {
        origGetMenuImg?.apply(this, arguments as unknown as [unknown, ComfyMenuOption[]]);
        const self = this;
        options.unshift({
            content: "🎯 Open Point Selector",
            callback: () => {
                const imgWidget = self.widgets?.find(
                    (w: ComfyWidget) => w.name === "image",
                );
                const filename = imgWidget?.value as string | undefined;
                if (!filename) {
                    flashNode(self, "#7a4a4a");
                    return;
                }

                // Parse subfolder if present (ComfyUI sends "subfolder/file.png")
                let resolvedFilename = filename;
                let subfolder = "";
                if (filename.includes("/") || filename.includes("\\")) {
                    const sep = filename.includes("/") ? "/" : "\\";
                    const parts = filename.split(sep);
                    resolvedFilename = parts.pop()!;
                    subfolder = parts.join(sep);
                }

                const params = new URLSearchParams({
                    filename: resolvedFilename, type: "input",
                    ...(subfolder ? { subfolder } : {}),
                });
                const imgSrc = api.apiURL("/view?" + params.toString());

                // Resolve the on-disk absolute path for SAM3 via server
                fetch("/ffmpega/resolve_image_path", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        filename: resolvedFilename,
                        subfolder,
                    }),
                })
                    .then(r => r.json())
                    .then((data: { image_path?: string }) => {
                        openPointSelector(self, imgSrc, undefined, data.image_path || "");
                    })
                    .catch(() => {
                        // Fallback: open without SAM3 path (draw mode still works)
                        openPointSelector(self, imgSrc);
                    });
            },
        }, {
            content: "🧹 Clear Mask",
            callback: () => {
                const mpWidget = self.widgets?.find((w: ComfyWidget) => w.name === "mask_points_data");
                if (mpWidget) {
                    mpWidget.value = "";
                }
                self.setDirtyCanvas?.(true, true);
                flashNode(self, "#4a7a4a");
            },
        }, null);
    };
}
