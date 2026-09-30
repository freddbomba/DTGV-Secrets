"""Supervisor-side project provisioning and registry management.

Per the 2026-09 decision the *Supervisor App* owns ``registry.json``: it creates
and maintains it.  The Researcher App never creates it (spec sections 11/15); it
only reads it and appends allocation records.

Everything here is UI-agnostic so the CLI (or a future GUI) can reuse it.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import default_config_dir
from .crypto import (
    generate_keypair,
    public_key_for_identity_file,
    read_identity,
    validate_recipient,
    write_identity_file,
)
from .errors import RegistryError, ValidationError
from .fs import ensure_private_dir, ensure_private_file, expand_path
from .id_grammar import validate_researcher_id
from .models import Registry, ResearcherEntry, SupervisorEntry
from .qr import qr_available, write_qr
from .registration import RegistrationRequest
from .registry import (
    interviews_dir,
    load_registry,
    registry_path,
    save_registry,
    templates_dir,
)
from .templates import install_default_templates
from .verify import VerifyReport, verify_project


# --------------------------------------------------------------------------- #
# result types
# --------------------------------------------------------------------------- #
@dataclass
class InitResult:
    project_path: Path
    registry_file: Path
    created_registry: bool
    supervisor_public_key: Optional[str]
    escrow_key_path: Optional[Path]
    escrow_key_created: bool
    templates_written: list[Path] = field(default_factory=list)


@dataclass
class ResearcherRow:
    researcher_id: str
    display_name: str
    active: bool
    age_public_key: str
    issued: int


@dataclass
class EscrowInfo:
    key_path: Path
    public_key: str


@dataclass
class EscrowBackupResult:
    directory: Path
    key_copy: Path
    public_qr: Optional[Path]
    secret_qr: Optional[Path]
    public_key: str


@dataclass
class SupervisorVerifyReport:
    base: VerifyReport
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.base.ok and not self.errors


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def default_escrow_key_path() -> Path:
    """Default location of the supervisor/escrow identity file."""
    return default_config_dir() / "keys" / "supervisor.key"


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup_registry(project_path: Path | str) -> Optional[Path]:
    """Copy ``registry.json`` aside before a mutation.  Returns the backup path."""
    path = registry_path(expand_path(project_path))
    if not path.exists():
        return None
    dest = path.with_name(f"{path.name}.bak.{_stamp()}")
    counter = 1
    while dest.exists():
        dest = path.with_name(f"{path.name}.bak.{_stamp()}.{counter}")
        counter += 1
    shutil.copy2(path, dest)
    return dest


def _save_registry(
    project_path: Path | str, registry: Registry, *, backup: bool = True
) -> Path:
    if backup:
        backup_registry(project_path)
    return save_registry(project_path, registry)


def _require_project(project_path: Optional[Path | str]) -> Path:
    if not project_path:
        raise ValidationError("A project path is required (pass --project).")
    project = expand_path(project_path)
    if not (project / "registry.json").exists():
        raise RegistryError(
            f"No registry.json in {project}. Run `interview-supervisor init` first."
        )
    return project


def ensure_escrow_key(
    key_path: Optional[Path | str] = None, *, force: bool = False
) -> tuple[Path, str, bool]:
    """Create the escrow key if missing; never overwrite unless ``force``.

    Returns ``(path, public_key, created)``.
    """
    path = expand_path(key_path) if key_path else default_escrow_key_path()
    if path.exists() and not force:
        return path, public_key_for_identity_file(path), False
    identity, public = generate_keypair()
    ensure_private_dir(path.parent)
    write_identity_file(identity, path)
    return path, public, True


def escrow_info(key_path: Optional[Path | str] = None) -> EscrowInfo:
    path = expand_path(key_path) if key_path else default_escrow_key_path()
    if not path.exists():
        raise RegistryError(
            f"Escrow key not found at {path}. Run `interview-supervisor init` "
            "with escrow creation enabled."
        )
    return EscrowInfo(key_path=path, public_key=public_key_for_identity_file(path))


# --------------------------------------------------------------------------- #
# project initialisation
# --------------------------------------------------------------------------- #
def init_project(
    project_path: Path | str,
    *,
    escrow_key_path: Optional[Path | str] = None,
    create_escrow: bool = True,
    install_templates: bool = True,
    force: bool = False,
) -> InitResult:
    """Create the shared project layout and ``registry.json`` if missing.

    Idempotent by default: an existing registry is kept.  ``force`` regenerates
    the escrow key and rewrites ``registry.json`` from scratch (destructive).
    """
    project = expand_path(project_path)
    project.mkdir(parents=True, exist_ok=True)
    interviews_dir(project).mkdir(parents=True, exist_ok=True)
    templates_dir(project).mkdir(parents=True, exist_ok=True)

    reg_file = registry_path(project)
    existing = reg_file.exists()
    if existing and not force:
        registry = load_registry(project)
    else:
        registry = Registry(last_serial=0, researchers={}, supervisor=None, issued=[])
    created_registry = not existing
    changed = created_registry or force

    escrow_path: Optional[Path] = None
    escrow_created = False
    supervisor_pub: Optional[str] = (
        registry.supervisor.age_public_key if registry.supervisor else None
    )
    if create_escrow:
        escrow_path, supervisor_pub, escrow_created = ensure_escrow_key(
            escrow_key_path, force=force
        )
        if registry.supervisor is None or registry.supervisor.age_public_key != supervisor_pub:
            registry.supervisor = SupervisorEntry(age_public_key=supervisor_pub)
            changed = True

    if changed:
        _save_registry(project, registry, backup=existing)

    templates_written: list[Path] = []
    if install_templates:
        templates_written = install_default_templates(project)

    return InitResult(
        project_path=project,
        registry_file=reg_file,
        created_registry=created_registry,
        supervisor_public_key=supervisor_pub,
        escrow_key_path=escrow_path,
        escrow_key_created=escrow_created,
        templates_written=templates_written,
    )


# --------------------------------------------------------------------------- #
# researcher management
# --------------------------------------------------------------------------- #
def _get_entry(registry: Registry, researcher_id: str) -> ResearcherEntry:
    rid = validate_researcher_id(researcher_id)
    if rid not in registry.researchers:
        raise RegistryError(f"Researcher {rid!r} is not registered.")
    return registry.researchers[rid]


def add_researcher(
    project_path: Path | str,
    researcher_id: str,
    display_name: str,
    age_public_key: str,
    *,
    active: bool = True,
) -> ResearcherEntry:
    """Add or replace a researcher entry in the registry."""
    project = _require_project(project_path)
    rid = validate_researcher_id(researcher_id)
    name = (display_name or "").strip()
    if not name:
        raise ValidationError("A display name is required (--name).")
    recipient = validate_recipient(age_public_key)
    registry = load_registry(project)
    registry.researchers[rid] = ResearcherEntry(
        display_name=name, age_public_key=recipient, active=active
    )
    _save_registry(project, registry)
    return registry.researchers[rid]


def add_researcher_from_registration(
    project_path: Path | str, request: RegistrationRequest
) -> ResearcherEntry:
    return add_researcher(
        project_path,
        request.researcher_id,
        request.display_name,
        request.age_public_key,
    )


def set_researcher_active(
    project_path: Path | str, researcher_id: str, active: bool
) -> ResearcherEntry:
    project = _require_project(project_path)
    registry = load_registry(project)
    entry = _get_entry(registry, researcher_id)
    entry.active = active
    _save_registry(project, registry)
    return entry


def remove_researcher(
    project_path: Path | str, researcher_id: str, *, force: bool = False
) -> int:
    """Remove a researcher; refuses when they have issued interviews."""
    project = _require_project(project_path)
    registry = load_registry(project)
    rid = validate_researcher_id(researcher_id)
    _get_entry(registry, rid)
    issued = [entry for entry in registry.issued if entry.researcher == rid]
    if issued and not force:
        raise RegistryError(
            f"Researcher {rid!r} has {len(issued)} issued interview(s). "
            "Deactivate instead, or pass --force."
        )
    del registry.researchers[rid]
    _save_registry(project, registry)
    return len(issued)


def list_researchers(project_path: Path | str) -> list[ResearcherRow]:
    project = _require_project(project_path)
    registry = load_registry(project)
    counts: dict[str, int] = {}
    for entry in registry.issued:
        counts[entry.researcher] = counts.get(entry.researcher, 0) + 1
    rows = []
    for rid in sorted(registry.researchers):
        entry = registry.researchers[rid]
        rows.append(
            ResearcherRow(
                researcher_id=rid,
                display_name=entry.display_name,
                active=entry.active,
                age_public_key=entry.age_public_key,
                issued=counts.get(rid, 0),
            )
        )
    return rows


def researcher_public_key(project_path: Path | str, researcher_id: str) -> str:
    project = _require_project(project_path)
    registry = load_registry(project)
    return _get_entry(registry, researcher_id).age_public_key


# --------------------------------------------------------------------------- #
# escrow backup
# --------------------------------------------------------------------------- #
_BACKUP_README = """\
Escrow key backup
=================
This directory contains the supervisor/escrow key material for the
interview-intake project.

