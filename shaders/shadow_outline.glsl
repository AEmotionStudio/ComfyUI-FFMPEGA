//!HOOK MAIN
//!BIND HOOKED
//!DESC Shadow Outline — dramatic drop shadow / depth silhouette

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 texel = 1.0 / HOOKED_size;
    float t = float(frame) * 0.015;
    vec4 col = HOOKED_tex(uv);

    // Multi-scale edge detection for silhouette extraction
    float c = dot(col.rgb, vec3(0.299, 0.587, 0.114));
    float edge = 0.0;
    float edge_dir_x = 0.0;
    float edge_dir_y = 0.0;

    // Sobel gradient for edge direction
    float tl = dot(HOOKED_tex(uv + vec2(-texel.x, -texel.y)).rgb, vec3(0.33));
    float tc = dot(HOOKED_tex(uv + vec2(0.0, -texel.y)).rgb, vec3(0.33));
    float tr = dot(HOOKED_tex(uv + vec2(texel.x, -texel.y)).rgb, vec3(0.33));
    float ml = dot(HOOKED_tex(uv + vec2(-texel.x, 0.0)).rgb, vec3(0.33));
    float mr = dot(HOOKED_tex(uv + vec2(texel.x, 0.0)).rgb, vec3(0.33));
    float bl = dot(HOOKED_tex(uv + vec2(-texel.x, texel.y)).rgb, vec3(0.33));
    float bc = dot(HOOKED_tex(uv + vec2(0.0, texel.y)).rgb, vec3(0.33));
    float br = dot(HOOKED_tex(uv + vec2(texel.x, texel.y)).rgb, vec3(0.33));

    edge_dir_x = -tl - 2.0*ml - bl + tr + 2.0*mr + br;
    edge_dir_y = -tl - 2.0*tc - tr + bl + 2.0*bc + br;
    edge = sqrt(edge_dir_x * edge_dir_x + edge_dir_y * edge_dir_y);
    edge = smoothstep(0.03, 0.12, edge);

    // Shadow: offset edges in light direction to create drop shadow
    vec2 shadow_dir = normalize(vec2(0.7, 0.5));  // light from top-left
    vec2 shadow_offset = shadow_dir * texel * 5.0;

    // Sample edge at shadow offset position (shadow is displaced edge)
    float shadow_c = dot(HOOKED_tex(uv - shadow_offset).rgb, vec3(0.33));
    float shadow_edge = 0.0;
    for (int dx = -1; dx <= 1; dx++) {
        for (int dy = -1; dy <= 1; dy++) {
            vec2 offset = vec2(float(dx), float(dy)) * texel;
            float n = dot(HOOKED_tex(uv - shadow_offset + offset).rgb, vec3(0.33));
            shadow_edge += abs(shadow_c - n);
        }
    }
    shadow_edge /= 9.0;
    shadow_edge = smoothstep(0.02, 0.06, shadow_edge);

    // Soft shadow (wider blur for ground shadow)
    float soft_shadow = 0.0;
    for (int i = 1; i <= 8; i++) {
        vec2 ss_uv = uv - shadow_dir * texel * float(i) * 2.0;
        float ss = dot(HOOKED_tex(ss_uv).rgb, vec3(0.33));
        float ss_edge = abs(c - ss);
        soft_shadow += smoothstep(0.01, 0.04, ss_edge) / float(i);
    }
    soft_shadow *= 0.1;

    // Dark shadow layer
    vec3 shadow_color = vec3(0.0, 0.0, 0.05);
    float total_shadow = (shadow_edge * 0.7 + soft_shadow) * 0.6;

    // Bright edge highlight (opposite side from shadow — rim light)
    float rim_c = dot(HOOKED_tex(uv + shadow_offset * 0.5).rgb, vec3(0.33));
    float rim_edge = abs(c - rim_c);
    rim_edge = smoothstep(0.02, 0.06, rim_edge);

    // Apply
    vec3 result = col.rgb;
    result = mix(result, shadow_color, total_shadow);
    result += vec3(0.9, 0.92, 1.0) * edge * 0.8;      // Primary outline
    result += vec3(1.0, 0.95, 0.85) * rim_edge * 0.4;   // Rim highlight

    return vec4(result, 1.0);
}
