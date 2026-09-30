"""Smoke tests for the researcher GUI (stubbed Tk + real Tk when available)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import interview_intake.gui as gui
from interview_intake.gui_common import GuiUnavailableError


def _stub_tk(monkeypatch):
    modules = {}
    for name in ("tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.messagebox"):
        module = MagicMock(name=name)
        monkeypatch.setitem(sys.modules, name, module)
        modules[name] = module
    return modules


def test_gui_module_imports_without_tkinter() -> None:
    import subprocess

    code = (
        "import sys; import interview_intake.gui as g; "
        "assert 'tkinter' not in sys.modules; "
        "assert callable(g.main); print('ok')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout


def test_tk_modules_raises_when_unavailable(monkeypatch) -> None:
    def boom(name, package=None):
        raise ImportError(name)

    monkeypatch.setattr(gui, "_import", boom)
    with pytest.raises(GuiUnavailableError):
        gui.tk_modules()


def test_researcher_app_builds_with_stubbed_tk(monkeypatch) -> None:
    _stub_tk(monkeypatch)
    tk, ttk, filedialog, messagebox = gui.tk_modules()
    app = gui.ResearcherApp(MagicMock(), tk, ttk, filedialog, messagebox)
    assert app.status_var is not None
    assert app.public_key_var is not None


def test_on_setup_wires_gui_common(monkeypatch) -> None:
    _stub_tk(monkeypatch)
    tk, ttk, filedialog, messagebox = gui.tk_modules()
    app = gui.ResearcherApp(MagicMock(), tk, ttk, filedialog, messagebox)

    fake_result = SimpleNamespace(
        public_key="age1example",
        config_path=Path("/tmp/config.json"),
        registration_path=None,
    )
    monkeypatch.setattr(gui, "run_researcher_setup", lambda **kwargs: fake_result)

    app.on_setup()
    assert app.public_key_var.set.called
    assert messagebox.showinfo.called


def test_on_setup_reports_errors(monkeypatch) -> None:
    _stub_tk(monkeypatch)
    tk, ttk, filedialog, messagebox = gui.tk_modules()
    app = gui.ResearcherApp(MagicMock(), tk, ttk, filedialog, messagebox)

    from interview_intake.errors import ValidationError

    def boom(**kwargs):
        raise ValidationError("nope")

    monkeypatch.setattr(gui, "run_researcher_setup", boom)
    app.on_setup()
    assert messagebox.showerror.called


def test_researcher_app_builds_with_real_tk() -> None:
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:  # pragma: no cover - headless CI
        pytest.skip("no display available")
    root.withdraw()
    ttk = importlib.import_module("tkinter.ttk")
    filedialog = importlib.import_module("tkinter.filedialog")
    messagebox = importlib.import_module("tkinter.messagebox")
    app = gui.ResearcherApp(root, tk, ttk, filedialog, messagebox)
    root.update()
    assert app is not None
    root.destroy()
