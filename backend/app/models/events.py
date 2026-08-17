from datetime import datetime

from sqlalchemy import BigInteger, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Event(Base):
    """Transactional outbox: business transactions write their DB state
    change and an outbox row here in the same transaction; a relay worker
    tails WHERE published_at IS NULL and publishes to Kafka, then marks it -
    avoids the dual-write problem without XA transactions. RANGE-partitioned
    weekly by created_at with retention drop of old published partitions."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(primary_key=True, server_default=func.now())
    aggregate_type: Mapped[str] = mapped_column(String, nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    kafka_topic: Mapped[str] = mapped_column(String, nullable=False)
    kafka_key: Mapped[str] = mapped_column(String, nullable=False)
    published_at: Mapped[datetime | None]
