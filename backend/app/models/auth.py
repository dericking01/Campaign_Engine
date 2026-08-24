from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OtpCode(Base):
    """A generic, purpose-tagged one-time-code - LOGIN_2FA / PASSWORD_CHANGE
    / PASSWORD_RESET all share this one table rather than three near-
    identical ones. code_hash is never the plaintext code (same principle
    as User.password_hash - see app.services.otp_service). pending_token
    is the opaque, random identifier handed to the client between
    "request an OTP" and "verify it" - the client never sees user_id or
    the code itself before verification succeeds."""

    __tablename__ = "otp_codes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("campaign.users.id", ondelete="CASCADE"), nullable=False)
    purpose: Mapped[str] = mapped_column(String, nullable=False)
    code_hash: Mapped[str] = mapped_column(String, nullable=False)
    pending_token: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    consumed_at: Mapped[datetime | None]
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class UserSession(Base):
    """Backs the sliding 30-minute-inactivity session model - the JWT
    carries this row's session_token as its `sid` claim; every
    authenticated request checks and bumps last_activity_at (see
    app.services.session_service / app.core.deps.get_current_user), so
    activity extends the session independently of the JWT's own
    (longer) cryptographic expiry."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("campaign.users.id", ondelete="CASCADE"), nullable=False)
    session_token: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    ip_address: Mapped[str | None] = mapped_column(String)
    user_agent: Mapped[str | None] = mapped_column(String)
    browser: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_activity_at: Mapped[datetime] = mapped_column(server_default=func.now())
    revoked_at: Mapped[datetime | None]
