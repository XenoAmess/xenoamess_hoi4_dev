# Development-only experiment: native-size transparent carrier at sampler 0,
# untouched full-resolution portrait at sampler 1. No raster downsampling.
Includes = { }

PixelShader = {
 Samplers = {
  HdPortrait = {
   Index = 1
   MagFilter = "Linear"
   MinFilter = "Linear"
   MipFilter = "None"
   AddressU = "Clamp"
   AddressV = "Clamp"
  }
 }
}

VertexStruct VS_INPUT {
 float3 vPosition : POSITION;
 float2 vTexCoord : TEXCOORD0;
};
VertexStruct VS_OUTPUT {
 float4 vPosition : PDX_POSITION;
 float2 uv : TEXCOORD0;
};
ConstantBuffer( 0, 0 ) {
 float4x4 WorldViewProjectionMatrix;
 float4 FlagCoords;
};

VertexShader = {
 MainCode HdVertex [[
  VS_OUTPUT main(const VS_INPUT v) {
   VS_OUTPUT result;
   result.vPosition = mul(WorldViewProjectionMatrix, float4(v.vPosition.xyz, 1));
   result.uv = v.vTexCoord;
   return result;
  }
 ]]
}
PixelShader = {
 MainCode HdPixel [[
  float4 main(VS_OUTPUT v) : PDX_COLOR {
   return tex2D(HdPortrait, v.uv);
  }
 ]]
}
BlendState BlendState {
 BlendEnable = yes
 SourceBlend = "src_alpha"
 DestBlend = "inv_src_alpha"
}
Effect Up { VertexShader = "HdVertex" PixelShader = "HdPixel" }
Effect Down { VertexShader = "HdVertex" PixelShader = "HdPixel" }
Effect Over { VertexShader = "HdVertex" PixelShader = "HdPixel" }
Effect Disable { VertexShader = "HdVertex" PixelShader = "HdPixel" }
