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
                'contact_sheet': resolve(__dirname, 'src/loadlast/contact_sheet.ts'),
                'video_editor': resolve(__dirname, 'src/videoeditor/video_editor.ts'),
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
        globals: true
    }
});

