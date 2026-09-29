"""Filesystem helpers: atomic writes, hashing, private directories, containment.

All JSON document writes go through :func:`write_json_atomic`, which mirrors the
``write_json_atomic`` contract from spec section 10: write to a temp file in the
same directory, ``fsync``, then ``os.replace``.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from .errors import IntakeError

_CHUNK = 1024 * 1024


def expand_path(path: str | os.PathLike[str]) -> Path:
    """Expand ``~`` and environment variables, returning a Path."""
    return Path(os.path.expandvars(os.path.expanduser(str(path))))


def write_json_atomic(path: Path, data: Any) -> None:
    """Atomically write ``data`` as pretty JSON to ``path``.

    The temporary file is created in the destination directory so that
    ``os.replace`` stays on the same filesystem and is therefore atomic.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        _fsync_dir(path.parent)
    except BaseException:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def read_json(path: Path) -> Any:
    """Read JSON from ``path`` raising :class:`IntakeError` on failure."""
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise IntakeError(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise IntakeError(f"Malformed JSON in {path}: {exc}") from exc


def _fsync_dir(directory: Path) -> None:
    """Best-effort fsync of a directory (unsupported on Windows)."""
    try:
        fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def sha256_file(path: Path) -> str:
    """Streaming SHA-256 of a file."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes | bytearray) -> str:
    return hashlib.sha256(data).hexdigest()


def ensure_private_dir(path: Path, mode: int = 0o700) -> Path:
    """Create ``path`` (and parents), hardening only newly-created directories.

    Pre-existing directories are left untouched so that, for example, choosing
    ``/tmp`` as a destination does not chmod the system temp dir.  Callers that
    care can inspect :func:`is_world_readable` and warn.
    """
    path = Path(path)
    created = False
    try:
        path.mkdir(parents=True, exist_ok=False)
        created = True
    except FileExistsError:
        pass
    except FileNotFoundError:  # parent removed between check and mkdir
        path.mkdir(parents=True, exist_ok=True)
        created = True
    if created and os.name == "posix":
        try:
            os.chmod(path, mode)
        except OSError:
            pass
    return path


def ensure_private_file(path: Path, mode: int = 0o600) -> Path:
    """Enforce ``mode`` on an existing file where supported."""
    path = Path(path)
    if os.name == "posix":
        try:
            os.chmod(path, mode)
        except OSError:
            pass
    return path


def is_within(child: Path, parent: Path) -> bool:
    """True if ``child`` is inside ``parent`` (or equal to it).

    Both paths are resolved first, so symlinks cannot be used to escape the
    check.  ``resolve(strict=False)`` tolerates the target not existing yet,
    which is exactly the decryption-output case.
    """
    child_r = Path(child).expanduser().resolve()
    parent_r = Path(parent).expanduser().resolve()
    try:
        child_r.relative_to(parent_r)
        return True
    except ValueError:
        return False


def is_world_readable(path: Path) -> bool:
    """True when the (resolved) path resides in a world-readable location.

    The check is intentionally conservative: it flags the classic temp dirs and
    any directory whose permission bits allow group/other access.  It is used
    only to *warn*, never to block.
    """
    path = Path(path).expanduser().resolve()
    directory = path if path.is_dir() else path.parent
    if not directory.exists():
        return False
    try:
        mode = directory.stat().st_mode
    except OSError:
        return False
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        return True
    return str(directory) in {"/tmp", "/var/tmp", "/dev/shm"}


def delete_file(path: Path) -> bool:
    """Delete a file, returning True if something was removed."""
    try:
        Path(path).unlink()
        return True
    except FileNotFoundError:
        return False


def wipe_file(path: Path) -> None:
    """Best-effort overwrite-then-unlink of a single file.

    On copy-on-write / flash storage this is not a guaranteed erasure; the SD
    card remains untrusted after use, as stated in the trust model.
    """
    path = Path(path)
    if not path.is_file():
        return
    try:
        size = path.stat().st_size
        with path.open("r+b") as handle:
            remaining = size
            while remaining > 0:
                block = min(_CHUNK, remaining)
                handle.write(b"\x00" * block)
                remaining -= block
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
