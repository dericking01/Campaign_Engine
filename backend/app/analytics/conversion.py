"""Campaign-to-subscription conversion - requirements doc §31's
"campaign-to-subscription conversion" core metric, and one of the
"product activation" attribution dimensions. Reuses
campaign.customer_subscription_state (Phase 3's set-based subscriber
sync) rather than a new data source.

Honest limitation, not hidden: customer_subscription_state only records
current is_subscribed status + when it was last synced (source =
'BATCH_SYNC'), not a per-customer activation timestamp. This function
reports *correlation* - "of the campaign's audience, how many are
currently subscribed" - not proven causation (an audience member could
have already been subscribed before the campaign ran, or activated for
an unrelated reason). A rigorous before/after causal measure would need
a subscription-state snapshot taken at campaign-send time, which doesn't
exist. Documented in docs/decisions.md rather than silently overstating
what this number means.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session


def compute_subscription_conversion(db: Session, msisdns: list[str], product_code: str) -> dict:
    if not msisdns:
        return {"audience_size": 0, "subscribed_count": 0, "conversion_rate": None, "product_code": product_code}

    subscribed_count = db.execute(
        text("""
            SELECT count(*) FROM campaign.customer_subscription_state
            WHERE customer_msisdn = ANY(:msisdns) AND product_code = :product_code AND is_subscribed
        """),
        {"msisdns": msisdns, "product_code": product_code},
    ).scalar_one()

    audience_size = len(msisdns)
    return {
        "audience_size": audience_size,
        "subscribed_count": subscribed_count,
        "conversion_rate": (subscribed_count / audience_size) if audience_size else None,
        "product_code": product_code,
    }
