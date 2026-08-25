//!HOOK MAIN
//!BIND HOOKED
//!DESC Toon 3D — depth-native cel-shading with normal-based rim lighting

// Auto-detect panel layout from texture aspect ratio:
//   2 panels: [color | depth]   → width/height > 1.8
//   3 panels: [color | depth | normals] → width/height > 2.8
// Falls back to luminance-only if no SBS data present.

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 texel = 1.0 / HOOKED_size;
    float aspect = HOOKED_size.x / HOOKED_size.y;

    // Detect panel layout
    int panels = 1;
    if (aspect > 2.8) panels = 3;
    else if (aspect > 1.8) panels = 2;

    float panel_w = 1.0 / float(panels);

    // Non-color panels → pass through unchanged
    if (uv.x >= panel_w) {
        return HOOKED_tex(uv);
    }

    // Read color from left panel
    vec2 col_uv = vec2(uv.x * float(panels), uv.y);
    vec4 col = HOOKED_tex(uv);
    float lum = dot(col.rgb, vec3(0.299, 0.587, 0.114));

    // Read depth (panel 2, if available)
    float depth = 0.5;
    if (panels >= 2) {
        vec2 depth_uv = vec2(uv.x + panel_w, uv.y);
        depth = dot(HOOKED_tex(depth_uv).rgb, vec3(0.333));
    }

    // Read normals (panel 3, if available)
    vec3 normal = vec3(0.0, 0.0, 1.0); // default: facing camera
    bool has_normals = (panels >= 3);
    if (has_normals) {
        vec2 norm_uv = vec2(uv.x + 2.0 * panel_w, uv.y);
        normal = HOOKED_tex(norm_uv).rgb * 2.0 - 1.0; // [0,1] → [-1,1]
        normal = normalize(normal);
    }

    float nearness = 1.0 - depth;

    // ── Depth-adaptive cel-shading ──
    float num_bands = mix(3.0, 7.0, nearness);
    vec3 cel = floor(col.rgb * num_bands + 0.5) / num_bands;
    float cel_gray = dot(cel, vec3(0.299, 0.587, 0.114));
    cel = mix(vec3(cel_gray), cel, 1.35);

    // ── Outline detection ──
    float depth_edge = 0.0;
    float lum_edge = 0.0;
    for (int dx = -1; dx <= 1; dx++) {
        for (int dy = -1; dy <= 1; dy++) {
            if (dx == 0 && dy == 0) continue;
            vec2 offset = vec2(float(dx), float(dy)) * texel;
            if (panels >= 2) {
                float nd = dot(HOOKED_tex(vec2(uv.x + panel_w + offset.x, uv.y + offset.y)).rgb, vec3(0.333));
                depth_edge += abs(depth - nd);
            }
            float nl = dot(HOOKED_tex(uv + offset).rgb, vec3(0.299, 0.587, 0.114));
            lum_edge += abs(lum - nl);
        }
    }
    depth_edge /= 8.0;
    lum_edge /= 8.0;

    float outline_thresh_d = mix(0.06, 0.015, nearness);
    float outline_thresh_l = mix(0.12, 0.04, nearness);
    float silhouette = smoothstep(outline_thresh_d, outline_thresh_d * 3.0, depth_edge);
    float detail_outline = smoothstep(outline_thresh_l, outline_thresh_l * 2.5, lum_edge);
    detail_outline *= nearness * 0.7;
    float outline = max(silhouette, detail_outline);

    // Wider outlines for near objects
    if (nearness > 0.5 && panels >= 2) {
        float wide_edge = 0.0;
        for (int dx = -2; dx <= 2; dx++) {
            for (int dy = -2; dy <= 2; dy++) {
                if (dx == 0 && dy == 0) continue;
                if (abs(dx) + abs(dy) > 3) continue;
                vec2 offset = vec2(float(dx), float(dy)) * texel;
                float nd = dot(HOOKED_tex(vec2(uv.x + panel_w + offset.x, uv.y + offset.y)).rgb, vec3(0.333));
                wide_edge += abs(depth - nd);
            }
        }
        wide_edge /= 16.0;
        outline = max(outline, smoothstep(0.01, 0.04, wide_edge) * nearness);
    }

    // ── Rim lighting ──
    float rim = 0.0;
    if (has_normals) {
        // Real normal-based rim: view dot product
        vec3 view_dir = vec3(0.0, 0.0, 1.0);
        float ndotv = max(dot(normal, view_dir), 0.0);
        rim = pow(1.0 - ndotv, 3.0) * nearness * 0.5;
    } else if (panels >= 2) {
        // Fallback: depth gradient rim
        vec2 depth_grad = vec2(
            dot(HOOKED_tex(vec2(uv.x + panel_w + texel.x, uv.y)).rgb, vec3(0.333)) -
            dot(HOOKED_tex(vec2(uv.x + panel_w - texel.x, uv.y)).rgb, vec3(0.333)),
            dot(HOOKED_tex(vec2(uv.x + panel_w, uv.y + texel.y)).rgb, vec3(0.333)) -
            dot(HOOKED_tex(vec2(uv.x + panel_w, uv.y - texel.y)).rgb, vec3(0.333))
        );
        rim = smoothstep(0.1, 0.5, length(depth_grad) * 4.0) * nearness * 0.3;
    }

    // ── Specular highlight from normals ──
    float spec = 0.0;
    if (has_normals) {
        vec3 light_dir = normalize(vec3(0.3, 0.5, 0.8));
        float ndotl = max(dot(normal, light_dir), 0.0);
        // Cel-shaded specular: hard step
        spec = step(0.85, ndotl) * nearness * 0.2;
    }

    // ── Compose ──
    vec3 result = cel;
    result += vec3(0.7, 0.8, 1.0) * rim;       // Blue-ish rim light
    result += vec3(1.0, 0.95, 0.9) * spec;     // Warm specular
    result = mix(result, vec3(0.02), outline);  // Ink outlines

    return vec4(clamp(result, 0.0, 1.0), 1.0);
}
