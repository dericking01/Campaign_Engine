from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return _pwd_context.verify(plain_password, password_hash)


def create_access_token(subject: str, role: str, session_token: str) -> str:
    """`exp` is the JWT's own crypto-expiry ceiling (generous, see
    settings.jwt_access_token_expire_minutes) - the real session length
    enforcement is the sliding `sid` lookup in app.core.deps.
    get_current_user (app.services.session_service.touch_session), which
    can invalidate this token long before `exp` if the session goes
    idle."""
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload: dict[str, Any] = {"sub": subject, "role": role, "sid": session_token, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
