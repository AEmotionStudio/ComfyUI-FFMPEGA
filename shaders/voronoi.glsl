//!HOOK MAIN
//!BIND HOOKED
//!DESC Voronoi Cell / Toon Edge Shading Shader

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 px = HOOKED_size;

    // ── Cell grid parameters ──
    float cellSize = 20.0;
    vec2 cellUV = uv * px / cellSize;
    vec2 cellIdx = floor(cellUV);

    // ── Voronoi distance (nearest cell center) ──
    float minDist = 10.0;
    vec2 nearestCell = cellIdx;

    for (int y = -1; y <= 1; y++) {
        for (int x = -1; x <= 1; x++) {
            vec2 neighbor = cellIdx + vec2(float(x), float(y));
            // Pseudo-random cell center offset
            vec2 rnd = fract(sin(vec2(
                dot(neighbor, vec2(127.1, 311.7)),
                dot(neighbor, vec2(269.5, 183.3))
            )) * 43758.5453);
            vec2 center = neighbor + rnd;
            float d = distance(cellUV, center);
            if (d < minDist) {
                minDist = d;
                nearestCell = neighbor;
            }
        }
    }

    // ── Sample color from cell center ──
    vec2 rnd = fract(sin(vec2(
        dot(nearestCell, vec2(127.1, 311.7)),
        dot(nearestCell, vec2(269.5, 183.3))
    )) * 43758.5453);
    vec2 sampleUV = (nearestCell + rnd) * cellSize / px;
    sampleUV = clamp(sampleUV, 0.0, 1.0);
    vec4 cellColor = HOOKED_tex(sampleUV);

    // ── Posterize colors (toon look) ──
    float levels = 6.0;
    cellColor.rgb = floor(cellColor.rgb * levels + 0.5) / levels;

    // ── Edge darkening at cell boundaries ──
    float edge = smoothstep(0.0, 0.15, minDist);
    cellColor.rgb *= edge;

    return cellColor;
}
