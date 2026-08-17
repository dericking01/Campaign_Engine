import json

from confluent_kafka import Producer

from app.core.config import get_settings

settings = get_settings()

_producer: Producer | None = None


def get_producer() -> Producer:
    global _producer
    if _producer is None:
        _producer = Producer({"bootstrap.servers": settings.kafka_bootstrap_servers})
    return _producer


def publish(topic: str, key: str, payload: dict) -> None:
    """Synchronous produce+flush: correct and simple for the outbox relay's
    one-event-at-a-time, low-frequency lifecycle notifications (this
    function only needs to know delivery succeeded before marking a
    campaign.events row published_at). Phase 5's dispatch workers need much
    higher throughput and use publish_batch() instead - do not reuse this
    helper for the dispatch hot path."""
    producer = get_producer()
    producer.produce(topic, key=key.encode("utf-8"), value=json.dumps(payload).encode("utf-8"))
    producer.flush(timeout=10)


def publish_batch(records: list[tuple[str, str, dict]]) -> None:
    """Queues many (topic, key, payload) records with librdkafka's internal
    buffer (produce() is async - no per-message network round trip) and
    flushes once at the end. Used when materializing a run's messages,
    where the queuing step may publish anywhere from a handful to millions
    of dispatch commands - a flush-per-message here would make queuing
    throughput-bound by network round trips instead of by Postgres/Kafka
    themselves."""
    producer = get_producer()
    for topic, key, payload in records:
        producer.produce(topic, key=key.encode("utf-8"), value=json.dumps(payload).encode("utf-8"))
        producer.poll(0)  # serve delivery-report callbacks / avoid queue buildup
    producer.flush(timeout=30)
