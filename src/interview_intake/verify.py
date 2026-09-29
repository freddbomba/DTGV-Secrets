"""Integrity verification for a project folder (``verify`` CLI command).

Without decrypting anything, this checks that:

* ``registry.json`` parses and its sequence is internally consistent;
* every issued interview has a folder, ``meta.json`` and ``audio.age``;
* each ``audio.age`` matches the size and SHA-256 recorded in ``meta.json``;
* interview folders missing from the registry (and FAILED markers) are surfaced.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .fs import read_json, sha256_file
from .id_grammar import is_interview_id
from .intake import FAILED_MARKER
from .models import Meta
from .registry import interviews_dir, load_registry


@dataclass
class VerifyReport:
    checked: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def verify_project(project_path: Path | str) -> VerifyReport:
    project_path = Path(project_path).expanduser()
    report = VerifyReport()

    try:
        registry = load_registry(project_path)
    except Exception as exc:
        report.errors.append(f"registry.json: {exc}")
        return report

    issued_ids = [entry.id for entry in registry.issued]
    seen: set[str] = set()
    for interview_id in issued_ids:
        if interview_id in seen:
            report.errors.append(f"registry lists {interview_id} more than once.")
        seen.add(interview_id)
        report.checked += 1
        _verify_interview(project_path, interview_id, report)

    if issued_ids:
        max_serial = max(int(i.rsplit("-", 1)[1]) for i in issued_ids if is_interview_id(i))
        if registry.last_serial < max_serial:
            report.errors.append(
                f"registry.last_serial ({registry.last_serial}) is below the highest "
                f"issued serial ({max_serial})."
            )

    directory = interviews_dir(project_path)
    if directory.is_dir():
        for child in sorted(directory.iterdir()):
            if not child.is_dir() or not is_interview_id(child.name):
                continue
            if child.name not in seen:
                marker = " (FAILED)" if (child / FAILED_MARKER).exists() else ""
                report.warnings.append(
                    f"Folder {child.name} exists but is not listed in registry.json{marker}."
                )

    return report


def _verify_interview(
    project_path: Path, interview_id: str, report: VerifyReport
) -> None:
    folder = interviews_dir(project_path) / interview_id
    if not folder.is_dir():
        report.errors.append(f"{interview_id}: folder is missing.")
        return

    if (folder / FAILED_MARKER).exists():
        report.warnings.append(
            f"{interview_id}: has a FAILED marker; needs supervisor reconciliation."
        )

    meta_path = folder / "meta.json"
    if not meta_path.exists():
        report.errors.append(f"{interview_id}: meta.json is missing.")
        return
    try:
        meta = Meta.from_dict(read_json(meta_path))
    except Exception as exc:
        report.errors.append(f"{interview_id}: invalid meta.json: {exc}")
        return

    if meta.interview_id != interview_id:
        report.errors.append(
            f"{interview_id}: meta.json interview_id is {meta.interview_id!r}."
        )

    audio = folder / meta.audio.filename
    if not audio.is_file():
        report.errors.append(f"{interview_id}: {meta.audio.filename} is missing.")
        return
    size = audio.stat().st_size
    if size != meta.audio.size_bytes:
        report.errors.append(
            f"{interview_id}: size mismatch (meta={meta.audio.size_bytes}, disk={size})."
        )
    digest = sha256_file(audio)
    if digest != meta.audio.encrypted_sha256:
        report.errors.append(
            f"{interview_id}: encrypted SHA-256 mismatch "
            f"(meta={meta.audio.encrypted_sha256}, disk={digest})."
        )
