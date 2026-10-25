"""Download the AICTE Approval Process Handbook 2024-27 and save its text (used for citations and vocabulary)."""
from __future__ import annotations

from pathlib import Path

import pymupdf
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "aph"
MIRRORS = [
    "https://cdnbbsr.s3waas.gov.in/s35938b4d054136e5d59ada6ec9c295d7a/uploads/2025/03/2025031399.pdf",
    "https://www.crescent.education/wp-content/uploads/2026/03/APH-Final-downloaded-on-23.12.2025.pdf",
]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pdf = OUT / "APH_2024_27.pdf"
    if not pdf.exists():
        for url in MIRRORS:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=180)
            if r.status_code == 200 and r.content.startswith(b"%PDF"):
                pdf.write_bytes(r.content)
                print("downloaded", url)
                break
        else:
            raise SystemExit("could not download the handbook")
    doc = pymupdf.open(pdf)
    with open(OUT / "aph_text.txt", "w", encoding="utf-8") as f:
        for i, p in enumerate(doc):
            f.write(f"\n\n===== PAGE {i + 1} =====\n" + p.get_text())
    print(f"{doc.page_count} pages, text saved")


if __name__ == "__main__":
    main()
