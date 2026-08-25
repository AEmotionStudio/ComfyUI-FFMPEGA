/**
 * FFMPEGALoadMaskVideo node UI handler.
 *
 * Features:
 * - Video preview on file selection and after execution
 * - Upload button for mask videos
 * - Download overlay and context menu
 */

import { api } from "comfyui/api";
import { addDownloadOverlay, addVideoPreviewMenu, createUploadButton } from "@ffmpega/shared/ui_helpers";
import type { ComfyNodeType, ComfyNodeData, ComfyNode, ComfyWidget } from "@ffmpega/types/comfyui";

interface LoadMaskVideoNode extends ComfyNode {
    addDOMWidget(name: string, type: string, el: HTMLElement, opts?: Record<string, unknown>): ComfyWidget;
    onExecuted?: (data: LoadMaskVideoExecutionData) => void;
    onRemoved?: () => void;
}

interface LoadMaskVideoExecutionData {
    video?: Array<{ filename: string; subfolder?: string; type?: string }>;
}

interface VideoDropdownWidget extends ComfyWidget {
    options: { values: string[] };
    callback?: (value: string) => void;
}

interface PreviewContainerElement extends HTMLDivElement {
    value?: unknown;
}

const VIDEO_ACCEPT = [
    "video/webm", "video/mp4", "video/x-matroska",
    "video/quicktime", "video/x-msvideo",
].join(",");

const VIDEO_EXTENSIONS = ["mp4", "avi", "mov", "mkv", "webm"];

const PASSTHROUGH_EVENTS = [
    "contextmenu", "pointerdown", "mousewheel",
    "pointermove", "pointerup",
] as const;

export function registerLoadMaskVideoNode(
    nodeType: ComfyNodeType,
    nodeData: ComfyNodeData,
): void {
    if (nodeData.name !== "FFMPEGALoadMaskVideo") return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;

    nodeType.prototype.onNodeCreated = function (this: LoadMaskVideoNode) {
        const result = onNodeCreated?.apply(this, arguments as unknown as []);
        const node = this;

        // Dark mask-themed colors
        this.color = "#3a3a5a";
        this.bgcolor = "#2a2a4a";

        // Upload button
        const { fileInput, uploadBtn } = createUploadButton(VIDEO_ACCEPT);
        document.body.append(fileInput);
        this.addDOMWidget("upload_button", "btn", uploadBtn, { serialize: false });

        // Preview container
        const previewContainer = document.createElement("div") as PreviewContainerElement;
        previewContainer.className = "ffmpega_preview";
        previewContainer.style.cssText =
            "width:100%;background:#1a1a1a;border-radius:6px;" +
            "overflow:hidden;position:relative;";

        const videoEl = document.createElement("video");
        videoEl.controls = true;
        videoEl.loop = true;
        videoEl.muted = true;
        videoEl.setAttribute("aria-label", "Mask video preview");
        videoEl.style.cssText = "width:100%;display:block;";

        const infoEl = document.createElement("div");
        infoEl.style.cssText =
            "padding:4px 8px;font-size:11px;color:#aaa;" +
            "font-family:monospace;background:#111;";
        infoEl.textContent = "No mask video selected";
        infoEl.setAttribute("role", "status");

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
            infoEl.textContent = parts.length ? parts.join(" | ") : "Loaded";
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

        previewContainer.appendChild(videoEl);
        previewContainer.appendChild(infoEl);

        addDownloadOverlay(previewContainer, videoEl);

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

        // Update preview from filename
        const updatePreview = (filename: string | null | undefined): void => {
            if (!filename) {
                previewContainer.style.display = "none";
                infoEl.textContent = "No mask video selected";
                return;
            }
            previewContainer.style.display = "";
            const params = new URLSearchParams({
                filename: filename,
                type: "input",
                timestamp: String(Date.now()),
            });
            videoEl.src = api.apiURL("/view?" + params.toString());
            infoEl.textContent = "Loading...";
        };

        // Upload handler
        const handleUpload = async (file: File): Promise<boolean> => {
            const body = new FormData();
            body.append("image", file);
            try {
                const resp = await fetch("/upload/image", { method: "POST", body });
                if (resp.status !== 200) return false;
                const data = await resp.json();
                const filename = data.name as string;
                if (maskVideoWidget) {
                    if (!maskVideoWidget.options.values.includes(filename)) {
                        maskVideoWidget.options.values.push(filename);
                    }
                    maskVideoWidget.value = filename;
                    maskVideoWidget.callback?.(filename);
                }
                updatePreview(filename);
                return true;
            } catch {
                return false;
            }
        };

        fileInput.onchange = async (): Promise<void> => {
            if (fileInput.files?.length) {
                await handleUpload(fileInput.files[0]);
            }
        };

        const maskVideoWidget = this.widgets?.find(
            (w: ComfyWidget) => w.name === "mask_video",
        ) as VideoDropdownWidget | undefined;

        // Watch dropdown for selection changes
        if (maskVideoWidget) {
            const origCallback = maskVideoWidget.callback;
            maskVideoWidget.callback = function (value: string): void {
                origCallback?.apply(this, arguments as unknown as [string]);
                updatePreview(value);
            };
            if (maskVideoWidget.value) {
                setTimeout(() => updatePreview(maskVideoWidget.value as string), 100);
            }
        }

        // Handle execution results
        const origOnExecuted = this.onExecuted;
        this.onExecuted = function (this: LoadMaskVideoNode, data: LoadMaskVideoExecutionData) {
            origOnExecuted?.apply(this, arguments as unknown as [LoadMaskVideoExecutionData]);
            if (data?.video?.[0]) {
                const v = data.video[0];
                const params = new URLSearchParams({
                    filename: v.filename,
                    subfolder: v.subfolder || "",
                    type: v.type || "input",
                    timestamp: String(Date.now()),
                });
                previewContainer.style.display = "";
                videoEl.src = api.apiURL("/view?" + params.toString());
            }
        };

        // Cleanup
        const origOnRemoved = this.onRemoved;
        this.onRemoved = function (): void {
            fileInput?.remove();
            origOnRemoved?.apply(this, arguments as unknown as []);
        };

        const getVideoUrl = (): string | null => videoEl.src || null;
        addVideoPreviewMenu(node, videoEl, previewContainer, previewWidget, getVideoUrl, infoEl);

        return result;
    };
}
