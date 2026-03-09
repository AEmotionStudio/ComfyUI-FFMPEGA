/**
 * Crop selector context menu hooks for LoadVideoPath and FrameExtract.
 *
 * Adds a "✂️ Open Crop Selector" context menu to these nodes.
 * Grabs the video URL and opens the shared crop selector modal.
 * Restores CSS crop preview when a node loads with existing crop_data.
 */

import { api } from "comfyui/api";
import { flashNode } from "@ffmpega/shared/ui_helpers";
import { openCropSelector, applyCropPreview } from "@ffmpega/shared/crop_selector";
import type { ComfyNodeType, ComfyNodeData, ComfyNode, ComfyWidget, ComfyMenuOption } from "@ffmpega/types/comfyui";

type NodeWithWidgets = ComfyNode & {
    widgets?: ComfyWidget[];
    getExtraMenuOptions?: (canvas: unknown, options: (ComfyMenuOption | null)[]) => void;
    onNodeCreated?: () => unknown;
};

/**
 * Try to restore the CSS crop preview on a node's video element.
 * Called after video metadata loads or after execution results arrive.
 */
function restoreCropPreview(node: NodeWithWidgets): void {
    const cdWidget = node.widgets?.find((w: ComfyWidget) => w.name === "crop_data");
    if (!cdWidget?.value) return;

    try {
        const rect = JSON.parse(String(cdWidget.value));
        if (rect && typeof rect.x === "number") {
            applyCropPreview(node, rect);
        }
    } catch { /* ignore */ }
}

/**
 * Set up a watcher that restores crop preview when the node's video
 * element fires `loadedmetadata`. Uses a MutationObserver to detect
 * when the <video> is added to the DOM, then attaches the listener.
 */
function watchForVideoAndRestoreCrop(node: NodeWithWidgets): void {
    // Small delay to let the DOM widget be created
    setTimeout(() => {
        const nodeEl = (node as unknown as { element?: HTMLElement }).element;
        if (!nodeEl) return;

        const videoEl = nodeEl.querySelector("video");
        if (videoEl) {
            videoEl.addEventListener("loadedmetadata", () => restoreCropPreview(node));
            // If already loaded, apply immediately
            if (videoEl.readyState >= 1) restoreCropPreview(node);
            return;
        }

        // Video not found yet — watch for it via MutationObserver
        const observer = new MutationObserver(() => {
            const vid = nodeEl.querySelector("video");
            if (vid) {
                observer.disconnect();
                vid.addEventListener("loadedmetadata", () => restoreCropPreview(node));
                if (vid.readyState >= 1) restoreCropPreview(node);
            }
        });
        observer.observe(nodeEl, { childList: true, subtree: true });

        // Auto-disconnect after 10s to avoid leaks
        setTimeout(() => observer.disconnect(), 10000);
    }, 200);
}

/**
 * Register crop selector context menu hooks for LoadVideoPath and FrameExtract.
 */
export function registerCropSelectorHooks(
    nodeType: ComfyNodeType,
    nodeData: ComfyNodeData,
): void {
    // --- LoadVideoPath: Add crop selector context menu + restore ---
    if (nodeData.name === "FFMPEGALoadVideoPath") {
        const origGetMenu = nodeType.prototype.getExtraMenuOptions;
        nodeType.prototype.getExtraMenuOptions = function (
            this: NodeWithWidgets,
            _: unknown,
            options: (ComfyMenuOption | null)[],
        ): void {
            origGetMenu?.apply(this, arguments as unknown as [unknown, ComfyMenuOption[]]);
            const self = this;
            options.unshift({
                content: "✂️ Open Crop Selector",
                callback: () => {
                    const vidWidget = self.widgets?.find((w: ComfyWidget) => w.name === "video");
                    const filename = vidWidget?.value as string | undefined;
                    if (!filename) {
                        flashNode(self, "#7a4a4a");
                        return;
                    }
                    const params = new URLSearchParams({ filename, type: "input" });
                    const src = api.apiURL("/view?" + params.toString());
                    openCropSelector(self, src);
                },
            }, null);
        };

        // Restore crop preview on node creation (e.g. workflow load)
        const origCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (this: NodeWithWidgets) {
            const result = origCreated?.apply(this, arguments as unknown as []);
            watchForVideoAndRestoreCrop(this);
            return result;
        };
    }

    // --- FrameExtract: Add crop selector context menu + restore ---
    if (nodeData.name === "FFMPEGAFrameExtract") {
        const origGetMenu = nodeType.prototype.getExtraMenuOptions;
        nodeType.prototype.getExtraMenuOptions = function (
            this: NodeWithWidgets,
            _: unknown,
            options: (ComfyMenuOption | null)[],
        ): void {
            origGetMenu?.apply(this, arguments as unknown as [unknown, ComfyMenuOption[]]);
            const self = this;
            options.unshift({
                content: "✂️ Open Crop Selector",
                callback: () => {
                    const pathWidget = self.widgets?.find((w: ComfyWidget) => w.name === "video_path");
                    const videoPath = (pathWidget?.value as string | undefined)?.trim();
                    if (!videoPath) {
                        flashNode(self, "#7a4a4a");
                        return;
                    }
                    const params = new URLSearchParams({
                        path: videoPath,
                        duration: "1",
                    });
                    const src = api.apiURL("/ffmpega/preview?" + params.toString());
                    openCropSelector(self, src);
                },
            }, null);
        };

        // Restore crop preview on node creation
        const origCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (this: NodeWithWidgets) {
            const result = origCreated?.apply(this, arguments as unknown as []);
            watchForVideoAndRestoreCrop(this);
            return result;
        };
    }
}

