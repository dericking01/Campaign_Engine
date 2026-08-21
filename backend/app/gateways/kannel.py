"""Kannel sendsms HTTP client - the only place in this codebase that talks
to the real SMSC gateway (192.168.1.10), matching the confirmed principle
that Kannel is a downstream gateway called exclusively from dispatch
workers, never the API or any other component.

Legacy scripts (smsmaster.php/ivrmaster.php/drmaster.php) called Kannel's
`/cgi-bin/sendsms` the same way but never inspected the response body -
any non-cURL-error response was logged as "sent". That's exactly the gap
this module closes: Kannel's sendsms HTTP interface returns a real status
line ("<code>: <text>") that distinguishes "accepted for delivery" from a
bad request, bad auth, or the SMSC/queue rejecting it - see classify().

Response classification (per confirmed decision - see docs/decisions.md):
ambiguous outcomes (timeout, connection error, unrecognized body) become
FAILED_UNCONFIRMED and are never auto-retried, since Kannel's HTTP API has
no idempotency token and a blind retry risks a real duplicate send.
"""

from dataclasses import dataclass
from enum import StrEnum
from itertools import cycle

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger(component="kannel_gateway")

_port_cycle = cycle(settings.kannel_port_list)


class DispatchOutcome(StrEnum):
    SENT = "SENT"
    FAILED_PERMANENT = "FAILED_PERMANENT"  # bad request/auth - retrying won't help
    FAILED_TRANSIENT = "FAILED_TRANSIENT"  # SMSC/queue busy - safe to retry
    FAILED_UNCONFIRMED = "FAILED_UNCONFIRMED"  # timeout/unrecognized - never auto-retry


@dataclass(frozen=True, slots=True)
class KannelResult:
    outcome: DispatchOutcome
    kannel_port: int
    http_status: int | None
    response_body: str | None


def next_port() -> int:
    return next(_port_cycle)


def classify(http_status: int | None, body: str | None, exc: Exception | None) -> DispatchOutcome:
    if exc is not None:
        # Network-level failure (timeout, connection refused/reset): we
        # genuinely don't know if Kannel received and queued the request.
        return DispatchOutcome.FAILED_UNCONFIRMED

    if http_status in (200, 202):
        # Kannel's sendsms success body is "<code>: <text>" - "0: Accepted
        # for delivery" is the documented success code. Any other leading
        # code on a 200/202 is treated as unconfirmed rather than assumed
        # successful, since this is submission acceptance, not a delivery
        # receipt either way.
        if body is not None and body.strip().startswith("0:"):
            return DispatchOutcome.SENT
        return DispatchOutcome.FAILED_UNCONFIRMED

    if http_status in (400, 401, 403, 404):
        # Malformed request, bad credentials, forbidden, or unknown
        # service/smsc - none of these are fixed by retrying the exact
        # same request.
        return DispatchOutcome.FAILED_PERMANENT

    if http_status in (500, 503):
        # Kannel-side transient trouble (SMSC link down, queue full) -
        # worth retrying after backoff.
        return DispatchOutcome.FAILED_TRANSIENT

    return DispatchOutcome.FAILED_UNCONFIRMED


def send(*, to_msisdn: str, text: str, sender_id: str, timeout_seconds: float = 8.0) -> KannelResult:
    port = next_port()
    url = f"http://{settings.kannel_host}:{port}/cgi-bin/sendsms"
    params = {
        "username": settings.kannel_username,
        "password": settings.kannel_password,
        "from": sender_id,
        "to": to_msisdn,
        "text": text,
    }
    try:
        resp = httpx.get(url, params=params, timeout=timeout_seconds)
        outcome = classify(resp.status_code, resp.text, None)
        return KannelResult(
            outcome=outcome, kannel_port=port, http_status=resp.status_code, response_body=resp.text[:500]
        )
    except httpx.HTTPError as exc:
        logger.warning("kannel.request_failed", port=port, to_msisdn=to_msisdn, error=str(exc))
        outcome = classify(None, None, exc)
        return KannelResult(outcome=outcome, kannel_port=port, http_status=None, response_body=str(exc)[:500])
