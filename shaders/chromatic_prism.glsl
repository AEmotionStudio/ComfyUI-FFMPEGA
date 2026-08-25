//!HOOK MAIN
//!BIND HOOKED
//!DESC Chromatic Prism — prismatic rainbow edge dispersion with bloom

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 texel = 1.0 / HOOKED_size;
    float t = float(frame) * 0.01;
    vec4 col = HOOKED_tex(uv);

    // ── Edge detection for dispersion strength ──
    float lum = dot(col.rgb, vec3(0.299, 0.587, 0.114));
    float lum_l = dot(HOOKED_tex(uv + vec2(-texel.x * 2.0, 0.0)).rgb, vec3(0.33));
    float lum_r = dot(HOOKED_tex(uv + vec2(texel.x * 2.0, 0.0)).rgb, vec3(0.33));
    float lum_u = dot(HOOKED_tex(uv + vec2(0.0, -texel.y * 2.0)).rgb, vec3(0.33));
    float lum_d = dot(HOOKED_tex(uv + vec2(0.0, texel.y * 2.0)).rgb, vec3(0.33));

    float gx = lum_r - lum_l;
    float gy = lum_d - lum_u;
    float edge = sqrt(gx*gx + gy*gy);
    vec2 edge_dir = normalize(vec2(gx, gy) + 0.0001);

    // ── Chromatic dispersion (different offsets per channel) ──
    // Dispersion strength increases with edge contrast
    float dispersion = edge * 12.0;
    dispersion *= (1.0 + sin(t * 0.8) * 0.15);  // Subtle animated pulsing

    // Sample each channel at different offsets along the edge normal
    vec2 offset_r = edge_dir * texel * dispersion * 1.5;
    vec2 offset_g = vec2(0.0);  // Green stays centered
    vec2 offset_b = -edge_dir * texel * dispersion * 1.5;

    float r = HOOKED_tex(uv + offset_r).r;
    float g = HOOKED_tex(uv + offset_g).g;
    float b = HOOKED_tex(uv + offset_b).b;

    // ── Extra spectral channels for rainbow effect ──
    // Sample intermediate wavelengths (orange, cyan, violet)
    vec2 offset_orange = edge_dir * texel * dispersion * 1.0;
    vec2 offset_cyan = -edge_dir * texel * dispersion * 0.75;
    vec2 offset_violet = -edge_dir * texel * dispersion * 2.0;

    vec3 s_orange = HOOKED_tex(uv + offset_orange).rgb;
    vec3 s_cyan = HOOKED_tex(uv + offset_cyan).rgb;
    vec3 s_violet = HOOKED_tex(uv + offset_violet).rgb;

    // Blend spectral samples into RGB
    float orange_contrib = (s_orange.r + s_orange.g * 0.5) * 0.15;
    float cyan_contrib = (s_cyan.g + s_cyan.b) * 0.5 * 0.15;
    float violet_contrib = (s_violet.r * 0.5 + s_violet.b) * 0.15;

    vec3 dispersed = vec3(r + orange_contrib, g + cyan_contrib * 0.3, b + violet_contrib);

    // ── Bloom on bright edges (prism catches light) ──
    float bright_edge = edge * smoothstep(0.5, 0.8, lum);
    vec3 bloom = vec3(0.0);
    float bloom_weight = 0.0;

    for (int dx = -3; dx <= 3; dx++) {
        for (int dy = -3; dy <= 3; dy++) {
            float w = exp(-float(dx*dx + dy*dy) / 6.0);
            vec3 s = HOOKED_tex(uv + vec2(float(dx), float(dy)) * texel * 2.0).rgb;
            float s_lum = dot(s, vec3(0.299, 0.587, 0.114));
            // Only bloom bright pixels
            bloom += s * smoothstep(0.6, 0.9, s_lum) * w;
            bloom_weight += w;
        }
    }
    bloom /= bloom_weight;

    // ── Compose: base + dispersion on edges + bloom ──
    float edge_mask = smoothstep(0.02, 0.12, edge);
    vec3 result = mix(col.rgb, dispersed, edge_mask * 0.8);
    result += bloom * bright_edge * 2.0;

    // Subtle rainbow tint on edges
    float rainbow = sin(dot(uv * HOOKED_size, edge_dir) * 0.3 + t) * 0.5 + 0.5;
    vec3 rainbow_color = vec3(
        sin(rainbow * 6.28) * 0.5 + 0.5,
        sin(rainbow * 6.28 + 2.09) * 0.5 + 0.5,
        sin(rainbow * 6.28 + 4.19) * 0.5 + 0.5
    );
    result += rainbow_color * edge_mask * 0.08;

    return vec4(clamp(result, 0.0, 1.0), 1.0);
}
