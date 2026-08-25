//!HOOK MAIN
//!BIND HOOKED
//!DESC Crystal Refraction — faceted diamond/gem refraction overlay

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.015;

    // Hexagonal/triangular facet grid
    float scale = 20.0;
    vec2 hex_uv = uv * scale;

    // Offset every other row for hex packing
    float row = floor(hex_uv.y);
    if (mod(row, 2.0) > 0.5) {
        hex_uv.x += 0.5;
    }

    vec2 cell_id = floor(hex_uv);
    vec2 cell_uv = fract(hex_uv);

    // Per-facet random tilt (simulates different gem faces)
    float rnd1 = fract(sin(dot(cell_id, vec2(127.1, 311.7))) * 43758.5453);
    float rnd2 = fract(sin(dot(cell_id, vec2(269.5, 183.3))) * 43758.5453);

    // Facet normal determines refraction offset
    vec2 facet_normal = vec2(
        (rnd1 - 0.5) * 2.0,
        (rnd2 - 0.5) * 2.0
    );

    // Slow facet rotation
    float angle = t + rnd1 * 6.28;
    float ca = cos(angle);
    float sa = sin(angle);
    facet_normal = vec2(
        facet_normal.x * ca - facet_normal.y * sa,
        facet_normal.x * sa + facet_normal.y * ca
    );

    // Refraction: distort UV per facet
    float refract_strength = 0.02;
    vec2 refracted_uv = uv + facet_normal * refract_strength;
    refracted_uv = clamp(refracted_uv, 0.0, 1.0);

    // Chromatic dispersion per facet
    float dispersion = 0.005;
    float r = HOOKED_tex(refracted_uv + facet_normal * dispersion).r;
    float g = HOOKED_tex(refracted_uv).g;
    float b = HOOKED_tex(refracted_uv - facet_normal * dispersion).b;

    vec3 col = vec3(r, g, b);

    // Sparkle at facet edges
    float edge_x = smoothstep(0.0, 0.08, cell_uv.x) * smoothstep(0.0, 0.08, 1.0 - cell_uv.x);
    float edge_y = smoothstep(0.0, 0.08, cell_uv.y) * smoothstep(0.0, 0.08, 1.0 - cell_uv.y);
    float edge = 1.0 - edge_x * edge_y;

    // Animated sparkle
    float sparkle = edge * (sin(t * 5.0 + rnd1 * 20.0) * 0.5 + 0.5) * 0.6;
    col += vec3(0.8, 0.9, 1.0) * sparkle;

    // Subtle facet edge darkening
    col *= mix(0.7, 1.0, edge_x * edge_y);

    return vec4(col, 1.0);
}
