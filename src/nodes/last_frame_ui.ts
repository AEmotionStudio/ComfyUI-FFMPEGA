/**
 * FFMPEGASaveLastFrame / FFMPEGALoadLastFrame node UI handlers.
 *
 * Both nodes work on the same named slot, so both show the same thing: a
 * thumbnail strip of whatever that slot currently holds. The strip is
 * populated from /ffmpega/last_frame/slot as soon as the node is placed —
 * without it you would have to queue a prompt just to find out which frame
 * you are about to continue a scene from.
 *
 * Also collapses LoadLastFrame's resize sub-widgets behind `enable_resize`,
 * matching how LoadLastImage treats the same shared widget group.
 */

import { api } from "comfyui/api";
import { toggleWidget, fitHeight } from "@ffmpega/shared/ui_helpers";
import type { ComfyNodeType, ComfyNodeData, ComfyNode, ComfyWidget } from "@ffmpega/types/comfyui";

const SAVE_NODE = "FFMPEGASaveLastFrame";
const LOAD_NODE = "FFMPEGALoadLastFrame";

/** How often to re-check the slot, in ms. */
const POLL_INTERVAL = 3000;

/**
 * Resize sub-widgets gated behind `enable_resize`, in node order.
 * Mirrors the list in src/loadlast/image_preview.ts — both come from
 * core.image_resize.resize_input_types().
 */
const RESIZE_WIDGETS = [
    "resize_width", "resize_height", "upscale_method", "keep_proportion",
    "pad_color", "crop_position", "divisible_by", "resize_device",
];

interface SlotFrame {
    filename: string;
    subfolder?: string;
    type?: string;
    mtime?: number;
}

interface SlotResponse {
    found?: boolean;
    slot?: string;
    frames?: SlotFrame[];
    signature?: string;
}

interface LastFrameNode extends ComfyNode {
    addDOMWidget(name: string, type: string, el: HTMLElement, opts?: Record<string, unknown>): ComfyWidget;
    onExecuted?: (data: unknown) => void;
    onRemoved?: () => void;
}

/** Build a /view URL for one slot frame, cache-busted by mtime. */
function frameUrl(frame: SlotFrame): string {
    const params = new URLSearchParams({
        filename: frame.filename,
        subfolder: frame.subfolder || "",
        type: frame.type || "output",
        t: String(frame.mtime ?? Date.now()),
    });
    return api.apiURL("/view?" + params.toString());
}

/** Show/hide the resize sub-widgets based on the enable_resize toggle. */
function applyResizeVisibility(node: ComfyNode): void {
    const enabled = Boolean(
        node.widgets?.find((w) => w.name === "enable_resize")?.value,
    );
    for (const name of RESIZE_WIDGETS) {
        toggleWidget(node.widgets?.find((w) => w.name === name), enabled);
    }
    fitHeight(node);
}

/**
 * Attach the slot preview strip and wire it to the slot_name widget.
 * Shared by both nodes — they differ only in which one writes the slot.
 */
