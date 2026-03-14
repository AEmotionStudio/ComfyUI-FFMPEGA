//!HOOK MAIN
//!BIND HOOKED
//!DESC RGB Glitch / Channel Split Shader

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.05;

    // ── Glitch trigger — intermittent bursts ──
    float glitchStrength = step(0.92, fract(sin(floor(t * 3.0) * 43.17) * 0.5 + 0.5));

    // ── RGB channel offset ──
    float offsetX = glitchStrength * 0.01 * sin(t * 17.0 + uv.y * 40.0);
    float offsetY = glitchStrength * 0.005 * cos(t * 23.0 + uv.x * 30.0);

    float r = HOOKED_tex(vec2(uv.x + offsetX, uv.y + offsetY)).r;
    float g = HOOKED_tex(uv).g;
    float b = HOOKED_tex(vec2(uv.x - offsetX, uv.y - offsetY)).b;

    vec3 col = vec3(r, g, b);

    // ── Horizontal slice displacement ──
    float sliceY = floor(uv.y * 30.0) / 30.0;
    float sliceRand = fract(sin(sliceY * 127.1 + floor(t * 5.0) * 311.7) * 43758.5);
    if (sliceRand > 0.95) {
        float shift = (sliceRand - 0.95) * 2.0 * sign(sin(t * 100.0));
        vec2 shiftUV = vec2(uv.x + shift * 0.1, uv.y);
        col = HOOKED_tex(shiftUV).rgb;
    }

    // ── Occasional color inversion on glitch ──
    float invTrigger = step(0.97, fract(sin(floor(t * 2.0) * 91.7) * 0.5 + 0.5));
    if (invTrigger > 0.5 && glitchStrength > 0.5) {
        float band = step(0.4, uv.y) * step(uv.y, 0.6);
        col = mix(col, 1.0 - col, band * 0.7);
    }

    return vec4(clamp(col, 0.0, 1.0), 1.0);
}
