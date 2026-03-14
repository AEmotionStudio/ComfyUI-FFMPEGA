//!HOOK MAIN
//!BIND HOOKED
//!DESC Particle Dissolve — frame breaks apart into drifting particles

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.02;
    vec4 col = HOOKED_tex(uv);

    // Animated dissolve threshold (cycles 0→1 slowly)
    float dissolve_progress = sin(t * 0.5) * 0.5 + 0.5;

    // Per-pixel noise for dissolve mask
    vec2 noise_uv = uv * 40.0;
    float n = fract(sin(dot(floor(noise_uv), vec2(12.9898, 78.233))) * 43758.5453);
    float n2 = fract(sin(dot(floor(noise_uv * 1.7), vec2(269.5, 183.3))) * 43758.5453);

    // Dissolve: pixels below threshold become particles
    float dissolve = step(n, dissolve_progress);

    // For dissolved pixels: drift them
    if (dissolve < 0.5) {
        // Particle drift direction (upward + sideways)
        float age = dissolve_progress - n;
        float drift_x = sin(n * 50.0 + t * 3.0) * age * 0.15;
        float drift_y = -age * 0.2 - n2 * age * 0.1;

        vec2 particle_uv = uv + vec2(drift_x, drift_y);
        particle_uv = clamp(particle_uv, 0.0, 1.0);

        col = HOOKED_tex(particle_uv);

        // Fade out as particle drifts
        float fade = smoothstep(0.3, 0.0, age);
        col.rgb *= fade;

        // Hot edge glow at dissolve boundary
        float boundary = smoothstep(0.05, 0.0, abs(n - dissolve_progress));
        col.rgb += vec3(1.0, 0.5, 0.1) * boundary * 1.5;
        col.rgb += vec3(1.0, 0.8, 0.3) * boundary * boundary * 2.0;

        // Ember particles
        float ember = smoothstep(0.03, 0.0, abs(n - dissolve_progress + 0.02));
        col.rgb += vec3(1.0, 0.3, 0.05) * ember * 3.0;
    } else {
        // Surviving pixels get slight heat distortion near dissolve edge
        float near_edge = smoothstep(0.1, 0.0, abs(n - dissolve_progress));
        vec2 heat = vec2(
            sin(uv.y * 50.0 + t * 5.0) * near_edge * 0.003,
            cos(uv.x * 50.0 + t * 5.0) * near_edge * 0.003
        );
        col = HOOKED_tex(uv + heat);

        // Subtle orange rim light at dissolve boundary
        col.rgb += vec3(0.5, 0.2, 0.05) * near_edge * 0.8;
    }

    return col;
}
