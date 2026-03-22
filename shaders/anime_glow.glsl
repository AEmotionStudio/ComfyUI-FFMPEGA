//!HOOK MAIN
//!BIND HOOKED
//!DESC Anime Glow — soft dreamy bloom with pastel color shift and sparkle

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 texel = 1.0 / HOOKED_size;
    float t = float(frame) * 0.012;
    vec4 col = HOOKED_tex(uv);

    float lum = dot(col.rgb, vec3(0.299, 0.587, 0.114));

    // ── Kawase-style blur for bloom extraction ──
    // Multi-pass approximation using expanding kernel
    vec3 bloom1 = vec3(0.0);
    float w1 = 0.0;
    for (int dx = -2; dx <= 2; dx++) {
        for (int dy = -2; dy <= 2; dy++) {
            float w = exp(-float(dx*dx + dy*dy) / 3.0);
            vec3 s = HOOKED_tex(uv + vec2(float(dx), float(dy)) * texel * 2.0).rgb;
            float s_lum = dot(s, vec3(0.299, 0.587, 0.114));
            // Extract only bright areas for bloom
            s *= smoothstep(0.45, 0.75, s_lum);
            bloom1 += s * w;
            w1 += w;
        }
    }
    bloom1 /= w1;

    // Second wider bloom pass
    vec3 bloom2 = vec3(0.0);
    float w2 = 0.0;
    for (int dx = -3; dx <= 3; dx++) {
        for (int dy = -3; dy <= 3; dy++) {
            float w = exp(-float(dx*dx + dy*dy) / 8.0);
            vec3 s = HOOKED_tex(uv + vec2(float(dx), float(dy)) * texel * 4.0).rgb;
            float s_lum = dot(s, vec3(0.299, 0.587, 0.114));
            s *= smoothstep(0.5, 0.8, s_lum);
            bloom2 += s * w;
            w2 += w;
        }
    }
    bloom2 /= w2;

    // Combined bloom
    vec3 bloom = bloom1 * 0.6 + bloom2 * 0.4;

    // ── Pastel color shift (warm highlights, cool shadows) ──
    vec3 pastel = col.rgb;
    // Warm shift in highlights
    float highlight = smoothstep(0.5, 0.85, lum);
    pastel += vec3(0.06, 0.03, -0.02) * highlight;

    // Cool shift in shadows
    float shadow = smoothstep(0.4, 0.15, lum);
    pastel += vec3(-0.03, 0.01, 0.05) * shadow;

    // Slight desaturation for dreamy look
    float gray = dot(pastel, vec3(0.299, 0.587, 0.114));
    pastel = mix(vec3(gray), pastel, 0.88);

    // ── Soft light blend mode for bloom ──
    vec3 result = pastel;
    // Soft light: 2*a*b + a²*(1-2b) when b<0.5
    // Simplified additive bloom
    result += bloom * 1.2;

    // ── Sparkle on very bright spots ──
    float sparkle_seed = fract(sin(dot(floor(uv * HOOKED_size / 3.0), vec2(12.9898, 78.233))) * 43758.5453);
    float sparkle = smoothstep(0.96, 1.0, sparkle_seed) * smoothstep(0.7, 0.9, lum);

    // Animated twinkle
    float twinkle = sin(sparkle_seed * 100.0 + t * 3.0) * 0.5 + 0.5;
    sparkle *= twinkle;

    // 4-point star shape
    vec2 spark_uv = fract(uv * HOOKED_size / 3.0) - 0.5;
    float star = max(
        exp(-abs(spark_uv.x) * 8.0) * exp(-abs(spark_uv.y) * 30.0),
        exp(-abs(spark_uv.x) * 30.0) * exp(-abs(spark_uv.y) * 8.0)
    );
    sparkle *= star;

    result += vec3(1.0, 0.95, 0.9) * sparkle * 2.0;

    // ── Gentle vignette ──
    vec2 vig_uv = uv - 0.5;
    float vig = 1.0 - dot(vig_uv, vig_uv) * 0.5;
    result *= vig;

    return vec4(clamp(result, 0.0, 1.0), 1.0);
}
