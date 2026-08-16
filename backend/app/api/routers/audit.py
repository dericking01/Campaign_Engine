from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_action
from app.core.permissions import Action
from app.models.audit import AuditLog

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditLogOut(BaseModel):
    id: int
    created_at: datetime
    actor_id: int | None
    action: str
    entity_type: str
    entity_id: str | None
    reason: str | None
    old_value: dict | None
    new_value: dict | None

    model_config = {"from_attributes": True}


@router.get(
    "",
    response_model=list[AuditLogOut],
    dependencies=[Depends(require_action(Action.AUDIT_VIEW))],
)
def list_audit_logs(db: Session = Depends(get_db)) -> list[AuditLog]:
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(200).all()
