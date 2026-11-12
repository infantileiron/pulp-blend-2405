import numpy as np
from ..constants.enums import PROPERTIES,CONSTRAINT_TOLERANCE

def latin_hypercube(n,d,seed):
 if not isinstance(n,int) or n<2 or not isinstance(d,int) or d<1:raise ValueError("LHS样本数与维数无效")
 rng=np.random.default_rng(seed);u=np.empty((n,d))
 for j in range(d):u[:,j]=(rng.permutation(n)+rng.random(n))/n
 return u

def simulate(materials,shares,spec,n_samples,seed,perturb_cost):
 x=np.asarray(shares,dtype=float)
 if len(x)!=len(materials) or not np.isfinite(x).all() or (x<-CONSTRAINT_TOLERANCE).any() or abs(float(x.sum())-1)>CONSTRAINT_TOLERANCE:raise ValueError("固定配方比例无效")
 dimensions=[]
 for m in materials:
  for key in PROPERTIES:dimensions.append({"material_id":m["material_id"],"property":key,"low":m[key]-m[key+"_width"],"high":m[key]+m[key+"_width"]})
  if perturb_cost:dimensions.append({"material_id":m["material_id"],"property":"cost","low":m["cost"]-m["cost_width"],"high":m["cost"]+m["cost_width"]})
 u=latin_hypercube(n_samples,len(dimensions),seed);values={key:np.zeros(n_samples) for key in PROPERTIES};cost=np.zeros(n_samples);column=0
 for i,m in enumerate(materials):
  for key in PROPERTIES:
   lo,hi=m[key]-m[key+"_width"],m[key]+m[key+"_width"]
   values[key]+=x[i]*(lo+(hi-lo)*u[:,column]);column+=1
  if perturb_cost:
   cost+=x[i]*(m["cost"]-m["cost_width"]+2*m["cost_width"]*u[:,column]);column+=1
  else:cost+=x[i]*m["cost"]
 compliant=np.ones(n_samples,dtype=bool)
 for key in PROPERTIES:compliant&=(values[key]>=spec[key+"_min"]-CONSTRAINT_TOLERANCE)&(values[key]<=spec[key+"_max"]+CONSTRAINT_TOLERANCE)
 samples=[{"index":i+1,"cost":float(cost[i]),"compliant":bool(compliant[i]),**{key:float(values[key][i]) for key in PROPERTIES}} for i in range(n_samples)]
 return {"n_samples":n_samples,"passed":int(compliant.sum()),"failed":int((~compliant).sum()),"compliance_rate":float(compliant.mean()),"cost_p05":float(np.quantile(cost,.05)),"cost_p50":float(np.quantile(cost,.5)),"cost_p95":float(np.quantile(cost,.95)),"seed":seed,"perturb_cost":perturb_cost,"dimension_count":len(dimensions),"dimensions":dimensions,"samples":samples,"fixed_shares":x.tolist(),"comparison_tolerance":CONSTRAINT_TOLERANCE,"assumption":"求得配方固定不变；每原浆属性独立均匀扰动，LHS各维分层。仅模拟线性加权混合；合规率为通过数/样本数，成本区间为模拟分位，不是认证或置信区间。"}
