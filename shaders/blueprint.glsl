//!HOOK MAIN
//!BIND HOOKED
//!DESC Blueprint — sacred geometry with hex grids, glyph rings and etching

vec4 hook() {
    vec2 pos = HOOKED_pos;
    vec4 original = HOOKED_tex(pos);
    float t = float(frame) * 0.005;

    // Center and aspect-correct
    vec2 uv = (pos - 0.5) * 2.0;
    uv.x *= HOOKED_size.x / HOOKED_size.y;

    float dist = length(uv);
    float angle = atan(uv.y, uv.x);
    float pattern = 0.0;

    // ── Hexagonal grid lines (6-fold symmetry, slowly rotating) ──
    float rot_hex = t * 0.05;
    float ch = cos(rot_hex);
    float sh = sin(rot_hex);
    vec2 hex_uv = vec2(ch * uv.x - sh * uv.y, sh * uv.x + ch * uv.y);
    for (int i = 0; i < 6; i++) {
        float hex_angle = float(i) * 3.14159265 / 3.0;
        vec2 dir = vec2(cos(hex_angle), sin(hex_angle));
        float d = abs(dot(hex_uv, dir));
        float line_val = smoothstep(0.003, 0.0, d) + smoothstep(0.003, 0.0, abs(d - 0.003));
        pattern = max(pattern, line_val);
    }

    // ── Triangular lattice (counter-rotating) ──
    float rot_tri = -t * 0.1;
    float ct = cos(rot_tri);
    float st = sin(rot_tri);
    vec2 tri_uv = vec2(ct * uv.x - st * uv.y, st * uv.x + ct * uv.y);
    for (int i = 0; i < 3; i++) {
        float tri_angle = float(i) * 6.2831853 / 3.0;
        float ca = cos(tri_angle);
        float sa = sin(tri_angle);
        vec2 p = vec2(ca * tri_uv.x - sa * tri_uv.y, sa * tri_uv.x + ca * tri_uv.y);
        float l1 = smoothstep(0.003, 0.0, abs(p.y + 0.25));
        float l2 = smoothstep(0.003, 0.0, abs(p.y - 0.25));
        pattern = max(pattern, l1);
        pattern = max(pattern, l2);
    }

    // ── Concentric glyph rings ──
    for (int i = 1; i < 8; i++) {
        float fi = float(i);
        float radius = fi * 0.12;
        if (dist > radius - 0.01 && dist < radius + 0.01) {
            // Glyphs: angle-quantized segments that flash in/out
            float glyph_angle = floor(angle * (10.0 + fi * 2.0)) / (10.0 + fi * 2.0);
            float glyph_flash = sin(glyph_angle * 50.0 + t * fi);
            if (glyph_flash > 0.5) {
                float ring_line = smoothstep(0.003, 0.0, abs(dist - radius));
                pattern = max(pattern, ring_line);
            }
        }
    }

    // ── Fine sinusoidal etching ──
    vec2 etch = uv * 30.0;
    float etch_val = (sin(etch.x) + cos(etch.y)) * 0.05;
    etch_val *= (1.0 - smoothstep(0.8, 0.9, dist));
    pattern += etch_val;
    pattern = clamp(pattern, 0.0, 1.0);

    // ── HSV rainbow color cycling ──
    float hue = 0.6 + fract(dist * 0.5 - t * 0.1);
    // HSV to RGB inline
    vec3 k = vec3(1.0, 2.0 / 3.0, 1.0 / 3.0);
    vec3 pp = abs(fract(vec3(hue) + k) * 6.0 - 3.0);
    vec3 blueprint_color = mix(vec3(1.0), clamp(pp - 1.0, 0.0, 1.0), 0.7);

    // ── Film grain ──
    float grain = fract(sin(dot(pos * 500.0, vec2(12.9898, 78.233))) * 43758.5453) * 0.05;

    // ── Combine ──
    vec3 geometry_color = vec3(grain);
    geometry_color += pattern * blueprint_color * 0.5;
    geometry_color += pow(max(pattern, 0.0), 3.0) * blueprint_color * 0.3;

    // ── Blend over original ──
    float strength = max(max(geometry_color.r, geometry_color.g), geometry_color.b);
    vec3 result = mix(original.rgb * 0.4, geometry_color + original.rgb * 0.2, smoothstep(0.01, 0.1, strength));

    return vec4(result, 1.0);
}
