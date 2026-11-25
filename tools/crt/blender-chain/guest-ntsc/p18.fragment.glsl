#version 330

const float _1840[15] = float[](2.0, 3.0, 3.0, 6.0, 6.0, 2.400000095367431640625, 3.400000095367431640625, 2.400000095367431640625, 3.25, 3.400000095367431640625, 4.400000095367431640625, 4.25, 7.400000095367431640625, 6.25, 5.25);

layout(std140) uniform LIBRA_UBO_FRAGMENT
{
    mat4 MVP;
    vec4 SourceSize;
    vec4 OriginalSize;
    vec4 OutputSize;
    uint FrameCount;
    float bloom;
    float halation;
    float slotms;
    float mask_gamma;
    float gamma_out;
    float overscanX;
    float overscanY;
    float VShift;
    float intres;
    float c_shape;
    float barspeed;
    float barintensity;
    float bardir;
    float sborder;
    float bloom_dist;
    float deconr;
    float decons;
    float addnoised;
    float noiseresd;
    float noisetype;
    float deconrr;
    float deconrg;
    float deconrb;
    float deconrry;
    float deconrgy;
    float deconrby;
    float dctypex;
    float dctypey;
    float post_br;
    float maskboost;
    float smoothmask;
    float gamma_c;
    float gamma_c2;
    float m_glow;
    float m_glow_low;
    float m_glow_high;
    float m_glow_dist;
    float m_glow_mask;
    float smask_mit;
    float mask_zoom;
    float no_scanlines;
    float bmask;
    float bmask1;
    float hmask1;
    float mzoom_sh;
    float mclip;
    float edgemask;
    float oimage;
    float interm;
} LIBRA_UBO_FRAGMENT_INSTANCE;

struct LIBRA_PUSH_FRAGMENT
{
    float IOS;
    float OS;
    float BLOOM;
    float brightboost;
    float brightboost1;
    float csize;
    float bsize1;
    float warpX;
    float warpY;
    float glow;
    float shadowMask;
    float masksize;
    float slotmask;
    float slotmask1;
    float slotwidth;
    float double_slot;
    float mcut;
    float maskDark;
    float maskLight;
    float maskstr;
    float mshift;
    float mask_layout;
    float mask_bloom;
    float hiscan;
    float pr_scan;
};

uniform LIBRA_PUSH_FRAGMENT LIBRA_PUSH_FRAGMENT_INSTANCE;

uniform sampler2D LIBRA_TEXTURE_Source;
uniform sampler2D LIBRA_TEXTURE_BloomPass;
uniform sampler2D LIBRA_TEXTURE_GlowPass;
uniform sampler2D LIBRA_TEXTURE_AvgLumPass;
uniform sampler2D LIBRA_TEXTURE_LinearizePass;
uniform sampler2D LIBRA_TEXTURE_PrePass0;
uniform sampler2D LIBRA_TEXTURE_StockPass;

in vec2 LIBRA_VARYING_0;
layout(location = 0) out vec4 FragColor;

vec2 Overscan(inout vec2 pos, float dx, float dy)
{
    pos = (pos * 2.0) - vec2(1.0);
    pos *= vec2(dx, dy);
    return (pos * 0.5) + vec2(0.5);
}

vec2 Warp(inout vec2 pos)
{
    pos = (pos * 2.0) - vec2(1.0);
    pos = mix(pos, vec2(pos.x * inversesqrt(1.0 - ((LIBRA_UBO_FRAGMENT_INSTANCE.c_shape * pos.y) * pos.y)), pos.y * inversesqrt(1.0 - ((LIBRA_UBO_FRAGMENT_INSTANCE.c_shape * pos.x) * pos.x))), vec2(LIBRA_PUSH_FRAGMENT_INSTANCE.warpX, LIBRA_PUSH_FRAGMENT_INSTANCE.warpY) / vec2(LIBRA_UBO_FRAGMENT_INSTANCE.c_shape));
    return (pos * 0.5) + vec2(0.5);
}

void fetch_pixel(inout vec3 c, inout vec3 b, inout vec3 g, vec2 coord, vec2 bcoord)
{
    float stepx = LIBRA_UBO_FRAGMENT_INSTANCE.OutputSize.z;
    float stepy = LIBRA_UBO_FRAGMENT_INSTANCE.OutputSize.w;
    float ds = LIBRA_UBO_FRAGMENT_INSTANCE.decons;
    vec2 dx = vec2(stepx, 0.0);
    vec2 dy = vec2(0.0, stepy);
    float posx = (2.0 * coord.x) - 1.0;
    float posy = (2.0 * coord.y) - 1.0;
    if (LIBRA_UBO_FRAGMENT_INSTANCE.dctypex > 0.02500000037252902984619140625)
    {
        posx = sign(posx) * pow(abs(posx), 1.0499999523162841796875 - LIBRA_UBO_FRAGMENT_INSTANCE.dctypex);
        dx *= posx;
    }
    if (LIBRA_UBO_FRAGMENT_INSTANCE.dctypey > 0.02500000037252902984619140625)
    {
        posy = sign(posy) * pow(abs(posy), 1.0499999523162841796875 - LIBRA_UBO_FRAGMENT_INSTANCE.dctypey);
        dy *= posy;
    }
    vec2 rc = (dx * LIBRA_UBO_FRAGMENT_INSTANCE.deconrr) + (dy * LIBRA_UBO_FRAGMENT_INSTANCE.deconrry);
    vec2 gc = (dx * LIBRA_UBO_FRAGMENT_INSTANCE.deconrg) + (dy * LIBRA_UBO_FRAGMENT_INSTANCE.deconrgy);
    vec2 bc = (dx * LIBRA_UBO_FRAGMENT_INSTANCE.deconrb) + (dy * LIBRA_UBO_FRAGMENT_INSTANCE.deconrby);
    float r1 = texture(LIBRA_TEXTURE_Source, coord + rc).x;
    float g1 = texture(LIBRA_TEXTURE_Source, coord + gc).y;
    float b1 = texture(LIBRA_TEXTURE_Source, coord + bc).z;
    vec3 d = vec3(r1, g1, b1);
    c = clamp(mix(c, d, vec3(ds)), vec3(0.0), vec3(1.0));
    r1 = texture(LIBRA_TEXTURE_BloomPass, bcoord + rc).x;
    g1 = texture(LIBRA_TEXTURE_BloomPass, bcoord + gc).y;
    b1 = texture(LIBRA_TEXTURE_BloomPass, bcoord + bc).z;
    d = vec3(r1, g1, b1);
    vec3 _1423 = mix(b, d, vec3(min(ds, 1.0)));
    g = _1423;
    b = _1423;
    r1 = texture(LIBRA_TEXTURE_GlowPass, bcoord + rc).x;
    g1 = texture(LIBRA_TEXTURE_GlowPass, bcoord + gc).y;
    b1 = texture(LIBRA_TEXTURE_GlowPass, bcoord + bc).z;
    d = vec3(r1, g1, b1);
    g = mix(g, d, vec3(min(ds, 1.0)));
}

