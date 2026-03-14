<style>
* { margin: 0; padding: 0; overflow: hidden; background: #000; }
canvas { width: 100vw; height: 100vh; display: block; }
</style>

<canvas id="canvas"></canvas>

<script>
const canvas = document.getElementById('canvas');
const gl = canvas.getContext('webgl2');
if (!gl) {
  console.error("WebGL2 is not supported in your browser.");
}

const vsSource = `#version 300 es
in vec4 a_pos;
void main() {
  gl_Position = a_pos;
}
`;

const fsSource = `#version 300 es
precision highp float;
uniform vec2 u_res;
uniform float u_time;
out vec4 fragColor;

vec3 hsv2rgb(vec3 c) {
    vec3 k = vec3(1.0, 2.0/3.0, 1.0/3.0);
    vec3 p = abs(fract(c.xxx + k) * 6.0 - 3.0);
    return c.z * mix(vec3(1.0), clamp(p - 1.0, 0.0, 1.0), c.y);
}

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_res.xy) / u_res.y;
    float r = length(uv);
    float theta = atan(uv.y, uv.x);
    
    vec3 colorAcc = vec3(0.0);
    float t = u_time * 0.4;
    
    for(float i = 1.0; i < 12.0; i++) {
        vec2 p = uv * (1.0 + i * 0.15);
        float twist = sin(t + i * 0.2) * 2.0;
        p *= mat2(cos(twist), -sin(twist), sin(twist), cos(twist));
        
        float modTheta = mod(theta * (2.0 + sin(t + i * 0.3)) + t, 6.2831853);
        float modR = pow(r, 1.0 + cos(t * 0.5 + i * 0.2) * 0.2);
        
        float pattern1 = sin(modTheta * 8.0 + t) * cos(modR * 15.0 + t * 0.5);
        float pattern2 = cos(length(p) * 10.0 - t) * sin(atan(p.y, p.x) * 5.0);
        float pattern = pattern1 * pattern2;
        
        float weight = smoothstep(0.8, 0.0, modR * (1.0 + 0.2 * sin(t + i)));
        weight *= 1.0 + 0.5 * sin(t * 2.0 + i * 0.5);
        
        vec3 color = hsv2rgb(vec3(
            mod(0.1 * i + t * 0.2, 1.0),  
            0.7 + 0.3 * sin(t + i * 0.5),  
            weight * abs(pattern) * 1.2     
        ));
        
        colorAcc += color * weight;
    }
    
    colorAcc *= 1.2;
    colorAcc = pow(colorAcc, vec3(0.4545));
    
    fragColor = vec4(colorAcc, 1.0);
}
`;

function compileShader(source, type) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        console.error("Shader compile error:", gl.getShaderInfoLog(shader));
    }
    return shader;
}

const vertexShader = compileShader(vsSource, gl.VERTEX_SHADER);
const fragmentShader = compileShader(fsSource, gl.FRAGMENT_SHADER);
const program = gl.createProgram();
gl.attachShader(program, vertexShader);
gl.attachShader(program, fragmentShader);
gl.linkProgram(program);
if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    console.error("Program link error:", gl.getProgramInfoLog(program));
}
gl.useProgram(program);

const vertices = new Float32Array([
    -1, -1,
     1, -1,
    -1,  1,
     1,  1
]);
const buffer = gl.createBuffer();
gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW);

const posAttrib = gl.getAttribLocation(program, "a_pos");
gl.enableVertexAttribArray(posAttrib);
gl.vertexAttribPointer(posAttrib, 2, gl.FLOAT, false, 0, 0);

const resUniform = gl.getUniformLocation(program, "u_res");
const timeUniform = gl.getUniformLocation(program, "u_time");

function resize() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.uniform2f(resUniform, canvas.width, canvas.height);
}
window.addEventListener("resize", resize);
resize();

function render(time) {
    time *= 0.001;
    gl.uniform1f(timeUniform, time);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    requestAnimationFrame(render);
}
requestAnimationFrame(render);
</script>
