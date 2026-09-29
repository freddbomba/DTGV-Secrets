"""Best-effort platform operations: media eject and default-player opening."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .errors import IntakeError


def find_mount_point(path: Path | str) -> Path:
    """Walk up from ``path`` to the nearest mount point."""
    current = Path(path).expanduser().resolve()
    if current.is_file():
        current = current.parent
    while not os.path.ismount(current):
        parent = current.parent
        if parent == current:
            break
        current = parent
    return current


def eject_path(path: Path | str) -> str:
    """Eject/unmount the volume containing ``path``.  Returns a status message.

    Best-effort and platform-specific; raises :class:`IntakeError` on failure.
    """
    mount = find_mount_point(path)
    try:
        if sys.platform.startswith("darwin"):
            cmd = ["diskutil", "eject", str(mount)]
        elif os.name == "nt":  # pragma: no cover - Windows best-effort
            cmd = [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(New-Object -comObject Shell.Application).NameSpace(17)."
                f"ParseName('{mount}').InvokeVerb('Eject')",
            ]
        else:
            if shutil.which("eject"):
                proc = subprocess.run(["eject", str(mount)], capture_output=True)
                if proc.returncode == 0:
                    return f"Ejected {mount}."
            cmd = ["umount", str(mount)]
        proc = subprocess.run(cmd, capture_output=True)
    except OSError as exc:
        raise IntakeError(f"Could not eject {mount}: {exc}") from exc
    if proc.returncode != 0:
        raise IntakeError(
            f"Could not eject {mount}: {proc.stderr.decode(errors='replace').strip()}"
        )
    return f"Ejected {mount}."
