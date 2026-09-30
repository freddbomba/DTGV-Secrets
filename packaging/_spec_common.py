"""Shared helpers for the PyInstaller spec files.

The spec files import this module after adding ``SPECPATH`` (the ``packaging/``
directory) to ``sys.path``.  Keeping the logic here avoids duplicating the
Analysis/EXE/COLLECT wiring across the two app specs.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

# Third-party packages bundled with the frozen apps (missing ones are skipped).
_PACKAGES = ("pyrage", "qrcode", "tkinterdnd2")

_BASE_HIDDEN = [
    "tkinter",
    "tkinter.ttk",
    "tkinter.filedialog",
    "tkinter.messagebox",
]


def gather():
    """Return ``(hiddenimports, datas, binaries)`` collected from the packages."""
    hidden = list(_BASE_HIDDEN)
    datas: list = []
    binaries: list = []
    for package in _PACKAGES:
        try:
            hidden += collect_submodules(package)
            datas += collect_data_files(package)
            binaries += collect_dynamic_libs(package)
        except Exception:
            # Optional dependency not installed in the build environment.
            pass
    return hidden, datas, binaries


def _merge(*tocs):
    """Merge TOCs by destination name so shared files are not duplicated."""
    merged: dict = {}
    for toc in tocs:
        for entry in toc:
            merged[entry[0]] = entry
    return list(merged.values())


def build(
    *,
    Analysis,
    PYZ,
    EXE,
    COLLECT,
    BUNDLE,
    entry_dir,
    src_dir,
    cli_entry: str,
    gui_entry: str,
    app_name: str,
    cli_name: str,
    bundle_id: str,
):
    """Build a CLI binary and a windowed GUI (a macOS .app when on Darwin)."""
    hidden, datas, binaries = gather()

    def _analysis(script: str):
        return Analysis(
            [str(Path(entry_dir) / script)],
            pathex=[str(src_dir)],
            binaries=binaries,
            datas=datas,
            hiddenimports=hidden,
            hookspath=[],
            hooksconfig={},
            runtime_hooks=[],
            excludes=[],
            noarchive=False,
        )

    cli_analysis = _analysis(cli_entry)
    cli_pyz = PYZ(cli_analysis.pure)
    cli_exe = EXE(
        cli_pyz,
        cli_analysis.scripts,
        [],
        exclude_binaries=True,
        name=cli_name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=True,
    )

    gui_analysis = _analysis(gui_entry)
    gui_pyz = PYZ(gui_analysis.pure)
    gui_exe = EXE(
        gui_pyz,
        gui_analysis.scripts,
        [],
        exclude_binaries=True,
        name=app_name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )

    collection = COLLECT(
        cli_exe,
        gui_exe,
        _merge(cli_analysis.binaries, gui_analysis.binaries),
        _merge(cli_analysis.datas, gui_analysis.datas),
        strip=False,
        upx=False,
        name=app_name,
    )

    if sys.platform == "darwin":
        BUNDLE(
            collection,
            name=f"{app_name}.app",
            icon=None,
            bundle_identifier=bundle_id,
            info_plist={"NSHighResolutionCapable": True},
        )
    return collection
