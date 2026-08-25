/**
 * ComposePanel — Compositing controls (PiP, Watermark, Chroma Key, etc.)
 *
 * Phase 1: PiP + Watermark sections
 * Phase 2+: Chroma Key, Blend, Split Screen, Masking, Vignette
 *
 * Each sub-feature is a collapsible section within a single "Compose" tab.
 */

export interface ComposeState {
    pip: PipState;
    watermark: WatermarkState;
    chromakey: ChromaKeyState;
    blend: BlendState;
    splitScreen: SplitScreenState;
    vignette: VignetteState;
    mask: MaskState;
    onionSkin: OnionSkinState;
}

export interface PipState {
    enabled: boolean;
    path: string;
    position: string;
    x: number;
    y: number;
    size: number;
    opacity: number;
    start_time: number | null;
    end_time: number | null;
    border: boolean;
    border_color: string;
    border_width: number;
}

export interface WatermarkState {
    enabled: boolean;
    path: string;
    position: string;
    x: number;
    y: number;
    size: number;
    opacity: number;
    persistent: boolean;
}

export interface ChromaKeyState {
    enabled: boolean;
    color: string;
    similarity: number;
    blend: number;
    mode: string;
}

export interface BlendState {
    enabled: boolean;
    mode: string;
    opacity: number;
}

export interface SplitScreenState {
    enabled: boolean;
    layout: string;
    border_width: number;
    border_color: string;
}

export interface VignetteState {
    enabled: boolean;
    intensity: number;
    softness: number;
}

export interface MaskState {
    enabled: boolean;
    shape: string;
    x: string;
    y: string;
    width: string;
    height: string;
    feather: number;
    invert: boolean;
    effect: string;
}

export interface OnionSkinState {
    enabled: boolean;
    blend_mode: string;
    opacity: number;
    decay: number;
}

export interface ComposePanelCallbacks {
    onComposeChanged: (state: ComposeState) => void;
}

const DEFAULT_STATE: ComposeState = {
    pip: {
        enabled: false, path: '', position: 'bottom-right',
        x: 0, y: 0, size: 25, opacity: 100,
        start_time: null, end_time: null,
        border: false, border_color: '#ffffff', border_width: 2,
    },
    watermark: {
        enabled: false, path: '', position: 'bottom-right',
        x: 0, y: 0, size: 15, opacity: 80, persistent: true,
    },
    chromakey: {
        enabled: false, color: '#00ff00', similarity: 0.3, blend: 0.1, mode: 'chromakey',
    },
    blend: {
        enabled: false, mode: 'normal', opacity: 1.0,
    },
    splitScreen: {
        enabled: false, layout: '2h', border_width: 0, border_color: '#000000',
    },
    vignette: {
        enabled: false, intensity: 50, softness: 0.5,
    },
    mask: {
        enabled: false, shape: 'rectangle', x: 'iw/4', y: 'ih/4',
        width: 'iw/2', height: 'ih/2', feather: 5, invert: false, effect: 'blur',
    },
    onionSkin: {
        enabled: false, blend_mode: 'screen', opacity: 50, decay: 0.97,
    },
};

const POSITION_PRESETS = [
    { value: 'top-left', label: '↖ TL' },
    { value: 'top-center', label: '↑ TC' },
    { value: 'top-right', label: '↗ TR' },
    { value: 'center', label: '⊙ C' },
    { value: 'bottom-left', label: '↙ BL' },
    { value: 'bottom-center', label: '↓ BC' },
    { value: 'bottom-right', label: '↘ BR' },
    { value: 'custom', label: '✎ XY' },
];

export class ComposePanel {
    private container: HTMLDivElement;
    private callbacks: ComposePanelCallbacks;
    private state: ComposeState;

