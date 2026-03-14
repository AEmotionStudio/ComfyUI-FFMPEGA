//!HOOK MAIN
//!BIND HOOKED
//!DESC Space Tunnel — warp tunnel with nebula, rings, god rays and stars

vec4 hook() {
    vec2 pos = HOOKED_pos;
    vec4 original = HOOKED_tex(pos);
    float t = float(frame) * 0.009;

    // Center and aspect-correct
    vec2 uv = (pos - 0.5) * 2.0;
    uv.x *= HOOKED_size.x / HOOKED_size.y;
    vec2 uv_orig = uv;

    float time = t * 0.3;

    // ── FBM domain warping (6 octaves via trig approx) ──
    float displacement_x = 0.0;
    float displacement_y = 0.0;
    float amp = 0.5;
    float freq = 1.0;
    vec2 p_dx = uv + time;
    vec2 p_dy = uv - time;
    for (int i = 0; i < 6; i++) {
        displacement_x += amp * sin(p_dx.x * freq * 2.3 + p_dx.y * freq * 1.7 + time);
        displacement_y += amp * sin(p_dy.x * freq * 1.9 + p_dy.y * freq * 2.1 - time);
        amp *= 0.5;
        freq *= 2.0;
    }
    uv += vec2(displacement_x, displacement_y) * 0.12;

    // ── Tunnel geometry ──
    float angle = atan(uv.y, uv.x);
    float radius = length(uv);
    float tunnel_depth = log(max(radius, 0.001)) - time * 1.5;

    // ── Concentric ring pattern ──
    float ring_pattern = fract(tunnel_depth * 0.3);
    float rings = smoothstep(0.8, 0.75, ring_pattern) * 0.5;

    // ── Nebula noise (trig-based simplex approx) ──
    vec2 neb_p = vec2(angle * 6.0, tunnel_depth);
    float nebula = sin(neb_p.x * 1.3 + neb_p.y * 2.1 + time) *
                   cos(neb_p.y * 1.7 - neb_p.x * 0.9 + time * 0.5);
    nebula += sin(neb_p.x * 3.1 + neb_p.y * 1.5 - time * 0.3) * 0.5;
    nebula = smoothstep(0.2, 0.8, nebula * 0.5 + 0.5);

    // ── Volumetric god rays ──
    float ray_base = sin(angle * 25.0 + time * 0.5) *
                     cos(angle * 17.0 - time * 0.3) * 0.5 + 0.5;
    float rays = pow(max(0.0, ray_base), 10.0);
    rays *= smoothstep(2.0, 0.0, radius);

    // ── Cosine color palette ──
    float palette_t = nebula + rings;
    vec3 col = vec3(0.5) + vec3(0.5) * cos(
        6.28318 * (vec3(1.0, 1.0, 0.5) * palette_t +
                   vec3(0.0, 0.10, 0.20 + time * 0.1))
    );

    // God ray warm color
    col += rays * vec3(1.0, 0.7, 0.3);

    // Center darkness (tunnel opening)
    col *= smoothstep(0.0, 0.15, radius);

    // ── Rushing star field ──
    float star_seed = fract(sin(dot(floor(uv_orig * 250.0), vec2(12.9898, 4.1414))) * 43758.5453);
    float star_intensity = pow(star_seed, 40.0);
    float star_speed = 1.0 + fract(sin(dot(floor(uv_orig * 50.0), vec2(12.9898, 4.1414))) * 43758.5453) * 2.0;
    float star_rush = smoothstep(0.9, 0.0, length(uv_orig) + fract(time * star_speed) - 1.0);
    col += vec3(star_intensity * star_rush);

    // ── Gamma + tone map ──
    col = pow(max(col, vec3(0.0)), vec3(0.85));
    col = col / (col + vec3(1.0));

    // ── Blend tunnel over original ──
    float strength = max(max(col.r, col.g), col.b);
    vec3 result = mix(original.rgb * 0.15, col + original.rgb * 0.1, smoothstep(0.01, 0.08, strength));

    return vec4(result, 1.0);
}
