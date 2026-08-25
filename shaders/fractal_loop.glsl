//!HOOK MAIN
//!BIND HOOKED
//!DESC Fractal Loop — iterated inversion fractal with rainbow distance coloring

vec4 hook() {
    vec2 pos = HOOKED_pos;
    vec4 original = HOOKED_tex(pos);
    float t = float(frame) * 0.003;

    // Center and aspect-correct
    vec2 uv = (pos - 0.5) * 2.0;
    uv.x *= HOOKED_size.x / HOOKED_size.y;

    // Fractal iteration: abs-fold + inversion + rotation
    for (int i = 0; i < 5; i++) {
        // Fold: mirror into positive quadrant
        uv = abs(uv);

        // Inversion: divide by squared length (Möbius-like)
        uv = uv / dot(uv, uv);

        // Translate
        uv -= 0.7;

        // Rotate: per-iteration with time
        float a = t * 0.3 + float(i) * 0.5;
        float s = sin(a);
        float c = cos(a);
        uv = vec2(c * uv.x - s * uv.y, s * uv.x + c * uv.y);
    }

    // Distance from origin in fractal space
    float d = length(uv);

    // Rainbow coloring based on distance
    vec3 fractal_col;
    fractal_col.r = 0.5 + 0.5 * sin(d * 3.0 - t * 2.0);
    fractal_col.g = 0.5 + 0.5 * sin(d * 3.5 - t * 1.5);
    fractal_col.b = 0.5 + 0.5 * sin(d * 4.0 - t * 3.0);

    // Distance fade
    fractal_col /= (d * 0.8 + 1.0);

    // Blend fractal over original image
    float fractal_strength = max(max(fractal_col.r, fractal_col.g), fractal_col.b);
    vec3 result = mix(original.rgb * 0.3, fractal_col + original.rgb * 0.15, smoothstep(0.02, 0.15, fractal_strength));

    return vec4(result, 1.0);
}
