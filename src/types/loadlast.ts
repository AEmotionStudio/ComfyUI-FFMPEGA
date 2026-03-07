/**
 * LoadLast shared type definitions.
 */

// ─── View Modes ───────────────────────────────────────────────────────
export const VIEW_MODES = {
    PLAYBACK: 'playback',
    GRID: 'grid',
    SIDE_BY_SIDE: 'sidebyside',
    FILMSTRIP: 'filmstrip',
    SELECTED: 'selected',
    EDIT: 'edit',
} as const;

export type ViewMode = typeof VIEW_MODES[keyof typeof VIEW_MODES];

// ─── Mode Geometry ────────────────────────────────────────────────────

export interface GridGeometry {
    mode: typeof VIEW_MODES.GRID;
    cols: number;
    rows: number;
    count: number;
    cellW: number;
    cellH: number;
    timestamps: number[];
}

export interface FilmstripGeometry {
    mode: typeof VIEW_MODES.FILMSTRIP;
    frameWidth: number;
    frameHeight: number;
    gap: number;
    count: number;
    timestamps: number[];
}

export interface SideBySideGeometry {
    mode: typeof VIEW_MODES.SIDE_BY_SIDE;
    videoWidth: number;
    gap: number;
    timestamps: number[];
}

export type ModeGeometry = GridGeometry | FilmstripGeometry | SideBySideGeometry;

// ─── Edit Types ───────────────────────────────────────────────────────

export interface EditSegment {
    id: string;
    start: number;
    end: number;
}

export interface EditTimelineGeometry {
    trackX: number;
    trackY: number;
    trackW: number;
    trackH: number;
    duration: number;
    segments: Array<{
        id: string;
        x: number;
        w: number;
        start: number;
        end: number;
    }>;
}

// ─── Video Entry ──────────────────────────────────────────────────────

export interface VideoEntry {
    filename: string;
    subfolder: string;
    type: string;
    format: string;
    mtime?: number;
}

// ─── Filmstrip State ──────────────────────────────────────────────────

export const ZOOM_LEVELS = [1.0, 0.5, 0.2, 0.1] as const;
export const ZOOM_LABELS = ['1 fps', '2 fps', '5 fps', '10 fps'] as const;
export const FRAMES_PER_PAGE = 4;

// ─── Toolbar Button ───────────────────────────────────────────────────

export interface ToolbarButtonDef {
    id: ViewMode;
    icon: string;
    tip: string;
}

export const TOOLBAR_BUTTONS: ToolbarButtonDef[] = [
    {
        id: VIEW_MODES.PLAYBACK,
        icon: '<svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor"><polygon points="3,1 12,7 3,13"/></svg>',
        tip: 'Playback',
    },
    {
        id: VIEW_MODES.GRID,
        icon: '<svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor"><rect x="1" y="1" width="3" height="3" rx="0.5"/><rect x="5.5" y="1" width="3" height="3" rx="0.5"/><rect x="10" y="1" width="3" height="3" rx="0.5"/><rect x="1" y="5.5" width="3" height="3" rx="0.5"/><rect x="5.5" y="5.5" width="3" height="3" rx="0.5"/><rect x="10" y="5.5" width="3" height="3" rx="0.5"/><rect x="1" y="10" width="3" height="3" rx="0.5"/><rect x="5.5" y="10" width="3" height="3" rx="0.5"/><rect x="10" y="10" width="3" height="3" rx="0.5"/></svg>',
        tip: 'Grid (3×3)',
    },
    {
        id: VIEW_MODES.SIDE_BY_SIDE,
        icon: '<svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor"><rect x="1" y="1" width="5" height="12" rx="1"/><rect x="8" y="1" width="5" height="12" rx="1"/></svg>',
        tip: 'Side by Side',
    },
    {
        id: VIEW_MODES.FILMSTRIP,
        icon: '<svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor"><rect x="0" y="0" width="14" height="14" rx="1" opacity="0.3"/><rect x="1" y="3" width="3" height="8" rx="0.5"/><rect x="5.5" y="3" width="3" height="8" rx="0.5"/><rect x="10" y="3" width="3" height="8" rx="0.5"/><rect x="1.5" y="0.5" width="1" height="1.5" rx="0.3"/><rect x="4" y="0.5" width="1" height="1.5" rx="0.3"/><rect x="6.5" y="0.5" width="1" height="1.5" rx="0.3"/><rect x="9" y="0.5" width="1" height="1.5" rx="0.3"/><rect x="11.5" y="0.5" width="1" height="1.5" rx="0.3"/><rect x="1.5" y="12" width="1" height="1.5" rx="0.3"/><rect x="4" y="12" width="1" height="1.5" rx="0.3"/><rect x="6.5" y="12" width="1" height="1.5" rx="0.3"/><rect x="9" y="12" width="1" height="1.5" rx="0.3"/><rect x="11.5" y="12" width="1" height="1.5" rx="0.3"/></svg>',
        tip: 'Filmstrip',
    },
    {
        id: VIEW_MODES.SELECTED,
        icon: '<svg width="14" height="14" viewBox="0 0 14 14" fill="currentColor"><path d="M7 1 L9 5.5 L13.5 5.5 L10 8.5 L11.5 13 L7 10.5 L2.5 13 L4 8.5 L0.5 5.5 L5 5.5 Z"/></svg>',
        tip: 'Selected Frames',
    },
    {
        id: VIEW_MODES.EDIT,
        icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/></svg>',
        tip: 'Edit Video ✂️',
    },
];
