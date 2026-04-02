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

        // Restore on workflow load
        const origConfigureImg = this.onConfigure;
        this.onConfigure = function (data: unknown): void {
            origConfigureImg?.apply(this, arguments as unknown as [unknown]);
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
