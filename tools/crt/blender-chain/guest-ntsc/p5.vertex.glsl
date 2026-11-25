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
    float quality;
    float ntsc_sat;
    float cust_fringing;
    float cust_artifacting;
    float ntsc_bright;
    float ntsc_scale;
    float ntsc_fields;
    float ntsc_phase;
    float ntsc_gamma;
    float ntsc_rainbow1;
    float ntsc_taps;
    float auto_res;
    float ntsc_charp;
    float ntsc_charp3;
    float speedup;
};

uniform LIBRA_PUSH_VERTEX LIBRA_PUSH_VERTEX_INSTANCE;

layout(location = 0) in vec4 Position;
out vec2 LIBRA_VARYING_0;
layout(location = 1) in vec2 TexCoord;
out vec2 LIBRA_VARYING_1;
out float LIBRA_VARYING_2;
out float LIBRA_VARYING_7;
out float LIBRA_VARYING_6;
out float LIBRA_VARYING_5;
out float LIBRA_VARYING_4;
out float LIBRA_VARYING_3;
out float LIBRA_VARYING_8;
float FrameCount;
float auto_rez;

void main()
{
    FrameCount = float(LIBRA_PUSH_VERTEX_INSTANCE.FrameCount);
    auto_rez = mix(1.0, 0.5, clamp((LIBRA_PUSH_VERTEX_INSTANCE.auto_res * round(LIBRA_PUSH_VERTEX_INSTANCE.OriginalSize.x / 300.0)) - 1.0, 0.0, 1.0));
    float res = min(LIBRA_PUSH_VERTEX_INSTANCE.ntsc_scale * auto_rez, 1.0);
    float OriginalSize = LIBRA_PUSH_VERTEX_INSTANCE.OriginalSize.x * auto_rez;
    gl_Position = LIBRA_UBO_VERTEX_INSTANCE.MVP * Position;
    LIBRA_VARYING_0 = TexCoord * vec2(LIBRA_PUSH_VERTEX_INSTANCE.speedup, 1.0);
    LIBRA_VARYING_1 = ((LIBRA_VARYING_0 * LIBRA_PUSH_VERTEX_INSTANCE.OriginalSize.xy) * vec2(res, res / auto_rez)) * vec2(4.0, 1.0);
    float _106;
    if (LIBRA_PUSH_VERTEX_INSTANCE.ntsc_phase < 1.5)
    {
        _106 = (OriginalSize > 300.0) ? 2.0 : 3.0;
    }
    else
    {
        _106 = (LIBRA_PUSH_VERTEX_INSTANCE.ntsc_phase > 2.5) ? 3.0 : 2.0;
    }
    LIBRA_VARYING_2 = _106;
    if (LIBRA_PUSH_VERTEX_INSTANCE.ntsc_phase == 4.0)
    {
        LIBRA_VARYING_2 = 3.0;
    }
    else
    {
        if (LIBRA_PUSH_VERTEX_INSTANCE.ntsc_phase == 5.0)
        {
            LIBRA_VARYING_2 = 2.0;
        }
    }
    bool _135 = LIBRA_VARYING_2 == 2.0;
    bool _141;
    if (_135)
    {
        _141 = LIBRA_PUSH_VERTEX_INSTANCE.ntsc_phase != 5.0;
    }
    else
    {
        _141 = _135;
    }
    float _142;
    if (_141)
    {
        _142 = 0.83775806427001953125;
    }
    else
    {
        bool _148 = OriginalSize <= 300.0;
        bool _154;
        if (!_148)
        {
            _154 = LIBRA_VARYING_2 == 3.0;
        }
        else
        {
            _154 = _148;
        }
        _142 = _154 ? 1.0471975803375244140625 : 1.57079637050628662109375;
    }
    LIBRA_VARYING_7 = _142;
    LIBRA_VARYING_6 = LIBRA_PUSH_VERTEX_INSTANCE.cust_artifacting;
    LIBRA_VARYING_5 = LIBRA_PUSH_VERTEX_INSTANCE.cust_fringing;
    LIBRA_VARYING_4 = LIBRA_PUSH_VERTEX_INSTANCE.ntsc_sat;
    LIBRA_VARYING_3 = LIBRA_PUSH_VERTEX_INSTANCE.ntsc_bright;
    LIBRA_VARYING_8 = 0.0;
    bool _180 = LIBRA_PUSH_VERTEX_INSTANCE.ntsc_fields == (-1.0);
    bool _185;
    if (_180)
    {
        _185 = LIBRA_VARYING_2 == 3.0;
    }
    else
    {
        _185 = _180;
    }
    if (_185)
    {
        LIBRA_VARYING_8 = 1.0;
    }
    else
    {
        if (LIBRA_PUSH_VERTEX_INSTANCE.ntsc_fields == 0.0)
        {
            LIBRA_VARYING_8 = 0.0;
        }
        else
        {
            if (LIBRA_PUSH_VERTEX_INSTANCE.ntsc_fields == 1.0)
            {
                LIBRA_VARYING_8 = 1.0;
            }
        }
    }
}

