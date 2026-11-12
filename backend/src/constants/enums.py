from enum import StrEnum
class Role(StrEnum):
 ADMIN="admin"
 ANALYST="analyst"
 VIEWER="viewer"
class RunStatus(StrEnum):
 QUEUED="queued"
 RUNNING="running"
 COMPLETED="completed"
 INFEASIBLE="infeasible"
 FAILED="failed"
PROPERTIES=["strength","whiteness","recycled"]
PHYSICAL_BOUNDS={"strength":(0.,100.),"whiteness":(0.,100.),"recycled":(0.,1.)}

CONSTRAINT_TOLERANCE=1e-7
