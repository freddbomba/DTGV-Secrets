"""Reserve-then-commit serial allocation (spec section 10).

The lock file is *advisory*.  Correctness comes from re-reading the registry
after the sync wait and confirming our ``tx_id`` is still the one on disk.  The
function is deliberately time- and sleep-injectable so concurrency can be
tested deterministically.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .errors import AllocationError, SerialExhaustedError
from .fs import read_json, write_json_atomic
from .id_grammar import build_interview_id
from .registry import load_registry, lock_path, save_registry

Clock = Callable[[], datetime]
Sleeper = Callable[[float], None]
UuidFactory = Callable[[], str]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def rfc3339(dt: datetime) -> str:
    """Format an aware datetime as ``...Z`` (matching issued_at/created_at)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_rfc3339(value: str) -> Optional[datetime]:
    try:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None


def _load_lock(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        data = read_json(path)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def clear_stale_lock(
    project_path: Path | str,
    lock_stale_seconds: int,
    now: datetime,
    *,
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    """Remove ``registry.lock`` if older than ``lock_stale_seconds``.

    Returns True if a stale lock was removed.  Uses ``created_at`` when it parses
    and falls back to the file mtime otherwise.
    """
    path = lock_path(project_path)
    if not path.exists():
        return False

    lock = _load_lock(path)
    created = parse_rfc3339(lock.get("created_at", "")) if lock else None
    if created is None:
        try:
            created = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            return False

    age = (now - created).total_seconds()
    if age <= lock_stale_seconds:
        return False

    try:
        path.unlink()
    except FileNotFoundError:
        return False
    if log is not None:
        log(f"Removed stale lock ({age:.0f}s old): {path}")
    return True


def allocate_serial(
    project_path: Path | str,
    researcher_id: str,
    mnemonic: str,
    *,
    sync_wait_seconds: int = 3,
    lock_stale_seconds: int = 60,
    max_retries: int = 5,
    clock: Optional[Clock] = None,
    sleeper: Optional[Sleeper] = None,
    uuid_factory: Optional[UuidFactory] = None,
    log: Optional[Callable[[str], None]] = None,
) -> str:
    """Allocate the next global serial and return the interview ID.

    Implements the reserve-then-commit algorithm from spec section 10 verbatim.
    """
    clock = clock or _utcnow
    sleeper = sleeper or time.sleep
    uuid_factory = uuid_factory or (lambda: str(uuid.uuid4()))
    lock_file = lock_path(project_path)

    for attempt in range(1, max_retries + 1):
        now = clock()
        clear_stale_lock(project_path, lock_stale_seconds, now, log=log)

        # 1. Read current registry (validates schema_version).
        reg = load_registry(project_path)
        proposed = reg.last_serial + 1
        if proposed > 9999:
            raise SerialExhaustedError(
                "Global serial exhausted (>9999). Manual intervention required; "
                "the ID grammar would need a schema_version bump."
            )

        tx_id = uuid_factory()
        lock = {
            "tx_id": tx_id,
            "researcher_id": researcher_id,
            "proposed_serial": proposed,
            "created_at": rfc3339(now),
        }

        # 2. Write reservation file (atomic).
        write_json_atomic(lock_file, lock)

        # 3. Wait for sync to propagate.
        if sync_wait_seconds > 0:
            sleeper(sync_wait_seconds)

        # 4. Re-read registry.
        reg2 = load_registry(project_path)

        # 5. Conflict: someone else committed. Retry.
        if reg2.last_serial != reg.last_serial:
            if log is not None:
                log(
                    f"Allocation attempt {attempt}: registry advanced "
                    f"{reg.last_serial} -> {reg2.last_serial}; retrying."
                )
            continue

        # 6. Verify our lock is still the one on disk.
        lock2 = _load_lock(lock_file)
        if not lock2 or lock2.get("tx_id") != tx_id:
            if log is not None:
                log(f"Allocation attempt {attempt}: lock taken over; retrying.")
            continue

        # 7. Build interview ID and commit.
        year = clock().year
        interview_id = build_interview_id(
            year, researcher_id, mnemonic, proposed
        )
        reg2.last_serial = proposed
        reg2.issued.append(_issued_entry(interview_id, researcher_id, clock()))
        save_registry(project_path, reg2)

        # 8. Remove lock.
        try:
            lock_file.unlink()
        except FileNotFoundError:
            pass

        return interview_id

    raise AllocationError(
        f"Allocation failed after {max_retries} attempts. Try again later."
    )


def _issued_entry(interview_id: str, researcher_id: str, now: datetime):
    from .models import IssuedEntry

    return IssuedEntry(id=interview_id, researcher=researcher_id, issued_at=rfc3339(now))
