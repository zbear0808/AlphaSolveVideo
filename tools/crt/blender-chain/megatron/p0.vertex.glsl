#version 330

layout(std140) uniform LIBRA_UBO_VERTEX
{
    mat4 MVP;
    vec4 SourceSize;
    vec4 OriginalSize;
    vec4 OutputSize;
    uint FrameCount;
    uint HDRMode;
} LIBRA_UBO_VERTEX_INSTANCE;

struct LIBRA_PUSH_VERTEX
{
    float hcrt_colour_space;
    float hcrt_lcd_resolution;
    float hcrt_lcd_subpixel;
    float hcrt_colour_system;
    float hcrt_phosphor_set;
    float hcrt_white_temperature_D65;
    float hcrt_white_temperature_D93;
    float hcrt_brightness;
    float hcrt_contrast;
    float hcrt_saturation;
    float hcrt_gamma_in;
    float hcrt_gamma_cutoff;
    float hcrt_colour_boost_factor;
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

