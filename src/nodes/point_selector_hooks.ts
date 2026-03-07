/**
 * Point selector context menu hooks for LoadVideoPath and FrameExtract.
 *
 * Adds a "🎯 Open Point Selector" context menu to these nodes.
 * Grabs the first video frame and opens the shared point selector modal.
 */

import { api } from "comfyui/api";
import { flashNode } from "@ffmpega/shared/ui_helpers";
import { openPointSelector } from "@ffmpega/shared/point_selector";
import type { ComfyNodeType, ComfyNodeData, ComfyNode, ComfyWidget, ComfyMenuOption } from "@ffmpega/types/comfyui";

type NodeWithWidgets = ComfyNode & {
    widgets?: ComfyWidget[];
    getExtraMenuOptions?: (canvas: unknown, options: (ComfyMenuOption | null)[]) => void;
};

/**
 * Capture the first frame of a video and open the point selector modal.
 */
function captureFirstFrameAndOpen(
    node: NodeWithWidgets,
    videoSrc: string,
): void {
    const tmpVideo = document.createElement("video");
    tmpVideo.crossOrigin = "anonymous";
    tmpVideo.muted = true;
    tmpVideo.preload = "auto";
    tmpVideo.src = videoSrc;
    tmpVideo.currentTime = 0.01; // seek past potential black frame

    const seekTimeout = setTimeout(() => {
        flashNode(node, "#7a4a4a");
        tmpVideo.remove();
    }, 10000);

    tmpVideo.addEventListener("seeked", () => {
        clearTimeout(seekTimeout);
        const c = document.createElement("canvas");
        c.width = tmpVideo.videoWidth;
        c.height = tmpVideo.videoHeight;
        c.getContext("2d")!.drawImage(tmpVideo, 0, 0);
        const frameDataUrl = c.toDataURL("image/jpeg", 0.95);
        openPointSelector(node, frameDataUrl, videoSrc);
        tmpVideo.remove();
    }, { once: true });

    tmpVideo.addEventListener("error", () => {
        clearTimeout(seekTimeout);
        flashNode(node, "#7a4a4a");
        tmpVideo.remove();
    }, { once: true });
}

/**
 * Register point selector context menu hooks for LoadVideoPath and FrameExtract.
 */
export function registerPointSelectorHooks(
    nodeType: ComfyNodeType,
    nodeData: ComfyNodeData,
): void {
    // --- LoadVideoPath: Add point selector context menu ---
    if (nodeData.name === "FFMPEGALoadVideoPath") {
        const origGetMenuVid = nodeType.prototype.getExtraMenuOptions;
        nodeType.prototype.getExtraMenuOptions = function (
            this: NodeWithWidgets,
            _: unknown,
            options: (ComfyMenuOption | null)[],
        ): void {
            origGetMenuVid?.apply(this, arguments as unknown as [unknown, ComfyMenuOption[]]);
            const self = this;
            options.unshift({
                content: "🎯 Open Point Selector",
                callback: () => {
                    const vidWidget = self.widgets?.find((w: ComfyWidget) => w.name === "video");
                    const filename = vidWidget?.value as string | undefined;
                    if (!filename) {
                        flashNode(self, "#7a4a4a");
                        return;
                    }
                    const params = new URLSearchParams({ filename, type: "input" });
                    const src = api.apiURL("/view?" + params.toString());
                    captureFirstFrameAndOpen(self, src);
                },
            }, null);
        };
    }

    // --- FrameExtract: Add point selector context menu ---
    if (nodeData.name === "FFMPEGAFrameExtract") {
        const origGetMenuExtract = nodeType.prototype.getExtraMenuOptions;
        nodeType.prototype.getExtraMenuOptions = function (
            this: NodeWithWidgets,
            _: unknown,
            options: (ComfyMenuOption | null)[],
        ): void {
            origGetMenuExtract?.apply(this, arguments as unknown as [unknown, ComfyMenuOption[]]);
            const self = this;
            options.unshift({
                content: "🎯 Open Point Selector",
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
                    captureFirstFrameAndOpen(self, src);
                },
            }, null);
        };
    }
}
