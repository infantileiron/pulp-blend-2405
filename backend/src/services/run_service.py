import logging
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select,update
from ..models.run import BlendRun
from ..models.scenario import BlendScenario
from ..models.dataset import PulpDataset
from ..models.spec import QualitySpec
from ..models.common import now
from ..constants.enums import PROPERTIES
from ..utils.queue import enqueue
from .linear_blend import solve
from .lhs_robustness import simulate

logger=logging.getLogger("pulp.runs")
# 租约秒数：worker 存活期间按更短间隔续租；超过该时长未续租视为中断，可被其他 worker 接管
LEASE_SECONDS=30
TERMINAL_STATUSES=("completed","infeasible","failed")
ACTIVE_STATUSES=("queued","running")

def _snapshot(scenario,data,spec_row):
 # 深拷贝 JSON 载荷，固化建单时刻的原浆、规格与抽样设置；后续实体改动不影响恢复重算
 spec={key+"_"+side:getattr(spec_row,key+"_"+side) for key in PROPERTIES for side in ["min","max"]}
 return {"scenario_id":scenario.id,"scenario_name":scenario.name,
         "dataset_id":data.id,"dataset_name":data.name,
         "spec_id":spec_row.id,"spec_name":spec_row.name,
         "n_samples":scenario.n_samples,"seed":scenario.seed,
         "perturb_cost":bool(scenario.perturb_cost),
         "materials":[dict(m) for m in data.materials],"spec":dict(spec)}

def create(db,body):
 scenario=db.get(BlendScenario,body.scenario_id)
 if scenario is None:raise HTTPException(422,"试算情景不存在")
 data=db.get(PulpDataset,scenario.dataset_id)
 spec_row=db.get(QualitySpec,scenario.spec_id)
 if data is None or spec_row is None:raise HTTPException(422,"试算情景引用的原浆数据或质量规格不存在")
 # 同一情景已有排队/运行中的试算时直接返回它：重复投递不产生第二条，也不会再算一遍
 existing=db.scalar(select(BlendRun).where(BlendRun.scenario_id==scenario.id,BlendRun.status.in_(ACTIVE_STATUSES)).order_by(BlendRun.created_at.asc()))
 if existing is not None:return existing
 row=BlendRun(id=str(uuid4()),scenario_id=scenario.id,status="queued",result={},error="",
              input_snapshot=_snapshot(scenario,data,spec_row),attempts=0)
 db.add(row);db.commit()
 # Redis 仅负责唤醒 worker；入队失败不丢单，扫描兜底会捡起 queued 行
 try:enqueue(row.id)
 except Exception:logger.exception("Redis 入队失败，试算 %s 等待扫描恢复",row.id)
 return row

def _lease_takeover_allowed(row,worker_id,ts,lease_seconds):
 # 活跃租约（含自己持有的）一律不可抢：串行 worker 不会重复认领在途试算
 # 无锁可直接进入；过期租约任何 worker 都可接管恢复
 if not row.locked_by or row.locked_at is None:return True
 return (ts-row.locked_at).total_seconds()>lease_seconds

def claim_run(db,run_id,worker_id,lease_seconds=LEASE_SECONDS):
 """原子认领指定试算（消息驱动、重复投递去重的统一入口）。

 终态行永远认领失败；别人持有的活跃租约不可抢；过期租约可接管。
 条件 UPDATE 附带原 locked_by 谓词，并发争抢时行锁保证只有一个 UPDATE 命中。"""
 ts=now()
 row=db.get(BlendRun,run_id)
 if row is None or row.status in TERMINAL_STATUSES:return False
 if not _lease_takeover_allowed(row,worker_id,ts,lease_seconds):return False
 previous_lock=row.locked_by
 affected=db.execute(update(BlendRun)
  .where(BlendRun.id==run_id,BlendRun.status.in_(ACTIVE_STATUSES),BlendRun.locked_by==previous_lock)
  .values(status="running",locked_by=worker_id,locked_at=ts,attempts=BlendRun.attempts+1,started_at=ts)
  .execution_options(synchronize_session=False))
 db.commit();db.expire_all()
 if affected.rowcount and previous_lock:logger.warning("试算 %s 租约过期（原持有者 %s），由 %s 接管恢复",run_id,previous_lock,worker_id)
 return bool(affected.rowcount)

def claim_next(db,worker_id,lease_seconds=LEASE_SECONDS):
 """扫描认领一条可运行试算（含中断后租约过期的 running 行），返回 run_id 或 None。"""
 ts=now()
 candidates=db.scalars(select(BlendRun).where(BlendRun.status.in_(ACTIVE_STATUSES)).order_by(BlendRun.created_at.asc())).all()
 for row in candidates:
  if not _lease_takeover_allowed(row,worker_id,ts,lease_seconds):continue
  previous_lock=row.locked_by
  affected=db.execute(update(BlendRun)
   .where(BlendRun.id==row.id,BlendRun.status.in_(ACTIVE_STATUSES),BlendRun.locked_by==previous_lock)
   .values(status="running",locked_by=worker_id,locked_at=ts,attempts=BlendRun.attempts+1,started_at=ts)
   .execution_options(synchronize_session=False))
  db.commit();db.expire_all()
  if affected.rowcount:
   if previous_lock:logger.warning("试算 %s 租约过期（原持有者 %s），由 %s 接管恢复",row.id,previous_lock,worker_id)
   return row.id
 return None

