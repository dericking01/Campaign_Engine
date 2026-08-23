"""Reusable engagement primitives - requirements doc §32's "existing promo
analytics" definitions, generalized to take an arbitrary MSISDN set + time
window rather than being hardcoded to one campaign or one promotion. Any
caller (a campaign rollup, an ad-hoc date-range report, a future
promotion-specific screen) can reuse the same functions.

Exact definitions from the requirements doc:
    APU (Active Promo Users): users who interacted at least once
    HGU (Highly Engaged Users): users with >5 SMS in chat_history during
                                 the window
    Engagement Rate: HGU / APU
    Average chatbot messages: total interactions / unique interacting users

Data source: chat.chat_history (owned by the existing AfyaCall chatbot
service, not this schema - campaign_app has read-only SELECT, see
deploy/scripts/bootstrap_db.sh). session_id encodes "{msisdn}-{dd-mm-yyyy}"
- verified live against 2.08M real rows: 99.99% match this format, and
100% of those have a canonical 255XXXXXXXXX MSISDN (see docs/decisions.md).
The ~0.01% that don't (test/synthetic session ids like "conv_<ts>_<rand>")
are excluded by the format regex itself - tolerated, not hard-failed on,
same principle as the Phase 2 import parser. Only message->>'type'='human'
rows count as "SMS" (customer-sent), never the bot's own replies.

No literal per-message timestamp exists on chat_history - only the date
embedded in session_id, which is exactly the granularity the doc's "grouped
by day" / "average active days" metrics need.
"""

from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

_SESSION_ID_FORMAT = r"^[0-9]{9,15}-[0-9]{2}-[0-9]{2}-[0-9]{4}$"


def compute_chat_engagement(
    db: Session, msisdns: list[str], window_start: datetime | date, window_end: datetime | date
) -> dict:
    if not msisdns:
        return {
            "apu": 0, "hgu": 0, "engagement_rate": None, "avg_messages_per_user": None,
            "avg_active_days_per_user": None, "days_active_distribution": {},
        }

    rows = db.execute(
        text(f"""
            WITH parsed AS (
                SELECT
                    split_part(session_id, '-', 1) AS msisdn,
                    to_date(
                        split_part(session_id, '-', 4) || '-' || split_part(session_id, '-', 3)
                        || '-' || split_part(session_id, '-', 2),
                        'YYYY-MM-DD'
                    ) AS day
                FROM chat.chat_history
                WHERE session_id ~ '{_SESSION_ID_FORMAT}'
                  AND message->>'type' = 'human'
                  AND split_part(session_id, '-', 1) = ANY(:msisdns)
            ),
            windowed AS (
                SELECT msisdn, day FROM parsed WHERE day BETWEEN :window_start AND :window_end
            ),
            per_user AS (
                SELECT msisdn, count(*) AS message_count, count(DISTINCT day) AS active_days
                FROM windowed GROUP BY msisdn
            )
            SELECT msisdn, message_count, active_days FROM per_user
        """),
        {
            "msisdns": msisdns,
            "window_start": window_start.date() if isinstance(window_start, datetime) else window_start,
            "window_end": window_end.date() if isinstance(window_end, datetime) else window_end,
        },
    ).all()

    apu = len(rows)
    hgu = sum(1 for r in rows if r.message_count > 5)
    total_messages = sum(r.message_count for r in rows)
    total_active_days = sum(r.active_days for r in rows)

    days_active_distribution: dict[str, int] = {}
    for r in rows:
        key = str(r.active_days)
        days_active_distribution[key] = days_active_distribution.get(key, 0) + 1

    return {
        "apu": apu,
        "hgu": hgu,
        "engagement_rate": (hgu / apu) if apu else None,
        "avg_messages_per_user": (total_messages / apu) if apu else None,
        "avg_active_days_per_user": (total_active_days / apu) if apu else None,
        "days_active_distribution": days_active_distribution,
    }


def compute_provider_engagement(
    db: Session, msisdns: list[str], window_start: datetime, window_end: datetime
) -> dict:
    """Doctor/provider-discovery engagement - the closest real proxy for
    "doctor calls" available in the source database (provider_appearances
    = a provider surfaced in a search result; provider_impressions = the
    customer actually viewed one). There is no telephony call log to
    attribute to - see docs/decisions.md for why this is honestly labeled
    "provider engagement" rather than "doctor calls"."""
    if not msisdns:
        return {"audience_size": 0, "engaged_count": 0, "engagement_rate": None, "total_events": 0}

    row = db.execute(
        text("""
            WITH events AS (
                SELECT customer_msisdn FROM provider.provider_appearances
                WHERE customer_msisdn = ANY(:msisdns) AND appeared_at BETWEEN :start AND :end
                UNION ALL
                SELECT customer_msisdn FROM provider.provider_impressions
                WHERE customer_msisdn = ANY(:msisdns) AND viewed_at BETWEEN :start AND :end
            )
            SELECT count(DISTINCT customer_msisdn) AS engaged, count(*) AS total FROM events
        """),
        {"msisdns": msisdns, "start": window_start, "end": window_end},
    ).one()

    audience_size = len(msisdns)
    return {
        "audience_size": audience_size,
        "engaged_count": row.engaged,
        "engagement_rate": (row.engaged / audience_size) if audience_size else None,
        "total_events": row.total,
    }
