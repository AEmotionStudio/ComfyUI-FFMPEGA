//!HOOK MAIN
//!BIND HOOKED
//!DESC Kaleidoscope — fractal neon rings with cosine color palette

vec4 hook() {
    vec2 pos = HOOKED_pos;
    vec4 original = HOOKED_tex(pos);
    float t = float(frame) * 0.006;

    // Center and aspect-correct
    vec2 uv = (pos - 0.5) * 2.0;
    uv.x *= HOOKED_size.x / HOOKED_size.y;
    vec2 uv0 = uv;

    // Slow rotation over time (replaces mouse interaction)
    float rot_angle = t * 0.5;
    float rs = sin(rot_angle);
    float rc = cos(rot_angle);
    uv = vec2(rc * uv.x - rs * uv.y, rs * uv.x + rc * uv.y);

    // Cosine color palette
    // palette(t) = a + b * cos(2π(c*t + d))
    // a=0.5, b=0.5, c=1.0, d=(0.263, 0.416, 0.557)

    vec3 final_color = vec3(0.0);

    // Fractal kaleidoscope loop (4 iterations)
    for (int i = 0; i < 4; i++) {
        float fi = float(i);

        // Fold space: fract wrapping creates repeating cells
        uv = fract(uv * 1.5) - 0.5;

        // Distance with exponential falloff from original position
        float d = length(uv) * exp(-length(uv0));

        // Cosine palette color
        float palette_t = length(uv0) + fi * 0.4 + t;
        vec3 col = vec3(0.5) + vec3(0.5) * cos(
            6.28318 * (vec3(1.0) * palette_t + vec3(0.263, 0.416, 0.557))
        );

        // Neon rings: sine modulation creates concentric rings
        d = sin(d * 8.0 + t) / 8.0;
        d = abs(d);

        // Glow: inverse power creates bright emission at ring centers
        d = pow(0.01 / max(d, 0.001), 1.2);

        final_color += col * d;
    }

    // Contrast boost
    final_color = pow(max(final_color, vec3(0.0)), vec3(1.4));

    // Tone map to prevent blow-out
    final_color = final_color / (final_color + vec3(1.0));

    // Blend kaleidoscope over original image
    float strength = max(max(final_color.r, final_color.g), final_color.b);
    vec3 result = mix(original.rgb * 0.2, final_color + original.rgb * 0.1, smoothstep(0.01, 0.1, strength));

    return vec4(result, 1.0);
}
