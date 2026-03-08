/**
 * MonitorCanvas — infinite canvas wrapper for the video preview.
 *
 * Wraps the video element in a zoomable/pannable container using CSS
 * transforms. Resolution is never distorted — only the viewport
 * transform changes. Inspired by PureRef and DaVinci Resolve's viewer.
 *
 * Controls:
 *   Scroll wheel        → zoom (centered on cursor)
 *   Middle-mouse drag   → pan
 *   Alt + left-drag     → pan
 *   Double-click        → Fit to View
 *   F key               → Fit to View
 *   1 key               → 100% (1:1 pixel)
 *   Zoom toolbar        → −, %, +, Fit buttons
 */

import { iconZoomIn, iconZoomOut, iconMaximize } from './icons';

export interface MonitorCanvasCallbacks {
    onZoomChanged?: (zoomPercent: number) => void;
}

const MIN_ZOOM = 0.10;
const MAX_ZOOM = 8.00;
const ZOOM_STEP = 1.15; // 15% per scroll tick

export class MonitorCanvas {
    private container: HTMLDivElement;
    private viewport: HTMLDivElement;
    private content: HTMLDivElement;
    private zoomBar: HTMLDivElement;
    private zoomLabel: HTMLSpanElement;
    private callbacks: MonitorCanvasCallbacks;

    private _zoom = 1.0;
    private _panX = 0;
    private _panY = 0;
    private _isPanning = false;
    private _panStartX = 0;
    private _panStartY = 0;
    private _panStartPanX = 0;
    private _panStartPanY = 0;

    constructor(video: HTMLVideoElement, callbacks: MonitorCanvasCallbacks = {}) {
        this.callbacks = callbacks;

        // ── Container (fills grid-area: monitor) ──
        this.container = document.createElement('div');
        this.container.className = 'veditor-monitor-canvas';
        this.container.setAttribute('data-tool-id', 'veditor-monitor-canvas');
        this.container.setAttribute('aria-label', 'Video preview canvas — scroll to zoom, middle-drag to pan');

        // ── Viewport (clips overflow, captures events) ──
        this.viewport = document.createElement('div');
        this.viewport.className = 'veditor-monitor-viewport';

        // ── Content (transformed: scale + translate) ──
        this.content = document.createElement('div');
        this.content.className = 'veditor-monitor-content';
        this.content.appendChild(video);

        this.viewport.appendChild(this.content);

        // ── Zoom toolbar ──
        this.zoomBar = document.createElement('div');
        this.zoomBar.className = 'veditor-zoom-bar';
        this.zoomBar.setAttribute('data-tool-id', 'veditor-zoom-bar');
        this.zoomBar.setAttribute('aria-label', 'Zoom controls');

        const zoomOutBtn = this._makeZoomBtn(
            iconZoomOut, 'Zoom Out', 'veditor-zoom-out',
            () => this.zoomBy(1 / ZOOM_STEP),
        );

        this.zoomLabel = document.createElement('span');
        this.zoomLabel.className = 'veditor-zoom-label';
        this.zoomLabel.textContent = '100%';
        this.zoomLabel.setAttribute('data-tool-id', 'veditor-zoom-level');
        this.zoomLabel.setAttribute('aria-label', 'Current zoom level');
        this.zoomLabel.title = 'Current zoom level (click for 100%)';
        this.zoomLabel.style.cursor = 'pointer';
        this.zoomLabel.addEventListener('click', () => this.setZoom(1.0));

        const zoomInBtn = this._makeZoomBtn(
            iconZoomIn, 'Zoom In', 'veditor-zoom-in',
            () => this.zoomBy(ZOOM_STEP),
        );

        const fitBtn = this._makeZoomBtn(
            iconMaximize, 'Fit to View (F)', 'veditor-zoom-fit',
            () => this.fitToView(),
        );

        this.zoomBar.append(zoomOutBtn, this.zoomLabel, zoomInBtn, fitBtn);

        this.container.append(this.viewport, this.zoomBar);

        // ── Events ──
        this._setupEvents();
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    get zoom(): number {
        return this._zoom;
    }

    /** Get the content div (used for mounting crop overlay) */
    get contentElement(): HTMLDivElement {
        return this.content;
    }

    // ── Public API ───────────────────────────────────────────────

    /** Set zoom level (clamped to range) */
    setZoom(level: number, centerX?: number, centerY?: number): void {
        const oldZoom = this._zoom;
        this._zoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, level));

