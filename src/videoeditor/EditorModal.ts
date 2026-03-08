/**
 * EditorModal — full-viewport NLE-style modal overlay for the Video Editor.
 *
 * Layout (CSS Grid):
 *   header   | header
 *   monitor  | tools (tabbed)
 *   transport | tools
 *   toolbar  | toolbar
 *   timeline | timeline
 *
 * Agent-friendly: every interactive element exposes data-tool-id,
 * aria-label, and title attributes for AI agent discoverability.
 */

import { EditManager } from '@ffmpega/loadlast/editing/EditManager';
import { EditTimeline } from '@ffmpega/loadlast/editing/EditTimeline';
import { TransportBar } from './TransportBar';
import { CropOverlay, CropRect } from './CropOverlay';
import { SpeedControl } from './SpeedControl';
import { AudioMixer } from './AudioMixer';
import { TextOverlayPanel, TextOverlay } from './TextOverlayPanel';
import { iconClapperboard, iconUndo, iconRedo, iconCheck, iconClose, iconCrop, iconGauge, iconVolume, iconText, iconShuffle } from './icons';
import { UndoManager, EditorState } from './UndoManager';
import { ToolsPanel } from './ToolsPanel';
import { EditToolbar, ToolMode } from './EditToolbar';
import { NLETimeline } from './NLETimeline';
import { MonitorCanvas } from './MonitorCanvas';
import { ShortcutOverlay } from './ShortcutOverlay';
import { TransitionEditor } from './TransitionEditor';

const INFO_ROUTE = '/ffmpega/video_info';
const PREVIEW_ROUTE = '/ffmpega/preview';

/** State bundle passed to/from the modal */
export interface ModalEditState {
    segments: number[][];
    cropRect: string;
    speedMap: Record<string, number>;
    volume: number;
    textOverlays: TextOverlay[];
    transitions: unknown[];
}

export interface EditorModalCallbacks {
    /** Called when user clicks Apply — edits should be persisted */
    onApply: (state: ModalEditState) => void;
    /** Called when user clicks Cancel or ESC */
    onCancel: () => void;
}

export class EditorModal {
    private dialog: HTMLDivElement;
    private panel: HTMLDivElement;
    private video: HTMLVideoElement;
    private editManager: EditManager;
    private nleTimeline: NLETimeline | null = null;
    private transport: TransportBar;
    private cropOverlay: CropOverlay;
    private speedControl: SpeedControl;
    private audioMixer: AudioMixer;
    private textPanel: TextOverlayPanel;
    private undoManager: UndoManager;
    private toolsPanel: ToolsPanel;
    private editToolbar: EditToolbar;
    private monitorCanvas: MonitorCanvas;
    private shortcutOverlay: ShortcutOverlay;
    private transitionEditor: TransitionEditor;
    private callbacks: EditorModalCallbacks;
    private videoPath: string = '';
    private _escHandler: ((e: KeyboardEvent) => void) | null = null;
    private _isOpen = false;
    private _currentToolMode: ToolMode = 'select';
    private _userDragging: boolean = false;

