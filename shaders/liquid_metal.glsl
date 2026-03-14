//!HOOK MAIN
//!BIND HOOKED
//!DESC Liquid Metal — chrome/mercury surface reflection simulation

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.025;
    vec2 texel = 1.0 / HOOKED_size;

    // Animated displacement field (simulating liquid metal surface)
    float wave1 = sin(uv.x * 15.0 + t * 2.0) * cos(uv.y * 12.0 + t * 1.5);
    float wave2 = sin(uv.x * 8.0 - t * 1.3 + uv.y * 10.0) * 0.7;
    float wave3 = sin((uv.x + uv.y) * 20.0 + t * 3.0) * 0.3;
    float surface = (wave1 + wave2 + wave3) * 0.33;

    // Surface normal from displacement (for reflection)
    float dx = sin((uv.x + texel.x) * 15.0 + t * 2.0) - sin((uv.x - texel.x) * 15.0 + t * 2.0);
    float dy = sin((uv.y + texel.y) * 12.0 + t * 1.5) - sin((uv.y - texel.y) * 12.0 + t * 1.5);
    vec2 normal = vec2(dx, dy) * 5.0;

    // Environment-mapped reflection of original image
    vec2 reflect_uv = uv + normal * 0.04;
    reflect_uv = clamp(reflect_uv, 0.0, 1.0);

    vec4 col = HOOKED_tex(reflect_uv);

    // Chrome coloring: convert to luminance, then map to metallic
    float lum = dot(col.rgb, vec3(0.299, 0.587, 0.114));

    // Specular highlights from surface curvature
    float specular = pow(max(surface * 0.5 + 0.5, 0.0), 8.0);

    // Chrome palette: silver/steel with blue tint
    vec3 chrome = mix(
        vec3(0.2, 0.22, 0.25),  // dark chrome
        vec3(0.9, 0.93, 0.97),  // bright chrome
        lum
    );

    // Fresnel-like edge brightening
    vec2 from_center = uv - 0.5;
    float fresnel = dot(from_center, from_center) * 2.0;
    chrome += vec3(0.15, 0.18, 0.25) * fresnel;

    // Specular highlights
    chrome += vec3(1.0, 0.98, 0.95) * specular * 0.8;

    // Subtle rainbow oil-slick iridescence
    float irid = sin(surface * 10.0 + t * 2.0) * 0.5 + 0.5;
    vec3 irid_color = vec3(
        sin(irid * 6.28) * 0.5 + 0.5,
        sin(irid * 6.28 + 2.094) * 0.5 + 0.5,
        sin(irid * 6.28 + 4.189) * 0.5 + 0.5
    );
    chrome += irid_color * 0.08;

    return vec4(chrome, 1.0);
}
