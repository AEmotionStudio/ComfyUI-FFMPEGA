/**
 * RelightPanel — Directional lighting editor for the NLE Video Editor.
 *
 * Provides controls for simulating directional lighting:
 * - Light direction: circular picker (azimuth) + vertical slider (elevation)
 * - Light color: color input
 * - Intensity slider: 0–200%
 * - Ambient fill slider: 0–100%
 * - Enable toggle
 *
 * The circular picker renders a small canvas showing the light direction
 * as a radial gradient + direction arrow.
 */

export interface RelightState {
    enabled: boolean;
    azimuth: number;      // degrees, 0=front, 90=right, -90=left
    elevation: number;    // degrees above horizon
    intensity: number;    // 0–2.0
    ambient: number;      // 0–1.0
    color_r: number;
    color_g: number;
    color_b: number;
}

export interface RelightCallbacks {
    onRelightChanged: (state: RelightState) => void;
}

const DEFAULT_STATE: RelightState = {
    enabled: false,
    azimuth: 0,
    elevation: 45,
    intensity: 1.0,
    ambient: 0.3,
    color_r: 255,
    color_g: 255,
    color_b: 255,
};

export class RelightPanel {
    private container: HTMLDivElement;
    private callbacks: RelightCallbacks;
    private state: RelightState;

    private enableToggle!: HTMLInputElement;
    private dirCanvas!: HTMLCanvasElement;
    private dirCtx!: CanvasRenderingContext2D;
    private elevSlider!: HTMLInputElement;
    private elevLabel!: HTMLSpanElement;
    private intensitySlider!: HTMLInputElement;
    private intensityLabel!: HTMLSpanElement;
    private ambientSlider!: HTMLInputElement;
    private ambientLabel!: HTMLSpanElement;
    private colorInput!: HTMLInputElement;
    private controlsContainer!: HTMLDivElement;

