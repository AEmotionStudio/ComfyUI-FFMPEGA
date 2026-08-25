/**
 * FiltersPanel — One-click cinematic filter presets for the NLE Video Editor.
 *
 * Displays a scrollable grid of preset cards with labels and color swatches.
 * Includes an intensity slider (0–100%) for blending the effect.
 *
 * Follows the same pattern as AudioMixer.ts / SpeedControl.ts / ColorGradingPanel.ts:
 * - `element` getter returns the root div
 * - Callbacks fire on selection changes
 * - State is serializable via `getState()` / `loadState()`
 */

import { iconShuffle } from './icons';

export interface FilterPresetState {
    preset: string;     // preset key or "none"
    intensity: number;  // 0–1
}

export interface FiltersCallbacks {
    onFilterChanged: (state: FilterPresetState) => void;
}

interface PresetDef {
    key: string;
    label: string;
    /** Approximate CSS filter for swatch/preview — not pixel-accurate. */
    css: string;
    /** Accent color for the swatch border when selected. */
    color: string;
}

const PRESETS: PresetDef[] = [
    { key: 'none',          label: 'None',          css: 'none',                                              color: '#888' },
    { key: 'cinematic',     label: 'Cinematic',     css: 'saturate(0.7) contrast(1.2) brightness(0.95)',      color: '#6366f1' },
    { key: 'vintage',       label: 'Vintage',       css: 'saturate(0.6) contrast(1.1) sepia(0.2)',            color: '#d4a574' },
    { key: 'noir',          label: 'Noir',          css: 'saturate(0) contrast(1.3) brightness(0.9)',         color: '#555' },
    { key: 'cyberpunk',     label: 'Cyberpunk',     css: 'saturate(1.6) contrast(1.3) hue-rotate(10deg)',     color: '#00e5ff' },
    { key: 'lofi',          label: 'Lo-Fi',         css: 'saturate(0.5) contrast(0.9) brightness(1.1)',       color: '#e8b4b8' },
    { key: 'sepia',         label: 'Sepia',         css: 'sepia(1)',                                          color: '#c49a6c' },
    { key: 'bleach_bypass', label: 'Bleach Bypass', css: 'saturate(0.4) contrast(1.5) brightness(0.95)',      color: '#b0b0b0' },
    { key: 'dream',         label: 'Dream',         css: 'blur(1px) brightness(1.15) saturate(0.8)',          color: '#c084fc' },
    { key: 'film_grain',    label: 'Film Grain',    css: 'saturate(0.85) contrast(1.1)',                      color: '#a0826d' },
    { key: 'b_and_w',       label: 'B&W',           css: 'saturate(0) contrast(1.1)',                         color: '#999' },
    { key: 'warm',          label: 'Warm',          css: 'sepia(0.15) saturate(1.1)',                         color: '#f59e0b' },
    { key: 'cool',          label: 'Cool',          css: 'hue-rotate(-10deg) saturate(1.05) brightness(0.97)',color: '#3b82f6' },
    { key: 'neon',          label: 'Neon',          css: 'saturate(3) brightness(1.1)',                       color: '#22d3ee' },
    { key: 'comic_book',    label: 'Comic Book',    css: 'saturate(1.5) contrast(1.3)',                       color: '#ef4444' },
    { key: 'thermal',       label: 'Thermal',       css: 'hue-rotate(180deg) saturate(2)',                    color: '#ff5722' },
];

export class FiltersPanel {
    private container: HTMLDivElement;
    private callbacks: FiltersCallbacks;
    private selectedKey: string = 'none';
    private intensity: number = 1.0;
    private cards: Map<string, HTMLDivElement> = new Map();
    private intensitySlider!: HTMLInputElement;
    private intensityLabel!: HTMLSpanElement;

