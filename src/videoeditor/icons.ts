/**
 * icons.ts — Inline SVG icons for the Video Editor.
 *
 * All icons sourced from Lucide (https://lucide.dev) — ISC licensed.
 * lucide-static v0.577.0
 *
 * Each function returns an SVG string sized at 1em so it scales with
 * surrounding font-size. All use currentColor for stroke to inherit
 * the parent text colour.
 */

/** Shared SVG wrapper — stroke-based Lucide style */
const L = (inner: string): string =>
    `<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-0.125em">${inner}</svg>`;

// ── Title / Branding ───────────────────────────────────────────────

/** Clapperboard — lucide/clapperboard */
export const iconClapperboard = L(
    '<path d="m12.296 3.464 3.02 3.956"/>' +
    '<path d="M20.2 6 3 11l-.9-2.4c-.3-1.1.3-2.2 1.3-2.5l13.5-4c1.1-.3 2.2.3 2.5 1.3z"/>' +
    '<path d="M3 11h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>' +
    '<path d="m6.18 5.276 3.1 3.899"/>'
);

// ── Transport ──────────────────────────────────────────────────────

/** Play — lucide/play */
export const iconPlay = L(
    '<path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"/>'
);

/** Pause — lucide/pause */
export const iconPause = L(
    '<rect x="14" y="3" width="5" height="18" rx="1"/>' +
    '<rect x="5" y="3" width="5" height="18" rx="1"/>'
);

/** Skip back — lucide/skip-back */
export const iconStepBack = L(
    '<path d="M17.971 4.285A2 2 0 0 1 21 6v12a2 2 0 0 1-3.029 1.715l-9.997-5.998a2 2 0 0 1-.003-3.432z"/>' +
    '<path d="M3 20V4"/>'
);

/** Skip forward — lucide/skip-forward */
export const iconStepForward = L(
    '<path d="M21 4v16"/>' +
    '<path d="M6.029 4.285A2 2 0 0 0 3 6v12a2 2 0 0 0 3.029 1.715l9.997-5.998a2 2 0 0 0 .003-3.432z"/>'
);

/** Skip to start — lucide/skip-back (bar + triangle) */
export const iconSkipStart = L(
    '<path d="M19 20 9 12l10-8z"/>' +
    '<line x1="5" x2="5" y1="19" y2="5"/>'
);

/** Repeat / Loop — lucide/repeat */
export const iconRepeat = L(
    '<path d="m17 2 4 4-4 4"/>' +
    '<path d="M3 11v-1a4 4 0 0 1 4-4h14"/>' +
    '<path d="m7 22-4-4 4-4"/>' +
    '<path d="M21 13v1a4 4 0 0 1-4 4H3"/>'
);

// ── Toolbar ────────────────────────────────────────────────────────

/** Mouse pointer / Select — lucide/mouse-pointer */
export const iconCursor = L(
    '<path d="M12.586 12.586 19 19"/>' +
    '<path d="M3.688 3.037a.497.497 0 0 0-.651.651l6.5 15.999a.501.501 0 0 0 .947-.062l1.569-6.083a2 2 0 0 1 1.448-1.479l6.124-1.579a.5.5 0 0 0 .063-.947z"/>'
);

/** Split — lucide/split */
export const iconSplit = L(
    '<path d="M16 3h5v5"/>' +
    '<path d="M8 3H3v5"/>' +
    '<path d="M12 22v-8.3a4 4 0 0 0-1.172-2.872L3 3"/>' +
    '<path d="m15 9 6-6"/>'
);

/** Trash — lucide/trash-2 */
export const iconTrash = L(
    '<path d="M10 11v6"/><path d="M14 11v6"/>' +
    '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>' +
    '<path d="M3 6h18"/>' +
    '<path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'
);

// ── Tool Tabs ──────────────────────────────────────────────────────

/** Crop — lucide/crop */
export const iconCrop = L(
    '<path d="M6 2v14a2 2 0 0 0 2 2h14"/>' +
    '<path d="M18 22V8a2 2 0 0 0-2-2H2"/>'
);

/** Gauge / Speed — lucide/gauge */
export const iconGauge = L(
    '<path d="m12 14 4-4"/>' +
    '<path d="M3.34 19a10 10 0 1 1 17.32 0"/>'
);

/** Volume — lucide/volume-2 */
export const iconVolume = L(
    '<path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z"/>' +
    '<path d="M16 9a5 5 0 0 1 0 6"/>' +
    '<path d="M19.364 18.364a9 9 0 0 0 0-12.728"/>'
);

/** Muted — lucide/volume-x */
export const iconMuted = L(
    '<path d="M11 4.702a.705.705 0 0 0-1.203-.498L6.413 7.587A1.4 1.4 0 0 1 5.416 8H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2.416a1.4 1.4 0 0 1 .997.413l3.383 3.384A.705.705 0 0 0 11 19.298z"/>' +
    '<line x1="22" x2="16" y1="9" y2="15"/>' +
    '<line x1="16" x2="22" y1="9" y2="15"/>'
);

