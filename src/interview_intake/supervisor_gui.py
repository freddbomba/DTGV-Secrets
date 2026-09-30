"""Supervisor GUI (standard-library tkinter only).

Importing this module NEVER imports ``tkinter``: Tk is resolved lazily by
:func:`tk_modules`, so the package stays headless-safe.  This is the UI layer of
the Supervisor App, which owns ``registry.json`` (the researcher side never
creates it).
"""

from __future__ import annotations

import importlib
import sys
from typing import Optional, Sequence

from .errors import IntakeError
from .fs import expand_path
from .gui_common import GuiUnavailableError
from .registration import read_registration
from .supervisor import (
    add_researcher,
    add_researcher_from_registration,
    backup_escrow,
    default_escrow_key_path,
    escrow_info,
    init_project,
    list_researchers,
    remove_researcher,
    set_researcher_active,
    verify_supervisor,
)


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


def format_verify(report) -> str:
    """Render a :class:`SupervisorVerifyReport` as plain text."""
    lines = [f"warning: {warning}" for warning in report.base.warnings]
    lines += [f"warning: {warning}" for warning in report.warnings]
    lines += [f"error: {error}" for error in report.base.errors]
    lines += [f"error: {error}" for error in report.errors]
    status = "OK" if report.ok else "FAILED"
    lines.append(f"Checked {report.base.checked} issued interview(s): {status}")
    return "\n".join(lines)


