/**
 * FFMPEGALoadVideoPath node UI handler.
 *
 * Features:
 * - Video preview with upload/drag-drop
 * - Dynamic output slots (images/audio) — hidden until inputs connected
 * - Live frame counter + playback clamping to effective range
 * - Widget polling for live info updates
 */

import { api } from "comfyui/api";
import { addDownloadOverlay, addVideoPreviewMenu, flashNode } from "@ffmpega/shared/ui_helpers";
import type { ComfyNodeType, ComfyNodeData, ComfyNode, ComfyWidget } from "@ffmpega/types/comfyui";

// ---- Type definitions ----

interface LoadVideoNode extends ComfyNode {
    findInputSlot(name: string): number;
    findOutputSlot(name: string): number;
    addOutput(name: string, type: string): void;
    removeOutput(index: number): void;
    onConnectionsChange?: (
        type: number, slotIndex: number, isConnected: boolean,
        link: unknown, ioSlot: unknown,
    ) => void;
    onConfigure?: (data: unknown) => void;
    onExecuted?: (data: LoadVideoExecutionData) => void;
    onRemoved?: () => void;
    onDragOver?: (e: DragEvent) => boolean;
    onDragDrop?: (e: DragEvent) => Promise<boolean>;
    addDOMWidget(name: string, type: string, el: HTMLElement, opts?: Record<string, unknown>): ComfyWidget;
}

interface LoadVideoExecutionData {
    video?: Array<{ filename: string; subfolder?: string; type?: string }>;
    video_info?: Array<{
        source_width?: number; source_height?: number;
        source_fps?: number; source_duration?: number;
        source_frames?: number;
    }>;
}

/** Cached video metadata from ffprobe or the video element */
interface VideoMeta {
    width: number;
    height: number;
    fps: number;
    duration: number;
    frames: number;
}

/** Button with drag-drop transient state */
interface UploadButtonElement extends HTMLButtonElement {
    _originalInnerHTML?: string;
    _originalBorder?: string;
    _originalAriaLabel?: string | null;
    _dragTimeout?: ReturnType<typeof setTimeout>;
}

