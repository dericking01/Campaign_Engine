"""The DB-driven half of RBAC - see app.core.permissions for the pure
membership-check half. One query per request (called from
app.core.deps.require_action), fetching the role's whole permission set
at once rather than one query per action-check - consistent with the
per-request DB cost already paid by get_current_user's own lookup, so
this isn't adding a new class of overhead, just one more indexed query.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_role_actions(db: Session, role_code: str) -> set[str]:
    rows = db.execute(
        text("SELECT action FROM campaign.role_permissions WHERE role_code = :role"), {"role": role_code}
    ).all()
    return {r[0] for r in rows}
