/**
 * EditManager — manages clip segment state for video editing.
 *
 * Tracks an ordered list of EditSegments (time ranges) and provides
 * operations: add, remove, split, update, reorder.
 * Syncs state to a hidden ComfyUI widget for backend consumption.
 */
import type { EditSegment } from '@ffmpega/types/loadlast';
import type { ComfyNode } from '@ffmpega/types/comfyui';

let _nextId = 0;
function genId(): string {
    return `seg_${++_nextId}_${Date.now()}`;
}

export class EditManager {
    segments: EditSegment[] = [];
    videoDuration: number = 0;
    private node: ComfyNode | null = null;

    /** Bind to a ComfyUI node for widget sync */
    bind(node: ComfyNode): void {
        this.node = node;
    }

    /** Initialize with a single segment spanning the full video */
    init(duration: number): void {
        this.videoDuration = duration;
        this.segments = [{ id: genId(), start: 0, end: duration }];
    }

    /** Add a new segment. Returns the new segment. */
    addSegment(start: number, end: number): EditSegment {
        start = Math.max(0, start);
        end = Math.min(this.videoDuration, end);
        if (end <= start) {
            throw new Error(`Invalid segment: end (${end}) <= start (${start})`);
        }
        const seg: EditSegment = { id: genId(), start, end };
        // Insert in sorted position
        const idx = this.segments.findIndex(s => s.start > start);
        if (idx === -1) {
            this.segments.push(seg);
        } else {
            this.segments.splice(idx, 0, seg);
        }
        return seg;
    }

    /** Remove a segment by ID */
    removeSegment(id: string): boolean {
        const idx = this.segments.findIndex(s => s.id === id);
        if (idx === -1) return false;
        this.segments.splice(idx, 1);
        return true;
    }

    /** Split the segment containing the given timestamp into two */
    splitAt(timestamp: number): boolean {
        const idx = this.segments.findIndex(
            s => timestamp > s.start && timestamp < s.end
        );
        if (idx === -1) return false;

        const seg = this.segments[idx];
        const left: EditSegment = { id: seg.id, start: seg.start, end: timestamp };
        const right: EditSegment = { id: genId(), start: timestamp, end: seg.end };

        this.segments.splice(idx, 1, left, right);
        return true;
    }

    /** Update a segment's start/end (e.g., from a trim handle drag) */
    updateSegment(id: string, start: number, end: number): boolean {
        const seg = this.segments.find(s => s.id === id);
        if (!seg) return false;

        start = Math.max(0, start);
        end = Math.min(this.videoDuration, end);
        if (end <= start + 0.05) return false; // minimum 50ms segment

        seg.start = start;
        seg.end = end;
        return true;
    }

    /** Move a segment from one position to another */
    reorderSegments(fromIdx: number, toIdx: number): boolean {
        if (fromIdx < 0 || fromIdx >= this.segments.length) return false;
        if (toIdx < 0 || toIdx >= this.segments.length) return false;
        if (fromIdx === toIdx) return false;

        const [seg] = this.segments.splice(fromIdx, 1);
        this.segments.splice(toIdx, 0, seg);
        return true;
    }

    /** Reset to a single full-length segment */
    reset(): void {
        this.segments = [{ id: genId(), start: 0, end: this.videoDuration }];
    }

    /** Total output duration of all segments */
    getOutputDuration(): number {
        return this.segments.reduce((sum, s) => sum + (s.end - s.start), 0);
    }

    /** Serialize segments to JSON array of [start, end] pairs */
    toJSON(): number[][] {
        return this.segments.map(s => [s.start, s.end]);
    }

    /** Check if segments differ from a full unedited video */
    hasEdits(): boolean {
        if (this.segments.length !== 1) return true;
        const s = this.segments[0];
        return Math.abs(s.start) > 0.01 || Math.abs(s.end - this.videoDuration) > 0.01;
    }

    /**
     * Map output timeline position → source video timestamp.
     * Output time 0 = start of first segment, output flows continuously
     * through all segments without gaps.
     */
    outputTimeToSource(outputTime: number): number {
        let accumulated = 0;
        for (const seg of this.segments) {
            const segDur = seg.end - seg.start;
            if (outputTime <= accumulated + segDur) {
                return seg.start + (outputTime - accumulated);
            }
            accumulated += segDur;
        }
        // Past the end — return end of last segment
        const last = this.segments[this.segments.length - 1];
        return last ? last.end : 0;
    }

    /**
     * Map source video timestamp → output timeline position.
     * Returns -1 if the source time is in a deleted gap.
     */
    sourceTimeToOutput(sourceTime: number): number {
        let accumulated = 0;
        for (const seg of this.segments) {
            if (sourceTime >= seg.start && sourceTime <= seg.end) {
                return accumulated + (sourceTime - seg.start);
            }
            accumulated += seg.end - seg.start;
        }
        return -1; // In a gap
    }

    /** Check if a source timestamp falls in a deleted gap */
    isInGap(sourceTime: number): boolean {
        return !this.segments.some(
            s => sourceTime >= s.start && sourceTime <= s.end,
        );
    }

    /** Sync segments to the hidden widgets on the node */
    syncToWidget(): void {
        if (!this.node) return;
        const json = JSON.stringify(this.toJSON());
        const action = this.hasEdits() ? 'passthrough' : 'none';

        const segWidget = this.node.widgets?.find((w) => w.name === '_edit_segments');
        if (segWidget) {
            segWidget.value = json;
        } else {
            if (!this.node.properties) this.node.properties = {};
            this.node.properties['_edit_segments'] = json;
        }

        const actWidget = this.node.widgets?.find((w) => w.name === '_edit_action');
        if (actWidget) {
            actWidget.value = action;
        } else {
            if (!this.node.properties) this.node.properties = {};
            this.node.properties['_edit_action'] = action;
        }
    }
}
