"""PyInstaller entry point for the researcher CLI binary.

Kept as a top-level script so relative imports inside the package still work
when frozen (a module run as ``__main__`` has no package context).
"""

from interview_intake.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
