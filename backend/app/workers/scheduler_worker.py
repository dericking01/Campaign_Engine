"""Consumes campaign.audience.events for 'run.start_requested' and runs
the message-queuing step (app.services.dispatch_service.queue_run_messages)
out-of-process from the API - same pattern as worker-audience for
'audience.generate_requested' on the same topic. Reusing the topic (rather
than adding a new one) keeps campaign_run lifecycle events in one place;
this worker just filters for the event types it owns.

Same at-least-once + commit-after-DB-success pattern as every other worker
here - see docs/architecture.md Idempotency section.
"""

import json
import time

from confluent_kafka import Consumer, TopicPartition

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.services.dispatch_service import queue_run_messages

settings = get_settings()
configure_logging(settings.environment)
logger = get_logger(component="worker", worker_type="scheduler")

TOPIC = "campaign.audience.events"
GROUP_ID = "scheduler-workers"


def handle_event(db, event: dict) -> None:
    event_type = event.get("event_type")
    payload = event.get("payload", {})

    if event_type == "run.start_requested":
        queue_run_messages(db, payload["campaign_run_id"])
    else:
        logger.debug("scheduler.ignored_event_type", event_type=event_type)


def run() -> None:
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": GROUP_ID,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
            # Materializing + publishing messages for a large run can take
            # real time (same rationale as worker-audience/worker-ingestion).
            "max.poll.interval.ms": 3_600_000,
        }
    )
    consumer.subscribe([TOPIC])
    logger.info("scheduler_worker.start", topic=TOPIC)

    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                logger.error("scheduler_worker.consume_error", error=str(msg.error()))
                continue

            event = json.loads(msg.value())
            db = SessionLocal()
            try:
                handle_event(db, event)
                consumer.commit(msg)
            except Exception:
                # Seek back to this exact message rather than merely
                # skipping the commit: within a single running process,
                # skipping alone does NOT cause redelivery on the next
                # poll() (librdkafka's fetch position already moved past
                # it) - if a later message then commits successfully, the
                # committed high-water mark silently jumps past this one,
                # permanently losing it even on a future restart. See
                # app.workers.dispatch_worker's module docstring for the
                # full explanation (found live while building Phase 5).
                logger.exception("scheduler_worker.handle_failed", kafka_event=event)
                db.rollback()
                consumer.seek(TopicPartition(msg.topic(), msg.partition(), msg.offset()))
                time.sleep(2)
            finally:
                db.close()
    finally:
        consumer.close()


if __name__ == "__main__":
    run()
