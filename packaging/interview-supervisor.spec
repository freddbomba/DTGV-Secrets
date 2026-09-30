# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Supervisor App.

Builds two binaries that share one bundled dependency set:

* ``interview-supervisor``  — console CLI
* ``Interview Supervisor``  — windowed GUI (a ``.app`` bundle on macOS)

Usage (from the repository root):

    pyinstaller --noconfirm packaging/interview-supervisor.spec

The output lands in ``dist/Interview Supervisor/`` (plus
``dist/Interview Supervisor.app`` on macOS).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, SPECPATH)  # noqa: F821 - SPECPATH is injected by PyInstaller
from _spec_common import build  # noqa: E402

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821

build(
    Analysis=Analysis,  # noqa: F821
    PYZ=PYZ,  # noqa: F821
    EXE=EXE,  # noqa: F821
    COLLECT=COLLECT,  # noqa: F821
    BUNDLE=BUNDLE,  # noqa: F821
    entry_dir=ROOT / "packaging" / "entry",
    src_dir=ROOT / "src",
    cli_entry="interview_supervisor_cli.py",
    gui_entry="interview_supervisor_gui.py",
    app_name="Interview Supervisor",
    cli_name="interview-supervisor",
    bundle_id="net.trasformatorio.interview-supervisor",
)
