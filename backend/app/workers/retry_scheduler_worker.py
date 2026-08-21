"""Retry is DB-driven, not Kafka-native (see docs/architecture.md): this
worker polls campaign.messages for rows in RETRYING whose next_attempt_at
is due, atomically claims them back to QUEUED with one UPDATE...RETURNING
(so two replicas of this worker - or a race with a manual /messages/{id}/
retry - can never double-claim the same row: a claim only ever succeeds
for a row still WHERE status='RETRYING'), and republishes them to their
*original* channel's dispatch topic. No .retry topics exist.
"""

import time

from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.kafka.producer import publish_batch

settings = get_settings()
configure_logging(settings.environment)
logger = get_logger(component="worker", worker_type="retry-scheduler")

BATCH_SIZE = 500
POLL_INTERVAL_SECONDS = 5.0


def claim_and_republish_due_batch(db) -> int:
    rows = db.execute(
        text("""
            WITH due AS (
                SELECT id, campaign_run_id FROM campaign.messages
                WHERE status = 'RETRYING' AND next_attempt_at <= now()
                ORDER BY next_attempt_at
                LIMIT :limit
                FOR UPDATE SKIP LOCKED
            )
            UPDATE campaign.messages m
            SET status = 'QUEUED', updated_at = now()
            FROM due
            WHERE m.id = due.id AND m.campaign_run_id = due.campaign_run_id
            RETURNING m.id, m.campaign_run_id, m.customer_msisdn, m.channel, m.message_body, m.sender_id
        """),
        {"limit": BATCH_SIZE},
    ).all()
    db.commit()

    if not rows:
        return 0

    records = [
        (
            f"campaign.dispatch.{r.channel.lower()}",
            r.customer_msisdn,
            {
                "message_id": r.id,
                "campaign_run_id": r.campaign_run_id,
                "customer_msisdn": r.customer_msisdn,
                "channel": r.channel,
                "text": r.message_body,
                "sender_id": r.sender_id,
            },
        )
        for r in rows
    ]
    publish_batch(records)
    return len(rows)


def run() -> None:
    logger.info("retry_scheduler.start")
    while True:
        db = SessionLocal()
        try:
            n = claim_and_republish_due_batch(db)
            if n:
                logger.info("retry_scheduler.republished", count=n)
        except Exception:
            logger.exception("retry_scheduler.batch_failed")
            db.rollback()
        finally:
            db.close()
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run()
