from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class StaffContact(Base, TimestampMixin):
    """A compliance roster, not a customer table: when a campaign has
    include_staff_notifications=true, every active row here is snapshotted
    into that run's messages alongside the real audience (see
    app.services.dispatch_service.queue_run_messages). Deliberately no FK
    from messages to this table - a staff member removed later must not
    retroactively affect or break historical message records."""

    __tablename__ = "staff_contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    msisdn: Mapped[str] = mapped_column(String(12), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, server_default="true")
