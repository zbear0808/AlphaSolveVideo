#version 330

layout(std140) uniform LIBRA_UBO_VERTEX
{
    vec4 SourceSize;
    mat4 MVP;
} LIBRA_UBO_VERTEX_INSTANCE;

struct LIBRA_PUSH_VERTEX
{
    vec4 OriginalSize;
    vec4 OutputSize;
    uint FrameCount;
    float inter;
    float interm;
    float iscan;
    float intres;
    float iscans;
    float hiscan;
};

uniform LIBRA_PUSH_VERTEX LIBRA_PUSH_VERTEX_INSTANCE;

layout(location = 0) in vec4 Position;
out vec2 LIBRA_VARYING_0;
layout(location = 1) in vec2 TexCoord;

void main()
{
    gl_Position = LIBRA_UBO_VERTEX_INSTANCE.MVP * Position;
    LIBRA_VARYING_0 = TexCoord * 1.000010013580322265625;
}

