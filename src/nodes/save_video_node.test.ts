/**
 * The state that lets a Save Video preview outlive its session.
 *
 * These three sit either side of the workflow file: one packs an execution
 * payload into it, one reads it back out of JSON that users can edit and
 * downgrade, and one turns it into a `/view` URL.
 */

import { describe, it, expect } from "vitest";
import {
    packPreviewState, readPreviewState, previewQuery, registerSaveVideoNode,
    applySaveVideoOutputs, nodeIdFromLocator,
} from "./save_video_node";
import type { ComfyNodeType, ComfyNodeData } from "@ffmpega/types/comfyui";

describe("packPreviewState", () => {
    it("keeps the file and the stats the info bar needs", () => {
        expect(packPreviewState({
            video: [{ filename: "vid_00007.mp4", subfolder: "FFMPEGA", type: "output" }],
            file_size: ["12.1 MB"],
            frame_count: [81],
            fps: [24],
        })).toEqual({
            filename: "vid_00007.mp4",
            subfolder: "FFMPEGA",
            type: "output",
            file_size: "12.1 MB",
            frame_count: 81,
            fps: 24,
        });
    });

    it("remembers preview-only runs too", () => {
        // save_output=false writes to the temp dir, which survives a tab
        // switch but not a restart.
        const state = packPreviewState({
            video: [{ filename: "ffmpega_preview_1234_0.mp4", subfolder: "", type: "temp" }],
            file_size: ["4.0 MB"],
            frame_count: [30],
            fps: [30],
        });
        expect(state?.type).toBe("temp");
    });

    it("keeps only the first video of a comparison run", () => {
        // The player has only ever shown video[0].
        const state = packPreviewState({
            video: [
                { filename: "a.mp4", subfolder: "", type: "output" },
                { filename: "b.mp4", subfolder: "", type: "output" },
            ],
            file_size: ["2 videos"],
        });
        expect(state?.filename).toBe("a.mp4");
    });

    it("defaults the stats an older payload does not carry", () => {
        expect(packPreviewState({
            video: [{ filename: "vid.mp4" }],
        })).toEqual({
            filename: "vid.mp4",
            subfolder: "",
            type: "output",
            file_size: undefined,
            frame_count: 0,
            fps: 0,
        });
    });

    it("returns null when the run produced no file", () => {
        expect(packPreviewState({ video: [], file_size: ["0 B"] })).toBeNull();
        expect(packPreviewState({})).toBeNull();
        expect(packPreviewState(undefined)).toBeNull();
    });

    it("returns null for an entry with no filename", () => {
        expect(packPreviewState({ video: [{ filename: "" }] })).toBeNull();
    });
});

describe("readPreviewState", () => {
    it("reads back what packPreviewState wrote", () => {
        const packed = packPreviewState({
            video: [{ filename: "vid.mp4", subfolder: "FFMPEGA", type: "output" }],
            file_size: ["12.1 MB"],
            frame_count: [81],
            fps: [24],
        })!;
        expect(readPreviewState(JSON.parse(JSON.stringify(packed)))).toEqual(packed);
    });

    it("treats a workflow with no saved preview as absent", () => {
        // Workflows written before this property existed.
        expect(readPreviewState(undefined)).toBeNull();
        expect(readPreviewState(null)).toBeNull();
    });

    it("rejects anything that is not a usable descriptor", () => {
        expect(readPreviewState("vid.mp4")).toBeNull();
        expect(readPreviewState(42)).toBeNull();
        expect(readPreviewState({})).toBeNull();
        expect(readPreviewState({ subfolder: "FFMPEGA", type: "output" })).toBeNull();
        expect(readPreviewState({ filename: 7 })).toBeNull();
    });

    it("fills in fields a hand-edited property left out or mistyped", () => {
        expect(readPreviewState({ filename: "vid.mp4" })).toEqual({
            filename: "vid.mp4",
            subfolder: "",
            type: "output",
            file_size: undefined,
            frame_count: undefined,
            fps: undefined,
        });
        expect(readPreviewState({
            filename: "vid.mp4", subfolder: null, type: "", frame_count: "81", fps: NaN,
        })).toEqual({
            filename: "vid.mp4",
            subfolder: "",
            type: "output",
            file_size: undefined,
            frame_count: undefined,
            fps: undefined,
        });
    });
});

