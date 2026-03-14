//!HOOK MAIN
//!BIND HOOKED
//!DESC Cartoon — cel-shaded toon look with thick ink outlines

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 texel = 1.0 / HOOKED_size;
    vec4 col = HOOKED_tex(uv);

    // ── Cel-shading: quantize colors into distinct bands ──
    // Convert to HSV-like space for better quantization
    float lum = dot(col.rgb, vec3(0.299, 0.587, 0.114));

    // Quantize luminance into 4 distinct zones (cartoon shading steps)
    float steps = 4.0;
    float quant_lum = floor(lum * steps + 0.5) / steps;
    float lum_ratio = (lum > 0.001) ? quant_lum / lum : 1.0;

    vec3 cel = col.rgb * lum_ratio;

    // Boost saturation slightly for cartoon pop
    float avg = (cel.r + cel.g + cel.b) / 3.0;
    cel = mix(vec3(avg), cel, 1.4);

    // ── Thick ink outlines via multi-directional edge detection ──
    float edge = 0.0;
    // 8-directional Sobel for thick edges
    for (int dx = -1; dx <= 1; dx++) {
        for (int dy = -1; dy <= 1; dy++) {
            if (dx == 0 && dy == 0) continue;
            vec2 offset = vec2(float(dx), float(dy)) * texel * 1.5;
            float neighbor_lum = dot(HOOKED_tex(uv + offset).rgb, vec3(0.299, 0.587, 0.114));
            edge += abs(lum - neighbor_lum);
        }
    }
    edge /= 8.0;

    // Thick, crisp outlines
    float outline = smoothstep(0.02, 0.06, edge);

    // Second pass: even thicker outlines at 2px radius
    float edge2 = 0.0;
    for (int dx = -2; dx <= 2; dx += 2) {
        for (int dy = -2; dy <= 2; dy += 2) {
            if (dx == 0 && dy == 0) continue;
            vec2 offset = vec2(float(dx), float(dy)) * texel;
            float neighbor_lum = dot(HOOKED_tex(uv + offset).rgb, vec3(0.299, 0.587, 0.114));
            edge2 += abs(lum - neighbor_lum);
        }
    }
    edge2 /= 8.0;
    outline = max(outline, smoothstep(0.03, 0.08, edge2) * 0.7);

    // Ink color: very dark, slightly warm
    vec3 ink = vec3(0.08, 0.06, 0.05);

    // Blend: cartoon colors with ink outlines on top
    vec3 result = mix(cel, ink, outline);

    return vec4(result, 1.0);
}
