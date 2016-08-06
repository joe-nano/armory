#version 450

#ifdef GL_ES
precision mediump float;
#endif

uniform sampler2D tex;
uniform sampler2D gbuffer0;

uniform vec2 dir;
uniform vec2 screenSize;

in vec2 texCoord;

const float blurWeights[10] = float[] (0.132572, 0.125472, 0.106373, 0.08078, 0.05495, 0.033482, 0.018275, 0.008934, 0.003912, 0.001535);
const float discardThreshold = 0.95;

vec3 result = vec3(0.0);

vec2 octahedronWrap(vec2 v) {
    return (1.0 - abs(v.yx)) * (vec2(v.x >= 0.0 ? 1.0 : -1.0, v.y >= 0.0 ? 1.0 : -1.0));
}

vec3 getNor(vec2 enc) {
    vec3 n;
    n.z = 1.0 - abs(enc.x) - abs(enc.y);
    n.xy = n.z >= 0.0 ? enc.xy : octahedronWrap(enc.xy);
    n = normalize(n);
    return n;
}

float doBlur(float blurWeight, int pos, vec3 nor) {
    vec2 texstep = dir / screenSize;
    
    vec3 nor2 = getNor(texture(gbuffer0, texCoord + pos * texstep).rg);
    float influenceFactor = 1.0;//step(discardThreshold, dot(nor2, nor));
    vec3 col = texture(tex, texCoord + (pos + 0.5) * texstep).rgb;
    result += col * blurWeight * influenceFactor;
    float weight = blurWeight * influenceFactor;
    
    nor2 = getNor(texture(gbuffer0, texCoord - pos * texstep).rg);
    influenceFactor = 1.0;//step(discardThreshold, dot(nor2, nor));
    col = texture(tex, texCoord - (pos + 0.5) * texstep).rgb;
    result += col * blurWeight * influenceFactor;
    weight += blurWeight * influenceFactor;
    
    return weight;
}

void main() {
    vec2 step = dir / screenSize;

    vec3 result = texture(tex, texCoord + (step * 4.5)).rgb;
    result += texture(tex, texCoord + (step * 3.5)).rgb;
    result += texture(tex, texCoord + (step * 2.5)).rgb;
    result += texture(tex, texCoord + step * 1.5).rgb;
    result += texture(tex, texCoord).rgb;
    result += texture(tex, texCoord - step * 1.5).rgb;
    result += texture(tex, texCoord - (step * 2.5)).rgb;
    result += texture(tex, texCoord - (step * 3.5)).rgb;
    result += texture(tex, texCoord - (step * 4.5)).rgb;
    result /= vec3(9.0);

    gl_FragColor.rgb = vec3(result);


    
	// vec3 nor = getNor(texture(gbuffer0, texCoord).rg);
 //    float weight = 0.0;
	
	// // for (int i = 0; i < 9; i++) {
 //        float blurWeight = blurWeights[0];
        
 //        vec3 col = texture(tex, texCoord).rgb;
 //        result += col * blurWeights[0];
 //        weight += blurWeight;
        
 //        weight += doBlur(blurWeights[1], 1, nor);
 //        weight += doBlur(blurWeights[1], 2, nor);
 //        weight += doBlur(blurWeights[2], 3, nor);
 //        weight += doBlur(blurWeights[2], 4, nor);
 //        weight += doBlur(blurWeights[3], 5, nor);
 //        weight += doBlur(blurWeights[4], 6, nor);
 //        weight += doBlur(blurWeights[5], 7, nor);
 //        weight += doBlur(blurWeights[6], 8, nor);
 //        weight += doBlur(blurWeights[7], 9, nor);
 //        weight += doBlur(blurWeights[8], 10, nor);
 //    // }

 //    result /= weight;
 //    gl_FragColor = vec4(result.rgb, 1.0);
    
}