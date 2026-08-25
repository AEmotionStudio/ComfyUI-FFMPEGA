/**
 * FacePoke UI — Node-level widget + modal editor integration.
 *
 * The node shows: Upload button → Video preview → "Open Editor" button.
 * Clicking "Open Editor" opens the FacePokeModal for full-screen editing.
 *
 * Matches the Video Editor node pattern:
 * - Upstream inputs always win over uploaded video
 * - Upload via button or drag-and-drop
 * - Video preview with aspect-ratio scaling
 * - Apply Edits → re-queue via _edit_action widget
 */

import type {
    ComfyApp,
    ComfyNode,
    ComfyNodeType,
    ComfyNodeData,
    ComfyWidget,
} from "@ffmpega/types/comfyui";
import { app } from "comfyui/app";
import { api } from "comfyui/api";
import { FacePokeModal, type AllEdits } from "../facepoke/FacePokeModal";
import facepokeCSS from "../facepoke/facepoke.css?inline";

// Inject CSS at runtime — ComfyUI only auto-loads .js files from web/,
// so we must inject the stylesheet ourselves (same pattern as Video Editor).
if (!document.querySelector('#fpoke-styles')) {
    const style = document.createElement('style');
    style.id = 'fpoke-styles';
    style.textContent = facepokeCSS;
    document.head.appendChild(style);
}

const NODE_TYPE = "FFMPEGAFacePoke";
const PREVIEW_ROUTE = "/ffmpega/preview";

const PASSTHROUGH_EVENTS = [
    "contextmenu", "pointerdown", "mousewheel",
    "pointermove", "pointerup",
] as const;

interface FacePokeNode extends ComfyNode {
    onDragOver?: (e: DragEvent) => boolean;
    onDragDrop?: (e: DragEvent) => Promise<boolean>;
    onRemoved?: () => void;
    onExecuted?: (data: any) => void;
}

// ── Shared singleton modal ──────────────────────────────────

let _sharedModal: FacePokeModal | null = null;
function getModal(): FacePokeModal {
    if (!_sharedModal) {
        _sharedModal = new FacePokeModal({
            onApply: () => {},
            onCancel: () => {},
        });
    }
    return _sharedModal;
}

// ── Registration ────────────────────────────────────────────

app.registerExtension({
    name: "ffmpega.facepoke",

    beforeRegisterNodeDef(
        nodeType: ComfyNodeType,
        nodeData: ComfyNodeData,
        _app: ComfyApp,
    ) {
        if (nodeData.name !== NODE_TYPE) return;

        const origCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function (this: FacePokeNode) {
            const result = origCreated?.apply(this, arguments as unknown as []);
            _setupNode(this);
            return result;
        };
    },
});

// ── Node Setup ──────────────────────────────────────────────

