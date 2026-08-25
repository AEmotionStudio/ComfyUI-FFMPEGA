/**
 * KeyframeEditor — compact canvas-based keyframe lane for the tools panel.
 *
 * Renders a horizontal lane showing keyframe diamonds, connected by
 * interpolation curves. Supports:
 * - Click to add keyframe at time/value
 * - Drag diamond horizontally (time) or vertically (value)
 * - Right-click or double-click to delete keyframe
 * - Hover tooltip with value
 *
 * Designed to be embedded inside SpeedControl or AudioMixer sections.
 */

import { KeyframeTrack, Keyframe, EasingType } from './KeyframeTrack';

export interface KeyframeEditorCallbacks {
    onKeyframesChanged: () => void;
    /** Returns the current playback time for the marker line. */
    getCurrentTime?: () => number;
}

const LANE_HEIGHT = 60;
const DIAMOND_SIZE = 6;
const PADDING_X = 8;
const PADDING_Y = 8;

export class KeyframeEditor {
    private container: HTMLDivElement;
    private canvas: HTMLCanvasElement;
    private ctx: CanvasRenderingContext2D;
    private track: KeyframeTrack;
    private callbacks: KeyframeEditorCallbacks;
    private duration: number = 10;
    private dragging: number = -1;  // index of keyframe being dragged
    private hovered: number = -1;
    private _animFrame: number | null = null;

