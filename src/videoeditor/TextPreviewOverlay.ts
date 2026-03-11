/**
 * TextPreviewOverlay — live text rendering on the video monitor with
 * interactive drag-to-position support.
 *
 * Renders each TextOverlay as a styled HTML div overlaid on the video
 * inside MonitorCanvas's content element. Scales with zoom/pan
 * automatically since it's positioned within the transform chain.
 *
 * Drag behaviour: each text element is draggable. Dragging converts
 * preset positions to pixel coords in video space, same coordinate
 * system as CropOverlay.
 */

import { TextOverlay } from './TextOverlayPanel';

export interface TextPreviewCallbacks {
    /** Called when user drags a text to a new position */
    onTextDragged: (index: number, x: string, y: string) => void;
    /** Called when user selects a text overlay on the monitor */
    onTextSelected: (index: number) => void;
}

export class TextPreviewOverlay {
    private container: HTMLDivElement;
    private callbacks: TextPreviewCallbacks;
    private videoWidth: number = 0;
    private videoHeight: number = 0;
    private overlays: TextOverlay[] = [];
    private selectedIndex: number = -1;

    // Drag state
    private _dragIndex: number = -1;
    private _dragStartX: number = 0;
    private _dragStartY: number = 0;
    private _dragOrigX: number = 0;
    private _dragOrigY: number = 0;

    // Bound handlers (stored so destroy() can remove the exact same reference)
    private _boundPointerMove = (e: PointerEvent) => this._onPointerMove(e);
    private _boundPointerUp = () => this._onPointerUp();
    private _listenersAttached = false;

