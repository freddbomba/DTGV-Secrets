"""Researcher configuration (spec section 14).

Default location: ``~/.config/interview-intake/config.json`` (honouring
``XDG_CONFIG_HOME`` when set, and ``INTERVIEW_INTAKE_CONFIG`` as a full-path
override for tests and unusual setups).
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Optional

from .errors import ConfigError, IntakeError
from .fs import expand_path, is_within, read_json, write_json_atomic
from .models import Config

CONFIG_ENV_VAR = "INTERVIEW_INTAKE_CONFIG"
DEFAULT_CONFIG_DIRNAME = "interview-intake"


def default_config_dir() -> Path:
    """Return the platform-appropriate config directory."""
    if os.name == "nt":  # Windows best-effort
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / DEFAULT_CONFIG_DIRNAME
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / DEFAULT_CONFIG_DIRNAME
    return Path.home() / ".config" / DEFAULT_CONFIG_DIRNAME


def default_config_path() -> Path:
    override = os.environ.get(CONFIG_ENV_VAR)
    if override:
        return expand_path(override)
    return default_config_dir() / "config.json"


def load_config(path: Optional[Path | str] = None) -> tuple[Config, Path]:
    """Load and validate config.json, returning ``(config, resolved_path)``."""
    config_path = expand_path(path) if path is not None else default_config_path()
    if not config_path.exists():
        raise ConfigError(
            f"Config not found at {config_path}. Run `interview-intake config init`."
        )
    raw = read_json(config_path)
    config = Config.from_dict(raw)
    validate_config(config)
    return config, config_path


def save_config(config: Config, path: Optional[Path | str] = None) -> Path:
    """Validate and atomically persist a config, returning the path used."""
    validate_config(config)
    config_path = expand_path(path) if path is not None else default_config_path()
    write_json_atomic(config_path, config.to_dict())
    return config_path


def validate_config(config: Config) -> Config:
    """Cross-field validation the schema alone cannot express."""
    project = expand_path(config.project_path)
    sync_root = expand_path(config.sync_root)
    if not is_within(project, sync_root):
        raise ConfigError(
            f"project_path ({project}) must be inside sync_root ({sync_root})."
        )
    key_path = expand_path(config.private_key_path)
    if key_path.exists() and os.name == "posix":
        mode = key_path.stat().st_mode & 0o777
        if mode & 0o077:
            raise ConfigError(
                f"Private key {key_path} is group/world-accessible (mode {mode:o}); "
                "expected 0600."
            )
    return config


def with_overrides(
    config: Config,
    *,
    researcher_id: Optional[str] = None,
    project_path: Optional[str] = None,
    sync_root: Optional[str] = None,
    private_key_path: Optional[str] = None,
) -> Config:
    """Return a copy of ``config`` with selected fields overridden then validated."""
    changes = {}
    if researcher_id is not None:
        changes["researcher_id"] = researcher_id
    if project_path is not None:
        changes["project_path"] = project_path
    if sync_root is not None:
        changes["sync_root"] = sync_root
    if private_key_path is not None:
        changes["private_key_path"] = private_key_path
    updated = replace(config, **changes)
    return validate_config(updated)


def key_path_for(config: Config) -> Path:
    """Resolve the configured private key path."""
    path = expand_path(config.private_key_path)
    if not path.exists():
        raise IntakeError(f"Private key not found at {path}.")
    return path
