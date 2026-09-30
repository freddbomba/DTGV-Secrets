"""Tests for the registration exchange document."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_intake.crypto import generate_keypair, write_identity_file
from interview_intake.errors import ValidationError
from interview_intake.registration import (
    RegistrationRequest,
    read_registration,
    write_registration,
)

pyrage = pytest.importorskip("pyrage")


@pytest.fixture
def identity(tmp_path: Path) -> Path:
    identity, _ = generate_keypair()
    return write_identity_file(identity, tmp_path / "keys" / "abc.key")


def test_create_for_derives_public_key(identity: Path) -> None:
    request = RegistrationRequest.create_for(identity, "abc", "Researcher ABC")
    assert request.researcher_id == "abc"
    assert request.display_name == "Researcher ABC"
    assert request.age_public_key.startswith("age1")
    assert request.created_at.endswith("Z")


def test_roundtrip(tmp_path: Path, identity: Path) -> None:
    request = RegistrationRequest.create_for(identity, "abc", "Researcher ABC")
    path = write_registration(tmp_path / "abc.pub.json", request)
    loaded = read_registration(path)
    assert loaded == request


def test_from_dict_rejects_missing_field() -> None:
    with pytest.raises(ValidationError):
        RegistrationRequest.from_dict({"schema_version": 1, "researcher_id": "abc"})


def test_invalid_researcher_id(identity: Path) -> None:
    with pytest.raises(ValidationError):
        RegistrationRequest.create_for(identity, "AB", "Bad")
