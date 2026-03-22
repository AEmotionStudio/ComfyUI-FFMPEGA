//!HOOK MAIN
//!BIND HOOKED
//!DESC Watercolor Bleed — wet watercolor with animated bleeding edges and pigment flow

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 texel = 1.0 / HOOKED_size;
    float t = float(frame) * 0.008;

    vec4 col = HOOKED_tex(uv);
    float lum = dot(col.rgb, vec3(0.299, 0.587, 0.114));

    // ── Paper texture (rough watercolor paper) ──
    float p1 = fract(sin(dot(uv * 500.0, vec2(12.9898, 78.233))) * 43758.5453);
    float p2 = fract(sin(dot(uv * 250.0, vec2(269.5, 183.3))) * 43758.5453);
    float paper = 0.90 + p1 * 0.06 + p2 * 0.04;

    // ── Animated edge-aware bleed (pigment spreads along wet paper) ──
    // Edge detection determines where pigment pools
    float edge = 0.0;
    vec2 grad = vec2(0.0);
    for (int dx = -1; dx <= 1; dx++) {
        for (int dy = -1; dy <= 1; dy++) {
            if (dx == 0 && dy == 0) continue;
            vec2 offset = vec2(float(dx), float(dy)) * texel * 1.5;
            float n_lum = dot(HOOKED_tex(uv + offset).rgb, vec3(0.299, 0.587, 0.114));
            float diff = abs(lum - n_lum);
            edge += diff;
            grad += vec2(float(dx), float(dy)) * diff;
        }
    }
    edge /= 8.0;
    grad = normalize(grad + 0.001);

    // ── Animated flow direction (time-varying bleed) ──
    // Water flows influenced by gravity + surface tension
    float flow_angle = atan(grad.y, grad.x) + sin(t * 0.5) * 0.3;
    vec2 flow_dir = vec2(cos(flow_angle), sin(flow_angle));

    // Add downward gravity bias
    flow_dir = normalize(flow_dir + vec2(0.0, 0.4));

    // ── Progressive bleed sampling along flow direction ──
    vec3 bleed = col.rgb;
    float total_w = 1.0;

    for (int i = 1; i <= 5; i++) {
        float fi = float(i);
        // Flow offset with time-varying wobble
        vec2 wobble = vec2(
            sin(t * 2.0 + fi * 1.7) * 0.3,
            cos(t * 1.5 + fi * 2.3) * 0.3
        );
        vec2 offset = (flow_dir + wobble * 0.2) * texel * fi * 2.0;

        float w = exp(-fi * 0.4);
        bleed += HOOKED_tex(uv + offset).rgb * w;
        bleed += HOOKED_tex(uv - offset * 0.5).rgb * w * 0.3;
        total_w += w + w * 0.3;
    }
    bleed /= total_w;

    // ── Pigment pooling at edges (darker) ──
    float pool = smoothstep(0.02, 0.10, edge);
    float pool_darken = 1.0 - pool * 0.3;

    // ── Wet-on-wet diffusion (blur in saturated areas) ──
    vec3 diffused = vec3(0.0);
    float dw = 0.0;
    float saturation = length(col.rgb - vec3(lum));

    // More diffusion in colorful (wet) areas
    float diff_radius = mix(1.0, 2.5, saturation * 2.0);
    for (int dx = -2; dx <= 2; dx++) {
        for (int dy = -2; dy <= 2; dy++) {
            float w = exp(-float(dx*dx + dy*dy) / (diff_radius * diff_radius));
            diffused += HOOKED_tex(uv + vec2(float(dx), float(dy)) * texel).rgb * w;
            dw += w;
        }
    }
    diffused /= dw;

    // Mix between sharp and diffused based on wetness
    float wetness = 0.3 + saturation * 1.5;
    wetness = clamp(wetness, 0.0, 0.7);
    vec3 watercolor = mix(bleed, diffused, wetness);

    // ── Color quantization (limited palette) ──
    watercolor = floor(watercolor * 10.0 + 0.5) / 10.0;

    // ── Apply pooling and paper ──
    watercolor *= pool_darken;

    // Paper shows through in light areas
    vec3 paper_color = vec3(0.96, 0.94, 0.88);
    float paper_mix = smoothstep(0.7, 0.95, dot(watercolor, vec3(0.33)));
    watercolor = mix(watercolor, paper_color, paper_mix * 0.6);

    // Apply paper texture
    watercolor *= paper;

    // Warm tint
    watercolor += vec3(0.015, 0.005, -0.01);

    // Desaturate slightly
    float g = dot(watercolor, vec3(0.299, 0.587, 0.114));
    watercolor = mix(vec3(g), watercolor, 0.82);

    return vec4(clamp(watercolor, 0.0, 1.0), 1.0);
}
