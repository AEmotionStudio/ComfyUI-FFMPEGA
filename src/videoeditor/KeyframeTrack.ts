/**
 * KeyframeTrack — generic data model for keyframe animation.
 *
 * Stores a sorted list of keyframes, each with a time, value, and easing.
 * Supports interpolation via `valueAt(t)` for both linear and eased curves.
 *
 * Used by SpeedControl (speed ramps) and AudioMixer (volume automation).
 */

export type EasingType = 'linear' | 'ease-in' | 'ease-out' | 'ease-in-out' | 'step';

export interface Keyframe {
    time: number;           // seconds on output timeline
    value: number;
    easing: EasingType;
}

export interface KeyframeTrackJSON {
    keyframes: Keyframe[];
    property: string;
    min: number;
    max: number;
    defaultValue: number;
}

export class KeyframeTrack {
    keyframes: Keyframe[] = [];
    readonly property: string;
    readonly min: number;
    readonly max: number;
    readonly defaultValue: number;

    constructor(property: string, min: number, max: number, defaultValue: number) {
        this.property = property;
        this.min = min;
        this.max = max;
        this.defaultValue = defaultValue;
    }

    /** Add or update a keyframe at the given time. */
    addKeyframe(time: number, value: number, easing: EasingType = 'linear'): void {
        value = Math.max(this.min, Math.min(this.max, value));

        // Replace existing keyframe at same time (within tolerance)
        const existing = this.keyframes.findIndex(k => Math.abs(k.time - time) < 0.01);
        if (existing >= 0) {
            this.keyframes[existing] = { time, value, easing };
        } else {
            this.keyframes.push({ time, value, easing });
        }
        this._sort();
    }

    /** Remove keyframe by index. */
    removeKeyframe(index: number): void {
        if (index >= 0 && index < this.keyframes.length) {
            this.keyframes.splice(index, 1);
        }
    }

    /** Remove keyframe nearest to time (within tolerance). */
    removeAt(time: number, tolerance: number = 0.1): boolean {
        const idx = this.keyframes.findIndex(k => Math.abs(k.time - time) <= tolerance);
        if (idx >= 0) {
            this.keyframes.splice(idx, 1);
            return true;
        }
        return false;
    }

    /** Find the keyframe index nearest to `time`. -1 if none within tolerance. */
    findNearest(time: number, tolerance: number = 0.2): number {
        let best = -1;
        let bestDist = Infinity;
        for (let i = 0; i < this.keyframes.length; i++) {
            const d = Math.abs(this.keyframes[i].time - time);
            if (d < bestDist && d <= tolerance) {
                bestDist = d;
                best = i;
            }
        }
        return best;
    }

    /** Get the interpolated value at time `t`. */
    valueAt(t: number): number {
        if (this.keyframes.length === 0) return this.defaultValue;
        if (this.keyframes.length === 1) return this.keyframes[0].value;

        // Before first keyframe — clamp
        if (t <= this.keyframes[0].time) return this.keyframes[0].value;

        // After last keyframe — clamp
        const last = this.keyframes[this.keyframes.length - 1];
        if (t >= last.time) return last.value;

        // Find surrounding pair
        for (let i = 0; i < this.keyframes.length - 1; i++) {
            const a = this.keyframes[i];
            const b = this.keyframes[i + 1];
            if (t >= a.time && t <= b.time) {
                const duration = b.time - a.time;
                if (duration <= 0) return a.value;
                const progress = (t - a.time) / duration;
                return _interpolate(a.value, b.value, progress, a.easing);
            }
        }

        return this.defaultValue;
    }

    /** Returns true if the track has any non-default keyframes. */
    hasKeyframes(): boolean {
        return this.keyframes.length > 0;
    }

    /** Serialize to JSON. */
    toJSON(): KeyframeTrackJSON {
        return {
            keyframes: this.keyframes.map(k => ({ ...k })),
            property: this.property,
            min: this.min,
            max: this.max,
            defaultValue: this.defaultValue,
        };
    }

    /** Load from JSON. */
    fromJSON(data: Partial<KeyframeTrackJSON>): void {
        this.keyframes = [];
        if (data.keyframes && Array.isArray(data.keyframes)) {
            for (const k of data.keyframes) {
                if (typeof k.time === 'number' && typeof k.value === 'number') {
                    this.addKeyframe(k.time, k.value, k.easing || 'linear');
                }
            }
        }
    }

    /** Clear all keyframes. */
    clear(): void {
        this.keyframes = [];
    }

    private _sort(): void {
        this.keyframes.sort((a, b) => a.time - b.time);
    }
}

// ── Easing functions ──────────────────────────────────────────────

function _interpolate(a: number, b: number, t: number, easing: EasingType): number {
    switch (easing) {
        case 'step':
            return a;
        case 'ease-in':
            t = t * t;
            break;
        case 'ease-out':
            t = 1 - (1 - t) * (1 - t);
            break;
        case 'ease-in-out':
            t = t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
            break;
        case 'linear':
        default:
            break;
    }
    return a + (b - a) * t;
}
