"""Tails campaign.events for unpublished rows and publishes them to Kafka,
then marks them published - the other half of the transactional outbox
pattern (writers are app.services.outbox.write_event, in the same DB
transaction as the business state change). See docs/architecture.md.

Uses SELECT ... FOR UPDATE SKIP LOCKED even though only one relay replica
runs today, so this remains correct if it's ever scaled to multiple
replicas without a rewrite.
"""

import time

from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.kafka.producer import publish

settings = get_settings()
configure_logging(settings.environment)
logger = get_logger(component="worker", worker_type="outbox-relay")

BATCH_SIZE = 500
POLL_INTERVAL_SECONDS = 1.0


def relay_one_batch(db) -> int:
    rows = db.execute(
        text("""
            SELECT id, created_at, kafka_topic, kafka_key, payload, event_type, aggregate_type, aggregate_id
            FROM campaign.events
            WHERE published_at IS NULL
            ORDER BY id
            LIMIT :limit
            FOR UPDATE SKIP LOCKED
        """),
        {"limit": BATCH_SIZE},
    ).mappings().all()

    for row in rows:
        publish(
            row["kafka_topic"],
            row["kafka_key"],
            {
                "event_type": row["event_type"],
                "aggregate_type": row["aggregate_type"],
                "aggregate_id": row["aggregate_id"],
                "payload": row["payload"],
            },
        )
        db.execute(
            text("""
                UPDATE campaign.events SET published_at = now()
                WHERE id = :id AND created_at = :created_at
            """),
            {"id": row["id"], "created_at": row["created_at"]},
        )
    db.commit()
    return len(rows)


def run() -> None:
    logger.info("outbox_relay.start")
    while True:
        db = SessionLocal()
        try:
            n = relay_one_batch(db)
            if n:
                logger.info("outbox_relay.published", count=n)
        except Exception:
            logger.exception("outbox_relay.batch_failed")
            db.rollback()
        finally:
            db.close()
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run()
