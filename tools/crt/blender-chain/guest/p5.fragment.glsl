#version 330

layout(std140) uniform LIBRA_UBO_FRAGMENT
{
    vec4 SourceSize;
    mat4 MVP;
} LIBRA_UBO_FRAGMENT_INSTANCE;

struct LIBRA_PUSH_FRAGMENT
{
    vec4 OriginalSize;
    vec4 OutputSize;
    uint FrameCount;
    float GAMMA_INPUT;
    float inter;
    float interm;
    float iscan;
    float intres;
    float iscans;
    float downsample_levelx;
    float downsample_levely;
    float gamma_out;
    float vga_mode;
    float hiscan;
};

uniform LIBRA_PUSH_FRAGMENT LIBRA_PUSH_FRAGMENT_INSTANCE;

uniform sampler2D LIBRA_TEXTURE_PrePass;

in vec2 LIBRA_VARYING_0;
layout(location = 0) out vec4 FragColor;

vec3 fetch_pixel(vec2 coord)
{
    vec2 dx = vec2(LIBRA_UBO_FRAGMENT_INSTANCE.SourceSize.z, 0.0) * LIBRA_PUSH_FRAGMENT_INSTANCE.downsample_levelx;
    vec2 dy = vec2(0.0, LIBRA_UBO_FRAGMENT_INSTANCE.SourceSize.w) * LIBRA_PUSH_FRAGMENT_INSTANCE.downsample_levely;
    vec2 d1 = dx + dy;
    vec2 d2 = dx - dy;
    float sum = 15.0;
    vec3 result = ((((((((texture(LIBRA_TEXTURE_PrePass, coord).xyz * 3.0) + (texture(LIBRA_TEXTURE_PrePass, coord + dx).xyz * 2.0)) + (texture(LIBRA_TEXTURE_PrePass, coord - dx).xyz * 2.0)) + (texture(LIBRA_TEXTURE_PrePass, coord + dy).xyz * 2.0)) + (texture(LIBRA_TEXTURE_PrePass, coord - dy).xyz * 2.0)) + texture(LIBRA_TEXTURE_PrePass, coord + d1).xyz) + texture(LIBRA_TEXTURE_PrePass, coord - d1).xyz) + texture(LIBRA_TEXTURE_PrePass, coord + d2).xyz) + texture(LIBRA_TEXTURE_PrePass, coord - d2).xyz;
    return result / vec3(sum);
}

vec3 plant(vec3 tar, float r)
{
    float t = max(max(tar.x, tar.y), tar.z) + 9.9999997473787516355514526367188e-06;
    return (tar * r) / vec3(t);
}

