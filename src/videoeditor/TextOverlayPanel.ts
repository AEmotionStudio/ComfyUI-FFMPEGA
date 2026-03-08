/**
 * TextOverlayPanel — UI for adding/editing text overlays (drawtext).
 *
 * Each overlay has: text, position, font size, font family, color,
 * alignment, background, outline, bold/italic, and time range.
 */

import {
    iconClose, iconPlus, iconBold, iconItalic,
    iconAlignLeft, iconAlignCenter, iconAlignRight,
} from './icons';

export interface TextOverlay {
    text: string;
    x: string;         // "center", "left", "right", or pixel string
    y: string;         // "center", "top", "bottom", or pixel string
    font_size: number;
    color: string;
    start_time: number | null;
    end_time: number | null;
    font: string | null;
    alignment: 'left' | 'center' | 'right';
    bold: boolean;
    italic: boolean;
    backgroundColor: string | null;
    backgroundOpacity: number;
    outlineColor: string | null;
    outlineWidth: number;
}

export interface TextOverlayPanelCallbacks {
    onOverlaysChanged: (overlays: TextOverlay[]) => void;
}

const POSITION_PRESETS: { label: string; x: string; y: string }[] = [
    { label: 'Top', x: 'center', y: 'top' },
    { label: 'Center', x: 'center', y: 'center' },
    { label: 'Bottom', x: 'center', y: 'bottom' },
    { label: 'Lower Third', x: 'center', y: '75%' },
];

const FONT_FAMILIES = [
    'sans-serif',
    'serif',
    'monospace',
    'Arial',
    'Helvetica',
    'Georgia',
    'Courier New',
    'Impact',
];

const TEXT_PRESETS: Record<string, Partial<TextOverlay>> = {
    subtitle: {
        text: 'Subtitle text',
        font: 'sans-serif',
        font_size: 32,
        color: '#ffffff',
        alignment: 'center',
        x: 'center', y: 'bottom',
        bold: false, italic: false,
        backgroundColor: '#000000',
        backgroundOpacity: 0.6,
        outlineColor: null, outlineWidth: 0,
    },
    title: {
        text: 'Title Card',
        font: 'serif',
        font_size: 72,
        color: '#ffffff',
        alignment: 'center',
        x: 'center', y: 'center',
        bold: true, italic: false,
        backgroundColor: null,
        backgroundOpacity: 0,
        outlineColor: '#000000', outlineWidth: 3,
    },
    lowerthird: {
        text: 'Name or Title',
        font: 'sans-serif',
        font_size: 28,
        color: '#ffffff',
        alignment: 'left',
        x: 'left', y: '75%',
        bold: true, italic: false,
        backgroundColor: '#1a1a2e',
        backgroundOpacity: 0.8,
        outlineColor: null, outlineWidth: 0,
    },
    credit: {
        text: 'Directed by\nYour Name',
        font: 'serif',
        font_size: 42,
        color: '#ffffff',
        alignment: 'center',
        x: 'center', y: 'center',
        bold: false, italic: true,
        backgroundColor: null,
        backgroundOpacity: 0,
        outlineColor: null, outlineWidth: 0,
    },
};

export class TextOverlayPanel {
    private container: HTMLDivElement;
    private listEl: HTMLDivElement;
    private callbacks: TextOverlayPanelCallbacks;
    private overlays: TextOverlay[] = [];

