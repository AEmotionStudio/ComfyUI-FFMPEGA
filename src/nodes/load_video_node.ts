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
import { addDownloadOverlay, addVideoPreviewMenu, createUploadButton, flashNode } from "@ffmpega/shared/ui_helpers";
import type { UploadButtonElement } from "@ffmpega/shared/ui_helpers";
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

        // Restore on workflow load — repair invalid combo values from old workflows
        const origConfigure = this.onConfigure;
        this.onConfigure = function (data: unknown): void {
            origConfigure?.apply(this, arguments as unknown as [unknown]);

            // Old workflows may have empty strings at indices where newer
            // widgets now live. Repair invalid values so ComfyUI validation
            // doesn't reject the prompt before execution.
            if (this.widgets) {
                // Combos: reset invalid values to first option (intended default)
                const staticCombos = ["mask_mode", "mask_output_type"];
                // INTs: reset non-numeric values to 0 (their default)
                const intWidgets = ["custom_width", "custom_height"];

                for (const w of this.widgets) {
                    if (w.type === "combo" && staticCombos.includes(w.name) && w.options?.values) {
                        const validValues = w.options.values as string[];
                        if (validValues.length > 0 && !validValues.includes(String(w.value))) {
                            w.value = validValues[0];
                        }
                    }
                    if (intWidgets.includes(w.name)) {
                        const v = w.value;
                        if (v === "" || v === null || v === undefined || isNaN(Number(v))) {
                            w.value = 0;
                        }
                    }
                }
            }
        };

        // Upload button (created early to appear above preview)
        const { fileInput, uploadBtn, updateBtnStyle: updateBtn } = createUploadButton(VIDEO_ACCEPT);
        document.body.append(fileInput);

        this.addDOMWidget("upload_button", "btn", uploadBtn, {
            serialize: false,
        });
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
        let _effEveryNth = 1;
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
            _effEveryNth = everyNth;
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
                // Map elapsed time → raw frame index, then account for nth-frame selection
                const rawFrame = Math.floor(elapsed * _effFps);
                const curFrame = Math.min(
                    Math.floor(rawFrame / _effEveryNth) + 1,
                    _effAvailFrames,
                );
                infoEl.textContent = `▶ ${curFrame}/${_effAvailFrames} • ${_effInfoText}`;
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

        const videoWrapper = document.createElement("div");
        videoWrapper.style.cssText = "position:relative;width:100%;";
        videoWrapper.appendChild(videoEl);
        previewContainer.appendChild(videoWrapper);
        previewContainer.appendChild(infoEl);

        // ── Mask preview overlay ──
        // Canvas overlay that darkens unmasked areas when a mask is set
        const maskOverlayCanvas = document.createElement("canvas");
        maskOverlayCanvas.style.cssText =
            "position:absolute;top:0;left:0;width:100%;height:100%;" +
            "pointer-events:none;z-index:2;display:none;";
        videoWrapper.appendChild(maskOverlayCanvas);

        let _maskOverlayVisible = false;
        let _maskOverlayDataHash = ""; // track changes to avoid redundant redraws

        const showMaskOverlay = (): void => {
            if (_maskOverlayVisible) {
                maskOverlayCanvas.style.display = "block";
            }
        };
        const hideMaskOverlay = (): void => {
            maskOverlayCanvas.style.display = "none";
        };

        // Draw the mask onto the overlay canvas: dark where unmasked, clear where masked
        const drawMaskOverlay = (maskImg: HTMLImageElement): void => {
            const w = videoEl.videoWidth || maskImg.naturalWidth;
            const h = videoEl.videoHeight || maskImg.naturalHeight;
            if (!w || !h) return;

            maskOverlayCanvas.width = w;
            maskOverlayCanvas.height = h;
            const ctx = maskOverlayCanvas.getContext("2d");
            if (!ctx) return;

            // Draw mask to read pixels
            ctx.clearRect(0, 0, w, h);
            ctx.drawImage(maskImg, 0, 0, w, h);
            const imgData = ctx.getImageData(0, 0, w, h);

            // Darken unmasked, clear masked (mask white=255=keep, black=0=darken)
            for (let i = 0; i < imgData.data.length; i += 4) {
                const val = imgData.data[i]; // grayscale mask value
                if (val > 128) {
                    // Masked region: fully transparent (clear)
                    imgData.data[i] = 0;
                    imgData.data[i + 1] = 0;
                    imgData.data[i + 2] = 0;
                    imgData.data[i + 3] = 0;
                } else {
                    // Unmasked region: dark wash
                    imgData.data[i] = 0;
                    imgData.data[i + 1] = 0;
                    imgData.data[i + 2] = 0;
                    imgData.data[i + 3] = 140;
                }
            }
            ctx.putImageData(imgData, 0, 0);

            _maskOverlayVisible = true;
            showMaskOverlay();
        };

        // Refresh the mask overlay from current widget data
        const refreshMaskOverlay = (): void => {
            const showWidget = node.widgets?.find(
                (w: ComfyWidget) => w.name === "show_mask_preview",
            );
            const showMask = showWidget?.value !== false;

            const mpWidget = node.widgets?.find(
                (w: ComfyWidget) => w.name === "mask_points_data",
            );
            const maskData = mpWidget?.value ? String(mpWidget.value) : "";

            if (!showMask || !maskData || maskData === "undefined") {
                _maskOverlayVisible = false;
                hideMaskOverlay();
                _maskOverlayDataHash = "";
                return;
            }

            // Check if data changed
            const hash = maskData.slice(0, 100) + maskData.length;
            if (hash === _maskOverlayDataHash) return;
            _maskOverlayDataHash = hash;

            try {
                const ptData = JSON.parse(maskData);

                if (ptData.mode === "draw" && ptData.mask_data) {
                    // Draw/nudge mode: decode base64 mask directly
                    const img = new Image();
                    img.onload = () => drawMaskOverlay(img);
                    img.src = "data:image/png;base64," + ptData.mask_data;
                } else if (ptData.points?.length > 0 || ptData.box) {
                    // Point/box mode: fetch raw mask from SAM3 endpoint
                    const vidWidget = node.widgets?.find(
                        (w: ComfyWidget) => w.name === "video",
                    );
                    if (!vidWidget?.value) return;

                    // Get frame path via first_frame endpoint
                    fetch("/ffmpega/first_frame", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            video_path: "input/" + String(vidWidget.value),
                        }),
                    })
                        .then(r => r.json())
                        .then((info: { frame_path?: string }) => {
                            // We need a frame image. Use the SAM3 endpoint to get raw mask
                            const body: Record<string, unknown> = {
                                frame_path: info.frame_path || "",
                                points: ptData.points || [],
                                labels: ptData.labels || [],
                                image_width: ptData.image_width || 0,
                                image_height: ptData.image_height || 0,
                                multi_object: ptData.mask_multi_object || false,
                                edge_refine: ptData.mask_edge_refine ?? false,
                            };
                            if (ptData.box) body.box = ptData.box;

                            return fetch("/ffmpega/sam3_point_mask", {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify(body),
                            });
                        })
                        .then(r => r.json())
                        .then((data: { raw_mask_b64?: string }) => {
                            if (data.raw_mask_b64) {
                                const img = new Image();
                                img.onload = () => drawMaskOverlay(img);
                                img.src = "data:image/png;base64," + data.raw_mask_b64;
                            }
                        })
                        .catch(() => { /* silently fail */ });
                }
            } catch {
                // Invalid JSON
            }
        };

        // Hide overlay during playback, show when paused
        videoEl.addEventListener("play", hideMaskOverlay);
        videoEl.addEventListener("pause", showMaskOverlay);
        videoEl.addEventListener("ended", showMaskOverlay);
        videoEl.addEventListener("loadedmetadata", () => {
            setTimeout(refreshMaskOverlay, 500);
        });

        // Poll for widget changes (show_mask_preview toggle or mask_points_data update)
        let _maskPollHash = "";
        const maskPollInterval = setInterval(() => {
            if (!node.graph) {
                clearInterval(maskPollInterval);
                return;
            }
            const showW = node.widgets?.find(
                (w: ComfyWidget) => w.name === "show_mask_preview",
            );
            const mpW = node.widgets?.find(
                (w: ComfyWidget) => w.name === "mask_points_data",
            );
            const pollHash = `${showW?.value}|${mpW?.value ? String(mpW.value).length : 0}`;
            if (pollHash !== _maskPollHash) {
                _maskPollHash = pollHash;
                refreshMaskOverlay();
            }
        }, 1000);

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

        // --- Upload/error helpers ---
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

        // Cleanup
        const origOnRemoved = this.onRemoved;
        this.onRemoved = function (): void {
            clearInterval(lvPollInterval);
            clearInterval(maskPollInterval);
            fileInput?.remove();
            origOnRemoved?.apply(this, arguments as unknown as []);
        };

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
                    }, 500);
                }
                return true;
            }
            return false;
        };

        this.onDragDrop = async (e: DragEvent): Promise<boolean> => {
            // Cancel drop visual revert — upload state handler takes over
            if (uploadBtn._dragTimeout) {
                clearTimeout(uploadBtn._dragTimeout);
                delete uploadBtn._dragTimeout;
            }
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
