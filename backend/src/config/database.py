from sqlalchemy import create_engine,inspect,text
from sqlalchemy.orm import DeclarativeBase,sessionmaker
from .settings import DATABASE_URL
class Base(DeclarativeBase): pass
engine=create_engine(DATABASE_URL,pool_pre_ping=True)
Session=sessionmaker(bind=engine,expire_on_commit=False)
def get_db():
 with Session() as db: yield db

# 中断恢复所需列；对已存在的库做幂等补列，不触碰任何历史行（已完成试算与归档原样保留）
_RUN_COLUMNS={
 "input_snapshot":"JSON",
 "attempts":"INTEGER NOT NULL DEFAULT 0",
 "locked_by":"VARCHAR(64) NOT NULL DEFAULT ''",
 "locked_at":"DATETIME NULL",
 "started_at":"DATETIME NULL",
 "finished_at":"DATETIME NULL",
}
def _upgrade_runs_table():
 inspector=inspect(engine)
 if "runs" not in inspector.get_table_names():return
 existing={col["name"] for col in inspector.get_columns("runs")}
 with engine.begin() as conn:
  for name,ddl in _RUN_COLUMNS.items():
   if name not in existing:conn.execute(text(f"ALTER TABLE runs ADD COLUMN {name} {ddl}"))

def initialize():
 from .. import models
 Base.metadata.create_all(engine)
 _upgrade_runs_table()
