/**
 * SnapEngine — shared snapping utility for NLE timelines.
 *
 * Given a candidate time value and a set of snap targets (segment edges),
 * returns the snapped value if within the snap threshold, or the
 * original value if not.
 */

/** Snap threshold in seconds (converted from pixels at runtime) */
const DEFAULT_SNAP_THRESHOLD_PX = 8;

export interface SnapResult {
    time: number;
    snapped: boolean;
    snapTarget?: number;
}

/**
 * Snap a time value to the nearest edge of any segment.
 *
 * @param time - The candidate time value
 * @param edges - Array of time values that are snap targets (segment start/end times)
 * @param thresholdPx - Snap threshold in pixels
 * @param trackW - Track width in pixels
 * @param duration - Total duration (for px→time conversion)
 * @param excludeEdge - Optional edge time to exclude (the edge being dragged)
 * @returns SnapResult with snapped time, whether a snap occurred, and the target
 */
export function snapToEdges(
    time: number,
    edges: number[],
    thresholdPx: number = DEFAULT_SNAP_THRESHOLD_PX,
    trackW: number = 1,
    duration: number = 1,
): SnapResult {
    const thresholdTime = (thresholdPx / trackW) * duration;

    let closest: number | null = null;
    let closestDist = Infinity;

    for (const edge of edges) {
        const dist = Math.abs(time - edge);
        if (dist < thresholdTime && dist < closestDist) {
            closest = edge;
            closestDist = dist;
        }
    }

    if (closest !== null) {
        return { time: closest, snapped: true, snapTarget: closest };
    }

    return { time, snapped: false };
}

/**
 * Collect all segment edges as snap targets.
 *
 * @param segments - Array of segments with start/end
 * @param excludeId - Segment ID to exclude (the segment being dragged)
 * @param excludeSide - Which side to exclude ('start' | 'end')
 * @returns Array of time values
 */
export function collectEdges(
    segments: { id: string; start: number; end: number }[],
    excludeId?: string,
    excludeSide?: 'start' | 'end',
): number[] {
    const edges: number[] = [];
    for (const seg of segments) {
        if (seg.id === excludeId) {
            // Include only the non-excluded side
            if (excludeSide !== 'start') edges.push(seg.start);
            if (excludeSide !== 'end') edges.push(seg.end);
        } else {
            edges.push(seg.start, seg.end);
        }
    }
    // Also snap to 0 and playhead could be added later
    edges.push(0);
    return edges;
}
