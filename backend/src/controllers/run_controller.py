from ..services import run_service
from ..models.run import BlendRun
from ..models.common import serialize
from .common import listing,require
def list_all(db):return listing(db,BlendRun)
def detail(db,ident):return serialize(require(db,BlendRun,ident))
def create(db,body):return serialize(run_service.create(db,body))