float igc(float mc)
{
    return pow(mc, LIBRA_UBO_FRAGMENT_INSTANCE.gamma_c);
}

vec3 Mask(inout vec2 pos, float mx, float mb)
{
    vec3 mask = vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.maskDark, LIBRA_PUSH_FRAGMENT_INSTANCE.maskDark, LIBRA_PUSH_FRAGMENT_INSTANCE.maskDark);
    vec3 one = vec3(1.0);
    if (LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask == 0.0)
    {
        float mc = 1.0 - max(LIBRA_PUSH_FRAGMENT_INSTANCE.maskstr, 0.0);
        pos.x = fract(pos.x * 0.5);
        if (pos.x < 0.4900000095367431640625)
        {
            mask.x = 1.0;
            mask.y = mc;
            mask.z = 1.0;
        }
        else
        {
            mask.x = mc;
            mask.y = 1.0;
            mask.z = mc;
        }
    }
    else
    {
        if (LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask == 1.0)
        {
            float line = LIBRA_PUSH_FRAGMENT_INSTANCE.maskLight;
            float odd = 0.0;
            if (fract(pos.x / 6.0) < 0.4900000095367431640625)
            {
                odd = 1.0;
            }
            if (fract((pos.y + odd) / 2.0) < 0.4900000095367431640625)
            {
                line = LIBRA_PUSH_FRAGMENT_INSTANCE.maskDark;
            }
            pos.x = floor(mod(pos.x, 3.0));
            if (pos.x < 0.5)
            {
                mask.x = LIBRA_PUSH_FRAGMENT_INSTANCE.maskLight;
            }
            else
            {
                if (pos.x < 1.5)
                {
                    mask.y = LIBRA_PUSH_FRAGMENT_INSTANCE.maskLight;
                }
                else
                {
                    mask.z = LIBRA_PUSH_FRAGMENT_INSTANCE.maskLight;
                }
            }
            mask *= line;
        }
        else
        {
            if (LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask == 2.0)
            {
                pos.x = floor(mod(pos.x, 3.0));
                if (pos.x < 0.5)
                {
                    mask.x = LIBRA_PUSH_FRAGMENT_INSTANCE.maskLight;
                }
                else
                {
                    if (pos.x < 1.5)
                    {
                        mask.y = LIBRA_PUSH_FRAGMENT_INSTANCE.maskLight;
                    }
                    else
                    {
                        mask.z = LIBRA_PUSH_FRAGMENT_INSTANCE.maskLight;
                    }
                }
            }
            else
            {
                if (LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask == 3.0)
                {
                    pos.x += (pos.y * 3.0);
                    pos.x = fract(pos.x / 6.0);
                    if (pos.x < 0.300000011920928955078125)
                    {
                        mask.x = LIBRA_PUSH_FRAGMENT_INSTANCE.maskLight;
                    }
                    else
                    {
                        if (pos.x < 0.60000002384185791015625)
                        {
                            mask.y = LIBRA_PUSH_FRAGMENT_INSTANCE.maskLight;
                        }
                        else
                        {
                            mask.z = LIBRA_PUSH_FRAGMENT_INSTANCE.maskLight;
                        }
                    }
                }
                else
                {
                    if (LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask == 4.0)
                    {
                        pos = floor(pos * vec2(1.0, 0.5));
                        pos.x += (pos.y * 3.0);
                        pos.x = fract(pos.x / 6.0);
                        if (pos.x < 0.300000011920928955078125)
                        {
                            mask.x = LIBRA_PUSH_FRAGMENT_INSTANCE.maskLight;
                        }
                        else
                        {
                            if (pos.x < 0.60000002384185791015625)
                            {
                                mask.y = LIBRA_PUSH_FRAGMENT_INSTANCE.maskLight;
                            }
                            else
                            {
                                mask.z = LIBRA_PUSH_FRAGMENT_INSTANCE.maskLight;
                            }
                        }
                    }
                    else
                    {
                        if (LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask == 5.0)
                        {
                            mask = vec3(0.0);
                            pos.x = fract(pos.x / 2.0);
                            if (pos.x < 0.4900000095367431640625)
                            {
                                mask.x = 1.0;
                                mask.z = 1.0;
                            }
                            else
                            {
                                mask.y = 1.0;
                            }
                            mask = clamp(mix(mix(one, mask, vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.mcut)), mix(one, mask, vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.maskstr)), vec3(mx)), vec3(0.0), vec3(1.0));
                        }
                        else
                        {
                            if (LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask == 6.0)
                            {
                                mask = vec3(0.0);
                                pos.x = floor(mod(pos.x, 3.0));
                                if (pos.x < 0.5)
                                {
                                    mask.x = 1.0;
                                }
                                else
                                {
                                    if (pos.x < 1.5)
                                    {
                                        mask.y = 1.0;
                                    }
                                    else
                                    {
                                        mask.z = 1.0;
                                    }
                                }
                                mask = clamp(mix(mix(one, mask, vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.mcut)), mix(one, mask, vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.maskstr)), vec3(mx)), vec3(0.0), vec3(1.0));
                            }
                            else
                            {
                                if (LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask == 7.0)
                                {
                                    mask = vec3(0.0);
                                    pos.x = fract(pos.x / 2.0);
                                    if (pos.x < 0.4900000095367431640625)
                                    {
                                        mask = vec3(0.0);
                                    }
                                    else
                                    {
                                        mask = vec3(1.0);
                                    }
                                    mask = clamp(mix(mix(one, mask, vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.mcut)), mix(one, mask, vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.maskstr)), vec3(mx)), vec3(0.0), vec3(1.0));
                                }
                                else
                                {
                                    if (LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask == 8.0)
                                    {
                                        mask = vec3(0.0);
                                        pos.x = fract(pos.x / 3.0);
                                        if (pos.x < 0.300000011920928955078125)
                                        {
                                            mask = vec3(0.0);
                                        }
                                        else
                                        {
                                            if (pos.x < 0.60000002384185791015625)
                                            {
                                                mask = vec3(1.0);
                                            }
                                            else
                                            {
                                                mask = vec3(1.0);
                                            }
                                        }
                                        mask = clamp(mix(mix(one, mask, vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.mcut)), mix(one, mask, vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.maskstr)), vec3(mx)), vec3(0.0), vec3(1.0));
                                    }
                                    else
                                    {
                                        if (LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask == 9.0)
                                        {
                                            mask = vec3(0.0);
                                            pos.x = fract(pos.x / 3.0);
                                            if (pos.x < 0.300000011920928955078125)
                                            {
                                                mask = vec3(0.0);
                                            }
                                            else
                                            {
                                                if (pos.x < 0.60000002384185791015625)
                                                {
                                                    mask.x = 1.0;
                                                    mask.z = 1.0;
                                                }
                                                else
                                                {
                                                    mask.y = 1.0;
                                                }
                                            }
                                            mask = clamp(mix(mix(one, mask, vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.mcut)), mix(one, mask, vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.maskstr)), vec3(mx)), vec3(0.0), vec3(1.0));
                                        }
                                        else
                                        {
                                            if (LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask == 10.0)
                                            {
                                                mask = vec3(0.0);
                                                pos.x = fract(pos.x * 0.25);
                                                if (pos.x < 0.20000000298023223876953125)
                                                {
                                                    mask = vec3(0.0);
                                                }
                                                else
                                                {
                                                    if (pos.x < 0.4000000059604644775390625)
                                                    {
                                                        mask.x = 1.0;
                                                    }
                                                    else
                                                    {
                                                        if (pos.x < 0.699999988079071044921875)
                                                        {
                                                            mask.y = 1.0;
                                                        }
                                                        else
                                                        {
                                                            mask.z = 1.0;
                                                        }
                                                    }
                                                }
                                                mask = clamp(mix(mix(one, mask, vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.mcut)), mix(one, mask, vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.maskstr)), vec3(mx)), vec3(0.0), vec3(1.0));
                                            }
                                            else
                                            {
                                                if (LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask == 11.0)
                                                {
                                                    mask = vec3(0.0);
                                                    pos.x = fract(pos.x * 0.25);
                                                    if (pos.x < 0.20000000298023223876953125)
                                                    {
                                                        mask.x = 1.0;
                                                    }
                                                    else
                                                    {
                                                        if (pos.x < 0.4000000059604644775390625)
                                                        {
                                                            mask.x = 1.0;
                                                            mask.y = 1.0;
                                                        }
                                                        else
                                                        {
                                                            if (pos.x < 0.699999988079071044921875)
                                                            {
                                                                mask.y = 1.0;
                                                                mask.z = 1.0;
                                                            }
                                                            else
                                                            {
                                                                mask.z = 1.0;
                                                            }
                                                        }
                                                    }
                                                    mask = clamp(mix(mix(one, mask, vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.mcut)), mix(one, mask, vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.maskstr)), vec3(mx)), vec3(0.0), vec3(1.0));
                                                }
                                                else
                                                {
                                                    if (LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask == 12.0)
                                                    {
                                                        mask = vec3(0.0);
                                                        pos.x = floor(mod(pos.x, 7.0));
                                                        if (pos.x < 0.5)
                                                        {
                                                            mask = vec3(0.0);
                                                        }
                                                        else
                                                        {
                                                            if (pos.x < 2.5)
                                                            {
                                                                mask.x = 1.0;
                                                            }
                                                            else
                                                            {
                                                                if (pos.x < 4.5)
                                                                {
                                                                    mask.y = 1.0;
                                                                }
                                                                else
                                                                {
                                                                    mask.z = 1.0;
                                                                }
                                                            }
                                                        }
                                                        mask = clamp(mix(mix(one, mask, vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.mcut)), mix(one, mask, vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.maskstr)), vec3(mx)), vec3(0.0), vec3(1.0));
                                                    }
                                                    else
                                                    {
                                                        if (LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask == 13.0)
                                                        {
                                                            mask = vec3(0.0);
                                                            pos.x = floor(mod(pos.x, 6.0));
                                                            if (pos.x < 0.5)
                                                            {
                                                                mask = vec3(0.0);
                                                            }
                                                            else
                                                            {
                                                                if (pos.x < 1.5)
                                                                {
                                                                    mask.x = 1.0;
                                                                }
                                                                else
                                                                {
                                                                    if (pos.x < 2.5)
                                                                    {
                                                                        mask.x = 1.0;
                                                                        mask.y = 1.0;
                                                                    }
                                                                    else
                                                                    {
                                                                        if (pos.x < 3.5)
                                                                        {
                                                                            mask = vec3(1.0);
                                                                        }
                                                                        else
                                                                        {
                                                                            if (pos.x < 4.5)
                                                                            {
                                                                                mask.y = 1.0;
                                                                                mask.z = 1.0;
                                                                            }
                                                                            else
                                                                            {
                                                                                mask.z = 1.0;
                                                                            }
                                                                        }
                                                                    }
                                                                }
                                                            }
                                                            mask = clamp(mix(mix(one, mask, vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.mcut)), mix(one, mask, vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.maskstr)), vec3(mx)), vec3(0.0), vec3(1.0));
                                                        }
                                                        else
                                                        {
                                                            mask = vec3(0.0);
                                                            pos.x = floor(mod(pos.x, 5.0));
                                                            if (pos.x < 0.5)
                                                            {
                                                                mask = vec3(0.0);
                                                            }
                                                            else
                                                            {
                                                                if (pos.x < 1.5)
                                                                {
                                                                    mask.x = 1.0;
                                                                }
                                                                else
                                                                {
                                                                    if (pos.x < 2.5)
                                                                    {
                                                                        mask.x = 1.0;
                                                                        mask.y = 1.0;
                                                                    }
                                                                    else
                                                                    {
                                                                        if (pos.x < 3.5)
                                                                        {
                                                                            mask.y = 1.0;
                                                                            mask.z = 1.0;
                                                                        }
                                                                        else
                                                                        {
                                                                            mask.z = 1.0;
                                                                        }
                                                                    }
                                                                }
                                                            }
                                                            mask = clamp(mix(mix(one, mask, vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.mcut)), mix(one, mask, vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.maskstr)), vec3(mx)), vec3(0.0), vec3(1.0));
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    if (LIBRA_PUSH_FRAGMENT_INSTANCE.mask_layout > 0.5)
    {
        mask = mask.xzy;
    }
    float maskmin = min(min(mask.x, mask.y), mask.z);
    return ((mask - vec3(maskmin)) * (1.0 + ((LIBRA_UBO_FRAGMENT_INSTANCE.maskboost - 1.0) * mb))) + vec3(maskmin);
}

