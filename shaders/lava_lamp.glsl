//!HOOK MAIN
//!BIND HOOKED
//!DESC Lava Lamp — animated metaball blobs that float and merge

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.025;
    vec4 col = HOOKED_tex(uv);

    // Define metaball centers (animated positions)
    float field = 0.0;
    vec3 blob_color_total = vec3(0.0);

    // 6 blobs with different orbits
    for (int i = 0; i < 6; i++) {
        float fi = float(i);
        float phase = fi * 1.047;  // 60-degree offsets

        vec2 blob_center = vec2(
            0.5 + sin(t * (0.3 + fi * 0.1) + phase) * (0.25 + fi * 0.03),
            0.5 + cos(t * (0.25 + fi * 0.08) + phase * 1.3) * (0.3 - fi * 0.02)
        );

        float radius = 0.08 + sin(t * 0.5 + fi) * 0.02;
        float dist = length(uv - blob_center);

        // Metaball field contribution (inverse square)
        float contribution = radius * radius / (dist * dist + 0.001);
        field += contribution;

        // Per-blob color (warm palette: orange, pink, yellow, red)
        vec3 blob_col;
        if (i < 2) blob_col = vec3(1.0, 0.3, 0.1);       // orange
        else if (i < 4) blob_col = vec3(0.9, 0.2, 0.5);   // pink
        else blob_col = vec3(1.0, 0.8, 0.1);               // yellow

        blob_color_total += blob_col * contribution;
    }

    // Normalize blob color by field
    if (field > 0.01) blob_color_total /= field;

    // Threshold field to create blob surfaces
    float blob_surface = smoothstep(1.5, 2.5, field);

    // Internal glow gradient within blobs
    float inner_glow = smoothstep(2.0, 5.0, field);

    // "Lava" color: bright core, darker edges
    vec3 lava = mix(blob_color_total * 0.6, blob_color_total * 1.5, inner_glow);

    // Background: dark with subtle original image
    vec3 bg = col.rgb * 0.3 + vec3(0.05, 0.02, 0.08);

    // Blend blobs over background
    vec3 result = mix(bg, lava, blob_surface);

    // Glow halo around blobs
    float halo = smoothstep(1.0, 1.8, field) * (1.0 - blob_surface);
    result += blob_color_total * halo * 0.3;

    // Subtle wax drip distortion on original underneath
    if (blob_surface < 0.1) {
        vec2 wax_distort = vec2(
            sin(uv.y * 20.0 + t * 2.0) * 0.003,
            cos(uv.x * 15.0 + t * 1.5) * 0.003
        ) * (1.0 - blob_surface);
        result = mix(HOOKED_tex(uv + wax_distort).rgb * 0.3 + vec3(0.05, 0.02, 0.08), result, blob_surface);
    }

    return vec4(result, 1.0);
}
