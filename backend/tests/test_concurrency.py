"""并发争抢与重复投递：同一试算只被计算一次，终态结果不被覆盖、不重复落。"""
from datetime import timedelta

from sqlalchemy import update

from src.models.run import BlendRun
from src.models.common import now
from src.models.report import Report
from src.services import run_service
from src.schemas.run import RunCreate


def test_two_workers_claim_only_one_wins(session,scenario_factory):
 db,_=session
 sid=scenario_factory()
 run=run_service.create(db,RunCreate(scenario_id=sid))
 # 两个 worker 同时扫描：只有一个成功认领，另一个拿不到该行
 first=run_service.claim_next(db,"worker-1")
 second=run_service.claim_next(db,"worker-2")
 assert first==run.id and second is None
 row=db.get(BlendRun,run.id)
 assert row.locked_by=="worker-1"


def test_duplicate_message_does_not_compute_twice(session,scenario_factory):
 db,fake=session
 sid=scenario_factory()
 run=run_service.create(db,RunCreate(scenario_id=sid))
 # 同一 run_id 消息被投递两遍（worker 重连/用户重发）
 run_service.compute(db,run.id,worker_id="worker-1")
 first=db.get(BlendRun,run.id)
 assert first.status=="completed"
 finished_at=first.finished_at;result_ref=first.result
 run_service.compute(db,run.id,worker_id="worker-2")
 row=db.get(BlendRun,run.id)
 assert row.status=="completed"
 assert row.attempts==1                      # 终态行不会被再次认领
 assert row.finished_at==finished_at        # 没有第二次写入
 assert row.result is result_ref or row.result==result_ref


def test_duplicate_submit_returns_same_active_run(session,scenario_factory):
 db,fake=session
 sid=scenario_factory()
 first=run_service.create(db,RunCreate(scenario_id=sid))
 second=run_service.create(db,RunCreate(scenario_id=sid))
 assert first.id==second.id                  # 排队中重复投递返回同一行，不建第二单
 assert len(fake._items)==1
 # 运行中重复投递同样幂等
 run_service.claim_next(db,"worker-1")
 third=run_service.create(db,RunCreate(scenario_id=sid))
 assert third.id==first.id
 assert db.query(BlendRun).count()==1


def test_stale_owner_cannot_overwrite_new_owners_result(session,scenario_factory):
 db,_=session
 sid=scenario_factory()
 run=run_service.create(db,RunCreate(scenario_id=sid))
 run_service.claim_next(db,"worker-A")
 # A 僵死，租约过期后 B 接管并完成
 stale=now()-timedelta(seconds=90)
 db.execute(update(BlendRun).where(BlendRun.id==run.id).values(locked_at=stale).execution_options(synchronize_session=False));db.commit();db.expire_all()
 run_service.compute(db,run.id,worker_id="worker-B")
 assert db.get(BlendRun,run.id).status=="completed"
 # A “复活”后试图用旧持有者身份落终态：条件更新必须拒绝
 ok=run_service._finish(db,run.id,"worker-A","failed",error="迟到的失败结果")
 assert ok is False
 row=db.get(BlendRun,run.id)
 assert row.status=="completed" and row.error==""


def test_completed_run_and_report_archive_untouched(session,scenario_factory):
 from src.models.review import FormulaReview
 db,_=session
 sid=scenario_factory()
 run=run_service.create(db,RunCreate(scenario_id=sid))
 run_service.compute(db,run.id,worker_id="worker-1")
 review=FormulaReview(id="rv1",run_id=run.id,action="复核说明至少八个字。",state="approved",reviewer="admin@pulp.demo")
 db.add(review);db.commit()
 report=Report(id="rp1",review_id=review.id,title="归档底稿",snapshot={"result":db.get(BlendRun,run.id).result})
 db.add(report);db.commit()
 snapshot_before=dict(report.snapshot)
 # 任何恢复/重投路径都不能改动已完成试算与归档
 run_service.compute(db,run.id,worker_id="worker-2")
 run_service.requeue_stuck(db)
 row=db.get(BlendRun,run.id)
 assert row.status=="completed" and row.attempts==1
 assert db.get(Report,"rp1").snapshot==snapshot_before


def test_failed_run_can_be_resubmitted_as_new_run(session,scenario_factory):
 db,_=session
 sid=scenario_factory(scenario_id="sc-fail",spec_kwargs=dict(strength_min=99.9,strength_max=100.,
   whiteness_min=99.9,whiteness_max=100.,recycled_min=.99,recycled_max=1.))
 run=run_service.create(db,RunCreate(scenario_id=sid))
 run_service.compute(db,run.id,worker_id="worker-1")
 # 不可行属于终态；再投递应新建试算而不是复活旧行
 assert db.get(BlendRun,run.id).status=="infeasible"
 again=run_service.create(db,RunCreate(scenario_id=sid))
 assert again.id!=run.id and again.status=="queued"
