//!HOOK MAIN
//!BIND HOOKED
//!DESC Mosaic Tile — Byzantine/Roman mosaic with irregular stone tiles

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.008;

    // Irregular grid: jittered square tiles
    float tile_scale = 30.0;
    vec2 tile_uv = uv * tile_scale;
    vec2 tile_id = floor(tile_uv);

    // Jitter tile positions for irregularity
    float rnd1 = fract(sin(dot(tile_id, vec2(127.1, 311.7))) * 43758.5453);
    float rnd2 = fract(sin(dot(tile_id, vec2(269.5, 183.3))) * 43758.5453);

    vec2 jitter = vec2(rnd1 - 0.5, rnd2 - 0.5) * 0.3;
    vec2 tile_center = (tile_id + 0.5 + jitter) / tile_scale;
    tile_center = clamp(tile_center, 0.0, 1.0);

    // Sample color from tile center
    vec3 tile_color = HOOKED_tex(tile_center).rgb;

    // Quantize colors to limited mosaic palette
    tile_color = floor(tile_color * 6.0 + 0.5) / 6.0;

    // Boost saturation for rich mosaic colors
    float lum = dot(tile_color, vec3(0.299, 0.587, 0.114));
    tile_color = mix(vec3(lum), tile_color, 1.5);

    // Per-tile slight color variation (different stone pieces)
    float color_var = fract(sin(dot(tile_id + 1.0, vec2(12.9898, 78.233))) * 43758.5453);
    tile_color *= (0.85 + color_var * 0.3);

    // Stone texture per tile
    vec2 f = fract(tile_uv) - 0.5 - jitter;
    float stone_noise = fract(sin(dot(f * 50.0 + tile_id, vec2(12.9898, 78.233))) * 43758.5453);
    tile_color *= (0.9 + stone_noise * 0.15);

    // Grout/mortar between tiles
    vec2 abs_f = abs(f);
    float grout_size = 0.06;
    float grout = smoothstep(grout_size, grout_size + 0.02, 0.5 - max(abs_f.x, abs_f.y));
    vec3 grout_color = vec3(0.35, 0.32, 0.28);

    // Tile edge: slight bevel / shadow
    float bevel = smoothstep(0.0, 0.05, 0.5 - max(abs_f.x, abs_f.y) - grout_size);
    tile_color *= mix(0.8, 1.0, bevel);

    // Subtle light reflection on tile surface (animated)
    float reflect = sin(tile_id.x * 3.0 + tile_id.y * 5.0 + t * 3.0) * 0.5 + 0.5;
    reflect = pow(reflect, 6.0) * 0.1;
    tile_color += reflect;

    vec3 result = mix(grout_color, tile_color, grout);

    return vec4(result, 1.0);
}
