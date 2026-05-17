#version 120
varying vec3 v_normal;

uniform vec3 u_light_dir;
uniform vec3 u_base_color;

void main() {
    vec3 n = normalize(v_normal);
    float diff = max(dot(n, normalize(u_light_dir)), 0.15);
    vec3 col = u_base_color * (0.35 + 0.65 * diff);
    gl_FragColor = vec4(col, 1.0);
}