function _setupNode(node: FacePokeNode): void {
    node.color = "#2a3a5a";
    node.bgcolor = "#1a2a4a";

    // Ensure hidden widgets
    _ensureHiddenWidgets(node);

    // ── Closure state ──
    let currentVideoPath = "";
    let lastEdits: AllEdits = {};

    const resizeNode = (): void => {
        node.setSize([
            node.size[0],
            node.computeSize([node.size[0], node.size[1]])[1],
        ]);
        node?.graph?.setDirtyCanvas(true);
    };

    // ════════════════════════════════════════════════════════════
    // 1. Upload Button
    // ════════════════════════════════════════════════════════════

    const fileInput = document.createElement("input");
    Object.assign(fileInput, { type: "file", accept: "video/*", style: "display:none" });
    document.body.append(fileInput);

    const uploadBtn = document.createElement("button");
    uploadBtn.innerHTML = "Upload Video...";
    uploadBtn.setAttribute("aria-label", "Upload Video");
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
        uploadBtn.style.backgroundColor = active ? "#333" : "#222";
        uploadBtn.style.outline = isFocused ? "2px solid #4a6a8a" : "none";
    };
    uploadBtn.onmouseenter = () => { isHovered = true; updateBtnStyle(); };
    uploadBtn.onmouseleave = () => { isHovered = false; updateBtnStyle(); };
    uploadBtn.onfocus = () => { isFocused = true; updateBtnStyle(); };
    uploadBtn.onblur = () => { isFocused = false; updateBtnStyle(); };
    uploadBtn.onclick = () => fileInput.click();
    uploadBtn.onpointerdown = (e) => e.stopPropagation();

    node.addDOMWidget("upload_button", "btn", uploadBtn, { serialize: false });

    // ════════════════════════════════════════════════════════════
    // 2. Video Preview
    // ════════════════════════════════════════════════════════════

    const previewContainer = document.createElement("div");
    previewContainer.className = "ffmpega_preview";
    previewContainer.style.cssText =
        "width:100%;background:#1a1a1a;border-radius:6px;" +
        "overflow:hidden;position:relative;display:none;";

    const videoEl = document.createElement("video");
    videoEl.controls = true;
    videoEl.loop = true;
    videoEl.muted = true;
    videoEl.volume = 1.0;
    videoEl.setAttribute("aria-label", "FacePoke video preview");
    videoEl.style.cssText = "width:100%;display:block;";

    let userUnmuted = false;
    videoEl.addEventListener("volumechange", () => { userUnmuted = !videoEl.muted; });
    videoEl.addEventListener("play", () => { if (userUnmuted) videoEl.muted = false; });
    videoEl.addEventListener("loadedmetadata", () => {
        previewWidget.aspectRatio = videoEl.videoWidth / videoEl.videoHeight;
        resizeNode();
    });
    videoEl.addEventListener("error", () => {
        previewContainer.style.display = "none";
        infoEl.textContent = "No video loaded";
        resizeNode();
    });

    const infoEl = document.createElement("div");
    infoEl.style.cssText =
        "padding:4px 8px;font-size:11px;color:#aaa;" +
        "font-family:monospace;background:#111;";
    infoEl.textContent = "No video loaded";

    previewContainer.appendChild(videoEl);
    previewContainer.appendChild(infoEl);

    for (const evt of PASSTHROUGH_EVENTS) {
        previewContainer.addEventListener(evt, (e: Event) => e.stopPropagation(), true);
    }

    const previewWidget = node.addDOMWidget(
        "videopreview", "preview", previewContainer,
        {
            serialize: false,
            hideOnZoom: false,
            getValue() { return (previewContainer as any).value; },
            setValue(v: unknown) { (previewContainer as any).value = v; },
        },
    );
    previewWidget.aspectRatio = null;
    previewWidget.computeSize = function (this: any, width: number): [number, number] {
        if (this.aspectRatio && previewContainer.style.display !== "none") {
            const h = (node.size[0] - 20) / this.aspectRatio + 10;
            return [width, Math.max(h, 0) + 30];
        }
        return [width, -4];
    };

    // ════════════════════════════════════════════════════════════
    // 3. "Open Editor" Button
    // ════════════════════════════════════════════════════════════

    const editorBtn = document.createElement("button");
    editorBtn.innerHTML = "🎭 Open Face Editor";
    editorBtn.setAttribute("aria-label", "Open Face Poke Editor");
    editorBtn.style.cssText = `
        width: 100%;
        margin-top: 4px;
        background: linear-gradient(135deg, #2a3a5a, #1a2a4a);
        color: #e8e8f0;
        border: 1px solid #4a6a8a;
        border-radius: 4px;
        padding: 8px;
        cursor: pointer;
        font-family: 'Inter', system-ui, sans-serif;
        font-size: 13px;
        font-weight: 600;
        transition: all 0.2s;
    `;
    editorBtn.onmouseenter = () => {
        editorBtn.style.background = "linear-gradient(135deg, #3a4a6a, #2a3a5a)";
        editorBtn.style.borderColor = "#6a8aaa";
    };
    editorBtn.onmouseleave = () => {
        editorBtn.style.background = "linear-gradient(135deg, #2a3a5a, #1a2a4a)";
        editorBtn.style.borderColor = "#4a6a8a";
    };
    editorBtn.onpointerdown = (e) => e.stopPropagation();
    editorBtn.onclick = () => {
        if (!currentVideoPath) {
            console.warn("[FacePoke] No video path set — upload or connect a video first");
            infoEl.textContent = "⚠ No video loaded — upload or connect one first";
            infoEl.style.color = "#ef4444";
            setTimeout(() => { infoEl.style.color = "#aaa"; }, 3000);
            return;
        }
        console.log("[FacePoke] Opening editor with path:", currentVideoPath);
        openEditor();
    };

    node.addDOMWidget("editor_button", "btn", editorBtn, { serialize: false });

    // ════════════════════════════════════════════════════════════
    // 4. Upload + Drag-and-Drop
    // ════════════════════════════════════════════════════════════

    const setUploadState = (uploading: boolean, filename = ""): void => {
        if (uploading) {
            uploadBtn.innerHTML = "⏳ Uploading...";
            (uploadBtn as any).disabled = true;
            uploadBtn.style.cursor = "wait";
            infoEl.textContent = `Uploading ${filename}...`;
            previewContainer.style.display = "";
            videoEl.style.display = "none";
        } else {
            uploadBtn.innerHTML = "Upload Video...";
            (uploadBtn as any).disabled = false;
            uploadBtn.style.cursor = "pointer";
            videoEl.style.display = "block";
        }
        node.setDirtyCanvas(true, true);
        resizeNode();
    };

    const handleUpload = async (file: File): Promise<boolean> => {
        setUploadState(true, file.name);
        const body = new FormData();
        body.append("image", file);

        try {
            const resp = await fetch("/upload/image", { method: "POST", body });
            if (resp.status !== 200) {
                infoEl.textContent = "Upload failed: " + resp.statusText;
                return false;
            }
            const data = await resp.json();
            const subfolder = (data.subfolder as string) || "";
            const inputPath = subfolder
                ? `input/${subfolder}/${data.name}`
                : `input/${data.name}`;

            const pathW = node.widgets?.find((w: ComfyWidget) => w.name === "video_path");
            if (pathW) pathW.value = inputPath;

            loadPreview(inputPath);
            return true;
        } catch (e) {
            console.warn("[FacePoke] Upload error:", e);
            infoEl.textContent = "Upload error: " + e;
            return false;
        } finally {
            setUploadState(false);
        }
    };

    fileInput.onchange = async () => {
        if (fileInput.files?.length) await handleUpload(fileInput.files[0]);
    };

    // Drag & drop
    let _dragTimeout: ReturnType<typeof setTimeout> | null = null;
    let _origHTML = "", _origBorder = "", _hasDrag = false;

    const _revertDrag = (): void => {
        if (!_hasDrag) return;
        uploadBtn.innerHTML = _origHTML;
        uploadBtn.style.border = _origBorder;
        uploadBtn.style.backgroundColor = "";
        updateBtnStyle();
        _hasDrag = false;
    };

    node.onDragOver = (e: DragEvent): boolean => {
        if (e?.dataTransfer?.types?.includes?.("Files")) {
            if (!(uploadBtn as any).disabled) {
                if (!_hasDrag) { _origHTML = uploadBtn.innerHTML; _origBorder = uploadBtn.style.border; _hasDrag = true; }
                uploadBtn.innerHTML = '<span aria-hidden="true">📂</span> Drop to Upload';
                uploadBtn.style.border = "1px dashed #4a6a8a";
                uploadBtn.style.backgroundColor = "#333";
                if (_dragTimeout) clearTimeout(_dragTimeout);
                _dragTimeout = setTimeout(() => { if (!(uploadBtn as any).disabled) _revertDrag(); }, 500);
            }
            return true;
        }
        return false;
    };

    node.onDragDrop = async (e: DragEvent): Promise<boolean> => {
        if (_dragTimeout) { clearTimeout(_dragTimeout); _dragTimeout = null; }
        _revertDrag();
        const file = e?.dataTransfer?.files?.[0];
        if (!file || !file.type.startsWith("video/")) return false;
        return await handleUpload(file);
    };

    // ════════════════════════════════════════════════════════════
    // 5. Video loading + onExecuted
    // ════════════════════════════════════════════════════════════

    function loadPreview(path: string): void {
        currentVideoPath = path;
        previewContainer.style.display = "";
        const url = api.apiURL(`${PREVIEW_ROUTE}?path=${encodeURIComponent(path)}`);
        videoEl.src = url;
        const filename = path.split("/").pop() || path;
        infoEl.textContent = filename;
    }

    const origOnExecuted = node.onExecuted;
    node.onExecuted = function (data: any): void {
        origOnExecuted?.call(node, data);

        // Show video preview from output
        if (data?.video_path?.[0]) {
            loadPreview(data.video_path[0]);
            resizeNode();
        }

        // Auto-open editor when paused (facepoke_meta present)
        if (data?.facepoke_meta?.[0]) {
            const fpMeta = data.facepoke_meta[0];
            currentVideoPath = fpMeta.video_path;
            loadPreview(fpMeta.video_path);
            resizeNode();

            // Parse existing edits
            try {
                lastEdits = fpMeta.edit_data ? JSON.parse(fpMeta.edit_data) : {};
            } catch {
                lastEdits = {};
            }

            // Check auto_open_editor widget (like Video Editor)
            const autoW = node.widgets?.find((w: ComfyWidget) => w.name === "auto_open_editor");
            if (autoW?.value && !getModal().isOpen) {
                console.log("[FacePoke] Auto-opening editor (workflow paused)");
                openEditor();
            }
        }
    };

    // ════════════════════════════════════════════════════════════
    // 6. Open Editor (modal)
    // ════════════════════════════════════════════════════════════

    function openEditor(): void {
        const modal = getModal();
        const nodeId = String(node.id);

        modal.setCallbacks({
            onApply: async (edits: AllEdits) => {
                lastEdits = edits;

                if (Object.keys(edits).length === 0) {
                    // Pass through — no edits
                    _setW(node, "_edit_action", "passthrough");
                    app.queuePrompt(0, 1).finally(() => _setW(node, "_edit_action", "none"));
                    return;
                }

                // Store server-side edits
                try {
                    await api.fetchApi("/facepoke/apply_edits", {
                        method: "POST",
                        body: JSON.stringify({ node_id: nodeId, edits }),
                    });
                } catch (e) {
                    console.error("[FacePoke] Failed to store edits:", e);
                }

                // Re-queue
                _setW(node, "_edit_action", "apply");
                app.queuePrompt(0, 1).finally(() => _setW(node, "_edit_action", "none"));
            },
            onCancel: () => {
                // Do nothing — user dismissed without changes
            },
        });

        modal.open(currentVideoPath, lastEdits);
    }

    // Poll video_path widget for upstream changes
    let lastPolledPath = "";
    const pollInterval = setInterval(() => {
        if (!node.graph) { clearInterval(pollInterval); return; }
        const pw = node.widgets?.find((w: ComfyWidget) => w.name === "video_path");
        const val = pw?.value ? String(pw.value).trim() : "";
        if (val && val !== lastPolledPath) {
            lastPolledPath = val;
            loadPreview(val);
        }
    }, 500);

    // Load from widget value if already set at creation
    const pathW = node.widgets?.find((w: ComfyWidget) => w.name === "video_path");
    if (pathW?.value && String(pathW.value).trim()) {
        loadPreview(String(pathW.value).trim());
    }

    // ════════════════════════════════════════════════════════════
    // 7. Cleanup
    // ════════════════════════════════════════════════════════════

    const origOnRemoved = node.onRemoved;
    node.onRemoved = function (): void {
        fileInput?.remove();
        clearInterval(pollInterval);
        origOnRemoved?.apply(this, arguments as unknown as []);
    };
}

// ── Widget helpers ──────────────────────────────────────────

function _setW(node: ComfyNode, name: string, value: unknown): void {
    const w = node.widgets?.find((w: ComfyWidget) => w.name === name);
    if (w) {
        w.value = value;
    } else {
        if (!node.properties) node.properties = {};
        node.properties[name] = value;
    }
}

const HIDDEN_WIDGETS: [string, string][] = [
    ["_edit_action", "none"],
];

function _ensureHiddenWidgets(node: ComfyNode): void {
    for (const [name, defaultVal] of HIDDEN_WIDGETS) {
        let w = node.widgets?.find((w: ComfyWidget) => w.name === name);
        if (!w) {
            w = node.addWidget(
                "text", name, defaultVal,
                () => { /* no-op */ },
                { serialize: true },
            );
        }
        w.computeSize = () => [0, -4] as [number, number];
        w.draw = () => { /* hidden */ };
    }
}
