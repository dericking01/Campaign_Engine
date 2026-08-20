"""Consumes campaign.audience.events and runs the rotation engine
out-of-process from the API - same control-plane/data-plane separation
principle as worker-ingestion, and the same at-least-once-delivery +
idempotent-DB-CAS pattern (see docs/architecture.md Idempotency section).

Offset commits only after generate_audience() fully succeeds; a crash mid-
rotation leaves the in-progress zone's transaction rolled back (nothing
partial), so redelivery just resumes cleanly - see app.rotation.engine and
app.services.campaign_service docstrings for why that's sufficient.
"""

import json
import time

from confluent_kafka import Consumer, TopicPartition

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.redis.locks import LockNotAcquired
from app.services.campaign_service import generate_audience

settings = get_settings()
configure_logging(settings.environment)
logger = get_logger(component="worker", worker_type="audience")

TOPIC = "campaign.audience.events"
GROUP_ID = "audience-workers"


def handle_event(db, event: dict) -> None:
    event_type = event.get("event_type")
    payload = event.get("payload", {})

    if event_type == "audience.generate_requested":
        generate_audience(db, payload["campaign_run_id"])
    else:
        logger.debug("audience.ignored_event_type", event_type=event_type)


def run() -> None:
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": GROUP_ID,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
            # Rotation over a large base can take real time (the eligibility
            # anti-join alone was measured at 18.5s for 16.9M rows; several
            # zones in one run compounds that) - same rationale as
            # worker-ingestion's identical setting.
            "max.poll.interval.ms": 3_600_000,
        }
    )
    consumer.subscribe([TOPIC])
    logger.info("audience_worker.start", topic=TOPIC)

    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                logger.error("audience_worker.consume_error", error=str(msg.error()))
                continue

            event = json.loads(msg.value())
            db = SessionLocal()
            try:
                handle_event(db, event)
                consumer.commit(msg)
            except LockNotAcquired:
                logger.info("audience_worker.locked_elsewhere", event=event)
                db.rollback()
                # Seek back rather than merely skipping the commit - see
                # app.workers.dispatch_worker's module docstring for why
                # skipping alone doesn't guarantee redelivery within a
                # single running process (found live while building Phase 5).
                consumer.seek(TopicPartition(msg.topic(), msg.partition(), msg.offset()))
                time.sleep(1)
            except Exception:
                logger.exception("audience_worker.handle_failed", kafka_event=event)
                db.rollback()
                consumer.seek(TopicPartition(msg.topic(), msg.partition(), msg.offset()))
                time.sleep(2)
            finally:
                db.close()
    finally:
        consumer.close()


if __name__ == "__main__":
    run()
