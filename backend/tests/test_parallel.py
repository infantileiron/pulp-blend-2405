"""多 worker 真实并发：线程级争抢同一试算，验证只算一次、只落一份结果。"""
import threading
from datetime import timedelta

import pytest
from sqlalchemy import create_engine,inspect,select,update
from sqlalchemy.orm import sessionmaker

from src.config import database as db_mod
from src.models.dataset import PulpDataset
from src.models.spec import QualitySpec
from src.models.scenario import BlendScenario
from src.models.run import BlendRun
from src.models.common import now
from src.services import run_service
from src.schemas.run import RunCreate


MATERIALS=[
 {"material_id":"P01","name":"针叶浆","cost":5200.,"min_share":0.,"max_share":.65,
  "strength":91.,"whiteness":89.,"recycled":0.,"strength_width":3.,"whiteness_width":1.5,
  "recycled_width":0.,"cost_width":200.},
 {"material_id":"P02","name":"回收浆","cost":2600.,"min_share":0.,"max_share":.95,
  "strength":56.,"whiteness":74.,"recycled":.95,"strength_width":4.,"whiteness_width":3.,
  "recycled_width":.03,"cost_width":130.},
]


@pytest.fixture()
def threaded_engine(tmp_path):
 db_file=tmp_path/"concurrency.sqlite"
 engine=create_engine(f"sqlite+pysqlite:///{db_file}",connect_args={"check_same_thread":False,"timeout":30})
 old_engine,old_session=db_mod.engine,db_mod.Session
 db_mod.engine=engine
 db_mod.Session=sessionmaker(bind=engine,expire_on_commit=False)
 db_mod.initialize()
 try:
  with db_mod.Session() as db:
   db.add(PulpDataset(id="ds1",name="原浆批",materials=MATERIALS,description=""))
   db.add(QualitySpec(id="sp1",name="规格",description="",strength_min=40.,strength_max=100.,
                      whiteness_min=60.,whiteness_max=100.,recycled_min=.25,recycled_max=1.))
   db.add(BlendScenario(id="sc1",name="情景",dataset_id="ds1",spec_id="sp1",
                        n_samples=60,seed=20261112,perturb_cost=True))
   db.commit()
  yield engine
 finally:
  db_mod.engine,db_mod.Session=old_engine,old_session
 engine.dispose()


def test_parallel_workers_single_run_computed_once(threaded_engine):
 with db_mod.Session() as db:
  run=run_service.create(db,RunCreate(scenario_id="sc1"));run_id=run.id

 outcomes=[];barrier=threading.Barrier(8)
 def worker(idx):
  barrier.wait()  # 尽量让 8 个线程同时开抢
  with db_mod.Session() as db:
   # 每个 worker 都既走消息路径又走扫描路径，覆盖重复投递与争抢
   run_service.compute(db,run_id,worker_id=f"worker-{idx}")
   outcomes.append(run_service.claim_next(db,f"worker-{idx}"))
 threads=[threading.Thread(target=worker,args=(i,)) for i in range(8)]
 for t in threads:t.start()
 for t in threads:t.join()

 with db_mod.Session() as db:
  row=db.get(BlendRun,run_id)
  assert row.status=="completed"
  assert row.attempts==1                       # 只有一个 worker 抢到，没有重复计算
  assert row.locked_by=="" and row.finished_at is not None
  assert len(row.result["robustness"]["samples"])==60
 assert outcomes.count(None)==8               # 终态后任何扫描都无可认领行


def test_parallel_claim_contention_only_one_winner(threaded_engine):
 with db_mod.Session() as db:
  run=run_service.create(db,RunCreate(scenario_id="sc1"));run_id=run.id

 winners=[];barrier=threading.Barrier(6)
 def claimer(idx):
  barrier.wait()
  with db_mod.Session() as db:
   won=run_service.claim_run(db,run_id,f"claimer-{idx}")
   if won:winners.append(idx)
 threads=[threading.Thread(target=claimer,args=(i,)) for i in range(6)]
 for t in threads:t.start()
 for t in threads:t.join()
 assert len(winners)==1
 with db_mod.Session() as db:
  row=db.get(BlendRun,run_id)
  assert row.status=="running" and row.attempts==1 and row.locked_by==f"claimer-{winners[0]}"


def test_parallel_takeover_after_crash_writes_single_result(threaded_engine):
 with db_mod.Session() as db:
  run=run_service.create(db,RunCreate(scenario_id="sc1"));run_id=run.id
  assert run_service.claim_run(db,run_id,"dead-worker")
  db.execute(update(BlendRun).where(BlendRun.id==run_id)
             .values(locked_at=now()-timedelta(seconds=120)).execution_options(synchronize_session=False))
  db.commit()

 done=threading.Event();barrier=threading.Barrier(5)
 def rescuer(idx):
  barrier.wait()
  with db_mod.Session() as db:
   if run_service.claim_run(db,run_id,f"rescue-{idx}"):
    run_service.run_claimed(db,run_id,f"rescue-{idx}")
    done.set()
 threads=[threading.Thread(target=rescuer,args=(i,)) for i in range(5)]
 for t in threads:t.start()
 for t in threads:t.join()
 with db_mod.Session() as db:
  row=db.get(BlendRun,run_id)
  assert row.status=="completed" and row.attempts==2   # 崩溃那次 + 接管那次，仅一份结果
  assert row.result["lp"]["feasible"] is True