float SlotMask(inout vec2 pos, float m, float swidth)
{
    if ((LIBRA_PUSH_FRAGMENT_INSTANCE.slotmask + LIBRA_PUSH_FRAGMENT_INSTANCE.slotmask1) == 0.0)
    {
        return 1.0;
    }
    else
    {
        pos.y = floor(pos.y / LIBRA_UBO_FRAGMENT_INSTANCE.slotms);
        float mlen = swidth * 2.0;
        float px = floor(mod(pos.x, 0.999989986419677734375 * mlen));
        float py = floor((fract(pos.y / (2.0 * LIBRA_PUSH_FRAGMENT_INSTANCE.double_slot)) * 2.0) * LIBRA_PUSH_FRAGMENT_INSTANCE.double_slot);
        float slot_dark = mix(1.0 - LIBRA_PUSH_FRAGMENT_INSTANCE.slotmask1, 1.0 - LIBRA_PUSH_FRAGMENT_INSTANCE.slotmask, m);
        float slot = 1.0;
        if ((py == 0.0) && (px < swidth))
        {
            slot = slot_dark;
        }
        else
        {
            if ((py == LIBRA_PUSH_FRAGMENT_INSTANCE.double_slot) && (px >= swidth))
            {
                slot = slot_dark;
            }
        }
        return slot;
    }
}