Files:
* escrow-*.key          the private age identity. KEEP SECRET. Mode 0600.
* escrow-public-*       QR of the PUBLIC key (safe to share).
* escrow-secret-*       QR of the PRIVATE key (SECRET, optional).

Handling:
* Store at least one copy offline (paper/USB in a safe place).
* Never place the escrow private key on a researcher machine or in Nextcloud.
* If a copy leaks, assume every interview is compromised.
* To restore: put the key back at ~/.config/interview-intake/keys/supervisor.key
  with mode 0600 and run `interview-supervisor escrow show`.
"""


def backup_escrow(
    key_path: Optional[Path | str] = None,
    out_dir: Optional[Path | str] = None,
    *,
    include_secret_qr: bool = True,
    qr_format: str = "svg",
) -> EscrowBackupResult:
    """Write a portable backup of the escrow key (key file + optional QRs)."""
    info = escrow_info(key_path)
    directory = expand_path(out_dir) if out_dir else (info.key_path.parent / "backup")
    ensure_private_dir(directory)
    stamp = _stamp()

    key_copy = directory / f"escrow-{stamp}.key"
    shutil.copy2(info.key_path, key_copy)
    ensure_private_file(key_copy)

    public_qr: Optional[Path] = None
    secret_qr: Optional[Path] = None
    if qr_available():
        public_qr = write_qr(
            info.public_key,
            directory / f"escrow-public-{stamp}.{qr_format}",
            fmt=qr_format,
        )
        if include_secret_qr:
            secret_qr = write_qr(
                read_identity(info.key_path),
                directory / f"escrow-secret-{stamp}.{qr_format}",
                fmt=qr_format,
            )
            ensure_private_file(secret_qr)

    (directory / "README-BACKUP.txt").write_text(_BACKUP_README, encoding="utf-8")
    return EscrowBackupResult(
        directory=directory,
        key_copy=key_copy,
        public_qr=public_qr,
        secret_qr=secret_qr,
        public_key=info.public_key,
    )


# --------------------------------------------------------------------------- #
# verification
# --------------------------------------------------------------------------- #
def verify_supervisor(project_path: Path | str) -> SupervisorVerifyReport:
    """Run the standard verify plus supervisor-level registry checks."""
    project = expand_path(project_path)
    base = verify_project(project)
    report = SupervisorVerifyReport(base=base)
    try:
        registry = load_registry(project)
    except Exception as exc:
        report.errors.append(f"registry.json: {exc}")
        return report

    if registry.supervisor is None:
        report.warnings.append("registry.json has no supervisor (escrow) public key.")

    by_key: dict[str, list[str]] = {}
    for rid, entry in registry.researchers.items():
        by_key.setdefault(entry.age_public_key, []).append(rid)
    for key, rids in by_key.items():
        if len(rids) > 1:
            report.warnings.append(
                "researchers share a public key: " + ", ".join(sorted(rids))
            )

    for entry in registry.issued:
        if entry.researcher not in registry.researchers:
            report.warnings.append(
                f"{entry.id}: issued for unknown researcher {entry.researcher!r}."
            )
        elif not registry.researchers[entry.researcher].active:
            report.warnings.append(
                f"{entry.id}: researcher {entry.researcher!r} is inactive."
            )
    return report
