"""Smoke tests for the supervisor GUI (stubbed Tk + real Tk when available)."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import interview_intake.supervisor_gui as supervisor_gui
from interview_intake.errors import ValidationError
from interview_intake.gui_common import GuiUnavailableError


def _stub_tk(monkeypatch):
    for name in ("tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.messagebox"):
        monkeypatch.setitem(sys.modules, name, MagicMock(name=name))


def test_supervisor_gui_imports_without_tkinter() -> None:
    code = (
        "import sys; import interview_intake.supervisor_gui as g; "
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

    monkeypatch.setattr(supervisor_gui, "_import", boom)
    with pytest.raises(GuiUnavailableError):
        supervisor_gui.tk_modules()


def test_supervisor_app_builds_with_stubbed_tk(monkeypatch) -> None:
    _stub_tk(monkeypatch)
    tk, ttk, filedialog, messagebox = supervisor_gui.tk_modules()
    app = supervisor_gui.SupervisorApp(MagicMock(), tk, ttk, filedialog, messagebox)
    assert app.status_var is not None
    assert app.escrow_public_var is not None


def test_on_init_wires_supervisor(monkeypatch) -> None:
    _stub_tk(monkeypatch)
    tk, ttk, filedialog, messagebox = supervisor_gui.tk_modules()
    app = supervisor_gui.SupervisorApp(MagicMock(), tk, ttk, filedialog, messagebox)

    fake = SimpleNamespace(
        registry_file=Path("/tmp/registry.json"),
        supervisor_public_key="age1example",
    )
    monkeypatch.setattr(supervisor_gui, "init_project", lambda *a, **k: fake)
    app.on_init()
    assert messagebox.showinfo.called


def test_on_add_reports_errors(monkeypatch) -> None:
    _stub_tk(monkeypatch)
    tk, ttk, filedialog, messagebox = supervisor_gui.tk_modules()
    app = supervisor_gui.SupervisorApp(MagicMock(), tk, ttk, filedialog, messagebox)

    def boom(*args, **kwargs):
        raise ValidationError("nope")

    monkeypatch.setattr(supervisor_gui, "add_researcher", boom)
    app.on_add_researcher()
    assert messagebox.showerror.called


def test_format_verify() -> None:
    report = SimpleNamespace(
        base=SimpleNamespace(warnings=["w1"], errors=["e0"], checked=2),
        warnings=["w2"],
        errors=["e1"],
        ok=False,
    )
    text = supervisor_gui.format_verify(report)
    assert "warning: w1" in text
    assert "warning: w2" in text
    assert "error: e0" in text
    assert "error: e1" in text
    assert text.endswith("FAILED")


def test_supervisor_app_builds_with_real_tk() -> None:
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:  # pragma: no cover - headless CI
        pytest.skip("no display available")
    root.withdraw()
    ttk = importlib.import_module("tkinter.ttk")
    filedialog = importlib.import_module("tkinter.filedialog")
    messagebox = importlib.import_module("tkinter.messagebox")
    app = supervisor_gui.SupervisorApp(root, tk, ttk, filedialog, messagebox)
    root.update()
    assert app is not None
    root.destroy()
