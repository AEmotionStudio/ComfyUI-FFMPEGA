/**
 * ColorGradingPanel — brightness, contrast, saturation, exposure, gamma,
 * color balance, and white balance controls for the NLE Video Editor.
 *
 * Follows the same pattern as AudioMixer.ts and SpeedControl.ts:
 * - Self-contained DOM construction in the constructor
 * - `element` getter returns the root div
 * - Callbacks fire on every slider change (for undo/live preview)
 * - State is serializable via `getState()` / `loadState()`
 */

import { iconPalette } from './icons';

export interface ColorGradingState {
    brightness: number;   // -1 to +1, default 0
    contrast: number;     // 0 to 3, default 1
    saturation: number;   // 0 to 3, default 1
    exposure: number;     // -3 to +3, default 0
    gamma: number;        // 0.1 to 4, default 1
    shadows_r: number;    // -1 to +1, default 0
    shadows_g: number;
    shadows_b: number;
    midtones_r: number;
    midtones_g: number;
    midtones_b: number;
    temperature: number;  // 2000 to 12000, default 6500
}

export interface ColorGradingCallbacks {
    onGradingChanged: (state: ColorGradingState) => void;
}

const DEFAULTS: ColorGradingState = {
    brightness: 0,
    contrast: 1,
    saturation: 1,
    exposure: 0,
    gamma: 1,
    shadows_r: 0,
    shadows_g: 0,
    shadows_b: 0,
    midtones_r: 0,
    midtones_g: 0,
    midtones_b: 0,
    temperature: 6500,
};

interface SliderDef {
    key: keyof ColorGradingState;
    label: string;
    min: number;
    max: number;
    step: number;
    default: number;
    format: (v: number) => string;
}

const EXPOSURE_SLIDERS: SliderDef[] = [
    { key: 'brightness', label: 'Brightness', min: -1, max: 1, step: 0.02, default: 0, format: v => v >= 0 ? `+${v.toFixed(2)}` : v.toFixed(2) },
    { key: 'contrast', label: 'Contrast', min: 0, max: 3, step: 0.02, default: 1, format: v => v.toFixed(2) },
    { key: 'saturation', label: 'Saturation', min: 0, max: 3, step: 0.02, default: 1, format: v => v.toFixed(2) },
    { key: 'exposure', label: 'Exposure', min: -3, max: 3, step: 0.05, default: 0, format: v => `${v >= 0 ? '+' : ''}${v.toFixed(2)} EV` },
    { key: 'gamma', label: 'Gamma', min: 0.1, max: 4, step: 0.02, default: 1, format: v => v.toFixed(2) },
];

const SHADOW_SLIDERS: SliderDef[] = [
    { key: 'shadows_r', label: 'Red', min: -1, max: 1, step: 0.02, default: 0, format: v => v >= 0 ? `+${v.toFixed(2)}` : v.toFixed(2) },
    { key: 'shadows_g', label: 'Green', min: -1, max: 1, step: 0.02, default: 0, format: v => v >= 0 ? `+${v.toFixed(2)}` : v.toFixed(2) },
    { key: 'shadows_b', label: 'Blue', min: -1, max: 1, step: 0.02, default: 0, format: v => v >= 0 ? `+${v.toFixed(2)}` : v.toFixed(2) },
];

const MIDTONE_SLIDERS: SliderDef[] = [
    { key: 'midtones_r', label: 'Red', min: -1, max: 1, step: 0.02, default: 0, format: v => v >= 0 ? `+${v.toFixed(2)}` : v.toFixed(2) },
    { key: 'midtones_g', label: 'Green', min: -1, max: 1, step: 0.02, default: 0, format: v => v >= 0 ? `+${v.toFixed(2)}` : v.toFixed(2) },
    { key: 'midtones_b', label: 'Blue', min: -1, max: 1, step: 0.02, default: 0, format: v => v >= 0 ? `+${v.toFixed(2)}` : v.toFixed(2) },
];

export class ColorGradingPanel {
    private container: HTMLDivElement;
    private callbacks: ColorGradingCallbacks;
    private sliders: Map<keyof ColorGradingState, HTMLInputElement> = new Map();
    private labels: Map<keyof ColorGradingState, HTMLSpanElement> = new Map();
    private defs: Map<keyof ColorGradingState, SliderDef> = new Map();

