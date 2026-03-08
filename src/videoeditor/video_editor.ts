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
    node.color = '#2a4a5a';
    node.bgcolor = '#1a3a4a';

    // ── Closure-scoped state ──
    let videoPath = '';
    let editState: ModalEditState = {
        segments: [],
        cropRect: '',
        speedMap: {},
        volume: 1.0,
        textOverlays: [],
        transitions: [],
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

    node.onDragOver = (e: DragEvent): boolean => {
        if (e?.dataTransfer?.types?.includes?.('Files')) return true;
        return false;
    };
    node.onDragDrop = async (e: DragEvent): Promise<boolean> => {
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
            if (autoW?.value === true && !getModal().isOpen) {
                const m = getModal();
                m.setCallbacks({
                    onApply: (state: ModalEditState) => {
                        editState = state;
                        _syncToWidgets(node, state);
                        infoEl.textContent = 'Edits applied';
                        previewContainer.style.display = '';
                        resizeNode();
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
    _setW(node, '_edit_action', 'passthrough');
}

function _setW(node: ComfyNode, name: string, value: unknown): void {
    const w = node.widgets?.find((w: ComfyWidget) => w.name === name);
    if (w) w.value = value;
    else { if (!node.properties) node.properties = {}; node.properties[name] = value; }
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
}
