//!HOOK MAIN
//!BIND HOOKED
//!DESC Pop Art — Warhol-style bold posterization with CMYK halftone dots

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 texel = 1.0 / HOOKED_size;
    float t = float(frame) * 0.003;
    vec4 col = HOOKED_tex(uv);

    // ── Extreme posterization (3-4 color levels) ──
    float levels = 4.0;
    vec3 poster = floor(col.rgb * levels + 0.5) / levels;

    // Boost saturation dramatically for pop art vibrancy
    float lum = dot(poster, vec3(0.299, 0.587, 0.114));
    poster = mix(vec3(lum), poster, 2.5);
    poster = clamp(poster, 0.0, 1.0);

    // ── CMYK halftone separation ──
    // Convert to CMY
    vec3 cmy = 1.0 - poster;
    float k = min(cmy.r, min(cmy.g, cmy.b));

    // Separate CMYK channels with offset angles (like print registration)
    float dot_size = 5.0;

    // Cyan dots at 15°
    float angle_c = 0.2618;  // 15 degrees
    vec2 rot_c = vec2(cos(angle_c), sin(angle_c));
    vec2 uv_c = vec2(dot(uv * HOOKED_size / dot_size, rot_c),
                      dot(uv * HOOKED_size / dot_size, vec2(-rot_c.y, rot_c.x)));
    vec2 cell_c = floor(uv_c) + 0.5;
    float dist_c = length(uv_c - cell_c);
    float dot_c = smoothstep(cmy.r * 0.5 + 0.02, cmy.r * 0.5 - 0.02, dist_c);

    // Magenta dots at 75°
    float angle_m = 1.309;  // 75 degrees
    vec2 rot_m = vec2(cos(angle_m), sin(angle_m));
    vec2 uv_m = vec2(dot(uv * HOOKED_size / dot_size, rot_m),
                      dot(uv * HOOKED_size / dot_size, vec2(-rot_m.y, rot_m.x)));
    vec2 cell_m = floor(uv_m) + 0.5;
    float dist_m = length(uv_m - cell_m);
    float dot_m = smoothstep(cmy.g * 0.5 + 0.02, cmy.g * 0.5 - 0.02, dist_m);

    // Yellow dots at 0°
    vec2 uv_y = uv * HOOKED_size / dot_size;
    vec2 cell_y = floor(uv_y) + 0.5;
    float dist_y = length(uv_y - cell_y);
    float dot_y = smoothstep(cmy.b * 0.5 + 0.02, cmy.b * 0.5 - 0.02, dist_y);

    // Key (black) dots at 45°
    float angle_k = 0.7854;  // 45 degrees
    vec2 rot_k = vec2(cos(angle_k), sin(angle_k));
    vec2 uv_k = vec2(dot(uv * HOOKED_size / dot_size, rot_k),
                      dot(uv * HOOKED_size / dot_size, vec2(-rot_k.y, rot_k.x)));
    vec2 cell_k = floor(uv_k) + 0.5;
    float dist_k = length(uv_k - cell_k);
    float dot_k = smoothstep(k * 0.5 + 0.02, k * 0.5 - 0.02, dist_k);

    // Reconstruct from CMYK dots on white paper
    vec3 result = vec3(1.0);
    result -= vec3(0.0, dot_c, dot_c);   // Cyan removes R
    result -= vec3(dot_m, 0.0, dot_m);   // Magenta removes G
    result -= vec3(dot_y, dot_y, 0.0);   // Yellow removes B
    result -= vec3(dot_k);               // Black removes all
    result = clamp(result, 0.0, 1.0);

    // ── Bold outlines ──
    float edge = 0.0;
    for (int dx = -1; dx <= 1; dx++) {
        for (int dy = -1; dy <= 1; dy++) {
            if (dx == 0 && dy == 0) continue;
            vec2 offset = vec2(float(dx), float(dy)) * texel * 1.5;
            float n_lum = dot(HOOKED_tex(uv + offset).rgb, vec3(0.33));
            edge += abs(lum - n_lum);
        }
    }
    edge /= 8.0;
    float outline = smoothstep(0.03, 0.10, edge);
    result = mix(result, vec3(0.0), outline * 0.85);

    return vec4(result, 1.0);
}
