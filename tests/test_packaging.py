"""Static checks for the packaging recipes and the release workflow.

These tests never freeze anything: they validate that the shell recipes parse,
that the Linux launchers are well-formed, and that the CI workflow is valid
YAML wired to the build scripts.  This keeps the packaging directory honest
without pulling heavy toolchains into the test environment.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "packaging"
DESKTOP_DIR = PACKAGING / "desktop"
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"

SHELL_SCRIPTS = sorted(PACKAGING.glob("build_*.sh"))
DESKTOP_FILES = sorted(DESKTOP_DIR.glob("*.desktop"))
ENTRY_SCRIPTS = sorted((PACKAGING / "entry").glob("*.py")) if (PACKAGING / "entry").is_dir() else []


@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=lambda p: p.name)
def test_build_script_parses(script: Path) -> None:
    """Every build_*.sh must be syntactically valid bash."""
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not available")
    subprocess.run([bash, "-n", str(script)], check=True)


def test_build_scripts_are_executable() -> None:
    if not SHELL_SCRIPTS:
        pytest.skip("no build scripts yet")
    for script in SHELL_SCRIPTS:
        assert script.stat().st_mode & 0o111, f"{script.name} is not executable"


def test_pyinstaller_entry_scripts_exist() -> None:
    assert ENTRY_SCRIPTS, "packaging/entry/ has no entry scripts"
    names = {p.name for p in ENTRY_SCRIPTS}
    assert {
        "interview_intake_cli.py",
        "interview_intake_gui.py",
        "interview_supervisor_cli.py",
        "interview_supervisor_gui.py",
    } <= names


def test_desktop_files_have_required_keys() -> None:
    if not DESKTOP_FILES:
        pytest.skip("no .desktop files yet")
    for path in DESKTOP_FILES:
        text = path.read_text(encoding="utf-8")
        for key in ("[Desktop Entry]", "Type=Application", "Name=", "Exec=", "Icon="):
            assert key in text, f"{path.name} is missing {key!r}"


def test_release_workflow_uses_build_scripts() -> None:
    if not WORKFLOW.exists():
        pytest.skip("no release workflow yet")
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "build_macos.sh" in text
    assert "build_linux.sh" in text


def test_release_workflow_parses() -> None:
    if not WORKFLOW.exists():
        pytest.skip("no release workflow yet")
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data.get("jobs")
    # PyYAML parses the bare ``on:`` key as the boolean ``True``.
    triggers = data.get("on", data.get(True))
    assert triggers is not None
    assert "workflow_dispatch" in triggers or "workflow_dispatch" in str(triggers)
