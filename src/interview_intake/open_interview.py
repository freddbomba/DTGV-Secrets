"""Researcher-side decryption helper (spec section 12).

Decrypts an interview to a private directory *outside* the Nextcloud sync root,
refusing any output path inside the sync tree.  Optionally opens the result with
the OS default player.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from .config import expand_path, key_path_for
from .crypto import CryptoBackend, select_backend
from .errors import IntakeError, SyncRootError, ValidationError
from .fs import (
    ensure_private_dir,
    ensure_private_file,
    is_world_readable,
    is_within,
    read_json,
)
from .id_grammar import validate_interview_id
from .intake import AUDIO_FILENAME
from .models import Config
from .registry import interview_dir, interviews_dir

Warn = Callable[[str], None]


def _default_warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def list_interviews(project_path: Path | str) -> list[str]:
    """Return interview IDs present under ``interviews/`` (sorted)."""
    directory = interviews_dir(project_path)
    if not directory.is_dir():
        return []
    ids = []
    for child in directory.iterdir():
        if not child.is_dir():
            continue
        try:
            ids.append(validate_interview_id(child.name))
        except ValidationError:
            continue
    return sorted(ids)


def default_output_path(interview_id: str, extension: str = "wav") -> Path:
    """Propose ``~/tmp/<interview_id>.<ext>`` (spec section 12 step 5)."""
    extension = (extension or "wav").lstrip(".").lower()
    return Path.home() / "tmp" / f"{interview_id}.{extension}"


def _recorded_format(folder: Path) -> str:
    meta_path = folder / "meta.json"
    if not meta_path.exists():
        return "wav"
    try:
        data = read_json(meta_path)
        fmt = data.get("audio", {}).get("format")
        return fmt if isinstance(fmt, str) and fmt else "wav"
    except Exception:
        return "wav"


def _refuse_if_in_sync_root(output: Path, sync_root: Path) -> None:
    if is_within(output, sync_root):
        raise SyncRootError(
            f"Refusing to decrypt into the Nextcloud sync root: {output} is inside "
            f"{expand_path(sync_root)}. Choose a path outside it (e.g. ~/tmp/)."
        )


def _warn_if_world_readable(output: Path, warn: Warn) -> None:
    directory = output.parent
    if is_world_readable(directory):
        warn(
            f"Output directory {directory} may be group/world accessible. "
            "Use a 0700 directory outside the sync root."
        )


def open_interview(
    project_path: Path | str,
    config: Config,
    interview_id: str,
    *,
    output: Optional[Path | str] = None,
    backend: Optional[CryptoBackend] = None,
    open_file: bool = True,
    force: bool = False,
    warn: Optional[Warn] = None,
) -> Path:
    """Decrypt ``interview_id`` to ``output`` and optionally open it."""
    warn = warn or _default_warn
    interview_id = validate_interview_id(interview_id)

    folder = interview_dir(project_path, interview_id)
    if not folder.is_dir():
        raise IntakeError(f"Interview folder not found: {folder}")
    audio = folder / AUDIO_FILENAME
    if not audio.is_file():
        raise IntakeError(f"Encrypted audio not found: {audio}")

    key_path = key_path_for(config)
    sync_root = expand_path(config.sync_root)

    if output is None:
        output = default_output_path(interview_id, _recorded_format(folder))
    output = expand_path(output)

    _refuse_if_in_sync_root(output, sync_root)

    if output.exists() and not force:
        raise IntakeError(
            f"Refusing to overwrite existing file {output}. Delete it or pass force."
        )

    ensure_private_dir(output.parent, 0o700)
    _warn_if_world_readable(output, warn)

    backend = backend or select_backend()
    if output.exists():
        output.unlink()
    backend.decrypt_file(audio, output, key_path)
    ensure_private_file(output, 0o600)

    if open_file:
        _open_with_default_player(output, warn)
    return output


def _open_with_default_player(path: Path, warn: Warn) -> None:
    try:
        if sys.platform.startswith("darwin"):
            subprocess.Popen(
                ["open", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif os.name == "nt":  # pragma: no cover - Windows best-effort
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(
                ["xdg-open", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except OSError as exc:
        warn(f"Could not open {path} with the default player: {exc}")
