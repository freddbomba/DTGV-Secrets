"""Pure, headless helpers shared by the Tk GUI layers.

Importing this module never imports ``tkinter``: :func:`tk_available` only probes
with :func:`importlib.util.find_spec`.  Everything here is UI-agnostic so it can
be unit-tested without a display.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import (
    key_path_for,
    load_config,
    save_config,
    validate_config,
)
from .crypto import (
    generate_keypair,
    public_key_for_identity_file,
    write_identity_file,
)
from .errors import IntakeError
from .fs import ensure_private_dir, expand_path, wipe_file
from .id_grammar import validate_mnemonic, validate_researcher_id
from .intake import perform_intake, scan_audio_files
from .media import eject_path
from .models import Config
from .open_interview import list_interviews, open_interview
from .qr import write_qr
from .registration import RegistrationRequest, write_registration
from .verify import verify_project


class GuiError(IntakeError):
    """Base class for GUI-facing errors."""


class GuiUnavailableError(GuiError):
    """The GUI backend (tkinter / display) is not available."""


class GuiActionError(GuiError):
    """An action requested from the GUI could not be completed."""


def tk_available() -> bool:
    """True when the stdlib ``tkinter`` package can be imported.

    This only probes the module spec; it never imports tkinter, so the rest of
    the package stays headless-safe.
    """
    return importlib.util.find_spec("tkinter") is not None


def display_name_for(researcher_id: str, override: Optional[str] = None) -> str:
    """Human-readable researcher name for the registration request."""
    if override and override.strip():
        return override.strip()
    return f"Researcher {researcher_id.upper()}"


def build_config(
    *,
    researcher_id: str,
    project_path: str,
    sync_root: str,
    private_key_path: str,
    sync_wait_seconds: int = 3,
    lock_stale_seconds: int = 60,
) -> Config:
    """Build and validate a researcher :class:`Config` (does not write it)."""
    config = Config(
        researcher_id=validate_researcher_id(researcher_id),
        private_key_path=str(expand_path(private_key_path)),
        project_path=str(expand_path(project_path)),
        sync_root=str(expand_path(sync_root)),
        sync_wait_seconds=int(sync_wait_seconds),
        lock_stale_seconds=int(lock_stale_seconds),
    )
    return validate_config(config)


def ensure_researcher_key(
    config: Config, *, force: bool = False
) -> tuple[Path, str]:
    """Create the researcher key if missing; return ``(key_path, public_key)``."""
    key_path = expand_path(config.private_key_path)
    if key_path.exists() and not force:
        return key_path, public_key_for_identity_file(key_path)
    identity, public = generate_keypair()
    ensure_private_dir(key_path.parent)
    write_identity_file(identity, key_path)
    return key_path, public


@dataclass
class ResearcherSetup:
    config: Config
    config_path: Path
    key_path: Path
    public_key: str
    registration_path: Optional[Path]


def run_researcher_setup(
    *,
    researcher_id: str,
    project_path: str,
    sync_root: str,
    private_key_path: str,
    config_path: Optional[Path | str] = None,
    display_name: Optional[str] = None,
    sync_wait_seconds: int = 3,
    lock_stale_seconds: int = 60,
    create_registration: bool = True,
    force: bool = False,
) -> ResearcherSetup:
    """First-run setup as used by the researcher GUI.

    Creates config, key (if missing) and the registration request.  Never touches
    ``registry.json`` — that is the supervisor's responsibility.
    """
    config = build_config(
        researcher_id=researcher_id,
        project_path=project_path,
        sync_root=sync_root,
        private_key_path=private_key_path,
        sync_wait_seconds=sync_wait_seconds,
        lock_stale_seconds=lock_stale_seconds,
    )
    resolved = save_config(config, config_path)
    key_path, public_key = ensure_researcher_key(config, force=force)

    registration_path: Optional[Path] = None
    if create_registration:
        registration_path = (
            resolved.parent
            / "registration"
            / f"{config.researcher_id}.pub.json"
        )
        request = RegistrationRequest.create_from_public_key(
            config.researcher_id,
            display_name_for(config.researcher_id, display_name),
            public_key,
        )
        write_registration(registration_path, request)

    return ResearcherSetup(
        config=config,
        config_path=resolved,
        key_path=key_path,
        public_key=public_key,
        registration_path=registration_path,
    )


def build_registration_request(
    config_path: Optional[Path | str] = None,
    display_name: Optional[str] = None,
) -> RegistrationRequest:
    """Load the config and build the registration request from its key."""
    config, _ = load_config(config_path)
    public_key = public_key_for_identity_file(key_path_for(config))
    return RegistrationRequest.create_from_public_key(
        config.researcher_id,
        display_name_for(config.researcher_id, display_name),
        public_key,
    )


def write_public_key_qr(
    public_key: str, path: Path | str, fmt: Optional[str] = None
) -> Path:
    """Render a public key as a QR file (svg/png/txt)."""
    return write_qr(public_key, expand_path(path), fmt=fmt)


def list_interviews_for(config_path: Optional[Path | str] = None) -> list[str]:
    """List interview IDs in the project configured by ``config_path``."""
    config, _ = load_config(config_path)
    return list_interviews(expand_path(config.project_path))


def resolve_audio_source(source: Path | str) -> Path:
    """Resolve a picked file/dir to a single audio file, or raise."""
    candidates = scan_audio_files(str(expand_path(source)))
    if not candidates:
        raise GuiActionError(f"No supported audio files found under {source!r}.")
    if len(candidates) > 1:
        raise GuiActionError(
            "Multiple audio files found; pick a single file instead of a folder."
        )
    return candidates[0]


def run_intake(
    config_path: Optional[Path | str],
    source: Path | str,
    mnemonic: str,
    *,
    backend=None,
    wipe_source: bool = False,
    eject_after: bool = False,
    max_retries: int = 5,
):
    """Run an intake from the GUI (thin wrapper over :func:`perform_intake`)."""
    config, _ = load_config(config_path)
    mnemonic = validate_mnemonic(mnemonic)
    audio = resolve_audio_source(source)
    result = perform_intake(
        expand_path(config.project_path),
        config,
        audio,
        mnemonic,
        backend=backend,
        max_retries=max_retries,
    )
    if wipe_source:
        wipe_file(audio)
    if eject_after:
        eject_path(audio)
    return result


def decrypt_interview(
    config_path: Optional[Path | str],
    interview_id: str,
    *,
    output: Optional[Path | str] = None,
    open_file: bool = True,
    force: bool = False,
) -> Path:
    """Decrypt an interview, refusing outputs inside the sync root."""
    config, _ = load_config(config_path)
    return open_interview(
        expand_path(config.project_path),
        config,
        interview_id,
        output=expand_path(output) if output else None,
        open_file=open_file,
        force=force,
    )


def load_verify_summary(project: Path | str) -> str:
    """Return a human-readable verify report for a project folder."""
    report = verify_project(expand_path(project))
    lines = [f"warning: {warning}" for warning in report.warnings]
    lines += [f"error: {error}" for error in report.errors]
    status = "OK" if report.ok else "FAILED"
    lines.append(f"Checked {report.checked} issued interview(s): {status}")
    return "\n".join(lines)
