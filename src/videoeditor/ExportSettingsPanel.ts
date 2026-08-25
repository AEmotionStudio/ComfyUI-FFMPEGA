/**
 * ExportSettingsPanel — Pre-export configuration for resolution,
 * codec, quality, format, and audio settings.
 *
 * Shown as a panel in the tools area. Users configure before applying.
 */

export interface ExportSettings {
    resolution: string;        // 'source' | '4k' | '1080p' | '720p' | '480p' | 'WxH'
    video_codec: string;       // 'h264' | 'h265' | 'vp9' | 'av1'
    crf: number;               // 0-51
    preset: string;            // 'ultrafast' | 'fast' | 'medium' | 'slow' | 'veryslow'
    format: string;            // 'mp4' | 'mkv' | 'webm' | 'mov'
    audio_codec: string;       // 'aac' | 'mp3' | 'opus' | 'flac'
    audio_bitrate: string;     // '128k' | '192k' | '256k' | '320k'
}

export interface ExportSettingsCallbacks {
    onSettingsChanged: (settings: ExportSettings) => void;
}

const DEFAULT_SETTINGS: ExportSettings = {
    resolution: 'source',
    video_codec: 'h264',
    crf: 18,
    preset: 'fast',
    format: 'mp4',
    audio_codec: 'aac',
    audio_bitrate: '192k',
};

export class ExportSettingsPanel {
    private container: HTMLDivElement;
    private callbacks: ExportSettingsCallbacks;
    private state: ExportSettings;

    private resSelect!: HTMLSelectElement;
    private codecSelect!: HTMLSelectElement;
    private crfSlider!: HTMLInputElement;
    private crfLabel!: HTMLSpanElement;
    private presetSelect!: HTMLSelectElement;
    private formatSelect!: HTMLSelectElement;
    private audioCodecSelect!: HTMLSelectElement;
    private audioBitrateSelect!: HTMLSelectElement;

