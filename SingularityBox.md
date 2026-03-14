<meta charset="UTF-8" >
    <meta name="viewport" content = "width=device-width, initial-scale=1.0" >
        <title>Singularity Shader </title>
            <style>
    body {
    margin: 0;
    overflow: hidden;
    background: #000;
}
    canvas {
    display: block;
    width: 100vw;
    height: 100vh;
}
#info {
    position: absolute;
    top: 10px;
    left: 10px;
    color: #ffffff;
    font - family: monospace;
    font - size: 12px;
    pointer - events: none;
    z - index: 100;
    background: rgba(255, 255, 255, 0.1);
    backdrop - filter: blur(10px);
    -webkit - backdrop - filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.2);
    border - radius: 10px;
    padding: 10px;
    box - shadow: 0 4px 30px rgba(0, 0, 0, 0.1);
}
</style>
    < div id = "info" > Click / Tap for water - like distortion ripples </div>
        < script type = "importmap" >
        {
            "imports": {
                "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js"
            }
        }
            </script>
            < script type = "module" >
    import * as THREE from 'three';

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x000000);
const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
document.body.appendChild(renderer.domElement);

const time = { value: 0 };

const numRipples = 3;
const rippleCenters = [];
const rippleTimes = [];
let currentRippleIndex = 0;
for (let i = 0; i < numRipples; i++) {
    rippleCenters.push(new THREE.Vector2(0.5, 0.5));
    rippleTimes.push(-1.0);
}

function onPointer(event) {
    event.preventDefault();
    let clientX, clientY;
    if (event.type === 'touchstart') {
        clientX = event.touches[0].clientX;
        clientY = event.touches[0].clientY;
    } else {
        clientX = event.clientX;
        clientY = event.clientY;
    }
    const normX = clientX / window.innerWidth;
    const normY = 1.0 - (clientY / window.innerHeight);
    rippleCenters[currentRippleIndex].set(normX, normY);
    rippleTimes[currentRippleIndex] = time.value;
    currentRippleIndex = (currentRippleIndex + 1) % numRipples;
}
renderer.domElement.addEventListener('click', onPointer);
renderer.domElement.addEventListener('touchstart', onPointer, { passive: false });

