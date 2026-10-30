"""Change the product name everywhere, from one place.

    python scripts/rename.py "NewName"
    python scripts/rename.py "NewName" --tagline "One-line description"

The app reads the name from brand.json when the server starts (header, sign-in page, browser tab, letters, API).
This script updates brand.json and replaces the old name in the documentation (README.md and other .md files),
so no file still carries the old name. Then restart the server (start.sh / start.bat). No rebuild is needed.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "brand.json"
SKIP = {".git", ".venv", "node_modules", "dist", "data", "__pycache__"}


def main() -> None:
    p = argparse.ArgumentParser(description="Rename the product")
    p.add_argument("name")
    p.add_argument("--tagline")
    a = p.parse_args()
    brand = json.loads(BRAND.read_text(encoding="utf-8"))
    old, new = brand["name"], a.name.strip()
    brand["name"] = new
    if a.tagline:
        brand["tagline"] = a.tagline
    BRAND.write_text(json.dumps(brand, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    changed = []
    if old != new:
        pat = re.compile(rf"\b{re.escape(old)}\b")
        for f in ROOT.rglob("*.md"):
            if SKIP & set(f.relative_to(ROOT).parts):
                continue
            t = f.read_text(encoding="utf-8")
            if pat.search(t):
                f.write_text(pat.sub(new, t), encoding="utf-8")
                changed.append(str(f.relative_to(ROOT)))
    print(f"Renamed '{old}' to '{new}' in brand.json" + (f" and {', '.join(changed)}" if changed else ""))
    print("Restart the server (start.sh or start.bat) to see it everywhere.")


if __name__ == "__main__":
    main()
