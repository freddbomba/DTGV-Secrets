"""Interview markdown templates (spec section 8).

Templates live in ``<project>/templates/`` so the whole team shares them.  If a
template is missing the app falls back to the bundled default and can seed the
project templates via ``install_default_templates``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

from .errors import TemplateError
from .registry import templates_dir

TRANSCRIPT_TEMPLATE_NAME = "transcript_template.md"
NOTE_TEMPLATE_NAME = "note_template.md"

TRANSCRIPT_TEMPLATE = """\
---
interview_id: {{interview_id}}
date: {{date}}
researcher_id: {{researcher_id}}
mnemonic: {{mnemonic}}
language: en
duration_min: null
personas:
  - pseudonym: P1
    role: participant
    bio: ""
    consent_ref: ""
  - pseudonym: P2
    role: interviewer
    bio: ""
context: ""
summary: ""
tags: []
technical_notes: ""

# === SAFETY REMINDERS ===
# - Do NOT paste real names, emails, or addresses into this file.
#   The pseudonym <-> identity mapping lives only in the supervisor's masterfile.
# - Do NOT decrypt audio into the Nextcloud synced folder.
#   Decrypt to a location outside the sync root, e.g. ~/tmp/.
# - When running Whisper, set TMPDIR to a directory outside the sync root
#   and wipe it afterwards. Whisper can leave temp audio files behind on failure.
# - Store this file only in its interview folder. Do not copy it elsewhere.
---

# Interview {{interview_id}}

## Context

## Summary

## Transcript

"""

NOTE_TEMPLATE = """\
---
interview_id: {{interview_id}}
date: {{date}}
researcher_id: {{researcher_id}}
mnemonic: {{mnemonic}}
language: en
duration_min: null
personas:
  - pseudonym: P1
    role: participant
    bio: ""
    consent_ref: ""
  - pseudonym: P2
    role: interviewer
    bio: ""
context: ""
summary: ""
tags: []
technical_notes: ""

# === SAFETY REMINDERS ===
# - Do NOT paste real names, emails, or addresses into this file.
#   The pseudonym <-> identity mapping lives only in the supervisor's masterfile.
# - Do NOT decrypt audio into the Nextcloud synced folder.
#   Decrypt to a location outside the sync root, e.g. ~/tmp/.
# - When running Whisper, set TMPDIR to a directory outside the sync root
#   and wipe it afterwards. Whisper can leave temp audio files behind on failure.
# - Store this file only in its interview folder. Do not copy it elsewhere.
---

# Interview {{interview_id}}

## Context

## Summary

## Observations

"""

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


def render_template(template: str, values: Mapping[str, str]) -> str:
    """Substitute ``{{name}}`` placeholders, rejecting unknown ones."""

    def replace(match):
        key = match.group(1)
        if key not in values:
            raise TemplateError(f"Template references unknown placeholder {key!r}.")
        return str(values[key])

    return _PLACEHOLDER_RE.sub(replace, template)


def load_template(project_path: Path | str, name: str) -> str:
    """Read a shared template, falling back to the bundled default."""
    path = templates_dir(project_path) / name
    if path.exists():
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise TemplateError(f"Cannot read template {path}: {exc}") from exc
    defaults = {TRANSCRIPT_TEMPLATE_NAME: TRANSCRIPT_TEMPLATE, NOTE_TEMPLATE_NAME: NOTE_TEMPLATE}
    if name not in defaults:
        raise TemplateError(f"Unknown template {name!r} and no default available.")
    return defaults[name]


def install_default_templates(project_path: Path | str, *, overwrite: bool = False) -> list[Path]:
    """Seed ``<project>/templates/`` with the bundled defaults."""
    directory = templates_dir(project_path)
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, content in (
        (TRANSCRIPT_TEMPLATE_NAME, TRANSCRIPT_TEMPLATE),
        (NOTE_TEMPLATE_NAME, NOTE_TEMPLATE),
    ):
        path = directory / name
        if path.exists() and not overwrite:
            continue
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def template_values(interview_id: str, date: str, researcher_id: str, mnemonic: str) -> dict[str, str]:
    return {
        "interview_id": interview_id,
        "date": date,
        "researcher_id": researcher_id,
        "mnemonic": mnemonic,
    }


def render_interview_documents(
    project_path: Path | str,
    *,
    interview_id: str,
    date: str,
    researcher_id: str,
    mnemonic: str,
) -> dict[str, str]:
    """Render transcript.md and note.md contents for an interview."""
    values = template_values(interview_id, date, researcher_id, mnemonic)
    return {
        "transcript.md": render_template(load_template(project_path, TRANSCRIPT_TEMPLATE_NAME), values),
        "note.md": render_template(load_template(project_path, NOTE_TEMPLATE_NAME), values),
    }
