"""Remove __pycache__ under project and venv."""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [ROOT, ROOT / "venv"]


def main() -> None:
    removed = 0
    for base in TARGETS:
        if not base.is_dir():
            continue
        for path in base.rglob("__pycache__"):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
    print(f"removed {removed} __pycache__ directories")


if __name__ == "__main__":
    main()
