//!HOOK MAIN
//!BIND HOOKED
//!DESC Watercolor — realistic wet watercolor with pigment pooling and paper texture

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 texel = 1.0 / HOOKED_size;
    float t = float(frame) * 0.005;

    // ── Paper texture (cold-press watercolor paper) ──
    float paper_hash1 = fract(sin(dot(uv * 600.0, vec2(12.9898, 78.233))) * 43758.5453);
    float paper_hash2 = fract(sin(dot(uv * 300.0, vec2(269.5, 183.3))) * 43758.5453);
    float paper_hash3 = fract(sin(dot(uv * 150.0, vec2(419.2, 371.9))) * 43758.5453);
    float paper = 0.88 + paper_hash1 * 0.05 + paper_hash2 * 0.04 + paper_hash3 * 0.03;

    // Paper fiber direction (adds directional texture)
    float fiber = sin(uv.x * HOOKED_size.x * 0.3 + paper_hash1 * 6.28) * 0.015;
    fiber += sin(uv.y * HOOKED_size.y * 0.2 + paper_hash2 * 6.28) * 0.01;

    // ── Kuwahara-style smoothing (watercolor blending) ──
    // Simplified anisotropic Kuwahara for soft, painterly regions
    int radius = 3;
    vec3 best_color = vec3(0.0);
    float min_var = 999.0;

    for (int qx = -1; qx <= 1; qx += 2) {
        for (int qy = -1; qy <= 1; qy += 2) {
            vec3 sum = vec3(0.0);
            vec3 sumSq = vec3(0.0);
            float count = 0.0;

            for (int dx = 0; dx <= radius; dx++) {
                for (int dy = 0; dy <= radius; dy++) {
                    vec2 offset = vec2(float(dx * qx), float(dy * qy)) * texel * 1.5;
                    vec3 s = HOOKED_tex(uv + offset).rgb;
                    sum += s;
                    sumSq += s * s;
                    count += 1.0;
                }
            }
            vec3 mean = sum / count;
            vec3 variance = sumSq / count - mean * mean;
            float totalVar = dot(variance, vec3(1.0));
            if (totalVar < min_var) {
                min_var = totalVar;
                best_color = mean;
            }
        }
    }

    // ── Edge-aware pigment pooling ──
    // Detect edges where pigment concentrates (darker at boundaries)
    float lum = dot(best_color, vec3(0.299, 0.587, 0.114));
    float edge = 0.0;
    for (int dx = -1; dx <= 1; dx++) {
        for (int dy = -1; dy <= 1; dy++) {
            if (dx == 0 && dy == 0) continue;
            vec2 offset = vec2(float(dx), float(dy)) * texel * 2.0;
            float n_lum = dot(HOOKED_tex(uv + offset).rgb, vec3(0.299, 0.587, 0.114));
            edge += abs(lum - n_lum);
        }
    }
    edge /= 8.0;

    // Pigment darkening at edges (wet paint pooling)
    float pigment_pool = smoothstep(0.01, 0.08, edge) * 0.25;

    // ── Color diffusion (soft bleeding between regions) ──
    vec3 bleed = vec3(0.0);
    float bw = 0.0;
    for (int dx = -2; dx <= 2; dx++) {
        for (int dy = -2; dy <= 2; dy++) {
            float w = exp(-float(dx*dx + dy*dy) / 3.0);
            // Slight downward bias (gravity pulls pigment)
            vec2 offset = vec2(float(dx), float(dy) + 0.3) * texel;
            bleed += HOOKED_tex(uv + offset).rgb * w;
            bw += w;
        }
    }
    bleed /= bw;

    // Mix Kuwahara result with bleed
    vec3 watercolor = mix(best_color, bleed, 0.3);

    // ── Subtle color quantization (watercolor has limited palette mixing) ──
    watercolor = floor(watercolor * 12.0 + 0.5) / 12.0;

    // ── Apply pigment pooling and paper ──
    watercolor -= pigment_pool;

    // Lighten towards paper white in bright areas
    float brightness = dot(watercolor, vec3(0.299, 0.587, 0.114));
    vec3 paper_color = vec3(0.97, 0.95, 0.90);
    float paper_show = smoothstep(0.65, 0.95, brightness);
    watercolor = mix(watercolor, paper_color, paper_show * 0.5);

    // Apply paper texture
    watercolor *= paper + fiber;

    // Desaturate slightly (watercolors are less vivid than digital)
    float gray = dot(watercolor, vec3(0.299, 0.587, 0.114));
    watercolor = mix(vec3(gray), watercolor, 0.85);

    // Warm tint
    watercolor += vec3(0.02, 0.01, -0.01);

    return vec4(clamp(watercolor, 0.0, 1.0), 1.0);
}
