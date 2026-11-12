import math
import numpy as np
from scipy.optimize import linprog
from ..constants.enums import PROPERTIES,CONSTRAINT_TOLERANCE

def solve(materials,spec):
 costs=np.array([m["cost"] for m in materials],dtype=float)
 if len(materials)<2 or not np.isfinite(costs).all() or (costs<=0).any():raise ValueError("原浆成本或数量无效")
 A=[];b=[]
 for key in PROPERTIES:
  values=np.array([m[key] for m in materials],dtype=float)
  A.extend([values,-values]);b.extend([spec[key+"_max"],-spec[key+"_min"]])
 bounds=[(m["min_share"],m["max_share"]) for m in materials]
 result=linprog(costs,A_ub=np.array(A),b_ub=np.array(b),A_eq=np.ones((1,len(materials))),b_eq=[1.],bounds=bounds,method="highs")
 if result.status==2:return {"feasible":False,"shares":[],"nominal_cost":None,"qualities":[],"reason":"供给上下限与质量界限无法同时满足","solver_status":int(result.status)}
 if not result.success:raise ValueError("线性规划求解未完成："+str(result.message))
 x=result.x
 if not np.isfinite(x).all() or abs(float(x.sum())-1)>CONSTRAINT_TOLERANCE or np.max(np.array(A)@x-np.array(b))>CONSTRAINT_TOLERANCE:raise ValueError("求解结果未通过约束校验")
 if any(x[i]<m["min_share"]-CONSTRAINT_TOLERANCE or x[i]>m["max_share"]+CONSTRAINT_TOLERANCE for i,m in enumerate(materials)):raise ValueError("供给比例未通过约束校验")
 qualities=[]
 for key in PROPERTIES:
  value=float(np.dot(x,[m[key] for m in materials]));qualities.append({"property":key,"value":value,"minimum":spec[key+"_min"],"maximum":spec[key+"_max"],"lower_slack":value-spec[key+"_min"],"upper_slack":spec[key+"_max"]-value})
 shares=[{"material_id":m["material_id"],"name":m["name"],"share":float(x[i]),"unit_cost":m["cost"],"min_share":m["min_share"],"max_share":m["max_share"],"lower_slack":float(x[i])-m["min_share"],"upper_slack":m["max_share"]-float(x[i])} for i,m in enumerate(materials)]
 return {"feasible":True,"shares":shares,"nominal_cost":float(costs@x),"qualities":qualities,"reason":"","solver_status":0,"share_sum":float(x.sum()),"constraint_tolerance":CONSTRAINT_TOLERANCE}
