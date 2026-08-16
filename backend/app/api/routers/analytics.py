from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.analytics.conversion import compute_subscription_conversion
from app.analytics.rollup import compute_and_store_rollup
from app.core.db import get_db
from app.core.deps import require_action
from app.core.permissions import Action
from app.models.analytics import AnalyticsRollup
from app.models.campaigns import CampaignRun

router = APIRouter(prefix="/analytics", tags=["analytics"])


class RollupOut(BaseModel):
    campaign_run_id: int
    computed_at: str
    core_metrics: dict
    chat_engagement: dict | None
    provider_engagement: dict | None


def _rollup_out(rollup: AnalyticsRollup) -> RollupOut:
    return RollupOut(
        campaign_run_id=rollup.campaign_run_id,
        computed_at=rollup.computed_at.isoformat(),
        core_metrics=rollup.core_metrics,
        chat_engagement=rollup.chat_engagement,
        provider_engagement=rollup.provider_engagement,
    )


@router.get(
    "/runs/{run_id}",
    response_model=RollupOut,
    dependencies=[Depends(require_action(Action.REPORTS_VIEW))],
)
def run_rollup(run_id: int, refresh: bool = False, db: Session = Depends(get_db)) -> RollupOut:
    """Cached for a terminal (COMPLETED/CANCELLED) run - worker-analytics
    already computed it the moment the run finished (see
    app.workers.message_events_worker / app.workers.analytics_worker).
    For a still-RUNNING run, or if ?refresh=true, computes fresh (a live
    snapshot) and updates the cache - cheap enough to do on every request
    (see app.analytics.core_metrics), unlike the chat-engagement scan
    which stays cache-first even on refresh for a terminal run.
    """
    run = db.get(CampaignRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign run not found")

    existing = db.get(AnalyticsRollup, run_id)
    if existing is not None and not refresh and run.status not in ("RUNNING",):
        return _rollup_out(existing)

    rollup = compute_and_store_rollup(db, run_id)
    return _rollup_out(rollup)


class ConversionOut(BaseModel):
    audience_size: int
    subscribed_count: int
    conversion_rate: float | None
    product_code: str


@router.get(
    "/runs/{run_id}/conversion",
    response_model=ConversionOut,
    dependencies=[Depends(require_action(Action.REPORTS_VIEW))],
)
def run_conversion(run_id: int, product_code: str, db: Session = Depends(get_db)) -> dict:
    """Subscription-conversion attribution, parameterized by product_code
    (not auto-computed - see app.analytics.rollup for why a campaign
    isn't tied to a single "product it promotes" in this schema)."""
    if db.get(CampaignRun, run_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign run not found")

    msisdns = [
        r[0]
        for r in db.execute(
            text("SELECT customer_msisdn FROM campaign.audience_members WHERE campaign_run_id = :id AND eligible"),
            {"id": run_id},
        ).all()
    ]
    return compute_subscription_conversion(db, msisdns, product_code)


class CampaignSummaryOut(BaseModel):
    campaign_id: int
    total_runs: int
    rolled_up_runs: int
    total_sent: int
    total_dead: int
    total_failed_unconfirmed: int
    total_audience: int
    avg_success_rate: float | None
    avg_engagement_rate: float | None


@router.get(
    "/campaigns/{campaign_id}/summary",
    response_model=CampaignSummaryOut,
    dependencies=[Depends(require_action(Action.REPORTS_VIEW))],
)
def campaign_summary(campaign_id: int, db: Session = Depends(get_db)) -> dict:
    """Aggregates every already-rolled-up run of a campaign - runs still
    RUNNING/PENDING (no rollup cached yet) are counted in total_runs but
    excluded from the aggregate numbers, per rolled_up_runs vs total_runs.
    """
    runs = db.query(CampaignRun).filter(CampaignRun.campaign_id == campaign_id).all()
    if not runs:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no runs found for this campaign")

    rollups = (
        db.query(AnalyticsRollup)
        .filter(AnalyticsRollup.campaign_run_id.in_([r.id for r in runs]))
        .all()
    )

    total_sent = total_dead = total_fu = total_audience = 0
    success_rates: list[float] = []
    engagement_rates: list[float] = []
    for r in rollups:
        counts = r.core_metrics.get("status_counts", {})
        total_sent += counts.get("SENT", 0)
        total_dead += counts.get("DEAD", 0)
        total_fu += counts.get("FAILED_UNCONFIRMED", 0)
        total_audience += r.core_metrics.get("total_audience", 0)
        if r.core_metrics.get("success_rate") is not None:
            success_rates.append(r.core_metrics["success_rate"])
        if r.chat_engagement and r.chat_engagement.get("engagement_rate") is not None:
            engagement_rates.append(r.chat_engagement["engagement_rate"])

    return {
        "campaign_id": campaign_id,
        "total_runs": len(runs),
        "rolled_up_runs": len(rollups),
        "total_sent": total_sent,
        "total_dead": total_dead,
        "total_failed_unconfirmed": total_fu,
        "total_audience": total_audience,
        "avg_success_rate": (sum(success_rates) / len(success_rates)) if success_rates else None,
        "avg_engagement_rate": (sum(engagement_rates) / len(engagement_rates)) if engagement_rates else None,
    }
