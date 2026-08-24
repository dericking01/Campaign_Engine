"""2FA/OTP, sliding sessions, and user profile fields.

users.phone is required to receive an OTP at all, so 2FA can never be
meaningfully "on" for a user with no phone on file - existing rows have
no phone, so this migration explicitly turns 2FA off for them (an
operator must set a phone via Profile Settings before re-enabling it;
the API also refuses to enable 2FA without a phone - see
app/api/routers/auth.py). New users are required to supply a phone at
creation time (app/api/routers/users.py) precisely so this bootstrapping
gap doesn't recur.

otp_codes is a generic, purpose-tagged one-time-code table (LOGIN_2FA /
PASSWORD_CHANGE / PASSWORD_RESET) rather than three separate tables -
same "one reusable primitive, not one-off tables" instinct as the
analytics primitives. code_hash (never the plaintext code) mirrors how
password_hash is stored - see app.services.otp_service.

user_sessions backs the sliding 30-minute-inactivity session model: the
JWT carries a `sid` claim pointing at a row here; every authenticated
request (app.core.deps.get_current_user) checks and bumps
last_activity_at, so activity extends the session and true idleness lets
it go stale - independent of the JWT's own (longer) cryptographic
expiry.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-24
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "campaign"
MSISDN_CHECK = "phone ~ '^255[0-9]{9}$'"


def upgrade() -> None:
    op.execute(f"""
        ALTER TABLE {SCHEMA}.users
            ADD COLUMN phone VARCHAR(12) CHECK ({MSISDN_CHECK}),
            ADD COLUMN two_factor_enabled BOOLEAN NOT NULL DEFAULT true,
            ADD COLUMN last_login_at TIMESTAMPTZ,
            ADD COLUMN last_login_ip TEXT,
            ADD COLUMN last_login_browser TEXT;
    """)
    # Can't 2FA a user we have no way to send a code to.
    op.execute(f"UPDATE {SCHEMA}.users SET two_factor_enabled = false WHERE phone IS NULL;")

    op.execute(f"""
        CREATE TABLE {SCHEMA}.otp_codes (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES {SCHEMA}.users(id) ON DELETE CASCADE,
            purpose TEXT NOT NULL CHECK (purpose IN ('LOGIN_2FA', 'PASSWORD_CHANGE', 'PASSWORD_RESET')),
            code_hash TEXT NOT NULL,
            pending_token TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_at TIMESTAMPTZ,
            attempt_count INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    op.execute(f"CREATE INDEX ix_otp_codes_pending_token ON {SCHEMA}.otp_codes (pending_token);")

    op.execute(f"""
        CREATE TABLE {SCHEMA}.user_sessions (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES {SCHEMA}.users(id) ON DELETE CASCADE,
            session_token TEXT NOT NULL UNIQUE,
            ip_address TEXT,
            user_agent TEXT,
            browser TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_at TIMESTAMPTZ
        );
    """)
    op.execute(f"CREATE INDEX ix_user_sessions_token ON {SCHEMA}.user_sessions (session_token);")


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.user_sessions;")
    op.execute(f"DROP TABLE IF EXISTS {SCHEMA}.otp_codes;")
    op.execute(f"""
        ALTER TABLE {SCHEMA}.users
            DROP COLUMN IF EXISTS phone,
            DROP COLUMN IF EXISTS two_factor_enabled,
            DROP COLUMN IF EXISTS last_login_at,
            DROP COLUMN IF EXISTS last_login_ip,
            DROP COLUMN IF EXISTS last_login_browser;
    """)
