#version 330

layout(std140) uniform LIBRA_UBO_VERTEX
{
    mat4 MVP;
} LIBRA_UBO_VERTEX_INSTANCE;

struct LIBRA_PUSH_VERTEX
{
    vec4 LinearizePassSize;
    vec4 OriginalSize;
    vec4 OutputSize;
    uint FrameCount;
    float SIZEH;
    float SIGMA_H;
    float FINE_GLOW;
    float m_glow;
    float m_glow_cutoff;
    float m_glow_low;
    float m_glow_high;
    float m_glow_dist;
    float m_glow_mask;
    float auto_res;
};

uniform LIBRA_PUSH_VERTEX LIBRA_PUSH_VERTEX_INSTANCE;

layout(location = 0) in vec4 Position;
out vec2 LIBRA_VARYING_0;
layout(location = 1) in vec2 TexCoord;
float auto_rez;
float FINE_GLOW;

void main()
{
    float _24;
    if (LIBRA_PUSH_VERTEX_INSTANCE.OriginalSize.y < 375.0)
    {
        _24 = mix(1.0, 2.0, clamp((LIBRA_PUSH_VERTEX_INSTANCE.auto_res * round(LIBRA_PUSH_VERTEX_INSTANCE.OriginalSize.x / 300.0)) - 1.0, 0.0, 1.0));
    }
    else
    {
        _24 = 1.0;
    }
    auto_rez = _24;
    float _51;
    if (LIBRA_PUSH_VERTEX_INSTANCE.FINE_GLOW > 0.5)
    {
        _51 = LIBRA_PUSH_VERTEX_INSTANCE.FINE_GLOW;
    }
    else
    {
        _51 = mix(0.75, 0.5, -LIBRA_PUSH_VERTEX_INSTANCE.FINE_GLOW);
    }
    FINE_GLOW = _51;
    gl_Position = LIBRA_UBO_VERTEX_INSTANCE.MVP * Position;
    LIBRA_VARYING_0 = TexCoord;
}