    constructor(callbacks: TextOverlayPanelCallbacks) {
        this.callbacks = callbacks;

        this.container = document.createElement('div');
        this.container.className = 'veditor-text-panel';
        this.container.setAttribute('data-tool-id', 'veditor-text-panel');
        this.container.setAttribute('aria-label', 'Text overlay editor');

        const header = document.createElement('div');
        header.className = 'veditor-text-header';
        header.innerHTML = '<span>Text Overlays</span>';

        const addBtn = document.createElement('button');
        addBtn.className = 'veditor-btn';
        addBtn.innerHTML = `${iconPlus} Add Text`;
        addBtn.setAttribute('data-tool-id', 'veditor-text-add');
        addBtn.setAttribute('aria-label', 'Add new text overlay');
        addBtn.title = 'Add new text overlay';
        addBtn.addEventListener('click', () => this._addOverlay());
        header.appendChild(addBtn);

        // Preset selector
        const presetRow = document.createElement('div');
        presetRow.className = 'veditor-control-row';
        presetRow.style.marginBottom = '8px';

        const presetLabel = document.createElement('span');
        presetLabel.className = 'veditor-control-label';
        presetLabel.textContent = 'Preset';

        const presetSelect = document.createElement('select');
        presetSelect.className = 'veditor-select';
        presetSelect.setAttribute('data-tool-id', 'veditor-text-preset');
        presetSelect.setAttribute('aria-label', 'Text overlay preset');

        const defaultOpt = document.createElement('option');
        defaultOpt.value = '';
        defaultOpt.textContent = 'Choose a preset…';
        presetSelect.appendChild(defaultOpt);

        for (const [key, preset] of Object.entries(TEXT_PRESETS)) {
            const opt = document.createElement('option');
            opt.value = key;
            opt.textContent = key === 'lowerthird' ? 'Lower Third' : key.charAt(0).toUpperCase() + key.slice(1);
            opt.setAttribute('data-tool-id', `veditor-text-preset-${key}`);
            presetSelect.appendChild(opt);
        }

        presetSelect.addEventListener('change', () => {
            const preset = TEXT_PRESETS[presetSelect.value];
            if (preset) {
                this._addOverlayFromPreset(preset);
                presetSelect.value = ''; // reset to placeholder
            }
        });

        presetRow.append(presetLabel, presetSelect);

        this.listEl = document.createElement('div');
        this.listEl.className = 'veditor-text-list';
        this.listEl.setAttribute('data-tool-id', 'veditor-text-list');
        this.listEl.setAttribute('aria-label', 'List of text overlays');

        this.container.append(header, presetRow, this.listEl);
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    getOverlays(): TextOverlay[] {
        return [...this.overlays];
    }

    loadOverlays(overlays: TextOverlay[]): void {
        this.overlays = overlays.map(o => ({ ...o }));
        this._renderList();
    }

    destroy(): void {
        this.container.remove();
    }

    // ── Private ──────────────────────────────────────────────────

    private _addOverlay(): void {
        this.overlays.push({
            text: 'Your text here',
            x: 'center',
            y: 'bottom',
            font_size: 48,
            color: '#ffffff',
            start_time: null,
            end_time: null,
            font: 'sans-serif',
            alignment: 'center',
            bold: false,
            italic: false,
            backgroundColor: null,
            backgroundOpacity: 0.6,
            outlineColor: null,
            outlineWidth: 2,
        });
        this._renderList();
        this._notify();
    }

    private _addOverlayFromPreset(preset: Partial<TextOverlay>): void {
        const defaults: TextOverlay = {
            text: 'Your text here',
            x: 'center',
            y: 'bottom',
            font_size: 48,
            color: '#ffffff',
            start_time: null,
            end_time: null,
            font: 'sans-serif',
            alignment: 'center',
            bold: false,
            italic: false,
            backgroundColor: null,
            backgroundOpacity: 0.6,
            outlineColor: null,
            outlineWidth: 2,
        };
        this.overlays.push({ ...defaults, ...preset });
        this._renderList();
        this._notify();
    }

    private _removeOverlay(index: number): void {
        this.overlays.splice(index, 1);
        this._renderList();
        this._notify();
    }

    private _renderList(): void {
        this.listEl.innerHTML = '';

        this.overlays.forEach((ov, idx) => {
            const card = document.createElement('div');
            card.className = 'veditor-text-card';
            card.setAttribute('data-tool-id', `veditor-text-card-${idx}`);
            card.setAttribute('aria-label', `Text overlay ${idx + 1}`);

            // ── Card Header (title + delete) ──
            const cardHeader = document.createElement('div');
            cardHeader.className = 'veditor-text-card-header';

            const cardTitle = document.createElement('span');
            cardTitle.className = 'veditor-text-card-title';
            cardTitle.textContent = `Text ${idx + 1}`;

            const delBtn = document.createElement('button');
            delBtn.className = 'veditor-btn veditor-text-del';
            delBtn.innerHTML = iconClose;
            delBtn.title = `Remove text overlay ${idx + 1}`;
            delBtn.setAttribute('data-tool-id', `veditor-text-del-${idx}`);
            delBtn.setAttribute('aria-label', `Remove text overlay ${idx + 1}`);
            delBtn.addEventListener('click', () => this._removeOverlay(idx));

            cardHeader.append(cardTitle, delBtn);

            // ── Text Input ──
            const textInput = document.createElement('textarea');
            textInput.className = 'veditor-text-textarea';
            textInput.value = ov.text;
            textInput.rows = 2;
            textInput.placeholder = 'Enter text...';
            textInput.setAttribute('data-tool-id', `veditor-text-input-${idx}`);
            textInput.setAttribute('aria-label', `Text content for overlay ${idx + 1}`);
            textInput.addEventListener('input', () => {
                ov.text = textInput.value;
                this._notify();
            });

            // ── Font & Style Row ──
            const fontRow = document.createElement('div');
            fontRow.className = 'veditor-control-row veditor-font-row';

            const fontSelect = this._makeSelect(
                FONT_FAMILIES, ov.font || 'sans-serif',
                (val) => { ov.font = val; this._notify(); },
                `veditor-text-font-${idx}`, 'Font family',
            );
            fontSelect.className = 'veditor-select veditor-font-select';

            const sizeInput = document.createElement('input');
            sizeInput.type = 'number';
            sizeInput.className = 'veditor-input veditor-size-input';
            sizeInput.value = String(ov.font_size);
            sizeInput.min = '8';
            sizeInput.max = '200';
            sizeInput.setAttribute('data-tool-id', `veditor-text-size-${idx}`);
            sizeInput.setAttribute('aria-label', 'Font size');
            sizeInput.addEventListener('change', () => {
                ov.font_size = parseInt(sizeInput.value, 10) || 48;
                this._notify();
            });

            const colorInput = document.createElement('input');
            colorInput.type = 'color';
            colorInput.value = this._nameToHex(ov.color);
            colorInput.className = 'veditor-color-input';
            colorInput.setAttribute('data-tool-id', `veditor-text-color-${idx}`);
            colorInput.setAttribute('aria-label', 'Text color');
            colorInput.addEventListener('change', () => {
                ov.color = colorInput.value;
                this._notify();
            });

            fontRow.append(fontSelect, sizeInput, colorInput);

            // ── Style Buttons Row (Bold, Italic, Alignment) ──
            const styleRow = document.createElement('div');
            styleRow.className = 'veditor-control-row veditor-style-row';

            const boldBtn = this._makeToggle(iconBold, 'Bold', ov.bold, (val) => {
                ov.bold = val;
                this._notify();
            }, `veditor-text-bold-${idx}`);

            const italicBtn = this._makeToggle(iconItalic, 'Italic', ov.italic, (val) => {
                ov.italic = val;
                this._notify();
            }, `veditor-text-italic-${idx}`);

            const sep = document.createElement('div');
            sep.className = 'veditor-toolbar-sep';

            const alignLeftBtn = this._makeAlignBtn(iconAlignLeft, 'left', ov, idx);
            const alignCenterBtn = this._makeAlignBtn(iconAlignCenter, 'center', ov, idx);
            const alignRightBtn = this._makeAlignBtn(iconAlignRight, 'right', ov, idx);

            styleRow.append(boldBtn, italicBtn, sep, alignLeftBtn, alignCenterBtn, alignRightBtn);

            // ── Position Presets ──
            const posRow = document.createElement('div');
            posRow.className = 'veditor-control-row veditor-pos-row';

            const posLabel = document.createElement('span');
            posLabel.className = 'veditor-control-label';
            posLabel.textContent = 'Position';

            POSITION_PRESETS.forEach(preset => {
                const btn = document.createElement('button');
                btn.className = 'veditor-btn veditor-preset-btn';
                if (ov.x === preset.x && ov.y === preset.y) btn.classList.add('active');
                btn.textContent = preset.label;
                btn.title = `Position: ${preset.label}`;
                btn.setAttribute('data-tool-id', `veditor-text-pos-${preset.label.toLowerCase().replace(' ', '-')}-${idx}`);
                btn.setAttribute('aria-label', `Position: ${preset.label}`);
                btn.addEventListener('click', () => {
                    ov.x = preset.x;
                    ov.y = preset.y;
                    this._renderList();
                    this._notify();
                });
                posRow.appendChild(btn);
            });

            posRow.prepend(posLabel);

            // ── Background & Outline ──
            const bgRow = document.createElement('div');
            bgRow.className = 'veditor-control-row veditor-bg-row';

            const bgLabel = document.createElement('label');
            bgLabel.className = 'veditor-toggle-label';

            const bgCheck = document.createElement('input');
            bgCheck.type = 'checkbox';
            bgCheck.className = 'veditor-checkbox';
            bgCheck.checked = ov.backgroundColor !== null;
            bgCheck.setAttribute('data-tool-id', `veditor-text-bg-toggle-${idx}`);
            bgCheck.setAttribute('aria-label', 'Enable text background');
            bgCheck.addEventListener('change', () => {
                ov.backgroundColor = bgCheck.checked ? '#000000' : null;
                this._renderList();
                this._notify();
            });

            bgLabel.append(bgCheck, document.createTextNode(' Background'));

            const outlineLabel = document.createElement('label');
            outlineLabel.className = 'veditor-toggle-label';

            const outlineCheck = document.createElement('input');
            outlineCheck.type = 'checkbox';
            outlineCheck.className = 'veditor-checkbox';
            outlineCheck.checked = ov.outlineColor !== null;
            outlineCheck.setAttribute('data-tool-id', `veditor-text-outline-toggle-${idx}`);
            outlineCheck.setAttribute('aria-label', 'Enable text outline');
            outlineCheck.addEventListener('change', () => {
                ov.outlineColor = outlineCheck.checked ? '#000000' : null;
                this._renderList();
                this._notify();
            });

            outlineLabel.append(outlineCheck, document.createTextNode(' Outline'));

            bgRow.append(bgLabel, outlineLabel);

            // Background color/opacity if enabled
            if (ov.backgroundColor !== null) {
                const bgColorRow = document.createElement('div');
                bgColorRow.className = 'veditor-control-row';

                const bgColorInput = document.createElement('input');
                bgColorInput.type = 'color';
                bgColorInput.value = ov.backgroundColor;
                bgColorInput.className = 'veditor-color-input';
                bgColorInput.setAttribute('data-tool-id', `veditor-text-bg-color-${idx}`);
                bgColorInput.addEventListener('change', () => {
                    ov.backgroundColor = bgColorInput.value;
                    this._notify();
                });

                const opacitySlider = document.createElement('input');
                opacitySlider.type = 'range';
                opacitySlider.min = '0';
                opacitySlider.max = '1';
                opacitySlider.step = '0.05';
                opacitySlider.value = String(ov.backgroundOpacity);
                opacitySlider.className = 'veditor-fade-slider';
                opacitySlider.setAttribute('data-tool-id', `veditor-text-bg-opacity-${idx}`);
                opacitySlider.setAttribute('aria-label', 'Background opacity');
                opacitySlider.addEventListener('input', () => {
                    ov.backgroundOpacity = parseFloat(opacitySlider.value);
                    this._notify();
                });

                const opacityLabel = document.createElement('span');
                opacityLabel.className = 'veditor-fade-label';
                opacityLabel.textContent = `${Math.round(ov.backgroundOpacity * 100)}%`;

                bgColorRow.append(bgColorInput, opacitySlider, opacityLabel);
                bgRow.after(bgColorRow);
                card.append(cardHeader, textInput, fontRow, styleRow, posRow, bgRow, bgColorRow);
            } else {
                card.append(cardHeader, textInput, fontRow, styleRow, posRow, bgRow);
            }

            // Outline color if enabled
            if (ov.outlineColor !== null) {
                const outlineRow = document.createElement('div');
                outlineRow.className = 'veditor-control-row';

                const outlineColorInput = document.createElement('input');
                outlineColorInput.type = 'color';
                outlineColorInput.value = ov.outlineColor;
                outlineColorInput.className = 'veditor-color-input';
                outlineColorInput.setAttribute('data-tool-id', `veditor-text-outline-color-${idx}`);
                outlineColorInput.addEventListener('change', () => {
                    ov.outlineColor = outlineColorInput.value;
                    this._notify();
                });

                const widthInput = document.createElement('input');
                widthInput.type = 'number';
                widthInput.className = 'veditor-input';
                widthInput.value = String(ov.outlineWidth);
                widthInput.min = '1';
                widthInput.max = '10';
                widthInput.setAttribute('data-tool-id', `veditor-text-outline-width-${idx}`);
                widthInput.setAttribute('aria-label', 'Outline width');
                widthInput.addEventListener('change', () => {
                    ov.outlineWidth = parseInt(widthInput.value, 10) || 2;
                    this._notify();
                });

                const wLabel = document.createElement('span');
                wLabel.className = 'veditor-control-label';
                wLabel.textContent = 'px';

                outlineRow.append(outlineColorInput, widthInput, wLabel);
                card.appendChild(outlineRow);
            }

            // ── Timing ──
            const timeRow = document.createElement('div');
            timeRow.className = 'veditor-control-row veditor-time-row';

            const startLabel = document.createElement('span');
            startLabel.className = 'veditor-control-label';
            startLabel.textContent = 'Start';

            const startInput = document.createElement('input');
            startInput.type = 'number';
            startInput.className = 'veditor-input veditor-time-input';
            startInput.value = ov.start_time !== null ? String(ov.start_time) : '';
            startInput.placeholder = '0.0';
            startInput.step = '0.1';
            startInput.min = '0';
            startInput.setAttribute('data-tool-id', `veditor-text-start-${idx}`);
            startInput.setAttribute('aria-label', 'Start time (seconds)');
            startInput.addEventListener('change', () => {
                ov.start_time = startInput.value ? parseFloat(startInput.value) : null;
                this._notify();
            });

            const endLabel = document.createElement('span');
            endLabel.className = 'veditor-control-label';
            endLabel.textContent = 'End';

            const endInput = document.createElement('input');
            endInput.type = 'number';
            endInput.className = 'veditor-input veditor-time-input';
            endInput.value = ov.end_time !== null ? String(ov.end_time) : '';
            endInput.placeholder = '∞';
            endInput.step = '0.1';
            endInput.min = '0';
            endInput.setAttribute('data-tool-id', `veditor-text-end-${idx}`);
            endInput.setAttribute('aria-label', 'End time (seconds)');
            endInput.addEventListener('change', () => {
                ov.end_time = endInput.value ? parseFloat(endInput.value) : null;
                this._notify();
            });

            const sLabel = document.createElement('span');
            sLabel.className = 'veditor-time-unit';
            sLabel.textContent = 's';

            const eLabel = document.createElement('span');
            eLabel.className = 'veditor-time-unit';
            eLabel.textContent = 's';

            timeRow.append(startLabel, startInput, sLabel, endLabel, endInput, eLabel);
            card.appendChild(timeRow);

            this.listEl.appendChild(card);
        });
    }

    private _makeSelect(
        options: string[],
        value: string,
        onChange: (val: string) => void,
        toolId: string,
        label: string,
    ): HTMLSelectElement {
        const select = document.createElement('select');
        select.className = 'veditor-select';
        select.setAttribute('data-tool-id', toolId);
        select.setAttribute('aria-label', label);
        options.forEach(opt => {
            const o = document.createElement('option');
            o.value = opt;
            o.textContent = opt;
            if (opt === value) o.selected = true;
            select.appendChild(o);
        });
        select.addEventListener('change', () => onChange(select.value));
        return select;
    }

    private _makeToggle(
        icon: string, label: string, active: boolean,
        onChange: (val: boolean) => void, toolId: string,
    ): HTMLButtonElement {
        const btn = document.createElement('button');
        btn.className = 'veditor-btn veditor-style-btn';
        if (active) btn.classList.add('active');
        btn.innerHTML = icon;
        btn.title = label;
        btn.setAttribute('data-tool-id', toolId);
        btn.setAttribute('aria-label', label);
        btn.setAttribute('aria-pressed', String(active));
        btn.addEventListener('click', () => {
            const next = !btn.classList.contains('active');
            btn.classList.toggle('active', next);
            btn.setAttribute('aria-pressed', String(next));
            onChange(next);
        });
        return btn;
    }

    private _makeAlignBtn(
        icon: string, align: 'left' | 'center' | 'right',
        ov: TextOverlay, idx: number,
    ): HTMLButtonElement {
        const btn = document.createElement('button');
        btn.className = 'veditor-btn veditor-style-btn';
        if (ov.alignment === align) btn.classList.add('active');
        btn.innerHTML = icon;
        btn.title = `Align ${align}`;
        btn.setAttribute('data-tool-id', `veditor-text-align-${align}-${idx}`);
        btn.setAttribute('aria-label', `Align ${align}`);
        btn.addEventListener('click', () => {
            ov.alignment = align;
            this._renderList();
            this._notify();
        });
        return btn;
    }

    private _nameToHex(color: string): string {
        const map: Record<string, string> = {
            white: '#ffffff',
            black: '#000000',
            red: '#ff0000',
            green: '#00ff00',
            blue: '#0000ff',
            yellow: '#ffff00',
        };
        return map[color.toLowerCase()] ?? color;
    }

    private _notify(): void {
        this.callbacks.onOverlaysChanged([...this.overlays]);
    }
}
