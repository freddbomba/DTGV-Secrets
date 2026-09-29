"""Typed documents: ``registry.json`` (spec section 5), ``meta.json`` (section 7)
and ``config.json`` (section 14).

Plain dataclasses plus explicit validation are used instead of a third-party
validation library so the core has no mandatory dependencies.  The schemas are
the contract: fields must not be silently added, dropped, or reordered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from .errors import ConfigError, RegistryError, SchemaVersionError, ValidationError
from .id_grammar import validate_mnemonic, validate_researcher_id

SCHEMA_VERSION = 1


def _require_mapping(value: Any, ctx: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(f"{ctx} must be a JSON object.")
    return value


def _require_str(obj: Mapping[str, Any], key: str, ctx: str) -> str:
    if key not in obj:
        raise ValidationError(f"{ctx} is missing required field {key!r}.")
    value = obj[key]
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{ctx}.{key} must be a non-empty string.")
    return value


def _require_int(obj: Mapping[str, Any], key: str, ctx: str) -> int:
    if key not in obj:
        raise ValidationError(f"{ctx} is missing required field {key!r}.")
    value = obj[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{ctx}.{key} must be an integer.")
    return value


def _require_bool(obj: Mapping[str, Any], key: str, ctx: str) -> bool:
    if key not in obj:
        raise ValidationError(f"{ctx} is missing required field {key!r}.")
    value = obj[key]
    if not isinstance(value, bool):
        raise ValidationError(f"{ctx}.{key} must be a boolean.")
    return value


def _check_schema_version(obj: Mapping[str, Any], ctx: str, expected: int = SCHEMA_VERSION) -> None:
    version = _require_int(obj, "schema_version", ctx)
    if version != expected:
        raise SchemaVersionError(
            f"{ctx} has schema_version={version}, expected {expected}. "
            "Manual migration is required."
        )


# --------------------------------------------------------------------------- #
# registry.json
# --------------------------------------------------------------------------- #
@dataclass
class ResearcherEntry:
    display_name: str
    age_public_key: str
    active: bool = True

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], researcher_id: str) -> "ResearcherEntry":
        ctx = f"registry.researchers[{researcher_id!r}]"
        data = _require_mapping(data, ctx)
        return cls(
            display_name=_require_str(data, "display_name", ctx),
            age_public_key=_require_str(data, "age_public_key", ctx),
            active=_require_bool(data, "active", ctx),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "display_name": self.display_name,
            "age_public_key": self.age_public_key,
            "active": self.active,
        }


@dataclass
class SupervisorEntry:
    age_public_key: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SupervisorEntry":
        ctx = "registry.supervisor"
        data = _require_mapping(data, ctx)
        return cls(age_public_key=_require_str(data, "age_public_key", ctx))

    def to_dict(self) -> dict[str, Any]:
        return {"age_public_key": self.age_public_key}


@dataclass
class IssuedEntry:
    id: str
    researcher: str
    issued_at: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], index: int) -> "IssuedEntry":
        ctx = f"registry.issued[{index}]"
        data = _require_mapping(data, ctx)
        return cls(
            id=_require_str(data, "id", ctx),
            researcher=_require_str(data, "researcher", ctx),
            issued_at=_require_str(data, "issued_at", ctx),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "researcher": self.researcher,
            "issued_at": self.issued_at,
        }


@dataclass
class Registry:
    last_serial: int
    researchers: dict[str, ResearcherEntry] = field(default_factory=dict)
    supervisor: Optional[SupervisorEntry] = None
    issued: list[IssuedEntry] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, data: Any) -> "Registry":
        data = _require_mapping(data, "registry")
        _check_schema_version(data, "registry")
        last_serial = _require_int(data, "last_serial", "registry")
        if last_serial < 0:
            raise RegistryError("registry.last_serial must be >= 0.")

        researchers_raw = _require_mapping(
            data.get("researchers", {}), "registry.researchers"
        )
        researchers: dict[str, ResearcherEntry] = {}
        for researcher_id, entry in researchers_raw.items():
            try:
                normalized = validate_researcher_id(researcher_id)
            except ValidationError as exc:
                raise RegistryError(
                    f"Invalid researcher key {researcher_id!r} in registry: {exc}"
                ) from exc
            researchers[normalized] = ResearcherEntry.from_dict(entry, normalized)

        supervisor_raw = data.get("supervisor")
        supervisor = (
            SupervisorEntry.from_dict(supervisor_raw) if supervisor_raw is not None else None
        )

        issued_raw = data.get("issued", [])
        if not isinstance(issued_raw, list):
            raise RegistryError("registry.issued must be a list.")
        issued = [IssuedEntry.from_dict(item, i) for i, item in enumerate(issued_raw)]

        return cls(
            last_serial=last_serial,
            researchers=researchers,
            supervisor=supervisor,
            issued=issued,
            schema_version=data["schema_version"],
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "researchers": {
                rid: entry.to_dict() for rid, entry in self.researchers.items()
            },
            "supervisor": self.supervisor.to_dict() if self.supervisor else {},
            "last_serial": self.last_serial,
            "issued": [entry.to_dict() for entry in self.issued],
        }
        return result


# --------------------------------------------------------------------------- #
# meta.json
# --------------------------------------------------------------------------- #
@dataclass
class AudioMeta:
    filename: str
    original_filename: str
    original_sha256: str
    encrypted_sha256: str
    size_bytes: int
    duration_seconds: Optional[float]
    format: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AudioMeta":
        ctx = "meta.audio"
        data = _require_mapping(data, ctx)
        duration = data.get("duration_seconds")
        if duration is not None and (
            isinstance(duration, bool) or not isinstance(duration, (int, float))
        ):
            raise ValidationError(f"{ctx}.duration_seconds must be a number or null.")
        return cls(
            filename=_require_str(data, "filename", ctx),
            original_filename=_require_str(data, "original_filename", ctx),
            original_sha256=_require_str(data, "original_sha256", ctx),
            encrypted_sha256=_require_str(data, "encrypted_sha256", ctx),
            size_bytes=_require_int(data, "size_bytes", ctx),
            duration_seconds=float(duration) if duration is not None else None,
            format=_require_str(data, "format", ctx),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "original_filename": self.original_filename,
            "original_sha256": self.original_sha256,
            "encrypted_sha256": self.encrypted_sha256,
            "size_bytes": self.size_bytes,
            "duration_seconds": self.duration_seconds,
            "format": self.format,
        }


@dataclass
class Meta:
    interview_id: str
    researcher_id: str
    mnemonic: str
    year: int
    serial: int
    audio: AudioMeta
    created_at: str
    app_version: str
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, data: Any) -> "Meta":
        data = _require_mapping(data, "meta")
        _check_schema_version(data, "meta")
        ctx = "meta"
        return cls(
            interview_id=_require_str(data, "interview_id", ctx),
            researcher_id=validate_researcher_id(
                _require_str(data, "researcher_id", ctx)
            ),
            mnemonic=validate_mnemonic(_require_str(data, "mnemonic", ctx)),
            year=_require_int(data, "year", ctx),
            serial=_require_int(data, "serial", ctx),
            audio=AudioMeta.from_dict(data.get("audio", {})),
            created_at=_require_str(data, "created_at", ctx),
            app_version=_require_str(data, "app_version", ctx),
            schema_version=data["schema_version"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "interview_id": self.interview_id,
            "researcher_id": self.researcher_id,
            "mnemonic": self.mnemonic,
            "year": self.year,
            "serial": self.serial,
            "audio": self.audio.to_dict(),
            "created_at": self.created_at,
            "app_version": self.app_version,
        }


# --------------------------------------------------------------------------- #
# config.json
# --------------------------------------------------------------------------- #
@dataclass
class Config:
    researcher_id: str
    private_key_path: str
    project_path: str
    sync_root: str
    sync_wait_seconds: int = 3
    lock_stale_seconds: int = 60
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def from_dict(cls, data: Any) -> "Config":
        try:
            data = _require_mapping(data, "config")
            _check_schema_version(data, "config")
            ctx = "config"
            sync_wait = _require_int(data, "sync_wait_seconds", ctx)
            lock_stale = _require_int(data, "lock_stale_seconds", ctx)
            if sync_wait < 0:
                raise ValidationError("config.sync_wait_seconds must be >= 0.")
            if lock_stale < 0:
                raise ValidationError("config.lock_stale_seconds must be >= 0.")
            return cls(
                researcher_id=validate_researcher_id(
                    _require_str(data, "researcher_id", ctx)
                ),
                private_key_path=_require_str(data, "private_key_path", ctx),
                project_path=_require_str(data, "project_path", ctx),
                sync_root=_require_str(data, "sync_root", ctx),
                sync_wait_seconds=sync_wait,
                lock_stale_seconds=lock_stale,
                schema_version=data["schema_version"],
            )
        except ValidationError as exc:
            raise ConfigError(str(exc)) from exc
        except SchemaVersionError as exc:
            raise ConfigError(str(exc)) from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "researcher_id": self.researcher_id,
            "private_key_path": self.private_key_path,
            "project_path": self.project_path,
            "sync_root": self.sync_root,
            "sync_wait_seconds": self.sync_wait_seconds,
            "lock_stale_seconds": self.lock_stale_seconds,
        }
