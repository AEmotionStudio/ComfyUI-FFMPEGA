//!HOOK MAIN
//!BIND HOOKED
//!DESC Focus Pull — cinematic DoF with normal-based specular bokeh

// Auto-detect panel layout:
//   2 panels: [color | depth]
//   3 panels: [color | depth | normals]

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 texel = 1.0 / HOOKED_size;
    float aspect = HOOKED_size.x / HOOKED_size.y;

    int panels = 1;
    if (aspect > 2.8) panels = 3;
    else if (aspect > 1.8) panels = 2;

    float panel_w = 1.0 / float(panels);

    // Non-color panels → pass through
    if (uv.x >= panel_w) {
        return HOOKED_tex(uv);
    }

    vec4 col = HOOKED_tex(uv);

    // Read depth
    float depth = 0.5;
    if (panels >= 2) {
        depth = dot(HOOKED_tex(vec2(uv.x + panel_w, uv.y)).rgb, vec3(0.333));
    }

    // Read normals
    vec3 normal = vec3(0.0, 0.0, 1.0);
    bool has_normals = (panels >= 3);
    if (has_normals) {
        normal = HOOKED_tex(vec2(uv.x + 2.0 * panel_w, uv.y)).rgb * 2.0 - 1.0;
        normal = normalize(normal);
    }

    // ── Focal plane ──
    float focal_depth = 0.35;
    float focal_range = 0.15;
    float coc = abs(depth - focal_depth);
    coc = smoothstep(0.0, focal_range, coc);

    // ── Blur radius ──
    float max_blur = 4.0;
    float blur_radius = coc * max_blur;

    if (blur_radius < 0.3) {
        // In focus: add normal-based specular if available
        if (has_normals) {
            vec3 light = normalize(vec3(0.3, 0.4, 0.7));
            vec3 view = vec3(0.0, 0.0, 1.0);
            vec3 half_v = normalize(light + view);
            float spec = pow(max(dot(normal, half_v), 0.0), 48.0);
            return vec4(clamp(col.rgb + vec3(1.0, 0.97, 0.92) * spec * 0.25, 0.0, 1.0), 1.0);
        }
        return vec4(col.rgb, 1.0);
    }

    // ── Bokeh-style circular blur ──
    vec3 blurred = vec3(0.0);
    float total_w = 0.0;

    vec2 poisson[16];
    poisson[0] = vec2(-0.94, -0.34);
    poisson[1] = vec2(0.94, 0.34);
    poisson[2] = vec2(-0.34, 0.94);
    poisson[3] = vec2(0.34, -0.94);
    poisson[4] = vec2(-0.76, 0.65);
    poisson[5] = vec2(0.76, -0.65);
    poisson[6] = vec2(-0.65, -0.76);
    poisson[7] = vec2(0.65, 0.76);
    poisson[8] = vec2(-0.17, -0.17);
    poisson[9] = vec2(0.17, 0.17);
    poisson[10] = vec2(-0.50, 0.10);
    poisson[11] = vec2(0.50, -0.10);
    poisson[12] = vec2(0.10, 0.50);
    poisson[13] = vec2(-0.10, -0.50);
    poisson[14] = vec2(-0.85, -0.85);
    poisson[15] = vec2(0.85, 0.85);

    for (int i = 0; i < 16; i++) {
        vec2 offset = poisson[i] * texel * blur_radius;
        vec2 sample_uv = uv + offset;
        sample_uv.x = clamp(sample_uv.x, 0.0, panel_w - texel.x);

        vec4 s = HOOKED_tex(sample_uv);

        float s_depth = depth;
        if (panels >= 2) {
            s_depth = dot(HOOKED_tex(vec2(sample_uv.x + panel_w, sample_uv.y)).rgb, vec3(0.333));
        }
        float s_coc = abs(s_depth - focal_depth);
        s_coc = smoothstep(0.0, focal_range, s_coc);

        float w = (s_coc >= coc * 0.5) ? 1.0 : 0.3;

        // Bokeh highlight boost
        float s_lum = dot(s.rgb, vec3(0.299, 0.587, 0.114));
        float highlight_boost = smoothstep(0.7, 0.95, s_lum) * 0.5 + 1.0;

        // Normal-enhanced bokeh: specular surfaces sparkle more
        if (has_normals) {
            vec3 s_normal = HOOKED_tex(vec2(sample_uv.x + 2.0 * panel_w, sample_uv.y)).rgb * 2.0 - 1.0;
            float facing = max(dot(normalize(s_normal), vec3(0.0, 0.0, 1.0)), 0.0);
            // Surfaces facing camera sparkle less, angles sparkle more
            highlight_boost += (1.0 - facing) * s_lum * 0.3;
        }

        blurred += s.rgb * w * highlight_boost;
        total_w += w * highlight_boost;
    }
    blurred /= total_w;

    vec3 result = mix(col.rgb, blurred, coc);

    // ── Vignette ──
    vec2 vig_uv = uv / panel_w * 2.0 - 1.0;
    float vig = 1.0 - dot(vig_uv, vig_uv) * 0.2;
    result *= clamp(vig, 0.7, 1.0);

    return vec4(clamp(result, 0.0, 1.0), 1.0);
}
