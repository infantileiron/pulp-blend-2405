import os,sys,json,types
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND))


class FakeRedis:
 """最小内存 Redis：实现 worker/queue 用到的 rpush/blpop/lpop/ping。"""
 def __init__(self):
  self._items=[]
 def rpush(self,_key,value):
  self._items.append(value);return len(self._items)
 def lpop(self,_key):
  return self._items.pop(0) if self._items else None
 def blpop(self,_key,timeout=0):
  return (None if not self._items else (_key,self._items.pop(0)))
 def ping(self):return True


@pytest.fixture()
def session(monkeypatch,tmp_path):
 from src.config import database as db_mod
 # 文件库 + 多连接：worker 另开会话/连接时各自独立事务，提交对其他连接立即可见，贴近 MySQL 语义
 engine=create_engine(f"sqlite+pysqlite:///{tmp_path/'test.sqlite'}",
                      connect_args={"check_same_thread":False,"timeout":30})
 db_mod.engine=engine
 db_mod.Session=sessionmaker(bind=engine,expire_on_commit=False)
 db_mod.initialize()
 fake=FakeRedis()
 import src.utils.queue as queue_mod
 monkeypatch.setattr(queue_mod,"client",lambda:fake)
 import src.services.run_service as run_service
 monkeypatch.setattr(run_service,"enqueue",lambda run_id:fake.rpush("q",run_id))
 with db_mod.Session() as db:
  yield db,fake


@pytest.fixture()
def scenario_factory(session):
 from src.models.dataset import PulpDataset
 from src.models.spec import QualitySpec
 from src.models.scenario import BlendScenario
 db,_=session
 def _make(dataset_id="ds1",spec_id="sp1",scenario_id="sc1",n_samples=40,seed=20261112,perturb_cost=True,
           materials=None,spec_kwargs=None):
  materials=materials or [
   {"material_id":"P01","name":"针叶浆","cost":5200.,"min_share":0.,"max_share":.65,
    "strength":91.,"whiteness":89.,"recycled":0.,"strength_width":3.,"whiteness_width":1.5,
    "recycled_width":0.,"cost_width":200.},
   {"material_id":"P02","name":"回收浆","cost":2600.,"min_share":0.,"max_share":.95,
    "strength":56.,"whiteness":74.,"recycled":.95,"strength_width":4.,"whiteness_width":3.,
    "recycled_width":.03,"cost_width":130.},
  ]
  spec_kwargs=spec_kwargs or dict(strength_min=40.,strength_max=100.,whiteness_min=60.,whiteness_max=100.,
                                  recycled_min=.25,recycled_max=1.)
  db.add(PulpDataset(id=dataset_id,name="原浆批"+dataset_id,materials=materials,description=""))
  db.add(QualitySpec(id=spec_id,name="规格"+spec_id,description="",**spec_kwargs))
  db.add(BlendScenario(id=scenario_id,name="情景"+scenario_id,dataset_id=dataset_id,spec_id=spec_id,
                       n_samples=n_samples,seed=seed,perturb_cost=perturb_cost))
  db.commit()
  return scenario_id
 return _make