const material = new THREE.ShaderMaterial({
    uniforms: {
        time: time,
        resolution: { value: new THREE.Vector2(window.innerWidth, window.innerHeight) },
        rippleCenter1: { value: rippleCenters[0] },
        rippleTime1: { value: rippleTimes[0] },
        rippleCenter2: { value: rippleCenters[1] },
        rippleTime2: { value: rippleTimes[1] },
        rippleCenter3: { value: rippleCenters[2] },
        rippleTime3: { value: rippleTimes[2] }
    },
    vertexShader: `
            varying vec2 vUv;
            void main() {
                vUv = uv;
                gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
            }
        `,
    fragmentShader: `
            uniform float time;
            uniform vec2 resolution;
            uniform vec2 rippleCenter1;
            uniform float rippleTime1;
            uniform vec2 rippleCenter2;
            uniform float rippleTime2;
            uniform vec2 rippleCenter3;
            uniform float rippleTime3;
            varying vec2 vUv;
        
            void main() {
                vec2 FC = gl_FragCoord.xy;
                vec2 r = resolution;
                vec4 o = vec4(0.0);
            
                vec2 distortedFC = FC;
                float rippleScale = 20.0;
            
                {
                    float age = time - rippleTime1;
                    if (age >= 0.0) {
                        vec2 delta = (FC / r - rippleCenter1) * 2.0;
                        float dist = length(delta);
                        if (dist > 0.0) {
                            float phase = dist * 30.0 - age * 20.0;
                            float wave = sin(phase) * exp(-age * 3.0) / (dist + 0.1);
                            vec2 offset = (delta / dist) * wave * rippleScale;
                            distortedFC += offset;
                        }
                    }
                }
                {
                    float age = time - rippleTime2;
                    if (age >= 0.0) {
                        vec2 delta = (FC / r - rippleCenter2) * 2.0;
                        float dist = length(delta);
                        if (dist > 0.0) {
                            float phase = dist * 30.0 - age * 20.0;
                            float wave = sin(phase) * exp(-age * 3.0) / (dist + 0.1);
                            vec2 offset = (delta / dist) * wave * rippleScale;
                            distortedFC += offset;
                        }
                    }
                }
                {
                    float age = time - rippleTime3;
                    if (age >= 0.0) {
                        vec2 delta = (FC / r - rippleCenter3) * 2.0;
                        float dist = length(delta);
                        if (dist > 0.0) {
                            float phase = dist * 30.0 - age * 20.0;
                            float wave = sin(phase) * exp(-age * 3.0) / (dist + 0.1);
                            vec2 offset = (delta / dist) * wave * rippleScale;
                            distortedFC += offset;
                        }
                    }
                }
            
                float wx = 1.4 + 0.2 * sin(time * 0.5);
                float wy = 1.0;
            
                for(float i = 0.0; i < 20.0; i++) {
                    float z = i;
                    float s;
                    float outerD;
                
                    vec3 p = z * normalize(vec3(distortedFC * 2.0 - vec2(r.x, r.y), r.y));
                    vec3 a = p;
                
                    vec2 rectCoord = abs(a.xy);
                    float rectDist = max(rectCoord.x / wx, rectCoord.y / wy);
                    float spiralRotation = time * 0.7 + 5.0 / (rectDist + 0.3);
                    float c = cos(spiralRotation);
                    float si = sin(spiralRotation);
                    a.xy = mat2(c, -si, si, c) * a.xy;
                
                    for(float dd = 2.0; dd < 8.0; dd += 1.0) {
                        float freq = dd + sin(time * 0.3 + i * 0.1);
                        a -= sin(a * freq + time + i).yzx / dd;
                    }
                
                    float dist = length(a.xy);
                    vec2 rectCoord2 = abs(a.xy);
                    float rectDist2 = max(rectCoord2.x / wx, rectCoord2.y / wy);
                    float angle = atan(a.y, a.x);
                    float spiralArms = sin(angle * 7.0 - rectDist2 * 4.0 + time * 1.5) * 0.8 + sin(angle * 3.0 + rectDist2 * 2.0 - time) * 0.3;
                    float noise = sin(a.x * 10.0 + time * 2.0) * cos(a.y * 10.0 + time * 3.0) * 0.05;
                    spiralArms += noise;
                 
                    s = a.z + a.y - time * 1.2;
                    outerD = abs(0.7 - dist + spiralArms * 0.25) + abs(cos(s * 1.5)) / 6.0 + abs(sin(s * 2.0)) / 8.0;
                    outerD = max(0.02, outerD);
                    z += outerD;
                
                    vec4 colorShift;
                    float pulse = sin(time * 2.0 + rectDist * 5.0) * 0.5 + 0.5;
                    if(rectDist < 0.5) {
                        colorShift = vec4(0.0, 2.5 * pulse, 8.0, 0.0);
                    } else if(rectDist < 1.0) {
                        colorShift = vec4(1.5 * pulse, 1.0, 7.5, 0.0);
                    } else if(rectDist < 1.5) {
                        colorShift = vec4(1.0, 0.0, 8.5 * pulse, 0.0);
                    } else {
                        colorShift = vec4(0.5 * pulse, 1.5, 7.0, 0.0);
                    }
                 
                    float glow = 1.0 / (outerD * outerD * 0.05 + 0.2);
                    o += (1.5 + glow * 1.5) * (cos(s - z + colorShift) + 1.0) / outerD;
                }
            
                o = o / 150.0;
                o = o / (1.0 + o);
                vec2 uv = FC / r - 0.5;
                float vig = 1.0 - length(uv) * 0.5;
                o.rgb *= vig;
                o.rgb = pow(o.rgb, vec3(0.9));
            
                gl_FragColor = o;
            }
        `
});

const geometry = new THREE.PlaneGeometry(2, 2);
const mesh = new THREE.Mesh(geometry, material);
scene.add(mesh);

window.addEventListener('resize', () => {
    const width = window.innerWidth;
    const height = window.innerHeight;
    renderer.setSize(width, height);
    material.uniforms.resolution.value.set(width, height);
});

function animate() {
    requestAnimationFrame(animate);
    time.value += 0.016;
    material.uniforms.rippleTime1.value = rippleTimes[0];
    material.uniforms.rippleTime2.value = rippleTimes[1];
    material.uniforms.rippleTime3.value = rippleTimes[2];
    for (let i = 0; i < numRipples; i++) {
        const age = time.value - rippleTimes[i];
        if (age > 5.0) {
            rippleTimes[i] = -1.0;
        }
    }
    material.uniforms.rippleCenter1.value.copy(rippleCenters[0]);
    material.uniforms.rippleCenter2.value.copy(rippleCenters[1]);
    material.uniforms.rippleCenter3.value.copy(rippleCenters[2]);
    renderer.render(scene, camera);
}

animate();
</script>