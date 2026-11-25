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
    float SIZEVB;
    float SIGMA_VB;
    float FINE_BLOOM;
};

uniform LIBRA_PUSH_VERTEX LIBRA_PUSH_VERTEX_INSTANCE;

layout(location = 0) in vec4 Position;
out vec2 LIBRA_VARYING_0;
layout(location = 1) in vec2 TexCoord;
float FINE_BLOOM;

void main()
{
    float _23;
    if (LIBRA_PUSH_VERTEX_INSTANCE.FINE_BLOOM > 0.5)
    {
        _23 = LIBRA_PUSH_VERTEX_INSTANCE.FINE_BLOOM;
    }
    else
    {
        _23 = mix(0.75, 0.5, -LIBRA_PUSH_VERTEX_INSTANCE.FINE_BLOOM);
    }
    FINE_BLOOM = _23;
    gl_Position = LIBRA_UBO_VERTEX_INSTANCE.MVP * Position;
    LIBRA_VARYING_0 = TexCoord;
}

