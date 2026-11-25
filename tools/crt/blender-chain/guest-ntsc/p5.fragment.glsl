#version 330

layout(std140) uniform LIBRA_UBO_FRAGMENT
{
    mat4 MVP;
} LIBRA_UBO_FRAGMENT_INSTANCE;

struct LIBRA_PUSH_FRAGMENT
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

uniform LIBRA_PUSH_FRAGMENT LIBRA_PUSH_FRAGMENT_INSTANCE;

uniform sampler2D LIBRA_TEXTURE_Source;

in float LIBRA_VARYING_3;
in float LIBRA_VARYING_5;
in float LIBRA_VARYING_6;
in float LIBRA_VARYING_4;
in vec2 LIBRA_VARYING_0;
layout(location = 0) out vec4 FragColor;
in float LIBRA_VARYING_2;
in float LIBRA_VARYING_8;
in vec2 LIBRA_VARYING_1;
in float LIBRA_VARYING_7;
float FrameCount;
float auto_rez;
mat3 mix_mat;

float smothstep(float e0, float e1, float x)
{
    return clamp((x - e0) / (e1 - e0), 0.0, 1.0);
}

vec3 rgb2yiq(vec3 col)
{
    return col * mat3(vec3(0.29890000820159912109375, 0.58700001239776611328125, 0.114000000059604644775390625), vec3(0.595899999141693115234375, -0.2743999958038330078125, -0.3215999901294708251953125), vec3(0.21150000393390655517578125, -0.52289998531341552734375, 0.311399996280670166015625));
}

float get_luma(vec3 c)
{
    return dot(c, vec3(0.29890000820159912109375, 0.58700001239776611328125, 0.114000000059604644775390625));
}

