/**
 * AudioMixer — volume control with mute, fade in/out, and EQ presets.
 */

import { iconVolume, iconMuted, iconMusic } from './icons';

export type EQPreset = 'flat' | 'voice' | 'music' | 'bass-boost';

export interface AudioMixerCallbacks {
    onVolumeChanged: (volume: number) => void;
    onFadeInChanged?: (seconds: number) => void;
    onFadeOutChanged?: (seconds: number) => void;
    onEQChanged?: (preset: EQPreset) => void;
}

export class AudioMixer {
    private container: HTMLDivElement;
    private callbacks: AudioMixerCallbacks;
    private slider: HTMLInputElement;
    private label: HTMLSpanElement;
    private muteBtn: HTMLButtonElement;
    private fadeInSlider: HTMLInputElement;
    private fadeInLabel: HTMLSpanElement;
    private fadeOutSlider: HTMLInputElement;
    private fadeOutLabel: HTMLSpanElement;
    private eqSelect: HTMLSelectElement;
    private isMuted: boolean = false;
    private lastVolume: number = 1.0;

    constructor(callbacks: AudioMixerCallbacks) {
        this.callbacks = callbacks;

        this.container = document.createElement('div');
        this.container.className = 'veditor-audio';
        this.container.setAttribute('data-tool-id', 'veditor-audio-mixer');
        this.container.setAttribute('aria-label', 'Audio controls');

        // ── Volume Section ──
        const volSection = this._makeSection('Volume');

        const volRow = document.createElement('div');
        volRow.className = 'veditor-control-row';

        this.muteBtn = document.createElement('button');
        this.muteBtn.className = 'veditor-btn veditor-mute-btn';
        this.muteBtn.innerHTML = iconVolume;
        this.muteBtn.title = 'Mute / Unmute (M)';
        this.muteBtn.setAttribute('data-tool-id', 'veditor-mute-btn');
        this.muteBtn.setAttribute('aria-label', 'Mute / Unmute audio (M)');
        this.muteBtn.addEventListener('click', () => this._toggleMute());

        this.slider = document.createElement('input');
        this.slider.type = 'range';
        this.slider.min = '0';
        this.slider.max = '2';
        this.slider.step = '0.05';
        this.slider.value = '1';
        this.slider.className = 'veditor-volume-slider';
        this.slider.setAttribute('data-tool-id', 'veditor-volume-slider');
        this.slider.setAttribute('aria-label', 'Volume level (0% to 200%)');
        this.slider.addEventListener('input', () => {
            const vol = parseFloat(this.slider.value);
            this.lastVolume = vol;
            this.isMuted = vol < 0.01;
            this.muteBtn.innerHTML = this.isMuted ? iconMuted : iconVolume;
            this.label.textContent = `${Math.round(vol * 100)}%`;
            this.callbacks.onVolumeChanged(vol);
        });

        this.label = document.createElement('span');
        this.label.className = 'veditor-volume-label';
        this.label.textContent = '100%';
        this.label.setAttribute('data-tool-id', 'veditor-volume-label');

        volRow.append(this.muteBtn, this.slider, this.label);
        volSection.appendChild(volRow);

        // ── Fade In Section ──
        const fadeInSection = this._makeSection('Fade In');

        const fadeInRow = document.createElement('div');
        fadeInRow.className = 'veditor-control-row';

        this.fadeInSlider = document.createElement('input');
        this.fadeInSlider.type = 'range';
        this.fadeInSlider.min = '0';
        this.fadeInSlider.max = '5';
        this.fadeInSlider.step = '0.1';
        this.fadeInSlider.value = '0';
        this.fadeInSlider.className = 'veditor-fade-slider';
        this.fadeInSlider.setAttribute('data-tool-id', 'veditor-fade-in-slider');
        this.fadeInSlider.setAttribute('aria-label', 'Audio fade in duration (0 to 5 seconds)');
        this.fadeInSlider.addEventListener('input', () => {
            const val = parseFloat(this.fadeInSlider.value);
            this.fadeInLabel.textContent = `${val.toFixed(1)}s`;
            this.callbacks.onFadeInChanged?.(val);
        });

        this.fadeInLabel = document.createElement('span');
        this.fadeInLabel.className = 'veditor-fade-label';
        this.fadeInLabel.textContent = '0.0s';
        this.fadeInLabel.setAttribute('data-tool-id', 'veditor-fade-in-label');

        fadeInRow.append(this.fadeInSlider, this.fadeInLabel);
        fadeInSection.appendChild(fadeInRow);

        // ── Fade Out Section ──
        const fadeOutSection = this._makeSection('Fade Out');

        const fadeOutRow = document.createElement('div');
        fadeOutRow.className = 'veditor-control-row';

        this.fadeOutSlider = document.createElement('input');
        this.fadeOutSlider.type = 'range';
        this.fadeOutSlider.min = '0';
        this.fadeOutSlider.max = '5';
        this.fadeOutSlider.step = '0.1';
        this.fadeOutSlider.value = '0';
        this.fadeOutSlider.className = 'veditor-fade-slider';
        this.fadeOutSlider.setAttribute('data-tool-id', 'veditor-fade-out-slider');
        this.fadeOutSlider.setAttribute('aria-label', 'Audio fade out duration (0 to 5 seconds)');
        this.fadeOutSlider.addEventListener('input', () => {
            const val = parseFloat(this.fadeOutSlider.value);
            this.fadeOutLabel.textContent = `${val.toFixed(1)}s`;
            this.callbacks.onFadeOutChanged?.(val);
        });

        this.fadeOutLabel = document.createElement('span');
        this.fadeOutLabel.className = 'veditor-fade-label';
        this.fadeOutLabel.textContent = '0.0s';
        this.fadeOutLabel.setAttribute('data-tool-id', 'veditor-fade-out-label');

        fadeOutRow.append(this.fadeOutSlider, this.fadeOutLabel);
        fadeOutSection.appendChild(fadeOutRow);

        // ── EQ Preset Section ──
        const eqSection = this._makeSection('EQ Preset');

        const eqRow = document.createElement('div');
        eqRow.className = 'veditor-control-row';

        const eqIcon = document.createElement('span');
        eqIcon.innerHTML = iconMusic;
        eqIcon.className = 'veditor-control-icon';

        this.eqSelect = document.createElement('select');
        this.eqSelect.className = 'veditor-select';
        this.eqSelect.setAttribute('data-tool-id', 'veditor-eq-preset');
        this.eqSelect.setAttribute('aria-label', 'Audio EQ preset');
        const eqPresets: { val: EQPreset; label: string }[] = [
            { val: 'flat', label: 'Flat (No EQ)' },
            { val: 'voice', label: 'Voice Enhancement' },
            { val: 'music', label: 'Music' },
            { val: 'bass-boost', label: 'Bass Boost' },
        ];
        eqPresets.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.val;
            opt.textContent = p.label;
            this.eqSelect.appendChild(opt);
        });
        this.eqSelect.addEventListener('change', () => {
            this.callbacks.onEQChanged?.(this.eqSelect.value as EQPreset);
        });

        eqRow.append(eqIcon, this.eqSelect);
        eqSection.appendChild(eqRow);

        this.container.append(volSection, fadeInSection, fadeOutSection, eqSection);
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    getVolume(): number {
        return this.isMuted ? 0 : parseFloat(this.slider.value);
    }

    setVolume(volume: number): void {
        this.slider.value = String(volume);
        this.lastVolume = volume;
        this.isMuted = volume < 0.01;
        this.muteBtn.innerHTML = this.isMuted ? iconMuted : iconVolume;
        this.label.textContent = `${Math.round(volume * 100)}%`;
    }

    getFadeIn(): number {
        return parseFloat(this.fadeInSlider.value);
    }

    getFadeOut(): number {
        return parseFloat(this.fadeOutSlider.value);
    }

    getEQPreset(): EQPreset {
        return this.eqSelect.value as EQPreset;
    }

    destroy(): void {
        this.container.remove();
    }

    // ── Private ──────────────────────────────────────────────────

    private _toggleMute(): void {
        this.isMuted = !this.isMuted;
        if (this.isMuted) {
            this.lastVolume = parseFloat(this.slider.value);
            this.slider.value = '0';
            this.muteBtn.innerHTML = iconMuted;
            this.label.textContent = '0%';
            this.callbacks.onVolumeChanged(0);
        } else {
            this.slider.value = String(this.lastVolume);
            this.muteBtn.innerHTML = iconVolume;
            this.label.textContent = `${Math.round(this.lastVolume * 100)}%`;
            this.callbacks.onVolumeChanged(this.lastVolume);
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
