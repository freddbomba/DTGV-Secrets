"""Researcher registration request: the public-key exchange document.

The Researcher App writes this file after ``setup``; the Supervisor App imports
it with ``interview-supervisor researcher add --from FILE``.  It contains only a
public key, so it is safe to email or show as a QR code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .crypto import public_key_for_identity_file, validate_recipient
from .errors import ValidationError
from .fs import expand_path, read_json, write_json_atomic
from .id_grammar import validate_researcher_id

REGISTRATION_SCHEMA_VERSION = 1


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class RegistrationRequest:
    researcher_id: str
    display_name: str
    age_public_key: str
    created_at: str
    schema_version: int = REGISTRATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        self.researcher_id = validate_researcher_id(self.researcher_id)
        self.display_name = (self.display_name or "").strip()
        if not self.display_name:
            raise ValidationError("display_name must not be empty.")
        self.age_public_key = validate_recipient(self.age_public_key)

    @classmethod
    def create_for(
        cls, identity_path: Path | str, researcher_id: str, display_name: str
    ) -> "RegistrationRequest":
        """Build a request by deriving the public key from an identity file."""
        public_key = public_key_for_identity_file(expand_path(identity_path))
        return cls(
            researcher_id=researcher_id,
            display_name=display_name,
            age_public_key=public_key,
            created_at=_utcnow(),
        )

    @classmethod
    def from_dict(cls, data: Any) -> "RegistrationRequest":
        if not isinstance(data, Mapping):
            raise ValidationError("registration must be a JSON object.")
        version = data.get("schema_version")
        if version != REGISTRATION_SCHEMA_VERSION:
            raise ValidationError(
                f"registration.schema_version must be {REGISTRATION_SCHEMA_VERSION}."
            )
        for key in ("researcher_id", "display_name", "age_public_key", "created_at"):
            if key not in data:
                raise ValidationError(f"registration is missing field {key!r}.")
        return cls(
            researcher_id=data["researcher_id"],
            display_name=data["display_name"],
            age_public_key=data["age_public_key"],
            created_at=data["created_at"],
            schema_version=version,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "researcher_id": self.researcher_id,
            "display_name": self.display_name,
            "age_public_key": self.age_public_key,
            "created_at": self.created_at,
        }


def write_registration(path: Path | str, request: RegistrationRequest) -> Path:
    path = expand_path(path)
    write_json_atomic(path, request.to_dict())
    return path


def read_registration(path: Path | str) -> RegistrationRequest:
    return RegistrationRequest.from_dict(read_json(expand_path(path)))
