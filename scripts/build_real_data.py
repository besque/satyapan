"""Build data/real/ (shipped with the repo) from public sources collected earlier.

Inputs (not in the repo; collected from public web pages, each with its URL and SHA-256):
  data/satyapan.sqlite      ledger parsed from public AICTE Extension of Approval letters
  data/raw/eoa/, data/raw/real/   the letter PDFs and two colleges' mandatory-disclosure documents
  data/raw/aph/APH_2024_27.pdf    AICTE Approval Process Handbook 2024-27
Outputs:
  data/real/institutions.json  institutions, their courses and every letter on record (with deficiencies and
                               the compliance time limit read from the letter itself)
  data/real/documents.json     certificate validity read from the colleges' own public postings
  data/real/aph_locs.json      where each cited clause sits in the handbook, and data/real/aph/p<N>.png pages
Run:  python scripts/build_real_data.py      (needs pymupdf; only to rebuild, the outputs are committed)
"""
from __future__ import annotations

import glob
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pymupdf
import yaml

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "real"
SETTINGS = yaml.safe_load((ROOT / "backend/app/settings.yaml").read_text(encoding="utf-8"))

REGION = {"South-West": "South-Western", "North-West": "North-Western", "South West": "South-Western"}
STATE_REGION = {
    "Karnataka": "South-Western", "Kerala": "South-Western", "Tamil Nadu": "Southern", "Puducherry": "Southern",
    "Telangana": "South-Central", "Andhra Pradesh": "South-Central", "Maharashtra": "Western", "Gujarat": "Western", "Goa": "Western",
    "Madhya Pradesh": "Central", "Chhattisgarh": "Central", "Uttar Pradesh": "Northern", "Uttarakhand": "Northern",
    "Punjab": "North-Western", "Haryana": "North-Western", "Delhi": "North-Western", "Himachal Pradesh": "North-Western",
    "Rajasthan": "North-Western", "Jammu and Kashmir": "North-Western", "West Bengal": "Eastern", "Odisha": "Eastern",
    "Jharkhand": "Eastern", "Bihar": "Eastern", "Assam": "North-Eastern", "Meghalaya": "North-Eastern",
}
WORDS = {"one": 1, "two": 2, "three": 3, "six": 6, "twelve": 12}
COMPLY = re.compile(r"shall\s+be\s+complied\s+within\s+([A-Za-z0-9]+)\s+(years?|months?)\s+from\s+the\s+date\s+of\s+issue", re.I)


def years_of(level: str, program: str) -> int:
    lv, pg = (level or "").upper(), (program or "").upper()
    if lv.startswith("DIPLOMA"):
        return 3
    if lv.startswith("INTEGRATED"):
        return 5
    if lv.startswith("FELLOW"):
        return 3
    if lv.startswith("POST"):
        return 2
    if "ARCHITECTURE" in pg:
        return 5
    if pg.startswith("MANAGEMENT") or pg.startswith("COMPUTER"):
        return 3
    return 4


