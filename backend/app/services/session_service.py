"""Sliding-inactivity sessions - see app.models.auth.UserSession's
docstring. A session is created once (on successful login, after any
2FA step) and then only ever touched (last_activity_at bumped) or
revoked; the JWT's `sid` claim is what ties a request back to its row.
"""

import re
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.auth import UserSession

settings = get_settings()

_BROWSER_PATTERNS = [
    ("Edge", r"Edg/"),
    ("Opera", r"OPR/|Opera/"),
    ("Chrome", r"Chrome/"),
    ("Firefox", r"Firefox/"),
    ("Safari", r"Version/.*Safari/"),
]


def parse_browser(user_agent: str | None) -> str:
    if not user_agent:
        return "Unknown"
    for name, pattern in _BROWSER_PATTERNS:
        if re.search(pattern, user_agent):
            return name
    return "Other"


def create_session(db: Session, *, user_id: int, ip_address: str | None, user_agent: str | None) -> UserSession:
    session = UserSession(
        user_id=user_id,
        session_token=secrets.token_urlsafe(32),
        ip_address=ip_address,
        user_agent=user_agent,
        browser=parse_browser(user_agent),
    )
    db.add(session)
    db.flush()
    return session


def touch_session(db: Session, session_token: str) -> UserSession | None:
    """Returns the session if it's alive (not revoked, within the
    sliding idle window) and bumps last_activity_at - this bump *is* the
    "active use extends the session" mechanism: it happens on every
    authenticated request via app.core.deps.get_current_user, no
    separate refresh-token dance needed. Returns None (caller then 401s)
    if the session is gone, revoked, or has gone stale past
    session_idle_timeout_minutes - a stale session is not resurrected by
    finding it again later, it's just gone."""
    session = db.query(UserSession).filter(UserSession.session_token == session_token).first()
    if session is None or session.revoked_at is not None:
        return None

    idle_cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.session_idle_timeout_minutes)
    if session.last_activity_at < idle_cutoff:
        return None

    session.last_activity_at = datetime.now(timezone.utc)
    db.flush()
    return session


def revoke_session(db: Session, session_token: str) -> None:
    db.query(UserSession).filter(UserSession.session_token == session_token).update({"revoked_at": datetime.now(timezone.utc)})
    db.flush()
