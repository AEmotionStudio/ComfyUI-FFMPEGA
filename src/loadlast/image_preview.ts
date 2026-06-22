/**
 * Image Preview widget for LoadLastImage node.
 *
 * DOM-based widget modeled on video_preview.ts, providing:
 *   - Toolbar with view mode buttons (Single, Grid, Side-by-Side, Diff, Edit)
 *   - Inline <img> preview that loads immediately via API
 *   - Canvas-based Grid, Side-by-Side, Diff rendering
 *   - Comparison slider for A/B inspection
 *   - Browser strip with scrollable thumbnails
 *   - Info bar showing filename, dimensions, format
 *   - Pin support (click thumbnail to lock iteration)
 *
 * Phase 1: Core preview + browser strip + toolbar
 * Phase 2: View modes (Grid, SideBySide, Diff, Comparison Slider)
 * Phase 3: Mini image editor
 * Phase 4: Mask/Points integration
 */

import { app } from 'comfyui/app';
import { api } from 'comfyui/api';
import cssText from './loadlast.css?inline';
import { CropOverlay, type CropRect } from '@ffmpega/videoeditor/CropOverlay';
import { openPointSelector } from '@ffmpega/shared/point_selector';
import { flashNode } from '@ffmpega/shared/ui_helpers';
import {
    iconImage, iconGrid, iconColumns, iconInvert, iconWand,
    iconArrowLeftRight, iconSun, iconLayers,
    iconCrop, iconScaling, iconRotateCW, iconExpand, iconPalette,
    iconCheck, iconCircleCheck, iconLock, iconFlip, iconFlipVertical,
    iconReset, iconPin,
} from '@ffmpega/videoeditor/icons';

// ─── CSS injection (shared with video_preview) ────────────────────────
if (!document.getElementById('loadlast-styles')) {
    const style = document.createElement('style');
    style.id = 'loadlast-styles';
    style.textContent = cssText;
    document.head.appendChild(style);
}

// Inject image-preview-specific styles
if (!document.getElementById('loadlast-image-styles')) {
    const style = document.createElement('style');
    style.id = 'loadlast-image-styles';
    style.textContent = `
        .ll_img_preview {
            width: 100%;
            display: block;
            background: #111;
            min-height: 60px;
            object-fit: contain;
        }
        .ll_img_preview.loading {
            opacity: 0.5;
        }
        .ll_thumb img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            pointer-events: none;
        }
        .ll_pin_badge {
            position: absolute;
            top: 2px;
            right: 3px;
            background: rgba(255, 200, 0, 0.9);
            color: #000;
            font: bold 8px/1 monospace;
            padding: 1px 3px;
            border-radius: 3px;
            pointer-events: none;
            z-index: 2;
        }
        .ll_toolbar_spacer {
            flex: 1;
        }
        .ll_comparison_container {
            position: relative;
            width: 100%;
            overflow: hidden;
            cursor: col-resize;
        }
        .ll_comparison_divider {
            position: absolute;
            top: 0;
            bottom: 0;
            width: 3px;
            background: #00ddff;
            cursor: col-resize;
            z-index: 5;
            box-shadow: 0 0 6px rgba(0, 221, 255, 0.6);
        }
        .ll_comparison_divider::after {
            content: '◀ ▶';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: rgba(0, 221, 255, 0.9);
            color: #000;
            font: bold 10px/1 monospace;
            padding: 4px 6px;
            border-radius: 10px;
            white-space: nowrap;
            letter-spacing: 2px;
        }
        .ll_comparison_label {
            position: absolute;
            top: 6px;
            background: rgba(0, 0, 0, 0.7);
            color: #ccc;
            font: 11px/1 monospace;
            padding: 3px 8px;
            border-radius: 4px;
            z-index: 4;
            pointer-events: none;
        }
        .ll_comparison_label.left { left: 6px; }
        .ll_comparison_label.right { right: 6px; }
        .ll_diff_controls {
            display: flex;
            gap: 4px;
            padding: 4px 8px;
            background: #111;
            border-top: 1px solid #222;
            align-items: center;
        }
        .ll_diff_btn {
            border: 1px solid #555;
            background: #222;
            color: #aaa;
            font-size: 11px;
            padding: 3px 8px;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.15s;
        }
        .ll_diff_btn:hover { background: #333; color: #fff; }
        .ll_diff_btn.active {
            background: rgba(0, 200, 255, 0.15);
            border-color: rgba(0, 200, 255, 0.4);
            color: #0cf;
        }
        /* ─── Edit mode styles ──────────────────────── */
        .ll_edit_area {
            position: relative;
            background: #111;
        }
        .ll_edit_toolbar_row {
            display: flex;
            align-items: center;
            gap: 4px;
            padding: 4px 8px;
            background: #111;
            border-top: 1px solid #222;
            flex-wrap: wrap;
        }
        .ll_edit_tool_btn {
            border: 1px solid #555;
            background: #222;
            color: #aaa;
            font-size: 11px;
            padding: 4px 8px;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.15s;
        }
        .ll_edit_tool_btn:hover { background: #333; color: #fff; }
        .ll_edit_tool_btn.active {
            background: rgba(0, 200, 255, 0.15);
            border-color: rgba(0, 200, 255, 0.4);
            color: #0cf;
        }
        .ll_edit_panel {
            padding: 6px 8px;
            background: #0f0f0f;
            border-top: 1px solid #222;
            display: none;
        }
        .ll_edit_panel.visible { display: block; }
        .ll_edit_panel_row {
            display: flex;
            align-items: center;
            gap: 6px;
            margin: 3px 0;
        }
        .ll_edit_panel_label {
            color: #888;
            font: 11px/1 monospace;
            width: 65px;
            flex-shrink: 0;
        }
        .ll_edit_panel_input {
            background: #1a1a1a;
            border: 1px solid #444;
            color: #ddd;
            font: 12px/1.2 monospace;
            padding: 3px 6px;
            border-radius: 3px;
            width: 60px;
        }
        .ll_edit_panel_input:focus {
            border-color: #0cf;
            outline: none;
        }
        .ll_edit_slider_row {
            display: flex;
            align-items: center;
            gap: 6px;
            margin: 3px 0;
        }
        .ll_edit_slider {
            flex: 1;
            height: 4px;
            accent-color: #00ddff;
            cursor: pointer;
        }
        .ll_edit_slider_val {
            color: #aaa;
            font: 11px/1 monospace;
            width: 35px;
            text-align: right;
        }
        .ll_edit_apply_btn {
            border: 1px solid #4ade80;
            background: transparent;
            color: #4ade80;
            font-size: 12px;
            padding: 5px 14px;
            border-radius: 4px;
            cursor: pointer;
            margin-left: auto;
            transition: all 0.15s;
        }
        .ll_edit_apply_btn:hover {
            background: #4ade80;
            color: #000;
        }
    `;
    document.head.appendChild(style);
}

// ─── Types ─────────────────────────────────────────────────────────────

interface ImageEntry {
    filename: string;
    subfolder: string;
    type: string;
    mtime: number;
}

interface EditState {
    crop_rect: CropRect | null;
    resize: { w: number; h: number } | null;
    rotation: number; // 0, 90, 180, 270
    flip: '' | 'horizontal' | 'vertical';
    padding: { top: number; right: number; bottom: number; left: number; color: string } | null;
    brightness: number; // 1.0 = normal
    contrast: number;
    saturation: number;
}

function makeDefaultEditState(): EditState {
    return {
        crop_rect: null,
        resize: null,
        rotation: 0,
        flip: '',
        padding: null,
        brightness: 1.0,
        contrast: 1.0,
        saturation: 1.0,
    };
}

type ViewMode = 'single' | 'grid' | 'sidebyside' | 'diff' | 'edit';
type DiffMode = 'heatmap' | 'overlay' | 'slider';
type EditTool = 'crop' | 'resize' | 'rotate' | 'padding' | 'color';

interface ToolbarDef {
    id: ViewMode;
    icon: string;
    tip: string;
}

const TOOLBAR_BUTTONS: ToolbarDef[] = [
    { id: 'single', icon: iconImage, tip: 'Single image' },
    { id: 'grid', icon: iconGrid, tip: 'Grid view' },
    { id: 'sidebyside', icon: iconColumns, tip: 'Side by side' },
    { id: 'diff', icon: iconInvert, tip: 'Diff view' },
    { id: 'edit', icon: iconWand, tip: 'Edit image' },
];

