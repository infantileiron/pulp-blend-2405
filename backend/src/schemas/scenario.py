from pydantic import BaseModel,Field
class ScenarioCreate(BaseModel):
 name:str=Field(min_length=2,max_length=180)
 dataset_id:str
 spec_id:str
 n_samples:int=Field(default=400,ge=20,le=2000)
 seed:int=Field(default=20261112,ge=0,le=2147483647)
 perturb_cost:bool=True
