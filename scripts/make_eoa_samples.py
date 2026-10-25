"""Build the EoA-verifier sample set: genuine public letters + tampered copies of them.

The tampered copies reproduce what a forger does to a real approval letter (raise an intake figure):
  * white-box + retype, incremental save (typical free online editor)
  * true redaction + retype + full re-save (more careful forger)
Also writes data/corpus_stats.json describing the real public corpus.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
logging.disable(logging.CRITICAL)

import pymupdf  # noqa: E402

from app import db  # noqa: E402
from app.config import DATA, EOA_DIR  # noqa: E402
from app.forensics import pdf as F  # noqa: E402

OUT = DATA / "samples"
GENUINE = ["ncr_christuniversity_in__4860e72bfc.pdf", "soe_cusat_ac_in__c73b7246c4.pdf", "www_mvsrec_edu_in__9af7587e9f.pdf",
           "patnawomenscollege_in__a27b0ce6fd.pdf", "skcet_ac_in__614b70fae2.pdf", "www_pondiuni_edu_in__4b657425c5.pdf"]


def course_intake(raw: bytes):
    """Return (page_no, old, new) for the first course row's approved-intake figure."""
    d = pymupdf.open(stream=raw, filetype="pdf")
    p = d[0]
    tabs = p.find_tables()
    for t in tabs.tables:
        rows = t.extract()
        if not rows or not any("Intake" in (c or "") for c in rows[0]):
            continue
        last = len(rows[0]) - 1
        intake_cols = [i for i, c in enumerate(rows[0]) if c and "Intake" in c]
        col = intake_cols[-1] if intake_cols else last
        for r in rows[1:]:
            v = (r[col] or "").strip()
            if v.isdigit() and int(v) > 0:
                return 0, v, str(int(v) * 2)
    return None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((EOA_DIR / "manifest.json").read_text("utf-8"))
    by_file = {v["file"]: v for v in manifest.values()}
    samples = []
    for i, name in enumerate(GENUINE):
        raw = (EOA_DIR / name).read_bytes()
        inst = name.split("__")[0].replace("_", ".")
        samples.append({"id": f"real{i}", "file": f"real{i}.pdf", "kind": "genuine", "label": f"Public EoA letter ({inst})",
                        "source_url": by_file[name]["source_url"]})
        (OUT / f"real{i}.pdf").write_bytes(raw)
        if i < 3:
            hit = course_intake(raw)
            if not hit:
                continue
            pg, old, new = hit
            try:
                t1 = _whiteout_cell(raw, old, new)
                (OUT / f"tamperA{i}.pdf").write_bytes(t1)
                samples.append({"id": f"tamperA{i}", "file": f"tamperA{i}.pdf", "kind": "tampered",
                                "label": f"Same letter, intake {old}→{new} by white-box edit ({inst})", "source_url": None})
                t2 = _redact_cell(raw, old, new)
                (OUT / f"tamperB{i}.pdf").write_bytes(t2)
                samples.append({"id": f"tamperB{i}", "file": f"tamperB{i}.pdf", "kind": "tampered",
                                "label": f"Same letter, intake {old}→{new} by redact + re-save ({inst})", "source_url": None})
            except Exception as e:  # noqa: BLE001
                print("tamper failed", name, e)
    # a real letter that was re-processed by a third-party tool before being posted (not tampered)
    samples.append({"id": "reproc", "file": "reproc.pdf", "kind": "reprocessed", "label": "Public letter re-saved via iLovePDF before posting",
                    "source_url": by_file["patnawomenscollege_in__a27b0ce6fd.pdf"]["source_url"]})
    (OUT / "reproc.pdf").write_bytes((EOA_DIR / "patnawomenscollege_in__a27b0ce6fd.pdf").read_bytes())
    samples = [s for s in samples if not (s["id"] == "real3")]   # patna duplicate shown as 'reproc'
    (OUT / "samples.json").write_text(json.dumps(samples, indent=1), "utf-8")
    print(f"{len(samples)} samples")
    corpus_stats()


def _target_rect(page, old):
    """The intake cell: the last occurrence of the figure on the first course row band."""
    hits = page.search_for(old)
    return hits[1] if len(hits) > 1 else hits[0]


def _whiteout_cell(raw: bytes, old: str, new: str) -> bytes:
    import os, tempfile
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "x.pdf"); open(p, "wb").write(raw)
        d = pymupdf.open(p); page = d[0]
        r = _target_rect(page, old)
        page.draw_rect(r + (-0.8, -0.8, 0.8, 0.8), color=None, fill=(1, 1, 1), overlay=True)
        page.insert_text((r.x0, r.y1 - 1.6), new, fontsize=r.height * 0.78, fontname="helv")
        d.saveIncr(); d.close()
        return open(p, "rb").read()


def _redact_cell(raw: bytes, old: str, new: str) -> bytes:
    d = pymupdf.open(stream=raw, filetype="pdf"); page = d[0]
    r = _target_rect(page, old)
    page.add_redact_annot(r, fill=(1, 1, 1)); page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)
    page.insert_text((r.x0, r.y1 - 1.6), new, fontsize=r.height * 0.78, fontname="helv")
    return d.tobytes(garbage=4, deflate=True)


def corpus_stats() -> None:
    prod, kinds, revs = Counter(), Counter(), Counter()
    files = sorted(EOA_DIR.glob("*.pdf"))
    for f in files:
        raw = f.read_bytes()
        m = pymupdf.open(stream=raw, filetype="pdf").metadata or {}
        pp = F.producer_profile(m)
        prod[(m.get("producer") or "?")[:40]] += 1
        kinds["original portal output" if pp["producer"] in ("Oracle BI Publisher 11.1.1.9.0", "Oracle Analytics Publisher")
              else ("scanned" if "scan" in pp["producer"].lower() else "re-processed by another tool")] += 1
        rv = F.revisions(raw)
        revs["linearized (not an edit)" if rv["linearized"] and rv["eof_markers"] > 1 and len(rv["revisions"]) == 1 else
             ("edited after generation" if len(rv["revisions"]) > 1 else "single revision")] += 1
    stats = {"files": len(files), "producers": prod.most_common(), "provenance": kinds.most_common(), "revisions": revs.most_common(),
             "letters": db.q1("SELECT COUNT(*) n FROM approvals WHERE source_url != ''")["n"],
             "institutions": db.q1("SELECT COUNT(*) n FROM institutions WHERE source='public_eoa'")["n"],
             "course_rows": db.q1("SELECT COUNT(*) n FROM approval_courses c JOIN approvals a ON a.id=c.approval_id WHERE a.source_url != ''")["n"],
             "years": [r["academic_year"] for r in db.q("SELECT DISTINCT academic_year FROM approvals WHERE source_url != '' ORDER BY academic_year")]}
    from app import ledger_checks
    cy = ledger_checks.cross_year()
    stats["cross_year"] = {"checks": cy["checks"], "issues": len(cy["issues"])}
    (DATA / "corpus_stats.json").write_text(json.dumps(stats, indent=1), "utf-8")
    print(json.dumps(stats, indent=1))


if __name__ == "__main__":
    main()
