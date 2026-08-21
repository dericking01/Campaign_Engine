from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_action
from app.core.permissions import Action
from app.models.staff import StaffContact
from app.models.user import User
from app.services.audit import write_audit_log

router = APIRouter(prefix="/staff", tags=["staff"])


class StaffContactOut(BaseModel):
    id: int
    name: str
    msisdn: str
    is_active: bool

    model_config = {"from_attributes": True}


class CreateStaffContactRequest(BaseModel):
    name: str
    msisdn: str


class UpdateStaffContactRequest(BaseModel):
    name: str | None = None
    msisdn: str | None = None
    is_active: bool | None = None


@router.get("", response_model=list[StaffContactOut], dependencies=[Depends(require_action(Action.STAFF_MANAGE))])
def list_staff(db: Session = Depends(get_db)) -> list[StaffContact]:
    return db.query(StaffContact).order_by(StaffContact.name).all()


@router.post("", response_model=StaffContactOut, status_code=status.HTTP_201_CREATED)
def create_staff(
    req: CreateStaffContactRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.STAFF_MANAGE)),
) -> StaffContact:
    contact = StaffContact(name=req.name.strip(), msisdn=req.msisdn.strip())
    db.add(contact)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "a staff contact with this MSISDN already exists") from exc

    write_audit_log(
        db,
        actor_id=current_user.id,
        action="staff.create",
        entity_type="staff_contact",
        entity_id=str(contact.id),
        new_value={"name": contact.name, "msisdn": contact.msisdn, "is_active": contact.is_active},
    )
    db.commit()
    return contact


@router.put("/{contact_id}", response_model=StaffContactOut)
def update_staff(
    contact_id: int,
    req: UpdateStaffContactRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.STAFF_MANAGE)),
) -> StaffContact:
    contact = db.get(StaffContact, contact_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "staff contact not found")

    old_value = {"name": contact.name, "msisdn": contact.msisdn, "is_active": contact.is_active}

    if req.name is not None:
        contact.name = req.name.strip()
    if req.msisdn is not None:
        contact.msisdn = req.msisdn.strip()
    if req.is_active is not None:
        contact.is_active = req.is_active

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "a staff contact with this MSISDN already exists") from exc

    write_audit_log(
        db,
        actor_id=current_user.id,
        action="staff.update",
        entity_type="staff_contact",
        entity_id=str(contact.id),
        old_value=old_value,
        new_value={"name": contact.name, "msisdn": contact.msisdn, "is_active": contact.is_active},
    )
    db.commit()
    return contact


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_staff(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_action(Action.STAFF_MANAGE)),
) -> None:
    contact = db.get(StaffContact, contact_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "staff contact not found")

    old_value = {"name": contact.name, "msisdn": contact.msisdn, "is_active": contact.is_active}
    db.delete(contact)

    write_audit_log(
        db,
        actor_id=current_user.id,
        action="staff.delete",
        entity_type="staff_contact",
        entity_id=str(contact_id),
        old_value=old_value,
    )
    db.commit()
