//!HOOK MAIN
//!BIND HOOKED
//!DESC Ebruli — Turkish water marbling with liquid flow distortion

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.015;
    vec2 texel = 1.0 / HOOKED_size;

    // ── Simplex-like noise via layered trig (2D) ──
    // Approximation of simplex noise for domain warping
    float scale = 3.0;
    float speed = 0.5;
    float strength = 0.3;
    float color_shift = 0.008;

    float time = t * speed;

    // Layer 1 noise: base flow field
    vec2 p1 = uv * scale + vec2(time * 0.1, time * 0.2);
    float n1 = sin(p1.x * 2.3 + sin(p1.y * 3.1 + time)) *
               cos(p1.y * 2.7 + cos(p1.x * 1.9 - time * 0.5));
    n1 += sin(p1.x * 4.1 - p1.y * 2.3 + time * 0.3) * 0.5;
    n1 *= 0.5;

    // Apply first warp
    vec2 flow_uv = uv + vec2(n1) * strength;

    // Layer 2 noise: secondary turbulence on warped coords
    vec2 p2 = flow_uv * scale * 1.5 - time * 0.3;
    float n2 = sin(p2.x * 3.1 + cos(p2.y * 2.5 + time * 0.4)) *
               cos(p2.y * 2.1 + sin(p2.x * 3.7 - time * 0.6));
    n2 += sin(p2.x * 1.7 + p2.y * 4.3 + time * 0.5) * 0.4;
    n2 *= 0.5;

    // ── Chromatic aberration along flow ──
    // Sample R, G, B from slightly offset positions
    vec2 r_offset = flow_uv + vec2(n2 * color_shift, 0.0);
    vec2 g_offset = flow_uv;
    vec2 b_offset = flow_uv - vec2(n2 * color_shift, 0.0);

    // Clamp to valid range
    r_offset = clamp(r_offset, 0.0, 1.0);
    g_offset = clamp(g_offset, 0.0, 1.0);
    b_offset = clamp(b_offset, 0.0, 1.0);

    float r = HOOKED_tex(r_offset).r;
    float g = HOOKED_tex(g_offset).g;
    float b = HOOKED_tex(b_offset).b;

    vec3 marbled = vec3(r, g, b);

    // ── Saturation boost for marbling richness ──
    float lum = dot(marbled, vec3(0.299, 0.587, 0.114));
    marbled = mix(vec3(lum), marbled, 1.4);

    // ── Subtle vignette ──
    float vignette = 1.0 - smoothstep(0.5, 1.5, length((uv - 0.5) * 2.0));
    marbled *= vignette;

    // ── Additional swirl: add subtle color tint based on flow ──
    vec3 warm_tint = vec3(1.02, 0.98, 0.95);
    vec3 cool_tint = vec3(0.95, 0.98, 1.03);
    float tint_mix = sin(n1 * 3.0 + n2 * 2.0 + time) * 0.5 + 0.5;
    marbled *= mix(warm_tint, cool_tint, tint_mix);

    return vec4(marbled, 1.0);
}
