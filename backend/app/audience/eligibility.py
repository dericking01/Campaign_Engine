"""Audience eligibility preview - the set-based query design from
docs/architecture.md §5, implemented as an aggregate SELECT (not the full
INSERT...SELECT into audience_members yet, since that needs a
campaign_run_id which doesn't exist until Phase 4's Campaign/CampaignRun
tables land). Same anti-join shape either way; Phase 4 reuses this exact
logic once there's a run to attach persisted rows to.

Replaces the legacy not_in_base.py pattern (pull subscription.subscribers
into a Python set, diff in memory) with indexed anti-joins pushed entirely
into Postgres - this is the whole point of the campaign-side
customer_subscription_state projection (app.services.subscription_service).
"""

from sqlalchemy import text
from sqlalchemy.orm import Session


def compute_eligibility_preview(
    db: Session,
    *,
    base_version_id: int,
    excluded_product_codes: list[str] | None = None,
    campaign_category: str | None = None,
) -> dict:
    excluded_product_codes = excluded_product_codes or []

    totals = db.execute(
        text("""
            SELECT
                count(*) AS total_candidates,
                count(*) FILTER (WHERE dnd.customer_msisdn IS NOT NULL) AS dnd_excluded,
                count(*) FILTER (
                    WHERE dnd.customer_msisdn IS NULL AND sub.customer_msisdn IS NOT NULL
                ) AS subscriber_excluded,
                count(*) FILTER (
                    WHERE dnd.customer_msisdn IS NULL AND sub.customer_msisdn IS NULL
                          AND cd.customer_msisdn IS NOT NULL
                ) AS cooldown_excluded,
                count(*) FILTER (
                    WHERE dnd.customer_msisdn IS NULL AND sub.customer_msisdn IS NULL
                          AND cd.customer_msisdn IS NULL
                ) AS final_eligible
            FROM campaign.base_members bm
            LEFT JOIN campaign.dnd_records dnd
                   ON dnd.customer_msisdn = bm.customer_msisdn AND dnd.is_active
            LEFT JOIN (
                SELECT DISTINCT customer_msisdn FROM campaign.customer_subscription_state
                WHERE is_subscribed AND product_code = ANY(:excluded_product_codes)
            ) sub ON sub.customer_msisdn = bm.customer_msisdn
            LEFT JOIN campaign.cooldown_state cd
                   ON cd.customer_msisdn = bm.customer_msisdn
                  AND cd.campaign_category = :campaign_category
                  AND cd.cooldown_until > now()
            WHERE bm.base_version_id = :base_version_id
        """),
        {
            "base_version_id": base_version_id,
            "excluded_product_codes": excluded_product_codes,
            "campaign_category": campaign_category,
        },
    ).mappings().one()

    zone_breakdown = db.execute(
        text("""
            SELECT coalesce(bm.territory, '(unspecified)') AS zone, count(*) AS eligible_count
            FROM campaign.base_members bm
            LEFT JOIN campaign.dnd_records dnd
                   ON dnd.customer_msisdn = bm.customer_msisdn AND dnd.is_active
            LEFT JOIN (
                SELECT DISTINCT customer_msisdn FROM campaign.customer_subscription_state
                WHERE is_subscribed AND product_code = ANY(:excluded_product_codes)
            ) sub ON sub.customer_msisdn = bm.customer_msisdn
            LEFT JOIN campaign.cooldown_state cd
                   ON cd.customer_msisdn = bm.customer_msisdn
                  AND cd.campaign_category = :campaign_category
                  AND cd.cooldown_until > now()
            WHERE bm.base_version_id = :base_version_id
              AND dnd.customer_msisdn IS NULL AND sub.customer_msisdn IS NULL AND cd.customer_msisdn IS NULL
            GROUP BY 1
            ORDER BY 2 DESC
        """),
        {
            "base_version_id": base_version_id,
            "excluded_product_codes": excluded_product_codes,
            "campaign_category": campaign_category,
        },
    ).all()

    return {
        "total_candidates": totals["total_candidates"],
        "dnd_excluded": totals["dnd_excluded"],
        "subscriber_excluded": totals["subscriber_excluded"],
        "cooldown_excluded": totals["cooldown_excluded"],
        "final_eligible": totals["final_eligible"],
        "zone_breakdown": {row.zone: row.eligible_count for row in zone_breakdown},
    }