    constructor(callbacks: FiltersCallbacks) {
        this.callbacks = callbacks;

        this.container = document.createElement('div');
        this.container.className = 'veditor-filters-panel';
        this.container.setAttribute('data-tool-id', 'veditor-filters-panel');
        this.container.setAttribute('aria-label', 'Filter preset controls');

        // ── Preset Grid ──
        const grid = document.createElement('div');
        grid.className = 'veditor-filter-grid';

        for (const preset of PRESETS) {
            const card = this._makeCard(preset);
            grid.appendChild(card);
            this.cards.set(preset.key, card);
        }

        // ── Intensity Section ──
        const intensitySection = document.createElement('div');
        intensitySection.className = 'veditor-panel-section veditor-filter-intensity-section';

        const intensityHeader = document.createElement('div');
        intensityHeader.className = 'veditor-section-label';
        intensityHeader.textContent = 'Intensity';

        const intensityRow = document.createElement('div');
        intensityRow.className = 'veditor-control-row';

        this.intensitySlider = document.createElement('input');
        this.intensitySlider.type = 'range';
        this.intensitySlider.min = '0';
        this.intensitySlider.max = '100';
        this.intensitySlider.step = '1';
        this.intensitySlider.value = '100';
        this.intensitySlider.className = 'veditor-grading-slider';
        this.intensitySlider.setAttribute('data-tool-id', 'veditor-filter-intensity');
        this.intensitySlider.setAttribute('aria-label', 'Filter intensity (0 to 100%)');

        this.intensityLabel = document.createElement('span');
        this.intensityLabel.className = 'veditor-grading-value';
        this.intensityLabel.textContent = '100%';

        this.intensitySlider.addEventListener('input', () => {
            this.intensity = parseInt(this.intensitySlider.value, 10) / 100;
            this.intensityLabel.textContent = `${Math.round(this.intensity * 100)}%`;
            this.callbacks.onFilterChanged(this.getState());
        });

        intensityRow.append(this.intensitySlider, this.intensityLabel);
        intensitySection.append(intensityHeader, intensityRow);

        this.container.append(grid, intensitySection);

        // Mark "none" as initially selected
        this._selectCard('none');
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    getState(): FilterPresetState {
        return {
            preset: this.selectedKey,
            intensity: this.intensity,
        };
    }

    loadState(state: Partial<FilterPresetState>): void {
        if (state.preset !== undefined) {
            this._selectCard(state.preset);
        }
        if (state.intensity !== undefined) {
            this.intensity = state.intensity;
            this.intensitySlider.value = String(Math.round(this.intensity * 100));
            this.intensityLabel.textContent = `${Math.round(this.intensity * 100)}%`;
        }
    }

    reset(): void {
        this._selectCard('none');
        this.intensity = 1.0;
        this.intensitySlider.value = '100';
        this.intensityLabel.textContent = '100%';
    }

    /**
     * Build CSS filter string for live preview approximation.
     * Blends with the selected preset's CSS using opacity scaling.
     */
    getCSSFilter(): string {
        if (this.selectedKey === 'none') return 'none';
        const preset = PRESETS.find(p => p.key === this.selectedKey);
        if (!preset || preset.css === 'none') return 'none';
        // CSS filters don't support opacity blending natively,
        // so we return the full effect. The video opacity can be
        // approximated by compositing, but for simplicity we just
        // apply the full CSS filter.
        return preset.css;
    }

    destroy(): void {
        this.container.remove();
    }

    // ── Private ──────────────────────────────────────────────────

    private _makeCard(preset: PresetDef): HTMLDivElement {
        const card = document.createElement('div');
        card.className = 'veditor-filter-card';
        card.setAttribute('data-tool-id', `veditor-filter-${preset.key}`);
        card.setAttribute('aria-label', `Filter: ${preset.label}`);
        card.title = preset.label;

        // Color swatch
        const swatch = document.createElement('div');
        swatch.className = 'veditor-filter-swatch';
        if (preset.key !== 'none') {
            swatch.style.filter = preset.css;
            swatch.style.borderColor = preset.color;
        }

        // Label
        const label = document.createElement('span');
        label.className = 'veditor-filter-label';
        label.textContent = preset.label;

        card.append(swatch, label);

        card.addEventListener('click', () => {
            this._selectCard(preset.key);
            this.callbacks.onFilterChanged(this.getState());
        });

        return card;
    }

    private _selectCard(key: string): void {
        this.selectedKey = key;
        for (const [k, card] of this.cards) {
            card.classList.toggle('active', k === key);
        }
    }
}
