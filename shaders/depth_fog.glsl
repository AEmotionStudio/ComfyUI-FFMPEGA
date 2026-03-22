//!HOOK MAIN
//!BIND HOOKED
//!DESC Depth Fog — atmospheric fog with normal-based surface glow

// Auto-detect panel layout:
//   2 panels: [color | depth]
//   3 panels: [color | depth | normals]

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 texel = 1.0 / HOOKED_size;
    float t = float(frame) * 0.005;
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

    // ── Fog density curve ──
    float fog_density = 2.5;
    float fog = 1.0 - exp(-depth * depth * fog_density);

    // ── Fog color with atmospheric scattering ──
    vec3 fog_near = vec3(0.85, 0.82, 0.78);
    vec3 fog_far = vec3(0.65, 0.72, 0.82);
    vec3 fog_color = mix(fog_near, fog_far, depth);

    float hue_drift = sin(t * 0.3) * 0.03;
    fog_color += vec3(hue_drift, hue_drift * 0.5, -hue_drift);

    // ── Height-based fog ──
    float height = 1.0 - uv.y;
    float height_fog = smoothstep(0.3, 0.8, height) * 0.3;
    fog = min(fog + height_fog * depth, 1.0);

    // ── Normal-based fog variation ──
    if (has_normals) {
        // Upward-facing surfaces catch more light through fog
        float up_facing = max(normal.y, 0.0);
        // Brighten upward surfaces (sun scattering through fog)
        fog_color += vec3(0.08, 0.06, 0.02) * up_facing * fog;

        // Side-facing surfaces accumulate more fog (grazing angle)
        float facing_camera = max(dot(normal, vec3(0.0, 0.0, 1.0)), 0.0);
        fog += (1.0 - facing_camera) * 0.1 * depth;
        fog = min(fog, 1.0);
    }

    // ── Color desaturation with distance ──
    float gray = dot(col.rgb, vec3(0.299, 0.587, 0.114));
    float desat = depth * 0.6;
    vec3 desaturated = mix(col.rgb, vec3(gray), desat);

    // ── Contrast reduction with distance ──
    float contrast_loss = depth * 0.3;
    desaturated = mix(desaturated, vec3(0.5), contrast_loss);

    // ── Apply fog ──
    vec3 result = mix(desaturated, fog_color, fog);

    // ── Light rays from depth edges ──
    if (panels >= 2) {
        float ray = 0.0;
        for (int i = 1; i <= 4; i++) {
            float fi = float(i);
            vec2 ray_offset = vec2(0.0, -fi) * texel * 3.0;
            float ray_depth = dot(HOOKED_tex(vec2(uv.x + panel_w + ray_offset.x, uv.y + ray_offset.y)).rgb, vec3(0.333));
            ray += abs(ray_depth - depth) * exp(-fi * 0.5);
        }
        ray = smoothstep(0.02, 0.1, ray) * fog * 0.15;
        result += vec3(1.0, 0.95, 0.85) * ray;
    }

    // ── Normal-based ambient occlusion in fog ──
    if (has_normals) {
        // Surfaces facing downward are darker in fog (less light)
        float ao = smoothstep(-0.3, 0.2, normal.y);
        result *= mix(0.85, 1.0, ao);
    }

    return vec4(clamp(result, 0.0, 1.0), 1.0);
}