// ─── Helpers ───────────────────────────────────────────────────────────

function buildViewURL(entry: ImageEntry): string {
    const params = new URLSearchParams({
        filename: entry.filename,
        subfolder: entry.subfolder,
        type: entry.type,
    });
    return api.apiURL(`/view?${params.toString()}`);
}

/** Load an image URL into an HTMLImageElement, returning a promise. */
function loadImage(url: string): Promise<HTMLImageElement> {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.onload = () => resolve(img);
        img.onerror = () => reject(new Error(`Failed to load: ${url}`));
        img.src = url;
    });
}

// ─── Resize toggle ─────────────────────────────────────────────────────

/** Resize sub-widgets gated behind the enable_resize toggle. */
const RESIZE_WIDGETS = [
    'resize_width', 'resize_height', 'upscale_method', 'keep_proportion',
    'pad_color', 'crop_position', 'divisible_by', 'resize_device',
];

/** VHS-style widget show/hide. */
function toggleWidget(widget: any, show: boolean): void {
    if (!widget) return;
    if (!widget._origType) {
        widget._origType = widget.type;
        widget._origComputeSize = widget.computeSize;
    }
    if (show) {
        widget.type = widget._origType;
        widget.computeSize = widget._origComputeSize;
        widget.hidden = false;
        if (widget.element) widget.element.hidden = false;
    } else {
        widget.type = 'hidden';
        widget.computeSize = () => [0, -4];
        widget.hidden = true;
        if (widget.element) widget.element.hidden = true;
    }
}

/** Show/hide the resize sub-widgets based on the enable_resize toggle. */
function applyResizeVisibility(node: any): void {
    const enableResize = node.widgets?.find((w: any) => w.name === 'enable_resize');
    const show = Boolean(enableResize?.value);
    for (const name of RESIZE_WIDGETS) {
        const w = node.widgets?.find((ww: any) => ww.name === name);
        if (w) toggleWidget(w, show);
    }
    node.setSize([node.size[0], node.computeSize([node.size[0], node.size[1]])[1]]);
    node?.graph?.setDirtyCanvas(true);
}

// ─── Extension ─────────────────────────────────────────────────────────