    constructor(callbacks: ComposePanelCallbacks) {
        this.callbacks = callbacks;
        this.state = JSON.parse(JSON.stringify(DEFAULT_STATE));

        this.container = document.createElement('div');
        this.container.className = 'veditor-compose-panel';
        this.container.setAttribute('data-tool-id', 'veditor-compose-panel');

        // ── PiP Section ──
        this.container.appendChild(
            this._buildSection('Picture-in-Picture', 'pip', () => this._buildPipContent()),
        );

        // ── Watermark Section ──
        this.container.appendChild(
            this._buildSection('Image Watermark', 'watermark', () => this._buildWatermarkContent()),
        );

        // ── Vignette Section ──
        this.container.appendChild(
            this._buildSection('Vignette', 'vignette', () => this._buildVignetteContent()),
        );

        // ── Chroma Key Section (Phase 2) ──
        this.container.appendChild(
            this._buildSection('Chroma Key', 'chromakey', () => this._buildChromaKeyContent()),
        );

        // ── Blend Modes Section (Phase 3) ──
        this.container.appendChild(
            this._buildSection('Blend Mode', 'blend', () => this._buildBlendContent()),
        );

        // ── Onion Skin Section ──
        this.container.appendChild(
            this._buildSection('Onion Skin', 'onionSkin', () => this._buildOnionSkinContent()),
        );
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    getState(): ComposeState {
        return JSON.parse(JSON.stringify(this.state));
    }

    loadState(s: Partial<ComposeState>): void {
        if (s.pip) Object.assign(this.state.pip, s.pip);
        if (s.watermark) Object.assign(this.state.watermark, s.watermark);
        if (s.chromakey) Object.assign(this.state.chromakey, s.chromakey);
        if (s.blend) Object.assign(this.state.blend, s.blend);
        if (s.splitScreen) Object.assign(this.state.splitScreen, s.splitScreen);
        if (s.vignette) Object.assign(this.state.vignette, s.vignette);
        if (s.mask) Object.assign(this.state.mask, s.mask);
        if (s.onionSkin) Object.assign(this.state.onionSkin, s.onionSkin);
        this._rebuild();
    }

    reset(): void {
        this.state = JSON.parse(JSON.stringify(DEFAULT_STATE));
        this._rebuild();
        this._notify();
    }

    destroy(): void {
        this.container.remove();
    }

    // ── Section Builder ──────────────────────────────────────────

    private _buildSection(
        title: string,
        stateKey: keyof ComposeState,
        contentBuilder: () => HTMLElement,
    ): HTMLDivElement {
        const section = document.createElement('div');
        section.className = 'veditor-compose-section';

        const header = document.createElement('div');
        header.className = 'veditor-compose-section-header';

        const toggle = document.createElement('input');
        toggle.type = 'checkbox';
        toggle.className = 'veditor-checkbox';
        toggle.checked = (this.state[stateKey] as any).enabled;
        toggle.setAttribute('data-tool-id', `veditor-compose-${stateKey}-toggle`);

        const label = document.createElement('span');
        label.className = 'veditor-compose-section-title';
        label.textContent = title;

        const chevron = document.createElement('span');
        chevron.className = 'veditor-compose-chevron';
        chevron.textContent = '▸';

        header.append(toggle, label, chevron);

        const content = document.createElement('div');
        content.className = 'veditor-compose-section-content';
        content.style.display = 'none';

        // Toggle enabled
        toggle.addEventListener('change', () => {
            (this.state[stateKey] as any).enabled = toggle.checked;
            this._notify();
        });

        // Expand/collapse
        header.addEventListener('click', (e) => {
            if (e.target === toggle) return;
            const isOpen = content.style.display !== 'none';
            content.style.display = isOpen ? 'none' : 'block';
            chevron.textContent = isOpen ? '▸' : '▾';
        });

        content.appendChild(contentBuilder());
        section.append(header, content);
        return section;
    }

    // ── PiP Content ──────────────────────────────────────────────

    private _buildPipContent(): HTMLElement {
        const frag = document.createElement('div');
        const pip = this.state.pip;

        // Path input
        frag.appendChild(this._labeledInput('Source file', 'text', pip.path, (v) => {
            pip.path = v;
            this._notify();
        }, 'veditor-compose-pip-path', '/path/to/overlay.mp4'));

        // Position presets
        frag.appendChild(this._positionPresets(pip.position, (v) => {
            pip.position = v;
            this._notify();
        }, 'pip'));

        // Custom X/Y
        const xyRow = this._row();
        xyRow.appendChild(this._smallInput('X', pip.x, (v) => { pip.x = Number(v) || 0; this._notify(); }, 'veditor-compose-pip-x'));
        xyRow.appendChild(this._smallInput('Y', pip.y, (v) => { pip.y = Number(v) || 0; this._notify(); }, 'veditor-compose-pip-y'));
        frag.appendChild(xyRow);

        // Size slider
        frag.appendChild(this._slider('Size', pip.size, 5, 100, 1, '%', (v) => {
            pip.size = v;
            this._notify();
        }, 'veditor-compose-pip-size'));

        // Opacity slider
        frag.appendChild(this._slider('Opacity', pip.opacity, 0, 100, 1, '%', (v) => {
            pip.opacity = v;
            this._notify();
        }, 'veditor-compose-pip-opacity'));

        // Timing
        const timeRow = this._row();
        timeRow.appendChild(this._smallInput('Start', pip.start_time ?? '', (v) => {
            pip.start_time = v === '' ? null : Number(v);
            this._notify();
        }, 'veditor-compose-pip-start'));
        timeRow.appendChild(this._smallInput('End', pip.end_time ?? '', (v) => {
            pip.end_time = v === '' ? null : Number(v);
            this._notify();
        }, 'veditor-compose-pip-end'));
        frag.appendChild(timeRow);

        // Border
        const borderRow = this._row();
        const borderCheck = document.createElement('input');
        borderCheck.type = 'checkbox';
        borderCheck.className = 'veditor-checkbox';
        borderCheck.checked = pip.border;
        borderCheck.addEventListener('change', () => { pip.border = borderCheck.checked; this._notify(); });
        const borderLabel = document.createElement('span');
        borderLabel.textContent = 'Border';
        borderLabel.className = 'veditor-control-label';
        borderRow.append(borderCheck, borderLabel);
        frag.appendChild(borderRow);

        return frag;
    }

    // ── Watermark Content ────────────────────────────────────────

    private _buildWatermarkContent(): HTMLElement {
        const frag = document.createElement('div');
        const wm = this.state.watermark;

        frag.appendChild(this._labeledInput('Image file', 'text', wm.path, (v) => {
            wm.path = v;
            this._notify();
        }, 'veditor-compose-wm-path', '/path/to/logo.png'));

        frag.appendChild(this._positionPresets(wm.position, (v) => {
            wm.position = v;
            this._notify();
        }, 'wm'));

        frag.appendChild(this._slider('Size', wm.size, 5, 50, 1, '%', (v) => {
            wm.size = v;
            this._notify();
        }, 'veditor-compose-wm-size'));

        frag.appendChild(this._slider('Opacity', wm.opacity, 0, 100, 1, '%', (v) => {
            wm.opacity = v;
            this._notify();
        }, 'veditor-compose-wm-opacity'));

        return frag;
    }

    // ── Vignette Content ─────────────────────────────────────────

    private _buildVignetteContent(): HTMLElement {
        const frag = document.createElement('div');
        const vig = this.state.vignette;

        frag.appendChild(this._slider('Intensity', vig.intensity, 0, 100, 1, '%', (v) => {
            vig.intensity = v;
            this._notify();
        }, 'veditor-compose-vig-intensity'));

        return frag;
    }

    // ── Chroma Key Content ───────────────────────────────────────

    private _buildChromaKeyContent(): HTMLElement {
        const frag = document.createElement('div');
        const ck = this.state.chromakey;

        // Key color
        const colorRow = this._row();
        const colorLabel = document.createElement('span');
        colorLabel.className = 'veditor-control-label';
        colorLabel.textContent = 'Key Color';
        const colorInput = document.createElement('input');
        colorInput.type = 'color';
        colorInput.value = ck.color;
        colorInput.className = 'veditor-color-input';
        colorInput.setAttribute('data-tool-id', 'veditor-compose-ck-color');
        colorInput.addEventListener('change', () => { ck.color = colorInput.value; this._notify(); });

        // Quick presets
        const greenBtn = document.createElement('button');
        greenBtn.className = 'veditor-btn veditor-preset-btn';
        greenBtn.textContent = 'Green';
        greenBtn.addEventListener('click', () => { ck.color = '#00ff00'; colorInput.value = '#00ff00'; this._notify(); });
        const blueBtn = document.createElement('button');
        blueBtn.className = 'veditor-btn veditor-preset-btn';
        blueBtn.textContent = 'Blue';
        blueBtn.addEventListener('click', () => { ck.color = '#0000ff'; colorInput.value = '#0000ff'; this._notify(); });

        colorRow.append(colorLabel, colorInput, greenBtn, blueBtn);
        frag.appendChild(colorRow);

        frag.appendChild(this._slider('Similarity', ck.similarity * 100, 1, 100, 1, '%', (v) => {
            ck.similarity = v / 100;
            this._notify();
        }, 'veditor-compose-ck-similarity'));

        frag.appendChild(this._slider('Edge Blend', ck.blend * 100, 0, 100, 1, '%', (v) => {
            ck.blend = v / 100;
            this._notify();
        }, 'veditor-compose-ck-blend'));

        return frag;
    }

    // ── Blend Mode Content ───────────────────────────────────────

    private _buildBlendContent(): HTMLElement {
        const frag = document.createElement('div');
        const bl = this.state.blend;

        const modeRow = this._row();
        const modeLabel = document.createElement('span');
        modeLabel.className = 'veditor-control-label';
        modeLabel.textContent = 'Mode';

        const modeSelect = document.createElement('select');
        modeSelect.className = 'veditor-select';
        modeSelect.setAttribute('data-tool-id', 'veditor-compose-blend-mode');
        const modes = ['normal','multiply','screen','overlay','difference','addition','subtract','dodge','burn','hardlight','softlight','exclusion','darken','lighten'];
        modes.forEach(m => {
            const o = document.createElement('option');
            o.value = m;
            o.textContent = m.charAt(0).toUpperCase() + m.slice(1);
            if (m === bl.mode) o.selected = true;
            modeSelect.appendChild(o);
        });
        modeSelect.addEventListener('change', () => { bl.mode = modeSelect.value; this._notify(); });
        modeRow.append(modeLabel, modeSelect);
        frag.appendChild(modeRow);

        frag.appendChild(this._slider('Opacity', bl.opacity * 100, 0, 100, 1, '%', (v) => {
            bl.opacity = v / 100;
            this._notify();
        }, 'veditor-compose-blend-opacity'));

        return frag;
    }

    // ── Onion Skin Content ───────────────────────────────────────

    private _buildOnionSkinContent(): HTMLElement {
        const frag = document.createElement('div');
        const os = this.state.onionSkin;

        // Blend mode dropdown
        const modeRow = this._row();
        const modeLabel = document.createElement('span');
        modeLabel.className = 'veditor-control-label';
        modeLabel.textContent = 'Blend';

        const modeSelect = document.createElement('select');
        modeSelect.className = 'veditor-select';
        modeSelect.setAttribute('data-tool-id', 'veditor-compose-oskin-blend');
        const modes = ['screen', 'normal', 'addition', 'difference', 'multiply', 'overlay', 'softlight'];
        modes.forEach(m => {
            const o = document.createElement('option');
            o.value = m;
            o.textContent = m.charAt(0).toUpperCase() + m.slice(1);
            if (m === os.blend_mode) o.selected = true;
            modeSelect.appendChild(o);
        });
        modeSelect.addEventListener('change', () => { os.blend_mode = modeSelect.value; this._notify(); });
        modeRow.append(modeLabel, modeSelect);
        frag.appendChild(modeRow);

        // Opacity slider
        frag.appendChild(this._slider('Opacity', os.opacity, 0, 100, 1, '%', (v) => {
            os.opacity = v;
            this._notify();
        }, 'veditor-compose-oskin-opacity'));

        // Decay slider (trail length)
        frag.appendChild(this._slider('Trail Length', os.decay * 1000, 900, 999, 1, '', (v) => {
            os.decay = v / 1000;
            this._notify();
        }, 'veditor-compose-oskin-decay'));

        return frag;
    }

    // ── Rebuild ──────────────────────────────────────────────────

    private _rebuild(): void {
        this.container.innerHTML = '';
        this.container.appendChild(
            this._buildSection('Picture-in-Picture', 'pip', () => this._buildPipContent()),
        );
        this.container.appendChild(
            this._buildSection('Image Watermark', 'watermark', () => this._buildWatermarkContent()),
        );
        this.container.appendChild(
            this._buildSection('Vignette', 'vignette', () => this._buildVignetteContent()),
        );
        this.container.appendChild(
            this._buildSection('Chroma Key', 'chromakey', () => this._buildChromaKeyContent()),
        );
        this.container.appendChild(
            this._buildSection('Blend Mode', 'blend', () => this._buildBlendContent()),
        );
        this.container.appendChild(
            this._buildSection('Onion Skin', 'onionSkin', () => this._buildOnionSkinContent()),
        );
    }

    // ── Shared UI helpers ────────────────────────────────────────

    private _notify(): void {
        this.callbacks.onComposeChanged(this.getState());
    }

    private _row(): HTMLDivElement {
        const r = document.createElement('div');
        r.className = 'veditor-control-row';
        return r;
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

    private _labeledInput(
        label: string, type: string, value: string,
        onChange: (v: string) => void, toolId: string, placeholder = '',
    ): HTMLDivElement {
        const row = this._row();
        const lbl = document.createElement('span');
        lbl.className = 'veditor-control-label';
        lbl.textContent = label;

        const input = document.createElement('input');
        input.type = type;
        input.className = 'veditor-input';
        input.value = value;
        input.placeholder = placeholder;
        input.style.flex = '1';
        input.setAttribute('data-tool-id', toolId);
        input.addEventListener('change', () => onChange(input.value));

        row.append(lbl, input);
        return row;
    }

    private _smallInput(
        label: string, value: string | number,
        onChange: (v: number | string) => void, toolId: string,
    ): HTMLElement {
        const wrap = document.createElement('span');
        wrap.style.display = 'inline-flex';
        wrap.style.alignItems = 'center';
        wrap.style.gap = '4px';

        const lbl = document.createElement('span');
        lbl.className = 'veditor-control-label';
        lbl.textContent = label;

        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'veditor-input';
        input.value = String(value);
        input.style.width = '60px';
        input.setAttribute('data-tool-id', toolId);
        input.addEventListener('change', () => {
            const n = parseFloat(input.value);
            onChange(isNaN(n) ? input.value : n);
        });

        wrap.append(lbl, input);
        return wrap;
    }

    private _positionPresets(
        current: string, onChange: (v: string) => void, prefix: string,
    ): HTMLDivElement {
        const row = this._row();
        row.style.flexWrap = 'wrap';
        row.style.gap = '3px';

        const lbl = document.createElement('span');
        lbl.className = 'veditor-control-label';
        lbl.textContent = 'Position';
        row.appendChild(lbl);

        POSITION_PRESETS.forEach(p => {
            const btn = document.createElement('button');
            btn.className = 'veditor-btn veditor-preset-btn';
            if (p.value === current) btn.classList.add('active');
            btn.textContent = p.label;
            btn.title = p.value;
            btn.setAttribute('data-tool-id', `veditor-compose-${prefix}-pos-${p.value}`);
            btn.addEventListener('click', () => {
                row.querySelectorAll('.veditor-preset-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                onChange(p.value);
            });
            row.appendChild(btn);
        });

        return row;
    }
}
