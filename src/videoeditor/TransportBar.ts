import { iconPlay, iconPause, iconStepBack, iconStepForward } from './icons';
import { EditManager } from '@ffmpega/loadlast/editing/EditManager';

/**
 * TransportBar — play/pause, frame-step, J/K/L shuttle, time display.
 *
 * Controls a native <video> element and reports playhead position
 * back to the timeline via a callback.
 *
 * Segment-aware: playback follows the segment ARRAY ORDER, not source
 * time order. A segment [7.0, 7.3] moved to position 0 plays first.
 * Tracks a `_currentSegIdx` to jump between segments non-linearly.
 */

export interface TransportBarCallbacks {
    onTimeUpdate: (time: number) => void;
    onPlayStateChange: (playing: boolean) => void;
}

export class TransportBar {
    private container: HTMLDivElement;
    private video: HTMLVideoElement | null = null;
    private callbacks: TransportBarCallbacks;
    private timeDisplay: HTMLSpanElement;
    private playBtn: HTMLButtonElement;
    private shuttleSpeed: number = 1;
    private _keyHandler: ((e: KeyboardEvent) => void) | null = null;
    private _editManager: EditManager | null = null;
    private _animFrameId: number | null = null;
    private _currentSegIdx: number = 0;
    private _seekLock: boolean = false;
    /** When a seek is pending, this holds the desired time */
    private _targetTime: number | null = null;

