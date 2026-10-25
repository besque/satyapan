"""Download public mandatory-disclosure documents of real Bangalore institutions (with provenance)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "real"

SOURCES = {
    "dsce": {
        "name": "Dayananda Sagar College of Engineering, Bengaluru",
        "files": {
            "eoa_2026_27.pdf": "https://www.dsce.edu.in/images/Home/Approvals/AICTE_EOA-Report_2026-27.pdf",
            "eoa_2025_26.pdf": "https://www.dsce.edu.in/images/Home/Approvals/EOA_Report_25-26.pdf",
            "eoa_2024_25.pdf": "https://www.dsce.edu.in/images/Home/Approvals/EOA-Report_2024-25.pdf",
            "eoa_2023_24.pdf": "https://www.dsce.edu.in/images/Home/Approvals/EOA23.pdf",
            "eoa_2022_23.pdf": "https://www.dsce.edu.in/images/Home/Approvals/EOA22.pdf",
            "eoa_2021_22.pdf": "https://www.dsce.edu.in/images/Home/Approvals/EOA_Report_21_22.pdf",
            "eoa_2020_21.pdf": "https://www.dsce.edu.in/images/Home/Approvals/EOA_Rpt_2020_21.pdf",
            "eoa_2019_20.pdf": "https://www.dsce.edu.in/images/Home/Approvals/EOA_Report_2019_20.pdf",
            "eoa_2018_19.pdf": "https://www.dsce.edu.in/images/Home/Approvals/EOA_Report_2018_19.pdf",
            "eoa_2017_18.pdf": "https://www.dsce.edu.in/images/Home/Approvals/AICTE_Extension_of_Approval_2017_18.pdf",
            "mandatory_disclosure_2025.pdf": "https://www.dsce.edu.in/images/Home/Approvals/AICTE_Mandatory2025.pdf",
            "fire_and_safety.pdf": "https://drive.google.com/uc?export=download&id=1CMnz8qimKOX1NEsQGXHBfyAPJz4CiKnR",
            "nba_naac.pdf": "https://www.dsce.edu.in/images/Home/Approvals/NBA_naac.pdf",
        },
    },
    "bmsce": {
        "name": "B.M.S. College of Engineering, Bengaluru",
        "files": {
            "fire_and_safety.pdf": "https://bmsce.ac.in/assets/files/MandatoryDisclosure/Fire and Safety.pdf",
            "occupancy_certificate.pdf": "https://bmsce.ac.in/assets/files/MandatoryDisclosure/Occupancy Certificate.pdf",
            "faculty_list.pdf": "https://bmsce.ac.in/assets/files/MandatoryDisclosure/Faculty List.pdf",
            "mandatory_disclosure.pdf": "https://bmsce.ac.in/assets/files/MandatoryDisclosure/Mandatory Disclosure Latest.pdf",
            "barrier_free.pdf": "https://bmsce.ac.in/assets/files/MandatoryDisclosure/Barrier free Environment.pdf",
            **{f"eoa_{y}_{str(y + 1)[2:]}.pdf": f"https://bmsce.ac.in/assets/files/AICTE/BMSCE-AICTE Extension of Approval- {y}-{y + 1}.{'PDF' if y == 2025 else 'pdf'}"
               for y in range(2015, 2027)},
        },
    },
}


def main() -> None:
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (research prototype)"
    for key, src in SOURCES.items():
        d = OUT / key
        d.mkdir(parents=True, exist_ok=True)
        man = {"institution": src["name"], "files": {}}
        for name, url in src["files"].items():
            p = urlsplit(url)
            url = urlunsplit((p.scheme, p.netloc, quote(p.path), p.query, ""))
            try:
                r = s.get(url, timeout=90)
            except Exception as e:  # noqa: BLE001
                print("FAIL", url, e); continue
            if r.status_code != 200 or not r.content.startswith(b"%PDF"):
                print("SKIP", r.status_code, url); continue
            (d / name).write_bytes(r.content)
            man["files"][name] = {"source_url": url, "sha256": hashlib.sha256(r.content).hexdigest(), "bytes": len(r.content),
                                  "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            print("OK", key, name, len(r.content))
        (d / "manifest.json").write_text(json.dumps(man, indent=1), "utf-8")


if __name__ == "__main__":
    main()
