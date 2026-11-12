from datetime import datetime
from sqlalchemy import String,Text,JSON,ForeignKey,Integer,DateTime
from sqlalchemy.orm import Mapped,mapped_column
from .common import RecordMixin
from ..config.database import Base
class BlendRun(RecordMixin,Base):
 __tablename__="runs"
 scenario_id:Mapped[str]=mapped_column(ForeignKey("scenarios.id"))
 status:Mapped[str]=mapped_column(String(20),default="queued")
 result:Mapped[dict]=mapped_column(JSON,default=dict)
 error:Mapped[str]=mapped_column(Text,default="")
 # 建单时固化的原始输入（原浆/规格/抽样设置），恢复时只按它重算，不读后续可能被改动的实体
 input_snapshot:Mapped[dict]=mapped_column(JSON,default=dict)
 attempts:Mapped[int]=mapped_column(Integer,default=0)
 locked_by:Mapped[str]=mapped_column(String(64),default="")
 locked_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
 started_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
 finished_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
