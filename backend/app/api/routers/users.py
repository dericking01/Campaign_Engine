import re
import secrets
import string
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import require_action
from app.core.logging import get_logger
from app.core.permissions import Action
from app.core.security import hash_password
from app.gateways import kannel
from app.models.role import Role
from app.models.user import User
from app.services.audit import write_audit_log

router = APIRouter(prefix="/users", tags=["users"])
settings = get_settings()
logger = get_logger(component="users_router")

PHONE_RE = re.compile(r"^255[0-9]{9}$")
# Avoids visually-ambiguous characters (0/O, 1/l/I) since this is read off
# an SMS and typed back in, unlike a browser-generated/pasted password.
_TEMP_PASSWORD_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"


def _generate_temp_password() -> str:
    return "".join(secrets.choice(_TEMP_PASSWORD_ALPHABET) for _ in range(10))


def _send_welcome_sms(user: User, temp_password: str) -> None:
    result = kannel.send(
        to_msisdn=user.phone,
        text=(
            f"Welcome to AfyaCall Campaign Engine. Your login: {user.email} / {temp_password}. "
            f"Sign in and change your password at {settings.portal_url}"
        ),
        sender_id=settings.otp_sender_id,
    )
    logger.info("users.welcome_sms_sent", user_id=user.id, outcome=result.outcome.value)


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    full_name: str | None
    phone: str | None
    is_active: bool
    two_factor_enabled: bool
    last_login_at: datetime | None
    last_login_ip: str | None
    last_login_browser: str | None

    model_config = {"from_attributes": True}


class CreateUserRequest(BaseModel):
    email: str
    phone: str
    role: str
    full_name: str | None = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        if not PHONE_RE.match(v):
            raise ValueError("phone must be in 255XXXXXXXXX format")
        return v


class UpdateUserRequest(BaseModel):
    role: str | None = None
    full_name: str | None = None
    phone: str | None = None
    is_active: bool | None = None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is not None and not PHONE_RE.match(v):
            raise ValueError("phone must be in 255XXXXXXXXX format")
        return v


def _snapshot(user: User) -> dict:
    return {
        "email": user.email,
        "role": user.role,
        "full_name": user.full_name,
        "phone": user.phone,
        "is_active": user.is_active,
    }


@router.get("", response_model=list[UserOut], dependencies=[Depends(require_action(Action.USER_MANAGE))])
def list_users(db: Session = Depends(get_db)) -> list[User]:
    return db.query(User).order_by(User.email).all()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    req: CreateUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.USER_MANAGE)),
) -> User:
    """The temporary password is system-generated and never returned in
    this response - it only ever exists in the SMS sent to the new
    user's own phone (see _send_welcome_sms), the same "credentials are
    delivered, never displayed" posture the OTP flows use."""
    if db.get(Role, req.role) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"role '{req.role}' does not exist")

    temp_password = _generate_temp_password()
    user = User(
        email=req.email.strip().lower(),
        phone=req.phone.strip(),
        password_hash=hash_password(temp_password),
        role=req.role,
        full_name=req.full_name.strip() if req.full_name else None,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "a user with this email or phone already exists") from exc

    write_audit_log(
        db,
        actor_id=current_user.id,
        action="user.create",
        entity_type="user",
        entity_id=str(user.id),
        new_value=_snapshot(user),
    )
    db.commit()
    _send_welcome_sms(user, temp_password)
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    req: UpdateUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.USER_MANAGE)),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")

    if user.id == current_user.id and req.is_active is False:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "you cannot deactivate your own account")
    if user.id == current_user.id and req.role is not None and req.role != current_user.role:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "you cannot change your own role")
    if req.role is not None and db.get(Role, req.role) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"role '{req.role}' does not exist")

    old_value = _snapshot(user)

    if req.role is not None:
        user.role = req.role
    if req.full_name is not None:
        user.full_name = req.full_name.strip()
    if req.phone is not None:
        user.phone = req.phone.strip()
    if req.is_active is not None:
        user.is_active = req.is_active

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "a user with this phone already exists") from exc

    write_audit_log(
        db,
        actor_id=current_user.id,
        action="user.update",
        entity_type="user",
        entity_id=str(user.id),
        old_value=old_value,
        new_value=_snapshot(user),
    )
    db.commit()
    return user


@router.post("/{user_id}/reset-password", response_model=UserOut)
def reset_user_password(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.USER_MANAGE)),
) -> User:
    """Admin-initiated reset: generates a new temporary password and
    resends it via SMS - same as account creation. Nobody but the user
    ever sees the plaintext, including the admin triggering this."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    if not user.phone:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "user has no phone number on file")

    temp_password = _generate_temp_password()
    user.password_hash = hash_password(temp_password)
    db.flush()

    write_audit_log(
        db,
        actor_id=current_user.id,
        action="user.reset_password",
        entity_type="user",
        entity_id=str(user.id),
    )
    db.commit()
    _send_welcome_sms(user, temp_password)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.USER_MANAGE)),
) -> None:
    if user_id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "you cannot delete your own account")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")

    old_value = _snapshot(user)
    db.delete(user)

    write_audit_log(
        db,
        actor_id=current_user.id,
        action="user.delete",
        entity_type="user",
        entity_id=str(user_id),
        old_value=old_value,
    )
    db.commit()
