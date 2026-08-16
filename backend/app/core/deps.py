from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.permissions import Action, role_can
from app.core.security import decode_access_token
from app.models.user import User
from app.services.rbac import get_role_actions

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise unauthorized

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise unauthorized

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
