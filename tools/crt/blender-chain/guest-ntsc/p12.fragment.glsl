#version 330

layout(std140) uniform LIBRA_UBO_FRAGMENT
{
    mat4 MVP;
} LIBRA_UBO_FRAGMENT_INSTANCE;

struct LIBRA_PUSH_FRAGMENT
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

uniform LIBRA_PUSH_FRAGMENT LIBRA_PUSH_FRAGMENT_INSTANCE;

uniform sampler2D LIBRA_TEXTURE_LinearizePass;

in vec2 LIBRA_VARYING_0;
layout(location = 0) out vec4 FragColor;
float auto_rez;

float gaussian(float x, float xscale)
{
    return exp(((-x) * x) * xscale);
}

void main()
{
    float _29;
    if (LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.y < 375.0)
    {
        _29 = mix(1.0, 1.85000002384185791015625, clamp((LIBRA_PUSH_FRAGMENT_INSTANCE.auto_res * round(LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.x / 300.0)) - 1.0, 0.0, 1.0));
    }
    else
    {
        _29 = 1.0;
    }
    auto_rez = _29;
    vec2 prescalex = vec2(textureSize(LIBRA_TEXTURE_LinearizePass, 0)) / LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.xy;
    vec4 SourceSize = LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize * vec4(prescalex.x, prescalex.y, 1.0 / prescalex.x, 1.0 / prescalex.y);
    float f = fract(SourceSize.x * LIBRA_VARYING_0.x);
    f = 0.5 - f;
    vec2 tex = (floor(SourceSize.xy * LIBRA_VARYING_0) * SourceSize.zw) + (SourceSize.zw * 0.5);
    vec3 color = vec3(0.0);
    float scolor = 0.0;
    vec2 dx = vec2(SourceSize.z, 0.0);
    float w = 0.0;
    float swsum = 0.0;
    float wsum = 0.0;
    vec3 cmax = vec3(0.0);
    vec3 cmin = vec3(1.0);
    float xscale = max(prescalex.x * 0.4000000059604644775390625, 1.0) * auto_rez;
    float hsharpness = (LIBRA_PUSH_FRAGMENT_INSTANCE.HSHARPNESS * xscale) * LIBRA_PUSH_FRAGMENT_INSTANCE.filter_res;
    xscale = 1.0 / ((((((2.0 * LIBRA_PUSH_FRAGMENT_INSTANCE.SIGMA_HOR) * LIBRA_PUSH_FRAGMENT_INSTANCE.SIGMA_HOR) * xscale) * xscale) * LIBRA_PUSH_FRAGMENT_INSTANCE.filter_res) * LIBRA_PUSH_FRAGMENT_INSTANCE.filter_res);
    float param = hsharpness;
    float param_1 = xscale;
    float sharp = gaussian(param, param_1) * LIBRA_PUSH_FRAGMENT_INSTANCE.S_SHARP;
    float maxsharp = LIBRA_PUSH_FRAGMENT_INSTANCE.MAXS;
    float FPR = hsharpness;
    float FPRi = 1.0 / hsharpness;
    float fpx = 0.0;
    float sp = 0.0;
    float sw = 0.0;
    float ts = 0.02500000037252902984619140625;
    vec3 luma = vec3(0.2125999927520751953125, 0.715200006961822509765625, 0.072200000286102294921875);
    float _204 = ceil(2.0 * FPR);
    float _207 = -_204;
    float LOOPSIZE = _204;
    float n = _207;
    do
    {
        vec3 pixel = texture(LIBRA_TEXTURE_LinearizePass, tex + (dx * n)).xyz;
        float param_2 = n + f;
        float param_3 = xscale;
        w = gaussian(param_2, param_3) - sharp;
        fpx = (abs(n + f) - FPR) * FPRi;
        if (w < 0.0)
        {
            w = max(w, mix(-maxsharp, 0.0, pow(clamp(fpx, 0.0, 1.0), LIBRA_PUSH_FRAGMENT_INSTANCE.HSHARP)));
        }
        else
        {
            cmax = max(cmax, pixel);
            cmin = min(cmin, pixel);
            sw = w * (dot(pixel, luma) + ts);
            sp = max(max(pixel.x, pixel.y), pixel.z);
            scolor += (sw * sp);
            swsum += sw;
        }
        color += (pixel * w);
        wsum += w;
        n += 1.0;
    } while (n <= LOOPSIZE);
    color /= vec3(wsum);
    scolor /= swsum;
    color = clamp(mix(clamp(color, cmin, cmax), color, vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.HARNG)), vec3(0.0), vec3(1.0));
    scolor = clamp(mix(max(max(color.x, color.y), color.z), scolor, LIBRA_PUSH_FRAGMENT_INSTANCE.spike), 0.0, 1.0);
    FragColor = vec4(color, scolor);
}

