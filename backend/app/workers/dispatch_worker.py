"""Consumes one channel's campaign.dispatch.{sms,ivr,doctor} topic and
calls app.services.dispatch_service.process_dispatch_message for each
command - the actual Kannel-calling hot path. One process per channel
(WORKER_TYPE=dispatch-sms/dispatch-ivr/dispatch-doctor selects which topic
via stub_runner), matching channel_configs' independent per-channel TPS
sub-allocations.

Rate-limit backpressure (app.redis.ratelimit.acquire_blocking) is handled
inside process_dispatch_message: when the ceiling is saturated, it raises
TimeoutError instead of touching the DB. Simply *not* calling commit()
would NOT redeliver this message on the next poll() within the same live
session - librdkafka's fetch position already advanced past it regardless
of whether the offset was committed, and if a later message's commit()
then succeeds, that commit's watermark silently jumps past this one,
permanently losing it even on a future restart (Kafka offset commits are
a single moving high-water mark per partition, not sparse
acknowledgments). The correct fix is an explicit seek() back to this
message's own offset before the next poll(), so it is genuinely
re-fetched and retried in place - the partition is intentionally blocked
on this message until the rate limiter admits it, exactly like the
single-threaded legacy scripts' own throttling loop, just coordinated
globally now instead of per-script.
"""

import json
import os
import time

from confluent_kafka import Consumer, TopicPartition

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.services.dispatch_service import process_dispatch_message

settings = get_settings()
configure_logging(settings.environment)

CHANNEL = os.environ.get("WORKER_TYPE", "dispatch-sms").removeprefix("dispatch-").upper()
TOPIC = f"campaign.dispatch.{CHANNEL.lower()}"
GROUP_ID = f"dispatch-{CHANNEL.lower()}-workers"

logger = get_logger(component="worker", worker_type=f"dispatch-{CHANNEL.lower()}")


def handle_message(db, payload: dict) -> None:
    process_dispatch_message(
        db,
        message_id=payload["message_id"],
        campaign_run_id=payload["campaign_run_id"],
        channel=payload["channel"],
        text_body=payload.get("text"),
        sender_id=payload["sender_id"],
    )


def run() -> None:
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": GROUP_ID,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
            # One message's handling is bounded (a rate-limit wait capped
            # at 5s plus one Kannel HTTP call) - the default 5-minute
            # max.poll.interval.ms is generous here, no override needed.
        }
    )
    consumer.subscribe([TOPIC])
    logger.info("dispatch_worker.start", topic=TOPIC, channel=CHANNEL)

    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                logger.error("dispatch_worker.consume_error", error=str(msg.error()))
                continue

            payload = json.loads(msg.value())
            db = SessionLocal()
            try:
                handle_message(db, payload)
                consumer.commit(msg)
            except TimeoutError:
                # Rate limiter saturated - no DB write happened. Seek back
                # to this exact message so it is retried in place (see
                # module docstring for why not-committing alone is not
                # sufficient here).
                db.rollback()
                logger.info("dispatch_worker.rate_limited_retry", topic=msg.topic(), offset=msg.offset())
                consumer.seek(TopicPartition(msg.topic(), msg.partition(), msg.offset()))
                time.sleep(0.2)
            except Exception:
                logger.exception("dispatch_worker.handle_failed", kafka_payload=payload)
                db.rollback()
            finally:
                db.close()
    finally:
        consumer.close()


if __name__ == "__main__":
    run()
