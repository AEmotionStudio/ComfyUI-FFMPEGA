/**
 * AudioTimeline — canvas-based audio track for the NLE timeline.
 *
 * Renders waveform peaks behind audio segments, with draggable trim
 * handles and double-click to split — mirrors EditTimeline behavior
 * but for audio segments.
 */

import { AudioEditManager, AudioSegment } from './AudioSegment';
import { snapToEdges, collectEdges } from './SnapEngine';

// ─── Constants ─────────────────────────────────────────────────────
const TRACK_H = 48;
const TRACK_PAD = 4;
const HANDLE_W = 8;
const PLAYHEAD_W = 2;

const SEG_COLOR = 'rgba(34, 197, 94, 0.35)';
const SEG_BORDER = 'rgba(34, 197, 94, 0.7)';
const SEG_MUTED_COLOR = 'rgba(100, 100, 100, 0.3)';
const EXCLUDED_COLOR = 'rgba(20, 20, 20, 0.85)';
const EXCLUDED_STRIPE = 'rgba(50, 50, 50, 0.5)';
const HANDLE_COLOR = '#fff';
const HANDLE_HOVER = '#4ade80';
const PLAYHEAD_COLOR = '#ff5555';
const WAVE_COLOR = 'rgba(34, 197, 94, 0.6)';
const WAVE_MUTED_COLOR = 'rgba(100, 100, 100, 0.3)';
const TRACK_BG = '#111';

interface AudioTimelineGeometry {
    trackX: number;
    trackY: number;
    trackW: number;
    trackH: number;
    duration: number;
    segments: { id: string; x: number; w: number; start: number; end: number }[];
}

type DragState =
    | { type: 'none' }
    | { type: 'handle-left'; segId: string; startX: number; origStart: number }
    | { type: 'handle-right'; segId: string; startX: number; origEnd: number }
    | { type: 'playhead'; startX: number; origTime: number };

export interface AudioTimelineCallbacks {
    onAudioSegmentsChanged: () => void;
    onAudioSegmentSelected: (index: number) => void;
    onPlayheadChanged: (time: number) => void;
}

export class AudioTimeline {
    private canvas: HTMLCanvasElement;
    private container: HTMLDivElement;
    private manager: AudioEditManager;
    private callbacks: AudioTimelineCallbacks;
    private geometry: AudioTimelineGeometry | null = null;
    private waveformPeaks: Float32Array | null = null;
    private playhead: number = 0;
    private hoveredHandle: string | null = null;
    private drag: DragState = { type: 'none' };
    private selectedSegmentIndex: number = -1;
    private _snapping: boolean = true;
    /** Last rendered playhead X position — used by _renderPlayheadOnly() to erase the old one */
    private _lastPlayheadX: number = -1;

    private _boundMouseDown = this._onMouseDown.bind(this);
    private _boundMouseMove = this._onMouseMove.bind(this);
    private _boundMouseUp = this._onMouseUp.bind(this);
    private _boundDblClick = this._onDoubleClick.bind(this);