    constructor(callbacks: EditorModalCallbacks) {
        this.callbacks = callbacks;

        // ── Remove any stale backdrop left by a previous instance ──
        document.querySelectorAll('.veditor-modal-backdrop').forEach((d) => d.remove());

        // ── Backdrop div (position: fixed, hidden by default) ──
        this.dialog = document.createElement('div');
        this.dialog.className = 'veditor-modal-backdrop';
        this.dialog.style.display = 'none';
        this.dialog.setAttribute('data-tool-id', 'veditor-modal');
        this.dialog.setAttribute('aria-label', 'Video Editor');
        this.dialog.setAttribute('role', 'dialog');
        this.dialog.setAttribute('aria-modal', 'true');
        this.dialog.addEventListener('click', (e) => {
            // Only close if clicking the backdrop itself, not the panel or its children
            if (e.target === this.dialog) this._cancel();
        });

        // ── Panel (CSS Grid) ──
        this.panel = document.createElement('div');
        this.panel.className = 'veditor-modal-panel';
        this.panel.setAttribute('data-tool-id', 'veditor-panel');

        // ═══════════════════════════════════════════════════════════
        // HEADER
        // ═══════════════════════════════════════════════════════════
        const header = document.createElement('div');
        header.className = 'veditor-modal-header';

        const titleWrap = document.createElement('div');
        titleWrap.style.display = 'flex';
        titleWrap.style.alignItems = 'center';
        titleWrap.style.gap = '8px';

        const title = document.createElement('h2');
        title.className = 'veditor-modal-title';
        title.innerHTML = `<span class="veditor-modal-title-icon">${iconClapperboard}</span> Video Editor`;

        titleWrap.appendChild(title);

        const shortcuts = document.createElement('div');
        shortcuts.className = 'veditor-header-shortcuts';
        shortcuts.innerHTML = [
            '<kbd>Space</kbd> Play',
            '<kbd>S</kbd> Split',
            '<kbd>V</kbd> Select',
            '<kbd>C</kbd> Razor',
            '<kbd>1-5</kbd> Tool Tabs',
            '<kbd>?</kbd> Shortcuts',
        ].join('  ·  ');

        const headerActions = document.createElement('div');
        headerActions.className = 'veditor-header-actions';

        const undoBtn = document.createElement('button');
        undoBtn.className = 'veditor-btn veditor-btn-sm';
        undoBtn.innerHTML = `${iconUndo} Undo`;
        undoBtn.title = 'Undo (Ctrl+Z)';
        undoBtn.setAttribute('data-tool-id', 'veditor-undo');
        undoBtn.setAttribute('aria-label', 'Undo last edit (Ctrl+Z)');
        undoBtn.addEventListener('click', () => this.undoManager.undo());

        const redoBtn = document.createElement('button');
        redoBtn.className = 'veditor-btn veditor-btn-sm';
        redoBtn.innerHTML = `${iconRedo} Redo`;
        redoBtn.title = 'Redo (Ctrl+Shift+Z)';
        redoBtn.setAttribute('data-tool-id', 'veditor-redo');
        redoBtn.setAttribute('aria-label', 'Redo last edit (Ctrl+Shift+Z)');
        redoBtn.addEventListener('click', () => this.undoManager.redo());

        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'veditor-btn veditor-btn-sm';
        cancelBtn.textContent = 'Cancel';
        cancelBtn.title = 'Cancel editing (ESC)';
        cancelBtn.setAttribute('data-tool-id', 'veditor-cancel');
        cancelBtn.setAttribute('aria-label', 'Cancel editing and close (ESC)');
        cancelBtn.addEventListener('click', () => this._cancel());

        const applyBtn = document.createElement('button');
        applyBtn.className = 'veditor-btn veditor-btn-sm veditor-btn-primary';
        applyBtn.innerHTML = `${iconCheck} Apply Edits`;
        applyBtn.title = 'Apply edits and continue workflow';
        applyBtn.setAttribute('data-tool-id', 'veditor-apply');
        applyBtn.setAttribute('aria-label', 'Apply all edits and continue workflow');
        applyBtn.addEventListener('click', () => this._apply());

        const closeBtn = document.createElement('button');
        closeBtn.className = 'veditor-modal-close';
        closeBtn.innerHTML = iconClose;
        closeBtn.title = 'Close (ESC)';
        closeBtn.setAttribute('data-tool-id', 'veditor-close');
        closeBtn.setAttribute('aria-label', 'Close editor without saving (ESC)');
        closeBtn.addEventListener('click', () => this._cancel());

        headerActions.append(undoBtn, redoBtn, cancelBtn, applyBtn, closeBtn);
        header.append(titleWrap, shortcuts, headerActions);

        // ═══════════════════════════════════════════════════════════
        // MONITOR (Infinite Canvas)
        // ═══════════════════════════════════════════════════════════
        this.video = document.createElement('video');
        this.video.controls = false;
        this.video.muted = false;
        this.video.preload = 'auto';
        this.video.setAttribute('data-tool-id', 'veditor-video');
        this.video.setAttribute('aria-label', 'Video preview');

        this.monitorCanvas = new MonitorCanvas(this.video);
        const monitor = this.monitorCanvas.element;
        monitor.setAttribute('data-tool-id', 'veditor-monitor');
        monitor.setAttribute('aria-label', 'Video preview monitor — scroll to zoom, middle-drag to pan, F to fit, 1 for 100%');

        // ═══════════════════════════════════════════════════════════
        // TRANSPORT
        // ═══════════════════════════════════════════════════════════
        const transportWrap = document.createElement('div');
        transportWrap.className = 'veditor-modal-transport';

        this.editManager = new EditManager();

        this.transport = new TransportBar({
            onTimeUpdate: (time) => {
                if (!this._userDragging) {
                    this.nleTimeline?.setPlayhead(time);
                }
            },
            onPlayStateChange: () => { },
        });
        this.transport.setEditManager(this.editManager);
        this.transport.bindVideo(this.video);
        transportWrap.appendChild(this.transport.element);

        // ═══════════════════════════════════════════════════════════
        // TOOLS PANEL (tabbed sidebar)
        // ═══════════════════════════════════════════════════════════
        this.cropOverlay = new CropOverlay({
            onCropChanged: () => this._pushUndo(),
        });

        this.speedControl = new SpeedControl({
            onSpeedChanged: () => this._pushUndo(),
        });

        this.audioMixer = new AudioMixer({
            onVolumeChanged: (vol) => {
                this.video.volume = Math.min(1, vol);
            },
        });

        this.textPanel = new TextOverlayPanel({
            onOverlaysChanged: () => this._pushUndo(),
        });

        this.transitionEditor = new TransitionEditor(this.editManager, {
            onTransitionsChanged: () => this._pushUndo(),
        });

        this.toolsPanel = new ToolsPanel([
            { id: 'crop', label: 'Crop', icon: iconCrop, content: this.cropOverlay.element },
            { id: 'speed', label: 'Speed', icon: iconGauge, content: this.speedControl.element },
            { id: 'audio', label: 'Audio', icon: iconVolume, content: this.audioMixer.element },
            { id: 'text', label: 'Text', icon: iconText, content: this.textPanel.element },
            { id: 'transitions', label: 'Trans', icon: iconShuffle, content: this.transitionEditor.element },
        ]);

        // Mount crop canvas overlay on the monitor content (zoom/pans with video)
        this.monitorCanvas.contentElement.appendChild(this.cropOverlay.canvasElement);

        // ═══════════════════════════════════════════════════════════
        // EDIT TOOLBAR
        // ═══════════════════════════════════════════════════════════
        this.editToolbar = new EditToolbar({
            onToolChanged: (mode) => {
                this._currentToolMode = mode;
            },
            onSplitRequested: () => {
                const playhead = this.nleTimeline?.timeline.playhead ?? 0;
                if (this.editManager.splitAt(playhead)) {
                    this._pushUndo();
                    this.nleTimeline?.render();
                }
            },
            onDeleteRequested: () => {
                if (this.editManager.segments.length > 1) {
                    const playhead = this.nleTimeline?.timeline.playhead ?? 0;
                    const hitSeg = this.editManager.segments.find(
                        (s) => playhead >= s.start && playhead <= s.end,
                    );
                    if (hitSeg) {
                        this.editManager.removeSegment(hitSeg.id);
                        this._pushUndo();
                        this.nleTimeline?.render();
                    }
                }
            },
            onResetRequested: () => {
                this.editManager.reset();
                this._pushUndo();
                this.nleTimeline?.render();
            },
        });

        // ═══════════════════════════════════════════════════════════
        // TIMELINE SLOT
        // ═══════════════════════════════════════════════════════════
        const timelineSlot = document.createElement('div');
        timelineSlot.className = 'veditor-modal-timeline';
        timelineSlot.id = 'veditor-timeline-slot';
        timelineSlot.setAttribute('data-tool-id', 'veditor-timeline-area');
        timelineSlot.setAttribute('aria-label', 'Timeline editing area');

        // ═══════════════════════════════════════════════════════════
        // UNDO MANAGER
        // ═══════════════════════════════════════════════════════════
        this.undoManager = new UndoManager({
            onRestore: (state) => this._restoreState(state),
        });

        // ═══════════════════════════════════════════════════════════
        // ASSEMBLE (CSS Grid will position everything)
        // ═══════════════════════════════════════════════════════════
        this.panel.append(
            header,
            monitor,
            transportWrap,
            this.toolsPanel.element,
            this.editToolbar.element,
            timelineSlot,
        );

        // Shortcut overlay (mounted on the backdrop, above everything)
        this.shortcutOverlay = new ShortcutOverlay();
        this.dialog.appendChild(this.shortcutOverlay.element);

        this.dialog.appendChild(this.panel);
        document.body.appendChild(this.dialog);
    }