function attachSlotPreview(node: LastFrameNode, emptyHint: string): void {
    const container = document.createElement("div");
    container.style.cssText =
        "width:100%;background:#1a1a1a;border-radius:6px;overflow:hidden;";

    const strip = document.createElement("div");
    strip.style.cssText =
        "display:flex;gap:4px;padding:4px;overflow-x:auto;align-items:flex-start;";

    const info = document.createElement("div");
    info.style.cssText =
        "padding:4px 8px;font-size:11px;color:#aaa;font-family:monospace;" +
        "background:#111;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;";
    info.setAttribute("role", "status");
    info.setAttribute("aria-live", "polite");
    info.textContent = emptyHint;

    container.appendChild(strip);
    container.appendChild(info);

    // Keep canvas gestures off the strip so scrolling it doesn't pan the graph.
    for (const evt of ["contextmenu", "pointerdown", "mousewheel", "pointermove", "pointerup"]) {
        container.addEventListener(evt, (e: Event) => e.stopPropagation(), true);
    }

    const widget = node.addDOMWidget(
        "slotpreview", "preview", container, { serialize: false, hideOnZoom: false },
    );
    // Aspect ratio of the first frame; drives how tall the strip renders.
    let aspectRatio: number | null = null;
    widget.computeSize = function (width: number): [number, number] {
        if (aspectRatio === null) return [width, 44];
        const thumb = Math.min((node.size[0] - 24) / aspectRatio, 220);
        return [width, Math.max(thumb, 40) + 38];
    };

    let signature = "";

    const render = (frames: SlotFrame[], slot: string): void => {
        strip.replaceChildren();
        if (!frames.length) {
            aspectRatio = null;
            info.textContent = emptyHint;
            fitHeight(node);
            return;
        }

        for (const frame of frames) {
            const img = document.createElement("img");
            img.src = frameUrl(frame);
            img.alt = frame.filename;
            img.title = frame.filename;
            img.style.cssText =
                "height:100%;max-height:220px;flex:0 0 auto;border-radius:3px;" +
                "object-fit:contain;background:#000;";
            img.addEventListener("load", () => {
                if (aspectRatio === null && img.naturalHeight) {
                    aspectRatio = img.naturalWidth / img.naturalHeight;
                    fitHeight(node);
                }
            });
            strip.appendChild(img);
        }

        const last = frames[frames.length - 1];
        info.textContent = frames.length === 1
            ? `${slot}: ${last.filename}`
            : `${slot}: ${frames.length} frames — newest ${last.filename}`;
        fitHeight(node);
    };

    const refresh = async (force = false): Promise<void> => {
        const slot = String(
            node.widgets?.find((w) => w.name === "slot_name")?.value ?? "default",
        );
        try {
            const resp = await fetch(
                api.apiURL(`/ffmpega/last_frame/slot?slot=${encodeURIComponent(slot)}`),
            );
            if (!resp.ok) return;
            const data = (await resp.json()) as SlotResponse;
            const sig = `${data.slot ?? slot}#${data.signature ?? ""}`;
            if (!force && sig === signature) return;
            signature = sig;
            // A fresh save reuses the same filenames, so bust the img cache.
            aspectRatio = null;
            render(data.frames ?? [], data.slot ?? slot);
        } catch {
            // Server not up yet, or the route is unavailable — leave the
            // last good strip in place rather than blanking it.
        }
    };

    void refresh(true);
    const timer = setInterval(() => void refresh(), POLL_INTERVAL);

    const origOnRemoved = node.onRemoved;
    node.onRemoved = function (this: LastFrameNode) {
        clearInterval(timer);
        return origOnRemoved?.apply(this, arguments as unknown as []);
    };

    // Refresh immediately on a slot rename instead of waiting for the poll.
    const slotWidget = node.widgets?.find((w) => w.name === "slot_name");
    if (slotWidget) {
        const origCallback = slotWidget.callback;
        slotWidget.callback = function (this: ComfyWidget, ...args: unknown[]) {
            const r = origCallback?.apply(this, args as never);
            void refresh(true);
            return r;
        };
    }

    const origOnExecuted = node.onExecuted;
    node.onExecuted = function (this: LastFrameNode, data: unknown) {
        const r = origOnExecuted?.apply(this, arguments as unknown as [unknown]);
        void refresh(true);
        return r;
    };
}

/** Register FFMPEGASaveLastFrame / FFMPEGALoadLastFrame node UI. */
export function registerLastFrameNodes(
    nodeType: ComfyNodeType,
    nodeData: ComfyNodeData,
): void {
    const isSave = nodeData.name === SAVE_NODE;
    const isLoad = nodeData.name === LOAD_NODE;
    if (!isSave && !isLoad) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;

    nodeType.prototype.onNodeCreated = function (this: LastFrameNode) {
        const result = onNodeCreated?.apply(this, arguments as unknown as []);

        if (isSave) {
            this.color = "#5a3a4a";
            this.bgcolor = "#4a2a3a";
        } else {
            this.color = "#5a4a3a";
            this.bgcolor = "#4a3a2a";
        }

        attachSlotPreview(
            this,
            isSave
                ? "Slot is empty — run to save a frame"
                : "Slot is empty — connect fallback_image to start a chain",
        );

        if (isLoad) {
            const node = this;
            const enableResize = node.widgets?.find((w) => w.name === "enable_resize");
            if (enableResize) {
                const origCallback = enableResize.callback;
                enableResize.callback = function (this: ComfyWidget, ...args: unknown[]) {
                    const r = origCallback?.apply(this, args as never);
                    applyResizeVisibility(node);
                    return r;
                };
            }
            // Deferred: widget values are restored from the workflow after
            // onNodeCreated, so reading enable_resize now would always see
            // the default and wrongly collapse a saved-open section.
            setTimeout(() => applyResizeVisibility(node), 0);
        }

        return result;
    };
}
