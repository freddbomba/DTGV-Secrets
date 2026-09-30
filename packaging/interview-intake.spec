# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Researcher App.

Builds two binaries that share one bundled dependency set:

* ``interview-intake``  — console CLI
* ``Interview Intake``  — windowed GUI (a ``.app`` bundle on macOS)

Usage (from the repository root):

    pyinstaller --noconfirm packaging/interview-intake.spec

The output lands in ``dist/Interview Intake/`` (plus ``dist/Interview Intake.app``
on macOS).
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
    cli_entry="interview_intake_cli.py",
    gui_entry="interview_intake_gui.py",
    app_name="Interview Intake",
    cli_name="interview-intake",
    bundle_id="net.trasformatorio.interview-intake",
)
