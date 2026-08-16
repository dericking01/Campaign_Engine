from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_action
from app.core.permissions import Action

router = APIRouter(prefix="/dnd", tags=["dnd"])


class DndListOut(BaseModel):
    id: int
    name: str
    version: int
    is_active: bool
    record_count: int

    model_config = {"from_attributes": True}


@router.get(
    "/lists", response_model=list[DndListOut], dependencies=[Depends(require_action(Action.CAMPAIGN_VIEW))]
)
def list_dnd_lists(db: Session = Depends(get_db)) -> list[DndListOut]:
    # DND lists are created exclusively via the import pipeline
    # (POST /imports/upload or /imports/drop-path/create with
    # import_kind=DND, then approve with dnd_list_name) - there is no
    # separate "create an empty list" endpoint, mirroring how bases are
    # only ever created by committing an import.
    rows = db.execute(
        text("""
            SELECT l.id, l.name, l.version, l.is_active, count(r.id) AS record_count
            FROM campaign.dnd_lists l
            LEFT JOIN campaign.dnd_records r ON r.dnd_list_id = l.id
            GROUP BY l.id
            ORDER BY l.name, l.version DESC
        """)
    ).mappings().all()
    return [DndListOut(**row) for row in rows]
