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
import {
    addDownloadOverlay, addVideoPreviewMenu, attachFileDropZone,
    attachPlayheadTracker, createUploadButton, fitHeight, flashNode,
    frameAtTime, rangeEndSeconds, toggleWidget,
} from "@ffmpega/shared/ui_helpers";
import type { PlayheadCause, UploadButtonElement } from "@ffmpega/shared/ui_helpers";
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

/** Mask sub-widgets gated behind the enable_mask toggle. */
const MASK_WIDGETS = [
    "mask_mode", "mask_output_type", "sam_version", "show_mask_preview",
] as const;

/**
 * Widget order as of the enable_mask release, and the order before it.
 * Used to un-shift widget values loaded from pre-enable_mask workflows —
 * ComfyUI restores widgets_values positionally, so inserting enable_mask
 * mid-list slides every later value onto the wrong widget.
 */
const LEGACY_SHIFTED_WIDGETS = [
    "enable_mask", "mask_mode", "mask_output_type", "sam_version",
    "show_mask_preview", "custom_width", "custom_height",
];

/** Fixed row height (px) for the upload button DOM widget. */
const UPLOAD_BTN_HEIGHT = 26;

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

        // --- enable_mask toggle → mask sub-widget visibility ---
        const updateMaskVisibility = (): void => {
            const enableMask = node.widgets?.find((w: ComfyWidget) => w.name === "enable_mask");
            const show = Boolean(enableMask?.value);
            for (const name of MASK_WIDGETS) {
                const w = node.widgets?.find((ww: ComfyWidget) => ww.name === name);
                if (w) toggleWidget(w, show);
            }
            fitHeight(node);
        };

        const enableMaskWidget = this.widgets?.find(
            (w: ComfyWidget) => w.name === "enable_mask",
        );
        if (enableMaskWidget) {
            updateMaskVisibility();
            const origMaskCb = enableMaskWidget.callback;
            enableMaskWidget.callback = function (...args: unknown[]) {
                origMaskCb?.apply(this, args);
                updateMaskVisibility();
            };
        }

        /**
         * Un-shift widget values from workflows saved before `enable_mask`
         * existed. ComfyUI restores widgets_values positionally, so a widget
         * inserted mid-list slides every later value one slot earlier —
         * enable_mask lands on the old mask_mode string, mask_mode on the old
         * mask_output_type, and so on. A string in the BOOLEAN enable_mask is
         * the tell — workflows predating mask_mode entirely fall short of this
         * index and keep their defaults, so they correctly skip the repair.
         */
        const repairLegacyWidgetShift = (): void => {
            const widgets = node.widgets;
            if (!widgets) return;

            const shifted = LEGACY_SHIFTED_WIDGETS.map(
                name => widgets.find((w: ComfyWidget) => w.name === name),
            );
            const enableMask = shifted[0];
            if (!enableMask || typeof enableMask.value !== "string") return;

            // Slide each loaded value one widget later, then derive the toggle
            // from the mask_mode value that landed on enable_mask.
            const loaded = shifted.map(w => w?.value);
            for (let i = shifted.length - 1; i > 0; i--) {
                const w = shifted[i];
                if (w) w.value = loaded[i - 1];
            }
            enableMask.value = String(loaded[0]) !== "none";
        };

        // Restore on workflow load — repair invalid combo values from old workflows
        const origConfigure = this.onConfigure;
        this.onConfigure = function (data: unknown): void {
            origConfigure?.apply(this, arguments as unknown as [unknown]);

            repairLegacyWidgetShift();

            // Old workflows may have empty strings at indices where newer
            // widgets now live. Repair invalid values so ComfyUI validation
            // doesn't reject the prompt before execution.
            if (this.widgets) {
                // Combos: reset invalid values to first option (intended default)
                const staticCombos = ["mask_mode", "mask_output_type"];
                // INTs: reset non-numeric values to 0 (their default)
                const intWidgets = ["custom_width", "custom_height"];

                for (const w of this.widgets) {
                    // _origType, not type — toggleWidget rewrites `type` to
                    // "hidden" while collapsed, but the value is still sent
                    // to the backend and still has to validate.
                    const wType = w._origType ?? w.type;
                    if (wType === "combo" && staticCombos.includes(w.name) && w.options?.values) {
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

            // Re-apply after saved widget values are restored
            updateMaskVisibility();
        };

        // Upload button (created early to appear above preview)
        const { fileInput, uploadBtn, updateBtnStyle: updateBtn } = createUploadButton(VIDEO_ACCEPT);
        document.body.append(fileInput);

        // Pin to a fixed row. ComfyUI's arrangeWidgets gives widgets with a
        // computeSize a fixed height and splits the node's leftover height
        // among the rest — without this the button is the only flexible
        // widget left and stretches to fill the node.
        uploadBtn.style.height = `${UPLOAD_BTN_HEIGHT}px`;
        uploadBtn.style.boxSizing = "border-box";
        const uploadWidget = this.addDOMWidget("upload_button", "btn", uploadBtn, {
            serialize: false,
        });
        uploadWidget.computeSize = (): [number, number] => [0, UPLOAD_BTN_HEIGHT];
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

        // Effective (post-trim) figures behind the info bar, recomputed by
        // updateDynamicInfo() and read by the live frame counter.
        let _srcMeta: VideoMeta | null = null;
        let _effAvailFrames = 0;
        let _effFps = 0;
        let _effEveryNth = 1;
        /** Segments shown before the frame count: resolution, frame rate. */
        let _infoHead: string[] = [];
        /** Segments shown after it: duration, in-point. */
        let _infoTail: string[] = [];
        /** " (of N)" source-frame context, empty when nothing is trimmed. */
        let _infoOfSrc = "";

        // Info overlay (defined early — referenced by videoEl events)
        const infoEl = document.createElement("div");
        infoEl.style.cssText =
            "padding:4px 8px;font-size:11px;color:#aaa;" +
            "font-family:monospace;background:#111;";
        infoEl.textContent = "No video selected";
        infoEl.setAttribute("role", "status");
        infoEl.setAttribute("aria-live", "polite");

        // --- Trim widget annotations ---
        // Dim "N left" suffixes on the trim spinners. Written to `label`
        // (drawn as displayName in the theme's secondary colour) rather than
        // a custom draw override — a widget-level `draw` replaces ComfyUI's
        // built-in rendering wholesale instead of layering on top of it.
        const setTrimLabel = (name: string, suffix: string | null): void => {
            const w = node.widgets?.find((ww: ComfyWidget) => ww.name === name);
            if (!w) return;
            if (suffix) {
                w.label = `${w.name} · ${suffix}`;
            } else {
                delete w.label;
            }
        };

        const clearTrimLabels = (): void => {
            setTrimLabel("skip_first_frames", null);
            setTrimLabel("frame_load_cap", null);
            node.setDirtyCanvas(true, true);
        };

        // --- Dynamic info bar calculation ---
        const updateDynamicInfo = (): void => {
            if (!_srcMeta) {
                infoEl.textContent = "No video selected";
                clearTrimLabels();
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

            // Frame budget, stage by stage: source → after skip → after nth
            // → after cap. The intermediates feed the trim widget labels.
            const baseFrames = forceRate > 0
                ? Math.ceil(srcDuration * forceRate)
                : srcFrames;

            const afterSkip = Math.max(0, baseFrames - skipFirst);
            const afterNth = everyNth > 1
                ? Math.max(0, Math.floor(afterSkip / everyNth))
                : afterSkip;
            const availFrames = frameCap > 0
                ? Math.min(afterNth, frameCap)
                : afterNth;

            setTrimLabel("skip_first_frames", `${afterSkip} left`);
            setTrimLabel(
                "frame_load_cap",
                frameCap > 0 ? `${afterNth - availFrames} left` : `all ${afterNth}`,
            );
            node.setDirtyCanvas(true, true);

            // Playing the selected frames back at effFps is what makes this the
            // *output* duration; the playback range in source time is longer
            // whenever select_every_nth skips frames (see rangeEndSeconds).
            const effDuration = effFps > 0 && availFrames > 0
                ? availFrames / effFps
                : srcDuration;

            const startTime = effFps > 0 ? skipFirst / effFps : 0;

            const head: string[] = [];
            if (_srcMeta.width && _srcMeta.height) {
                head.push(`${_srcMeta.width}×${_srcMeta.height}`);
            }
            if (forceRate > 0 && forceRate !== srcFps) {
                head.push(`${srcFps}fps → ${forceRate}fps`);
            } else {
                head.push(`${srcFps}fps`);
            }

            const tail: string[] = [];
            if (Math.abs(effDuration - srcDuration) > 0.1) {
                tail.push(`${formatTimeLV(effDuration)} (of ${formatTimeLV(srcDuration)})`);
            } else {
                tail.push(formatTimeLV(srcDuration));
            }
            if (startTime > 0.05) {
                tail.push(`from ${formatTimeLV(startTime)}`);
            }

            _infoHead = head;
            _infoTail = tail;
            _infoOfSrc = availFrames !== srcFrames ? ` (of ${srcFrames})` : "";
            _effAvailFrames = availFrames;
            _effFps = effFps;
            _effEveryNth = everyNth;

            paintInfo();
        };

        /**
         * Assemble the info bar.
         *
         * With no `currentFrame` the frame total sits in its usual place,
         * between the frame rate and the duration. Given one, that segment
         * becomes the playhead and moves to the front, where a number that
         * changes several times a second is easiest to read — and where it
         * cannot be mistaken for the static total it replaces. The ▶ marks
         * playback; a paused scrub still reports the frame it landed on.
         */
        const buildInfoText = (currentFrame?: number, playing = false): string => {
            if (!_srcMeta) return "No video selected";
            if (currentFrame === undefined) {
                return [
                    ..._infoHead,
                    `${_effAvailFrames} frames${_infoOfSrc}`,
                    ..._infoTail,
                ].join(" • ");
            }
            const marker = playing ? "▶ " : "";
            return [
                `${marker}${currentFrame}/${_effAvailFrames}f${_infoOfSrc}`,
                ..._infoHead,
                ..._infoTail,
            ].join(" • ");
        };

        const paintInfo = (currentFrame?: number, playing = false): void => {
            infoEl.textContent = buildInfoText(currentFrame, playing);
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
        let _lastTime = 0;

        const detachPlayhead = attachPlayheadTracker(
            videoEl,
            (time: number, playing: boolean, cause: PlayheadCause) => {
                // Loop back to the in-point only when playback runs off the
                // out-point on its own. A seek — the scrubber, or the "Jump:"
                // menu items — must never be undone; and once the user has
                // deliberately parked past the out-point, playing on from
                // there is their call too, which is what the previous-tick
                // test preserves.
                if (
                    cause === "frame" && playing && _playEnd < Infinity
                    && time >= _playEnd && _lastTime < _playEnd
                ) {
                    videoEl.currentTime = _playStart;
                    _lastTime = _playStart;
                    return;
                }
                _lastTime = time;

                // Nothing to count against until the trim maths has run.
                if (!_srcMeta || _effAvailFrames <= 0) return;
                const frame = frameAtTime(
                    time - _playStart, _effFps, _effEveryNth, _effAvailFrames,
                );
                paintInfo(frame > 0 ? frame : undefined, playing);
            },
        );

        const updatePlaybackRange = (): void => {
            if (!_srcMeta) return;

            const forceRate = (node.widgets?.find((w: ComfyWidget) => w.name === "force_rate")?.value as number) ?? 0;
            const skipFirst = (node.widgets?.find((w: ComfyWidget) => w.name === "skip_first_frames")?.value as number) ?? 0;
            const frameCap = (node.widgets?.find((w: ComfyWidget) => w.name === "frame_load_cap")?.value as number) ?? 0;
            const everyNth = (node.widgets?.find((w: ComfyWidget) => w.name === "select_every_nth")?.value as number) ?? 1;

            // Same fallback the info bar uses — ffprobe may not have answered
            // yet, and a range built on a different rate than the one on
            // display would clamp playback somewhere the numbers don't explain.
            const srcFps = _srcMeta.fps || 24;
            const effFps = forceRate > 0 ? forceRate : srcFps;

            const prevStart = _playStart;
            _playStart = effFps > 0 ? skipFirst / effFps : 0;

            let availFrames = forceRate > 0
                ? Math.ceil(_srcMeta.duration * forceRate)
                : (_srcMeta.frames || Math.round(_srcMeta.duration * srcFps));
            availFrames = Math.max(0, availFrames - skipFirst);
            if (everyNth > 1) availFrames = Math.floor(availFrames / everyNth);
            if (frameCap > 0) availFrames = Math.min(availFrames, frameCap);

            _playEnd = rangeEndSeconds(_playStart, availFrames, everyNth, effFps);

            if (isFinite(_playEnd) && _playEnd > _srcMeta.duration) {
                _playEnd = _srcMeta.duration;
            }

            // Chase the in-point only when it actually moved. Editing
            // frame_load_cap or select_every_nth leaves the start alone, and
            // should leave the position the user scrubbed to alone with it.
            if (
                _playStart !== prevStart
                && isFinite(_playStart) && _playStart < videoEl.duration
            ) {
                videoEl.currentTime = _playStart;
            }
        };

        // Seed the cache with what the widgets already hold, so the first tick
        // reports only real edits. An empty cache makes every widget look
        // changed, which used to fire a range update — and a seek to the
        // in-point — about 800 ms after the node appeared.
        for (const name of TRIM_WIDGETS) {
            const w = node.widgets?.find((ww: ComfyWidget) => ww.name === name);
            if (w) lvWidgetValues[name] = w.value;
        }

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

        // ── File drop overlay ──
        // Shown while a file drag is over the node. Sits above the mask
        // overlay (z 2) and the download button (z 10); pointer-events:none
        // keeps previewContainer itself as the drop target.
        const dropOverlay = document.createElement("div");
        dropOverlay.style.cssText =
            "position:absolute;inset:0;display:none;z-index:20;" +
            "flex-direction:column;align-items:center;justify-content:center;gap:6px;" +
            "background:rgba(74,106,138,0.18);border:2px dashed #4a6a8a;" +
            "border-radius:6px;color:#cfe3f5;font-family:monospace;font-size:12px;" +
            "pointer-events:none;";
        dropOverlay.innerHTML =
            `<span style="font-size:22px" aria-hidden="true">🎞</span>` +
            `<span>Drop video to load</span>`;
        previewContainer.appendChild(dropOverlay);

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
            const enableWidget = node.widgets?.find(
                (w: ComfyWidget) => w.name === "enable_mask",
            );
            const showWidget = node.widgets?.find(
                (w: ComfyWidget) => w.name === "show_mask_preview",
            );
            // enable_mask off means no mask is generated, so don't leave a
            // stale overlay on the preview from a previous session.
            const showMask = Boolean(enableWidget?.value) && showWidget?.value !== false;

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
            const enableW = node.widgets?.find(
                (w: ComfyWidget) => w.name === "enable_mask",
            );
            const showW = node.widgets?.find(
                (w: ComfyWidget) => w.name === "show_mask_preview",
            );
            const mpW = node.widgets?.find(
                (w: ComfyWidget) => w.name === "mask_points_data",
            );
            const pollHash = `${enableW?.value}|${showW?.value}|${mpW?.value ? String(mpW.value).length : 0}`;
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
            // Drop the outgoing clip's frame budget either way — until the new
            // one has been probed there is nothing to count a playhead against.
            _effAvailFrames = 0;
            if (!filename) {
                previewContainer.style.display = "none";
                infoEl.textContent = "No video selected";
                _srcMeta = null;
                clearTrimLabels();
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
            if (_dragTimer) clearTimeout(_dragTimer);
            detachPlayhead();
            detachPreviewDrop();
            detachButtonDrop();
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
                // api.fetchApi, not a bare fetch — it resolves the route
                // through api_base + "/api" and attaches the Comfy-User and
                // auth headers. A bare "/upload/image" misses all three.
                const resp = await api.fetchApi("/upload/image", {
                    method: "POST",
                    body: body,
                });
                if (resp.status !== 200) {
                    const detail = await resp.text().catch(() => "");
                    console.error(
                        "FFMPEGA: video upload failed",
                        resp.status, resp.statusText, detail,
                    );
                    showError(`Upload failed (${resp.status}): ${resp.statusText}`);
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
                console.error("FFMPEGA: video upload threw", err);
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

        // --- Drag-and-drop ---
        // Three regions can receive a drop: the canvas-drawn widget rows (via
        // LiteGraph's onDragOver/onDragDrop) and the two DOM widgets, which
        // sit above the canvas and would otherwise swallow the event. All
        // three funnel through the same accept/upload pair.
        const acceptVideoFile = (file: File): boolean => {
            const ext = file.name.split(".").pop()?.toLowerCase();
            return !!ext && VIDEO_EXTENSIONS.includes(ext);
        };

        const rejectVideoFile = (file: File): void => {
            showError("Invalid file type: " + (file.name.split(".").pop() ?? ""));
        };

        const dropVideoFile = async (file: File): Promise<boolean> => {
            if (!acceptVideoFile(file)) {
                rejectVideoFile(file);
                return false;
            }
            return await handleUpload(file);
        };

        // Drag cue, shown on the preview overlay and the upload button at once.
        let _dragActive = false;
        let _dragBtnHTML = "";
        let _dragBtnBorder = "";
        let _dragBtnAria: string | null = null;
        let _dragTimer: ReturnType<typeof setTimeout> | null = null;

        const setDragActive = (active: boolean): void => {
            if (_dragTimer) {
                clearTimeout(_dragTimer);
                _dragTimer = null;
            }
            if (active) {
                // The canvas region gives us no drag-leave callback — ComfyUI's
                // canvas dragleave only clears its own dragOverNode — so the cue
                // self-expires unless a dragover keeps refreshing it.
                _dragTimer = setTimeout(() => setDragActive(false), 400);
            }
            if (active === _dragActive) return;
            // Don't fight an in-flight upload for the button, but always let
            // the overlay clear — otherwise a drop that starts an upload would
            // strand it on screen.
            if (active && uploadBtn.disabled) return;
            _dragActive = active;

            if (active) {
                _dragBtnHTML = uploadBtn.innerHTML;
                _dragBtnBorder = uploadBtn.style.border;
                _dragBtnAria = uploadBtn.getAttribute("aria-label");
                uploadBtn.innerHTML = `<span aria-hidden="true">📂</span> Drop to Upload`;
                uploadBtn.setAttribute("aria-label", "Drop to Upload");
                uploadBtn.style.border = "1px dashed #4a6a8a";
                uploadBtn.style.backgroundColor = "#333";
                dropOverlay.style.display = "flex";
            } else {
                if (!uploadBtn.disabled) {
                    uploadBtn.innerHTML = _dragBtnHTML;
                    uploadBtn.style.border = _dragBtnBorder;
                    if (_dragBtnAria) {
                        uploadBtn.setAttribute("aria-label", _dragBtnAria);
                    } else {
                        uploadBtn.removeAttribute("aria-label");
                    }
                    updateBtn();
                }
                dropOverlay.style.display = "none";
            }
        };

        const dropZoneOpts = {
            accept: acceptVideoFile,
            onDrop: dropVideoFile,
            onReject: rejectVideoFile,
            onDragStateChange: setDragActive,
            disabled: (): boolean => uploadBtn.disabled,
        };
        const detachPreviewDrop = attachFileDropZone(previewContainer, dropZoneOpts);
        const detachButtonDrop = attachFileDropZone(uploadBtn, dropZoneOpts);

        // Canvas-drawn region of the node — LiteGraph hit-tests the node under
        // the cursor and routes the document-level drop back here.
        this.onDragOver = (e: DragEvent): boolean => {
            if (!e?.dataTransfer?.types?.includes?.("Files")) return false;
            setDragActive(true);
            return true;
        };

        this.onDragDrop = async (e: DragEvent): Promise<boolean> => {
            setDragActive(false);
            if (!e?.dataTransfer?.types?.includes?.("Files")) return false;
            // Claim the drop but ignore it — returning true keeps ComfyUI from
            // spawning a node for a file we're refusing.
            if (uploadBtn.disabled) return true;
            const file = e.dataTransfer?.files?.[0];
            if (!file) return false;
            return await dropVideoFile(file);
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
