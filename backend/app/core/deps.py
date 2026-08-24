from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.permissions import Action, role_can
from app.core.security import decode_access_token
from app.models.user import User
from app.services.rbac import get_role_actions
from app.services.session_service import touch_session

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Two things must both be true: the JWT is cryptographically valid
    (not expired, correctly signed) AND its `sid` points at a session
    that hasn't gone idle past settings.session_idle_timeout_minutes -
    see app.services.session_service. The second check is what actually
    enforces the 30-minute sliding timeout; the JWT's own (much longer)
    `exp` is just an outer ceiling. A session found alive here has its
    last_activity_at bumped as a side effect - this one check, run on
    every authenticated request, is the entire "active use extends the
    session" mechanism."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise unauthorized

    payload = decode_access_token(token)
    if not payload or "sub" not in payload or "sid" not in payload:
        raise unauthorized

    # Committed immediately, independent of whatever the rest of this
    # request does with `db` - get_db() never auto-commits, and this
    # bookkeeping write must survive even if the endpoint's own business
    # transaction later rolls back (a failed action shouldn't also kill
    # the user's otherwise-healthy session).
    if touch_session(db, payload["sid"]) is None:
        raise unauthorized
    db.commit()

    user = db.query(User).filter(User.email == payload["sub"], User.is_active.is_(True)).first()
    if not user:
        raise unauthorized
    return user


def require_action(action: Action) -> Callable[[User], User]:
    """FastAPI dependency factory: 403s unless the current user's role permits `action`.

    This is the actual security boundary for RBAC (not the portal's UI gating,
    which is ergonomics only) - see app.core.permissions.
    """

    def _checker(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        granted = get_role_actions(db, current_user.role)
        if not role_can(granted, action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' is not permitted to perform '{action.value}'",
            )
        return current_user

    return _checker
