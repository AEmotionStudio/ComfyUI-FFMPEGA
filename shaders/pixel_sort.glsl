//!HOOK MAIN
//!BIND HOOKED
//!DESC Pixel Sort — glitch art brightness-based pixel row sorting

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.03;

    // Determine sort threshold — pixels brighter than this get "sorted"
    float sort_threshold = 0.3 + sin(t * 0.5) * 0.15;

    float lum = dot(HOOKED_tex(uv).rgb, vec3(0.299, 0.587, 0.114));

    // Only sort pixels above threshold
    if (lum > sort_threshold) {
        // Simulate sorting by shifting UV horizontally toward bright clusters
        // Sample neighbors to determine sort direction
        float scan_range = 20.0;
        float texel_x = 1.0 / HOOKED_size.x;
        float brightest_offset = 0.0;
        float brightest_lum = lum;

        // Scan along row for brightest nearby pixel
        for (float i = -scan_range; i <= scan_range; i += 1.0) {
            vec2 scan_uv = vec2(uv.x + i * texel_x, uv.y);
            scan_uv.x = clamp(scan_uv.x, 0.0, 1.0);
            float scan_lum = dot(HOOKED_tex(scan_uv).rgb, vec3(0.299, 0.587, 0.114));
            if (scan_lum > brightest_lum && scan_lum > sort_threshold) {
                brightest_lum = scan_lum;
                brightest_offset = i;
            }
        }

        // Shift this pixel toward the brightest cluster
        float shift = brightest_offset * texel_x * 0.3;
        vec2 sorted_uv = vec2(clamp(uv.x + shift, 0.0, 1.0), uv.y);

        // Create streak effect by averaging along shift direction
        vec3 sorted_color = vec3(0.0);
        float weight = 0.0;
        for (float s = 0.0; s <= 1.0; s += 0.2) {
            vec2 streak_uv = mix(uv, sorted_uv, s);
            float w = 1.0 - s * 0.5;
            sorted_color += HOOKED_tex(streak_uv).rgb * w;
            weight += w;
        }
        sorted_color /= weight;

        // Band artifacts at sort boundaries
        float band = fract(uv.x * HOOKED_size.x * 0.1 + t);
        band = smoothstep(0.48, 0.5, band) * 0.1;

        return vec4(sorted_color + band, 1.0);
    }

    return HOOKED_tex(uv);
}
