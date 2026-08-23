"""Consumes campaign.message-events (message.attempt_outcome, written by
app.services.dispatch_service.process_dispatch_message on every dispatch
attempt) and closes a real gap: nothing previously transitioned a run out
of RUNNING once its dispatch naturally finished - it just sat there
forever, even after every message reached a terminal status. On each
terminal outcome, checks whether the whole run is now done
(app.services.dispatch_service.check_and_complete_run) and, if so, flips
it to COMPLETED and publishes to campaign.analytics.events - the trigger
worker-analytics consumes to compute and cache that run's rollup (see
app.analytics.rollup) once, rather than every dashboard view recomputing
it from scratch.

Same at-least-once + idempotent-DB-CAS pattern as every other consumer in
this codebase; same seek()-on-failure fix as app.workers.audience_worker
(skipping a commit alone doesn't guarantee redelivery within a single
running process - see docs/decisions.md #35).
"""

import json
import time

from confluent_kafka import Consumer, TopicPartition

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.services.dispatch_service import check_and_complete_run

settings = get_settings()
configure_logging(settings.environment)
logger = get_logger(component="worker", worker_type="message-events")

TOPIC = "campaign.message-events"
GROUP_ID = "message-events-workers"

_TERMINAL_STATUSES = ("SENT", "DEAD", "FAILED_UNCONFIRMED")


def handle_event(db, event: dict) -> None:
    event_type = event.get("event_type")
    payload = event.get("payload", {})

    if event_type != "message.attempt_outcome":
        logger.debug("message_events.ignored_event_type", event_type=event_type)
        return

    if payload.get("status") not in _TERMINAL_STATUSES:
        return

    completed = check_and_complete_run(db, payload["campaign_run_id"])
    if completed:
        logger.info("message_events.run_completed", campaign_run_id=payload["campaign_run_id"])


def run() -> None:
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": GROUP_ID,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([TOPIC])
    logger.info("message_events_worker.start", topic=TOPIC)

    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                logger.error("message_events_worker.consume_error", error=str(msg.error()))
                continue

            event = json.loads(msg.value())
            db = SessionLocal()
            try:
                handle_event(db, event)
                consumer.commit(msg)
            except Exception:
                logger.exception("message_events_worker.handle_failed", kafka_event=event)
                db.rollback()
                consumer.seek(TopicPartition(msg.topic(), msg.partition(), msg.offset()))
                time.sleep(2)
            finally:
                db.close()
    finally:
        consumer.close()


if __name__ == "__main__":
    run()
