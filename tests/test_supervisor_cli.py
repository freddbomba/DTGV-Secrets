"""CLI integration tests for the Supervisor App."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_intake.crypto import generate_keypair
from interview_intake.registration import RegistrationRequest, write_registration
from interview_intake.supervisor_cli import main

pyrage = pytest.importorskip("pyrage")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    project = tmp_path / "sync" / "project"
    code = main(
        ["init", "-p", str(project), "--escrow-key", str(tmp_path / "keys" / "supervisor.key")]
    )
    assert code == 0
    return project


def test_init_cli(project: Path) -> None:
    assert (project / "registry.json").exists()
    assert (project / "interviews").is_dir()
    assert (project / "templates" / "transcript_template.md").exists()


def test_add_list_and_show(project: Path, capsys) -> None:
    _, researcher_pub = generate_keypair()
    code = main(
        ["researcher", "add", "abc", "--name", "Researcher ABC", "--key", researcher_pub, "-p", str(project)]
    )
    assert code == 0

    capsys.readouterr()
    code = main(["researcher", "list", "-p", str(project)])
    out = capsys.readouterr().out
    assert code == 0
    assert "abc" in out and "Researcher ABC" in out

    code = main(["escrow", "show", "--escrow-key", str(project.parent.parent / "keys" / "supervisor.key")])
    out = capsys.readouterr().out
    assert code == 0
    assert "age1" in out


def test_add_from_registration(project: Path, tmp_path: Path, capsys) -> None:
    identity, _ = generate_keypair()
    identity_path = tmp_path / "abc.key"
    identity_path.write_text(identity + "\n", encoding="utf-8")
    import os

    os.chmod(identity_path, 0o600)
    request = RegistrationRequest.create_for(identity_path, "abc", "Researcher ABC")
    reg_file = write_registration(tmp_path / "abc.pub.json", request)

    code = main(["researcher", "add", "--from", str(reg_file), "-p", str(project)])
    assert code == 0
    out = capsys.readouterr().out
    assert "Researcher ABC" in out


def test_add_bad_key_fails(project: Path, capsys) -> None:
    code = main(["researcher", "add", "abc", "--name", "X", "--key", "nope", "-p", str(project)])
    assert code == 1
    assert "error:" in capsys.readouterr().err


def test_verify_and_registry_show(project: Path, capsys) -> None:
    assert main(["verify", "-p", str(project)]) == 0
    assert "OK" in capsys.readouterr().out

    assert main(["registry", "show", "-p", str(project)]) == 0
    assert '"schema_version": 1' in capsys.readouterr().out