    constructor(manager: AudioEditManager, callbacks: AudioTimelineCallbacks) {
        this.manager = manager;
        this.callbacks = callbacks;

        this.container = document.createElement('div');
        this.container.className = 'veditor-audio-timeline';

        this.canvas = document.createElement('canvas');
        this.canvas.style.cssText = 'width:100%;cursor:pointer;border-radius:4px;';
        this.container.appendChild(this.canvas);

        this._bindEvents();
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    /** Set waveform peak data for rendering */
    setWaveform(peaks: Float32Array): void {
        this.waveformPeaks = peaks;
        this.render();
    }

    /** Update playhead position (lightweight — only redraws the playhead line) */
    setPlayhead(time: number): void {
        this.playhead = Math.max(0, Math.min(time, this.manager.videoDuration));
        this._renderPlayheadOnly();
    }

    /** Set the selected segment index */
    setSelectedIndex(index: number): void {
        this.selectedSegmentIndex = index;
        this.render();
    }

    /** Set snapping enabled/disabled */
    setSnapping(enabled: boolean): void {
        this._snapping = enabled;
    }

    /** Full render pass */
    render(): void {
        const dur = this.manager.videoDuration;
        if (dur <= 0) return;

        const rect = this.canvas.parentElement?.getBoundingClientRect();
        const w = rect ? rect.width : 400;
        const h = TRACK_H + TRACK_PAD * 2;

        const dpr = window.devicePixelRatio || 1;
        this.canvas.width = w * dpr;
        this.canvas.height = h * dpr;
        this.canvas.style.height = `${h}px`;

        const ctx = this.canvas.getContext('2d');
        if (!ctx) return;
        ctx.scale(dpr, dpr);

        const trackX = TRACK_PAD;
        const trackY = TRACK_PAD;
        const trackW = w - TRACK_PAD * 2;
        const trackH = TRACK_H;

        // Background
        ctx.fillStyle = TRACK_BG;
        ctx.fillRect(0, 0, w, h);

        // Excluded background (full track)
        ctx.fillStyle = EXCLUDED_COLOR;
        ctx.fillRect(trackX, trackY, trackW, trackH);

        // Excluded stripes
        ctx.save();
        ctx.beginPath();
        ctx.rect(trackX, trackY, trackW, trackH);
        ctx.clip();
        ctx.strokeStyle = EXCLUDED_STRIPE;
        ctx.lineWidth = 1;
        for (let x = -h; x < w + h; x += 8) {
            ctx.beginPath();
            ctx.moveTo(x, trackY);
            ctx.lineTo(x + h, trackY + trackH);
            ctx.stroke();
        }
        ctx.restore();

        // Build geometry
        const segGeos: AudioTimelineGeometry['segments'] = [];

        // Draw segments
        for (let i = 0; i < this.manager.segments.length; i++) {
            const seg = this.manager.segments[i];
            const x = trackX + (seg.start / dur) * trackW;
            const segW = ((seg.end - seg.start) / dur) * trackW;
            const isMuted = seg.muted;
            const isSelected = i === this.selectedSegmentIndex;

            // Segment fill
            ctx.fillStyle = isMuted ? SEG_MUTED_COLOR : SEG_COLOR;
            ctx.fillRect(x, trackY, segW, trackH);

            // Waveform inside this segment
            if (this.waveformPeaks) {
                this._drawWaveform(ctx, x, trackY, segW, trackH, seg, isMuted);
            }

            // Segment border
            ctx.strokeStyle = isSelected ? '#4ade80' : SEG_BORDER;
            ctx.lineWidth = isSelected ? 2 : 1;
            ctx.strokeRect(x, trackY, segW, trackH);

            // Volume indicator (small label)
            if (segW > 50) {
                const volLabel = isMuted ? 'MUTED' : `${Math.round(seg.volume * 100)}%`;
                ctx.font = '9px monospace';
                ctx.fillStyle = isMuted ? '#888' : '#ccc';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'bottom';
                ctx.fillText(volLabel, x + segW / 2, trackY + trackH - 3);
            }

            // Trim handles
            const isHoveredL = this.hoveredHandle === `${seg.id}-left`;
            const isHoveredR = this.hoveredHandle === `${seg.id}-right`;

            ctx.fillStyle = isHoveredL ? HANDLE_HOVER : HANDLE_COLOR;
            ctx.fillRect(x, trackY, HANDLE_W, trackH);
            ctx.fillStyle = '#333';
            ctx.fillRect(x + 3, trackY + trackH / 2 - 6, 2, 12);

            ctx.fillStyle = isHoveredR ? HANDLE_HOVER : HANDLE_COLOR;
            ctx.fillRect(x + segW - HANDLE_W, trackY, HANDLE_W, trackH);
            ctx.fillStyle = '#333';
            ctx.fillRect(x + segW - HANDLE_W + 3, trackY + trackH / 2 - 6, 2, 12);

            segGeos.push({ id: seg.id, x, w: segW, start: seg.start, end: seg.end });
        }

        this.geometry = { trackX, trackY, trackW, trackH, duration: dur, segments: segGeos };

        // Playhead
        const phX = trackX + (this.playhead / dur) * trackW;
        this._lastPlayheadX = phX;
        ctx.fillStyle = PLAYHEAD_COLOR;
        ctx.fillRect(phX - PLAYHEAD_W / 2, trackY - 2, PLAYHEAD_W, trackH + 4);
    }

    /**
     * Lightweight playhead-only redraw.
     * Erases the old playhead stripe and draws the new one without
     * recomputing segments, waveforms, or stripe patterns.
     * Falls back to a full render() if geometry isn't available yet.
     */
    private _renderPlayheadOnly(): void {
        if (!this.geometry) {
            // First render hasn't happened yet — do a full pass
            this.render();
            return;
        }

        const ctx = this.canvas.getContext('2d');
        if (!ctx) return;

        const dpr = window.devicePixelRatio || 1;
        const { trackX, trackY, trackW, trackH, duration } = this.geometry;
        if (duration <= 0) return;

        ctx.save();
        ctx.scale(dpr, dpr);

        // Erase old playhead (restore to track background)
        if (this._lastPlayheadX >= 0) {
            const eraseX = this._lastPlayheadX - PLAYHEAD_W / 2 - 1;
            const eraseW = PLAYHEAD_W + 2;
            const eraseY = trackY - 2;
            // Redraw just the erased column by doing a full render.
            // For maximum efficiency we could cache a bitmap strip,
            // but the simplest correct approach is to clear and re-render
            // this narrow column. Since the full render is only ~10 rects
            // wide, a targeted clip + full render is still far cheaper
            // than an unconstrained full render.
            ctx.beginPath();
            ctx.rect(eraseX, eraseY, eraseW, trackH + 4);
            ctx.clip();

            // Restore track background under playhead
            ctx.fillStyle = TRACK_BG;
            ctx.fillRect(eraseX, 0, eraseW, trackY + trackH + TRACK_PAD);
            ctx.fillStyle = EXCLUDED_COLOR;
            ctx.fillRect(eraseX, trackY, eraseW, trackH);

            // Excluded stripes (same pattern as render())
            const h = trackH + TRACK_PAD * 2;
            ctx.strokeStyle = EXCLUDED_STRIPE;
            ctx.lineWidth = 1;
            // Clamp to stripes that actually intersect the narrow erase column
            const stripeStart = Math.floor((eraseX - h) / 8) * 8;
            for (let sx = stripeStart; sx < eraseX + eraseW; sx += 8) {
                ctx.beginPath();
                ctx.moveTo(sx, trackY);
                ctx.lineTo(sx + h, trackY + trackH);
                ctx.stroke();
            }

            // Redraw any segment fill + waveform that overlaps this column.
            // _drawWaveform also paints fade overlays; the outer clip constrains
            // all drawing to the narrow erase strip.  Segment borders, volume
            // labels, and trim handles are omitted — invisible at 4 px.
            for (const segGeo of this.geometry.segments) {
                if (eraseX < segGeo.x + segGeo.w && eraseX + eraseW > segGeo.x) {
                    const seg = this.manager.segments.find(s => s.id === segGeo.id);
                    if (seg) {
                        ctx.fillStyle = seg.muted ? SEG_MUTED_COLOR : SEG_COLOR;
                        ctx.fillRect(segGeo.x, trackY, segGeo.w, trackH);
                        if (this.waveformPeaks) {
                            this._drawWaveform(ctx, segGeo.x, trackY, segGeo.w, trackH, seg, seg.muted);
                        }
                    }
                }
            }

            ctx.restore();
            ctx.save();
            ctx.scale(dpr, dpr);
        }

        // Draw new playhead
        const phX = trackX + (this.playhead / duration) * trackW;
        this._lastPlayheadX = phX;
        ctx.fillStyle = PLAYHEAD_COLOR;
        ctx.fillRect(phX - PLAYHEAD_W / 2, trackY - 2, PLAYHEAD_W, trackH + 4);

        ctx.restore();
    }

    destroy(): void {
        this.canvas.removeEventListener('mousedown', this._boundMouseDown);
        this.canvas.removeEventListener('mousemove', this._boundMouseMove);
        document.removeEventListener('mouseup', this._boundMouseUp);
        this.canvas.removeEventListener('dblclick', this._boundDblClick);
    }

    // ── Waveform rendering ──────────────────────────────────────

    private _drawWaveform(
        ctx: CanvasRenderingContext2D,
        segX: number,
        segY: number,
        segW: number,
        segH: number,
        seg: AudioSegment,
        isMuted: boolean,
    ): void {
        if (!this.waveformPeaks) return;
        const dur = this.manager.videoDuration;
        const peakCount = this.waveformPeaks.length;

        // Map segment time range to peak indices
        const startBin = Math.floor((seg.start / dur) * peakCount);
        const endBin = Math.ceil((seg.end / dur) * peakCount);
        const binRange = endBin - startBin;
        if (binRange <= 0) return;

        const segDur = seg.end - seg.start;

        ctx.save();
        ctx.beginPath();
        ctx.rect(segX, segY, segW, segH);
        ctx.clip();

        ctx.fillStyle = isMuted ? WAVE_MUTED_COLOR : WAVE_COLOR;
        const centerY = segY + segH / 2;
        const maxAmplitude = segH * 0.4;

        const barWidth = Math.max(1, segW / binRange);
        for (let i = 0; i < binRange; i++) {
            const peakIdx = startBin + i;
            if (peakIdx >= peakCount) break;

            // Calculate fade envelope at this bar's time position
            const barTime = (i / binRange) * segDur; // time within segment
            let fadeFactor = 1.0;

            // Fade in
            if (seg.fadeIn > 0 && barTime < seg.fadeIn) {
                fadeFactor *= barTime / seg.fadeIn;
            }

            // Fade out
            const timeFromEnd = segDur - barTime;
            if (seg.fadeOut > 0 && timeFromEnd < seg.fadeOut) {
                fadeFactor *= timeFromEnd / seg.fadeOut;
            }

            const peak = this.waveformPeaks[peakIdx] * (isMuted ? 0.3 : seg.volume) * fadeFactor;
            const barH = Math.max(1, peak * maxAmplitude);
            const barX = segX + (i / binRange) * segW;

            ctx.fillRect(barX, centerY - barH, barWidth, barH * 2);
        }

        // Draw fade region overlays for visual clarity
        if (seg.fadeIn > 0 && !isMuted) {
            const fadeInW = (seg.fadeIn / segDur) * segW;
            const grad = ctx.createLinearGradient(segX, 0, segX + fadeInW, 0);
            grad.addColorStop(0, 'rgba(34, 197, 94, 0.25)');
            grad.addColorStop(1, 'rgba(34, 197, 94, 0)');
            ctx.fillStyle = grad;
            ctx.fillRect(segX, segY, fadeInW, segH);

            // Fade-in marker line
            ctx.strokeStyle = 'rgba(34, 197, 94, 0.6)';
            ctx.lineWidth = 1;
            ctx.setLineDash([3, 3]);
            ctx.beginPath();
            ctx.moveTo(segX + fadeInW, segY);
            ctx.lineTo(segX + fadeInW, segY + segH);
            ctx.stroke();
            ctx.setLineDash([]);
        }

        if (seg.fadeOut > 0 && !isMuted) {
            const fadeOutW = (seg.fadeOut / segDur) * segW;
            const fadeOutX = segX + segW - fadeOutW;
            const grad = ctx.createLinearGradient(fadeOutX, 0, segX + segW, 0);
            grad.addColorStop(0, 'rgba(34, 197, 94, 0)');
            grad.addColorStop(1, 'rgba(34, 197, 94, 0.25)');
            ctx.fillStyle = grad;
            ctx.fillRect(fadeOutX, segY, fadeOutW, segH);

            // Fade-out marker line
            ctx.strokeStyle = 'rgba(34, 197, 94, 0.6)';
            ctx.lineWidth = 1;
            ctx.setLineDash([3, 3]);
            ctx.beginPath();
            ctx.moveTo(fadeOutX, segY);
            ctx.lineTo(fadeOutX, segY + segH);
            ctx.stroke();
            ctx.setLineDash([]);
        }

        ctx.restore();
    }

    // ── Events ──────────────────────────────────────────────────

    private _bindEvents(): void {
        this.canvas.addEventListener('mousedown', this._boundMouseDown);
        this.canvas.addEventListener('mousemove', this._boundMouseMove);
        document.addEventListener('mouseup', this._boundMouseUp);
        this.canvas.addEventListener('dblclick', this._boundDblClick);
    }

    private _canvasToTrack(clientX: number): number {
        const rect = this.canvas.getBoundingClientRect();
        return clientX - rect.left;
    }

    private _xToTime(x: number): number {
        if (!this.geometry) return 0;
        const { trackX, trackW, duration } = this.geometry;
        return Math.max(0, Math.min(duration, ((x - trackX) / trackW) * duration));
    }

    private _hitTest(cx: number, cy: number): { type: 'handle-left' | 'handle-right' | 'playhead' | 'track' | 'none'; segId?: string; segIndex?: number } {
        if (!this.geometry) return { type: 'none' };
        const { trackX, trackW, trackY, trackH, duration } = this.geometry;

        if (cy < trackY - 4 || cy > trackY + trackH + 4) return { type: 'none' };

        // Check playhead
        const phX = trackX + (this.playhead / duration) * trackW;
        if (Math.abs(cx - phX) < 6) return { type: 'playhead' };

        for (let i = 0; i < this.geometry.segments.length; i++) {
            const seg = this.geometry.segments[i];

            if (cx >= seg.x - 2 && cx <= seg.x + HANDLE_W + 2 && cy >= trackY && cy <= trackY + trackH) {
                return { type: 'handle-left', segId: seg.id, segIndex: i };
            }
            if (cx >= seg.x + seg.w - HANDLE_W - 2 && cx <= seg.x + seg.w + 2 && cy >= trackY && cy <= trackY + trackH) {
                return { type: 'handle-right', segId: seg.id, segIndex: i };
            }
        }

        // Check which segment was clicked
        for (let i = 0; i < this.geometry.segments.length; i++) {
            const seg = this.geometry.segments[i];
            if (cx >= seg.x && cx <= seg.x + seg.w) {
                return { type: 'track', segIndex: i };
            }
        }

        return { type: 'track' };
    }

    private _onMouseDown(e: MouseEvent): void {
        e.stopPropagation();
        const cx = this._canvasToTrack(e.clientX);
        const rect = this.canvas.getBoundingClientRect();
        const cy = e.clientY - rect.top;
        const hit = this._hitTest(cx, cy);

        if (hit.type === 'handle-left' && hit.segId) {
            const seg = this.manager.segments.find(s => s.id === hit.segId);
            if (seg) {
                this.drag = { type: 'handle-left', segId: hit.segId, startX: e.clientX, origStart: seg.start };
            }
        } else if (hit.type === 'handle-right' && hit.segId) {
            const seg = this.manager.segments.find(s => s.id === hit.segId);
            if (seg) {
                this.drag = { type: 'handle-right', segId: hit.segId, startX: e.clientX, origEnd: seg.end };
            }
        } else if (hit.type === 'playhead') {
            this.drag = { type: 'playhead', startX: e.clientX, origTime: this.playhead };
        } else if (hit.type === 'track') {
            if (hit.segIndex !== undefined) {
                this.selectedSegmentIndex = hit.segIndex;
                this.callbacks.onAudioSegmentSelected(hit.segIndex);
            }
            // Click on track → move playhead
            const time = this._xToTime(cx);
            this.callbacks.onPlayheadChanged(time);
            this.render();
        }
    }

    private _onMouseMove(e: MouseEvent): void {
        const cx = this._canvasToTrack(e.clientX);
        const rect = this.canvas.getBoundingClientRect();
        const cy = e.clientY - rect.top;

        if (this.drag.type === 'none') {
            const hit = this._hitTest(cx, cy);
            if (hit.type === 'handle-left' || hit.type === 'handle-right') {
                this.canvas.style.cursor = 'ew-resize';
                this.hoveredHandle = hit.segId ? `${hit.segId}-${hit.type === 'handle-left' ? 'left' : 'right'}` : null;
            } else if (hit.type === 'playhead') {
                this.canvas.style.cursor = 'col-resize';
                this.hoveredHandle = null;
            } else {
                this.canvas.style.cursor = 'pointer';
                this.hoveredHandle = null;
            }
            this.render();
            return;
        }

        if (!this.geometry) return;
        const { trackW, duration } = this.geometry;
        const drag = this.drag;
        const dx = e.clientX - drag.startX;
        const dt = (dx / trackW) * duration;

        if (drag.type === 'handle-left') {
            let newStart = Math.max(0, drag.origStart + dt);
            if (this._snapping) {
                const edges = collectEdges(this.manager.segments, drag.segId, 'start');
                const snap = snapToEdges(newStart, edges, 8, trackW, duration);
                newStart = snap.time;
            }
            this.manager.updateSegment(drag.segId, newStart, this.manager.segments.find(s => s.id === drag.segId)!.end);
            this.render();
        } else if (drag.type === 'handle-right') {
            let newEnd = Math.min(duration, drag.origEnd + dt);
            if (this._snapping) {
                const edges = collectEdges(this.manager.segments, drag.segId, 'end');
                const snap = snapToEdges(newEnd, edges, 8, trackW, duration);
                newEnd = snap.time;
            }
            this.manager.updateSegment(drag.segId, this.manager.segments.find(s => s.id === drag.segId)!.start, newEnd);
            this.render();
        } else if (drag.type === 'playhead') {
            this.playhead = Math.max(0, Math.min(duration, drag.origTime + dt));
            this.callbacks.onPlayheadChanged(this.playhead);
            this._renderPlayheadOnly();
        }
    }

    private _onMouseUp(): void {
        if (this.drag.type !== 'none') {
            if (this.drag.type === 'handle-left' || this.drag.type === 'handle-right') {
                this.callbacks.onAudioSegmentsChanged();
            }
            this.drag = { type: 'none' };
        }
    }

    private _onDoubleClick(e: MouseEvent): void {
        e.stopPropagation();
        const cx = this._canvasToTrack(e.clientX);
        const time = this._xToTime(cx);
        if (this.manager.splitAt(time)) {
            this.callbacks.onAudioSegmentsChanged();
            this.render();
        }
    }
}
