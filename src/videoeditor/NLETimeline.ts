/**
 * NLETimeline — multi-track timeline wrapper for the Video Editor modal.
 *
 * Renders V1 (video) and A1 (audio) track lanes around the existing
 * EditTimeline canvas. Supports horizontal zoom for detailed editing
 * of long videos and snapping for precise segment alignment.
 *
 * Agent-friendly: all interactive areas have data-tool-id and aria-label.
 */

import { EditManager } from '@ffmpega/loadlast/editing/EditManager';
import { EditTimeline, EditTimelineCallbacks } from '@ffmpega/loadlast/editing/EditTimeline';
import { AudioTimeline } from './AudioTimeline';

const MIN_ZOOM = 1;
const MAX_ZOOM = 20;
const ZOOM_STEP = 1.25;
const HEADER_W = 56;

export class NLETimeline {
    private container: HTMLDivElement;
    private scrollWrapper: HTMLDivElement;
    private scrollInner: HTMLDivElement;
    private ruler: HTMLDivElement;
    private tracksContainer: HTMLDivElement;
    private videoTrack: HTMLDivElement;
    private audioTrack: HTMLDivElement;
    private editTimeline: EditTimeline;
    private audioTimeline: AudioTimeline | null = null;
    private manager: EditManager;
    private playheadEl: HTMLDivElement;
    private _snapping: boolean = true;
    private _zoom: number = 1;
    private _zoomLabel: HTMLSpanElement;
    private _callbacks: EditTimelineCallbacks;

