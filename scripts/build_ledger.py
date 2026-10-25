"""Build the institutional record ledger from the real public EoA corpus.

  python scripts/build_ledger.py            -> parse every PDF in data/raw/eoa, (re)load ledger tables
Prints parse coverage and the cross-year consistency checks it could run on real data.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import db, docmodel  # noqa: E402
from app.config import EOA_DIR  # noqa: E402
from app.extract import eoa  # noqa: E402


def main() -> None:
    manifest = json.loads((EOA_DIR / "manifest.json").read_text("utf-8"))
    by_file = {v["file"]: (sha, v) for sha, v in manifest.items()}
    with db.tx() as c:
        c.execute("DELETE FROM approval_courses WHERE approval_id IN (SELECT id FROM approvals WHERE source_url IS NOT NULL AND source_url != '')")
        c.execute("DELETE FROM approvals WHERE source_url IS NOT NULL AND source_url != ''")
        c.execute("DELETE FROM institutions WHERE source='public_eoa'")

    stats = defaultdict(int)
    failures = []
    for f in sorted(EOA_DIR.glob("*.pdf")):
        print("..", f.name, flush=True)
        sha, meta = by_file.get(f.name, (None, {}))
        try:
            doc = docmodel.load(f, allow_ocr=False)
            letters = eoa.parse(doc)
        except Exception as e:  # noqa: BLE001
            failures.append((f.name, repr(e))); continue
        stats["files"] += 1
        if not letters:
            failures.append((f.name, "no letters recognised")); continue
        for L in letters:
            stats["letters"] += 1
            pid, ay = L.get("permanent_id"), L.academic_year
            if not pid or not ay:
                stats["letters_missing_core"] += 1
                continue
            if L.courses:
                stats["letters_with_courses"] += 1
            stats["course_rows"] += len(L.courses)
            inst = {
                "permanent_id": pid, "name": L.get("name"), "trust": L.get("trust"), "address": L.get("address"),
                "state": L.get("state"), "region": L.get("region"), "inst_type": L.get("inst_type"),
                "est_year": int(L.get("est_year")) if (L.get("est_year") or "").isdigit() else None,
                "lat": None, "lon": None, "source": "public_eoa", "extra": None,
            }
            existing = db.q1("SELECT * FROM institutions WHERE permanent_id=?", (pid,))
            if not existing or (inst["name"] and not existing["name"]):
                db.insert("institutions", inst, replace=True)
            with db.tx() as c:
                cur = c.execute(
                    "INSERT OR IGNORE INTO approvals (permanent_id, academic_year, application_id, fno, date_of_approval,"
                    " letter_printed, letter_kind, source_sha, source_url, source_pages, deficiencies) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (pid, ay, L.application_no, L.get("fno"), L.get("date_of_approval"), L.get("letter_printed"),
                     L.get("kind"), sha, meta.get("source_url", f.name), json.dumps(L.pages), json.dumps(L.deficiencies)))
                if cur.rowcount == 0:
                    stats["duplicate_letters"] += 1
                    continue
                aid = cur.lastrowid
                for crs in L.courses:
                    c.execute("INSERT INTO approval_courses VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                              (aid, crs.level, crs.program, crs.course, None, crs.affiliating_body, crs.intake_prev,
                               crs.intake_curr, crs.nri, crs.fn, int(crs.is_new)))

    inst_n = db.q1("SELECT COUNT(*) n FROM institutions WHERE source='public_eoa'")["n"]
    appr_n = db.q1("SELECT COUNT(*) n FROM approvals WHERE source_url != ''")["n"]
    print(f"files={stats['files']} letters={stats['letters']} with_courses={stats['letters_with_courses']} "
          f"course_rows={stats['course_rows']} missing_core={stats['letters_missing_core']} dup={stats['duplicate_letters']}")
    print(f"institutions={inst_n} approvals={appr_n}")
    for name, err in failures:
        print("FAIL", name, err)

    # Cross-year consistency on real data: letter(Y+1).intake_prev must equal letter(Y).intake_curr
    checked = mismatched = 0
    rows = db.q("SELECT a.permanent_id, a.academic_year, c.course, c.intake_prev, c.intake_curr, c.is_new "
                "FROM approvals a JOIN approval_courses c ON c.approval_id=a.id")
    idx = defaultdict(dict)
    for r in rows:
        idx[(r["permanent_id"], r["academic_year"])][r["course"].upper()] = r
    for (pid, ay), courses in idx.items():
        prev_ay = f"{int(ay[:4]) - 1}-{str(int(ay[:4]))[-2:]}"
        prev = idx.get((pid, prev_ay))
        if not prev:
            continue
        for course, r in courses.items():
            if r["intake_prev"] is None or course not in prev:
                continue
            checked += 1
            if prev[course]["intake_curr"] != r["intake_prev"]:
                mismatched += 1
                print(f"  cross-year mismatch {pid} {course}: {prev_ay} letter says {prev[course]['intake_curr']}, {ay} letter says prev={r['intake_prev']}")
    print(f"cross-year course checks={checked} mismatches={mismatched}")


if __name__ == "__main__":
    main()
