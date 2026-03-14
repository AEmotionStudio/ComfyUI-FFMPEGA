//!HOOK MAIN
//!BIND HOOKED
//!DESC Hologram Scan — sci-fi holographic projection with scan beam

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.03;
    vec4 col = HOOKED_tex(uv);

    // Convert to luminance for hologram base
    float lum = dot(col.rgb, vec3(0.299, 0.587, 0.114));

    // Hologram base color: cyan/blue tint
    vec3 holo_base = vec3(0.1, 0.6, 0.9) * lum + vec3(0.0, 0.2, 0.3) * (1.0 - lum);

    // Horizontal scan lines (tight)
    float scan = sin(uv.y * HOOKED_size.y * 1.5) * 0.5 + 0.5;
    scan = pow(scan, 0.3);
    holo_base *= mix(0.6, 1.0, scan);

    // Moving scan beam — bright horizontal band sweeping down
    float beam_y = fract(t * 0.4);
    float beam = smoothstep(0.03, 0.0, abs(uv.y - beam_y));
    holo_base += vec3(0.3, 0.8, 1.0) * beam * 1.5;

    // Edge wireframe glow (Sobel-like)
    vec2 texel = 1.0 / HOOKED_size;
    float l = dot(HOOKED_tex(uv + vec2(-texel.x, 0.0)).rgb, vec3(0.33));
    float r = dot(HOOKED_tex(uv + vec2(texel.x, 0.0)).rgb, vec3(0.33));
    float u = dot(HOOKED_tex(uv + vec2(0.0, -texel.y)).rgb, vec3(0.33));
    float d = dot(HOOKED_tex(uv + vec2(0.0, texel.y)).rgb, vec3(0.33));
    float edge = abs(l - r) + abs(u - d);
    edge = smoothstep(0.03, 0.15, edge);
    holo_base += vec3(0.2, 0.9, 1.0) * edge * 0.8;

    // Jitter / static noise
    float noise = fract(sin(dot(uv * HOOKED_size + t * 100.0, vec2(12.9898, 78.233))) * 43758.5453);
    holo_base += noise * 0.05;

    // Flickering transparency
    float flicker = sin(t * 15.0) * 0.03 + sin(t * 37.0) * 0.02;
    holo_base *= (0.85 + flicker);

    // Triangular interlacing artifact
    float interlace = step(0.5, mod(floor(uv.y * HOOKED_size.y) + float(frame), 2.0));
    holo_base *= mix(0.9, 1.0, interlace);

    return vec4(holo_base, 1.0);
}
