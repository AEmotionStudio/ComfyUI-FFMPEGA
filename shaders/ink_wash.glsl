//!HOOK MAIN
//!BIND HOOKED
//!DESC Ink Wash — East Asian sumi-e ink painting with bleed and wash

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.015;
    vec2 texel = 1.0 / HOOKED_size;

    // ── Ink wash relies on luminance gradients ──
    vec4 col = HOOKED_tex(uv);
    float lum = dot(col.rgb, vec3(0.299, 0.587, 0.114));

    // Edge detection for ink strokes
    float edge = 0.0;
    for (int dx = -1; dx <= 1; dx++) {
        for (int dy = -1; dy <= 1; dy++) {
            if (dx == 0 && dy == 0) continue;
            vec2 offset = vec2(float(dx), float(dy)) * texel * 2.0;
            float n_lum = dot(HOOKED_tex(uv + offset).rgb, vec3(0.299, 0.587, 0.114));
            edge += abs(lum - n_lum);
        }
    }
    edge /= 8.0;

    // Ink concentration: dark areas get more ink, light areas are washed
    float ink_density = 1.0 - lum;
    ink_density = pow(ink_density, 0.6);  // Non-linear for sumi-e look

    // Paper texture: subtle noise
    float paper_noise = fract(sin(dot(uv * 500.0, vec2(12.9898, 78.233))) * 43758.5453);
    float paper = 0.92 + paper_noise * 0.08;

    // Ink bleed: slight blur in high-density areas
    vec3 bleed = vec3(0.0);
    float bleed_weight = 0.0;
    for (int dx = -2; dx <= 2; dx++) {
        for (int dy = -2; dy <= 2; dy++) {
            vec2 offset = vec2(float(dx), float(dy)) * texel;
            // Directional bleed: ink flows slightly downward
            offset.y += abs(float(dx)) * texel.y * 0.5;
            float w = exp(-float(dx*dx + dy*dy) / 4.0);
            bleed += HOOKED_tex(uv + offset).rgb * w;
            bleed_weight += w;
        }
    }
    bleed /= bleed_weight;
    float bleed_lum = dot(bleed, vec3(0.299, 0.587, 0.114));

    // Combine: ink strokes + wash gradients on paper
    float final_ink = mix(bleed_lum, lum, 0.6);
    final_ink = 1.0 - pow(1.0 - final_ink, 1.5) * ink_density;

    // Strong ink outlines
    float outline = smoothstep(0.015, 0.06, edge) * 0.85;
    final_ink -= outline;
    final_ink = max(final_ink, 0.05);

    // Rice paper color: warm off-white
    vec3 paper_color = vec3(0.95, 0.92, 0.85) * paper;
    vec3 ink_color = vec3(0.08, 0.06, 0.05);

    vec3 result = mix(ink_color, paper_color, final_ink);

    // Very subtle warm tint in mid-wash areas (like diluted ink)
    float mid_wash = smoothstep(0.3, 0.5, final_ink) * smoothstep(0.7, 0.5, final_ink);
    result += vec3(0.02, 0.01, 0.0) * mid_wash;

    return vec4(result, 1.0);
}
