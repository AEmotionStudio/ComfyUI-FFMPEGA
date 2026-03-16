/**
 * video_editor.ts — Main entry point for the Video Editor extension.
 *
 * Follows the same widget patterns as frame_extract_node and video_preview:
 * - Upload + editor buttons ABOVE the preview (always visible)
 * - Preview widget with aspectRatio-based computeSize
 * - node.setSize for resize on content change
 * - All state kept in closures (no external map)
 */

import type {
    ComfyApp,
    ComfyNode,
    ComfyNodeType,
    ComfyNodeData,
    ComfyWidget,
} from '@ffmpega/types/comfyui';
import { app } from 'comfyui/app';
import { api } from 'comfyui/api';
import { addDownloadOverlay } from '@ffmpega/shared/ui_helpers';
import { EditorModal, ModalEditState } from './EditorModal';
import editorCSS from './video_editor.css?inline';

// Inject CSS at runtime — ComfyUI only auto-loads .js files from web/,
// so we must inject the stylesheet ourselves.
if (!document.querySelector('#veditor-styles')) {
    const style = document.createElement('style');
    style.id = 'veditor-styles';
    style.textContent = editorCSS;
    document.head.appendChild(style);
}

const NODE_TYPE = 'FFMPEGAVideoEditor';
const PREVIEW_ROUTE = '/ffmpega/preview';

/** Module-level singleton — shared by all VideoEditor nodes */
let _sharedModal: EditorModal | null = null;
function getModal(): EditorModal {
    if (!_sharedModal) {
        _sharedModal = new EditorModal({
            onApply: () => { },
            onCancel: () => { },
        });
    }
    return _sharedModal;
}

const PASSTHROUGH_EVENTS = [
    'contextmenu', 'pointerdown', 'mousewheel',
    'pointermove', 'pointerup',
] as const;

interface EditorNode extends ComfyNode {
    onDragOver?: (e: DragEvent) => boolean;
    onDragDrop?: (e: DragEvent) => Promise<boolean>;
    onRemoved?: () => void;
    onExecuted?: (data: any) => void;
}

interface PreviewContainer extends HTMLDivElement {
    value?: unknown;
}

app.registerExtension({
    name: 'ffmpega.videoeditor',

    beforeRegisterNodeDef(
        nodeType: ComfyNodeType,
        nodeData: ComfyNodeData,
        _app: ComfyApp,
    ) {
        if (nodeData.name !== NODE_TYPE) return;

        const origCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (this: EditorNode) {
            const result = origCreated?.apply(this, arguments as unknown as []);
            _setupNode(this);
            return result;
        };
    },
});

