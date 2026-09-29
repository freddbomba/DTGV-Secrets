from __future__ import annotations

import os
from pathlib import Path

import pytest

from interview_intake.fs import (
    ensure_private_dir,
    is_within,
    is_world_readable,
    read_json,
    sha256_file,
    wipe_file,
    write_json_atomic,
)
from interview_intake.errors import IntakeError


def test_write_read_json_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "data.json"
    write_json_atomic(path, {"a": 1, "b": [2, 3]})
    assert read_json(path) == {"a": 1, "b": [2, 3]}
    assert path.read_text(encoding="utf-8").endswith("\n")


def test_read_json_missing(tmp_path: Path) -> None:
    with pytest.raises(IntakeError):
        read_json(tmp_path / "nope.json")


def test_read_json_malformed(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{oops", encoding="utf-8")
    with pytest.raises(IntakeError):
        read_json(path)


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions only")
def test_ensure_private_dir_creates_0700(tmp_path: Path) -> None:
    target = tmp_path / "private"
    ensure_private_dir(target)
    assert target.stat().st_mode & 0o777 == 0o700


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions only")
def test_ensure_private_dir_does_not_chmod_existing(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    os.chmod(shared, 0o755)
    ensure_private_dir(shared)
    # A pre-existing directory must be left alone (e.g. /tmp).
    assert shared.stat().st_mode & 0o777 == 0o755


def test_is_within(tmp_path: Path) -> None:
    root = tmp_path / "sync"
    (root / "project").mkdir(parents=True)
    assert is_within(root / "project" / "x.txt", root)
    assert is_within(root, root)
    assert not is_within(tmp_path / "outside" / "x.txt", root)


def test_is_within_resolves_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "sync"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = outside / "link"
    link.symlink_to(root / "target")
    assert is_within(link, root)


def test_sha256_file(tmp_path: Path) -> None:
    import hashlib

    path = tmp_path / "f.bin"
    path.write_bytes(b"hello")
    assert sha256_file(path) == hashlib.sha256(b"hello").hexdigest()


def test_is_world_readable_private(tmp_path: Path) -> None:
    # pytest's tmp dirs are 0700, so a not-yet-created child is not world-read
    assert not is_world_readable(tmp_path / "missing")


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions only")
def test_is_world_readable_detects_open_dir(tmp_path: Path) -> None:
    directory = tmp_path / "open"
    directory.mkdir()
    os.chmod(directory, 0o755)
    assert is_world_readable(directory / "file.txt")


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions only")
def test_wipe_file(tmp_path: Path) -> None:
    path = tmp_path / "secret.bin"
    path.write_bytes(b"secret data")
    wipe_file(path)
    assert not path.exists()
    # Wiping a missing file is a no-op.
    wipe_file(path)
