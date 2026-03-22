//!HOOK MAIN
//!BIND HOOKED
//!DESC Comic Book — Ben-Day halftone dots with heavy Kirby-style bold outlines

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 texel = 1.0 / HOOKED_size;
    float t = float(frame) * 0.002;
    vec4 col = HOOKED_tex(uv);

    float lum = dot(col.rgb, vec3(0.299, 0.587, 0.114));

    // ── Heavy posterization (4 levels for comic look) ──
    vec3 poster = floor(col.rgb * 4.0 + 0.5) / 4.0;

    // ── Ben-Day dots (classic comic printing) ──
    float dot_size = 4.0;
    vec2 dot_uv = uv * HOOKED_size / dot_size;
    vec2 dot_cell = floor(dot_uv) + 0.5;
    float dot_dist = length(dot_uv - dot_cell);

    // Dot radius proportional to darkness per channel
    float r_radius = (1.0 - poster.r) * 0.48;
    float g_radius = (1.0 - poster.g) * 0.48;
    float b_radius = (1.0 - poster.b) * 0.48;

    // Offset dot grids slightly per channel (avoid moiré)
    vec2 dot_uv_r = (uv + vec2(0.001, 0.0)) * HOOKED_size / dot_size;
    vec2 dot_uv_b = (uv + vec2(0.0, 0.001)) * HOOKED_size / dot_size;
    vec2 dot_cell_r = floor(dot_uv_r) + 0.5;
    vec2 dot_cell_b = floor(dot_uv_b) + 0.5;

    float r = smoothstep(r_radius + 0.03, r_radius - 0.03, length(dot_uv_r - dot_cell_r));
    float g = smoothstep(g_radius + 0.03, g_radius - 0.03, dot_dist);
    float b = smoothstep(b_radius + 0.03, b_radius - 0.03, length(dot_uv_b - dot_cell_b));

    // White paper where no dots
    vec3 halftone = vec3(1.0) - vec3(1.0 - r, 1.0 - g, 1.0 - b) * col.rgb;
    // Simplify: use dots to modulate posterized color on white
    vec3 result = mix(vec3(1.0), poster, vec3(
        smoothstep(r_radius + 0.03, r_radius - 0.03, length(dot_uv_r - dot_cell_r)),
        smoothstep(g_radius + 0.03, g_radius - 0.03, dot_dist),
        smoothstep(b_radius + 0.03, b_radius - 0.03, length(dot_uv_b - dot_cell_b))
    ));

    // ── Multi-scale bold outlines (Kirby-style thick ink) ──
    // Inner outline (fine detail)
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

    // Outer outline (bold strokes)
    float edge_bold = 0.0;
    for (int dx = -2; dx <= 2; dx++) {
        for (int dy = -2; dy <= 2; dy++) {
            if (dx == 0 && dy == 0) continue;
            vec2 offset = vec2(float(dx), float(dy)) * texel * 1.5;
            float n_lum = dot(HOOKED_tex(uv + offset).rgb, vec3(0.33));
            edge_bold += abs(lum - n_lum);
        }
    }
    edge_bold /= 24.0;

    // Extra bold at 3px
    float edge_extra = 0.0;
    for (int dx = -3; dx <= 3; dx += 2) {
        for (int dy = -3; dy <= 3; dy += 2) {
            if (dx == 0 && dy == 0) continue;
            vec2 offset = vec2(float(dx), float(dy)) * texel;
            float n_lum = dot(HOOKED_tex(uv + offset).rgb, vec3(0.33));
            edge_extra += abs(lum - n_lum);
        }
    }
    edge_extra /= 12.0;

    float outline = smoothstep(0.02, 0.06, edge_fine);
    outline = max(outline, smoothstep(0.03, 0.08, edge_bold) * 0.85);
    outline = max(outline, smoothstep(0.04, 0.10, edge_extra) * 0.7);

    // Ink black outlines
    result = mix(result, vec3(0.02), outline);

    // Boost saturation for comic vibrancy
    float avg = (result.r + result.g + result.b) / 3.0;
    result = mix(vec3(avg), result, 1.6);

    return vec4(clamp(result, 0.0, 1.0), 1.0);
}
