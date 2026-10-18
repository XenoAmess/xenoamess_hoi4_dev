# Development hypothesis: a plain native-size opaque layout carrier keeps a
# normal sprite quad; the untouched HD portrait binds through masking slot 5.
# The carrier contains no portrait and is never a low-resolution substitute.
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
  HdMaskTexture = {
   Index = 5
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
 MainCode HdMaskVertex [[
  VS_OUTPUT main(const VS_INPUT v) {
   VS_OUTPUT result;
   result.vPosition = mul(WorldViewProjectionMatrix, float4(v.vPosition.xyz, 1));
   result.uv = v.vTexCoord;
   return result;
  }
 ]]
}
PixelShader = {
 MainCode HdMaskPixel [[
  float4 main(VS_OUTPUT v) : PDX_COLOR {
   return tex2D(HdMaskTexture, v.uv) * Color;
  }
 ]]
}
BlendState BlendState {
 BlendEnable = yes
 SourceBlend = "src_alpha"
 DestBlend = "inv_src_alpha"
}
Effect Up { VertexShader = "HdMaskVertex" PixelShader = "HdMaskPixel" }
Effect Down { VertexShader = "HdMaskVertex" PixelShader = "HdMaskPixel" }
Effect Over { VertexShader = "HdMaskVertex" PixelShader = "HdMaskPixel" }
Effect Disable { VertexShader = "HdMaskVertex" PixelShader = "HdMaskPixel" }
