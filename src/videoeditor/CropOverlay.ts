/**
 * CropOverlay — interactive crop rectangle on the video preview.
 *
 * Draggable corners/edges, aspect ratio lock (Shift), presets,
 * rule-of-thirds grid, numeric input fields, flip aspect, and
 * output resolution preview.
 */

import { iconCrop, iconFlip, iconReset } from './icons';

export interface CropRect {
    x: number;
    y: number;
    w: number;
    h: number;
}

export interface CropOverlayCallbacks {
    onCropChanged: (rect: CropRect | null) => void;
}

type AspectPreset = '16:9' | '9:16' | '4:3' | '1:1' | 'free';

const HANDLE_SIZE = 10;

export class CropOverlay {
    private canvasWrapper: HTMLDivElement;
    private canvas: HTMLCanvasElement;
    private controls: HTMLDivElement;
    private callbacks: CropOverlayCallbacks;
    private rect: CropRect | null = null;
    private videoWidth: number = 0;
    private videoHeight: number = 0;
    private aspectPreset: AspectPreset = 'free';
    private isDragging: boolean = false;
    private dragType: string = 'none';
    private dragStart: { x: number; y: number } = { x: 0, y: 0 };
    private origRect: CropRect = { x: 0, y: 0, w: 0, h: 0 };
    private enabled: boolean = false;

    // Numeric input fields
    private inputX: HTMLInputElement;
    private inputY: HTMLInputElement;
    private inputW: HTMLInputElement;
    private inputH: HTMLInputElement;
    private outputLabel: HTMLSpanElement;

