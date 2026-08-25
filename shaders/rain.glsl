//!HOOK MAIN
//!BIND HOOKED
//!DESC Rain — animated raindrops with streaks, splashes, and refraction

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.04;

    // ── Rain streaks (diagonal falling lines) ──
    float streak = 0.0;
    for (int i = 0; i < 3; i++) {
        float layer_speed = 1.0 + float(i) * 0.5;
        float layer_density = 15.0 + float(i) * 10.0;
        float layer_angle = 0.15 + float(i) * 0.05;

        // Rotated UV for angled rain
        vec2 rain_uv = vec2(
            uv.x + uv.y * layer_angle,
            uv.y - t * layer_speed
        );

        // Column grid
        float col_x = floor(rain_uv.x * layer_density);
        float col_rnd = fract(sin(col_x * 127.1 + float(i) * 50.0) * 43758.5453);

        // Drop along column
        float drop_y = fract(rain_uv.y * 3.0 + col_rnd * 10.0);
        float drop_len = 0.3 + col_rnd * 0.4;

        if (drop_y < drop_len) {
            float line_x = fract(rain_uv.x * layer_density);
            float line_dist = abs(line_x - 0.5);
            float thickness = 0.02 - float(i) * 0.005;
            streak += smoothstep(thickness, 0.0, line_dist) * (1.0 - drop_y / drop_len) * 0.3;
        }
    }

    // ── Splash ripples on surfaces ──
    float splash = 0.0;
    for (int i = 0; i < 4; i++) {
        vec2 splash_center = vec2(
            fract(sin(float(i) * 127.1 + floor(t * 2.0)) * 43758.5453),
            fract(sin(float(i) * 311.7 + floor(t * 2.0)) * 43758.5453)
        );
        float splash_time = fract(t * 0.8 + float(i) * 0.25);
        float splash_radius = splash_time * 0.04;
        float dist = length(uv - splash_center);
        float ring = smoothstep(0.003, 0.0, abs(dist - splash_radius));
        ring *= (1.0 - splash_time);  // Fade out
        splash += ring;
    }

    // ── Lens refraction from drops ──
    vec2 refract = vec2(0.0);

    // Grid of lens droplets
    vec2 drop_grid = uv * 12.0;
    vec2 drop_cell = floor(drop_grid);
    vec2 drop_f = fract(drop_grid);
    float drop_rnd = fract(sin(dot(drop_cell, vec2(127.1, 311.7))) * 43758.5453);

    // Droplet position within cell
    vec2 drop_pos = vec2(drop_rnd, fract(drop_rnd * 7.31));
    float drop_dist = length(drop_f - drop_pos);
    float drop_size = 0.1 + drop_rnd * 0.15;

    if (drop_dist < drop_size) {
        // Refraction: offset UV based on position within droplet
        vec2 drop_normal = (drop_f - drop_pos) / drop_size;
        refract = drop_normal * 0.015 * (1.0 - drop_dist / drop_size);
    }

    vec2 sample_uv = clamp(uv + refract, 0.0, 1.0);
    vec4 col = HOOKED_tex(sample_uv);

    // Apply rain streak overlay (semi-transparent white)
    col.rgb += vec3(0.6, 0.65, 0.7) * streak;

    // Splash highlights
    col.rgb += vec3(0.5, 0.55, 0.6) * splash;

    // Overall mood: slight blue-gray tint + darkening
    col.rgb = mix(col.rgb, col.rgb * vec3(0.85, 0.88, 0.95), 0.3);

    // Droplet highlight
    if (drop_dist < drop_size) {
        float highlight = pow(1.0 - drop_dist / drop_size, 3.0) * 0.2;
        col.rgb += vec3(0.8, 0.85, 0.9) * highlight;
    }

    return vec4(col.rgb, 1.0);
}
