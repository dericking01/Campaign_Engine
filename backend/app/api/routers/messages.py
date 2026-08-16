from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_action
from app.core.permissions import Action
from app.models.user import User
from app.services.audit import write_audit_log

router = APIRouter(prefix="/messages", tags=["messages"])

MANUALLY_RETRIABLE_STATUSES = ("DEAD", "FAILED_UNCONFIRMED")


class MessageOut(BaseModel):
    id: int
    customer_msisdn: str
    channel: str
    status: str
    attempt_count: int
    next_attempt_at: datetime | None


class MessagesPage(BaseModel):
    items: list[MessageOut]
    total: int
    limit: int
    offset: int


@router.get(
    "/runs/{run_id}",
    response_model=MessagesPage,
    dependencies=[Depends(require_action(Action.CAMPAIGN_VIEW))],
)
def list_messages(
    run_id: int, status_filter: str | None = None, limit: int = 100, offset: int = 0, db: Session = Depends(get_db)
) -> dict:
    """Server-side paginated/filterable by status - never rendering
    millions of message rows client-side (requirements doc §25 UI note)."""
    limit = min(limit, 1000)
    params: dict = {"run_id": run_id, "limit": limit, "offset": offset}
    where = "campaign_run_id = :run_id"
    if status_filter:
        where += " AND status = :status_filter"
        params["status_filter"] = status_filter

    total = db.execute(text(f"SELECT count(*) FROM campaign.messages WHERE {where}"), params).scalar_one()
    rows = db.execute(
        text(f"""
            SELECT id, customer_msisdn, channel, status, attempt_count, next_attempt_at
            FROM campaign.messages
            WHERE {where}
            ORDER BY id
            LIMIT :limit OFFSET :offset
        """),
        params,
    ).all()
    return {
        "items": [
            {
                "id": r.id,
                "customer_msisdn": r.customer_msisdn,
                "channel": r.channel,
                "status": r.status,
                "attempt_count": r.attempt_count,
                "next_attempt_at": r.next_attempt_at,
            }
            for r in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/runs/{run_id}/summary",
    dependencies=[Depends(require_action(Action.CAMPAIGN_VIEW))],
)
def message_status_summary(run_id: int, db: Session = Depends(get_db)) -> dict:
    """Grouped counts by status - a single aggregate query, not a
    paginated row fetch, so this stays cheap on a run with millions of
    messages (the Execution Monitor polls this every few seconds)."""
    rows = db.execute(
        text("SELECT status, count(*) FROM campaign.messages WHERE campaign_run_id = :id GROUP BY status"),
        {"id": run_id},
    ).all()
    return {"counts": {r.status: r.count for r in rows}}


@router.post("/{message_id}/retry")
def retry_message(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.CAMPAIGN_START_STOP)),
) -> dict:
    """Manual retry for DEAD/FAILED_UNCONFIRMED messages surfaced to ops
    review - never automatic for FAILED_UNCONFIRMED (see docs/decisions.md).
    Sets next_attempt_at to now so worker-retry-scheduler picks it up on
    its next poll (no direct Kafka publish here - keeps this endpoint as
    just a DB state change, consistent with "retry is DB-driven")."""
    result = db.execute(
        text("""
            UPDATE campaign.messages SET status = 'RETRYING', next_attempt_at = :now, updated_at = now()
            WHERE id = :id AND status = ANY(:statuses)
        """),
        {"id": message_id, "now": datetime.now(timezone.utc), "statuses": list(MANUALLY_RETRIABLE_STATUSES)},
    )
    if result.rowcount == 0:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"message {message_id} is not in a manually-retriable state"
        )
    write_audit_log(
        db, actor_id=current_user.id, action="message.manual_retry", entity_type="message", entity_id=str(message_id)
    )
    db.commit()
    return {"detail": f"Message {message_id} queued for retry."}
