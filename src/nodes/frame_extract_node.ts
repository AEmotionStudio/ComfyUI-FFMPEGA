/**
 * FFMPEGAFrameExtract node UI handler.
 *
 * Features:
 * - Live video preview with frame info  
 * - Upload button + drag-drop
 * - Widget polling for live preview updates
 * - Context menu with video preview controls
 */

import { api } from "comfyui/api";
import { addDownloadOverlay, addVideoPreviewMenu, flashNode } from "@ffmpega/shared/ui_helpers";
import type { ComfyNodeType, ComfyNodeData, ComfyNode, ComfyWidget } from "@ffmpega/types/comfyui";

// ---- Type definitions ----

interface FrameExtractNode extends ComfyNode {
    onDragOver?: (e: DragEvent) => boolean;
    onDragDrop?: (e: DragEvent) => Promise<boolean>;
    onRemoved?: () => void;
    onExecuted?: (data: FrameExtractExecutionData) => void;
    addDOMWidget(name: string, type: string, el: HTMLElement, opts?: Record<string, unknown>): ComfyWidget;
}

interface FrameExtractExecutionData {
    video?: Array<{ filename: string; subfolder?: string; type?: string }>;
    frame_info?: Array<{
        count: number; width: number; height: number;
        start: number; end: number; duration: number;
        source_fps: number; fps: number;
    }>;
}

interface VideoInfoResponse {
    width?: number;
    height?: number;
    fps?: number;
    duration?: number;
    frames?: number;
}

/** Button element with drag-drop transient state */
interface UploadButtonElement extends HTMLButtonElement {
    _originalInnerHTML?: string;
    _originalBorder?: string;
    _originalAriaLabel?: string | null;
    _dragTimeout?: ReturnType<typeof setTimeout>;
}

interface PreviewContainerElement extends HTMLDivElement {
    value?: unknown;
}

// ---- Constants ----

const VIDEO_ACCEPT = [
    "video/webm", "video/mp4", "video/x-matroska",
    "video/quicktime", "video/x-msvideo", "video/x-flv",
    "video/x-ms-wmv", "video/mpeg", "video/3gpp",
    "image/gif",
].join(",");

const VIDEO_EXTENSIONS = [
    "mp4", "avi", "mov", "mkv", "webm", "flv",
    "wmv", "m4v", "mpg", "mpeg", "ts", "mts", "gif",
];

const WATCH_WIDGETS = ["video_path", "start_time", "duration", "fps", "max_frames"];

const PASSTHROUGH_EVENTS = [
    "contextmenu", "pointerdown", "mousewheel",
    "pointermove", "pointerup",
] as const;

// ---- Helpers ----

/** Format seconds as m:ss.s or ss.s */
function formatTime(sec: number): string {
    if (sec < 0) sec = 0;
    const m = Math.floor(sec / 60);
    const s = (sec % 60).toFixed(1);
    return m > 0 ? `${m}:${s.padStart(4, "0")}` : `${s}s`;
}

// ---- Registration ----

