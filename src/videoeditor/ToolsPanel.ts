/**
 * ToolsPanel — tabbed sidebar wrapping Crop, Speed, Audio, Text panels.
 *
 * Renders a horizontal tab bar and swaps visibility of sub-component
 * content. Each tab and control is agent-discoverable via data-tool-id
 * and aria-label attributes.
 */

export interface TabDefinition {
    id: string;
    label: string;
    icon: string;
    content: HTMLElement;
}

export class ToolsPanel {
    private container: HTMLDivElement;
    private tabBar: HTMLDivElement;
    private contentArea: HTMLDivElement;
    private tabs: TabDefinition[] = [];
    private tabButtons: Map<string, HTMLButtonElement> = new Map();
    private tabPanes: Map<string, HTMLDivElement> = new Map();
    private activeTabId: string = '';

    constructor(tabs: TabDefinition[]) {
        this.tabs = tabs;

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

        // ── Content area ──
        this.contentArea = document.createElement('div');
        this.contentArea.className = 'veditor-tab-content';

        for (const tab of tabs) {
            // Tab button
            const btn = document.createElement('button');
            btn.className = 'veditor-tab';
            btn.innerHTML = `${tab.icon} ${tab.label}`;
            btn.setAttribute('role', 'tab');
            btn.setAttribute('aria-selected', 'false');
            btn.setAttribute('aria-controls', `veditor-pane-${tab.id}`);
            btn.setAttribute('data-tool-id', `veditor-tab-${tab.id}`);
            btn.setAttribute('aria-label', `${tab.label} tools`);
            btn.title = `${tab.label} tools`;
            btn.addEventListener('click', () => this.activateTab(tab.id));
            this.tabBar.appendChild(btn);
            this.tabButtons.set(tab.id, btn);

            // Tab pane
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
        if (tabs.length > 0) {
            this.activateTab(tabs[0].id);
        }
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    activateTab(tabId: string): void {
        if (this.activeTabId === tabId) return;
        this.activeTabId = tabId;

        // Update button states
        for (const [id, btn] of this.tabButtons) {
            const isActive = id === tabId;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-selected', String(isActive));
        }

        // Update pane visibility
        for (const [id, pane] of this.tabPanes) {
            pane.classList.toggle('active', id === tabId);
        }
    }

    /** Allow keyboard switching — call from modal's key handler */
    handleNumberKey(num: number): boolean {
        if (num >= 1 && num <= this.tabs.length) {
            this.activateTab(this.tabs[num - 1].id);
            return true;
        }
        return false;
    }

    destroy(): void {
        this.container.remove();
    }
}
