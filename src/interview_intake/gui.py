"""Researcher GUI (standard-library tkinter only).

Importing this module NEVER imports ``tkinter``: Tk is resolved lazily by
:func:`tk_modules` / :func:`_create_root`, so the package stays headless-safe and
importable on machines without Tk.  ``tkinterdnd2`` is an optional drag&drop
enhancement; its absence is harmless.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Optional, Sequence

from .errors import IntakeError
from .fs import expand_path
from .gui_common import GuiUnavailableError, build_registration_request, run_intake, run_researcher_setup, write_public_key_qr


def _import(name: str):
    """Indirection so tests can simulate an unavailable tkinter."""
    return importlib.import_module(name)


def tk_modules():
    """Return ``(tk, ttk, filedialog, messagebox)`` or raise GuiUnavailableError."""
    try:
        tk = _import("tkinter")
        ttk = _import("tkinter.ttk")
        filedialog = _import("tkinter.filedialog")
        messagebox = _import("tkinter.messagebox")
    except Exception as exc:  # pragma: no cover - depends on environment
        raise GuiUnavailableError(
            "Tkinter is not available. Install python3-tk (Linux) or use the CLI."
        ) from exc
    return tk, ttk, filedialog, messagebox


def _create_root(tk, *, prefer_dnd: bool = True):
    """Create a Tk root, using tkinterdnd2 for drag&drop when available."""
    if prefer_dnd:
        try:
            import tkinterdnd2  # noqa: PLC0415

            return tkinterdnd2.TkinterDnD.Tk(), True
        except Exception:
            pass
    return tk.Tk(), False


class ResearcherApp:
    """Researcher workflow: Setup / Intake / Open / Registration."""

    def __init__(self, root, tk, ttk, filedialog, messagebox, *, dnd: bool = False) -> None:
        self.root = root
        self.tk = tk
        self.ttk = ttk
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.dnd = dnd

        self.config_path_var = tk.StringVar()
        self.researcher_id_var = tk.StringVar()
        self.project_path_var = tk.StringVar()
        self.sync_root_var = tk.StringVar()
        self.key_path_var = tk.StringVar()
        self.display_name_var = tk.StringVar()
        self.intake_source_var = tk.StringVar()
        self.mnemonic_var = tk.StringVar()
        self.interview_id_var = tk.StringVar()
        self.output_path_var = tk.StringVar()
        self.public_key_var = tk.StringVar(value="(none yet)")
        self.status_var = tk.StringVar(value="Ready.")

        root.title("Interview Intake — Researcher")
        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True)
        notebook.add(self._build_setup_tab(notebook), text="Setup")
        notebook.add(self._build_intake_tab(notebook), text="Intake")
        notebook.add(self._build_open_tab(notebook), text="Open")
        notebook.add(self._build_registration_tab(notebook), text="Registration")
        ttk.Label(root, textvariable=self.status_var, anchor="w").pack(fill="x")

    # -- helpers ----------------------------------------------------------- #
    def _row(self, parent, label: str, var, browse=None):
        frame = self.ttk.Frame(parent)
        frame.pack(fill="x", padx=8, pady=4)
        self.ttk.Label(frame, text=label, width=16, anchor="w").pack(side="left")
        entry = self.ttk.Entry(frame, textvariable=var)
        entry.pack(side="left", fill="x", expand=True)
        if browse is not None:
            self.ttk.Button(frame, text="…", command=browse).pack(side="left")
        return entry

    def _set_status(self, text: object) -> None:
        self.status_var.set(str(text))

    def _config_path(self) -> Optional[str]:
        value = self.config_path_var.get()
        return value or None

    # -- tabs -------------------------------------------------------------- #
    def _build_setup_tab(self, parent):
        frame = self.ttk.Frame(parent)
        self._row(frame, "Config file", self.config_path_var, self._pick_config_path)
        self._row(frame, "Researcher ID", self.researcher_id_var)
        self._row(frame, "Project path", self.project_path_var, self._pick_project)
        self._row(frame, "Sync root", self.sync_root_var, self._pick_sync_root)
        self._row(frame, "Private key", self.key_path_var, self._pick_key_path)
        self._row(frame, "Display name", self.display_name_var)
        self.ttk.Button(frame, text="Create config & key", command=self.on_setup).pack(
            anchor="w", padx=8, pady=8
        )
        return frame

    def _build_intake_tab(self, parent):
        frame = self.ttk.Frame(parent)
        self._row(frame, "Audio file/folder", self.intake_source_var, self._pick_source)
        self._row(frame, "Mnemonic", self.mnemonic_var)
        self.ttk.Button(frame, text="Run intake", command=self.on_intake).pack(
            anchor="w", padx=8, pady=8
        )
        return frame

    def _build_open_tab(self, parent):
        frame = self.ttk.Frame(parent)
        self._row(frame, "Interview ID", self.interview_id_var)
        self._row(frame, "Output (optional)", self.output_path_var, self._pick_output)
        buttons = self.ttk.Frame(frame)
        buttons.pack(anchor="w", padx=8, pady=8)
        self.ttk.Button(buttons, text="List", command=self.on_list_interviews).pack(
            side="left"
        )
        self.ttk.Button(buttons, text="Decrypt", command=self.on_open).pack(
            side="left", padx=6
        )
        self.interview_list = self.tk.Listbox(frame, height=6)
        self.interview_list.pack(fill="both", expand=True, padx=8, pady=4)
        return frame

    def _build_registration_tab(self, parent):
        frame = self.ttk.Frame(parent)
        self._row(frame, "Public key", self.public_key_var)
        buttons = self.ttk.Frame(frame)
        buttons.pack(anchor="w", padx=8, pady=8)
        self.ttk.Button(buttons, text="Refresh", command=self.on_refresh_registration).pack(
            side="left"
        )
        self.ttk.Button(buttons, text="Export JSON", command=self.on_export_registration).pack(
            side="left", padx=6
        )
        self.ttk.Button(buttons, text="Export QR", command=self.on_export_qr).pack(
            side="left", padx=6
        )
        return frame

    # -- pickers ----------------------------------------------------------- #
    def _pick_config_path(self):
        path = self.filedialog.asksaveasfilename(defaultextension=".json")
        if path:
            self.config_path_var.set(path)

    def _pick_project(self):
        path = self.filedialog.askdirectory()
        if path:
            self.project_path_var.set(path)

    def _pick_sync_root(self):
        path = self.filedialog.askdirectory()
        if path:
            self.sync_root_var.set(path)

    def _pick_key_path(self):
        path = self.filedialog.asksaveasfilename(defaultextension=".key")
        if path:
            self.key_path_var.set(path)

    def _pick_source(self):
        path = self.filedialog.askopenfilename()
        if path:
            self.intake_source_var.set(path)

    def _pick_output(self):
        path = self.filedialog.asksaveasfilename()
        if path:
            self.output_path_var.set(path)

    # -- actions ----------------------------------------------------------- #
    def on_setup(self):
        try:
            result = run_researcher_setup(
                researcher_id=self.researcher_id_var.get(),
                project_path=self.project_path_var.get(),
                sync_root=self.sync_root_var.get(),
                private_key_path=self.key_path_var.get(),
                config_path=self._config_path(),
                display_name=self.display_name_var.get(),
            )
            self.public_key_var.set(result.public_key)
            self._set_status(f"Config written: {result.config_path}")
            message = f"Setup complete.\nPublic key:\n{result.public_key}"
            if result.registration_path:
                message += f"\nRegistration: {result.registration_path}"
            self.messagebox.showinfo("Interview Intake", message)
        except IntakeError as exc:
            self.messagebox.showerror("Interview Intake", str(exc))

    def on_intake(self):
        try:
            result = run_intake(
                self._config_path(),
                self.intake_source_var.get(),
                self.mnemonic_var.get(),
            )
            self._set_status(f"Created {result.interview_id}")
            self.messagebox.showinfo("Interview Intake", f"Created {result.interview_id}")
        except IntakeError as exc:
            self.messagebox.showerror("Interview Intake", str(exc))

    def on_list_interviews(self):
        from .gui_common import list_interviews_for

        try:
            ids = list_interviews_for(self._config_path())
            self.interview_list.delete(0, "end")
            for interview_id in ids:
                self.interview_list.insert("end", interview_id)
            self._set_status(f"{len(ids)} interview(s)")
        except IntakeError as exc:
            self.messagebox.showerror("Interview Intake", str(exc))

    def on_open(self):
        from .gui_common import decrypt_interview

        try:
            path = decrypt_interview(
                self._config_path(),
                self.interview_id_var.get(),
                output=self.output_path_var.get() or None,
                open_file=True,
            )
            self._set_status(f"Decrypted to {path}")
            self.messagebox.showinfo("Interview Intake", f"Decrypted to {path}")
        except IntakeError as exc:
            self.messagebox.showerror("Interview Intake", str(exc))

    def on_refresh_registration(self):
        try:
            request = build_registration_request(self._config_path())
            self.public_key_var.set(request.age_public_key)
            self._set_status("Registration loaded.")
        except IntakeError as exc:
            self.messagebox.showerror("Interview Intake", str(exc))

    def on_export_registration(self):
        from .registration import write_registration

        try:
            request = build_registration_request(self._config_path())
            path = self.filedialog.asksaveasfilename(defaultextension=".json")
            if not path:
                return
            write_registration(expand_path(path), request)
            self._set_status(f"Wrote {path}")
        except IntakeError as exc:
            self.messagebox.showerror("Interview Intake", str(exc))

    def on_export_qr(self):
        try:
            request = build_registration_request(self._config_path())
            path = self.filedialog.asksaveasfilename(defaultextension=".svg")
            if not path:
                return
            write_public_key_qr(request.age_public_key, expand_path(path))
            self._set_status(f"Wrote QR: {path}")
        except IntakeError as exc:
            self.messagebox.showerror("Interview Intake", str(exc))


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        tk, ttk, filedialog, messagebox = tk_modules()
    except GuiUnavailableError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    try:
        root, dnd = _create_root(tk)
    except Exception as exc:  # pragma: no cover - typically no display
        print(f"Cannot start the GUI: {exc}", file=sys.stderr)
        return 1
    ResearcherApp(root, tk, ttk, filedialog, messagebox, dnd=dnd)
    root.mainloop()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
