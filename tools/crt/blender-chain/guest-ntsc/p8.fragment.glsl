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
    float CSHARPEN;
    float CCONTR;
    float CDETAILS;
    float NDEBLUR;
    float DEDGE;
    float DESHARP;
    float DSMART;
};

uniform LIBRA_PUSH_FRAGMENT LIBRA_PUSH_FRAGMENT_INSTANCE;

uniform sampler2D LIBRA_TEXTURE_Source;
uniform sampler2D LIBRA_TEXTURE_PrePass0;

in vec2 LIBRA_VARYING_0;
layout(location = 0) out vec4 FragColor;
float resmult;

float get_luma(vec3 c)
{
    return dot(c, vec3(0.2989999949932098388671875, 0.58700001239776611328125, 0.114000000059604644775390625));
}

vec3 rgb2yiq(vec3 col)
{
    return col * mat3(vec3(0.29890000820159912109375, 0.58700001239776611328125, 0.114000000059604644775390625), vec3(0.595899999141693115234375, -0.2743999958038330078125, -0.3215999901294708251953125), vec3(0.21150000393390655517578125, -0.52289998531341552734375, 0.311399996280670166015625));
}

vec3 yiq2rgb(vec3 yiq)
{
    return yiq * mat3(vec3(1.0, 0.95599997043609619140625, 0.620999991893768310546875), vec3(1.0, -0.272000014781951904296875, -0.64740002155303955078125), vec3(1.0, -1.10599994659423828125, 1.70459997653961181640625));
}

void main()
{
    resmult = round(LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.x / 300.0);
    vec2 g01 = vec2(((-0.5) * resmult) * LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.z, 0.0);
    vec2 g21 = vec2((0.5 * resmult) * LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.z, 0.0);
    vec3 c01 = texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0 + g01).xyz;
    vec3 c21 = texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0 + g21).xyz;
    vec3 c11 = texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0).xyz;
    vec3 b11 = (c01 + c21) * 0.5;
    float contrast = max(max(c11.x, c11.y), c11.z);
    contrast = mix(2.0 * LIBRA_PUSH_FRAGMENT_INSTANCE.CCONTR, LIBRA_PUSH_FRAGMENT_INSTANCE.CCONTR, contrast);
    vec3 mn = min(min(c01, c21), c11);
    vec3 mn1 = min(mn, c11 * (1.0 - contrast));
    vec3 mx = max(max(c01, c21), c11);
    vec3 mx1 = max(mx, c11 * (1.0 + contrast));
    vec3 dif = pow((mx1 - mn1) + vec3(9.9999997473787516355514526367188e-06), vec3(0.75));
    vec3 sharpen = mix(vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.CSHARPEN * LIBRA_PUSH_FRAGMENT_INSTANCE.CDETAILS), vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.CSHARPEN), dif);
    vec3 res = clamp(mix(c11, b11, -sharpen), mn1, mx1);
    if (LIBRA_PUSH_FRAGMENT_INSTANCE.NDEBLUR > 1.125)
    {
        vec2 tex0 = (floor(LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.xy * LIBRA_VARYING_0) + vec2(0.5)) * LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.zw;
        vec3 param = texture(LIBRA_TEXTURE_PrePass0, LIBRA_VARYING_0 + (g01 * 2.0)).xyz;
        float l01 = get_luma(param);
        vec3 param_1 = texture(LIBRA_TEXTURE_PrePass0, LIBRA_VARYING_0 + (g21 * 2.0)).xyz;
        float l21 = get_luma(param_1);
        vec3 param_2 = texture(LIBRA_TEXTURE_PrePass0, tex0).xyz;
        float l11 = get_luma(param_2);
        float dth = texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0).w;
        float DEB = max(mix(0.375 * LIBRA_PUSH_FRAGMENT_INSTANCE.NDEBLUR, LIBRA_PUSH_FRAGMENT_INSTANCE.NDEBLUR, max(1.0 - LIBRA_PUSH_FRAGMENT_INSTANCE.DSMART, dth)), 1.0);
        float v11 = min(min(l01, l21), l11);
        l11 = max(max(l01, l21), l11);
        vec3 param_3 = c01;
        vec3 param_4 = c21;
        vec3 param_5 = c11;
        float lmin = min(min(get_luma(param_3), get_luma(param_4)), get_luma(param_5));
        vec3 param_6 = c01;
        vec3 param_7 = c21;
        vec3 param_8 = c11;
        float lmax = max(max(get_luma(param_6), get_luma(param_7)), get_luma(param_8));
        float ln1 = min(mix(v11, lmin, lmin), lmin);
        float lx1 = max(mix(lmax, l11, lmax), lmax);
        vec3 param_9 = res;
        float r11 = get_luma(param_9);
        float dif1 = max(r11 - ln1, 0.0) + 9.9999997473787516355514526367188e-06;
        dif1 = pow(dif1, DEB);
        float dif2 = max(lx1 - r11, 0.0) + 9.9999997473787516355514526367188e-06;
        dif2 = pow(dif2, DEB);
        float ratio = dif1 / (dif1 + dif2);
        float lsharpen = mix(ln1, lx1, ratio);
        lsharpen = min(lsharpen, max(LIBRA_PUSH_FRAGMENT_INSTANCE.DEDGE * lsharpen, r11));
        vec3 param_10 = res;
        res = rgb2yiq(param_10);
        v11 = res.x;
        res.x = lsharpen;
        res.x = clamp(((1.0 + LIBRA_PUSH_FRAGMENT_INSTANCE.DESHARP) * res.x) - (LIBRA_PUSH_FRAGMENT_INSTANCE.DESHARP * v11), ln1 * (1.0 - contrast), lx1 * (1.0 + contrast));
        vec3 param_11 = res;
        res = max(yiq2rgb(param_11), vec3(0.0));
    }
    FragColor = vec4(res, 1.0);
}