    constructor(callbacks: TransportBarCallbacks) {
        this.callbacks = callbacks;
        this.container = document.createElement('div');
        this.container.className = 'veditor-transport';
        this.container.setAttribute('data-tool-id', 'veditor-transport');
        this.container.setAttribute('aria-label', 'Video transport controls');
        this.container.setAttribute('role', 'toolbar');

        // Frame step back
        const stepBack = this._makeBtn(iconStepBack, 'Step back 1 frame (←)', () => this._stepFrame(-1), 'veditor-step-back');

        // Play/Pause
        this.playBtn = this._makeBtn(iconPlay, 'Play / Pause (Space or K)', () => this._togglePlay(), 'veditor-play-btn');

        // Frame step forward
        const stepFwd = this._makeBtn(iconStepForward, 'Step forward 1 frame (→)', () => this._stepFrame(1), 'veditor-step-forward');

        // Time display
        this.timeDisplay = document.createElement('span');
        this.timeDisplay.className = 'veditor-time';
        this.timeDisplay.textContent = '00:00.00 / 00:00.00';
        this.timeDisplay.setAttribute('data-tool-id', 'veditor-timecode');
        this.timeDisplay.setAttribute('aria-label', 'Current time / total duration');
        this.timeDisplay.setAttribute('aria-live', 'polite');

        this.container.append(stepBack, this.playBtn, stepFwd, this.timeDisplay);

        // Keyboard shortcuts
        this._keyHandler = (e: KeyboardEvent) => this._onKeyDown(e);
        document.addEventListener('keydown', this._keyHandler);
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    /** Bind the edit manager for segment-aware playback */
    setEditManager(manager: EditManager): void {
        this._editManager = manager;
    }

    bindVideo(video: HTMLVideoElement): void {
        this.video = video;
        video.addEventListener('timeupdate', () => {
            // Don't enforce during user-initiated seeks
            if (!this._seekLock && !video.paused) {
                this._enforceSegments();
            }
            this._updateTimeDisplay();
            this.callbacks.onTimeUpdate(
                this._targetTime !== null ? this._targetTime : video.currentTime,
            );
        });
        // When a seek completes, clear the target only if we actually arrived
        video.addEventListener('seeked', () => {
            if (this._targetTime !== null) {
                // Only clear if video actually reached near the target
                // (failed seeks stay at 0 or the old position)
                if (Math.abs(video.currentTime - this._targetTime) < 0.5) {
                    this._targetTime = null;
                }
                // else: seek failed — keep _targetTime for display
            }
            this._updateTimeDisplay();
            this.callbacks.onTimeUpdate(
                this._targetTime !== null ? this._targetTime : video.currentTime,
            );
        });
        video.addEventListener('play', () => {
            this._targetTime = null; // Real playback supersedes pending seek
            this.playBtn.innerHTML = iconPause;
            this.callbacks.onPlayStateChange(true);
            this._startSegmentPolling();
        });
        video.addEventListener('pause', () => {
            this.playBtn.innerHTML = iconPlay;
            this.callbacks.onPlayStateChange(false);
            this._stopSegmentPolling();
        });
        video.addEventListener('loadedmetadata', () => {
            this._updateTimeDisplay();
        });
    }

    seekTo(time: number): void {
        if (!this.video) return;
        // Lock out enforcement during seek
        this._seekLock = true;
        const dur = this.video.duration;
        const maxTime = (dur && isFinite(dur)) ? dur : Infinity;
        const clamped = Math.max(0, Math.min(time, maxTime));
        this._targetTime = clamped;

        // Try setting currentTime directly
        this.video.currentTime = clamped;

        // Also try fastSeek if available (better for some formats)
        if (typeof this.video.fastSeek === 'function') {
            try { this.video.fastSeek(clamped); } catch { /* ignore */ }
        }

        // Update segment index using the TARGET time (not video.currentTime
        // which may not have updated yet for async seeks)
        this._syncSegmentIndexForTime(clamped);

        // Update display immediately with target time
        this._updateTimeDisplay();
        this.callbacks.onTimeUpdate(clamped);

        // Release lock after the seek settles
        requestAnimationFrame(() => { this._seekLock = false; });
    }

    /** Seek to an output-timeline position (mapped through segment order) */
    seekToOutput(outputTime: number): void {
        if (!this.video || !this._editManager) {
            this.seekTo(outputTime);
            return;
        }
        const mgr = this._editManager;
        const segs = mgr.segments;
        let accumulated = 0;

        for (let i = 0; i < segs.length; i++) {
            const segDur = segs[i].end - segs[i].start;
            if (outputTime <= accumulated + segDur) {
                this._currentSegIdx = i;
                this.video.currentTime = segs[i].start + (outputTime - accumulated);
                return;
            }
            accumulated += segDur;
        }

        // Past end — go to start of first
        this._currentSegIdx = 0;
        if (segs.length > 0) {
            this.video.currentTime = segs[0].start;
        }
    }

    destroy(): void {
        if (this._keyHandler) {
            document.removeEventListener('keydown', this._keyHandler);
            this._keyHandler = null;
        }
        this._stopSegmentPolling();
        this.container.remove();
    }

    // ── Private ──────────────────────────────────────────────────

    /**
     * Figure out which segment index the current video.currentTime
     * falls in. Used after a raw seekTo() call.
     */
    private _syncSegmentIndex(): void {
        if (!this.video || !this._editManager) return;
        this._syncSegmentIndexForTime(this.video.currentTime);
    }

    /** Sync segment index using a given time (not video.currentTime) */
    private _syncSegmentIndexForTime(t: number): void {
        if (!this._editManager) return;
        const segs = this._editManager.segments;

        // Prefer current index if it still matches
        const cur = segs[this._currentSegIdx];
        if (cur && t >= cur.start - 0.1 && t <= cur.end + 0.1) return;

        for (let i = 0; i < segs.length; i++) {
            if (t >= segs[i].start - 0.1 && t <= segs[i].end + 0.1) {
                this._currentSegIdx = i;
                return;
            }
        }
        // No match — find the nearest segment
        let bestIdx = 0;
        let bestDist = Infinity;
        for (let i = 0; i < segs.length; i++) {
            const mid = (segs[i].start + segs[i].end) / 2;
            const dist = Math.abs(t - mid);
            if (dist < bestDist) {
                bestDist = dist;
                bestIdx = i;
            }
        }
        this._currentSegIdx = bestIdx;
    }

    /**
     * Enforce segment boundaries during playback.
     * Follows array order (non-linear): when current segment ends,
     * jump to the NEXT segment in the array regardless of source time.
     */
    private _enforceSegments(): void {
        if (!this.video || !this._editManager) return;
        if (this._seekLock || this.video.paused) return; // Don't fight user seeks
        const segs = this._editManager.segments;
        if (segs.length === 0) return;

        // Clamp index
        if (this._currentSegIdx < 0 || this._currentSegIdx >= segs.length) {
            this._currentSegIdx = 0;
        }

        const seg = segs[this._currentSegIdx];
        const t = this.video.currentTime;

        // Past the end of CURRENT segment?
        if (t >= seg.end - 0.02) {
            const nextIdx = this._currentSegIdx + 1;
            if (nextIdx < segs.length) {
                // Jump to next segment in array order (may be non-linear)
                this._currentSegIdx = nextIdx;
                this.video.currentTime = segs[nextIdx].start;
            } else {
                // Past all segments — loop to first
                this._currentSegIdx = 0;
                if (!this.video.paused) {
                    this.video.currentTime = segs[0].start;
                }
            }
            return;
        }

        // Before the start of current segment (can happen after reorder)?
        if (t < seg.start - 0.05) {
            this.video.currentTime = seg.start;
        }
    }

    /**
     * rAF polling for responsive segment boundary enforcement.
     * HTML5 timeupdate fires ~4Hz; rAF gives ~60Hz.
     */
    private _startSegmentPolling(): void {
        if (this._animFrameId !== null) return;
        const poll = (): void => {
            this._enforceSegments();
            this._animFrameId = requestAnimationFrame(poll);
        };
        this._animFrameId = requestAnimationFrame(poll);
    }

    private _stopSegmentPolling(): void {
        if (this._animFrameId !== null) {
            cancelAnimationFrame(this._animFrameId);
            this._animFrameId = null;
        }
    }

    private _togglePlay(): void {
        if (!this.video) return;
        if (this.video.paused) {
            // If at end of last segment, jump to start first
            if (this._editManager) {
                const segs = this._editManager.segments;
                if (segs.length > 0) {
                    const lastSeg = segs[segs.length - 1];
                    if (this.video.currentTime >= lastSeg.end - 0.02 &&
                        this._currentSegIdx >= segs.length - 1) {
                        this._currentSegIdx = 0;
                        this.video.currentTime = segs[0].start;
                    }
                }
            }
            this.video.playbackRate = this.shuttleSpeed;
            this.video.play();
        } else {
            this.video.pause();
        }
    }

    private _stepFrame(direction: number): void {
        if (!this.video) return;
        this.video.pause();
        const fps = 30;
        const dt = direction / fps;
        let newTime = this.video.currentTime + dt;

        if (this._editManager) {
            const segs = this._editManager.segments;
            const seg = segs[this._currentSegIdx];
            if (seg) {
                if (direction > 0 && newTime >= seg.end) {
                    // Step forward past current segment end
                    const nextIdx = this._currentSegIdx + 1;
                    if (nextIdx < segs.length) {
                        this._currentSegIdx = nextIdx;
                        newTime = segs[nextIdx].start;
                    } else {
                        newTime = seg.end - 1 / fps; // stay at end
                    }
                } else if (direction < 0 && newTime < seg.start) {
                    // Step backward past current segment start
                    const prevIdx = this._currentSegIdx - 1;
                    if (prevIdx >= 0) {
                        this._currentSegIdx = prevIdx;
                        newTime = segs[prevIdx].end - 1 / fps;
                    } else {
                        newTime = seg.start; // stay at start
                    }
                }
            }
        }

        this.video.currentTime = Math.max(0, newTime);
    }

    private _onKeyDown(e: KeyboardEvent): void {
        if (
            e.target instanceof HTMLInputElement ||
            e.target instanceof HTMLTextAreaElement
        ) {
            return;
        }

        switch (e.key.toLowerCase()) {
            case 'k':
                e.preventDefault();
                this._togglePlay();
                break;
            case 'j':
                e.preventDefault();
                this.shuttleSpeed = Math.max(0.25, this.shuttleSpeed / 2);
                if (this.video && !this.video.paused) {
                    this.video.playbackRate = this.shuttleSpeed;
                }
                break;
            case 'l':
                e.preventDefault();
                this.shuttleSpeed = Math.min(4, this.shuttleSpeed * 2);
                if (this.video && !this.video.paused) {
                    this.video.playbackRate = this.shuttleSpeed;
                }
                break;
            case 'i':
            case 'o':
            case 's':
                break;
            case ' ':
                e.preventDefault();
                this._togglePlay();
                break;
        }
    }

    /**
     * Time display: shows output-relative time when edit manager is bound.
     * Computes output time by walking segments in array order up to current.
     */
    private _updateTimeDisplay(): void {
        if (!this.video) return;
        // Use target time if we have one (pending seek)
        const currentTime = this._targetTime !== null ? this._targetTime : this.video.currentTime;

        if (this._editManager) {
            const mgr = this._editManager;
            const segs = mgr.segments;
            const outputDur = mgr.getOutputDuration();

            // Compute output time from segment index + position within segment
            let outputTime = 0;
            for (let i = 0; i < this._currentSegIdx && i < segs.length; i++) {
                outputTime += segs[i].end - segs[i].start;
            }
            const seg = segs[this._currentSegIdx];
            if (seg) {
                outputTime += Math.max(0, currentTime - seg.start);
                outputTime = Math.min(outputTime, outputDur);
            }

            this.timeDisplay.textContent = `${this._formatTime(outputTime)} / ${this._formatTime(outputDur)}`;
        } else {
            const current = this._formatTime(currentTime);
            const total = this._formatTime(this.video.duration || 0);
            this.timeDisplay.textContent = `${current} / ${total}`;
        }
    }

    private _formatTime(seconds: number): string {
        if (!isFinite(seconds)) return '00:00.00';
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins.toString().padStart(2, '0')}:${secs.toFixed(2).padStart(5, '0')}`;
    }

    private _makeBtn(label: string, title: string, onClick: () => void, toolId?: string): HTMLButtonElement {
        const btn = document.createElement('button');
        btn.className = 'veditor-btn veditor-btn-icon';
        btn.innerHTML = label;
        btn.title = title;
        if (toolId) {
            btn.setAttribute('data-tool-id', toolId);
            btn.setAttribute('aria-label', title);
        }
        btn.addEventListener('click', onClick);
        return btn;
    }
}
