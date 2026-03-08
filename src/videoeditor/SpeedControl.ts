/**
 * SpeedControl — per-segment speed control with presets, reverse,
 * speed curve, and frame interpolation options.
 *
 * Range: 0.1x → 8.0x. Presets: 0.25x, 0.5x, 0.75x, 1x, 1.5x, 2x, 4x.
 */

import { iconGauge, iconReverse, iconCurve, iconFilm } from './icons';

export type SpeedCurve = 'linear' | 'ease-in' | 'ease-out' | 'ease-in-out';

export interface SpeedControlCallbacks {
    onSpeedChanged: (segmentIndex: number, speed: number) => void;
    onReverseChanged?: (segmentIndex: number, reversed: boolean) => void;
    onCurveChanged?: (segmentIndex: number, curve: SpeedCurve) => void;
    onInterpolationChanged?: (enabled: boolean) => void;
}

export class SpeedControl {
    private container: HTMLDivElement;
    private callbacks: SpeedControlCallbacks;
    private slider: HTMLInputElement;
    private speedInput: HTMLInputElement;
    private label: HTMLSpanElement;
    private reverseBtn: HTMLButtonElement;
    private curveSelect: HTMLSelectElement;
    private interpToggle: HTMLInputElement;
    private currentSegment: number = 0;
    private speedMap: Map<number, number> = new Map();
    private reverseMap: Map<number, boolean> = new Map();
    private curveMap: Map<number, SpeedCurve> = new Map();
    private _interpolation = false;

    constructor(callbacks: SpeedControlCallbacks) {
        this.callbacks = callbacks;

        this.container = document.createElement('div');
        this.container.className = 'veditor-speed';
        this.container.setAttribute('data-tool-id', 'veditor-speed-control');
        this.container.setAttribute('aria-label', 'Playback speed controls');

        // ── Speed Section ──
        const speedSection = this._makeSection('Speed');

        const sliderRow = document.createElement('div');
        sliderRow.className = 'veditor-control-row';

        this.slider = document.createElement('input');
        this.slider.type = 'range';
        this.slider.min = '0.1';
        this.slider.max = '8';
        this.slider.step = '0.05';
        this.slider.value = '1';
        this.slider.className = 'veditor-speed-slider';
        this.slider.setAttribute('data-tool-id', 'veditor-speed-slider');
        this.slider.setAttribute('aria-label', 'Playback speed (0.1x to 8x)');
        this.slider.addEventListener('input', () => this._onSliderChange());

        this.speedInput = document.createElement('input');
        this.speedInput.type = 'number';
        this.speedInput.className = 'veditor-input veditor-speed-input';
        this.speedInput.min = '0.1';
        this.speedInput.max = '8';
        this.speedInput.step = '0.05';
        this.speedInput.value = '1.00';
        this.speedInput.setAttribute('data-tool-id', 'veditor-speed-input');
        this.speedInput.setAttribute('aria-label', 'Speed value');
        this.speedInput.addEventListener('change', () => {
            const val = Math.max(0.1, Math.min(8, parseFloat(this.speedInput.value) || 1));
            this.slider.value = String(val);
            this._setSpeed(val);
        });

        this.label = document.createElement('span');
        this.label.className = 'veditor-speed-value';
        this.label.textContent = '1.00x';

        sliderRow.append(this.slider, this.speedInput);

        // Preset buttons
        const presetRow = document.createElement('div');
        presetRow.className = 'veditor-preset-row';

        const presets = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 4.0];
        presets.forEach(p => {
            const btn = document.createElement('button');
            btn.className = 'veditor-btn veditor-preset-btn';
            btn.textContent = `${p}x`;
            btn.title = `Set speed to ${p}x`;
            btn.setAttribute('data-tool-id', `veditor-speed-preset-${String(p).replace('.', '')}`);
            btn.setAttribute('aria-label', `Set speed to ${p}x`);
            btn.addEventListener('click', () => {
                this.slider.value = String(p);
                this.speedInput.value = p.toFixed(2);
                this._setSpeed(p);
            });
            presetRow.appendChild(btn);
        });

        speedSection.append(sliderRow, presetRow);

        // ── Reverse Section ──
        const reverseSection = this._makeSection('Reverse');

        this.reverseBtn = document.createElement('button');
        this.reverseBtn.className = 'veditor-btn veditor-toggle-btn';
        this.reverseBtn.innerHTML = `${iconReverse} Reversed`;
        this.reverseBtn.title = 'Toggle reverse playback';
        this.reverseBtn.setAttribute('data-tool-id', 'veditor-speed-reverse');
        this.reverseBtn.setAttribute('aria-label', 'Toggle reverse playback');
        this.reverseBtn.setAttribute('aria-pressed', 'false');
        this.reverseBtn.addEventListener('click', () => this._toggleReverse());

        reverseSection.appendChild(this.reverseBtn);

        // ── Speed Curve Section ──
        const curveSection = this._makeSection('Speed Curve');

        const curveRow = document.createElement('div');
        curveRow.className = 'veditor-control-row';

