# Development experiment: full-HD texture stays intact; shader maps its entire
# UV range into the original-size region of the engine-created quad.
# Oversized quad hit testing and layout remain unqualified until actual tests.
Includes = { "buttonstate.fxh" }
PixelShader = {
 Samplers = {
  MapTexture = {
   Index = 0
   MagFilter = "Linear"
   MinFilter = "Linear"
   MipFilter = "None"
   AddressU = "Clamp"
   AddressV = "Clamp"
  }
 }
}
VertexStruct VS_OUTPUT {
 float4 vPosition : PDX_POSITION;
 float2 uv : TEXCOORD0;
};
VertexShader = {
 MainCode HdWindowVertex [[
  VS_OUTPUT main(const VS_INPUT v) {
   VS_OUTPUT result;
   result.vPosition = mul(WorldViewProjectionMatrix, float4(v.vPosition.xyz, 1));
   result.uv = v.vTexCoord;
   return result;
  }
 ]]
}
PixelShader = {
 MainCode HdWindowPixel [[
  float4 main(VS_OUTPUT v) : PDX_COLOR {
   float2 portraitUv = v.uv / float2(__WINDOW_X__, __WINDOW_Y__);
   clip(portraitUv);
   clip(1.0 - portraitUv);
   return tex2D(MapTexture, portraitUv) * Color;
  }
 ]]
}
BlendState BlendState {
 BlendEnable = yes
 SourceBlend = "src_alpha"
 DestBlend = "inv_src_alpha"
}
Effect Up { VertexShader = "HdWindowVertex" PixelShader = "HdWindowPixel" }
Effect Down { VertexShader = "HdWindowVertex" PixelShader = "HdWindowPixel" }
Effect Over { VertexShader = "HdWindowVertex" PixelShader = "HdWindowPixel" }
Effect Disable { VertexShader = "HdWindowVertex" PixelShader = "HdWindowPixel" }