    /** Open the modal with a video path and optional initial state */
    async open(videoPath: string, initialState?: ModalEditState): Promise<void> {
        if (this._isOpen) return;
        this._isOpen = true;
        this.videoPath = videoPath;

        // Load initial state
        if (initialState) {
            this.speedControl.loadSpeedMap(initialState.speedMap);
            this.audioMixer.setVolume(initialState.volume);
            this.textPanel.loadOverlays(initialState.textOverlays);
            try {
                const crop = JSON.parse(initialState.cropRect);
                if (crop && crop.w && crop.h) this.cropOverlay.setRect(crop);
            } catch { /* ignore */ }
        }

        // Fetch video info
        try {
            const resp = await fetch(`${INFO_ROUTE}?path=${encodeURIComponent(videoPath)}`);
            if (resp.ok) {
                const info = await resp.json();
                this.editManager.init(info.duration || 1);
                this.cropOverlay.setVideoDimensions(info.width || 640, info.height || 480);

                // Load segments from initial state
                if (initialState && initialState.segments.length > 0) {
                    this.editManager.segments = initialState.segments.map(
                        ([start, end], i) => ({
                            id: `restored_${i}`,
                            start,
                            end,
                        }),
                    );
                }
            }
        } catch (e) {
            console.warn('[VideoEditor] Failed to fetch video info:', e);
        }

        // Load video preview
        this.video.src = `${PREVIEW_ROUTE}?path=${encodeURIComponent(videoPath)}`;
        this.video.load();

        // Show modal
        this.dialog.style.display = 'flex';

        // Fit to view once video dimensions are known
        this.video.addEventListener('loadeddata', () => {
            this.monitorCanvas.fitToView();
        }, { once: true });

        // Build NLE timeline after DOM insertion (needs layout)
        requestAnimationFrame(() => {
            const slot = this.panel.querySelector('#veditor-timeline-slot');
            if (slot) {
                this.nleTimeline = new NLETimeline(this.editManager, {
                    onSegmentsChanged: () => {
                        this._pushUndo();
                        this.transitionEditor.refresh();
                    },
                    onPlayheadChanged: (time) => this.transport.seekTo(time),
                    onTrimHandleDrag: (time) => this.transport.seekTo(time),
                    onRequestSplit: () => { },
                    onDragStart: () => {
                        this._userDragging = true;
                        this.video.pause();
                    },
                    onDragEnd: () => {
                        this._userDragging = false;
                    },
                });
                slot.innerHTML = '';
                slot.appendChild(this.nleTimeline.element);
                this.nleTimeline.render();
            }
        });

        // ── Keyboard handler ──
        this._escHandler = (e: KeyboardEvent) => {
            // Skip if typing in an input
            if (
                e.target instanceof HTMLInputElement ||
                e.target instanceof HTMLTextAreaElement
            ) {
                return;
            }

            // ESC → cancel
            if (e.key === 'Escape') {
                this._cancel();
                return;
            }

            // Ctrl+Z / Ctrl+Shift+Z → undo/redo
            if (e.ctrlKey && e.key === 'z' && !e.shiftKey) {
                e.preventDefault();
                this.undoManager.undo();
                return;
            }
            if (e.ctrlKey && e.key === 'z' && e.shiftKey) {
                e.preventDefault();
                this.undoManager.redo();
                return;
            }

            // Number keys → tab switch
            const num = parseInt(e.key, 10);
            if (num >= 1 && num <= 5 && !e.ctrlKey && !e.altKey) {
                if (this.toolsPanel.handleNumberKey(num)) {
                    e.preventDefault();
                    return;
                }
            }

            // Shortcut overlay (? or H)
            if (this.shortcutOverlay.handleKey(e.key)) {
                e.preventDefault();
                return;
            }

            // Monitor canvas shortcuts (F = fit to view)
            if (this.monitorCanvas.handleKey(e.key)) {
                e.preventDefault();
                return;
            }

            // Toolbar shortcuts (V, C, S, Delete/Backspace)
            if (this.editToolbar.handleKey(e.key)) {
                e.preventDefault();
                return;
            }
        };
        document.addEventListener('keydown', this._escHandler);

        // Push initial undo state
        this.undoManager.push(this._getState());
    }

