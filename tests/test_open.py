from __future__ import annotations

import pytest

from interview_intake.errors import IntakeError, SyncRootError
from interview_intake.intake import perform_intake
from interview_intake.open_interview import (
    default_output_path,
    list_interviews,
    open_interview,
)

from conftest import FakeBackend


def _make_interview(project, config, source_wav, clock) -> str:
    result = perform_intake(
        project, config, source_wav, "xyz", backend=FakeBackend(), clock=clock
    )
    return result.interview_id


def test_list_interviews(project, config, source_wav, clock) -> None:
    assert list_interviews(project) == []
    interview_id = _make_interview(project, config, source_wav, clock)
    assert list_interviews(project) == [interview_id]


def test_decrypt_outside_sync_root(project, config, source_wav, clock, tmp_path) -> None:
    interview_id = _make_interview(project, config, source_wav, clock)
    out = tmp_path / "out" / f"{interview_id}.wav"
    result = open_interview(
        project,
        config,
        interview_id,
        output=out,
        backend=FakeBackend(),
        open_file=False,
        warn=lambda message: None,
    )
    assert result == out
    assert out.read_bytes() == source_wav.read_bytes()


def test_refuse_inside_sync_root(project, config, source_wav, clock) -> None:
    interview_id = _make_interview(project, config, source_wav, clock)
    with pytest.raises(SyncRootError):
        open_interview(
            project,
            config,
            interview_id,
            output=project / "leak.wav",
            backend=FakeBackend(),
            open_file=False,
            warn=lambda message: None,
        )
    # Nothing was written into the sync root.
    assert not (project / "leak.wav").exists()


def test_refuse_sync_root_itself(project, config, source_wav, clock, tmp_path) -> None:
    interview_id = _make_interview(project, config, source_wav, clock)
    with pytest.raises(SyncRootError):
        open_interview(
            project,
            config,
            interview_id,
            output=tmp_path / "sync" / "leak.wav",
            backend=FakeBackend(),
            open_file=False,
            warn=lambda message: None,
        )


def test_refuse_overwrite(project, config, source_wav, clock, tmp_path) -> None:
    interview_id = _make_interview(project, config, source_wav, clock)
    out = tmp_path / "out" / "existing.wav"
    out.parent.mkdir(parents=True)
    out.write_bytes(b"existing")
    with pytest.raises(IntakeError):
        open_interview(
            project,
            config,
            interview_id,
            output=out,
            backend=FakeBackend(),
            open_file=False,
            warn=lambda message: None,
        )


def test_force_overwrite(project, config, source_wav, clock, tmp_path) -> None:
    interview_id = _make_interview(project, config, source_wav, clock)
    out = tmp_path / "out" / "existing.wav"
    out.parent.mkdir(parents=True)
    out.write_bytes(b"existing")
    open_interview(
        project,
        config,
        interview_id,
        output=out,
        backend=FakeBackend(),
        open_file=False,
        force=True,
        warn=lambda message: None,
    )
    assert out.read_bytes() == source_wav.read_bytes()


def test_default_output_path() -> None:
    path = default_output_path("2026-abc-xyz-0001")
    assert path.name == "2026-abc-xyz-0001.wav"
    assert path.parent.name == "tmp"


def test_missing_interview(project, config) -> None:
    with pytest.raises(IntakeError):
        open_interview(
            project,
            config,
            "2026-abc-xyz-0999",
            backend=FakeBackend(),
            open_file=False,
            warn=lambda message: None,
        )


def test_invalid_interview_id(project, config) -> None:
    with pytest.raises(IntakeError):
        open_interview(
            project,
            config,
            "not-an-id",
            backend=FakeBackend(),
            open_file=False,
            warn=lambda message: None,
        )


def test_symlink_escape_into_sync_root_is_refused(
    project, config, source_wav, clock, tmp_path
) -> None:
    interview_id = _make_interview(project, config, source_wav, clock)
    link = tmp_path / "out" / "link.wav"
    link.parent.mkdir(parents=True)
    link.symlink_to(project / "target.wav")
    with pytest.raises(SyncRootError):
        open_interview(
            project,
            config,
            interview_id,
            output=link,
            backend=FakeBackend(),
            open_file=False,
            warn=lambda message: None,
        )
