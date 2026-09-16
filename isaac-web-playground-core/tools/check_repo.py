#!/usr/bin/env python3
"""Small repository-hygiene checks that need no Isaac Sim installation."""

from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
errors: list[str] = []

for document in ROOT.rglob("*.md"):
    text = document.read_text(encoding="utf-8", errors="replace")
    for match in MARKDOWN_LINK.finditer(text):
        target = match.group(1).strip().strip("<>").split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        destination = (document.parent / target).resolve()
        try:
            destination.relative_to(ROOT)
        except ValueError:
            continue
        if not destination.exists():
            errors.append(f"broken link: {document.relative_to(ROOT)} -> {target}")

for cache in ROOT.rglob("__pycache__"):
    errors.append(f"generated cache committed/present: {cache.relative_to(ROOT)}")
for compiled in ROOT.rglob("*.pyc"):
    errors.append(f"compiled Python file committed/present: {compiled.relative_to(ROOT)}")

if errors:
    print("Repository hygiene: FAIL")
    for error in errors:
        print(f"  - {error}")
    raise SystemExit(1)

print("Repository hygiene: PASS")
