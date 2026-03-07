/**
 * SelectionManager — per-mode frame selection state.
 *
 * Each view mode has its own independent Set<timestamp>.
 * Selections sync to a hidden widget for backend consumption.
 */
import { VIEW_MODES, type ViewMode } from '@ffmpega/types/loadlast';
import type { ComfyNode } from '@ffmpega/types/comfyui';

export class SelectionManager {
    private selections = new Map<ViewMode, Set<number>>();
    private node: ComfyNode | null = null;

    constructor() {
        // Initialize all modes with empty sets
        for (const mode of Object.values(VIEW_MODES)) {
            this.selections.set(mode, new Set());
        }
    }

    /** Bind to a ComfyUI node for widget sync */
    bind(node: ComfyNode): void {
        this.node = node;
    }

    /** Get the selection set for a mode */
    get(mode: ViewMode): Set<number> {
        return this.selections.get(mode) ?? new Set();
    }

    /** Toggle a timestamp in a mode's selection. Returns true if added. */
    toggle(mode: ViewMode, timestamp: number): boolean {
        const set = this.get(mode);
        const key = Math.round(timestamp * 1000) / 1000;
        if (set.has(key)) {
            set.delete(key);
            return false;
        }
        set.add(key);
        return true;
    }

    /** Clear all selections for a mode */
    clearMode(mode: ViewMode): void {
        this.get(mode).clear();
    }

    /** Clear ALL selections across all modes */
    clearAll(): void {
        for (const set of this.selections.values()) {
            set.clear();
        }
    }

    /** Get total selected count across all modes */
    totalCount(): number {
        let count = 0;
        for (const set of this.selections.values()) {
            count += set.size;
        }
        return count;
    }

    /** Get all unique timestamps across all modes, sorted */
    allTimestamps(): number[] {
        const all = new Set<number>();
        for (const set of this.selections.values()) {
            for (const t of set) all.add(t);
        }
        return Array.from(all).sort((a, b) => a - b);
    }

    /** Get all timestamps with their source mode(s) */
    allTimestampsWithSource(): Map<number, ViewMode[]> {
        const result = new Map<number, ViewMode[]>();
        for (const [mode, set] of this.selections.entries()) {
            if (mode === VIEW_MODES.SELECTED) continue;
            for (const t of set) {
                const existing = result.get(t) ?? [];
                existing.push(mode);
                result.set(t, existing);
            }
        }
        return result;
    }

    /** Sync selections to the hidden _selected_timestamps widget */
    syncToWidget(): void {
        if (!this.node) return;
        const sorted = this.allTimestamps();
        const json = JSON.stringify(sorted);

        const w = this.node.widgets?.find((w) => w.name === '_selected_timestamps');
        if (w) {
            w.value = json;
        } else {
            if (!this.node.properties) this.node.properties = {};
            this.node.properties['_selected_timestamps'] = json;
        }
    }

    /** Get entries iterator for rendering */
    entries(): IterableIterator<[ViewMode, Set<number>]> {
        return this.selections.entries();
    }
}
