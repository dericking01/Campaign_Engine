"""Batch sync of campaign.customer_subscription_state against the existing
subscription.subscribers table.

This is the direct fix for the anti-pattern in the legacy
not_in_base.py script, which ran `SELECT DISTINCT customer_msisdn FROM
subscription.subscribers`, pulled all ~2.1M rows into a Python/pandas set,
and computed the exclusion diff in application memory. Since
subscription.subscribers lives in the *same* Postgres database (just a
different schema - campaign_app has read-only SELECT on it, see
deploy/scripts/bootstrap_db.sh), the correct fix isn't "stream it out and
copy it back in" - it's a single set-based INSERT...SELECT that never
leaves Postgres at all, letting the database do what it's already good at.

Verified live: subscription.subscribers.customer_msisdn is already 100%
canonical (255 + 9 digits, confirmed against all 2,093,596 real rows), so
no normalization step is needed here - the regex guard below is defensive
consistency, not a required transformation.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.logging import get_logger

logger = get_logger(component="subscription_service")


def sync_subscriptions(db: Session, product_code: str) -> dict:
    """Upserts current subscribers as is_subscribed=true, then flips
    anyone previously tracked for this product who has since disappeared
    from the source table to is_subscribed=false (never deletes - history
    is preserved, matching the append-only spirit of the rest of the
    schema)."""
    upserted = db.execute(
        text("""
            INSERT INTO campaign.customer_subscription_state
                (customer_msisdn, product_code, is_subscribed, source, synced_at)
            SELECT DISTINCT customer_msisdn, :product_code, true, 'BATCH_SYNC', now()
            FROM subscription.subscribers
            WHERE customer_msisdn ~ '^255[0-9]{9}$'
            ON CONFLICT (customer_msisdn, product_code)
            DO UPDATE SET is_subscribed = true, source = 'BATCH_SYNC', synced_at = now()
        """),
        {"product_code": product_code},
    ).rowcount

    unsubscribed = db.execute(
        text("""
            UPDATE campaign.customer_subscription_state s
            SET is_subscribed = false, source = 'BATCH_SYNC', synced_at = now()
            WHERE s.product_code = :product_code AND s.is_subscribed = true
              AND NOT EXISTS (
                  SELECT 1 FROM subscription.subscribers b
                  WHERE b.customer_msisdn = s.customer_msisdn
              )
        """),
        {"product_code": product_code},
    ).rowcount

    db.commit()
    logger.info(
        "subscription.synced", product_code=product_code, upserted=upserted, unsubscribed=unsubscribed
    )
    return {"product_code": product_code, "upserted": upserted, "unsubscribed": unsubscribed}
