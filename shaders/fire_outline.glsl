//!HOOK MAIN
//!BIND HOOKED
//!DESC Fire Outline — burning contour with rising flame and ember particles

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 texel = 1.0 / HOOKED_size;
    float t = float(frame) * 0.05;
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
    edge = smoothstep(0.01, 0.06, edge);

    // Flame noise: upward-moving turbulence along edges
    float flame_noise = 0.0;
    float freq = 1.0;
    for (int i = 0; i < 4; i++) {
        float n = sin(uv.x * 30.0 * freq + t * 3.0 * freq)
                * cos((uv.y - t * 0.5) * 20.0 * freq + t * 2.0);
        flame_noise += abs(n) / freq;
        freq *= 2.0;
    }
    flame_noise *= 0.25;

    // Flame reaches upward from edges
    float flame_reach = edge;
    // Extend flame upward: sample edges below current pixel
    for (int i = 1; i <= 6; i++) {
        float below_y = uv.y + float(i) * texel.y * 3.0;
        if (below_y > 1.0) break;
        float below_c = dot(HOOKED_tex(vec2(uv.x, below_y)).rgb, vec3(0.33));
        float below_edge = 0.0;
        for (int dx = -1; dx <= 1; dx++) {
            float bn = dot(HOOKED_tex(vec2(uv.x + float(dx) * texel.x, below_y)).rgb, vec3(0.33));
            below_edge += abs(below_c - bn);
        }
        below_edge /= 3.0;
        float dist_fade = 1.0 - float(i) / 7.0;
        flame_reach += smoothstep(0.02, 0.06, below_edge) * dist_fade * 0.4;
    }

    // Add noise to flame
    flame_reach *= (0.7 + flame_noise * 0.6);

    // Fire color gradient: white core → yellow → orange → red → dark
    vec3 fire_color;
    if (flame_reach > 0.8) {
        fire_color = mix(vec3(1.0, 0.9, 0.4), vec3(1.0, 1.0, 0.9), (flame_reach - 0.8) / 0.2);
    } else if (flame_reach > 0.5) {
        fire_color = mix(vec3(1.0, 0.5, 0.0), vec3(1.0, 0.9, 0.4), (flame_reach - 0.5) / 0.3);
    } else if (flame_reach > 0.2) {
        fire_color = mix(vec3(0.8, 0.1, 0.0), vec3(1.0, 0.5, 0.0), (flame_reach - 0.2) / 0.3);
    } else {
        fire_color = vec3(0.8, 0.1, 0.0) * (flame_reach / 0.2);
    }

    // Ember sparks
    vec2 spark_grid = uv * vec2(30.0, 40.0);
    vec2 spark_cell = floor(spark_grid);
    float spark_rnd = fract(sin(dot(spark_cell + floor(t * 5.0), vec2(127.1, 311.7))) * 43758.5453);
    float spark = step(0.995, spark_rnd) * edge * 3.0;
    fire_color += vec3(1.0, 0.8, 0.3) * spark;

    // Blend fire over original
    vec3 result = col.rgb + fire_color * flame_reach;

    return vec4(result, 1.0);
}
