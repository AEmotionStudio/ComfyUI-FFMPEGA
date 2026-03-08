/**
 * ShortcutOverlay — keyboard shortcut cheatsheet modal.
 *
 * Shows all available shortcuts organized by category.
 * Triggered by `?` or `H` key. Dismissed by Esc, backdrop click,
 * or pressing `?`/`H` again.
 */

import { iconClose } from './icons';

interface ShortcutCategory {
    title: string;
    shortcuts: { key: string; desc: string }[];
}

const CATEGORIES: ShortcutCategory[] = [
    {
        title: 'Transport',
        shortcuts: [
            { key: 'Space', desc: 'Play / Pause' },
            { key: '← →', desc: 'Step back / forward' },
        ],
    },
    {
        title: 'Tools',
        shortcuts: [
            { key: 'V', desc: 'Select tool' },
            { key: 'C', desc: 'Razor tool' },
            { key: 'S', desc: 'Split at playhead' },
            { key: 'Del', desc: 'Delete segment' },
            { key: 'R', desc: 'Reset all segments' },
        ],
    },
    {
        title: 'Monitor',
        shortcuts: [
            { key: 'F', desc: 'Fit to view' },
            { key: 'Scroll', desc: 'Zoom in / out' },
            { key: 'Mid-drag', desc: 'Pan canvas' },
            { key: 'Dbl-click', desc: 'Fit to view' },
        ],
    },
    {
        title: 'Panels',
        shortcuts: [
            { key: '1–5', desc: 'Switch tool tabs' },
            { key: '?', desc: 'Toggle this overlay' },
        ],
    },
    {
        title: 'General',
        shortcuts: [
            { key: 'Ctrl+Z', desc: 'Undo' },
            { key: 'Ctrl+Shift+Z', desc: 'Redo' },
            { key: 'Esc', desc: 'Close editor' },
        ],
    },
];

export class ShortcutOverlay {
    private backdrop: HTMLDivElement;
    private isVisible = false;

    constructor() {
        this.backdrop = document.createElement('div');
        this.backdrop.className = 'veditor-shortcuts-backdrop';
        this.backdrop.setAttribute('data-tool-id', 'veditor-shortcut-overlay');
        this.backdrop.setAttribute('aria-label', 'Keyboard shortcuts overlay');
        this.backdrop.style.display = 'none';
        this.backdrop.addEventListener('click', (e) => {
            if (e.target === this.backdrop) this.hide();
        });

        const panel = document.createElement('div');
        panel.className = 'veditor-shortcuts-panel';
        panel.addEventListener('click', (e) => e.stopPropagation());

        // Header
        const header = document.createElement('div');
        header.className = 'veditor-shortcuts-header';

        const title = document.createElement('h3');
        title.className = 'veditor-shortcuts-title';
        title.textContent = 'Keyboard Shortcuts';

        const closeBtn = document.createElement('button');
        closeBtn.className = 'veditor-btn';
        closeBtn.innerHTML = iconClose;
        closeBtn.title = 'Close shortcuts';
        closeBtn.setAttribute('data-tool-id', 'veditor-shortcuts-close');
        closeBtn.setAttribute('aria-label', 'Close shortcuts overlay');
        closeBtn.addEventListener('click', () => this.hide());

        header.append(title, closeBtn);

        // Grid of categories
        const grid = document.createElement('div');
        grid.className = 'veditor-shortcuts-grid';

        for (const cat of CATEGORIES) {
            const section = document.createElement('div');
            section.className = 'veditor-shortcuts-section';

            const catTitle = document.createElement('div');
            catTitle.className = 'veditor-shortcuts-cat';
            catTitle.textContent = cat.title;
            section.appendChild(catTitle);

            for (const sc of cat.shortcuts) {
                const row = document.createElement('div');
                row.className = 'veditor-shortcut-row';

                const kbd = document.createElement('kbd');
                kbd.className = 'veditor-kbd';
                kbd.textContent = sc.key;

                const desc = document.createElement('span');
                desc.className = 'veditor-shortcut-desc';
                desc.textContent = sc.desc;

                row.append(kbd, desc);
                section.appendChild(row);
            }

            grid.appendChild(section);
        }

        panel.append(header, grid);
        this.backdrop.appendChild(panel);
    }

    get element(): HTMLDivElement {
        return this.backdrop;
    }

    toggle(): void {
        if (this.isVisible) this.hide();
        else this.show();
    }

    show(): void {
        this.isVisible = true;
        this.backdrop.style.display = 'flex';
    }

    hide(): void {
        this.isVisible = false;
        this.backdrop.style.display = 'none';
    }

    /** Returns true if the overlay consumed the key event */
    handleKey(key: string): boolean {
        if (key === '?' || (key.toLowerCase() === 'h' && !this.isVisible)) {
            this.toggle();
            return true;
        }
        if (key === 'Escape' && this.isVisible) {
            this.hide();
            return true;
        }
        return false;
    }

    destroy(): void {
        this.backdrop.remove();
    }
}