    constructor(manager: EditManager, callbacks: EditTimelineCallbacks) {
        this.manager = manager;
        this._callbacks = callbacks;

        this.container = document.createElement('div');
        this.container.className = 'veditor-nle-timeline';
        this.container.setAttribute('data-tool-id', 'veditor-timeline');
        this.container.setAttribute('aria-label', 'Multi-track editing timeline');
        this.container.setAttribute('role', 'region');

        // ── Toolbar (snap + zoom) ──
        const toolbar = document.createElement('div');
        toolbar.className = 'veditor-timeline-toolbar';
        toolbar.style.cssText = 'display:flex;align-items:center;justify-content:space-between;padding:2px 4px;gap:4px;flex-shrink:0;';

        // Left: Snap toggle
        const snapBtn = document.createElement('button');
        snapBtn.className = 'veditor-btn veditor-snap-btn active';
        snapBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg> Snap`;
        snapBtn.title = 'Toggle clip snapping (S)';
        snapBtn.setAttribute('data-tool-id', 'veditor-snap-toggle');
        snapBtn.setAttribute('aria-label', 'Toggle clip snapping');
        snapBtn.style.cssText = 'font-size:11px;padding:2px 8px;border-radius:4px;';
        snapBtn.addEventListener('click', () => {
            this._snapping = !this._snapping;
            snapBtn.classList.toggle('active', this._snapping);
            this.editTimeline.setSnapping(this._snapping);
            this.audioTimeline?.setSnapping(this._snapping);
        });

        // Right: Zoom controls
        const zoomGroup = document.createElement('div');
        zoomGroup.style.cssText = 'display:flex;align-items:center;gap:2px;';

        const zoomOutBtn = this._makeToolbarBtn('−', 'Zoom out timeline', 'veditor-tl-zoom-out', () => this.setZoom(this._zoom / ZOOM_STEP));
        const zoomInBtn = this._makeToolbarBtn('+', 'Zoom in timeline', 'veditor-tl-zoom-in', () => this.setZoom(this._zoom * ZOOM_STEP));
        const zoomFitBtn = this._makeToolbarBtn('Fit', 'Fit timeline to view', 'veditor-tl-zoom-fit', () => this.setZoom(1));

        this._zoomLabel = document.createElement('span');
        this._zoomLabel.style.cssText = 'font-size:10px;color:rgba(255,255,255,0.4);min-width:36px;text-align:center;font-variant-numeric:tabular-nums;';
        this._zoomLabel.textContent = '1.0×';

        zoomGroup.append(zoomOutBtn, this._zoomLabel, zoomInBtn, zoomFitBtn);
        toolbar.append(snapBtn, zoomGroup);

        // ── Scrollable wrapper (contains ruler + tracks) ──
        this.scrollWrapper = document.createElement('div');
        this.scrollWrapper.className = 'veditor-timeline-scroll';
        this.scrollWrapper.style.cssText = 'flex:1;overflow-x:auto;overflow-y:hidden;min-height:0;position:relative;';

        this.scrollInner = document.createElement('div');
        this.scrollInner.className = 'veditor-timeline-scroll-inner';
        this.scrollInner.style.cssText = 'min-width:100%;position:relative;display:flex;flex-direction:column;';

        // ── Ruler ──
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
        this.editTimeline = new EditTimeline(manager, callbacks);
        const canvasWrap = this.videoTrack.querySelector('.veditor-track-canvas-wrap');
        if (canvasWrap) {
            canvasWrap.appendChild(this.editTimeline.element);
        }

        // ── A1 Track ──
        this.audioTrack = this._createTrack('A1', 'audio');

        // ── Playhead ──
        this.playheadEl = document.createElement('div');
        this.playheadEl.className = 'veditor-playhead';
        this.playheadEl.style.left = `${HEADER_W}px`;
        this.playheadEl.setAttribute('data-tool-id', 'veditor-playhead');
        this.playheadEl.setAttribute('aria-label', 'Playhead position indicator');

        // ── Assemble ──
        this.tracksContainer.append(this.videoTrack, this.audioTrack);
        this.scrollInner.append(this.ruler, this.tracksContainer, this.playheadEl);
        this.scrollWrapper.appendChild(this.scrollInner);
        this.container.append(toolbar, this.scrollWrapper);

        // ── Ruler click → seek ──
        this.ruler.addEventListener('pointerdown', (e: PointerEvent) => {
            e.stopPropagation();
            const time = this._rulerXToTime(e.clientX);
            if (time >= 0) {
                this.setPlayhead(time);
                callbacks.onPlayheadChanged(time);
            }
        });

        // ── Ctrl+Scroll to zoom ──
        this.scrollWrapper.addEventListener('wheel', (e: WheelEvent) => {
            if (e.ctrlKey || e.metaKey) {
                e.preventDefault();
                const factor = e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;

                // Zoom centered on cursor position
                const wrapperRect = this.scrollWrapper.getBoundingClientRect();
                const cursorX = e.clientX - wrapperRect.left + this.scrollWrapper.scrollLeft;
                const cursorFrac = cursorX / this.scrollInner.clientWidth;

                this.setZoom(this._zoom * factor);

                // Restore scroll position to keep cursor position stable
                const newCursorX = cursorFrac * this.scrollInner.clientWidth;
                this.scrollWrapper.scrollLeft = newCursorX - (e.clientX - wrapperRect.left);
            }
        }, { passive: false });

    }

    get element(): HTMLDivElement {
        return this.container;
    }

    get timeline(): EditTimeline {
        return this.editTimeline;
    }

    setPlayhead(time: number): void {
        this.editTimeline.setPlayhead(time);
        this.audioTimeline?.setPlayhead(time);
        this._updatePlayheadPosition(time);
    }

    setZoom(zoom: number): void {
        this._zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, zoom));
        this._zoomLabel.textContent = `${this._zoom.toFixed(1)}×`;

        // Change the inner width
        const baseW = this.scrollWrapper.clientWidth;
        const innerW = Math.max(baseW, baseW * this._zoom);
        this.scrollInner.style.width = `${innerW}px`;

        // Re-render canvases at new width
        this.render();
    }

    render(): void {
        this.editTimeline.render();
        this.audioTimeline?.render();
        this._renderRuler();
        if (this.editTimeline.playhead > 0) {
            this._updatePlayheadPosition(this.editTimeline.playhead);
        }
    }

    /** Mount an AudioTimeline in the A1 track */
    setAudioTimeline(at: AudioTimeline): void {
        this.audioTimeline = at;
        at.setSnapping(this._snapping);
        const wrap = this.audioTrack.querySelector('.veditor-track-canvas-wrap');
        if (wrap) {
            wrap.innerHTML = '';
            wrap.appendChild(at.element);
        }
    }

    /** Scroll to keep a time value visible */
    scrollToTime(time: number): void {
        const dur = this.manager.videoDuration;
        if (dur <= 0) return;

        const innerW = this.scrollInner.clientWidth;
        const trackW = innerW - HEADER_W;
        const x = HEADER_W + (time / dur) * trackW;

        const wrapW = this.scrollWrapper.clientWidth;
        const scrollLeft = this.scrollWrapper.scrollLeft;

        // If playhead is near the edges, scroll to keep it visible
        const margin = wrapW * 0.1;
        if (x < scrollLeft + margin) {
            this.scrollWrapper.scrollLeft = Math.max(0, x - margin);
        } else if (x > scrollLeft + wrapW - margin) {
            this.scrollWrapper.scrollLeft = x - wrapW + margin;
        }
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

        const innerW = this.scrollInner.clientWidth;
        const trackW = innerW - HEADER_W;
        const x = HEADER_W + (time / dur) * trackW;
        this.playheadEl.style.left = `${x}px`;
    }

    private _renderRuler(): void {
        const dur = this.manager.videoDuration;
        if (dur <= 0) return;

        this.ruler.innerHTML = '';
        const innerW = this.scrollInner.clientWidth;
        const trackW = innerW - HEADER_W;

        // Determine interval based on visible duration (zoom-aware)
        const pxPerSec = trackW / dur;
        let interval: number;
        if (pxPerSec > 100) interval = 0.5;
        else if (pxPerSec > 50) interval = 1;
        else if (pxPerSec > 20) interval = 2;
        else if (pxPerSec > 10) interval = 5;
        else if (pxPerSec > 4) interval = 10;
        else interval = 30;

        for (let t = 0; t <= dur; t += interval) {
            const marker = document.createElement('div');
            const x = HEADER_W + (t / dur) * trackW;
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
                white-space: nowrap;
            `;
            const mins = Math.floor(t / 60);
            const secs = Math.floor(t % 60);
            const frac = t % 1;
            if (frac > 0.01) {
                label.textContent = `${mins}:${secs.toString().padStart(2, '0')}.${Math.round(frac * 10)}`;
            } else {
                label.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;
            }
            marker.append(label, tick);
            this.ruler.appendChild(marker);
        }
    }

    /** Map a ruler clientX to source time */
    private _rulerXToTime(clientX: number): number {
        const dur = this.manager.videoDuration;
        if (dur <= 0) return -1;
        const innerRect = this.scrollInner.getBoundingClientRect();
        const innerW = this.scrollInner.clientWidth;
        const trackW = innerW - HEADER_W;
        const x = clientX - innerRect.left - HEADER_W;
        if (x < 0 || x > trackW) return -1;
        return (x / trackW) * dur;
    }

    private _makeToolbarBtn(text: string, title: string, toolId: string, onClick: () => void): HTMLButtonElement {
        const btn = document.createElement('button');
        btn.className = 'veditor-btn';
        btn.textContent = text;
        btn.title = title;
        btn.setAttribute('data-tool-id', toolId);
        btn.setAttribute('aria-label', title);
        btn.style.cssText = 'font-size:11px;padding:2px 8px;border-radius:4px;min-width:24px;';
        btn.addEventListener('click', () => onClick());
        return btn;
    }
}
