//!HOOK MAIN
//!BIND HOOKED
//!DESC Animated Water Ripple Distortion Shader

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.04;

    // ── Ripple parameters ──
    vec2 center = vec2(0.5, 0.5);
    float dist = distance(uv, center);

    // ── Concentric ripple displacement ──
    float freq = 25.0;
    float amplitude = 0.008;
    float decay = max(0.0, 1.0 - dist * 2.5);

    float ripple = sin(dist * freq - t * 4.0) * amplitude * decay;

    // ── Secondary ripple from offset center ──
    vec2 center2 = vec2(0.3, 0.6);
    float dist2 = distance(uv, center2);
    float decay2 = max(0.0, 1.0 - dist2 * 3.0);
    float ripple2 = sin(dist2 * 20.0 - t * 3.0 + 1.5) * amplitude * 0.6 * decay2;

    // ── Apply displacement along radial direction ──
    vec2 dir = normalize(uv - center + 0.001);
    vec2 dir2 = normalize(uv - center2 + 0.001);
    vec2 displaced = uv + dir * ripple + dir2 * ripple2;

    // Clamp to valid range
    displaced = clamp(displaced, 0.0, 1.0);

    vec4 col = HOOKED_tex(displaced);

    // ── Caustic highlights ──
    float caustic = abs(sin(dist * freq - t * 4.0)) * decay;
    caustic = smoothstep(0.7, 1.0, caustic) * 0.15;
    col.rgb += caustic;

    // ── Slight blue tint for underwater feel ──
    col.r *= 0.95;
    col.b *= 1.05;

    return col;
}
