"""存量库补列幂等：旧版 runs 表升级后历史行保持原样，新行具备恢复字段。"""
from sqlalchemy import inspect,text

from src.config import database as db_mod
from src.models.run import BlendRun


def test_upgrade_adds_columns_once_and_keeps_history(session,scenario_factory):
 from src.schemas.run import RunCreate
 from src.services import run_service
 db,_=session
 sid=scenario_factory()
 run=run_service.create(db,RunCreate(scenario_id=sid))
 # 补列后再次执行升级不报错、不重复加列
 db_mod._upgrade_runs_table()
 db_mod._upgrade_runs_table()
 cols={c["name"] for c in inspect(db_mod.engine).get_columns("runs")}
 assert {"input_snapshot","attempts","locked_by","locked_at","started_at","finished_at"} <= cols
 row=db.get(BlendRun,run.id)
 assert row.attempts==0 and row.locked_by=="" and row.input_snapshot["materials"]


def test_upgrade_on_legacy_table_without_columns(session):
 # 手工模拟旧库：删掉新列后重新跑升级，数据行仍在
 engine=db_mod.engine
 with engine.begin() as conn:
  for col in ["input_snapshot","attempts","locked_by","locked_at","started_at","finished_at"]:
   conn.execute(text(f"ALTER TABLE runs DROP COLUMN {col}"))
 assert "attempts" not in {c["name"] for c in inspect(engine).get_columns("runs")}
 db_mod._upgrade_runs_table()
 cols={c["name"] for c in inspect(engine).get_columns("runs")}
 assert {"input_snapshot","attempts","locked_by","locked_at","started_at","finished_at"} <= cols
