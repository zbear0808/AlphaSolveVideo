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
};

uniform LIBRA_PUSH_FRAGMENT LIBRA_PUSH_FRAGMENT_INSTANCE;

uniform sampler2D LIBRA_TEXTURE_Source;

layout(location = 0) out vec4 FragColor;
in vec2 LIBRA_VARYING_0;

void main()
{
    FragColor = vec4(texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0).xyz, 1.0);
}

