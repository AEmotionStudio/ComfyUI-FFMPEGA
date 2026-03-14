//!HOOK MAIN
//!BIND HOOKED
//!DESC Jelly Wobble — elastic gelatin distortion that wobbles with motion

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.06;

    // Multiple overlapping sine-wave distortions at different frequencies
    // to create organic, squishy jelly-like movement
    vec2 wobble = vec2(0.0);

    // Primary wobble: large slow undulation
    wobble.x += sin(uv.y * 8.0 + t * 3.0) * 0.015;
    wobble.y += cos(uv.x * 7.0 + t * 2.5) * 0.015;

    // Secondary wobble: faster ripples
    wobble.x += sin(uv.y * 15.0 - t * 5.0 + uv.x * 3.0) * 0.008;
    wobble.y += cos(uv.x * 13.0 + t * 4.0 + uv.y * 4.0) * 0.008;

    // Tertiary: very fast micro-jiggle
    wobble.x += sin(uv.y * 30.0 + t * 8.0) * 0.003;
    wobble.y += sin(uv.x * 25.0 - t * 7.0) * 0.003;

    // Edge stiffness: wobble less at frame edges (like jelly in a mold)
    float edge_x = smoothstep(0.0, 0.15, uv.x) * smoothstep(0.0, 0.15, 1.0 - uv.x);
    float edge_y = smoothstep(0.0, 0.15, uv.y) * smoothstep(0.0, 0.15, 1.0 - uv.y);
    wobble *= edge_x * edge_y;

    vec2 sample_uv = clamp(uv + wobble, 0.0, 1.0);
    vec4 col = HOOKED_tex(sample_uv);

    // Subtle caustic-like bright spots from refraction
    float caustic = sin(uv.x * 40.0 + wobble.x * 200.0 + t * 2.0)
                  * sin(uv.y * 35.0 + wobble.y * 200.0 - t * 1.5);
    caustic = pow(max(caustic, 0.0), 3.0) * 0.15;
    col.rgb += caustic;

    // Very slight color shift at high-distortion areas
    float distortion_amount = length(wobble) * 50.0;
    col.r = HOOKED_tex(sample_uv + wobble * 0.3).r;
    col.b = HOOKED_tex(sample_uv - wobble * 0.3).b;

    return col;
}
