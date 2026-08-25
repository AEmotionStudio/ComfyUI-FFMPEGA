//!HOOK MAIN
//!BIND HOOKED
//!DESC Hex Matrix — hexagonal tiling with depth-aware parallax

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.025;

    // Hexagonal coordinate system
    float hex_scale = 15.0;
    vec2 hex_uv = uv * hex_scale;

    // Convert to axial hex coordinates
    vec2 q_r = vec2(
        (2.0/3.0) * hex_uv.x,
        (-1.0/3.0) * hex_uv.x + (sqrt(3.0)/3.0) * hex_uv.y
    );

    // Round to nearest hex center
    vec2 hex_id = floor(q_r + 0.5);
    float rnd = fract(sin(dot(hex_id, vec2(127.1, 311.7))) * 43758.5453);

    // Hex center back in UV space
    vec2 hex_center;
    hex_center.x = hex_id.x * 1.5;
    hex_center.y = hex_id.y * sqrt(3.0) + hex_id.x * sqrt(3.0) * 0.5;
    hex_center /= hex_scale;

    // Distance from hex center (in screen space)
    float hex_dist = length(uv - hex_center) * hex_scale;

    // Per-hex depth offset (parallax)
    float depth = rnd;
    vec2 parallax = vec2(sin(t), cos(t * 0.7)) * depth * 0.01;

    // Sample original with parallax
    vec2 sample_uv = clamp(uv + parallax, 0.0, 1.0);
    vec4 col = HOOKED_tex(sample_uv);

    // Hex cell edge glow
    float edge = smoothstep(0.4, 0.5, hex_dist);
    vec3 edge_color = vec3(0.0, 0.8, 0.6) * edge * 0.6;

    // Animated pulse per hex (data traveling through grid)
    float pulse = sin(hex_id.x * 2.0 + hex_id.y * 3.0 + t * 4.0) * 0.5 + 0.5;
    pulse = pow(pulse, 4.0);  // Sharp pulse
    vec3 pulse_color = vec3(0.1, 0.9, 0.7) * pulse * 0.3 * (1.0 - edge);

    // Depth-based brightness (closer hexes brighter)
    col.rgb *= mix(0.7, 1.0, depth);

    // Combine
    col.rgb += edge_color + pulse_color;

    // Subtle hex interior gradient
    float inner_grad = 1.0 - hex_dist * 0.3;
    col.rgb *= inner_grad;

    return col;
}
