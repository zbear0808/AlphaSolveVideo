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
    float SIGMA_HOR;
    float HSHARPNESS;
    float S_SHARP;
    float HARNG;
    float HSHARP;
    float spike;
    float filter_res;
    float MAXS;
    float auto_res;
};

uniform LIBRA_PUSH_VERTEX LIBRA_PUSH_VERTEX_INSTANCE;

layout(location = 0) in vec4 Position;
out vec2 LIBRA_VARYING_0;
layout(location = 1) in vec2 TexCoord;
float auto_rez;

void main()
{
    float _24;
    if (LIBRA_PUSH_VERTEX_INSTANCE.OriginalSize.y < 375.0)
    {
        _24 = mix(1.0, 1.85000002384185791015625, clamp((LIBRA_PUSH_VERTEX_INSTANCE.auto_res * round(LIBRA_PUSH_VERTEX_INSTANCE.OriginalSize.x / 300.0)) - 1.0, 0.0, 1.0));
    }
    else
    {
        _24 = 1.0;
    }
    auto_rez = _24;
    gl_Position = LIBRA_UBO_VERTEX_INSTANCE.MVP * Position;
    LIBRA_VARYING_0 = TexCoord * 1.000010013580322265625;
}

