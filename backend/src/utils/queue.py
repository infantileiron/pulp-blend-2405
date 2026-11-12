from redis import Redis
from ..config.settings import REDIS_URL
QUEUE="pulp-blend:runs"
def client(): return Redis.from_url(REDIS_URL,decode_responses=True)
def enqueue(run_id):
 # Redis 只承担唤醒通知；试算的权威状态在 MySQL，worker 另有定时扫描兜底，消息丢失不影响恢复
 client().rpush(QUEUE,run_id)
