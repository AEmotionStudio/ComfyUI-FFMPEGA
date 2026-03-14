//!HOOK MAIN
//!BIND HOOKED
//!DESC Plasma Burn — classic plasma field overlaid and burned into frame

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec4 col = HOOKED_tex(uv);
    float t = float(frame) * 0.04;

    // Classic plasma: sum of sine waves at different frequencies
    float p = 0.0;
    p += sin(uv.x * 10.0 + t);
    p += sin(uv.y * 8.0 - t * 0.7);
    p += sin((uv.x + uv.y) * 6.0 + t * 0.5);
    p += sin(sqrt(dot(uv - 0.5, uv - 0.5)) * 12.0 - t * 1.3);
    p *= 0.25;

    // Map plasma to a hot color ramp (purple/orange/cyan)
    vec3 plasma_color = vec3(
        sin(p * 3.14159 * 2.0) * 0.5 + 0.5,
        sin(p * 3.14159 * 2.0 + 2.094) * 0.5 + 0.5,
        sin(p * 3.14159 * 2.0 + 4.189) * 0.5 + 0.5
    );

    // Burn: brighten or darken original based on plasma intensity
    // Screen blend mode for the hot spots
    float burn_strength = 0.5;
    vec3 result = 1.0 - (1.0 - col.rgb) * (1.0 - plasma_color * burn_strength);

    // Extra glow in high-plasma regions
    float glow = smoothstep(0.3, 0.8, p + 0.5) * 0.4;
    result += plasma_color * glow;

    return vec4(result, 1.0);
}
