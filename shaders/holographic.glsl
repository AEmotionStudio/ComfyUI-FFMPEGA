//!HOOK MAIN
//!BIND HOOKED
//!DESC Holographic Iridescent Color Shift Shader

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.02;

    vec4 col = HOOKED_tex(uv);

    // ── Iridescent shift based on view angle approximation ──
    // Use screen-space gradient as a proxy for surface angle
    float angle = uv.x * 2.0 + uv.y * 1.5 + t;

    // Rainbow hue shift
    vec3 holo;
    holo.r = sin(angle * 6.28318 + 0.0) * 0.5 + 0.5;
    holo.g = sin(angle * 6.28318 + 2.094) * 0.5 + 0.5;
    holo.b = sin(angle * 6.28318 + 4.189) * 0.5 + 0.5;

    // ── Fresnel-like edge glow ──
    vec2 center = uv - 0.5;
    float dist = length(center);
    float fresnel = smoothstep(0.0, 0.5, dist);

    // Blend holographic color with original
    float blend = 0.25 + fresnel * 0.15;
    col.rgb = mix(col.rgb, col.rgb * holo * 2.0, blend);

    // ── Subtle shimmer / sparkle ──
    float sparkle = fract(sin(dot(uv * 100.0 + t, vec2(12.9898, 78.233))) * 43758.5);
    sparkle = step(0.97, sparkle) * 0.4;
    col.rgb += sparkle;

    // ── Boost saturation slightly ──
    float luma = dot(col.rgb, vec3(0.299, 0.587, 0.114));
    col.rgb = mix(vec3(luma), col.rgb, 1.3);

    return vec4(clamp(col.rgb, 0.0, 1.0), col.a);
}
