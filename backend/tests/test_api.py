"""HTTP 层：多用户/重复投递经真实路由只产生一个活跃试算，终态行不被复活。"""
import pytest
from sqlalchemy import select
from fastapi.testclient import TestClient

from src.main import app
from src.config.database import get_db,Session as AppSession,initialize
from src.config import database as db_mod
from src.models.user import User
from src.models.run import BlendRun
from src.utils.security import hash_password,issue
from src.services import run_service


@pytest.fixture(autouse=True)
def _no_demo_seed(monkeypatch):
 # 避免 app lifespan 向测试库灌入演示数据
 monkeypatch.setattr("src.main.SEED_DEMO",False)
 yield
 app.dependency_overrides.clear()


def _client(engine_session_factory):
 def _override():
  with engine_session_factory() as db:yield db
 app.dependency_overrides[get_db]=_override
 return TestClient(app)


def test_duplicate_post_returns_same_run_over_http(session,scenario_factory):
 scenario_factory()
 db,fake=session
 db.add(User(id="u1",email="analyst@pulp.demo",role="analyst",password_hash=hash_password("pw")));db.commit()
 token=issue(db.get(User,"u1"))
 client=_client(db_mod.Session)
 headers={"Authorization":f"Bearer {token}"}
 r1=client.post("/runs",json={"scenario_id":"sc1"},headers=headers)
 r2=client.post("/runs",json={"scenario_id":"sc1"},headers=headers)
 assert r1.status_code==201 and r2.status_code==201
 assert r1.json()["id"]==r2.json()["id"]            # 重复投递复用同一活跃试算
 assert r2.json()["status"]=="queued"
 assert len(fake._items)==1                          # 只入队一次
 with db_mod.Session() as probe:
  assert probe.scalars(select(BlendRun)).all().__len__()==1


def test_viewer_cannot_create_run_over_http(session,scenario_factory):
 scenario_factory()
 db,_=session
 db.add(User(id="u2",email="viewer@pulp.demo",role="viewer",password_hash=hash_password("pw")));db.commit()
 token=issue(db.get(User,"u2"))
 client=_client(db_mod.Session)
 r=client.post("/runs",json={"scenario_id":"sc1"},headers={"Authorization":f"Bearer {token}"})
 assert r.status_code==403


def test_anonymous_post_unauthorized(session,scenario_factory):
 scenario_factory()
 client=_client(db_mod.Session)
 r=client.post("/runs",json={"scenario_id":"sc1"})
 assert r.status_code==401


def test_completed_run_not_resurrected_by_new_http_post(session,scenario_factory):
 scenario_factory()
 db,_=session
 db.add(User(id="u3",email="analyst2@pulp.demo",role="analyst",password_hash=hash_password("pw")));db.commit()
 token=issue(db.get(User,"u3"))
 # 先把唯一情景的试算跑到终态
 from src.schemas.run import RunCreate
 first=run_service.create(db,RunCreate(scenario_id="sc1"))
 run_service.compute(db,first.id,worker_id="w1")
 assert db.get(BlendRun,first.id).status=="completed"
 client=_client(db_mod.Session)
 r=client.post("/runs",json={"scenario_id":"sc1"},headers={"Authorization":f"Bearer {token}"})
 # 终态后允许新建下一单，但旧行保持原样（attempts 不变、仍是 completed）
 assert r.status_code==201
 new_id=r.json()["id"]
 assert new_id!=first.id
 old=db.get(BlendRun,first.id)
 assert old.status=="completed" and old.attempts==1
