/**
 * FFMPEGASaveVideo node UI handler.
 *
 * Features:
 * - Video preview after execution (DOM widget)
 * - Download overlay button
 * - Context menu with preview controls
 * - Info bar: resolution, frame count (live playhead while playing), duration,
 *   file size
 */

import { api } from "comfyui/api";
import {
    addDownloadOverlay, addVideoPreviewMenu, attachPlayheadTracker,
    wireDynamicInputs, toggleWidget, fitHeight,
} from "@ffmpega/shared/ui_helpers";
import type { PlayheadCause } from "@ffmpega/shared/ui_helpers";
import type { ComfyNodeType, ComfyNodeData, ComfyNode, ComfyWidget } from "@ffmpega/types/comfyui";

/** Must match core.video.encode_opts.SOURCE_FORMAT. */
const SOURCE_FORMAT = "source (no re-encode)";

/**
 * Every widget that lives behind the `show_advanced` toggle, in node order.
 * The toggle itself is not listed — it is always visible.
 */
const ADVANCED_WIDGETS = [
    "output_format", "color_policy", "crf", "encode_preset", "bit_depth",
    "audio_codec", "audio_bitrate", "faststart", "loop_count", "pingpong",
    "trim_to_audio", "embed_workflow", "frame_output",
];

/**
 * Widgets to hide for a given output format, once advanced options are open.
 *
 * Each format only understands some of the encoding controls: VP9 and AV1
 * take a deadline/speed rather than an x264 preset, ProRes and FFV1 have
 * fixed quality, and GIF/WebP carry no audio at all. Showing the rest would
 * imply they do something.
 *
 * `color_policy` never appears here: it still governs how a connected IMAGE
 * batch is encoded, even in pass-through mode.
 */
const HIDDEN_BY_FORMAT: Record<string, string[]> = {
    [SOURCE_FORMAT]: [
        "crf", "encode_preset", "bit_depth",
        "audio_codec", "audio_bitrate", "faststart", "pingpong",
    ],
    "h264-mp4": [],
    "h265-mp4": [],
    "vp9-webm": ["encode_preset", "faststart"],
    "av1-webm": ["encode_preset", "faststart"],
    "prores-mov": ["crf", "encode_preset", "bit_depth", "faststart"],
    "ffv1-mkv": ["crf", "encode_preset", "faststart"],
    "gif": [
        "crf", "encode_preset", "bit_depth",
        "audio_codec", "audio_bitrate", "faststart", "trim_to_audio",
    ],
    "webp": [
        "encode_preset", "bit_depth",
        "audio_codec", "audio_bitrate", "faststart", "trim_to_audio",
    ],
};

/**
 * Apply both levels of visibility: the advanced disclosure, then the
 * per-format pruning inside it.
 *
 * Hiding only affects display — the widgets keep their values, so collapsing
 * the section never silently changes what gets encoded.
 */
function applyWidgetVisibility(node: ComfyNode): void {
    const findWidget = (name: string) =>
        node.widgets?.find((w) => w.name === name);

    const advancedOpen = Boolean(findWidget("show_advanced")?.value);
    const format = String(findWidget("output_format")?.value ?? SOURCE_FORMAT);
    const hiddenForFormat = HIDDEN_BY_FORMAT[format] ?? [];

    for (const name of ADVANCED_WIDGETS) {
        const show = advancedOpen && !hiddenForFormat.includes(name);
        toggleWidget(findWidget(name), show);
    }
    fitHeight(node);
}

/** Extended node type for SaveVideo with internal state */
interface SaveVideoNode extends ComfyNode {
    _savedFileSize?: string;
    _savedFrameCount?: number;
    _savedFps?: number;
    addDOMWidget(name: string, type: string, el: HTMLElement, opts?: Record<string, unknown>): ComfyWidget;
    onExecuted?: (data: SaveVideoExecutionData) => void;
    onRemoved?: () => void;
}

/** Execution data returned from Python backend */
interface SaveVideoExecutionData {
    video?: Array<{ filename: string; subfolder?: string; type?: string }>;
    file_size?: string[];
    /** Frames in the saved file, probed server-side. 0 when unknown. */
    frame_count?: number[];
    /** Frame rate of the saved file — the source's own when passing through. */
    fps?: number[];
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
            paintInfo();
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

