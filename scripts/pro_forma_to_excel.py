#!/usr/bin/env python3
"""Utility: convert the pro forma sample data into an Excel workbook.

Usage:
    python scripts/pro_forma_to_excel.py
    python scripts/pro_forma_to_excel.py \
        --input tests/data/pro_forma_interviews.json \
        --output pro_forma_interviews.xlsx

The conversion logic lives in ``interview_intake.proforma``; this is a thin
standalone wrapper so the script can be run without installing the package
(it puts ``src/`` on ``sys.path``).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from interview_intake.proforma import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
