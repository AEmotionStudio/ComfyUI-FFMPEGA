/**
 * FFMPEGA Help Sidebar — Main module.
 *
 * Registers a sidebar tab with ComfyUI and renders the help panel
 * with context-aware node documentation, tips, shortcuts, workflows,
 * changelog, search, and external links.
 */

import { app } from "comfyui/app";
import type { ComfyNode } from "@ffmpega/types/comfyui";
import {
    NODE_DOCS,
    TIPS_AND_TRICKS,
    EDITOR_SHORTCUTS,
    CHANGELOG_HIGHLIGHTS,
    EXAMPLE_WORKFLOWS,
    EXTERNAL_LINKS,
    type NodeDoc,
} from "./sidebar_docs";
import SIDEBAR_CSS from "./sidebar.css?inline";

// ── State ───────────────────────────────────────────────────────────

let sidebarRegistered = false;
let currentHighlightedType: string | null = null;
let pollIntervalId: ReturnType<typeof setInterval> | null = null;

/** Set of all FFMPEGA node types for fast lookup */
const FFMPEGA_NODE_TYPES = new Set(NODE_DOCS.map((n) => n.type));

// ── CSS Loader ──────────────────────────────────────────────────────

function loadSidebarStyles(): void {
    const id = "ffmpega-sidebar-styles";
    if (document.getElementById(id)) return;

    const style = document.createElement("style");
    style.id = id;
    style.textContent = SIDEBAR_CSS;
    document.head.appendChild(style);
}

// ── Helpers ─────────────────────────────────────────────────────────

function el(tag: string, cls?: string, text?: string): HTMLElement {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text) e.textContent = text;
    return e;
}

function makeSection(
    id: string,
    title: string,
    collapsed: boolean,
    renderBody: (body: HTMLElement) => void,
): HTMLElement {
    const section = el("div", "ffmpega-section");
    section.dataset.sectionId = id;

    // Header
    const header = el("div", `ffmpega-section-header${collapsed ? " collapsed" : ""}`);
    header.setAttribute("tabindex", "0");
    header.setAttribute("role", "button");
    header.setAttribute("aria-expanded", String(!collapsed));
    header.innerHTML = `<span class="chevron">▼</span><span class="section-title">${title}</span>`;

    // Body
    const body = el("div", `ffmpega-section-body${collapsed ? " collapsed" : ""}`);
    renderBody(body);

    // Toggle
    const toggle = () => {
        const isCollapsed = header.classList.toggle("collapsed");
        body.classList.toggle("collapsed", isCollapsed);
        header.setAttribute("aria-expanded", String(!isCollapsed));
    };
    header.addEventListener("click", toggle);
    header.addEventListener("keydown", (e) => {
        if ((e as KeyboardEvent).key === "Enter" || (e as KeyboardEvent).key === " ") {
            e.preventDefault();
            toggle();
        }
    });

    section.appendChild(header);
    section.appendChild(body);
    return section;
}

// ── Node doc renderer ───────────────────────────────────────────────

function renderNodeDoc(body: HTMLElement, doc: NodeDoc): void {
    // Description
    body.appendChild(el("div", "ffmpega-node-desc", doc.description));

    // Tips
    if (doc.tips.length > 0) {
        const ul = el("ul", "ffmpega-tips");
        for (const tip of doc.tips) {
            ul.appendChild(el("li", undefined, tip));
        }
        body.appendChild(ul);
    }

    // Inputs table
    if (doc.inputs.length > 0) {
        const table = document.createElement("table");
        table.className = "ffmpega-inputs-table";
        table.innerHTML = "<thead><tr><th>Input</th><th>Info</th></tr></thead>";
        const tbody = document.createElement("tbody");
        for (const inp of doc.inputs) {
            const tr = document.createElement("tr");
            tr.innerHTML = `<td>${inp.name}</td><td>${inp.info}</td>`;
            tbody.appendChild(tr);
        }
        table.appendChild(tbody);
        body.appendChild(table);
    }

    // Related workflows
    if (doc.relatedWorkflows && doc.relatedWorkflows.length > 0) {
        const label = el("div", "ffmpega-group-title", "RELATED WORKFLOWS");
        body.appendChild(label);
        for (const wf of doc.relatedWorkflows) {
            const info = EXAMPLE_WORKFLOWS.find((w) => w.filename === wf);
            if (info) {
                const item = el("div", "ffmpega-workflow-item");
                item.innerHTML = `<span>📂</span><div><div class="ffmpega-workflow-title">${info.title}</div></div>`;
                item.title = `Load workflow: ${info.title}`;
                body.appendChild(item);
            }
        }
    }
}

