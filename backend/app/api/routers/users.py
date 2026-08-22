from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_action
from app.core.permissions import Action
from app.core.security import hash_password
from app.models.role import Role
from app.models.user import User
from app.services.audit import write_audit_log

router = APIRouter(prefix="/users", tags=["users"])


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    full_name: str | None
    is_active: bool

    model_config = {"from_attributes": True}


class CreateUserRequest(BaseModel):
    email: str
    password: str
    role: str
    full_name: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


class UpdateUserRequest(BaseModel):
    role: str | None = None
    full_name: str | None = None
    is_active: bool | None = None
    password: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str | None) -> str | None:
        if v is not None and len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


def _snapshot(user: User) -> dict:
    return {"email": user.email, "role": user.role, "full_name": user.full_name, "is_active": user.is_active}


@router.get("", response_model=list[UserOut], dependencies=[Depends(require_action(Action.USER_MANAGE))])
def list_users(db: Session = Depends(get_db)) -> list[User]:
    return db.query(User).order_by(User.email).all()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    req: CreateUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.USER_MANAGE)),
) -> User:
    if db.get(Role, req.role) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"role '{req.role}' does not exist")

    user = User(
        email=req.email.strip().lower(),
        password_hash=hash_password(req.password),
        role=req.role,
        full_name=req.full_name.strip() if req.full_name else None,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "a user with this email already exists") from exc

    write_audit_log(
        db,
        actor_id=current_user.id,
        action="user.create",
        entity_type="user",
        entity_id=str(user.id),
        new_value=_snapshot(user),
    )
    db.commit()
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
    if req.is_active is not None:
        user.is_active = req.is_active
    if req.password is not None:
        user.password_hash = hash_password(req.password)

    db.flush()

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
