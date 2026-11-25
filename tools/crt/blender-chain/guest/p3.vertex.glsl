#version 330

layout(std140) uniform LIBRA_UBO_VERTEX
{
    mat4 MVP;
} LIBRA_UBO_VERTEX_INSTANCE;

struct LIBRA_PUSH_VERTEX
{
    vec4 SourceSize;
    vec4 OriginalSize;
    vec4 OutputSize;
    uint FrameCount;
    float TNTC;
    float LS;
    float LUTLOW;
    float LUTBR;
    float CP;
    float CS;
    float WP;
    float wp_saturation;
    float AS;
    float agsat;
    float BP;
    float vigstr;
    float vigdef;
    float sega_fix;
    float pre_bb;
    float contr;
    float pre_gc;
};

uniform LIBRA_PUSH_VERTEX LIBRA_PUSH_VERTEX_INSTANCE;

layout(location = 0) in vec4 Position;
out vec2 LIBRA_VARYING_0;
layout(location = 1) in vec2 TexCoord;

void main()
{
    gl_Position = LIBRA_UBO_VERTEX_INSTANCE.MVP * Position;
    LIBRA_VARYING_0 = TexCoord;
}

