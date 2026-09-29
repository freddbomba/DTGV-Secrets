"""Interview-ID grammar (spec section 4).

The canonical interview ID is::

    ^[0-9]{4}-[a-z]{3}-[a-z]{3}-[0-9]{4}$

    YYYY  year of interview, auto-generated at intake
    AAA   researcher ID, 3 lowercase letters, fixed in config.json
    BBB   mnemonic, 3 lowercase letters, entered at intake
    NNNN  global serial, 4 digits, zero-padded, allocated by the app

All output is lowercase; uppercase input is normalised.  The mnemonic may not
be a reserved word (Windows device names and a few internal names).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import ValidationError

INTERVIEW_ID_RE = re.compile(r"^[0-9]{4}-[a-z]{3}-[a-z]{3}-[0-9]{4}$")
RESEARCHER_ID_RE = re.compile(r"^[a-z]{3}$")
MNEMONIC_RE = re.compile(r"^[a-z]{3}$")

# Windows reserved device names plus names the app uses internally.
RESERVED_WORDS: frozenset[str] = frozenset(
    {"key", "tmp", "new", "old", "aux", "con", "prn", "nul"}
)

MAX_SERIAL = 9999
MIN_SERIAL = 0


@dataclass(frozen=True)
class InterviewId:
    """A parsed, validated interview ID."""

    year: int
    researcher_id: str
    mnemonic: str
    serial: int

    def __str__(self) -> str:
        return build_interview_id(
            self.year, self.researcher_id, self.mnemonic, self.serial
        )


def normalize_mnemonic(value: str) -> str:
    """Lowercase and strip a raw mnemonic without validating it."""
    if value is None:
        raise ValidationError("Mnemonic is required.")
    return str(value).strip().lower()


def validate_mnemonic(value: str) -> str:
    """Return the normalised mnemonic or raise :class:`ValidationError`."""
    normalized = normalize_mnemonic(value)
    if not MNEMONIC_RE.match(normalized):
        raise ValidationError(
            f"Invalid mnemonic {value!r}: expected exactly 3 letters a-z."
        )
    if normalized in RESERVED_WORDS:
        raise ValidationError(
            f"Invalid mnemonic {normalized!r}: reserved word. "
            f"Reserved: {', '.join(sorted(RESERVED_WORDS))}."
        )
    return normalized


def validate_researcher_id(value: str) -> str:
    """Return the normalised researcher ID or raise :class:`ValidationError`."""
    if value is None:
        raise ValidationError("Researcher ID is required.")
    normalized = str(value).strip().lower()
    if not RESEARCHER_ID_RE.match(normalized):
        raise ValidationError(
            f"Invalid researcher ID {value!r}: expected exactly 3 letters a-z."
        )
    return normalized


def validate_serial(serial: int) -> int:
    """Ensure a serial fits the 4-digit grammar."""
    if isinstance(serial, bool) or not isinstance(serial, int):
        raise ValidationError(f"Serial must be an integer, got {serial!r}.")
    if not (MIN_SERIAL <= serial <= MAX_SERIAL):
        raise ValidationError(
            f"Serial {serial} out of range {MIN_SERIAL}-{MAX_SERIAL}."
        )
    return serial


def validate_year(year: int) -> int:
    """Ensure a year is exactly four digits."""
    if isinstance(year, bool) or not isinstance(year, int):
        raise ValidationError(f"Year must be an integer, got {year!r}.")
    if not (1000 <= year <= 9999):
        raise ValidationError(f"Year {year} is not a 4-digit year.")
    return year


def build_interview_id(
    year: int, researcher_id: str, mnemonic: str, serial: int
) -> str:
    """Build a canonical interview ID from its four fields."""
    year = validate_year(year)
    researcher_id = validate_researcher_id(researcher_id)
    mnemonic = validate_mnemonic(mnemonic)
    serial = validate_serial(serial)
    return f"{year:04d}-{researcher_id}-{mnemonic}-{serial:04d}"


def parse_interview_id(value: str) -> InterviewId:
    """Parse and validate an interview ID."""
    if value is None:
        raise ValidationError("Interview ID is required.")
    text = str(value).strip()
    if not INTERVIEW_ID_RE.match(text):
        raise ValidationError(
            f"Invalid interview ID {value!r}: expected "
            "YYYY-aaa-bbb-NNNN (all lowercase)."
        )
    year_s, researcher_id, mnemonic, serial_s = text.split("-")
    return InterviewId(
        year=int(year_s),
        researcher_id=researcher_id,
        mnemonic=mnemonic,
        serial=int(serial_s),
    )


def validate_interview_id(value: str) -> str:
    """Return the ID if valid, else raise :class:`ValidationError`."""
    return str(parse_interview_id(value))


def is_interview_id(value: str) -> bool:
    """Boolean check, useful for filtering directory names."""
    return isinstance(value, str) and INTERVIEW_ID_RE.match(value) is not None
