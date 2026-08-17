"""Transactional outbox writer.

Callers write their business state change and an outbox row in the same
DB transaction (same Session, no commit in between) - a separate relay
worker (app.workers.outbox_relay_worker) tails unpublished rows and
publishes them to Kafka. This is what makes "write to Postgres" and
"notify Kafka" atomic without XA transactions - see docs/architecture.md.
"""

from datetime import datetime, timezone

from app.models.events import Event


def write_event(
    db,
    *,
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    payload: dict,
    kafka_topic: str,
    kafka_key: str,
) -> Event:
    event = Event(
        created_at=datetime.now(timezone.utc),
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload,
        kafka_topic=kafka_topic,
        kafka_key=kafka_key,
    )
    db.add(event)
    return event
