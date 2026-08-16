from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditLog(Base):
    """Append-only, RANGE-partitioned monthly by created_at. Every high-impact
    action (import approval, campaign start/pause/stop, config changes, ...)
    writes one row here - see docs/architecture.md."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(primary_key=True, server_default=func.now())
    actor_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("campaign.users.id"))
    action: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String)
    old_value: Mapped[dict | None] = mapped_column(JSONB)
    new_value: Mapped[dict | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(String)
