#version 120
attribute vec3 a_position;
attribute vec3 a_normal;

uniform mat4 u_mvp;
uniform mat4 u_model;
uniform mat3 u_normal_mat;

varying vec3 v_normal;

void main() {
    vec4 world = u_model * vec4(a_position, 1.0);
    v_normal = normalize(u_normal_mat * a_normal);
    gl_Position = u_mvp * world;
}
