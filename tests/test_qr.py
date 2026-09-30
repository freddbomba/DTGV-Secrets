"""Tests for QR rendering helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from interview_intake import qr
from interview_intake.qr import QrUnavailableError


def test_qr_is_available_in_dev_env() -> None:
    assert qr.qr_available() is True


def test_render_ascii_has_quiet_zone_and_rows() -> None:
    text = qr.render_ascii("age1abcdef")
    lines = text.splitlines()
    assert len(lines) >= 21  # at least a v1 code plus border
    assert any("██" in line for line in lines)
    assert lines[0].strip() == ""  # top quiet zone


def test_render_svg_is_wellformed() -> None:
    svg = qr.render_svg("age1abcdef", module_size=4)
    assert svg.startswith("<?xml")
    assert "<svg" in svg and "</svg>" in svg
    assert "<rect" in svg


def test_write_qr_svg_and_txt(tmp_path: Path) -> None:
    svg = qr.write_qr("age1abcdef", tmp_path / "code.svg")
    txt = qr.write_qr("age1abcdef", tmp_path / "code.txt")
    assert svg.read_text(encoding="utf-8").startswith("<?xml")
    assert "██" in txt.read_text(encoding="utf-8")


def test_unsupported_format_raises(tmp_path: Path) -> None:
    with pytest.raises(Exception):
        qr.write_qr("age1abcdef", tmp_path / "code.gif")


def test_unavailable_package_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(qr, "qr_available", lambda: False)
    with pytest.raises(QrUnavailableError):
        qr.render_ascii("age1abcdef")
