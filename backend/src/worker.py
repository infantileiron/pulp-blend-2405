import os,time,uuid,logging,threading
from pathlib import Path
from .config.database import Session,initialize
from .utils.queue import client,QUEUE
from .services import run_service

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger=logging.getLogger("pulp.worker")
heartbeat=Path("/artifacts/worker-heartbeat")
SWEEP_SECONDS=float(os.getenv("WORKER_SWEEP_SECONDS","10"))
HEARTBEAT_SECONDS=float(os.getenv("WORKER_HEARTBEAT_SECONDS","8"))
WORKER_ID=f"{os.getenv('HOSTNAME','worker')}-{os.getpid()}-{uuid.uuid4().hex[:8]}"

def _run_with_heartbeat(run_id):
 stop=threading.Event()
 def beat():
  while not stop.wait(HEARTBEAT_SECONDS):
   try:
    with Session() as db:
     if not run_service.heartbeat(db,run_id,WORKER_ID):return
   except Exception:logger.exception("续租失败 run=%s",run_id)
 t=threading.Thread(target=beat,name=f"hb-{run_id[:8]}",daemon=True)
 t.start()
 try:
  with Session() as db:run_service.run_claimed(db,run_id,WORKER_ID)
 finally:stop.set()

def main():
 initialize()
 logger.info("worker %s 启动，扫描并恢复中断试算",WORKER_ID)
 with Session() as db:run_service.requeue_stuck(db)
 last_sweep=0.0
 while True:
  try:
   heartbeat.touch()
   # Redis 消息仅作唤醒；重复消息/多 worker 由 claim_run 的条件更新去重
   item=None
   try:item=client().blpop(QUEUE,timeout=2)
   except Exception:logger.exception("Redis 不可用，退回定时扫描")
   if item:
    run_id=item[1]
    with Session() as db:
     won=run_service.claim_run(db,run_id,WORKER_ID)
    if won:_run_with_heartbeat(run_id)
   tick=time.monotonic()
   if tick-last_sweep>=SWEEP_SECONDS:
    last_sweep=tick
    with Session() as db:
     run_id=run_service.claim_next(db,WORKER_ID)
    if run_id:_run_with_heartbeat(run_id)
  except Exception:
   logger.exception("Worker 循环异常")
   time.sleep(2)

if __name__=="__main__":main()