describe("previewQuery", () => {
    it("addresses the file the way /view expects", () => {
        const q = new URLSearchParams(previewQuery(
            { filename: "vid_00007.mp4", subfolder: "FFMPEGA", type: "output" },
            1700000000000,
        ));
        expect(q.get("filename")).toBe("vid_00007.mp4");
        expect(q.get("subfolder")).toBe("FFMPEGA");
        expect(q.get("type")).toBe("output");
        expect(q.get("timestamp")).toBe("1700000000000");
    });

    it("busts the cache on every build", () => {
        // Same name, new content: `overwrite` lets a later run replace the
        // file in place, so a restore must not reuse the previous URL.
        const state = { filename: "vid.mp4", subfolder: "", type: "output" };
        expect(previewQuery(state, 1)).not.toBe(previewQuery(state, 2));
    });

    it("escapes names that would otherwise break the query", () => {
        const q = new URLSearchParams(previewQuery(
            { filename: "my video &1.mp4", subfolder: "a b", type: "output" },
            1,
        ));
        expect(q.get("filename")).toBe("my video &1.mp4");
        expect(q.get("subfolder")).toBe("a b");
    });
});

// ---------------------------------------------------------------------------

/**
 * The round trip itself, against the real `registerSaveVideoNode`.
 *
 * The point of the feature is that a save outlives the node instance that made
 * it, so these build one node, run it, serialize what LiteGraph would
 * serialize, and hand that to a *second* node — the same thing a workflow tab
 * switch, a reload, or a server restart does.
 */

/** Enough of a LiteGraph node for `onNodeCreated` to run against. */
function makeNode() {
    const widgets: Array<Record<string, unknown>> = [];
    let domElement: HTMLElement | undefined;
    const node = {
        size: [400, 300] as [number, number],
        properties: {} as Record<string, unknown>,
        widgets,
        inputs: [] as Array<{ name: string; type: string }>,
        graph: { setDirtyCanvas: () => { /* no-op */ } },
        computeSize: () => [400, 300] as [number, number],
        setSize: () => { /* no-op */ },
        setDirtyCanvas: () => { /* no-op */ },
        addInput(name: string, type: string) { this.inputs.push({ name, type }); },
        removeInput(i: number) { this.inputs.splice(i, 1); },
        addDOMWidget(name: string, type: string, el: HTMLElement, options?: Record<string, unknown>) {
            domElement = el;
            document.body.appendChild(el);
            const w = { name, type, element: el, options, value: undefined as unknown };
            widgets.push(w);
            return w;
        },
        get previewContainer(): HTMLElement { return domElement!; },
        get videoEl(): HTMLVideoElement { return domElement!.querySelector("video")!; },
        get infoEl(): HTMLElement { return domElement!.querySelector("div")!; },
    };
    return node;
}

type FakeNode = ReturnType<typeof makeNode>;

/** Register the handler once and run its `onNodeCreated` on a fresh node. */
function createNode(): FakeNode {
    const nodeType = { prototype: {} } as unknown as ComfyNodeType;
    registerSaveVideoNode(nodeType, { name: "FFMPEGASaveVideo" } as ComfyNodeData);
    const node = makeNode();
    (nodeType.prototype as unknown as { onNodeCreated: () => void })
        .onNodeCreated.call(node as unknown as never);
    return node;
}

/** What LiteGraph writes into the workflow: a JSON clone of `properties`. */
function serializeProperties(node: FakeNode): Record<string, unknown> {
    return JSON.parse(JSON.stringify(node.properties));
}

/** Let the restore's requestAnimationFrame land. */
const flush = (): Promise<void> => new Promise(r => setTimeout(r, 20));

const EXECUTED = {
    video: [{ filename: "vid_00007.mp4", subfolder: "FFMPEGA", type: "output" }],
    file_size: ["12.1 MB"],
    frame_count: [81],
    fps: [24],
};

