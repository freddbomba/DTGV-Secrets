"""age encryption/decryption backends (spec section 9).

Two backends are provided:

* :class:`PyrageBackend` -- preferred, Rust-backed, whole-file in memory.  The
  plaintext buffer is a ``bytearray`` and is zeroed after use; no plaintext is
  ever written to disk.
* :class:`AgeCliBackend` -- fallback that streams the source through the ``age``
  CLI via stdin (single pass, hashed while streaming).

Both return the SHA-256 of the original plaintext and of the encrypted output.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, Sequence

from .errors import CryptoError
from .fs import ensure_private_file, sha256_file

_CHUNK = 1024 * 1024
AGE_SECRET_PREFIX = "AGE-SECRET-KEY-1"


@dataclass(frozen=True)
class EncryptionResult:
    original_sha256: str
    encrypted_sha256: str
    encrypted_size: int


class CryptoBackend(Protocol):
    name: str

    def encrypt_file(
        self, src: Path, dst: Path, recipients: Sequence[str]
    ) -> EncryptionResult: ...

    def decrypt_file(self, src: Path, dst: Path, identity_path: Path) -> None: ...


def _read_identity(path: Path) -> str:
    """Extract the secret key line from an age identity file."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise CryptoError(f"Cannot read identity file {path}: {exc}") from exc
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    raise CryptoError(f"No identity found in {path}.")


def read_identity(path: Path) -> str:
    """Public wrapper around the identity-file reader (used by backup tooling)."""
    return _read_identity(path)


def validate_recipient(recipient: str) -> str:
    """Validate and normalise an age X25519 public key (recipient).

    Always checks the structural prefix.  When ``pyrage`` is available the key is
    additionally parsed, which catches typos before they reach the registry.
    """
    value = str(recipient or "").strip()
    if not value:
        raise CryptoError("Empty age recipient.")
    if not value.startswith("age1") or len(value) < 16:
        raise CryptoError(f"Not a valid age X25519 recipient: {value!r}")
    if importlib.util.find_spec("pyrage") is not None:
        import pyrage

        try:
            pyrage.x25519.Recipient.from_str(value)
        except Exception as exc:
            raise CryptoError(f"Invalid age recipient {value!r}: {exc}") from exc
    return value


def public_key_for_identity_file(path: Path) -> str:
    """Derive the age recipient (public key) for an existing identity file.

    Lets the app be idempotent: if a key already exists we report its public key
    instead of overwriting it.  Uses pyrage when available, else ``age-keygen -y``.
    """
    path = Path(path)
    if not path.exists():
        raise CryptoError(f"Identity file not found: {path}")
    if importlib.util.find_spec("pyrage") is not None:
        import pyrage

        identity = _read_identity(path)
        try:
            return str(pyrage.x25519.Identity.from_str(identity).to_public())
        except Exception as exc:
            raise CryptoError(f"Could not parse identity {path}: {exc}") from exc
    binary = shutil.which("age-keygen")
    if binary is None:
        raise CryptoError("Cannot derive the public key: install pyrage or age-keygen.")
    proc = subprocess.run([binary, "-y", str(path)], capture_output=True)
    if proc.returncode != 0:
        raise CryptoError(
            f"age-keygen -y failed: {proc.stderr.decode(errors='replace').strip()}"
        )
    return proc.stdout.decode().strip()


def _write_all_atomic(dst: Path, data: bytes) -> None:
    """Write ciphertext/plaintext to ``dst`` via a same-dir temp + replace."""
    import tempfile

    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{dst.name}.", suffix=".tmp", dir=str(dst.parent)
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, dst)
    except BaseException:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


class PyrageBackend:
    """Preferred backend using the ``pyrage`` Rust binding."""

    name = "pyrage"

    def __init__(self) -> None:
        if importlib.util.find_spec("pyrage") is None:  # pragma: no cover
            raise CryptoError(
                "pyrage is not installed. Install `pyrage` or use the age CLI backend."
            )

    @staticmethod
    def _pyrage():
        import pyrage

        return pyrage

    def encrypt_file(
        self, src: Path, dst: Path, recipients: Sequence[str]
    ) -> EncryptionResult:
        if not recipients:
            raise CryptoError("At least one recipient is required.")
        pyrage = self._pyrage()
        try:
            parsed = [pyrage.x25519.Recipient.from_str(r) for r in recipients]
        except Exception as exc:
            raise CryptoError(f"Invalid age recipient: {exc}") from exc

        buffer = bytearray()
        digest = hashlib.sha256()
        with Path(src).open("rb") as handle:
            for chunk in iter(lambda: handle.read(_CHUNK), b""):
                digest.update(chunk)
                buffer.extend(chunk)
        original_sha256 = digest.hexdigest()

        try:
            encrypted = pyrage.encrypt(bytes(buffer), parsed)
        except Exception as exc:
            raise CryptoError(f"age encryption failed: {exc}") from exc
        finally:
            _zero(buffer)

        _write_all_atomic(dst, encrypted)
        encrypted_sha256 = hashlib.sha256(encrypted).hexdigest()
        return EncryptionResult(
            original_sha256=original_sha256,
            encrypted_sha256=encrypted_sha256,
            encrypted_size=len(encrypted),
        )

    def decrypt_file(self, src: Path, dst: Path, identity_path: Path) -> None:
        pyrage = self._pyrage()
        identity_str = _read_identity(identity_path)
        try:
            identity = pyrage.x25519.Identity.from_str(identity_str)
        except Exception as exc:
            raise CryptoError(f"Invalid age identity: {exc}") from exc

        try:
            ciphertext = Path(src).read_bytes()
        except OSError as exc:
            raise CryptoError(f"Cannot read {src}: {exc}") from exc
        try:
            plaintext = pyrage.decrypt(ciphertext, [identity])
        except Exception as exc:
            raise CryptoError(f"age decryption failed: {exc}") from exc

        buffer = bytearray(plaintext)
        del plaintext
        try:
            _write_all_atomic(dst, bytes(buffer))
        finally:
            _zero(buffer)
        ensure_private_file(dst)