    constructor(callbacks: RelightCallbacks) {
        this.callbacks = callbacks;
        this.state = { ...DEFAULT_STATE };

        this.container = document.createElement('div');
        this.container.className = 'veditor-relight-panel';
        this.container.setAttribute('data-tool-id', 'veditor-relight-panel');
        this.container.setAttribute('aria-label', 'Relighting controls');

        // ── Enable Toggle ──
        const enableSection = this._makeSection('Directional Relight');
        const enableRow = document.createElement('div');
        enableRow.className = 'veditor-control-row';

        const enableLabel = document.createElement('label');
        enableLabel.className = 'veditor-toggle-label';
        enableLabel.textContent = 'Enable relighting';

        this.enableToggle = document.createElement('input');
        this.enableToggle.type = 'checkbox';
        this.enableToggle.className = 'veditor-checkbox';
        this.enableToggle.setAttribute('data-tool-id', 'veditor-relight-enable');
        this.enableToggle.addEventListener('change', () => {
            this.state.enabled = this.enableToggle.checked;
            this.controlsContainer.style.display = this.state.enabled ? 'block' : 'none';
            this._notify();
        });

        enableRow.append(enableLabel, this.enableToggle);
        enableSection.appendChild(enableRow);

        // ── Controls container (hidden when disabled) ──
        this.controlsContainer = document.createElement('div');
        this.controlsContainer.style.display = 'none';

        // ── Light Direction Canvas ──
        const dirSection = this._makeSection('Light Direction');

        this.dirCanvas = document.createElement('canvas');
        this.dirCanvas.className = 'veditor-relight-dir-canvas';
        this.dirCanvas.width = 100;
        this.dirCanvas.height = 100;
        this.dirCanvas.setAttribute('aria-label', 'Light direction picker');
        this.dirCtx = this.dirCanvas.getContext('2d')!;

        this.dirCanvas.addEventListener('mousedown', (e) => this._onDirClick(e));
        this.dirCanvas.addEventListener('mousemove', (e) => {
            if (e.buttons === 1) this._onDirClick(e);
        });

        dirSection.appendChild(this.dirCanvas);

        // ── Elevation Slider ──
        const elevSection = this._makeSection('Elevation');
        const elevRow = document.createElement('div');
        elevRow.className = 'veditor-control-row';

        this.elevSlider = document.createElement('input');
        this.elevSlider.type = 'range';
        this.elevSlider.min = '0';
        this.elevSlider.max = '90';
        this.elevSlider.step = '1';
        this.elevSlider.value = '45';
        this.elevSlider.className = 'veditor-grading-slider';
        this.elevSlider.setAttribute('data-tool-id', 'veditor-relight-elevation');

        this.elevLabel = document.createElement('span');
        this.elevLabel.className = 'veditor-grading-value';
        this.elevLabel.textContent = '45°';

        this.elevSlider.addEventListener('input', () => {
            this.state.elevation = parseInt(this.elevSlider.value, 10);
            this.elevLabel.textContent = `${this.state.elevation}°`;
            this._drawDirection();
            this._notify();
        });

        elevRow.append(this.elevSlider, this.elevLabel);
        elevSection.appendChild(elevRow);

        // ── Intensity Slider ──
        const intSection = this._makeSection('Intensity');
        const intRow = document.createElement('div');
        intRow.className = 'veditor-control-row';

        this.intensitySlider = document.createElement('input');
        this.intensitySlider.type = 'range';
        this.intensitySlider.min = '0';
        this.intensitySlider.max = '200';
        this.intensitySlider.step = '1';
        this.intensitySlider.value = '100';
        this.intensitySlider.className = 'veditor-grading-slider';
        this.intensitySlider.setAttribute('data-tool-id', 'veditor-relight-intensity');

        this.intensityLabel = document.createElement('span');
        this.intensityLabel.className = 'veditor-grading-value';
        this.intensityLabel.textContent = '100%';

        this.intensitySlider.addEventListener('input', () => {
            this.state.intensity = parseInt(this.intensitySlider.value, 10) / 100;
            this.intensityLabel.textContent = `${Math.round(this.state.intensity * 100)}%`;
            this._notify();
        });

        intRow.append(this.intensitySlider, this.intensityLabel);
        intSection.appendChild(intRow);

        // ── Ambient Slider ──
        const ambSection = this._makeSection('Ambient Fill');
        const ambRow = document.createElement('div');
        ambRow.className = 'veditor-control-row';

        this.ambientSlider = document.createElement('input');
        this.ambientSlider.type = 'range';
        this.ambientSlider.min = '0';
        this.ambientSlider.max = '100';
        this.ambientSlider.step = '1';
        this.ambientSlider.value = '30';
        this.ambientSlider.className = 'veditor-grading-slider';
        this.ambientSlider.setAttribute('data-tool-id', 'veditor-relight-ambient');

        this.ambientLabel = document.createElement('span');
        this.ambientLabel.className = 'veditor-grading-value';
        this.ambientLabel.textContent = '30%';

        this.ambientSlider.addEventListener('input', () => {
            this.state.ambient = parseInt(this.ambientSlider.value, 10) / 100;
            this.ambientLabel.textContent = `${Math.round(this.state.ambient * 100)}%`;
            this._notify();
        });

        ambRow.append(this.ambientSlider, this.ambientLabel);
        ambSection.appendChild(ambRow);

        // ── Light Color ──
        const colorSection = this._makeSection('Light Color');
        const colorRow = document.createElement('div');
        colorRow.className = 'veditor-control-row';

        this.colorInput = document.createElement('input');
        this.colorInput.type = 'color';
        this.colorInput.value = '#ffffff';
        this.colorInput.className = 'veditor-relight-color-input';
        this.colorInput.setAttribute('data-tool-id', 'veditor-relight-color');

        this.colorInput.addEventListener('input', () => {
            const hex = this.colorInput.value;
            this.state.color_r = parseInt(hex.slice(1, 3), 16);
            this.state.color_g = parseInt(hex.slice(3, 5), 16);
            this.state.color_b = parseInt(hex.slice(5, 7), 16);
            this._drawDirection();
            this._notify();
        });

        colorRow.appendChild(this.colorInput);
        colorSection.appendChild(colorRow);

        // ── Reset ──
        const resetRow = document.createElement('div');
        resetRow.className = 'veditor-control-row';

        const resetBtn = document.createElement('button');
        resetBtn.className = 'veditor-btn veditor-toggle-btn';
        resetBtn.textContent = 'Reset Lighting';
        resetBtn.setAttribute('data-tool-id', 'veditor-relight-reset');
        resetBtn.addEventListener('click', () => this.reset());
        resetRow.appendChild(resetBtn);

        this.controlsContainer.append(
            dirSection, elevSection, intSection, ambSection, colorSection, resetRow
        );

        this.container.append(enableSection, this.controlsContainer);
        this._drawDirection();
    }

    get element(): HTMLDivElement {
        return this.container;
    }

    getState(): RelightState {
        return { ...this.state };
    }

