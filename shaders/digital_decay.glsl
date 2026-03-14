//!HOOK MAIN
//!BIND HOOKED
//!DESC Digital Decay — corrupted digital signal with pixel rot and static

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.04;

    // Horizontal tear lines — random positions that shift per frame
    float tear_seed = floor(t * 3.0);
    float tear1_y = fract(sin(tear_seed * 127.1) * 43758.5453);
    float tear2_y = fract(sin(tear_seed * 269.5) * 43758.5453);
    float tear3_y = fract(sin(tear_seed * 483.7) * 43758.5453);

    float tear1 = smoothstep(0.01, 0.0, abs(uv.y - tear1_y));
    float tear2 = smoothstep(0.008, 0.0, abs(uv.y - tear2_y));
    float tear3 = smoothstep(0.015, 0.0, abs(uv.y - tear3_y));

    // Horizontal displacement at tear lines
    vec2 displaced_uv = uv;
    if (tear1 > 0.1) displaced_uv.x += (fract(sin(tear_seed * 321.7) * 43758.5453) - 0.5) * 0.15;
    if (tear2 > 0.1) displaced_uv.x += (fract(sin(tear_seed * 567.3) * 43758.5453) - 0.5) * 0.08;
    if (tear3 > 0.1) displaced_uv.x += (fract(sin(tear_seed * 891.1) * 43758.5453) - 0.5) * 0.2;

    displaced_uv = clamp(displaced_uv, 0.0, 1.0);

    // Pixel rot: some areas randomly decay to wrong colors
    vec2 rot_cell = floor(uv * 60.0);
    float rot_rnd = fract(sin(dot(rot_cell + floor(t * 2.0), vec2(12.9898, 78.233))) * 43758.5453);
    bool is_rotted = rot_rnd > 0.97;  // ~3% of cells are corrupted

    vec4 col;
    if (is_rotted) {
        // Corrupted pixel: show garbled data
        float garble = fract(sin(dot(rot_cell, vec2(127.1, 311.7))) * 43758.5453);
        col = vec4(
            garble,
            fract(garble * 7.31),
            fract(garble * 13.17),
            1.0
        );
    } else {
        col = HOOKED_tex(displaced_uv);
    }

    // Vertical color banding (broadcast interference)
    float band = sin(uv.y * HOOKED_size.y * 0.8 + t * 20.0);
    band = smoothstep(0.95, 1.0, band) * 0.15;
    col.rgb += band;

    // Static snow overlay that intensifies randomly
    float snow_intensity = (sin(t * 7.0) * 0.5 + 0.5) * 0.12;
    float snow = fract(sin(dot(uv * HOOKED_size + t * 100.0, vec2(12.9898, 78.233))) * 43758.5453);
    col.rgb = mix(col.rgb, vec3(snow), snow_intensity);

    // Brief full-frame whiteout flash (every ~100 frames)
    float flash = smoothstep(0.98, 1.0, sin(t * 0.5));
    col.rgb = mix(col.rgb, vec3(0.9), flash * 0.6);

    return col;
}
