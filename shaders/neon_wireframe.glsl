//!HOOK MAIN
//!BIND HOOKED
//!DESC Neon Wireframe — glowing neon contour lines on dark background

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 texel = 1.0 / HOOKED_size;
    float t = float(frame) * 0.015;
    vec4 col = HOOKED_tex(uv);

    float lum = dot(col.rgb, vec3(0.299, 0.587, 0.114));

    // ── Multi-scale edge extraction ──
    // Fine edges (1px)
    float edge_fine = 0.0;
    for (int dx = -1; dx <= 1; dx++) {
        for (int dy = -1; dy <= 1; dy++) {
            if (dx == 0 && dy == 0) continue;
            vec2 offset = vec2(float(dx), float(dy)) * texel;
            float n_lum = dot(HOOKED_tex(uv + offset).rgb, vec3(0.33));
            edge_fine += abs(lum - n_lum);
        }
    }
    edge_fine /= 8.0;

    // Medium edges (2px) — structural outlines
    float edge_med = 0.0;
    for (int dx = -2; dx <= 2; dx++) {
        for (int dy = -2; dy <= 2; dy++) {
            if (dx == 0 && dy == 0) continue;
            if (abs(dx) + abs(dy) > 3) continue;
            vec2 offset = vec2(float(dx), float(dy)) * texel;
            float n_lum = dot(HOOKED_tex(uv + offset).rgb, vec3(0.33));
            edge_med += abs(lum - n_lum);
        }
    }
    edge_med /= 16.0;

    // Coarse edges (4px) — glow base
    float edge_coarse = 0.0;
    for (int dx = -3; dx <= 3; dx += 2) {
        for (int dy = -3; dy <= 3; dy += 2) {
            vec2 offset = vec2(float(dx), float(dy)) * texel * 1.5;
            float n_lum = dot(HOOKED_tex(uv + offset).rgb, vec3(0.33));
            edge_coarse += abs(lum - n_lum);
        }
    }
    edge_coarse /= 12.0;

    // ── Edge masks ──
    float line_fine = smoothstep(0.02, 0.06, edge_fine);
    float line_med = smoothstep(0.015, 0.05, edge_med);
    float line_coarse = smoothstep(0.01, 0.04, edge_coarse);

    // ── Neon color cycling based on edge position ──
    // Use the original image hue to tint the neon
    vec3 img_color = col.rgb / (max(col.r, max(col.g, col.b)) + 0.001);

    // Animated hue rotation for electric feel
    float hue_shift = t * 0.3;
    vec3 neon_base = vec3(
        sin(hue_shift) * 0.5 + 0.5,
        sin(hue_shift + 2.094) * 0.5 + 0.5,
        sin(hue_shift + 4.189) * 0.5 + 0.5
    );

    // Mix image color influence with animated neon
    vec3 neon_color = mix(img_color, neon_base, 0.4);
    neon_color = normalize(neon_color + 0.001) * 1.5;  // Boost brightness

    // ── Glow layers ──
    // Inner core: bright white-ish
    vec3 core = vec3(1.0, 0.98, 0.95) * line_fine;

    // Middle glow: colored neon
    vec3 glow_mid = neon_color * line_med * 0.8;

    // Outer glow: soft, wider, colored
    vec3 glow_outer = neon_color * line_coarse * 0.3;

    // ── Animated pulse ──
    float pulse = 0.85 + sin(t * 2.0) * 0.15;

    // ── Dark background (reveals only the neon) ──
    // Keep a hint of the original image, very dark
    vec3 dark_bg = col.rgb * 0.06;

    // Optional: luminance-based contour lines (like topographic)
    float contour = abs(sin(lum * 12.0)) ;
    contour = smoothstep(0.95, 1.0, contour);
    vec3 contour_glow = neon_color * contour * 0.15;

    // ── Compose all layers ──
    vec3 result = dark_bg;
    result += glow_outer * pulse;
    result += glow_mid * pulse;
    result += core * pulse;
    result += contour_glow;

    // ── Bloom post-process (fake wide glow) ──
    vec3 bloom = vec3(0.0);
    float bw = 0.0;
    for (int dx = -2; dx <= 2; dx++) {
        for (int dy = -2; dy <= 2; dy++) {
            float w = exp(-float(dx*dx + dy*dy) / 4.0);
            vec2 offset = vec2(float(dx), float(dy)) * texel * 3.0;
            vec3 s = HOOKED_tex(uv + offset).rgb;
            float s_edge = dot(s, vec3(0.33));
            // Only bloom edges, not flat areas
            bloom += s * w * smoothstep(0.3, 0.6, abs(s_edge - lum) * 5.0);
            bw += w;
        }
    }
    bloom /= bw;
    result += bloom * neon_color * 0.2;

    return vec4(clamp(result, 0.0, 1.0), 1.0);
}