def date_of(s: str | None) -> str | None:
    for fmt in ("%d-%b-%Y", "%d %B %Y", "%d-%B-%Y"):
        try:
            return datetime.strptime((s or "").strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return None


def pid_of(s: str) -> str | None:
    m = re.search(r"1-\d{5,}", s or "")
    return m.group(0) if m else None


def letter_files() -> dict:
    out = {}
    for f in glob.glob(str(DATA / "raw/eoa/*.pdf")) + glob.glob(str(DATA / "raw/real/*/*.pdf")):
        out[hashlib.sha256(Path(f).read_bytes()).hexdigest()] = f
    return out


def comply_within(path: str | None, pages: list[int] | None) -> dict | None:
    if not path:
        return None
    doc = pymupdf.open(path)
    idx = pages if pages else range(doc.page_count)
    text = " ".join(doc[i].get_text() for i in idx if i < doc.page_count)
    m = COMPLY.search(" ".join(text.split()))
    if not m:
        return None
    w = m.group(1).lower()
    n = WORDS.get(w) or (int(w) if w.isdigit() else None)
    unit = "months" if m.group(2).lower().startswith("month") else "years"
    return {"n": n, "unit": unit, "text": m.group(0).replace("  ", " ")}


def build_institutions() -> list[dict]:
    c = sqlite3.connect(DATA / "satyapan.sqlite")
    c.row_factory = sqlite3.Row
    files = letter_files()
    insts: dict[str, dict] = {}
    for r in c.execute("SELECT * FROM institutions WHERE source='public_eoa'"):
        pid = pid_of(r["permanent_id"])
        if not pid or not r["name"]:
            continue
        region = REGION.get(r["region"] or "", r["region"]) or STATE_REGION.get(r["state"] or "")
        insts[pid] = {"pid": pid, "name": r["name"], "trust": r["trust"], "address": r["address"], "state": r["state"],
                      "region": region, "inst_type": r["inst_type"], "est_year": r["est_year"], "letters": [], "programmes": []}
    for r in c.execute("SELECT * FROM approvals ORDER BY academic_year"):
        pid = pid_of(r["permanent_id"])
        if pid not in insts:
            continue
        defs = [x["particular"] for x in json.loads(r["deficiencies"] or "[]") if str(x.get("status", "")).lower() == "yes"]
        courses = [dict(x) for x in c.execute("SELECT level, program, course, intake_curr, is_new FROM approval_courses WHERE approval_id=?", (r["id"],))]
        path = files.get(r["source_sha"])
        within = comply_within(path, json.loads(r["source_pages"] or "[]")) if defs else None
        insts[pid]["letters"].append({
            "ay": r["academic_year"], "kind": r["letter_kind"], "application_no": r["application_id"],
            "issued_on": date_of(r["date_of_approval"]), "printed_on": date_of(r["letter_printed"]),
            "deficiencies": list(dict.fromkeys(defs)), "comply_within": within, "source_url": r["source_url"], "sha256": r["source_sha"],
            "courses": len(courses), "intake": sum(x["intake_curr"] or 0 for x in courses),
            "new_courses": sum(1 for x in courses if x["is_new"])})
        if courses:
            insts[pid]["programmes"] = [{"level": x["level"], "program": x["program"], "course": x["course"],
                                         "years": years_of(x["level"], x["program"]), "intake": x["intake_curr"]} for x in courses]
    out = [i for i in insts.values() if i["letters"]]
    for i in out:   # several public PDFs repeat the same letter: keep one per academic year
        seen, keep = set(), []
        for l in sorted(i["letters"], key=lambda x: (x["ay"], x["issued_on"] or "")):
            if l["ay"] in seen:
                keep[-1] = l if len(l["deficiencies"]) >= len(keep[-1]["deficiencies"]) else keep[-1]
                continue
            seen.add(l["ay"])
            keep.append(l)
        i["letters"] = keep
    return sorted(out, key=lambda x: x["name"])


def build_documents() -> list[dict]:
    """Validity facts read from the colleges' own postings (Satyapan's checks), worded as observations."""
    bms = json.loads((DATA / "raw/real/bmsce/manifest.json").read_text())["files"]
    dsce = json.loads((DATA / "raw/real/dsce/manifest.json").read_text())["files"]
    return [
        {"pid": "1-5884543", "doc_type": "fire_noc", "valid_until": "2024-03-15", "issued_on": "2022-03-15",
         "note": "Posted copy says 'renewed for a further period of two years' from 15 Mar 2022, so it was valid until 15 Mar 2024. A renewed certificate may exist but is not in the public disclosure.",
         "source_url": bms["fire_and_safety.pdf"]["source_url"], "sha256": bms["fire_and_safety.pdf"]["sha256"]},
        {"pid": "1-5884543", "doc_type": "occupancy", "issued_on": "2019-11-25", "valid_until": None, "partial": True,
         "note": "Posted copy is a partial occupancy certificate dated 25 Nov 2019; a partial or provisional certificate is accepted for two consecutive academic years only (Annexure-3).",
         "source_url": bms["occupancy_certificate.pdf"]["source_url"], "sha256": bms["occupancy_certificate.pdf"]["sha256"]},
        {"pid": "1-10575091", "doc_type": "fire_noc", "valid_until": None, "issued_on": None,
         "note": "The file the college links as its fire safety certificate does not show an issuing office, certificate number or validity date, so its validity cannot be read. Needs checking by hand.",
         "source_url": dsce["fire_and_safety.pdf"]["source_url"], "sha256": dsce["fire_and_safety.pdf"]["sha256"]},
    ]


def build_aph() -> dict:
    pdf = pymupdf.open(DATA / "raw/aph/APH_2024_27.pdf")
    (OUT / "aph").mkdir(parents=True, exist_ok=True)
    locs = {}
    for key, cite in SETTINGS["cites"].items():
        if cite.get("source") == "letter":
            continue
        q = " ".join(cite["quote"].split())
        found = None
        for probe in (q, q[:80], q[:50], q[:32]):
            for p in pdf:
                rects = p.search_for(probe)
                if rects:
                    printed = next((int(ln) for ln in p.get_text().splitlines()[:6] if ln.strip().isdigit()), None)
                    found = {"pdf_page": p.number, "printed_page": printed, "rects": [[round(v, 1) for v in (r.x0, r.y0, r.x1, r.y1)] for r in rects[:6]],
                             "page_size": [p.rect.width, p.rect.height]}
                    break
            if found:
                break
        if not found:
            print("  not found in the handbook:", key, q[:60])
            continue
        locs[key] = found
        img = OUT / "aph" / f"p{found['pdf_page']}.png"
        if not img.exists():
            pdf[found["pdf_page"]].get_pixmap(matrix=pymupdf.Matrix(1.35, 1.35)).save(img)
    return locs


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    insts = build_institutions()
    (OUT / "institutions.json").write_text(json.dumps(insts, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "documents.json").write_text(json.dumps(build_documents(), ensure_ascii=False, indent=1), encoding="utf-8")
    locs = build_aph()
    (OUT / "aph_locs.json").write_text(json.dumps(locs, indent=1), encoding="utf-8")
    n_letters = sum(len(i["letters"]) for i in insts)
    n_def = sum(1 for i in insts for l in i["letters"] if l["deficiencies"])
    print(f"{len(insts)} institutions, {n_letters} letters ({n_def} with deficiencies), {len(locs)} handbook clauses located")
    if len(locs) < len([k for k, v in SETTINGS["cites"].items() if v.get("source") != "letter"]):
        sys.exit(1)


if __name__ == "__main__":
    main()
