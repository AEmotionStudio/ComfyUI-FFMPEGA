//!HOOK MAIN
//!BIND HOOKED
//!DESC Datamosh — simulated I-frame corruption / motion smear

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.03;

    // Create pseudo-random block grid (simulating macroblocks)
    float block_size = 16.0;
    vec2 block = floor(uv * HOOKED_size / block_size);

    // Per-block random — some blocks are "corrupted"
    float block_rnd = fract(sin(dot(block, vec2(127.1, 311.7))) * 43758.5453);
    float block_rnd2 = fract(sin(dot(block, vec2(269.5, 183.3))) * 43758.5453);

    // Corruption probability oscillates with time
    float corrupt_threshold = 0.55 + sin(t * 2.0) * 0.15;
    bool is_corrupted = block_rnd > corrupt_threshold;

    vec2 sample_uv = uv;
    if (is_corrupted) {
        // Smear: shift sampling UV based on block random
        vec2 smear_dir = vec2(
            (block_rnd2 - 0.5) * 2.0,
            (fract(block_rnd * 7.31) - 0.5) * 2.0
        );
        float smear_amount = 0.03 + block_rnd * 0.05;
        sample_uv += smear_dir * smear_amount;

        // Some blocks get stuck (freeze at block center)
        if (block_rnd2 > 0.7) {
            vec2 block_center = (block + 0.5) * block_size / HOOKED_size;
            sample_uv = mix(sample_uv, block_center, 0.5);
        }
    }

    sample_uv = clamp(sample_uv, 0.0, 1.0);
    vec4 col = HOOKED_tex(sample_uv);

    // Color channel corruption in corrupted blocks
    if (is_corrupted && block_rnd2 > 0.5) {
        float shift = 0.005 * block_rnd;
        col.r = HOOKED_tex(sample_uv + vec2(shift, 0.0)).r;
        col.b = HOOKED_tex(sample_uv - vec2(shift, 0.0)).b;
    }

    // Block edge artifacts
    vec2 block_uv = fract(uv * HOOKED_size / block_size);
    if (is_corrupted) {
        float edge = smoothstep(0.0, 0.05, min(block_uv.x, block_uv.y));
        float edge2 = smoothstep(0.0, 0.05, min(1.0 - block_uv.x, 1.0 - block_uv.y));
        col.rgb *= mix(0.6, 1.0, edge * edge2);
    }

    return col;
}
