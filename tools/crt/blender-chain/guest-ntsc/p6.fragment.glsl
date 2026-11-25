#version 330

const float _262[33] = float[](-0.0001748439972288906574249267578125, -0.0002058440004475414752960205078125, -0.0001494530006311833858489990234375, -5.16930012963712215423583984375e-05, 0.0, -6.6171000071335583925247192382812e-05, -0.00024505800683982670307159423828125, -0.00043292800546623766422271728515625, -0.000472643994726240634918212890625, -0.00025223600096069276332855224609375, 0.00019892900309059768915176391601562, 0.0006870580255053937435150146484375, 0.0009441120200790464878082275390625, 0.000803467002697288990020751953125, 0.00036319901118986308574676513671875, 1.3421999938145745545625686645508e-05, 0.0002534019877202808856964111328125, 0.00133946095593273639678955078125, 0.00293297204189002513885498046875, 0.0039834850467741489410400390625, 0.00302668311633169651031494140625, -0.001102056005038321018218994140625, -0.0083730258047580718994140625, -0.016897700726985931396484375, -0.0229144804179668426513671875, -0.02164234779775142669677734375, -0.028863273561000823974609375, 0.0272719562053680419921875, 0.0549219213426113128662109375, 0.09834258258342742919921875, 0.139044284820556640625, 0.168055832386016845703125, 0.1785714328289031982421875);
const float _499[33] = float[](0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -0.00011884699779329821467399597167969, -0.00027130599482916295528411865234375, -0.00050264201126992702484130859375, -0.0009308329899795353412628173828125, -0.001451013027690351009368896484375, -0.00206474401056766510009765625, -0.00270043197087943553924560546875, -0.0032412759028375148773193359375, -0.0035249479115009307861328125, -0.0033502839505672454833984375, -0.00249172910116612911224365234375, -0.0007211489719338715076446533203125, 0.002164659090340137481689453125, 0.00631363503634929656982421875, 0.011789103038609027862548828125, 0.01854565925896167755126953125, 0.02641439624130725860595703125, 0.0351007096469402313232421875, 0.044196568429470062255859375, 0.05320720374584197998046875, 0.061590276658535003662109375, 0.068803600966930389404296875, 0.074356190860271453857421875, 0.077856563031673431396484375, 0.079052396118640899658203125);

layout(std140) uniform LIBRA_UBO_FRAGMENT
{
    mat4 MVP;
} LIBRA_UBO_FRAGMENT_INSTANCE;

struct LIBRA_PUSH_FRAGMENT
{
    vec4 OutputSize;
    vec4 OriginalSize;
    vec4 SourceSize;
    float ntsc_scale;
    float ntsc_phase;
    float ntsc_ring;
    float ntsc_cscale;
    float ntsc_cscale1;
    float ntsc_taps;
    float auto_res;
    float ntsc_charp;
    float ntsc_charp3;
    float speedup;
    float nscale;
};

uniform LIBRA_PUSH_FRAGMENT LIBRA_PUSH_FRAGMENT_INSTANCE;

uniform sampler2D LIBRA_TEXTURE_Source;
uniform sampler2D LIBRA_TEXTURE_PrePass0;

in vec2 LIBRA_VARYING_0;
layout(location = 0) out vec4 FragColor;
float auto_rez;

float smothstep(float e0, float e1, float x)
{
    return clamp((x - e0) / (e1 - e0), 0.0, 1.0);
}

vec3 fetch_offset2(vec2 dx)
{
    return texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0 + dx).xyz + texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0 - dx).xyz;
}

vec3 fetch_offset3(vec3 dx)
{
    return vec3(texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0 + dx.xz).x + texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0 - dx.xz).x, texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0 + dx.yz).yz + texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0 - dx.yz).yz);
}

float get_luma(vec3 c)
{
    return dot(c, vec3(0.29890000820159912109375, 0.58700001239776611328125, 0.114000000059604644775390625));
}

