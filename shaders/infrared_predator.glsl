//!HOOK MAIN
//!BIND HOOKED
//!DESC Infrared Predator — thermal hunting vision with heat signatures

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.03;
    vec4 col = HOOKED_tex(uv);
    vec2 texel = 1.0 / HOOKED_size;

    // Luminance as heat proxy (bright areas = hot targets)
    float heat = dot(col.rgb, vec3(0.299, 0.587, 0.114));

    // Edge detection for target outline wireframe
    float lum_l = dot(HOOKED_tex(uv + vec2(-texel.x, 0.0)).rgb, vec3(0.33));
    float lum_r = dot(HOOKED_tex(uv + vec2(texel.x, 0.0)).rgb, vec3(0.33));
    float lum_u = dot(HOOKED_tex(uv + vec2(0.0, -texel.y)).rgb, vec3(0.33));
    float lum_d = dot(HOOKED_tex(uv + vec2(0.0, texel.y)).rgb, vec3(0.33));
    float edge = abs(lum_l - lum_r) + abs(lum_u - lum_d);
    edge = smoothstep(0.02, 0.1, edge);

    // Heat map palette: cold blue → green → yellow → red → white hot
    vec3 thermal;
    if (heat < 0.15) {
        thermal = mix(vec3(0.0, 0.0, 0.15), vec3(0.0, 0.1, 0.4), heat / 0.15);
    } else if (heat < 0.35) {
        thermal = mix(vec3(0.0, 0.1, 0.4), vec3(0.0, 0.5, 0.2), (heat - 0.15) / 0.2);
    } else if (heat < 0.55) {
        thermal = mix(vec3(0.0, 0.5, 0.2), vec3(0.8, 0.8, 0.0), (heat - 0.35) / 0.2);
    } else if (heat < 0.75) {
        thermal = mix(vec3(0.8, 0.8, 0.0), vec3(1.0, 0.2, 0.0), (heat - 0.55) / 0.2);
    } else {
        thermal = mix(vec3(1.0, 0.2, 0.0), vec3(1.0, 1.0, 0.8), (heat - 0.75) / 0.25);
    }

    // Target outline wireframe in bright cyan
    thermal += vec3(0.0, 0.8, 0.9) * edge * 0.7;

    // Animated scan line
    float scan_y = fract(t * 0.5);
    float scan_line = smoothstep(0.003, 0.0, abs(uv.y - scan_y)) * 0.5;
    thermal += vec3(0.0, 0.5, 0.4) * scan_line;

    // Targeting reticle (corners of frame)
    float reticle = 0.0;
    // Top-left bracket
    if (uv.x < 0.08 && abs(uv.y - 0.08) < 0.002) reticle = 1.0;
    if (uv.y < 0.08 && abs(uv.x - 0.08) < 0.002) reticle = 1.0;
    // Top-right bracket
    if (uv.x > 0.92 && abs(uv.y - 0.08) < 0.002) reticle = 1.0;
    if (uv.y < 0.08 && abs(uv.x - 0.92) < 0.002) reticle = 1.0;
    // Bottom brackets
    if (uv.x < 0.08 && abs(uv.y - 0.92) < 0.002) reticle = 1.0;
    if (uv.y > 0.92 && abs(uv.x - 0.08) < 0.002) reticle = 1.0;
    if (uv.x > 0.92 && abs(uv.y - 0.92) < 0.002) reticle = 1.0;
    if (uv.y > 0.92 && abs(uv.x - 0.92) < 0.002) reticle = 1.0;
    // Center crosshair
    float center_dist = length(uv - 0.5);
    if (center_dist < 0.04 && center_dist > 0.035) reticle = 0.5;
    if ((abs(uv.x - 0.5) < 0.001 || abs(uv.y - 0.5) < 0.001) && center_dist < 0.06 && center_dist > 0.015)
        reticle = 0.8;

    thermal += vec3(0.0, 1.0, 0.8) * reticle;

    // Noise
    float noise = fract(sin(dot(uv * HOOKED_size + t * 40.0, vec2(12.9898, 78.233))) * 43758.5453);
    thermal += (noise - 0.5) * 0.04;

    return vec4(thermal, 1.0);
}
