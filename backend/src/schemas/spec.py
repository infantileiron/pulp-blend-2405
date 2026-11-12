from pydantic import BaseModel,Field,model_validator
class SpecCreate(BaseModel):
 name:str=Field(min_length=2,max_length=180)
 strength_min:float=Field(default=70,ge=0,le=100,allow_inf_nan=False)
 strength_max:float=Field(default=100,ge=0,le=100,allow_inf_nan=False)
 whiteness_min:float=Field(default=80,ge=0,le=100,allow_inf_nan=False)
 whiteness_max:float=Field(default=100,ge=0,le=100,allow_inf_nan=False)
 recycled_min:float=Field(default=.25,ge=0,le=1,allow_inf_nan=False)
 recycled_max:float=Field(default=1,ge=0,le=1,allow_inf_nan=False)
 description:str=Field(default="",max_length=2000)
 @model_validator(mode="after")
 def ordered(self):
  for key in ["strength","whiteness","recycled"]:
   if getattr(self,key+"_min")>getattr(self,key+"_max"):raise ValueError("质量下界不能高于上界")
  return self
