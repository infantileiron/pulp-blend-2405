from sqlalchemy import String,Text,JSON,ForeignKey,Double
from sqlalchemy.orm import Mapped,mapped_column
from .common import RecordMixin
from ..config.database import Base
class QualitySpec(RecordMixin,Base):
 __tablename__="specs"
 name:Mapped[str]=mapped_column(String(180),unique=True)
 strength_min:Mapped[float]=mapped_column(Double)
 strength_max:Mapped[float]=mapped_column(Double)
 whiteness_min:Mapped[float]=mapped_column(Double)
 whiteness_max:Mapped[float]=mapped_column(Double)
 recycled_min:Mapped[float]=mapped_column(Double)
 recycled_max:Mapped[float]=mapped_column(Double)
 description:Mapped[str]=mapped_column(Text,default="")
