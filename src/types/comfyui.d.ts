/**
 * ComfyUI Type Definitions
 *
 * Type definitions for ComfyUI's app, canvas, and graph APIs.
 * Based on ComfyUI runtime behavior. Adapted from ComfyUI-LoadLast.
 */

// ============================================================================
// ComfyUI App
// ============================================================================

export interface ComfyApp {
    graph: ComfyGraph;
    canvas: ComfyCanvas;
    ui: ComfyUI;
    extensionManager: ComfyExtensionManager;
    registerExtension(extension: ComfyExtension): void;
}

export interface ComfyExtension {
    name: string;
    setup?: () => Promise<void> | void;
    init?: () => Promise<void> | void;
    beforeRegisterNodeDef?: (
        nodeType: ComfyNodeType,
        nodeData: ComfyNodeData,
        app: ComfyApp,
    ) => void;
}

export interface ComfyNodeType {
    prototype: ComfyNodePrototype;
}

export interface ComfyNodePrototype {
    onNodeCreated?: () => unknown;
    onExecuted?: (data: any) => void;
    getExtraMenuOptions?: (canvas: unknown, options: ComfyMenuOption[]) => void;
    _ffmpegaOrigGetExtraMenu?: (canvas: unknown, options: ComfyMenuOption[]) => void;
    color?: string;
    bgcolor?: string;
    [key: string]: unknown;
}

export interface ComfyNodeData {
    name: string;
    [key: string]: unknown;
}

// ============================================================================
// ComfyUI UI
// ============================================================================

export interface ComfyUI {
    settings: ComfySettings;
}

export interface ComfySettings {
    addSetting(setting: ComfySetting): void;
    getSettingValue(id: string): unknown;
    setSettingValue(id: string, value: unknown): void;
}

export interface ComfySetting {
    id: string;
    name: string;
    type: 'text' | 'number' | 'slider' | 'combo' | 'color' | 'boolean';
    defaultValue: unknown;
    min?: number;
    max?: number;
    step?: number;
    options?: Array<{ value: unknown; text: string }>;
    tooltip?: string;
    onChange?: (value: unknown) => void;
}

// ============================================================================
// ComfyUI Extension Manager
// ============================================================================

export interface ComfyExtensionManager {
    setting: {
        get(id: string): unknown;
        set(id: string, value: unknown): void;
    };
}

// ============================================================================
// ComfyUI Graph & Nodes
// ============================================================================

export interface ComfyGraph {
    _nodes: ComfyNode[];
    getNodeById(id: number): ComfyNode | null;
    setDirtyCanvas(fg: boolean, bg?: boolean): void;
}

export interface ComfyNode {
    id: number;
    title: string;
    type: string;
    mode: number;
    pos: [number, number];
    size: [number, number];
    color?: string;
    bgcolor?: string;
    flags?: {
        collapsed?: boolean;
    };
    graph?: ComfyGraph;
    widgets?: ComfyWidget[];
    inputs: ComfySlot[];
    outputs?: ComfySlot[];
    properties?: Record<string, unknown>;
    addWidget(
        type: string,
        name: string,
        value: unknown,
        callback?: (value: unknown) => void,
        options?: Record<string, unknown>,
    ): ComfyWidget;
    addDOMWidget(
        name: string,
        type: string,
        element: HTMLElement,
        options?: Record<string, unknown>,
    ): ComfyWidget;
    addInput(name: string, type: string): void;
    removeInput(slot: number): void;
    setSize(size: [number, number]): void;
    setDirtyCanvas(fg: boolean, bg: boolean): void;
    computeSize(size?: [number, number]): [number, number];
    getExtraMenuOptions?: (canvas: unknown, options: ComfyMenuOption[]) => void;
    onConnectionsChange?: (
        type: number,
        slotIndex: number,
        isConnected: boolean,
        link: unknown,
        ioSlot: unknown,
    ) => void;
    onConfigure?: (info: ComfyNodeSerializedInfo) => void;
    // internal state
    _isFlashing?: boolean;
    _previousPrompt?: string;
}

export interface ComfyWidget {
    name: string;
    type: string;
    value: unknown;
    options?: Record<string, unknown>;
    min?: number;
    max?: number;
    step?: number;
    element?: HTMLElement;
    hidden?: boolean;
    callback?: (...args: any[]) => void;
    computeSize?: (width: number) => [number, number];
    draw?: (ctx: CanvasRenderingContext2D, node: ComfyNode, width: number, y: number, height: number) => void;
    getValue?: () => unknown;
    setValue?: (value: unknown) => void;
    aspectRatio?: number | null;
    // Internal state for toggle pattern
    _origType?: string;
    _origComputeSize?: (width: number) => [number, number];
}

export interface ComfySlot {
    name: string;
    type: string;
    link?: number | null;
    links?: number[];
}

export interface ComfyNodeSerializedInfo {
    inputs?: Array<{ name: string; type: string; link?: number | null }>;
    [key: string]: unknown;
}

// ============================================================================
// ComfyUI Canvas
// ============================================================================

export interface ComfyCanvas {
    canvas: HTMLCanvasElement;
    ds: {
        scale: number;
        offset: [number, number];
    };
    node_over: ComfyNode | null;
}

// ============================================================================
// ComfyUI API
// ============================================================================

export interface ComfyAPI {
    fetchApi(url: string, options?: RequestInit): Promise<Response>;
    apiURL(url: string): string;
    addEventListener(event: string, callback: (data: unknown) => void): void;
}

// ============================================================================
// Menu
// ============================================================================

export interface ComfyMenuOption {
    content: string;
    callback?: () => void;
    submenu?: {
        options: ComfyMenuOption[];
    };
}

// ============================================================================
// LiteGraph global
// ============================================================================

declare global {
    // eslint-disable-next-line no-var
    var app: ComfyApp;
    // eslint-disable-next-line no-var
    var LiteGraph: {
        INPUT: number;
        OUTPUT: number;
    };
}

export { };
