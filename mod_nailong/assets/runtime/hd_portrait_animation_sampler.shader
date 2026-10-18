# Development hypothesis: use a native-size empty layout carrier and bind the
# unchanged fullsize portrait through the stock sprite animation texture slot.
# Ignore animation coordinates and time: the portrait itself stays static.
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
  AnimatedTexture = {
   Index = 2
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
 MainCode HdCarrierVertex [[
  VS_OUTPUT main(const VS_INPUT v) {
   VS_OUTPUT result;
   result.vPosition = mul(WorldViewProjectionMatrix, float4(v.vPosition.xyz, 1));
   result.uv = v.vTexCoord;
   return result;
  }
 ]]
}
PixelShader = {
 MainCode HdCarrierPixel [[
  float4 main(VS_OUTPUT v) : PDX_COLOR {
   return tex2D(AnimatedTexture, v.uv) * Color;
  }
 ]]
}
BlendState BlendState {
 BlendEnable = yes
 SourceBlend = "src_alpha"
 DestBlend = "inv_src_alpha"
}
Effect Up { VertexShader = "HdCarrierVertex" PixelShader = "HdCarrierPixel" }
Effect Down { VertexShader = "HdCarrierVertex" PixelShader = "HdCarrierPixel" }
Effect Over { VertexShader = "HdCarrierVertex" PixelShader = "HdCarrierPixel" }
Effect Disable { VertexShader = "HdCarrierVertex" PixelShader = "HdCarrierPixel" }
