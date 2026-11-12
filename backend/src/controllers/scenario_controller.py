from ..services import scenario_service
from ..models.scenario import BlendScenario
from ..models.common import serialize
from .common import listing,require
def list_all(db):return listing(db,BlendScenario)
def detail(db,ident):return serialize(require(db,BlendScenario,ident))
def create(db,body):return serialize(scenario_service.create(db,body))
