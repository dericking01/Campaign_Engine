"""role_can() is now a pure set-membership check (see
app.core.permissions) - the actual "which actions does this role have"
lookup is a DB query (app.services.rbac.get_role_actions), so these tests
exercise the pure logic against the *intended default* seed permission
sets (migration 0007's SEED_ROLES) rather than live DB state. Live DB
state (including any GUI edits to a role's permissions) is verified via
curl against the real deployed stack, matching every other DB-dependent
behavior in this codebase - see docs/decisions.md.
"""

from app.core.permissions import Action, role_can

SUPER_ADMIN = {a.value for a in Action}
CAMPAIGN_MANAGER = {
    "import:create",
    "import:approve",
    "base:manage",
    "dnd:manage",
    "campaign:create",
    "campaign:configure",
    "campaign:view",
    "reports:view",
    "reports:export",
    "staff:manage",
}
OPERATIONS = {"campaign:start_stop", "campaign:view", "reports:view"}
ANALYST = {"campaign:view", "reports:view", "reports:export"}
VIEWER = {"campaign:view", "reports:view"}


def test_analyst_cannot_start_stop_campaigns() -> None:
    """The requirements doc is explicit: an ANALYST must never be able to
    accidentally start/stop a live campaign (§34/§22)."""
    assert not role_can(ANALYST, Action.CAMPAIGN_START_STOP)


def test_viewer_cannot_start_stop_campaigns() -> None:
    assert not role_can(VIEWER, Action.CAMPAIGN_START_STOP)


def test_operations_can_start_stop_campaigns() -> None:
    assert role_can(OPERATIONS, Action.CAMPAIGN_START_STOP)


def test_campaign_manager_cannot_start_stop_campaigns() -> None:
    """Campaign managers configure and approve; OPERATIONS runs them - this
    separation is deliberate, not an oversight."""
    assert not role_can(CAMPAIGN_MANAGER, Action.CAMPAIGN_START_STOP)


def test_super_admin_can_do_everything() -> None:
    for action in Action:
        assert role_can(SUPER_ADMIN, action)


def test_viewer_is_read_only() -> None:
    write_actions = {
        Action.IMPORT_CREATE,
        Action.IMPORT_APPROVE,
        Action.BASE_MANAGE,
        Action.DND_MANAGE,
        Action.CAMPAIGN_CREATE,
        Action.CAMPAIGN_CONFIGURE,
        Action.CAMPAIGN_START_STOP,
        Action.USER_MANAGE,
        Action.SYSTEM_CONFIGURE,
    }
    for action in write_actions:
        assert not role_can(VIEWER, action)
