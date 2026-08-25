/**
 * Stand-in for ComfyUI's `/scripts/api.js` and `/scripts/app.js` under vitest.
 *
 * Those live in the host application, not in node_modules — the build leaves
 * the imports external and rewrites them to runtime paths, but a test run has
 * to resolve them for real. Aliased in `vite.config.ts` under `test` only, so
 * the shipped bundles are unaffected.
 *
 * This exists so a module can be imported for its pure helpers without
 * dragging in the host. It is deliberately minimal: anything that needs the
 * real API belongs in a browser check, not a unit test.
 */

export const api = {
    apiURL: (route: string): string => `/api${route}`,
    fetchApi: (): Promise<Response> => Promise.reject(new Error("api.fetchApi is not available in tests")),
    addEventListener: (): void => { /* no-op */ },
    removeEventListener: (): void => { /* no-op */ },
};

export const app = {
    graph: undefined as unknown,
    canvas: undefined as unknown,
    registerExtension: (): void => { /* no-op */ },
};
