/**
 * AIComposePanel — AI-powered compositing controls
 *
 * Background Removal: bria-rmbg/birefnet model selection, background type
 * Depth Effects: bokeh blur, fog, tilt-shift with depth map generation
 */

export interface AIComposeState {
    bg_removal: BgRemovalState;
    depth_effect: DepthEffectState;
}

export interface BgRemovalState {
    enabled: boolean;
    model: string;
    background_type: string;
    background_color: string;
    background_path: string;
    edge_refine: number;
    blur_strength: number;
}

export interface DepthEffectState {
    enabled: boolean;
    model: string;
    effect: string;
    focus_distance: number;
    blur_amount: number;
    fog_density: number;
    fog_color: string;
    tilt_shift_center: number;
    tilt_shift_width: number;
}

export interface AIComposePanelCallbacks {
    onAIComposeChanged: (state: AIComposeState) => void;
}

const REMBG_MODELS = [
    { value: 'bria-rmbg', label: 'BRIA RMBG (Best Quality)' },
    { value: 'birefnet-general', label: 'BiRefNet (High Quality)' },
    { value: 'birefnet-general-lite', label: 'BiRefNet Lite (Fast)' },
    { value: 'isnet-general-use', label: 'ISNet General' },
    { value: 'u2net', label: 'U2Net' },
    { value: 'silueta', label: 'Silueta (Lightweight)' },
];

const BG_TYPES = [
    { value: 'transparent', label: 'Transparent (WebM)' },
    { value: 'blur', label: 'Blurred Original' },
    { value: 'solid', label: 'Solid Color' },
    { value: 'image', label: 'Image File' },
];

const DEPTH_MODELS = [
    { value: 'video-depth-anything', label: 'Video Depth Anything' },
    { value: 'marigold', label: 'Marigold' },
];

const DEPTH_EFFECTS = [
    { value: 'bokeh', label: 'Depth of Field (Bokeh)' },
    { value: 'fog', label: 'Atmospheric Fog' },
    { value: 'tilt-shift', label: 'Tilt-Shift (Miniature)' },
];

const DEFAULT_STATE: AIComposeState = {
    bg_removal: {
        enabled: false,
        model: 'bria-rmbg',
        background_type: 'transparent',
        background_color: '#000000',
        background_path: '',
        edge_refine: 0.5,
        blur_strength: 15,
    },
    depth_effect: {
        enabled: false,
        model: 'video-depth-anything',
        effect: 'bokeh',
        focus_distance: 0.5,
        blur_amount: 10,
        fog_density: 0.5,
        fog_color: '#cccccc',
        tilt_shift_center: 0.5,
        tilt_shift_width: 0.3,
    },
};

export class AIComposePanel {
    private container: HTMLDivElement;
    private callbacks: AIComposePanelCallbacks;
    private state: AIComposeState;

