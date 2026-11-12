from fastapi import APIRouter,Depends
from ..config.database import get_db
from ..utils.auth import current,write_user,admin
from ..schemas.scenario import ScenarioCreate
from ..controllers import scenario_controller as controller,common
from ..models.scenario import BlendScenario
from ..models.common import serialize
router=APIRouter(prefix="/scenarios",tags=["scenarios"])
@router.get("")
def listing(db=Depends(get_db),user=Depends(current)):return controller.list_all(db)
@router.get("/{ident}")
def detail(ident:str,db=Depends(get_db),user=Depends(current)):return controller.detail(db,ident)
@router.post("",status_code=201)
def create(body:ScenarioCreate,db=Depends(get_db),user=Depends(write_user)):return controller.create(db,body)