function _setupNode(node: EditorNode): void {
    node.color = '#2a5a4a';
    node.bgcolor = '#1a4a3a';

    // ── Ensure hidden widgets exist and are invisible ──
    _ensureHiddenWidgets(node);

    // ── Closure-scoped state ──
    let videoPath = '';
    let editState: ModalEditState = {
        segments: [],
        cropRect: '',
        speedMap: {},
        volume: 1.0,
        textOverlays: [],
        transitions: [],
        audioSegments: [],
        colorGrading: {
            brightness: 0, contrast: 1, saturation: 1, exposure: 0, gamma: 1,
            shadows_r: 0, shadows_g: 0, shadows_b: 0,
            midtones_r: 0, midtones_g: 0, midtones_b: 0,
            temperature: 6500,
        },
        filterPreset: { preset: 'none', intensity: 1.0 },
        keyframes: null,
        relight: { enabled: false, azimuth: 0, elevation: 45, intensity: 1.0, ambient: 0.3, color_r: 255, color_g: 255, color_b: 255 },
        exportSettings: { resolution: 'source', video_codec: 'h264', crf: 18, preset: 'fast', format: 'mp4', audio_codec: 'aac', audio_bitrate: '192k' },
        compose: { pip: { enabled: false }, watermark: { enabled: false }, chromakey: { enabled: false }, blend: { enabled: false }, splitScreen: { enabled: false }, vignette: { enabled: false }, mask: { enabled: false } } as any,
        aiCompose: { bg_removal: { enabled: false }, depth_effect: { enabled: false } } as any,
        transform: { enabled: false, position_x: 0, position_y: 0, scale: 100, rotation: 0, anchor_x: 50, anchor_y: 50, flip_h: false, flip_v: false, opacity: 100 },
    };

    // ── Resize helper ──
    const resizeNode = (): void => {
        node.setSize([
            node.size[0],
            node.computeSize([node.size[0], node.size[1]])[1],
        ]);
        node?.graph?.setDirtyCanvas(true);
    };

    // ════════════════════════════════════════════════════════════
    // 1. Upload Button Widget (FIRST — always visible at top)
    // ════════════════════════════════════════════════════════════

    const fileInput = document.createElement('input');
    Object.assign(fileInput, { type: 'file', accept: 'video/*', style: 'display:none' });
    document.body.append(fileInput);

    const uploadBtn = document.createElement('button');
    uploadBtn.innerHTML = 'Upload Video...';
    uploadBtn.setAttribute('aria-label', 'Upload Video');
    uploadBtn.style.cssText = `
        width: 100%;
        margin-top: 4px;
        background-color: #222;
        color: #ccc;
        border: 1px solid #333;
        border-radius: 4px;
        padding: 6px;
        cursor: pointer;
        font-family: monospace;
        font-size: 12px;
        transition: background-color 0.2s;
    `;

    let isHovered = false, isFocused = false;
    const updateBtnStyle = (): void => {
        if ((uploadBtn as any).disabled) return;
        const active = isHovered || isFocused;
        uploadBtn.style.backgroundColor = active ? '#333' : '#222';
        uploadBtn.style.outline = isFocused ? '2px solid #4a6a8a' : 'none';
    };
    uploadBtn.onmouseenter = () => { isHovered = true; updateBtnStyle(); };
    uploadBtn.onmouseleave = () => { isHovered = false; updateBtnStyle(); };
    uploadBtn.onfocus = () => { isFocused = true; updateBtnStyle(); };
    uploadBtn.onblur = () => { isFocused = false; updateBtnStyle(); };
    uploadBtn.onclick = () => fileInput.click();
    uploadBtn.onpointerdown = (e) => e.stopPropagation();

    node.addDOMWidget('upload_button', 'btn', uploadBtn, { serialize: false });

    // ════════════════════════════════════════════════════════════
    // 2. "Open Editor" Button Widget (SECOND — always visible)
    // ════════════════════════════════════════════════════════════

    const editorBtn = document.createElement('button');
    editorBtn.innerHTML = 'Open Editor';
    editorBtn.style.cssText = `
        width: 100%;
        margin-top: 2px;
        background-color: #2a4a7a;
        color: #fff;
        border: 1px solid #3a5a9b;
        border-radius: 4px;
        padding: 6px;
        cursor: pointer;
        font-family: monospace;
        font-size: 12px;
        font-weight: 600;
        transition: background-color 0.2s;
    `;
    editorBtn.onmouseenter = () => { editorBtn.style.backgroundColor = '#3a5a9b'; };
    editorBtn.onmouseleave = () => { editorBtn.style.backgroundColor = '#2a4a7a'; };
    editorBtn.onclick = () => {
        if (!videoPath) {
            infoEl.textContent = 'Load a video first';
            previewContainer.style.display = '';
            resizeNode();
            return;
        }
        const m = getModal();
        m.setCallbacks({
            onApply: (state: ModalEditState) => {
                editState = state;
                _syncToWidgets(node, state);
                infoEl.textContent = 'Edits applied';
                previewContainer.style.display = '';
                resizeNode();
                // Resume the paused workflow (only if it was actually paused)
                const pauseW = node.widgets?.find((w: ComfyWidget) => w.name === 'pause_on_input');
                if (pauseW?.value) {
                    // Reset _edit_action AFTER the prompt is serialized —
                    // queuePrompt is async so we must wait for it.
                    app.queuePrompt(0, 1).finally(() => _setW(node, '_edit_action', 'none'));
                } else {
                    _setW(node, '_edit_action', 'none');
                }
            },
            onCancel: () => { },
        });
        m.open(videoPath, editState);
    };
    editorBtn.onpointerdown = (e) => e.stopPropagation();

    node.addDOMWidget('editor_button', 'btn', editorBtn, { serialize: false });

    // ════════════════════════════════════════════════════════════
    // 3. Video Preview Widget (LAST — below buttons)
    // ════════════════════════════════════════════════════════════

    const previewContainer = document.createElement('div') as PreviewContainer;
    previewContainer.className = 'ffmpega_preview';
    previewContainer.style.cssText =
        'width:100%;background:#1a1a1a;border-radius:6px;' +
        'overflow:hidden;position:relative;display:none;';

    const videoEl = document.createElement('video');
    videoEl.controls = true;
    videoEl.loop = true;
    videoEl.muted = true;
    videoEl.volume = 1.0;
    videoEl.setAttribute('aria-label', 'Video editor preview');
    videoEl.style.cssText = 'width:100%;display:block;';

    let userUnmuted = false;
    videoEl.addEventListener('volumechange', () => { userUnmuted = !videoEl.muted; });
    videoEl.addEventListener('play', () => { if (userUnmuted) videoEl.muted = false; });
    videoEl.addEventListener('loadedmetadata', () => {
        previewWidget.aspectRatio = videoEl.videoWidth / videoEl.videoHeight;
        resizeNode();
    });
    videoEl.addEventListener('error', () => {
        previewContainer.style.display = 'none';
        infoEl.textContent = 'No video loaded';
        resizeNode();
    });

    const infoEl = document.createElement('div');
    infoEl.style.cssText =
        'padding:4px 8px;font-size:11px;color:#aaa;' +
        'font-family:monospace;background:#111;';
    infoEl.textContent = 'No video loaded';

    previewContainer.appendChild(videoEl);
    previewContainer.appendChild(infoEl);

    addDownloadOverlay(previewContainer, videoEl);

    for (const evt of PASSTHROUGH_EVENTS) {
        previewContainer.addEventListener(evt, (e: Event) => e.stopPropagation(), true);
    }

    const previewWidget = node.addDOMWidget(
        'videopreview', 'preview', previewContainer,
        {
            serialize: false,
            hideOnZoom: false,
            hint: '<kbd>1-0</kbd> Tool Tabs',
            getValue() { return previewContainer.value; },
            setValue(v: unknown) { previewContainer.value = v; },
        },
    );
    previewWidget.aspectRatio = null;
    previewWidget.computeSize = function (this: any, width: number): [number, number] {
        if (this.aspectRatio && previewContainer.style.display !== 'none') {
            const h = (node.size[0] - 20) / this.aspectRatio + 10;
            return [width, Math.max(h, 0) + 30];
        }
        return [width, -4]; // collapsed when no video
    };

    // ════════════════════════════════════════════════════════════
    // 4. Upload handler + drag-and-drop
    // ════════════════════════════════════════════════════════════

    const setUploadState = (uploading: boolean, filename = ''): void => {
        if (uploading) {
            uploadBtn.innerHTML = '⏳ Uploading...';
            (uploadBtn as any).disabled = true;
            uploadBtn.style.cursor = 'wait';
            infoEl.textContent = `Uploading ${filename}...`;
            previewContainer.style.display = '';
            videoEl.style.display = 'none';
        } else {
            uploadBtn.innerHTML = 'Upload Video...';
            (uploadBtn as any).disabled = false;
            uploadBtn.style.cursor = 'pointer';
            videoEl.style.display = 'block';
        }
        node.setDirtyCanvas(true, true);
        resizeNode();
    };

    const handleUpload = async (file: File): Promise<boolean> => {
        setUploadState(true, file.name);
        const body = new FormData();
        body.append('image', file);

        try {
            const resp = await fetch('/upload/image', { method: 'POST', body });
            if (resp.status !== 200) {
                infoEl.textContent = 'Upload failed: ' + resp.statusText;
                return false;
            }
            const data = await resp.json();
            const subfolder = (data.subfolder as string) || '';
            const inputPath = subfolder
                ? `input/${subfolder}/${data.name}`
                : `input/${data.name}`;

            const pathW = node.widgets?.find((w: ComfyWidget) => w.name === 'video_path');
            if (pathW) pathW.value = inputPath;

            loadPreview(inputPath);
            return true;
        } catch (e) {
            console.warn('[VideoEditor] Upload error:', e);
            infoEl.textContent = 'Upload error: ' + e;
            return false;
        } finally {
            setUploadState(false);
        }
    };

    fileInput.onchange = async () => {
        if (fileInput.files?.length) await handleUpload(fileInput.files[0]);
    };

    // Track drag revert timeout on the button element
    let _dragTimeout: ReturnType<typeof setTimeout> | null = null;
    let _origUploadHTML = '';
    let _origUploadBorder = '';
    let _hasDragVisual = false;

    const _revertDragVisual = (): void => {
        if (!_hasDragVisual) return;
        uploadBtn.innerHTML = _origUploadHTML;
        uploadBtn.style.border = _origUploadBorder;
        uploadBtn.style.backgroundColor = '';
        updateBtnStyle();
        _hasDragVisual = false;
    };

    node.onDragOver = (e: DragEvent): boolean => {
        if (e?.dataTransfer?.types?.includes?.('Files')) {
            if (!(uploadBtn as any).disabled) {
                if (!_hasDragVisual) {
                    _origUploadHTML = uploadBtn.innerHTML;
                    _origUploadBorder = uploadBtn.style.border;
                    _hasDragVisual = true;
                }
                uploadBtn.innerHTML = '<span aria-hidden="true">📂</span> Drop to Upload';
                uploadBtn.style.border = '1px dashed #4a6a8a';
                uploadBtn.style.backgroundColor = '#333';

                if (_dragTimeout) clearTimeout(_dragTimeout);
                _dragTimeout = setTimeout(() => {
                    if (!(uploadBtn as any).disabled) _revertDragVisual();
                }, 500);
            }
            return true;
        }
        return false;
    };
    node.onDragDrop = async (e: DragEvent): Promise<boolean> => {
        // Cancel drop visual revert — upload state handler takes over
        if (_dragTimeout) {
            clearTimeout(_dragTimeout);
            _dragTimeout = null;
        }
        _revertDragVisual();
        const file = e?.dataTransfer?.files?.[0];
        if (!file || !file.type.startsWith('video/')) return false;
        return await handleUpload(file);
    };

    // ════════════════════════════════════════════════════════════
    // 5. Cleanup
    // ════════════════════════════════════════════════════════════

    const origOnRemoved = node.onRemoved;
    node.onRemoved = function (): void {
        fileInput?.remove();
        clearInterval(pollInterval);
        origOnRemoved?.apply(this, arguments as unknown as []);
    };

    // ════════════════════════════════════════════════════════════
    // 6. Video loading + onExecuted
    // ════════════════════════════════════════════════════════════

    function loadPreview(path: string): void {
        videoPath = path;
        previewContainer.style.display = '';
        const url = api.apiURL(`${PREVIEW_ROUTE}?path=${encodeURIComponent(path)}`);
        videoEl.src = url;
        const filename = path.split('/').pop() || path;
        infoEl.textContent = filename;
    }

    const origOnExecuted = node.onExecuted;
    node.onExecuted = function (data: any): void {
        origOnExecuted?.call(node, data);

        if (data?.video_path?.[0]) {
            loadPreview(data.video_path[0]);
            resizeNode();

            const autoW = node.widgets?.find((w: ComfyWidget) => w.name === 'auto_open_editor');
            if (autoW?.value && !getModal().isOpen) {
                const m = getModal();
                m.setCallbacks({
                    onApply: (state: ModalEditState) => {
                        editState = state;
                        _syncToWidgets(node, state);
                        infoEl.textContent = 'Edits applied';
                        previewContainer.style.display = '';
                        resizeNode();
                        // Resume the paused workflow (only if it was actually paused)
                        const pauseW2 = node.widgets?.find((w: ComfyWidget) => w.name === 'pause_on_input');
                        if (pauseW2?.value) {
                            app.queuePrompt(0, 1).finally(() => _setW(node, '_edit_action', 'none'));
                        } else {
                            _setW(node, '_edit_action', 'none');
                        }
                    },
                    onCancel: () => { },
                });
                m.open(videoPath, editState);
            }
        }
    };

    // Load from widget value if already set
    const pathW = node.widgets?.find((w: ComfyWidget) => w.name === 'video_path');
    if (pathW?.value && String(pathW.value).trim()) {
        loadPreview(String(pathW.value).trim());
    }

    // Poll video_path widget for changes
    let lastPath = '';
    const pollInterval = setInterval(() => {
        if (!node.graph) { clearInterval(pollInterval); return; }
        const pw = node.widgets?.find((w: ComfyWidget) => w.name === 'video_path');
        const val = pw?.value ? String(pw.value).trim() : '';
        if (val && val !== lastPath) {
            lastPath = val;
            loadPreview(val);
        }
    }, 500);

    _loadStateFromWidgets(node, editState);
}

