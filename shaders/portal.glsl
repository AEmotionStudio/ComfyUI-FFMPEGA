//!HOOK MAIN
//!BIND HOOKED
//!DESC Portal Vortex — swirling vortex distortion that warps the image

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.03;

    vec2 center = vec2(0.5, 0.5);
    vec2 delta = uv - center;
    float dist = length(delta);
    float angle = atan(delta.y, delta.x);

    // Vortex twist: stronger near center, fades at edges
    float twist_amount = 3.0 * smoothstep(0.6, 0.0, dist);
    float twisted_angle = angle + twist_amount * (1.0 - dist) + t * 2.0;

    // Spiral arms
    float spiral = sin(twisted_angle * 3.0 - dist * 20.0 + t * 4.0) * 0.5 + 0.5;

    // Apply twist to UV
    vec2 twisted_uv = center + vec2(
        cos(twisted_angle),
        sin(twisted_angle)
    ) * dist;
    twisted_uv = clamp(twisted_uv, 0.0, 1.0);

    vec4 col = HOOKED_tex(twisted_uv);

    // Radial energy streaks
    float streaks = pow(spiral, 3.0) * smoothstep(0.5, 0.1, dist);

    // Portal rim glow
    float rim = smoothstep(0.05, 0.0, abs(dist - 0.35 - sin(t) * 0.05));
    rim += smoothstep(0.03, 0.0, abs(dist - 0.25 - cos(t * 1.3) * 0.03)) * 0.7;

    // Color: cool blues/purples at center, warm at rim
    vec3 portal_color = mix(
        vec3(0.2, 0.3, 1.0),   // deep blue center
        vec3(0.8, 0.3, 0.9),   // purple rim
        dist * 2.0
    );

    col.rgb += portal_color * (streaks * 0.5 + rim * 1.2);

    // Center brightening (event horizon glow)
    float center_glow = smoothstep(0.15, 0.0, dist) * 0.6;
    col.rgb += vec3(0.8, 0.9, 1.0) * center_glow;

    // Chromatic distortion near center
    if (dist < 0.3) {
        float ca = (0.3 - dist) * 0.02;
        vec2 ca_offset = normalize(delta + 0.0001) * ca;
        col.r = HOOKED_tex(twisted_uv + ca_offset).r;
        col.b = HOOKED_tex(twisted_uv - ca_offset).b;
    }

    return col;
}
