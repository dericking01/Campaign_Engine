"""Dynamic, GUI-configurable roles and permissions.

Replaces the hardcoded Role StrEnum + ROLE_ACTIONS dict in
app.core.permissions with two tables: `roles` (the assignable role
catalog) and `role_permissions` (which Action each role grants). Actions
themselves stay a fixed code-level enum (app.core.permissions.Action) -
each one corresponds to a real `require_action(Action.X)` call already
wired into a specific endpoint, so the *catalog* of what can be permitted
isn't GUI-definable, only which roles have which of them.

Seeds the exact same 5 roles and permission sets the old ROLE_ACTIONS dict
had, marked is_system=true (protects them from deletion, and SUPER_ADMIN
additionally can't have its permission set edited - see app/api/routers/
roles.py - so there's always at least one way to fix a permissions
mistake via the GUI).

users.role's old inline CHECK (fixed to exactly 5 literal values) is
replaced with a real FK to roles.code - the DB now enforces "role must be
a real registered role" without hardcoding which ones.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-22
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "campaign"

# Mirrors the Action StrEnum values in app/core/permissions.py exactly.
ALL_ACTIONS = [
    "import:create",
    "import:approve",
    "base:manage",
    "dnd:manage",
    "campaign:create",
    "campaign:configure",
    "campaign:start_stop",
    "campaign:view",
    "reports:view",
    "reports:export",
    "audit:view",
    "user:manage",
    "system:configure",
    "staff:manage",
]

SEED_ROLES = {
    "SUPER_ADMIN": ("Super Admin", "Full access to every action.", ALL_ACTIONS),
    "CAMPAIGN_MANAGER": (
        "Campaign Manager",
        "Configures imports, bases, DND, campaigns, and staff notifications; cannot start/stop live runs.",
        [
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
        ],
    ),
    "OPERATIONS": (
        "Operations",
        "Starts, pauses, resumes, and stops live campaign runs.",
        ["campaign:start_stop", "campaign:view", "reports:view"],
    ),
    "ANALYST": (
        "Analyst",
        "Read-only plus report export.",
        ["campaign:view", "reports:view", "reports:export"],
    ),
    "VIEWER": ("Viewer", "Read-only.", ["campaign:view", "reports:view"]),
}


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE {SCHEMA}.roles (
            code TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            description TEXT,
            is_system BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute(f"""
        CREATE TABLE {SCHEMA}.role_permissions (
            role_code TEXT NOT NULL REFERENCES {SCHEMA}.roles(code) ON DELETE CASCADE,
            action TEXT NOT NULL,
            PRIMARY KEY (role_code, action)
        );
    """)

    conn = op.get_bind()
    for code, (label, description, actions) in SEED_ROLES.items():
        conn.execute(
            text(f"""
                INSERT INTO {SCHEMA}.roles (code, label, description, is_system)
                VALUES (:code, :label, :description, true)
            """),
            {"code": code, "label": label, "description": description},
        )
        for action in actions:
            conn.execute(
                text(f"INSERT INTO {SCHEMA}.role_permissions (role_code, action) VALUES (:code, :action)"),
                {"code": code, "action": action},
            )

    op.execute(f"ALTER TABLE {SCHEMA}.users DROP CONSTRAINT users_role_check;")
    op.execute(
        f"ALTER TABLE {SCHEMA}.users ADD CONSTRAINT users_role_fkey "
        f"FOREIGN KEY (role) REFERENCES {SCHEMA}.roles(code);"
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.users DROP CONSTRAINT IF EXISTS users_role_fkey;")
    op.execute(
        f"ALTER TABLE {SCHEMA}.users ADD CONSTRAINT users_role_check "
        f"CHECK (role IN ('SUPER_ADMIN','CAMPAIGN_MANAGER','OPERATIONS','ANALYST','VIEWER'));"
    )
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.role_permissions;")
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.roles;")
