/**
 * EditTimeline — canvas-based editing timeline with trim handles.
 *
 * Renders a horizontal track showing the full video duration with
 * colored segment regions, draggable trim handles, a playhead,
 * and controls for split/delete/reset.
 */
import type { EditSegment, EditTimelineGeometry } from '@ffmpega/types/loadlast';
import type { EditManager } from './EditManager';
import { fmtDuration } from '@ffmpega/shared/utils';

// ─── Constants ─────────────────────────────────────────────────────────
const TRACK_H = 48;
const TRACK_PAD = 12;
const HANDLE_W = 8;
const PLAYHEAD_W = 2;

const SEG_COLOR = 'rgba(90, 170, 200, 0.5)';
const SEG_BORDER = '#5ac';
const EXCLUDED_COLOR = 'rgba(30, 30, 30, 0.85)';
const EXCLUDED_STRIPE = 'rgba(60, 60, 60, 0.6)';
const HANDLE_COLOR = '#fff';
const HANDLE_HOVER = '#00ddff';
const PLAYHEAD_COLOR = '#ff5555';
const TRACK_BG = '#1a1a1a';

type DragState =
    | { type: 'none' }
    | { type: 'handle-left'; segId: string; startX: number; origStart: number }
    | { type: 'handle-right'; segId: string; startX: number; origEnd: number }
    | { type: 'playhead'; startX: number; origTime: number };

export interface EditTimelineCallbacks {
    onSegmentsChanged: () => void;
    onPlayheadChanged: (time: number) => void;
    onTrimHandleDrag: (time: number) => void;
    onRequestSplit: () => void;
    onDragStart?: () => void;
    onDragEnd?: () => void;
}

export class EditTimeline {
    private canvas: HTMLCanvasElement;
    private container: HTMLDivElement;
    private manager: EditManager;
    private callbacks: EditTimelineCallbacks;

    private geometry: EditTimelineGeometry | null = null;
    public playhead: number = 0;
    private hoveredHandle: string | null = null;
    private drag: DragState = { type: 'none' };

    // Bound handlers (stored so destroy() can remove the exact same reference)
    private _boundMouseDown = this._onMouseDown.bind(this);
    private _boundMouseMove = this._onMouseMove.bind(this);
    private _boundMouseUp = this._onMouseUp.bind(this);
    private _boundDblClick = this._onDoubleClick.bind(this);

