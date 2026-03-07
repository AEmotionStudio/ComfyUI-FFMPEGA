/**
 * Type declarations for ComfyUI script imports.
 *
 * These modules are provided by ComfyUI at runtime and are external to our build.
 * The relative paths (../../scripts/*) are resolved by Vite at build time
 * and by TypeScript via tsconfig paths.
 */

declare module 'comfyui/app' {
    interface ComfyApp {
        graph: any;
        canvas: any;
        ui: any;
        extensionManager: any;
        registerExtension(extension: any): void;
    }
    export const app: ComfyApp;
}

declare module 'comfyui/api' {
    interface ComfyAPI {
        fetchApi(url: string, options?: RequestInit): Promise<Response>;
        apiURL(url: string): string;
        addEventListener(event: string, callback: (data: any) => void): void;
    }
    export const api: ComfyAPI;
}

// CSS inline imports (Vite)
declare module '*.css?inline' {
    const content: string;
    export default content;
}
