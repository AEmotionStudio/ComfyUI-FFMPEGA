//!HOOK MAIN
//!BIND HOOKED
//!DESC Smoke — animated fog wisps drifting across the frame

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.02;
    vec4 col = HOOKED_tex(uv);

    // Multi-octave procedural smoke noise
    float smoke = 0.0;
    float amp = 1.0;
    float freq = 3.0;

    for (int i = 0; i < 5; i++) {
        vec2 p = uv * freq + vec2(t * (0.3 + float(i) * 0.1), float(i) * 1.5);
        // Pseudo-noise via layered sines
        float n = sin(p.x * 2.3 + sin(p.y * 3.1)) *
                  cos(p.y * 2.7 + cos(p.x * 1.9)) * 0.5 + 0.5;
        n *= sin(p.x * 1.1 - p.y * 0.7 + t * 0.5) * 0.5 + 0.5;
        smoke += n * amp;
        amp *= 0.5;
        freq *= 2.1;
    }
    smoke /= 1.9;

    // Wisps: concentrate smoke in flowing streams
    float wisp1 = sin(uv.x * 5.0 + t * 0.8 + sin(uv.y * 3.0)) * 0.5 + 0.5;
    float wisp2 = sin(uv.x * 3.0 - t * 0.6 + cos(uv.y * 5.0 + t * 0.3)) * 0.5 + 0.5;
    float wisp3 = cos(uv.y * 4.0 + t * 0.4 + sin(uv.x * 2.0)) * 0.5 + 0.5;
    float wisps = pow(wisp1 * wisp2, 1.5) + pow(wisp2 * wisp3, 1.5) * 0.5;

    float final_smoke = smoke * wisps;

    // Density: thicker at bottom, thinner at top
    float density_gradient = smoothstep(0.0, 0.7, 1.0 - uv.y);
    final_smoke *= mix(0.4, 1.0, density_gradient);

    // Smoke color: warm gray with slight blue tint
    vec3 smoke_color = mix(
        vec3(0.6, 0.6, 0.65),  // light smoke
        vec3(0.25, 0.25, 0.3), // dark smoke
        final_smoke
    );

    // Blend smoke over original (screen-like)
    float smoke_opacity = final_smoke * 0.6;
    vec3 result = mix(col.rgb, smoke_color, smoke_opacity);

    // Light scattering: brighten where smoke is thin
    float scatter = (1.0 - final_smoke) * 0.08 * density_gradient;
    result += vec3(0.8, 0.75, 0.7) * scatter;

    return vec4(result, 1.0);
}
