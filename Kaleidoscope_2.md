<html lang="en">
<head>
<meta charset="UTF-8">
<title>Quantum Nebula - Pure Visual</title>
<style>
    body, html {
        margin: 0;
        padding: 0;
        width: 100vw;
        height: 100vh;
        overflow: hidden;
        background: #000;
        cursor: move; /* Kullanıcıya "sürükle" hissi vermek için */
    }

    canvas {
        display: block;
        width: 100%;
        height: 100%;
    }
</style>
</head>
<body>

<canvas id="canvas"></canvas>

<script type="x-shader/x-fragment" id="fragment-shader">#version 300 es
precision highp float;
out vec4 O;
uniform float time;
uniform vec2 resolution;
uniform vec2 move;

// --- QUANTUM NEBULA CORE ---
#define R resolution
#define T (time * 0.2)
#define ROT(a) mat2(cos(a), -sin(a), sin(a), cos(a))

// Estetik Renk Paleti
vec3 palette(float t) {
    vec3 a = vec3(0.5, 0.5, 0.5);
    vec3 b = vec3(0.5, 0.5, 0.5);
    vec3 c = vec3(1.0, 1.0, 1.0);
    vec3 d = vec3(0.263, 0.416, 0.557); 
    return a + b * cos(6.28318 * (c * t + d));
}

// 2D Rotation
vec2 rotate(vec2 v, float a) {
    float s = sin(a);
    float c = cos(a);
    return mat2(c, -s, s, c) * v;
}

void main() {
    // Koordinatları ayarla
    vec2 uv = (gl_FragCoord.xy * 2.0 - R) / min(R.x, R.y);
    vec2 uv0 = uv; 
    
    // ETKİLEŞİM: Fare hareketine göre uzayı bük (Kaleidoscope Dönüşü)
    // move.x ve move.y, farenin kümülatif hareketidir.
    uv = rotate(uv, length(move) * 0.002);

    vec3 finalColor = vec3(0.0);
    
    // Fraktal Döngü (Kaleidoscope Etkisi)
    for (float i = 0.0; i < 4.0; i++) {
        uv = fract(uv * 1.5) - 0.5;
        
        float d = length(uv) * exp(-length(uv0));
        
        // Renkler
        vec3 col = palette(length(uv0) + i * 0.4 + T);
        
        // Neon Halkalar
        d = sin(d * 8.0 + T) / 8.0;
        d = abs(d);
        
        // Parlama (Glow)
        d = pow(0.01 / d, 1.2);
        
        finalColor += col * d;
    }
    
    // Kontrast
    finalColor = pow(finalColor, vec3(1.4));
    
    O = vec4(finalColor, 1.0);
}
</script>

<script>
// --- MOTOR BAŞLATILIYOR ---
const canvas = document.getElementById('canvas');
let gl, program;
let startTime = Date.now();
let mouse = { dx: 0, dy: 0 }; // Kümülatif hareket

// Başlangıç
window.onload = () => {
    initGL();
    
    // Etkileşim: Fare veya Dokunmatik
    window.addEventListener('mousemove', e => {
        mouse.dx += e.movementX;
        mouse.dy += e.movementY;
    });
    
    // Mobilde de çalışsın diye touch event (basit versiyon)
    let lastX, lastY;
    window.addEventListener('touchstart', e => {
        lastX = e.touches[0].clientX;
        lastY = e.touches[0].clientY;
    });
    window.addEventListener('touchmove', e => {
        let x = e.touches[0].clientX;
        let y = e.touches[0].clientY;
        mouse.dx += (x - lastX);
        mouse.dy += (y - lastY);
        lastX = x;
        lastY = y;
    });

    window.addEventListener('resize', resize);
    render();
};

function initGL() {
    gl = canvas.getContext('webgl2');
    if (!gl) { 
        // Fallback for older browsers if needed, but keeping simple for now
        alert("Cihazınız WebGL2 desteklemiyor."); 
        return; 
    }
    
    resize();
    
    // Shader Kaynağını Al
    const fragSource = document.getElementById('fragment-shader').textContent.trim();
    createProgram(fragSource);
}

function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    gl.viewport(0, 0, canvas.width, canvas.height);
}

// Shader Derleme
function createShader(gl, type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        console.error(gl.getShaderInfoLog(shader));
        gl.deleteShader(shader);
        return null;
    }
    return shader;
}

function createProgram(fragSource) {
    const vsSource = `#version 300 es
        in vec4 position;
        void main() { gl_Position = position; }
    `;
    
    const vs = createShader(gl, gl.VERTEX_SHADER, vsSource);
    const fs = createShader(gl, gl.FRAGMENT_SHADER, fragSource);
    
    if (!vs || !fs) return;

    program = gl.createProgram();
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);

    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        console.error(gl.getProgramInfoLog(program));
        return;
    }

    // Tam Ekran Üçgen (Canvas'ı kaplamak için)
    const vertices = new Float32Array([-1, -1, 3, -1, -1, 3]);
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW);
    
    const positionLoc = gl.getAttribLocation(program, 'position');
    gl.enableVertexAttribArray(positionLoc);
    gl.vertexAttribPointer(positionLoc, 2, gl.FLOAT, false, 0, 0);
}

// Render Döngüsü
function render() {
    if (program) {
        gl.useProgram(program);
        
        // Uniform verilerini gönder
        gl.uniform1f(gl.getUniformLocation(program, 'time'), (Date.now() - startTime) / 1000);
        gl.uniform2f(gl.getUniformLocation(program, 'resolution'), canvas.width, canvas.height);
        gl.uniform2f(gl.getUniformLocation(program, 'move'), mouse.dx, mouse.dy);
        
        gl.drawArrays(gl.TRIANGLES, 0, 3);
    }
    requestAnimationFrame(render);
}
</script>
</body>
</html>