    constructor(callbacks: AIComposePanelCallbacks) {
        this.callbacks = callbacks;
        this.state = JSON.parse(JSON.stringify(DEFAULT_STATE));

        this.container = document.createElement('div');
        this.container.className = 'veditor-ai-compose-panel';
        this.container.setAttribute('data-tool-id', 'veditor-ai-compose-panel');

        this._build();
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    getState(): AIComposeState {
        return JSON.parse(JSON.stringify(this.state));
    }

    loadState(s: Partial<AIComposeState>): void {
        if (s.bg_removal) Object.assign(this.state.bg_removal, s.bg_removal);
        if (s.depth_effect) Object.assign(this.state.depth_effect, s.depth_effect);
        this._build();
    }

    reset(): void {
        this.state = JSON.parse(JSON.stringify(DEFAULT_STATE));
        this._build();
        this._notify();
    }

    // ── Build ────────────────────────────────────────────────────

    private _build(): void {
        this.container.innerHTML = '';

        // ── AI Notice ──
        const notice = document.createElement('div');
        notice.className = 'veditor-ai-notice';
        notice.innerHTML = '⚠️ AI features require GPU and model downloads. Processing may take several minutes.';
        this.container.appendChild(notice);

        // ── Background Removal Section ──
        this.container.appendChild(this._buildBgRemovalSection());

        // ── Depth Effects Section ──
        this.container.appendChild(this._buildDepthSection());
    }

    // ── Background Removal ───────────────────────────────────────

    private _buildBgRemovalSection(): HTMLElement {
        const section = this._section('Background Removal');
        const bg = this.state.bg_removal;

        // Enable
        section.appendChild(this._toggle('Enable Background Removal', bg.enabled, (v) => {
            bg.enabled = v;
            this._notify();
        }, 'veditor-ai-bg-enable'));

        // Model
        section.appendChild(this._dropdown('Model', REMBG_MODELS, bg.model, (v) => {
            bg.model = v;
            this._notify();
        }, 'veditor-ai-bg-model'));

        // Background type
        section.appendChild(this._dropdown('Background', BG_TYPES, bg.background_type, (v) => {
            bg.background_type = v;
            this._notify();
        }, 'veditor-ai-bg-type'));

        // Conditional: solid color
        if (bg.background_type === 'solid') {
            const colorRow = this._row();
            const colorLabel = document.createElement('span');
            colorLabel.className = 'veditor-control-label';
            colorLabel.textContent = 'Color';
            const colorInput = document.createElement('input');
            colorInput.type = 'color';
            colorInput.value = bg.background_color;
            colorInput.className = 'veditor-color-input';
            colorInput.addEventListener('change', () => { bg.background_color = colorInput.value; this._notify(); });
            colorRow.append(colorLabel, colorInput);
            section.appendChild(colorRow);
        }

        // Conditional: blur strength
        if (bg.background_type === 'blur') {
            section.appendChild(this._slider('Blur Strength', bg.blur_strength, 1, 50, 1, '', (v) => {
                bg.blur_strength = v;
                this._notify();
            }, 'veditor-ai-bg-blur'));
        }

        // Edge refinement
        section.appendChild(this._slider('Edge Refinement', bg.edge_refine * 100, 0, 100, 1, '%', (v) => {
            bg.edge_refine = v / 100;
            this._notify();
        }, 'veditor-ai-bg-edge'));

        return section;
    }

    // ── Depth Effects ────────────────────────────────────────────

    private _buildDepthSection(): HTMLElement {
        const section = this._section('Depth Effects');
        const de = this.state.depth_effect;

        // Enable
        section.appendChild(this._toggle('Enable Depth Effects', de.enabled, (v) => {
            de.enabled = v;
            this._notify();
        }, 'veditor-ai-depth-enable'));

        // Model
        section.appendChild(this._dropdown('Depth Model', DEPTH_MODELS, de.model, (v) => {
            de.model = v;
            this._notify();
        }, 'veditor-ai-depth-model'));

        // Effect type
        section.appendChild(this._dropdown('Effect', DEPTH_EFFECTS, de.effect, (v) => {
            de.effect = v;
            this._notify();
        }, 'veditor-ai-depth-effect'));

        // Effect-specific controls
        if (de.effect === 'bokeh') {
            section.appendChild(this._slider('Focus Distance', de.focus_distance * 100, 0, 100, 1, '%', (v) => {
                de.focus_distance = v / 100;
                this._notify();
            }, 'veditor-ai-depth-focus'));

            section.appendChild(this._slider('Blur Amount', de.blur_amount, 1, 30, 1, '', (v) => {
                de.blur_amount = v;
                this._notify();
            }, 'veditor-ai-depth-blur'));
        }

        if (de.effect === 'fog') {
            section.appendChild(this._slider('Fog Density', de.fog_density * 100, 0, 100, 1, '%', (v) => {
                de.fog_density = v / 100;
                this._notify();
            }, 'veditor-ai-depth-fog-density'));

            const colorRow = this._row();
            const colorLabel = document.createElement('span');
            colorLabel.className = 'veditor-control-label';
            colorLabel.textContent = 'Fog Color';
            const colorInput = document.createElement('input');
            colorInput.type = 'color';
            colorInput.value = de.fog_color;
            colorInput.className = 'veditor-color-input';
            colorInput.addEventListener('change', () => { de.fog_color = colorInput.value; this._notify(); });
            colorRow.append(colorLabel, colorInput);
            section.appendChild(colorRow);
        }

        if (de.effect === 'tilt-shift') {
            section.appendChild(this._slider('Focus Center', de.tilt_shift_center * 100, 0, 100, 1, '%', (v) => {
                de.tilt_shift_center = v / 100;
                this._notify();
            }, 'veditor-ai-depth-tilt-center'));

            section.appendChild(this._slider('Focus Width', de.tilt_shift_width * 100, 5, 100, 1, '%', (v) => {
                de.tilt_shift_width = v / 100;
                this._notify();
            }, 'veditor-ai-depth-tilt-width'));

            section.appendChild(this._slider('Blur Amount', de.blur_amount, 1, 30, 1, '', (v) => {
                de.blur_amount = v;
                this._notify();
            }, 'veditor-ai-depth-tilt-blur'));
        }

        return section;
    }

    // ── Shared UI helpers ────────────────────────────────────────

    private _notify(): void {
        this.callbacks.onAIComposeChanged(this.getState());
    }

    private _row(): HTMLDivElement {
        const r = document.createElement('div');
        r.className = 'veditor-control-row';
        return r;
    }

    private _section(title: string): HTMLDivElement {
        const s = document.createElement('div');
        s.className = 'veditor-compose-section';
        const header = document.createElement('div');
        header.className = 'veditor-compose-section-header';
        const t = document.createElement('span');
        t.className = 'veditor-compose-section-title';
        t.textContent = title;
        header.appendChild(t);
        s.appendChild(header);
        return s;
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

    private _dropdown(
        label: string, options: {value: string; label: string}[],
        current: string, onChange: (v: string) => void, toolId: string,
    ): HTMLDivElement {
        const row = this._row();
        const lbl = document.createElement('span');
        lbl.className = 'veditor-control-label';
        lbl.textContent = label;

        const select = document.createElement('select');
        select.className = 'veditor-select';
        select.setAttribute('data-tool-id', toolId);
        options.forEach(o => {
            const opt = document.createElement('option');
            opt.value = o.value;
            opt.textContent = o.label;
            if (o.value === current) opt.selected = true;
            select.appendChild(opt);
        });
        select.addEventListener('change', () => onChange(select.value));

        row.append(lbl, select);
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
}