/** Type / Text — lucide/type */
export const iconText = L(
    '<path d="M12 4v16"/>' +
    '<path d="M4 7V5a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v2"/>' +
    '<path d="M9 20h6"/>'
);

// ── Header Actions ─────────────────────────────────────────────────

/** Undo — lucide/undo-2 */
export const iconUndo = L(
    '<path d="M9 14 4 9l5-5"/>' +
    '<path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"/>'
);

/** Redo — lucide/redo-2 */
export const iconRedo = L(
    '<path d="m15 14 5-5-5-5"/>' +
    '<path d="M20 9H9.5A5.5 5.5 0 0 0 4 14.5A5.5 5.5 0 0 0 9.5 20H13"/>'
);

/** Check — lucide/check */
export const iconCheck = L('<path d="M20 6 9 17l-5-5"/>');

/** Close / X — lucide/x */
export const iconClose = L('<path d="M18 6 6 18"/><path d="m6 6 12 12"/>');

// ── Monitor / Zoom ────────────────────────────────────────────────

/** Zoom In — lucide/zoom-in */
export const iconZoomIn = L(
    '<circle cx="11" cy="11" r="8"/>' +
    '<line x1="21" x2="16.65" y1="21" y2="16.65"/>' +
    '<line x1="11" x2="11" y1="8" y2="14"/>' +
    '<line x1="8" x2="14" y1="11" y2="11"/>'
);

/** Zoom Out — lucide/zoom-out */
export const iconZoomOut = L(
    '<circle cx="11" cy="11" r="8"/>' +
    '<line x1="21" x2="16.65" y1="21" y2="16.65"/>' +
    '<line x1="8" x2="14" y1="11" y2="11"/>'
);

/** Maximize / Fit — lucide/maximize */
export const iconMaximize = L(
    '<path d="M8 3H5a2 2 0 0 0-2 2v3"/>' +
    '<path d="M21 8V5a2 2 0 0 0-2-2h-3"/>' +
    '<path d="M3 16v3a2 2 0 0 0 2 2h3"/>' +
    '<path d="M16 21h3a2 2 0 0 0 2-2v-3"/>'
);

// ── Toolbar Extras ────────────────────────────────────────────────

/** Rotate CCW / Reset — lucide/rotate-ccw */
export const iconReset = L(
    '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>' +
    '<path d="M3 3v5h5"/>'
);

/** Flip Horizontal — lucide/flip-horizontal-2 */
export const iconFlip = L(
    '<path d="m3 7 5 5-5 5V7"/>' +
    '<path d="m21 7-5 5 5 5V7"/>' +
    '<path d="M12 20v2"/>' +
    '<path d="M12 14v2"/>' +
    '<path d="M12 8v2"/>' +
    '<path d="M12 2v2"/>'
);

/** Arrow Down-Up / Reverse — lucide/arrow-down-up */
export const iconReverse = L(
    '<path d="m3 16 4 4 4-4"/>' +
    '<path d="M7 20V4"/>' +
    '<path d="m21 8-4-4-4 4"/>' +
    '<path d="M17 4v16"/>'
);

/** Spline / Curve — lucide/spline */
export const iconCurve = L(
    '<circle cx="19" cy="5" r="2"/>' +
    '<circle cx="5" cy="19" r="2"/>' +
    '<path d="M5 17A12 12 0 0 1 17 5"/>'
);

/** Film / Frame Interpolation — lucide/film */
export const iconFilm = L(
    '<rect width="18" height="18" x="3" y="3" rx="2"/>' +
    '<path d="M7 3v18"/>' +
    '<path d="M3 7.5h4"/>' +
    '<path d="M3 12h18"/>' +
    '<path d="M3 16.5h4"/>' +
    '<path d="M17 3v18"/>' +
    '<path d="M17 7.5h4"/>' +
    '<path d="M17 16.5h4"/>'
);

/** Music — lucide/music */
export const iconMusic = L(
    '<path d="M9 18V5l12-2v13"/>' +
    '<circle cx="6" cy="18" r="3"/>' +
    '<circle cx="18" cy="16" r="3"/>'
);

/** Bold — lucide/bold */
export const iconBold = L(
    '<path d="M6 12h9a4 4 0 0 1 0 8H7a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h7a4 4 0 0 1 0 8"/>'
);

/** Italic — lucide/italic */
export const iconItalic = L(
    '<line x1="19" x2="10" y1="4" y2="4"/>' +
    '<line x1="14" x2="5" y1="20" y2="20"/>' +
    '<line x1="15" x2="9" y1="4" y2="20"/>'
);

/** Align Left — lucide/align-left */
export const iconAlignLeft = L(
    '<line x1="21" x2="3" y1="6" y2="6"/>' +
    '<line x1="15" x2="3" y1="12" y2="12"/>' +
    '<line x1="17" x2="3" y1="18" y2="18"/>'
);

/** Align Center — lucide/align-center */
export const iconAlignCenter = L(
    '<line x1="21" x2="3" y1="6" y2="6"/>' +
    '<line x1="17" x2="7" y1="12" y2="12"/>' +
    '<line x1="19" x2="5" y1="18" y2="18"/>'
);

