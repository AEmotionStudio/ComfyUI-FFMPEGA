//!HOOK MAIN
//!BIND HOOKED
//!DESC VHS Analog Distortion Shader

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.03;

    // ── Horizontal jitter (tracking noise) ──
    float jitter = sin(uv.y * 50.0 + t * 7.0) * 0.002;
    jitter += sin(uv.y * 130.0 + t * 13.0) * 0.001;
    uv.x += jitter;

    // ── Vertical roll (occasional) ──
    float roll = step(0.98, fract(t * 0.1)) * 0.02;
    uv.y = fract(uv.y + roll);

    // ── Chroma bleed (offset R and B channels) ──
    float offset = 0.003 + sin(t * 2.0) * 0.001;
    float r = HOOKED_tex(vec2(uv.x + offset, uv.y)).r;
    float g = HOOKED_tex(uv).g;
    float b = HOOKED_tex(vec2(uv.x - offset, uv.y)).b;

    vec3 col = vec3(r, g, b);

    // ── Reduce saturation slightly ──
    float luma = dot(col, vec3(0.299, 0.587, 0.114));
    col = mix(vec3(luma), col, 0.75);

    // ── Scanlines (lighter than CRT) ──
    float scanline = sin(uv.y * HOOKED_size.y * 3.14159) * 0.5 + 0.5;
    col *= mix(1.0, scanline, 0.12);

    // ── Film grain / noise ──
    float noise = fract(sin(dot(uv + t, vec2(12.9898, 78.233))) * 43758.5453);
    col += (noise - 0.5) * 0.06;

    // ── Slight warm tint ──
    col.r += 0.02;
    col.b -= 0.02;

    return vec4(clamp(col, 0.0, 1.0), 1.0);
}