void main()
{
    auto_rez = mix(1.0, 0.5, clamp((LIBRA_PUSH_FRAGMENT_INSTANCE.auto_res * round(LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.x / 300.0)) - 1.0, 0.0, 1.0));
    if ((LIBRA_VARYING_0.x * LIBRA_PUSH_FRAGMENT_INSTANCE.speedup) > 1.00325000286102294921875)
    {
        discard;
    }
    float luma_filter_3_phase[33] = float[](0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1.2020000212942250072956085205078e-05, -2.2145999537315219640731811523438e-05, -1.315499957854626700282096862793e-05, -1.2020000212942250072956085205078e-05, -4.9979000323219224810600280761719e-05, -0.00011393999739084392786026000976562, -0.0001221499987877905368804931640625, -5.6120002227544318884611129760742e-06, 0.00017051599570550024509429931640625, 0.00023719899763818830251693725585938, 0.0001696399995125830173492431640625, 0.00028568800189532339572906494140625, 0.00098457396961748600006103515625, 0.00201868289150297641754150390625, 0.0020022750832140445709228515625, -0.0059098820202052593231201171875, -0.01204908080399036407470703125, -0.01822285912930965423583984375, -0.022606931626796722412109375, 0.00246085994876921176910400390625, 0.0358682237565517425537109375, 0.084016449749469757080078125, 0.13556349277496337890625, 0.17526127398014068603515625, 0.2201765477657318115234375);
    float res = (LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_scale * auto_rez) * LIBRA_PUSH_FRAGMENT_INSTANCE.nscale;
    float OriginalSize = LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.x * auto_rez;
    vec2 one_x = ((LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.zz * 0.25) / vec2(res)) / vec2(LIBRA_PUSH_FRAGMENT_INSTANCE.speedup);
    vec3 signal = vec3(0.0);
    float _209;
    if (LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_phase < 1.5)
    {
        _209 = (OriginalSize > 300.0) ? 2.0 : 3.0;
    }
    else
    {
        _209 = (LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_phase > 2.5) ? 3.0 : 2.0;
    }
    float phase = _209;
    if (LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_phase > 3.5)
    {
        phase = 3.0;
        luma_filter_3_phase = _262;
    }
    float offset = 0.0;
    int i = 0;
    float j = 0.0;
    vec3 wsum = vec3(0.0);
    vec3 sums = wsum;
    vec3 tmp = wsum;
    if (phase < 2.5)
    {
        float iloop = max(LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_taps, 8.0);
        if (LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_charp > 0.25)
        {
            iloop = min(iloop, 14.0);
        }
        int loopstart = int(32.0 - iloop);
        float ltap = iloop + 1.0;
        float cs_sub = iloop - (iloop / LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_cscale);
        float ctap = 0.0;
        float param = 16.0;
        float param_1 = 8.0;
        float param_2 = iloop;
        float mit = 1.0 + (0.039999999105930328369140625 * pow(smothstep(param, param_1, param_2), 0.5));
        vec2 dx = vec2(one_x.x * mit, 0.0);
        vec2 dx1 = dx;
        i = loopstart;
        for (; i < 32; i++)
        {
            offset = float(i - loopstart);
            j = offset + 1.0;
            dx1 = dx * (offset - iloop);
            vec2 param_3 = dx1;
            sums = fetch_offset2(param_3);
            ctap = max(j - cs_sub, 0.0);
            tmp = vec3(_262[max(i, 0)], vec2(ctap));
            wsum += tmp;
            signal += (sums * tmp);
        }
        ctap = ltap - cs_sub;
        tmp = vec3(0.1785714328289031982421875, vec2(ctap));
        wsum = (wsum + wsum) + tmp;
        signal += (texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0).xyz * tmp);
        signal /= wsum;
    }
    else
    {
        one_x.y /= LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_cscale1;
        vec3 dx_1 = vec3(one_x.x, one_x.y, 0.0);
        float mit_1 = 1.0;
        float iloop_1 = min(LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_taps, 24.0);
        if (LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_phase > 3.5)
        {
            iloop_1 = max(iloop_1, 8.0);
            float param_4 = 16.0;
            float param_5 = 8.0;
            float param_6 = iloop_1;
            mit_1 = 1.0 + (0.039999999105930328369140625 * pow(smothstep(param_4, param_5, param_6), 0.5));
        }
        vec3 dx1_1 = dx_1;
        dx_1.x *= mit_1;
        int loopstart_1 = int(32.0 - iloop_1);
        i = loopstart_1;
        for (; i < 32; i++)
        {
            offset = float(i - loopstart_1);
            vec2 _463 = dx_1.xy * (offset - iloop_1);
            dx1_1.x = _463.x;
            dx1_1.y = _463.y;
            vec3 param_7 = dx1_1;
            sums = fetch_offset3(param_7);
            tmp = vec3(luma_filter_3_phase[i], vec2(_499[i]));
            wsum += tmp;
            signal += (sums * tmp);
        }
        tmp = vec3(luma_filter_3_phase[32], 0.079052396118640899658203125, 0.079052396118640899658203125);
        wsum = (wsum + wsum) + tmp;
        signal += (texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0).xyz * tmp);
        signal /= wsum;
    }
    signal.x = clamp(signal.x, 0.0, 1.0);
    if (LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_ring > 0.0500000007450580596923828125)
    {
        vec2 dx_2 = vec2((LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.z / min(res, 1.0)) / LIBRA_PUSH_FRAGMENT_INSTANCE.speedup, 0.0);
        float a = texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0 - (dx_2 * 2.0)).w;
        float b = texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0 - dx_2).w;
        float c = texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0 + (dx_2 * 2.0)).w;
        float d = texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0 + dx_2).w;
        float e = texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0).w;
        signal.x = mix(signal.x, clamp(signal.x, min(min(min(a, b), min(c, d)), e), max(max(max(a, b), max(c, d)), e)), LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_ring);
    }
    vec3 param_8 = texture(LIBRA_TEXTURE_PrePass0, LIBRA_VARYING_0 * vec2(LIBRA_PUSH_FRAGMENT_INSTANCE.speedup, 1.0)).xyz;
    float orig = get_luma(param_8);
    FragColor = vec4(signal, orig);
}

