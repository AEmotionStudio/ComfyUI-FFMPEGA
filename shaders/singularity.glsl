//!HOOK MAIN
//!BIND HOOKED
//!DESC Singularity — wormhole traverse with energy fibers, rings, clouds and sparks

vec4 hook() {
    vec2 pos = HOOKED_pos;
    vec4 original = HOOKED_tex(pos);
    float t = float(frame) * 0.01;

    // Center and aspect-correct
    vec2 uv = (pos - 0.5) * 2.0;
    uv.x *= HOOKED_size.x / HOOKED_size.y;

    // Polar coordinates for tunnel geometry
    float angle = atan(uv.y, uv.x);
    float radius = length(uv);

    // Tunnel depth (log mapping creates infinite depth illusion)
    float z = log(max(radius, 0.001)) * 14.0 - t * 3.5;

    // Twisted angle (wormhole warping)
    float twisted_angle = angle + sin(z * 0.18) * 2.2 + cos(z * 0.08) * 1.1;

    // 3D position on tunnel surface
    float cx = cos(twisted_angle);
    float sx = sin(twisted_angle);

    vec3 color = vec3(0.0);

    // ── Dark base nebula ──
    float n_base = sin(cx * 0.35 + z * 0.35 + t * 0.18) *
                   cos(sx * 0.35 + z * 0.2 - t * 0.1) * 0.5 + 0.5;
    vec3 base_a = vec3(0.01, 0.005, 0.06);
    vec3 base_b = vec3(0.06, 0.02, 0.18);
    color += mix(base_a, base_b, n_base);

    // ── Energy fibers (cyan + magenta) ──
    float n_fib = sin(cx * 4.5 + t * 1.1 + z * 0.13) *
                  cos(sx * 4.5 - t * 0.5 + z * 0.2);
    n_fib += sin(cx * 6.0 + sx * 3.0 + t * 0.8) * 0.4;
    float fib = pow(max(0.0, smoothstep(0.2, 0.7, n_fib * 0.5 + 0.5)), 2.2);

    float n_fib2 = sin(cx * 6.75 - t * 0.7 + z * 0.2) *
                   cos(sx * 6.75 + t * 0.4 - z * 0.15);
    n_fib2 += sin(cx * 4.0 - sx * 5.0 - t * 0.5) * 0.35;
    float fib2 = pow(max(0.0, smoothstep(0.25, 0.75, n_fib2 * 0.5 + 0.5)), 2.0);

    color += vec3(0.0, 0.85, 1.0) * fib * 2.2;      // Cyan fibers
    color += vec3(1.0, 0.12, 0.72) * fib2 * 2.0;     // Magenta fibers
    color += vec3(0.65, 0.25, 1.0) * fib * fib2 * 2.8; // Purple intersection

    // ── Pulsating rings (gold + teal) ──
    float zD1 = z * 2.6 + sin(cx * 1.4 + sx * 1.4 - t) * 2.2;
    float zD2 = z * 3.8 + cos(cx * 2.0 + sx * 2.0 + t * 1.3) * 1.5;
    float rings1 = smoothstep(0.94, 1.0, abs(sin(zD1)));
    float rings2 = smoothstep(0.96, 1.0, abs(sin(zD2)));

    // Noise-modulated ring visibility
    float ring_mask1 = sin(cx * 2.0 + sx * 2.0 + t) * 0.5 + 0.5;
    float ring_mask2 = cos(cx * 2.5 - sx * 2.5 - t * 0.8) * 0.5 + 0.5;
    rings1 *= smoothstep(0.2, 1.0, ring_mask1);
    rings2 *= smoothstep(0.3, 1.0, ring_mask2);

    color += vec3(1.0, 0.75, 0.25) * rings1 * 2.5;   // Gold rings
    color += vec3(0.15, 1.0, 0.82) * rings2 * 2.2;    // Teal rings

    // ── Between-mask for clouds and filaments ──
    float rings_total = rings1 + rings2;
    float between_mask = 1.0 - smoothstep(0.01, 0.20, rings_total);
    between_mask *= 1.0 - smoothstep(0.03, 0.28, fib + fib2);
    between_mask = clamp(between_mask, 0.0, 1.0);

    // ── Dark matter clouds ──
    float cloud = sin(cx * 1.3 + z * 0.4 - t * 0.07) *
                  cos(sx * 1.3 + z * 0.3 + t * 0.04);
    cloud += sin(cx * 4.4 + z * 0.9 + t * 0.04) * 0.35;
    cloud = smoothstep(-0.18, 0.72, cloud * 0.5 + 0.5);
    vec3 cloud_col = mix(vec3(0.02, 0.01, 0.07), vec3(0.10, 0.04, 0.20), cloud);
    cloud_col += vec3(0.0, 0.04, 0.12) * smoothstep(0.6, 1.0, cloud);
    color += cloud_col * between_mask * 0.7;

    // ── Dust sparks ──
    float spark_seed = fract(sin(dot(vec2(cx * 20.0, z * 4.5), vec2(12.9898, 78.233))) * 43758.5453);
    float spark = smoothstep(0.88, 0.99, spark_seed);
    vec3 spark_col = mix(vec3(1.0, 0.7, 0.3), vec3(0.5, 0.9, 1.0),
                         fract(twisted_angle + z * 0.2));
    color += spark_col * spark * between_mask * 0.65;

    // ── Edge glow ──
    float edge_glow = smoothstep(0.88, 0.97, abs(sin(zD1 + 0.05)));
    color += vec3(0.0, 1.0, 0.9) * edge_glow * 0.5;

    // ── Center radial glow ──
    float radial = 1.0 - smoothstep(0.0, 0.8, radius);
    color += vec3(0.05, 0.02, 0.12) * radial * 0.5;

    // ── Tone mapping and color grading ──
    color = max(color, vec3(0.0));
    color = pow(color, vec3(1.08));
    float lum = dot(color, vec3(0.2126, 0.7152, 0.0722));
    color = mix(vec3(lum), color, 1.25);  // Saturation boost
    color = color / (color + vec3(1.0));  // Reinhard

    // ── Blend over original ──
    float strength = max(max(color.r, color.g), color.b);
    vec3 result = mix(original.rgb * 0.1, color + original.rgb * 0.08, smoothstep(0.005, 0.06, strength));

    return vec4(result, 1.0);
}
