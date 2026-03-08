/**
 * NLETimeline — multi-track timeline wrapper for the Video Editor modal.
 *
 * Renders V1 (video) and A1 (audio) track lanes around the existing
 * EditTimeline canvas. Phase 1: both tracks mirror the same segment
 * data — true multi-track compositing is Phase 2+.
 *
 * Agent-friendly: all interactive areas have data-tool-id and aria-label.
 */

import { EditManager } from '@ffmpega/loadlast/editing/EditManager';
import { EditTimeline, EditTimelineCallbacks } from '@ffmpega/loadlast/editing/EditTimeline';

export class NLETimeline {
    private container: HTMLDivElement;
    private ruler: HTMLDivElement;
    private tracksContainer: HTMLDivElement;
    private videoTrack: HTMLDivElement;
    private audioTrack: HTMLDivElement;
    private editTimeline: EditTimeline;
    private manager: EditManager;
    private playheadEl: HTMLDivElement;

    constructor(manager: EditManager, callbacks: EditTimelineCallbacks) {
        this.manager = manager;

        this.container = document.createElement('div');
        this.container.className = 'veditor-nle-timeline';
        this.container.setAttribute('data-tool-id', 'veditor-timeline');
        this.container.setAttribute('aria-label', 'Multi-track editing timeline');
        this.container.setAttribute('role', 'region');

        // ── Ruler (time markers) ──
        this.ruler = document.createElement('div');
        this.ruler.className = 'veditor-timeline-ruler';
        this.ruler.setAttribute('data-tool-id', 'veditor-timeline-ruler');
        this.ruler.setAttribute('aria-label', 'Timeline ruler - click to seek');
        this.ruler.style.cursor = 'pointer';

        // ── Tracks container ──
        this.tracksContainer = document.createElement('div');
        this.tracksContainer.className = 'veditor-timeline-tracks';

        // ── V1 Track ──
        this.videoTrack = this._createTrack('V1', 'video');

        // Create the actual EditTimeline and put its canvas in the V1 track
        this.editTimeline = new EditTimeline(manager, callbacks);
        const canvasWrap = this.videoTrack.querySelector('.veditor-track-canvas-wrap');
        if (canvasWrap) {
            // Remove the EditTimeline's own container chrome and use just its element
            canvasWrap.appendChild(this.editTimeline.element);
        }

        // ── A1 Track ──
        this.audioTrack = this._createTrack('A1', 'audio');
        const audioCanvasWrap = this.audioTrack.querySelector('.veditor-track-canvas-wrap');
        if (audioCanvasWrap) {
            // Phase 1: simple colored bar placeholder for audio
            const audioBar = document.createElement('div');
            audioBar.style.cssText = `
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg,
                    rgba(34, 197, 94, 0.15) 0%,
                    rgba(34, 197, 94, 0.25) 50%,
                    rgba(34, 197, 94, 0.15) 100%
                );
                border-radius: 4px;
                position: relative;
            `;
            audioBar.setAttribute('data-tool-id', 'veditor-audio-track-content');
            audioBar.setAttribute('aria-label', 'Audio track (visual placeholder)');

            // Simple waveform-like visual
            const waveform = document.createElement('div');
            waveform.style.cssText = `
                position: absolute;
                inset: 8px 4px;
                background: repeating-linear-gradient(
                    90deg,
                    rgba(34, 197, 94, 0.4) 0px,
                    rgba(34, 197, 94, 0.1) 2px,
                    rgba(34, 197, 94, 0.3) 4px
                );
                border-radius: 2px;
                opacity: 0.6;
            `;
            audioBar.appendChild(waveform);
            audioCanvasWrap.appendChild(audioBar);
        }

        // ── Playhead ──
        this.playheadEl = document.createElement('div');
        this.playheadEl.className = 'veditor-playhead';
        this.playheadEl.style.left = '56px'; // Start at track start
        this.playheadEl.setAttribute('data-tool-id', 'veditor-playhead');
        this.playheadEl.setAttribute('aria-label', 'Playhead position indicator');

        // ── Assemble ──
        this.tracksContainer.append(this.videoTrack, this.audioTrack);
        this.container.append(this.ruler, this.tracksContainer, this.playheadEl);

        // ── Ruler click → seek ──
        this.ruler.addEventListener('pointerdown', (e: PointerEvent) => {
            e.stopPropagation();
            const time = this._rulerXToTime(e.clientX);
            if (time >= 0) {
                this.setPlayhead(time);
                callbacks.onPlayheadChanged(time);
            }
        });
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    get timeline(): EditTimeline {
        return this.editTimeline;
    }

    setPlayhead(time: number): void {
        this.editTimeline.setPlayhead(time);
        this._updatePlayheadPosition(time);
    }

    render(): void {
        this.editTimeline.render();
        this._renderRuler();
    }

    destroy(): void {
        this.editTimeline.destroy();
        this.container.remove();
    }

    // ── Private ──────────────────────────────────────────────────

    private _createTrack(label: string, type: 'video' | 'audio'): HTMLDivElement {
        const track = document.createElement('div');
        track.className = 'veditor-track';
        track.setAttribute('data-tool-id', `veditor-track-${label.toLowerCase()}`);
        track.setAttribute('aria-label', `${type === 'video' ? 'Video' : 'Audio'} track ${label}`);

        const header = document.createElement('div');
        header.className = `veditor-track-header veditor-track-header-${type}`;
        header.textContent = label;
        header.setAttribute('data-tool-id', `veditor-track-header-${label.toLowerCase()}`);

        const canvasWrap = document.createElement('div');
        canvasWrap.className = 'veditor-track-canvas-wrap';

        track.append(header, canvasWrap);
        return track;
    }

    private _updatePlayheadPosition(time: number): void {
        const dur = this.manager.videoDuration;
        if (dur <= 0) return;

        // Header is 56px, then track content fills the rest
        const headerW = 56;
        const containerW = this.tracksContainer.clientWidth;
        const trackW = containerW - headerW;
        const x = headerW + (time / dur) * trackW;
        this.playheadEl.style.left = `${x}px`;
    }

    private _renderRuler(): void {
        const dur = this.manager.videoDuration;
        if (dur <= 0) return;

        this.ruler.innerHTML = '';
        const headerW = 56;
        const containerW = this.container.clientWidth;
        const trackW = containerW - headerW;

        // Determine interval based on duration
        let interval = 1;
        if (dur > 60) interval = 10;
        else if (dur > 30) interval = 5;
        else if (dur > 10) interval = 2;

        for (let t = 0; t <= dur; t += interval) {
            const marker = document.createElement('div');
            const x = headerW + (t / dur) * trackW;
            marker.style.cssText = `
                position: absolute;
                left: ${x}px;
                top: 0;
                height: 100%;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: flex-end;
                padding-bottom: 2px;
            `;
            const tick = document.createElement('div');
            tick.style.cssText = `
                width: 1px;
                height: 8px;
                background: rgba(255,255,255,0.15);
            `;
            const label = document.createElement('span');
            label.style.cssText = `
                font-size: 9px;
                color: rgba(255,255,255,0.3);
                font-variant-numeric: tabular-nums;
                transform: translateX(-50%);
            `;
            const mins = Math.floor(t / 60);
            const secs = Math.floor(t % 60);
            label.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
            marker.append(label, tick);
            this.ruler.appendChild(marker);
        }
    }

    /** Map a ruler clientX to source time */
    private _rulerXToTime(clientX: number): number {
        const dur = this.manager.videoDuration;
        if (dur <= 0) return -1;
        const headerW = 56;
        const containerRect = this.container.getBoundingClientRect();
        const containerW = containerRect.width;
        const trackW = containerW - headerW;
        const x = clientX - containerRect.left - headerW;
        if (x < 0 || x > trackW) return -1;
        return (x / trackW) * dur;
    }
}
