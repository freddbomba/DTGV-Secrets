from __future__ import annotations

import pytest

from interview_intake.errors import ValidationError
from interview_intake.id_grammar import (
    MAX_SERIAL,
    RESERVED_WORDS,
    build_interview_id,
    is_interview_id,
    parse_interview_id,
    validate_interview_id,
    validate_mnemonic,
    validate_researcher_id,
)


@pytest.mark.parametrize(
    "value",
    [
        "2026-abc-xyz-0001",
        "2026-abc-xyz-0000",
        "1999-def-qrs-9999",
    ],
)
def test_valid_ids(value: str) -> None:
    assert validate_interview_id(value) == value
    assert is_interview_id(value)


@pytest.mark.parametrize(
    "value",
    [
        "2026-ABC-xyz-0001",  # uppercase
        "2026-abc-XYZ-0001",
        "2026-abc-xyz-1",  # short serial
        "2026-abc-xyz-00001",  # long serial
        "26-abc-xyz-0001",  # short year
        "2026-ab-xyz-0001",  # short researcher
        "2026-abc-xyz-000a",  # non-digit serial
        "2026abcxyz0001",  # no separators
        "",
        "2026-abc-xyz-0001-extra",
    ],
)
def test_invalid_ids(value: str) -> None:
    with pytest.raises(ValidationError):
        validate_interview_id(value)
    assert not is_interview_id(value)


def test_parse_roundtrip() -> None:
    parsed = parse_interview_id("2026-abc-xyz-0042")
    assert (parsed.year, parsed.researcher_id, parsed.mnemonic, parsed.serial) == (
        2026,
        "abc",
        "xyz",
        42,
    )
    assert str(parsed) == "2026-abc-xyz-0042"


def test_build_normalises_and_pads() -> None:
    assert build_interview_id(2026, "ABC", " XYZ ", 1) == "2026-abc-xyz-0001"


@pytest.mark.parametrize("word", sorted(RESERVED_WORDS))
def test_reserved_words_rejected(word: str) -> None:
    with pytest.raises(ValidationError):
        validate_mnemonic(word)


def test_mnemonic_normalisation() -> None:
    assert validate_mnemonic("  XyZ ") == "xyz"


@pytest.mark.parametrize("bad", ["", "ab", "abcd", "x1z", "x z", "x-z"])
def test_mnemonic_rejects_bad(bad: str) -> None:
    with pytest.raises(ValidationError):
        validate_mnemonic(bad)


def test_researcher_id() -> None:
    assert validate_researcher_id("ABC") == "abc"
    with pytest.raises(ValidationError):
        validate_researcher_id("ab")


def test_serial_bounds() -> None:
    with pytest.raises(ValidationError):
        build_interview_id(2026, "abc", "xyz", MAX_SERIAL + 1)
    with pytest.raises(ValidationError):
        build_interview_id(2026, "abc", "xyz", -1)