// ── Widget sync helpers ─────────────────────────────────────────────

function _syncToWidgets(node: ComfyNode, state: ModalEditState): void {
    _setW(node, '_edit_segments', JSON.stringify(state.segments));
    _setW(node, '_crop_rect', state.cropRect);
    _setW(node, '_speed_map', JSON.stringify(state.speedMap));
    _setW(node, '_volume', state.volume);
    _setW(node, '_text_overlays', JSON.stringify(state.textOverlays));
    _setW(node, '_transitions', JSON.stringify(state.transitions));
    _setW(node, '_audio_segments', JSON.stringify(state.audioSegments));
    _setW(node, '_color_grading', JSON.stringify(state.colorGrading));
    _setW(node, '_filter_preset', JSON.stringify(state.filterPreset));
    _setW(node, '_keyframes', JSON.stringify(state.keyframes ?? {}));
    _setW(node, '_relight_params', JSON.stringify(state.relight));
    _setW(node, '_export_settings', JSON.stringify(state.exportSettings));
    _setW(node, '_compose_layers', JSON.stringify(state.compose));
    _setW(node, '_ai_compose', JSON.stringify(state.aiCompose));
    _setW(node, '_transform', JSON.stringify(state.transform));
    _setW(node, '_edit_action', 'passthrough');
}

