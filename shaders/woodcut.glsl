//!HOOK MAIN
//!BIND HOOKED
//!DESC Woodcut — Japanese woodblock / linocut print with carved line texture

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 texel = 1.0 / HOOKED_size;
    float t = float(frame) * 0.003;
    vec4 col = HOOKED_tex(uv);

    float lum = dot(col.rgb, vec3(0.299, 0.587, 0.114));

    // ── Sobel gradient for stroke direction ──
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
    float angle = atan(gy, gx);

    // ── Directional carving lines (aligned to local gradient) ──
    // Lines perpendicular to the gradient = following the form
    float carve_angle = angle + 1.5708;  // 90° offset
    vec2 carve_dir = vec2(cos(carve_angle), sin(carve_angle));

    // Multi-frequency carving for rich texture
    float carve_coord = dot(uv * HOOKED_size, carve_dir);
    float carve1 = sin(carve_coord * 0.8) * 0.5 + 0.5;
    float carve2 = sin(carve_coord * 1.6 + 0.5) * 0.5 + 0.5;

    // Line thickness varies with darkness
    float darkness = 1.0 - lum;
    float line_thresh1 = mix(0.8, 0.2, darkness);
    float line_thresh2 = mix(0.85, 0.15, darkness * darkness);

    float carved = smoothstep(line_thresh1 - 0.05, line_thresh1 + 0.05, carve1);
    float carved2 = smoothstep(line_thresh2 - 0.05, line_thresh2 + 0.05, carve2);

    // Cross-hatch in very dark areas
    float cross_coord = dot(uv * HOOKED_size, vec2(-carve_dir.y, carve_dir.x));
    float cross_carve = sin(cross_coord * 0.9) * 0.5 + 0.5;
    float cross_thresh = mix(0.9, 0.25, max(0.0, darkness - 0.5) * 2.0);
    float cross = smoothstep(cross_thresh - 0.05, cross_thresh + 0.05, cross_carve);

    float line_mask = carved * carved2 * cross;

    // ── Wood grain texture (subtle background) ──
    float grain = fract(sin(dot(uv * 200.0, vec2(12.9898, 78.233))) * 43758.5453);
    float grain2 = sin(uv.y * HOOKED_size.y * 0.05 + grain * 2.0) * 0.02;

    // ── Ink pressure variation (imperfect printing) ──
    float pressure = fract(sin(dot(floor(uv * 50.0), vec2(127.1, 311.7))) * 43758.5453);
    float ink_var = 0.9 + pressure * 0.1;

    // ── Strong outlines ──
    float outline = smoothstep(0.03, 0.10, edge);

    // ── Compose: ink on paper ──
    vec3 paper = vec3(0.94, 0.91, 0.84) + grain2;  // Warm rice paper
    vec3 ink = vec3(0.05, 0.03, 0.02) * ink_var;    // Dark sumi ink

    // Carved areas show paper, uncarved show ink based on darkness
    vec3 result = mix(ink, paper, line_mask);

    // Outlines always ink
    result = mix(result, ink, outline * 0.9);

    // Very bright areas are always paper (highlights)
    result = mix(result, paper, smoothstep(0.85, 0.95, lum));

    return vec4(clamp(result, 0.0, 1.0), 1.0);
}
