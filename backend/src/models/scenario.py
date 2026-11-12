from sqlalchemy import String,Text,JSON,ForeignKey,Double
from sqlalchemy.orm import Mapped,mapped_column
from .common import RecordMixin
from ..config.database import Base
class BlendScenario(RecordMixin,Base):
 __tablename__="scenarios"
 name:Mapped[str]=mapped_column(String(180),unique=True)
 dataset_id:Mapped[str]=mapped_column(ForeignKey("datasets.id"))
 spec_id:Mapped[str]=mapped_column(ForeignKey("specs.id"))
 n_samples:Mapped[int]
 seed:Mapped[int]
 perturb_cost:Mapped[bool]
