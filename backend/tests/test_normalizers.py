import pytest

from app.ingestion.normalizers import RejectionReason, is_canonical, normalize_msisdn

VALID_VARIANTS = [
    ("0712345678", "255712345678"),  # local format (docx example)
    ("+255712345678", "255712345678"),  # plus-prefixed (docx example)
    ("255712345678", "255712345678"),  # already canonical (docx example)
    ("712345678", "255712345678"),  # bare 9-digit (docx example)
    ("255 712 345 678", "255712345678"),  # spaced, real-world messiness
    ("0754-123-456", "255754123456"),  # dashed
    ('"255712345678"', "255712345678"),  # quoted, as legacy CSVs had
    ("  0712345678  ", "255712345678"),  # surrounding whitespace
]


@pytest.mark.parametrize("raw,expected", VALID_VARIANTS)
def test_normalizes_documented_variants_to_same_canonical_form(raw: str, expected: str) -> None:
    result = normalize_msisdn(raw)
    assert result.is_valid
    assert result.msisdn == expected
    assert is_canonical(result.msisdn)


def test_rejects_empty() -> None:
    result = normalize_msisdn("")
    assert not result.is_valid
    assert result.reason == RejectionReason.EMPTY


def test_rejects_none() -> None:
    result = normalize_msisdn(None)
    assert not result.is_valid
    assert result.reason == RejectionReason.EMPTY


def test_rejects_non_numeric() -> None:
    result = normalize_msisdn("abcdefg")
    assert not result.is_valid
    assert result.reason == RejectionReason.NON_NUMERIC


def test_rejects_too_short() -> None:
    result = normalize_msisdn("12345")
    assert not result.is_valid
    assert result.reason == RejectionReason.INVALID_LENGTH


def test_rejects_13_digit_number() -> None:
    """The requirements doc's ASCII placeholder implied 13 digits; the
    legacy PHP regex and real Tanzanian numbering both say 12 - a 13-digit
    number must be rejected, not silently truncated (see docs/decisions.md
    item 4)."""
    result = normalize_msisdn("2557123456789")
    assert not result.is_valid
    assert result.reason == RejectionReason.INVALID_LENGTH


def test_rejects_wrong_country_code() -> None:
    result = normalize_msisdn("254712345678")  # Kenyan, not Tanzanian
    assert not result.is_valid


def test_does_not_silently_mutate_invalid_numbers() -> None:
    """Requirements doc: 'Invalid/non-Tanzanian/structurally invalid numbers
    must be classified as rejected rather than silently modified.'"""
    result = normalize_msisdn("notanumberatall")
    assert result.msisdn is None
