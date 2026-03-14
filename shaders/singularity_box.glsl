//!HOOK MAIN
//!BIND HOOKED
//!DESC Singularity Box — raymarched spiral singularity with zone coloring

vec4 hook() {
    vec2 pos = HOOKED_pos;
    vec4 original = HOOKED_tex(pos);
    float t = float(frame) * 0.016;

    // Normalized coordinates
    vec2 uv = pos * 2.0 - 1.0;
    uv.x *= HOOKED_size.x / HOOKED_size.y;

    vec4 o = vec4(0.0);

    float wx = 1.4 + 0.2 * sin(t * 0.5);
    float wy = 1.0;

    // 20-iteration volumetric march
    for (int i = 0; i < 20; i++) {
        float fi = float(i);
        float z = fi;

        // Ray direction
        vec3 p = z * normalize(vec3(uv, 1.0));
        vec3 a = p;

        // Rectangular distance field
        vec2 rect_coord = abs(a.xy);
        float rect_dist = max(rect_coord.x / wx, rect_coord.y / wy);

        // Spiral rotation based on rect distance
        float spiral_rot = t * 0.7 + 5.0 / (rect_dist + 0.3);
        float cr = cos(spiral_rot);
        float sr = sin(spiral_rot);
        a.xy = vec2(cr * a.x - sr * a.y, sr * a.x + cr * a.y);

        // Iterative folding (6 octaves)
        for (int dd = 2; dd < 8; dd++) {
            float freq = float(dd) + sin(t * 0.3 + fi * 0.1);
            vec3 fold = sin(a * freq + t + fi);
            a -= vec3(fold.y, fold.z, fold.x) / float(dd);
        }

        // Spiral arms pattern
        float dist = length(a.xy);
        vec2 rect2 = abs(a.xy);
        float rd2 = max(rect2.x / wx, rect2.y / wy);
        float angle = atan(a.y, a.x);

        float spiral_arms = sin(angle * 7.0 - rd2 * 4.0 + t * 1.5) * 0.8 +
                           sin(angle * 3.0 + rd2 * 2.0 - t) * 0.3;

        // Micro noise
        float noise = sin(a.x * 10.0 + t * 2.0) * cos(a.y * 10.0 + t * 3.0) * 0.05;
        spiral_arms += noise;

        // Surface distance
        float s = a.z + a.y - t * 1.2;
        float outer_d = abs(0.7 - dist + spiral_arms * 0.25) +
                       abs(cos(s * 1.5)) / 6.0 + abs(sin(s * 2.0)) / 8.0;
        outer_d = max(0.02, outer_d);
        z += outer_d;

        // Zone-based color shifting
        float pulse = sin(t * 2.0 + rect_dist * 5.0) * 0.5 + 0.5;
        vec4 color_shift;
        if (rect_dist < 0.5) {
            color_shift = vec4(0.0, 2.5 * pulse, 8.0, 0.0);
        } else if (rect_dist < 1.0) {
            color_shift = vec4(1.5 * pulse, 1.0, 7.5, 0.0);
        } else if (rect_dist < 1.5) {
            color_shift = vec4(1.0, 0.0, 8.5 * pulse, 0.0);
        } else {
            color_shift = vec4(0.5 * pulse, 1.5, 7.0, 0.0);
        }

        // Glow accumulation
        float glow = 1.0 / (outer_d * outer_d * 0.05 + 0.2);
        o += (1.5 + glow * 1.5) * (cos(s - z + color_shift) + 1.0) / outer_d;
    }

    // Normalize and tone map
    o = o / 150.0;
    o = o / (1.0 + o);  // Reinhard

    // Vignette
    float vig = 1.0 - length(pos - 0.5) * 1.0;
    o.rgb *= max(vig, 0.0);

    // Gamma
    o.rgb = pow(max(o.rgb, vec3(0.0)), vec3(0.9));

    // Blend over original
    float strength = max(max(o.r, o.g), o.b);
    vec3 result = mix(original.rgb * 0.15, o.rgb + original.rgb * 0.08,
                      smoothstep(0.005, 0.06, strength));

    return vec4(result, 1.0);
}
