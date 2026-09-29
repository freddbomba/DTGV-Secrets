"""Interview Intake App.

Ingests interview audio from an SD card, encrypts it with ``age`` (X25519 +
ChaCha20-Poly1305), and files it under a globally unique, sequentially numbered
interview ID inside a shared Nextcloud project folder.  It also scaffolds the
``transcript.md`` / ``note.md`` files the researcher fills in later.

The package deliberately does **not** transcribe, read the supervisor masterfile,
manage identity mapping, or sync Nextcloud.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
