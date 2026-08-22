from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Role(Base, TimestampMixin):
    """The assignable role catalog - GUI-configurable (see
    app/api/routers/roles.py), unlike Action (app.core.permissions), which
    stays a fixed code-level enum since each Action corresponds to a real
    require_action() call already wired into a specific endpoint.
    is_system=true marks the 5 originally-seeded roles: protected from
    deletion, and SUPER_ADMIN specifically can't have its permission set
    edited either - see roles.py for why."""

    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_code: Mapped[str] = mapped_column(String, ForeignKey("campaign.roles.code", ondelete="CASCADE"), primary_key=True)
    action: Mapped[str] = mapped_column(String, primary_key=True)
