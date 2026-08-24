from datetime import datetime

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    phone: Mapped[str | None] = mapped_column(String(12), unique=True)
    """255XXXXXXXXX - required to send an OTP, so two_factor_enabled can
    never be meaningfully true without one (enforced in
    app.api.routers.auth, not just here)."""
    two_factor_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_login_at: Mapped[datetime | None]
    last_login_ip: Mapped[str | None] = mapped_column(String)
    last_login_browser: Mapped[str | None] = mapped_column(String)
