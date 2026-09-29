from __future__ import annotations

import pytest

from interview_intake.errors import TemplateError
from interview_intake.templates import (
    NOTE_TEMPLATE_NAME,
    TRANSCRIPT_TEMPLATE_NAME,
    install_default_templates,
    load_template,
    render_interview_documents,
    render_template,
)


def test_render_known_placeholder() -> None:
    assert render_template("id={{interview_id}}", {"interview_id": "x"}) == "id=x"
    assert render_template("{{ date }}", {"date": "2026-01-01"}) == "2026-01-01"
    assert render_template("id={{interview_id}}", {"interview_id": "x"}) == "id=x"


def test_render_unknown_placeholder() -> None:
    with pytest.raises(TemplateError):
        render_template("{{nope}}", {})


def test_defaults_have_placeholders(project) -> None:
    transcript = load_template(project, TRANSCRIPT_TEMPLATE_NAME)
    assert "{{interview_id}}" in transcript
    note = load_template(project, NOTE_TEMPLATE_NAME)
    assert "{{interview_id}}" in note


def test_rendered_structures(project) -> None:
    documents = render_interview_documents(
        project,
        interview_id="2026-abc-xyz-0001",
        date="2026-04-12",
        researcher_id="abc",
        mnemonic="xyz",
    )
    transcript = documents["transcript.md"]
    note = documents["note.md"]
    assert "interview_id: 2026-abc-xyz-0001" in transcript
    assert "date: 2026-04-12" in transcript
    assert "## Transcript" in transcript
    assert "## Observations" in note
    assert "## Transcript" not in note
    assert "{{" not in transcript
    assert "{{" not in note


def test_custom_project_template_wins(project) -> None:
    (project / "templates" / TRANSCRIPT_TEMPLATE_NAME).write_text(
        "custom {{interview_id}}", encoding="utf-8"
    )
    documents = render_interview_documents(
        project,
        interview_id="2026-abc-xyz-0001",
        date="2026-04-12",
        researcher_id="abc",
        mnemonic="xyz",
    )
    assert documents["transcript.md"] == "custom 2026-abc-xyz-0001"


def test_install_default_templates(project) -> None:
    written = install_default_templates(project)
    assert len(written) == 2
    assert (project / "templates" / TRANSCRIPT_TEMPLATE_NAME).exists()
    assert (project / "templates" / NOTE_TEMPLATE_NAME).exists()
    # Idempotent without overwrite.
    assert install_default_templates(project) == []
    overwritten = install_default_templates(project, overwrite=True)
    assert len(overwritten) == 2
