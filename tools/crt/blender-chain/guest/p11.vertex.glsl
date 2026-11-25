#version 330

layout(std140) uniform LIBRA_UBO_VERTEX
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
    float noisetype;
    float noiseresd;
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
} LIBRA_UBO_VERTEX_INSTANCE;

struct LIBRA_PUSH_VERTEX
{
    float TATE;
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

uniform LIBRA_PUSH_VERTEX LIBRA_PUSH_VERTEX_INSTANCE;

layout(location = 0) in vec4 Position;
out vec2 LIBRA_VARYING_0;
layout(location = 1) in vec2 TexCoord;

void main()
{
    gl_Position = LIBRA_UBO_VERTEX_INSTANCE.MVP * Position;
    LIBRA_VARYING_0 = TexCoord * 1.000010013580322265625;
}

