"""Keep the documentation honest.

The README embeds local screenshots; this test makes sure every referenced
image actually exists so the docs never render a broken link.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_readme_images_exist() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    assert refs, "README has no screenshots"
    for ref in refs:
        assert not ref.startswith(("http://", "https://")), f"remote image: {ref}"
        assert (ROOT / ref).is_file(), f"missing image referenced by README: {ref}"


def test_readme_screenshot_helper_exists() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "capture_gui_screenshots.py" in text
    assert (ROOT / "scripts" / "capture_gui_screenshots.py").is_file()