void main()
{
    FrameCount = float(LIBRA_PUSH_FRAGMENT_INSTANCE.FrameCount);
    auto_rez = mix(1.0, 0.5, clamp((LIBRA_PUSH_FRAGMENT_INSTANCE.auto_res * round(LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.x / 300.0)) - 1.0, 0.0, 1.0));
    mix_mat = mat3(vec3(LIBRA_VARYING_3, LIBRA_VARYING_5, LIBRA_VARYING_5), vec3(LIBRA_VARYING_6, 2.0 * LIBRA_VARYING_4, 0.0), vec3(LIBRA_VARYING_6, 0.0, 2.0 * LIBRA_VARYING_4));
    if (LIBRA_VARYING_0.x > 1.0)
    {
        FragColor = vec4(0.0);
    }
    else
    {
        float res = LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_scale * auto_rez;
        float mit = LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_taps;
        bool _135 = LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_charp > 0.25;
        bool _141;
        if (_135)
        {
            _141 = LIBRA_VARYING_2 == 2.0;
        }
        else
        {
            _141 = _135;
        }
        if (_141)
        {
            mit = clamp(mit, 8.0, min(LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_taps, 14.0));
        }
        float param = 16.0;
        float param_1 = 8.0;
        float param_2 = mit;
        mit = smothstep(param, param_1, param_2) * 0.324999988079071044921875;
        vec3 col = texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0).xyz;
        vec3 param_3 = col;
        vec3 yiq = rgb2yiq(param_3);
        yiq.x = pow(yiq.x, LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_gamma);
        float lum = yiq.x;
        if (LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_phase == 4.0)
        {
            vec2 dx = vec2(LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.z / auto_rez, 0.0);
            vec3 param_4 = texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0 - dx).xyz;
            float c1 = get_luma(param_4);
            vec3 param_5 = texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0 + dx).xyz;
            float c2 = get_luma(param_5);
            float mix01 = min(5.0 * abs(c1 - c2), 1.0);
            c1 = pow(c1, LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_gamma);
            c2 = pow(c2, LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_gamma);
            yiq.x = mix(min(0.5 * (yiq.x + max(c1, c2)), max(yiq.x, min(c1, c2))), yiq.x, mix01);
        }
        vec3 tmp = yiq;
        vec3 yiq2 = yiq;
        vec3 yiqs = yiq;
        vec3 yiqz = yiq;
        if (LIBRA_VARYING_8 > 0.5)
        {
            float _267;
            if (LIBRA_VARYING_2 < 2.5)
            {
                _267 = 3.1415927410125732421875 * (mod(LIBRA_VARYING_1.y, 2.0) + mod(FrameCount + 1.0, 2.0));
            }
            else
            {
                _267 = 2.0944998264312744140625 * (mod(LIBRA_VARYING_1.y, 3.0) + mod(FrameCount + 1.0, 2.0));
            }
            float chroma_phase2 = _267;
            float mod_phase2 = chroma_phase2 + (LIBRA_VARYING_1.x * LIBRA_VARYING_7);
            float i_mod2 = cos(mod_phase2);
            float q_mod2 = sin(mod_phase2);
            vec3 _310 = yiq2;
            vec2 _312 = _310.yz * vec2(i_mod2, q_mod2);
            yiq2.y = _312.x;
            yiq2.z = _312.y;
            yiq2 *= mix_mat;
            vec3 _323 = yiq2;
            vec2 _325 = _323.yz * vec2(i_mod2, q_mod2);
            yiq2.y = _325.x;
            yiq2.z = _325.y;
            vec3 _330 = yiq2;
            vec2 _336 = mix(_330.yz, tmp.yz, vec2(mit));
            yiq2.y = _336.x;
            yiq2.z = _336.y;
            if (res > 1.02499997615814208984375)
            {
                mod_phase2 = chroma_phase2 + ((LIBRA_VARYING_1.x * LIBRA_VARYING_7) * res);
                i_mod2 = cos(mod_phase2);
                q_mod2 = sin(mod_phase2);
                vec3 _361 = yiqs;
                vec2 _363 = _361.yz * vec2(i_mod2, q_mod2);
                yiqs.y = _363.x;
                yiqs.z = _363.y;
                yiq2.x = dot(yiqs, mix_mat[0]);
            }
        }
        float _378;
        if (LIBRA_VARYING_2 < 2.5)
        {
            _378 = 3.1415927410125732421875 * (mod(LIBRA_VARYING_1.y, 2.0) + mod(FrameCount, 2.0));
        }
        else
        {
            _378 = 2.0944998264312744140625 * (mod(LIBRA_VARYING_1.y, 3.0) + mod(FrameCount, 2.0));
        }
        float chroma_phase = _378;
        float mod_phase = chroma_phase + (LIBRA_VARYING_1.x * LIBRA_VARYING_7);
        float i_mod = cos(mod_phase);
        float q_mod = sin(mod_phase);
        vec3 _413 = yiq;
        vec2 _415 = _413.yz * vec2(i_mod, q_mod);
        yiq.y = _415.x;
        yiq.z = _415.y;
        yiq *= mix_mat;
        vec3 _426 = yiq;
        vec2 _428 = _426.yz * vec2(i_mod, q_mod);
        yiq.y = _428.x;
        yiq.z = _428.y;
        vec3 _433 = yiq;
        vec2 _439 = mix(_433.yz, tmp.yz, vec2(mit));
        yiq.y = _439.x;
        yiq.z = _439.y;
        if (res > 1.02499997615814208984375)
        {
            mod_phase = chroma_phase + ((LIBRA_VARYING_1.x * LIBRA_VARYING_7) * res);
            i_mod = cos(mod_phase);
            q_mod = sin(mod_phase);
            vec3 _463 = yiqz;
            vec2 _465 = _463.yz * vec2(i_mod, q_mod);
            yiqz.y = _465.x;
            yiqz.z = _465.y;
            yiq.x = dot(yiqz, mix_mat[0]);
        }
        if (LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_phase == 4.0)
        {
            yiq.x = lum;
            yiq2.x = lum;
        }
        if (LIBRA_VARYING_8 > 0.5)
        {
            bool _491 = LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_rainbow1 < 0.5;
            bool _497;
            if (!_491)
            {
                _497 = LIBRA_VARYING_2 > 2.5;
            }
            else
            {
                _497 = _491;
            }
            if (_497)
            {
                yiq = (yiq + yiq2) * 0.5;
            }
            else
            {
                yiq.x = 0.5 * (yiq.x + yiq2.x);
            }
        }
        FragColor = vec4(yiq, lum);
    }
}

