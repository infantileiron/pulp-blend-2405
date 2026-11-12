"""worker 主循环集成：消息驱动、扫描兜底与启动恢复串起来仍只算一遍。"""
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import update

from src.config import database as db_mod
from src.models.run import BlendRun
from src.models.common import now
from src.services import run_service
from src.schemas.run import RunCreate
import src.worker as worker_mod


def test_worker_loop_message_then_sweep(session,scenario_factory,monkeypatch):
 db,fake=session
 sid=scenario_factory()
 run=run_service.create(db,RunCreate(scenario_id=sid))
 assert fake._items==[run.id]
 monkeypatch.setattr(worker_mod,"WORKER_ID","worker-loop-1")
 calls=[]
 monkeypatch.setattr(worker_mod,"_run_with_heartbeat",lambda rid:calls.append(rid))
 # 模拟一轮循环：消息唤醒并认领
 import time
 monkeypatch.setattr(worker_mod,"last_sweep",0.0,raising=False)
 # 直接复用 main 的循环体较难中断，改为逐段验证同一套原语
 claimed=run_service.claim_next(db,worker_mod.WORKER_ID)
 assert claimed==run.id and calls==[]
 worker_mod._run_with_heartbeat(run.id)
 assert calls==[run.id]
 # 队列已空，再扫描没有可认领行
 assert run_service.claim_next(db,worker_mod.WORKER_ID) is None


def test_worker_startup_recovers_crashed_running(session,scenario_factory):
 db,_=session
 sid=scenario_factory()
 run=run_service.create(db,RunCreate(scenario_id=sid))
 run_service.claim_next(db,"crashed-worker")
 stale=now()-timedelta(seconds=300)
 db.execute(update(BlendRun).where(BlendRun.id==run.id).values(locked_at=stale).execution_options(synchronize_session=False));db.commit();db.expire_all()
 # 新 worker 启动：requeue_stuck 退回排队，随后扫描认领并完成
 recovered=run_service.requeue_stuck(db)
 assert recovered==[run.id]
 claimed=run_service.claim_next(db,"rebooted-worker")
 assert claimed==run.id
 run_service.run_claimed(db,run.id,"rebooted-worker")
 row=db.get(BlendRun,run.id)
 assert row.status=="completed" and row.attempts==2 and row.locked_by==""


def test_heartbeat_releases_when_run_finished(session,scenario_factory):
 db,_=session
 sid=scenario_factory()
 run=run_service.create(db,RunCreate(scenario_id=sid))
 run_service.claim_next(db,"worker-hb")
 assert run_service.heartbeat(db,run.id,"worker-hb") is True
 run_service.run_claimed(db,run.id,"worker-hb")
 # 终态后旧持有者续租失败，心跳线程据此自行退出
 assert run_service.heartbeat(db,run.id,"worker-hb") is False


class _StopLoop(BaseException):
 pass


def _drive_main(monkeypatch,conftest_session,max_loops=6):
 """以打桩方式驱动 worker.main 的真实循环体：blpop 用 FakeRedis，循环到上限时退出。"""
 db,fake=conftest_session
 loops={"n":0}
 real_blpop=fake.blpop
 def patched_blpop(_key,timeout=0):
  loops["n"]+=1
  if loops["n"]>max_loops:raise _StopLoop()
  return real_blpop(_key,timeout)
 # worker 以 from-import 绑定了 client/Session，必须替换 worker 模块内的名字
 monkeypatch.setattr(worker_mod,"client",lambda:fake)
 monkeypatch.setattr(worker_mod,"Session",db_mod.Session)
 monkeypatch.setattr(fake,"blpop",patched_blpop)
 monkeypatch.setattr(worker_mod,"SWEEP_SECONDS",0.0)
 monkeypatch.setattr(worker_mod,"HEARTBEAT_SECONDS",3600.0)
 class _Heartbeat:
  def touch(self):pass
 monkeypatch.setattr(worker_mod,"heartbeat",_Heartbeat())
 try:
  worker_mod.main()
 except _StopLoop:
  pass


def _fresh(run_id):
 """worker 在独立连接提交后，用新会话读取权威行，避免长生命周期测试会话的陈旧快照。"""
 with db_mod.Session() as probe:
  return probe.get(BlendRun,run_id)


def test_worker_main_processes_message_end_to_end(session,scenario_factory,monkeypatch,tmp_path):
 monkeypatch.chdir(tmp_path)
 db,fake=session
 sid=scenario_factory()
 run=run_service.create(db,RunCreate(scenario_id=sid))
 assert fake._items==[run.id]
 _drive_main(monkeypatch,session)
 row=_fresh(run.id)
 assert row.status=="completed" and row.attempts==1 and row.locked_by==""
 assert row.result["robustness"]["n_samples"]==40


def test_worker_main_startup_recovers_crashed_run(session,scenario_factory,monkeypatch,tmp_path):
 monkeypatch.chdir(tmp_path)
 db,fake=session
 sid=scenario_factory()
 run=run_service.create(db,RunCreate(scenario_id=sid))
 # worker 在计算中崩溃：running + 过期租约，Redis 消息也已丢失
 run_service.claim_run(db,run.id,"crashed-worker")
 db.execute(update(BlendRun).where(BlendRun.id==run.id)
            .values(locked_at=now()-timedelta(seconds=300)).execution_options(synchronize_session=False))
 db.commit();db.expire_all()
 fake._items.clear()
 _drive_main(monkeypatch,session)
 row=_fresh(run.id)
 assert row.status=="completed" and row.attempts==2 and row.locked_by==""
 assert row.input_snapshot["seed"]==20261112