function _setW(node: ComfyNode, name: string, value: unknown): void {
    const w = node.widgets?.find((w: ComfyWidget) => w.name === name);
    if (w) {
        w.value = value;
    } else {
        // Fallback — store in properties (hidden widgets should exist from
        // _ensureHiddenWidgets, but guard against edge cases).
        if (!node.properties) node.properties = {};
        node.properties[name] = value;
    }
}

/** Hidden widget names and their defaults */
const HIDDEN_WIDGETS: [string, string][] = [
    ['_edit_segments', '[]'],
    ['_edit_action', 'none'],
    ['_crop_rect', ''],
    ['_speed_map', '{}'],
    ['_volume', '1.0'],
    ['_text_overlays', '[]'],
    ['_transitions', '[]'],
    ['_audio_segments', '[]'],
    ['_color_grading', '{}'],
    ['_filter_preset', '{}'],
    ['_keyframes', '{}'],
    ['_relight_params', '{}'],
    ['_export_settings', '{}'],
    ['_compose_layers', '{}'],
    ['_ai_compose', '{}'],
    ['_transform', '{}'],
];

/**
 * Ensure all hidden widgets exist on the node and are invisible.
 *
 * ComfyUI creates hidden widgets internally, but they may not always
 * be present as widget objects (depends on version/timing). This
 * function checks for each hidden widget and creates it if missing,
 * using ComfyUI's `converted-widget` type to prevent rendering.
 */
