//!HOOK MAIN
//!BIND HOOKED
//!DESC Topographic — elevation contour lines like a terrain map

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.01;
    vec4 col = HOOKED_tex(uv);

    // Luminance as "elevation"
    float elevation = dot(col.rgb, vec3(0.299, 0.587, 0.114));

    // Animated elevation shift (terrain slowly changes)
    elevation += sin(t * 0.5) * 0.05;

    // Contour lines: sharp lines at regular elevation intervals
    float contour_spacing = 0.08;
    float contour = fract(elevation / contour_spacing);
    float contour_line = smoothstep(0.04, 0.0, abs(contour - 0.5) - 0.45);

    // Major contour lines (every 5th line, thicker)
    float major_spacing = contour_spacing * 5.0;
    float major_contour = fract(elevation / major_spacing);
    float major_line = smoothstep(0.06, 0.0, abs(major_contour - 0.5) - 0.43);

    // Height-based color zones
    vec3 zone_color;
    if (elevation < 0.15) {
        zone_color = vec3(0.2, 0.35, 0.55);   // deep blue (water)
    } else if (elevation < 0.25) {
        zone_color = vec3(0.25, 0.5, 0.3);    // dark green (lowland)
    } else if (elevation < 0.4) {
        zone_color = vec3(0.4, 0.65, 0.3);    // green (forest)
    } else if (elevation < 0.55) {
        zone_color = vec3(0.65, 0.6, 0.35);   // yellow-green (highland)
    } else if (elevation < 0.7) {
        zone_color = vec3(0.7, 0.55, 0.3);    // tan (mountain)
    } else if (elevation < 0.85) {
        zone_color = vec3(0.6, 0.45, 0.35);   // brown (high mountain)
    } else {
        zone_color = vec3(0.9, 0.9, 0.95);    // white (snow)
    }

    // Paper texture
    float paper = fract(sin(dot(uv * 500.0, vec2(12.9898, 78.233))) * 43758.5453);
    zone_color *= (0.95 + paper * 0.05);

    // Apply contour lines (dark ink)
    vec3 ink = vec3(0.15, 0.12, 0.1);
    vec3 result = mix(zone_color, ink, contour_line * 0.7);
    result = mix(result, ink, major_line * 0.9);

    // Subtle gradient shading for depth feel
    vec2 texel = 1.0 / HOOKED_size;
    float elev_r = dot(HOOKED_tex(uv + vec2(texel.x, 0.0)).rgb, vec3(0.33));
    float elev_d = dot(HOOKED_tex(uv + vec2(0.0, texel.y)).rgb, vec3(0.33));
    float slope = abs(elevation - elev_r) + abs(elevation - elev_d);
    result *= 1.0 - slope * 2.0;

    return vec4(result, 1.0);
}