    constructor(manager: EditManager, callbacks: EditTimelineCallbacks) {
        this.manager = manager;
        this.callbacks = callbacks;

        // Container
        this.container = document.createElement('div');
        this.container.className = 'll_edit_timeline';

        // Canvas
        this.canvas = document.createElement('canvas');
        this.canvas.className = 'll_edit_canvas';
        this.canvas.style.cssText = 'width:100%;cursor:pointer;border-radius:4px;';
        this.container.appendChild(this.canvas);

        this._bindEvents();
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    /** Set the playhead position */
    setPlayhead(time: number): void {
        this.playhead = Math.max(0, Math.min(time, this.manager.videoDuration));
        this.render();
    }

    /** Full render pass */
    render(): void {
        const dur = this.manager.videoDuration;
        if (dur <= 0) return;

        const rect = this.canvas.parentElement?.getBoundingClientRect();
        const w = rect ? rect.width : 400;
        const h = TRACK_H + TRACK_PAD * 2 + 24; // track + padding + labels

        // Set canvas resolution
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
        ctx.fillStyle = '#111';
        ctx.fillRect(0, 0, w, h);

        // Track background
        ctx.fillStyle = TRACK_BG;
        ctx.fillRect(trackX, trackY, trackW, trackH);
        ctx.strokeStyle = '#333';
        ctx.lineWidth = 1;
        ctx.strokeRect(trackX, trackY, trackW, trackH);

        // Build geometry for hit testing
        const segGeos: EditTimelineGeometry['segments'] = [];

        // Draw excluded regions first (full track = excluded)
        ctx.fillStyle = EXCLUDED_COLOR;
        ctx.fillRect(trackX, trackY, trackW, trackH);

        // Draw diagonal stripes on excluded regions
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

        // Draw segments (included regions)
        for (const seg of this.manager.segments) {
            const x = trackX + (seg.start / dur) * trackW;
            const segW = ((seg.end - seg.start) / dur) * trackW;

            // Segment fill
            ctx.fillStyle = SEG_COLOR;
            ctx.fillRect(x, trackY, segW, trackH);

            // Segment border
            ctx.strokeStyle = SEG_BORDER;
            ctx.lineWidth = 1.5;
            ctx.strokeRect(x, trackY, segW, trackH);

            // Duration label centered in segment
            if (segW > 40) {
                const label = fmtDuration(seg.end - seg.start);
                ctx.font = '10px monospace';
                ctx.fillStyle = '#ddd';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(label, x + segW / 2, trackY + trackH / 2);
            }

            // Trim handles
            const isHoveredL = this.hoveredHandle === `${seg.id}-left`;
            const isHoveredR = this.hoveredHandle === `${seg.id}-right`;

            // Left handle
            ctx.fillStyle = isHoveredL ? HANDLE_HOVER : HANDLE_COLOR;
            ctx.fillRect(x, trackY, HANDLE_W, trackH);
            ctx.fillStyle = '#333';
            ctx.fillRect(x + 3, trackY + trackH / 2 - 6, 2, 12);

            // Right handle
            ctx.fillStyle = isHoveredR ? HANDLE_HOVER : HANDLE_COLOR;
            ctx.fillRect(x + segW - HANDLE_W, trackY, HANDLE_W, trackH);
            ctx.fillStyle = '#333';
            ctx.fillRect(x + segW - HANDLE_W + 3, trackY + trackH / 2 - 6, 2, 12);

            segGeos.push({ id: seg.id, x, w: segW, start: seg.start, end: seg.end });
        }

        this.geometry = { trackX, trackY, trackW, trackH, duration: dur, segments: segGeos };

        // Playhead
        const phX = trackX + (this.playhead / dur) * trackW;
        ctx.fillStyle = PLAYHEAD_COLOR;
        ctx.fillRect(phX - PLAYHEAD_W / 2, trackY - 4, PLAYHEAD_W, trackH + 8);
        // Playhead triangle top
        ctx.beginPath();
        ctx.moveTo(phX - 5, trackY - 4);
        ctx.lineTo(phX + 5, trackY - 4);
        ctx.lineTo(phX, trackY + 2);
        ctx.closePath();
        ctx.fill();

        // Time labels at bottom
        ctx.font = '10px monospace';
        ctx.fillStyle = '#666';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        ctx.fillText('0:00', trackX, trackY + trackH + 4);
        ctx.textAlign = 'right';
        ctx.fillText(fmtDuration(dur), trackX + trackW, trackY + trackH + 4);
        ctx.textAlign = 'center';
        ctx.fillStyle = PLAYHEAD_COLOR;
        const phLabel = fmtDuration(this.playhead);
        ctx.fillText(phLabel, Math.max(trackX + 20, Math.min(phX, trackX + trackW - 20)), trackY + trackH + 4);

        // Output duration
        const outDur = this.manager.getOutputDuration();
        ctx.textAlign = 'center';
        ctx.fillStyle = '#5ac';
        ctx.fillText(
            `Output: ${fmtDuration(outDur)} / ${fmtDuration(dur)} (${this.manager.segments.length} segment${this.manager.segments.length !== 1 ? 's' : ''})`,
            w / 2, trackY + trackH + 14,
        );

    }

    private _bindEvents(): void {
        this.canvas.addEventListener('mousedown', this._boundMouseDown);
        this.canvas.addEventListener('mousemove', this._boundMouseMove);
        document.addEventListener('mouseup', this._boundMouseUp);
        this.canvas.addEventListener('dblclick', this._boundDblClick);
    }

    private _canvasToTrack(clientX: number, clientY: number): { x: number; y: number } {
        const rect = this.canvas.getBoundingClientRect();
        return {
            x: clientX - rect.left,
            y: clientY - rect.top,
        };
    }

    private _xToTime(x: number): number {
        if (!this.geometry) return 0;
        const { trackX, trackW, duration } = this.geometry;
        return Math.max(0, Math.min(duration, ((x - trackX) / trackW) * duration));
    }

    private _hitTest(cx: number, cy: number): { type: 'handle-left' | 'handle-right' | 'playhead' | 'track' | 'none'; segId?: string } {
        if (!this.geometry) return { type: 'none' };
        const { trackX, trackY, trackW, trackH, duration } = this.geometry;

        // Check if within track vertically
        if (cy < trackY - 6 || cy > trackY + trackH + 6) return { type: 'none' };

        // Check playhead
        const phX = trackX + (this.playhead / duration) * trackW;
        if (Math.abs(cx - phX) < 6) return { type: 'playhead' };

        // Check segment handles
        for (const seg of this.geometry.segments) {
            // Left handle
            if (cx >= seg.x - 2 && cx <= seg.x + HANDLE_W + 2 && cy >= trackY && cy <= trackY + trackH) {
                return { type: 'handle-left', segId: seg.id };
            }
            // Right handle
            if (cx >= seg.x + seg.w - HANDLE_W - 2 && cx <= seg.x + seg.w + 2 && cy >= trackY && cy <= trackY + trackH) {
                return { type: 'handle-right', segId: seg.id };
            }
        }

        // Track click
        if (cx >= trackX && cx <= trackX + trackW) {
            return { type: 'track' };
        }

        return { type: 'none' };
    }

    private _onMouseDown(e: MouseEvent): void {
        e.stopPropagation();
        const { x, y } = this._canvasToTrack(e.clientX, e.clientY);
        const hit = this._hitTest(x, y);

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
            this.callbacks.onDragStart?.();
        } else if (hit.type === 'track') {
            // Click on track → move playhead
            this.playhead = this._xToTime(x);
            this.callbacks.onPlayheadChanged(this.playhead);
            this.render();
        }
    }

