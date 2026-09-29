"""Shared pytest fixtures and a fake age backend (no real crypto in unit tests)."""

from __future__ import annotations

import hashlib
import os
import wave
from datetime import datetime, timezone
from pathlib import Path

import pytest

from interview_intake.crypto import EncryptionResult
from interview_intake.fs import write_json_atomic
from interview_intake.models import Config

RECIP_ABC = "age1abcabcabcabcabcabcabcabcabcabcabcabcabcabcabcabcabcabcabc"
RECIP_SUP = "age1supsupsupsupsupsupsupsupsupsupsupsupsupsupsupsupsupsupsup"
MARKER = b"FAKEAGE1\n"


class FakeBackend:
    """Reversible, deterministic stand-in for the real age backend."""

    name = "fake"

    def __init__(self) -> None:
        self.recipients: list[str] = []

    def encrypt_file(self, src, dst, recipients):
        data = Path(src).read_bytes()
        self.recipients = list(recipients)
        cipher = MARKER + bytes(b ^ 0x5A for b in data)
        Path(dst).write_bytes(cipher)
        return EncryptionResult(
            original_sha256=hashlib.sha256(data).hexdigest(),
            encrypted_sha256=hashlib.sha256(cipher).hexdigest(),
            encrypted_size=len(cipher),
        )

    def decrypt_file(self, src, dst, identity_path):
        data = Path(src).read_bytes()
        if not data.startswith(MARKER):
            raise ValueError("not a fake age file")
        Path(dst).write_bytes(bytes(b ^ 0x5A for b in data[len(MARKER):]))


class FailingBackend:
    """Writes a partial output then fails, to exercise FAILED handling."""

    name = "failing"

    def __init__(self) -> None:
        self.fail_after = True

    def encrypt_file(self, src, dst, recipients):
        Path(dst).write_bytes(b"partial-ciphertext")
        raise RuntimeError("simulated age failure")

    def decrypt_file(self, src, dst, identity_path):  # pragma: no cover
        raise RuntimeError("simulated age failure")


def write_wav(path: Path, seconds: float = 0.2, rate: int = 8000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(rate * seconds))
    return path


FIXED_NOW = datetime(2026, 4, 12, 9, 14, 22, tzinfo=timezone.utc)


def fixed_clock() -> datetime:
    return FIXED_NOW


@pytest.fixture
def clock():
    return fixed_clock


@pytest.fixture
def project(tmp_path: Path) -> Path:
    project = tmp_path / "sync" / "project"
    (project / "interviews").mkdir(parents=True)
    (project / "templates").mkdir()
    registry = {
        "schema_version": 1,
        "researchers": {
            "abc": {
                "display_name": "Researcher ABC",
                "age_public_key": RECIP_ABC,
                "active": True,
            }
        },
        "supervisor": {"age_public_key": RECIP_SUP},
        "last_serial": 0,
        "issued": [],
    }
    write_json_atomic(project / "registry.json", registry)
    return project


@pytest.fixture
def private_key(tmp_path: Path) -> Path:
    key = tmp_path / "keys" / "abc.key"
    key.parent.mkdir(parents=True)
    key.write_text("# fake\nAGE-SECRET-KEY-1FAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE\n")
    os.chmod(key, 0o600)
    return key


@pytest.fixture
def config(tmp_path: Path, project: Path, private_key: Path) -> Config:
    return Config(
        researcher_id="abc",
        private_key_path=str(private_key),
        project_path=str(project),
        sync_root=str(tmp_path / "sync"),
        sync_wait_seconds=0,
        lock_stale_seconds=60,
    )


@pytest.fixture
def source_wav(tmp_path: Path) -> Path:
    return write_wav(tmp_path / "sd" / "REC_0042.wav", seconds=0.25)


@pytest.fixture
def fake_backend() -> FakeBackend:
    return FakeBackend()