    /** Update callbacks — used by singleton pattern so different nodes can
     *  set their own onApply/onCancel before opening the shared modal. */
    setCallbacks(callbacks: EditorModalCallbacks): void {
        this.callbacks = callbacks;
    }

    /** Close the modal without applying */
    close(): void {
        if (!this._isOpen) return;
        this._isOpen = false;

        this.video.pause();
        this.video.src = '';

        if (this.nleTimeline) {
            this.nleTimeline.destroy();
            this.nleTimeline = null;
        }

        if (this._escHandler) {
            document.removeEventListener('keydown', this._escHandler);
            this._escHandler = null;
        }

        this.dialog.style.display = 'none';
    }

    get isOpen(): boolean {
        return this._isOpen;
    }

    // ── Private ──────────────────────────────────────────────────────

    private _getState(): EditorState {
        return {
            segments: this.editManager.toJSON(),
            cropRect: JSON.stringify(this.cropOverlay.getRect() ?? {}),
            speedMap: this.speedControl.getSpeedMap(),
            volume: this.audioMixer.getVolume(),
            textOverlays: this.textPanel.getOverlays(),
            transitions: [],
        };
    }

    private _pushUndo(): void {
        this.undoManager.push(this._getState());
    }

    private _restoreState(state: EditorState): void {
        // Segments
        this.editManager.segments = state.segments.map(([start, end], i) => ({
            id: `restored_${i}`,
            start,
            end,
        }));
        this.nleTimeline?.render();

        // Crop
        try {
            const crop = JSON.parse(state.cropRect);
            if (crop && crop.w && crop.h) {
                this.cropOverlay.setRect(crop as CropRect);
            } else {
                this.cropOverlay.setRect(null);
            }
        } catch {
            this.cropOverlay.setRect(null);
        }

        // Speed
        this.speedControl.loadSpeedMap(state.speedMap);

        // Volume
        this.audioMixer.setVolume(state.volume);

        // Text
        this.textPanel.loadOverlays(state.textOverlays as TextOverlay[]);
    }

    private _apply(): void {
        const state: ModalEditState = {
            segments: this.editManager.toJSON(),
            cropRect: JSON.stringify(this.cropOverlay.getRect() ?? {}),
            speedMap: this.speedControl.getSpeedMap(),
            volume: this.audioMixer.getVolume(),
            textOverlays: this.textPanel.getOverlays() as TextOverlay[],
            transitions: [],
        };
        this.close();
        this.callbacks.onApply(state);
    }

    private _cancel(): void {
        this.close();
        this.callbacks.onCancel();
    }
}
