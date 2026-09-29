from __future__ import annotations

from pathlib import Path

import pytest

from interview_intake.errors import RegistryError, SchemaVersionError
from interview_intake.fs import write_json_atomic
from interview_intake.registry import (
    get_researcher,
    get_supervisor,
    is_issued,
    load_registry,
    save_registry,
)


def test_load_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(RegistryError):
        load_registry(tmp_path)


def test_load_missing_optional(tmp_path: Path) -> None:
    registry = load_registry(tmp_path, required=False)
    assert registry.last_serial == 0


def test_schema_mismatch(tmp_path: Path) -> None:
    write_json_atomic(tmp_path / "registry.json", {"schema_version": 2})
    with pytest.raises(SchemaVersionError):
        load_registry(tmp_path)


def test_roundtrip(project: Path) -> None:
    registry = load_registry(project)
    assert registry.last_serial == 0
    assert get_researcher(registry, "abc").active
    assert get_supervisor(registry).age_public_key
    assert not is_issued(registry, "2026-abc-xyz-0001")


def test_unknown_researcher(project: Path) -> None:
    registry = load_registry(project)
    with pytest.raises(RegistryError):
        get_researcher(registry, "zzz")


def test_inactive_researcher(project: Path) -> None:
    registry = load_registry(project)
    registry.researchers["abc"].active = False
    save_registry(project, registry)
    with pytest.raises(RegistryError):
        get_researcher(load_registry(project), "abc")


def test_save_preserves_schema(project: Path) -> None:
    registry = load_registry(project)
    registry.last_serial = 7
    save_registry(project, registry)
    reloaded = load_registry(project)
    assert reloaded.last_serial == 7
    assert reloaded.schema_version == 1


def test_issued_entry_roundtrip(project: Path) -> None:
    from interview_intake.models import IssuedEntry

    registry = load_registry(project)
    registry.last_serial = 1
    registry.issued.append(
        IssuedEntry(id="2026-abc-xyz-0001", researcher="abc", issued_at="2026-01-01T00:00:00Z")
    )
    save_registry(project, registry)
    reloaded = load_registry(project)
    assert is_issued(reloaded, "2026-abc-xyz-0001")
