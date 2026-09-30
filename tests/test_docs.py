"""Keep the documentation honest.

The README embeds local screenshots; this test makes sure every referenced
image actually exists so the docs never render a broken link.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = (
    ROOT / "README.md",
    ROOT / "INSTALL.md",
    ROOT / "packaging" / "README.md",
    *sorted((ROOT / "docs").glob("*.md")),
)


def _heading_slugs(text: str) -> set[str]:
    slugs = set()
    for match in re.finditer(r"^#{1,6}\s+(.+?)\s*$", text, re.M):
        slugs.add(re.sub(r"[^a-z0-9 -]", "", match.group(1).lower()).replace(" ", "-"))
    return slugs


def _local_links(text: str):
    for target in re.findall(r"\]\(([^)]+)\)", text):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        yield target


def test_all_doc_links_and_anchors_resolve() -> None:
    slugs = {doc: _heading_slugs(doc.read_text(encoding="utf-8")) for doc in DOCS}
    for doc in DOCS:
        for target in _local_links(doc.read_text(encoding="utf-8")):
            path, _, anchor = target.partition("#")
            if path:
                resolved = (doc.parent / path).resolve()
                assert resolved.exists(), f"{doc.relative_to(ROOT)} -> missing {target}"
                if anchor and resolved.suffix == ".md":
                    assert anchor in _heading_slugs(resolved.read_text(encoding="utf-8")), (
                        f"{doc.relative_to(ROOT)} -> bad anchor {target}"
                    )
            elif anchor:
                assert anchor in slugs[doc], f"{doc.relative_to(ROOT)} -> bad anchor {target}"


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


def test_gui_doc_mentions_screenshot_helper() -> None:
    text = (ROOT / "docs" / "gui.md").read_text(encoding="utf-8")
    assert "capture_gui_screenshots.py" in text
    assert (ROOT / "scripts" / "capture_gui_screenshots.py").is_file()