function _ensureHiddenWidgets(node: ComfyNode): void {
    for (const [name, defaultVal] of HIDDEN_WIDGETS) {
        let w = node.widgets?.find((w: ComfyWidget) => w.name === name);
        if (!w) {
            w = node.addWidget(
                'text', name, defaultVal,
                () => { /* no-op */ },
                { serialize: true },
            );
        }
        // Visually hide: collapse height AND suppress draw.
        // Don't change `type` — that breaks prompt serialization.
        w.computeSize = () => [0, -4] as [number, number];
        w.draw = () => { /* no-op: prevent LiteGraph from rendering */ };
    }
}

function _getW(node: ComfyNode, name: string, fb: string = ''): string {
    const w = node.widgets?.find((w: ComfyWidget) => w.name === name);
    if (w) return String(w.value ?? fb);
    return String(node.properties?.[name] ?? fb);
}

function _loadStateFromWidgets(node: ComfyNode, editState: ModalEditState): void {
    try { const s = JSON.parse(_getW(node, '_edit_segments', '[]')); if (Array.isArray(s)) editState.segments = s; } catch { }
    try { const m = JSON.parse(_getW(node, '_speed_map', '{}')); if (typeof m === 'object') editState.speedMap = m; } catch { }
    try { const v = parseFloat(_getW(node, '_volume', '1.0')); if (!isNaN(v)) editState.volume = v; } catch { }
    try { const o = JSON.parse(_getW(node, '_text_overlays', '[]')); if (Array.isArray(o)) editState.textOverlays = o; } catch { }
    editState.cropRect = _getW(node, '_crop_rect', '');
    try { const t = JSON.parse(_getW(node, '_transitions', '[]')); if (Array.isArray(t)) editState.transitions = t; } catch { }
    try { const a = JSON.parse(_getW(node, '_audio_segments', '[]')); if (Array.isArray(a)) editState.audioSegments = a; } catch { }
    try { const c = JSON.parse(_getW(node, '_color_grading', '{}')); if (typeof c === 'object' && c !== null) editState.colorGrading = c; } catch { }
    try { const f = JSON.parse(_getW(node, '_filter_preset', '{}')); if (typeof f === 'object' && f !== null) editState.filterPreset = f; } catch { }
    try { const k = JSON.parse(_getW(node, '_keyframes', '{}')); if (typeof k === 'object' && k !== null && k.keyframes) editState.keyframes = k; } catch { }
    try { const r = JSON.parse(_getW(node, '_relight_params', '{}')); if (typeof r === 'object' && r !== null) editState.relight = r; } catch { }
    try { const e = JSON.parse(_getW(node, '_export_settings', '{}')); if (typeof e === 'object' && e !== null) editState.exportSettings = e; } catch { }
    try { const c = JSON.parse(_getW(node, '_compose_layers', '{}')); if (typeof c === 'object' && c !== null) editState.compose = c; } catch { }
    try { const ai = JSON.parse(_getW(node, '_ai_compose', '{}')); if (typeof ai === 'object' && ai !== null) editState.aiCompose = ai; } catch { }
    try { const tr = JSON.parse(_getW(node, '_transform', '{}')); if (typeof tr === 'object' && tr !== null) editState.transform = tr; } catch { }
}