    constructor(callbacks: CropOverlayCallbacks) {
        this.callbacks = callbacks;

        this.canvasWrapper = document.createElement('div');
        this.canvasWrapper.className = 'veditor-crop-canvas-wrap';
        this.canvasWrapper.style.pointerEvents = 'none';
        this.canvasWrapper.style.position = 'absolute';
        this.canvasWrapper.style.top = '0';
        this.canvasWrapper.style.left = '0';
        this.canvasWrapper.style.width = '100%';
        this.canvasWrapper.style.height = '100%';

        this.canvas = document.createElement('canvas');
        this.canvas.className = 'veditor-crop-canvas';
        this.canvas.style.pointerEvents = 'auto';
        this.canvas.style.width = '100%';
        this.canvas.style.height = '100%';
        this.canvasWrapper.appendChild(this.canvas);

        // Controls
        this.controls = document.createElement('div');
        this.controls.className = 'veditor-crop-controls';
        this.controls.setAttribute('data-tool-id', 'veditor-crop-controls');

        // ── Toggle & Presets Section ──
        const toggleSection = this._makeSection('Crop');

        const toggleRow = document.createElement('div');
        toggleRow.className = 'veditor-control-row';

        const toggleBtn = document.createElement('button');
        toggleBtn.className = 'veditor-btn veditor-toggle-btn';
        toggleBtn.innerHTML = `${iconCrop} Enable Crop`;
        toggleBtn.title = 'Toggle crop';
        toggleBtn.setAttribute('data-tool-id', 'veditor-crop-toggle');
        toggleBtn.setAttribute('aria-label', 'Toggle crop');
        toggleBtn.addEventListener('click', () => {
            this.enabled = !this.enabled;
            toggleBtn.classList.toggle('active', this.enabled);
            if (this.enabled && !this.rect) {
                this.rect = {
                    x: Math.round(this.videoWidth * 0.1),
                    y: Math.round(this.videoHeight * 0.1),
                    w: Math.round(this.videoWidth * 0.8),
                    h: Math.round(this.videoHeight * 0.8),
                };
            }
            if (!this.enabled) {
                this.rect = null;
                this.callbacks.onCropChanged(null);
            }
            this._updateInputs();
            this.render();
        });

        toggleRow.appendChild(toggleBtn);
        toggleSection.appendChild(toggleRow);

        // Aspect presets
        const presetRow = document.createElement('div');
        presetRow.className = 'veditor-preset-row';

        const presets: AspectPreset[] = ['free', '16:9', '9:16', '4:3', '1:1'];
        presets.forEach(p => {
            const btn = document.createElement('button');
            btn.className = 'veditor-btn veditor-preset-btn';
            if (p === this.aspectPreset) btn.classList.add('active');
            btn.textContent = p === 'free' ? 'Free' : p;
            btn.title = `Aspect ratio: ${p}`;
            btn.setAttribute('data-tool-id', `veditor-crop-aspect-${p.replace(':', '')}`);
            btn.setAttribute('aria-label', `Aspect ratio: ${p}`);
            btn.addEventListener('click', () => {
                this.aspectPreset = p;
                // Update active state on all preset buttons
                presetRow.querySelectorAll('.veditor-preset-btn').forEach(b =>
                    b.classList.remove('active'));
                btn.classList.add('active');
                if (this.rect && p !== 'free') {
                    this._applyAspect(p);
                }
                this._updateInputs();
                this.render();
            });
            presetRow.appendChild(btn);
        });

        // Flip aspect button
        const flipBtn = document.createElement('button');
        flipBtn.className = 'veditor-btn veditor-preset-btn';
        flipBtn.innerHTML = `${iconFlip}`;
        flipBtn.title = 'Flip aspect ratio (swap width/height)';
        flipBtn.setAttribute('data-tool-id', 'veditor-crop-flip');
        flipBtn.setAttribute('aria-label', 'Flip aspect ratio');
        flipBtn.addEventListener('click', () => {
            if (!this.rect) return;
            const oldW = this.rect.w;
            this.rect.w = this.rect.h;
            this.rect.h = oldW;
            // Re-center
            this.rect.x = Math.max(0, Math.round((this.videoWidth - this.rect.w) / 2));
            this.rect.y = Math.max(0, Math.round((this.videoHeight - this.rect.h) / 2));
            // Clamp
            if (this.rect.w > this.videoWidth) this.rect.w = this.videoWidth;
            if (this.rect.h > this.videoHeight) this.rect.h = this.videoHeight;
            this._updateInputs();
            this.render();
            this.callbacks.onCropChanged(this.rect);
        });
        presetRow.appendChild(flipBtn);

        toggleSection.appendChild(presetRow);

        // ── Numeric Inputs Section ──
        const numSection = this._makeSection('Dimensions');

        const numRow1 = document.createElement('div');
        numRow1.className = 'veditor-control-row';

        const xLabel = this._makeLabel('X');
        this.inputX = this._makeNumInput('veditor-crop-x', 'X position', (v) => {
            if (this.rect) { this.rect.x = v; this.render(); this.callbacks.onCropChanged(this.rect); }
        });

        const yLabel = this._makeLabel('Y');
        this.inputY = this._makeNumInput('veditor-crop-y', 'Y position', (v) => {
            if (this.rect) { this.rect.y = v; this.render(); this.callbacks.onCropChanged(this.rect); }
        });

        numRow1.append(xLabel, this.inputX, yLabel, this.inputY);

        const numRow2 = document.createElement('div');
        numRow2.className = 'veditor-control-row';

        const wLabel = this._makeLabel('W');
        this.inputW = this._makeNumInput('veditor-crop-w', 'Width', (v) => {
            if (this.rect) { this.rect.w = v; this.render(); this.callbacks.onCropChanged(this.rect); }
        });

        const hLabel = this._makeLabel('H');
        this.inputH = this._makeNumInput('veditor-crop-h', 'Height', (v) => {
            if (this.rect) { this.rect.h = v; this.render(); this.callbacks.onCropChanged(this.rect); }
        });

        numRow2.append(wLabel, this.inputW, hLabel, this.inputH);

        numSection.append(numRow1, numRow2);

        // ── Output Resolution ──
        const outputSection = this._makeSection('Output');

        const outputRow = document.createElement('div');
        outputRow.className = 'veditor-control-row';

        this.outputLabel = document.createElement('span');
        this.outputLabel.className = 'veditor-output-label';
        this.outputLabel.textContent = 'No crop';
        this.outputLabel.setAttribute('data-tool-id', 'veditor-crop-output');
        this.outputLabel.setAttribute('aria-label', 'Output resolution');

        outputRow.appendChild(this.outputLabel);
        outputSection.appendChild(outputRow);

        // ── Reset ──
        const resetRow = document.createElement('div');
        resetRow.className = 'veditor-control-row';

        const resetBtn = document.createElement('button');
        resetBtn.className = 'veditor-btn veditor-toggle-btn';
        resetBtn.innerHTML = `${iconReset} Reset Crop`;
        resetBtn.title = 'Reset crop';
        resetBtn.setAttribute('data-tool-id', 'veditor-crop-reset');
        resetBtn.setAttribute('aria-label', 'Reset crop');
        resetBtn.addEventListener('click', () => {
            this.rect = null;
            this.enabled = false;
            toggleBtn.classList.remove('active');
            this._updateInputs();
            this.callbacks.onCropChanged(null);
            this.render();
        });

        resetRow.appendChild(resetBtn);

        this.controls.append(toggleSection, numSection, outputSection, resetRow);

        // Bind events
        this.canvas.addEventListener('mousedown', (e) => this._onMouseDown(e));
        document.addEventListener('mousemove', (e) => this._onMouseMove(e));
        document.addEventListener('mouseup', () => this._onMouseUp());
    }

