"""Loading and saving ``registry.json`` (spec section 5).

The registry is re-read before every allocation and its ``schema_version`` is
validated.  Writes are atomic (see :func:`interview_intake.fs.write_json_atomic`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .errors import RegistryError
from .fs import read_json, write_json_atomic
from .models import Registry
from .id_grammar import validate_researcher_id

REGISTRY_FILENAME = "registry.json"
LOCK_FILENAME = "registry.lock"
TEMPLATES_DIRNAME = "templates"
INTERVIEWS_DIRNAME = "interviews"


def registry_path(project_path: Path | str) -> Path:
    return Path(project_path) / REGISTRY_FILENAME


def lock_path(project_path: Path | str) -> Path:
    return Path(project_path) / LOCK_FILENAME


def interviews_dir(project_path: Path | str) -> Path:
    return Path(project_path) / INTERVIEWS_DIRNAME


def templates_dir(project_path: Path | str) -> Path:
    return Path(project_path) / TEMPLATES_DIRNAME


def interview_dir(project_path: Path | str, interview_id: str) -> Path:
    return interviews_dir(project_path) / interview_id


def load_registry(project_path: Path | str, *, required: bool = True) -> Registry:
    """Load, parse and validate the registry.

    ``required`` is False for tooling that needs to tolerate an absent registry
    (for example ``verify`` on a brand-new project).  The app itself always
    requires it.
    """
    path = registry_path(project_path)
    if not path.exists():
        if required:
            raise RegistryError(
                f"registry.json not found at {path}. The app will not create it; "
                "the supervisor must provision the project first."
            )
        return Registry(last_serial=0)
    raw = read_json(path)
    return Registry.from_dict(raw)


def save_registry(project_path: Path | str, registry: Registry) -> Path:
    path = registry_path(project_path)
    write_json_atomic(path, registry.to_dict())
    return path


def get_researcher(registry: Registry, researcher_id: str):
    """Return the researcher entry or raise a clear :class:`RegistryError`."""
    normalized = validate_researcher_id(researcher_id)
    entry = registry.researchers.get(normalized)
    if entry is None:
        raise RegistryError(
            f"Researcher {normalized!r} is not registered. "
            "The supervisor must register the researcher first."
        )
    if not entry.active:
        raise RegistryError(f"Researcher {normalized!r} is inactive.")
    return entry


def get_supervisor(registry: Registry):
    if registry.supervisor is None or not registry.supervisor.age_public_key:
        raise RegistryError("Supervisor public key is missing from registry.json.")
    return registry.supervisor


def is_issued(registry: Registry, interview_id: str) -> bool:
    return any(entry.id == interview_id for entry in registry.issued)


def find_issued(registry: Registry, interview_id: str) -> Optional[object]:
    for entry in registry.issued:
        if entry.id == interview_id:
            return entry
    return None
