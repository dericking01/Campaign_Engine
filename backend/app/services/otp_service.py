"""Generic OTP request/verify - backs login 2FA, self-service password
change, and forgot-password (see app.models.auth.OtpCode's docstring for
why these three share one table/service rather than three near-identical
ones).

Delivery reuses the exact same Kannel gateway campaign dispatch uses
(app.gateways.kannel) - not a separate SMS integration - with sender_id
fixed to settings.otp_sender_id ("AFYACALL"), distinct from a campaign's
configurable sender_id since this is an AfyaCall-system message, never
campaign content.
"""

import secrets
import string
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import hash_password, verify_password
from app.gateways import kannel
from app.models.auth import OtpCode
from app.models.user import User

settings = get_settings()
logger = get_logger(component="otp_service")

_DIGITS = string.digits
_UPPER = string.ascii_uppercase


def _generate_code() -> str:
    """4 characters: 3 digits + 1 capital letter, at a randomized
    position among the 4 - not the same slot every time."""
    chars = [secrets.choice(_DIGITS) for _ in range(3)] + [secrets.choice(_UPPER)]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def request_otp(db: Session, *, user: User, purpose: str) -> str:
    """Generates a code, stores its hash, sends it via SMS, and returns
    the opaque pending_token the client holds until it calls verify_otp.
    Raises ValueError if the user has no phone on file - callers decide
    whether that's a 400 (self-service) or silently swallowed (forgot-
    password, to avoid confirming the account exists - see
    app.api.routers.auth.forgot_password_request)."""
    if not user.phone:
        raise ValueError(f"user {user.id} has no phone number on file")

    code = _generate_code()
    pending_token = secrets.token_urlsafe(32)
    otp = OtpCode(
        user_id=user.id,
        purpose=purpose,
        code_hash=hash_password(code),
        pending_token=pending_token,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expiry_minutes),
    )
    db.add(otp)
    db.flush()

    result = kannel.send(
        to_msisdn=user.phone,
        text=f"AfyaCall Campaign Engine: your verification code is {code}. "
        f"Expires in {settings.otp_expiry_minutes} minutes. Do not share this code.",
        sender_id=settings.otp_sender_id,
    )
    logger.info(
        "otp.sent", user_id=user.id, purpose=purpose, outcome=result.outcome.value, http_status=result.http_status
    )
    return pending_token


class OtpVerifyError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def verify_otp(db: Session, *, pending_token: str, code: str, purpose: str) -> User:
    """Raises OtpVerifyError on any failure (invalid token, wrong/expired
    code, already consumed, too many attempts) - the caller returns a
    uniform 401 regardless of which, so a wrong code and a bogus/expired
    token look identical to the client (no information leak about which
    part was wrong)."""
    otp = db.query(OtpCode).filter(OtpCode.pending_token == pending_token, OtpCode.purpose == purpose).first()
    if otp is None:
        raise OtpVerifyError("invalid or expired code")
    if otp.consumed_at is not None:
        raise OtpVerifyError("this code has already been used")
    if otp.expires_at < datetime.now(timezone.utc):
        raise OtpVerifyError("this code has expired")
    if otp.attempt_count >= settings.otp_max_attempts:
        raise OtpVerifyError("too many attempts - request a new code")

    otp.attempt_count += 1
    if not verify_password(code.strip().upper(), otp.code_hash):
        db.flush()
        raise OtpVerifyError("incorrect code")

    otp.consumed_at = datetime.now(timezone.utc)
    db.flush()

    user = db.get(User, otp.user_id)
    if user is None or not user.is_active:
        raise OtpVerifyError("account is no longer active")
    return user
