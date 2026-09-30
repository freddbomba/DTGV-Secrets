"""Tests for the supervisor core (registry provisioning + management)."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_intake import supervisor
from interview_intake.crypto import generate_keypair
from interview_intake.errors import IntakeError, RegistryError
from interview_intake.models import IssuedEntry
from interview_intake.registry import (
    interviews_dir,
    load_registry,
    registry_path,
    save_registry,
    templates_dir,
)

pyrage = pytest.importorskip("pyrage")


@pytest.fixture
def keys() -> dict[str, str]:
    _, researcher_pub = generate_keypair()
    _, supervisor_pub = generate_keypair()
    return {"researcher": researcher_pub, "supervisor": supervisor_pub}


@pytest.fixture
def project(tmp_path: Path, keys: dict[str, str]) -> Path:
    project = tmp_path / "sync" / "project"
    supervisor.init_project(
        project,
        escrow_key_path=tmp_path / "keys" / "supervisor.key",
        install_templates=True,
    )
    return project


def test_init_creates_layout_and_registry(tmp_path: Path, keys: dict[str, str]) -> None:
    project = tmp_path / "sync" / "project"
    result = supervisor.init_project(
        project, escrow_key_path=tmp_path / "keys" / "supervisor.key"
    )
    assert result.created_registry is True
    assert registry_path(project).exists()
    assert interviews_dir(project).is_dir()
    assert templates_dir(project).is_dir()
    assert result.escrow_key_created is True
    assert result.escrow_key_path is not None and result.escrow_key_path.exists()
    registry = load_registry(project)
    assert registry.supervisor is not None
    assert registry.supervisor.age_public_key == result.supervisor_public_key


def test_init_is_idempotent(project: Path, tmp_path: Path, keys: dict[str, str]) -> None:
    supervisor.add_researcher(project, "abc", "Researcher ABC", keys["researcher"])
    result = supervisor.init_project(
        project, escrow_key_path=tmp_path / "keys" / "supervisor.key"
    )
    assert result.created_registry is False
    registry = load_registry(project)
    assert "abc" in registry.researchers
    assert registry.supervisor is not None


def test_add_and_list_researcher(project: Path, keys: dict[str, str]) -> None:
    entry = supervisor.add_researcher(
        project, "abc", "Researcher ABC", keys["researcher"]
    )
    assert entry.active is True
    rows = supervisor.list_researchers(project)
    assert [r.researcher_id for r in rows] == ["abc"]
    assert rows[0].display_name == "Researcher ABC"
    assert rows[0].issued == 0


def test_add_rejects_bad_key(project: Path) -> None:
    with pytest.raises(IntakeError):
        supervisor.add_researcher(project, "abc", "Bad", "not-a-key")


def test_add_rejects_empty_name(project: Path, keys: dict[str, str]) -> None:
    with pytest.raises(IntakeError):
        supervisor.add_researcher(project, "abc", "  ", keys["researcher"])


def test_deactivate_and_activate(project: Path, keys: dict[str, str]) -> None:
    supervisor.add_researcher(project, "abc", "Researcher ABC", keys["researcher"])
    supervisor.set_researcher_active(project, "abc", False)
    assert load_registry(project).researchers["abc"].active is False
    supervisor.set_researcher_active(project, "abc", True)
    assert load_registry(project).researchers["abc"].active is True


def test_remove_refuses_with_issued(project: Path, keys: dict[str, str]) -> None:
    supervisor.add_researcher(project, "abc", "Researcher ABC", keys["researcher"])
    registry = load_registry(project)
    registry.issued.append(
        IssuedEntry(id="2026-abc-xyz-0001", researcher="abc", issued_at="2026-01-01T00:00:00Z")
    )
    save_registry(project, registry)

    with pytest.raises(RegistryError):
        supervisor.remove_researcher(project, "abc")

    removed = supervisor.remove_researcher(project, "abc", force=True)
    assert removed == 1
    assert "abc" not in load_registry(project).researchers


def test_backup_registry_creates_copy(project: Path, keys: dict[str, str]) -> None:
    supervisor.add_researcher(project, "abc", "Researcher ABC", keys["researcher"])
    backups = list(project.glob("registry.json.bak.*"))
    assert backups, "expected an automatic registry backup"


def test_backup_escrow_writes_key_and_readme(tmp_path: Path, keys: dict[str, str]) -> None:
    key_path = tmp_path / "keys" / "supervisor.key"
    supervisor.init_project(tmp_path / "project", escrow_key_path=key_path)
    result = supervisor.backup_escrow(key_path, tmp_path / "backup")
    assert result.key_copy.exists()
    assert (result.directory / "README-BACKUP.txt").exists()
    assert result.public_key.startswith("age1")


def test_verify_supervisor_reports_duplicate_keys(project: Path, keys: dict[str, str]) -> None:
    supervisor.add_researcher(project, "abc", "A", keys["researcher"])
    supervisor.add_researcher(project, "def", "B", keys["researcher"])
    report = supervisor.verify_supervisor(project)
    assert any("share a public key" in w for w in report.warnings)


def test_verify_supervisor_reports_unknown_researcher(project: Path, keys: dict[str, str]) -> None:
    registry = load_registry(project)
    registry.issued.append(
        IssuedEntry(id="2026-abc-xyz-0001", researcher="zzz", issued_at="2026-01-01T00:00:00Z")
    )
    save_registry(project, registry)
    report = supervisor.verify_supervisor(project)
    assert any("unknown researcher" in w for w in report.warnings)
