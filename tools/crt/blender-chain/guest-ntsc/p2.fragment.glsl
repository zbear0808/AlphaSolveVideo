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
    float PR;
    float PG;
    float PB;
    float esrc;
    float bth;
};

uniform LIBRA_PUSH_FRAGMENT LIBRA_PUSH_FRAGMENT_INSTANCE;

uniform sampler2D LIBRA_TEXTURE_OriginalHistory0;
uniform sampler2D LIBRA_TEXTURE_Source;
uniform sampler2D LIBRA_TEXTURE_AfterglowPassFeedback;

in vec2 LIBRA_VARYING_0;
layout(location = 0) out vec4 FragColor;

void main()
{
    vec2 dx = vec2(LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.z, 0.0);
    vec2 dy = vec2(0.0, LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.w);
    vec3 color0 = texture(LIBRA_TEXTURE_OriginalHistory0, LIBRA_VARYING_0).xyz;
    vec3 color1 = texture(LIBRA_TEXTURE_OriginalHistory0, LIBRA_VARYING_0 - dx).xyz;
    vec3 color2 = texture(LIBRA_TEXTURE_OriginalHistory0, LIBRA_VARYING_0 + dx).xyz;
    vec3 color3 = texture(LIBRA_TEXTURE_OriginalHistory0, LIBRA_VARYING_0 - dy).xyz;
    vec3 color4 = texture(LIBRA_TEXTURE_OriginalHistory0, LIBRA_VARYING_0 + dy).xyz;
    if (LIBRA_PUSH_FRAGMENT_INSTANCE.esrc > 1.5)
    {
        color0 = texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0).xyz;
        color1 = texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0 - dx).xyz;
        color2 = texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0 + dx).xyz;
        color3 = texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0 - dy).xyz;
        color4 = texture(LIBRA_TEXTURE_Source, LIBRA_VARYING_0 + dy).xyz;
    }
    vec3 color = (((((color0 * 2.5) + color1) + color2) + color3) + color4) / vec3(6.5);
    vec3 accumulate = texture(LIBRA_TEXTURE_AfterglowPassFeedback, LIBRA_VARYING_0).xyz;
    float w = 1.0;
    float b = LIBRA_PUSH_FRAGMENT_INSTANCE.bth / 255.0;
    float c = max(max(color0.x, color0.y), color0.z);
    w = smoothstep(b, 2.0 * b, c);
    vec3 result = mix(max(mix(color, accumulate, vec3(0.4900000095367431640625) + vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.PR, LIBRA_PUSH_FRAGMENT_INSTANCE.PG, LIBRA_PUSH_FRAGMENT_INSTANCE.PB)) - vec3(0.0049019609577953815460205078125), vec3(0.0)), color, vec3(w));
    FragColor = vec4(result, w);
}

