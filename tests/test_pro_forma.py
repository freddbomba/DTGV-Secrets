"""Tests for the pro forma sample data and Excel export."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from interview_intake import proforma
from interview_intake.id_grammar import (
    validate_interview_id,
    validate_mnemonic,
    validate_researcher_id,
)

DATA = Path(__file__).parent / "data" / "pro_forma_interviews.json"


def test_data_file_exists() -> None:
    assert DATA.is_file()


def test_has_fifteen_records() -> None:
    data = proforma.load_pro_forma(DATA)
    assert len(data["interviews"]) == 15


def test_records_are_valid_and_sequential() -> None:
    data = proforma.load_pro_forma(DATA)
    serials = []
    for record in data["interviews"]:
        assert set(record) == {
            "interview_id",
            "date",
            "researcher_id",
            "mnemonic",
            "location",
            "language",
            "participants",
            "duration_seconds",
            "original_filename",
            "format",
            "size_bytes",
            "transcription_status",
            "consent_ref",
            "notes",
        }
        validate_interview_id(record["interview_id"])
        validate_researcher_id(record["researcher_id"])
        validate_mnemonic(record["mnemonic"])
        assert isinstance(record["participants"], int)
        assert isinstance(record["duration_seconds"], int)
        assert isinstance(record["size_bytes"], int)
        serials.append(int(record["interview_id"].rsplit("-", 1)[1]))
    assert serials == list(range(1, 16))


def test_rows_have_header_and_data() -> None:
    data = proforma.load_pro_forma(DATA)
    rows = proforma.rows_for(data["interviews"])
    assert rows[0][0] == "Interview ID"
    assert len(rows) == 16
    assert rows[1][0] == "2026-abc-xyz-0001"


def test_load_rejects_bad_shape(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"nope": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        proforma.load_pro_forma(bad)


def test_load_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        proforma.load_pro_forma(tmp_path / "nope.json")


def test_excel_export(tmp_path: Path) -> None:
    openpyxl = pytest.importorskip("openpyxl")
    data = proforma.load_pro_forma(DATA)
    output = proforma.write_excel(data["interviews"], tmp_path / "pro_forma.xlsx")

    assert output.exists()
    workbook = openpyxl.load_workbook(output)
    sheet = workbook.active
    assert sheet.max_row == 16  # header + 15 interviews
    assert sheet.max_column == len(proforma.COLUMNS)
    assert sheet["A1"].value == "Interview ID"
    assert sheet["A2"].value == "2026-abc-xyz-0001"
    assert sheet["A16"].value == "2026-ghi-bcd-0015"
    assert sheet.freeze_panes == "A2"


def test_cli_writes_workbook(tmp_path: Path, capsys) -> None:
    pytest.importorskip("openpyxl")
    output = tmp_path / "out.xlsx"
    code = proforma.main(["--input", str(DATA), "--output", str(output)])
    assert code == 0
    assert output.exists()
    assert "15 interviews" in capsys.readouterr().out


def test_cli_missing_openpyxl_or_bad_input(tmp_path: Path, capsys) -> None:
    code = proforma.main(
        ["--input", str(tmp_path / "nope.json"), "--output", str(tmp_path / "o.xlsx")]
    )
    assert code == 1
    assert "error:" in capsys.readouterr().err
