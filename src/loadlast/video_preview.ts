/**
 * Load Last Video — Enhanced Video Preview Widget (TypeScript)
 *
 * Features:
 *   - Immediate video preview (no queue needed)
 *   - Toolbar with view modes: Playback, Grid, Side-by-Side, Filmstrip, Selected
 *   - Video browser strip (thumbnails of all recent videos)
 *   - Custom scrollbar with drag support
 *   - Frame selection with per-mode state
 *   - Paginated filmstrip browser with zoom/scrubber
 *   - Selection markers on playback/filmstrip timelines
 */

import { api } from 'comfyui/api';
import { app } from 'comfyui/app';
import {
    VIEW_MODES,
    ZOOM_LEVELS,
    ZOOM_LABELS,
    FRAMES_PER_PAGE,
    TOOLBAR_BUTTONS,
    type ViewMode,
    type ModeGeometry,
    type VideoEntry,
} from '@ffmpega/types/loadlast';
import { captureFrame, captureFrames, viewUrl, fmtDuration } from '@ffmpega/shared/utils';
import { SelectionManager } from '@ffmpega/loadlast/selection/SelectionManager';
import { hitTestFrame } from '@ffmpega/loadlast/selection/HitTester';
import { drawSelectionOverlay } from '@ffmpega/loadlast/selection/SelectionOverlay';
import { EditManager } from '@ffmpega/loadlast/editing/EditManager';
import { EditTimeline } from '@ffmpega/loadlast/editing/EditTimeline';
import cssText from './loadlast.css?inline';

// ─── Inject stylesheet once ────────────────────────────────────────────
if (!document.getElementById('loadlast-styles')) {
    const style = document.createElement('style');
    style.id = 'loadlast-styles';
    style.textContent = cssText;
    document.head.appendChild(style);
}

// ─── Extension ─────────────────────────────────────────────────────────