        const curveIcon = document.createElement('span');
        curveIcon.innerHTML = iconCurve;
        curveIcon.className = 'veditor-control-icon';

        this.curveSelect = document.createElement('select');
        this.curveSelect.className = 'veditor-select';
        this.curveSelect.setAttribute('data-tool-id', 'veditor-speed-curve');
        this.curveSelect.setAttribute('aria-label', 'Speed curve type');
        const curves: { val: SpeedCurve; label: string }[] = [
            { val: 'linear', label: 'Linear' },
            { val: 'ease-in', label: 'Ease In' },
            { val: 'ease-out', label: 'Ease Out' },
            { val: 'ease-in-out', label: 'Ease In-Out' },
        ];
        curves.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.val;
            opt.textContent = c.label;
            this.curveSelect.appendChild(opt);
        });
        this.curveSelect.addEventListener('change', () => {
            const curve = this.curveSelect.value as SpeedCurve;
            this.curveMap.set(this.currentSegment, curve);
            this.callbacks.onCurveChanged?.(this.currentSegment, curve);
        });

        curveRow.append(curveIcon, this.curveSelect);
        curveSection.appendChild(curveRow);

        // ── Frame Interpolation Section ──
        const interpSection = this._makeSection('Frame Interpolation');

        const interpRow = document.createElement('div');
        interpRow.className = 'veditor-control-row';

        const interpIcon = document.createElement('span');
        interpIcon.innerHTML = iconFilm;
        interpIcon.className = 'veditor-control-icon';

        const interpLabel = document.createElement('label');
        interpLabel.className = 'veditor-toggle-label';
        interpLabel.textContent = 'Enable smooth slow-motion';

        this.interpToggle = document.createElement('input');
        this.interpToggle.type = 'checkbox';
        this.interpToggle.className = 'veditor-checkbox';
        this.interpToggle.setAttribute('data-tool-id', 'veditor-speed-interpolation');
        this.interpToggle.setAttribute('aria-label', 'Enable frame interpolation for smooth slow-motion');
        this.interpToggle.addEventListener('change', () => {
            this._interpolation = this.interpToggle.checked;
            this.callbacks.onInterpolationChanged?.(this._interpolation);
        });

        interpRow.append(interpIcon, interpLabel, this.interpToggle);
        interpSection.appendChild(interpRow);

        this.container.append(speedSection, reverseSection, curveSection, interpSection);
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    /** Switch context to a different segment. */
    setActiveSegment(index: number): void {
        this.currentSegment = index;
        const speed = this.speedMap.get(index) ?? 1.0;
        this.slider.value = String(speed);
        this.speedInput.value = speed.toFixed(2);
        this.label.textContent = `${speed.toFixed(2)}x`;

        const reversed = this.reverseMap.get(index) ?? false;
        this.reverseBtn.classList.toggle('active', reversed);
        this.reverseBtn.setAttribute('aria-pressed', String(reversed));

        const curve = this.curveMap.get(index) ?? 'linear';
        this.curveSelect.value = curve;
    }

    /** Get the full speed map as a JSON-suitable object. */
    getSpeedMap(): Record<string, number> {
        const result: Record<string, number> = {};
        for (const [idx, speed] of this.speedMap) {
            if (Math.abs(speed - 1.0) > 0.01) {
                result[String(idx)] = speed;
            }
        }
        return result;
    }

    /** Load speed map from a parsed object. */
    loadSpeedMap(map: Record<string, number>): void {
        this.speedMap.clear();
        for (const [key, val] of Object.entries(map)) {
            this.speedMap.set(parseInt(key, 10), val);
        }
        this.setActiveSegment(this.currentSegment);
    }

    /** Check if frame interpolation is enabled */
    get interpolation(): boolean {
        return this._interpolation;
    }

    /** Reset all speeds to 1x. */
    reset(): void {
        this.speedMap.clear();
        this.reverseMap.clear();
        this.curveMap.clear();
        this._interpolation = false;
        this.interpToggle.checked = false;
        this.slider.value = '1';
        this.speedInput.value = '1.00';
        this.label.textContent = '1.00x';
        this.reverseBtn.classList.remove('active');
        this.reverseBtn.setAttribute('aria-pressed', 'false');
        this.curveSelect.value = 'linear';
    }

    destroy(): void {
        this.container.remove();
    }

    // ── Private ──────────────────────────────────────────────────

    private _setSpeed(speed: number): void {
        this.speedMap.set(this.currentSegment, speed);
        this.label.textContent = `${speed.toFixed(2)}x`;
        this.callbacks.onSpeedChanged(this.currentSegment, speed);
    }

    private _onSliderChange(): void {
        const speed = parseFloat(this.slider.value);
        this.speedInput.value = speed.toFixed(2);
        this._setSpeed(speed);
    }

    private _toggleReverse(): void {
        const current = this.reverseMap.get(this.currentSegment) ?? false;
        const next = !current;
        this.reverseMap.set(this.currentSegment, next);
        this.reverseBtn.classList.toggle('active', next);
        this.reverseBtn.setAttribute('aria-pressed', String(next));
        this.callbacks.onReverseChanged?.(this.currentSegment, next);
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
