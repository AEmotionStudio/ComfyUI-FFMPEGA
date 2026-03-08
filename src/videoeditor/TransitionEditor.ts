/**
 * TransitionEditor — segment transition type & duration controls.
 *
 * When 2+ segments exist, shows transition presets at each cut point.
 * Stores metadata (type, duration) that FFmpeg `xfade` will use.
 */

import { iconShuffle } from './icons';
import { EditManager } from '@ffmpega/loadlast/editing/EditManager';

export type TransitionType = 'none' | 'fade' | 'dissolve' | 'wipeleft' | 'wiperight' | 'slideleft' | 'slideright';

export interface TransitionDef {
    type: TransitionType;
    duration: number; // seconds
}

const TRANSITION_LABELS: Record<TransitionType, string> = {
    none: 'None (Hard Cut)',
    fade: 'Fade',
    dissolve: 'Dissolve',
    wipeleft: 'Wipe Left',
    wiperight: 'Wipe Right',
    slideleft: 'Slide Left',
    slideright: 'Slide Right',
};

export interface TransitionEditorCallbacks {
    onTransitionsChanged: () => void;
}

export class TransitionEditor {
    private container: HTMLDivElement;
    private listEl: HTMLDivElement;
    private emptyMsg: HTMLDivElement;
    private _transitions: TransitionDef[] = [];
    private manager: EditManager;
    private callbacks: TransitionEditorCallbacks;

    constructor(manager: EditManager, callbacks: TransitionEditorCallbacks) {
        this.manager = manager;
        this.callbacks = callbacks;

        this.container = document.createElement('div');
        this.container.setAttribute('data-tool-id', 'veditor-transitions');
        this.container.setAttribute('aria-label', 'Segment transitions editor');

        // Empty message
        this.emptyMsg = document.createElement('div');
        this.emptyMsg.className = 'veditor-section-label';
        this.emptyMsg.textContent = 'Split the video to add transitions between segments.';
        this.emptyMsg.style.textTransform = 'none';
        this.emptyMsg.style.letterSpacing = 'normal';
        this.emptyMsg.style.fontWeight = '400';
        this.emptyMsg.style.color = 'var(--ve-text-dim)';

        // Transition list
        this.listEl = document.createElement('div');
        this.listEl.className = 'veditor-text-list'; // reuse text list styles

        this.container.append(this.emptyMsg, this.listEl);
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    get transitions(): TransitionDef[] {
        return this._transitions;
    }

    /** Re-render based on current segment count */
    refresh(): void {
        const segs = this.manager.segments;
        const cutCount = segs.length - 1;

        // Ensure transitions array matches cut count
        while (this._transitions.length < cutCount) {
            this._transitions.push({ type: 'none', duration: 0.5 });
        }
        if (this._transitions.length > cutCount) {
            this._transitions.length = cutCount;
        }

        // Show/hide
        this.emptyMsg.style.display = cutCount > 0 ? 'none' : 'block';
        this.listEl.innerHTML = '';

        for (let i = 0; i < cutCount; i++) {
            this.listEl.appendChild(this._makeCard(i, segs[i], segs[i + 1]));
        }
    }

    private _makeCard(
        index: number,
        segA: { start: number; end: number },
        segB: { start: number; end: number },
    ): HTMLDivElement {
        const card = document.createElement('div');
        card.className = 'veditor-text-card'; // reuse card styles

        const header = document.createElement('div');
        header.className = 'veditor-text-card-header';
        const title = document.createElement('span');
        title.className = 'veditor-text-card-title';
        title.innerHTML = `${iconShuffle} Cut ${index + 1}`;

        const timeLabel = document.createElement('span');
        timeLabel.className = 'veditor-time-unit';
        timeLabel.textContent = `${segA.end.toFixed(1)}s → ${segB.start.toFixed(1)}s`;

        header.append(title, timeLabel);

        // Type selector
        const typeSection = this._makeSection('Type');
        const typeRow = document.createElement('div');
        typeRow.className = 'veditor-control-row';

        const select = document.createElement('select');
        select.className = 'veditor-select';
        select.setAttribute('data-tool-id', `veditor-transition-type-${index}`);
        select.setAttribute('aria-label', `Transition type for cut ${index + 1}`);

        for (const [value, label] of Object.entries(TRANSITION_LABELS)) {
            const opt = document.createElement('option');
            opt.value = value;
            opt.textContent = label;
            if (value === this._transitions[index].type) opt.selected = true;
            select.appendChild(opt);
        }

        select.addEventListener('change', () => {
            this._transitions[index].type = select.value as TransitionType;
            this.callbacks.onTransitionsChanged();
            // Show/hide duration based on type
            durationSection.style.display = select.value === 'none' ? 'none' : 'block';
        });

        typeRow.appendChild(select);
        typeSection.appendChild(typeRow);

        // Duration slider
        const durationSection = this._makeSection('Duration');
        durationSection.style.display = this._transitions[index].type === 'none' ? 'none' : 'block';

        const durRow = document.createElement('div');
        durRow.className = 'veditor-control-row';

        const slider = document.createElement('input');
        slider.type = 'range';
        slider.className = 'veditor-fade-slider';
        slider.min = '0.1';
        slider.max = '3';
        slider.step = '0.1';
        slider.value = String(this._transitions[index].duration);
        slider.setAttribute('data-tool-id', `veditor-transition-dur-${index}`);
        slider.setAttribute('aria-label', `Transition duration for cut ${index + 1}`);

        const durLabel = document.createElement('span');
        durLabel.className = 'veditor-fade-label';
        durLabel.textContent = `${this._transitions[index].duration.toFixed(1)}s`;

        slider.addEventListener('input', () => {
            const val = parseFloat(slider.value);
            this._transitions[index].duration = val;
            durLabel.textContent = `${val.toFixed(1)}s`;
        });
        slider.addEventListener('change', () => {
            this.callbacks.onTransitionsChanged();
        });

        durRow.append(slider, durLabel);
        durationSection.appendChild(durRow);

        card.append(header, typeSection, durationSection);
        return card;
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

    destroy(): void {
        this.container.remove();
    }
}
