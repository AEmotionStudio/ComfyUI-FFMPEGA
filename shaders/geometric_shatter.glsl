//!HOOK MAIN
//!BIND HOOKED
//!DESC Geometric Shatter — image breaks into triangular shards

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.015;

    // Triangular grid
    float scale = 10.0;
    vec2 grid_uv = uv * scale;

    // Create triangle cells via splitting quads diagonally
    vec2 cell = floor(grid_uv);
    vec2 f = fract(grid_uv);

    // Determine which triangle we're in (upper-left or lower-right)
    float triangle = step(f.x + f.y, 1.0);
    vec2 tri_id = cell * 2.0 + vec2(triangle);

    // Per-shard random properties
    float rnd1 = fract(sin(dot(tri_id, vec2(127.1, 311.7))) * 43758.5453);
    float rnd2 = fract(sin(dot(tri_id, vec2(269.5, 183.3))) * 43758.5453);
    float rnd3 = fract(sin(dot(tri_id, vec2(419.2, 371.9))) * 43758.5453);

    // Shard displacement (explosion from center)
    vec2 center = vec2(0.5, 0.5);
    vec2 shard_center = (cell + (triangle > 0.5 ? vec2(0.33, 0.33) : vec2(0.66, 0.66))) / scale;
    vec2 explode_dir = normalize(shard_center - center + 0.001);

    // Animated explosion intensity (breathing between intact and shattered)
    float explode_amount = sin(t * 0.8) * 0.5 + 0.5;
    explode_amount = pow(explode_amount, 2.0);

    // Displacement per shard
    float shard_speed = 0.5 + rnd1 * 1.5;
    vec2 displacement = explode_dir * explode_amount * 0.05 * shard_speed;

    // Rotation per shard
    float rot_angle = (rnd2 - 0.5) * explode_amount * 1.0;
    vec2 shard_origin = shard_center;
    vec2 local = uv - shard_origin;
    float ca = cos(rot_angle);
    float sa = sin(rot_angle);
    vec2 rotated = vec2(
        local.x * ca - local.y * sa,
        local.x * sa + local.y * ca
    );
    vec2 sample_uv = rotated + shard_origin + displacement;
    sample_uv = clamp(sample_uv, 0.0, 1.0);

    vec4 col = HOOKED_tex(sample_uv);

    // Z-depth per shard (parallax)
    float depth = rnd3 * explode_amount;
    col.rgb *= (1.0 - depth * 0.3);

    // Shard edge highlight (crack lines)
    float edge_x, edge_y;
    if (triangle > 0.5) {
        edge_x = smoothstep(0.0, 0.03, f.x);
        edge_y = smoothstep(0.0, 0.03, f.y);
        float diag = smoothstep(0.0, 0.03, abs(f.x + f.y - 1.0));
        float edge = 1.0 - edge_x * edge_y * diag;
        col.rgb = mix(col.rgb, vec3(0.9), edge * explode_amount * 0.8);
    } else {
        edge_x = smoothstep(0.0, 0.03, 1.0 - f.x);
        edge_y = smoothstep(0.0, 0.03, 1.0 - f.y);
        float diag = smoothstep(0.0, 0.03, abs(f.x + f.y - 1.0));
        float edge = 1.0 - edge_x * edge_y * diag;
        col.rgb = mix(col.rgb, vec3(0.9), edge * explode_amount * 0.8);
    }

    // Glass-like specular on shard surface
    float spec = pow(rnd1, 4.0) * explode_amount * 0.3;
    col.rgb += vec3(0.8, 0.85, 0.9) * spec;

    return col;
}
