//!HOOK MAIN
//!BIND HOOKED
//!DESC Emboss 3D — deep dimensional relief carving with lighting

vec4 hook() {
    vec2 uv = HOOKED_pos;
    vec2 texel = 1.0 / HOOKED_size;
    float t = float(frame) * 0.01;

    // Animated light direction (rotating overhead light)
    vec2 light_dir = normalize(vec2(cos(t), sin(t)));

    // Multi-scale emboss for deep 3D relief effect
    float emboss = 0.0;

    // Fine detail emboss
    float p1 = dot(HOOKED_tex(uv + light_dir * texel).rgb, vec3(0.33));
    float p2 = dot(HOOKED_tex(uv - light_dir * texel).rgb, vec3(0.33));
    emboss += (p1 - p2) * 2.0;

    // Medium detail emboss (2px)
    float p3 = dot(HOOKED_tex(uv + light_dir * texel * 2.0).rgb, vec3(0.33));
    float p4 = dot(HOOKED_tex(uv - light_dir * texel * 2.0).rgb, vec3(0.33));
    emboss += (p3 - p4) * 1.0;

    // Large detail emboss (4px)
    float p5 = dot(HOOKED_tex(uv + light_dir * texel * 4.0).rgb, vec3(0.33));
    float p6 = dot(HOOKED_tex(uv - light_dir * texel * 4.0).rgb, vec3(0.33));
    emboss += (p5 - p6) * 0.5;

    emboss /= 3.5;

    // Surface base: original with reduced saturation
    vec4 col = HOOKED_tex(uv);
    float lum = dot(col.rgb, vec3(0.299, 0.587, 0.114));
    vec3 surface = mix(vec3(lum), col.rgb, 0.3);

    // Apply emboss as light/shadow
    vec3 highlight = vec3(1.0, 0.95, 0.85);
    vec3 shadow = vec3(0.1, 0.12, 0.18);

    vec3 result;
    if (emboss > 0.0) {
        result = mix(surface, highlight, emboss * 1.5);
    } else {
        result = mix(surface, shadow, -emboss * 1.5);
    }

    // Specular sparkle on high ridges
    float spec = pow(max(emboss, 0.0), 4.0) * 2.0;
    result += vec3(1.0) * spec;

    return vec4(result, 1.0);
}
