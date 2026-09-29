from __future__ import annotations

from pathlib import Path

import pytest

from interview_intake.errors import IntakeError, SourceError, ValidationError
from interview_intake.fs import read_json, sha256_file
from interview_intake.intake import (
    FAILED_MARKER,
    perform_intake,
    scan_audio_files,
)
from interview_intake.models import Meta
from interview_intake.registry import load_registry

from conftest import RECIP_ABC, RECIP_SUP, FailingBackend, write_wav


def test_intake_success(project, config, source_wav, fake_backend, clock) -> None:
    result = perform_intake(
        project, config, source_wav, "xyz", backend=fake_backend, clock=clock
    )

    assert result.interview_id == "2026-abc-xyz-0001"
    assert result.registry_confirmed
    assert not result.failures

    assert result.audio_path.name == "audio.age"
    assert result.audio_path.exists()
    assert result.transcript_path.exists()
    assert result.note_path.exists()

    meta = Meta.from_dict(read_json(result.meta_path))
    assert meta.interview_id == result.interview_id
    assert meta.researcher_id == "abc"
    assert meta.mnemonic == "xyz"
    assert meta.year == 2026
    assert meta.serial == 1
    assert meta.audio.original_filename == "REC_0042.wav"
    assert meta.audio.format == "wav"
    assert meta.audio.original_sha256 == sha256_file(source_wav)
    assert meta.audio.encrypted_sha256 == sha256_file(result.audio_path)
    assert meta.audio.size_bytes == result.audio_path.stat().st_size
    assert meta.audio.duration_seconds == pytest.approx(0.25, abs=0.02)
    assert meta.created_at == "2026-04-12T09:14:22Z"

    # Both recipients are used, in order.
    assert fake_backend.recipients == [RECIP_ABC, RECIP_SUP]

    # Plaintext is not present in the encrypted artifact.
    assert source_wav.read_bytes() not in result.audio_path.read_bytes()

    # Markdown scaffolding.
    transcript = result.transcript_path.read_text(encoding="utf-8")
    assert "interview_id: 2026-abc-xyz-0001" in transcript
    assert "## Transcript" in transcript
    note = result.note_path.read_text(encoding="utf-8")
    assert "## Observations" in note
    assert "## Transcript" not in note
    assert "SAFETY REMINDERS" in note

    registry = load_registry(project)
    assert registry.last_serial == 1
    assert registry.issued[0].id == result.interview_id
    assert not (project / "registry.lock").exists()


def test_intake_failure_leaves_marker(project, config, source_wav, clock) -> None:
    with pytest.raises(RuntimeError):
        perform_intake(
            project, config, source_wav, "xyz", backend=FailingBackend(), clock=clock
        )

    folder = project / "interviews" / "2026-abc-xyz-0001"
    assert (folder / FAILED_MARKER).exists()
    assert not (folder / "audio.age").exists()
    assert not (folder / "meta.json").exists()
    # The serial is still consumed (phantom serial), by design.
    assert load_registry(project).last_serial == 1


def test_registry_unconfirmed(project, config, source_wav, fake_backend, clock, monkeypatch) -> None:
    monkeypatch.setattr("interview_intake.intake.is_issued", lambda reg, iid: False)
    result = perform_intake(
        project, config, source_wav, "xyz", backend=fake_backend, clock=clock
    )
    assert not result.registry_confirmed
    assert result.failures
    assert "not found in registry.json" in result.failures[0]


def test_invalid_mnemonic_aborts_before_allocation(project, config, source_wav, fake_backend, clock) -> None:
    with pytest.raises(ValidationError):
        perform_intake(
            project, config, source_wav, "toolong", backend=fake_backend, clock=clock
        )
    assert not (project / "interviews" / "2026-abc-toolong-0001").exists()


def test_unsupported_extension(project, config, tmp_path, fake_backend, clock) -> None:
    bad = tmp_path / "sd" / "clip.ogg"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"x")
    with pytest.raises(SourceError):
        perform_intake(project, config, bad, "xyz", backend=fake_backend, clock=clock)


def test_missing_source(project, config, tmp_path, fake_backend, clock) -> None:
    with pytest.raises(SourceError):
        perform_intake(
            project, config, tmp_path / "nope.wav", "xyz", backend=fake_backend, clock=clock
        )


def test_missing_private_key(project, config, source_wav, fake_backend, clock) -> None:
    from dataclasses import replace

    broken = replace(config, private_key_path=str(project.parent / "missing.key"))
    with pytest.raises(IntakeError):
        perform_intake(
            project, broken, source_wav, "xyz", backend=fake_backend, clock=clock
        )


def test_scan_audio_files(tmp_path: Path) -> None:
    sd = tmp_path / "sd"
    write_wav(sd / "a.wav")
    (sd / "b.mp3").write_bytes(b"x")
    (sd / "c.m4a").write_bytes(b"x")
    (sd / "d.flac").write_bytes(b"x")
    (sd / "notes.txt").write_text("ignore")
    (sd / ".hidden.wav").write_bytes(b"x")
    found = [p.name for p in scan_audio_files(sd)]
    assert found == ["a.wav", "b.mp3", "c.m4a", "d.flac"]

    # Single-file input.
    assert scan_audio_files(sd / "a.wav") == [sd / "a.wav"]
    assert scan_audio_files(sd / "notes.txt") == []


def test_scan_missing(tmp_path: Path) -> None:
    with pytest.raises(SourceError):
        scan_audio_files(tmp_path / "nope")
