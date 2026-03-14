//!HOOK MAIN
//!BIND HOOKED
//!DESC CRT Scanline + Barrel Distortion Shader

vec4 hook() {
    vec2 uv = HOOKED_pos;

    // ── Barrel distortion (CRT curvature) ──
    vec2 cc = uv - 0.5;
    float r2 = dot(cc, cc);
    float barrel = 1.0 + 0.15 * r2 + 0.05 * r2 * r2;
    uv = cc * barrel + 0.5;

    // Clamp to avoid sampling outside texture
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0)
        return vec4(0.0, 0.0, 0.0, 1.0);

    vec4 col = HOOKED_tex(uv);

    // ── Scanlines ──
    float scanline = sin(uv.y * HOOKED_size.y * 3.14159) * 0.5 + 0.5;
    scanline = mix(1.0, scanline, 0.25);
    col.rgb *= scanline;

    // ── Subtle RGB phosphor pattern ──
    float px = mod(floor(uv.x * HOOKED_size.x), 3.0);
    vec3 mask = vec3(
        px == 0.0 ? 1.0 : 0.85,
        px == 1.0 ? 1.0 : 0.85,
        px == 2.0 ? 1.0 : 0.85
    );
    col.rgb *= mask;

    // ── Slight vignette ──
    float vig = 1.0 - 0.3 * r2;
    col.rgb *= vig;

    return col;
}
