//!HOOK MAIN
//!BIND HOOKED
//!DESC Oil Paint — Kuwahara painterly smoothing with thick brush strokes

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 texel = 1.0 / HOOKED_size;

    // Kuwahara filter: sample 4 quadrants, pick the one with lowest variance
    // This creates the distinctive flat-color brush stroke look
    int radius = 4;
    vec3 best_color = vec3(0.0);
    float min_var = 999.0;

    for (int qx = -1; qx <= 1; qx += 2) {
        for (int qy = -1; qy <= 1; qy += 2) {
            vec3 sum = vec3(0.0);
            vec3 sumSq = vec3(0.0);
            float count = 0.0;

            for (int dx = 0; dx <= radius; dx++) {
                for (int dy = 0; dy <= radius; dy++) {
                    vec2 offset = vec2(float(dx * qx), float(dy * qy)) * texel;
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

    // Directional brush strokes: detect local gradient for stroke direction
    float lum_l = dot(HOOKED_tex(uv + vec2(-texel.x, 0.0)).rgb, vec3(0.33));
    float lum_r = dot(HOOKED_tex(uv + vec2(texel.x, 0.0)).rgb, vec3(0.33));
    float lum_u = dot(HOOKED_tex(uv + vec2(0.0, -texel.y)).rgb, vec3(0.33));
    float lum_d = dot(HOOKED_tex(uv + vec2(0.0, texel.y)).rgb, vec3(0.33));

    float gx = lum_r - lum_l;
    float gy = lum_d - lum_u;

    // Perpendicular to gradient = stroke direction
    vec2 stroke_dir = normalize(vec2(-gy, gx) + 0.0001);

    // Sample along stroke direction for elongated brush effect
    vec3 stroke_color = best_color;
    float sw = 1.0;
    for (int i = 1; i <= 3; i++) {
        float w = 1.0 / float(i + 1);
        stroke_color += HOOKED_tex(uv + stroke_dir * texel * float(i) * 2.0).rgb * w;
        stroke_color += HOOKED_tex(uv - stroke_dir * texel * float(i) * 2.0).rgb * w;
        sw += w * 2.0;
    }
    stroke_color /= sw;

    // Blend Kuwahara with stroke-extended sampling
    vec3 result = mix(best_color, stroke_color, 0.4);

    // Subtle color quantization for painterly feel
    result = floor(result * 20.0) / 20.0;

    // Boost saturation slightly
    float lum = dot(result, vec3(0.299, 0.587, 0.114));
    result = mix(vec3(lum), result, 1.3);

    return vec4(result, 1.0);
}
