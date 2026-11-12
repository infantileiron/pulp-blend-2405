from uuid import uuid4
from sqlalchemy import select
from fastapi import HTTPException
from ..models.dataset import PulpDataset
from .materials import parse_csv

def create(db,body):
 if db.scalar(select(PulpDataset).where(PulpDataset.name==body.name)):raise HTTPException(409,"原浆批次名称已存在")
 try:materials=parse_csv(body.csv_text)
 except ValueError as e:raise HTTPException(422,str(e))
 row=PulpDataset(id=str(uuid4()),name=body.name,materials=materials,description=body.description);db.add(row);db.commit();return row
