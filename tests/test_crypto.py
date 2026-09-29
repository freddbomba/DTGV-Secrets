"""Tests for the real pyrage backend (skipped if pyrage is unavailable)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from interview_intake.crypto import (
    CryptoError,
    PyrageBackend,
    available_backends,
    generate_keypair,
    public_key_for_identity_file,
    select_backend,
    write_identity_file,
)
from interview_intake.fs import sha256_file

pyrage = pytest.importorskip("pyrage")


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions only")
def test_generate_and_write_keypair(tmp_path: Path) -> None:
    identity, recipient = generate_keypair()
    assert recipient.startswith("age1")
    key = tmp_path / "id.key"
    write_identity_file(identity, key)
    assert key.stat().st_mode & 0o777 == 0o600
    text = key.read_text(encoding="utf-8")
    assert "AGE-SECRET-KEY-1" in text


def test_encrypt_decrypt_to_two_recipients(tmp_path: Path) -> None:
    id1, r1 = generate_keypair()
    id2, r2 = generate_keypair()
    src = tmp_path / "a.wav"
    src.write_bytes(b"audio-bytes" * 1000)
    enc = tmp_path / "audio.age"

    backend = PyrageBackend()
    result = backend.encrypt_file(src, enc, [r1, r2])
    assert result.original_sha256 == sha256_file(src)
    assert result.encrypted_sha256 == sha256_file(enc)
    assert result.encrypted_size == enc.stat().st_size
    assert src.read_bytes() not in enc.read_bytes()

    for index, identity in enumerate((id1, id2)):
        key = tmp_path / f"id{index}.key"
        write_identity_file(identity, key)
        out = tmp_path / f"out{index}.wav"
        backend.decrypt_file(enc, out, key)
        assert out.read_bytes() == src.read_bytes()


def test_public_key_for_identity_file(tmp_path: Path) -> None:
    identity, recipient = generate_keypair()
    key = tmp_path / "id.key"
    write_identity_file(identity, key)
    assert public_key_for_identity_file(key) == recipient


def test_public_key_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CryptoError):
        public_key_for_identity_file(tmp_path / "nope.key")


def test_invalid_recipient(tmp_path: Path) -> None:
    src = tmp_path / "a.wav"
    src.write_bytes(b"x")
    with pytest.raises(CryptoError):
        PyrageBackend().encrypt_file(src, tmp_path / "a.age", ["not-a-recipient"])


def test_available_and_select() -> None:
    assert "pyrage" in available_backends()
    assert select_backend("auto").name in {"pyrage", "age-cli"}
    assert select_backend("pyrage").name == "pyrage"
    with pytest.raises(CryptoError):
        select_backend("bogus")
