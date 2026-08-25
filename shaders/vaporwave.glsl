//!HOOK MAIN
//!BIND HOOKED
//!DESC Vaporwave — retro 80s aesthetic with grid, sunset, and glitch

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.03;
    vec4 col = HOOKED_tex(uv);

    // ── Color grading: push to pink/cyan/purple ──
    float lum = dot(col.rgb, vec3(0.299, 0.587, 0.114));

    vec3 vapor_grade;
    if (lum < 0.3) {
        vapor_grade = mix(vec3(0.05, 0.0, 0.15), vec3(0.3, 0.05, 0.4), lum / 0.3);
    } else if (lum < 0.6) {
        vapor_grade = mix(vec3(0.3, 0.05, 0.4), vec3(0.9, 0.3, 0.6), (lum - 0.3) / 0.3);
    } else {
        vapor_grade = mix(vec3(0.9, 0.3, 0.6), vec3(0.3, 0.9, 1.0), (lum - 0.6) / 0.4);
    }
    col.rgb = mix(col.rgb, vapor_grade, 0.6);

    // ── Retro sunset gradient (background layer) ──
    float sunset = 0.0;
    if (uv.y < 0.5) {
        sunset = smoothstep(0.0, 0.5, uv.y);
        vec3 sunset_top = vec3(0.1, 0.0, 0.3);
        vec3 sunset_mid = vec3(0.5, 0.1, 0.5);
        vec3 sunset_color = mix(sunset_mid, sunset_top, sunset);

        // Horizontal bands in sunset (retro sun lines)
        float sun_bands = sin(uv.y * 60.0) * 0.5 + 0.5;
        sun_bands = step(0.5, sun_bands);
        sunset_color *= mix(0.7, 1.0, sun_bands);

        col.rgb = mix(col.rgb, sunset_color, (1.0 - sunset) * 0.3);
    }

    // ── Perspective grid floor (lower half) ──
    if (uv.y > 0.5) {
        float grid_y = (uv.y - 0.5) * 2.0;  // 0 to 1 in bottom half

        // Perspective: lines converge
        float perspective = 1.0 / (grid_y + 0.1);

        // Horizontal grid lines (scrolling)
        float h_line = sin((grid_y * perspective * 5.0 - t * 2.0) * 3.14159);
        h_line = smoothstep(0.9, 1.0, h_line);

        // Vertical grid lines
        float v_coord = (uv.x - 0.5) * perspective;
        float v_line = sin(v_coord * 20.0 * 3.14159);
        v_line = smoothstep(0.9, 1.0, v_line);

        float grid = max(h_line, v_line);

        // Grid color: neon cyan/magenta
        vec3 grid_color = mix(
            vec3(0.0, 0.8, 1.0),
            vec3(1.0, 0.2, 0.8),
            sin(t + grid_y * 5.0) * 0.5 + 0.5
        );

        col.rgb += grid_color * grid * 0.5 * (1.0 - grid_y * 0.5);
    }

    // ── Chromatic aberration ──
    float ca = 0.003;
    col.r = HOOKED_tex(uv + vec2(ca, 0.0)).r;
    col.b = HOOKED_tex(uv - vec2(ca, 0.0)).b;

    // ── Scanlines ──
    float scan = sin(uv.y * HOOKED_size.y * 1.5) * 0.5 + 0.5;
    col.rgb *= mix(0.88, 1.0, scan);

    // Boost saturation
    float avg = (col.r + col.g + col.b) / 3.0;
    col.rgb = mix(vec3(avg), col.rgb, 1.5);

    return vec4(col.rgb, 1.0);
}