describe("save video preview persistence", () => {
    it("shows nothing until the node has run", () => {
        const node = createNode();
        expect(node.previewContainer.style.display).toBe("none");
        expect(node.infoEl.textContent).toBe("Waiting for execution...");
    });

    it("plays the file and records it in the workflow after a run", () => {
        const node = createNode();
        (node as unknown as { onExecuted: (d: unknown) => void }).onExecuted.call(node, EXECUTED);

        expect(node.previewContainer.style.display).toBe("");
        expect(node.videoEl.src).toContain("filename=vid_00007.mp4");
        expect(node.videoEl.src).toContain("subfolder=FFMPEGA");
        expect(node.infoEl.textContent).toBe("Saved: vid_00007.mp4 (12.1 MB)");
        expect(node.properties._ffmpega_saved_video).toMatchObject({
            filename: "vid_00007.mp4", subfolder: "FFMPEGA", type: "output",
            file_size: "12.1 MB", frame_count: 81, fps: 24,
        });
    });

    it("brings the save back on a node rebuilt from the workflow", async () => {
        const first = createNode();
        (first as unknown as { onExecuted: (d: unknown) => void }).onExecuted.call(first, EXECUTED);
        const saved = serializeProperties(first);

        // A tab switch, reload, or restart: new node, same workflow JSON.
        const second = createNode();
        second.properties = saved;
        (second as unknown as { onConfigure: (i: unknown) => void })
            .onConfigure.call(second, { properties: saved });
        await flush();

        expect(second.previewContainer.style.display).toBe("");
        expect(second.videoEl.src).toContain("filename=vid_00007.mp4");
        expect(second.infoEl.textContent).toBe("Saved: vid_00007.mp4 (12.1 MB)");
        // The stats the info bar fills in once metadata arrives.
        expect((second as unknown as { _savedFrameCount: number })._savedFrameCount).toBe(81);
        expect((second as unknown as { _savedFps: number })._savedFps).toBe(24);
    });

    it("asks for the file again rather than replaying a cached URL", async () => {
        const first = createNode();
        (first as unknown as { onExecuted: (d: unknown) => void }).onExecuted.call(first, EXECUTED);
        const firstSrc = first.videoEl.src;
        const saved = serializeProperties(first);
        // The timestamp is minted per URL, so it must not be in what we stored.
        expect(saved._ffmpega_saved_video).not.toHaveProperty("timestamp");

        await new Promise(r => setTimeout(r, 5));
        const second = createNode();
        second.properties = saved;
        (second as unknown as { onConfigure: (i: unknown) => void })
            .onConfigure.call(second, { properties: saved });
        await flush();

        expect(second.videoEl.src).not.toBe(firstSrc);
    });

    it("stays empty for a workflow saved before this existed", async () => {
        const node = createNode();
        (node as unknown as { onConfigure: (i: unknown) => void }).onConfigure.call(node, {});
        await flush();

        expect(node.previewContainer.style.display).toBe("none");
        expect(node.infoEl.textContent).toBe("Waiting for execution...");
    });

    it("keeps the previous preview when a run produces no file", () => {
        const node = createNode();
        const exec = (node as unknown as { onExecuted: (d: unknown) => void }).onExecuted;
        exec.call(node, EXECUTED);
        const src = node.videoEl.src;

        exec.call(node, { video: [], file_size: ["0 B"], frame_count: [0], fps: [0] });

        expect(node.videoEl.src).toBe(src);
        expect(node.properties._ffmpega_saved_video).toMatchObject({ filename: "vid_00007.mp4" });
    });

    it("collapses silently when the remembered file is gone", async () => {
        // Temp previews after a restart, or an output deleted on disk: /view
        // 404s, the video errors, and the node shrinks back.
        const node = createNode();
        const saved = { _ffmpega_saved_video: { filename: "gone.mp4", subfolder: "", type: "temp" } };
        node.properties = saved;
        (node as unknown as { onConfigure: (i: unknown) => void })
            .onConfigure.call(node, { properties: saved });
        await flush();
        expect(node.previewContainer.style.display).toBe("");

        node.videoEl.dispatchEvent(new Event("error"));
        expect(node.previewContainer.style.display).toBe("none");
    });
});

// ---------------------------------------------------------------------------

/**
 * The tab-switch path: ComfyUI hands the whole `app.nodeOutputs` map back.
 *
 * This is the one the workflow property could not cover, since a tab switch
 * restores outputs from ComfyUI's own per-workflow snapshot rather than from
 * anything we serialize.
 */

