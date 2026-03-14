//!HOOK MAIN
//!BIND HOOKED
//!DESC Noir — hard contrast film noir with dramatic light shafts

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.015;
    vec4 col = HOOKED_tex(uv);

    // Convert to high-contrast monochrome
    float lum = dot(col.rgb, vec3(0.299, 0.587, 0.114));

    // Hard contrast curve (crush blacks, blow highlights)
    lum = smoothstep(0.15, 0.85, lum);
    lum = pow(lum, 0.8);

    // Film noir base: warm shadows + cool highlights
    vec3 shadows = vec3(0.05, 0.04, 0.06);
    vec3 highlights = vec3(0.85, 0.82, 0.78);
    vec3 noir = mix(shadows, highlights, lum);

    // ── Dramatic venetian blind light shafts ──
    float blind_angle = 0.3;
    float blind_spacing = 0.06;
    float blind_coord = uv.x * cos(blind_angle) + uv.y * sin(blind_angle);
    float blinds = sin(blind_coord / blind_spacing * 3.14159) * 0.5 + 0.5;
    blinds = smoothstep(0.3, 0.7, blinds);

    // Animated: blinds slowly rotate
    float anim_angle = blind_angle + sin(t * 0.3) * 0.1;
    float anim_coord = uv.x * cos(anim_angle) + uv.y * sin(anim_angle);
    float anim_blinds = sin(anim_coord / blind_spacing * 3.14159) * 0.5 + 0.5;
    anim_blinds = smoothstep(0.3, 0.7, anim_blinds);

    // Light shaft: bright warm light through blind gaps
    float light_shaft = anim_blinds * 0.25;
    noir += vec3(0.2, 0.18, 0.12) * light_shaft;

    // Shadow from blinds
    noir *= mix(0.6, 1.0, anim_blinds);

    // ── Film grain ──
    float grain = fract(sin(dot(uv * HOOKED_size + t * 50.0, vec2(12.9898, 78.233))) * 43758.5453);
    noir += (grain - 0.5) * 0.08;

    // ── Vignette (heavy, dramatic) ──
    float vig = 1.0 - 0.6 * pow(length(uv - 0.5) * 1.4, 2.0);
    noir *= vig;

    // ── Slight sepia warmth ──
    noir = mix(noir, noir * vec3(1.05, 1.0, 0.9), 0.3);

    return vec4(noir, 1.0);
}
