import json
from sqlalchemy import select,func
from src.config.database import initialize,Session
from src.models import PulpDataset,QualitySpec,BlendScenario,BlendRun,FormulaReview,Report,User
from src.utils.security import hash_password
from src.services.run_service import compute

def make_materials():
 raw=[("P01","北杉针叶浆",5200,91,89,0,.65,3,1.5,0,200),("P02","南桉阔叶浆",3900,70,88,0,.7,3,2,0,160),("P03","高白竹浆",4200,74,91,0,.5,2.5,1.5,0,180),("P04","棉短绒浆",6500,98,94,0,.3,1.5,.8,0,250),("P05","净选回收浆",2600,56,74,.95,.6,4,3,.03,130),("P06","办公再生浆",3100,63,81,.88,.65,3,2,.04,150),("P07","未漂苇浆",2400,61,62,0,.25,4,3,0,120),("P08","机械木浆",2200,47,69,0,.25,5,3,0,100)]
 return [{"material_id":r[0],"name":r[1],"cost":r[2],"strength":r[3],"whiteness":r[4],"recycled":r[5],"min_share":0.,"max_share":r[6],"strength_width":r[7],"whiteness_width":r[8],"recycled_width":r[9],"cost_width":r[10]} for r in raw]

def seed():
 initialize()
 with Session() as db:
  for role in ["admin","analyst","viewer"]:
   email=role+"@pulp.demo"
   if not db.scalar(select(User).where(User.email==email)):db.add(User(id="user-"+role,email=email,role=role,password_hash=hash_password("PulpDemo2026!")))
  if not db.get(PulpDataset,"demo-dataset"):db.add(PulpDataset(id="demo-dataset",name="岑岳十一月原浆报价与检测",materials=make_materials(),description="8种模拟原浆；文件cenyue_pulp_202611.csv；属性仅按声明线性混合"))
  if not db.get(QualitySpec,"demo-spec"):db.add(QualitySpec(id="demo-spec",name="文化用纸模拟质量窗口",strength_min=70,strength_max=100,whiteness_min=80,whiteness_max=100,recycled_min=.25,recycled_max=1,description="强度指数、白度%、回收纤维率分别限定；不作工业认证"))
  db.commit()
  if not db.get(BlendScenario,"demo-scenario"):db.add(BlendScenario(id="demo-scenario",name="名义低成本与固定配方扰动",dataset_id="demo-dataset",spec_id="demo-spec",n_samples=400,seed=20261112,perturb_cost=True))
  db.commit()
  if not db.get(BlendRun,"demo-run"):db.add(BlendRun(id="demo-run",scenario_id="demo-scenario",status="queued",result={},error=""));db.commit();compute(db,"demo-run")
  if not db.get(FormulaReview,"demo-review"):db.add(FormulaReview(id="demo-review",run_id="demo-run",action="核查名义最优配方的活跃质量约束，并观察固定配方扰动通过数；线性混合和独立均匀误差仅为模拟假设。",state="approved",reviewer="admin@pulp.demo"))
  db.commit()
  if not db.get(Report,"demo-report"):db.add(Report(id="demo-report",review_id="demo-review",title="岑岳原浆配方稳健性底稿",snapshot={"result":db.get(BlendRun,"demo-run").result,"action":db.get(FormulaReview,"demo-review").action,"reviewer":"admin@pulp.demo"}))
  db.commit()
  return {cls.__tablename__:db.scalar(select(func.count()).select_from(cls)) for cls in [User,PulpDataset,QualitySpec,BlendScenario,BlendRun,FormulaReview,Report]}
if __name__=="__main__":print(json.dumps(seed(),ensure_ascii=False))