describe("nodeIdFromLocator", () => {
    it("reads a root-graph node id", () => {
        expect(nodeIdFromLocator("42")).toBe("42");
    });

    it("reads the node id out of a subgraph locator", () => {
        expect(nodeIdFromLocator("b3f1c2d4-1111-2222-3333-444455556666:42")).toBe("42");
    });
});

describe("applySaveVideoOutputs", () => {
    it("restores the player from the outputs map", () => {
        const node = createNode();
        (node as unknown as { id: number }).id = 7;
        expect(node.previewContainer.style.display).toBe("none");

        applySaveVideoOutputs({ _nodes: [node as never] }, { "7": EXECUTED });

        expect(node.previewContainer.style.display).toBe("");
        expect(node.videoEl.src).toContain("filename=vid_00007.mp4");
        expect(node.infoEl.textContent).toBe("Saved: vid_00007.mp4 (12.1 MB)");
    });

    it("also writes the workflow property, so a later reload is covered", () => {
        // A run recovered from history has outputs but no saved property yet.
        const node = createNode();
        (node as unknown as { id: number }).id = 7;

        applySaveVideoOutputs({ _nodes: [node as never] }, { "7": EXECUTED });

        expect(node.properties._ffmpega_saved_video)
            .toMatchObject({ filename: "vid_00007.mp4", frame_count: 81, fps: 24 });
    });

    it("matches a node living inside a subgraph", () => {
        const node = createNode();
        (node as unknown as { id: number }).id = 12;

        applySaveVideoOutputs(
            { _nodes: [node as never] },
            { "b3f1c2d4-1111-2222-3333-444455556666:12": EXECUTED },
        );

        expect(node.videoEl.src).toContain("filename=vid_00007.mp4");
    });

    it("leaves nodes with no output of their own alone", () => {
        const node = createNode();
        (node as unknown as { id: number }).id = 7;

        applySaveVideoOutputs({ _nodes: [node as never] }, { "9": EXECUTED });

        expect(node.previewContainer.style.display).toBe("none");
    });

    it("ignores other node types and empty maps", () => {
        const foreign = { id: 7, properties: {} };
        expect(() => {
            applySaveVideoOutputs({ _nodes: [foreign as never] }, { "7": EXECUTED });
            applySaveVideoOutputs({ _nodes: [] }, { "7": EXECUTED });
            applySaveVideoOutputs(undefined, { "7": EXECUTED });
            applySaveVideoOutputs({ _nodes: [] }, undefined);
            applySaveVideoOutputs({ _nodes: [] }, {});
        }).not.toThrow();
    });

    it("does not clear a live preview when the map has nothing for it", () => {
        // resetAllOutputsAndPreviews() assigns {}, which fires the same hook.
        const node = createNode();
        (node as unknown as { id: number }).id = 7;
        (node as unknown as { onExecuted: (d: unknown) => void }).onExecuted.call(node, EXECUTED);
        const src = node.videoEl.src;

        applySaveVideoOutputs({ _nodes: [node as never] }, {});

        expect(node.videoEl.src).toBe(src);
        expect(node.previewContainer.style.display).toBe("");
    });
});

describe("applySaveVideoOutputs — nested graphs", () => {
    it("reaches a node inside a subgraph", () => {
        const inner = createNode();
        (inner as unknown as { id: number }).id = 12;
        const subgraphHost = { id: 3, properties: {}, subgraph: { _nodes: [inner] } };

        applySaveVideoOutputs(
            { _nodes: [subgraphHost as never] },
            { "b3f1c2d4-1111-2222-3333-444455556666:12": EXECUTED },
        );

        expect(inner.videoEl.src).toContain("filename=vid_00007.mp4");
    });

    it("does not loop on a subgraph that references itself", () => {
        // Subgraph definitions are shared between instances, so the same graph
        // object can be reachable more than once.
        const node = createNode();
        (node as unknown as { id: number }).id = 7;
        const graph: { _nodes: unknown[] } = { _nodes: [node] };
        (node as unknown as { subgraph: unknown }).subgraph = graph;

        expect(() => applySaveVideoOutputs(graph as never, { "7": EXECUTED })).not.toThrow();
        expect(node.videoEl.src).toContain("filename=vid_00007.mp4");
    });
});
