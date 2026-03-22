//!HOOK MAIN
//!BIND HOOKED
//!DESC Relief Sculpt — emboss with real NormalCrafter surface normals

// Auto-detect panel layout:
//   2 panels: [color | depth]         → approximate normals from depth
//   3 panels: [color | depth | normals] → use real NormalCrafter normals

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 texel = 1.0 / HOOKED_size;
    float t = float(frame) * 0.01;
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

    // ── Surface normal ──
    vec3 normal = vec3(0.0, 0.0, 1.0);
    bool has_normals = (panels >= 3);

    if (has_normals) {
        // Real NormalCrafter normals — much more accurate!
        normal = HOOKED_tex(vec2(uv.x + 2.0 * panel_w, uv.y)).rgb * 2.0 - 1.0;
        normal = normalize(normal);
    } else if (panels >= 2) {
        // Fallback: approximate normals from depth central differences
        float d_right = dot(HOOKED_tex(vec2(uv.x + panel_w + texel.x, uv.y)).rgb, vec3(0.333));
        float d_left  = dot(HOOKED_tex(vec2(uv.x + panel_w - texel.x, uv.y)).rgb, vec3(0.333));
        float d_up    = dot(HOOKED_tex(vec2(uv.x + panel_w, uv.y - texel.y)).rgb, vec3(0.333));
        float d_down  = dot(HOOKED_tex(vec2(uv.x + panel_w, uv.y + texel.y)).rgb, vec3(0.333));
        normal = normalize(vec3(
            (d_left - d_right) * 8.0,
            (d_up - d_down) * 8.0,
            1.0
        ));
    }

    float nearness = 1.0 - depth;

    // ── Animated directional light ──
    float light_angle = t * 0.5;
    vec3 light_dir = normalize(vec3(
        cos(light_angle) * 0.7,
        sin(light_angle) * 0.5,
        0.8
    ));

    // ── Diffuse lighting ──
    float diffuse = max(dot(normal, light_dir), 0.0);
    diffuse = diffuse * 0.6 + 0.4;

    // ── Specular highlight (Blinn-Phong) ──
    vec3 view_dir = vec3(0.0, 0.0, 1.0);
    vec3 half_dir = normalize(light_dir + view_dir);
    float spec = pow(max(dot(normal, half_dir), 0.0), 32.0);

    // With real normals, add secondary specular for micro-detail
    float micro_spec = 0.0;
    if (has_normals) {
        // Higher frequency specular — captures fine surface detail
        float fine_spec = pow(max(dot(normal, half_dir), 0.0), 128.0);
        micro_spec = fine_spec * nearness * 0.3;
    }

    // ── Relief emboss effect ──
    float emboss = 0.0;
    if (has_normals) {
        // Direct from normal vector: x/y components = surface tilt
        emboss = (normal.x + normal.y) * 1.5;
    } else if (panels >= 2) {
        float d_left  = dot(HOOKED_tex(vec2(uv.x + panel_w - texel.x, uv.y)).rgb, vec3(0.333));
        float d_right = dot(HOOKED_tex(vec2(uv.x + panel_w + texel.x, uv.y)).rgb, vec3(0.333));
        float d_up    = dot(HOOKED_tex(vec2(uv.x + panel_w, uv.y - texel.y)).rgb, vec3(0.333));
        float d_down  = dot(HOOKED_tex(vec2(uv.x + panel_w, uv.y + texel.y)).rgb, vec3(0.333));
        emboss = (d_left - d_right + d_up - d_down) * 3.0;
    }

    // ── Base material ──
    vec3 stone_color = vec3(0.82, 0.78, 0.72);
    vec3 base = mix(col.rgb * 0.3 + stone_color * 0.7, col.rgb, 0.35);
    base += emboss * 0.3;

    vec3 result = base * diffuse;
    result += vec3(1.0, 0.98, 0.92) * spec * 0.6;
    result += vec3(0.95, 0.92, 0.88) * micro_spec;

    // ── Depth-based edge carving ──
    if (panels >= 2) {
        float depth_edge = 0.0;
        for (int dx = -1; dx <= 1; dx++) {
            for (int dy = -1; dy <= 1; dy++) {
                if (dx == 0 && dy == 0) continue;
                vec2 offset = vec2(float(dx), float(dy)) * texel;
                float nd = dot(HOOKED_tex(vec2(uv.x + panel_w + offset.x, uv.y + offset.y)).rgb, vec3(0.333));
                depth_edge += abs(depth - nd);
            }
        }
        depth_edge /= 8.0;
        float carved = smoothstep(0.01, 0.06, depth_edge) * nearness;
        result = mix(result, result * 0.3, carved * 0.5);
    }

    // ── Normal-based ambient occlusion ──
    if (has_normals) {
        // Concave surfaces (normals pointing inward) are darker
        float ao = smoothstep(-0.2, 0.3, normal.z);
        result *= mix(0.7, 1.0, ao);
    }

    // ── Patina in crevices ──
    float crevice = smoothstep(0.5, 0.3, diffuse) * nearness;
    vec3 patina = vec3(0.35, 0.55, 0.45);
    result = mix(result, patina, crevice * 0.25);

    return vec4(clamp(result, 0.0, 1.0), 1.0);
}
