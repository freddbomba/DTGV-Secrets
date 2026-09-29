from __future__ import annotations

from pathlib import Path

from interview_intake.intake import FAILED_MARKER, perform_intake
from interview_intake.verify import verify_project

from conftest import FakeBackend


def test_verify_ok(project, config, source_wav, clock) -> None:
    perform_intake(project, config, source_wav, "xyz", backend=FakeBackend(), clock=clock)
    report = verify_project(project)
    assert report.ok
    assert report.checked == 1
    assert not report.errors


def test_verify_detects_tampering(project, config, source_wav, clock) -> None:
    result = perform_intake(
        project, config, source_wav, "xyz", backend=FakeBackend(), clock=clock
    )
    result.audio_path.write_bytes(result.audio_path.read_bytes() + b"tamper")
    report = verify_project(project)
    assert not report.ok
    assert any("mismatch" in error for error in report.errors)


def test_verify_flags_failed_marker(project, config, source_wav, clock) -> None:
    result = perform_intake(
        project, config, source_wav, "xyz", backend=FakeBackend(), clock=clock
    )
    (result.interview_dir / FAILED_MARKER).write_text("{}", encoding="utf-8")
    report = verify_project(project)
    assert report.ok  # FAILED is a warning, not an integrity error
    assert any("FAILED" in warning for warning in report.warnings)


def test_verify_flags_unregistered_folder(project) -> None:
    stray = project / "interviews" / "2026-abc-qqq-0001"
    stray.mkdir()
    report = verify_project(project)
    assert report.ok
    assert any("not listed" in warning for warning in report.warnings)


def test_verify_missing_registry(tmp_path: Path) -> None:
    report = verify_project(tmp_path)
    assert not report.ok
