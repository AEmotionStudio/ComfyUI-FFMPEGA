/**
 * icons.ts — Inline SVG icons for the FacePoke editor.
 *
 * All icons sourced from Lucide (https://lucide.dev) — ISC licensed.
 * lucide-static v0.577.0
 *
 * Reuses the same wrapper as the Video Editor so icons are visually
 * consistent across the extension.
 */

/** Shared SVG wrapper — stroke-based Lucide style */
const L = (inner: string): string =>
    `<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-0.125em">${inner}</svg>`;

// ── Transport ──────────────────────────────────────────────────────

/** Play — lucide/play */
export const fpIconPlay = L(
    '<path d="M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z"/>'
);

/** Pause — lucide/pause */
export const fpIconPause = L(
    '<rect x="14" y="3" width="5" height="18" rx="1"/>' +
    '<rect x="5" y="3" width="5" height="18" rx="1"/>'
);

/** Skip to start — lucide/skip-back */
export const fpIconSkipStart = L(
    '<path d="M19 20 9 12l10-8z"/>' +
    '<line x1="5" x2="5" y1="19" y2="5"/>'
);

/** Skip to end — lucide/skip-forward */
export const fpIconSkipEnd = L(
    '<path d="M5 4l10 8-10 8z"/>' +
    '<line x1="19" x2="19" y1="5" y2="19"/>'
);

/** Chevron left — lucide/chevron-left */
export const fpIconPrev = L('<path d="m15 18-6-6 6-6"/>');

/** Chevron right — lucide/chevron-right */
export const fpIconNext = L('<path d="m9 18 6-6-6-6"/>');

// ── Actions ────────────────────────────────────────────────────────

/** Undo — lucide/undo-2 */
export const fpIconUndo = L(
    '<path d="M9 14 4 9l5-5"/>' +
    '<path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"/>'
);

/** Redo — lucide/redo-2 */
export const fpIconRedo = L(
    '<path d="m15 14 5-5-5-5"/>' +
    '<path d="M20 9H9.5A5.5 5.5 0 0 0 4 14.5A5.5 5.5 0 0 0 9.5 20H13"/>'
);

/** Check — lucide/check */
export const fpIconCheck = L('<path d="M20 6 9 17l-5-5"/>');

/** Close / X — lucide/x */
export const fpIconClose = L('<path d="M18 6 6 18"/><path d="m6 6 12 12"/>');

/** Reset / Rotate CCW — lucide/rotate-ccw */
export const fpIconReset = L(
    '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>' +
    '<path d="M3 3v5h5"/>'
);

// ── Toggle / View ─────────────────────────────────────────────────

/** Eye — lucide/eye */
export const fpIconEye = L(
    '<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/>' +
    '<circle cx="12" cy="12" r="3"/>'
);

/** Eye Off — lucide/eye-off */
export const fpIconEyeOff = L(
    '<path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"/>' +
    '<path d="M14.084 14.158a3 3 0 0 1-4.242-4.242"/>' +
    '<path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"/>' +
    '<path d="m2 2 20 20"/>'
);

/** Scan Search / Landmarks — lucide/scan-search */
export const fpIconLandmarks = L(
    '<path d="M3 7V5a2 2 0 0 1 2-2h2"/>' +
    '<path d="M17 3h2a2 2 0 0 1 2 2v2"/>' +
    '<path d="M21 17v2a2 2 0 0 1-2 2h-2"/>' +
    '<path d="M7 21H5a2 2 0 0 1-2-2v-2"/>' +
    '<circle cx="12" cy="12" r="3"/>' +
    '<path d="m16 16-1.9-1.9"/>'
);

// ── Editing ────────────────────────────────────────────────────────

/** Theater (face) — lucide/drama */
export const fpIconFace = L(
    '<path d="M10 11h.01"/>' +
    '<path d="M14 6h.01"/>' +
    '<path d="M18 6h.01"/>' +
    '<path d="M6.5 13.1h.01"/>' +
    '<path d="M22 5c0 9-4 12-6 12s-6-3-6-12c0-2 2-3 6-3s6 1 6 3"/>' +
    '<path d="M17.4 9.9c-.8.8-2 .8-2.8 0"/>' +
    '<path d="M10.1 7.1C9 7.2 7.7 7.7 6 8.6c-3.5 2-4.7 3.9-3.7 5.6 4.5 7.8 9.5 8.4 11.2 7.4.9-.5 1.9-2.1 1.9-4.7"/>' +
    '<path d="M9.1 16.5c.3-1.1 1.4-1.7 2.4-1.4"/>'
);

/** Spline / Interpolate — lucide/spline */
export const fpIconInterpolate = L(
    '<circle cx="19" cy="5" r="2"/>' +
    '<circle cx="5" cy="19" r="2"/>' +
    '<path d="M5 17A12 12 0 0 1 17 5"/>'
);

/** Forward / Pass through — lucide/arrow-right */
export const fpIconPassThrough = L(
    '<path d="M5 12h14"/>' +
    '<path d="m12 5 7 7-7 7"/>'
);

/** Scan Face / Blaze detector — lucide/scan-face */
export const fpIconScanFace = L(
    '<path d="M3 7V5a2 2 0 0 1 2-2h2"/>' +
    '<path d="M17 3h2a2 2 0 0 1 2 2v2"/>' +
    '<path d="M21 17v2a2 2 0 0 1-2 2h-2"/>' +
    '<path d="M7 21H5a2 2 0 0 1-2-2v-2"/>' +
    '<path d="M8 14s1.5 2 4 2 4-2 4-2"/>' +
    '<path d="M9 9h.01"/>' +
    '<path d="M15 9h.01"/>'
);

/** Upload — lucide/upload */
export const fpIconUpload = L(
    '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>' +
    '<polyline points="17 8 12 3 7 8"/>' +
    '<line x1="12" x2="12" y1="3" y2="15"/>'
);

/** Video — lucide/video */
export const fpIconVideo = L(
    '<path d="m16 13 5.223 3.482a.5.5 0 0 0 .777-.416v-8.132a.5.5 0 0 0-.777-.416L16 11"/>' +
    '<rect x="2" y="6" width="14" height="12" rx="2"/>'
);

/** Image — lucide/image */
export const fpIconImage = L(
    '<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/>' +
    '<circle cx="9" cy="9" r="2"/>' +
    '<path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>'
);

/** X Circle — lucide/x-circle (for remove) */
export const fpIconRemove = L(
    '<circle cx="12" cy="12" r="10"/>' +
    '<path d="m15 9-6 6"/>' +
    '<path d="m9 9 6 6"/>'
);
