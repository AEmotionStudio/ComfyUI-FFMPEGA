//!HOOK MAIN
//!BIND HOOKED
//!DESC Supernova — expanding nebula filaments with glowing core and stars

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec4 original = HOOKED_tex(uv);
    float t = float(frame) * 0.008;

    // Center-relative coordinates
    vec2 centered = uv - 0.5;
    // Aspect correction
    centered.x *= HOOKED_size.x / HOOKED_size.y;

    float radius = length(centered);
    float angle = atan(centered.y, centered.x);

    // ── Pseudo-random & noise functions (inlined) ──
    // 2D random
    float rnd_seed = fract(sin(dot(centered * 200.0, vec2(12.9898, 78.233))) * 43758.5453);

    // 3D noise via layered sines (approximation of value noise)
    // We can't do proper 3D noise lookups in libplacebo, so we use
    // layered trigonometric functions that approximate it well

    // ── FBM-like 3D turbulence (6 octaves via trig approximation) ──
    float filaments1 = 0.0;
    float amp1 = 0.5;
    float freq1 = 1.0;
    vec3 p1 = vec3(sin(angle) * 3.0, cos(angle) * 3.0, radius * 3.0 + t * 0.5);
    for (int i = 0; i < 6; i++) {
        float n = sin(p1.x * freq1 * 2.3 + p1.z * freq1) *
                  cos(p1.y * freq1 * 2.7 + p1.z * freq1 * 0.8) * 0.5 + 0.5;
        n *= sin(p1.z * freq1 * 1.1 + p1.x * freq1 * 0.7) * 0.5 + 0.5;
        filaments1 += n * amp1;
        amp1 *= 0.5;
        freq1 *= 2.0;
    }
    filaments1 /= 0.96;

    // Shape filaments: sharpen via abs-fold + power
    filaments1 = 1.0 - abs(filaments1 - 0.5) * 2.0;
    filaments1 = pow(max(filaments1, 0.0), 10.0);

    // Expanding shell envelope
    float outer1 = t * 0.5 + 1.5;
    float inner1 = outer1 - 0.5;
    filaments1 *= smoothstep(outer1, inner1, radius);

    // Filament layer 1 colors: blue base, white glow
    vec3 fil1_base = vec3(0.1, 0.2, 0.8);
    vec3 fil1_glow = vec3(0.8, 0.8, 1.0);

    // ── Second filament layer (different scale + speed) ──
    float filaments2 = 0.0;
    float amp2 = 0.5;
    float freq2 = 1.0;
    vec3 p2 = vec3(sin(angle) * 5.0, cos(angle) * 5.0, radius * 4.0 + t * 0.8) + vec3(3.7, 5.2, 1.3);
    for (int i = 0; i < 6; i++) {
        float n = sin(p2.x * freq2 * 2.3 + p2.z * freq2) *
                  cos(p2.y * freq2 * 2.7 + p2.z * freq2 * 0.8) * 0.5 + 0.5;
        n *= sin(p2.z * freq2 * 1.1 + p2.x * freq2 * 0.7) * 0.5 + 0.5;
        filaments2 += n * amp2;
        amp2 *= 0.5;
        freq2 *= 2.0;
    }
    filaments2 /= 0.96;

    filaments2 = 1.0 - abs(filaments2 - 0.5) * 2.0;
    filaments2 = pow(max(filaments2, 0.0), 15.0);

    float outer2 = t * 0.8 + 1.5;
    float inner2 = outer2 - 0.4;
    filaments2 *= smoothstep(outer2, inner2, radius);

    // Filament layer 2 colors: orange base, warm glow
    vec3 fil2_base = vec3(0.9, 0.5, 0.1);
    vec3 fil2_glow = vec3(1.0, 1.0, 0.8);

    // ── Combine gas layers ──
    vec3 gas = vec3(0.0);
    gas += filaments1 * fil1_base;
    gas += pow(max(filaments1, 0.0), 12.0) * fil1_glow * 5.0;
    gas += filaments2 * fil2_base;
    gas += pow(max(filaments2, 0.0), 18.0) * fil2_glow * 5.0;

    // ── Glowing core ──
    float core_fade = smoothstep(1.5, 0.0, t);
    float core_tex = sin(centered.x * 3.0 - t) * cos(centered.y * 3.0 + t * 0.5) * 0.5 + 0.5;
    float core_intensity = (1.0 - smoothstep(0.0, 0.2, radius)) * pow(core_fade, 2.0);
    vec3 core_color = vec3(1.0, 0.9, 0.7);
    gas += core_intensity * core_tex * 2.0 * core_color;

    // ── Background stars ──
    float star_seed = fract(sin(dot(floor(uv * 200.0), vec2(12.9898, 78.233))) * 43758.5453);
    float star_brightness = pow(star_seed, 50.0);
    float star_dist = fract(star_seed * 10.0 + t * 0.2);
    float star_mask = 1.0 - smoothstep(0.0, 0.01, abs(radius - star_dist));
    gas += star_brightness * star_mask * vec3(1.0, 1.0, 0.8);

    // ── Tone mapping (Reinhard) ──
    gas = gas / (gas + vec3(1.0));
    gas = pow(gas, vec3(0.8));

    // ── Blend supernova over original image ──
    float nebula_strength = max(max(gas.r, gas.g), gas.b);
    vec3 result = mix(original.rgb, gas + original.rgb * 0.2, smoothstep(0.01, 0.1, nebula_strength));

    return vec4(result, 1.0);
}