    /** Controls element for the side panel */
    get element(): HTMLDivElement {
        return this.controls;
    }

    /** Canvas overlay element for mounting on the video monitor */
    get canvasElement(): HTMLDivElement {
        return this.canvasWrapper;
    }

    setVideoDimensions(width: number, height: number): void {
        this.videoWidth = width;
        this.videoHeight = height;
        this.canvas.width = width;
        this.canvas.height = height;
        this._updateInputs();
        this.render();
    }

    getRect(): CropRect | null {
        return this.rect;
    }

    setRect(rect: CropRect | null): void {
        this.rect = rect;
        this.enabled = rect !== null;
        this._updateInputs();
        this.render();
    }

    render(): void {
        const ctx = this.canvas.getContext('2d');
        if (!ctx) return;

        ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        if (!this.enabled || !this.rect) return;

        const { x, y, w, h } = this.rect;

        // Dim outside crop area
        ctx.fillStyle = 'rgba(0, 0, 0, 0.6)';
        ctx.fillRect(0, 0, this.canvas.width, y);
        ctx.fillRect(0, y + h, this.canvas.width, this.canvas.height - y - h);
        ctx.fillRect(0, y, x, h);
        ctx.fillRect(x + w, y, this.canvas.width - x - w, h);

        // Crop border
        ctx.strokeStyle = '#00ddff';
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y, w, h);

        // Rule of thirds
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
        ctx.lineWidth = 1;
        for (let i = 1; i < 3; i++) {
            const gx = x + (w * i) / 3;
            const gy = y + (h * i) / 3;
            ctx.beginPath();
            ctx.moveTo(gx, y);
            ctx.lineTo(gx, y + h);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo(x, gy);
            ctx.lineTo(x + w, gy);
            ctx.stroke();
        }

