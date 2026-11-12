from uuid import uuid4
from sqlalchemy import select
from fastapi import HTTPException
from ..models.spec import QualitySpec

def create(db,body):
 if db.scalar(select(QualitySpec).where(QualitySpec.name==body.name)):raise HTTPException(409,"质量规格名称已存在")
 row=QualitySpec(id=str(uuid4()),**body.model_dump());db.add(row);db.commit();return row
