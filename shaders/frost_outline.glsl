//!HOOK MAIN
//!BIND HOOKED
//!DESC Frost Outline — icy crystallization spreading along edges

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 texel = 1.0 / HOOKED_size;
    float t = float(frame) * 0.02;
    vec4 col = HOOKED_tex(uv);

    // Edge detection
    float c = dot(col.rgb, vec3(0.299, 0.587, 0.114));
    float edge = 0.0;
    for (int dx = -2; dx <= 2; dx++) {
        for (int dy = -2; dy <= 2; dy++) {
            if (dx == 0 && dy == 0) continue;
            vec2 offset = vec2(float(dx), float(dy)) * texel;
            float n = dot(HOOKED_tex(uv + offset).rgb, vec3(0.299, 0.587, 0.114));
            edge += abs(c - n);
        }
    }
    edge /= 24.0;
    edge = smoothstep(0.01, 0.05, edge);

    // Ice crystal branching pattern (fractal-ish noise along edges)
    float crystal = 0.0;
    float ice_scale = 50.0;
    vec2 ice_uv = uv * ice_scale;
    vec2 ice_cell = floor(ice_uv);
    vec2 ice_f = fract(ice_uv);

    // Branching: lines from cell corners in 6 directions (snowflake symmetry)
    float branch_rnd = fract(sin(dot(ice_cell, vec2(127.1, 311.7))) * 43758.5453);
    for (int i = 0; i < 6; i++) {
        float a = float(i) * 1.0472 + branch_rnd * 0.5;  // 60-degree increments
        vec2 branch_dir = vec2(cos(a), sin(a));
        float line_dist = abs(dot(ice_f - 0.5, vec2(-branch_dir.y, branch_dir.x)));
        crystal += smoothstep(0.04, 0.0, line_dist) * smoothstep(0.6, 0.0, length(ice_f - 0.5));
    }
    crystal = min(crystal, 1.0);

    // Crystal grows from edges
    float frost = crystal * edge;

    // Extended frost: sample nearby for edge proximity
    for (int dx = -4; dx <= 4; dx += 2) {
        for (int dy = -4; dy <= 4; dy += 2) {
            vec2 offset = vec2(float(dx), float(dy)) * texel;
            float nc = dot(HOOKED_tex(uv + offset).rgb, vec3(0.33));
            float n_edge = abs(c - nc);
            float dist = length(vec2(float(dx), float(dy)));
            frost += smoothstep(0.02, 0.05, n_edge) * crystal * 0.15 / (1.0 + dist * 0.3);
        }
    }

    // Animated sparkle on frost
    float sparkle = sin(uv.x * 200.0 + t * 10.0) * sin(uv.y * 180.0 - t * 8.0);
    sparkle = pow(max(sparkle, 0.0), 8.0) * frost * 2.0;

    // Ice colors: white core, pale blue glow
    vec3 ice_core = vec3(0.95, 0.97, 1.0) * frost;
    vec3 ice_glow = vec3(0.5, 0.7, 0.95) * frost * 0.5;
    vec3 ice_sparkle = vec3(0.9, 0.95, 1.0) * sparkle;

    // Slight desaturation and cooling of areas near frost
    vec3 cooled = mix(col.rgb, col.rgb * vec3(0.85, 0.9, 1.05), frost * 0.4);

    vec3 result = cooled + ice_core + ice_glow + ice_sparkle;

    return vec4(result, 1.0);
}