/** Video widget with combo dropdown options */
interface VideoDropdownWidget extends ComfyWidget {
    options: { values: string[] };
    callback?: (value: string) => void;
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

const TRIM_WIDGETS = ["force_rate", "skip_first_frames", "frame_load_cap", "select_every_nth"];

const PASSTHROUGH_EVENTS = [
    "contextmenu", "pointerdown", "mousewheel",
    "pointermove", "pointerup",
] as const;

// ---- Helpers ----

/** Format seconds as m:ss.s or ss.s */
function formatTimeLV(sec: number): string {
    if (sec < 0) sec = 0;
    const m = Math.floor(sec / 60);
    const s = (sec % 60).toFixed(1);
    return m > 0 ? `${m}:${s.padStart(4, "0")}` : `${s}s`;
}

// ---- Registration ----

export function registerLoadVideoNode(
    nodeType: ComfyNodeType,
    nodeData: ComfyNodeData,
): void {
    if (nodeData.name !== "FFMPEGALoadVideoPath") return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;

    nodeType.prototype.onNodeCreated = function (this: LoadVideoNode) {
        const result = onNodeCreated?.apply(this, arguments as unknown as []);
        const node = this;

        this.color = "#5a4a2a";
        this.bgcolor = "#4a3a1a";

        // --- Dynamic output slot visibility ---
        const _syncDynamicOutputs = (): void => {
            const imagesIn = node.findInputSlot("images");
            const audioIn = node.findInputSlot("audio");

            const anyConnected =
                (imagesIn >= 0 && node.inputs[imagesIn].link != null) ||
                (audioIn >= 0 && node.inputs[audioIn].link != null);

            const imagesOut = node.findOutputSlot("images");
            const audioOut = node.findOutputSlot("audio");
            const hasOutputs = imagesOut >= 0 || audioOut >= 0;

            if (anyConnected && !hasOutputs) {
                node.addOutput("images", "IMAGE");
                node.addOutput("audio", "AUDIO");
            } else if (!anyConnected && hasOutputs) {
                const aIdx = node.findOutputSlot("audio");
                if (aIdx >= 0) node.removeOutput(aIdx);
                const iIdx = node.findOutputSlot("images");
                if (iIdx >= 0) node.removeOutput(iIdx);
            }

            node.setDirtyCanvas(true, true);
        };

        // Initial state: remove both outputs
        requestAnimationFrame(() => {
            const aIdx = node.findOutputSlot("audio");
            if (aIdx >= 0) node.removeOutput(aIdx);
            const iIdx = node.findOutputSlot("images");
            if (iIdx >= 0) node.removeOutput(iIdx);
            node.setDirtyCanvas(true, true);
        });

        // React to connection changes
        const origOnCC = this.onConnectionsChange;
        this.onConnectionsChange = function (
            type: number, slotIndex: number,
            isConnected: boolean, link: unknown, ioSlot: unknown,
        ): void {
            origOnCC?.apply(this, arguments as unknown as [number, number, boolean, unknown, unknown]);
            if (type === LiteGraph.INPUT) {
                const name = this.inputs?.[slotIndex]?.name;
                if (name === "images" || name === "audio") {
                    _syncDynamicOutputs();
                }
            }
        };

        // Restore on workflow load
        const origConfigure = this.onConfigure;
        this.onConfigure = function (data: unknown): void {
            origConfigure?.apply(this, arguments as unknown as [unknown]);
            requestAnimationFrame(_syncDynamicOutputs);
        };

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
        videoEl.setAttribute("aria-label", "Video preview");
        videoEl.style.cssText = "width:100%;display:block;";

        // Playback position tracking for live frame counter
        let _srcMeta: VideoMeta | null = null;
        let _effAvailFrames = 0;
        let _effFps = 0;
        let _effSkipFirst = 0;
        let _effInfoText = "";

        // Info overlay (defined early — referenced by videoEl events)
        const infoEl = document.createElement("div");
        infoEl.style.cssText =
            "padding:4px 8px;font-size:11px;color:#aaa;" +
            "font-family:monospace;background:#111;";
        infoEl.textContent = "No video selected";
        infoEl.setAttribute("role", "status");
        infoEl.setAttribute("aria-live", "polite");

        // --- Dynamic info bar calculation ---
        const updateDynamicInfo = (): void => {
            if (!_srcMeta) {
                infoEl.textContent = "No video selected";
                return;
            }

            const forceRate = (node.widgets?.find((w: ComfyWidget) => w.name === "force_rate")?.value as number) ?? 0;
            const skipFirst = (node.widgets?.find((w: ComfyWidget) => w.name === "skip_first_frames")?.value as number) ?? 0;
            const frameCap = (node.widgets?.find((w: ComfyWidget) => w.name === "frame_load_cap")?.value as number) ?? 0;
            const everyNth = (node.widgets?.find((w: ComfyWidget) => w.name === "select_every_nth")?.value as number) ?? 1;

            const srcFps = _srcMeta.fps || 24;
            const srcDuration = _srcMeta.duration || 0;
            const srcFrames = _srcMeta.frames || Math.round(srcDuration * srcFps);

            const effFps = forceRate > 0 ? forceRate : srcFps;

            let availFrames = forceRate > 0
                ? Math.ceil(srcDuration * forceRate)
                : srcFrames;

            availFrames = Math.max(0, availFrames - skipFirst);
            if (everyNth > 1) {
                availFrames = Math.max(0, Math.floor(availFrames / everyNth));
            }
            if (frameCap > 0) {
                availFrames = Math.min(availFrames, frameCap);
            }

            const effDuration = effFps > 0 && availFrames > 0
                ? availFrames / effFps
                : srcDuration;

            const startTime = effFps > 0 ? skipFirst / effFps : 0;

            const parts: string[] = [];
            if (_srcMeta.width && _srcMeta.height) {
                parts.push(`${_srcMeta.width}×${_srcMeta.height}`);
            }
            if (forceRate > 0 && forceRate !== srcFps) {
                parts.push(`${srcFps}fps → ${forceRate}fps`);
            } else {
                parts.push(`${srcFps}fps`);
            }
            if (availFrames !== srcFrames) {
                parts.push(`${availFrames} frames (of ${srcFrames})`);
            } else {
                parts.push(`${availFrames} frames`);
            }
            if (Math.abs(effDuration - srcDuration) > 0.1) {
                parts.push(`${formatTimeLV(effDuration)} (of ${formatTimeLV(srcDuration)})`);
            } else {
                parts.push(formatTimeLV(srcDuration));
            }
            if (startTime > 0.05) {
                parts.push(`from ${formatTimeLV(startTime)}`);
            }

            infoEl.textContent = parts.join(" • ");
            _effInfoText = infoEl.textContent;
            _effAvailFrames = availFrames;
            _effFps = effFps;
            _effSkipFirst = skipFirst;
        };

        videoEl.addEventListener("loadedmetadata", () => {
            previewWidget.aspectRatio =
                videoEl.videoWidth / videoEl.videoHeight;

            _srcMeta = {
                width: videoEl.videoWidth,
                height: videoEl.videoHeight,
                fps: 0,
                duration: videoEl.duration,
                frames: 0,
            };

            // Fetch accurate metadata via ffprobe
            const vidWidget = node.widgets?.find((w: ComfyWidget) => w.name === "video");
            if (vidWidget?.value) {
                const infoParams = new URLSearchParams({
                    path: "input/" + String(vidWidget.value),
                });
                fetch(api.apiURL("/ffmpega/video_info?" + infoParams.toString()))
                    .then(r => r.json())
                    .then((info: { fps?: number; frames?: number; duration?: number }) => {
                        if (info?.fps && _srcMeta) {
                            _srcMeta.fps = info.fps;
                            _srcMeta.frames = info.frames || Math.round((info.duration ?? 0) * info.fps);
                            _srcMeta.duration = info.duration || _srcMeta.duration;
                        }
                        updateDynamicInfo();
                    })
                    .catch(() => updateDynamicInfo());
            } else {
                updateDynamicInfo();
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

        // --- Widget polling for live updates ---
        let _lvDebounce: ReturnType<typeof setTimeout> | null = null;
        const lvWidgetValues: Record<string, unknown> = {};

        // Playback range clamping
        let _playStart = 0;
        let _playEnd = Infinity;

        videoEl.addEventListener("timeupdate", () => {
            if (_playEnd < Infinity && videoEl.currentTime >= _playEnd) {
                videoEl.currentTime = _playStart;
            }
            if (_srcMeta && _srcMeta.fps > 0 && _effAvailFrames > 0 && _effInfoText) {
                const elapsed = Math.max(0, videoEl.currentTime - _playStart);
                const curFrame = Math.min(
                    Math.floor(elapsed * _effFps) + 1,
                    _effAvailFrames,
                );
                const srcFrame = curFrame + _effSkipFirst;
                infoEl.textContent = `▶ ${curFrame}/${_effAvailFrames} (src frame ${srcFrame}) • ${_effInfoText}`;
            }
        });

        const updatePlaybackRange = (): void => {
            if (!_srcMeta || !_srcMeta.fps) return;

            const forceRate = (node.widgets?.find((w: ComfyWidget) => w.name === "force_rate")?.value as number) ?? 0;
            const skipFirst = (node.widgets?.find((w: ComfyWidget) => w.name === "skip_first_frames")?.value as number) ?? 0;
            const frameCap = (node.widgets?.find((w: ComfyWidget) => w.name === "frame_load_cap")?.value as number) ?? 0;
            const everyNth = (node.widgets?.find((w: ComfyWidget) => w.name === "select_every_nth")?.value as number) ?? 1;

            const srcFps = _srcMeta.fps;
            const effFps = forceRate > 0 ? forceRate : srcFps;

            _playStart = effFps > 0 ? skipFirst / effFps : 0;

            let availFrames = forceRate > 0
                ? Math.ceil(_srcMeta.duration * forceRate)
                : (_srcMeta.frames || Math.round(_srcMeta.duration * srcFps));
            availFrames = Math.max(0, availFrames - skipFirst);
            if (everyNth > 1) availFrames = Math.floor(availFrames / everyNth);
            if (frameCap > 0) availFrames = Math.min(availFrames, frameCap);

            if (effFps > 0 && availFrames > 0) {
                _playEnd = _playStart + (availFrames / effFps);
            } else {
                _playEnd = Infinity;
            }

            if (isFinite(_playEnd) && _playEnd > _srcMeta.duration) {
                _playEnd = _srcMeta.duration;
            }

            if (isFinite(_playStart) && _playStart < videoEl.duration) {
                videoEl.currentTime = _playStart;
            }
        };

        const lvPollInterval = setInterval(() => {
            if (!node.graph) {
                clearInterval(lvPollInterval);
                return;
            }
            let changed = false;
            for (const name of TRIM_WIDGETS) {
                const w = node.widgets?.find((ww: ComfyWidget) => ww.name === name);
                if (w && lvWidgetValues[name] !== w.value) {
                    lvWidgetValues[name] = w.value;
                    changed = true;
                }
            }
            if (changed) {
                if (_lvDebounce) clearTimeout(_lvDebounce);
                _lvDebounce = setTimeout(() => {
                    updateDynamicInfo();
                    updatePlaybackRange();
                }, 300);
            }
        }, 500);

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

        // Update preview from filename
        const updatePreview = (filename: string | null | undefined): void => {
            if (!filename) {
                previewContainer.style.display = "none";
                infoEl.textContent = "No video selected";
                _srcMeta = null;
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

        // --- Upload widget ---
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

        const videoWidget = this.widgets?.find(
            (w: ComfyWidget) => w.name === "video",
        ) as VideoDropdownWidget | undefined;

        const fileInput = document.createElement("input");
        Object.assign(fileInput, {
            type: "file",
            accept: VIDEO_ACCEPT,
            style: "display: none",
        });
        document.body.append(fileInput);

        // Cleanup
        const origOnRemoved = this.onRemoved;
        this.onRemoved = function (): void {
            clearInterval(lvPollInterval);
            fileInput?.remove();
            origOnRemoved?.apply(this, arguments as unknown as []);
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
        const updateBtn = (): void => {
            if (uploadBtn.disabled) return;
            const active = isHovered || isFocused;
            uploadBtn.style.backgroundColor = active ? "#333" : "#222";
            uploadBtn.style.outline = isFocused ? "2px solid #4a6a8a" : "none";
            uploadBtn.style.outlineOffset = isFocused ? "2px" : "0px";
        };
        uploadBtn.onmouseenter = (): void => { isHovered = true; updateBtn(); };
        uploadBtn.onmouseleave = (): void => { isHovered = false; updateBtn(); };
        uploadBtn.onfocus = (): void => { isFocused = true; updateBtn(); };
        uploadBtn.onblur = (): void => { isFocused = false; updateBtn(); };
        uploadBtn.onclick = (): void => { fileInput.click(); };
        uploadBtn.onpointerdown = (e: PointerEvent): void => { e.stopPropagation(); };

        this.addDOMWidget("upload_button", "btn", uploadBtn, {
            serialize: false,
        });

        const setUploadState = (isUploading: boolean, filename = ""): void => {
            if (isUploading) {
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

                if (videoWidget) {
                    if (!videoWidget.options.values.includes(filename)) {
                        videoWidget.options.values.push(filename);
                    }
                    videoWidget.value = filename;
                    videoWidget.callback?.(filename);
                }
                updatePreview(filename);
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

        // Drag-and-drop
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
                            updateBtn();
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

        // Watch dropdown for selection changes
        if (videoWidget) {
            const origCallback = videoWidget.callback;
            videoWidget.callback = function (value: string): void {
                origCallback?.apply(this, arguments as unknown as [string]);
                updatePreview(value);
            };
            if (videoWidget.value) {
                setTimeout(() => updatePreview(videoWidget.value as string), 100);
            }
        }

        // Handle execution results
        const origOnExecuted = this.onExecuted;
        this.onExecuted = function (this: LoadVideoNode, data: LoadVideoExecutionData): void {
            origOnExecuted?.apply(this, arguments as unknown as [LoadVideoExecutionData]);

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

            if (data?.video_info?.[0]) {
                const info = data.video_info[0];
                _srcMeta = {
                    width: info.source_width || _srcMeta?.width || 0,
                    height: info.source_height || _srcMeta?.height || 0,
                    fps: info.source_fps || _srcMeta?.fps || 24,
                    duration: info.source_duration || _srcMeta?.duration || 0,
                    frames: info.source_frames || _srcMeta?.frames || 0,
                };
                updateDynamicInfo();
            }
        };

        // Context menu
        const getVideoUrlLoad = (): string | null => videoEl.src || null;
        addVideoPreviewMenu(node, videoEl, previewContainer, previewWidget, getVideoUrlLoad, infoEl);

        return result;
    };
}
