/**
 * HitTester — determine which frame was clicked given canvas coordinates.
 */
import type { ModeGeometry, GridGeometry, FilmstripGeometry, SideBySideGeometry } from '@ffmpega/types/loadlast';
import { VIEW_MODES } from '@ffmpega/types/loadlast';

/** Returns the timestamp of the clicked frame, or null if no hit. */
export function hitTestFrame(geometry: ModeGeometry | null, cx: number, cy: number): number | null {
    if (!geometry) return null;

    switch (geometry.mode) {
        case VIEW_MODES.GRID:
            return hitTestGrid(geometry, cx, cy);
        case VIEW_MODES.FILMSTRIP:
            return hitTestFilmstrip(geometry, cx, cy);
        case VIEW_MODES.SIDE_BY_SIDE:
            return hitTestSideBySide(geometry, cx, cy);
        default:
            return null;
    }
}

function hitTestGrid(g: GridGeometry, cx: number, cy: number): number | null {
    const col = Math.floor(cx / g.cellW);
    const row = Math.floor(cy / g.cellH);
    if (col < 0 || col >= g.cols || row < 0 || row >= g.rows) return null;
    const idx = row * g.cols + col;
    if (idx >= g.count) return null;
    return g.timestamps[idx] ?? null;
}

function hitTestFilmstrip(g: FilmstripGeometry, cx: number, _cy: number): number | null {
    const fw = g.frameWidth + g.gap;
    const idx = Math.floor(cx / fw);
    if (idx < 0 || idx >= g.count) return null;
    return g.timestamps[idx] ?? null;
}

function hitTestSideBySide(g: SideBySideGeometry, cx: number, _cy: number): number | null {
    const halfW = g.videoWidth;
    if (cx < halfW) return g.timestamps[0] ?? null;
    if (cx > halfW + g.gap) return g.timestamps[1] ?? null;
    return null;
}
