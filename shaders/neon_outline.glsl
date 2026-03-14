//!HOOK MAIN
//!BIND HOOKED
//!DESC Neon Outline — glowing neon contour lines with animated pulse

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 texel = 1.0 / HOOKED_size;
    float t = float(frame) * 0.04;
    vec4 col = HOOKED_tex(uv);

    // Multi-radius edge detection for varying outline thickness
    float edge_thin = 0.0;
    float edge_thick = 0.0;

    // Thin outline (1px Sobel)
    float c = dot(col.rgb, vec3(0.299, 0.587, 0.114));
    for (int dx = -1; dx <= 1; dx++) {
        for (int dy = -1; dy <= 1; dy++) {
            if (dx == 0 && dy == 0) continue;
            vec2 offset = vec2(float(dx), float(dy)) * texel;
            float n = dot(HOOKED_tex(uv + offset).rgb, vec3(0.299, 0.587, 0.114));
            edge_thin += abs(c - n);
        }
    }
    edge_thin /= 8.0;
    edge_thin = smoothstep(0.02, 0.08, edge_thin);

    // Thick outline (3px radius for glow bloom)
    for (int dx = -3; dx <= 3; dx++) {
        for (int dy = -3; dy <= 3; dy++) {
            if (dx == 0 && dy == 0) continue;
            if (abs(dx) + abs(dy) > 5) continue;
            vec2 offset = vec2(float(dx), float(dy)) * texel;
            float n = dot(HOOKED_tex(uv + offset).rgb, vec3(0.299, 0.587, 0.114));
            edge_thick += abs(c - n);
        }
    }
    edge_thick /= 36.0;
    edge_thick = smoothstep(0.01, 0.05, edge_thick);

    // Animated neon color cycling
    vec3 neon1 = vec3(1.0, 0.1, 0.5);   // hot pink
    vec3 neon2 = vec3(0.1, 0.5, 1.0);   // electric blue
    vec3 neon3 = vec3(0.2, 1.0, 0.5);   // mint green
    float phase = sin(t * 0.5) * 0.5 + 0.5;
    vec3 neon_color = mix(mix(neon1, neon2, phase), neon3, sin(t * 0.3) * 0.5 + 0.5);

    // Animated pulse
    float pulse = sin(t * 3.0) * 0.15 + 0.85;

    // Core outline: bright white
    float core = edge_thin * pulse;
    // Glow bloom: colored, softer
    float glow = edge_thick * pulse * 0.6;

    vec3 result = col.rgb;
    // Additive glow bloom first
    result += neon_color * glow * 2.0;
    // Sharp white core on top
    result += vec3(1.0) * core * 1.5;

    return vec4(result, 1.0);
}