def heartbeat(db,run_id,worker_id):
 """续租。仅持有者可续；行已进入终态或租约易主时返回 False，提示心跳线程退出。"""
 ts=now()
 result=db.execute(update(BlendRun)
  .where(BlendRun.id==run_id,BlendRun.locked_by==worker_id,BlendRun.status=="running")
  .values(locked_at=ts).execution_options(synchronize_session=False))
 db.commit();db.expire_all()
 return result.rowcount==1

def _finish(db,run_id,worker_id,status,result=None,error=""):
 """条件落结果：仅当前持有者且仍在 running 才能写终态，重复/过期写入被拒绝，杜绝重复落结果。"""
 ts=now()
 values={"status":status,"error":error[:1000],"finished_at":ts,"locked_by":"","locked_at":None}
 if result is not None:values["result"]=result
 affected=db.execute(update(BlendRun)
  .where(BlendRun.id==run_id,BlendRun.status=="running",BlendRun.locked_by==worker_id)
  .values(**values).execution_options(synchronize_session=False))
 db.commit();db.expire_all()
 return affected.rowcount==1

def compute(db,run_id,worker_id="inline"):
 """认领并计算同一把锁内完成：重复消息、并发 worker 只有一个能进入实际计算。"""
 if not claim_run(db,run_id,worker_id):return
 run_claimed(db,run_id,worker_id)

def run_claimed(db,run_id,worker_id):
 """执行已被本 worker 认领的试算；结束时条件落结果，丢锁则放弃写入。"""
 row=db.get(BlendRun,run_id)
 if row is None or row.status!="running" or row.locked_by!=worker_id:return
 try:
  snap=row.input_snapshot or {}
  materials=snap.get("materials")
  spec=snap.get("spec")
  if not materials or not spec:
   # 兼容历史行（补列前创建、且未完成的试算）：回退到关联实体，并补固化快照
   scenario=db.get(BlendScenario,row.scenario_id);data=db.get(PulpDataset,scenario.dataset_id);spec_row=db.get(QualitySpec,scenario.spec_id)
   materials=[dict(m) for m in data.materials]
   spec={key+"_"+side:getattr(spec_row,key+"_"+side) for key in PROPERTIES for side in ["min","max"]}
   snapshot=_snapshot(scenario,data,spec_row)
   db.execute(update(BlendRun).where(BlendRun.id==row.id).values(input_snapshot=snapshot).execution_options(synchronize_session=False));db.commit();db.expire_all()
   row=db.get(BlendRun,run_id);snap=row.input_snapshot
  lp=solve(materials,spec)
  robust=simulate(materials,[r["share"] for r in lp["shares"]],spec,snap["n_samples"],snap["seed"],snap["perturb_cost"]) if lp["feasible"] else None
  result={"dataset_name":snap.get("dataset_name"),"spec_name":snap.get("spec_name"),"scenario_name":snap.get("scenario_name"),
          "spec":spec,"lp":lp,"robustness":robust,"materials":materials,
          "cost_unit":"CNY/tonne","property_units":{"strength":"模拟强度指数","whiteness":"%","recycled":"fraction"},
          "input_snapshot":{k:v for k,v in snap.items() if k not in ("materials","spec")}}
  _finish(db,run_id,worker_id,"completed" if lp["feasible"] else "infeasible",result=result)
 except Exception as e:
  logger.exception("试算 %s 第 %s 次尝试失败",run_id,row.attempts)
  _finish(db,run_id,worker_id,"failed",error=str(e))

def requeue_stuck(db,lease_seconds=LEASE_SECONDS):
 """显式恢复入口：把 worker 中断且租约过期的僵死 running 退回排队（输入快照不变）。
 正常路径下 claim_run/claim_next 会直接接管过期租约，本函数供 worker 启动扫描与测试使用。"""
 ts=now()
 rows=db.scalars(select(BlendRun).where(BlendRun.status=="running")).all()
 recovered=[]
 for row in rows:
  if row.locked_by and row.locked_at and (ts-row.locked_at).total_seconds()<=lease_seconds:continue
  db.execute(update(BlendRun).where(BlendRun.id==row.id,BlendRun.status=="running",BlendRun.locked_by==row.locked_by)
   .values(status="queued",locked_by="",locked_at=None).execution_options(synchronize_session=False))
  recovered.append(row.id)
 if recovered:db.commit();db.expire_all();logger.warning("恢复中断试算回排队：%s",recovered)
 return recovered
