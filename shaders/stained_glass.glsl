//!HOOK MAIN
//!BIND HOOKED
//!DESC Stained Glass — cathedral window panels with lead borders

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.01;

    // Voronoi cell decomposition for irregular glass panels
    float cell_scale = 12.0;
    vec2 scaled_uv = uv * cell_scale;
    vec2 cell_id = floor(scaled_uv);

    float min_dist = 10.0;
    float second_dist = 10.0;
    vec2 nearest_cell = cell_id;
    vec3 panel_color = vec3(0.0);

    // Check 3x3 neighborhood for nearest Voronoi center
    for (int dx = -1; dx <= 1; dx++) {
        for (int dy = -1; dy <= 1; dy++) {
            vec2 neighbor = cell_id + vec2(float(dx), float(dy));
            // Randomized cell center
            float rnd1 = fract(sin(dot(neighbor, vec2(127.1, 311.7))) * 43758.5453);
            float rnd2 = fract(sin(dot(neighbor, vec2(269.5, 183.3))) * 43758.5453);
            vec2 center = neighbor + vec2(rnd1, rnd2) * 0.8 + 0.1;

            float dist = length(scaled_uv - center);
            if (dist < min_dist) {
                second_dist = min_dist;
                min_dist = dist;
                nearest_cell = neighbor;
            } else if (dist < second_dist) {
                second_dist = dist;
            }
        }
    }

    // Lead border: edge between cells
    float edge = second_dist - min_dist;
    float lead = smoothstep(0.08, 0.0, edge);

    // Sample original at Voronoi cell center for panel color
    float rnd_x = fract(sin(dot(nearest_cell, vec2(127.1, 311.7))) * 43758.5453);
    float rnd_y = fract(sin(dot(nearest_cell, vec2(269.5, 183.3))) * 43758.5453);
    vec2 cell_center_uv = (nearest_cell + vec2(rnd_x, rnd_y) * 0.8 + 0.1) / cell_scale;
    cell_center_uv = clamp(cell_center_uv, 0.0, 1.0);
    panel_color = HOOKED_tex(cell_center_uv).rgb;

    // Glass saturation boost + slight color tinting
    float panel_lum = dot(panel_color, vec3(0.299, 0.587, 0.114));
    panel_color = mix(vec3(panel_lum), panel_color, 1.8);  // saturate

    // Translucency: lighten to simulate backlit glass
    panel_color = mix(panel_color, vec3(1.0), 0.15);

    // Light refraction pattern within each panel
    float refract = sin(min_dist * 20.0 + t * 2.0) * 0.03;
    panel_color += refract;

    // Slight color variation across each panel (non-uniform glass)
    float variation = fract(sin(dot(nearest_cell + 0.5, vec2(12.9898, 78.233))) * 43758.5453);
    panel_color *= (0.9 + variation * 0.2);

    // Lead border: dark gray metallic
    vec3 lead_color = vec3(0.15, 0.14, 0.12);

    // Specular highlight on lead
    float lead_spec = pow(max(1.0 - edge * 8.0, 0.0), 4.0) * 0.3;
    lead_color += lead_spec;

    vec3 result = mix(panel_color, lead_color, lead);

    return vec4(result, 1.0);
}
