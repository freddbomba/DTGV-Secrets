"""Regenerate the per-role app icons from the lab source art.

The source of truth is ``packaging/icons/icon-orange.png`` (with the matching
``icon-orange.svg`` kept for reference).  This script derives:

* ``interview-intake.png`` / ``interview-supervisor.png`` - 256x256 PNGs used
  by the Linux ``.desktop`` launchers, the AppImage and the ``.deb``;
* ``interview-intake.icns`` / ``interview-supervisor.icns`` - multi-resolution
  ICNS files used by the macOS ``.app`` bundle.

Usage::

    python -m pip install pillow        # one-time, authoring only
    python packaging/make_icons.py      # (re)generate all derived icons

The generated files are committed, so building the apps does not need Pillow.
"""

from __future__ import annotations

import argparse
import io
import struct
from pathlib import Path

ICONS_DIR = Path(__file__).resolve().parent / "icons"
SOURCE = ICONS_DIR / "icon-orange.png"
ROLES = ("interview-intake", "interview-supervisor")
PNG_SIZE = 256

# ICNS entry type -> square pixel size.  Modern macOS accepts PNG payloads.
_ICNS_TYPES = (
    (b"icp4", 16),
    (b"icp5", 32),
    (b"icp6", 64),
    (b"ic07", 128),
    (b"ic08", 256),
    (b"ic09", 512),
    (b"ic10", 1024),
    (b"ic11", 32),
    (b"ic12", 64),
    (b"ic13", 256),
    (b"ic14", 512),
)


def _load_source():
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - authoring tool
        raise SystemExit(
            "Pillow is required to (re)generate icons: python -m pip install pillow"
        ) from exc
    return Image.open(SOURCE).convert("RGBA")


def _png_bytes(image, size: int) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    image.resize((size, size), Image.LANCZOS).save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _icns_bytes(image) -> bytes:
    cache: dict[int, bytes] = {}
    entries = []
    for type_code, size in _ICNS_TYPES:
        if size not in cache:
            cache[size] = _png_bytes(image, size)
        payload = cache[size]
        entries.append(type_code + struct.pack(">I", len(payload) + 8) + payload)
    body = b"".join(entries)
    return b"icns" + struct.pack(">I", len(body) + 8) + body


def _targets(image) -> dict[Path, bytes]:
    targets: dict[Path, bytes] = {}
    for role in ROLES:
        targets[ICONS_DIR / f"{role}.png"] = _png_bytes(image, PNG_SIZE)
        targets[ICONS_DIR / f"{role}.icns"] = _icns_bytes(image)
    return targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    if not SOURCE.is_file():
        raise SystemExit(f"missing source icon: {SOURCE}")

    for path, data in _targets(_load_source()).items():
        path.write_bytes(data)
        print(f"wrote {path.relative_to(ICONS_DIR.parent.parent)} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
