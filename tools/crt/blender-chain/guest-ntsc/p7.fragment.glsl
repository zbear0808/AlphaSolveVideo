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
    float ntsc_phase;
    float auto_res;
    float ntsc_sharp;
    float ntsc_fonts;
    float ntsc_charp;
    float ntsc_charp3;
    float ntsc_shape;
    float ntsc_gamma;
    float ntsc_rainbow1;
    float speedup;
    float RFNOISE;
    float RFNOISE1;
    float RFNOISE2;
};

uniform LIBRA_PUSH_FRAGMENT LIBRA_PUSH_FRAGMENT_INSTANCE;

uniform sampler2D LIBRA_TEXTURE_Source;
uniform sampler2D LIBRA_TEXTURE_NPass1;
uniform sampler2D LIBRA_TEXTURE_PrePass0;

in vec2 LIBRA_VARYING_1;
layout(location = 0) out vec4 FragColor;
in vec2 LIBRA_VARYING_0;
in vec2 LIBRA_VARYING_2;
float auto_rez;
float RFNOISE;

vec3 yiq2rgb(vec3 yiq)
{
    return yiq * mat3(vec3(1.0, 0.95599997043609619140625, 0.620999991893768310546875), vec3(1.0, -0.272000014781951904296875, -0.64740002155303955078125), vec3(1.0, -1.10599994659423828125, 1.70459997653961181640625));
}

float smothstep(float e0, float e1, float x)
{
    return clamp((x - e0) / (e1 - e0), 0.0, 1.0);
}

vec3 rgb2yiq(vec3 col)
{
    return col * mat3(vec3(0.29890000820159912109375, 0.58700001239776611328125, 0.114000000059604644775390625), vec3(0.595899999141693115234375, -0.2743999958038330078125, -0.3215999901294708251953125), vec3(0.21150000393390655517578125, -0.52289998531341552734375, 0.311399996280670166015625));
}

vec2 psrnd(vec2 TexCoord, float FrameCount)
{
    vec3 p = vec3(TexCoord * 16758.544921875, FrameCount);
    float x = fract(sin(dot(p, vec3(12.98980045318603515625, 78.233001708984375, 3.183000087738037109375))) * 43758.546875);
    float y = fract(sin(dot(p, vec3(25.9796009063720703125, 14.11299991607666015625, 11.270999908447265625))) * 96321.9140625);
    return vec2(x, y);
}

vec3 Noise(inout vec2 TexCoord, float FrameCount)
{
    vec2 param = TexCoord;
    float param_1 = FrameCount;
    TexCoord = psrnd(param, param_1);
    vec3 p = vec3(TexCoord * 758.5452880859375, FrameCount);
    float res1 = fract(sin(dot(p, vec3(12.98983478546142578125, 78.2334136962890625, 0.16452999413013458251953125))) * 43758.546875);
    float res2 = fract(sin(dot(p, vec3(39.346790313720703125, 11.13523006439208984375, 83.155731201171875))) * 39459.32421875);
    float res3 = fract(sin(dot(p, vec3(73.15691375732421875, 52.23503875732421875, 9.15196990966796875))) * 60493.84765625);
    float lns = float(abs(res1 - 0.5) < (0.20000000298023223876953125 * RFNOISE));
    float cny = float(abs(res2 - 0.5) < (0.5 * RFNOISE));
    float cnz = float(abs(res3 - 0.5) < (0.5 * RFNOISE));
    float param_2 = 0.5 - (0.20000000298023223876953125 * RFNOISE);
    float param_3 = 0.5 + (0.20000000298023223876953125 * RFNOISE);
    float param_4 = res1;
    lns = ((lns * smothstep(param_2, param_3, param_4)) * 0.660000026226043701171875) - (0.3300000131130218505859375 * lns);
    float param_5 = 0.5 - (0.5 * RFNOISE);
    float param_6 = 0.5 + (0.5 * RFNOISE);
    float param_7 = res2;
    cny = (cny * smothstep(param_5, param_6, param_7)) - (0.5 * cny);
    float param_8 = 0.5 - (0.5 * RFNOISE);
    float param_9 = 0.5 + (0.5 * RFNOISE);
    float param_10 = res3;
    cnz = (cnz * smothstep(param_8, param_9, param_10)) - (0.5 * cnz);
    return vec3(lns, cny, cnz);
}

