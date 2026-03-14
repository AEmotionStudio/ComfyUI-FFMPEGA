//!HOOK MAIN
//!BIND HOOKED
//!DESC Night Vision Green Phosphor Shader

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.03;

    vec4 col = HOOKED_tex(uv);

    // ── Convert to luminance ──
    float luma = dot(col.rgb, vec3(0.299, 0.587, 0.114));

    // ── Amplify brightness (night vision gain) ──
    luma = pow(luma, 0.7) * 1.3;

    // ── Green phosphor color ──
    vec3 nightVis = vec3(luma * 0.2, luma * 1.0, luma * 0.15);

    // ── Scanlines ──
    float scanline = sin(uv.y * HOOKED_size.y * 3.14159 * 0.5) * 0.5 + 0.5;
    nightVis *= mix(1.0, scanline, 0.15);

    // ── Static noise ──
    float noise = fract(sin(dot(uv * 1000.0 + t, vec2(12.9898, 78.233))) * 43758.5453);
    nightVis += (noise - 0.5) * 0.08;

    // ── Vignette (scope-like circular mask) ──
    vec2 cc = uv - 0.5;
    float r2 = dot(cc, cc);
    float vig = smoothstep(0.35, 0.15, r2);
    nightVis *= vig;

    // ── Subtle flicker ──
    float flicker = 1.0 + sin(t * 30.0) * 0.02;
    nightVis *= flicker;

    return vec4(clamp(nightVis, 0.0, 1.0), 1.0);
}
