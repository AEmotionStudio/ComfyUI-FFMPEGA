// Entry point: imports all per-node modules and registers them with ComfyUI
/**
 * FFMPEGA Custom UI Widgets for ComfyUI
 *
 * This file is the entry point that registers all FFMPEGA node UI handlers.
 * Each node handler is defined in its own module under src/nodes/.
 */

import { app } from "comfyui/app";

// Per-node handlers
import { registerNodeStyling } from "@ffmpega/nodes/node_styling";
import { registerAgentNode } from "@ffmpega/nodes/agent_node";
import { registerFrameExtractNode } from "@ffmpega/nodes/frame_extract_node";
import { registerLoadVideoNode } from "@ffmpega/nodes/load_video_node";
import { registerLoadMaskVideoNode } from "@ffmpega/nodes/load_mask_video_node";
import { registerSaveVideoNode, applySaveVideoOutputs } from "@ffmpega/nodes/save_video_node";
import { registerSaveImageNode } from "@ffmpega/nodes/save_image_node";
import { registerLoadImageNode } from "@ffmpega/nodes/load_image_node";
import { registerLastFrameNodes } from "@ffmpega/nodes/last_frame_ui";
import { registerTextInputNode } from "@ffmpega/nodes/text_input_node";
import { registerPointSelectorHooks } from "@ffmpega/nodes/point_selector_hooks";
import { registerCropSelectorHooks } from "@ffmpega/nodes/crop_selector_hooks";

// Sidebar
import { initSidebar } from "@ffmpega/sidebar/sidebar";

// Register FFMPEGA extensions
app.registerExtension({
    name: "FFMPEGA.UI",

    async setup() {
        initSidebar();
    },

    /**
     * Fires when ComfyUI swaps the whole `app.nodeOutputs` map, which is what
     * happens on a workflow tab switch (`ChangeTracker.restore()`) and when a
     * run is opened from the queue history. Save Video rebuilds its player from
     * it — the same hook core's audio and 3D previews restore themselves in.
     */
    onNodeOutputsUpdated(nodeOutputs: Record<string, Record<string, unknown> | undefined>) {
        // rootGraph, not graph: the map covers the whole workflow, but `graph`
        // is only whatever the user currently has open.
        applySaveVideoOutputs(app.rootGraph ?? app.graph, nodeOutputs);
    },

    async beforeRegisterNodeDef(nodeType: import("@ffmpega/types/comfyui").ComfyNodeType, nodeData: import("@ffmpega/types/comfyui").ComfyNodeData, _app: unknown) {
        // Styling-only nodes (Preview, MediaBridge, BatchProcessor, VideoInfo)
        if (registerNodeStyling(nodeType, nodeData)) return;

        // Complex node handlers
        registerAgentNode(nodeType, nodeData);
        registerFrameExtractNode(nodeType, nodeData);
        registerLoadVideoNode(nodeType, nodeData);
        registerLoadMaskVideoNode(nodeType, nodeData);
        registerSaveVideoNode(nodeType, nodeData);
        registerSaveImageNode(nodeType, nodeData);
        registerLoadImageNode(nodeType, nodeData);
        registerLastFrameNodes(nodeType, nodeData);
        registerTextInputNode(nodeType, nodeData);

        // Point selector context menu hooks (LoadVideoPath, FrameExtract)
        registerPointSelectorHooks(nodeType, nodeData);

        // Crop selector context menu hooks (LoadVideoPath, FrameExtract)
        registerCropSelectorHooks(nodeType, nodeData);
    },
});

console.log("FFMPEGA UI extensions loaded");
