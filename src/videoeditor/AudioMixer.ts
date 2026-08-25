/**
 * AudioMixer — volume control with mute, fade in/out, and EQ presets.
 */

import { iconVolume, iconMuted, iconMusic } from './icons';
import type { AudioSegment } from './AudioSegment';

export type EQPreset = 'flat' | 'voice' | 'music' | 'bass-boost';

export interface AudioMixerCallbacks {
    onVolumeChanged: (volume: number) => void;
    onFadeInChanged?: (seconds: number) => void;
    onFadeOutChanged?: (seconds: number) => void;
    onEQChanged?: (preset: EQPreset) => void;
    onAceRepaintChanged?: (active: boolean) => void;
    onAceRepaintStrengthChanged?: (strength: number) => void;
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
    /** Dedicated master volume — persists independently of per-segment editing */
    private _masterVolume: number = 1.0;
    private segmentHeader: HTMLDivElement;
    private _selectedSegIndex: number = -1;
    private aceRepaintBtn: HTMLButtonElement;
    private aceStrengthSlider: HTMLInputElement;
    private aceStrengthLabel: HTMLSpanElement;
    private _aceRepaintActive: boolean = false;

    constructor(callbacks: AudioMixerCallbacks) {
        this.callbacks = callbacks;

        this.container = document.createElement('div');
        this.container.className = 'veditor-audio';
        this.container.setAttribute('data-tool-id', 'veditor-audio-mixer');
        this.container.setAttribute('aria-label', 'Audio controls');

        // ── Segment Header ──
        this.segmentHeader = document.createElement('div');
        this.segmentHeader.className = 'veditor-section-label';
        this.segmentHeader.textContent = 'Master Audio';
        this.segmentHeader.style.marginBottom = '8px';
        this.segmentHeader.style.textTransform = 'none';
        this.segmentHeader.style.letterSpacing = 'normal';
        this.segmentHeader.style.fontWeight = '500';
        this.segmentHeader.style.color = 'var(--ve-text-primary)';
        this.container.appendChild(this.segmentHeader);

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

        // ── ACE-Step Repaint Section ──
        const aceSection = this._makeSection('ACE-Step Repaint');
        aceSection.setAttribute('data-tool-id', 'veditor-ace-repaint-section');
        aceSection.title = 'Mark this audio segment for ACE-Step quality enhancement';

        const aceRow = document.createElement('div');
        aceRow.className = 'veditor-control-row';

        this.aceRepaintBtn = document.createElement('button');
        this.aceRepaintBtn.className = 'veditor-btn veditor-toggle-btn';
        this.aceRepaintBtn.textContent = '🎵 Repaint Off';
        this.aceRepaintBtn.title = 'Toggle ACE-Step repaint for this segment';
        this.aceRepaintBtn.setAttribute('data-tool-id', 'veditor-ace-repaint-toggle');
        this.aceRepaintBtn.setAttribute('aria-label', 'Toggle ACE-Step audio repaint');
        this.aceRepaintBtn.addEventListener('click', () => {
            this._aceRepaintActive = !this._aceRepaintActive;
            this._updateAceRepaintBtn();
            this.callbacks.onAceRepaintChanged?.(this._aceRepaintActive);
        });
        aceRow.appendChild(this.aceRepaintBtn);
        aceSection.appendChild(aceRow);

        const aceStrengthRow = document.createElement('div');
        aceStrengthRow.className = 'veditor-control-row';

        this.aceStrengthSlider = document.createElement('input');
        this.aceStrengthSlider.type = 'range';
        this.aceStrengthSlider.min = '0';
        this.aceStrengthSlider.max = '1';
        this.aceStrengthSlider.step = '0.05';
        this.aceStrengthSlider.value = '0.5';
        this.aceStrengthSlider.className = 'veditor-fade-slider';
        this.aceStrengthSlider.setAttribute('data-tool-id', 'veditor-ace-strength-slider');
        this.aceStrengthSlider.setAttribute('aria-label', 'ACE-Step repaint strength (0 to 1)');
        this.aceStrengthSlider.addEventListener('input', () => {
            const val = parseFloat(this.aceStrengthSlider.value);
            this.aceStrengthLabel.textContent = `${Math.round(val * 100)}%`;
            this.callbacks.onAceRepaintStrengthChanged?.(val);
        });

        this.aceStrengthLabel = document.createElement('span');
        this.aceStrengthLabel.className = 'veditor-fade-label';
        this.aceStrengthLabel.textContent = '50%';
        this.aceStrengthLabel.setAttribute('data-tool-id', 'veditor-ace-strength-label');

        aceStrengthRow.append(this.aceStrengthSlider, this.aceStrengthLabel);
        aceSection.appendChild(aceStrengthRow);

        // ── Reset Section ──
        const resetRow = document.createElement('div');
        resetRow.className = 'veditor-control-row';

        const resetBtn = document.createElement('button');
        resetBtn.className = 'veditor-btn veditor-toggle-btn';
        resetBtn.innerHTML = `${iconVolume} Reset Audio`;
        resetBtn.title = 'Reset all audio settings to defaults';
        resetBtn.setAttribute('data-tool-id', 'veditor-audio-reset');
        resetBtn.setAttribute('aria-label', 'Reset audio settings');
        resetBtn.addEventListener('click', () => {
            // Fire callbacks BEFORE reset() — reset() calls clearSegmentSelection()
            // which sets _selectedSegIndex = -1, and EditorModal's callbacks check
            // that index to know which AudioSegment to update. If we reset first,
            // the callbacks become no-ops and the segment data isn't actually reset.
            this.callbacks.onVolumeChanged(1.0);
            this.callbacks.onFadeInChanged?.(0);
            this.callbacks.onFadeOutChanged?.(0);
            this.callbacks.onEQChanged?.('flat');
            this.callbacks.onAceRepaintChanged?.(false);
            this.callbacks.onAceRepaintStrengthChanged?.(0.5);
            this.reset();
        });
        resetRow.appendChild(resetBtn);

        this.container.append(volSection, fadeInSection, fadeOutSection, eqSection, aceSection, resetRow);
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    /**
     * Get the master volume (independent of per-segment editing).
     * Always returns the master volume, even when a segment is selected
     * and the slider shows the segment's volume.
     *
     * Note: per-segment volume/mute is handled by AudioEditManager,
     * not by this getter.
     */
    getMasterVolume(): number {
        return this._masterVolume;
    }

    /** Set the master volume and update the slider (if no segment is selected) */
    setMasterVolume(volume: number): void {
        this._masterVolume = volume;
        // Only update UI if we're showing master controls
        if (this._selectedSegIndex < 0) {
            this.setVolume(volume);
        }
    }

    setVolume(volume: number): void {
        this.slider.value = String(volume);
        this.lastVolume = volume;
        this.isMuted = volume < 0.01;
        this.muteBtn.innerHTML = this.isMuted ? iconMuted : iconVolume;
        this.label.textContent = `${Math.round(volume * 100)}%`;
    }

    /** Load values from an AudioSegment for per-segment editing */
    loadSegment(seg: AudioSegment, index: number): void {
        this._selectedSegIndex = index;
        this.segmentHeader.textContent = `Audio Segment ${index + 1}`;
        this.segmentHeader.style.color = 'var(--ve-success)';

        this.setVolume(seg.volume);
        this.fadeInSlider.value = String(seg.fadeIn);
        this.fadeInLabel.textContent = `${seg.fadeIn.toFixed(1)}s`;
        this.fadeOutSlider.value = String(seg.fadeOut);
        this.fadeOutLabel.textContent = `${seg.fadeOut.toFixed(1)}s`;
        this.eqSelect.value = seg.eq;
        this.isMuted = seg.muted;
        this.muteBtn.innerHTML = seg.muted ? iconMuted : iconVolume;

        // ACE-Step Repaint
        this._aceRepaintActive = seg.aceRepaint;
        this._updateAceRepaintBtn();
        this.aceStrengthSlider.value = String(seg.aceRepaintStrength);
        this.aceStrengthLabel.textContent = `${Math.round(seg.aceRepaintStrength * 100)}%`;
    }

    /** Clear segment selection, restore master volume to slider, and show master label */
    clearSegmentSelection(): void {
        this._selectedSegIndex = -1;
        this.segmentHeader.textContent = 'Master Audio';
        this.segmentHeader.style.color = 'var(--ve-text-primary)';
        // Restore master volume to the slider UI
        this.setVolume(this._masterVolume);
    }

    /** Get current control values for saving to a segment */
    getSegmentProps(): { volume: number; fadeIn: number; fadeOut: number; eq: EQPreset; muted: boolean; aceRepaint: boolean; aceRepaintStrength: number } {
        return {
            volume: parseFloat(this.slider.value),
            fadeIn: parseFloat(this.fadeInSlider.value),
            fadeOut: parseFloat(this.fadeOutSlider.value),
            eq: this.eqSelect.value as EQPreset,
            muted: this.isMuted,
            aceRepaint: this._aceRepaintActive,
            aceRepaintStrength: parseFloat(this.aceStrengthSlider.value),
        };
    }

    get selectedSegmentIndex(): number {
        return this._selectedSegIndex;
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

    /** Reset all audio settings to defaults */
    reset(): void {
        this._masterVolume = 1.0;
        this.setVolume(1.0);
        this.fadeInSlider.value = '0';
        this.fadeInLabel.textContent = '0.0s';
        this.fadeOutSlider.value = '0';
        this.fadeOutLabel.textContent = '0.0s';
        this.eqSelect.value = 'flat';
        this.isMuted = false;
        this.muteBtn.innerHTML = iconVolume;
        this._aceRepaintActive = false;
        this._updateAceRepaintBtn();
        this.aceStrengthSlider.value = '0.5';
        this.aceStrengthLabel.textContent = '50%';
        this.clearSegmentSelection();
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

    private _updateAceRepaintBtn(): void {
        if (this._aceRepaintActive) {
            this.aceRepaintBtn.textContent = '🎵 Repaint On';
            this.aceRepaintBtn.style.background = 'var(--ve-success, #22c55e)';
            this.aceRepaintBtn.style.color = '#000';
        } else {
            this.aceRepaintBtn.textContent = '🎵 Repaint Off';
            this.aceRepaintBtn.style.background = '';
            this.aceRepaintBtn.style.color = '';
        }
    }
}
