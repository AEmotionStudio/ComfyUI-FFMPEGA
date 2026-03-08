/**
 * FFMPEGA Node Styling — Typed module for styling-only node handlers.
 *
 * These nodes only need custom colors in onNodeCreated.
 * Extracted from the monolithic ffmpega_ui.ts.
 */

/** Node name → [color, bgcolor] mapping for styling-only nodes */
const NODE_COLORS: Record<string, [string, string]> = {
    "FFMPEGAPreview": ["#3a5a3a", "#2a4a2a"],
    "FFMPEGAVideoToPath": ["#3a5a4a", "#2a4a3a"],
    "FFMPEGABatchProcessor": ["#5a3a3a", "#4a2a2a"],
    "FFMPEGAVideoInfo": ["#4a4a3a", "#3a3a2a"],
    "LoadLastImage": ["#5a4a3a", "#4a3a2a"],
};

/**
 * Register styling for a node.
 * Called from beforeRegisterNodeDef for each styling-only node.
 */
export function registerNodeStyling(
    nodeType: any,
    nodeData: { name: string },
): boolean {
    const colors = NODE_COLORS[nodeData.name];
    if (!colors) return false;

    const [color, bgcolor] = colors;
    const onNodeCreated = nodeType.prototype.onNodeCreated;

    nodeType.prototype.onNodeCreated = function (this: any) {
        const result = onNodeCreated?.apply(this, arguments);
        this.color = color;
        this.bgcolor = bgcolor;
        return result;
    };

    return true;
}

/** Check if a node name is a styling-only node */
export function isStylingOnlyNode(name: string): boolean {
    return name in NODE_COLORS;
}
