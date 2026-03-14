//!HOOK MAIN
//!BIND HOOKED
//!DESC Spirals — shifting multi-layer spiral vortex with HSV rainbow

vec4 hook() {
    vec2 pos = HOOKED_pos;
    vec4 original = HOOKED_tex(pos);
    float t = float(frame) * 0.012;

    // Center and aspect-correct
    vec2 uv = (pos - 0.5) * 2.0;
    uv.x *= HOOKED_size.x / HOOKED_size.y;

    float r = length(uv);
    float theta = atan(uv.y, uv.x);

    vec3 color_acc = vec3(0.0);

    // 12 spiral layers with shifting rotation + rainbow HSV
    for (int i = 1; i < 12; i++) {
        float fi = float(i);

        // Scale UV per layer
        vec2 p = uv * (1.0 + fi * 0.15);

        // Per-layer twist rotation
        float twist = sin(t + fi * 0.2) * 2.0;
        float ct = cos(twist);
        float st = sin(twist);
        p = vec2(ct * p.x - st * p.y, st * p.x + ct * p.y);

        // Modulated polar coordinates
        float mod_theta = mod(theta * (2.0 + sin(t + fi * 0.3)) + t, 6.2831853);
        float mod_r = pow(max(r, 0.001), 1.0 + cos(t * 0.5 + fi * 0.2) * 0.2);

        // Double-pattern interference
        float pattern1 = sin(mod_theta * 8.0 + t) * cos(mod_r * 15.0 + t * 0.5);
        float pattern2 = cos(length(p) * 10.0 - t) * sin(atan(p.y, p.x) * 5.0);
        float pattern = pattern1 * pattern2;

        // Radial weight with breathing
        float weight = smoothstep(0.8, 0.0, mod_r * (1.0 + 0.2 * sin(t + fi)));
        weight *= 1.0 + 0.5 * sin(t * 2.0 + fi * 0.5);

        // HSV rainbow color per layer
        float hue = mod(0.1 * fi + t * 0.2, 1.0);
        float sat = 0.7 + 0.3 * sin(t + fi * 0.5);
        float val = weight * abs(pattern) * 1.2;

        // HSV to RGB inline
        vec3 k = vec3(1.0, 2.0 / 3.0, 1.0 / 3.0);
        vec3 pp = abs(fract(vec3(hue) + k) * 6.0 - 3.0);
        vec3 layer_color = val * mix(vec3(1.0), clamp(pp - 1.0, 0.0, 1.0), sat);

        color_acc += layer_color * weight;
    }

    // Brightness boost + gamma correction
    color_acc *= 1.2;
    color_acc = pow(max(color_acc, vec3(0.0)), vec3(0.4545));

    // Tone map
    color_acc = color_acc / (color_acc + vec3(1.0));

    // Blend spirals over original
    float strength = max(max(color_acc.r, color_acc.g), color_acc.b);
    vec3 result = mix(original.rgb * 0.2, color_acc + original.rgb * 0.1, smoothstep(0.01, 0.08, strength));

    return vec4(result, 1.0);
}
