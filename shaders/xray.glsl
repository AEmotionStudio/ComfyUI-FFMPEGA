//!HOOK MAIN
//!BIND HOOKED
//!DESC X-Ray Vision — medical imaging with edge-glow and depth simulation

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.02;
    vec4 col = HOOKED_tex(uv);
    vec2 texel = 1.0 / HOOKED_size;

    // Convert to inverted luminance (X-ray: bright = dense)
    float lum = dot(col.rgb, vec3(0.299, 0.587, 0.114));
    float xray_lum = 1.0 - lum;

    // Enhanced edge detection for "bone structure"
    float samples[8];
    float angles[8];
    for (int i = 0; i < 8; i++) {
        float a = float(i) * 0.7854; // 45-degree increments
        vec2 offset = vec2(cos(a), sin(a)) * texel * 2.0;
        samples[i] = dot(HOOKED_tex(uv + offset).rgb, vec3(0.299, 0.587, 0.114));
    }

    float edge = 0.0;
    for (int i = 0; i < 8; i++) {
        edge += abs(lum - samples[i]);
    }
    edge /= 8.0;
    edge = smoothstep(0.01, 0.08, edge);

    // X-ray blue-white palette
    vec3 xray_dark = vec3(0.0, 0.02, 0.08);
    vec3 xray_mid = vec3(0.05, 0.15, 0.35);
    vec3 xray_bright = vec3(0.7, 0.8, 0.95);
    vec3 xray_hot = vec3(0.95, 0.97, 1.0);

    vec3 xray_color;
    if (xray_lum < 0.3) {
        xray_color = mix(xray_dark, xray_mid, xray_lum / 0.3);
    } else if (xray_lum < 0.7) {
        xray_color = mix(xray_mid, xray_bright, (xray_lum - 0.3) / 0.4);
    } else {
        xray_color = mix(xray_bright, xray_hot, (xray_lum - 0.7) / 0.3);
    }

    // Edge glow (simulating bone/structure boundaries)
    xray_color += vec3(0.3, 0.5, 0.8) * edge * 1.5;

    // Animated scanning artifact (vertical sweep line)
    float scan_x = fract(t * 0.3);
    float scan_line = smoothstep(0.005, 0.0, abs(uv.x - scan_x));
    xray_color += vec3(0.3, 0.6, 0.9) * scan_line;

    // Film grain/noise (x-ray detector noise)
    float noise = fract(sin(dot(uv * HOOKED_size + t * 50.0, vec2(12.9898, 78.233))) * 43758.5453);
    xray_color += (noise - 0.5) * 0.06;

    // Subtle pulsing (simulated exposure variations)
    float pulse = sin(t * 3.0) * 0.03;
    xray_color *= (1.0 + pulse);

    return vec4(xray_color, 1.0);
}
