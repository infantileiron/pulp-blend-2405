from uuid import uuid4
from fastapi import HTTPException
from ..models.run import BlendRun
from ..models.scenario import BlendScenario
from ..models.dataset import PulpDataset
from ..models.spec import QualitySpec
from ..constants.enums import PROPERTIES
from ..utils.queue import enqueue
from .linear_blend import solve
from .lhs_robustness import simulate

def create(db,body):
 if not db.get(BlendScenario,body.scenario_id):raise HTTPException(422,"试算情景不存在")
 row=BlendRun(id=str(uuid4()),scenario_id=body.scenario_id,status="queued",result={},error="");db.add(row);db.commit()
 try:enqueue(row.id)
 except Exception:
  row.status="failed";row.error="Redis队列不可用，请稍后重试";db.commit();raise HTTPException(503,row.error)
 return row

def compute(db,run_id):
 row=db.get(BlendRun,run_id)
 if row is None or row.status not in ["queued","running"]:return
 row.status="running";db.commit()
 try:
  scenario=db.get(BlendScenario,row.scenario_id);data=db.get(PulpDataset,scenario.dataset_id);spec_row=db.get(QualitySpec,scenario.spec_id)
  spec={key+"_"+side:getattr(spec_row,key+"_"+side) for key in PROPERTIES for side in ["min","max"]};lp=solve(data.materials,spec)
  robust=simulate(data.materials,[r["share"] for r in lp["shares"]],spec,scenario.n_samples,scenario.seed,scenario.perturb_cost) if lp["feasible"] else None
  row.result={"dataset_name":data.name,"spec_name":spec_row.name,"scenario_name":scenario.name,"spec":spec,"lp":lp,"robustness":robust,"materials":data.materials,"cost_unit":"CNY/tonne","property_units":{"strength":"模拟强度指数","whiteness":"%","recycled":"fraction"}};row.status="completed" if lp["feasible"] else "infeasible"
 except Exception as e:row.status="failed";row.error=str(e)[:1000]
 db.commit()
