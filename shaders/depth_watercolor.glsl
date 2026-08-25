//!HOOK MAIN
//!BIND HOOKED
//!DESC Depth Watercolor — stroke direction from surface normals

// Auto-detect panel layout:
//   2 panels: [color | depth]
//   3 panels: [color | depth | normals]

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 texel = 1.0 / HOOKED_size;
    float t = float(frame) * 0.006;
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
    float lum = dot(col.rgb, vec3(0.299, 0.587, 0.114));

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

    float nearness = 1.0 - depth;

    // ── Depth-adaptive blur (Kuwahara-style) ──
    float kernel_size = mix(4.0, 1.5, nearness);

    // Normal-based stroke direction
    vec2 stroke_dir = vec2(1.0, 0.0); // default horizontal
    if (has_normals) {
        // Use surface tangent as stroke direction
        // Project normal's XY onto stroke plane
        stroke_dir = normalize(vec2(normal.y, -normal.x) + vec2(0.001));
    }

    vec3 smoothed = vec3(0.0);
    float sw = 0.0;
    int ksize = int(kernel_size + 0.5);
    for (int dx = -ksize; dx <= ksize; dx++) {
        for (int dy = -ksize; dy <= ksize; dy++) {
            vec2 d = vec2(float(dx), float(dy));
            float dist = length(d);
            if (dist > kernel_size) continue;

            // With normals: elongate kernel along stroke direction
            float w;
            if (has_normals) {
                float along = abs(dot(normalize(d + vec2(0.001)), stroke_dir));
                // Elongate: samples along stroke direction have higher weight
                float stretch = mix(0.5, 1.5, along);
                w = exp(-dist * dist / (kernel_size * kernel_size * 0.5 * stretch));
            } else {
                w = exp(-dist * dist / (kernel_size * kernel_size * 0.5));
            }

            vec2 s_uv = uv + d * texel;
            s_uv.x = clamp(s_uv.x, 0.0, panel_w - texel.x);
            smoothed += HOOKED_tex(s_uv).rgb * w;
            sw += w;
        }
    }
    smoothed /= sw;

    // ── Depth-adaptive color quantization ──
    float palette = mix(5.0, 12.0, nearness);
    vec3 quantized = floor(smoothed * palette + 0.5) / palette;

    // ── Paper texture ──
    float paper_scale = mix(200.0, 600.0, nearness);
    float p1 = fract(sin(dot(uv * paper_scale, vec2(12.9898, 78.233))) * 43758.5453);
    float p2 = fract(sin(dot(uv * paper_scale * 0.5, vec2(269.5, 183.3))) * 43758.5453);
    float paper = 0.92 + p1 * 0.05 + p2 * 0.03;

    // Normal-based paper texture variation
    if (has_normals) {
        // Surfaces facing away from camera show more paper grain
        float facing = max(dot(normal, vec3(0.0, 0.0, 1.0)), 0.0);
        paper *= mix(0.88, 1.0, facing);
    }

    // ── Pigment edge pooling ──
    float depth_edge = 0.0;
    float color_edge = 0.0;
    if (panels >= 2) {
        for (int dx = -1; dx <= 1; dx++) {
            for (int dy = -1; dy <= 1; dy++) {
                if (dx == 0 && dy == 0) continue;
                vec2 offset = vec2(float(dx), float(dy)) * texel;
                float nd = dot(HOOKED_tex(vec2(uv.x + panel_w + offset.x, uv.y + offset.y)).rgb, vec3(0.333));
                depth_edge += abs(depth - nd);
                float nl = dot(HOOKED_tex(uv + offset).rgb, vec3(0.299, 0.587, 0.114));
                color_edge += abs(lum - nl);
            }
        }
        depth_edge /= 8.0;
        color_edge /= 8.0;
    }

    // Normal-based pooling enhancement
    float normal_pool = 0.0;
    if (has_normals) {
        // Concave surfaces (normal z < 1) collect more pigment
        normal_pool = (1.0 - max(normal.z, 0.0)) * 0.2 * nearness;
    }

    float pool = smoothstep(0.01, 0.06, depth_edge) * 0.4 +
                 smoothstep(0.03, 0.10, color_edge) * nearness * 0.3 +
                 normal_pool;
    float pool_darken = 1.0 - pool;

    // ── Wet edge bleeding ──
    float bleed_amount = mix(2.0, 0.5, nearness);
    vec2 flow = vec2(
        sin(t + uv.y * 10.0) * 0.5,
        cos(t * 0.7 + uv.x * 8.0) * 0.3 + 0.5
    );

    // Normal-influenced flow: pigment flows along surface tilt
    if (has_normals) {
        flow += normal.xy * 0.4;
    }

    vec2 bleed_offset = normalize(flow) * texel * bleed_amount;
    vec2 bleed_uv = uv + bleed_offset;
    bleed_uv.x = clamp(bleed_uv.x, 0.0, panel_w - texel.x);
    vec3 bled = HOOKED_tex(bleed_uv).rgb;

    float bleed_mix = depth * 0.3;
    quantized = mix(quantized, bled, bleed_mix);

    // ── Compose ──
    vec3 result = quantized * pool_darken;

    vec3 paper_color = vec3(0.97, 0.95, 0.90);
    float paper_show = smoothstep(0.75, 0.95, dot(result, vec3(0.33)));
    result = mix(result, paper_color, paper_show * 0.5);
    result *= paper;

    // Warm tint + depth desaturation
    result += vec3(0.015, 0.008, -0.008);
    float g = dot(result, vec3(0.299, 0.587, 0.114));
    float desat = mix(0.75, 0.92, nearness);
    result = mix(vec3(g), result, desat);

    return vec4(clamp(result, 0.0, 1.0), 1.0);
}
