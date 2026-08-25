//!HOOK MAIN
//!BIND HOOKED
//!DESC Shockwave — expanding concentric ring distortion from center

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.025;

    vec2 center = vec2(0.5, 0.5);
    float dist = distance(uv, center);

    // Expanding ring — loops every ~4 seconds
    float ring_radius = fract(t * 0.3) * 1.2;
    float ring_width = 0.08;
    float ring_dist = abs(dist - ring_radius);
    float ring_strength = smoothstep(ring_width, 0.0, ring_dist);

    // Distortion: push pixels radially outward from shock front
    vec2 dir = normalize(uv - center + 0.0001);
    float distortion = ring_strength * 0.06 * sin(ring_dist * 80.0);
    vec2 displaced_uv = uv + dir * distortion;

    // Clamp
    displaced_uv = clamp(displaced_uv, 0.0, 1.0);

    vec4 col = HOOKED_tex(displaced_uv);

    // Bright flash at the ring front
    float flash = ring_strength * ring_strength * 0.8;
    vec3 flash_color = vec3(0.7, 0.85, 1.0);
    col.rgb += flash_color * flash;

    // Subtle chromatic aberration at shock front
    if (ring_strength > 0.1) {
        float ca = ring_strength * 0.01;
        col.r = HOOKED_tex(displaced_uv + dir * ca).r;
        col.b = HOOKED_tex(displaced_uv - dir * ca).b;
    }

    return col;
}
