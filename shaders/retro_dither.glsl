//!HOOK MAIN
//!BIND HOOKED
//!DESC Retro Dither — ordered Bayer 8x8 dithering with retro palette quantization

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.002;
    vec4 col = HOOKED_tex(uv);

    // ── Bayer 8×8 dither matrix ──
    // Classic ordered dithering pattern
    int x = int(mod(uv.x * HOOKED_size.x, 8.0));
    int y = int(mod(uv.y * HOOKED_size.y, 8.0));

    // Bayer 8x8 threshold values (normalized 0-1)
    // Row-major flattened
    float bayer;
    int idx = y * 8 + x;

    // Compute Bayer 8x8 recursively from 2x2 base
    // B(0) = [0,2; 3,1], B(n) = [4*B(n-1), 4*B(n-1)+2; 4*B(n-1)+3, 4*B(n-1)+1]
    int bx = x;
    int by = y;
    int val = 0;
    for (int bit = 2; bit >= 0; bit--) {
        int bitmask = 1 << bit;
        int qx = (bx & bitmask) != 0 ? 1 : 0;
        int qy = (by & bitmask) != 0 ? 1 : 0;
        // 2x2 matrix positions: [0,2; 3,1]
        int m;
        if (qx == 0 && qy == 0) m = 0;
        else if (qx == 1 && qy == 0) m = 2;
        else if (qx == 0 && qy == 1) m = 3;
        else m = 1;
        val = val * 4 + m;
    }
    bayer = float(val) / 64.0;

    // ── Retro palette quantization ──
    // Reduce to N levels per channel with dithering
    float palette_size = 6.0;  // 6 levels per channel = 216 colors (web-safe-ish)

    // Dither: offset color by bayer threshold before quantizing
    float dither_strength = 1.0 / palette_size;
    vec3 dithered = col.rgb + (bayer - 0.5) * dither_strength;

    // Quantize to palette
    vec3 quantized = floor(dithered * palette_size + 0.5) / palette_size;
    quantized = clamp(quantized, 0.0, 1.0);

    // ── Optional: CRT-style scanlines for extra retro feel ──
    float scanline = sin(uv.y * HOOKED_size.y * 3.14159) * 0.5 + 0.5;
    scanline = mix(1.0, scanline, 0.08);
    quantized *= scanline;

    // ── Subtle pixel grid (shows individual pixels) ──
    float pixel_scale = 2.0;  // 2x pixel enlargement
    vec2 pixel_uv = fract(uv * HOOKED_size / pixel_scale);
    float pixel_border = 1.0;
    if (pixel_uv.x < 0.05 || pixel_uv.x > 0.95 || pixel_uv.y < 0.05 || pixel_uv.y > 0.95) {
        pixel_border = 0.92;
    }
    quantized *= pixel_border;

    // Slight warm tint (like old monitors)
    quantized += vec3(0.02, 0.01, -0.01);

    // Boost saturation slightly for retro pop
    float avg = (quantized.r + quantized.g + quantized.b) / 3.0;
    quantized = mix(vec3(avg), quantized, 1.2);

    return vec4(clamp(quantized, 0.0, 1.0), 1.0);
}