app.registerExtension({
    name: 'LoadLast.ImagePreview',
    beforeRegisterNodeDef(nodeType: any, nodeData: any, _app: any) {
        if (nodeData?.name !== 'LoadLastImage') return;

        const origCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (this: any) {
            origCreated?.apply(this, arguments);

            const node = this;
            let currentMode: ViewMode = 'single';
            let diffMode: DiffMode = 'slider';
            let currentEntry: ImageEntry | null = null;
            let allImages: ImageEntry[] = [];
            let selectedIndex = -1;
            let pollTimer: ReturnType<typeof setInterval> | null = null;

            // Cached loaded images for multi-image modes
            let loadedImages: HTMLImageElement[] = [];

            // Comparison slider position (0-1)
            let sliderPos = 0.5;

            // Edit mode state
            let editState = makeDefaultEditState();
            let editTool: EditTool | null = null;
            let editWrapper: HTMLDivElement | null = null;
            let editCropOverlay: CropOverlay | null = null;
            let editImg: HTMLImageElement | null = null;

            // Style
            node.color = '#3a5a3a';
            node.bgcolor = '#2a4a2a';

            // ─── enable_resize toggle → resize sub-widget visibility ──
            const enableResizeWidget = node.widgets?.find((w: any) => w.name === 'enable_resize');
            if (enableResizeWidget) {
                applyResizeVisibility(node);
                const origResizeCb = enableResizeWidget.callback;
                enableResizeWidget.callback = function (this: any, ...args: any[]) {
                    origResizeCb?.apply(this, args);
                    applyResizeVisibility(node);
                };
                const origResizeConfigure = node.onConfigure;
                node.onConfigure = function (this: any, ...args: any[]) {
                    origResizeConfigure?.apply(this, args);
                    applyResizeVisibility(node);
                };
            }

            // ─── Container ────────────────────────────────────────
            const container = document.createElement('div');
            container.className = 'll_container';

            // ─── Toolbar ──────────────────────────────────────────
            const toolbar = document.createElement('div');
            toolbar.className = 'll_toolbar';

            const buttons: HTMLButtonElement[] = [];
            for (const def of TOOLBAR_BUTTONS) {
                const btn = document.createElement('button');
                btn.innerHTML = def.icon;
                btn.title = def.tip;
                btn.dataset.mode = def.id;
                btn.className = 'll_toolbar_btn';
                if (def.id === 'single') btn.classList.add('active');
                btn.addEventListener('click', (e: Event) => {
                    e.stopPropagation();
                    switchMode(def.id);
                });
                buttons.push(btn);
                toolbar.appendChild(btn);
            }

            function highlightToolbar(): void {
                for (const btn of buttons) {
                    btn.classList.toggle('active', btn.dataset.mode === currentMode);
                }
            }

            // ─── Image preview (single mode) ──────────────────────
            const imgEl = document.createElement('img');
            imgEl.className = 'll_img_preview loading';
            imgEl.alt = 'Image preview';
            imgEl.draggable = false;

            imgEl.onload = () => {
                imgEl.classList.remove('loading');
                if (imgEl.naturalWidth && imgEl.naturalHeight) {
                    const newAR = imgEl.naturalWidth / imgEl.naturalHeight;
                    // Only resize when aspect ratio actually changes (avoids constant jitter)
                    if (!previewWidget.aspectRatio || Math.abs(previewWidget.aspectRatio - newAR) > 0.01) {
                        previewWidget.aspectRatio = newAR;
                        fitNode();
                    }
                }
            };
            imgEl.onerror = () => {
                imgEl.classList.remove('loading');
            };

            // ─── Canvas (grid/sbs/diff modes) ─────────────────────
            const canvasEl = document.createElement('canvas');
            canvasEl.className = 'll_canvas';
            canvasEl.style.display = 'none';
            canvasEl.style.width = '100%';
            canvasEl.style.cursor = 'default';

            // ─── Comparison slider container ──────────────────────
            const compContainer = document.createElement('div');
            compContainer.className = 'll_comparison_container';
            compContainer.style.display = 'none';

            const compCanvasA = document.createElement('canvas');
            compCanvasA.style.cssText = 'width:100%;display:block;';
            const compCanvasB = document.createElement('canvas');
            compCanvasB.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;';

            // Thin divider line (1px, no grab handle)
            const compDivider = document.createElement('div');
            compDivider.style.cssText = 'position:absolute;top:0;width:1px;height:100%;background:rgba(255,255,255,0.5);pointer-events:none;z-index:5;';

            const compLabelA = document.createElement('div');
            compLabelA.className = 'll_comparison_label left';
            compLabelA.textContent = 'A (Previous)';
            const compLabelB = document.createElement('div');
            compLabelB.className = 'll_comparison_label right';
            compLabelB.textContent = 'B (Latest)';

            compContainer.append(compCanvasA, compCanvasB, compDivider, compLabelA, compLabelB);

            // Hover-based wipe: both canvases share space at split point
            const updateCompSlider = (): void => {
                const w = compContainer.offsetWidth;
                const px = Math.round(sliderPos * w);
                compDivider.style.left = `${px}px`;
                // Canvas A shows left half, Canvas B shows right half
                compCanvasA.style.clipPath = `inset(0 ${w - px}px 0 0)`;
                compCanvasB.style.clipPath = `inset(0 0 0 ${px}px)`;
            };

            // Update on hover (no click needed)
            compContainer.addEventListener('mousemove', (e: MouseEvent) => {
                const rect = compContainer.getBoundingClientRect();
                sliderPos = Math.max(0.01, Math.min(0.99, (e.clientX - rect.left) / rect.width));
                updateCompSlider();
            });

            // ─── Diff controls ────────────────────────────────────
            const diffControls = document.createElement('div');
            diffControls.className = 'll_diff_controls';
            diffControls.style.display = 'none';

            const diffModes: { id: DiffMode; label: string }[] = [
                { id: 'slider', label: `${iconArrowLeftRight} Slider` },
                { id: 'heatmap', label: `${iconSun} Heatmap` },
                { id: 'overlay', label: `${iconLayers} Overlay` },
            ];

            const diffBtns: HTMLButtonElement[] = [];
            for (const dm of diffModes) {
                const btn = document.createElement('button');
                btn.className = 'll_diff_btn';
                btn.innerHTML = dm.label;
                btn.dataset.diffMode = dm.id;
                if (dm.id === diffMode) btn.classList.add('active');
                btn.addEventListener('click', (e: Event) => {
                    e.stopPropagation();
                    diffMode = dm.id;
                    for (const b of diffBtns) b.classList.toggle('active', b.dataset.diffMode === diffMode);
                    renderCurrentMode();
                });
                diffBtns.push(btn);
                diffControls.appendChild(btn);
            }

            // SBS sub-mode label
            const sbsControls = document.createElement('div');
            sbsControls.className = 'll_diff_controls';
            sbsControls.style.display = 'none';
            const sbsLabel = document.createElement('span');
            sbsLabel.style.cssText = 'color:#888;font-size:11px;';
            sbsLabel.textContent = 'Hover to compare  │  A = Previous  │  B = Latest';
            sbsControls.appendChild(sbsLabel);

            // ─── Info bar ─────────────────────────────────────────
            const infoEl = document.createElement('div');
            infoEl.className = 'll_info';
            infoEl.textContent = 'No image loaded';

            // ─── Browser strip ────────────────────────────────────
            const browserStrip = document.createElement('div');
            browserStrip.className = 'll_browser_strip';

            // Scroll track
            const scrollTrack = document.createElement('div');
            scrollTrack.className = 'll_scroll_track';
            const scrollThumb = document.createElement('div');
            scrollThumb.className = 'll_scroll_thumb';
            scrollTrack.appendChild(scrollThumb);

            function updateScrollIndicator(): void {
                const sw = browserStrip.scrollWidth;
                const cw = browserStrip.clientWidth;
                if (sw <= cw) {
                    scrollTrack.style.display = allImages.length > 1 ? 'block' : 'none';
                    scrollThumb.style.width = '100%';
                    scrollThumb.style.left = '0px';
                    scrollThumb.style.opacity = '0.3';
                    return;
                }
                scrollTrack.style.display = 'block';
                scrollThumb.style.opacity = '1';
                const trackW = scrollTrack.clientWidth;
                const ratio = cw / sw;
                const thumbW = Math.max(20, trackW * ratio);
                scrollThumb.style.width = `${thumbW}px`;
                const scrollRange = sw - cw;
                const thumbRange = trackW - thumbW;
                const pos = scrollRange > 0 ? (browserStrip.scrollLeft / scrollRange) * thumbRange : 0;
                scrollThumb.style.left = `${pos}px`;
            }

            browserStrip.addEventListener('scroll', updateScrollIndicator);

            // Middle-mouse scroll
            browserStrip.addEventListener('wheel', (e: WheelEvent) => {
                if (e.deltaY !== 0) {
                    e.preventDefault();
                    browserStrip.scrollLeft += e.deltaY;
                }
            }, { passive: false });

            // Thumb drag
            scrollThumb.addEventListener('mousedown', (e: MouseEvent) => {
                e.preventDefault();
                e.stopPropagation();
                scrollThumb.classList.add('dragging');
                const startX = e.clientX;
                const startScroll = browserStrip.scrollLeft;
                const trackW = scrollTrack.clientWidth;
                const thumbW = scrollThumb.offsetWidth;
                const scrollRange = browserStrip.scrollWidth - browserStrip.clientWidth;

                const onMove = (ev: MouseEvent) => {
                    const dx = ev.clientX - startX;
                    const scrollDelta = (trackW - thumbW) > 0
                        ? (dx / (trackW - thumbW)) * scrollRange
                        : 0;
                    browserStrip.scrollLeft = startScroll + scrollDelta;
                };
                const onUp = () => {
                    scrollThumb.classList.remove('dragging');
                    document.removeEventListener('mousemove', onMove);
                    document.removeEventListener('mouseup', onUp);
                };
                document.addEventListener('mousemove', onMove);
                document.addEventListener('mouseup', onUp);
            });

            // Scroll track click
            scrollTrack.addEventListener('mousedown', (e: MouseEvent) => {
                if (e.target === scrollThumb) return;
                e.preventDefault();
                const rect = scrollTrack.getBoundingClientRect();
                const clickX = e.clientX - rect.left;
                const trackW = rect.width;
                const scrollRange = browserStrip.scrollWidth - browserStrip.clientWidth;
                browserStrip.scrollLeft = (clickX / trackW) * scrollRange;
            });

            // ─── Widget ───────────────────────────────────────────
            const previewWidget = node.addDOMWidget('preview', 'custom', container, {
                serialize: false,
                hideOnZoom: false,
                getValue() { return ''; },
                setValue() { },
            });
            previewWidget.aspectRatio = null;
            previewWidget.computeSize = function (this: any, width: number): [number, number] {
                if (container.style.display === 'none') return [width, 0];
                // toolbar(32) + infoBar(22) + browserStrip+scrollbar(~100)
                let chrome = 32 + 22 + (allImages.length > 1 ? 100 : 0);
                // Extra chrome for controls or edit panels
                if (currentMode === 'diff' || currentMode === 'sidebyside') chrome += 30;
                if (currentMode === 'edit') chrome += 250; // edit toolbar + active panel + controls
                if (this.aspectRatio) {
                    const h = (node.size[0] - 20) / this.aspectRatio;
                    return [width, Math.max(h, 80) + chrome];
                }
                return [width, 80 + chrome];
            };

            // ─── Assemble DOM ─────────────────────────────────────
            container.appendChild(toolbar);
            container.appendChild(imgEl);
            container.appendChild(canvasEl);
            container.appendChild(compContainer);
            container.appendChild(sbsControls);
            container.appendChild(diffControls);
            container.appendChild(infoEl);

            const stripWrapper = document.createElement('div');
            stripWrapper.className = 'll_strip_wrapper';
            stripWrapper.appendChild(browserStrip);
            stripWrapper.appendChild(scrollTrack);
            container.appendChild(stripWrapper);

            // ─── Utility ──────────────────────────────────────────
            function fitNode(): void {
                const sz = previewWidget.computeSize?.(node.size[0]);
                if (sz) {
                    node.size[1] = sz[1] + 40;
                    node.onResize?.(node.size);
                    node.setDirtyCanvas(true, true);
                    node.graph?.setDirtyCanvas(true, true);
                }
            }

            // ─── View mode switching ──────────────────────────────
            function switchMode(mode: ViewMode): void {
                // Clean up edit mode when leaving
                if (mode !== 'edit') cleanupEditMode();

                currentMode = mode;
                highlightToolbar();

                // Hide all preview elements — reset canvas height to prevent layout push
                imgEl.style.display = 'none';
                canvasEl.style.display = 'none';
                canvasEl.height = 0;
                compContainer.style.display = 'none';
                diffControls.style.display = 'none';
                sbsControls.style.display = 'none';

                if (mode === 'single') {
                    imgEl.style.display = 'block';
                    updatePreview();
                } else if (mode === 'grid') {
                    canvasEl.style.display = 'block';
                    renderCurrentMode();
                } else if (mode === 'sidebyside') {
                    canvasEl.style.display = 'block';
                    sbsControls.style.display = 'flex';
                    renderCurrentMode();
                } else if (mode === 'diff') {
                    diffControls.style.display = 'flex';
                    if (diffMode === 'slider') {
                        compContainer.style.display = 'block';
                    } else {
                        canvasEl.style.display = 'block';
                    }
                    renderCurrentMode();
                } else if (mode === 'edit') {
                    buildEditMode();
                }

                fitNode();
            }

            // ─── Edit Mode ────────────────────────────────────────
            function buildEditMode(): void {
                cleanupEditMode();
                editState = makeDefaultEditState();
                editTool = null;

                editWrapper = document.createElement('div');
                editWrapper.className = 'll_edit_wrapper';

                // Image area + crop overlay
                const editArea = document.createElement('div');
                editArea.className = 'll_edit_area';

                editImg = document.createElement('img');
                editImg.className = 'll_img_preview';
                editImg.draggable = false;
                if (currentEntry) editImg.src = buildViewURL(currentEntry);
                editArea.appendChild(editImg);

                // CropOverlay
                editCropOverlay = new CropOverlay({
                    onCropChanged: (rect) => {
                        editState.crop_rect = rect;
                        updateEditPreview();
                    },
                });
                editArea.appendChild(editCropOverlay.canvasElement);
                editCropOverlay.canvasElement.style.display = 'none';

                editWrapper.appendChild(editArea);

                // Tool buttons row
                const toolRow = document.createElement('div');
                toolRow.className = 'll_edit_toolbar_row';

                const tools: { id: EditTool; icon: string; label: string }[] = [
                    { id: 'crop', icon: iconCrop, label: 'Crop' },
                    { id: 'resize', icon: iconScaling, label: 'Resize' },
                    { id: 'rotate', icon: iconRotateCW, label: 'Transform' },
                    { id: 'padding', icon: iconExpand, label: 'Padding' },
                    { id: 'color', icon: iconPalette, label: 'Color' },
                ];

                const toolBtns: HTMLButtonElement[] = [];
                for (const tool of tools) {
                    const btn = document.createElement('button');
                    btn.className = 'll_edit_tool_btn';
                    btn.innerHTML = `${tool.icon} ${tool.label}`;
                    btn.dataset.tool = tool.id;
                    btn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        const newTool = editTool === tool.id ? null : tool.id;
                        editTool = newTool;
                        for (const b of toolBtns) b.classList.toggle('active', b.dataset.tool === editTool);
                        showEditPanel(editWrapper!, tool.id, editTool !== null);
                    });
                    toolBtns.push(btn);
                    toolRow.appendChild(btn);
                }

                // Spacer to push action buttons right
                const editSpacer = document.createElement('div');
                editSpacer.className = 'll_toolbar_spacer';
                toolRow.appendChild(editSpacer);

                // Reset All button
                const resetAllBtn = document.createElement('button');
                resetAllBtn.className = 'll_edit_tool_btn';
                resetAllBtn.innerHTML = `${iconReset} Reset All`;
                resetAllBtn.style.cssText = 'border-color:#f87171;color:#f87171;';
                resetAllBtn.title = 'Reset all edit settings to defaults';
                resetAllBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    editState = makeDefaultEditState();
                    // Rebuild the edit UI to reflect default state
                    buildEditMode();
                    // Also clear any applied edits on the backend
                    postEditState();
                    fitNode();
                });
                toolRow.appendChild(resetAllBtn);

                // Apply button
                const applyBtn = document.createElement('button');
                applyBtn.className = 'll_edit_apply_btn';
                applyBtn.innerHTML = `${iconCircleCheck} Apply Edits`;
                applyBtn.addEventListener('click', () => {
                    postEditState();
                    applyBtn.innerHTML = `${iconCheck} Applied!`;
                    applyBtn.style.background = '#4ade80';
                    applyBtn.style.color = '#000';
                    setTimeout(() => {
                        applyBtn.innerHTML = `${iconCircleCheck} Apply Edits`;
                        applyBtn.style.background = '';
                        applyBtn.style.color = '#4ade80';
                    }, 1200);
                });
                toolRow.appendChild(applyBtn);

                editWrapper.appendChild(toolRow);

                // Tool panels
                buildCropPanel(editWrapper, editImg);
                buildResizePanel(editWrapper, editImg);
                buildTransformPanel(editWrapper);
                buildPaddingPanel(editWrapper);
                buildColorPanel(editWrapper);

                // Insert before strip
                container.insertBefore(editWrapper, stripWrapper);

                infoEl.textContent = currentEntry
                    ? `Edit: ${currentEntry.filename}`
                    : 'Edit mode';
            }

            function showEditPanel(wrapper: HTMLDivElement, toolId: string, show: boolean): void {
                const panels = wrapper.querySelectorAll('.ll_edit_panel');
                panels.forEach(p => {
                    const el = p as HTMLElement;
                    if (el.dataset.panel === toolId) {
                        el.classList.toggle('visible', show);
                    } else {
                        el.classList.remove('visible');
                    }
                });

                // Toggle crop overlay visibility
                if (editCropOverlay) {
                    editCropOverlay.canvasElement.style.display = (toolId === 'crop' && show) ? 'block' : 'none';
                }
            }

            function buildCropPanel(wrapper: HTMLDivElement, editImg: HTMLImageElement): void {
                const panel = document.createElement('div');
                panel.className = 'll_edit_panel';
                panel.dataset.panel = 'crop';

                const info = document.createElement('div');
                info.style.cssText = 'color:#888;font:11px/1.4 monospace;padding:4px 0;';
                info.textContent = 'Use the crop overlay on the image above. Select presets or drag handles.';
                panel.appendChild(info);

                // CropOverlay controls (from the component)
                if (editCropOverlay) {
                    panel.appendChild(editCropOverlay.element);

                    // Set dimensions when image loads
                    const setDims = () => {
                        if (editImg.naturalWidth && editImg.naturalHeight) {
                            editCropOverlay!.setVideoDimensions(editImg.naturalWidth, editImg.naturalHeight);
                        }
                    };
                    if (editImg.complete && editImg.naturalWidth) setDims();
                    else editImg.addEventListener('load', setDims, { once: true });
                }

                wrapper.appendChild(panel);
            }

            function buildResizePanel(wrapper: HTMLDivElement, editImg: HTMLImageElement): void {
                const panel = document.createElement('div');
                panel.className = 'll_edit_panel';
                panel.dataset.panel = 'resize';

                const row = document.createElement('div');
                row.className = 'll_edit_panel_row';

                const wLabel = document.createElement('span');
                wLabel.className = 'll_edit_panel_label';
                wLabel.textContent = 'Width';
                const wInput = document.createElement('input');
                wInput.className = 'll_edit_panel_input';
                wInput.type = 'number';
                wInput.min = '1';
                wInput.placeholder = 'auto';

                const hLabel = document.createElement('span');
                hLabel.className = 'll_edit_panel_label';
                hLabel.textContent = 'Height';
                const hInput = document.createElement('input');
                hInput.className = 'll_edit_panel_input';
                hInput.type = 'number';
                hInput.min = '1';
                hInput.placeholder = 'auto';

                // Lock aspect checkbox
                const lockLabel = document.createElement('label');
                lockLabel.style.cssText = 'color:#888;font:11px monospace;display:flex;align-items:center;gap:3px;';
                const lockCheck = document.createElement('input');
                lockCheck.type = 'checkbox';
                lockCheck.checked = true;
                lockLabel.innerHTML = `${iconLock} Lock`;
                lockLabel.prepend(lockCheck);

                const updateResize = () => {
                    const w = parseInt(wInput.value) || 0;
                    const h = parseInt(hInput.value) || 0;
                    editState.resize = (w > 0 && h > 0) ? { w, h } : null;
                };

                wInput.addEventListener('input', () => {
                    if (lockCheck.checked && editImg && editImg.naturalWidth && editImg.naturalHeight) {
                        const w = parseInt(wInput.value) || 0;
                        if (w > 0) hInput.value = String(Math.round(w * editImg.naturalHeight / editImg.naturalWidth));
                    }
                    updateResize();
                    updateEditPreview();
                });
                hInput.addEventListener('input', () => {
                    if (lockCheck.checked && editImg && editImg.naturalWidth && editImg.naturalHeight) {
                        const h = parseInt(hInput.value) || 0;
                        if (h > 0) wInput.value = String(Math.round(h * editImg.naturalWidth / editImg.naturalHeight));
                    }
                    updateResize();
                    updateEditPreview();
                });

                // Presets
                const presetRow = document.createElement('div');
                presetRow.className = 'll_edit_panel_row';
                const presetLabel = document.createElement('span');
                presetLabel.className = 'll_edit_panel_label';
                presetLabel.textContent = 'Presets';
                presetRow.appendChild(presetLabel);

                for (const [label, scale] of [['50%', 0.5], ['75%', 0.75], ['150%', 1.5], ['200%', 2.0]] as [string, number][]) {
                    const btn = document.createElement('button');
                    btn.className = 'll_edit_tool_btn';
                    btn.textContent = label;
                    btn.style.fontSize = '10px';
                    btn.addEventListener('click', () => {
                        if (editImg && editImg.naturalWidth && editImg.naturalHeight) {
                            wInput.value = String(Math.round(editImg.naturalWidth * scale));
                            hInput.value = String(Math.round(editImg.naturalHeight * scale));
                            updateResize();
                            updateEditPreview();
                        }
                    });
                    presetRow.appendChild(btn);
                }

                row.append(wLabel, wInput, hLabel, hInput, lockLabel);
                panel.append(row, presetRow);
                wrapper.appendChild(panel);
            }

            function buildTransformPanel(wrapper: HTMLDivElement): void {
                const panel = document.createElement('div');
                panel.className = 'll_edit_panel';
                panel.dataset.panel = 'rotate';

                const row = document.createElement('div');
                row.className = 'll_edit_panel_row';

                const rotLabel = document.createElement('span');
                rotLabel.className = 'll_edit_panel_label';
                rotLabel.textContent = 'Rotate';
                row.appendChild(rotLabel);

                const rotInfo = document.createElement('span');
                rotInfo.style.cssText = 'color:#aaa;font:11px monospace;margin-left:auto;';
                rotInfo.textContent = '0°';

                for (const angle of [90, 180, 270]) {
                    const btn = document.createElement('button');
                    btn.className = 'll_edit_tool_btn';
                    btn.textContent = `${angle}°`;
                    btn.addEventListener('click', () => {
                        editState.rotation = editState.rotation === angle ? 0 : angle;
                        rotInfo.textContent = `${editState.rotation}°`;
                        // Highlight
                        row.querySelectorAll('.ll_edit_tool_btn').forEach(b => {
                            const a = parseInt(b.textContent || '0');
                            (b as HTMLElement).classList.toggle('active', a === editState.rotation);
                        });
                        updateEditPreview();
                    });
                    if (editState.rotation === angle) btn.classList.add('active');
                    row.appendChild(btn);
                }
                row.appendChild(rotInfo);

                // Flip row
                const flipRow = document.createElement('div');
                flipRow.className = 'll_edit_panel_row';
                const flipLabel = document.createElement('span');
                flipLabel.className = 'll_edit_panel_label';
                flipLabel.textContent = 'Flip';
                flipRow.appendChild(flipLabel);

                for (const dir of ['horizontal', 'vertical'] as const) {
                    const btn = document.createElement('button');
                    btn.className = 'll_edit_tool_btn';
                    btn.innerHTML = dir === 'horizontal' ? `${iconFlip} Horizontal` : `${iconFlipVertical} Vertical`;
                    btn.addEventListener('click', () => {
                        editState.flip = editState.flip === dir ? '' : dir;
                        flipRow.querySelectorAll('.ll_edit_tool_btn').forEach(b => {
                            (b as HTMLElement).classList.toggle('active', b.textContent?.toLowerCase().includes(editState.flip) || false);
                        });
                        updateEditPreview();
                    });
                    flipRow.appendChild(btn);
                }

                panel.append(row, flipRow);
                wrapper.appendChild(panel);
            }

            function buildPaddingPanel(wrapper: HTMLDivElement): void {
                const panel = document.createElement('div');
                panel.className = 'll_edit_panel';
                panel.dataset.panel = 'padding';

                const inputs: Record<string, HTMLInputElement> = {};
                const sliders: Record<string, HTMLInputElement> = {};

                for (const side of ['top', 'right', 'bottom', 'left']) {
                    const row = document.createElement('div');
                    row.className = 'll_edit_slider_row';
                    const lbl = document.createElement('span');
                    lbl.className = 'll_edit_panel_label';
                    lbl.textContent = side.charAt(0).toUpperCase() + side.slice(1);

                    const slider = document.createElement('input');
                    slider.className = 'll_edit_slider';
                    slider.type = 'range';
                    slider.min = '0';
                    slider.max = '500';
                    slider.step = '1';
                    slider.value = '0';

                    const inp = document.createElement('input');
                    inp.className = 'll_edit_panel_input';
                    inp.type = 'number';
                    inp.min = '0';
                    inp.max = '500';
                    inp.value = '0';
                    inp.style.width = '55px';

                    // Keep slider + input in sync
                    slider.addEventListener('input', () => {
                        inp.value = slider.value;
                        updatePadding();
                    });
                    inp.addEventListener('input', () => {
                        slider.value = inp.value;
                        updatePadding();
                    });

                    inputs[side] = inp;
                    sliders[side] = slider;
                    row.append(lbl, slider, inp);

                    if (side === 'top') {
                        // Uniform checkbox
                        const uniLabel = document.createElement('label');
                        uniLabel.style.cssText = 'color:#888;font:11px monospace;display:flex;align-items:center;gap:3px;margin-left:4px;';
                        const uniCheck = document.createElement('input');
                        uniCheck.type = 'checkbox';
                        uniCheck.id = 'll_pad_uniform';
                        uniLabel.append(uniCheck, 'Uniform');
                        row.appendChild(uniLabel);

                        uniCheck.addEventListener('change', () => {
                            if (uniCheck.checked) {
                                const v = inputs.top.value;
                                for (const s of ['right', 'bottom', 'left']) {
                                    inputs[s].value = v;
                                    sliders[s].value = v;
                                }
                                updatePadding();
                            }
                        });
                    }
                    panel.appendChild(row);
                }

                // Color picker
                const colorRow = document.createElement('div');
                colorRow.className = 'll_edit_panel_row';
                const colorLbl = document.createElement('span');
                colorLbl.className = 'll_edit_panel_label';
                colorLbl.textContent = 'Color';
                const colorInput = document.createElement('input');
                colorInput.type = 'color';
                colorInput.value = '#000000';
                colorInput.style.cssText = 'width:40px;height:24px;border:none;cursor:pointer;';
                colorInput.addEventListener('input', updatePadding);
                colorRow.append(colorLbl, colorInput);
                panel.appendChild(colorRow);

                function updatePadding(): void {
                    const uni = (document.getElementById('ll_pad_uniform') as HTMLInputElement)?.checked;
                    if (uni) {
                        const v = inputs.top.value;
                        for (const s of ['right', 'bottom', 'left']) {
                            inputs[s].value = v;
                            sliders[s].value = v;
                        }
                    }
                    const t = parseInt(inputs.top.value) || 0;
                    const r = parseInt(inputs.right.value) || 0;
                    const b = parseInt(inputs.bottom.value) || 0;
                    const l = parseInt(inputs.left.value) || 0;
                    if (t > 0 || r > 0 || b > 0 || l > 0) {
                        editState.padding = { top: t, right: r, bottom: b, left: l, color: colorInput.value };
                    } else {
                        editState.padding = null;
                    }
                    updateEditPreview();
                }

                wrapper.appendChild(panel);
            }

            function buildColorPanel(wrapper: HTMLDivElement): void {
                const panel = document.createElement('div');
                panel.className = 'll_edit_panel';
                panel.dataset.panel = 'color';

                const sliders: { key: 'brightness' | 'contrast' | 'saturation'; label: string; min: number; max: number; step: number }[] = [
                    { key: 'brightness', label: 'Brightness', min: 0.2, max: 3.0, step: 0.05 },
                    { key: 'contrast', label: 'Contrast', min: 0.2, max: 3.0, step: 0.05 },
                    { key: 'saturation', label: 'Saturation', min: 0.0, max: 3.0, step: 0.05 },
                ];

                for (const s of sliders) {
                    const row = document.createElement('div');
                    row.className = 'll_edit_slider_row';

                    const label = document.createElement('span');
                    label.className = 'll_edit_panel_label';
                    label.textContent = s.label;

                    const slider = document.createElement('input');
                    slider.className = 'll_edit_slider';
                    slider.type = 'range';
                    slider.min = String(s.min);
                    slider.max = String(s.max);
                    slider.step = String(s.step);
                    slider.value = '1.0';

                    const val = document.createElement('span');
                    val.className = 'll_edit_slider_val';
                    val.textContent = '1.00';

                    slider.addEventListener('input', () => {
                        const v = parseFloat(slider.value);
                        editState[s.key] = v;
                        val.textContent = v.toFixed(2);
                        updateEditPreview();
                    });

                    // Double-click to reset
                    slider.addEventListener('dblclick', () => {
                        slider.value = '1.0';
                        editState[s.key] = 1.0;
                        val.textContent = '1.00';
                        updateEditPreview();
                    });

                    row.append(label, slider, val);
                    panel.appendChild(row);
                }

                // Reset colors button
                const resetRow = document.createElement('div');
                resetRow.className = 'll_edit_panel_row';
                const resetBtn = document.createElement('button');
                resetBtn.className = 'll_edit_tool_btn';
                resetBtn.innerHTML = `${iconReset} Reset Colors`;
                resetBtn.addEventListener('click', () => {
                    editState.brightness = 1.0;
                    editState.contrast = 1.0;
                    editState.saturation = 1.0;
                    panel.querySelectorAll<HTMLInputElement>('.ll_edit_slider').forEach(s => {
                        s.value = '1.0';
                    });
                    panel.querySelectorAll('.ll_edit_slider_val').forEach(v => {
                        v.textContent = '1.00';
                    });
                    updateEditPreview();
                });
                resetRow.appendChild(resetBtn);
                panel.appendChild(resetRow);

                wrapper.appendChild(panel);
            }

            function postEditState(): void {
                const edits: Record<string, any> = {};
                if (editState.crop_rect) edits.crop_rect = editState.crop_rect;
                if (editState.resize) edits.resize = editState.resize;
                if (editState.rotation) edits.rotation = editState.rotation;
                if (editState.flip) edits.flip = editState.flip;
                if (editState.padding) edits.padding = editState.padding;
                if (editState.brightness !== 1.0) edits.brightness = editState.brightness;
                if (editState.contrast !== 1.0) edits.contrast = editState.contrast;
                if (editState.saturation !== 1.0) edits.saturation = editState.saturation;

                fetch(api.apiURL('/loadlast/apply_image_edits'), {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        node_id: String(node.id),
                        edits: Object.keys(edits).length > 0 ? edits : null,
                    }),
                }).catch(() => {});
            }

            /** Apply CSS-based live preview of edit state to the edit image */
            function updateEditPreview(): void {
                if (!editImg) return;

                // Build CSS transform for rotation + flip
                const transforms: string[] = [];
                if (editState.rotation) transforms.push(`rotate(${editState.rotation}deg)`);
                if (editState.flip === 'horizontal') transforms.push('scaleX(-1)');
                if (editState.flip === 'vertical') transforms.push('scaleY(-1)');
                editImg.style.transform = transforms.length ? transforms.join(' ') : '';

                // CSS filter for brightness/contrast/saturation
                const filters: string[] = [];
                if (editState.brightness !== 1.0) filters.push(`brightness(${editState.brightness})`);
                if (editState.contrast !== 1.0) filters.push(`contrast(${editState.contrast})`);
                if (editState.saturation !== 1.0) filters.push(`saturate(${editState.saturation})`);
                editImg.style.filter = filters.length ? filters.join(' ') : '';

                // Visual padding indicator on the image area
                const area = editImg.parentElement;
                if (area && editState.padding) {
                    const p = editState.padding;
                    // Scale padding for display (px mapped proportionally)
                    const scale = Math.min(1, (area.clientWidth || 300) / (editImg.naturalWidth || 1));
                    area.style.padding = `${Math.round(p.top * scale)}px ${Math.round(p.right * scale)}px ${Math.round(p.bottom * scale)}px ${Math.round(p.left * scale)}px`;
                    area.style.backgroundColor = p.color || '#000';
                } else if (area) {
                    area.style.padding = '';
                    area.style.backgroundColor = '';
                }
            }

            function cleanupEditMode(): void {
                if (editCropOverlay) {
                    editCropOverlay.destroy();
                    editCropOverlay = null;
                }
                if (editWrapper) {
                    editWrapper.remove();
                    editWrapper = null;
                }
            }

            // ─── Multi-image loading ──────────────────────────────
            async function loadBrowserImages(count: number): Promise<HTMLImageElement[]> {
                const images: HTMLImageElement[] = [];
                const entries = allImages.slice(0, count);
                for (const entry of entries) {
                    try {
                        const img = await loadImage(buildViewURL(entry));
                        images.push(img);
                    } catch {
                        // Skip failed loads
                    }
                }
                loadedImages = images;
                return images;
            }

            /**
             * Get the comparison pair: [imageA (older), imageB (newer)]
             * Uses selected index in the strip. If nothing selected, uses latest + previous.
             */
            function getComparisonIndices(): [number, number] {
                // Determine "selected" position in the allImages array
                let sel = selectedIndex >= 0 ? selectedIndex : 0;
                if (sel >= allImages.length) sel = 0;
                // Previous image is the one after it in the array (allImages is newest-first)
                const prev = Math.min(sel + 1, allImages.length - 1);
                return [prev, sel]; // [A=older, B=newer]
            }

            // ─── Canvas rendering ─────────────────────────────────
            async function renderCurrentMode(): Promise<void> {
                if (currentMode === 'grid') {
                    await renderGrid();
                } else if (currentMode === 'sidebyside') {
                    await renderSideBySide();
                } else if (currentMode === 'diff') {
                    if (diffMode === 'slider') {
                        await renderDiffSlider();
                    } else {
                        await renderDiff();
                    }
                }
            }

            // ─── Grid Mode ────────────────────────────────────────
            async function renderGrid(): Promise<void> {
                // Load ALL images from the browser strip
                const images = await loadBrowserImages(allImages.length);
                if (images.length === 0) return;

                const cols = Math.ceil(Math.sqrt(images.length));
                const rows = Math.ceil(images.length / cols);
                const gap = 4;

                // Use first image as the cell size reference
                const cellW = images[0].naturalWidth;
                const cellH = images[0].naturalHeight;
                const totalW = cols * cellW + (cols - 1) * gap;
                const totalH = rows * cellH + (rows - 1) * gap;

                canvasEl.width = totalW;
                canvasEl.height = totalH;
                const ctx = canvasEl.getContext('2d');
                if (!ctx) return;

                // Dark background
                ctx.fillStyle = '#111';
                ctx.fillRect(0, 0, totalW, totalH);

                for (let i = 0; i < images.length; i++) {
                    const col = i % cols;
                    const row = Math.floor(i / cols);
                    const x = col * (cellW + gap);
                    const y = row * (cellH + gap);

                    // Draw image, fitting to cell
                    const img = images[i];
                    const scale = Math.min(cellW / img.naturalWidth, cellH / img.naturalHeight);
                    const dw = img.naturalWidth * scale;
                    const dh = img.naturalHeight * scale;
                    const dx = x + (cellW - dw) / 2;
                    const dy = y + (cellH - dh) / 2;
                    ctx.drawImage(img, dx, dy, dw, dh);

                    // Index label
                    ctx.fillStyle = 'rgba(0,0,0,0.6)';
                    ctx.fillRect(x, y + cellH - 16, 30, 16);
                    ctx.fillStyle = '#ccc';
                    ctx.font = '11px monospace';
                    ctx.textAlign = 'left';
                    ctx.fillText(`#${i + 1}`, x + 3, y + cellH - 4);
                }

                previewWidget.aspectRatio = totalW / totalH;
                infoEl.textContent = `Grid: ${images.length} images │ ${cols}×${rows} │ ${totalW}×${totalH}`;
                fitNode();
            }

            // ─── Side-by-Side Mode (Two images, no slider) ────────
            async function renderSideBySide(): Promise<void> {
                const [idxA, idxB] = getComparisonIndices();
                if (allImages.length < 2) {
                    infoEl.textContent = 'Side-by-Side: need at least 2 images';
                    return;
                }

                let imgA: HTMLImageElement, imgB: HTMLImageElement;
                try {
                    [imgA, imgB] = await Promise.all([
                        loadImage(buildViewURL(allImages[idxA])),
                        loadImage(buildViewURL(allImages[idxB])),
                    ]);
                } catch { return; }

                // Each image gets half the canvas width
                const gap = 4;
                const cellW = Math.max(imgA.naturalWidth, imgB.naturalWidth);
                const cellH = Math.max(imgA.naturalHeight, imgB.naturalHeight);
                const totalW = cellW * 2 + gap;
                const totalH = cellH;

                canvasEl.width = totalW;
                canvasEl.height = totalH;
                const ctx = canvasEl.getContext('2d');
                if (!ctx) return;

                ctx.fillStyle = '#111';
                ctx.fillRect(0, 0, totalW, totalH);

                // Left = selected (newer)
                const sB = Math.min(cellW / imgB.naturalWidth, cellH / imgB.naturalHeight);
                const dwB = imgB.naturalWidth * sB;
                const dhB = imgB.naturalHeight * sB;
                ctx.drawImage(imgB, (cellW - dwB) / 2, (cellH - dhB) / 2, dwB, dhB);

                // Right = previous (older)
                const sA = Math.min(cellW / imgA.naturalWidth, cellH / imgA.naturalHeight);
                const dwA = imgA.naturalWidth * sA;
                const dhA = imgA.naturalHeight * sA;
                ctx.drawImage(imgA, cellW + gap + (cellW - dwA) / 2, (cellH - dhA) / 2, dwA, dhA);

                // Center divider
                ctx.fillStyle = '#333';
                ctx.fillRect(cellW, 0, gap, totalH);

                // Labels
                ctx.font = 'bold 12px monospace';
                ctx.fillStyle = 'rgba(0,0,0,0.6)';
                ctx.fillRect(4, 4, 90, 18);
                ctx.fillRect(cellW + gap + 4, 4, 90, 18);
                ctx.fillStyle = '#0cf';
                ctx.fillText('Selected', 8, 17);
                ctx.fillStyle = '#aaa';
                ctx.fillText('Previous', cellW + gap + 8, 17);

                previewWidget.aspectRatio = totalW / totalH;
                infoEl.textContent = `Side-by-Side │ Selected: ${allImages[idxB]?.filename || '?'} │ Previous: ${allImages[idxA]?.filename || '?'}`;
                fitNode();
            }

            // ─── Diff Mode — Slider (B→A: selected on left, previous revealed) ─
            async function renderDiffSlider(): Promise<void> {
                compContainer.style.display = 'block';
                canvasEl.style.display = 'none';

                const [idxA, idxB] = getComparisonIndices();
                if (allImages.length < 2) {
                    infoEl.textContent = 'Diff: need at least 2 images';
                    return;
                }

                let imgA: HTMLImageElement, imgB: HTMLImageElement;
                try {
                    [imgA, imgB] = await Promise.all([
                        loadImage(buildViewURL(allImages[idxA])),
                        loadImage(buildViewURL(allImages[idxB])),
                    ]);
                } catch { return; }

                const w = Math.max(imgA.naturalWidth, imgB.naturalWidth);
                const h = Math.max(imgA.naturalHeight, imgB.naturalHeight);

                // Canvas A (full background) = selected/newer (B)
                compCanvasA.width = w;
                compCanvasA.height = h;
                const ctxA = compCanvasA.getContext('2d');
                if (ctxA) {
                    ctxA.fillStyle = '#111';
                    ctxA.fillRect(0, 0, w, h);
                    const s = Math.min(w / imgB.naturalWidth, h / imgB.naturalHeight);
                    const dw = imgB.naturalWidth * s;
                    const dh = imgB.naturalHeight * s;
                    ctxA.drawImage(imgB, (w - dw) / 2, (h - dh) / 2, dw, dh);
                }

                // Canvas B (clipped by slider) = previous/older (A)
                compCanvasB.width = w;
                compCanvasB.height = h;
                const ctxB = compCanvasB.getContext('2d');
                if (ctxB) {
                    ctxB.fillStyle = '#111';
                    ctxB.fillRect(0, 0, w, h);
                    const s = Math.min(w / imgA.naturalWidth, h / imgA.naturalHeight);
                    const dw = imgA.naturalWidth * s;
                    const dh = imgA.naturalHeight * s;
                    ctxB.drawImage(imgA, (w - dw) / 2, (h - dh) / 2, dw, dh);
                }

                compLabelA.textContent = `Selected: ${allImages[idxB]?.filename || ''}`;
                compLabelB.textContent = `Previous: ${allImages[idxA]?.filename || ''}`;

                previewWidget.aspectRatio = w / h;
                updateCompSlider();
                infoEl.textContent = `Diff (Slider) │ ← Selected  |  Previous →`;
                fitNode();
            }

            // ─── Diff Mode — Heatmap / Overlay ────────────────────
            async function renderDiff(): Promise<void> {
                compContainer.style.display = 'none';
                canvasEl.style.display = 'block';

                const [idxA, idxB] = getComparisonIndices();
                if (allImages.length < 2) {
                    infoEl.textContent = 'Diff: need at least 2 images';
                    return;
                }

                let imgA: HTMLImageElement, imgB: HTMLImageElement;
                try {
                    [imgA, imgB] = await Promise.all([
                        loadImage(buildViewURL(allImages[idxA])),
                        loadImage(buildViewURL(allImages[idxB])),
                    ]);
                } catch { return; }

                // Normalize to same size
                const w = Math.max(imgA.naturalWidth, imgB.naturalWidth);
                const h = Math.max(imgA.naturalHeight, imgB.naturalHeight);

                // Draw both images scaled to the same canvas size, then extract pixel data
                const tmpA = document.createElement('canvas');
                tmpA.width = w; tmpA.height = h;
                const ctxTmpA = tmpA.getContext('2d');
                if (!ctxTmpA) return;
                ctxTmpA.fillStyle = '#000';
                ctxTmpA.fillRect(0, 0, w, h);
                const sA = Math.min(w / imgA.naturalWidth, h / imgA.naturalHeight);
                const dwA = imgA.naturalWidth * sA;
                const dhA = imgA.naturalHeight * sA;
                ctxTmpA.drawImage(imgA, (w - dwA) / 2, (h - dhA) / 2, dwA, dhA);
                const dataA = ctxTmpA.getImageData(0, 0, w, h);

                const tmpB = document.createElement('canvas');
                tmpB.width = w; tmpB.height = h;
                const ctxTmpB = tmpB.getContext('2d');
                if (!ctxTmpB) return;
                ctxTmpB.fillStyle = '#000';
                ctxTmpB.fillRect(0, 0, w, h);
                const sB = Math.min(w / imgB.naturalWidth, h / imgB.naturalHeight);
                const dwB = imgB.naturalWidth * sB;
                const dhB = imgB.naturalHeight * sB;
                ctxTmpB.drawImage(imgB, (w - dwB) / 2, (h - dhB) / 2, dwB, dhB);
                const dataB = ctxTmpB.getImageData(0, 0, w, h);

                canvasEl.width = w;
                canvasEl.height = h;
                const ctx = canvasEl.getContext('2d');
                if (!ctx) return;

                const output = ctx.createImageData(w, h);

                if (diffMode === 'heatmap') {
                    // Blue (no diff) → Red (max diff)
                    for (let i = 0; i < dataA.data.length; i += 4) {
                        const dr = Math.abs(dataA.data[i] - dataB.data[i]);
                        const dg = Math.abs(dataA.data[i + 1] - dataB.data[i + 1]);
                        const db = Math.abs(dataA.data[i + 2] - dataB.data[i + 2]);
                        const diff = (dr + dg + db) / 3;
                        const t = Math.min(1, diff / 80); // sensitivity

                        // Blue → Yellow → Red gradient
                        output.data[i] = Math.round(t * 255);     // R
                        output.data[i + 1] = Math.round(t > 0.5 ? (1 - t) * 2 * 200 : t * 2 * 200); // G
                        output.data[i + 2] = Math.round((1 - t) * 200); // B
                        output.data[i + 3] = 255; // A
                    }
                    infoEl.textContent = 'Diff (Heatmap) │ Blue=same, Red=different';
                } else {
                    // Overlay: Selected image with diff highlighted in magenta
                    for (let i = 0; i < dataA.data.length; i += 4) {
                        const dr = Math.abs(dataA.data[i] - dataB.data[i]);
                        const dg = Math.abs(dataA.data[i + 1] - dataB.data[i + 1]);
                        const db = Math.abs(dataA.data[i + 2] - dataB.data[i + 2]);
                        const diff = (dr + dg + db) / 3;
                        const t = Math.min(1, diff / 40); // higher sensitivity for overlay

                        // Blend between selected image and magenta highlight
                        output.data[i] = Math.round(dataB.data[i] * (1 - t) + 255 * t);     // R
                        output.data[i + 1] = Math.round(dataB.data[i + 1] * (1 - t));          // G
                        output.data[i + 2] = Math.round(dataB.data[i + 2] * (1 - t) + 255 * t); // B
                        output.data[i + 3] = 255;
                    }
                    infoEl.textContent = 'Diff (Overlay) │ Magenta = changed pixels';
                }

                ctx.putImageData(output, 0, 0);
                previewWidget.aspectRatio = w / h;
                fitNode();
            }

            // ─── Preview loading ──────────────────────────────────
            function updatePreview(): void {
                if (!currentEntry) return;
                if (currentMode !== 'single' && currentMode !== 'edit') return;
                const url = buildViewURL(currentEntry);
                if (imgEl.src !== url) {
                    imgEl.classList.add('loading');
                    imgEl.src = url;
                }
                updateInfoBar();
            }

            function updateInfoBar(): void {
                if (!currentEntry) {
                    infoEl.textContent = 'No image loaded';
                    return;
                }
                const name = currentEntry.filename;
                const ext = name.split('.').pop()?.toUpperCase() || '';
                const dims = imgEl.naturalWidth && imgEl.naturalHeight
                    ? `${imgEl.naturalWidth}×${imgEl.naturalHeight}`
                    : '';
                const parts = [name];
                if (dims) parts.push(dims);
                if (ext) parts.push(ext);
                infoEl.textContent = parts.join(' │ ');
            }

            // ─── Browser strip population ─────────────────────────
            function populateBrowserStrip(images: ImageEntry[]): void {
                browserStrip.innerHTML = '';
                allImages = images;

                for (let i = 0; i < images.length; i++) {
                    const entry = images[i];
                    const thumbEl = document.createElement('div');
                    thumbEl.className = 'll_thumb';
                    thumbEl.style.width = '64px';
                    thumbEl.style.height = '48px';

                    const img = document.createElement('img');
                    img.src = buildViewURL(entry);
                    img.alt = entry.filename;
                    img.loading = 'lazy';
                    thumbEl.appendChild(img);

                    // Label
                    const label = document.createElement('div');
                    label.className = 'll_thumb_label';
                    label.textContent = entry.filename.length > 12
                        ? '…' + entry.filename.slice(-11)
                        : entry.filename;
                    thumbEl.appendChild(label);

                    // Active state
                    if (i === selectedIndex ||
                        (selectedIndex < 0 && currentEntry?.filename === entry.filename)) {
                        thumbEl.classList.add('active');
                    }

                    // Pin badge
                    const pinWidget = node.widgets?.find((w: any) => w.name === 'pin_index');
                    if (pinWidget && pinWidget.value > 0 && i === 0) {
                        const badge = document.createElement('div');
                        badge.className = 'll_pin_badge';
                        badge.innerHTML = iconPin;
                        thumbEl.appendChild(badge);
                    }

                    // Click to select
                    thumbEl.addEventListener('click', (e: Event) => {
                        e.stopPropagation();
                        selectedIndex = i;
                        currentEntry = entry;

                        // Send selection to backend
                        fetch(api.apiURL('/loadlast/select_image'), {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                node_id: String(node.id),
                                entry: {
                                    filename: entry.filename,
                                    subfolder: entry.subfolder,
                                    type: entry.type,
                                },
                            }),
                        }).catch(() => { });

                        // Update preview based on mode
                        if (currentMode === 'single') {
                            updatePreview();
                        } else if (currentMode === 'edit') {
                            updatePreview();
                            // Also update the edit mode image
                            if (editImg) {
                                editImg.src = buildViewURL(entry);
                            }
                        } else {
                            renderCurrentMode();
                        }
                        highlightStrip();
                    });

                    browserStrip.appendChild(thumbEl);
                }

                // Update scroll after populating
                requestAnimationFrame(() => {
                    updateScrollIndicator();
                });
            }

            function highlightStrip(): void {
                const thumbs = browserStrip.querySelectorAll('.ll_thumb');
                thumbs.forEach((t: Element, i: number) => {
                    t.classList.toggle('active',
                        i === selectedIndex ||
                        (selectedIndex < 0 && currentEntry?.filename === allImages[i]?.filename),
                    );
                });
            }

            // ─── Polling for latest image ─────────────────────────
            async function pollLatest(): Promise<void> {
                try {
                    const srcWidget = node.widgets?.find((w: any) => w.name === 'source_folder');
                    const prefixWidget = node.widgets?.find((w: any) => w.name === 'filename_filter');
                    const source = srcWidget?.value || '';
                    const prefix = prefixWidget?.value || '';

                    const params = new URLSearchParams();
                    if (source) params.set('source', source);
                    if (prefix) params.set('prefix', prefix);

                    // Fetch latest
                    const resp = await fetch(api.apiURL(`/loadlast/latest_image?${params.toString()}`));
                    if (!resp.ok) return;
                    const data = await resp.json();

                    if (data.found && data.filename) {
                        const newEntry: ImageEntry = {
                            filename: data.filename,
                            subfolder: data.subfolder || '',
                            type: data.type || 'output',
                            mtime: data.mtime || 0,
                        };

                        const pinWidget = node.widgets?.find((w: any) => w.name === 'pin_index');
                        const isPinned = pinWidget && pinWidget.value > 0;

                        if (!isPinned && selectedIndex < 0) {
                            if (!currentEntry || currentEntry.filename !== newEntry.filename ||
                                currentEntry.mtime !== newEntry.mtime) {
                                currentEntry = newEntry;
                                if (currentMode === 'single' || currentMode === 'edit') {
                                    updatePreview();
                                }
                                // Other modes will update when strip refreshes
                            }
                        }
                    }

                    // Fetch image list for browser strip
                    const listResp = await fetch(
                        api.apiURL(`/loadlast/image_list?${params.toString()}&limit=30`),
                    );
                    if (listResp.ok) {
                        const listData = await listResp.json();
                        if (listData.images && Array.isArray(listData.images)) {
                            populateBrowserStrip(listData.images);
                        }
                    }
                } catch {
                    // Network error — silent
                }
            }

            // Start polling on node creation
            pollLatest();
            pollTimer = setInterval(pollLatest, 5000);

            // ─── onExecuted — update from execution results ───────
            const origOnExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (this: any, output: any) {
                origOnExecuted?.apply(this, arguments);

                if (output?.images && Array.isArray(output.images) && output.images.length > 0) {
                    const entry = output.images[0] as ImageEntry;
                    currentEntry = {
                        filename: entry.filename,
                        subfolder: entry.subfolder || '',
                        type: entry.type || 'output',
                        mtime: Date.now() / 1000,
                    };
                    selectedIndex = -1;

                    if (currentMode === 'single' || currentMode === 'edit') {
                        updatePreview();
                    }
                    // Refresh the strip (which may trigger canvas re-render)
                    pollLatest();
                }
            };

            // ─── Cleanup ──────────────────────────────────────────
            const origRemoved = nodeType.prototype.onRemoved;
            nodeType.prototype.onRemoved = function (this: any) {
                if (pollTimer) {
                    clearInterval(pollTimer);
                    pollTimer = null;
                }
                origRemoved?.apply(this, arguments);
            };
        };

        // ─── Context menu: Point Selector / Mask Editor ───────
        const origGetMenu = nodeType.prototype.getExtraMenuOptions;
        nodeType.prototype.getExtraMenuOptions = function (
            this: any,
            _canvas: unknown,
            options: any[],
        ): void {
            origGetMenu?.apply(this, arguments);
            const self = this;

            // Find current image source for the point selector
            options.unshift({
                content: '🎯 Open Mask / Point Editor',
                callback: () => {
                    // Try to get image URL from current preview
                    const preview = self.widgets?.find((w: any) => w.name === 'preview');
                    const imgEl = preview?.element?.querySelector?.('img.ll_img_preview') as HTMLImageElement | null;
                    const src = imgEl?.src;
                    if (!src) {
                        flashNode(self, '#7a4a4a');
                        return;
                    }
                    openPointSelector(self, src);
                },
            }, null);
        };
    },
});