class AgeCliBackend:
    """Fallback backend shelling out to the ``age`` binary.

    Encryption streams the source through stdin in one pass, hashing as it goes,
    so no plaintext temporary file is created.
    """

    name = "age-cli"

    def __init__(self, binary: Optional[str] = None) -> None:
        self.binary = binary or shutil.which("age") or "age"
        if shutil.which(self.binary) is None:
            raise CryptoError(
                "The `age` CLI was not found on PATH. Install age or pyrage."
            )

    def encrypt_file(
        self, src: Path, dst: Path, recipients: Sequence[str]
    ) -> EncryptionResult:
        if not recipients:
            raise CryptoError("At least one recipient is required.")
        dst = Path(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        args = [self.binary, "--output", str(dst)]
        for recipient in recipients:
            args += ["--recipient", recipient]
        digest = hashlib.sha256()
        try:
            proc = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            assert proc.stdin is not None
            with Path(src).open("rb") as handle:
                for chunk in iter(lambda: handle.read(_CHUNK), b""):
                    digest.update(chunk)
                    proc.stdin.write(chunk)
            proc.stdin.close()
            stderr = proc.stderr.read() if proc.stderr else b""
            returncode = proc.wait()
        except OSError as exc:
            raise CryptoError(f"Failed to run age: {exc}") from exc
        if returncode != 0:
            raise CryptoError(
                f"age encryption failed (exit {returncode}): "
                f"{stderr.decode(errors='replace').strip()}"
            )
        return EncryptionResult(
            original_sha256=digest.hexdigest(),
            encrypted_sha256=sha256_file(dst),
            encrypted_size=dst.stat().st_size,
        )

    def decrypt_file(self, src: Path, dst: Path, identity_path: Path) -> None:
        dst = Path(dst)
        if dst.exists():
            raise CryptoError(f"Refusing to overwrite existing file: {dst}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        args = [
            self.binary,
            "--decrypt",
            "--identity",
            str(identity_path),
            "--output",
            str(dst),
            str(src),
        ]
        try:
            proc = subprocess.run(args, capture_output=True)
        except OSError as exc:
            raise CryptoError(f"Failed to run age: {exc}") from exc
        if proc.returncode != 0:
            raise CryptoError(
                f"age decryption failed (exit {proc.returncode}): "
                f"{proc.stderr.decode(errors='replace').strip()}"
            )
        ensure_private_file(dst)


def _zero(buffer: bytearray) -> None:
    """Zero a mutable buffer in place."""
    for i in range(len(buffer)):
        buffer[i] = 0


def available_backends() -> list[str]:
    found = []
    if importlib.util.find_spec("pyrage") is not None:
        found.append("pyrage")
    if shutil.which("age"):
        found.append("age-cli")
    return found


def select_backend(prefer: str = "auto") -> CryptoBackend:
    """Return a backend, honouring an explicit preference."""
    prefer = (prefer or "auto").lower()
    if prefer in ("pyrage",):
        return PyrageBackend()
    if prefer in ("cli", "age-cli", "age"):
        return AgeCliBackend()
    if prefer != "auto":
        raise CryptoError(f"Unknown crypto backend preference: {prefer!r}")

    try:
        return PyrageBackend()
    except CryptoError:
        pass
    try:
        return AgeCliBackend()
    except CryptoError as exc:
        raise CryptoError(
            "No age backend available. Install the `pyrage` Python package or "
            "the `age` CLI."
        ) from exc


def generate_keypair() -> tuple[str, str]:
    """Generate an age X25519 keypair, returning ``(identity, recipient)``.

    Enables the ``keygen`` helper.  Uses pyrage when importable and falls back
    to the ``age-keygen`` CLI.
    """
    if importlib.util.find_spec("pyrage") is not None:
        import pyrage

        identity = pyrage.x25519.Identity.generate()
        return str(identity), str(identity.to_public())

    binary = shutil.which("age-keygen")
    if binary is None:
        raise CryptoError(
            "Cannot generate a keypair: install pyrage or the age-keygen CLI."
        )
    proc = subprocess.run([binary], capture_output=True)
    if proc.returncode != 0:
        raise CryptoError(
            f"age-keygen failed: {proc.stderr.decode(errors='replace').strip()}"
        )
    identity = ""
    recipient = ""
    for line in proc.stdout.decode().splitlines():
        line = line.strip()
        if line.startswith("# public key:"):
            recipient = line.split(":", 1)[1].strip()
        elif line and not line.startswith("#"):
            identity = line
    if not identity or not recipient:
        raise CryptoError("age-keygen produced unexpected output.")
    return identity, recipient


def write_identity_file(identity: str, path: Path) -> Path:
    """Write an age identity to ``path`` with mode 0600."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(str(path), flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("# created by interview-intake\n")
            handle.write(identity.strip() + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        ensure_private_file(path)
    return path
