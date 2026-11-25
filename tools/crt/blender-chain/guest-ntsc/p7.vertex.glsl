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
    uint FrameCount;
    float ntsc_phase;
    float auto_res;
    float ntsc_sharp;
    float ntsc_fonts;
    float ntsc_charp;
    float ntsc_charp3;
    float ntsc_shape;
    float ntsc_gamma;
    float ntsc_rainbow1;
    float speedup;
    float RFNOISE;
    float RFNOISE1;
    float RFNOISE2;
};

uniform LIBRA_PUSH_VERTEX LIBRA_PUSH_VERTEX_INSTANCE;

layout(location = 0) in vec4 Position;
out vec2 LIBRA_VARYING_1;
layout(location = 1) in vec2 TexCoord;
out vec2 LIBRA_VARYING_2;
out vec2 LIBRA_VARYING_0;
float auto_rez;
float RFNOISE;

void main()
{
    auto_rez = mix(1.0, 0.5, clamp((LIBRA_PUSH_VERTEX_INSTANCE.auto_res * round(LIBRA_PUSH_VERTEX_INSTANCE.OriginalSize.x / 300.0)) - 1.0, 0.0, 1.0));
    RFNOISE = (LIBRA_PUSH_VERTEX_INSTANCE.RFNOISE * LIBRA_PUSH_VERTEX_INSTANCE.RFNOISE) + 9.9999997473787516355514526367188e-06;
    gl_Position = LIBRA_UBO_VERTEX_INSTANCE.MVP * Position;
    LIBRA_VARYING_1 = TexCoord / vec2(LIBRA_PUSH_VERTEX_INSTANCE.speedup, 1.0);
    LIBRA_VARYING_2 = (floor(LIBRA_VARYING_1 * LIBRA_PUSH_VERTEX_INSTANCE.OriginalSize.xy) + vec2(0.5)) * LIBRA_PUSH_VERTEX_INSTANCE.OriginalSize.zw;
    LIBRA_VARYING_0 = TexCoord + vec2((0.5 * (LIBRA_PUSH_VERTEX_INSTANCE.OriginalSize.z / auto_rez)) / 4.0, 0.0);
}

