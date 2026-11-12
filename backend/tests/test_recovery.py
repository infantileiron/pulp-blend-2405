"""中断重启恢复：排队/运行中的试算在 worker 崩溃后自动恢复，且沿用建单时的原始输入。"""
from datetime import timedelta

from sqlalchemy import select,update

from src.models.run import BlendRun
from src.models.common import now
from src.services import run_service
from src.schemas.run import RunCreate


def _create_run(db,scenario_id):
 return run_service.create(db,RunCreate(scenario_id=scenario_id))


def test_queued_run_picked_up_after_worker_restart(session,scenario_factory):
 db,fake=session
 sid=scenario_factory()
 run=_create_run(db,sid)
 assert run.status=="queued" and run.attempts==0
 # 模拟重启：新 worker 直接扫描认领（队列消息已随 Redis 清空也不影响）
 fake._items.clear()
 claimed=run_service.claim_next(db,"worker-restart-1")
 assert claimed==run.id
 row=db.get(BlendRun,run.id)
 assert row.status=="running" and row.locked_by=="worker-restart-1" and row.attempts==1
 run_service.run_claimed(db,run.id,"worker-restart-1")
 row=db.get(BlendRun,run.id)
 assert row.status=="completed" and row.finished_at is not None and row.locked_by==""
 assert row.result["lp"]["feasible"] is True and len(row.result["robustness"]["samples"])==40


def test_running_run_lease_expiry_taken_over(session,scenario_factory):
 db,_=session
 sid=scenario_factory()
 run=_create_run(db,sid)
 assert run_service.claim_next(db,"worker-A")==run.id
 # worker-A 在计算中崩溃：租约停留在 45 秒前，超过 30 秒租约
 stale=now()-timedelta(seconds=45)
 db.execute(update(BlendRun).where(BlendRun.id==run.id).values(locked_at=stale).execution_options(synchronize_session=False));db.commit();db.expire_all()
 # 租约未过期时别的 worker 抢不走
 fresh=db.get(BlendRun,run.id);fresh.locked_at=now()-timedelta(seconds=5);db.commit()
 assert run_service.claim_next(db,"worker-B") is None
 # 过期后 worker-B 接管，attempts 累加，最终正常落结果
 db.execute(update(BlendRun).where(BlendRun.id==run.id).values(locked_at=stale).execution_options(synchronize_session=False));db.commit();db.expire_all()
 assert run_service.claim_next(db,"worker-B")==run.id
 row=db.get(BlendRun,run.id)
 assert row.locked_by=="worker-B" and row.attempts==2
 run_service.run_claimed(db,run.id,"worker-B")
 row=db.get(BlendRun,run.id)
 assert row.status=="completed" and row.result["robustness"]["n_samples"]==40


def test_requeue_stuck_returns_only_expired_runs(session,scenario_factory):
 db,_=session
 sid=scenario_factory(scenario_id="sc-a")
 run=_create_run(db,sid)
 run_service.claim_next(db,"worker-A")
 # 活跃租约不动
 assert run_service.requeue_stuck(db)==[]
 # 过期租约退回排队，锁信息清空，快照保留
 stale=now()-timedelta(seconds=120)
 db.execute(update(BlendRun).where(BlendRun.id==run.id).values(locked_at=stale).execution_options(synchronize_session=False));db.commit();db.expire_all()
 assert run_service.requeue_stuck(db)==[run.id]
 row=db.get(BlendRun,run.id)
 assert row.status=="queued" and row.locked_by=="" and row.locked_at is None
 assert row.input_snapshot["seed"]==20261112 and row.attempts==1


def test_recovery_uses_original_snapshot_not_later_edits(session,scenario_factory):
 from src.models.dataset import PulpDataset
 from src.models.spec import QualitySpec
 db,_=session
 sid=scenario_factory(n_samples=40,seed=20261112)
 run=_create_run(db,sid)
 original_snapshot=dict(run.input_snapshot)
 # 建单之后，原浆涨价、规格收紧、情景抽样设置被改动
 ds=db.get(PulpDataset,"ds1");ds.materials=[{**m,"cost":m["cost"]*3} for m in ds.materials]
 sp=db.get(QualitySpec,"sp1");sp.strength_min=99.9
 db.commit()
 # 崩溃恢复：新 worker 用快照重算，结果中的成本仍是建单时的价格水平
 stale=now()-timedelta(seconds=99)
 db.execute(update(BlendRun).where(BlendRun.id==run.id)
            .values(status="running",locked_by="dead-worker",locked_at=stale,attempts=1)
            .execution_options(synchronize_session=False));db.commit();db.expire_all()
 run_service.compute(db,run.id,worker_id="worker-new")
 row=db.get(BlendRun,run.id)
 assert row.status=="completed"
 assert row.input_snapshot==original_snapshot
 assert row.result["input_snapshot"]["seed"]==20261112
 assert row.result["input_snapshot"]["n_samples"]==40
 nominal=row.result["lp"]["nominal_cost"]
 assert nominal<5000  # 三倍涨价后的名义成本会显著更高，证明用的是快照价


def test_redis_outage_does_not_lose_queued_run(session,scenario_factory,monkeypatch):
 db,fake=session
 sid=scenario_factory()
 # 建单时 Redis 故障：行已落库，扫描兜底仍能恢复
 import src.services.run_service as rs
 def boom(_):raise RuntimeError("redis down")
 monkeypatch.setattr(rs,"enqueue",boom)
 run=run_service.create(db,RunCreate(scenario_id=sid))
 assert run.status=="queued" and fake._items==[]
 assert run_service.claim_next(db,"worker-sweep")==run.id
