from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from interview_intake.allocation import allocate_serial, rfc3339
from interview_intake.errors import AllocationError, SerialExhaustedError
from interview_intake.fs import read_json, write_json_atomic
from interview_intake.registry import load_registry, save_registry
from interview_intake.models import IssuedEntry

FIXED = datetime(2026, 4, 12, 9, 14, 22, tzinfo=timezone.utc)


def _clock():
    return FIXED


def test_basic_allocation(project: Path) -> None:
    interview_id = allocate_serial(
        project, "abc", "xyz", sync_wait_seconds=0, clock=_clock, sleeper=lambda s: None
    )
    assert interview_id == "2026-abc-xyz-0001"
    registry = load_registry(project)
    assert registry.last_serial == 1
    assert registry.issued[0].id == interview_id
    assert not (project / "registry.lock").exists()


def test_serial_increments(project: Path) -> None:
    first = allocate_serial(
        project, "abc", "xyz", sync_wait_seconds=0, clock=_clock, sleeper=lambda s: None
    )
    second = allocate_serial(
        project, "abc", "qrs", sync_wait_seconds=0, clock=_clock, sleeper=lambda s: None
    )
    assert (first, second) == ("2026-abc-xyz-0001", "2026-abc-qrs-0002")


def test_serial_exhausted(project: Path) -> None:
    registry = load_registry(project)
    registry.last_serial = 9999
    save_registry(project, registry)
    with pytest.raises(SerialExhaustedError):
        allocate_serial(
            project, "abc", "xyz", sync_wait_seconds=0, clock=_clock, sleeper=lambda s: None
        )


def test_retry_on_competing_commit(project: Path) -> None:
    """First sleep simulates another researcher committing."""

    state = {"done": False}

    def sleeper(_seconds: float) -> None:
        if state["done"]:
            return
        state["done"] = True
        reg = load_registry(project)
        reg.last_serial = 1
        reg.issued.append(
            IssuedEntry(
                id="2026-def-aaa-0001",
                researcher="abc",
                issued_at=rfc3339(FIXED),
            )
        )
        save_registry(project, reg)

    interview_id = allocate_serial(
        project, "abc", "xyz", sync_wait_seconds=1, clock=_clock, sleeper=sleeper
    )
    assert interview_id == "2026-abc-xyz-0002"
    assert not (project / "registry.lock").exists()


def test_retry_on_lock_takeover(project: Path) -> None:
    """A competing transaction overwrites our lock but does not commit yet."""

    state = {"done": False}

    def sleeper(_seconds: float) -> None:
        if state["done"]:
            return
        state["done"] = True
        write_json_atomic(
            project / "registry.lock",
            {
                "tx_id": "someone-else",
                "researcher_id": "def",
                "proposed_serial": 1,
                "created_at": rfc3339(FIXED),
            },
        )

    interview_id = allocate_serial(
        project, "abc", "xyz", sync_wait_seconds=1, clock=_clock, sleeper=sleeper
    )
    assert interview_id == "2026-abc-xyz-0001"


def test_retries_exhausted(project: Path) -> None:
    def sleeper(_seconds: float) -> None:
        reg = load_registry(project)
        reg.last_serial += 1
        save_registry(project, reg)

    with pytest.raises(AllocationError):
        allocate_serial(
            project,
            "abc",
            "xyz",
            sync_wait_seconds=1,
            clock=_clock,
            sleeper=sleeper,
            max_retries=3,
        )


def test_stale_lock_removed(project: Path) -> None:
    old = FIXED - timedelta(seconds=120)
    write_json_atomic(
        project / "registry.lock",
        {
            "tx_id": "stale",
            "researcher_id": "abc",
            "proposed_serial": 1,
            "created_at": rfc3339(old),
        },
    )
    interview_id = allocate_serial(
        project,
        "abc",
        "xyz",
        sync_wait_seconds=0,
        lock_stale_seconds=60,
        clock=_clock,
        sleeper=lambda s: None,
    )
    assert interview_id == "2026-abc-xyz-0001"
    assert not (project / "registry.lock").exists()


def test_fresh_lock_not_removed(project: Path) -> None:
    write_json_atomic(
        project / "registry.lock",
        {
            "tx_id": "fresh",
            "researcher_id": "def",
            "proposed_serial": 1,
            "created_at": rfc3339(FIXED),
        },
    )
    # Our own lock write will overwrite it, so the transaction still succeeds.
    interview_id = allocate_serial(
        project,
        "abc",
        "xyz",
        sync_wait_seconds=0,
        lock_stale_seconds=60,
        clock=_clock,
        sleeper=lambda s: None,
    )
    assert interview_id == "2026-abc-xyz-0001"


def test_lock_record_shape(project: Path) -> None:
    captured = {}

    def sleeper(_seconds: float) -> None:
        captured.update(read_json(project / "registry.lock"))

    allocate_serial(
        project, "abc", "xyz", sync_wait_seconds=1, clock=_clock, sleeper=sleeper
    )
    assert captured["researcher_id"] == "abc"
    assert captured["proposed_serial"] == 1
    assert set(captured) == {"tx_id", "researcher_id", "proposed_serial", "created_at"}