    constructor(callbacks: ExportSettingsCallbacks) {
        this.callbacks = callbacks;
        this.state = { ...DEFAULT_SETTINGS };

        this.container = document.createElement('div');
        this.container.className = 'veditor-export-panel';
        this.container.setAttribute('data-tool-id', 'veditor-export-panel');
        this.container.setAttribute('aria-label', 'Export settings');

        // ── Resolution ──
        const resSection = this._makeSection('Resolution');
        this.resSelect = this._makeDropdown(
            [
                { value: 'source', label: 'Source (Original)' },
                { value: '4k', label: '4K (3840×2160)' },
                { value: '1080p', label: '1080p (1920×1080)' },
                { value: '720p', label: '720p (1280×720)' },
                { value: '480p', label: '480p (854×480)' },
            ],
            'source', 'veditor-export-resolution', 'Output resolution',
            (v) => { this.state.resolution = v; this._notify(); },
        );
        resSection.appendChild(this.resSelect);

        // ── Video Codec ──
        const codecSection = this._makeSection('Video Codec');
        this.codecSelect = this._makeDropdown(
            [
                { value: 'h264', label: 'H.264 (Best Compatibility)' },
                { value: 'h265', label: 'H.265/HEVC (Smaller Files)' },
                { value: 'vp9', label: 'VP9 (Web)' },
                { value: 'av1', label: 'AV1 (Best Quality, Slow)' },
            ],
            'h264', 'veditor-export-codec', 'Video codec',
            (v) => { this.state.video_codec = v; this._notify(); },
        );
        codecSection.appendChild(this.codecSelect);

        // ── Quality (CRF) ──
        const crfSection = this._makeSection('Quality (CRF)');
        const crfRow = document.createElement('div');
        crfRow.className = 'veditor-control-row';

        this.crfSlider = document.createElement('input');
        this.crfSlider.type = 'range';
        this.crfSlider.min = '0';
        this.crfSlider.max = '51';
        this.crfSlider.step = '1';
        this.crfSlider.value = '18';
        this.crfSlider.className = 'veditor-grading-slider';
        this.crfSlider.setAttribute('data-tool-id', 'veditor-export-crf');

        this.crfLabel = document.createElement('span');
        this.crfLabel.className = 'veditor-grading-value';
        this.crfLabel.textContent = '18 (High)';

        this.crfSlider.addEventListener('input', () => {
            this.state.crf = parseInt(this.crfSlider.value, 10);
            this.crfLabel.textContent = `${this.state.crf} (${this._crfQualityLabel(this.state.crf)})`;
            this._notify();
        });

        crfRow.append(this.crfSlider, this.crfLabel);
        crfSection.appendChild(crfRow);

        // ── Encoding Speed ──
        const presetSection = this._makeSection('Encoding Speed');
        this.presetSelect = this._makeDropdown(
            [
                { value: 'ultrafast', label: 'Ultra Fast (Lowest Quality)' },
                { value: 'fast', label: 'Fast (Default)' },
                { value: 'medium', label: 'Medium (Balanced)' },
                { value: 'slow', label: 'Slow (Better Quality)' },
                { value: 'veryslow', label: 'Very Slow (Best Quality)' },
            ],
            'fast', 'veditor-export-preset', 'Encoding speed',
            (v) => { this.state.preset = v; this._notify(); },
        );
        presetSection.appendChild(this.presetSelect);

        // ── Format ──
        const fmtSection = this._makeSection('Output Format');
        this.formatSelect = this._makeDropdown(
            [
                { value: 'mp4', label: 'MP4 (Universal)' },
                { value: 'mkv', label: 'MKV (All Codecs)' },
                { value: 'webm', label: 'WebM (Web)' },
                { value: 'mov', label: 'MOV (Apple)' },
            ],
            'mp4', 'veditor-export-format', 'Output format',
            (v) => { this.state.format = v; this._notify(); },
        );
        fmtSection.appendChild(this.formatSelect);

        // ── Audio Codec ──
        const audioSection = this._makeSection('Audio Codec');
        this.audioCodecSelect = this._makeDropdown(
            [
                { value: 'aac', label: 'AAC (Default)' },
                { value: 'mp3', label: 'MP3' },
                { value: 'opus', label: 'Opus (Best Quality)' },
                { value: 'flac', label: 'FLAC (Lossless)' },
            ],
            'aac', 'veditor-export-audio-codec', 'Audio codec',
            (v) => { this.state.audio_codec = v; this._notify(); },
        );
        audioSection.appendChild(this.audioCodecSelect);

        // ── Audio Bitrate ──
        const bitrateSection = this._makeSection('Audio Bitrate');
        this.audioBitrateSelect = this._makeDropdown(
            [
                { value: '128k', label: '128 kbps' },
                { value: '192k', label: '192 kbps (Default)' },
                { value: '256k', label: '256 kbps' },
                { value: '320k', label: '320 kbps (High)' },
            ],
            '192k', 'veditor-export-audio-bitrate', 'Audio bitrate',
            (v) => { this.state.audio_bitrate = v; this._notify(); },
        );
        bitrateSection.appendChild(this.audioBitrateSelect);

        // ── Reset ──
        const resetRow = document.createElement('div');
        resetRow.className = 'veditor-control-row';

        const resetBtn = document.createElement('button');
        resetBtn.className = 'veditor-btn veditor-toggle-btn';
        resetBtn.textContent = 'Reset to Defaults';
        resetBtn.setAttribute('data-tool-id', 'veditor-export-reset');
        resetBtn.addEventListener('click', () => this.reset());
        resetRow.appendChild(resetBtn);

        this.container.append(
            resSection, codecSection, crfSection, presetSection,
            fmtSection, audioSection, bitrateSection, resetRow,
        );
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    getState(): ExportSettings {
        return { ...this.state };
    }

    loadState(s: Partial<ExportSettings>): void {
        Object.assign(this.state, s);
        this.resSelect.value = this.state.resolution;
        this.codecSelect.value = this.state.video_codec;
        this.crfSlider.value = String(this.state.crf);
        this.crfLabel.textContent = `${this.state.crf} (${this._crfQualityLabel(this.state.crf)})`;
        this.presetSelect.value = this.state.preset;
        this.formatSelect.value = this.state.format;
        this.audioCodecSelect.value = this.state.audio_codec;
        this.audioBitrateSelect.value = this.state.audio_bitrate;
    }

    reset(): void {
        this.state = { ...DEFAULT_SETTINGS };
        this.loadState(this.state);
        this._notify();
    }

    destroy(): void {
        this.container.remove();
    }

    // ── Private ──────────────────────────────────────────────────

    private _notify(): void {
        this.callbacks.onSettingsChanged(this.getState());
    }

    private _crfQualityLabel(crf: number): string {
        if (crf === 0) return 'Lossless';
        if (crf <= 15) return 'Very High';
        if (crf <= 23) return 'High';
        if (crf <= 28) return 'Medium';
        if (crf <= 35) return 'Low';
        return 'Very Low';
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

    private _makeDropdown(
        options: { value: string; label: string }[],
        defaultValue: string,
        toolId: string,
        ariaLabel: string,
        onChange: (val: string) => void,
    ): HTMLSelectElement {
        const select = document.createElement('select');
        select.className = 'veditor-select';
        select.setAttribute('data-tool-id', toolId);
        select.setAttribute('aria-label', ariaLabel);
        options.forEach(opt => {
            const o = document.createElement('option');
            o.value = opt.value;
            o.textContent = opt.label;
            if (opt.value === defaultValue) o.selected = true;
            select.appendChild(o);
        });
        select.addEventListener('change', () => onChange(select.value));
        return select;
    }
}
