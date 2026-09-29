"""Optional drag-and-drop GUI.

Tkinter's stock widgets cannot receive OS drag-and-drop events; that requires the
third-party ``tkinterdnd2`` package.  This module is therefore defensive: if
Tkinter or ``tkinterdnd2`` is unavailable it prints an explanation and exits,
and the CLI remains the supported path.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Sequence

from .errors import IntakeError


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        import tkinter as tk
        from tkinter import messagebox, simpledialog
    except Exception:  # pragma: no cover - depends on Tk availability
        _explain("Tkinter is not installed.")
        return 1

    try:
        from tkinterdnd2 import DND_FILES, TkinterDnD
    except Exception:  # pragma: no cover - optional dependency
        _explain("The optional 'tkinterdnd2' package is not installed.")
        return 1

    # Imports deferred so the core never depends on Tk.
    from .config import expand_path, load_config  # noqa: PLC0415
    from .intake import perform_intake  # noqa: PLC0415

    root = TkinterDnD.Tk()
    root.title("Interview Intake")
    root.geometry("560x320")

    state: dict[str, object] = {"path": None}

    label = tk.Label(
        root,
        text="Drag an audio file (or SD-card folder) here",
        width=60,
        height=8,
        relief="groove",
    )
    label.pack(padx=20, pady=20, fill="both", expand=True)

    status = tk.Label(root, text="", anchor="w", justify="left")
    status.pack(padx=20, pady=(0, 10), fill="x")

    def on_drop(event) -> None:  # pragma: no cover - GUI path
        paths = root.tk.splitlist(event.data)
        if paths:
            state["path"] = paths[0]
            status.config(text=f"Selected: {paths[0]}")

    label.drop_target_register(DND_FILES)
    label.dnd_bind("<<Drop>>", on_drop)

    def run_intake() -> None:  # pragma: no cover - GUI path
        path = state.get("path")
        if not path:
            messagebox.showwarning("Interview Intake", "Drop an audio file first.")
            return
        try:
            config, _ = load_config()
            mnemonic = simpledialog.askstring("Mnemonic", "Three-letter mnemonic:")
            if not mnemonic:
                return
            result = perform_intake(
                expand_path(config.project_path), config, Path(str(path)), mnemonic
            )
            messagebox.showinfo(
                "Interview Intake", f"Created {result.interview_id}"
            )
            status.config(text=f"Created {result.interview_id}")
        except IntakeError as exc:
            messagebox.showerror("Interview Intake", str(exc))

    button = tk.Button(root, text="Intake…", command=run_intake)
    button.pack(pady=(0, 20))

    root.mainloop()
    return 0


def _explain(reason: str) -> None:
    print(
        f"{reason}\n"
        "Drag-and-drop is optional. Use the CLI instead, e.g.:\n"
        "  interview-intake intake /media/SDCARD/REC_0042.wav -m xyz\n"
        "See the README for details.",
        file=sys.stderr,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
