#version 330

layout(std140) uniform LIBRA_UBO_VERTEX
{
    mat4 MVP;
} LIBRA_UBO_VERTEX_INSTANCE;

struct LIBRA_PUSH_VERTEX
{
    vec4 OutputSize;
    vec4 OriginalSize;
    vec4 SourceSize;
    float ntsc_scale;
    float ntsc_phase;
    float ntsc_ring;
    float ntsc_cscale;
    float ntsc_cscale1;
    float ntsc_taps;
    float auto_res;
    float ntsc_charp;
    float ntsc_charp3;
    float speedup;
    float nscale;
};

uniform LIBRA_PUSH_VERTEX LIBRA_PUSH_VERTEX_INSTANCE;

layout(location = 0) in vec4 Position;
out vec2 LIBRA_VARYING_0;
layout(location = 1) in vec2 TexCoord;
float auto_rez;

void main()
{
    auto_rez = mix(1.0, 0.5, clamp((LIBRA_PUSH_VERTEX_INSTANCE.auto_res * round(LIBRA_PUSH_VERTEX_INSTANCE.OriginalSize.x / 300.0)) - 1.0, 0.0, 1.0));
    gl_Position = LIBRA_UBO_VERTEX_INSTANCE.MVP * Position;
    LIBRA_VARYING_0 = TexCoord + vec2(((0.5 / LIBRA_PUSH_VERTEX_INSTANCE.speedup) * (LIBRA_PUSH_VERTEX_INSTANCE.OriginalSize.z / auto_rez)) / 4.0, 0.0);
}