        /**
         * Build the info bar: resolution | frames | duration | size.
         *
         * Resolution and duration come off the video element, but a `<video>`
         * exposes no frame count and no frame rate, so those are probed
         * server-side and arrive with the execution payload. Anything still
         * unknown — an older payload, or a machine without ffprobe — is left
         * out rather than guessed.
         *
         * Passing `currentFrame` turns the frame segment into a playhead;
         * it is substituted in place so the bar does not reflow on play.
         */
        function buildInfoText(currentFrame?: number): string {
            const parts: string[] = [];
            const w = videoEl.videoWidth;
            const h = videoEl.videoHeight;
            if (w && h) parts.push(`${w}×${h}`);

            const total = node._savedFrameCount ?? 0;
            if (total > 0) {
                const fps = node._savedFps ? ` @ ${node._savedFps}fps` : "";
                parts.push(
                    currentFrame === undefined
                        ? `${total}f${fps}`
                        : `▶ ${currentFrame}/${total}f${fps}`,
                );
            }

            const d = videoEl.duration;
            if (d && isFinite(d)) {
                const m = Math.floor(d / 60);
                const s = (d % 60).toFixed(1);
                parts.push(m > 0 ? `${m}m ${s}s` : `${s}s`);
            }
            if (node._savedFileSize) {
                parts.push(node._savedFileSize);
            }
            return parts.join(" | ");
        }

        /** Repaint the bar, keeping the last text if there is nothing to show. */
        function paintInfo(currentFrame?: number): void {
            const text = buildInfoText(currentFrame);
            if (text) infoEl.textContent = text;
        }

        /** 1-based frame under the playhead, or undefined if fps is unknown. */
        function currentFrame(): number | undefined {
            const fps = node._savedFps ?? 0;
            const total = node._savedFrameCount ?? 0;
            if (fps <= 0 || total <= 0) return undefined;
            return Math.min(Math.floor(videoEl.currentTime * fps) + 1, total);
        }

        // --- Live frame counter ---
        // The playhead shows while the video is moving — playing, or parked
        // somewhere the user scrubbed to. A plain pause returns the bar to the
        // static count, since that is the number worth reading at rest.
        const detachPlayhead = attachPlayheadTracker(
            videoEl,
            (_time: number, playing: boolean, cause: PlayheadCause) => {
                const scrubbed = cause === "seek" && !playing;
                paintInfo(playing || scrubbed ? currentFrame() : undefined);
            },
        );

        const origOnRemovedSave = this.onRemoved;
        this.onRemoved = function (): void {
            detachPlayhead();
            origOnRemovedSave?.apply(this, arguments as unknown as []);
        };

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
                node._savedFrameCount = data?.frame_count?.[0] ?? 0;
                node._savedFps = data?.fps?.[0] ?? 0;

                infoEl.textContent = `Saved: ${v.filename}`;
                if (node._savedFileSize) {
                    infoEl.textContent += ` (${node._savedFileSize})`;
                }
            }
        };

        const getVideoUrlSave = (): string | null => videoEl.src || null;
        addVideoPreviewMenu(node, videoEl, previewContainer, previewWidget, getVideoUrlSave, infoEl);

        // --- Dynamic comparison inputs (video_path_a/b/..., images_a/b/...) ---
        wireDynamicInputs(
            node,
            [
                { prefix: "video_path_", type: "STRING", excludes: [] },
                { prefix: "images_", type: "IMAGE", excludes: [] },
            ],
            [
                { name: "video_path", type: "STRING" },
                { name: "images", type: "IMAGE" },
            ],
        );

        // --- Advanced options disclosure + per-format widget pruning ---
        for (const name of ["show_advanced", "output_format"]) {
            const widget = node.widgets?.find((w) => w.name === name);
            if (!widget) continue;
            const origCallback = widget.callback;
            widget.callback = function (this: ComfyWidget, ...args: unknown[]) {
                const r = origCallback?.apply(this, args as never);
                applyWidgetVisibility(node);
                return r;
            };
        }
        // Run once for the initial state, after ComfyUI has restored any
        // serialized widget values.
        requestAnimationFrame(() => applyWidgetVisibility(node));

        return result;
    };
}
