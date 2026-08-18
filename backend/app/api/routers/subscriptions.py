from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_action
from app.core.permissions import Action
from app.models.user import User
from app.services.audit import write_audit_log
from app.services.subscription_service import sync_subscriptions

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


class SyncRequest(BaseModel):
    product_code: str = "AFYACALL_SUBSCRIBER"


class SyncResult(BaseModel):
    product_code: str
    upserted: int
    unsubscribed: int


@router.post("/sync", response_model=SyncResult)
def sync(
    req: SyncRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.SYSTEM_CONFIGURE)),
) -> dict:
    """Runs synchronously (not via Kafka/worker like imports): this is a
    single set-based SQL statement pair entirely inside Postgres, not a
    file stream - even at 2M+ source rows it completes in seconds, not
    minutes. Revisit if subscription.subscribers grows enough to change
    that.

    product_code defaults to a single generic "subscribed to AfyaCall"
    signal since subscription.subscribers is one flat table, not
    per-product - see docs/decisions.md item 7 (still open: the richer
    per-product exclusion model this table supports needs the actual
    per-product source tables identified first).
    """
    db.execute(
        text("""
            INSERT INTO campaign.customer_products (code, label)
            VALUES (:code, :code)
            ON CONFLICT (code) DO NOTHING
        """),
        {"code": req.product_code},
    )
    db.commit()
    result = sync_subscriptions(db, req.product_code)
    write_audit_log(
        db,
        actor_id=current_user.id,
        action="subscription.sync",
        entity_type="customer_product",
        entity_id=req.product_code,
        new_value=result,
    )
    db.commit()
    return result