// ── Main render ─────────────────────────────────────────────────────

function renderSidebar(container: HTMLElement): void {
    if (container.querySelector(".ffmpega-sidebar")) return;
    container.innerHTML = "";

    const sidebar = el("div", "ffmpega-sidebar");

    // ── Header
    const header = el("div", "ffmpega-sidebar-header");
    header.innerHTML = `<span>📖</span><h2>FFMPEGA Help</h2><span class="version-badge">v2.14</span>`;
    sidebar.appendChild(header);

    // ── Context hint (shows selected node — updated by polling)
    const contextHint = el("div", "ffmpega-context-hint ffmpega-hidden");
    contextHint.id = "ffmpega-context-hint";
    contextHint.innerHTML = `<span>🎯</span> Viewing: <span class="node-name" id="ffmpega-context-name"></span>`;
    sidebar.appendChild(contextHint);

    // ── Search bar
    const searchBar = el("div", "ffmpega-search-bar");
    const searchInput = document.createElement("input");
    searchInput.type = "text";
    searchInput.className = "ffmpega-search-input";
    searchInput.placeholder = "Search docs…";
    searchInput.setAttribute("aria-label", "Search FFMPEGA documentation");
    searchBar.appendChild(searchInput);
    sidebar.appendChild(searchBar);

    // ── Content
    const content = el("div", "ffmpega-sidebar-content");

    // 1. Node Reference
    content.appendChild(el("div", "ffmpega-group-title", "NODE REFERENCE"));
    for (const doc of NODE_DOCS) {
        const section = makeSection(
            `node-${doc.type}`,
            doc.title,
            true,
            (body) => renderNodeDoc(body, doc),
        );
        section.dataset.nodeType = doc.type;
        section.dataset.searchText = [
            doc.title, doc.description, ...doc.tips,
            ...doc.inputs.map((i) => `${i.name} ${i.info}`),
        ].join(" ").toLowerCase();
        content.appendChild(section);
    }

    // 2. Tips & Tricks
    content.appendChild(el("div", "ffmpega-group-title", "TIPS & TRICKS"));
    for (const cat of TIPS_AND_TRICKS) {
        const section = makeSection(
            `tips-${cat.title.toLowerCase()}`,
            `${cat.icon} ${cat.title}`,
            true,
            (body) => {
                const ul = el("ul", "ffmpega-tips");
                for (const tip of cat.tips) {
                    ul.appendChild(el("li", undefined, tip));
                }
                body.appendChild(ul);
            },
        );
        section.dataset.searchText = [cat.title, ...cat.tips].join(" ").toLowerCase();
        content.appendChild(section);
    }

    // 3. Video Editor Shortcuts
    const shortcutsSection = makeSection(
        "shortcuts",
        "⌨️ Video Editor Shortcuts",
        true,
        (body) => {
            const table = document.createElement("table");
            table.className = "ffmpega-shortcuts-table";
            for (const sc of EDITOR_SHORTCUTS) {
                const tr = document.createElement("tr");
                tr.innerHTML = `<td><span class="ffmpega-kbd">${sc.key}</span></td><td>${sc.action}</td>`;
                table.appendChild(tr);
            }
            body.appendChild(table);
        },
    );
    shortcutsSection.dataset.searchText = ["shortcuts", "keyboard", "keys",
        ...EDITOR_SHORTCUTS.map((s) => `${s.key} ${s.action}`)].join(" ").toLowerCase();
    content.appendChild(shortcutsSection);

    // 4. Quick Start Workflows
    content.appendChild(el("div", "ffmpega-group-title", "EXAMPLE WORKFLOWS"));
    const workflowsSection = makeSection(
        "workflows",
        "📂 Example Workflows",
        true,
        (body) => {
            for (const wf of EXAMPLE_WORKFLOWS) {
                const item = el("div", "ffmpega-workflow-item");
                item.innerHTML = `<span>📄</span><div><div class="ffmpega-workflow-title">${wf.title}</div><div class="ffmpega-workflow-desc">${wf.description}</div></div>`;
                item.title = `Workflow: ${wf.title}`;
                body.appendChild(item);
            }
        },
    );
    workflowsSection.dataset.searchText = EXAMPLE_WORKFLOWS
        .map((w) => `${w.title} ${w.description}`).join(" ").toLowerCase();
    content.appendChild(workflowsSection);

    // 5. What's New
    content.appendChild(el("div", "ffmpega-group-title", "WHAT'S NEW"));
    for (const entry of CHANGELOG_HIGHLIGHTS) {
        const section = makeSection(
            `changelog-${entry.version}`,
            `🆕 v${entry.version}`,
            true,
            (body) => {
                const versionLine = el("div", "ffmpega-changelog-version");
                versionLine.innerHTML = `v${entry.version}<span class="ffmpega-changelog-date">${entry.date}</span>`;
                body.appendChild(versionLine);

                const ul = el("ul", "ffmpega-changelog-list") as HTMLUListElement;
                for (const hl of entry.highlights) {
                    ul.appendChild(el("li", undefined, hl));
                }
                body.appendChild(ul);
            },
        );
        section.dataset.searchText = [entry.version, ...entry.highlights].join(" ").toLowerCase();
        content.appendChild(section);
    }

    // 6. External Links
    content.appendChild(el("div", "ffmpega-group-title", "LINKS"));
    const linksSection = makeSection(
        "links",
        "🔗 Resources & Links",
        true,
        (body) => {
            for (const link of EXTERNAL_LINKS) {
                const a = document.createElement("a");
                a.className = "ffmpega-link-item";
                a.href = link.url;
                a.target = "_blank";
                a.rel = "noopener noreferrer";
                a.innerHTML = `<span>${link.icon}</span>${link.label}`;
                body.appendChild(a);
            }
        },
    );
    linksSection.dataset.searchText = EXTERNAL_LINKS
        .map((l) => l.label).join(" ").toLowerCase();
    content.appendChild(linksSection);

    sidebar.appendChild(content);
    container.appendChild(sidebar);

    // ── Search handler
    searchInput.addEventListener("input", () => {
        const query = searchInput.value.trim().toLowerCase();
        const sections = content.querySelectorAll<HTMLElement>(".ffmpega-section");
        const groupTitles = content.querySelectorAll<HTMLElement>(".ffmpega-group-title");

        if (!query) {
            sections.forEach((s) => s.classList.remove("ffmpega-hidden"));
            groupTitles.forEach((g) => g.classList.remove("ffmpega-hidden"));
            return;
        }

        // Hide/show sections based on search text
        sections.forEach((s) => {
            const text = s.dataset.searchText || "";
            const matches = text.includes(query);
            s.classList.toggle("ffmpega-hidden", !matches);
            // Auto-expand matching sections
            if (matches) {
                s.querySelector(".ffmpega-section-header")?.classList.remove("collapsed");
                s.querySelector(".ffmpega-section-body")?.classList.remove("collapsed");
            }
        });

        // Hide group titles if all their sections are hidden
        groupTitles.forEach((g) => {
            let next = g.nextElementSibling;
            let hasVisible = false;
            while (next && !next.classList.contains("ffmpega-group-title")) {
                if (next.classList.contains("ffmpega-section") && !next.classList.contains("ffmpega-hidden")) {
                    hasVisible = true;
                    break;
                }
                next = next.nextElementSibling;
            }
            g.classList.toggle("ffmpega-hidden", !hasVisible);
        });
    });

    // ── Start polling for selected node
    loadSidebarStyles();
    startNodePolling(content);
}

