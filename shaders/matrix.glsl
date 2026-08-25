//!HOOK MAIN
//!BIND HOOKED
//!DESC Matrix — digital rain cascade with glowing character columns

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.04;

    vec4 original = HOOKED_tex(uv);

    // Convert to green-tinted base
    float lum = dot(original.rgb, vec3(0.299, 0.587, 0.114));
    vec3 green_base = vec3(lum * 0.15, lum * 0.7, lum * 0.2);

    // ── Digital rain columns ──
    float col_count = 50.0;
    float row_count = 35.0;
    float col_x = floor(uv.x * col_count);
    float col_rnd = fract(sin(col_x * 127.1) * 43758.5453);
    float col_rnd2 = fract(sin(col_x * 269.5) * 43758.5453);

    // Each column has a falling head at different speeds
    float speed = 0.3 + col_rnd * 2.0;
    float head_y = fract(t * speed * 0.2 + col_rnd * 10.0);

    // Trail length varies per column
    float trail_len = 0.15 + col_rnd2 * 0.35;

    // Distance from head (wrapping)
    float dist = uv.y - head_y;
    if (dist < 0.0) dist += 1.0;

    // Trail brightness: bright at head, fading behind
    float trail = smoothstep(trail_len, 0.0, dist);

    // ── Character cells ──
    float char_y = floor(uv.y * row_count);
    float char_x = floor(uv.x * col_count);

    // Random character change (flickering glyphs)
    float char_rnd = fract(sin(dot(vec2(char_x, char_y + floor(t * 8.0)),
                       vec2(12.9898, 78.233))) * 43758.5453);

    // Character visibility: only show in cells where trail is active
    float glyph = step(0.25, char_rnd) * trail;

    // Cell UV for character shape simulation
    vec2 cell_uv = vec2(fract(uv.x * col_count), fract(uv.y * row_count));

    // Simple glyph shape: random rectangles within cell
    float glyph_rnd = fract(sin(dot(vec2(char_x, char_y + floor(t * 4.0)),
                        vec2(127.1, 311.7))) * 43758.5453);
    float shape = 0.0;
    // Horizontal bar
    if (glyph_rnd > 0.5) shape += step(0.3, cell_uv.x) * step(cell_uv.x, 0.7) *
                                   step(0.4, cell_uv.y) * step(cell_uv.y, 0.6);
    // Vertical bar
    if (glyph_rnd > 0.3) shape += step(0.4, cell_uv.x) * step(cell_uv.x, 0.6) *
                                   step(0.2, cell_uv.y) * step(cell_uv.y, 0.8);
    // Corner dot
    if (glyph_rnd < 0.4) shape += step(0.6, cell_uv.x) * step(0.2, cell_uv.y) *
                                   step(cell_uv.y, 0.4);
    shape = min(shape, 1.0);

    // ── Bright head (leading character) ──
    float head_brightness = smoothstep(0.015, 0.0, dist) * 3.0;

    // ── Compose ──
    vec3 rain_green = vec3(0.1, 0.8, 0.2) * glyph * shape;
    vec3 head_white = vec3(0.7, 1.0, 0.8) * head_brightness * shape;

    // Subtle column glow behind characters
    float column_glow = trail * 0.1;
    vec3 glow = vec3(0.05, 0.2, 0.08) * column_glow;

    vec3 result = green_base * 0.4 + rain_green * 0.8 + head_white + glow;

    return vec4(result, 1.0);
}