    constructor(track: KeyframeTrack, callbacks: KeyframeEditorCallbacks) {
        this.track = track;
        this.callbacks = callbacks;

        this.container = document.createElement('div');
        this.container.className = 'veditor-keyframe-editor';
        this.container.setAttribute('data-tool-id', `veditor-kf-${track.property}`);

        // Enable toggle header
        const header = document.createElement('div');
        header.className = 'veditor-kf-header';

        const label = document.createElement('span');
        label.className = 'veditor-kf-label';
        label.textContent = `${track.property.charAt(0).toUpperCase() + track.property.slice(1)} Keyframes`;

        const clearBtn = document.createElement('button');
        clearBtn.className = 'veditor-btn veditor-kf-clear-btn';
        clearBtn.textContent = 'Clear';
        clearBtn.title = 'Remove all keyframes';
        clearBtn.addEventListener('click', () => {
            this.track.clear();
            this.render();
            this.callbacks.onKeyframesChanged();
        });

        header.append(label, clearBtn);

        // Canvas
        this.canvas = document.createElement('canvas');
        this.canvas.className = 'veditor-kf-canvas';
        this.canvas.height = LANE_HEIGHT;
        this.canvas.setAttribute('aria-label', `Keyframe editor for ${track.property}`);

        this.ctx = this.canvas.getContext('2d')!;

        // Mouse events
        this.canvas.addEventListener('mousedown', (e) => this._onMouseDown(e));
        this.canvas.addEventListener('mousemove', (e) => this._onMouseMove(e));
        this.canvas.addEventListener('mouseup', () => this._onMouseUp());
        this.canvas.addEventListener('mouseleave', () => this._onMouseUp());
        this.canvas.addEventListener('dblclick', (e) => this._onDblClick(e));
        this.canvas.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            this._onDblClick(e); // right-click = delete nearest
        });

        // Info hint
        const hint = document.createElement('div');
        hint.className = 'veditor-kf-hint';
        hint.textContent = 'Click to add • Drag to move • Double-click to delete';

        this.container.append(header, this.canvas, hint);
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    /** Set the timeline duration for time→pixel mapping. */
    setDuration(d: number): void {
        this.duration = Math.max(0.1, d);
        this.render();
    }

    /** Resize canvas width and re-render. */
    resize(width?: number): void {
        const w = width ?? this.container.clientWidth;
        if (w > 0) {
            this.canvas.width = w;
            this.render();
        }
    }

    /** Re-render the keyframe lane. */
    render(): void {
        const w = this.canvas.width;
        const h = this.canvas.height;
        const ctx = this.ctx;
        if (w <= 0) return;

        ctx.clearRect(0, 0, w, h);

        const areaW = w - 2 * PADDING_X;
        const areaH = h - 2 * PADDING_Y;

        // Background
        ctx.fillStyle = 'rgba(30, 30, 44, 0.5)';
        ctx.fillRect(0, 0, w, h);

        // Grid lines (value range)
        ctx.strokeStyle = 'rgba(255,255,255,0.05)';
        ctx.lineWidth = 1;
        for (let i = 0; i <= 4; i++) {
            const y = PADDING_Y + (areaH * i) / 4;
            ctx.beginPath();
            ctx.moveTo(PADDING_X, y);
            ctx.lineTo(w - PADDING_X, y);
            ctx.stroke();
        }

        // Min/max labels
        ctx.fillStyle = 'rgba(255,255,255,0.3)';
        ctx.font = '9px monospace';
        ctx.textAlign = 'left';
        ctx.fillText(String(this.track.max), 2, PADDING_Y + 8);
        ctx.fillText(String(this.track.min), 2, h - PADDING_Y);

        // Default value line
        const defY = this._valueToY(this.track.defaultValue, areaH);
        ctx.strokeStyle = 'rgba(99,102,241,0.3)';
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(PADDING_X, defY);
        ctx.lineTo(w - PADDING_X, defY);
        ctx.stroke();
        ctx.setLineDash([]);

        // Interpolation curve
        if (this.track.keyframes.length >= 2) {
            ctx.strokeStyle = 'rgba(99,102,241,0.7)';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            const steps = Math.min(areaW, 200);
            for (let s = 0; s <= steps; s++) {
                const t = (s / steps) * this.duration;
                const val = this.track.valueAt(t);
                const x = this._timeToX(t, areaW);
                const y = this._valueToY(val, areaH);
                if (s === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            }
            ctx.stroke();
        }

        // Playhead marker
        if (this.callbacks.getCurrentTime) {
            const ct = this.callbacks.getCurrentTime();
            const px = this._timeToX(ct, areaW);
            ctx.strokeStyle = 'rgba(255,255,255,0.4)';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(px, PADDING_Y);
            ctx.lineTo(px, h - PADDING_Y);
            ctx.stroke();
        }

        // Keyframe diamonds
        for (let i = 0; i < this.track.keyframes.length; i++) {
            const kf = this.track.keyframes[i];
            const x = this._timeToX(kf.time, areaW);
            const y = this._valueToY(kf.value, areaH);

            ctx.save();
            ctx.translate(x, y);
            ctx.rotate(Math.PI / 4);

            const isHovered = i === this.hovered;
            const isDragging = i === this.dragging;
            const size = isDragging ? DIAMOND_SIZE + 2 : isHovered ? DIAMOND_SIZE + 1 : DIAMOND_SIZE;

            ctx.fillStyle = isDragging ? '#818cf8' : isHovered ? '#a5b4fc' : '#6366f1';
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 1.5;
            ctx.fillRect(-size / 2, -size / 2, size, size);
            ctx.strokeRect(-size / 2, -size / 2, size, size);

            ctx.restore();

            // Value tooltip on hover
            if (isHovered) {
                ctx.fillStyle = 'rgba(0,0,0,0.7)';
                const text = `${kf.value.toFixed(2)} @ ${kf.time.toFixed(1)}s`;
                const tw = ctx.measureText(text).width + 8;
                ctx.fillRect(x - tw / 2, y - 22, tw, 16);
                ctx.fillStyle = '#fff';
                ctx.font = '10px monospace';
                ctx.textAlign = 'center';
                ctx.fillText(text, x, y - 10);
            }
        }
    }

    /** Get the underlying track. */
    getTrack(): KeyframeTrack {
        return this.track;
    }

    destroy(): void {
        if (this._animFrame) cancelAnimationFrame(this._animFrame);
        this.container.remove();
    }

    // ── Private ──────────────────────────────────────────────────

    private _timeToX(t: number, areaW: number): number {
        return PADDING_X + (t / this.duration) * areaW;
    }

    private _xToTime(x: number, areaW: number): number {
        return Math.max(0, Math.min(this.duration, ((x - PADDING_X) / areaW) * this.duration));
    }

    private _valueToY(v: number, areaH: number): number {
        const norm = (v - this.track.min) / (this.track.max - this.track.min);
        return PADDING_Y + (1 - norm) * areaH;  // Y is inverted
    }

    private _yToValue(y: number, areaH: number): number {
        const norm = 1 - (y - PADDING_Y) / areaH;
        return this.track.min + norm * (this.track.max - this.track.min);
    }

    private _hitTest(mx: number, my: number): number {
        const areaW = this.canvas.width - 2 * PADDING_X;
        const areaH = this.canvas.height - 2 * PADDING_Y;
        for (let i = 0; i < this.track.keyframes.length; i++) {
            const kf = this.track.keyframes[i];
            const x = this._timeToX(kf.time, areaW);
            const y = this._valueToY(kf.value, areaH);
            const dist = Math.sqrt((mx - x) ** 2 + (my - y) ** 2);
            if (dist <= DIAMOND_SIZE + 4) return i;
        }
        return -1;
    }

    private _onMouseDown(e: MouseEvent): void {
        const rect = this.canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const hit = this._hitTest(mx, my);

        if (hit >= 0) {
            // Start dragging existing keyframe
            this.dragging = hit;
        } else {
            // Add new keyframe at click position
            const areaW = this.canvas.width - 2 * PADDING_X;
            const areaH = this.canvas.height - 2 * PADDING_Y;
            const t = this._xToTime(mx, areaW);
            const v = this._yToValue(my, areaH);
            this.track.addKeyframe(t, v);
            this.render();
            this.callbacks.onKeyframesChanged();
        }
    }

    private _onMouseMove(e: MouseEvent): void {
        const rect = this.canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const areaW = this.canvas.width - 2 * PADDING_X;
        const areaH = this.canvas.height - 2 * PADDING_Y;

        if (this.dragging >= 0) {
            // Move keyframe
            const kf = this.track.keyframes[this.dragging];
            if (kf) {
                kf.time = this._xToTime(mx, areaW);
                kf.value = Math.max(
                    this.track.min,
                    Math.min(this.track.max, this._yToValue(my, areaH)),
                );
                this.render();
            }
        } else {
            // Hover highlight
            const hit = this._hitTest(mx, my);
            if (hit !== this.hovered) {
                this.hovered = hit;
                this.canvas.style.cursor = hit >= 0 ? 'pointer' : 'crosshair';
                this.render();
            }
        }
    }

    private _onMouseUp(): void {
        if (this.dragging >= 0) {
            this.dragging = -1;
            this.callbacks.onKeyframesChanged();
            this.render();
        }
    }

    private _onDblClick(e: MouseEvent): void {
        const rect = this.canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const hit = this._hitTest(mx, my);

        if (hit >= 0) {
            this.track.removeKeyframe(hit);
            this.hovered = -1;
            this.render();
            this.callbacks.onKeyframesChanged();
        }
    }
}