export function registerFrameExtractNode(
    nodeType: ComfyNodeType,
    nodeData: ComfyNodeData,
): void {
    if (nodeData.name !== "FFMPEGAFrameExtract") return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;

    nodeType.prototype.onNodeCreated = function (this: FrameExtractNode) {
        const result = onNodeCreated?.apply(this, arguments as unknown as []);
        const node = this;

        this.color = "#2a4a5a";
        this.bgcolor = "#1a3a4a";

        // --- Video preview DOM widget ---
        const previewContainer = document.createElement("div") as PreviewContainerElement;
        previewContainer.className = "ffmpega_preview";
        previewContainer.style.cssText =
            "width:100%;background:#1a1a1a;border-radius:6px;" +
            "overflow:hidden;position:relative;";

        const videoEl = document.createElement("video");
        videoEl.controls = true;
        videoEl.loop = true;
        videoEl.muted = true;
        videoEl.volume = 1.0;
        videoEl.setAttribute("aria-label", "Frame extraction preview");
        videoEl.style.cssText = "width:100%;display:block;";

        // Remember user's mute preference across video loads
        let userUnmuted = false;
        videoEl.addEventListener("volumechange", () => {
            userUnmuted = !videoEl.muted;
        });
        videoEl.addEventListener("play", () => {
            if (userUnmuted) videoEl.muted = false;
        });
        videoEl.addEventListener("loadedmetadata", () => {
            previewWidget.aspectRatio =
                videoEl.videoWidth / videoEl.videoHeight;
            node.setSize([
                node.size[0],
                node.computeSize([node.size[0], node.size[1]])[1],
            ]);
            node?.graph?.setDirtyCanvas(true);
        });

        // Info overlay
        const infoEl = document.createElement("div");
        infoEl.style.cssText =
            "padding:4px 8px;font-size:11px;color:#aaa;" +
            "font-family:monospace;background:#111;";
        infoEl.textContent = "No video loaded";
        infoEl.setAttribute("role", "status");
        infoEl.setAttribute("aria-live", "polite");

        videoEl.addEventListener("error", () => {
            previewContainer.style.display = "none";
            infoEl.textContent = "No video loaded";
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
            return [width, 34];
        };

        // --- Live preview: watch video_path, start_time, duration ---
        let _previewDebounce: ReturnType<typeof setTimeout> | null = null;

        const updateLivePreview = (): void => {
            const pathWidget = node.widgets?.find((w: ComfyWidget) => w.name === "video_path");
            const startWidget = node.widgets?.find((w: ComfyWidget) => w.name === "start_time");
            const durWidget = node.widgets?.find((w: ComfyWidget) => w.name === "duration");

            const videoPath = (pathWidget?.value as string | undefined)?.trim();
            if (!videoPath) {
                previewContainer.style.display = "none";
                infoEl.textContent = "No video loaded";
                node.setSize([
                    node.size[0],
                    node.computeSize([node.size[0], node.size[1]])[1],
                ]);
                node?.graph?.setDirtyCanvas(true);
                return;
            }

            const startTime = (startWidget?.value as number) ?? 0;
            const duration = (durWidget?.value as number) ?? 0;

            const params = new URLSearchParams({
                path: videoPath,
                start_time: String(startTime),
                _t: String(Date.now()),
            });
            if (duration > 0) {
                params.set("duration", String(duration));
            }
            const previewUrl = api.apiURL("/ffmpega/preview?" + params.toString());

            previewContainer.style.display = "";
            infoEl.textContent = "Loading preview...";
            videoEl.src = previewUrl;

            // Fetch video info for the info bar
            const infoParams = new URLSearchParams({ path: videoPath });
            fetch(api.apiURL("/ffmpega/video_info?" + infoParams.toString()))
                .then(r => r.json())
                .then((info: VideoInfoResponse) => {
                    if (!info?.width) return;
                    const fpsW = node.widgets?.find((w: ComfyWidget) => w.name === "fps");
                    const extractFps = (fpsW?.value as number) ?? 1;
                    const maxFramesW = node.widgets?.find((w: ComfyWidget) => w.name === "max_frames");
                    const maxFrames = (maxFramesW?.value as number) ?? 100;

                    const actualDur = Math.min(duration, (info.duration ?? 0) - startTime);
                    const expectedFrames = Math.min(
                        Math.max(0, Math.floor(actualDur * extractFps)),
                        maxFrames,
                    );

                    const startFmt = formatTime(startTime);
                    const endFmt = formatTime(startTime + actualDur);

                    infoEl.textContent =
                        `~${expectedFrames} frames • ${info.width}×${info.height}` +
                        ` • ${startFmt}–${endFmt} @ ${extractFps}fps`;
                })
                .catch(() => {
                    infoEl.textContent = "Preview loaded";
                });
        };

        const debouncedPreview = (): void => {
            if (_previewDebounce) clearTimeout(_previewDebounce);
            _previewDebounce = setTimeout(updateLivePreview, 600);
        };

        // Widget polling for live updates
        const widgetValues: Record<string, unknown> = {};
        const pollInterval = setInterval(() => {
            if (!node.graph) {
                clearInterval(pollInterval);
                return;
            }
            let changed = false;
            for (const name of WATCH_WIDGETS) {
                const w = node.widgets?.find((ww: ComfyWidget) => ww.name === name);
                if (w && widgetValues[name] !== w.value) {
                    widgetValues[name] = w.value;
                    changed = true;
                }
            }
            if (changed) debouncedPreview();
        }, 500);

        // Initial preview load
        setTimeout(updateLivePreview, 300);

        // Handle execution results
        const origOnExecuted = this.onExecuted;
        this.onExecuted = function (this: FrameExtractNode, data: FrameExtractExecutionData): void {
            origOnExecuted?.apply(this, arguments as unknown as [FrameExtractExecutionData]);

            if (data?.video?.[0]) {
                const v = data.video[0];
                const params = new URLSearchParams({
                    filename: v.filename,
                    subfolder: v.subfolder || "",
                    type: v.type || "temp",
                    timestamp: String(Date.now()),
                });
                previewContainer.style.display = "";
                videoEl.src = api.apiURL("/view?" + params.toString());
            }

            if (data?.frame_info?.[0]) {
                const fi = data.frame_info[0];
                const startFmt = formatTime(fi.start);
                const endFmt = formatTime(fi.end);
                const durFmt = formatTime(fi.duration);
                infoEl.textContent =
                    `${fi.count} frames • ${fi.width}×${fi.height}` +
                    ` • ${startFmt}–${endFmt} (${durFmt})` +
                    ` • src ${fi.source_fps}fps → extract ${fi.fps}fps`;
            }
        };

        // --- Upload button + drag-drop ---
        const fileInput = document.createElement("input");
        Object.assign(fileInput, {
            type: "file",
            accept: VIDEO_ACCEPT,
            style: "display: none",
        });
        document.body.append(fileInput);

        // Clean up on node removal
        const origOnRemoved = this.onRemoved;
        this.onRemoved = function (): void {
            clearInterval(pollInterval);
            fileInput?.remove();
            origOnRemoved?.apply(this, arguments as unknown as []);
        };

        const showError = (msg: string): void => {
            flashNode(node, "#7a4a4a");
            infoEl.textContent = msg;
            previewContainer.style.display = "";
            node.setSize([
                node.size[0],
                node.computeSize([node.size[0], node.size[1]])[1],
            ]);
            node?.graph?.setDirtyCanvas(true);
        };

        const uploadBtn = document.createElement("button") as UploadButtonElement;
        uploadBtn.innerHTML = "Upload Video...";
        uploadBtn.setAttribute("aria-label", "Upload Video");
        uploadBtn.style.cssText = `
            width: 100%;
            margin-top: 4px;
            background-color: #222;
            color: #ccc;
            border: 1px solid #333;
            border-radius: 4px;
            padding: 6px;
            cursor: pointer;
            font-family: monospace;
            font-size: 12px;
            transition: background-color 0.2s;
        `;

        let isHovered = false;
        let isFocused = false;
        const updateUploadBtn = (): void => {
            if (uploadBtn.disabled) return;
            const active = isHovered || isFocused;
            uploadBtn.style.backgroundColor = active ? "#333" : "#222";
            uploadBtn.style.outline = isFocused ? "2px solid #4a6a8a" : "none";
            uploadBtn.style.outlineOffset = isFocused ? "2px" : "0px";
        };
        uploadBtn.onmouseenter = (): void => { isHovered = true; updateUploadBtn(); };
        uploadBtn.onmouseleave = (): void => { isHovered = false; updateUploadBtn(); };
        uploadBtn.onfocus = (): void => { isFocused = true; updateUploadBtn(); };
        uploadBtn.onblur = (): void => { isFocused = false; updateUploadBtn(); };
        uploadBtn.onclick = (): void => { fileInput.click(); };
        uploadBtn.onpointerdown = (e: PointerEvent): void => { e.stopPropagation(); };

        this.addDOMWidget("upload_button", "btn", uploadBtn, {
            serialize: false,
        });

        const setUploadState = (uploading: boolean, filename = ""): void => {
            if (uploading) {
                uploadBtn.innerHTML = `<span aria-hidden="true">⏳</span> Uploading...`;
                uploadBtn.setAttribute("aria-label", "Uploading Video");
                uploadBtn.disabled = true;
                uploadBtn.style.cursor = "wait";
                infoEl.textContent = `Uploading ${filename}...`;
                previewContainer.style.display = "";
                videoEl.style.display = "none";
            } else {
                uploadBtn.innerHTML = "Upload Video...";
                uploadBtn.setAttribute("aria-label", "Upload Video");
                uploadBtn.disabled = false;
                uploadBtn.style.cursor = "pointer";
                videoEl.style.display = "block";
            }
            node.setDirtyCanvas(true, true);
            node.setSize([
                node.size[0],
                node.computeSize([node.size[0], node.size[1]])[1],
            ]);
        };

        const handleUpload = async (file: File): Promise<boolean> => {
            setUploadState(true, file.name);
            const body = new FormData();
            body.append("image", file);

            try {
                const resp = await fetch("/upload/image", {
                    method: "POST",
                    body: body,
                });
                if (resp.status !== 200) {
                    showError("Upload failed: " + resp.statusText);
                    return false;
                }
                const data = await resp.json();
                const filename = data.name as string;

                const pathWidget = node.widgets?.find((w: ComfyWidget) => w.name === "video_path");
                if (pathWidget) {
                    const subfolder = (data.subfolder as string) || "";
                    const inputPath = subfolder
                        ? `input/${subfolder}/${filename}`
                        : `input/${filename}`;
                    pathWidget.value = inputPath;
                }

                debouncedPreview();
                flashNode(node, "#4a7a4a");
                return true;
            } catch (err) {
                console.warn("FFMPEGA: Video upload failed", err);
                showError("Upload error: " + err);
                return false;
            } finally {
                setUploadState(false);
            }
        };

        fileInput.onchange = async (): Promise<void> => {
            if (fileInput.files?.length) {
                await handleUpload(fileInput.files[0]);
            }
        };

        // Drag-and-drop support
        this.onDragOver = (e: DragEvent): boolean => {
            if (e?.dataTransfer?.types?.includes?.("Files")) {
                if (!uploadBtn.disabled) {
                    if (!Object.prototype.hasOwnProperty.call(uploadBtn, "_originalInnerHTML")) {
                        uploadBtn._originalInnerHTML = uploadBtn.innerHTML;
                    }
                    if (!Object.prototype.hasOwnProperty.call(uploadBtn, "_originalBorder")) {
                        uploadBtn._originalBorder = uploadBtn.style.border;
                    }
                    if (!Object.prototype.hasOwnProperty.call(uploadBtn, "_originalAriaLabel")) {
                        uploadBtn._originalAriaLabel = uploadBtn.getAttribute("aria-label");
                    }
                    uploadBtn.innerHTML = `<span aria-hidden="true">📂</span> Drop to Upload`;
                    uploadBtn.setAttribute("aria-label", "Drop to Upload");
                    uploadBtn.style.border = "1px dashed #4a6a8a";
                    uploadBtn.style.backgroundColor = "#333";

                    if (uploadBtn._dragTimeout) clearTimeout(uploadBtn._dragTimeout);
                    uploadBtn._dragTimeout = setTimeout(() => {
                        if (!uploadBtn.disabled) {
                            if (Object.prototype.hasOwnProperty.call(uploadBtn, "_originalInnerHTML")) {
                                uploadBtn.innerHTML = uploadBtn._originalInnerHTML!;
                                delete uploadBtn._originalInnerHTML;
                            }
                            if (Object.prototype.hasOwnProperty.call(uploadBtn, "_originalBorder")) {
                                uploadBtn.style.border = uploadBtn._originalBorder!;
                                delete uploadBtn._originalBorder;
                            }
                            if (Object.prototype.hasOwnProperty.call(uploadBtn, "_originalAriaLabel")) {
                                if (uploadBtn._originalAriaLabel) {
                                    uploadBtn.setAttribute("aria-label", uploadBtn._originalAriaLabel);
                                } else {
                                    uploadBtn.removeAttribute("aria-label");
                                }
                                delete uploadBtn._originalAriaLabel;
                            }
                            updateUploadBtn();
                        }
                    }, 100);
                }
                return true;
            }
            return false;
        };

        this.onDragDrop = async (e: DragEvent): Promise<boolean> => {
            if (!e?.dataTransfer?.types?.includes?.("Files")) return false;
            const file = e.dataTransfer?.files?.[0];
            if (!file) return false;

            const ext = file.name.split(".").pop()?.toLowerCase();
            if (!ext || !VIDEO_EXTENSIONS.includes(ext)) {
                showError("Invalid file type: " + ext);
                return false;
            }

            return await handleUpload(file);
        };

        // --- Video preview context menu ---
        const getVideoUrl = (): string | null => videoEl.src || null;
        addVideoPreviewMenu(node, videoEl, previewContainer, previewWidget, getVideoUrl, infoEl);

        return result;
    };
}
