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
import { ColorGradingPanel, ColorGradingState } from './ColorGradingPanel';
import { FiltersPanel, FilterPresetState } from './FiltersPanel';
import { KeyframeTrackJSON } from './KeyframeTrack';
import { RelightPanel, RelightState } from './RelightPanel';
import { ExportSettingsPanel, ExportSettings } from './ExportSettingsPanel';
import { ComposePanel, ComposeState } from './ComposePanel';
import { AIComposePanel, AIComposeState } from './AIComposePanel';
import { TransformPanel, TransformState } from './TransformPanel';
import { iconClapperboard, iconUndo, iconRedo, iconCheck, iconClose, iconCrop, iconGauge, iconVolume, iconText, iconShuffle, iconPalette, iconWand, iconSun, iconSettings, iconLayers, iconBrain, iconMove } from './icons';
import { UndoManager, EditorState } from './UndoManager';
import { ToolsPanel } from './ToolsPanel';
import { EditToolbar, ToolMode } from './EditToolbar';
import { NLETimeline } from './NLETimeline';
import { MonitorCanvas } from './MonitorCanvas';
import { ShortcutOverlay } from './ShortcutOverlay';
import { TransitionEditor } from './TransitionEditor';
import { TextPreviewOverlay } from './TextPreviewOverlay';
import { TransitionPreview } from './TransitionPreview';
import { AudioEditManager } from './AudioSegment';
import { AudioTimeline } from './AudioTimeline';
import { extractWaveform } from './WaveformExtractor';

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
    audioSegments: object[];
    colorGrading: ColorGradingState;
    filterPreset: FilterPresetState;
    keyframes: KeyframeTrackJSON | null;
    relight: RelightState;
    exportSettings: ExportSettings;
    compose: ComposeState;
    aiCompose: AIComposeState;
    transform: TransformState;
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
    private audioEditManager: AudioEditManager;
    private audioTimeline: AudioTimeline | null = null;
    private transport: TransportBar;
    private cropOverlay: CropOverlay;
    private speedControl: SpeedControl;
    private audioMixer: AudioMixer;
    private textPanel: TextOverlayPanel;
    private colorGradingPanel: ColorGradingPanel;
    private filtersPanel: FiltersPanel;
    private relightPanel: RelightPanel;
    private exportSettingsPanel: ExportSettingsPanel;
    private composePanel: ComposePanel;
    private aiComposePanel: AIComposePanel;
    private transformPanel: TransformPanel;
    private undoManager: UndoManager;
    private toolsPanel: ToolsPanel;
    private editToolbar: EditToolbar;
    private monitorCanvas: MonitorCanvas;
    private shortcutOverlay: ShortcutOverlay;
    private transitionEditor: TransitionEditor;
    private textPreview: TextPreviewOverlay;
    private transitionPreview: TransitionPreview;
    private callbacks: EditorModalCallbacks;
    private videoPath: string = '';
    private _escHandler: ((e: KeyboardEvent) => void) | null = null;
    private _timeupdateHandler: (() => void) | null = null;
    private _textPreviewTimer: ReturnType<typeof setTimeout> | null = null;
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
            '<kbd>1-0</kbd> Tool Tabs',
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
                    this.nleTimeline?.scrollToTime(time);
                }
            },
            onPlayStateChange: () => { },
        });
        this.transport.setEditManager(this.editManager);
        this.transport.bindVideo(this.video);
        transportWrap.appendChild(this.transport.element);

        // Transition preview
        this.transitionPreview = new TransitionPreview();
        this.transitionPreview.bind(this.video);
        this.transport.setTransitionPreview(this.transitionPreview);

        // ═══════════════════════════════════════════════════════════
        // TOOLS PANEL (tabbed sidebar)
        // ═══════════════════════════════════════════════════════════
        this.cropOverlay = new CropOverlay({
            onCropChanged: () => this._pushUndo(),
            onPreviewChanged: (clipPath) => this.transitionPreview.setBaseClipPath(clipPath),
        });
        this.cropOverlay.bindVideo(this.video);

        this.speedControl = new SpeedControl({
            onSpeedChanged: (_segIdx, speed) => {
                this._pushUndo();
                // Live preview: update video playback rate
                this.transport.setPlaybackRate(speed);
            },
        });

        this.audioEditManager = new AudioEditManager();
        this.transport.setAudioEditManager(this.audioEditManager);

        this.audioMixer = new AudioMixer({
            onVolumeChanged: (vol) => {
                const idx = this.audioMixer.selectedSegmentIndex;
                if (idx >= 0 && this.audioEditManager.segments[idx]) {
                    this.audioEditManager.segments[idx].volume = vol;
                    this.audioEditManager.segments[idx].muted = vol < 0.01;
                    this.audioTimeline?.render();
                }
                // Live volume is enforced by TransportBar's rAF loop
                // via AudioEditManager.getVolumeAtTime() — no need to set here.
                this._pushUndo();
            },
            onFadeInChanged: (sec) => {
                const idx = this.audioMixer.selectedSegmentIndex;
                if (idx >= 0 && this.audioEditManager.segments[idx]) {
                    this.audioEditManager.segments[idx].fadeIn = sec;
                    this.audioTimeline?.render();
                }
                this._pushUndo();
            },
            onFadeOutChanged: (sec) => {
                const idx = this.audioMixer.selectedSegmentIndex;
                if (idx >= 0 && this.audioEditManager.segments[idx]) {
                    this.audioEditManager.segments[idx].fadeOut = sec;
                    this.audioTimeline?.render();
                }
                this._pushUndo();
            },
            onEQChanged: (preset) => {
                const idx = this.audioMixer.selectedSegmentIndex;
                if (idx >= 0 && this.audioEditManager.segments[idx]) {
                    this.audioEditManager.segments[idx].eq = preset;
                    this.audioTimeline?.render();
                }
                this._pushUndo();
            },
        });

        this.textPreview = new TextPreviewOverlay({
            onTextDragged: (index, x, y) => {
                const overlays = this.textPanel.getOverlays();
                if (overlays[index]) {
                    overlays[index].x = x;
                    overlays[index].y = y;
                    this.textPanel.loadOverlays(overlays);
                    this._pushUndo();
                    this._refreshTextPreview();
                }
            },
            onTextSelected: (index) => {
                this.textPreview.setSelectedIndex(index);
            },
        });

        this.textPanel = new TextOverlayPanel({
            onOverlaysChanged: () => {
                this._pushUndo();
                this._refreshTextPreview();
            },
            getVideoPath: () => this.videoPath,
        });

        this.transitionEditor = new TransitionEditor(this.editManager, {
            onTransitionsChanged: () => {
                this._pushUndo();
                this.transport.setTransitions(this.transitionEditor.transitions);
            },
        });

        this.colorGradingPanel = new ColorGradingPanel({
            onGradingChanged: () => {
                this._pushUndo();
                this._applyCSSPreview();
            },
        });

        this.filtersPanel = new FiltersPanel({
            onFilterChanged: () => {
                this._pushUndo();
                this._applyCSSPreview();
            },
        });

        this.relightPanel = new RelightPanel({
            onRelightChanged: () => {
                this._pushUndo();
            },
        });

        this.exportSettingsPanel = new ExportSettingsPanel({
            onSettingsChanged: () => {
                this._pushUndo();
            },
        });

        this.composePanel = new ComposePanel({
            onComposeChanged: () => {
                this._pushUndo();
            },
        });

        this.aiComposePanel = new AIComposePanel({
            onAIComposeChanged: () => {
                this._pushUndo();
            },
        });

        this.transformPanel = new TransformPanel({
            onTransformChanged: () => {
                this._pushUndo();
            },
        });

        this.toolsPanel = new ToolsPanel([
            {
                label: 'EDIT',
                tabs: [
                    { id: 'crop', label: 'Crop', icon: iconCrop, content: this.cropOverlay.element },
                    { id: 'speed', label: 'Speed', icon: iconGauge, content: this.speedControl.element },
                    { id: 'audio', label: 'Audio', icon: iconVolume, content: this.audioMixer.element },
                    { id: 'text', label: 'Text', icon: iconText, content: this.textPanel.element },
                    { id: 'transitions', label: 'Trans', icon: iconShuffle, content: this.transitionEditor.element },
                ],
            },
            {
                label: 'FX',
                tabs: [
                    { id: 'color', label: 'Color', icon: iconPalette, content: this.colorGradingPanel.element },
                    { id: 'filters', label: 'Filters', icon: iconWand, content: this.filtersPanel.element },
                    { id: 'relight', label: 'Relight', icon: iconSun, content: this.relightPanel.element },
                    { id: 'export', label: 'Export', icon: iconSettings, content: this.exportSettingsPanel.element },
                ],
            },
            {
                label: 'COMPOSE',
                tabs: [
                    { id: 'compose', label: 'Compose', icon: iconLayers, content: this.composePanel.element },
                    { id: 'ai', label: 'AI', icon: iconBrain, content: this.aiComposePanel.element },
                    { id: 'transform', label: 'Xform', icon: iconMove, content: this.transformPanel.element },
                ],
            },
        ]);

        // Mount crop canvas and text preview overlays on the monitor content
        this.monitorCanvas.contentElement.appendChild(this.cropOverlay.canvasElement);
        this.monitorCanvas.contentElement.appendChild(this.textPreview.element);

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
                this.audioEditManager.reset();
                this.audioMixer.clearSegmentSelection();
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
            this.audioMixer.setMasterVolume(initialState.volume);
            this.textPanel.loadOverlays(initialState.textOverlays);
            if (initialState.colorGrading) {
                this.colorGradingPanel.loadState(initialState.colorGrading);
            }
            if (initialState.filterPreset) {
                this.filtersPanel.loadState(initialState.filterPreset);
            }
            if (initialState.keyframes) {
                this.speedControl.loadKeyframeData(initialState.keyframes);
            }
            if (initialState.relight) {
                this.relightPanel.loadState(initialState.relight);
            }
            if (initialState.exportSettings) {
                this.exportSettingsPanel.loadState(initialState.exportSettings);
            }
            if (initialState.compose) {
                this.composePanel.loadState(initialState.compose);
            }
            if (initialState.aiCompose) {
                this.aiComposePanel.loadState(initialState.aiCompose);
            }
            if (initialState.transform) {
                this.transformPanel.loadState(initialState.transform);
            }
            this._applyCSSPreview();
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
                this.audioEditManager.init(info.duration || 1);
                this.cropOverlay.setVideoDimensions(info.width || 640, info.height || 480);
                this.textPreview.setVideoDimensions(info.width || 640, info.height || 480);

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

                // Load audio segments from initial state (after init() so we
                // don't overwrite saved per-segment volume/fade/EQ/mute data)
                if (initialState && initialState.audioSegments && initialState.audioSegments.length > 0) {
                    this.audioEditManager.fromJSON(initialState.audioSegments as object[]);
                }
            }
        } catch (e) {
            console.warn('[VideoEditor] Failed to fetch video info:', e);
        }

        // Load video preview
        this.video.src = `${PREVIEW_ROUTE}?path=${encodeURIComponent(videoPath)}`;
        this.video.load();

        // Restore overlays hidden by previous close()
        this.textPreview.show();

        // Show modal
        this.dialog.style.display = 'flex';

        // Fit to view once video dimensions are known
        this.video.addEventListener('loadeddata', () => {
            this.monitorCanvas.fitToView();
        }, { once: true });

        // Live text preview: debounced refresh on time updates for time-gating.
        // timeupdate fires ~4Hz; debouncing to 200ms avoids rebuilding the DOM
        // on every event while still keeping the preview responsive.
        this._timeupdateHandler = () => {
            if (this._textPreviewTimer) return;
            this._textPreviewTimer = setTimeout(() => {
                this._textPreviewTimer = null;
                this._refreshTextPreview();
            }, 200);
        };
        this.video.addEventListener('timeupdate', this._timeupdateHandler);

        // Live audio volume is handled in TransportBar's ~60Hz rAF loop
        // via setAudioEditManager() for smooth fades and gap muting.

        // Build NLE timeline after DOM insertion (needs layout)
        requestAnimationFrame(() => {
            const slot = this.panel.querySelector('#veditor-timeline-slot');
            if (slot) {
                this.nleTimeline = new NLETimeline(this.editManager, {
                    onSegmentsChanged: () => {
                        // Linked splitting: mirror video edits to audio
                        if (this.audioEditManager.linked) {
                            this._syncAudioToVideo();
                        }
                        this._pushUndo();
                        this.transitionEditor.refresh();
                        this.audioTimeline?.render();
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

                // Create and mount AudioTimeline
                this.audioTimeline = new AudioTimeline(this.audioEditManager, {
                    onAudioSegmentsChanged: () => {
                        this._pushUndo();
                    },
                    onAudioSegmentSelected: (index) => {
                        const seg = this.audioEditManager.segments[index];
                        if (seg) {
                            this.audioMixer.loadSegment(seg, index);
                            this.audioTimeline?.setSelectedIndex(index);
                            // Switch to audio tab
                            this.toolsPanel.activateTab('audio');
                        }
                    },
                    onPlayheadChanged: (time) => this.transport.seekTo(time),
                });
                this.nleTimeline.setAudioTimeline(this.audioTimeline);

                // Fetch waveform in background (server-side first, client fallback)
                const videoUrl = `${PREVIEW_ROUTE}?path=${encodeURIComponent(this.videoPath)}`;
                extractWaveform(this.videoPath, videoUrl).then(wf => {
                    this.audioTimeline?.setWaveform(wf.peaks);
                }).catch(e => {
                    console.warn('[VideoEditor] Waveform extraction failed:', e);
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

            // Number keys → tab switch (1-9, 0 for tab 10)
            const num = parseInt(e.key, 10);
            if (!isNaN(num) && !e.ctrlKey && !e.altKey) {
                const tabNum = num === 0 ? 10 : num;
                if (this.toolsPanel.handleNumberKey(tabNum)) {
                    e.preventDefault();
                    return;
                }
            }

            // Extended tab shortcuts: - for tab 11, = for tab 12
            if ((e.key === '-' || e.key === '=') && !e.ctrlKey && !e.altKey) {
                const tabNum = e.key === '-' ? 11 : 12;
                if (this.toolsPanel.handleNumberKey(tabNum)) {
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

            // Toolbar shortcuts (V, S, Delete/Backspace)
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
        this.video.style.filter = 'none';  // Reset CSS preview filter

        if (this.nleTimeline) {
            this.nleTimeline.destroy();
            this.nleTimeline = null;
        }

        if (this.audioTimeline) {
            this.audioTimeline.destroy();
            this.audioTimeline = null;
        }

        this.textPreview.hide();
        this.transitionPreview.clear();

        if (this._timeupdateHandler) {
            this.video.removeEventListener('timeupdate', this._timeupdateHandler);
            this._timeupdateHandler = null;
        }
        if (this._textPreviewTimer) {
            clearTimeout(this._textPreviewTimer);
            this._textPreviewTimer = null;
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
            // Master volume — applied globally by the FFmpeg export pipeline.
            // Per-segment volumes live independently in `audioSegments` below
            // and are used for live preview only (FFmpeg rendering not yet implemented).
            volume: this.audioMixer.getMasterVolume(),
            textOverlays: this.textPanel.getOverlays(),
            transitions: [],
            audioSegments: this.audioEditManager.toJSON(),
            colorGrading: this.colorGradingPanel.getState(),
            filterPreset: this.filtersPanel.getState(),
            keyframes: this.speedControl.getKeyframeData() ?? null,
            relight: this.relightPanel.getState(),
            exportSettings: this.exportSettingsPanel.getState(),
            compose: this.composePanel.getState(),
            aiCompose: this.aiComposePanel.getState(),
            transform: this.transformPanel.getState(),
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
        this.audioMixer.setMasterVolume(state.volume);

        // Audio segments
        if (state.audioSegments && Array.isArray(state.audioSegments) && state.audioSegments.length > 0) {
            this.audioEditManager.fromJSON(state.audioSegments as object[]);
            this.audioMixer.clearSegmentSelection();
            this.audioTimeline?.setSelectedIndex(-1);
            this.audioTimeline?.render();
        }

        // Text
        this.textPanel.loadOverlays(state.textOverlays as TextOverlay[]);
        this._refreshTextPreview();

        // Color grading
        if (state.colorGrading) {
            this.colorGradingPanel.loadState(state.colorGrading);
        }

        // Filter preset
        if (state.filterPreset) {
            this.filtersPanel.loadState(state.filterPreset as FilterPresetState);
        }

        this._applyCSSPreview();

        // Keyframes
        if (state.keyframes) {
            this.speedControl.loadKeyframeData(state.keyframes as any);
        }

        // Relight
        if (state.relight) {
            this.relightPanel.loadState(state.relight as RelightState);
        }

        // Export settings
        if (state.exportSettings) {
            this.exportSettingsPanel.loadState(state.exportSettings as ExportSettings);
        }

        // Compose
        if (state.compose) {
            this.composePanel.loadState(state.compose as ComposeState);
        }

        // AI Compose
        if (state.aiCompose) {
            this.aiComposePanel.loadState(state.aiCompose as AIComposeState);
        }

        // Transform
        if (state.transform) {
            this.transformPanel.loadState(state.transform as TransformState);
        }
    }

    /**
     * Combine CSS filter approximations from color grading and filter preset
     * into a single style.filter on the video element for live preview.
     */
    private _applyCSSPreview(): void {
        const parts: string[] = [];
        const gradingCSS = this.colorGradingPanel.getCSSFilter();
        if (gradingCSS && gradingCSS !== 'none') parts.push(gradingCSS);
        const filterCSS = this.filtersPanel.getCSSFilter();
        if (filterCSS && filterCSS !== 'none') parts.push(filterCSS);
        this.video.style.filter = parts.length > 0 ? parts.join(' ') : 'none';
    }

    /** Sync audio segments to match video segments (linked mode) */
    private _syncAudioToVideo(): void {
        const videoSegs = this.editManager.segments;
        const audioMgr = this.audioEditManager;

        // Rebuild audio segments to match video segment boundaries
        // Preserve audio properties for overlapping regions
        const newAudioSegs = videoSegs.map(vSeg => {
            // Find existing audio segment that best overlaps this video segment
            const existing = audioMgr.segments.find(
                a => a.start < vSeg.end && a.end > vSeg.start,
            );
            return audioMgr.createSegment(vSeg.start, vSeg.end, existing ? {
                volume: existing.volume,
                fadeIn: existing.fadeIn,
                fadeOut: existing.fadeOut,
                eq: existing.eq,
                muted: existing.muted,
            } : undefined);
        });
        audioMgr.replaceAll(newAudioSegs);
        this.audioTimeline?.render();
    }

    private _refreshTextPreview(): void {
        const overlays = this.textPanel.getOverlays();
        const currentTime = this.video.currentTime;
        this.textPreview.refresh(overlays, currentTime);
    }

    private _apply(): void {
        const state: ModalEditState = {
            segments: this.editManager.toJSON(),
            cropRect: JSON.stringify(this.cropOverlay.getRect() ?? {}),
            speedMap: this.speedControl.getSpeedMap(),
            volume: this.audioMixer.getMasterVolume(),
            textOverlays: this.textPanel.getOverlays() as TextOverlay[],
            transitions: [],
            audioSegments: this.audioEditManager.toJSON(),
            colorGrading: this.colorGradingPanel.getState(),
            filterPreset: this.filtersPanel.getState(),
            keyframes: this.speedControl.getKeyframeData() ?? null,
            relight: this.relightPanel.getState(),
            exportSettings: this.exportSettingsPanel.getState(),
            compose: this.composePanel.getState(),
            aiCompose: this.aiComposePanel.getState(),
            transform: this.transformPanel.getState(),
        };
        this.close();
        this.callbacks.onApply(state);
    }

    private _cancel(): void {
        this.close();
        this.callbacks.onCancel();
    }
}
