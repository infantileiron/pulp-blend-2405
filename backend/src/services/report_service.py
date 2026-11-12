import csv,io,json
from uuid import uuid4
from sqlalchemy import select
from fastapi import HTTPException
from ..models.review import FormulaReview
from ..models.run import BlendRun
from ..models.report import Report

def create(db,body):
 review=db.get(FormulaReview,body.review_id)
 if review is None or review.state!="approved":raise HTTPException(409,"报告须关联已批准配方复核")
 existing=db.scalar(select(Report).where(Report.review_id==body.review_id))
 if existing:return existing
 run=db.get(BlendRun,review.run_id);row=Report(id=str(uuid4()),review_id=review.id,title=body.title,snapshot={"result":run.result,"action":review.action,"reviewer":review.reviewer});db.add(row);db.commit();return row

def export(row,samples=False):
 result=row.snapshot["result"];lp=result["lp"];robust=result["robustness"];out=io.StringIO();writer=csv.writer(out)
 if samples:
  keys=["index","strength","whiteness","recycled","cost","compliant"];writer.writerow(keys+["quality_comparison_tolerance"])
  for sample in robust["samples"]:writer.writerow([sample[k] for k in keys]+[robust["comparison_tolerance"]])
 else:
  writer.writerow(["material_id","name","share","unit_cost_CNY_per_tonne","nominal_blend_cost","simulation_passed","simulation_n","simulation_rate","cost_p05","cost_p50","cost_p95","quality_comparison_tolerance"])
  for share in lp["shares"]:writer.writerow([share["material_id"],share["name"],share["share"],share["unit_cost"],lp["nominal_cost"],robust["passed"],robust["n_samples"],robust["compliance_rate"],robust["cost_p05"],robust["cost_p50"],robust["cost_p95"],robust["comparison_tolerance"]])
 return "\ufeff"+out.getvalue()
