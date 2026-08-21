"""Writes to campaign.audit_logs - append-only, RANGE-partitioned monthly
(see app.models.audit.AuditLog). Every high-impact action should call this;
so far only app.api.routers.staff does (the staff notification roster is a
compliance-sensitive list, so it was the first caller to actually need this
write path - see docs/decisions.md). Full audit coverage across every
high-impact action remains Phase 6 scope.

Callers pass the same DB session as their own business-state change so the
audit row commits atomically with it - same "no separate transaction"
principle as app.services.outbox.write_event.
"""

from app.models.audit import AuditLog


def write_audit_log(
    db,
    *,
    actor_id: int | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    old_value: dict | None = None,
    new_value: dict | None = None,
    reason: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
    )
    db.add(entry)
    return entry
