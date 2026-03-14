//!HOOK MAIN
//!BIND HOOKED
//!DESC Cyberpunk — neon-drenched dystopian aesthetic with glitch elements

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.04;
    vec2 texel = 1.0 / HOOKED_size;
    vec4 col = HOOKED_tex(uv);

    // ── Chromatic aberration (strong) ──
    float ca_amount = 0.004 + sin(t * 3.0) * 0.001;
    vec2 ca_dir = normalize(uv - 0.5 + 0.001);
    float r = HOOKED_tex(uv + ca_dir * ca_amount).r;
    float g = col.g;
    float b = HOOKED_tex(uv - ca_dir * ca_amount).b;
    col.rgb = vec3(r, g, b);

    // ── Neon color grading: push to cyan/magenta ──
    float lum = dot(col.rgb, vec3(0.299, 0.587, 0.114));

    // Shadows → deep blue, midtones → magenta, highlights → cyan
    vec3 grade;
    if (lum < 0.3) {
        grade = mix(vec3(0.02, 0.02, 0.1), vec3(0.15, 0.05, 0.25), lum / 0.3);
    } else if (lum < 0.6) {
        grade = mix(vec3(0.15, 0.05, 0.25), vec3(0.1, 0.4, 0.5), (lum - 0.3) / 0.3);
    } else {
        grade = mix(vec3(0.1, 0.4, 0.5), vec3(0.4, 0.9, 0.95), (lum - 0.6) / 0.4);
    }

    col.rgb = mix(col.rgb, grade, 0.5);

    // ── Boost saturation on neon colors ──
    float avg = (col.r + col.g + col.b) / 3.0;
    col.rgb = mix(vec3(avg), col.rgb, 1.6);

    // ── Neon edge glow ──
    float edge = 0.0;
    float c_lum = dot(col.rgb, vec3(0.33));
    for (int dx = -1; dx <= 1; dx++) {
        for (int dy = -1; dy <= 1; dy++) {
            if (dx == 0 && dy == 0) continue;
            vec2 offset = vec2(float(dx), float(dy)) * texel;
            float n = dot(HOOKED_tex(uv + offset).rgb, vec3(0.33));
            edge += abs(c_lum - n);
        }
    }
    edge /= 8.0;
    edge = smoothstep(0.02, 0.08, edge);

    // Neon glow color cycling
    vec3 neon = vec3(
        sin(t * 2.0) * 0.5 + 0.5,
        sin(t * 2.0 + 2.0) * 0.5 + 0.5,
        sin(t * 2.0 + 4.0) * 0.5 + 0.5
    );
    col.rgb += neon * edge * 0.5;

    // ── Horizontal glitch lines (occasional) ──
    float glitch_seed = floor(t * 5.0);
    float glitch_y = fract(sin(glitch_seed * 127.1) * 43758.5453);
    float glitch_line = smoothstep(0.005, 0.0, abs(uv.y - glitch_y));
    if (glitch_line > 0.1) {
        float shift = (fract(sin(glitch_seed * 311.7) * 43758.5453) - 0.5) * 0.1;
        col.rgb = HOOKED_tex(vec2(clamp(uv.x + shift, 0.0, 1.0), uv.y)).rgb;
        col.rgb *= vec3(1.2, 0.8, 1.2);  // Magenta tint on glitched line
    }

    // ── Scanline overlay ──
    float scan = sin(uv.y * HOOKED_size.y * 1.5) * 0.5 + 0.5;
    col.rgb *= mix(0.85, 1.0, scan);

    return vec4(col.rgb, 1.0);
}
