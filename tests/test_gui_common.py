"""Tests for the pure GUI helpers (no display / no tkinter import required)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from interview_intake import gui_common
from interview_intake.config import save_config
from interview_intake.errors import IntakeError
from interview_intake.registration import read_registration

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_module_import_does_not_import_tkinter() -> None:
    code = (
        "import sys, interview_intake.gui_common as g; "
        "assert 'tkinter' not in sys.modules; "
        "assert isinstance(g.tk_available(), bool); "
        "print('ok')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=REPO_ROOT
    )
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout


def test_build_config_valid(tmp_path: Path) -> None:
    sync = tmp_path / "sync"
    project = sync / "project"
    project.mkdir(parents=True)
    config = gui_common.build_config(
        researcher_id="abc",
        project_path=str(project),
        sync_root=str(sync),
        private_key_path=str(tmp_path / "keys" / "abc.key"),
    )
    assert config.researcher_id == "abc"


def test_build_config_rejects_project_outside_sync_root(tmp_path: Path) -> None:
    with pytest.raises(IntakeError):
        gui_common.build_config(
            researcher_id="abc",
            project_path=str(tmp_path / "project"),
            sync_root=str(tmp_path / "elsewhere"),
            private_key_path=str(tmp_path / "abc.key"),
        )


def test_resolve_audio_source_single_empty_and_multiple(tmp_path: Path) -> None:
    from tests.conftest import write_wav

    single = write_wav(tmp_path / "one" / "a.wav")
    assert gui_common.resolve_audio_source(single) == single

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(gui_common.GuiActionError):
        gui_common.resolve_audio_source(empty)

    many = tmp_path / "many"
    write_wav(many / "b.wav")
    write_wav(many / "c.wav")
    with pytest.raises(gui_common.GuiActionError):
        gui_common.resolve_audio_source(many)


def test_write_public_key_qr(tmp_path: Path) -> None:
    path = gui_common.write_public_key_qr("age1exampleexample", tmp_path / "pk.svg")
    assert path.exists()
    assert path.read_text(encoding="utf-8").startswith("<?xml")


def test_load_verify_summary_ok(project: Path) -> None:
    summary = gui_common.load_verify_summary(project)
    assert summary.endswith("OK")


def test_list_interviews_for_empty(tmp_path: Path, project: Path, config) -> None:
    cfg = tmp_path / "config.json"
    save_config(config, cfg)
    assert gui_common.list_interviews_for(cfg) == []


def test_run_intake_with_fake_backend(
    tmp_path: Path, project: Path, config, source_wav: Path, fake_backend
) -> None:
    cfg = tmp_path / "config.json"
    save_config(config, cfg)
    result = gui_common.run_intake(cfg, source_wav, "xyz", backend=fake_backend)
    assert result.interview_id == "2026-abc-xyz-0001"


def test_run_researcher_setup_creates_key_and_registration(tmp_path: Path) -> None:
    pytest.importorskip("pyrage")
    sync = tmp_path / "sync"
    project = sync / "project"
    project.mkdir(parents=True)
    cfg = tmp_path / "cfg" / "config.json"

    result = gui_common.run_researcher_setup(
        researcher_id="abc",
        project_path=str(project),
        sync_root=str(sync),
        private_key_path=str(tmp_path / "keys" / "abc.key"),
        config_path=cfg,
        display_name="Alice Brown",
    )
    assert result.config_path.exists()
    assert result.key_path.exists()
    assert result.public_key.startswith("age1")
    assert result.registration_path is not None
    request = read_registration(result.registration_path)
    assert request.display_name == "Alice Brown"
    assert request.age_public_key == result.public_key

    # The researcher side must never create registry.json.
    assert not (project / "registry.json").exists()

    # Reuse: the key is not regenerated and the public key is re-derived.
    key_path, public_key = gui_common.ensure_researcher_key(result.config)
    assert key_path == result.key_path
    assert public_key == result.public_key

    # And the registration can be rebuilt from the persisted config.
    rebuilt = gui_common.build_registration_request(result.config_path)
    assert rebuilt.age_public_key == result.public_key