    constructor(callbacks: ColorGradingCallbacks) {
        this.callbacks = callbacks;

        this.container = document.createElement('div');
        this.container.className = 'veditor-color-grading';
        this.container.setAttribute('data-tool-id', 'veditor-color-grading');
        this.container.setAttribute('aria-label', 'Color grading controls');

        // ── Tone Section ──
        const toneSection = this._makeSection('Tone & Exposure');
        this._buildSliders(toneSection, EXPOSURE_SLIDERS);

        // ── Color Balance: Shadows ──
        const shadowSection = this._makeSection('Shadows');
        this._buildSliders(shadowSection, SHADOW_SLIDERS);

        // ── Color Balance: Midtones ──
        const midtoneSection = this._makeSection('Midtones');
        this._buildSliders(midtoneSection, MIDTONE_SLIDERS);

        // ── White Balance ──
        const wbSection = this._makeSection('White Balance');
        const tempDef: SliderDef = {
            key: 'temperature',
            label: 'Temperature',
            min: 2000,
            max: 12000,
            step: 100,
            default: 6500,
            format: v => `${Math.round(v)}K`,
        };
        this._buildSliders(wbSection, [tempDef]);

        // Add warm/cool labels
        const wbHint = document.createElement('div');
        wbHint.className = 'veditor-control-row';
        wbHint.style.justifyContent = 'space-between';
        wbHint.style.fontSize = '9px';
        wbHint.style.color = 'var(--ve-text-dim)';
        wbHint.style.marginTop = '-2px';
        wbHint.innerHTML = '<span style="color:#ff9955">🔥 Warm</span><span style="color:#5599ff">❄️ Cool</span>';
        wbSection.appendChild(wbHint);

        // ── Reset Button ──
        const resetRow = document.createElement('div');
        resetRow.className = 'veditor-control-row';

        const resetBtn = document.createElement('button');
        resetBtn.className = 'veditor-btn veditor-toggle-btn';
        resetBtn.innerHTML = `${iconPalette} Reset Color`;
        resetBtn.title = 'Reset all color grading to defaults';
        resetBtn.setAttribute('data-tool-id', 'veditor-color-reset');
        resetBtn.setAttribute('aria-label', 'Reset color grading settings');
        resetBtn.addEventListener('click', () => {
            this.reset();
            this.callbacks.onGradingChanged(this.getState());
        });
        resetRow.appendChild(resetBtn);

        this.container.append(toneSection, shadowSection, midtoneSection, wbSection, resetRow);
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    /** Get the current state for serialization / undo. */
    getState(): ColorGradingState {
        const state = { ...DEFAULTS };
        for (const [key, slider] of this.sliders) {
            (state as Record<string, number>)[key] = parseFloat(slider.value);
        }
        return state;
    }

    /** Load state (from undo restore or initial widget data). */
    loadState(state: Partial<ColorGradingState>): void {
        for (const [key, def] of this.defs) {
            const val = state[key] ?? def.default;
            const slider = this.sliders.get(key);
            const label = this.labels.get(key);
            if (slider) slider.value = String(val);
            if (label) label.textContent = def.format(val);
        }
    }

    /** Reset all controls to defaults. */
    reset(): void {
        this.loadState(DEFAULTS);
    }

    /**
     * Build CSS filter string for live preview approximation.
     * Not pixel-accurate with FFmpeg, but gives immediate visual feedback.
     */
    getCSSFilter(): string {
        const s = this.getState();
        const parts: string[] = [];

        // brightness: CSS uses 1.0 = no change, FFmpeg uses 0 = no change
        if (Math.abs(s.brightness) > 0.01) {
            parts.push(`brightness(${1 + s.brightness})`);
        }
        if (Math.abs(s.contrast - 1) > 0.01) {
            parts.push(`contrast(${s.contrast})`);
        }
        if (Math.abs(s.saturation - 1) > 0.01) {
            parts.push(`saturate(${s.saturation})`);
        }
        // Exposure → approximate as brightness boost
        if (Math.abs(s.exposure) > 0.01) {
            parts.push(`brightness(${1 + s.exposure * 0.1})`);
        }
        // Temperature → approximate with sepia + hue-rotate
        if (Math.abs(s.temperature - 6500) > 100) {
            const warmth = (s.temperature - 6500) / 5500; // -1 to +1
            if (warmth > 0) {
                parts.push(`sepia(${(warmth * 0.15).toFixed(3)})`);
            } else {
                parts.push(`hue-rotate(${(warmth * 15).toFixed(1)}deg)`);
            }
        }

        return parts.length > 0 ? parts.join(' ') : 'none';
    }

    destroy(): void {
        this.container.remove();
    }

    // ── Private ──────────────────────────────────────────────────

    private _buildSliders(section: HTMLDivElement, defs: SliderDef[]): void {
        for (const def of defs) {
            this.defs.set(def.key, def);

            const row = document.createElement('div');
            row.className = 'veditor-control-row veditor-grading-row';

            const labelEl = document.createElement('span');
            labelEl.className = 'veditor-grading-label';
            labelEl.textContent = def.label;

            const slider = document.createElement('input');
            slider.type = 'range';
            slider.min = String(def.min);
            slider.max = String(def.max);
            slider.step = String(def.step);
            slider.value = String(def.default);
            slider.className = 'veditor-grading-slider';
            slider.setAttribute('data-tool-id', `veditor-grading-${def.key}`);
            slider.setAttribute('aria-label', `${def.label} (${def.min} to ${def.max})`);

            const valueEl = document.createElement('span');
            valueEl.className = 'veditor-grading-value';
            valueEl.textContent = def.format(def.default);

            slider.addEventListener('input', () => {
                const val = parseFloat(slider.value);
                valueEl.textContent = def.format(val);
                this.callbacks.onGradingChanged(this.getState());
            });

            // Double-click to reset individual slider
            slider.addEventListener('dblclick', () => {
                slider.value = String(def.default);
                valueEl.textContent = def.format(def.default);
                this.callbacks.onGradingChanged(this.getState());
            });

            this.sliders.set(def.key, slider);
            this.labels.set(def.key, valueEl);

            row.append(labelEl, slider, valueEl);
            section.appendChild(row);
        }
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
}
