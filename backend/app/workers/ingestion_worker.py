"""Consumes campaign.import.events and runs the actual streaming
stage/commit pipeline (app.services.import_service) out-of-process from the
API - keeping the control-plane/data-plane separation the requirements doc
calls for (a 17M-row import must never run inside an API request/response
cycle or block the API's event loop).

At-least-once delivery, idempotent-by-design consumption: the Kafka offset
is committed only after the DB work for that message fully completes (see
docs/architecture.md Idempotency section). A redelivered stage_requested
event just re-runs stage_import, which is safe to re-run (COPY into
import_staging_rows would duplicate rows on a true re-run of an
already-staged import, so this worker additionally guards by checking the
import's current status before acting - see _should_process).
"""

import json
import time

from confluent_kafka import Consumer, TopicPartition

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.models.imports import Import
from app.redis.locks import LockNotAcquired, distributed_lock
from app.services.import_service import commit_import, stage_import

settings = get_settings()
configure_logging(settings.environment)
logger = get_logger(component="worker", worker_type="ingestion")

TOPIC = "campaign.import.events"
GROUP_ID = "ingestion-workers"


def _should_process(db, import_id: int, expected_statuses: set[str]) -> bool:
    imp = db.get(Import, import_id)
    if imp is None:
        logger.warning("ingestion.import_not_found", import_id=import_id)
        return False
    if imp.status not in expected_statuses:
        logger.info(
            "ingestion.skip_stale_event",
            import_id=import_id,
            current_status=imp.status,
            expected_statuses=sorted(expected_statuses),
        )
        return False
    return True


def _handle_locked(db, event_type: str, import_id: int, payload: dict) -> None:
    """Runs the actual status-check-then-act sequence. Must only ever be
    called while holding campaign:lock:import:{import_id} - see
    handle_event. The status check alone is not a sufficient concurrency
    guard (TOCTOU under READ COMMITTED: two concurrent transactions can
    both read the pre-claim status before either commits) - caught live
    during Phase 2 real-scale testing when two commit_import() calls for
    the same import ran concurrently. See docs/decisions.md.
    """
    if event_type == "import.stage_requested":
        # VALIDATING is included so a stage that was interrupted mid-stream
        # (container killed, not a clean exception) can be safely re-run
        # from scratch on redelivery - stage_import() itself discards any
        # partial staging rows before restarting. See its docstring.
        if _should_process(db, import_id, {"IMPORT_CREATED", "UPLOADED", "VALIDATING"}):
            stage_import(db, import_id)
    elif event_type == "import.commit_requested":
        if _should_process(db, import_id, {"APPROVED"}):
            commit_import(
                db,
                import_id,
                base_id=payload.get("base_id"),
                dnd_list_name=payload.get("dnd_list_name"),
            )
    else:
        logger.debug("ingestion.ignored_event_type", event_type=event_type)


def handle_event(db, event: dict) -> None:
    event_type = event.get("event_type")
    payload = event.get("payload", {})
    import_id = payload.get("import_id")

    if event_type not in ("import.stage_requested", "import.commit_requested"):
        logger.debug("ingestion.ignored_event_type", event_type=event_type)
        return

    # TTL matches max.poll.interval.ms below - both bounds exist for the
    # same reason (a large-file stage/commit can legitimately run for many
    # minutes) and should not silently drift apart.
    with distributed_lock(f"campaign:lock:import:{import_id}", ttl_seconds=3600):
        _handle_locked(db, event_type, import_id, payload)


def run() -> None:
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": GROUP_ID,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
            # Default max.poll.interval.ms (5 min) assumes a fast per-message
            # handler and evicts the consumer from the group if poll() isn't
            # called again in time. This worker's handler can legitimately
            # run for many minutes on a large file (verified live: a 17M-row
            # file took ~19 min end-to-end) with no poll() call in between,
            # since the whole file is processed inside one handle_event()
            # call. Caught live during Phase 2 real-scale testing: staging
            # completed correctly, but the group evicted this consumer
            # mid-way, leaving it unable to cleanly pick up the next
            # message. Raised generously (1h) rather than restructuring the
            # loop to poll(0) during processing, since ingestion work is
            # fundamentally long-running. NOTE: this worker does not
            # currently heartbeat into Redis during a long stage_import()
            # call (real workers bypass app.workers.stub_runner's heartbeat
            # loop entirely), so liveness monitoring can't yet distinguish
            # "still streaming a large file" from "wedged" - flagged in
            # docs/decisions.md as a follow-up.
            "max.poll.interval.ms": 3_600_000,
        }
    )
    consumer.subscribe([TOPIC])
    logger.info("ingestion_worker.start", topic=TOPIC)

    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                logger.error("ingestion_worker.consume_error", error=str(msg.error()))
                continue

            event = json.loads(msg.value())
            db = SessionLocal()
            try:
                handle_event(db, event)
                consumer.commit(msg)  # only after DB work fully succeeded
            except LockNotAcquired:
                # Another invocation is actively processing this import
                # right now (e.g. an overlapping worker during a redeploy,
                # or a manual retry racing a still-running attempt) - not a
                # failure. Seek back so this event is redelivered and
                # re-checked once the lock is free (see the seek() note in
                # the Exception branch below for why not-committing alone
                # is not sufficient).
                logger.info("ingestion.import_locked_elsewhere", event=event)
                db.rollback()
                consumer.seek(TopicPartition(msg.topic(), msg.partition(), msg.offset()))
                time.sleep(1)
            except Exception:
                # NB: "event" is structlog's own reserved kwarg for the log
                # message itself - the Kafka event payload must use a
                # different key or logger.exception() raises a TypeError.
                logger.exception("ingestion_worker.handle_failed", kafka_event=event)
                db.rollback()
                # Seek back to this message rather than merely skipping
                # the commit: within a single running process, skipping
                # alone does not cause redelivery on the next poll() -
                # if a later message then commits successfully, the
                # committed high-water mark silently jumps past this one,
                # permanently losing it even on a future restart. See
                # app.workers.dispatch_worker's module docstring for the
                # full explanation (found live while building Phase 5).
                consumer.seek(TopicPartition(msg.topic(), msg.partition(), msg.offset()))
                time.sleep(2)
            finally:
                db.close()
    finally:
        consumer.close()


if __name__ == "__main__":
    run()
