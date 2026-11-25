#version 330

layout(std140) uniform LIBRA_UBO_FRAGMENT
{
    mat4 MVP;
} LIBRA_UBO_FRAGMENT_INSTANCE;

struct LIBRA_PUSH_FRAGMENT
{
    vec4 LinearizePassSize;
    vec4 OriginalSize;
    vec4 OutputSize;
    uint FrameCount;
    float SIZEHB;
    float SIGMA_HB;
    float FINE_BLOOM;
};

uniform LIBRA_PUSH_FRAGMENT LIBRA_PUSH_FRAGMENT_INSTANCE;

uniform sampler2D LIBRA_TEXTURE_LinearizePass;

in vec2 LIBRA_VARYING_0;
layout(location = 0) out vec4 FragColor;
float FINE_BLOOM;
float invsqrsigma;

float gaussian(float x)
{
    return exp(((-x) * x) * invsqrsigma);
}

void main()
{
    float _27;
    if (LIBRA_PUSH_FRAGMENT_INSTANCE.FINE_BLOOM > 0.5)
    {
        _27 = LIBRA_PUSH_FRAGMENT_INSTANCE.FINE_BLOOM;
    }
    else
    {
        _27 = mix(0.75, 0.5, -LIBRA_PUSH_FRAGMENT_INSTANCE.FINE_BLOOM);
    }
    FINE_BLOOM = _27;
    invsqrsigma = 1.0 / ((2.0 * LIBRA_PUSH_FRAGMENT_INSTANCE.SIGMA_HB) * LIBRA_PUSH_FRAGMENT_INSTANCE.SIGMA_HB);
    vec4 SourceSize1 = LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize * vec4(FINE_BLOOM, FINE_BLOOM, 1.0 / FINE_BLOOM, 1.0 / FINE_BLOOM);
    float f = fract(SourceSize1.x * LIBRA_VARYING_0.x);
    f = 0.5 - f;
    vec2 tex = (floor(SourceSize1.xy * LIBRA_VARYING_0) * SourceSize1.zw) + (SourceSize1.zw * 0.5);
    vec4 color = vec4(0.0);
    vec2 dx = vec2(SourceSize1.z, 0.0);
    float wsum = 0.0;
    float _113 = -LIBRA_PUSH_FRAGMENT_INSTANCE.SIZEHB;
    float n = _113;
    do
    {
        vec4 pixel = texture(LIBRA_TEXTURE_LinearizePass, tex + (dx * n));
        float param = n + f;
        float w = gaussian(param);
        pixel.w = max(max(pixel.x, pixel.y), pixel.z);
        pixel.w *= (pixel.w * pixel.w);
        color += (pixel * w);
        wsum += w;
        n += 1.0;
    } while (n <= LIBRA_PUSH_FRAGMENT_INSTANCE.SIZEHB);
    color /= vec4(wsum);
    FragColor = vec4(color.xyz, pow(color.w, 0.3333329856395721435546875));
}

