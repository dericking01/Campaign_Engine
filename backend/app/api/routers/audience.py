from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audience.eligibility import compute_eligibility_preview
from app.core.db import get_db
from app.core.deps import require_action
from app.core.permissions import Action
from app.models.bases import BaseVersion
from app.models.campaigns import CampaignRun

router = APIRouter(prefix="/audience", tags=["audience"])


class EligibilityPreviewRequest(BaseModel):
    base_version_id: int
    excluded_product_codes: list[str] = []
    campaign_category: str | None = None


class EligibilityPreviewResponse(BaseModel):
    total_candidates: int
    dnd_excluded: int
    subscriber_excluded: int
    cooldown_excluded: int
    final_eligible: int
    zone_breakdown: dict[str, int]


@router.post(
    "/preview",
    response_model=EligibilityPreviewResponse,
    dependencies=[Depends(require_action(Action.CAMPAIGN_CONFIGURE))],
)
def preview_eligibility(
    req: EligibilityPreviewRequest, db: Session = Depends(get_db)
) -> dict:
    """General-purpose Odoo-like dry-run: total candidates / DND excluded /
    subscriber excluded / cooldown excluded / final eligible / per-zone
    breakdown (requirements doc §20) - the set-based query design from
    docs/architecture.md §5. Not tied to a campaign yet (Phase 4 adds
    campaigns/campaign_runs and a persisted audience_members version of
    this same query) - callers specify the base version and exclusion
    scope directly.
    """
    base_version = db.get(BaseVersion, req.base_version_id)
    if base_version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "base version not found")

    return compute_eligibility_preview(
        db,
        base_version_id=req.base_version_id,
        excluded_product_codes=req.excluded_product_codes,
        campaign_category=req.campaign_category,
    )


class AudienceMemberOut(BaseModel):
    customer_msisdn: str
    zone: str
    eligible: bool


class AudienceMembersPage(BaseModel):
    items: list[AudienceMemberOut]
    total: int
    limit: int
    offset: int


@router.get(
    "/runs/{run_id}/members",
    response_model=AudienceMembersPage,
    dependencies=[Depends(require_action(Action.CAMPAIGN_VIEW))],
)
def list_audience_members(
    run_id: int, limit: int = 100, offset: int = 0, db: Session = Depends(get_db)
) -> dict:
    """Answers "exactly which customers were selected" - server-side
    paginated (default page size 100, capped at 1000), never rendering
    millions of rows client-side.
    """
    if db.get(CampaignRun, run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign run not found")
    limit = min(limit, 1000)

    total = db.execute(
        text("SELECT count(*) FROM campaign.audience_members WHERE campaign_run_id = :id"),
        {"id": run_id},
    ).scalar_one()
    rows = db.execute(
        text("""
            SELECT customer_msisdn, zone, eligible FROM campaign.audience_members
            WHERE campaign_run_id = :id
            ORDER BY customer_msisdn
            LIMIT :limit OFFSET :offset
        """),
        {"id": run_id, "limit": limit, "offset": offset},
    ).all()
    return {
        "items": [{"customer_msisdn": r.customer_msisdn, "zone": r.zone, "eligible": r.eligible} for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
