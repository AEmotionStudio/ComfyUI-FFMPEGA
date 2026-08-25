/// <reference types="vitest" />
import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
    build: {
        lib: {
            entry: {
                'ffmpega_ui': resolve(__dirname, 'src/ffmpega_ui.ts'),
                'ffmpega_effects_ui': resolve(__dirname, 'src/ffmpega_effects_ui.ts'),
                'video_preview': resolve(__dirname, 'src/loadlast/video_preview.ts'),
                'image_preview': resolve(__dirname, 'src/loadlast/image_preview.ts'),
                'video_editor': resolve(__dirname, 'src/videoeditor/video_editor.ts'),
                'facepoke_ui': resolve(__dirname, 'src/nodes/facepoke_ui.ts'),
                'frame_picker_ui': resolve(__dirname, 'src/nodes/frame_picker_ui.ts'),
            },
            formats: ['es'],
            fileName: (_format, entryName) => `${entryName}.js`
        },
        outDir: 'web',
        emptyOutDir: true,
        rollupOptions: {
            external: [
                /^\/scripts\//,
                /^\.\.\/\.\.\/scripts\//,
                /^comfyui\//,
            ],
            output: {
                entryFileNames: '[name].js',
                chunkFileNames: '_chunks/[name]-[hash].js',
                paths: {
                    // Map comfyui/* TS aliases → runtime ComfyUI paths
                    'comfyui/app': '../../scripts/app.js',
                    'comfyui/api': '../../scripts/api.js',
                },
            }
        },
        sourcemap: false,
        minify: false
    },
    resolve: {
        alias: {
            '@ffmpega': resolve(__dirname, 'src'),
        }
    },
    test: {
        environment: 'happy-dom',
        globals: true,
        // `comfyui/*` is external at build time and rewritten to the host's
        // /scripts/*.js, so nothing resolves it in a test run. Point it at a
        // stub — build output is untouched.
        alias: {
            'comfyui/api': resolve(__dirname, 'src/test/comfyui_stub.ts'),
            'comfyui/app': resolve(__dirname, 'src/test/comfyui_stub.ts'),
        }
    }
});

