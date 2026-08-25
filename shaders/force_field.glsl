//!HOOK MAIN
//!BIND HOOKED
//!DESC Force Field / Energy Barrier Glow Shader

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.03;

    vec4 col = HOOKED_tex(uv);

    // ── Edge detection via Sobel-like gradient ──
    vec2 texel = 1.0 / HOOKED_size;

    float tl = dot(HOOKED_tex(uv + vec2(-texel.x, -texel.y)).rgb, vec3(0.333));
    float t0 = dot(HOOKED_tex(uv + vec2(0.0, -texel.y)).rgb, vec3(0.333));
    float tr = dot(HOOKED_tex(uv + vec2(texel.x, -texel.y)).rgb, vec3(0.333));
    float ml = dot(HOOKED_tex(uv + vec2(-texel.x, 0.0)).rgb, vec3(0.333));
    float mr = dot(HOOKED_tex(uv + vec2(texel.x, 0.0)).rgb, vec3(0.333));
    float bl = dot(HOOKED_tex(uv + vec2(-texel.x, texel.y)).rgb, vec3(0.333));
    float b0 = dot(HOOKED_tex(uv + vec2(0.0, texel.y)).rgb, vec3(0.333));
    float br = dot(HOOKED_tex(uv + vec2(texel.x, texel.y)).rgb, vec3(0.333));

    float gx = -tl - 2.0*ml - bl + tr + 2.0*mr + br;
    float gy = -tl - 2.0*t0 - tr + bl + 2.0*b0 + br;
    float edge = sqrt(gx * gx + gy * gy);
    edge = smoothstep(0.05, 0.4, edge);

    // ── Animated energy color ──
    float hueShift = t * 2.0 + uv.y * 3.0;
    vec3 energy;
    energy.r = sin(hueShift) * 0.5 + 0.5;
    energy.g = sin(hueShift + 2.094) * 0.5 + 0.5;
    energy.b = sin(hueShift + 4.189) * 0.5 + 0.5;

    // ── Pulsing glow intensity ──
    float pulse = sin(t * 3.0) * 0.3 + 0.7;
    edge *= pulse;

    // ── Hex grid pattern (energy lattice) ──
    float hexScale = 40.0;
    vec2 hexUV = uv * hexScale;
    vec2 hexR = vec2(1.0, 1.732);
    vec2 hexH = hexR * 0.5;
    vec2 a = mod(hexUV, hexR) - hexH;
    vec2 b2 = mod(hexUV - hexH, hexR) - hexH;
    float hexDist = min(dot(a, a), dot(b2, b2));
    float hexLine = smoothstep(0.0, 0.05, abs(hexDist - 0.15));
    hexLine = 1.0 - (1.0 - hexLine) * 0.3;

    // ── Compose: original + edge glow ──
    vec3 result = col.rgb;
    result += energy * edge * 1.5;
    result *= hexLine;

    return vec4(clamp(result, 0.0, 1.0), col.a);
}