void main()
{
    auto_rez = mix(1.0, 0.5, clamp((LIBRA_PUSH_FRAGMENT_INSTANCE.auto_res * round(LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.x / 300.0)) - 1.0, 0.0, 1.0));
    RFNOISE = (LIBRA_PUSH_FRAGMENT_INSTANCE.RFNOISE * LIBRA_PUSH_FRAGMENT_INSTANCE.RFNOISE) + 9.9999997473787516355514526367188e-06;
    bool _279 = LIBRA_PUSH_FRAGMENT_INSTANCE.speedup > 1.25;
    bool _302;
    if (_279)
    {
        bool _286 = LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.y > 500.0;
        bool _294;
        if (_286)
        {
            _294 = LIBRA_PUSH_FRAGMENT_INSTANCE.SourceSize.y > 820.0;
        }
        else
        {
            _294 = _286;
        }
        bool _301;
        if (!_294)
        {
            _301 = LIBRA_PUSH_FRAGMENT_INSTANCE.SourceSize.y > 820.0;
        }
        else
        {
            _301 = _294;
        }
        _302 = _301;
    }
    else
    {
        _302 = _279;
    }
    if (_302)
    {
        vec3 signal = texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_1).xyz;
        signal.x = pow(signal.x, 1.0 / LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_gamma);
        vec3 param = signal;
        FragColor = vec4(clamp(yiq2rgb(param), vec3(0.0), vec3(1.0)), 1.0);
    }
    else
    {
        vec2 xx = vec2(((0.5 * LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.z) / auto_rez) / LIBRA_PUSH_FRAGMENT_INSTANCE.speedup, 0.0);
        vec2 dx = vec2(((0.0625 * LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.z) / auto_rez) / LIBRA_PUSH_FRAGMENT_INSTANCE.speedup, 0.0);
        vec2 texcoord0 = (floor(LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.xy * LIBRA_VARYING_0) + vec2(0.5)) * LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.zw;
        vec2 texcoord = LIBRA_VARYING_0 - (dx * 2.0);
        vec2 vTex = LIBRA_VARYING_0;
        if (LIBRA_PUSH_FRAGMENT_INSTANCE.speedup > 1.25)
        {
            texcoord0 = LIBRA_VARYING_2;
            texcoord = LIBRA_VARYING_1;
            vTex = LIBRA_VARYING_1;
        }
        vec3 l1 = texture(LIBRA_TEXTURE_Source, texcoord + xx).xyz;
        vec3 l2 = texture(LIBRA_TEXTURE_Source, texcoord - xx).xyz;
        float dy = 0.0;
        vec2 yy = vec2(0.0, LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.w);
        xx = vec2((LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.z / auto_rez) / LIBRA_PUSH_FRAGMENT_INSTANCE.speedup, 0.0);
        float _425;
        if (LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_phase < 1.5)
        {
            _425 = ((LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.x * auto_rez) > 300.0) ? 2.0 : 3.0;
        }
        else
        {
            _425 = (LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_phase > 2.5) ? 3.0 : 2.0;
        }
        float phase = _425;
        if (LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_phase > 3.5)
        {
            phase = 3.0;
        }
        float th = (phase < 2.5) ? 0.02500000037252902984619140625 : 0.0074999998323619365692138671875;
        float ca = texture(LIBRA_TEXTURE_NPass1, (texcoord0 - xx) - xx).w;
        float c0 = texture(LIBRA_TEXTURE_NPass1, texcoord0 - xx).w;
        float c1 = texture(LIBRA_TEXTURE_NPass1, texcoord0).w;
        float c2 = texture(LIBRA_TEXTURE_NPass1, texcoord0 + xx).w;
        float cb = texture(LIBRA_TEXTURE_NPass1, (texcoord0 + xx) + xx).w;
        float param_1 = th;
        float param_2 = 0.0;
        float param_3 = min(abs(c1 - c0), abs(c2 - c1));
        float line0 = smothstep(param_1, param_2, param_3);
        float param_4 = th;
        float param_5 = 0.0;
        float param_6 = min(abs(ca - c0), abs(c2 - cb));
        float line1 = max(smothstep(param_4, param_5, param_6), line0);
        float param_7 = th;
        float param_8 = 0.0;
        float param_9 = min(abs(ca - c2), abs(c0 - cb));
        float line2 = max(smothstep(param_7, param_8, param_9), line1);
        float diffboost = 0.0;
        if (LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_fonts > 0.25499999523162841796875)
        {
            float b1 = texture(LIBRA_TEXTURE_NPass1, texcoord0 - yy).w;
            float d1 = texture(LIBRA_TEXTURE_NPass1, texcoord0 + yy).w;
            float d2 = texture(LIBRA_TEXTURE_NPass1, (texcoord0 + xx) + yy).w;
            float maxdif = float((0.5 * (abs(c0 - c1) + abs(c1 - c2))) > (1.0 - LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_fonts));
            float param_10 = 0.100000001490116119384765625;
            float param_11 = 0.0;
            float param_12 = max(abs(c1 - b1), abs(c1 - d1));
            float linecb = smothstep(param_10, param_11, param_12);
            bool _609 = abs(c1 - b1) < 0.0500000007450580596923828125;
            bool _618;
            if (!_609)
            {
                _618 = abs(c2 - d2) < 0.0500000007450580596923828125;
            }
            else
            {
                _618 = _609;
            }
            linecb *= float(_618);
            float xdif1 = 0.0;
            float xdif2 = 0.0;
            float th_1 = 0.2150000035762786865234375;
            for (float i = 0.5; i < 10.5; i += 1.0)
            {
                float j = i + 1.0;
                ca = texture(LIBRA_TEXTURE_Source, texcoord - (xx * i)).x;
                c0 = texture(LIBRA_TEXTURE_Source, texcoord - (xx * j)).x;
                c2 = texture(LIBRA_TEXTURE_Source, texcoord + (xx * i)).x;
                cb = texture(LIBRA_TEXTURE_Source, texcoord + (xx * j)).x;
                xdif1 = max(abs(ca - c0) - th_1, xdif1);
                xdif2 = max(abs(cb - c2) - th_1, xdif2);
            }
            float param_13 = 0.0;
            float param_14 = 0.125;
            float param_15 = min(xdif1, xdif2);
            float linex = smothstep(param_13, param_14, param_15);
            diffboost = min((linex * linecb) * maxdif, 0.625);
        }
        vec3 ref = texture(LIBRA_TEXTURE_Source, texcoord).xyz;
        vec2 orig = ref.yz;
        bool _714 = LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_rainbow1 > 0.5;
        bool _727;
        if (_714)
        {
            bool _718 = phase < 2.5;
            bool _726;
            if (!_718)
            {
                _726 = LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_phase == 5.0;
            }
            else
            {
                _726 = _718;
            }
            _727 = _726;
        }
        else
        {
            _727 = _714;
        }
        if (_727)
        {
            float ybool = 1.0;
            if ((LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_rainbow1 < 1.5) && (line0 != 0.0))
            {
                ybool = 0.0;
            }
            else
            {
                if ((LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_rainbow1 < 2.5) && (line2 != 0.0))
                {
                    ybool = 0.0;
                }
            }
            float line_no = floor(mod(LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.y * LIBRA_VARYING_0.y, 2.0));
            float frame_no = floor(mod(float(LIBRA_PUSH_FRAGMENT_INSTANCE.FrameCount), 2.0));
            float ii = abs(line_no - frame_no);
            dy = (ii * LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.w) * ybool;
            vec2 ref1 = texture(LIBRA_TEXTURE_Source, texcoord - vec2(0.0, dy)).yz;
            vec2 ref2 = texture(LIBRA_TEXTURE_Source, texcoord + vec2(0.0, dy)).yz;
            vec2 rdf1 = abs(orig - ref1);
            vec2 rdf2 = abs(orig - ref2);
            rdf1 /= max(rdf1 + rdf2, vec2(1.0000000116860974230803549289703e-07));
            vec2 _813 = mix(ref1, ref2, rdf1);
            ref.y = _813.x;
            ref.z = _813.y;
        }
        float lum1 = min(texture(LIBRA_TEXTURE_NPass1, vTex - dx).w, texture(LIBRA_TEXTURE_NPass1, vTex + dx).w);
        float lum2 = ref.x;
        vec3 l3 = abs(l1 - l2);
        float dif = max(max(max(l3.x, l3.y), max(l3.z, abs((l1.x * l1.x) - (l2.x * l2.x)))), diffboost);
        float dff = pow(dif, 0.125);
        float param_16 = 0.20000000298023223876953125;
        float param_17 = 0.100000001490116119384765625;
        float param_18 = abs(lum2 - lum1);
        float lc = smothstep(param_16, param_17, param_18) * dff;
        float param_19 = 0.0500000007450580596923828125 - (0.02999999932944774627685546875 * lc);
        float param_20 = 0.425000011920928955078125 - (0.375 * lc);
        float param_21 = dif;
        float tmp = smothstep(param_19, param_20, param_21);
        float tmp1 = pow((tmp + 0.100000001490116119384765625) / 1.10000002384185791015625, 0.25);
        float sweight = mix(tmp, tmp1, line0);
        float sweighr = mix(tmp, tmp1, line2);
        vec3 signal_1 = ref;
        float ntsc_sharp = abs(LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_sharp);
        if (ntsc_sharp > 0.25)
        {
            float mixer = sweight;
            if (LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_sharp > 0.25)
            {
                mixer = sweighr;
            }
            mixer *= (0.100000001490116119384765625 * ntsc_sharp);
            float lummix = mix(lum2, lum1, mixer);
            float lm1 = mix(lum2 * lum2, lum1 * lum1, mixer);
            lm1 = sqrt(lm1);
            float lm2 = mix(sqrt(lum2), sqrt(lum1), mixer);
            lm2 *= lm2;
            float k1 = abs(lummix - lm1) + 9.9999997473787516355514526367188e-06;
            float k2 = abs(lummix - lm2) + 9.9999997473787516355514526367188e-06;
            signal_1.x = min(((k2 * lm1) + (k1 * lm2)) / (k1 + k2), 1.0);
            signal_1.x = min(signal_1.x, max(LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_shape * signal_1.x, lum2));
        }
        if ((LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_charp + LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_charp3) > 0.25)
        {
            dx.x = (0.0625 * LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.z) / auto_rez;
            float texcoordx = (LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.x * (LIBRA_VARYING_0.x + dx.x)) - 0.5;
            float fpx = fract(texcoordx);
            texcoordx = (floor(texcoordx) + 0.5) * LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.z;
            float mixer_1 = sweight;
            if (LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_sharp > 0.25)
            {
                mixer_1 = sweighr;
            }
            float param_22 = 0.07500000298023223876953125;
            float param_23 = 0.125;
            float param_24 = max(l3.y, l3.z);
            float param_25 = 0.014999999664723873138427734375;
            float param_26 = 0.0274999998509883880615234375;
            float param_27 = dif;
            mixer_1 = mix(smothstep(param_22, param_23, param_24), smothstep(param_25, param_26, param_27), line2) * mixer_1;
            float _1062;
            if (phase < 2.5)
            {
                _1062 = LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_charp;
            }
            else
            {
                _1062 = LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_charp3;
            }
            mixer_1 *= (0.100000001490116119384765625 * _1062);
            texcoord = vec2(texcoordx, texcoord.y);
            vec3 param_28 = mix(texture(LIBRA_TEXTURE_PrePass0, texcoord).xyz, texture(LIBRA_TEXTURE_PrePass0, texcoord + (dx * 16.0)).xyz, vec3(clamp((1.5 * fpx) - 0.25, 0.0, 1.0)));
            vec3 orig_ch = rgb2yiq(param_28);
            vec3 _1100 = signal_1;
            vec2 _1106 = mix(_1100.yz, orig_ch.yz, vec2(mixer_1));
            signal_1.y = _1106.x;
            signal_1.z = _1106.y;
        }
        if ((LIBRA_PUSH_FRAGMENT_INSTANCE.RFNOISE1 + LIBRA_PUSH_FRAGMENT_INSTANCE.RFNOISE2) > 0.004999999888241291046142578125)
        {
            vec2 param_29 = LIBRA_VARYING_0;
            float param_30 = float(LIBRA_PUSH_FRAGMENT_INSTANCE.FrameCount);
            vec3 _1129 = Noise(param_29, param_30);
            vec3 ns = _1129;
            float Y = mix(0.375, 1.0, pow(signal_1.x, 0.20000000298023223876953125));
            signal_1.x = clamp(signal_1.x + (LIBRA_PUSH_FRAGMENT_INSTANCE.RFNOISE1 * ns.x), 0.0, 1.0);
            signal_1.y = clamp(signal_1.y + (((Y * LIBRA_PUSH_FRAGMENT_INSTANCE.RFNOISE2) * (0.324999988079071044921875 + (1.3250000476837158203125 * abs(signal_1.y)))) * ns.y), -0.60000002384185791015625, 0.60000002384185791015625);
            signal_1.z = clamp(signal_1.z + (((Y * LIBRA_PUSH_FRAGMENT_INSTANCE.RFNOISE2) * (0.324999988079071044921875 + (1.3250000476837158203125 * abs(signal_1.z)))) * ns.z), -0.5299999713897705078125, 0.5299999713897705078125);
        }
        signal_1.x = pow(signal_1.x, 1.0 / LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_gamma);
        vec3 param_31 = signal_1;
        signal_1 = clamp(yiq2rgb(param_31), vec3(0.0), vec3(1.0));
        bool _1201 = phase == 2.0;
        bool _1208;
        if (!_1201)
        {
            _1208 = LIBRA_PUSH_FRAGMENT_INSTANCE.ntsc_phase > 3.5;
        }
        else
        {
            _1208 = _1201;
        }
        sweighr = _1208 ? sweighr : 1.0;
        FragColor = vec4(signal_1, sweighr);
    }
}

