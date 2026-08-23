"""Orchestrates the reusable primitives (core_metrics/engagement) into one
cached rollup per campaign_run - see app.models.analytics.AnalyticsRollup.

subscription_conversion is deliberately NOT auto-computed here: a
Campaign isn't tied to a single "product it promotes" in this schema
(campaigns.product_exclusion_codes is an *exclusion* list, not a target),
so guessing which product_code to check would misrepresent the primitive
as a fixed report rather than the parameterized tool it's meant to be.
Callers request it explicitly via GET /analytics/runs/{id}/conversion
with the product_code they actually care about.
"""

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.analytics.core_metrics import compute_core_metrics
from app.analytics.engagement import compute_chat_engagement, compute_provider_engagement
from app.models.analytics import AnalyticsRollup


def compute_and_store_rollup(db: Session, campaign_run_id: int) -> AnalyticsRollup:
    core = compute_core_metrics(db, campaign_run_id)

    audience_msisdns = [
        r[0]
        for r in db.execute(
            text("SELECT customer_msisdn FROM campaign.audience_members WHERE campaign_run_id = :id AND eligible"),
            {"id": campaign_run_id},
        ).all()
    ]

    run = db.execute(
        text("SELECT started_at, completed_at FROM campaign.campaign_runs WHERE id = :id"),
        {"id": campaign_run_id},
    ).one()
    window_start = run.started_at or datetime.now(timezone.utc)
    window_end = run.completed_at or datetime.now(timezone.utc)

    chat_engagement = compute_chat_engagement(db, audience_msisdns, window_start, window_end)
    provider_engagement = compute_provider_engagement(db, audience_msisdns, window_start, window_end)

    rollup = db.get(AnalyticsRollup, campaign_run_id)
    if rollup is None:
        rollup = AnalyticsRollup(campaign_run_id=campaign_run_id)
        db.add(rollup)

    rollup.core_metrics = core
    rollup.chat_engagement = chat_engagement
    rollup.provider_engagement = provider_engagement
    rollup.computed_at = datetime.now(timezone.utc)

    db.commit()
    return rollup
