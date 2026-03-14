//!HOOK MAIN
//!BIND HOOKED
//!DESC Electric Arc — lightning/tesla coil arcs between bright regions

vec4 hook() {
    vec2 uv = HOOKED_pos;
    float t = float(frame) * 0.05;
    vec4 col = HOOKED_tex(uv);

    float lum = dot(col.rgb, vec3(0.299, 0.587, 0.114));

    // Find bright "charge points" — edges become arc attractors
    vec2 texel = 1.0 / HOOKED_size;
    float edge = 0.0;
    float l = dot(HOOKED_tex(uv + vec2(-texel.x, 0.0)).rgb, vec3(0.33));
    float r = dot(HOOKED_tex(uv + vec2(texel.x, 0.0)).rgb, vec3(0.33));
    float u = dot(HOOKED_tex(uv + vec2(0.0, -texel.y)).rgb, vec3(0.33));
    float d = dot(HOOKED_tex(uv + vec2(0.0, texel.y)).rgb, vec3(0.33));
    edge = abs(l - r) + abs(u - d);

    // Generate lightning bolt patterns using fractal noise
    float bolt = 0.0;
    float freq = 30.0;
    float amp = 1.0;

    for (int i = 0; i < 5; i++) {
        float n = sin(uv.x * freq + t * (3.0 + float(i))) *
                  cos(uv.y * freq * 0.7 + t * (2.0 + float(i) * 0.5));
        n += sin((uv.x + uv.y) * freq * 0.5 - t * (4.0 + float(i)));
        bolt += abs(n) * amp;
        freq *= 2.0;
        amp *= 0.5;
    }

    bolt = 1.0 - bolt * 0.2;
    bolt = pow(max(bolt, 0.0), 15.0);  // Sharp lightning lines

    // Arc intensity follows image edges (electricity along contours)
    float arc_strength = bolt * smoothstep(0.02, 0.1, edge) * 3.0;

    // Additional random discharge sparks
    float spark = fract(sin(dot(floor(uv * 100.0 + floor(t * 10.0)),
                   vec2(12.9898, 78.233))) * 43758.5453);
    spark = step(0.997, spark) * lum * 2.0;

    // Electric colors: white core, blue-purple glow
    vec3 arc_core = vec3(0.9, 0.95, 1.0) * arc_strength;
    vec3 arc_glow = vec3(0.3, 0.4, 1.0) * arc_strength * 0.5;
    vec3 spark_color = vec3(0.5, 0.7, 1.0) * spark;

    // Darken frame slightly to make arcs pop
    vec3 result = col.rgb * 0.85;
    result += arc_core + arc_glow + spark_color;

    return vec4(result, 1.0);
}
