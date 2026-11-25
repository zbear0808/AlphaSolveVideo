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
    float smart_ei;
    float ei_limit;
    float sth;
    float overscanX;
    float overscanY;
    float VShift;
    float c_shape;
    float intres;
    float prescalex;
    float scan_falloff;
    float bloom_dist;
    float scangamma;
    float bmask1;
    float hmask1;
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
    float gsl;
    float scanline1;
    float scanline2;
    float beam_min;
    float beam_max;
    float beam_size;
    float h_sharp;
    float s_sharp;
    float csize;
    float bsize1;
    float warpX;
    float warpY;
    float glow;
    float spike;
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

