//!HOOK MAIN
//!BIND HOOKED
//!DESC Sketch — multi-pass pencil drawing with hatching and paper texture

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 texel = 1.0 / HOOKED_size;

    // ── Multi-directional edge detection (pencil strokes) ──
    float lum = dot(HOOKED_tex(uv).rgb, vec3(0.299, 0.587, 0.114));

    // Sobel in X and Y
    float tl = dot(HOOKED_tex(uv + vec2(-texel.x, -texel.y)).rgb, vec3(0.33));
    float t  = dot(HOOKED_tex(uv + vec2(0.0, -texel.y)).rgb, vec3(0.33));
    float tr = dot(HOOKED_tex(uv + vec2(texel.x, -texel.y)).rgb, vec3(0.33));
    float l  = dot(HOOKED_tex(uv + vec2(-texel.x, 0.0)).rgb, vec3(0.33));
    float r  = dot(HOOKED_tex(uv + vec2(texel.x, 0.0)).rgb, vec3(0.33));
    float bl = dot(HOOKED_tex(uv + vec2(-texel.x, texel.y)).rgb, vec3(0.33));
    float b  = dot(HOOKED_tex(uv + vec2(0.0, texel.y)).rgb, vec3(0.33));
    float br = dot(HOOKED_tex(uv + vec2(texel.x, texel.y)).rgb, vec3(0.33));

    float gx = -tl - 2.0*l - bl + tr + 2.0*r + br;
    float gy = -tl - 2.0*t - tr + bl + 2.0*b + br;
    float edge = sqrt(gx*gx + gy*gy);

    // Edge direction for hatching alignment
    float edge_angle = atan(gy, gx);

    // ── Cross-hatching in dark areas ──
    // Hatching density based on darkness (darker = more hatching)
    float darkness = 1.0 - lum;

    // Primary hatch (45 degrees)
    float hatch1_coord = uv.x * HOOKED_size.x * 0.707 + uv.y * HOOKED_size.y * 0.707;
    float hatch1 = abs(sin(hatch1_coord * 0.8));
    hatch1 = smoothstep(0.3, 0.5, hatch1);

    // Secondary hatch (135 degrees, cross)
    float hatch2_coord = uv.x * HOOKED_size.x * 0.707 - uv.y * HOOKED_size.y * 0.707;
    float hatch2 = abs(sin(hatch2_coord * 0.8));
    hatch2 = smoothstep(0.3, 0.5, hatch2);

    // Tertiary hatch (horizontal, for very dark areas)
    float hatch3 = abs(sin(uv.y * HOOKED_size.y * 0.6));
    hatch3 = smoothstep(0.3, 0.5, hatch3);

    // Apply hatching based on darkness level
    float hatching = 1.0;
    if (darkness > 0.3) hatching *= mix(1.0, hatch1, (darkness - 0.3) * 2.0);
    if (darkness > 0.5) hatching *= mix(1.0, hatch2, (darkness - 0.5) * 2.5);
    if (darkness > 0.75) hatching *= mix(1.0, hatch3, (darkness - 0.75) * 4.0);

    // ── Paper texture ──
    float paper_noise = fract(sin(dot(uv * 800.0, vec2(12.9898, 78.233))) * 43758.5453);
    float paper_grain = fract(sin(dot(uv * 400.0, vec2(269.5, 183.3))) * 43758.5453);
    float paper = 0.90 + paper_noise * 0.06 + paper_grain * 0.04;

    // ── Combine: pencil on paper ──
    // Invert edges (dark pencil lines on light paper)
    float pencil_line = 1.0 - smoothstep(0.05, 0.25, edge);

    // Paper base with pencil strokes
    vec3 paper_color = vec3(0.96, 0.94, 0.89) * paper;
    vec3 pencil_color = vec3(0.12, 0.10, 0.08);

    // Layer: paper → hatching → outlines
    float sketch = pencil_line * hatching;
    vec3 result = mix(pencil_color, paper_color, sketch);

    // Slight warm tint in light areas
    result += vec3(0.02, 0.01, 0.0) * sketch;

    return vec4(result, 1.0);
}
