/**
 * Contact Sheet widget for Load Last Image node.
 *
 * Displays a scrollable strip of 64×64 thumbnails loaded from ComfyUI's
 * /view endpoint. Click to pin an iteration; right-click for context menu.
 */

import { app } from 'comfyui/app';
import { api } from 'comfyui/api';

const THUMB_SIZE = 64;
const THUMB_GAP = 4;
const STRIP_BG = '#1a1a1a';
const STRIP_BORDER = '#333';
const PIN_HIGHLIGHT = '#4a9eff';
const HOVER_HIGHLIGHT = '#2a2a2a';

declare const LiteGraph: any;

interface ThumbData {
    filename: string;
    subfolder: string;
    type: string;
    iteration: number;
    loaded: boolean;
    image: HTMLImageElement | null;
}

function roundRect(
    ctx: CanvasRenderingContext2D,
    x: number, y: number, w: number, h: number, r: number,
): void {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
}

app.registerExtension({
    name: 'LoadLast.ContactSheet',
    beforeRegisterNodeDef(nodeType: any, nodeData: any, _app: any) {
        if (nodeData.name !== 'LoadLastImage') return;

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (this: any) {
            origOnNodeCreated?.apply(this, arguments);

            this._thumbs = [] as ThumbData[];
            this._hoveredIndex = -1;
            this._pinnedIteration = 0;
            this._stripScrollX = 0;

            const widget = this.addCustomWidget({
                name: 'contact_sheet',
                type: 'custom',
                value: '',
                draw: (ctx: CanvasRenderingContext2D, _node: any, width: number, y: number) => {
                    this._drawContactSheet(ctx, width, y);
                },
                computeSize: () => [0, THUMB_SIZE + 16],
            });
            this._contactSheetWidget = widget;
        };

        // Handle thumbnail data from backend execution results
        const origOnExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (this: any, output: any) {
            origOnExecuted?.apply(this, arguments);

            if (output?.thumbnails) {
                this._thumbs = output.thumbnails.map((t: any): ThumbData => ({
                    filename: t.filename,
                    subfolder: t.subfolder || '',
                    type: t.type || 'temp',
                    iteration: t.iteration || 0,
                    loaded: false,
                    image: null,
                }));

                for (const thumb of this._thumbs as ThumbData[]) {
                    const img = new Image();
                    const params = new URLSearchParams({
                        filename: thumb.filename,
                        subfolder: thumb.subfolder,
                        type: thumb.type,
                    });
                    img.src = api.apiURL(`/view?${params.toString()}`);
                    img.onload = () => {
                        thumb.loaded = true;
                        thumb.image = img;
                        this.setDirtyCanvas(true, false);
                    };
                }
                this.setDirtyCanvas(true, false);
            }
        };

        nodeType.prototype._drawContactSheet = function (
            this: any,
            ctx: CanvasRenderingContext2D,
            nodeWidth: number,
            y: number,
        ): void {
            if (!this._thumbs.length) return;

            const stripY = y + 4;
            const stripH = THUMB_SIZE + 8;
            const contentW = nodeWidth - 20;

            ctx.fillStyle = STRIP_BG;
            ctx.strokeStyle = STRIP_BORDER;
            ctx.lineWidth = 1;
            roundRect(ctx, 10, stripY, contentW, stripH, 4);
            ctx.fill();
            ctx.stroke();

            ctx.save();
            ctx.beginPath();
            ctx.rect(12, stripY + 2, contentW - 4, stripH - 4);
            ctx.clip();

            const startX = 14 - this._stripScrollX;
            for (let i = 0; i < this._thumbs.length; i++) {
                const thumb: ThumbData = this._thumbs[i];
                const x = startX + i * (THUMB_SIZE + THUMB_GAP);

                if (x + THUMB_SIZE < 10 || x > nodeWidth) continue;

                if (i === this._hoveredIndex) {
                    ctx.fillStyle = HOVER_HIGHLIGHT;
                    ctx.fillRect(x - 1, stripY + 3, THUMB_SIZE + 2, THUMB_SIZE + 2);
                }

                if (thumb.iteration === this._pinnedIteration && this._pinnedIteration > 0) {
                    ctx.strokeStyle = PIN_HIGHLIGHT;
                    ctx.lineWidth = 2;
                    ctx.strokeRect(x - 1, stripY + 3, THUMB_SIZE + 2, THUMB_SIZE + 2);
                    ctx.lineWidth = 1;
                }

                if (thumb.loaded && thumb.image) {
                    ctx.drawImage(thumb.image, x, stripY + 4, THUMB_SIZE, THUMB_SIZE);
                } else {
                    ctx.fillStyle = '#333';
                    ctx.fillRect(x, stripY + 4, THUMB_SIZE, THUMB_SIZE);
                    ctx.fillStyle = '#666';
                    ctx.textAlign = 'center';
                    ctx.font = '10px monospace';
                    ctx.fillText('...', x + THUMB_SIZE / 2, stripY + 4 + THUMB_SIZE / 2 + 3);
                }

                ctx.fillStyle = 'rgba(0,0,0,0.6)';
                ctx.fillRect(x, stripY + 4 + THUMB_SIZE - 14, THUMB_SIZE, 14);
                ctx.fillStyle = '#ccc';
                ctx.textAlign = 'center';
                ctx.font = '10px monospace';
                ctx.fillText(
                    `#${thumb.iteration}`,
                    x + THUMB_SIZE / 2,
                    stripY + 4 + THUMB_SIZE - 3,
                );
            }
            ctx.restore();
        };

        // Mouse interactions
        const origOnMouseDown = nodeType.prototype.onMouseDown;
        nodeType.prototype.onMouseDown = function (this: any, e: MouseEvent, pos: [number, number], canvas: any) {
            const thumbIdx = this._hitTestThumb(pos);
            if (thumbIdx >= 0) {
                const thumb: ThumbData = this._thumbs[thumbIdx];

                if (e.button === 2) {
                    e.preventDefault();
                    this._showThumbContextMenu(e, thumb);
                    return true;
                }

                this._pinnedIteration = thumb.iteration;
                const pinWidget = this.widgets?.find((w: any) => w.name === 'pin_index');
                if (pinWidget) pinWidget.value = thumb.iteration;
                this.setDirtyCanvas(true, false);
                return true;
            }
            return origOnMouseDown?.apply(this, arguments);
        };

        nodeType.prototype._hitTestThumb = function (this: any, pos: [number, number]): number {
            if (!this._thumbs.length || !this._contactSheetWidget) return -1;
            const widgetY = this._contactSheetWidget.last_y || 0;
            const stripY = widgetY + 4;
            const startX = 14 - this._stripScrollX;

            for (let i = 0; i < this._thumbs.length; i++) {
                const x = startX + i * (THUMB_SIZE + THUMB_GAP);
                if (
                    pos[0] >= x && pos[0] <= x + THUMB_SIZE &&
                    pos[1] >= stripY + 4 && pos[1] <= stripY + 4 + THUMB_SIZE
                ) {
                    return i;
                }
            }
            return -1;
        };

        nodeType.prototype._showThumbContextMenu = function (this: any, e: MouseEvent, thumb: ThumbData): void {
            new LiteGraph.ContextMenu(
                [
                    {
                        title: `Pin iteration #${thumb.iteration}`,
                        callback: () => {
                            this._pinnedIteration = thumb.iteration;
                            const pinWidget = this.widgets?.find((w: any) => w.name === 'pin_index');
                            if (pinWidget) pinWidget.value = thumb.iteration;
                            this.setDirtyCanvas(true, false);
                        },
                    },
                    {
                        title: 'Unpin',
                        callback: () => {
                            this._pinnedIteration = 0;
                            const pinWidget = this.widgets?.find((w: any) => w.name === 'pin_index');
                            if (pinWidget) pinWidget.value = 0;
                            this.setDirtyCanvas(true, false);
                        },
                    },
                    null,
                    {
                        title: 'Open in preview',
                        callback: () => {
                            const params = new URLSearchParams({
                                filename: thumb.filename,
                                subfolder: thumb.subfolder,
                                type: thumb.type,
                            });
                            window.open(api.apiURL(`/view?${params.toString()}`), '_blank');
                        },
                    },
                ],
                { event: e, scale: 1.0 },
            );
        };
    },
});