    loadState(s: Partial<RelightState>): void {
        Object.assign(this.state, s);
        this.enableToggle.checked = this.state.enabled;
        this.controlsContainer.style.display = this.state.enabled ? 'block' : 'none';
        this.elevSlider.value = String(this.state.elevation);
        this.elevLabel.textContent = `${this.state.elevation}°`;
        this.intensitySlider.value = String(Math.round(this.state.intensity * 100));
        this.intensityLabel.textContent = `${Math.round(this.state.intensity * 100)}%`;
        this.ambientSlider.value = String(Math.round(this.state.ambient * 100));
        this.ambientLabel.textContent = `${Math.round(this.state.ambient * 100)}%`;
        const hex = `#${this.state.color_r.toString(16).padStart(2, '0')}${this.state.color_g.toString(16).padStart(2, '0')}${this.state.color_b.toString(16).padStart(2, '0')}`;
        this.colorInput.value = hex;
        this._drawDirection();
    }

    reset(): void {
        this.state = { ...DEFAULT_STATE };
        this.enableToggle.checked = false;
        this.controlsContainer.style.display = 'none';
        this.elevSlider.value = '45';
        this.elevLabel.textContent = '45°';
        this.intensitySlider.value = '100';
        this.intensityLabel.textContent = '100%';
        this.ambientSlider.value = '30';
        this.ambientLabel.textContent = '30%';
        this.colorInput.value = '#ffffff';
        this._drawDirection();
        this._notify();
    }

    destroy(): void {
        this.container.remove();
    }

    // ── Private ──────────────────────────────────────────────────

    private _notify(): void {
        this.callbacks.onRelightChanged(this.getState());
    }

    private _onDirClick(e: MouseEvent): void {
        const rect = this.dirCanvas.getBoundingClientRect();
        const cx = rect.width / 2;
        const cy = rect.height / 2;
        const dx = e.clientX - rect.left - cx;
        const dy = e.clientY - rect.top - cy;
        const angle = Math.atan2(dx, -dy) * (180 / Math.PI);
        this.state.azimuth = Math.round(angle);
        this._drawDirection();
        this._notify();
    }

    private _drawDirection(): void {
        const ctx = this.dirCtx;
        const w = this.dirCanvas.width;
        const h = this.dirCanvas.height;
        const cx = w / 2;
        const cy = h / 2;
        const r = Math.min(cx, cy) - 4;

        ctx.clearRect(0, 0, w, h);

        // Background circle
        ctx.fillStyle = 'rgba(30, 30, 44, 0.6)';
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.fill();

        // Border
        ctx.strokeStyle = 'rgba(99,102,241,0.3)';
        ctx.lineWidth = 1;
        ctx.stroke();

        // Crosshair
        ctx.strokeStyle = 'rgba(255,255,255,0.1)';
        ctx.beginPath();
        ctx.moveTo(cx - r, cy);
        ctx.lineTo(cx + r, cy);
        ctx.moveTo(cx, cy - r);
        ctx.lineTo(cx, cy + r);
        ctx.stroke();

        // Light gradient (simulates spotlight cone)
        const azRad = (this.state.azimuth * Math.PI) / 180;
        const gx = cx + Math.sin(azRad) * r * 0.5;
        const gy = cy - Math.cos(azRad) * r * 0.5;
        const lightColor = `rgba(${this.state.color_r}, ${this.state.color_g}, ${this.state.color_b}, ${0.3 * this.state.intensity})`;

        const grad = ctx.createRadialGradient(gx, gy, 0, gx, gy, r * 0.8);
        grad.addColorStop(0, lightColor);
        grad.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.fill();

        // Arrow line from center to light position
        const arrowLen = r * 0.7;
        const ax = cx + Math.sin(azRad) * arrowLen;
        const ay = cy - Math.cos(azRad) * arrowLen;

        ctx.strokeStyle = '#6366f1';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(ax, ay);
        ctx.stroke();

        // Arrow head
        ctx.fillStyle = '#6366f1';
        ctx.beginPath();
        ctx.arc(ax, ay, 4, 0, Math.PI * 2);
        ctx.fill();

        // Center dot
        ctx.fillStyle = 'rgba(255,255,255,0.4)';
        ctx.beginPath();
        ctx.arc(cx, cy, 3, 0, Math.PI * 2);
        ctx.fill();

        // Azimuth label
        ctx.fillStyle = 'rgba(255,255,255,0.5)';
        ctx.font = '9px monospace';
        ctx.textAlign = 'center';
        ctx.fillText(`${this.state.azimuth}°`, cx, h - 2);
    }

    private _makeSection(title: string): HTMLDivElement {
        const section = document.createElement('div');
        section.className = 'veditor-panel-section';
        const label = document.createElement('div');
        label.className = 'veditor-section-label';
        label.textContent = title;
        section.appendChild(label);
        return section;
    }
}
