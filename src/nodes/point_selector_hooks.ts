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
 * Helper: read skip_first_frames & force_rate from a node, compute seek time.
 * Falls back to 30fps if force_rate is 0 and we can't determine the FPS.
 */
function getSkipTimeSec(node: NodeWithWidgets): number {
    const skipWidget = node.widgets?.find((w: ComfyWidget) => w.name === "skip_first_frames");
    const rateWidget = node.widgets?.find((w: ComfyWidget) => w.name === "force_rate");
    const skipFrames = Number(skipWidget?.value) || 0;
    const fps = Number(rateWidget?.value) || 0;
    if (skipFrames <= 0) return 0.01; // default: tiny offset to skip black frame
    return skipFrames / (fps > 0 ? fps : 30);
}

/**
 * Capture a video frame at a specific time and open the point selector modal.
 */
function captureFirstFrameAndOpen(
    node: NodeWithWidgets,
    videoSrc: string,
    startTimeSec: number = 0.01,
): void {
    const tmpVideo = document.createElement("video");
    tmpVideo.crossOrigin = "anonymous";
    tmpVideo.muted = true;
    tmpVideo.preload = "auto";
    tmpVideo.src = videoSrc;
    tmpVideo.currentTime = startTimeSec;

    // Extract video file path from the URL to get on-disk frame path for SAM3
    let videoFilePath = "";
    try {
        const u = new URL(videoSrc, window.location.origin);
        videoFilePath = u.searchParams.get("filename") || u.searchParams.get("path") || "";
    } catch { /* ignore */ }

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
        tmpVideo.remove();

        // Get server-side frame path for SAM3
        if (videoFilePath) {
            const skipWidget = node.widgets?.find((w: ComfyWidget) => w.name === "skip_first_frames");
            const skipFrames = Number(skipWidget?.value) || 0;
            fetch("/ffmpega/first_frame", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ video_path: videoFilePath, skip_frames: skipFrames }),
            })
                .then(r => r.json())
                .then((data: { frame_path?: string }) => {
                    openPointSelector(node, frameDataUrl, videoSrc, data.frame_path || "");
                })
                .catch(() => {
                    openPointSelector(node, frameDataUrl, videoSrc);
                });
        } else {
            openPointSelector(node, frameDataUrl, videoSrc);
        }
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
                    captureFirstFrameAndOpen(self, src, getSkipTimeSec(self));
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
