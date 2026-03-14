<style>
    * { margin: 0; padding: 0; }
    html, body {
        width: 100%;
        height: 100%;
        overflow: hidden;
    }
    canvas {
        display: block;
        background: #000;
        width: 100%;
        height: 100%;
    }
</style>

<canvas id="glcanvas"></canvas>

<script>
(function() {
    var canvas = document.getElementById("glcanvas");
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    var gl = canvas.getContext("webgl");
    if (!gl) {
        console.error("Unable to initialize WebGL.");
        return;
    }

    var vertexSrc = `
        attribute vec2 a_position;
        void main() {
            gl_Position = vec4(a_position, 0.0, 1.0);
        }
    `;

    var fragmentSrc = `
        precision highp float;
        uniform float iTime;
        uniform vec2 iResolution;

        float rand(vec2 n) {
            return fract(sin(dot(n, vec2(12.9898, 4.1414))) * 43758.5453);
        }

        vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
        vec2 mod289(vec2 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
        vec3 permute(vec3 x) { return mod289(((x*34.0)+1.0)*x); }
        float snoise(vec2 v) {
            const vec4 C = vec4(0.211324865405187, 0.366025403784439, -0.577350269189626, 0.024390243902439);
            vec2 i  = floor(v + dot(v, C.yy) );
            vec2 x0 = v -   i + dot(i, C.xx);
            vec2 i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
            vec4 x12 = x0.xyxy + C.xxzz;
            x12.xy -= i1;
            i = mod289(i);
            vec3 p = permute( permute( i.y + vec3(0.0, i1.y, 1.0 )) + i.x + vec3(0.0, i1.x, 1.0 ));
            vec3 m = max(0.5 - vec3(dot(x0,x0), dot(x12.xy,x12.xy), dot(x12.zw,x12.zw)), 0.0);
            m = m*m; m = m*m;
            vec3 x = 2.0 * fract(p * C.www) - 1.0;
            vec3 h = abs(x) - 0.5;
            vec3 ox = floor(x + 0.5);
            vec3 a0 = x - ox;
            m *= 1.79284291400159 - 0.85373472095314 * ( a0*a0 + h*h );
            vec3 g;
            g.x  = a0.x  * x0.x  + h.x  * x0.y;
            g.yz = a0.yz * x12.xz + h.yz * x12.yw;
            return 130.0 * dot(m, g);
        }

        float fbm(vec2 p) {
            float value = 0.0;
            float amplitude = 0.5;
            for (int i = 0; i < 6; i++) {
                value += amplitude * snoise(p);
                p *= 2.0;
                amplitude *= 0.5;
            }
            return value;
        }

        vec3 palette(float t, vec3 a, vec3 b, vec3 c, vec3 d) {
            return a + b * cos(6.28318 * (c * t + d));
        }

        void main() {
            vec2 uv = (2.0 * gl_FragCoord.xy - iResolution.xy) / iResolution.y;
            vec2 uv_orig = uv;
            float time = iTime * 0.3;
            vec2 displacement = vec2(fbm(uv + time), fbm(uv - time));
            uv += displacement * 0.12;

            float angle = atan(uv.y, uv.x);
            float radius = length(uv);
            float tunnel_depth = log(radius) - time * 1.5;

            float ring_pattern = fract(tunnel_depth * 0.3);
            float rings = smoothstep(0.8, 0.75, ring_pattern) * 0.5;

            float nebula_noise = snoise(vec2(angle * 6.0, tunnel_depth));
            nebula_noise = smoothstep(0.4, 1.0, nebula_noise);

            float ray_noise = snoise(vec2(angle * 25.0, time * 0.5));
            float rays = pow(max(0.0, ray_noise), 10.0);
            rays *= smoothstep(2.0, 0.0, radius);

            float combined_texture = nebula_noise + rings;

            vec3 col = palette(combined_texture,
                               vec3(0.5, 0.5, 0.5),
                               vec3(0.5, 0.5, 0.5),
                               vec3(1.0, 1.0, 0.5),
                               vec3(0.0, 0.10, 0.20 + time * 0.1));

            col += rays * vec3(1.0, 0.7, 0.3);

            col *= smoothstep(0.0, 0.15, radius);
            float star_noise = rand(floor(uv_orig * 250.0));
            float star_intensity = pow(star_noise, 40.0);
            vec3 stars = vec3(star_intensity);
            float star_speed = 1.0 + rand(floor(uv_orig * 50.0)) * 2.0;
            stars *= smoothstep(0.9, 0.0, length(uv_orig) + fract(time * star_speed) - 1.0);

            vec3 final_color = col + stars;
            final_color = pow(final_color, vec3(0.85));

            gl_FragColor = vec4(final_color, 1.0);
        }
    `;

    function compileShader(gl, source, type) {
        var shader = gl.createShader(type);
        gl.shaderSource(shader, source);
        gl.compileShader(shader);
        if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
            console.error("An error occurred compiling the shaders: " + gl.getShaderInfoLog(shader));
            gl.deleteShader(shader);
            return null;
        }
        return shader;
    }

    var vertexShader = compileShader(gl, vertexSrc, gl.VERTEX_SHADER);
    var fragmentShader = compileShader(gl, fragmentSrc, gl.FRAGMENT_SHADER);
    if (!vertexShader || !fragmentShader) {
        return;
    }

    var program = gl.createProgram();
    gl.attachShader(program, vertexShader);
    gl.attachShader(program, fragmentShader);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        console.error("Unable to initialize the shader program: " + gl.getProgramInfoLog(program));
        return;
    }
    gl.useProgram(program);

    var vertices = new Float32Array([ -1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1 ]);
    var buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, vertices, gl.STATIC_DRAW);

    var aPosition = gl.getAttribLocation(program, "a_position");
    gl.enableVertexAttribArray(aPosition);
    gl.vertexAttribPointer(aPosition, 2, gl.FLOAT, false, 0, 0);

    var iTimeLocation = gl.getUniformLocation(program, "iTime");
    var iResolutionLocation = gl.getUniformLocation(program, "iResolution");

    var startTime = Date.now();
    function render() {
        var currentTime = (Date.now() - startTime) / 1000.0;
        gl.uniform1f(iTimeLocation, currentTime);
        gl.uniform2f(iResolutionLocation, canvas.width, canvas.height);

        gl.viewport(0, 0, canvas.width, canvas.height);
        gl.clearColor(0.0, 0.0, 0.0, 1.0);
        gl.clear(gl.COLOR_BUFFER_BIT);
        gl.drawArrays(gl.TRIANGLES, 0, 6);

        requestAnimationFrame(render);
    }

    window.addEventListener("resize", function() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        gl.viewport(0, 0, canvas.width, canvas.height);
    });

    render();
})();
</script>

