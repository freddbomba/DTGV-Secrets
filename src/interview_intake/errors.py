"""Exception hierarchy for the interview-intake app.

Every error raised intentionally by the app derives from :class:`IntakeError`
so the CLI can present a clean message instead of a traceback.
"""

from __future__ import annotations


class IntakeError(Exception):
    """Base class for all expected application errors."""


class ConfigError(IntakeError):
    """Configuration file missing, malformed, or internally inconsistent."""


class RegistryError(IntakeError):
    """``registry.json`` is missing, malformed, or inconsistent."""


class SchemaVersionError(RegistryError):
    """A persisted document carries an unsupported ``schema_version``."""


class ValidationError(IntakeError):
    """A user-supplied value failed validation (mnemonic, ID, path, ...)."""


class AllocationError(IntakeError):
    """Serial allocation could not complete."""


class SerialExhaustedError(AllocationError):
    """The 4-digit global serial space (0000-9999) is exhausted."""


class CryptoError(IntakeError):
    """Encryption/decryption failed or no usable age backend is available."""


class SyncRootError(IntakeError):
    """An operation would write plaintext inside the Nextcloud sync root."""


class TemplateError(IntakeError):
    """Interview templates are missing or malformed."""


class SourceError(IntakeError):
    """A source audio file / SD card could not be read."""


class VerificationError(IntakeError):
    """A post-write integrity check failed."""
