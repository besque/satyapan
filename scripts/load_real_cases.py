"""Load real institutions (public documents only) as 'public disclosure review' cases.

For each institution in data/raw/real/<key>/:
  * every EoA letter goes into the institutional record (with its public source URL);
  * the latest letter gives the approved courses/intake, which become the case's course list;
  * the fire certificate, occupancy certificate and mandatory disclosure they publish are run through
    the same checks. Checks that need non-public documents show as "not public".
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
logging.disable(logging.CRITICAL)

from app import db, docmodel, pipeline  # noqa: E402
from app.config import RAW  # noqa: E402
from app.extract import eoa  # noqa: E402

REAL = RAW / "real"
DECLARED = {"fire_and_safety.pdf": "fire_noc", "occupancy_certificate.pdf": "occupancy_certificate",
            "mandatory_disclosure.pdf": "mandatory_disclosure", "mandatory_disclosure_2025.pdf": "mandatory_disclosure"}
EXTRA = {"dsce": {"principal": "Dr. B G Prasad"}, "bmsce": {"principal": "Dr. Bheemsha Arya"}}


def load_letters(key: str, man: dict) -> list:
    letters = []
    for f in sorted((REAL / key).glob("eoa_*.pdf")):
        meta = man["files"].get(f.name, {})
        for L in eoa.parse(docmodel.load(f, allow_ocr=False)):
            pid, ay = L.get("permanent_id"), L.academic_year
            if not pid or not ay:
                continue
            letters.append((L, f))
            if not db.q1("SELECT 1 FROM institutions WHERE permanent_id=?", (pid,)) or L.get("name"):
                db.insert("institutions", {"permanent_id": pid, "name": L.get("name"), "trust": L.get("trust"), "address": L.get("address"),
                                           "state": L.get("state") or "Karnataka", "region": L.get("region"), "inst_type": L.get("inst_type"),
                                           "est_year": int(L.get("est_year")) if (L.get("est_year") or "").isdigit() else None,
                                           "lat": None, "lon": None, "source": "public_eoa", "extra": None}, replace=True)
            with db.tx() as c:
                old = c.execute("SELECT id FROM approvals WHERE permanent_id=? AND academic_year=?", (pid, ay)).fetchall()
                for o in old:
                    c.execute("DELETE FROM approval_courses WHERE approval_id=?", (o["id"],))
                    c.execute("DELETE FROM approvals WHERE id=?", (o["id"],))
                cur = c.execute("INSERT INTO approvals (permanent_id, academic_year, application_id, fno, date_of_approval, letter_printed,"
                                " letter_kind, source_sha, source_url, source_pages, deficiencies) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                (pid, ay, L.application_no, L.get("fno"), L.get("date_of_approval"), L.get("letter_printed"), L.get("kind"),
                                 meta.get("sha256"), meta.get("source_url", f.name), json.dumps(L.pages), json.dumps(L.deficiencies)))
                for crs in L.courses:
                    c.execute("INSERT INTO approval_courses VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                              (cur.lastrowid, crs.level, crs.program, crs.course, None, crs.affiliating_body, crs.intake_prev,
                               crs.intake_curr, crs.nri, crs.fn, int(crs.is_new)))
    return letters


def build_case(key: str) -> str | None:
    man = json.loads((REAL / key / "manifest.json").read_text("utf-8"))
    letters = load_letters(key, man)
    if not letters:
        print("no letters for", key); return None
    latest, latest_file = max(letters, key=lambda x: x[0].academic_year)
    pid = latest.get("permanent_id")
    inst = db.q1("SELECT * FROM institutions WHERE permanent_id=?", (pid,))
    y = int(latest.academic_year[:4]) + 1
    form = {
        "application_no": "PUBLIC-REVIEW", "permanent_id": pid, "category": "PUBLIC_REVIEW", "academic_year": f"{y}-{str(y + 1)[2:]}",
        "application_date": date.today().isoformat(), "institution_name": inst["name"], "trust_name": latest.get("trust"),
        "address": latest.get("address"), "state": inst.get("state") or "Karnataka", "chairperson": None,
        "courses": [{"level": c.level, "program": c.program, "course": c.course, "intake": c.intake_curr or 0,
                     "affiliating_body": c.affiliating_body} for c in latest.courses if (c.intake_curr or 0) > 0],
        "builtup_area_sqm": None, "building_completion_year": None, "campus_lat": None, "campus_lon": None, "ter_txn_id": None,
        "faculty": [], "principal": {"name": EXTRA.get(key, {}).get("principal"), "qualification": "Ph.D", "regular": True},
        "public_sources": {n: v["source_url"] for n, v in man["files"].items()},
    }
    files = []
    for name, declared in DECLARED.items():
        p = REAL / key / name
        if p.exists():
            files.append((name, p.read_bytes(), declared))
    files.append((latest_file.name, latest_file.read_bytes(), "eoa_letter"))
    aid = pipeline.process(form, files, source="public", actor="loader", role="system", defer_network=True)
    print(f"  {key}: {inst['name']} -> {aid} ({len(letters)} letters in record, {len(files)} documents checked)", flush=True)
    return aid


def main() -> list[str]:
    ids = [a for a in (build_case(k) for k in sorted(p.name for p in REAL.iterdir() if p.is_dir())) if a]
    pipeline.refresh_network()
    return ids


if __name__ == "__main__":
    main()
