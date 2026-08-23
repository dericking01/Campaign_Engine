"""Consumes campaign.analytics.events (currently just 'run.completed',
published by app.services.dispatch_service.check_and_complete_run once a
run's dispatch naturally finishes) and materializes that run's rollup via
app.analytics.rollup.compute_and_store_rollup - once, cached in
campaign.analytics_rollups, rather than every dashboard view recomputing
core metrics + chat/provider engagement from scratch against
potentially millions of message rows and a 2M-row external chat_history
table.

Same at-least-once + idempotent pattern as every other consumer here:
compute_and_store_rollup is a plain upsert (INSERT-or-UPDATE by
campaign_run_id), so redelivery just recomputes and overwrites with the
same answer - safe, not merely tolerated.
"""

import json
import time

from confluent_kafka import Consumer, TopicPartition

from app.analytics.rollup import compute_and_store_rollup
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger

settings = get_settings()
configure_logging(settings.environment)
logger = get_logger(component="worker", worker_type="analytics")

TOPIC = "campaign.analytics.events"
GROUP_ID = "analytics-workers"


def handle_event(db, event: dict) -> None:
    event_type = event.get("event_type")
    payload = event.get("payload", {})

    if event_type == "run.completed":
        compute_and_store_rollup(db, payload["campaign_run_id"])
    else:
        logger.debug("analytics.ignored_event_type", event_type=event_type)


def run() -> None:
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": GROUP_ID,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
            # The chat-engagement query scans a real ~2M-row external
            # table with no index this app can add (see
            # app.analytics.engagement) - generous but bounded, same
            # rationale as the ingestion/audience workers' identical
            # setting for their own genuinely-slow operations.
            "max.poll.interval.ms": 600_000,
        }
    )
    consumer.subscribe([TOPIC])
    logger.info("analytics_worker.start", topic=TOPIC)

    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                logger.error("analytics_worker.consume_error", error=str(msg.error()))
                continue

            event = json.loads(msg.value())
            db = SessionLocal()
            try:
                handle_event(db, event)
                consumer.commit(msg)
            except Exception:
                logger.exception("analytics_worker.handle_failed", kafka_event=event)
                db.rollback()
                consumer.seek(TopicPartition(msg.topic(), msg.partition(), msg.offset()))
                time.sleep(2)
            finally:
                db.close()
    finally:
        consumer.close()


if __name__ == "__main__":
    run()