/** Align Right — lucide/align-right */
export const iconAlignRight = L(
    '<line x1="21" x2="3" y1="6" y2="6"/>' +
    '<line x1="21" x2="9" y1="12" y2="12"/>' +
    '<line x1="21" x2="7" y1="18" y2="18"/>'
);

/** Plus / Add — lucide/plus */
export const iconPlus = L(
    '<path d="M5 12h14"/>' +
    '<path d="M12 5v14"/>'
);

/** Minus — lucide/minus */
export const iconMinus = L('<path d="M5 12h14"/>');

/** Shuffle / Transition — lucide/shuffle */
export const iconShuffle = L(
    '<path d="M2 18h1.4c1.3 0 2.5-.6 3.3-1.7l6.1-8.6c.7-1.1 2-1.7 3.3-1.7H22"/>' +
    '<path d="m18 2 4 4-4 4"/>' +
    '<path d="M2 6h1.9c1.5 0 2.9.9 3.6 2.2"/>' +
    '<path d="M22 18h-5.9c-1.3 0-2.6-.7-3.3-1.8l-.5-.8"/>' +
    '<path d="m18 14 4 4-4 4"/>'
);

/** Help Circle — lucide/help-circle */
export const iconHelp = L(
    '<circle cx="12" cy="12" r="10"/>' +
    '<path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>' +
    '<path d="M12 17h.01"/>'
);

/** Palette — lucide/palette */
export const iconPalette = L(
    '<circle cx="13.5" cy="6.5" r=".5" fill="currentColor"/>' +
    '<circle cx="17.5" cy="10.5" r=".5" fill="currentColor"/>' +
    '<circle cx="8.5" cy="7.5" r=".5" fill="currentColor"/>' +
    '<circle cx="6.5" cy="12.5" r=".5" fill="currentColor"/>' +
    '<path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z"/>'
);

/** Wand Sparkles — lucide/wand-sparkles */
export const iconWand = L(
    '<path d="m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 0 1.72l1.28 1.28a1.2 1.2 0 0 0 1.72 0L21.64 5.36a1.2 1.2 0 0 0 0-1.72"/>' +
    '<path d="m14 7 3 3"/>' +
    '<path d="M5 6v4"/>' +
    '<path d="M19 14v4"/>' +
    '<path d="M10 2v2"/>' +
    '<path d="M7 8H3"/>' +
    '<path d="M21 16h-4"/>' +
    '<path d="M11 3H9"/>'
);

/** Sun — lucide/sun */
export const iconSun = L(
    '<circle cx="12" cy="12" r="4"/>' +
    '<path d="M12 2v2"/>' +
    '<path d="M12 20v2"/>' +
    '<path d="m4.93 4.93 1.41 1.41"/>' +
    '<path d="m17.66 17.66 1.41 1.41"/>' +
    '<path d="M2 12h2"/>' +
    '<path d="M20 12h2"/>' +
    '<path d="m6.34 17.66-1.41 1.41"/>' +
    '<path d="m19.07 4.93-1.41 1.41"/>'
);

/** Settings — lucide/settings-2 */
export const iconSettings = L(
    '<path d="M20 7h-9"/>' +
    '<path d="M14 17H5"/>' +
    '<circle cx="17" cy="17" r="3"/>' +
    '<circle cx="7" cy="7" r="3"/>'
);

/** Layers — lucide/layers */
export const iconLayers = L(
    '<path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.84Z"/>' +
    '<path d="m22.18 12.08-1.39-.63-8.58 3.9a2 2 0 0 1-1.66 0l-8.58-3.9-1.39.63a1 1 0 0 0 0 1.84l8.58 3.9a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.84Z"/>' +
    '<path d="m22.18 16.08-1.39-.63-8.58 3.9a2 2 0 0 1-1.66 0l-8.58-3.9-1.39.63a1 1 0 0 0 0 1.84l8.58 3.9a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.84Z"/>'
);

/** Brain — lucide/brain */
export const iconBrain = L(
    '<path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/>' +
    '<path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/>' +
    '<path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/>' +
    '<path d="M17.599 6.5a3 3 0 0 0 .399-1.375"/>' +
    '<path d="M6.003 5.125A3 3 0 0 0 6.401 6.5"/>' +
    '<path d="M3.477 10.896a4 4 0 0 1 .585-.396"/>' +
    '<path d="M19.938 10.5a4 4 0 0 1 .585.396"/>' +
    '<path d="M6 18a4 4 0 0 1-1.967-.516"/>' +
    '<path d="M19.967 17.484A4 4 0 0 1 18 18"/>'
);

/** Move — lucide/move */
export const iconMove = L(
    '<polyline points="5 9 2 12 5 15"/>' +
    '<polyline points="9 5 12 2 15 5"/>' +
    '<polyline points="15 19 12 22 9 19"/>' +
    '<polyline points="19 9 22 12 19 15"/>' +
    '<line x1="2" x2="22" y1="12" y2="12"/>' +
    '<line x1="12" x2="12" y1="2" y2="22"/>'
);
