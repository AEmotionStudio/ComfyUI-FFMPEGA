/**
 * TransitionPreview — CSS-based live transition effects on the video element.
 *
 * Applied during playback when the playhead approaches a segment boundary
 * that has a transition. Uses:
 *   - opacity for fade/dissolve
 *   - clip-path for wipe effects  
 *   - clip-path + transform for slide effects
 *
 * The preview renders the "outgoing" half of the transition (fade-out,
 * wipe-out, slide-out) since we only have one video element — we can't
 * composite two frames. This still gives a strong sense of the transition.
 */

import { TransitionDef, TransitionType } from './TransitionEditor';

export class TransitionPreview {
    private videoEl: HTMLVideoElement | null = null;
    private _active = false;
    private _baseClipPath: string = '';

    constructor() {}

    /** Bind the video element to apply CSS effects to */
    bind(video: HTMLVideoElement): void {
        this.videoEl = video;
        // Ensure transitions are smooth
        video.style.transition = 'none';
    }

    /**
     * Called every frame (~60Hz) from the segment polling loop.
     * Computes transition progress and applies CSS effects.
     *
     * @param currentTime - current video time
     * @param segEnd - end time of the current segment
     * @param segStart - start time of the current segment  
     * @param transition - the transition def for THIS cut (null if none or last segment)
     * @param isNewSegment - true on the first frame after jumping to a new segment
     */
    update(
        currentTime: number,
        segEnd: number,
        segStart: number,
        transition: TransitionDef | null,
        isNewSegment: boolean,
    ): void {
        if (!this.videoEl) return;

        if (!transition || transition.type === 'none') {
            this._clearEffects();
            return;
        }

        const dur = transition.duration;
        const halfDur = dur / 2;

        // Outgoing phase: approaching end of current segment
        const timeToEnd = segEnd - currentTime;
        if (timeToEnd <= halfDur && timeToEnd > 0) {
            // Progress: 0 (start of transition) → 1 (at cut point)
            const progress = 1 - (timeToEnd / halfDur);
            this._applyOutgoing(transition.type, progress);
            this._active = true;
            return;
        }

        // Incoming phase: just entered a new segment.
        // NOTE: The caller (TransportBar._enforceSegments) passes the
        // *previous* cut's transition for this phase, which is correct —
        // the incoming half should match the outgoing half of the same cut.
        // Wipe/slide directions are intentionally inverted in _applyIncoming
        // to create a symmetric "wipe-out then wipe-in" visual effect.
        const timeFromStart = currentTime - segStart;
        if (isNewSegment || (timeFromStart <= halfDur && timeFromStart >= 0)) {
            // Progress: 1 (at cut point) → 0 (fully revealed)
            const progress = 1 - (timeFromStart / halfDur);
            if (progress > 0) {
                this._applyIncoming(transition.type, Math.max(0, progress));
                this._active = true;
                return;
            }
        }

        // Outside transition window
        if (this._active) {
            this._clearEffects();
        }
    }

    /** Clear all transition effects */
    clear(): void {
        this._clearEffects();
    }

    /**
     * Set a base clip-path that should be preserved while transitions run.
     * Used by CropOverlay to avoid clip-path conflicts.
     * When set, wipe/slide transitions degrade to opacity-only.
     */
    setBaseClipPath(clipPath: string): void {
        this._baseClipPath = clipPath;
    }

    /** Clean up: clear effects and release video reference */
    destroy(): void {
        this._clearEffects();
        this.videoEl = null;
    }

    // ── Private ──────────────────────────────────────────────────

    /** Apply outgoing (fade-out / wipe-out / slide-out) effect */
    private _applyOutgoing(type: TransitionType, progress: number): void {
        if (!this.videoEl) return;

        // When crop preview is active, wipe/slide would overwrite the crop's
        // clip-path. Fall back to opacity-only for those types.
        const safeType = this._baseClipPath ? 'fade' : type;

        switch (safeType) {
            case 'fade':
            case 'dissolve':
                this.videoEl.style.opacity = String(1 - progress);
                this.videoEl.style.transform = '';
                break;

            case 'wipeleft':
                // Reveal shrinks from right to left
                this.videoEl.style.opacity = '';
                this.videoEl.style.clipPath = `inset(0 ${progress * 100}% 0 0)`;
                this.videoEl.style.transform = '';
                break;

            case 'wiperight':
                // Reveal shrinks from left to right
                this.videoEl.style.opacity = '';
                this.videoEl.style.clipPath = `inset(0 0 0 ${progress * 100}%)`;
                this.videoEl.style.transform = '';
                break;

            case 'slideleft':
                this.videoEl.style.opacity = '';
                this.videoEl.style.transform = `translateX(${-progress * 100}%)`;
                break;

            case 'slideright':
                this.videoEl.style.opacity = '';
                this.videoEl.style.transform = `translateX(${progress * 100}%)`;
                break;
        }
    }

    /**
     * Apply incoming (fade-in / wipe-in / slide-in) effect.
     * Wipe/slide directions are intentionally inverted relative to the
     * outgoing phase so the visual effect is symmetric across the cut:
     *   - wipeleft outgoing clips from right → incoming clips from left
     *   - slideright outgoing slides right → incoming slides from right
     */
    private _applyIncoming(type: TransitionType, progress: number): void {
        if (!this.videoEl) return;

        // Fall back to opacity when crop preview owns clip-path
        const safeType = this._baseClipPath ? 'fade' : type;

        switch (safeType) {
            case 'fade':
            case 'dissolve':
                this.videoEl.style.opacity = String(1 - progress);
                this.videoEl.style.transform = '';
                break;

            case 'wipeleft':
                // Incoming wipe from left: clip from left side
                this.videoEl.style.opacity = '';
                this.videoEl.style.clipPath = `inset(0 0 0 ${progress * 100}%)`;
                this.videoEl.style.transform = '';
                break;

            case 'wiperight':
                // Incoming wipe from right: clip from right side
                this.videoEl.style.opacity = '';
                this.videoEl.style.clipPath = `inset(0 ${progress * 100}% 0 0)`;
                this.videoEl.style.transform = '';
                break;

            case 'slideleft':
                this.videoEl.style.opacity = '';
                this.videoEl.style.transform = `translateX(${progress * 100}%)`;
                break;

            case 'slideright':
                this.videoEl.style.opacity = '';
                this.videoEl.style.transform = `translateX(${-progress * 100}%)`;
                break;
        }
    }

    private _clearEffects(): void {
        if (!this.videoEl) return;
        if (this._active) {
            this.videoEl.style.opacity = '';
            // Restore crop preview's clip-path instead of clearing entirely
            this.videoEl.style.clipPath = this._baseClipPath;
            this.videoEl.style.transform = '';
            this._active = false;
        }
    }
}
