from datetime import datetime

from sqlalchemy import BigInteger, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Message(Base, TimestampMixin):
    """The idempotency-critical table: UNIQUE(campaign_run_id,
    customer_msisdn, channel) is the canonical identity used throughout the
    dispatch pipeline (see docs/architecture.md §Idempotency). HASH-partitioned
    by campaign_run_id (32 partitions). `channel` is deliberately duplicated
    here (derivable from campaign_runs->campaigns) because the dispatcher's
    hot-path CAS update must not join across tables under load."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    campaign_run_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    customer_msisdn: Mapped[str] = mapped_column(String(12), nullable=False)
    channel: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="CREATED")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_attempt_at: Mapped[datetime | None]
    message_body: Mapped[str | None] = mapped_column(String)
    sender_id: Mapped[str | None] = mapped_column(String)
    """Resolved once at queue time (campaign override, else the channel's
    default) and carried through Kafka on every publish/republish, so the
    dispatch/retry hot path never needs a channel_configs lookup."""


class MessageAttempt(Base):
    """Append-only attempt/audit detail, RANGE-partitioned monthly by
    attempted_at. campaign_run_id is denormalized from Message purely so the
    FK to the (campaign_run_id, id) composite key on the HASH-partitioned
    `messages` table is expressible - see docs/architecture.md."""

    __tablename__ = "message_attempts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    attempted_at: Mapped[datetime] = mapped_column(primary_key=True, server_default=func.now())
    campaign_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    kannel_port: Mapped[int | None] = mapped_column(Integer)
    http_status: Mapped[int | None] = mapped_column(Integer)
    kannel_response_body: Mapped[str | None] = mapped_column(String)
    outcome: Mapped[str | None] = mapped_column(String)