    constructor(callbacks: TextPreviewCallbacks) {
        this.callbacks = callbacks;

        this.container = document.createElement('div');
        this.container.className = 'veditor-text-preview-overlay';
        this.container.style.position = 'absolute';
        this.container.style.top = '0';
        this.container.style.left = '0';
        this.container.style.width = '100%';
        this.container.style.height = '100%';
        this.container.style.pointerEvents = 'none';
        this.container.style.overflow = 'hidden';
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    setVideoDimensions(width: number, height: number): void {
        this.videoWidth = width;
        this.videoHeight = height;
        this.container.style.width = `${width}px`;
        this.container.style.height = `${height}px`;
    }

    setSelectedIndex(index: number): void {
        this.selectedIndex = index;
        this._updateSelection();
    }

    /**
     * Refresh the overlay rendering.
     * @param overlays Current overlay data
     * @param currentTime Current video time (for time-gating)
     */
    refresh(overlays: TextOverlay[], currentTime: number): void {
        this.overlays = overlays;
        this.container.innerHTML = '';

        for (let i = 0; i < overlays.length; i++) {
            const ov = overlays[i];

            // Time-gating: hide if outside time range
            if (ov.start_time !== null && currentTime < ov.start_time) continue;
            if (ov.end_time !== null && currentTime > ov.end_time) continue;

            const el = this._createTextElement(ov, i);
            this.container.appendChild(el);
        }
    }

    /** Hide overlay and detach global drag listeners */
    hide(): void {
        this.container.style.display = 'none';
        this.container.innerHTML = '';
        this._detachListeners();
    }

    /** Show overlay and attach global drag listeners */
    show(): void {
        this.container.style.display = '';
        this._attachListeners();
    }

    /** Final teardown — removes event listeners and detaches from DOM */
    destroy(): void {
        this._detachListeners();
        this.container.remove();
    }

    private _attachListeners(): void {
        if (this._listenersAttached) return;
        document.addEventListener('pointermove', this._boundPointerMove);
        document.addEventListener('pointerup', this._boundPointerUp);
        this._listenersAttached = true;
    }

    private _detachListeners(): void {
        if (!this._listenersAttached) return;
        document.removeEventListener('pointermove', this._boundPointerMove);
        document.removeEventListener('pointerup', this._boundPointerUp);
        this._listenersAttached = false;
    }

    // ── Private ──────────────────────────────────────────────────

    private _createTextElement(ov: TextOverlay, index: number): HTMLDivElement {
        const el = document.createElement('div');
        el.className = 'veditor-text-preview-item';
        el.setAttribute('data-text-index', String(index));
        el.style.pointerEvents = 'auto';
        el.style.cursor = 'move';
        el.style.position = 'absolute';
        el.style.userSelect = 'none';
        el.style.whiteSpace = 'pre-wrap';
        el.style.maxWidth = '90%';

        // Text content
        el.textContent = ov.text;

        // Font styling
        el.style.fontFamily = ov.font || 'sans-serif';
        el.style.fontSize = `${ov.font_size}px`;
        el.style.color = ov.color;
        el.style.fontWeight = ov.bold ? 'bold' : 'normal';
        el.style.fontStyle = ov.italic ? 'italic' : 'normal';
        el.style.textAlign = ov.alignment || 'center';
        el.style.lineHeight = '1.2';

        // Background
        if (ov.backgroundColor) {
            const bgOpacity = Math.round((ov.backgroundOpacity ?? 0.6) * 255);
            const hex = bgOpacity.toString(16).padStart(2, '0');
            el.style.backgroundColor = `${ov.backgroundColor}${hex}`;
            el.style.padding = '4px 8px';
            el.style.borderRadius = '4px';
        }

        // Outline (text-shadow based)
        if (ov.outlineColor && ov.outlineWidth > 0) {
            const ow = ov.outlineWidth;
            const oc = ov.outlineColor;
            el.style.textShadow = [
                `${ow}px ${ow}px 0 ${oc}`,
                `${-ow}px ${ow}px 0 ${oc}`,
                `${ow}px ${-ow}px 0 ${oc}`,
                `${-ow}px ${-ow}px 0 ${oc}`,
                `0 ${ow}px 0 ${oc}`,
                `0 ${-ow}px 0 ${oc}`,
                `${ow}px 0 0 ${oc}`,
                `${-ow}px 0 0 ${oc}`,
            ].join(', ');
        }

        // Position
        this._applyPosition(el, ov);

        // Selected state
        if (index === this.selectedIndex) {
            el.style.outline = '2px solid #6366f1';
            el.style.outlineOffset = '4px';
        }

        // Drag start
        el.addEventListener('pointerdown', (e) => {
            e.preventDefault();
            e.stopPropagation();
            this._dragIndex = index;
            this._dragStartX = e.clientX;
            this._dragStartY = e.clientY;

            // Resolve current pixel position for drag origin
            const rect = el.getBoundingClientRect();
            const containerRect = this.container.getBoundingClientRect();
            const scaleX = this.videoWidth / containerRect.width;
            const scaleY = this.videoHeight / containerRect.height;
            this._dragOrigX = (rect.left - containerRect.left) * scaleX;
            this._dragOrigY = (rect.top - containerRect.top) * scaleY;

            this.selectedIndex = index;
            this.callbacks.onTextSelected(index);
            this._updateSelection();
        });

        return el;
    }

    private _applyPosition(el: HTMLDivElement, ov: TextOverlay): void {
        const x = ov.x;
        const y = ov.y;

        // Horizontal
        if (x === 'center') {
            el.style.left = '50%';
            el.style.transform = 'translateX(-50%)';
        } else if (x === 'left') {
            el.style.left = '5%';
            el.style.transform = '';
        } else if (x === 'right') {
            el.style.right = '5%';
            el.style.transform = '';
        } else if (x.endsWith('%')) {
            el.style.left = x;
            el.style.transform = 'translateX(-50%)';
        } else {
            // Pixel value
            const px = parseFloat(x);
            if (!isNaN(px)) {
                el.style.left = `${(px / this.videoWidth) * 100}%`;
                el.style.transform = '';
            }
        }

        // Vertical
        if (y === 'center') {
            el.style.top = '50%';
            el.style.transform = (el.style.transform || '') +
                (el.style.transform ? ' translateY(-50%)' : 'translateY(-50%)');
        } else if (y === 'top') {
            el.style.top = '5%';
        } else if (y === 'bottom') {
            el.style.bottom = '5%';
        } else if (y.endsWith('%')) {
            el.style.top = y;
        } else {
            // Pixel value
            const px = parseFloat(y);
            if (!isNaN(px)) {
                el.style.top = `${(px / this.videoHeight) * 100}%`;
            }
        }
    }

    private _onPointerMove(e: PointerEvent): void {
        if (this._dragIndex < 0) return;

        const containerRect = this.container.getBoundingClientRect();
        const scaleX = this.videoWidth / containerRect.width;
        const scaleY = this.videoHeight / containerRect.height;

        const dx = (e.clientX - this._dragStartX) * scaleX;
        const dy = (e.clientY - this._dragStartY) * scaleY;

        let newX = Math.round(this._dragOrigX + dx);
        let newY = Math.round(this._dragOrigY + dy);

        // Clamp to video bounds
        newX = Math.max(0, Math.min(this.videoWidth - 20, newX));
        newY = Math.max(0, Math.min(this.videoHeight - 20, newY));

        this.callbacks.onTextDragged(this._dragIndex, String(newX), String(newY));
    }

    private _onPointerUp(): void {
        this._dragIndex = -1;
    }

    private _updateSelection(): void {
        const items = this.container.querySelectorAll('.veditor-text-preview-item');
        items.forEach((item, i) => {
            const el = item as HTMLDivElement;
            if (i === this.selectedIndex) {
                el.style.outline = '2px solid #6366f1';
                el.style.outlineOffset = '4px';
            } else {
                el.style.outline = '';
                el.style.outlineOffset = '';
            }
        });
    }
}
