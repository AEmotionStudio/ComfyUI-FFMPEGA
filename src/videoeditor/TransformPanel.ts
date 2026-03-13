/**
 * TransformPanel — Spatial transform controls
 *
 * Position X/Y, Scale, Rotation with per-track controls.
 * Integrates with existing KeyframeTrack for animated transforms.
 */

export interface TransformState {
    enabled: boolean;
    position_x: number;
    position_y: number;
    scale: number;
    rotation: number;
    anchor_x: number;
    anchor_y: number;
    flip_h: boolean;
    flip_v: boolean;
    opacity: number;
}

export interface TransformPanelCallbacks {
    onTransformChanged: (state: TransformState) => void;
}

const DEFAULT_STATE: TransformState = {
    enabled: false,
    position_x: 0,
    position_y: 0,
    scale: 100,
    rotation: 0,
    anchor_x: 50,
    anchor_y: 50,
    flip_h: false,
    flip_v: false,
    opacity: 100,
};

export class TransformPanel {
    private container: HTMLDivElement;
    private callbacks: TransformPanelCallbacks;
    private state: TransformState;

    constructor(callbacks: TransformPanelCallbacks) {
        this.callbacks = callbacks;
        this.state = { ...DEFAULT_STATE };

        this.container = document.createElement('div');
        this.container.className = 'veditor-transform-panel';
        this.container.setAttribute('data-tool-id', 'veditor-transform-panel');

        this._build();
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    getState(): TransformState {
        return { ...this.state };
    }

    loadState(s: Partial<TransformState>): void {
        Object.assign(this.state, s);
        this._build();
    }

    reset(): void {
        this.state = { ...DEFAULT_STATE };
        this._build();
        this._notify();
    }

    // ── Build ────────────────────────────────────────────────────

    private _build(): void {
        this.container.innerHTML = '';

        // Enable toggle
        this.container.appendChild(this._toggle('Enable Transform', this.state.enabled, (v) => {
            this.state.enabled = v;
            this._notify();
        }, 'veditor-transform-enable'));

        // Position
        const posRow = this._row();
        posRow.appendChild(this._numInput('X', this.state.position_x, -2000, 2000, (v) => {
            this.state.position_x = v;
            this._notify();
        }, 'veditor-transform-x'));
        posRow.appendChild(this._numInput('Y', this.state.position_y, -2000, 2000, (v) => {
            this.state.position_y = v;
            this._notify();
        }, 'veditor-transform-y'));
        this.container.appendChild(posRow);

        // Scale
        this.container.appendChild(this._slider('Scale', this.state.scale, 10, 400, 1, '%', (v) => {
            this.state.scale = v;
            this._notify();
        }, 'veditor-transform-scale'));

        // Rotation
        this.container.appendChild(this._slider('Rotation', this.state.rotation, -180, 180, 1, '°', (v) => {
            this.state.rotation = v;
            this._notify();
        }, 'veditor-transform-rotation'));

        // Opacity
        this.container.appendChild(this._slider('Opacity', this.state.opacity, 0, 100, 1, '%', (v) => {
            this.state.opacity = v;
            this._notify();
        }, 'veditor-transform-opacity'));

        // Flip buttons
        const flipRow = this._row();
        flipRow.appendChild(this._toggleBtn('↔ Flip H', this.state.flip_h, (v) => {
            this.state.flip_h = v;
            this._notify();
        }, 'veditor-transform-flip-h'));
        flipRow.appendChild(this._toggleBtn('↕ Flip V', this.state.flip_v, (v) => {
            this.state.flip_v = v;
            this._notify();
        }, 'veditor-transform-flip-v'));
        this.container.appendChild(flipRow);

        // Reset button
        const resetRow = this._row();
        const resetBtn = document.createElement('button');
        resetBtn.className = 'veditor-btn';
        resetBtn.textContent = 'Reset Transform';
        resetBtn.setAttribute('data-tool-id', 'veditor-transform-reset');
        resetBtn.addEventListener('click', () => this.reset());
        resetRow.appendChild(resetBtn);
        this.container.appendChild(resetRow);
    }

    // ── Shared UI helpers ────────────────────────────────────────

    private _notify(): void {
        this.callbacks.onTransformChanged(this.getState());
    }

    private _row(): HTMLDivElement {
        const r = document.createElement('div');
        r.className = 'veditor-control-row';
        return r;
    }

    private _toggle(
        label: string, checked: boolean,
        onChange: (v: boolean) => void, toolId: string,
    ): HTMLDivElement {
        const row = this._row();
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.className = 'veditor-checkbox';
        cb.checked = checked;
        cb.setAttribute('data-tool-id', toolId);
        cb.addEventListener('change', () => onChange(cb.checked));

        const lbl = document.createElement('span');
        lbl.className = 'veditor-control-label';
        lbl.textContent = label;

        row.append(cb, lbl);
        return row;
    }

    private _slider(
        label: string, value: number, min: number, max: number,
        step: number, unit: string,
        onChange: (v: number) => void, toolId: string,
    ): HTMLDivElement {
        const row = this._row();
        const lbl = document.createElement('span');
        lbl.className = 'veditor-control-label';
        lbl.textContent = label;

        const slider = document.createElement('input');
        slider.type = 'range';
        slider.min = String(min);
        slider.max = String(max);
        slider.step = String(step);
        slider.value = String(value);
        slider.className = 'veditor-grading-slider';
        slider.setAttribute('data-tool-id', toolId);

        const val = document.createElement('span');
        val.className = 'veditor-grading-value';
        val.textContent = `${value}${unit}`;

        slider.addEventListener('input', () => {
            const v = parseFloat(slider.value);
            val.textContent = `${v}${unit}`;
            onChange(v);
        });

        row.append(lbl, slider, val);
        return row;
    }

    private _numInput(
        label: string, value: number, min: number, max: number,
        onChange: (v: number) => void, toolId: string,
    ): HTMLElement {
        const wrap = document.createElement('span');
        wrap.style.display = 'inline-flex';
        wrap.style.alignItems = 'center';
        wrap.style.gap = '4px';

        const lbl = document.createElement('span');
        lbl.className = 'veditor-control-label';
        lbl.textContent = label;

        const input = document.createElement('input');
        input.type = 'number';
        input.className = 'veditor-input';
        input.value = String(value);
        input.min = String(min);
        input.max = String(max);
        input.style.width = '65px';
        input.setAttribute('data-tool-id', toolId);
        input.addEventListener('change', () => {
            let v = parseFloat(input.value) || 0;
            v = Math.max(min, Math.min(max, v));
            input.value = String(v);
            onChange(v);
        });

        wrap.append(lbl, input);
        return wrap;
    }

    private _toggleBtn(
        label: string, active: boolean,
        onChange: (v: boolean) => void, toolId: string,
    ): HTMLElement {
        const btn = document.createElement('button');
        btn.className = 'veditor-btn veditor-preset-btn';
        if (active) btn.classList.add('active');
        btn.textContent = label;
        btn.setAttribute('data-tool-id', toolId);
        btn.addEventListener('click', () => {
            const next = !btn.classList.contains('active');
            btn.classList.toggle('active', next);
            onChange(next);
        });
        return btn;
    }
}
