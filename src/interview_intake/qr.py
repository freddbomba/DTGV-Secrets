"""QR rendering helpers (optional ``qrcode`` dependency).

Terminal and SVG output need only the pure-Python ``qrcode`` package; PNG output
additionally needs Pillow.  Callers should check :func:`qr_available` or handle
:class:`QrUnavailableError`.

Only *public* information should normally be rendered for display.  Rendering a
private/secret key is possible (key backup) but the caller is responsible for
writing it to a private location and warning the user.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Optional

from .errors import IntakeError


class QrUnavailableError(IntakeError):
    """The optional ``qrcode`` package is not installed."""


def qr_available() -> bool:
    """True when the optional ``qrcode`` package can be imported."""
    return importlib.util.find_spec("qrcode") is not None


def _qrcode():
    if not qr_available():
        raise QrUnavailableError(
            "QR rendering needs the optional 'qrcode' package. Install it with: "
            "pip install 'interview-intake[qr]'"
        )
    import qrcode

    return qrcode


def _matrix(text: str) -> list[list[bool]]:
    """Build the QR module matrix for ``text`` (quiet zone included)."""
    qrcode = _qrcode()
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=1,
        border=4,
    )
    qr.add_data(text)
    qr.make(fit=True)
    return qr.get_matrix()


def render_ascii(text: str) -> str:
    """Return a terminal-friendly QR (two characters per module)."""
    matrix = _matrix(text)
    lines = ["".join("██" if cell else "  " for cell in row) for row in matrix]
    return "\n".join(lines) + "\n"


def render_svg(text: str, *, module_size: int = 8) -> str:
    """Return an SVG document for ``text`` using the standard library only.

    ``qrcode`` is still required to compute the matrix; no image library is.
    """
    matrix = _matrix(text)
    dimension = len(matrix) * module_size
    rects = []
    for y, row in enumerate(matrix):
        for x, filled in enumerate(row):
            if filled:
                rects.append(
                    f'<rect x="{x * module_size}" y="{y * module_size}" '
                    f'width="{module_size}" height="{module_size}"/>'
                )
    body = "\n    ".join(rects)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{dimension}" '
        f'height="{dimension}" viewBox="0 0 {dimension} {dimension}">\n'
        f'  <rect width="{dimension}" height="{dimension}" fill="#ffffff"/>\n'
        f'  <g fill="#000000">\n    {body}\n  </g>\n'
        "</svg>\n"
    )


def render_png(text: str, path: Path) -> Path:
    """Write a PNG QR to ``path`` (requires Pillow)."""
    qrcode = _qrcode()
    try:
        import PIL  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on Pillow
        raise QrUnavailableError(
            "PNG QR output needs Pillow. Install it or use SVG output instead."
        ) from exc
    qrcode.make(text).save(str(path))
    return Path(path)


def write_qr(text: str, path: Path, *, fmt: Optional[str] = None) -> Path:
    """Write a QR for ``text`` to ``path``.

    The format is taken from ``fmt`` or the file suffix (``svg``, ``png`` or
    ``txt``/``ascii``); the default is ``svg``.
    """
    path = Path(path)
    suffix = (fmt or path.suffix.lstrip(".") or "svg").lower()
    path.parent.mkdir(parents=True, exist_ok=True)
    if suffix in ("ascii", "txt", "text"):
        path.write_text(render_ascii(text), encoding="utf-8")
    elif suffix == "svg":
        path.write_text(render_svg(text), encoding="utf-8")
    elif suffix == "png":
        render_png(text, path)
    else:
        raise IntakeError(f"Unsupported QR output format: {suffix!r}")
    return path
