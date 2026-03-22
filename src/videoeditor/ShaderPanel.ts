/**
 * ShaderPanel — GPU shader preset selector for the NLE Video Editor.
 *
 * Displays a grid of shader preset cards with color-coded swatches,
 * an intensity slider (0–100%), and shader info tooltips.
 *
 * Follows the same pattern as FiltersPanel.ts:
 * - `element` getter returns the root div
 * - Callbacks fire on selection changes
 * - State is serializable via `getState()` / `loadState()`
 */

import { iconShuffle } from './icons';

export interface ShaderPresetState {
    preset: string;     // preset key or "none"
    intensity: number;  // 0–1
    enable_vda: boolean;     // VDA depth toggle
    enable_normals: boolean; // NormalCrafter toggle
    depth_encoder: string;   // "vits" | "vitb" | "vitl"
    depth_strength: number;  // 0–1
}

export interface ShaderCallbacks {
    onShaderChanged: (state: ShaderPresetState) => void;
}

interface ShaderDef {
    key: string;
    label: string;
    description: string;
    /** CSS approximation for the swatch preview. */
    css: string;
    /** Accent color for the swatch border when selected. */
    color: string;
}

const SHADERS: ShaderDef[] = [
    {
        key: 'none', label: 'None', description: 'No shader effect',
        css: 'none', color: '#888',
    },
    {
        key: 'crt', label: 'CRT', description: 'Scanlines + barrel distortion',
        css: 'contrast(1.2) brightness(0.9)', color: '#22c55e',
    },
    {
        key: 'vhs', label: 'VHS', description: 'Analog tape distortion + color bleed',
        css: 'saturate(0.7) sepia(0.15) blur(0.5px)', color: '#d4a574',
    },
    {
        key: 'holographic', label: 'Holographic', description: 'Iridescent rainbow shift',
        css: 'saturate(1.5) hue-rotate(30deg) brightness(1.1)', color: '#c084fc',
    },
    {
        key: 'glitch', label: 'Glitch', description: 'RGB channel split + displacement',
        css: 'contrast(1.3) saturate(1.2)', color: '#ef4444',
    },
    {
        key: 'voronoi', label: 'Voronoi', description: 'Cell/toon edge shading',
        css: 'contrast(1.5) saturate(0.8)', color: '#f97316',
    },
    {
        key: 'water_ripple', label: 'Water Ripple', description: 'Animated water distortion',
        css: 'brightness(1.05) saturate(1.1)', color: '#3b82f6',
    },
    {
        key: 'night_vision', label: 'Night Vision', description: 'Green phosphor + noise',
        css: 'saturate(0) brightness(1.3) sepia(0.3) hue-rotate(70deg)', color: '#4ade80',
    },
    {
        key: 'force_field', label: 'Force Field', description: 'Energy barrier glow on edges',
        css: 'brightness(1.1) saturate(1.8) contrast(1.2)', color: '#06b6d4',
    },
    {
        key: 'plasma_burn', label: 'Plasma Burn', description: 'Animated plasma field overlay',
        css: 'saturate(1.5) hue-rotate(40deg) brightness(1.1)', color: '#f97316',
    },
    {
        key: 'shockwave', label: 'Shockwave', description: 'Expanding ring distortion',
        css: 'brightness(1.15) contrast(1.1)', color: '#60a5fa',
    },
    {
        key: 'datamosh', label: 'Datamosh', description: 'I-frame corruption glitch art',
        css: 'contrast(1.4) saturate(1.1)', color: '#ef4444',
    },
    {
        key: 'crystal', label: 'Crystal', description: 'Faceted diamond refraction',
        css: 'brightness(1.1) contrast(1.2) saturate(1.1)', color: '#e2e8f0',
    },
    {
        key: 'aurora', label: 'Aurora', description: 'Northern lights ribbons',
        css: 'brightness(0.95) saturate(1.3)', color: '#34d399',
    },
    {
        key: 'hologram_scan', label: 'Hologram', description: 'Sci-fi holographic projection',
        css: 'saturate(0.5) sepia(0.3) hue-rotate(180deg) brightness(1.1)', color: '#22d3ee',
    },
    {
        key: 'portal', label: 'Portal', description: 'Swirling vortex distortion',
        css: 'hue-rotate(250deg) saturate(1.5) brightness(1.1)', color: '#a855f7',
    },
    {
        key: 'circuit_board', label: 'Circuit', description: 'PCB traces on image edges',
        css: 'saturate(0.7) hue-rotate(70deg) brightness(0.8)', color: '#4ade80',
    },
    {
        key: 'dissolve', label: 'Dissolve', description: 'Particle dissolve with embers',
        css: 'brightness(0.9) contrast(1.2)', color: '#fb923c',
    },
    {
        key: 'hex_matrix', label: 'Hex Matrix', description: 'Hex grid with parallax depth',
        css: 'saturate(0.8) hue-rotate(150deg) contrast(1.1)', color: '#06b6d4',
    },
    {
        key: 'liquid_metal', label: 'Liquid Metal', description: 'Chrome mercury surface',
        css: 'saturate(0) contrast(1.5) brightness(1.1)', color: '#94a3b8',
    },
    {
        key: 'xray', label: 'X-Ray', description: 'Medical X-ray imaging',
        css: 'invert(1) saturate(0) brightness(1.2) contrast(1.3)', color: '#818cf8',
    },
    // Creative batch 2
    {
        key: 'cartoon', label: 'Cartoon', description: 'Cel-shaded toon with ink outlines',
        css: 'contrast(1.4) saturate(1.5)', color: '#f472b6',
    },
    {
        key: 'jelly', label: 'Jelly', description: 'Elastic gelatin wobble distortion',
        css: 'brightness(1.05) saturate(1.1)', color: '#c084fc',
    },
    {
        key: 'emboss_3d', label: 'Emboss 3D', description: 'Relief carving with rotating light',
        css: 'grayscale(0.5) contrast(1.5) brightness(1.1)', color: '#d6d3d1',
    },
    {
        key: 'infrared_predator', label: 'Predator', description: 'Thermal hunting vision + reticle',
        css: 'saturate(0) sepia(1) hue-rotate(-30deg) contrast(1.5)', color: '#ef4444',
    },
    {
        key: 'digital_decay', label: 'Decay', description: 'Corrupted signal with pixel rot',
        css: 'contrast(1.3) brightness(0.95)', color: '#a1a1aa',
    },
    {
        key: 'underwater', label: 'Underwater', description: 'Deep sea with caustics & particles',
        css: 'saturate(0.7) hue-rotate(160deg) brightness(0.85)', color: '#0ea5e9',
    },
    {
        key: 'electric_arc', label: 'Electric', description: 'Tesla arc lightning on edges',
        css: 'brightness(0.85) contrast(1.2) saturate(1.3)', color: '#38bdf8',
    },
    {
        key: 'ink_wash', label: 'Ink Wash', description: 'Sumi-e ink painting on rice paper',
        css: 'grayscale(0.8) contrast(1.3) sepia(0.2)', color: '#57534e',
    },
    // Outline shaders (pair with SAM3 masking)
    {
        key: 'neon_outline', label: 'Neon Outline', description: 'Glowing neon contour lines',
        css: 'brightness(0.5) contrast(2) saturate(2)', color: '#f0abfc',
    },
    {
        key: 'fire_outline', label: 'Fire Outline', description: 'Burning edge with rising flames',
        css: 'brightness(0.9) contrast(1.3)', color: '#fb923c',
    },
    {
        key: 'frost_outline', label: 'Frost Outline', description: 'Icy crystal edges',
        css: 'brightness(1.1) saturate(0.7) hue-rotate(190deg)', color: '#7dd3fc',
    },
    {
        key: 'shadow_outline', label: 'Shadow', description: 'Dramatic drop shadow silhouette',
        css: 'brightness(0.8) contrast(1.4)', color: '#52525b',
    },
    // GPU-enhanced classics
    {
        key: 'oil_paint', label: 'Oil Paint', description: 'Kuwahara brush stroke smoothing',
        css: 'blur(1px) saturate(1.3) contrast(1.1)', color: '#fbbf24',
    },
    {
        key: 'rain', label: 'Rain', description: 'Animated rain streaks & lens drops',
        css: 'brightness(0.88) saturate(0.8)', color: '#60a5fa',
    },
    {
        key: 'matrix', label: 'Matrix', description: 'Digital rain with glyph characters',
        css: 'saturate(0) brightness(0.5) sepia(0.5) hue-rotate(70deg)', color: '#22c55e',
    },
    {
        key: 'sketch', label: 'Sketch', description: 'Pencil hatching with paper texture',
        css: 'grayscale(1) contrast(2) brightness(1.2)', color: '#78716c',
    },
    // Boundary-pushing batch 3
    {
        key: 'pixel_sort', label: 'Pixel Sort', description: 'Glitch art brightness sorting',
        css: 'contrast(1.3) saturate(1.1)', color: '#f43f5e',
    },
    {
        key: 'topographic', label: 'Topographic', description: 'Elevation contour terrain map',
        css: 'saturate(0.5) hue-rotate(60deg) contrast(1.2)', color: '#65a30d',
    },
    {
        key: 'stained_glass', label: 'Stained Glass', description: 'Cathedral window panels',
        css: 'saturate(1.8) brightness(1.1) contrast(1.1)', color: '#e11d48',
    },
    {
        key: 'smoke', label: 'Smoke', description: 'Animated fog wisps drifting',
        css: 'brightness(0.85) contrast(0.8) saturate(0.6)', color: '#9ca3af',
    },
    {
        key: 'geometric_shatter', label: 'Shatter', description: 'Exploding triangle shards',
        css: 'brightness(1.05) contrast(1.2)', color: '#e2e8f0',
    },
    {
        key: 'noir', label: 'Noir', description: 'Film noir with venetian blinds',
        css: 'grayscale(0.9) contrast(1.5) brightness(0.9)', color: '#404040',
    },
    {
        key: 'cyberpunk', label: 'Cyberpunk', description: 'Neon dystopian aesthetic',
        css: 'saturate(2) hue-rotate(270deg) contrast(1.2)', color: '#d946ef',
    },
    {
        key: 'mosaic', label: 'Mosaic', description: 'Byzantine stone tile mosaic',
        css: 'saturate(1.3) contrast(1.1)', color: '#b45309',
    },
    {
        key: 'lava_lamp', label: 'Lava Lamp', description: 'Animated metaball blobs',
        css: 'saturate(1.5) hue-rotate(20deg) brightness(1.1)', color: '#f97316',
    },
    {
        key: 'vaporwave', label: 'Vaporwave', description: 'Retro 80s grid + sunset',
        css: 'saturate(1.5) hue-rotate(280deg) brightness(1.05)', color: '#c084fc',
    },
    {
        key: 'supernova', label: 'Supernova', description: 'Expanding nebula filaments + stars',
        css: 'brightness(1.1) saturate(1.5) hue-rotate(220deg)', color: '#6366f1',
    },
    {
        key: 'fractal_loop', label: 'Fractal Loop', description: 'Iterated inversion fractal',
        css: 'saturate(2) contrast(1.3) hue-rotate(90deg)', color: '#a855f7',
    },
    {
        key: 'kaleidoscope', label: 'Kaleidoscope', description: 'Neon ring fractal',
        css: 'saturate(2) contrast(1.4) hue-rotate(180deg)', color: '#ec4899',
    },
    {
        key: 'ebruli', label: 'Ebruli', description: 'Turkish water marbling',
        css: 'saturate(1.4) contrast(1.1) blur(1px)', color: '#7c3aed',
    },
    {
        key: 'spirals', label: 'Spirals', description: 'Multi-layer spiral vortex',
        css: 'saturate(2) contrast(1.3) hue-rotate(120deg)', color: '#14b8a6',
    },
    {
        key: 'space_tunnel', label: 'Space Tunnel', description: 'Warp tunnel + nebula + stars',
        css: 'saturate(1.5) contrast(1.4) brightness(0.9)', color: '#3b82f6',
    },
    {
        key: 'singularity', label: 'Singularity', description: 'Wormhole with energy fibers',
        css: 'saturate(1.6) contrast(1.5) hue-rotate(260deg)', color: '#8b5cf6',
    },
    {
        key: 'blueprint', label: 'Blueprint', description: 'Sacred geometry + glyph rings',
        css: 'saturate(0.8) contrast(1.6) hue-rotate(200deg)', color: '#60a5fa',
    },
    {
        key: 'singularity_box', label: 'Singularity Box', description: 'Raymarched spiral singularity',
        css: 'saturate(1.8) contrast(1.5) hue-rotate(280deg)', color: '#a78bfa',
    },
    // NPR & Stylized batch
    {
        key: 'anime_pro', label: 'Anime Pro', description: 'Advanced cel-shading with halftone shadows & rim light',
        css: 'contrast(1.4) saturate(1.5)', color: '#f472b6',
    },
    {
        key: 'anime_glow', label: 'Anime Glow', description: 'Dreamy bloom with pastel tints & sparkle',
        css: 'brightness(1.15) saturate(0.9) contrast(0.95)', color: '#fda4af',
    },
    {
        key: 'comic_book', label: 'Comic Book', description: 'Ben-Day halftone dots with bold Kirby outlines',
        css: 'contrast(1.5) saturate(1.6)', color: '#facc15',
    },
    {
        key: 'pop_art', label: 'Pop Art', description: 'Warhol CMYK halftone with bold posterization',
        css: 'contrast(1.6) saturate(2.5)', color: '#f43f5e',
    },
    {
        key: 'watercolor', label: 'Watercolor', description: 'Realistic pigment pooling & paper texture',
        css: 'blur(0.5px) saturate(0.85) contrast(1.1)', color: '#67e8f9',
    },
    {
        key: 'watercolor_bleed', label: 'Watercolor Bleed', description: 'Animated wet bleeding edges & pigment flow',
        css: 'blur(1px) saturate(0.8) contrast(1.05)', color: '#5eead4',
    },
    {
        key: 'woodcut', label: 'Woodcut', description: 'Japanese linocut with carved line texture',
        css: 'grayscale(0.8) contrast(1.5) sepia(0.3)', color: '#a16207',
    },
    {
        key: 'chromatic_prism', label: 'Chromatic Prism', description: 'Prismatic rainbow edge dispersion',
        css: 'saturate(1.2) brightness(1.05)', color: '#c084fc',
    },
    {
        key: 'retro_dither', label: 'Retro Dither', description: 'Ordered Bayer 8×8 dithering with retro palette',
        css: 'contrast(1.1) saturate(1.2)', color: '#34d399',
    },
    {
        key: 'neon_wireframe', label: 'Neon Wire', description: 'Glowing neon contour lines on dark background',
        css: 'brightness(0.3) contrast(2) saturate(2.5)', color: '#22d3ee',
    },
    // Depth-Native batch (read depth per-pixel via SBS)
    {
        key: 'toon_3d', label: 'Toon 3D', description: 'Depth-aware cel-shading with 3D silhouette outlines',
        css: 'contrast(1.5) saturate(1.4)', color: '#e879f9',
    },
    {
        key: 'depth_fog', label: 'Depth Fog', description: 'Real atmospheric perspective with depth-based fog',
        css: 'brightness(0.9) saturate(0.7) contrast(0.85)', color: '#94a3b8',
    },
    {
        key: 'focus_pull', label: 'Focus Pull', description: 'Cinematic depth-of-field with bokeh blur',
        css: 'blur(1px) brightness(1.02) contrast(1.05)', color: '#a78bfa',
    },
    {
        key: 'relief_sculpt', label: 'Relief Sculpt', description: 'Emboss relief using depth as 3D height map',
        css: 'grayscale(0.5) contrast(1.6) sepia(0.2)', color: '#d4a276',
    },
    {
        key: 'depth_watercolor', label: 'Depth Water', description: 'Watercolor with depth-modulated strokes',
        css: 'blur(0.5px) saturate(0.8) contrast(1.1)', color: '#38bdf8',
    },
];

