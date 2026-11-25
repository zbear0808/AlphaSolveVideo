#version 330

layout(std140) uniform LIBRA_UBO_VERTEX
{
    mat4 MVP;
    vec4 SourceSize;
    vec4 OriginalSize;
    vec4 OutputSize;
    uint FrameCount;
    uint HDRMode;
    float BrightnessNits;
    float hcrt_r709_gamma_out;
    float hcrt_srgb_gamma_out;
    float hcrt_p3_gamma_out;
    float hcrt_adobe_gamma_out;
    float hcrt_r709_gamma_cutoff;
    float hcrt_srgb_gamma_cutoff;
    float hcrt_h_size;
    float hcrt_v_size;
    float hcrt_h_cent;
    float hcrt_v_cent;
} LIBRA_UBO_VERTEX_INSTANCE;

struct LIBRA_PUSH_VERTEX
{
    float hcrt_colour_space;
    float hcrt_max_nits;
    float hcrt_lcd_resolution;
    float hcrt_lcd_subpixel;
    float hcrt_red_vertical_convergence;
    float hcrt_green_vertical_convergence;
    float hcrt_blue_vertical_convergence;
    float hcrt_red_horizontal_convergence;
    float hcrt_green_horizontal_convergence;
    float hcrt_blue_horizontal_convergence;
    float hcrt_bloom_strength;
    float hcrt_crt_screen_type;
    float hcrt_crt_resolution;
    float hcrt_red_scanline_min;
    float hcrt_red_scanline_max;
    float hcrt_red_scanline_attack;
    float hcrt_green_scanline_min;
    float hcrt_green_scanline_max;
    float hcrt_green_scanline_attack;
    float hcrt_blue_scanline_min;
    float hcrt_blue_scanline_max;
    float hcrt_blue_scanline_attack;
    float hcrt_red_beam_sharpness;
    float hcrt_red_beam_attack;
    float hcrt_green_beam_sharpness;
    float hcrt_green_beam_attack;
    float hcrt_blue_beam_sharpness;
    float hcrt_blue_beam_attack;
};

uniform LIBRA_PUSH_VERTEX LIBRA_PUSH_VERTEX_INSTANCE;

layout(location = 0) in vec4 Position;
out vec2 LIBRA_VARYING_0;
layout(location = 1) in vec2 TexCoord;

void main()
{
    gl_Position = LIBRA_UBO_VERTEX_INSTANCE.MVP * Position;
    LIBRA_VARYING_0 = TexCoord * vec2(1.000010013580322265625);
}

