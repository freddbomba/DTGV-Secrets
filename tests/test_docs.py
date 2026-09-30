"""Keep the documentation honest.

The README embeds local screenshots; this test makes sure every referenced
image actually exists so the docs never render a broken link.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = (ROOT / "README.md", ROOT / "packaging" / "README.md")


def test_all_doc_images_exist() -> None:
    total = 0
    for doc in DOCS:
        text = doc.read_text(encoding="utf-8")
        refs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
        for ref in refs:
            assert not ref.startswith(("http://", "https://")), f"remote image: {ref}"
            assert (doc.parent / ref).resolve().is_file(), (
                f"missing image referenced by {doc.relative_to(ROOT)}: {ref}"
            )
            total += 1
    assert total >= 8, "expected at least the 8 GUI screenshots"


def test_readme_screenshot_helper_exists() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "capture_gui_screenshots.py" in text
    assert (ROOT / "scripts" / "capture_gui_screenshots.py").is_file()
