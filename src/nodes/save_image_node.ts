/**
 * FFMPEGASaveImage node UI handler.
 *
 * Adds auto-growing dynamic comparison inputs (images_a/b/..., image_path_a/b/...)
 * so several images can be connected and combined side-by-side. The image
 * preview itself is rendered by ComfyUI's standard `ui.images` payload.
 */

import { wireDynamicInputs } from "@ffmpega/shared/ui_helpers";
import type { ComfyNodeType, ComfyNodeData, ComfyNode } from "@ffmpega/types/comfyui";

/**
 * Register FFMPEGASaveImage node UI.
 */
export function registerSaveImageNode(
    nodeType: ComfyNodeType,
    nodeData: ComfyNodeData,
): void {
    if (nodeData.name !== "FFMPEGASaveImage") return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;

    nodeType.prototype.onNodeCreated = function (this: ComfyNode) {
        const result = onNodeCreated?.apply(this, arguments as unknown as []);
        const node = this;

        this.color = "#2a5a3a";
        this.bgcolor = "#1a4a2a";

        // --- Dynamic comparison inputs (images_a/b/..., image_path_a/b/...) ---
        wireDynamicInputs(
            node,
            [
                { prefix: "images_", type: "IMAGE", excludes: [] },
                { prefix: "image_path_", type: "STRING", excludes: [] },
            ],
            [
                { name: "images", type: "IMAGE" },
                { name: "image_path", type: "STRING" },
            ],
        );

        return result;
    };
}
