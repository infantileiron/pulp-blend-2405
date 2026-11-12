from ..services import review_service
from ..models.review import FormulaReview
from ..models.common import serialize
from .common import listing,require
def list_all(db):return listing(db,FormulaReview)
def detail(db,ident):return serialize(require(db,FormulaReview,ident))
def create(db,body):return serialize(review_service.create(db,body))
