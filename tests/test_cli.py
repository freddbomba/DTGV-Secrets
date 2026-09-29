"""CLI integration tests using real pyrage encryption."""

from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from interview_intake.cli import main
from interview_intake.crypto import generate_keypair, write_identity_file

pyrage = pytest.importorskip("pyrage")


def _write_wav(path: Path, seconds: float = 0.1) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * int(8000 * seconds))
    return path.read_bytes()


def _project(tmp_path: Path) -> tuple[Path, Path, Path]:
    sync = tmp_path / "sync"
    project = sync / "project"
    (project / "interviews").mkdir(parents=True)
    keydir = tmp_path / "keys"
    keydir.mkdir()
    researcher_id, researcher_pub = generate_keypair()
    _, supervisor_pub = generate_keypair()
    write_identity_file(researcher_id, keydir / "abc.key")
    registry = {
        "schema_version": 1,
        "researchers": {
            "abc": {
                "display_name": "Researcher ABC",
                "age_public_key": researcher_pub,
                "active": True,
            }
        },
        "supervisor": {"age_public_key": supervisor_pub},
        "last_serial": 0,
        "issued": [],
    }
    (project / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
    return project, keydir / "abc.key", tmp_path / "config.json"


def test_cli_config_init_show(tmp_path: Path, capsys) -> None:
    project, key, cfg = _project(tmp_path)
    code = main(
        [
            "--config",
            str(cfg),
            "config",
            "init",
            "--researcher-id",
            "abc",
            "--project-path",
            str(project),
            "--sync-root",
            str(project.parent),
            "--private-key-path",
            str(key),
            "--install-templates",
        ]
    )
    assert code == 0
    assert cfg.exists()
    assert (project / "templates" / "transcript_template.md").exists()

    code = main(["--config", str(cfg), "config", "show"])
    out = capsys.readouterr().out
    assert code == 0
    assert '"researcher_id": "abc"' in out


def test_cli_intake_open_verify(tmp_path: Path, capsys) -> None:
    project, key, cfg = _project(tmp_path)
    main(
        [
            "--config",
            str(cfg),
            "config",
            "init",
            "--researcher-id",
            "abc",
            "--project-path",
            str(project),
            "--sync-root",
            str(project.parent),
            "--private-key-path",
            str(key),
        ]
    )
    source = tmp_path / "sd" / "REC_0042.wav"
    plaintext = _write_wav(source)

    code = main(
        ["--config", str(cfg), "intake", str(source), "-m", "XYZ", "--yes"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "2026-abc-xyz-0001" in out

    assert main(["--config", str(cfg), "verify"]) == 0

    assert main(["--config", str(cfg), "open", "--list"]) == 0
    assert "2026-abc-xyz-0001" in capsys.readouterr().out

    destination = tmp_path / "outside" / "p.wav"
    code = main(
        [
            "--config",
            str(cfg),
            "open",
            "2026-abc-xyz-0001",
            "-o",
            str(destination),
            "--no-open",
        ]
    )
    assert code == 0
    assert destination.read_bytes() == plaintext

    # Decrypting into the sync root must fail.
    code = main(
        [
            "--config",
            str(cfg),
            "open",
            "2026-abc-xyz-0001",
            "-o",
            str(project / "leak.wav"),
            "--no-open",
        ]
    )
    assert code == 1
    assert not (project / "leak.wav").exists()


def test_cli_keygen(tmp_path: Path, capsys) -> None:
    out = tmp_path / "keys"
    code = main(["keygen", "--out", str(out), "--name", "abc"])
    assert code == 0
    assert (out / "abc.key").exists()
    assert "age1" in capsys.readouterr().out


def test_cli_missing_config(tmp_path: Path, capsys) -> None:
    code = main(["--config", str(tmp_path / "nope.json"), "verify"])
    assert code == 1
    assert "Config not found" in capsys.readouterr().err


def test_cli_templates(tmp_path: Path) -> None:
    project, _, _ = _project(tmp_path)
    assert main(["templates", "--project", str(project)]) == 0
    assert (project / "templates" / "note_template.md").exists()


def test_cli_keygen_is_idempotent(tmp_path: Path, capsys) -> None:
    out = tmp_path / "keys"
    assert main(["keygen", "--out", str(out), "--name", "abc"]) == 0
    first = (out / "abc.key").read_bytes()
    assert main(["keygen", "--out", str(out), "--name", "abc"]) == 0
    # Existing key is reused, not overwritten.
    assert (out / "abc.key").read_bytes() == first
    assert "Public key" in capsys.readouterr().out


def test_cli_setup_first_run_and_reuse(tmp_path: Path, capsys) -> None:
    sync = tmp_path / "sync"
    project = sync / "project"
    project.mkdir(parents=True)
    cfg = tmp_path / "config.json"
    keys = tmp_path / "keys"
    args = [
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
        str(keys / "abc.key"),
        "--escrow-key-path",
        str(keys / "supervisor.key"),
        "--create-escrow",
        "--install-templates",
        "--yes",
    ]
    assert main(args) == 0
    assert cfg.exists()
    assert (keys / "abc.key").exists()
    assert (keys / "supervisor.key").exists()
    assert (project / "templates" / "transcript_template.md").exists()
    out = capsys.readouterr().out
    assert "registry.json" in out and "age1" in out

    # Re-running reuses keys instead of creating new ones.
    researcher_before = (keys / "abc.key").read_bytes()
    escrow_before = (keys / "supervisor.key").read_bytes()
    assert main(args) == 0
    assert (keys / "abc.key").read_bytes() == researcher_before
    assert (keys / "supervisor.key").read_bytes() == escrow_before
    assert "Reusing existing researcher key" in capsys.readouterr().out


def test_cli_setup_does_not_create_registry(tmp_path: Path) -> None:
    sync = tmp_path / "sync"
    project = sync / "project"
    project.mkdir(parents=True)
    code = main(
        [
            "--config",
            str(tmp_path / "config.json"),
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
    # Spec section 15: the app must never create registry.json.
    assert not (project / "registry.json").exists()