app.registerExtension({
    name: 'LoadLast.VideoPreview',
    beforeRegisterNodeDef(nodeType: any, nodeData: any, _app: any) {
        if (nodeData?.name !== 'LoadLastVideo') return;

        const origCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (this: any) {
            origCreated?.apply(this, arguments);

            const node = this;
            const selections = new SelectionManager();
            selections.bind(node);

            let currentMode: ViewMode = VIEW_MODES.PLAYBACK;
            let modeGeometry: ModeGeometry | null = null;
            let lastFilename = '';

            // ─── Edit mode state ──────────────────────────────────
            const editMgr = new EditManager();
            editMgr.bind(node);
            let editTimeline: EditTimeline | null = null;
            let editWrapper: HTMLDivElement | null = null;
            let editPlaybackRaf: number | null = null;
            let editPlaying = false;
            let editOutputTime = 0;
            let editPlayBtn: HTMLButtonElement | null = null;
            let editTimeDisplay: HTMLSpanElement | null = null;
            let editBlackOverlay: HTMLDivElement | null = null;

            // ─── Filmstrip pagination state ───────────────────────
            let filmstripZoom = 0;
            let filmstripPage = 0;

            // Style
            node.color = '#2a4a5a';
            node.bgcolor = '#1a3a4a';

            // ─── Container ────────────────────────────────────────
            const container = document.createElement('div');
            container.className = 'll_container';
            container.tabIndex = 0; // for keyboard events

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
                btn.addEventListener('click', (e: Event) => {
                    e.stopPropagation();
                    switchMode(def.id);
                });
                buttons.push(btn);
                toolbar.appendChild(btn);
            }

            // Clear selection button
            const clearBtn = document.createElement('button');
            clearBtn.innerHTML = '<svg width="11" height="11" viewBox="0 0 11 11" fill="currentColor"><path d="M1.5 0.5 L5.5 4.5 L9.5 0.5 L10.5 1.5 L6.5 5.5 L10.5 9.5 L9.5 10.5 L5.5 6.5 L1.5 10.5 L0.5 9.5 L4.5 5.5 L0.5 1.5 Z"/></svg>';
            clearBtn.title = 'Clear selection';
            clearBtn.className = 'll_clear_btn';
            clearBtn.addEventListener('click', (e: Event) => {
                e.stopPropagation();
                selections.clearMode(currentMode);
                updateSelectionUI();
                // Re-render to remove selection overlays drawn on canvas
                if (currentMode !== VIEW_MODES.PLAYBACK) renderCurrentMode();
                else drawSelectionOverlay(canvasEl, modeGeometry, selections.get(currentMode));
            });
            toolbar.appendChild(clearBtn);

            // ─── Selection count badge (top-right) ───────────────
            const selBadge = document.createElement('div');
            selBadge.className = 'll_sel_badge';
            // Hover styles handled by CSS .ll_sel_badge:hover
            selBadge.addEventListener('click', (e: Event) => {
                e.stopPropagation();
                selections.clearAll();
                updateSelectionUI();
                // Re-render to remove selection overlays drawn on canvas
                if (currentMode !== VIEW_MODES.PLAYBACK) renderCurrentMode();
                else drawSelectionOverlay(canvasEl, modeGeometry, selections.get(currentMode));
            });
            container.appendChild(selBadge);

            function updateSelBadge(): void {
                const total = selections.totalCount();
                if (total > 0) {
                    selBadge.innerHTML = `${total} sel <svg width="8" height="8" viewBox="0 0 8 8" fill="#000" style="vertical-align:middle;margin-left:3px;opacity:0.6"><path d="M1 0 L4 3 L7 0 L8 1 L5 4 L8 7 L7 8 L4 5 L1 8 L0 7 L3 4 L0 1 Z"/></svg>`;
                    selBadge.style.display = 'block';
                } else {
                    selBadge.style.display = 'none';
                }
            }

            function highlightToolbar(): void {
                for (const btn of buttons) {
                    const active = btn.dataset.mode === currentMode;
                    btn.classList.toggle('active', active);
                }
                const selCount = selections.totalCount();
                clearBtn.style.display = selCount > 0 ? 'block' : 'none';
                updateSelBadge();
            }

            // ─── Selection UI helpers ─────────────────────────────
            function updateSelectionUI(): void {
                selections.syncToWidget();
                updatePlaybackMarkers();

                const modeCount = selections.get(currentMode).size;
                const totalCount = selections.totalCount();
                const extra = modeCount > 0 ? ` │ ${modeCount} selected` : '';
                const totalExtra = totalCount > 0 ? ` │ ${totalCount} total ` : '';
                infoEl.textContent = (infoEl.textContent || '').split('│')[0].trim()
                    + extra + totalExtra;
                highlightToolbar();
            }

            // ─── Playback markers ─────────────────────────────────
            const markerBar = document.createElement('div');
            markerBar.className = 'loadlast_marker_bar';
            markerBar.className = 'll_marker_bar';

            function updatePlaybackMarkers(): void {
                const dur = videoEl.duration;
                markerBar.innerHTML = '';
                const allTs = selections.allTimestamps();
                if (allTs.length === 0 || !dur || !isFinite(dur)) {
                    markerBar.style.display = 'none';
                    return;
                }
                markerBar.style.display = 'block';
                for (const t of allTs) {
                    const pct = (t / dur) * 100;
                    if (pct < 0 || pct > 100) continue;
                    const tick = document.createElement('div');
                    tick.className = 'll_marker_tick';
                    tick.style.left = `calc(${pct.toFixed(2)}% - 1px)`;
                    tick.title = fmtDuration(t);
                    markerBar.appendChild(tick);
                }
            }

            // ─── Video element ────────────────────────────────────
            const videoEl = document.createElement('video');
            videoEl.controls = true;
            videoEl.loop = true;
            videoEl.muted = true;
            videoEl.autoplay = true;
            videoEl.setAttribute('aria-label', 'Last video preview');
            videoEl.className = 'll_video';

            // ─── Canvas element ───────────────────────────────────
            const canvasEl = document.createElement('canvas');
            canvasEl.className = 'll_canvas';

            // Canvas click → frame selection
            canvasEl.addEventListener('click', (e: MouseEvent) => {
                if (!modeGeometry) return;
                e.stopPropagation();
                const rect = canvasEl.getBoundingClientRect();
                const scaleX = canvasEl.width / rect.width;
                const scaleY = canvasEl.height / rect.height;
                const cx = (e.clientX - rect.left) * scaleX;
                const cy = (e.clientY - rect.top) * scaleY;

                const ts = hitTestFrame(modeGeometry, cx, cy);
                if (ts === null) return;

                selections.toggle(currentMode, ts);
                updateSelectionUI();
                // Re-render to cleanly add/remove selection overlays
                renderCurrentMode();
            });

            // ─── Info bar ─────────────────────────────────────────
            const infoEl = document.createElement('div');
            infoEl.className = 'll_info';

            // ─── Browser strip (video thumbnails) ─────────────────
            const browserStrip = document.createElement('div');
            browserStrip.className = 'loadlast_browser_strip';
            browserStrip.className = 'll_browser_strip';

            // Scroll track
            const scrollTrack = document.createElement('div');
            scrollTrack.className = 'll_scroll_track';
            const scrollThumb = document.createElement('div');
            scrollThumb.className = 'll_scroll_thumb';
            // Hover styles handled by CSS .ll_scroll_thumb:hover
            scrollTrack.appendChild(scrollThumb);

            let thumbDragging = false;
            function updateScrollIndicator(): void {
                const sw = browserStrip.scrollWidth;
                const cw = browserStrip.clientWidth;
                if (sw <= cw) {
                    // Still show the track as a thin bar so user sees it exists
                    scrollTrack.style.display = allVideos.length > 1 ? 'block' : 'none';
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
                thumbDragging = true;
                scrollThumb.style.cursor = 'grabbing';
                scrollThumb.style.background = '#bbb';
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
                    thumbDragging = false;
                    scrollThumb.style.cursor = 'grab';
                    scrollThumb.style.background = '#5ac';
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
                // toolbar(32) + infoBar(22) + markerBar(14) + browserStrip+scrollbar(100)
                let chrome = 32 + 22 + 14 + (allVideos.length > 1 ? 100 : 0);
                if (currentMode === VIEW_MODES.FILMSTRIP) chrome += 50;
                if (currentMode === VIEW_MODES.EDIT) chrome += 180; // transport + timeline + controls
                if (this.aspectRatio) {
                    const h = (node.size[0] - 20) / this.aspectRatio;
                    return [width, Math.max(h, 80) + chrome];
                }
                return [width, 80 + chrome];
            };

            // ─── Assemble DOM ─────────────────────────────────────
            container.appendChild(toolbar);
            container.appendChild(videoEl);
            container.appendChild(markerBar);
            container.appendChild(canvasEl);
            container.appendChild(infoEl);

            const stripWrapper = document.createElement('div');
            stripWrapper.className = 'll_strip_wrapper';
            stripWrapper.appendChild(browserStrip);
            stripWrapper.appendChild(scrollTrack);
            container.appendChild(stripWrapper);

            // ─── View mode switching ──────────────────────────────
            async function switchMode(mode: ViewMode): Promise<void> {
                currentMode = mode;
                highlightToolbar();

                // Clean up edit mode when leaving
                if (mode !== VIEW_MODES.EDIT) {
                    cleanupEditMode();
                }

                if (mode === VIEW_MODES.PLAYBACK) {
                    modeGeometry = null;
                    canvasEl.style.display = 'none';
                    canvasEl.height = 0;   // Reset canvas height so it doesn't push layout
                    videoEl.style.display = 'block';
                    videoEl.play().catch(() => { });
                    const sel = selections.get(VIEW_MODES.PLAYBACK);
                    const selInfo = sel.size ? ` │ ${sel.size} selected` : '';
                    infoEl.textContent = buildInfoText() + selInfo;
                } else if (mode === VIEW_MODES.EDIT) {
                    // ─── Edit mode: self-contained wrapper ──────────
                    canvasEl.style.display = 'none';
                    canvasEl.height = 0;
                    videoEl.controls = false;
                    videoEl.pause();

                    // Build wrapper
                    editWrapper = document.createElement('div');
                    editWrapper.className = 'll_edit_wrapper';

                    // Video area with overlay
                    const videoArea = document.createElement('div');
                    videoArea.className = 'll_edit_video_area';
                    videoEl.style.display = 'block';
                    videoArea.appendChild(videoEl);  // move video into wrapper

                    editBlackOverlay = document.createElement('div');
                    editBlackOverlay.className = 'll_edit_black_overlay';
                    videoArea.appendChild(editBlackOverlay);
                    editWrapper.appendChild(videoArea);

                    // Transport bar
                    const transport = document.createElement('div');
                    transport.className = 'll_edit_transport';

                    editPlayBtn = document.createElement('button');
                    editPlayBtn.className = 'll_edit_play_btn';
                    editPlayBtn.textContent = '▶';
                    editPlayBtn.title = 'Play edited clip';
                    editPlayBtn.addEventListener('click', (e: Event) => {
                        e.stopPropagation();
                        if (editPlaying) {
                            stopEditPlayback();
                        } else {
                            startEditPlayback();
                        }
                    });
                    transport.appendChild(editPlayBtn);

                    editTimeDisplay = document.createElement('span');
                    editTimeDisplay.className = 'll_edit_time_display';
                    editTimeDisplay.textContent = '0:00 / 0:00';
                    transport.appendChild(editTimeDisplay);
                    editWrapper.appendChild(transport);

                    // Timeline
                    const dur = videoEl.duration;
                    if (dur && isFinite(dur)) {
                        editMgr.init(dur);
                        editOutputTime = 0;
                        updateEditTimeDisplay();

                        editTimeline = new EditTimeline(editMgr, {
                            onSegmentsChanged: () => {
                                editMgr.syncToWidget();
                                updateEditPreview();
                                updateEditInfo();
                                updateEditTimeDisplay();
                            },
                            onPlayheadChanged: (time: number) => {
                                videoEl.currentTime = time;
                                if (editBlackOverlay) {
                                    editBlackOverlay.style.display = editMgr.isInGap(time) ? 'block' : 'none';
                                }
                                editOutputTime = Math.max(0, editMgr.sourceTimeToOutput(time));
                                updateEditTimeDisplay();
                            },
                            onTrimHandleDrag: (time: number) => {
                                videoEl.currentTime = time;
                                if (editBlackOverlay) editBlackOverlay.style.display = 'none';
                                editOutputTime = Math.max(0, editMgr.sourceTimeToOutput(time));
                                updateEditTimeDisplay();
                            },
                            onRequestSplit: () => { },
                        });
                        editWrapper.appendChild(editTimeline.element);

                        videoEl.currentTime = editMgr.segments[0]?.start ?? 0;

                        requestAnimationFrame(() => {
                            editTimeline?.render();
                        });
                    }

                    // Insert wrapper into container, before stripWrapper
                    container.insertBefore(editWrapper, stripWrapper);
                    updateEditInfo();
                } else {
                    videoEl.pause();
                    videoEl.style.display = 'none';
                    canvasEl.style.display = 'block';
                    await renderCurrentMode();
                }

                // Clean up filmstrip controls when leaving filmstrip
                if (mode !== VIEW_MODES.FILMSTRIP) {
                    const oldCtrl = container.querySelector('.filmstrip_controls');
                    if (oldCtrl) oldCtrl.remove();
                }

                // Recalculate node size immediately
                fitNode();
            }

            /** Tear down edit mode: move video back, remove wrapper, restore controls */
            function cleanupEditMode(): void {
                stopEditPlayback();
                if (editTimeline) {
                    editTimeline = null;
                }
                if (editWrapper) {
                    // Move video back to container (before stripWrapper)
                    videoEl.style.display = 'none';
                    videoEl.controls = true;
                    container.insertBefore(videoEl, stripWrapper);
                    editWrapper.remove();
                    editWrapper = null;
                }
                editPlayBtn = null;
                editTimeDisplay = null;
                editBlackOverlay = null;
            }

            function updateEditInfo(): void {
                if (!editMgr.hasEdits()) {
                    infoEl.textContent = buildInfoText() + ' │ ✂️ Edit mode (no changes)';
                } else {
                    const outDur = fmtDuration(editMgr.getOutputDuration());
                    const segs = editMgr.segments.length;
                    infoEl.textContent = `✂️ Edit: ${outDur} output │ ${segs} segment${segs !== 1 ? 's' : ''}`;
                }
            }

            /** Update video to reflect current edit state (jump out of gaps) */
            function updateEditPreview(): void {
                const srcTime = videoEl.currentTime;
                const inGap = editMgr.isInGap(srcTime);
                if (editBlackOverlay) {
                    editBlackOverlay.style.display = inGap ? 'block' : 'none';
                }
                if (inGap && editMgr.segments.length > 0) {
                    const nextSeg = editMgr.segments.find(s => s.start >= srcTime);
                    if (nextSeg) {
                        videoEl.currentTime = nextSeg.start;
                    } else {
                        videoEl.currentTime = editMgr.segments[0].start;
                    }
                    if (editBlackOverlay) editBlackOverlay.style.display = 'none';
                }
                editOutputTime = Math.max(0, editMgr.sourceTimeToOutput(videoEl.currentTime));
            }

            /** Update the transport time display */
            function updateEditTimeDisplay(): void {
                if (!editTimeDisplay) return;
                const pos = fmtDuration(editOutputTime);
                const total = fmtDuration(editMgr.getOutputDuration());
                editTimeDisplay.textContent = `${pos} / ${total}`;
            }

            /** Start NLE playback: plays through segments, skipping gaps */
            function startEditPlayback(): void {
                if (editPlaying) return;
                editPlaying = true;
                if (editPlayBtn) editPlayBtn.textContent = '⏸';

                let lastFrameTime = performance.now();

                function editLoop(now: number): void {
                    if (!editPlaying) return;
                    const dt = (now - lastFrameTime) / 1000;
                    lastFrameTime = now;

                    editOutputTime += dt;
                    const totalDur = editMgr.getOutputDuration();
                    if (editOutputTime >= totalDur) {
                        editOutputTime = 0;
                    }

                    const srcTime = editMgr.outputTimeToSource(editOutputTime);
                    videoEl.currentTime = srcTime;
                    if (editBlackOverlay) editBlackOverlay.style.display = 'none';

                    if (editTimeline) {
                        editTimeline.playhead = srcTime;
                        editTimeline.render();
                    }
                    updateEditTimeDisplay();

                    editPlaybackRaf = requestAnimationFrame(editLoop);
                }

                videoEl.pause();
                editPlaybackRaf = requestAnimationFrame(editLoop);
            }

            /** Stop NLE playback */
            function stopEditPlayback(): void {
                editPlaying = false;
                if (editPlayBtn) editPlayBtn.textContent = '▶';
                if (editPlaybackRaf !== null) {
                    cancelAnimationFrame(editPlaybackRaf);
                    editPlaybackRaf = null;
                }
            }
            // ─── Keyboard shortcuts ───────────────────────────────
            container.addEventListener('keydown', (e: KeyboardEvent) => {
                if (currentMode !== VIEW_MODES.FILMSTRIP) return;
                const dur = videoEl.duration;
                if (!dur || !isFinite(dur)) return;
                const interval = ZOOM_LEVELS[filmstripZoom];
                const totalFrames = Math.max(1, Math.floor(dur / interval));
                const totalPages = Math.ceil(totalFrames / FRAMES_PER_PAGE);

                if (e.key === 'ArrowRight') {
                    e.stopPropagation();
                    e.preventDefault();
                    if (e.shiftKey) {
                        const nextStart = filmstripPage * FRAMES_PER_PAGE + 1;
                        filmstripPage = Math.min(Math.floor(nextStart / FRAMES_PER_PAGE), totalPages - 1);
                    } else {
                        if (filmstripPage < totalPages - 1) filmstripPage++;
                    }
                    renderCurrentMode();
                } else if (e.key === 'ArrowLeft') {
                    e.stopPropagation();
                    e.preventDefault();
                    if (e.shiftKey) {
                        const prevStart = filmstripPage * FRAMES_PER_PAGE - 1;
                        filmstripPage = Math.max(Math.floor(prevStart / FRAMES_PER_PAGE), 0);
                    } else {
                        if (filmstripPage > 0) filmstripPage--;
                    }
                    renderCurrentMode();
                }
            });

            // ─── Playback click → select frame ───────────────────
            const flashOverlay = document.createElement('div');
            flashOverlay.className = 'll_flash_overlay';
            container.appendChild(flashOverlay);

            function flashSelection(added: boolean): void {
                flashOverlay.style.borderColor = added ? '#00ddff' : '#ff4444';
                flashOverlay.style.opacity = '1';
                setTimeout(() => {
                    flashOverlay.style.transition = 'opacity 0.4s ease-out';
                    flashOverlay.style.opacity = '0';
                    setTimeout(() => {
                        flashOverlay.style.transition = 'opacity 0.1s ease-in';
                    }, 400);
                }, 100);
            }

            videoEl.addEventListener('click', (e: MouseEvent) => {
                if (currentMode !== VIEW_MODES.PLAYBACK) return;
                if (!videoEl.paused) return;
                e.stopPropagation();
                const ts = Math.round(videoEl.currentTime * 1000) / 1000;
                const added = selections.toggle(VIEW_MODES.PLAYBACK, ts);
                flashSelection(added);
                updateSelectionUI();
            }, true);

            // ─── Render current mode ──────────────────────────────
            async function renderCurrentMode(): Promise<void> {
                const vw = videoEl.videoWidth;
                const vh = videoEl.videoHeight;
                if (!vw || !vh) return;

                if (currentMode === VIEW_MODES.GRID) {
                    infoEl.textContent = 'Capturing grid frames...';
                    const cols = 3, rows = 3, count = cols * rows;
                    const frames = await captureFrames(videoEl, count);
                    if (!frames.length) {
                        infoEl.textContent = 'Could not capture frames';
                        return;
                    }

                    const cellW = Math.round(300 * (vw / vh));
                    const cellH = 300;
                    canvasEl.width = cellW * cols;
                    canvasEl.height = cellH * rows;
                    const ctx = canvasEl.getContext('2d')!;
                    ctx.fillStyle = '#000';
                    ctx.fillRect(0, 0, canvasEl.width, canvasEl.height);

                    const dur = videoEl.duration;
                    for (let i = 0; i < frames.length; i++) {
                        const col = i % cols;
                        const row = Math.floor(i / cols);
                        const x = col * cellW;
                        const y = row * cellH;
                        ctx.drawImage(frames[i], 0, 0, vw, vh, x, y, cellW, cellH);

                        const t = (dur * i) / Math.max(count - 1, 1);
                        const label = fmtDuration(t);
                        ctx.font = 'bold 11px monospace';
                        ctx.fillStyle = 'rgba(0,0,0,0.7)';
                        ctx.fillRect(x + 2, y + 2, ctx.measureText(label).width + 8, 16);
                        ctx.fillStyle = '#ccc';
                        ctx.textBaseline = 'top';
                        ctx.fillText(label, x + 5, y + 4);
                    }

                    previewWidget.aspectRatio = canvasEl.width / canvasEl.height;
                    modeGeometry = {
                        mode: VIEW_MODES.GRID,
                        cols, rows, count,
                        cellW, cellH,
                        timestamps: Array.from({ length: count }, (_, i) =>
                            Math.round(((dur * i) / Math.max(count - 1, 1)) * 1000) / 1000
                        ),
                    };
                    const gSelCount = selections.get(VIEW_MODES.GRID).size;
                    infoEl.textContent = `Grid: ${count} frames │ ${fmtDuration(dur)}`
                        + (gSelCount ? ` │ ${gSelCount} selected` : '');
                    drawSelectionOverlay(canvasEl, modeGeometry, selections.get(VIEW_MODES.GRID));
                    fitNode();

                } else if (currentMode === VIEW_MODES.SIDE_BY_SIDE) {
                    infoEl.textContent = 'Capturing comparison frames...';
                    const dur = videoEl.duration;
                    const firstFrame = await captureFrame(videoEl, 0);
                    const lastFrame = await captureFrame(videoEl, Math.max(dur - 0.1, 0));

                    const h = 300;
                    const w = Math.round(h * (vw / vh));
                    const gap = 4;
                    canvasEl.width = w * 2 + gap;
                    canvasEl.height = h;
                    const ctx = canvasEl.getContext('2d')!;
                    ctx.fillStyle = '#000';
                    ctx.fillRect(0, 0, canvasEl.width, canvasEl.height);
                    ctx.drawImage(firstFrame, 0, 0, vw, vh, 0, 0, w, h);
                    ctx.drawImage(lastFrame, 0, 0, vw, vh, w + gap, 0, w, h);

                    // Labels
                    ctx.font = 'bold 11px monospace';
                    ctx.textBaseline = 'top';
                    for (const [label, x] of [['FIRST', 4], ['LAST', w + gap + 4]] as const) {
                        ctx.fillStyle = 'rgba(0,0,0,0.7)';
                        ctx.fillRect(x, 4, ctx.measureText(label).width + 8, 16);
                        ctx.fillStyle = '#ccc';
                        ctx.fillText(label, x + 4, 6);
                    }

                    previewWidget.aspectRatio = canvasEl.width / canvasEl.height;
                    const ts0 = 0;
                    const ts1 = Math.round(Math.max(dur - 0.1, 0) * 1000) / 1000;
                    modeGeometry = {
                        mode: VIEW_MODES.SIDE_BY_SIDE,
                        videoWidth: w,
                        gap,
                        timestamps: [ts0, ts1],
                    };
                    const sSelCount = selections.get(VIEW_MODES.SIDE_BY_SIDE).size;
                    infoEl.textContent = `Side by Side │ ${fmtDuration(dur)}`
                        + (sSelCount ? ` │ ${sSelCount} selected` : '');
                    drawSelectionOverlay(canvasEl, modeGeometry, selections.get(VIEW_MODES.SIDE_BY_SIDE));
                    fitNode();

                } else if (currentMode === VIEW_MODES.FILMSTRIP) {
                    const dur = videoEl.duration;
                    if (!dur || !isFinite(dur)) return;

                    const interval = ZOOM_LEVELS[filmstripZoom];
                    const totalFrames = Math.max(1, Math.floor(dur / interval));
                    const totalPages = Math.ceil(totalFrames / FRAMES_PER_PAGE);
                    filmstripPage = Math.max(0, Math.min(filmstripPage, totalPages - 1));
                    const startIdx = filmstripPage * FRAMES_PER_PAGE;
                    const endIdx = Math.min(startIdx + FRAMES_PER_PAGE, totalFrames);
                    const pageCount = endIdx - startIdx;

                    infoEl.textContent = `Capturing frames ${startIdx + 1}–${endIdx} of ${totalFrames}...`;
                    const pageFrames: OffscreenCanvas[] = [];
                    const pageTimestamps: number[] = [];
                    for (let i = startIdx; i < endIdx; i++) {
                        const t = Math.min(i * interval, dur - 0.01);
                        pageTimestamps.push(Math.round(t * 1000) / 1000);
                        pageFrames.push(await captureFrame(videoEl, t));
                    }

                    const fh = 200;
                    const fw = Math.round(fh * (vw / vh));
                    const gap = 3;
                    canvasEl.width = (fw + gap) * pageCount - gap;
                    canvasEl.height = fh;
                    const ctx = canvasEl.getContext('2d')!;
                    ctx.fillStyle = '#000';
                    ctx.fillRect(0, 0, canvasEl.width, canvasEl.height);

                    for (let i = 0; i < pageFrames.length; i++) {
                        const x = i * (fw + gap);
                        ctx.drawImage(pageFrames[i], 0, 0, vw, vh, x, 0, fw, fh);

                        // Timestamp label
                        const label = fmtDuration(pageTimestamps[i]);
                        ctx.font = 'bold 11px monospace';
                        ctx.textBaseline = 'top';
                        ctx.fillStyle = 'rgba(0,0,0,0.75)';
                        const tw = ctx.measureText(label).width;
                        ctx.fillRect(x + 3, 3, tw + 8, 18);
                        ctx.fillStyle = '#eee';
                        ctx.fillText(label, x + 7, 6);

                        // Frame number
                        const frameNum = `#${startIdx + i + 1}`;
                        ctx.font = 'bold 10px monospace';
                        ctx.textBaseline = 'bottom';
                        ctx.fillStyle = 'rgba(0,0,0,0.75)';
                        const fnw = ctx.measureText(frameNum).width;
                        ctx.fillRect(x + 3, fh - 18, fnw + 8, 16);
                        ctx.fillStyle = '#aaa';
                        ctx.fillText(frameNum, x + 7, fh - 4);
                    }

                    previewWidget.aspectRatio = canvasEl.width / canvasEl.height;
                    modeGeometry = {
                        mode: VIEW_MODES.FILMSTRIP,
                        frameWidth: fw,
                        frameHeight: fh,
                        gap,
                        count: pageCount,
                        timestamps: pageTimestamps,
                    };
                    drawSelectionOverlay(canvasEl, modeGeometry, selections.get(VIEW_MODES.FILMSTRIP));

                    // ─── Filmstrip controls ───────────────────────
                    const oldCtrl = container.querySelector('.filmstrip_controls');
                    if (oldCtrl) oldCtrl.remove();

                    const ctrl = document.createElement('div');
                    ctrl.className = 'filmstrip_controls ll_filmstrip_ctrl';

                    // Row 1: nav + zoom + counter
                    const row1 = document.createElement('div');
                    row1.className = 'll_filmstrip_row';
                    row1.style.cssText = 'font-size:11px;font-family:monospace;color:#999;';

                    const makeBtn = (text: string, tip: string, onClick: () => void): HTMLButtonElement => {
                        const b = document.createElement('button');
                        b.textContent = text;
                        b.title = tip;
                        b.className = 'll_filmstrip_btn';
                        b.addEventListener('click', (e: Event) => { e.stopPropagation(); onClick(); });
                        return b;
                    };

                    const prevBtn = makeBtn('◀', 'Previous page', () => {
                        if (filmstripPage > 0) { filmstripPage--; renderCurrentMode(); }
                    });
                    const nextBtn = makeBtn('▶', 'Next page', () => {
                        if (filmstripPage < totalPages - 1) { filmstripPage++; renderCurrentMode(); }
                    });
                    const zoomOutBtn = makeBtn('➖', 'Zoom out (sparser)', () => {
                        if (filmstripZoom > 0) { filmstripZoom--; filmstripPage = 0; renderCurrentMode(); }
                    });
                    const zoomInBtn = makeBtn('➕', 'Zoom in (denser)', () => {
                        if (filmstripZoom < ZOOM_LEVELS.length - 1) { filmstripZoom++; filmstripPage = 0; renderCurrentMode(); }
                    });

                    row1.append(prevBtn, nextBtn);
                    const sep1 = document.createElement('span');
                    sep1.textContent = '│'; sep1.style.color = '#444';
                    row1.append(sep1);
                    row1.append(zoomOutBtn, zoomInBtn);
                    const zoomLabel = document.createElement('span');
                    zoomLabel.textContent = ZOOM_LABELS[filmstripZoom];
                    zoomLabel.style.color = '#5ac';
                    row1.append(zoomLabel);
                    const sep2 = document.createElement('span');
                    sep2.textContent = '│'; sep2.style.color = '#444';
                    row1.append(sep2);
                    const counter = document.createElement('span');
                    counter.textContent = `Frames ${startIdx + 1}–${endIdx} of ${totalFrames}`;
                    row1.append(counter);

                    const fSelCount = selections.get(VIEW_MODES.FILMSTRIP).size;
                    if (fSelCount > 0) {
                        const selLabel = document.createElement('span');
                        selLabel.textContent = `│ ${fSelCount} selected`;
                        selLabel.style.color = '#5ac';
                        row1.append(selLabel);
                    }
                    ctrl.appendChild(row1);

                    // Row 2: Timeline scrubber
                    const scrubber = document.createElement('div');
                    scrubber.className = 'll_scrubber';
                    scrubber.style.cssText =
                        'position:relative;height:16px;background:#1a1a1a;' +
                        'border-radius:3px;cursor:pointer;border:1px solid #333;';

                    const rangeStart = (startIdx * interval) / dur;
                    const rangeEnd = (endIdx * interval) / dur;
                    const rangeEl = document.createElement('div');
                    rangeEl.style.cssText =
                        `position:absolute;top:0;bottom:0;` +
                        `left:${(rangeStart * 100).toFixed(2)}%;` +
                        `width:${((rangeEnd - rangeStart) * 100).toFixed(2)}%;` +
                        `background:rgba(90,170,200,0.3);border-radius:3px;`;
                    scrubber.appendChild(rangeEl);

                    // Selection markers on scrubber
                    for (const t of selections.allTimestamps()) {
                        const pct = (t / dur) * 100;
                        if (pct < 0 || pct > 100) continue;
                        const dot = document.createElement('div');
                        dot.className = 'll_marker_tick';
                        dot.style.cssText =
                            `top:3px;width:4px;height:10px;` +
                            `left:calc(${pct.toFixed(2)}% - 2px);`;
                        scrubber.appendChild(dot);
                    }

                    scrubber.addEventListener('mousedown', (e: MouseEvent) => {
                        e.stopPropagation();
                        const rect = scrubber.getBoundingClientRect();
                        const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
                        const targetTime = ratio * dur;
                        const targetIdx = Math.floor(targetTime / interval);
                        filmstripPage = Math.floor(targetIdx / FRAMES_PER_PAGE);
                        renderCurrentMode();
                    });

                    ctrl.appendChild(scrubber);
                    container.insertBefore(ctrl, stripWrapper);

                    infoEl.textContent = `Filmstrip: ${ZOOM_LABELS[filmstripZoom]} │ pg ${filmstripPage + 1}/${totalPages} │ ${fmtDuration(dur)}`;
                    fitNode();

                } else if (currentMode === VIEW_MODES.SELECTED) {
                    const allTs = selections.allTimestampsWithSource();
                    if (allTs.size === 0) {
                        canvasEl.width = 400;
                        canvasEl.height = 100;
                        const ctx = canvasEl.getContext('2d')!;
                        ctx.fillStyle = '#111';
                        ctx.fillRect(0, 0, 400, 100);
                        ctx.font = '13px monospace';
                        ctx.fillStyle = '#555';
                        ctx.textAlign = 'center';
                        ctx.textBaseline = 'middle';
                        ctx.fillText('No frames selected. Click frames in other modes.', 200, 50);
                        previewWidget.aspectRatio = 4;
                        modeGeometry = null;
                        infoEl.textContent = 'Selected: 0 frames';
                        fitNode();
                        return;
                    }

                    const sorted = Array.from(allTs.entries()).sort((a, b) => a[0] - b[0]);
                    infoEl.textContent = `Capturing ${sorted.length} selected frames...`;

                    const galFrames: OffscreenCanvas[] = [];
                    for (const [ts] of sorted) {
                        galFrames.push(await captureFrame(videoEl, ts));
                    }

                    const galCols = sorted.length <= 2 ? sorted.length : sorted.length <= 4 ? 2 : 3;
                    const galRows = Math.ceil(sorted.length / galCols);
                    const cellH = 180;
                    const cellW = Math.round(cellH * (vw / vh));
                    const galGap = 4;

                    canvasEl.width = galCols * (cellW + galGap) - galGap;
                    canvasEl.height = galRows * (cellH + galGap) - galGap;
                    const ctx = canvasEl.getContext('2d')!;
                    ctx.fillStyle = '#111';
                    ctx.fillRect(0, 0, canvasEl.width, canvasEl.height);

                    const modeIcons: Record<string, string> = {
                        playback: '▶', grid: '📊', sidebyside: '↔', filmstrip: '🎞',
                    };

                    for (let i = 0; i < galFrames.length; i++) {
                        const col = i % galCols;
                        const row = Math.floor(i / galCols);
                        const x = col * (cellW + galGap);
                        const y = row * (cellH + galGap);

                        ctx.drawImage(galFrames[i], 0, 0, vw, vh, x, y, cellW, cellH);

                        // Cyan border
                        ctx.strokeStyle = '#00ddff';
                        ctx.lineWidth = 2;
                        ctx.strokeRect(x + 1, y + 1, cellW - 2, cellH - 2);

                        // Timestamp label
                        const label = fmtDuration(sorted[i][0]);
                        ctx.font = 'bold 11px monospace';
                        ctx.textBaseline = 'top';
                        ctx.fillStyle = 'rgba(0,0,0,0.8)';
                        const tw = ctx.measureText(label).width;
                        ctx.fillRect(x + 3, y + 3, tw + 8, 16);
                        ctx.fillStyle = '#00ddff';
                        ctx.fillText(label, x + 7, y + 5);

                        // Source mode badge
                        const modes = sorted[i][1];
                        const badge = modes.map((m: ViewMode) => modeIcons[m] || m).join('');
                        ctx.font = '10px monospace';
                        ctx.textBaseline = 'bottom';
                        ctx.fillStyle = 'rgba(0,0,0,0.8)';
                        const bw = ctx.measureText(badge).width;
                        ctx.fillRect(x + cellW - bw - 10, y + cellH - 18, bw + 8, 16);
                        ctx.fillStyle = '#aaa';
                        ctx.fillText(badge, x + cellW - bw - 6, y + cellH - 4);
                    }

                    previewWidget.aspectRatio = canvasEl.width / canvasEl.height;
                    modeGeometry = null;
                    infoEl.textContent = `Selected: ${sorted.length} frames`;
                    fitNode();
                }
            }

            // ─── Helpers ──────────────────────────────────────────
            function buildInfoText(): string {
                const parts: string[] = [];
                if (videoEl.videoWidth && videoEl.videoHeight)
                    parts.push(`${videoEl.videoWidth}×${videoEl.videoHeight}`);
                const d = fmtDuration(videoEl.duration);
                if (d) parts.push(d);
                if (lastFilename) parts.push(lastFilename);
                return parts.join(' │ ') || 'Video loaded';
            }

            function fitNode(): void {
                const sz = previewWidget.computeSize?.(node.size[0]);
                if (sz) {
                    node.size[1] = sz[1] + 40;
                    node.onResize?.(node.size);
                    node.setDirtyCanvas(true, true);
                    node.graph?.setDirtyCanvas(true, true);
                }
            }

            // ─── Fetch latest video ───────────────────────────────
            let allVideos: VideoEntry[] = [];
            async function fetchLatestVideo(): Promise<void> {
                try {
                    const resp = await api.fetchApi('/loadlast/latest_video');
                    const data = await resp.json();
                    if (data.found) {
                        const entry: VideoEntry = {
                            filename: data.filename,
                            subfolder: data.subfolder || '',
                            type: data.type || 'output',
                            format: data.format || '',
                        };
                        loadVideo(entry);
                        fetchVideoList();
                    }
                } catch (e) {
                    console.warn('[LoadLast] Failed to fetch latest video:', e);
                }
            }

            function loadVideo(entry: VideoEntry): void {
                const url = viewUrl(entry);
                if (videoEl.src !== location.origin + url) {
                    videoEl.src = url;
                    lastFilename = entry.filename;
                    infoEl.textContent = `Loading ${entry.filename}...`;
                }
            }

            // ─── Video browser strip ──────────────────────────────
            async function fetchVideoList(): Promise<void> {
                try {
                    const resp = await api.fetchApi('/loadlast/video_list');
                    const data = await resp.json();
                    if (data.videos) {
                        allVideos = data.videos;
                        renderBrowserStrip();
                        updateScrollIndicator();
                    }
                } catch (e) {
                    console.warn('[LoadLast] Failed to fetch video list:', e);
                }
            }

            function renderBrowserStrip(): void {
                browserStrip.innerHTML = '';
                if (allVideos.length <= 1) {
                    stripWrapper.style.display = 'none';
                    return;
                }
                stripWrapper.style.display = 'block';

                for (const entry of allVideos) {
                    const thumb = document.createElement('div');
                    thumb.className = 'll_thumb';
                    thumb.style.cssText = 'width:80px;height:60px;';

                    const active = entry.filename === lastFilename;
                    if (active) thumb.classList.add('active');

                    const vid = document.createElement('video');
                    vid.src = viewUrl(entry);
                    vid.muted = true;
                    vid.preload = 'metadata';
                    vid.className = 'll_thumb video';
                    thumb.appendChild(vid);

                    const label = document.createElement('div');
                    label.className = 'll_thumb_label';
                    label.textContent = entry.filename;
                    label.title = entry.filename;
                    thumb.appendChild(label);

                    thumb.addEventListener('click', (e: Event) => {
                        e.stopPropagation();
                        loadVideo(entry);
                        renderBrowserStrip();
                    });
                    // Hover styles handled by CSS .ll_thumb:hover

                    browserStrip.appendChild(thumb);
                }
            }

            // ─── Video loaded handler ─────────────────────────────
            videoEl.addEventListener('loadedmetadata', () => {
                previewWidget.aspectRatio =
                    videoEl.videoWidth / videoEl.videoHeight;
                infoEl.textContent = buildInfoText();
                fitNode();
                if (currentMode !== VIEW_MODES.PLAYBACK) {
                    renderCurrentMode();
                }
                updatePlaybackMarkers();
            });

            // ─── Auto-refresh ─────────────────────────────────────
            const refreshWidget = node.widgets?.find((w: any) => w.name === 'refresh_mode');
            if (refreshWidget?.value === 'auto' || !refreshWidget) {
                fetchLatestVideo();
            }

            api.addEventListener('executed', (data: any) => {
                if (data?.detail?.output?.gifs?.length > 0) {
                    fetchLatestVideo();
                } else if (data?.detail?.output?.video?.length > 0) {
                    fetchLatestVideo();
                }
            });

            // ─── Context menu ──────────────────────────────────────
            const origGetExtra = node.constructor.prototype.getExtraMenuOptions;
            node.getExtraMenuOptions = function (_: any, options: any[]) {
                origGetExtra?.apply(this, arguments);

                const optNew: any[] = [];
                const hasVideo = !!videoEl.src && container.style.display !== 'none';

                // --- Video URL helper ---
                function getVideoUrl(): string | null {
                    return videoEl.src || null;
                }

                // --- Flash node helper ---
                function flashBg(color = '#4a5a7a'): void {
                    const orig = node.bgcolor;
                    node.bgcolor = color;
                    node.setDirtyCanvas(true, true);
                    setTimeout(() => {
                        if (node.bgcolor === color) node.bgcolor = orig;
                        node.setDirtyCanvas(true, true);
                    }, 350);
                }

                // ─── Video controls ────────────────────────────

                if (hasVideo) {
                    // Open in new tab
                    optNew.push({
                        content: '🔗 Open Preview',
                        callback: () => window.open(videoEl.src, '_blank'),
                    });

                    // Save / download
                    optNew.push({
                        content: '💾 Save Video',
                        callback: () => {
                            const a = document.createElement('a');
                            a.href = videoEl.src;
                            try {
                                const params = new URL(a.href, location.origin).searchParams;
                                a.download = params.get('filename') || 'video.mp4';
                            } catch { a.download = 'video.mp4'; }
                            document.body.append(a);
                            a.click();
                            requestAnimationFrame(() => a.remove());
                        },
                    });

                    // Pause / resume
                    optNew.push({
                        content: videoEl.paused ? '▶️ Resume' : '⏸️ Pause',
                        callback: () => {
                            if (videoEl.paused) videoEl.play().catch(() => { });
                            else videoEl.pause();
                        },
                    });

                    // Mute / unmute
                    optNew.push({
                        content: videoEl.muted ? '🔊 Unmute' : '🔇 Mute',
                        callback: () => { videoEl.muted = !videoEl.muted; },
                    });

                    // Playback speed submenu
                    optNew.push({
                        content: '⏱️ Playback Speed',
                        submenu: {
                            options: [
                                { content: '0.25x', callback: () => { videoEl.playbackRate = 0.25; flashBg('#5a5a3a'); } },
                                { content: '0.5x', callback: () => { videoEl.playbackRate = 0.5; flashBg('#5a5a3a'); } },
                                { content: '1x (Normal)', callback: () => { videoEl.playbackRate = 1.0; flashBg('#5a5a3a'); } },
                                { content: '1.5x', callback: () => { videoEl.playbackRate = 1.5; flashBg('#5a5a3a'); } },
                                { content: '2x', callback: () => { videoEl.playbackRate = 2.0; flashBg('#5a5a3a'); } },
                            ],
                        },
                    });

                    // Loop toggle
                    optNew.push({
                        content: videoEl.loop ? '🔁 Loop: ON' : '➡️ Loop: OFF',
                        callback: () => { videoEl.loop = !videoEl.loop; flashBg('#5a5a3a'); },
                    });

                    // Copy video path
                    optNew.push({
                        content: '📋 Copy Video Path',
                        callback: async () => {
                            try {
                                const params = new URL(videoEl.src, location.origin).searchParams;
                                const filename = params.get('filename') || videoEl.src;
                                await navigator.clipboard.writeText(filename);
                                flashBg('#4a7a4a');
                                infoEl.textContent = '📋 Copied!';
                                setTimeout(() => { infoEl.textContent = buildInfoText(); }, 1200);
                            } catch { flashBg('#7a4a4a'); }
                        },
                    });

                    // Screenshot current frame
                    if (videoEl.videoWidth) {
                        optNew.push({
                            content: '📸 Screenshot Frame',
                            callback: async () => {
                                try {
                                    const c = document.createElement('canvas');
                                    c.width = videoEl.videoWidth;
                                    c.height = videoEl.videoHeight;
                                    c.getContext('2d')!.drawImage(videoEl, 0, 0);
                                    const blob = await new Promise<Blob | null>(r => c.toBlob(r, 'image/png'));
                                    if (blob && navigator.clipboard?.write) {
                                        await navigator.clipboard.write([
                                            new ClipboardItem({ 'image/png': blob }),
                                        ]);
                                        flashBg('#4a7a4a');
                                        infoEl.textContent = '📸 Copied to clipboard!';
                                    } else if (blob) {
                                        const url = URL.createObjectURL(blob);
                                        const a = document.createElement('a');
                                        a.href = url; a.download = 'screenshot.png';
                                        a.click(); URL.revokeObjectURL(url);
                                        flashBg('#4a7a4a');
                                        infoEl.textContent = '📸 Saved!';
                                    }
                                    setTimeout(() => { infoEl.textContent = buildInfoText(); }, 1200);
                                } catch { flashBg('#7a4a4a'); }
                            },
                        });
                    }
                }

                // Show / hide preview
                optNew.push({
                    content: container.style.display === 'none' ? '👁️ Show Preview' : '🙈 Hide Preview',
                    callback: () => {
                        if (container.style.display === 'none') {
                            container.style.display = '';
                            if (!videoEl.paused) videoEl.play().catch(() => { });
                        } else {
                            videoEl.pause();
                            container.style.display = 'none';
                        }
                        fitNode();
                    },
                });

                // ─── Separator ──────────────────────────────
                optNew.push(null);

                // ─── Selection-specific actions ─────────────

                const totalSel = selections.totalCount();

                // Select all frames (in grid/filmstrip modes with known duration)
                if (currentMode !== VIEW_MODES.PLAYBACK && videoEl.duration > 0) {
                    optNew.push({
                        content: '✅ Select All Visible Frames',
                        callback: () => {
                            if (!modeGeometry) return;
                            const frames = modeGeometry.timestamps;
                            if (frames) {
                                for (const ts of frames) {
                                    const set = selections.get(currentMode);
                                    const key = Math.round(ts * 1000) / 1000;
                                    set.add(key);
                                }
                                updateSelectionUI();
                                renderCurrentMode();
                                flashBg('#4a7a4a');
                            }
                        },
                    });
                }

                // Clear all selections
                if (totalSel > 0) {
                    optNew.push({
                        content: `🗑️ Clear All Selections (${totalSel})`,
                        callback: () => {
                            selections.clearAll();
                            updateSelectionUI();
                            if (currentMode !== VIEW_MODES.PLAYBACK) renderCurrentMode();
                            else drawSelectionOverlay(canvasEl, modeGeometry, selections.get(currentMode));
                            flashBg('#5a4a3a');
                        },
                    });
                }

                // Copy selected timestamps
                if (totalSel > 0) {
                    optNew.push({
                        content: '📋 Copy Selected Timestamps',
                        callback: async () => {
                            const ts = selections.allTimestamps();
                            const text = ts.map(t => t.toFixed(3)).join(', ');
                            try {
                                await navigator.clipboard.writeText(text);
                                flashBg('#4a7a4a');
                                infoEl.textContent = `📋 ${ts.length} timestamps copied!`;
                                setTimeout(() => { infoEl.textContent = buildInfoText(); }, 1200);
                            } catch { flashBg('#7a4a4a'); }
                        },
                    });
                }

                // View mode quick switch submenu
                optNew.push({
                    content: '🎨 View Mode',
                    submenu: {
                        options: [
                            { content: `${currentMode === VIEW_MODES.PLAYBACK ? '● ' : ''}Playback`, callback: () => { switchMode(VIEW_MODES.PLAYBACK); } },
                            { content: `${currentMode === VIEW_MODES.GRID ? '● ' : ''}Grid`, callback: () => { switchMode(VIEW_MODES.GRID); } },
                            { content: `${currentMode === VIEW_MODES.SIDE_BY_SIDE ? '● ' : ''}Side by Side`, callback: () => { switchMode(VIEW_MODES.SIDE_BY_SIDE); } },
                            { content: `${currentMode === VIEW_MODES.FILMSTRIP ? '● ' : ''}Filmstrip`, callback: () => { switchMode(VIEW_MODES.FILMSTRIP); } },
                            { content: `${currentMode === VIEW_MODES.SELECTED ? '● ' : ''}Selected`, callback: () => { switchMode(VIEW_MODES.SELECTED); } },
                        ],
                    },
                });

                // Prepend our options before existing ones
                if (options.length > 0 && options[0] != null && optNew.length > 0) {
                    optNew.push(null);
                }
                options.unshift(...optNew);
            };

            highlightToolbar();
        };
    },
});
