"""MSISDN normalization to the canonical 255XXXXXXXXX (12-digit) form.

Canonical length is 12 digits total (255 + 9-digit subscriber number), not
13 - see docs/decisions.md item 4. This matches both the legacy PHP dispatch
scripts' actual production regex (`^255\\d{9}$` in smsmaster.php/
ivrmaster.php/drmaster.php) and real Tanzanian mobile numbering (country
code + 9-digit subscriber number). This module is the single source of
normalization logic; the DB CHECK constraint (`^255[0-9]{9}$`) is the same
rule enforced again at the storage boundary.

Deliberately does NOT validate against a whitelist of real mobile operator
prefixes (Vodacom/Airtel/Tigo/Halotel/Zantel/TTCL ranges shift over time and
none of the source documents asked for this) - only structural format is
enforced, matching the explicit requirement and the legacy code's own
behavior.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

_CANONICAL_RE = re.compile(r"^255[0-9]{9}$")
_NON_DIGIT_RE = re.compile(r"\D")


class RejectionReason(StrEnum):
    EMPTY = "EMPTY"
    NON_NUMERIC = "NON_NUMERIC"
    INVALID_LENGTH = "INVALID_LENGTH"
    INVALID_FORMAT = "INVALID_FORMAT"


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    msisdn: str | None
    reason: RejectionReason | None

    @property
    def is_valid(self) -> bool:
        return self.msisdn is not None


def normalize_msisdn(raw: str | None) -> NormalizationResult:
    """Normalize one raw MSISDN value to the canonical 255XXXXXXXXX form.

    Accepts the variants explicitly documented as needing to resolve to the
    same canonical representation: 0712345678 (local), +255712345678,
    255712345678 (already canonical), and 712345678 (bare 9-digit
    subscriber number). Non-digit separators (spaces, dashes) are stripped
    before classification, since real source files are not always cleanly
    formatted.
    """
    if raw is None:
        return NormalizationResult(None, RejectionReason.EMPTY)

    value = raw.strip().strip('"').strip()
    if not value:
        return NormalizationResult(None, RejectionReason.EMPTY)

    digits = _NON_DIGIT_RE.sub("", value)
    if not digits:
        return NormalizationResult(None, RejectionReason.NON_NUMERIC)

    candidate: str
    if digits.startswith("255") and len(digits) == 12:
        candidate = digits
    elif digits.startswith("0") and len(digits) == 10:
        candidate = "255" + digits[1:]
    elif len(digits) == 9:
        candidate = "255" + digits
    else:
        return NormalizationResult(None, RejectionReason.INVALID_LENGTH)

    if not _CANONICAL_RE.match(candidate):
        return NormalizationResult(None, RejectionReason.INVALID_FORMAT)

    return NormalizationResult(candidate, None)


def is_canonical(msisdn: str) -> bool:
    """True if `msisdn` is already in canonical form - useful for asserting
    invariants on data already committed to campaign.* tables."""
    return bool(_CANONICAL_RE.match(msisdn))
