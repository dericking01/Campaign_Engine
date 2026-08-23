"""Idempotent dev/demo seed data: one SUPER_ADMIN user, the 3 channel
configs (with the confirmed placeholder TPS split - see docs/decisions.md
item 3), and a starter zone list matching the requirements doc's own
audience-preview example (South/Lake/Central/Northern).

Safe to re-run: every insert is ON CONFLICT DO NOTHING/UPDATE keyed on a
natural unique column, never a blind INSERT.

Usage: python -m app.scripts.seed
"""

import os

from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password
from app.models.config import ChannelConfig, ZoneConfig
from app.models.user import User

configure_logging("development")
logger = get_logger(component="seed")

ADMIN_EMAIL = os.environ.get("SEED_ADMIN_EMAIL", "admin@afyacall.co.tz")
ADMIN_PASSWORD = os.environ.get("SEED_ADMIN_PASSWORD", "ChangeMe123!")

ZONES = ["SOUTH", "LAKE", "CENTRAL", "NORTHERN"]

CHANNELS = [
    # (channel, sender_id, tps_allocation) - placeholder split, see docs/decisions.md.
    ("SMS", "15723", 140),
    ("IVR", "15723", 40),
    ("DOCTOR", "15723", 20),
]


def run() -> None:
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == ADMIN_EMAIL).first():
            db.add(
                User(
                    email=ADMIN_EMAIL,
                    password_hash=hash_password(ADMIN_PASSWORD),
                    role="SUPER_ADMIN",
                    full_name="Seed Admin",
                )
            )
            logger.info("seed.admin_created", email=ADMIN_EMAIL)
        else:
            logger.info("seed.admin_already_exists", email=ADMIN_EMAIL)

        for code, sender_id, tps in CHANNELS:
            existing = db.get(ChannelConfig, code)
            if existing is None:
                db.add(ChannelConfig(channel=code, sender_id=sender_id, tps_allocation=tps))
                logger.info("seed.channel_created", channel=code)

        for code in ZONES:
            if not db.query(ZoneConfig).filter(ZoneConfig.code == code).first():
                db.add(ZoneConfig(code=code, label=code.title()))
                logger.info("seed.zone_created", zone=code)

        db.commit()
        logger.info("seed.complete")
    finally:
        db.close()


if __name__ == "__main__":
    run()
