//!HOOK MAIN
//!BIND HOOKED
//!DESC Anime Pro — advanced cel-shading with halftone shadows, rim light, specular highlights

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 texel = 1.0 / HOOKED_size;
    float t = float(frame) * 0.008;
    vec4 col = HOOKED_tex(uv);

    // ── Luminance and color analysis ──
    float lum = dot(col.rgb, vec3(0.299, 0.587, 0.114));
    vec3 hsv_approx = col.rgb;  // work in RGB, quantize luminance

    // ── Multi-band cel shading (5 distinct tonal bands) ──
    float bands = 5.0;
    float quant = floor(lum * bands + 0.5) / bands;
    float lum_scale = (lum > 0.001) ? quant / lum : 1.0;
    vec3 cel = col.rgb * lum_scale;

    // ── Halftone dots in shadow regions ──
    float shadow_mask = smoothstep(0.45, 0.25, lum);
    float dot_scale = 6.0;  // dots per texel
    vec2 dot_uv = uv * HOOKED_size / dot_scale;
    vec2 dot_center = floor(dot_uv) + 0.5;
    float dot_dist = length(dot_uv - dot_center);

    // Dot radius varies with shadow darkness
    float dot_radius = mix(0.1, 0.45, shadow_mask);
    float halftone = smoothstep(dot_radius + 0.05, dot_radius - 0.05, dot_dist);

    // Apply halftone: darken shadow areas with dot pattern
    float halftone_darken = mix(1.0, mix(0.7, 1.0, halftone), shadow_mask);
    cel *= halftone_darken;

    // ── Sobel edge detection for ink outlines ──
    float tl = dot(HOOKED_tex(uv + vec2(-texel.x, -texel.y)).rgb, vec3(0.33));
    float tc = dot(HOOKED_tex(uv + vec2(0.0, -texel.y)).rgb, vec3(0.33));
    float tr = dot(HOOKED_tex(uv + vec2(texel.x, -texel.y)).rgb, vec3(0.33));
    float ml = dot(HOOKED_tex(uv + vec2(-texel.x, 0.0)).rgb, vec3(0.33));
    float mr = dot(HOOKED_tex(uv + vec2(texel.x, 0.0)).rgb, vec3(0.33));
    float bl = dot(HOOKED_tex(uv + vec2(-texel.x, texel.y)).rgb, vec3(0.33));
    float bc = dot(HOOKED_tex(uv + vec2(0.0, texel.y)).rgb, vec3(0.33));
    float br = dot(HOOKED_tex(uv + vec2(texel.x, texel.y)).rgb, vec3(0.33));

    float gx = -tl - 2.0*ml - bl + tr + 2.0*mr + br;
    float gy = -tl - 2.0*tc - tr + bl + 2.0*bc + br;
    float edge = sqrt(gx*gx + gy*gy);

    // Variable-width outlines: thicker on dark edges, thinner on bright
    float outline_thin = smoothstep(0.04, 0.12, edge);
    float outline_thick = smoothstep(0.02, 0.08, edge);
    float outline = mix(outline_thin, outline_thick, smoothstep(0.5, 0.2, lum));

    // ── Rim lighting (Fresnel-like edge glow) ──
    // Approximate surface normal from luminance gradient
    vec2 grad = vec2(gx, gy);
    float grad_strength = length(grad);

    // Animated rim light direction (subtle rotation)
    float rim_angle = t * 0.5;
    vec2 rim_dir = vec2(cos(rim_angle), sin(rim_angle));
    float rim_dot = abs(dot(normalize(grad + 0.001), rim_dir));

    float rim = smoothstep(0.5, 0.9, rim_dot) * grad_strength * 4.0;
    rim *= smoothstep(0.3, 0.6, lum);  // Only on mid-tones and highlights
    rim = clamp(rim, 0.0, 0.6);

    // Rim color: warm highlight
    vec3 rim_color = vec3(1.0, 0.95, 0.85) * rim;

    // ── Specular highlight spots ──
    float spec = smoothstep(0.82, 0.92, lum);
    vec3 spec_color = vec3(1.0, 0.98, 0.95) * spec * 0.5;

    // ── Combine: cel shading + rim + specular - outline ──
    vec3 ink = vec3(0.06, 0.04, 0.03);
    vec3 result = cel + rim_color + spec_color;
    result = mix(result, ink, outline * 0.9);

    // Saturation boost for anime vibrancy
    float avg = (result.r + result.g + result.b) / 3.0;
    result = mix(vec3(avg), result, 1.5);

    return vec4(clamp(result, 0.0, 1.0), 1.0);
}