vec3 plant(vec3 tar, float r)
{
    float t = max(max(tar.x, tar.y), tar.z) + 9.9999997473787516355514526367188e-06;
    return (tar * r) / vec3(t);
}

vec3 gc2(vec3 c, float w3)
{
    float mc = max(max(c.x, c.y), c.z);
    float gp = 1.0 / (1.0 + ((LIBRA_UBO_FRAGMENT_INSTANCE.gamma_c2 - 1.0) * mix(0.375, 1.0, w3)));
    float mg = pow(mc, gp);
    return (c * mg) / vec3(mc + 1.0000000133514319600180897396058e-10);
}

vec3 _noise(inout vec3 v)
{
    if (LIBRA_UBO_FRAGMENT_INSTANCE.addnoised < 0.0)
    {
        v.z = -LIBRA_UBO_FRAGMENT_INSTANCE.addnoised;
    }
    else
    {
        v.z = mod(v.z, 6001.0) / 1753.0;
    }
    v = (fract(v) + fract(v * 10000.0)) + fract(v * 9.9999997473787516355514526367188e-05);
    v += vec3(0.123450003564357757568359375, 0.6789000034332275390625, 0.3141590058803558349609375);
    v = fract((v * dot(v, v)) * 123.45600128173828125);
    v = fract((v * dot(v, v)) * 123.45600128173828125);
    v = fract((v * dot(v, v)) * 123.45600128173828125);
    v = fract((v * dot(v, v)) * 123.45600128173828125);
    return v;
}

float humbar(inout float pos)
{
    if (LIBRA_UBO_FRAGMENT_INSTANCE.barintensity == 0.0)
    {
        return 1.0;
    }
    else
    {
        float _1002;
        if (LIBRA_UBO_FRAGMENT_INSTANCE.barintensity >= 0.0)
        {
            _1002 = pos;
        }
        else
        {
            _1002 = 1.0 - pos;
        }
        pos = _1002;
        pos = fract(pos + (mod(float(LIBRA_UBO_FRAGMENT_INSTANCE.FrameCount), LIBRA_UBO_FRAGMENT_INSTANCE.barspeed) / (LIBRA_UBO_FRAGMENT_INSTANCE.barspeed - 1.0)));
        float _1028;
        if (LIBRA_UBO_FRAGMENT_INSTANCE.barintensity < 0.0)
        {
            _1028 = pos;
        }
        else
        {
            _1028 = 1.0 - pos;
        }
        pos = _1028;
        return (1.0 - LIBRA_UBO_FRAGMENT_INSTANCE.barintensity) + (LIBRA_UBO_FRAGMENT_INSTANCE.barintensity * pos);
    }
}

float corner(inout vec2 pos)
{
    pos = abs((pos - vec2(0.5)) * 2.0);
    vec2 aspect = vec2(1.0, LIBRA_UBO_FRAGMENT_INSTANCE.OutputSize.x / LIBRA_UBO_FRAGMENT_INSTANCE.OutputSize.y);
    float b = (LIBRA_PUSH_FRAGMENT_INSTANCE.bsize1 * 0.0500000007450580596923828125) + 0.0005000000237487256526947021484375;
    pos.y += (b * (aspect.y - 1.0));
    vec2 crn = max(vec2(LIBRA_PUSH_FRAGMENT_INSTANCE.csize), vec2((2.0 * b) + 0.00150000001303851604461669921875));
    vec2 cp = max(pos - (vec2(1.0) - (crn * aspect)), vec2(0.0)) / aspect;
    float cd = sqrt(dot(cp, cp));
    pos = max(pos, (vec2(1.0) - crn) + vec2(cd));
    float res = mix(1.0, 0.0, smoothstep(1.0 - b, 1.0, sqrt(max(pos.x, pos.y))));
    return pow(res, LIBRA_UBO_FRAGMENT_INSTANCE.sborder);
}

