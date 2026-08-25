//!HOOK MAIN
//!BIND HOOKED
//!DESC Circuit Board — PCB trace pattern that follows image edges

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.02;
    vec4 col = HOOKED_tex(uv);

    // Grid for circuit traces
    float grid_scale = 30.0;
    vec2 grid_uv = uv * grid_scale;
    vec2 cell = floor(grid_uv);
    vec2 f = fract(grid_uv);

    // Edge detection to guide trace intensity
    vec2 texel = 1.0 / HOOKED_size;
    float lum = dot(col.rgb, vec3(0.299, 0.587, 0.114));
    float lum_r = dot(HOOKED_tex(uv + vec2(texel.x, 0.0)).rgb, vec3(0.299, 0.587, 0.114));
    float lum_d = dot(HOOKED_tex(uv + vec2(0.0, texel.y)).rgb, vec3(0.299, 0.587, 0.114));
    float edge = abs(lum - lum_r) + abs(lum - lum_d);

    // Per-cell random for trace routing
    float rnd = fract(sin(dot(cell, vec2(127.1, 311.7))) * 43758.5453);
    float rnd2 = fract(sin(dot(cell, vec2(269.5, 183.3))) * 43758.5453);

    // Traces: thin lines along cell edges forming circuit patterns
    float trace = 0.0;

    // Horizontal trace
    if (rnd > 0.3) {
        trace = max(trace, 1.0 - smoothstep(0.0, 0.06, abs(f.y - 0.5)));
    }
    // Vertical trace
    if (rnd2 > 0.4) {
        trace = max(trace, 1.0 - smoothstep(0.0, 0.06, abs(f.x - 0.5)));
    }
    // Corner pads (solder points)
    float pad_dist = length(f - vec2(rnd > 0.5 ? 0.0 : 1.0, rnd2 > 0.5 ? 0.0 : 1.0));
    float pad = smoothstep(0.15, 0.08, pad_dist);
    trace = max(trace, pad);

    // Via holes (center dots in some cells)
    if (rnd > 0.7) {
        float via = smoothstep(0.1, 0.05, length(f - 0.5));
        trace = max(trace, via);
    }

    // Traces stronger near edges in the image
    trace *= mix(0.4, 1.0, smoothstep(0.0, 0.1, edge));

    // Animated data pulse traveling along traces
    float pulse_pos = fract(t * 1.5 + rnd * 6.28);
    float pulse;
    if (rnd > 0.3 && rnd2 <= 0.4) {
        pulse = smoothstep(0.06, 0.0, abs(f.x - pulse_pos));
    } else {
        pulse = smoothstep(0.06, 0.0, abs(f.y - pulse_pos));
    }
    pulse *= trace;

    // Colors: dark green PCB base + copper traces + bright data pulse
    vec3 pcb = col.rgb * vec3(0.3, 0.5, 0.35);
    vec3 copper = vec3(0.7, 0.5, 0.2) * trace * 0.6;
    vec3 data_light = vec3(0.2, 1.0, 0.4) * pulse * 1.5;

    vec3 result = pcb + copper + data_light;

    return vec4(result, 1.0);
}
