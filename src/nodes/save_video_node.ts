/**
 * FFMPEGASaveVideo node UI handler.
 *
 * Features:
 * - Video preview after execution (DOM widget)
 * - Download overlay button
 * - Context menu with preview controls
 * - File size display in info bar
 */

import { api } from "comfyui/api";
import { addDownloadOverlay, addVideoPreviewMenu } from "@ffmpega/shared/ui_helpers";
import type { ComfyNodeType, ComfyNodeData, ComfyNode, ComfyWidget } from "@ffmpega/types/comfyui";

/** Extended node type for SaveVideo with internal state */
interface SaveVideoNode extends ComfyNode {
    _savedFileSize?: string;
    addDOMWidget(name: string, type: string, el: HTMLElement, opts?: Record<string, unknown>): ComfyWidget;
    onExecuted?: (data: SaveVideoExecutionData) => void;
}

/** Execution data returned from Python backend */
interface SaveVideoExecutionData {
    video?: Array<{ filename: string; subfolder?: string; type?: string }>;
    file_size?: string[];
}

/** Preview container element with value property */
interface PreviewContainerElement extends HTMLDivElement {
    value?: unknown;
}

/**
 * Register FFMPEGASaveVideo node UI.
 */
export function registerSaveVideoNode(
    nodeType: ComfyNodeType,
    nodeData: ComfyNodeData,
): void {
    if (nodeData.name !== "FFMPEGASaveVideo") return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;

    nodeType.prototype.onNodeCreated = function (this: SaveVideoNode) {
        const result = onNodeCreated?.apply(this, arguments as unknown as []);
        const node = this;

        this.color = "#2a5a3a";
        this.bgcolor = "#1a4a2a";

        // --- Video preview DOM widget ---
        const previewContainer = document.createElement("div") as PreviewContainerElement;
        previewContainer.className = "ffmpega_preview";
        previewContainer.style.cssText =
            "width:100%;background:#1a1a1a;border-radius:6px;" +
            "overflow:hidden;display:none;position:relative;";

        const videoEl = document.createElement("video");
        videoEl.controls = true;
        videoEl.loop = true;
        videoEl.muted = true;
        videoEl.setAttribute("aria-label", "Output video preview");
        videoEl.style.cssText = "width:100%;display:block;";
        videoEl.addEventListener("loadedmetadata", () => {
            previewWidget.aspectRatio =
                videoEl.videoWidth / videoEl.videoHeight;
            const w = videoEl.videoWidth;
            const h = videoEl.videoHeight;
            const d = videoEl.duration;
            const parts: string[] = [];
            if (w && h) parts.push(`${w}×${h}`);
            if (d && isFinite(d)) {
                const m = Math.floor(d / 60);
                const s = (d % 60).toFixed(1);
                parts.push(m > 0 ? `${m}m ${s}s` : `${s}s`);
            }
            if (node._savedFileSize) {
                parts.push(node._savedFileSize);
            }
            if (parts.length) {
                infoEl.textContent = parts.join(" | ");
            }
            node.setSize([
                node.size[0],
                node.computeSize([node.size[0], node.size[1]])[1],
            ]);
            node?.graph?.setDirtyCanvas(true);
        });
        videoEl.addEventListener("error", () => {
            previewContainer.style.display = "none";
            node.setSize([
                node.size[0],
                node.computeSize([node.size[0], node.size[1]])[1],
            ]);
            node?.graph?.setDirtyCanvas(true);
        });

        const infoEl = document.createElement("div");
        infoEl.style.cssText =
            "padding:4px 8px;font-size:11px;color:#aaa;" +
            "font-family:monospace;background:#111;";
        infoEl.textContent = "Waiting for execution...";
        infoEl.setAttribute("role", "status");
        infoEl.setAttribute("aria-live", "polite");

        previewContainer.appendChild(videoEl);
        previewContainer.appendChild(infoEl);

        addDownloadOverlay(previewContainer, videoEl);

        const PASSTHROUGH_EVENTS = [
            "contextmenu", "pointerdown", "mousewheel",
            "pointermove", "pointerup",
        ] as const;
        for (const evt of PASSTHROUGH_EVENTS) {
            previewContainer.addEventListener(evt, (e: Event) => {
                e.stopPropagation();
            }, true);
        }

        const previewWidget = this.addDOMWidget(
            "videopreview", "preview", previewContainer,
            {
                serialize: false,
                hideOnZoom: false,
                getValue() { return (previewContainer as PreviewContainerElement).value; },
                setValue(v: unknown) { (previewContainer as PreviewContainerElement).value = v; },
            }
        );
        previewWidget.aspectRatio = null;
        previewWidget.computeSize = function (this: ComfyWidget, width: number): [number, number] {
            if (this.aspectRatio && previewContainer.style.display !== "none") {
                const h = (node.size[0] - 20) / this.aspectRatio + 10;
                return [width, Math.max(h, 0) + 30];
            }
            return [width, -4];
        };

        const origOnExecuted = this.onExecuted;
        this.onExecuted = function (this: SaveVideoNode, data: SaveVideoExecutionData) {
            origOnExecuted?.apply(this, arguments as unknown as [SaveVideoExecutionData]);
            if (data?.video?.[0]) {
                const v = data.video[0];
                const params = new URLSearchParams({
                    filename: v.filename,
                    subfolder: v.subfolder || "",
                    type: v.type || "output",
                    timestamp: String(Date.now()),
                });
                previewContainer.style.display = "";
                videoEl.src = api.apiURL("/view?" + params.toString());

                if (data?.file_size?.[0]) {
                    node._savedFileSize = data.file_size[0];
                }

                infoEl.textContent = `Saved: ${v.filename}`;
                if (node._savedFileSize) {
                    infoEl.textContent += ` (${node._savedFileSize})`;
                }
            }
        };

        const getVideoUrlSave = (): string | null => videoEl.src || null;
        addVideoPreviewMenu(node, videoEl, previewContainer, previewWidget, getVideoUrlSave, infoEl);

        return result;
    };
}
