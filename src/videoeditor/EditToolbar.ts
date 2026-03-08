/**
 * EditToolbar — editing tool bar between transport and timeline.
 *
 * Provides mode-based tool selection (Select, Razor) and action buttons
 * (Split, Delete). All buttons are agent-discoverable via data-tool-id
 * and aria-label attributes.
 */

import { iconCursor, iconScissors, iconSplit, iconTrash, iconReset } from './icons';

export type ToolMode = 'select' | 'razor';

export interface EditToolbarCallbacks {
    onToolChanged: (mode: ToolMode) => void;
    onSplitRequested: () => void;
    onDeleteRequested: () => void;
    onResetRequested: () => void;
}

export class EditToolbar {
    private container: HTMLDivElement;
    private callbacks: EditToolbarCallbacks;
    private currentMode: ToolMode = 'select';
    private modeButtons: Map<ToolMode, HTMLButtonElement> = new Map();

    constructor(callbacks: EditToolbarCallbacks) {
        this.callbacks = callbacks;

        this.container = document.createElement('div');
        this.container.className = 'veditor-modal-toolbar';
        this.container.setAttribute('role', 'toolbar');
        this.container.setAttribute('aria-label', 'Editing tools');
        this.container.setAttribute('data-tool-id', 'veditor-edit-toolbar');

        // ── Mode tools group ──
        const modeGroup = document.createElement('div');
        modeGroup.className = 'veditor-toolbar-group';

        const selectBtn = this._makeToolBtn(
            iconCursor, 'Select', 'Select tool — click to select segments (V)',
            'veditor-tool-select', () => this.setMode('select'),
        );
        selectBtn.classList.add('active');
        this.modeButtons.set('select', selectBtn);

        const razorBtn = this._makeToolBtn(
            iconScissors, 'Razor', 'Razor tool — click on timeline to cut (C)',
            'veditor-tool-razor', () => this.setMode('razor'),
        );
        this.modeButtons.set('razor', razorBtn);

        modeGroup.append(selectBtn, razorBtn);

        // ── Separator ──
        const sep1 = document.createElement('div');
        sep1.className = 'veditor-toolbar-sep';

        // ── Action buttons group ──
        const actionGroup = document.createElement('div');
        actionGroup.className = 'veditor-toolbar-group';

        const splitBtn = this._makeToolBtn(
            iconSplit, 'Split', 'Split at playhead (S)',
            'veditor-action-split', () => this.callbacks.onSplitRequested(),
        );

        const deleteBtn = this._makeToolBtn(
            iconTrash, 'Delete', 'Delete selected segment (Delete)',
            'veditor-action-delete', () => this.callbacks.onDeleteRequested(),
        );

        const resetBtn = this._makeToolBtn(
            iconReset, 'Reset', 'Reset all segments (R)',
            'veditor-action-reset', () => this.callbacks.onResetRequested(),
        );

        actionGroup.append(splitBtn, deleteBtn, resetBtn);

        // ── Spacer ──
        const spacer = document.createElement('div');
        spacer.className = 'veditor-spacer';

        this.container.append(modeGroup, sep1, actionGroup, spacer);
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    get mode(): ToolMode {
        return this.currentMode;
    }

    setMode(mode: ToolMode): void {
        if (this.currentMode === mode) return;
        this.currentMode = mode;

        for (const [m, btn] of this.modeButtons) {
            btn.classList.toggle('active', m === mode);
            btn.setAttribute('aria-pressed', String(m === mode));
        }

        this.callbacks.onToolChanged(mode);
    }

    /** Handle keyboard shortcuts — call from modal key handler */
    handleKey(key: string): boolean {
        switch (key.toLowerCase()) {
            case 'v':
                this.setMode('select');
                return true;
            case 'c':
                this.setMode('razor');
                return true;
            case 's':
                this.callbacks.onSplitRequested();
                return true;
            case 'r':
                this.callbacks.onResetRequested();
                return true;
            case 'delete':
            case 'backspace':
                this.callbacks.onDeleteRequested();
                return true;
            default:
                return false;
        }
    }

    destroy(): void {
        this.container.remove();
    }

    // ── Private ──────────────────────────────────────────────────

    private _makeToolBtn(
        icon: string,
        label: string,
        tooltip: string,
        toolId: string,
        onClick: () => void,
    ): HTMLButtonElement {
        const btn = document.createElement('button');
        btn.className = 'veditor-tool-btn';
        btn.innerHTML = `${icon} ${label}`;
        btn.title = tooltip;
        btn.setAttribute('data-tool-id', toolId);
        btn.setAttribute('aria-label', tooltip);
        btn.setAttribute('aria-pressed', 'false');
        btn.addEventListener('click', onClick);
        return btn;
    }
}
