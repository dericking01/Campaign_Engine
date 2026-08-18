from datetime import datetime

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DndList(Base, TimestampMixin):
    """Versioned DND dataset. 'On DND' = union of all active records across
    all active lists (default policy - see docs/decisions.md)."""

    __tablename__ = "dnd_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    source_import_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("campaign.imports.id")
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    effective_from: Mapped[datetime | None]
    effective_to: Mapped[datetime | None]


class DndRecord(Base):
    __tablename__ = "dnd_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    dnd_list_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("campaign.dnd_lists.id", ondelete="CASCADE"), nullable=False
    )
    customer_msisdn: Mapped[str] = mapped_column(String(12), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
