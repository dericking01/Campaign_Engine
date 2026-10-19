"""Idempotent production bootstrap, run by the compose `migrate` job right
after `alembic upgrade head`:

- the initial SUPER_ADMIN from SUPER_USERNAME/SUPER_EMAIL/SUPER_PASSWORD/
  SUPER_PHONE, validated and normalized exactly like POST /users
  (app.api.routers.users.CreateUserRequest), with 2FA on - the phone is
  what makes that meaningful (see docs/decisions.md #66);
- the 3 channel_configs rows. Dispatch JOINs on them and the GUI can only
  edit them (PUT /system/channels/...), never create them, so without this
  a fresh environment silently queues zero messages.

Unlike app.scripts.seed (dev/demo data with a default password), nothing
here has a fallback credential or demo row. An existing admin is never
modified - in particular their password is never reset on redeploy, since
they may have changed it through the portal since.

Usage: python -m app.scripts.bootstrap
"""

import sys

from pydantic import ValidationError

from app.api.routers.users import CreateUserRequest
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password
from app.models.config import ChannelConfig
from app.models.role import Role
from app.models.user import User
from app.services.audit import write_audit_log

settings = get_settings()
configure_logging(settings.environment)
logger = get_logger(component="bootstrap")

SUPER_ADMIN_ROLE = "SUPER_ADMIN"
MIN_PASSWORD_LENGTH = 8  # same rule as app.api.routers.auth password change/reset

# Sender IDs per docs/decisions.md and migration 0006 (DOCTOR is "AFYACALL",
# matching legacy drmaster.php); TPS comes from the env-configured split.
CHANNELS = [
    ("SMS", "15723", settings.sms_tps_allocation),
    ("IVR", "15723", settings.ivr_tps_allocation),
    ("DOCTOR", "AFYACALL", settings.doctor_tps_allocation),
]


class BootstrapError(Exception):
    pass


def _seed_super_admin(db) -> None:
    fields = {
        "SUPER_USERNAME": settings.super_username,
        "SUPER_EMAIL": settings.super_email,
        "SUPER_PASSWORD": settings.super_password,
        "SUPER_PHONE": settings.super_phone,
    }
    if not any(fields.values()):
        logger.warning("bootstrap.super_admin_skipped", reason="SUPER_* env vars not set")
        return
    # Checked before validating the rest, so SUPER_PASSWORD can be removed
    # from .env after first login without failing every later deploy.
    if settings.super_email and (
        db.query(User).filter(User.email == settings.super_email.strip().lower()).first() is not None
    ):
        logger.info("bootstrap.super_admin_already_exists", email=settings.super_email.strip().lower())
        return
    missing = [name for name, value in fields.items() if not value]
    if missing:
        raise BootstrapError(f"missing env vars: {', '.join(missing)}")
    if len(settings.super_password) < MIN_PASSWORD_LENGTH:
        raise BootstrapError(f"SUPER_PASSWORD must be at least {MIN_PASSWORD_LENGTH} characters")

    try:
        req = CreateUserRequest(
            email=settings.super_email,
            phone=settings.super_phone,
            role=SUPER_ADMIN_ROLE,
            full_name=settings.super_username,
        )
    except ValidationError as exc:
        raise BootstrapError(f"invalid SUPER_* env vars: {exc}") from exc

    email = req.email.strip().lower()
    phone = req.phone.strip()

    if db.get(Role, SUPER_ADMIN_ROLE) is None:
        raise BootstrapError(f"role '{SUPER_ADMIN_ROLE}' does not exist - has migration 0007 run?")

    if db.query(User).filter(User.phone == phone).first() is not None:
        raise BootstrapError("SUPER_PHONE already belongs to a different user")

    user = User(
        email=email,
        phone=phone,
        password_hash=hash_password(settings.super_password),
        role=SUPER_ADMIN_ROLE,
        full_name=req.full_name.strip() if req.full_name else None,
        two_factor_enabled=True,
    )
    db.add(user)
    db.flush()
    write_audit_log(
        db,
        actor_id=None,
        action="user.create",
        entity_type="user",
        entity_id=str(user.id),
        new_value={"email": user.email, "role": user.role, "full_name": user.full_name, "phone": user.phone},
        reason="initial SUPER_ADMIN created by app.scripts.bootstrap",
    )
    logger.info("bootstrap.super_admin_created", email=email, user_id=user.id)


def _seed_channel_configs(db) -> None:
    for code, sender_id, tps in CHANNELS:
        if db.get(ChannelConfig, code) is None:
            db.add(ChannelConfig(channel=code, sender_id=sender_id, tps_allocation=tps))
            logger.info("bootstrap.channel_created", channel=code, sender_id=sender_id, tps=tps)


def run() -> None:
    db = SessionLocal()
    try:
        _seed_super_admin(db)
        _seed_channel_configs(db)
        db.commit()
        logger.info("bootstrap.complete")
    except BootstrapError as exc:
        db.rollback()
        logger.error("bootstrap.failed", error=str(exc))
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    run()