class SupervisorApp:
    """Supervisor workflow: Init / Researchers / Escrow / Verify."""

    def __init__(self, root, tk, ttk, filedialog, messagebox) -> None:
        self.root = root
        self.tk = tk
        self.ttk = ttk
        self.filedialog = filedialog
        self.messagebox = messagebox

        self.project_var = tk.StringVar()
        self.escrow_key_var = tk.StringVar(value=str(default_escrow_key_path()))
        self.create_escrow_var = tk.IntVar(value=1)
        self.install_templates_var = tk.IntVar(value=1)
        self.researcher_id_var = tk.StringVar()
        self.display_name_var = tk.StringVar()
        self.public_key_var = tk.StringVar()
        self.registration_file_var = tk.StringVar()
        self.escrow_public_var = tk.StringVar(value="(none yet)")
        self.status_var = tk.StringVar(value="Ready.")

        root.title("Interview Supervisor")
        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True)
        notebook.add(self._build_init_tab(notebook), text="Init")
        notebook.add(self._build_researchers_tab(notebook), text="Researchers")
        notebook.add(self._build_escrow_tab(notebook), text="Escrow")
        notebook.add(self._build_verify_tab(notebook), text="Verify")
        ttk.Label(root, textvariable=self.status_var, anchor="w").pack(fill="x")

    # -- helpers ----------------------------------------------------------- #
    def _row(self, parent, label: str, var, browse=None):
        frame = self.ttk.Frame(parent)
        frame.pack(fill="x", padx=8, pady=4)
        self.ttk.Label(frame, text=label, width=18, anchor="w").pack(side="left")
        entry = self.ttk.Entry(frame, textvariable=var)
        entry.pack(side="left", fill="x", expand=True)
        if browse is not None:
            self.ttk.Button(frame, text="…", command=browse).pack(side="left")
        return entry

    def _set_status(self, text: object) -> None:
        self.status_var.set(str(text))

    def _project(self) -> str:
        value = self.project_var.get()
        return value

    # -- tabs -------------------------------------------------------------- #
    def _build_init_tab(self, parent):
        frame = self.ttk.Frame(parent)
        self._row(frame, "Project folder", self.project_var, self._pick_project)
        self._row(frame, "Escrow key", self.escrow_key_var, self._pick_escrow_key)
        self.ttk.Checkbutton(
            frame, text="Create escrow key", variable=self.create_escrow_var
        ).pack(anchor="w", padx=8)
        self.ttk.Checkbutton(
            frame, text="Install default templates", variable=self.install_templates_var
        ).pack(anchor="w", padx=8)
        self.ttk.Button(frame, text="Initialise project", command=self.on_init).pack(
            anchor="w", padx=8, pady=8
        )
        return frame

    def _build_researchers_tab(self, parent):
        frame = self.ttk.Frame(parent)
        self._row(frame, "Researcher ID", self.researcher_id_var)
        self._row(frame, "Display name", self.display_name_var)
        self._row(frame, "Public key", self.public_key_var)
        self._row(frame, "Registration file", self.registration_file_var, self._pick_registration)
        buttons = self.ttk.Frame(frame)
        buttons.pack(anchor="w", padx=8, pady=8)
        self.ttk.Button(buttons, text="Add", command=self.on_add_researcher).pack(side="left")
        self.ttk.Button(buttons, text="Activate", command=self.on_activate).pack(side="left", padx=6)
        self.ttk.Button(buttons, text="Deactivate", command=self.on_deactivate).pack(side="left", padx=6)
        self.ttk.Button(buttons, text="Remove", command=self.on_remove).pack(side="left", padx=6)
        self.ttk.Button(buttons, text="Refresh", command=self.on_refresh_researchers).pack(
            side="left", padx=6
        )
        self.researcher_list = self.tk.Listbox(frame, height=8)
        self.researcher_list.pack(fill="both", expand=True, padx=8, pady=4)
        return frame

    def _build_escrow_tab(self, parent):
        frame = self.ttk.Frame(parent)
        self._row(frame, "Escrow key", self.escrow_key_var)
        self._row(frame, "Public key", self.escrow_public_var)
        buttons = self.ttk.Frame(frame)
        buttons.pack(anchor="w", padx=8, pady=8)
        self.ttk.Button(buttons, text="Show public key", command=self.on_show_escrow).pack(side="left")
        self.ttk.Button(buttons, text="Backup (key + QR)", command=self.on_backup_escrow).pack(
            side="left", padx=6
        )
        return frame

    def _build_verify_tab(self, parent):
        frame = self.ttk.Frame(parent)
        self.ttk.Button(frame, text="Verify project", command=self.on_verify).pack(
            anchor="w", padx=8, pady=8
        )
        self.verify_text = self.tk.Text(frame, height=12)
        self.verify_text.pack(fill="both", expand=True, padx=8, pady=4)
        return frame

    # -- pickers ----------------------------------------------------------- #
    def _pick_project(self):
        path = self.filedialog.askdirectory()
        if path:
            self.project_var.set(path)

    def _pick_escrow_key(self):
        path = self.filedialog.asksaveasfilename(defaultextension=".key")
        if path:
            self.escrow_key_var.set(path)

    def _pick_registration(self):
        path = self.filedialog.askopenfilename(filetypes=[("Registration", "*.json")])
        if path:
            self.registration_file_var.set(path)

    # -- actions ----------------------------------------------------------- #
    def on_init(self):
        try:
            result = init_project(
                self._project(),
                escrow_key_path=self.escrow_key_var.get() or None,
                create_escrow=bool(self.create_escrow_var.get()),
                install_templates=bool(self.install_templates_var.get()),
            )
            self._set_status(f"Registry: {result.registry_file}")
            message = f"Project initialised.\nRegistry: {result.registry_file}"
            if result.supervisor_public_key:
                message += f"\nEscrow public key:\n{result.supervisor_public_key}"
            self.messagebox.showinfo("Interview Supervisor", message)
        except IntakeError as exc:
            self.messagebox.showerror("Interview Supervisor", str(exc))

    def on_add_researcher(self):
        try:
            registration = self.registration_file_var.get()
            if registration:
                request = read_registration(expand_path(registration))
                entry = add_researcher_from_registration(self._project(), request)
            else:
                entry = add_researcher(
                    self._project(),
                    self.researcher_id_var.get(),
                    self.display_name_var.get(),
                    self.public_key_var.get(),
                )
            self._set_status(f"Registered {entry.display_name}")
            self.on_refresh_researchers()
        except IntakeError as exc:
            self.messagebox.showerror("Interview Supervisor", str(exc))

    def on_activate(self):
        self._set_active(True)

    def on_deactivate(self):
        self._set_active(False)

    def _set_active(self, active: bool) -> None:
        try:
            set_researcher_active(self._project(), self.researcher_id_var.get(), active)
            self.on_refresh_researchers()
        except IntakeError as exc:
            self.messagebox.showerror("Interview Supervisor", str(exc))

    def on_remove(self):
        try:
            remove_researcher(self._project(), self.researcher_id_var.get())
            self.on_refresh_researchers()
        except IntakeError as exc:
            self.messagebox.showerror("Interview Supervisor", str(exc))

    def on_refresh_researchers(self):
        try:
            rows = list_researchers(self._project())
            self.researcher_list.delete(0, "end")
            for row in rows:
                status = "active" if row.active else "inactive"
                self.researcher_list.insert(
                    "end", f"{row.researcher_id}  {row.display_name}  {status}  ({row.issued})"
                )
            self._set_status(f"{len(rows)} researcher(s)")
        except IntakeError as exc:
            self.messagebox.showerror("Interview Supervisor", str(exc))

    def on_show_escrow(self):
        try:
            info = escrow_info(self.escrow_key_var.get() or None)
            self.escrow_public_var.set(info.public_key)
            self._set_status(f"Escrow key: {info.key_path}")
        except IntakeError as exc:
            self.messagebox.showerror("Interview Supervisor", str(exc))

    def on_backup_escrow(self):
        try:
            directory = self.filedialog.askdirectory()
            if not directory:
                return
            result = backup_escrow(
                self.escrow_key_var.get() or None, expand_path(directory)
            )
            self._set_status(f"Backup written to {result.directory}")
            self.messagebox.showinfo(
                "Interview Supervisor",
                f"Backup written to:\n{result.directory}\n\n"
                "Keep the secret-key QR offline and never on researcher machines.",
            )
        except IntakeError as exc:
            self.messagebox.showerror("Interview Supervisor", str(exc))

    def on_verify(self):
        try:
            report = verify_supervisor(self._project())
            text = format_verify(report)
            self.verify_text.delete("1.0", "end")
            self.verify_text.insert("1.0", text)
            self._set_status("Verify OK" if report.ok else "Verify FAILED")
        except IntakeError as exc:
            self.messagebox.showerror("Interview Supervisor", str(exc))


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        tk, ttk, filedialog, messagebox = tk_modules()
    except GuiUnavailableError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    try:
        root = tk.Tk()
    except Exception as exc:  # pragma: no cover - typically no display
        print(f"Cannot start the GUI: {exc}", file=sys.stderr)
        return 1
    SupervisorApp(root, tk, ttk, filedialog, messagebox)
    root.mainloop()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