void main()
{
    vec3 c1 = texture(LIBRA_TEXTURE_PrePass, LIBRA_VARYING_0).xyz;
    vec3 c2 = texture(LIBRA_TEXTURE_PrePass, LIBRA_VARYING_0 + vec2(0.0, LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.w)).xyz;
    if ((LIBRA_PUSH_FRAGMENT_INSTANCE.downsample_levelx + LIBRA_PUSH_FRAGMENT_INSTANCE.downsample_levely) > 0.02500000037252902984619140625)
    {
        vec2 param = LIBRA_VARYING_0;
        c1 = fetch_pixel(param);
        vec2 param_1 = LIBRA_VARYING_0 + vec2(0.0, LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.w);
        c2 = fetch_pixel(param_1);
    }
    vec3 c = c1;
    float intera = 1.0;
    float gamma_in = LIBRA_PUSH_FRAGMENT_INSTANCE.GAMMA_INPUT;
    float m1 = max(max(c1.x, c1.y), c1.z);
    float m2 = max(max(c2.x, c2.y), c2.z);
    vec3 df = abs(c1 - c2);
    float d = max(max(df.x, df.y), df.z);
    if (LIBRA_PUSH_FRAGMENT_INSTANCE.interm == 2.0)
    {
        d = mix(0.100000001490116119384765625 * d, 10.0 * d, step(m1 / (m2 + 9.9999997473787516355514526367188e-05), m2 / (m1 + 9.9999997473787516355514526367188e-05)));
    }
    float r = m1;
    float yres_div = 1.0;
    if (LIBRA_PUSH_FRAGMENT_INSTANCE.intres > 1.25)
    {
        yres_div = LIBRA_PUSH_FRAGMENT_INSTANCE.intres;
    }
    bool hscan = LIBRA_PUSH_FRAGMENT_INSTANCE.hiscan > 0.5;
    bool _287 = LIBRA_PUSH_FRAGMENT_INSTANCE.inter <= (LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.y / yres_div);
    bool _293;
    if (_287)
    {
        _293 = LIBRA_PUSH_FRAGMENT_INSTANCE.interm > 0.5;
    }
    else
    {
        _293 = _287;
    }
    bool _299;
    if (_293)
    {
        _299 = LIBRA_PUSH_FRAGMENT_INSTANCE.intres != 1.0;
    }
    else
    {
        _299 = _293;
    }
    bool _305;
    if (_299)
    {
        _305 = LIBRA_PUSH_FRAGMENT_INSTANCE.intres != 0.5;
    }
    else
    {
        _305 = _299;
    }
    bool _312;
    if (_305)
    {
        _312 = LIBRA_PUSH_FRAGMENT_INSTANCE.vga_mode < 0.5;
    }
    else
    {
        _312 = _305;
    }
    if (_312 || hscan)
    {
        intera = 0.25;
        float line_no = floor(mod(LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.y * LIBRA_VARYING_0.y, 2.0));
        float frame_no = floor(mod(float(LIBRA_PUSH_FRAGMENT_INSTANCE.FrameCount), 2.0));
        float ii = abs(line_no - frame_no);
        bool _343 = LIBRA_PUSH_FRAGMENT_INSTANCE.interm < 3.5;
        bool _351;
        if (!_343)
        {
            _351 = LIBRA_PUSH_FRAGMENT_INSTANCE.interm > 5.5;
        }
        else
        {
            _351 = _343;
        }
        if (_351)
        {
            if (LIBRA_PUSH_FRAGMENT_INSTANCE.interm == 6.0)
            {
                c = mix(c2, c1, vec3(ii));
            }
            else
            {
                vec3 param_2 = mix(c2, c2 * c2, vec3(LIBRA_PUSH_FRAGMENT_INSTANCE.iscans));
                float param_3 = max(max(c2.x, c2.y), c2.z);
                c2 = plant(param_2, param_3);
                r = max(m1 * ii, (1.0 - LIBRA_PUSH_FRAGMENT_INSTANCE.iscan) * min(m1, m2));
                vec3 param_4 = mix(mix(c1, c2, vec3(min(mix(m1, 1.0 - m2, min(m1, 1.0 - m1)) / (d + 9.9999997473787516355514526367188e-06), 1.0))), c1, vec3(ii));
                float param_5 = r;
                c = plant(param_4, param_5);
                if (LIBRA_PUSH_FRAGMENT_INSTANCE.interm == 3.0)
                {
                    c = mix(c2, c1, vec3(ii)) * (1.0 - (0.5 * LIBRA_PUSH_FRAGMENT_INSTANCE.iscan));
                }
            }
        }
        if (LIBRA_PUSH_FRAGMENT_INSTANCE.interm == 4.0)
        {
            vec3 param_6 = mix(c, c * c, vec3(0.5 * LIBRA_PUSH_FRAGMENT_INSTANCE.iscans));
            float param_7 = max(max(c.x, c.y), c.z);
            c = plant(param_6, param_7) * (1.0 - (0.5 * LIBRA_PUSH_FRAGMENT_INSTANCE.iscan));
        }
        if (LIBRA_PUSH_FRAGMENT_INSTANCE.interm == 5.0)
        {
            c = mix(c2, c1, vec3(0.5));
            vec3 param_8 = mix(c, c * c, vec3(0.5 * LIBRA_PUSH_FRAGMENT_INSTANCE.iscans));
            float param_9 = max(max(c.x, c.y), c.z);
            c = plant(param_8, param_9) * (1.0 - (0.5 * LIBRA_PUSH_FRAGMENT_INSTANCE.iscan));
        }
        if (hscan)
        {
            c = c1;
        }
    }
    if (LIBRA_PUSH_FRAGMENT_INSTANCE.vga_mode > 0.5)
    {
        c = c1;
        if (LIBRA_PUSH_FRAGMENT_INSTANCE.inter <= LIBRA_PUSH_FRAGMENT_INSTANCE.OriginalSize.y)
        {
            intera = 0.75;
        }
        else
        {
            intera = 0.5;
        }
    }
    c = pow(c, vec3(gamma_in));
    if (LIBRA_VARYING_0.x > 0.5)
    {
        gamma_in = intera;
    }
    else
    {
        gamma_in = 1.0 / gamma_in;
    }
    FragColor = vec4(c, gamma_in);
}

