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
    float scans;
    float gamma_c;
    float gamma_c2;
    float gamma_out;
    float overscanX;
    float overscanY;
    float VShift;
    float intres;
    float prescalex;
    float c_shape;
    float scangamma;
    float sborder;
    float scan_falloff;
    float bloom_dist;
    float bmask1;
    float hmask1;
    float interm;
} LIBRA_UBO_VERTEX_INSTANCE;

struct LIBRA_PUSH_VERTEX
{
    float IOS;
    float OS;
    float BLOOM;
    float brightboost;
    float brightboost1;
    float gsl;
    float scanline1;
    float scanline2;
    float beam_min;
    float beam_max;
    float beam_size;
    float h_sharp;
    float s_sharp;
    float warpX;
    float warpY;
    float glow;
    float shadowMask;
    float masksize;
    float ring;
    float no_scanlines;
    float tds;
    float clips;
    float hiscan;
    float rolling_scan;
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

