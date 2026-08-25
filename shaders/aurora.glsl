//!HOOK MAIN
//!BIND HOOKED
//!DESC Aurora — northern lights ribbons overlaid on video

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.02;
    vec4 col = HOOKED_tex(uv);

    // Multiple aurora ribbons at different heights
    float aurora = 0.0;
    vec3 aurora_color = vec3(0.0);

    for (float i = 0.0; i < 3.0; i++) {
        float offset = i * 0.15;
        float speed = 0.3 + i * 0.1;

        // Ribbon path: wavy horizontal band
        float ribbon_y = 0.3 + offset +
            sin(uv.x * 4.0 + t * speed) * 0.08 +
            sin(uv.x * 7.0 - t * speed * 1.3 + i * 2.0) * 0.04 +
            sin(uv.x * 13.0 + t * speed * 0.7) * 0.02;

        float dist = abs(uv.y - ribbon_y);

        // Soft ribbon shape
        float ribbon = smoothstep(0.12, 0.0, dist);

        // Curtain folds — vertical brightness variation
        float folds = sin(uv.x * 20.0 + t * 2.0 + i * 3.0) * 0.5 + 0.5;
        folds *= sin(uv.x * 35.0 - t * 3.0) * 0.3 + 0.7;

        ribbon *= folds;
        aurora += ribbon;

        // Color per ribbon (green/blue/purple)
        vec3 c;
        if (i < 1.0) c = vec3(0.1, 0.9, 0.4);      // green
        else if (i < 2.0) c = vec3(0.2, 0.5, 0.9);   // blue
        else c = vec3(0.6, 0.2, 0.8);                  // purple

        aurora_color += c * ribbon;
    }

    // Additive blend the aurora over original
    aurora = min(aurora, 1.5);
    vec3 result = col.rgb + aurora_color * 0.7;

    // Slight darkening of sky areas to make aurora pop
    float darken = smoothstep(0.6, 0.2, uv.y) * 0.15;
    result = mix(result, result * 0.8, darken * (1.0 - aurora));

    return vec4(result, 1.0);
}
