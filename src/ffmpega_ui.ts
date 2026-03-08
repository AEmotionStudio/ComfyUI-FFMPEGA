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
import { registerSaveVideoNode } from "@ffmpega/nodes/save_video_node";
import { registerLoadImageNode } from "@ffmpega/nodes/load_image_node";
import { registerTextInputNode } from "@ffmpega/nodes/text_input_node";
import { registerPointSelectorHooks } from "@ffmpega/nodes/point_selector_hooks";

// Register FFMPEGA extensions
app.registerExtension({
    name: "FFMPEGA.UI",

    async beforeRegisterNodeDef(nodeType: import("@ffmpega/types/comfyui").ComfyNodeType, nodeData: import("@ffmpega/types/comfyui").ComfyNodeData, _app: unknown) {
        // Styling-only nodes (Preview, VideoToPath, BatchProcessor, VideoInfo)
        if (registerNodeStyling(nodeType, nodeData)) return;

        // Complex node handlers
        registerAgentNode(nodeType, nodeData);
        registerFrameExtractNode(nodeType, nodeData);
        registerLoadVideoNode(nodeType, nodeData);
        registerSaveVideoNode(nodeType, nodeData);
        registerLoadImageNode(nodeType, nodeData);
        registerTextInputNode(nodeType, nodeData);

        // Point selector context menu hooks (LoadVideoPath, FrameExtract)
        registerPointSelectorHooks(nodeType, nodeData);
    },
});

console.log("FFMPEGA UI extensions loaded");
