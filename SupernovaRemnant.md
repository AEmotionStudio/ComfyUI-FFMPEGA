<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Supernova Remnant</title>
<style>
    body {
        margin: 0;
        overflow: hidden;
        background-color: #000;
    }
    canvas {
        display: block;
    }
    #theme-button {
        position: absolute;
        top: 20px;
        right: 20px;
        background: rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(10px);
        border: 2px solid rgba(255, 255, 255, 0.2);
        border-radius: 10px;
        padding: 10px 20px;
        color: white;
        font-family: Arial, sans-serif;
        font-size: 16px;
        cursor: pointer;
        transition: all 0.3s ease;
        z-index: 1;
        animation: borderGlow 5s linear infinite;
    }
    #theme-button:hover {
        background: rgba(255, 255, 255, 0.2);
        box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
    }
    @keyframes borderGlow {
        0% {
            border-color: rgba(100, 181, 246, 0.8);
            box-shadow: 0 0 10px rgba(100, 181, 246, 0.8), 0 0 20px rgba(100, 181, 246, 0.5);
        }
        25% {
            border-color: rgba(255, 152, 0, 0.8);
            box-shadow: 0 0 10px rgba(255, 152, 0, 0.8), 0 0 20px rgba(255, 152, 0, 0.5);
        }
        50% {
            border-color: rgba(186, 104, 200, 0.8);
            box-shadow: 0 0 10px rgba(186, 104, 200, 0.8), 0 0 20px rgba(186, 104, 200, 0.5);
        }
        75% {
            border-color: rgba(0, 188, 212, 0.8);
            box-shadow: 0 0 10px rgba(0, 188, 212, 0.8), 0 0 20px rgba(0, 188, 212, 0.5);
        }
        100% {
            border-color: rgba(100, 181, 246, 0.8);
            box-shadow: 0 0 10px rgba(100, 181, 246, 0.8), 0 0 20px rgba(100, 181, 246, 0.5);
        }
    }