// ── Node selection polling ──────────────────────────────────────────

function startNodePolling(content: HTMLElement): void {
    if (pollIntervalId) clearInterval(pollIntervalId);

    pollIntervalId = setInterval(() => {
        try {
            const selectedNode = getSelectedFFMPEGANode();
            const nodeType = selectedNode?.type || null;

            if (nodeType === currentHighlightedType) return;
            currentHighlightedType = nodeType;

            // Update context hint
            const hint = document.getElementById("ffmpega-context-hint");
            const nameEl = document.getElementById("ffmpega-context-name");
            if (hint && nameEl) {
                if (nodeType) {
                    const doc = NODE_DOCS.find((d) => d.type === nodeType);
                    nameEl.textContent = doc?.title || nodeType;
                    hint.classList.remove("ffmpega-hidden");
                } else {
                    hint.classList.add("ffmpega-hidden");
                }
            }

            // Clear previous highlights
            content.querySelectorAll<HTMLElement>(".ffmpega-section-header.highlighted")
                .forEach((h) => h.classList.remove("highlighted"));

            if (!nodeType) return;

            // Find and highlight the matching section
            const section = content.querySelector<HTMLElement>(
                `.ffmpega-section[data-node-type="${nodeType}"]`,
            );
            if (!section) return;

            const header = section.querySelector<HTMLElement>(".ffmpega-section-header");
            const body = section.querySelector<HTMLElement>(".ffmpega-section-body");
            if (header) {
                header.classList.add("highlighted");
                header.classList.remove("collapsed");
                header.setAttribute("aria-expanded", "true");
            }
            if (body) {
                body.classList.remove("collapsed");
            }

            // Scroll into view
            section.scrollIntoView({ behavior: "smooth", block: "nearest" });
        } catch {
            // Silently ignore errors during polling
        }
    }, 500);
}

