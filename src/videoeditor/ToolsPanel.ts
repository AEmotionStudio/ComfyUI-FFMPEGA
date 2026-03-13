/**
 * ToolsPanel — tabbed sidebar with grouped categories.
 *
 * Renders tabs organized into logical category groups (Edit, Effects, Compose)
 * with visual separators. Each tab shows an icon with a tooltip label.
 * Keyboard shortcuts 1-9, 0 for tabs 1-10, and extended keys for 11-12.
 */

export interface TabDefinition {
    id: string;
    label: string;
    icon: string;
    content: HTMLElement;
}

export interface TabGroup {
    label: string;
    tabs: TabDefinition[];
}

export class ToolsPanel {
    private container: HTMLDivElement;
    private tabBar: HTMLDivElement;
    private contentArea: HTMLDivElement;
    private allTabs: TabDefinition[] = [];
    private tabButtons: Map<string, HTMLButtonElement> = new Map();
    private tabPanes: Map<string, HTMLDivElement> = new Map();
    private activeTabId: string = '';

    constructor(groups: TabGroup[]) {
        // Flatten for indexed access
        this.allTabs = groups.flatMap(g => g.tabs);

        this.container = document.createElement('div');
        this.container.className = 'veditor-modal-tools';
        this.container.setAttribute('role', 'region');
        this.container.setAttribute('aria-label', 'Editing tools panel');
        this.container.setAttribute('data-tool-id', 'veditor-tools-panel');

        // ── Tab bar ──
        this.tabBar = document.createElement('div');
        this.tabBar.className = 'veditor-tabs';
        this.tabBar.setAttribute('role', 'tablist');
        this.tabBar.setAttribute('aria-label', 'Tool tabs');

        for (let gi = 0; gi < groups.length; gi++) {
            const group = groups[gi];

            // Category group container
            const groupEl = document.createElement('div');
            groupEl.className = 'veditor-tab-group';

            // Category label
            const catLabel = document.createElement('span');
            catLabel.className = 'veditor-tab-group-label';
            catLabel.textContent = group.label;
            groupEl.appendChild(catLabel);

            // Tab buttons row within group
            const btnRow = document.createElement('div');
            btnRow.className = 'veditor-tab-group-btns';

            for (const tab of group.tabs) {
                const idx = this.allTabs.indexOf(tab);
                const btn = document.createElement('button');
                btn.className = 'veditor-tab';
                btn.innerHTML = tab.icon;
                btn.setAttribute('role', 'tab');
                btn.setAttribute('aria-selected', 'false');
                btn.setAttribute('aria-controls', `veditor-pane-${tab.id}`);
                btn.setAttribute('data-tool-id', `veditor-tab-${tab.id}`);
                btn.setAttribute('aria-label', `${tab.label} tools`);
                btn.title = `${tab.label} (${this._shortcutLabel(idx)})`;
                btn.addEventListener('click', () => this.activateTab(tab.id));
                btnRow.appendChild(btn);
                this.tabButtons.set(tab.id, btn);
            }

            groupEl.appendChild(btnRow);
            this.tabBar.appendChild(groupEl);

            // Divider between groups (not after the last one)
            if (gi < groups.length - 1) {
                const divider = document.createElement('div');
                divider.className = 'veditor-tab-divider';
                this.tabBar.appendChild(divider);
            }
        }

        // ── Content area ──
        this.contentArea = document.createElement('div');
        this.contentArea.className = 'veditor-tab-content';

        for (const tab of this.allTabs) {
            const pane = document.createElement('div');
            pane.className = 'veditor-tab-pane';
            pane.id = `veditor-pane-${tab.id}`;
            pane.setAttribute('role', 'tabpanel');
            pane.setAttribute('aria-label', `${tab.label} options`);
            pane.appendChild(tab.content);
            this.contentArea.appendChild(pane);
            this.tabPanes.set(tab.id, pane);
        }

        this.container.append(this.tabBar, this.contentArea);

        // Activate first tab
        if (this.allTabs.length > 0) {
            this.activateTab(this.allTabs[0].id);
        }
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    activateTab(tabId: string): void {
        if (this.activeTabId === tabId) return;
        this.activeTabId = tabId;

        for (const [id, btn] of this.tabButtons) {
            const isActive = id === tabId;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-selected', String(isActive));
        }

        for (const [id, pane] of this.tabPanes) {
            pane.classList.toggle('active', id === tabId);
        }
    }

    /** Allow keyboard switching — call from modal's key handler */
    handleNumberKey(num: number): boolean {
        if (num >= 1 && num <= this.allTabs.length) {
            this.activateTab(this.allTabs[num - 1].id);
            return true;
        }
        return false;
    }

    private _shortcutLabel(idx: number): string {
        if (idx < 9) return String(idx + 1);
        if (idx === 9) return '0';
        if (idx === 10) return '-';
        if (idx === 11) return '=';
        return '';
    }

    destroy(): void {
        this.container.remove();
    }
}