        // Corner handles
        ctx.fillStyle = '#00ddff';
        const corners = [
            [x, y], [x + w, y], [x, y + h], [x + w, y + h],
        ];
        for (const [cx, cy] of corners) {
            ctx.fillRect(cx - HANDLE_SIZE / 2, cy - HANDLE_SIZE / 2, HANDLE_SIZE, HANDLE_SIZE);
        }
    }

    destroy(): void {
        this.canvasWrapper.remove();
        this.controls.remove();
    }

    // ── Private ──────────────────────────────────────────────────

    private _updateInputs(): void {
        if (this.rect) {
            this.inputX.value = String(Math.round(this.rect.x));
            this.inputY.value = String(Math.round(this.rect.y));
            this.inputW.value = String(Math.round(this.rect.w));
            this.inputH.value = String(Math.round(this.rect.h));
            this.outputLabel.textContent = `Output: ${Math.round(this.rect.w)}×${Math.round(this.rect.h)}`;
        } else {
            this.inputX.value = '';
            this.inputY.value = '';
            this.inputW.value = '';
            this.inputH.value = '';
            this.outputLabel.textContent = this.videoWidth
                ? `Original: ${this.videoWidth}×${this.videoHeight}`
                : 'No crop';
        }
    }

    private _onMouseDown(e: MouseEvent): void {
        if (!this.enabled || !this.rect) return;
        const pos = this._canvasPos(e);
        this.dragType = this._hitTest(pos.x, pos.y);
        if (this.dragType === 'none') return;

        this.isDragging = true;
        this.dragStart = pos;
        this.origRect = { ...this.rect };
        e.preventDefault();
    }

    private _onMouseMove(e: MouseEvent): void {
        if (!this.isDragging || !this.rect) return;
        const pos = this._canvasPos(e);
        const dx = pos.x - this.dragStart.x;
        const dy = pos.y - this.dragStart.y;

        switch (this.dragType) {
            case 'move':
                this.rect.x = Math.max(0, Math.min(this.videoWidth - this.rect.w, this.origRect.x + dx));
                this.rect.y = Math.max(0, Math.min(this.videoHeight - this.rect.h, this.origRect.y + dy));
                break;
            case 'tl':
                this.rect.x = Math.max(0, this.origRect.x + dx);
                this.rect.y = Math.max(0, this.origRect.y + dy);
                this.rect.w = Math.max(20, this.origRect.w - dx);
                this.rect.h = Math.max(20, this.origRect.h - dy);
                break;
            case 'tr':
                this.rect.y = Math.max(0, this.origRect.y + dy);
                this.rect.w = Math.max(20, this.origRect.w + dx);
                this.rect.h = Math.max(20, this.origRect.h - dy);
                break;
            case 'bl':
                this.rect.x = Math.max(0, this.origRect.x + dx);
                this.rect.w = Math.max(20, this.origRect.w - dx);
                this.rect.h = Math.max(20, this.origRect.h + dy);
                break;
            case 'br':
                this.rect.w = Math.max(20, this.origRect.w + dx);
                this.rect.h = Math.max(20, this.origRect.h + dy);
                break;
        }

        if (this.aspectPreset !== 'free' && e.shiftKey) {
            this._applyAspect(this.aspectPreset);
        }

        this._updateInputs();
        this.render();
        this.callbacks.onCropChanged(this.rect);
    }

    private _onMouseUp(): void {
        if (this.isDragging && this.rect) {
            this.callbacks.onCropChanged(this.rect);
        }
        this.isDragging = false;
        this.dragType = 'none';
    }

    private _hitTest(mx: number, my: number): string {
        if (!this.rect) return 'none';
        const { x, y, w, h } = this.rect;
        const hs = HANDLE_SIZE;

        if (Math.abs(mx - x) < hs && Math.abs(my - y) < hs) return 'tl';
        if (Math.abs(mx - (x + w)) < hs && Math.abs(my - y) < hs) return 'tr';
        if (Math.abs(mx - x) < hs && Math.abs(my - (y + h)) < hs) return 'bl';
        if (Math.abs(mx - (x + w)) < hs && Math.abs(my - (y + h)) < hs) return 'br';

        if (mx > x && mx < x + w && my > y && my < y + h) return 'move';

        return 'none';
    }

    private _applyAspect(preset: AspectPreset): void {
        if (!this.rect) return;
        let ratio: number;
        switch (preset) {
            case '16:9': ratio = 16 / 9; break;
            case '9:16': ratio = 9 / 16; break;
            case '4:3': ratio = 4 / 3; break;
            case '1:1': ratio = 1; break;
            default: return;
        }
        this.rect.h = Math.round(this.rect.w / ratio);
        if (this.rect.h > this.videoHeight) {
            this.rect.h = this.videoHeight;
            this.rect.w = Math.round(this.rect.h * ratio);
        }
    }

    private _canvasPos(e: MouseEvent): { x: number; y: number } {
        const rect = this.canvas.getBoundingClientRect();
        const scaleX = this.canvas.width / rect.width;
        const scaleY = this.canvas.height / rect.height;
        return {
            x: (e.clientX - rect.left) * scaleX,
            y: (e.clientY - rect.top) * scaleY,
        };
    }

    private _makeSection(title: string): HTMLDivElement {
        const section = document.createElement('div');
        section.className = 'veditor-panel-section';
        const label = document.createElement('div');
        label.className = 'veditor-section-label';
        label.textContent = title;
        section.appendChild(label);
        return section;
    }

    private _makeLabel(text: string): HTMLSpanElement {
        const label = document.createElement('span');
        label.className = 'veditor-control-label';
        label.textContent = text;
        return label;
    }

    private _makeNumInput(
        toolId: string, label: string,
        onChange: (val: number) => void,
    ): HTMLInputElement {
        const input = document.createElement('input');
        input.type = 'number';
        input.className = 'veditor-input';
        input.min = '0';
        input.setAttribute('data-tool-id', toolId);
        input.setAttribute('aria-label', label);
        input.addEventListener('change', () => {
            onChange(parseInt(input.value, 10) || 0);
            this._updateInputs();
        });
        return input;
    }
}
