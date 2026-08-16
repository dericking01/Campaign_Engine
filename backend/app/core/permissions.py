"""Action catalog + the pure permission check.

Action stays a fixed code-level enum: each value corresponds to a real
require_action(Action.X) call already wired into a specific endpoint, so
the catalog of what *can* be permitted isn't GUI-definable - only which
roles have which of them is (see app.models.role.Role/RolePermission and
app/api/routers/roles.py). role_can() is deliberately DB-agnostic (a pure
set-membership check) so it stays fast to unit test without a live
database - the actual "which actions does this role have" lookup lives in
app.services.rbac.get_role_actions, one query per request, called from
app.core.deps.require_action.
"""

from enum import StrEnum


class Action(StrEnum):
    IMPORT_CREATE = "import:create"
    IMPORT_APPROVE = "import:approve"
    BASE_MANAGE = "base:manage"
    DND_MANAGE = "dnd:manage"
    CAMPAIGN_CREATE = "campaign:create"
    CAMPAIGN_CONFIGURE = "campaign:configure"
    CAMPAIGN_START_STOP = "campaign:start_stop"
    CAMPAIGN_VIEW = "campaign:view"
    REPORTS_VIEW = "reports:view"
    REPORTS_EXPORT = "reports:export"
    AUDIT_VIEW = "audit:view"
    USER_MANAGE = "user:manage"
    SYSTEM_CONFIGURE = "system:configure"
    STAFF_MANAGE = "staff:manage"


def role_can(granted_actions: set[str], action: Action) -> bool:
    return action.value in granted_actions
