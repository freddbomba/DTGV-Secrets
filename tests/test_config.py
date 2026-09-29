from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_intake.config import (
    load_config,
    save_config,
    validate_config,
    with_overrides,
)
from interview_intake.errors import ConfigError
from interview_intake.models import Config


def _config(**overrides) -> Config:
    base = dict(
        researcher_id="abc",
        private_key_path="~/keys/abc.key",
        project_path="~/Nextcloud/project",
        sync_root="~/Nextcloud",
        sync_wait_seconds=3,
        lock_stale_seconds=60,
    )
    base.update(overrides)
    return Config(**base)


def test_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    config = _config(
        private_key_path=str(tmp_path / "k"),
        project_path=str(tmp_path / "sync" / "project"),
        sync_root=str(tmp_path / "sync"),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "sync").mkdir()
    save_config(config, path)
    loaded, resolved = load_config(path)
    assert loaded == config
    assert resolved == path


def test_project_must_be_inside_sync_root(tmp_path: Path) -> None:
    config = _config(
        private_key_path=str(tmp_path / "k"),
        project_path=str(tmp_path / "elsewhere"),
        sync_root=str(tmp_path / "sync"),
    )
    with pytest.raises(ConfigError):
        validate_config(config)


def test_schema_version_mismatch() -> None:
    with pytest.raises(ConfigError):
        Config.from_dict(
            {
                "schema_version": 99,
                "researcher_id": "abc",
                "private_key_path": "k",
                "project_path": "p",
                "sync_root": "s",
                "sync_wait_seconds": 1,
                "lock_stale_seconds": 1,
            }
        )


def test_missing_field() -> None:
    with pytest.raises(ConfigError):
        Config.from_dict({"schema_version": 1})


def test_with_overrides(tmp_path: Path) -> None:
    sync = tmp_path / "sync"
    project = sync / "project"
    config = _config(
        private_key_path=str(tmp_path / "k"),
        project_path=str(project),
        sync_root=str(sync),
    )
    updated = with_overrides(config, researcher_id="def")
    assert updated.researcher_id == "def"
    with pytest.raises(ConfigError):
        with_overrides(config, project_path=str(tmp_path / "outside"))


def test_load_missing(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.json")


def test_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(Exception):
        load_config(path)


def test_loaded_json_shape(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    config = _config(
        private_key_path=str(tmp_path / "k"),
        project_path=str(tmp_path / "sync" / "project"),
        sync_root=str(tmp_path / "sync"),
    )
    (tmp_path / "sync").mkdir()
    save_config(config, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert data["researcher_id"] == "abc"