function getSelectedFFMPEGANode(): ComfyNode | null {
    try {
        // Check for selected nodes first
        const graph = app?.graph;
        if (!graph?._nodes) return null;

        for (const node of graph._nodes) {
            if (
                node &&
                FFMPEGA_NODE_TYPES.has(node.type) &&
                // Check if the node is selected (LiteGraph selection)
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                (node as any).is_selected
            ) {
                return node;
            }
        }

        // Fallback: check node_over (hovered)
        const hovered = app?.canvas?.node_over;
        if (hovered && FFMPEGA_NODE_TYPES.has(hovered.type)) {
            return hovered;
        }

        return null;
    } catch {
        return null;
    }
}

// ── Registration ────────────────────────────────────────────────────

export function registerSidebar(): void {
    if (sidebarRegistered) return;

    if (!app.extensionManager) {
        console.warn("FFMPEGA: extensionManager not available, sidebar registration skipped");
        return;
    }

    try {
        app.extensionManager.registerSidebarTab({
            id: "ffmpega-help",
            icon: "pi pi-book",
            title: "FFMPEGA",
            tooltip: "FFMPEGA Help & Documentation",
            type: "custom",
            render: (el: HTMLElement) => {
                renderSidebar(el);
            },
        });

        sidebarRegistered = true;
        console.log("FFMPEGA: Help sidebar registered");
    } catch (e) {
        console.warn("FFMPEGA: Failed to register sidebar:", e);
    }
}

/**
 * Initialize sidebar — called from the extension's setup() hook.
 * Defers registration to ensure app is fully ready.
 */
export function initSidebar(): void {
    setTimeout(() => {
        registerSidebar();
    }, 100);
}
