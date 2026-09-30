#!/usr/bin/env python3
"""Capture the GUI tabs to ``docs/images/`` for the README.

The apps are instantiated with sample data (no files are written, no actions are
fired) and each notebook tab is screenshotted with X11 tools.

Requirements: an X display, ``tkinter``, and either ImageMagick ``import`` or
``xwd`` + ``convert``.  Run from anywhere::

    python scripts/capture_gui_screenshots.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from interview_intake import gui as gui_mod  # noqa: E402
from interview_intake import supervisor_gui as sup_mod  # noqa: E402

OUT = ROOT / "docs" / "images"
GEOMETRY = "880x600+60+60"
EXAMPLE_KEY = "age1qyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqszqgpqyqszqgpqyq"


def _find_notebook(widget, ttk):
    for child in widget.winfo_children():
        if isinstance(child, ttk.Notebook):
            return child
        found = _find_notebook(child, ttk)
        if found is not None:
            return found
    return None


def _grab(root, path: Path) -> None:
    root.update_idletasks()
    root.update()
    time.sleep(0.4)
    root.update()
    tmp = Path("/tmp/_gui_capture.xwd")
    wid = str(root.winfo_id())
    if shutil.which("xwd") and shutil.which("convert"):
        subprocess.run(["xwd", "-silent", "-id", wid, "-out", str(tmp)], check=True)
        subprocess.run(["convert", str(tmp), str(path)], check=True)
    else:
        subprocess.run(["import", "-window", wid, str(path)], check=True)
    print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")


def _capture_app(app, ttk, labels: tuple[str, ...], prefix: str) -> None:
    notebook = _find_notebook(app.root, ttk)
    assert notebook is not None, "notebook not found"
    for index, label in enumerate(labels):
        notebook.select(index)
        _grab(app.root, OUT / f"{prefix}-{label}.png")


def _researcher() -> None:
    tk, ttk, filedialog, messagebox = gui_mod.tk_modules()
    root = tk.Tk()
    root.geometry(GEOMETRY)
    try:
        ttk.Style(root).theme_use("clam")
    except Exception:  # noqa: BLE001 - theme is cosmetic only
        pass
    app = gui_mod.ResearcherApp(
        root, tk, ttk, filedialog, messagebox, dnd=False
    )
    app.config_path_var.set("~/.config/interview-intake/config.json")
    app.researcher_id_var.set("abc")
    app.project_path_var.set("~/Nextcloud/DTGV/project")
    app.sync_root_var.set("~/Nextcloud/DTGV")
    app.key_path_var.set("~/.config/interview-intake/keys/abc.key")
    app.display_name_var.set("Researcher ABC")
    app.public_key_var.set(EXAMPLE_KEY)
    app.intake_source_var.set("/media/abc/SDCARD/REC_0001.wav")
    app.mnemonic_var.set("foo")
    app.interview_id_var.set("2026-abc-foo-0001")
    for interview_id in ("2026-abc-foo-0001", "2026-abc-foo-0002", "2026-abc-bar-0003"):
        app.interview_list.insert("end", interview_id)
    app._set_status("Ready.")
    _capture_app(app, ttk, ("setup", "intake", "open", "registration"), "gui-researcher")
    root.destroy()


def _supervisor() -> None:
    tk, ttk, filedialog, messagebox = sup_mod.tk_modules()
    root = tk.Tk()
    root.geometry(GEOMETRY)
    try:
        ttk.Style(root).theme_use("clam")
    except Exception:  # noqa: BLE001 - theme is cosmetic only
        pass
    app = sup_mod.SupervisorApp(root, tk, ttk, filedialog, messagebox)
    app.project_var.set("~/Nextcloud/DTGV/project")
    app.researcher_id_var.set("abc")
    app.display_name_var.set("Researcher ABC")
    app.public_key_var.set(EXAMPLE_KEY)
    app.registration_file_var.set("~/Downloads/abc.pub.json")
    app.escrow_public_var.set(EXAMPLE_KEY)
    app.researcher_list.insert("end", "abc   active   age1qyq…yq   2 interviews")
    app.researcher_list.insert("end", "xyz   inactive age1qqq…qq   0 interviews")
    app.verify_text.insert("end", "Checked 3 issued interview(s): OK\n")
    app._set_status("Ready.")
    _capture_app(app, ttk, ("init", "researchers", "escrow", "verify"), "gui-supervisor")
    root.destroy()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    _researcher()
    _supervisor()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