    private _onMouseMove(e: MouseEvent): void {
        const { x, y } = this._canvasToTrack(e.clientX, e.clientY);

        if (this.drag.type === 'none') {
            // Update cursor for hover
            const hit = this._hitTest(x, y);
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
            const newStart = Math.max(0, drag.origStart + dt);
            const seg = this.manager.segments.find(s => s.id === drag.segId);
            if (seg) this.manager.updateSegment(drag.segId, newStart, seg.end);
            this.callbacks.onTrimHandleDrag(newStart);
            this.render();
        } else if (drag.type === 'handle-right') {
            const newEnd = Math.min(duration, drag.origEnd + dt);
            const seg = this.manager.segments.find(s => s.id === drag.segId);
            if (seg) this.manager.updateSegment(drag.segId, seg.start, newEnd);
            this.callbacks.onTrimHandleDrag(newEnd);
            this.render();
        } else if (drag.type === 'playhead') {
            this.playhead = Math.max(0, Math.min(duration, drag.origTime + dt));
            this.callbacks.onPlayheadChanged(this.playhead);
            this.render();
        }
    }

    private _onMouseUp(_e: MouseEvent): void {
        if (this.drag.type !== 'none') {
            if (this.drag.type === 'handle-left' || this.drag.type === 'handle-right') {
                this.callbacks.onSegmentsChanged();
            }
            if (this.drag.type === 'playhead') {
                this.callbacks.onDragEnd?.();
            }
            this.drag = { type: 'none' };
        }
    }

    private _onDoubleClick(e: MouseEvent): void {
        e.stopPropagation();
        const { x, y } = this._canvasToTrack(e.clientX, e.clientY);
        if (!this.geometry) return;
        const { trackY, trackH } = this.geometry;
        if (y < trackY || y > trackY + trackH) return;

        // Double-click → split at this position
        const time = this._xToTime(x);
        if (this.manager.splitAt(time)) {
            this.callbacks.onSegmentsChanged();
            this.render();
        }
    }

    /** Cleanup event listeners */
    destroy(): void {
        this.canvas.removeEventListener('mousedown', this._boundMouseDown);
        this.canvas.removeEventListener('mousemove', this._boundMouseMove);
        document.removeEventListener('mouseup', this._boundMouseUp);
        this.canvas.removeEventListener('dblclick', this._boundDblClick);
    }
}
