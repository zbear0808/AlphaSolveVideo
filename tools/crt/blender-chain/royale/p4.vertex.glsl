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
};

uniform LIBRA_PUSH_VERTEX LIBRA_PUSH_VERTEX_INSTANCE;

layout(location = 0) in vec4 Position;
out vec2 LIBRA_VARYING_0;
layout(location = 1) in vec2 TexCoord;
out vec2 LIBRA_VARYING_1;

void main()
{
    gl_Position = LIBRA_UBO_VERTEX_INSTANCE.MVP * Position;
    LIBRA_VARYING_0 = TexCoord;
    vec2 dxdy_scale = LIBRA_PUSH_VERTEX_INSTANCE.SourceSize.xy * LIBRA_PUSH_VERTEX_INSTANCE.OutputSize.zw;
    vec2 dxdy = dxdy_scale * LIBRA_PUSH_VERTEX_INSTANCE.SourceSize.zw;
    LIBRA_VARYING_1 = vec2(dxdy.x, 0.0);
}