export class ShaderPanel {
    private container: HTMLDivElement;
    private callbacks: ShaderCallbacks;
    private selectedKey: string = 'none';
    private intensity: number = 1.0;
    private enableVda: boolean = false;
    private enableNormals: boolean = false;
    private depthEncoder: string = 'vits';
    private depthStrength: number = 1.0;
    private cards: Map<string, HTMLDivElement> = new Map();
    private intensitySlider!: HTMLInputElement;
    private intensityLabel!: HTMLSpanElement;
    private vdaCheckbox!: HTMLInputElement;
    private normalsCheckbox!: HTMLInputElement;
    private depthEncoderSelect!: HTMLSelectElement;
    private depthStrengthSlider!: HTMLInputElement;
    private depthStrengthLabel!: HTMLSpanElement;
    private depthSection!: HTMLDivElement;

    constructor(callbacks: ShaderCallbacks) {
        this.callbacks = callbacks;

        this.container = document.createElement('div');
        this.container.className = 'veditor-filters-panel';
        this.container.setAttribute('data-tool-id', 'veditor-shader-panel');
        this.container.setAttribute('aria-label', 'GPU shader preset controls');

        // ── GPU badge ──
        const header = document.createElement('div');
        header.className = 'veditor-section-label';
        header.style.display = 'flex';
        header.style.alignItems = 'center';
        header.style.gap = '8px';

        const badge = document.createElement('span');
        badge.textContent = '⚡ GPU';
        badge.style.cssText = `
            font-size: 10px; padding: 2px 6px; border-radius: 4px;
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            color: #fff; font-weight: 600; letter-spacing: 0.5px;
        `;
        const headerText = document.createElement('span');
        headerText.textContent = 'Shader Presets';
        header.append(headerText, badge);

        // ── Preset Grid ──
        const grid = document.createElement('div');
        grid.className = 'veditor-filter-grid';

        for (const shader of SHADERS) {
            const card = this._makeCard(shader);
            grid.appendChild(card);
            this.cards.set(shader.key, card);
        }

        // ── Intensity Section ──
        const intensitySection = document.createElement('div');
        intensitySection.className = 'veditor-panel-section veditor-filter-intensity-section';

        const intensityHeader = document.createElement('div');
        intensityHeader.className = 'veditor-section-label';
        intensityHeader.textContent = 'Intensity';

        const intensityRow = document.createElement('div');
        intensityRow.className = 'veditor-control-row';

        this.intensitySlider = document.createElement('input');
        this.intensitySlider.type = 'range';
        this.intensitySlider.min = '0';
        this.intensitySlider.max = '100';
        this.intensitySlider.step = '1';
        this.intensitySlider.value = '100';
        this.intensitySlider.className = 'veditor-grading-slider';
        this.intensitySlider.setAttribute('data-tool-id', 'veditor-shader-intensity');
        this.intensitySlider.setAttribute('aria-label', 'Shader intensity (0 to 100%)');

        this.intensityLabel = document.createElement('span');
        this.intensityLabel.className = 'veditor-grading-value';
        this.intensityLabel.textContent = '100%';

        this.intensitySlider.addEventListener('input', () => {
            this.intensity = parseInt(this.intensitySlider.value, 10) / 100;
            this.intensityLabel.textContent = `${Math.round(this.intensity * 100)}%`;
            this.callbacks.onShaderChanged(this.getState());
        });

        intensityRow.append(this.intensitySlider, this.intensityLabel);
        intensitySection.append(intensityHeader, intensityRow);

        // ── Depth-Aware Section ──
        this.depthSection = document.createElement('div');
        this.depthSection.className = 'veditor-panel-section';
        this.depthSection.style.cssText = `
            margin-top: 12px; padding-top: 12px;
            border-top: 1px solid rgba(255,255,255,0.08);
        `;

        const depthHeader = document.createElement('div');
        depthHeader.className = 'veditor-section-label';
        depthHeader.style.display = 'flex';
        depthHeader.style.alignItems = 'center';
        depthHeader.style.gap = '8px';

        const depthBadge = document.createElement('span');
        depthBadge.textContent = '🔮 AI';
        depthBadge.style.cssText = `
            font-size: 10px; padding: 2px 6px; border-radius: 4px;
            background: linear-gradient(135deg, #06b6d4, #8b5cf6);
            color: #fff; font-weight: 600; letter-spacing: 0.5px;
        `;
        const depthText = document.createElement('span');
        depthText.textContent = 'AI Passes';
        depthHeader.append(depthText, depthBadge);

        // VDA toggle
        const vdaRow = document.createElement('div');
        vdaRow.className = 'veditor-control-row';
        vdaRow.style.cssText = 'margin-top: 6px; gap: 8px; align-items: center;';

        this.vdaCheckbox = document.createElement('input');
        this.vdaCheckbox.type = 'checkbox';
        this.vdaCheckbox.checked = false;
        this.vdaCheckbox.setAttribute('data-tool-id', 'veditor-shader-enable-vda');
        this.vdaCheckbox.style.cssText = 'width: 16px; height: 16px; cursor: pointer; accent-color: #06b6d4;';

        const vdaLabel = document.createElement('span');
        vdaLabel.className = 'veditor-grading-value';
        vdaLabel.textContent = 'VDA Depth';
        vdaLabel.style.cssText = 'flex: 1; cursor: pointer;';
        vdaLabel.addEventListener('click', () => { this.vdaCheckbox.click(); });

        this.vdaCheckbox.addEventListener('change', () => {
            this.enableVda = this.vdaCheckbox.checked;
            this._updateDepthVisibility();
            this.callbacks.onShaderChanged(this.getState());
        });

        vdaRow.append(this.vdaCheckbox, vdaLabel);

        // NormalCrafter toggle
        const normalsRow = document.createElement('div');
        normalsRow.className = 'veditor-control-row';
        normalsRow.style.cssText = 'margin-top: 4px; gap: 8px; align-items: center;';

        this.normalsCheckbox = document.createElement('input');
        this.normalsCheckbox.type = 'checkbox';
        this.normalsCheckbox.checked = false;
        this.normalsCheckbox.setAttribute('data-tool-id', 'veditor-shader-enable-normals');
        this.normalsCheckbox.style.cssText = 'width: 16px; height: 16px; cursor: pointer; accent-color: #8b5cf6;';

        const normalsLabel = document.createElement('span');
        normalsLabel.className = 'veditor-grading-value';
        normalsLabel.textContent = 'NormalCrafter';
        normalsLabel.style.cssText = 'flex: 1; cursor: pointer;';
        normalsLabel.addEventListener('click', () => { this.normalsCheckbox.click(); });

        this.normalsCheckbox.addEventListener('change', () => {
            this.enableNormals = this.normalsCheckbox.checked;
            this.callbacks.onShaderChanged(this.getState());
        });

        normalsRow.append(this.normalsCheckbox, normalsLabel);

        // Depth encoder dropdown
        const depthEncoderRow = document.createElement('div');
        depthEncoderRow.className = 'veditor-control-row';
        depthEncoderRow.style.cssText = 'margin-top: 4px; gap: 8px;';

        const depthEncoderLabel = document.createElement('span');
        depthEncoderLabel.className = 'veditor-grading-value';
        depthEncoderLabel.textContent = 'Model';
        depthEncoderLabel.style.minWidth = '40px';

        this.depthEncoderSelect = document.createElement('select');
        this.depthEncoderSelect.className = 'veditor-grading-slider';
        this.depthEncoderSelect.setAttribute('data-tool-id', 'veditor-shader-depth-encoder');
        this.depthEncoderSelect.style.cssText = `
            flex: 1; padding: 4px 8px; border-radius: 6px;
            background: rgba(255,255,255,0.06); color: #e2e8f0;
            border: 1px solid rgba(255,255,255,0.1);
            font-size: 12px; cursor: pointer;
        `;
        for (const [val, label] of [['vits', 'Small (fast, ~102 MB)'],
                                     ['vitb', 'Base (~390 MB)'],
                                     ['vitl', 'Large (best, ~670 MB)']] as const) {
            const opt = document.createElement('option');
            opt.value = val;
            opt.textContent = label;
            this.depthEncoderSelect.appendChild(opt);
        }
        this.depthEncoderSelect.addEventListener('change', () => {
            this.depthEncoder = this.depthEncoderSelect.value;
            this.callbacks.onShaderChanged(this.getState());
        });

        depthEncoderRow.append(depthEncoderLabel, this.depthEncoderSelect);

        // Depth strength slider
        const depthStrengthRow = document.createElement('div');
        depthStrengthRow.className = 'veditor-control-row';
        depthStrengthRow.style.cssText = 'margin-top: 4px;';

        const depthStrLabel = document.createElement('span');
        depthStrLabel.className = 'veditor-grading-value';
        depthStrLabel.textContent = 'Strength';
        depthStrLabel.style.minWidth = '40px';

        this.depthStrengthSlider = document.createElement('input');
        this.depthStrengthSlider.type = 'range';
        this.depthStrengthSlider.min = '0';
        this.depthStrengthSlider.max = '100';
        this.depthStrengthSlider.step = '1';
        this.depthStrengthSlider.value = '100';
        this.depthStrengthSlider.className = 'veditor-grading-slider';
        this.depthStrengthSlider.setAttribute('data-tool-id', 'veditor-shader-depth-strength');

        this.depthStrengthLabel = document.createElement('span');
        this.depthStrengthLabel.className = 'veditor-grading-value';
        this.depthStrengthLabel.textContent = '100%';

        this.depthStrengthSlider.addEventListener('input', () => {
            this.depthStrength = parseInt(this.depthStrengthSlider.value, 10) / 100;
            this.depthStrengthLabel.textContent = `${Math.round(this.depthStrength * 100)}%`;
            this.callbacks.onShaderChanged(this.getState());
        });

        depthStrengthRow.append(depthStrLabel, this.depthStrengthSlider, this.depthStrengthLabel);

        this.depthSection.append(
            depthHeader, vdaRow, normalsRow, depthEncoderRow, depthStrengthRow,
        );

        this.container.append(header, grid, intensitySection, this.depthSection);

        // Mark "none" as initially selected
        this._selectCard('none');
        this._updateDepthVisibility();
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    getState(): ShaderPresetState {
        return {
            preset: this.selectedKey,
            intensity: this.intensity,
            enable_vda: this.enableVda,
            enable_normals: this.enableNormals,
            depth_encoder: this.depthEncoder,
            depth_strength: this.depthStrength,
        };
    }

    loadState(state: Partial<ShaderPresetState>): void {
        if (state.preset !== undefined) {
            this._selectCard(state.preset);
        }
        if (state.intensity !== undefined) {
            this.intensity = state.intensity;
            this.intensitySlider.value = String(Math.round(this.intensity * 100));
            this.intensityLabel.textContent = `${Math.round(this.intensity * 100)}%`;
        }
        if (state.enable_vda !== undefined) {
            this.enableVda = state.enable_vda;
            this.vdaCheckbox.checked = state.enable_vda;
        }
        if (state.enable_normals !== undefined) {
            this.enableNormals = state.enable_normals;
            this.normalsCheckbox.checked = state.enable_normals;
        }
        if (state.depth_encoder !== undefined) {
            this.depthEncoder = state.depth_encoder;
            this.depthEncoderSelect.value = state.depth_encoder;
        }
        if (state.depth_strength !== undefined) {
            this.depthStrength = state.depth_strength;
            this.depthStrengthSlider.value = String(Math.round(this.depthStrength * 100));
            this.depthStrengthLabel.textContent = `${Math.round(this.depthStrength * 100)}%`;
        }
        this._updateDepthVisibility();
    }

    reset(): void {
        this._selectCard('none');
        this.intensity = 1.0;
        this.intensitySlider.value = '100';
        this.intensityLabel.textContent = '100%';
        this.enableVda = false;
        this.vdaCheckbox.checked = false;
        this.enableNormals = false;
        this.normalsCheckbox.checked = false;
        this.depthEncoder = 'vits';
        this.depthEncoderSelect.value = 'vits';
        this.depthStrength = 1.0;
        this.depthStrengthSlider.value = '100';
        this.depthStrengthLabel.textContent = '100%';
        this._updateDepthVisibility();
    }

    destroy(): void {
        this.container.remove();
    }

    // ── Private ──────────────────────────────────────────────────

    private _makeCard(shader: ShaderDef): HTMLDivElement {
        const card = document.createElement('div');
        card.className = 'veditor-filter-card';
        card.setAttribute('data-tool-id', `veditor-shader-${shader.key}`);
        card.setAttribute('aria-label', `Shader: ${shader.label}`);
        card.title = `${shader.label} — ${shader.description}`;

        // Color swatch
        const swatch = document.createElement('div');
        swatch.className = 'veditor-filter-swatch';
        if (shader.key !== 'none') {
            swatch.style.filter = shader.css;
            swatch.style.borderColor = shader.color;
        }

        // Label
        const label = document.createElement('span');
        label.className = 'veditor-filter-label';
        label.textContent = shader.label;

        card.append(swatch, label);

        card.addEventListener('click', () => {
            this._selectCard(shader.key);
            this.callbacks.onShaderChanged(this.getState());
        });

        return card;
    }

    private _selectCard(key: string): void {
        this.selectedKey = key;
        for (const [k, card] of this.cards) {
            card.classList.toggle('active', k === key);
        }
    }

    private _updateDepthVisibility(): void {
        const active = this.enableVda || this.enableNormals;
        // Show/hide encoder and strength rows when any AI pass is active
        const rows = this.depthSection.querySelectorAll('.veditor-control-row');
        // rows[0] = VDA toggle (always visible)
        // rows[1] = NormalCrafter toggle (always visible)
        // rows[2] = encoder, rows[3] = strength
        if (rows.length >= 4) {
            (rows[2] as HTMLElement).style.display = active ? '' : 'none';
            (rows[3] as HTMLElement).style.display = active ? '' : 'none';
        }
    }
}