</style>
<script type="importmap">
{
  "imports": {
    "three": "https://cdn.jsdelivr.net/npm/three@0.165.0/build/three.module.js"
  }
}
</script>
<canvas id="gl-canvas"></canvas>
<button id="theme-button">Change Theme</button>
<script type="module">
    import * as THREE from 'three';
    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    const renderer = new THREE.WebGLRenderer({ canvas: document.getElementById('gl-canvas') });
    const clock = new THREE.Clock();
    const vertexShader = `
        void main() {
            gl_Position = vec4(position, 1.0);
        }
    `;
    const fragmentShader = `
        precision highp float;
        uniform vec2 u_resolution;
        uniform float u_time;
        uniform vec3 color_fil1_base;
        uniform vec3 color_fil1_glow;
        uniform vec3 color_fil2_base;
        uniform vec3 color_fil2_glow;
        uniform vec3 color_core;
        uniform vec3 color_stars;
        float random(vec2 st) {
            return fract(sin(dot(st.xy, vec2(12.9898, 78.233))) * 43758.5453123);
        }
        float noise(vec2 st) {
            vec2 i = floor(st);
            vec2 f = fract(st);
            vec2 u = f * f * (3.0 - 2.0 * f);
            return mix(mix(random(i + vec2(0.0, 0.0)), random(i + vec2(1.0, 0.0)), u.x),
                       mix(random(i + vec2(0.0, 1.0)), random(i + vec2(1.0, 1.0)), u.x), u.y);
        }
        float fbm(vec2 st) {
            float value = 0.0;
            float amplitude = 0.5;
            for (int i = 0; i < 6; i++) {
                value += amplitude * noise(st);
                st *= 2.0;
                amplitude *= 0.5;
            }
            return value;
        }
        float random3(vec3 st) {
            return fract(sin(dot(st, vec3(12.9898, 78.233, 45.543))) * 43758.5453123);
        }
        float noise3(vec3 st) {
            vec3 i = floor(st);
            vec3 f = fract(st);
            vec3 u = f * f * (3.0 - 2.0 * f);
            return mix(mix(mix(random3(i + vec3(0.0, 0.0, 0.0)), random3(i + vec3(1.0, 0.0, 0.0)), u.x),
                           mix(random3(i + vec3(0.0, 1.0, 0.0)), random3(i + vec3(1.0, 1.0, 0.0)), u.x), u.y),
                       mix(mix(random3(i + vec3(0.0, 0.0, 1.0)), random3(i + vec3(1.0, 0.0, 1.0)), u.x),
                           mix(random3(i + vec3(0.0, 1.0, 1.0)), random3(i + vec3(1.0, 1.0, 1.0)), u.x), u.y), u.z);
        }
        float fbm3(vec3 st) {
            float value = 0.0;
            float amplitude = 0.5;
            for (int i = 0; i < 6; i++) {
                value += amplitude * noise3(st);
                st *= 2.0;
                amplitude *= 0.5;
            }
            return value;
        }
        void main() {
            vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution.xy) / u_resolution.y;
            float time = u_time * 0.3;
            vec3 final_color = vec3(0.0);
            float radius = length(uv);
            float angle = atan(uv.y, uv.x);
            vec3 gas_color = vec3(0.0);
            float speed1 = 0.5;
            float outer1 = time * speed1 + 1.5;
            float inner1 = outer1 - 0.5;
            float angular_scale1 = 3.0;
            float radial_scale1 = 3.0;
            vec3 p1 = vec3(sin(angle) * angular_scale1, cos(angle) * angular_scale1, radius * radial_scale1 + time * speed1);
            float filaments1 = fbm3(p1);
            filaments1 = 1.0 - abs(filaments1 - 0.5) * 2.0;
            filaments1 = pow(filaments1, 10.0);
            filaments1 *= smoothstep(outer1, inner1, radius);
            gas_color += filaments1 * color_fil1_base;
            gas_color += pow(filaments1, 12.0) * color_fil1_glow * 5.0;
            float speed2 = 0.8;
            float outer2 = time * speed2 + 1.5;
            float inner2 = outer2 - 0.4;
            float angular_scale2 = 5.0;
            float radial_scale2 = 4.0;
            vec3 p2 = vec3(sin(angle) * angular_scale2, cos(angle) * angular_scale2, radius * radial_scale2 + time * speed2) + vec3(3.7, 5.2, 1.3);
            float filaments2 = fbm3(p2);
            filaments2 = 1.0 - abs(filaments2 - 0.5) * 2.0;
            filaments2 = pow(filaments2, 15.0);
            filaments2 *= smoothstep(outer2, inner2, radius);
            gas_color += filaments2 * color_fil2_base;
            gas_color += pow(filaments2, 18.0) * color_fil2_glow * 5.0;
            float core_fade = smoothstep(1.5, 0.0, time);
            float core_texture = fbm(uv * 3.0 - time);
            float core_intensity = (1.0 - smoothstep(0.0, 0.2, radius)) * pow(core_fade, 2.0);
            gas_color += core_intensity * (core_texture * 2.0) * color_core;
            final_color += gas_color;
            float star_seed = random(floor(uv*200.0));
            float star_brightness = pow(star_seed, 50.0);
            
            float star_dist = fract(star_seed * 10.0 + time * 0.2);
            float star_mask = 1.0 - smoothstep(0.0, 0.01, abs(radius - star_dist));
            
            final_color += star_brightness * star_mask * color_stars;
            final_color = final_color / (final_color + vec3(1.0));
            final_color = pow(final_color, vec3(0.8));
            gl_FragColor = vec4(final_color, 1.0);
        }
    `;
    
    const geometry = new THREE.PlaneGeometry(2, 2);
    const uniforms = {
        u_time: { value: 0.0 },
        u_resolution: { value: new THREE.Vector2() },
        color_fil1_base: { value: new THREE.Vector3(0.1, 0.2, 0.8) },
        color_fil1_glow: { value: new THREE.Vector3(0.8, 0.8, 1.0) },
        color_fil2_base: { value: new THREE.Vector3(0.9, 0.5, 0.1) },
        color_fil2_glow: { value: new THREE.Vector3(1.0, 1.0, 0.8) },
        color_core: { value: new THREE.Vector3(1.0, 0.9, 0.7) },
        color_stars: { value: new THREE.Vector3(1.0, 1.0, 0.8) }
    };
    const material = new THREE.ShaderMaterial({
        vertexShader: vertexShader,
        fragmentShader: fragmentShader,
        uniforms: uniforms
    });
    const plane = new THREE.Mesh(geometry, material);
    scene.add(plane);
    const themes = [
        { 
            fil1_base: [0.1, 0.2, 0.8],
            fil1_glow: [0.8, 0.8, 1.0],
            fil2_base: [0.9, 0.5, 0.1],
            fil2_glow: [1.0, 1.0, 0.8],
            core: [1.0, 0.9, 0.7],
            stars: [1.0, 1.0, 0.8]
        },
        { 
            fil1_base: [0.8, 0.1, 0.2],
            fil1_glow: [1.0, 0.8, 0.8],
            fil2_base: [0.5, 0.1, 0.9],
            fil2_glow: [0.8, 0.8, 1.0],
            core: [1.0, 0.7, 0.9],
            stars: [1.0, 0.8, 1.0]
        },
        { 
            fil1_base: [0.1, 0.8, 0.2],
            fil1_glow: [0.8, 1.0, 0.8],
            fil2_base: [0.1, 0.5, 0.9],
            fil2_glow: [0.8, 1.0, 1.0],
            core: [0.7, 1.0, 0.9],
            stars: [0.8, 1.0, 1.0]
        }
    ];
    let currentTheme = 0;
    const themeButton = document.getElementById('theme-button');
    themeButton.addEventListener('click', () => {
        currentTheme = (currentTheme + 1) % themes.length;
        const theme = themes[currentTheme];
        uniforms.color_fil1_base.value.set(...theme.fil1_base);
        uniforms.color_fil1_glow.value.set(...theme.fil1_glow);
        uniforms.color_fil2_base.value.set(...theme.fil2_base);
        uniforms.color_fil2_glow.value.set(...theme.fil2_glow);
        uniforms.color_core.value.set(...theme.core);
        uniforms.color_stars.value.set(...theme.stars);
    });
    function onWindowResize() {
        const width = window.innerWidth;
        const height = window.innerHeight;
        renderer.setPixelRatio(window.devicePixelRatio);
        renderer.setSize(width, height);
        uniforms.u_resolution.value.x = renderer.domElement.width;
        uniforms.u_resolution.value.y = renderer.domElement.height;
    }
    function animate() {
        requestAnimationFrame(animate);
        uniforms.u_time.value = clock.getElapsedTime();
        renderer.render(scene, camera);
    }
    onWindowResize();
    window.addEventListener('resize', onWindowResize, false);
    animate();
</script>