        if (centerX !== undefined && centerY !== undefined) {
            // Zoom centered on cursor position
            const scale = this._zoom / oldZoom;
            this._panX = centerX - (centerX - this._panX) * scale;
            this._panY = centerY - (centerY - this._panY) * scale;
        }

        this._applyTransform();
        this._updateZoomLabel();
        this.callbacks.onZoomChanged?.(Math.round(this._zoom * 100));
    }

    /** Multiply current zoom by factor */
    zoomBy(factor: number, centerX?: number, centerY?: number): void {
        this.setZoom(this._zoom * factor, centerX, centerY);
    }

    /** Fit video to viewport (reset pan, calculate zoom) */
    fitToView(): void {
        const vw = this.viewport.clientWidth;
        const vh = this.viewport.clientHeight;
        const cw = this.content.scrollWidth || vw;
        const ch = this.content.scrollHeight || vh;

        if (cw === 0 || ch === 0) {
            this._zoom = 1;
            this._panX = 0;
            this._panY = 0;
        } else {
            this._zoom = Math.min(vw / cw, vh / ch, 1.0);
            this._panX = (vw - cw * this._zoom) / 2;
            this._panY = (vh - ch * this._zoom) / 2;
        }

        this._applyTransform();
        this._updateZoomLabel();
        this.callbacks.onZoomChanged?.(Math.round(this._zoom * 100));
    }

    /** Handle keyboard shortcuts — returns true if consumed */
    handleKey(key: string): boolean {
        switch (key.toLowerCase()) {
            case 'f':
                this.fitToView();
                return true;
            default:
                return false;
        }
    }

    destroy(): void {
        this.container.remove();
    }

    // ── Private ─────────────────────────────────────────────────

    private _applyTransform(): void {
        this.content.style.transform =
            `translate(${this._panX}px, ${this._panY}px) scale(${this._zoom})`;
    }

    private _updateZoomLabel(): void {
        this.zoomLabel.textContent = `${Math.round(this._zoom * 100)}%`;
    }

    private _setupEvents(): void {
        // Scroll to zoom
        this.viewport.addEventListener('wheel', (e) => {
            e.preventDefault();
            const rect = this.viewport.getBoundingClientRect();
            const cx = e.clientX - rect.left;
            const cy = e.clientY - rect.top;
            const factor = e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
            this.zoomBy(factor, cx, cy);
        }, { passive: false });

        // Double-click to fit
        this.viewport.addEventListener('dblclick', () => {
            this.fitToView();
        });

        // Middle-mouse drag or Alt+Left to pan
        this.viewport.addEventListener('pointerdown', (e) => {
            if (e.button === 1 || (e.button === 0 && e.altKey)) {
                e.preventDefault();
                this._isPanning = true;
                this._panStartX = e.clientX;
                this._panStartY = e.clientY;
                this._panStartPanX = this._panX;
                this._panStartPanY = this._panY;
                this.viewport.setPointerCapture(e.pointerId);
                this.viewport.style.cursor = 'grabbing';
            }
        });

        this.viewport.addEventListener('pointermove', (e) => {
            if (!this._isPanning) return;
            this._panX = this._panStartPanX + (e.clientX - this._panStartX);
            this._panY = this._panStartPanY + (e.clientY - this._panStartY);
            this._applyTransform();
        });

        this.viewport.addEventListener('pointerup', (e) => {
            if (this._isPanning) {
                this._isPanning = false;
                this.viewport.releasePointerCapture(e.pointerId);
                this.viewport.style.cursor = '';
            }
        });
    }

    private _makeZoomBtn(
        icon: string, label: string, toolId: string,
        onClick: () => void,
    ): HTMLButtonElement {
        const btn = document.createElement('button');
        btn.className = 'veditor-btn veditor-zoom-btn';
        btn.innerHTML = icon;
        btn.title = label;
        btn.setAttribute('data-tool-id', toolId);
        btn.setAttribute('aria-label', label);
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            onClick();
        });
        return btn;
    }
}
