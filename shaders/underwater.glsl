//!HOOK MAIN
//!BIND HOOKED
//!DESC Underwater — deep sea submersion with caustics and color absorption

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.025;

    // Gentle wave distortion (water refraction)
    vec2 wave = vec2(
        sin(uv.y * 12.0 + t * 2.0) * cos(uv.x * 8.0 + t) * 0.006,
        cos(uv.x * 10.0 + t * 1.5) * sin(uv.y * 6.0 - t * 0.8) * 0.006
    );
    vec2 sample_uv = clamp(uv + wave, 0.0, 1.0);
    vec4 col = HOOKED_tex(sample_uv);

    // Water color absorption (reds fade first, then greens)
    // Simulates depth-based color shift
    float depth = 0.6; // simulated depth factor
    col.r *= (1.0 - depth * 0.6);
    col.g *= (1.0 - depth * 0.2);
    col.b *= (1.0 + depth * 0.1);

    // Tint toward deep blue-green
    vec3 water_tint = vec3(0.05, 0.15, 0.25);
    col.rgb = mix(col.rgb, water_tint, 0.25);

    // Animated caustics (light patterns from surface)
    float caustic1 = sin(uv.x * 25.0 + t * 3.0) * sin(uv.y * 20.0 + t * 2.0);
    float caustic2 = sin(uv.x * 18.0 - t * 2.5 + uv.y * 15.0)
                   * cos(uv.y * 22.0 + t * 1.8);
    float caustic3 = sin((uv.x + uv.y) * 30.0 + t * 4.0)
                   * sin((uv.x - uv.y) * 25.0 - t * 3.0);
    float caustic = max(caustic1, 0.0) + max(caustic2, 0.0) * 0.7 + max(caustic3, 0.0) * 0.5;
    caustic = pow(caustic * 0.5, 2.0);

    // Caustics are brighter at top (closer to surface)
    float surface_proximity = 1.0 - uv.y;
    col.rgb += vec3(0.15, 0.25, 0.3) * caustic * surface_proximity * 0.8;

    // Light rays from surface (god rays)
    float ray_x = sin(uv.x * 5.0 + t * 0.3) * 0.5 + 0.5;
    float ray = pow(ray_x, 5.0) * surface_proximity * 0.15;
    col.rgb += vec3(0.1, 0.15, 0.2) * ray;

    // Floating particle motes
    vec2 mote_grid = uv * vec2(15.0, 20.0);
    vec2 mote_cell = floor(mote_grid);
    vec2 mote_f = fract(mote_grid);
    float mote_rnd = fract(sin(dot(mote_cell, vec2(127.1, 311.7))) * 43758.5453);
    float mote_y = fract(mote_rnd + t * 0.1 * (mote_rnd + 0.5));
    float mote = smoothstep(0.08, 0.0, length(mote_f - vec2(mote_rnd, mote_y)));
    col.rgb += vec3(0.2, 0.3, 0.35) * mote * 0.8;

    // Slight vignette (light falloff at depth)
    float vig = 1.0 - 0.4 * length(uv - 0.5);
    col.rgb *= vig;

    return vec4(col.rgb, 1.0);
}
