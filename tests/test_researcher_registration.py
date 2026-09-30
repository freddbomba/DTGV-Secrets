"""Phase 2: researcher registration request + guided helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_intake import cli
from interview_intake.cli import main

pyrage = pytest.importorskip("pyrage")


@pytest.fixture
def setup_project(tmp_path: Path) -> tuple[Path, Path]:
    sync = tmp_path / "sync"
    project = sync / "project"
    project.mkdir(parents=True)
    cfg = tmp_path / "cfg" / "config.json"
    code = main(
        [
            "--config",
            str(cfg),
            "setup",
            "--researcher-id",
            "abc",
            "--project-path",
            str(project),
            "--sync-root",
            str(sync),
            "--private-key-path",
            str(tmp_path / "keys" / "abc.key"),
            "--yes",
        ]
    )
    assert code == 0
    return cfg, project


def test_setup_writes_registration_next_to_config(setup_project) -> None:
    cfg, _ = setup_project
    reg = cfg.parent / "registration" / "abc.pub.json"
    assert reg.exists()
    data = json.loads(reg.read_text(encoding="utf-8"))
    assert data["researcher_id"] == "abc"
    assert data["display_name"] == "Researcher ABC"
    assert data["age_public_key"].startswith("age1")


def test_setup_no_registration_flag(tmp_path: Path) -> None:
    sync = tmp_path / "sync"
    project = sync / "project"
    project.mkdir(parents=True)
    cfg = tmp_path / "cfg" / "config.json"
    code = main(
        [
            "--config",
            str(cfg),
            "setup",
            "--researcher-id",
            "abc",
            "--project-path",
            str(project),
            "--sync-root",
            str(sync),
            "--private-key-path",
            str(tmp_path / "keys" / "abc.key"),
            "--no-registration",
            "--yes",
        ]
    )
    assert code == 0
    assert not (cfg.parent / "registration" / "abc.pub.json").exists()


def test_registration_show_and_export(setup_project, tmp_path: Path, capsys) -> None:
    cfg, _ = setup_project

    assert main(["--config", str(cfg), "registration"]) == 0
    out = capsys.readouterr().out
    assert '"researcher_id": "abc"' in out

    out_file = tmp_path / "abc.pub.json"
    qr_file = tmp_path / "abc.svg"
    code = main(
        [
            "--config",
            str(cfg),
            "registration",
            "--out",
            str(out_file),
            "--display-name",
            "Alice Brown",
            "--qr-out",
            str(qr_file),
        ]
    )
    assert code == 0
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["display_name"] == "Alice Brown"
    assert qr_file.read_text(encoding="utf-8").startswith("<?xml")


def test_select_interview_happy_and_cancel(monkeypatch, capsys) -> None:
    monkeypatch.setattr("builtins.input", lambda *a: "2")
    assert cli._select_interview(["a", "b", "c"]) == "b"

    monkeypatch.setattr("builtins.input", lambda *a: "")
    assert cli._select_interview(["a"]) is None


def test_registration_import_by_supervisor_roundtrip(setup_project, tmp_path: Path) -> None:
    """The supervisor CLI can import the file the researcher just wrote."""
    from interview_intake.supervisor import init_project

    cfg, _ = setup_project
    reg = cfg.parent / "registration" / "abc.pub.json"

    project = tmp_path / "shared" / "project"
    init_project(project, escrow_key_path=tmp_path / "keys" / "sup.key")

    from interview_intake.supervisor_cli import main as sup_main

    assert sup_main(["researcher", "add", "--from", str(reg), "-p", str(project)]) == 0

    from interview_intake.registry import load_registry

    registry = load_registry(project)
    assert "abc" in registry.researchers