void main()
{
    vec4 SourceSize = LIBRA_UBO_FRAGMENT_INSTANCE.OriginalSize;
    float lum = texture(LIBRA_TEXTURE_AvgLumPass, vec2(0.5)).w;
    float gamma_in = 1.0 / texture(LIBRA_TEXTURE_LinearizePass, vec2(0.25)).w;
    float intera = texture(LIBRA_TEXTURE_LinearizePass, vec2(0.75, 0.25)).w;
    bool _1482 = intera < 0.3499999940395355224609375;
    bool _1489;
    if (_1482)
    {
        _1489 = LIBRA_UBO_FRAGMENT_INSTANCE.interm == 6.0;
    }
    else
    {
        _1489 = _1482;
    }
    bool inter6 = _1489;
    bool _1495 = (intera < 0.3499999940395355224609375) && (!inter6);
    bool _1503;
    if (!_1495)
    {
        _1503 = LIBRA_UBO_FRAGMENT_INSTANCE.no_scanlines > 0.02500000037252902984619140625;
    }
    else
    {
        _1503 = _1495;
    }
    bool _1510;
    if (_1503)
    {
        _1510 = LIBRA_PUSH_FRAGMENT_INSTANCE.hiscan < 0.5;
    }
    else
    {
        _1510 = _1503;
    }
    bool interb = _1510;
    vec2 texcoord = LIBRA_VARYING_0;
    if ((LIBRA_PUSH_FRAGMENT_INSTANCE.IOS > 0.0) && (!interb))
    {
        vec2 ofactor = LIBRA_UBO_FRAGMENT_INSTANCE.OutputSize.xy / LIBRA_UBO_FRAGMENT_INSTANCE.OriginalSize.xy;
        vec2 _1536;
        if (LIBRA_PUSH_FRAGMENT_INSTANCE.IOS < 2.5)
        {
            _1536 = floor(ofactor);
        }
        else
        {
            _1536 = ceil(ofactor);
        }
        vec2 intfactor = _1536;
        vec2 diff = ofactor / intfactor;
        float scan = diff.y;
        vec2 param = texcoord;
        float param_1 = scan;
        float param_2 = scan;
        vec2 _1558 = Overscan(param, param_1, param_2);
        texcoord = _1558;
        bool _1561 = LIBRA_PUSH_FRAGMENT_INSTANCE.IOS == 1.0;
        bool _1568;
        if (!_1561)
        {
            _1568 = LIBRA_PUSH_FRAGMENT_INSTANCE.IOS == 3.0;
        }
        else
        {
            _1568 = _1561;
        }
        if (_1568)
        {
            texcoord = vec2(LIBRA_VARYING_0.x, texcoord.y);
        }
    }
    float factor = (1.0 + (((1.0 - (0.5 * LIBRA_PUSH_FRAGMENT_INSTANCE.OS)) * LIBRA_PUSH_FRAGMENT_INSTANCE.BLOOM) / 100.0)) - ((lum * LIBRA_PUSH_FRAGMENT_INSTANCE.BLOOM) / 100.0);
    vec2 param_3 = texcoord;
    float param_4 = factor;
    float param_5 = factor;
    vec2 _1601 = Overscan(param_3, param_4, param_5);
    texcoord = _1601;
    texcoord.y -= (LIBRA_UBO_FRAGMENT_INSTANCE.VShift * LIBRA_UBO_FRAGMENT_INSTANCE.OriginalSize.w);
    vec2 param_6 = texcoord;
    float param_7 = (LIBRA_UBO_FRAGMENT_INSTANCE.OriginalSize.x - LIBRA_UBO_FRAGMENT_INSTANCE.overscanX) / LIBRA_UBO_FRAGMENT_INSTANCE.OriginalSize.x;
    float param_8 = (LIBRA_UBO_FRAGMENT_INSTANCE.OriginalSize.y - LIBRA_UBO_FRAGMENT_INSTANCE.overscanY) / LIBRA_UBO_FRAGMENT_INSTANCE.OriginalSize.y;
    vec2 _1632 = Overscan(param_6, param_7, param_8);
    texcoord = _1632;
    vec2 pos1 = LIBRA_VARYING_0;
    vec2 param_9 = texcoord;
    vec2 _1638 = Warp(param_9);
    vec2 pos = _1638;
    vec2 param_10 = LIBRA_VARYING_0;
    vec2 _1642 = Warp(param_10);
    vec2 pos0 = _1642;
    vec2 posb = (pos0 - vec2(0.5)) * 2.0;
    if (LIBRA_PUSH_FRAGMENT_INSTANCE.BLOOM < 0.5)
    {
        posb = max(abs(posb), abs((pos - vec2(0.5)) * 2.0)) * sign(posb);
    }
    posb = (posb * 0.5) + vec2(0.5);
    vec3 color = texture(LIBRA_TEXTURE_Source, pos1).xyz;
    vec3 Bloom = texture(LIBRA_TEXTURE_BloomPass, pos).xyz;
    vec3 Glow = texture(LIBRA_TEXTURE_GlowPass, pos).xyz;
    if ((((((abs(LIBRA_UBO_FRAGMENT_INSTANCE.deconrr) + abs(LIBRA_UBO_FRAGMENT_INSTANCE.deconrry)) + abs(LIBRA_UBO_FRAGMENT_INSTANCE.deconrg)) + abs(LIBRA_UBO_FRAGMENT_INSTANCE.deconrgy)) + abs(LIBRA_UBO_FRAGMENT_INSTANCE.deconrb)) + abs(LIBRA_UBO_FRAGMENT_INSTANCE.deconrby)) > 0.20000000298023223876953125)
    {
        vec3 param_11 = color;
        vec3 param_12 = Bloom;
        vec3 param_13 = Glow;
        vec2 param_14 = pos1;
        vec2 param_15 = pos;
        fetch_pixel(param_11, param_12, param_13, param_14, param_15);
        color = param_11;
        Bloom = param_12;
        Glow = param_13;
    }
    float param_16 = max(max(color.x, color.y), color.z);
    float cm = igc(param_16);
    float mx1 = texture(LIBRA_TEXTURE_Source, pos1).w;
    float colmx = max(mx1, cm);
    float w3 = min((max((cm - 0.0005000000237487256526947021484375) * 1.0004999637603759765625, 0.0) + 9.9999997473787516355514526367188e-05) / (colmx + 0.0005000000237487256526947021484375), 1.0);
    if (interb)
    {
        w3 = 1.0;
    }
    vec2 dx = vec2(0.001000000047497451305389404296875, 0.0);
    float mx0 = texture(LIBRA_TEXTURE_Source, pos1 - dx).w;
    float mx2 = texture(LIBRA_TEXTURE_Source, pos1 + dx).w;
    float mxg = max(max(mx0, mx1), max(mx2, cm));
    float mx = pow(mxg, 1.39999997615814208984375 / gamma_in);
    float cx = pow(colmx, 1.39999997615814208984375 / gamma_in);
    dx = vec2(LIBRA_UBO_FRAGMENT_INSTANCE.OriginalSize.z, 0.0) * 0.25;
    mx0 = texture(LIBRA_TEXTURE_Source, pos1 - dx).w;
    mx2 = texture(LIBRA_TEXTURE_Source, pos1 + dx).w;
    float mb = 1.0 - min(abs(mx0 - mx2) / (0.5 + mx1), 1.0);
    vec3 one = vec3(1.0);
    vec3 orig1 = color;
    vec3 cmask = one;
    vec3 cmask1 = one;
    vec3 cmask2 = one;
    float mwidth = _1840[int(LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask)];
    float mask_compensate = fract(mwidth);
    float mwidth1 = mwidth;
    if (LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask > (-0.5))
    {
        vec2 maskcoord = LIBRA_VARYING_0 * LIBRA_UBO_FRAGMENT_INSTANCE.OutputSize.xy;
        vec2 scoord = maskcoord;
        mwidth = floor(mwidth) * LIBRA_PUSH_FRAGMENT_INSTANCE.masksize;
        float swidth = mwidth;
        bool zoomed = abs(LIBRA_UBO_FRAGMENT_INSTANCE.mask_zoom) > 0.75;
        float mscale = 1.0;
        vec2 maskcoord0 = maskcoord;
        maskcoord.y = floor(maskcoord.y / LIBRA_PUSH_FRAGMENT_INSTANCE.masksize);
        mwidth1 = max(mwidth + LIBRA_UBO_FRAGMENT_INSTANCE.mask_zoom, 2.0);
        if (LIBRA_PUSH_FRAGMENT_INSTANCE.mshift > 0.25)
        {
            float stagg_lvl = 1.0;
            if (fract(LIBRA_PUSH_FRAGMENT_INSTANCE.mshift) > 0.25)
            {
                stagg_lvl = 2.0;
            }
            float next_line = float(floor(mod(maskcoord.y, 2.0 * stagg_lvl)) < stagg_lvl);
            maskcoord0.x += ((next_line * 0.5) * mwidth1);
        }
        maskcoord = maskcoord0 / vec2(LIBRA_PUSH_FRAGMENT_INSTANCE.masksize);
        if (!zoomed)
        {
            vec2 param_17 = floor(maskcoord);
            float param_18 = mx;
            float param_19 = mb;
            vec3 _1941 = Mask(param_17, param_18, param_19);
            cmask = _1941;
        }
        else
        {
            mscale = mwidth1 / mwidth;
            float mlerp = fract(maskcoord.x / mscale);
            if (LIBRA_UBO_FRAGMENT_INSTANCE.mzoom_sh > 0.02500000037252902984619140625)
            {
                mlerp = clamp(((1.0 + LIBRA_UBO_FRAGMENT_INSTANCE.mzoom_sh) * mlerp) - (0.5 * LIBRA_UBO_FRAGMENT_INSTANCE.mzoom_sh), 0.0, 1.0);
            }
            float mcoord = floor(maskcoord.x / mscale);
            bool _1976 = LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask == 12.0;
            bool _1983;
            if (_1976)
            {
                _1983 = LIBRA_UBO_FRAGMENT_INSTANCE.mask_zoom == (-2.0);
            }
            else
            {
                _1983 = _1976;
            }
            if (_1983)
            {
                mcoord = ceil(maskcoord.x / mscale);
            }
            vec2 param_20 = vec2(mcoord, maskcoord.y);
            float param_21 = mx;
            float param_22 = mb;
            vec3 _2000 = Mask(param_20, param_21, param_22);
            vec2 param_23 = vec2(mcoord + 1.0, maskcoord.y);
            float param_24 = mx;
            float param_25 = mb;
            vec3 _2011 = Mask(param_23, param_24, param_25);
            cmask = mix(_2000, _2011, vec3(mlerp));
        }
        float sm_offset = 0.0;
        bool _2019 = LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask == 0.0;
        bool _2026;
        if (!_2019)
        {
            _2026 = LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask == 2.0;
        }
        else
        {
            _2026 = _2019;
        }
        bool _2033;
        if (!_2026)
        {
            _2033 = LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask == 5.0;
        }
        else
        {
            _2033 = _2026;
        }
        bool _2040;
        if (!_2033)
        {
            _2040 = LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask == 6.0;
        }
        else
        {
            _2040 = _2033;
        }
        bool _2047;
        if (!_2040)
        {
            _2047 = LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask == 8.0;
        }
        else
        {
            _2047 = _2040;
        }
        bool _2054;
        if (!_2047)
        {
            _2054 = LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask == 11.0;
        }
        else
        {
            _2054 = _2047;
        }
        bool bsm_offset = _2054;
        if (zoomed)
        {
            if ((LIBRA_PUSH_FRAGMENT_INSTANCE.mask_layout < 0.5) && bsm_offset)
            {
                sm_offset = 1.0;
            }
            else
            {
                if (bsm_offset)
                {
                    sm_offset = -1.0;
                }
            }
        }
        swidth = round(mwidth1);
        if (LIBRA_PUSH_FRAGMENT_INSTANCE.slotwidth > 0.5)
        {
            swidth = LIBRA_PUSH_FRAGMENT_INSTANCE.slotwidth;
        }
        float smask = 1.0;
        vec2 param_26 = scoord + vec2(sm_offset, 0.0);
        float param_27 = mx;
        float param_28 = swidth;
        float _2089 = SlotMask(param_26, param_27, param_28);
        smask = _2089;
        smask = clamp(smask + mix(LIBRA_UBO_FRAGMENT_INSTANCE.smask_mit, 0.0, w3 * pow(colmx, 0.300000011920928955078125)), 0.0, 1.0);
        cmask2 = cmask;
        cmask *= smask;
        cmask1 = cmask;
        if (abs(LIBRA_PUSH_FRAGMENT_INSTANCE.mask_bloom) > 0.02500000037252902984619140625)
        {
            float maxbl = max(max(max(Bloom.x, Bloom.y), Bloom.z), mxg);
            maxbl *= max(mix(1.0, 2.0 - colmx, LIBRA_UBO_FRAGMENT_INSTANCE.bloom_dist), 0.0);
            if (LIBRA_PUSH_FRAGMENT_INSTANCE.mask_bloom > 0.02500000037252902984619140625)
            {
                cmask = max(min(cmask + vec3(maxbl * LIBRA_PUSH_FRAGMENT_INSTANCE.mask_bloom), vec3(1.0)), cmask);
            }
            else
            {
                vec3 param_29 = pow(Bloom, vec3(0.3499999940395355224609375));
                float param_30 = maxbl;
                cmask = max(mix(cmask, (cmask * (1.0 - (0.5 * maxbl))) + plant(param_29, param_30), vec3(-LIBRA_PUSH_FRAGMENT_INSTANCE.mask_bloom)), cmask);
            }
        }
        color = pow(color, vec3(LIBRA_UBO_FRAGMENT_INSTANCE.mask_gamma / gamma_in));
        color *= cmask;
        color = min(color, vec3(1.0));
        color = pow(color, vec3(gamma_in / LIBRA_UBO_FRAGMENT_INSTANCE.mask_gamma));
        cmask = min(cmask, vec3(1.0));
        cmask1 = min(cmask1, vec3(1.0));
    }
    float dark_compensate = mix(max((clamp(mix(LIBRA_PUSH_FRAGMENT_INSTANCE.mcut, LIBRA_PUSH_FRAGMENT_INSTANCE.maskstr, mx), 0.0, 1.0) - 1.0) + mask_compensate, 0.0) + 1.0, 1.0, mx);
    if (LIBRA_PUSH_FRAGMENT_INSTANCE.shadowMask < (-0.5))
    {
        dark_compensate = 1.0;
    }
    float bb = mix(LIBRA_PUSH_FRAGMENT_INSTANCE.brightboost, LIBRA_PUSH_FRAGMENT_INSTANCE.brightboost1, mx) * dark_compensate;
    color *= bb;
    vec3 Ref = texture(LIBRA_TEXTURE_LinearizePass, pos).xyz;
    float maxb = texture(LIBRA_TEXTURE_BloomPass, pos).w;
    float vig = texture(LIBRA_TEXTURE_PrePass0, clamp(pos, vec2(0.0) + (LIBRA_UBO_FRAGMENT_INSTANCE.OriginalSize.zw * 0.5), vec2(1.0) - (LIBRA_UBO_FRAGMENT_INSTANCE.OriginalSize.zw * 0.5))).w;
    if (LIBRA_PUSH_FRAGMENT_INSTANCE.pr_scan > 0.02500000037252902984619140625)
    {
        float mbl = max(max(Bloom.x, Bloom.y), Bloom.z);
        vec3 param_31 = orig1;
        float param_32 = mbl;
        Bloom = mix(Bloom, mix(Bloom, plant(param_31, param_32), vec3(min(2.5 * (1.0 - w3), 1.0))), vec3(min(2.0 * LIBRA_PUSH_FRAGMENT_INSTANCE.pr_scan, 1.0)));
    }
    vec3 Bloom1 = Bloom;
    vec3 bcmask = mix(one, cmask1, vec3(LIBRA_UBO_FRAGMENT_INSTANCE.bmask1));
    vec3 hcmask = mix(one, cmask1, vec3(LIBRA_UBO_FRAGMENT_INSTANCE.hmask1));
    if (abs(LIBRA_UBO_FRAGMENT_INSTANCE.bloom) > 0.02500000037252902984619140625)
    {
        if (LIBRA_UBO_FRAGMENT_INSTANCE.bloom < (-0.00999999977648258209228515625))
        {
            vec3 param_33 = Bloom;
            float param_34 = maxb;
            Bloom1 = plant(param_33, param_34);
        }
        Bloom1 = min(Bloom1 * (orig1 + color), max(((vec3(colmx) + orig1) - color) * 0.5, Bloom1 * 0.001000000047497451305389404296875));
        Bloom1 = (Bloom1 + mix(Bloom1, mix(orig1 * colmx, Bloom1, vec3(0.5)), vec3(1.0) - color)) * 0.5;
        Bloom1 = (bcmask * Bloom1) * max(mix(1.0, 2.0 - colmx, LIBRA_UBO_FRAGMENT_INSTANCE.bloom_dist), 0.0);
        color = pow(pow(color, vec3(LIBRA_UBO_FRAGMENT_INSTANCE.mask_gamma / gamma_in)) + (pow(Bloom1, vec3(LIBRA_UBO_FRAGMENT_INSTANCE.mask_gamma / gamma_in)) * abs(LIBRA_UBO_FRAGMENT_INSTANCE.bloom)), vec3(gamma_in / LIBRA_UBO_FRAGMENT_INSTANCE.mask_gamma));
    }
    if (LIBRA_UBO_FRAGMENT_INSTANCE.halation > 0.00999999977648258209228515625)
    {
        Bloom = (Bloom + (Bloom * Bloom)) * 0.5;
        float mbl_1 = max(max(Bloom.x, Bloom.y), Bloom.z);
        float cmxh = 0.5 * (colmx + (colmx * colmx));
        mbl_1 = mix(mix(cmxh, mix(cmxh, mbl_1, mbl_1), colmx), mbl_1, mb);
        vec3 param_35 = Bloom;
        float param_36 = mix(sqrt(mbl_1 * cmxh), max(mbl_1 - (0.1500000059604644775390625 * (1.0 - colmx)), 0.4000000059604644775390625 * cmxh), pow(colmx, 0.25));
        Bloom = plant(param_35, param_36) * mix(0.425000011920928955078125, 1.0, colmx);
        vec3 param_37 = vec3(0.324999988079071044921875) + (orig1 / vec3(w3));
        float param_38 = 0.5 * (1.0 + w3);
        Bloom = (((vec3(3.0 - colmx) - color) * plant(param_37, param_38)) * hcmask) * Bloom;
        color = pow(pow(color, vec3(LIBRA_UBO_FRAGMENT_INSTANCE.mask_gamma / gamma_in)) + (pow(Bloom, vec3(LIBRA_UBO_FRAGMENT_INSTANCE.mask_gamma / gamma_in)) * LIBRA_UBO_FRAGMENT_INSTANCE.halation), vec3(gamma_in / LIBRA_UBO_FRAGMENT_INSTANCE.mask_gamma));
    }
    else
    {
        if (LIBRA_UBO_FRAGMENT_INSTANCE.halation < (-0.00999999977648258209228515625))
        {
            float mbl_2 = max(max(Bloom.x, Bloom.y), Bloom.z);
            vec3 param_39 = ((Bloom + Ref) + orig1) + ((Bloom * Bloom) * Bloom);
            float param_40 = min(mbl_2 * mbl_2, 0.75);
            Bloom = plant(param_39, param_40);
            Bloom = (hcmask * (2.0 * mix(1.0, w3, 0.5 * colmx))) * Bloom;
            color -= (Bloom * LIBRA_UBO_FRAGMENT_INSTANCE.halation);
        }
    }
    color = min(color, vec3(1.0));
    vec3 param_41 = color;
    float param_42 = w3;
    color = gc2(param_41, param_42);
    if (LIBRA_UBO_FRAGMENT_INSTANCE.smoothmask > 0.125)
    {
        float w4 = pow(w3, 0.425000011920928955078125 + (0.300000011920928955078125 * LIBRA_UBO_FRAGMENT_INSTANCE.smoothmask));
        w4 = max(w4 - ((0.17499999701976776123046875 * colmx) * LIBRA_UBO_FRAGMENT_INSTANCE.smoothmask), 0.20000000298023223876953125);
        vec3 param_43 = orig1;
        float param_44 = 1.0 + ((0.17499999701976776123046875 * colmx) * LIBRA_UBO_FRAGMENT_INSTANCE.smoothmask);
        color = mix(min(color / vec3(w4), plant(param_43, param_44)) * w4, color, vec3(w4));
    }
    if (LIBRA_UBO_FRAGMENT_INSTANCE.m_glow < 0.5)
    {
        Glow = mix(Glow, color * 0.25, vec3(colmx));
    }
    else
    {
        maxb = max(max(Glow.x, Glow.y), Glow.z);
        vec3 param_45 = orig1 + (Ref * 0.001000000047497451305389404296875);
        float param_46 = 1.0;
        vec3 orig2 = plant(param_45, param_46);
        vec3 param_47 = Glow;
        float param_48 = 1.0;
        Bloom = plant(param_47, param_48);
        Ref = abs(orig2 - Bloom);
        mx0 = max(max(orig2.x, orig2.y), orig2.z) - min(min(orig2.x, orig2.y), orig2.z);
        mx2 = max(max(Bloom.x, Bloom.y), Bloom.z) - min(min(Bloom.x, Bloom.y), Bloom.z);
        Bloom = mix(min(Bloom, orig2) * maxb, mix(mix(Glow, Glow * max(max(Ref.x, Ref.y), Ref.z), vec3(max(mx, mx0))), mix(color, Glow, vec3(mx2)), Ref * max(mx0, mx2)), vec3(min(sqrt((1.10000002384185791015625 - mx0) * (0.100000001490116119384765625 + mx2)), 1.0)));
        if (LIBRA_UBO_FRAGMENT_INSTANCE.m_glow > 1.5)
        {
            Glow = mix((Glow * 0.5) * Glow, Bloom, Bloom);
        }
        Glow = mix(Glow * LIBRA_UBO_FRAGMENT_INSTANCE.m_glow_low, Bloom * LIBRA_UBO_FRAGMENT_INSTANCE.m_glow_high, vec3(pow(colmx, LIBRA_UBO_FRAGMENT_INSTANCE.m_glow_dist / gamma_in)));
    }
    if (LIBRA_UBO_FRAGMENT_INSTANCE.m_glow < 0.5)
    {
        if (LIBRA_PUSH_FRAGMENT_INSTANCE.glow >= 0.0)
        {
            color += ((Glow * 0.5) * LIBRA_PUSH_FRAGMENT_INSTANCE.glow);
        }
        else
        {
            color += ((min(cmask2 * cmask2, vec3(1.0)) * abs(LIBRA_PUSH_FRAGMENT_INSTANCE.glow)) * Glow);
        }
    }
    else
    {
        vec3 cmaskg = clamp(mix(one, cmask1, vec3(LIBRA_UBO_FRAGMENT_INSTANCE.m_glow_mask)), vec3(0.0), vec3(1.0));
        color += ((cmaskg * abs(LIBRA_PUSH_FRAGMENT_INSTANCE.glow)) * Glow);
    }
    color = min(color, vec3(1.0));
    if (LIBRA_UBO_FRAGMENT_INSTANCE.edgemask > 0.0500000007450580596923828125)
    {
        mx0 = texture(LIBRA_TEXTURE_Source, pos1 - dx).w;
        mx0 = texture(LIBRA_TEXTURE_Source, pos1 - (dx * (1.0 - (0.75 * sqrt(mx0))))).w;
        mx2 = texture(LIBRA_TEXTURE_Source, pos1 + dx).w;
        mx2 = texture(LIBRA_TEXTURE_Source, pos1 + (dx * (1.0 - (0.75 * sqrt(mx2))))).w;
        float mx3 = texture(LIBRA_TEXTURE_Source, pos1 - (dx * 4.0)).w;
        float mx4 = texture(LIBRA_TEXTURE_Source, pos1 + (dx * 4.0)).w;
        mx4 = max(pow(abs(mx3 - mx4), 0.550000011920928955078125 - (0.4000000059604644775390625 * cx)), min(max(mx3, mx4) / min(0.100000001490116119384765625 + cx, 1.0), 1.0));
        mb = 1.0 - abs(pow(mx0, 1.0 - (0.64999997615814208984375 * mx2)) - pow(mx2, 1.0 - (0.64999997615814208984375 * mx0)));
        mb = (mx4 * LIBRA_UBO_FRAGMENT_INSTANCE.edgemask) * (1.00010001659393310546875 - (mb * mb));
        vec3 temp = mix(color, orig1, vec3(mb));
        color = max(temp + mix(mix(temp * 1.625, temp, vec3(cx)) * (3.5 * mb), vec3(0.0), pow(color, vec3(0.75) - vec3(0.5 * colmx))), color);
    }
    color *= mix(1.0, mix(0.5 * (1.0 + w3), w3, mx), LIBRA_PUSH_FRAGMENT_INSTANCE.pr_scan);
    color = min(color, max(orig1, color) * mix(one, cmask1, vec3(LIBRA_UBO_FRAGMENT_INSTANCE.mclip)));
    color = pow(color, vec3(1.0 / LIBRA_UBO_FRAGMENT_INSTANCE.gamma_out));
    float rc = (0.60000002384185791015625 * sqrt(max(max(color.x, color.y), color.z))) + 0.4000000059604644775390625;
    if (abs(LIBRA_UBO_FRAGMENT_INSTANCE.addnoised) > 0.00999999977648258209228515625)
    {
        vec3 param_49 = vec3(floor((LIBRA_UBO_FRAGMENT_INSTANCE.OutputSize.xy * LIBRA_VARYING_0) / vec2(LIBRA_UBO_FRAGMENT_INSTANCE.noiseresd)), float(LIBRA_UBO_FRAGMENT_INSTANCE.FrameCount));
        vec3 _2992 = _noise(param_49);
        vec3 noise0 = _2992;
        if (LIBRA_UBO_FRAGMENT_INSTANCE.noisetype < 0.5)
        {
            color = mix(color, noise0, vec3((0.25 * abs(LIBRA_UBO_FRAGMENT_INSTANCE.addnoised)) * rc));
        }
        else
        {
            color = min(color * mix(1.0, 1.5 * noise0.x, 0.5 * abs(LIBRA_UBO_FRAGMENT_INSTANCE.addnoised)), vec3(1.0));
        }
    }
    colmx = max(max(orig1.x, orig1.y), orig1.z);
    color += (mix(cmask2, color * (0.125 * (1.0 - colmx)), vec3(min(20.0 * colmx, 1.0))) * LIBRA_UBO_FRAGMENT_INSTANCE.bmask);
    float param_50 = mix(pos.y, pos.x, LIBRA_UBO_FRAGMENT_INSTANCE.bardir);
    float _3060 = humbar(param_50);
    vec2 param_51 = posb;
    float _3068 = corner(param_51);
    FragColor = mix(vec4((((color * vig) * _3060) * LIBRA_UBO_FRAGMENT_INSTANCE.post_br) * _3068, 1.0), texture(LIBRA_TEXTURE_StockPass, (floor(pos1 * LIBRA_UBO_FRAGMENT_INSTANCE.OriginalSize.xy) + vec2(0.5)) * LIBRA_UBO_FRAGMENT_INSTANCE.OriginalSize.zw), vec4(step(pos1.x, LIBRA_UBO_FRAGMENT_INSTANCE.oimage - 0.00025000001187436282634735107421875)));
}

