"""Intake workflow (spec section 11).

Ingest a single audio file: encrypt it to the researcher + supervisor, write
``meta.json`` and the markdown scaffolds, and confirm the serial was committed.

The plaintext is never written to disk.  If anything after folder creation
fails, the partial ``audio.age`` is removed and a ``FAILED`` marker is left in
the interview folder for the supervisor to reconcile.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from . import __version__
from .allocation import allocate_serial, rfc3339
from .config import key_path_for
from .crypto import CryptoBackend, EncryptionResult, select_backend
from .errors import (
    IntakeError,
    SourceError,
    VerificationError,
)
from .fs import sha256_file, write_json_atomic
from .id_grammar import parse_interview_id, validate_mnemonic
from .models import AudioMeta, Config, Meta
from .registry import (
    get_researcher,
    get_supervisor,
    interview_dir,
    is_issued,
    load_registry,
)
from .templates import render_interview_documents

AUDIO_EXTENSIONS = (".wav", ".mp3", ".m4a", ".flac")
FAILED_MARKER = "FAILED"
AUDIO_FILENAME = "audio.age"

Clock = Callable[[], datetime]


@dataclass
class IntakeResult:
    interview_id: str
    interview_dir: Path
    audio_path: Path
    meta_path: Path
    transcript_path: Path
    note_path: Path
    meta: Meta
    registry_confirmed: bool
    failures: list[str]


def scan_audio_files(path: Path | str) -> list[Path]:
    """Return candidate audio files under ``path`` (file or directory)."""
    root = Path(path).expanduser()
    if root.is_file():
        return [root] if root.suffix.lower() in AUDIO_EXTENSIONS else []
    if not root.is_dir():
        raise SourceError(f"Source path does not exist: {root}")
    found = [
        child
        for child in sorted(root.rglob("*"))
        if child.is_file()
        and child.suffix.lower() in AUDIO_EXTENSIONS
        and not child.name.startswith(".")
    ]
    return found


def infer_duration_seconds(path: Path) -> Optional[float]:
    """Best-effort duration; WAV via stdlib, others via optional ``mutagen``."""
    suffix = Path(path).suffix.lower()
    if suffix == ".wav":
        try:
            import wave

            with wave.open(str(path), "rb") as handle:
                frames = handle.getnframes()
                rate = handle.getframerate()
                if rate:
                    return frames / float(rate)
        except Exception:
            return None
    try:
        from mutagen import File as MutagenFile  # type: ignore

        audio = MutagenFile(str(path))
        if audio is not None and audio.info is not None:
            length = getattr(audio.info, "length", None)
            if length is not None:
                return float(length)
    except Exception:
        return None
    return None


def build_audio_meta(
    source: Path,
    result: EncryptionResult,
) -> AudioMeta:
    return AudioMeta(
        filename=AUDIO_FILENAME,
        original_filename=source.name,
        original_sha256=result.original_sha256,
        encrypted_sha256=result.encrypted_sha256,
        # size_bytes describes the stored encrypted artifact, matching `filename`.
        size_bytes=result.encrypted_size,
        duration_seconds=infer_duration_seconds(source),
        format=source.suffix.lower().lstrip("."),
    )


def _require_source_file(source: Path) -> Path:
    source = Path(source).expanduser()
    if not source.exists():
        raise SourceError(f"Source audio file not found: {source}")
    if not source.is_file():
        raise SourceError(f"Source is not a regular file: {source}")
    if source.suffix.lower() not in AUDIO_EXTENSIONS:
        raise SourceError(
            f"Unsupported audio extension {source.suffix!r}. "
            f"Supported: {', '.join(AUDIO_EXTENSIONS)}."
        )
    return source


def perform_intake(
    project_path: Path | str,
    config: Config,
    source_file: Path | str,
    mnemonic: str,
    *,
    backend: Optional[CryptoBackend] = None,
    clock: Optional[Clock] = None,
    max_retries: int = 5,
    app_version: str = __version__,
    log: Optional[Callable[[str], None]] = None,
) -> IntakeResult:
    """Run the full intake workflow for one audio file."""
    project_path = Path(project_path).expanduser()
    clock = clock or (lambda: datetime.now(timezone.utc))
    source = _require_source_file(Path(source_file))
    mnemonic = validate_mnemonic(mnemonic)

    # 2. Validate the researcher's key path and the registry before touching the SD card.
    key_path_for(config)
    registry = load_registry(project_path)
    researcher = get_researcher(registry, config.researcher_id)
    supervisor = get_supervisor(registry)
    if not researcher.age_public_key:
        raise IntakeError("Researcher public key is missing.")
    recipients = [researcher.age_public_key, supervisor.age_public_key]

    backend = backend or select_backend()

    # 5. Allocate the serial (commits last_serial + issued).
    interview_id = allocate_serial(
        project_path,
        config.researcher_id,
        mnemonic,
        sync_wait_seconds=config.sync_wait_seconds,
        lock_stale_seconds=config.lock_stale_seconds,
        max_retries=max_retries,
        clock=clock,
        log=log,
    )
    parsed = parse_interview_id(interview_id)

    # 6. Create the interview folder (umask-controlled; shared with the team).
    folder = interview_dir(project_path, interview_id)
    folder.mkdir(parents=True, exist_ok=True)

    audio_path = folder / AUDIO_FILENAME
    meta_path = folder / "meta.json"
    transcript_path = folder / "transcript.md"
    note_path = folder / "note.md"

    try:
        # 7. Stream/encrypt the audio (no plaintext to disk).
        result = backend.encrypt_file(source, audio_path, recipients)

        # Verify the encrypted artifact on disk before recording it.
        on_disk = sha256_file(audio_path)
        if on_disk != result.encrypted_sha256:
            raise VerificationError(
                "Encrypted file on disk does not match its computed hash "
                f"(expected {result.encrypted_sha256}, got {on_disk})."
            )

        created_at = rfc3339(clock())
        meta = Meta(
            interview_id=interview_id,
            researcher_id=parsed.researcher_id,
            mnemonic=parsed.mnemonic,
            year=parsed.year,
            serial=parsed.serial,
            audio=build_audio_meta(source, result),
            created_at=created_at,
            app_version=app_version,
        )

        # 8. Write meta.json.
        write_json_atomic(meta_path, meta.to_dict())

        # 9. Scaffold transcript.md and note.md.
        documents = render_interview_documents(
            project_path,
            interview_id=interview_id,
            date=clock().astimezone(timezone.utc).strftime("%Y-%m-%d"),
            researcher_id=parsed.researcher_id,
            mnemonic=parsed.mnemonic,
        )
        (folder / "transcript.md").write_text(documents["transcript.md"], encoding="utf-8")
        (folder / "note.md").write_text(documents["note.md"], encoding="utf-8")
    except BaseException as exc:
        _record_failure(folder, audio_path, exc, clock)
        raise

    # 10. Re-read the registry and confirm the ID is listed.
    failures: list[str] = []
    registry_confirmed = False
    try:
        fresh = load_registry(project_path)
        registry_confirmed = is_issued(fresh, interview_id)
    except IntakeError as exc:  # pragma: no cover - defensive
        failures.append(str(exc))
    if not registry_confirmed:
        message = (
            f"Interview {interview_id} was not found in registry.json after intake. "
            "The registry write may not have synced; re-check the shared folder."
        )
        failures.append(message)
        if log is not None:
            log("WARNING: " + message)

    return IntakeResult(
        interview_id=interview_id,
        interview_dir=folder,
        audio_path=audio_path,
        meta_path=meta_path,
        transcript_path=transcript_path,
        note_path=note_path,
        meta=meta,
        registry_confirmed=registry_confirmed,
        failures=failures,
    )


def _record_failure(
    folder: Path,
    audio_path: Path,
    exc: BaseException,
    clock: Clock,
) -> None:
    """Remove a partial ``audio.age`` and drop a FAILED marker."""
    try:
        if audio_path.exists():
            audio_path.unlink()
    except OSError:
        pass
    marker = folder / FAILED_MARKER
    payload = {
        "status": "FAILED",
        "error_type": type(exc).__name__,
        "error": str(exc),
        "failed_at": rfc3339(clock()),
    }
    try:
        marker.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass
