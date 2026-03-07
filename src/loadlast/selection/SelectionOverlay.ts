/**
 * SelectionOverlay — draw selection indicators on the canvas.
 */
import { VIEW_MODES } from '@ffmpega/types/loadlast';
import type { ModeGeometry, GridGeometry, FilmstripGeometry, SideBySideGeometry } from '@ffmpega/types/loadlast';

const OVERLAY_COLOR = 'rgba(0, 221, 255, 0.25)';
const BORDER_COLOR = '#00ddff';
const BORDER_WIDTH = 3;

/** Draw selection overlays on canvas for all selected frames in the current mode. */
export function drawSelectionOverlay(
    canvas: HTMLCanvasElement,
    geometry: ModeGeometry | null,
    selectedTimestamps: Set<number>,
): void {
    if (!geometry) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    switch (geometry.mode) {
        case VIEW_MODES.GRID:
            drawGridOverlay(ctx, geometry, selectedTimestamps);
            break;
        case VIEW_MODES.FILMSTRIP:
            drawFilmstripOverlay(ctx, geometry, selectedTimestamps);
            break;
        case VIEW_MODES.SIDE_BY_SIDE:
            drawSideBySideOverlay(ctx, geometry, selectedTimestamps);
            break;
    }
}

function drawGridOverlay(ctx: CanvasRenderingContext2D, g: GridGeometry, sel: Set<number>): void {
    for (let i = 0; i < g.count; i++) {
        const key = Math.round(g.timestamps[i] * 1000) / 1000;
        if (!sel.has(key)) continue;
        const col = i % g.cols;
        const row = Math.floor(i / g.cols);
        const x = col * g.cellW;
        const y = row * g.cellH;
        drawFrameOverlay(ctx, x, y, g.cellW, g.cellH);
    }
}

function drawFilmstripOverlay(ctx: CanvasRenderingContext2D, g: FilmstripGeometry, sel: Set<number>): void {
    for (let i = 0; i < g.count; i++) {
        const key = Math.round(g.timestamps[i] * 1000) / 1000;
        if (!sel.has(key)) continue;
        const x = i * (g.frameWidth + g.gap);
        drawFrameOverlay(ctx, x, 0, g.frameWidth, g.frameHeight);
    }
}

function drawSideBySideOverlay(ctx: CanvasRenderingContext2D, g: SideBySideGeometry, sel: Set<number>): void {
    for (let i = 0; i < g.timestamps.length; i++) {
        const key = Math.round(g.timestamps[i] * 1000) / 1000;
        if (!sel.has(key)) continue;
        const x = i === 0 ? 0 : g.videoWidth + g.gap;
        const canvasHeight = ctx.canvas.height;
        drawFrameOverlay(ctx, x, 0, g.videoWidth, canvasHeight);
    }
}

function drawFrameOverlay(
    ctx: CanvasRenderingContext2D,
    x: number,
    y: number,
    w: number,
    h: number,
): void {
    // Cyan border
    ctx.strokeStyle = BORDER_COLOR;
    ctx.lineWidth = BORDER_WIDTH;
    ctx.strokeRect(x + 1, y + 1, w - 2, h - 2);

    // Overlay fill
    ctx.fillStyle = OVERLAY_COLOR;
    ctx.fillRect(x, y, w, h);

    // Checkmark
    drawCheckmark(ctx, x + w - 24, y + 6, 14);
}

/** Draw a small checkmark icon. */
function drawCheckmark(ctx: CanvasRenderingContext2D, x: number, y: number, size: number): void {
    ctx.save();
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 2.5;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();
    ctx.moveTo(x, y + size * 0.5);
    ctx.lineTo(x + size * 0.35, y + size * 0.8);
    ctx.lineTo(x + size, y + size * 0.15);
    ctx.stroke();
    ctx.restore();
}
