<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Aetheric Blueprint</title>
<style>
    body {
        margin: 0;
        padding: 0;
        overflow: hidden;
        background-color: #02000a;
        display: flex;
        justify-content: center;
        align-items: center;
        min-height: 100vh;
    }
    canvas {
        display: block;
        cursor: pointer;
        width: 100%;
        height: 100%;
    }
    .info {
        position: absolute;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        color: rgba(255, 255, 255, 0.4);
        font-family: 'Inter', 'Helvetica Neue', sans-serif;
        font-size: 14px;
        text-align: center;
        pointer-events: none;
        text-shadow: 0 0 5px rgba(0, 0, 0, 0.5);
    }
</style>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400&display=swap" rel="stylesheet">
<script type="importmap">
    {
        "imports": {
            "three": "https://cdnjs.cloudflare.com/ajax/libs/three.js/0.163.0/three.module.js"
        }
    }
</script>
<div class="info">Click to activate the blueprint</div>
<script type="module">
    import * as THREE from 'three';

    let scene, camera, renderer, material, quad;
    const clock = new THREE.Clock();

    function init() {
        scene = new THREE.Scene();
        camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 10);
        camera.position.z = 1;

        renderer = new THREE.WebGLRenderer({
            antialias: true,
            powerPreference: 'high-performance'
        });
        renderer.setSize(window.innerWidth, window.innerHeight);
        document.body.appendChild(renderer.domElement);

        const uniforms = {
            time: { value: 0.0 },
            resolution: { value: new THREE.Vector2(window.innerWidth, window.innerHeight) },
            clickTime: { value: -100.0 }
        };

        material = new THREE.ShaderMaterial({
            uniforms: uniforms,
            vertexShader: `
                varying vec2 vUv;
                void main() {
                    vUv = uv;
                    gl_Position = vec4(position, 1.0);
                }
            `,
            fragmentShader: `
                precision highp float;

                uniform vec2 resolution;
                uniform float time;
                uniform float clickTime;
                
                varying vec2 vUv;

                #define PI 3.14159265359
                #define TWO_PI (2.0 * PI)

                mat2 rotate2d(float angle) { return mat2(cos(angle), -sin(angle), sin(angle), cos(angle)); }
                
                float line(float a, float b, float width){
                    return smoothstep(a - width, a, b) - smoothstep(a, a + width, b);
                }
                
                float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
                vec3 hsv2rgb(vec3 c) {
                    vec4 K = vec4(1.0, 2.0 / 3.0, 1.0 / 3.0, 3.0);
                    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
                    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
                }

                float getBlueprintPattern(vec2 uv) {
                    float pattern = 0.0;
                    float dist = length(uv);
                    float angle = atan(uv.y, uv.x);
                    
                    vec2 hex_uv = rotate2d(time * 0.05) * uv;
                    for(float i = 0.0; i < 6.0; i++) {
                        float hex_angle = i * PI / 3.0;
                        pattern = max(pattern, line(dot(hex_uv, vec2(cos(hex_angle), sin(hex_angle))), 0.0, 0.003));
                    }
                    
                    vec2 tri_uv = rotate2d(-time * 0.1) * uv;
                    for(float i = 0.0; i < 3.0; i++) {
                        float tri_angle = i * TWO_PI / 3.0;
                        vec2 p = rotate2d(tri_angle) * tri_uv;
                        pattern = max(pattern, line(p.y, -0.25, 0.003));
                        pattern = max(pattern, line(p.y, 0.25, 0.003));
                    }
                    
                    for(float i = 1.0; i < 8.0; i++){
                        float radius = i * 0.12;
                        if (dist > radius - 0.01 && dist < radius + 0.01) {
                            float glyph_angle = floor(angle * (10.0 + i * 2.0)) / (10.0 + i * 2.0);
                            float glyph_time_offset = sin(glyph_angle * 50.0 + time * i);
                            if (glyph_time_offset > 0.5) {
                                pattern = max(pattern, line(dist, radius, 0.003));
                            }
                        }
                    }

                    vec2 etch_uv = uv * 30.0;
                    pattern += (sin(etch_uv.x) + cos(etch_uv.y)) * 0.05 * (1.0 - smoothstep(0.8, 0.9, dist));
                    
                    return clamp(pattern, 0.0, 1.0);
                }

                void main() {
                    vec2 uv = (gl_FragCoord.xy * 2.0 - resolution.xy) / min(resolution.x, resolution.y);
                    vec2 distorted_uv = uv;

                    float timeSinceClick = time - clickTime;
                    float activation_wave = 0.0;
                    float core_flash = 0.0;
                    vec3 bloomGlow = vec3(0.0);
                    
                    float clickEffectDuration = 2.5;
                    if (timeSinceClick > 0.0 && timeSinceClick < clickEffectDuration) {
                        float progress = timeSinceClick / clickEffectDuration;
                        float effect_intensity = sin(progress * PI);

                        float wave_radius = progress * 1.5;
                        float wave = smoothstep(wave_radius - 0.1, wave_radius, length(uv)) - smoothstep(wave_radius, wave_radius + 0.1, length(uv));
                        activation_wave = wave * effect_intensity;
                        
                        if (length(uv) > 0.0) {
                            distorted_uv -= normalize(uv) * activation_wave * 0.1;
                        }
                        
                        core_flash = pow(1.0 - progress, 15.0) * 0.8;

                        float bloom_amount = pow(wave, 2.0) * effect_intensity;
                        vec3 bloom_color = vec3(0.7, 0.8, 1.0);
                        bloomGlow = bloom_color * bloom_amount * 10.0;
                    }
                    
                    float patternValue = getBlueprintPattern(distorted_uv);
                    
                    vec3 finalColor = vec3(hash(vUv * 500.0) * 0.05);
                    float hue = 0.6 + fract(length(uv) * 0.5 - time * 0.1);
                    vec3 blueprint_color = hsv2rgb(vec3(hue, 0.7, 1.0));
                    vec3 activation_color = vec3(1.0, 0.9, 0.7);
                    
                    finalColor += patternValue * blueprint_color * 0.5;
                    
                    finalColor += activation_wave * patternValue * activation_color * 5.0;

                    finalColor += bloomGlow * patternValue;

                    finalColor += pow(patternValue, 3.0) * blueprint_color * 0.3;
                    finalColor += core_flash;

                    gl_FragColor = vec4(clamp(finalColor, 0.0, 1.0), 1.0);
                }
            `
        });

        quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material);
        scene.add(quad);

        renderer.domElement.addEventListener('click', (event) => {
            material.uniforms.clickTime.value = clock.getElapsedTime(); 
        }, false);
    }

    function onWindowResize() {
        const width = window.innerWidth;
        const height = window.innerHeight;
        renderer.setSize(width, height);
        camera.updateProjectionMatrix();
        material.uniforms.resolution.value.set(width, height);
    }

    function animate() {
        requestAnimationFrame(animate);
        material.uniforms.time.value = clock.getElapsedTime(); 
        renderer.render(scene, camera);
    }

    init();
    window.addEventListener('resize', onWindowResize);
    animate();
</script>