"""Unique constraint on users.phone.

app/api/routers/users.py already caught IntegrityError on user create/
update and reported "a user with this email or phone already exists" -
but 0009 never actually added a DB-level constraint enforcing that, so
two accounts could silently share a phone number (and therefore share
an OTP delivery target - a real security-relevant gap, not just a data
hygiene one). A plain UNIQUE constraint is correct even though phone is
nullable: Postgres treats NULL <> NULL, so any number of accounts with
no phone on file remain unaffected.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-23
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "campaign"


def upgrade() -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.users ADD CONSTRAINT users_phone_key UNIQUE (phone);")


def downgrade() -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.users DROP CONSTRAINT IF EXISTS users_phone_key;")
