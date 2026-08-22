from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_action
from app.core.permissions import Action
from app.models.role import Role
from app.models.user import User
from app.services.audit import write_audit_log

router = APIRouter(prefix="/roles", tags=["roles"])

VALID_ACTIONS = {a.value for a in Action}

# Human-readable labels for the permissions-matrix UI - purely cosmetic,
# the Action value itself is what's actually stored/checked.
ACTION_LABELS: dict[str, str] = {
    "import:create": "Create imports",
    "import:approve": "Approve/reject imports",
    "base:manage": "Manage bases",
    "dnd:manage": "Manage DND lists",
    "campaign:create": "Create campaigns",
    "campaign:configure": "Configure campaigns & trigger runs",
    "campaign:start_stop": "Start/pause/resume/stop live runs",
    "campaign:view": "View campaigns, bases, DND, imports",
    "reports:view": "View reports",
    "reports:export": "Export reports",
    "audit:view": "View audit log",
    "user:manage": "Manage users, roles & permissions",
    "system:configure": "Configure system (channels, sync)",
    "staff:manage": "Manage staff notification roster",
}


class ActionOut(BaseModel):
    value: str
    label: str


class RoleOut(BaseModel):
    code: str
    label: str
    description: str | None
    is_system: bool
    actions: list[str]


class CreateRoleRequest(BaseModel):
    code: str
    label: str
    description: str | None = None
    actions: list[str] = []

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        v = v.strip().upper().replace(" ", "_")
        if not v or not all(c.isalnum() or c == "_" for c in v):
            raise ValueError("code must be alphanumeric/underscore only")
        return v

    @field_validator("actions")
    @classmethod
    def validate_actions(cls, v: list[str]) -> list[str]:
        invalid = set(v) - VALID_ACTIONS
        if invalid:
            raise ValueError(f"Unknown action(s): {sorted(invalid)}")
        return v


class UpdateRoleRequest(BaseModel):
    label: str | None = None
    description: str | None = None
    actions: list[str] | None = None

    @field_validator("actions")
    @classmethod
    def validate_actions(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        invalid = set(v) - VALID_ACTIONS
        if invalid:
            raise ValueError(f"Unknown action(s): {sorted(invalid)}")
        return v


def _role_out(db: Session, role: Role) -> RoleOut:
    actions = db.execute(
        text("SELECT action FROM campaign.role_permissions WHERE role_code = :code ORDER BY action"),
        {"code": role.code},
    ).all()
    return RoleOut(
        code=role.code,
        label=role.label,
        description=role.description,
        is_system=role.is_system,
        actions=[a[0] for a in actions],
    )


@router.get("/actions", response_model=list[ActionOut], dependencies=[Depends(require_action(Action.USER_MANAGE))])
def list_actions() -> list[ActionOut]:
    """The fixed catalog of every permission that can be granted - powers
    the columns/rows of the permissions-matrix UI. Not GUI-editable itself
    (see module docstring in app.core.permissions)."""
    return [ActionOut(value=a.value, label=ACTION_LABELS.get(a.value, a.value)) for a in Action]


@router.get("", response_model=list[RoleOut], dependencies=[Depends(require_action(Action.USER_MANAGE))])
def list_roles(db: Session = Depends(get_db)) -> list[RoleOut]:
    roles = db.query(Role).order_by(Role.code).all()
    return [_role_out(db, r) for r in roles]


@router.post("", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
def create_role(
    req: CreateRoleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.USER_MANAGE)),
) -> RoleOut:
    role = Role(code=req.code, label=req.label, description=req.description, is_system=False)
    db.add(role)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"a role with code '{req.code}' already exists") from exc

    for action in req.actions:
        db.execute(
            text("INSERT INTO campaign.role_permissions (role_code, action) VALUES (:code, :action)"),
            {"code": role.code, "action": action},
        )

    write_audit_log(
        db,
        actor_id=current_user.id,
        action="role.create",
        entity_type="role",
        entity_id=role.code,
        new_value={"label": role.label, "actions": sorted(req.actions)},
    )
    db.commit()
    return _role_out(db, role)


@router.put("/{code}", response_model=RoleOut)
def update_role(
    code: str,
    req: UpdateRoleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.USER_MANAGE)),
) -> RoleOut:
    role = db.get(Role, code)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role not found")
    if role.code == "SUPER_ADMIN" and req.actions is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "SUPER_ADMIN always has every permission and can't be edited - "
            "this guarantees at least one role can always fix a permissions mistake.",
        )

    old = _role_out(db, role)

    if req.label is not None:
        role.label = req.label
    if req.description is not None:
        role.description = req.description
    db.flush()

    if req.actions is not None:
        db.execute(text("DELETE FROM campaign.role_permissions WHERE role_code = :code"), {"code": role.code})
        for action in req.actions:
            db.execute(
                text("INSERT INTO campaign.role_permissions (role_code, action) VALUES (:code, :action)"),
                {"code": role.code, "action": action},
            )

    write_audit_log(
        db,
        actor_id=current_user.id,
        action="role.update",
        entity_type="role",
        entity_id=role.code,
        old_value={"label": old.label, "actions": old.actions},
        new_value={"label": role.label, "actions": sorted(req.actions) if req.actions is not None else old.actions},
    )
    db.commit()
    return _role_out(db, role)


@router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.USER_MANAGE)),
) -> None:
    role = db.get(Role, code)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "role not found")
    if role.is_system:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "system roles cannot be deleted")

    in_use = db.execute(
        text("SELECT count(*) FROM campaign.users WHERE role = :code"), {"code": code}
    ).scalar_one()
    if in_use > 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{in_use} user(s) still have this role - reassign them first"
        )

    old = _role_out(db, role)
    db.delete(role)

    write_audit_log(
        db,
        actor_id=current_user.id,
        action="role.delete",
        entity_type="role",
        entity_id=code,
        old_value={"label": old.label, "actions": old.actions},
    )
    db.commit()
