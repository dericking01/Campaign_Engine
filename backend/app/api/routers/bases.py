from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_action
from app.core.permissions import Action
from app.models.bases import BaseVersion, CampaignBase

router = APIRouter(prefix="/bases", tags=["bases"])


class BaseOut(BaseModel):
    id: int
    name: str
    description: str | None
    is_active: bool

    model_config = {"from_attributes": True}


class BaseVersionOut(BaseModel):
    id: int
    base_id: int
    member_count: int | None
    is_current: bool
    committed_at: datetime | None

    model_config = {"from_attributes": True}


@router.get(
    "", response_model=list[BaseOut], dependencies=[Depends(require_action(Action.CAMPAIGN_VIEW))]
)
def list_bases(db: Session = Depends(get_db)) -> list[CampaignBase]:
    return db.query(CampaignBase).order_by(CampaignBase.name).all()


@router.get(
    "/{base_id}/versions",
    response_model=list[BaseVersionOut],
    dependencies=[Depends(require_action(Action.CAMPAIGN_VIEW))],
)
def list_base_versions(base_id: int, db: Session = Depends(get_db)) -> list[BaseVersion]:
    return (
        db.query(BaseVersion)
        .filter(BaseVersion.base_id == base_id)
        .order_by(BaseVersion.id.desc())
        .all()
    )
