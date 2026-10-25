"""Evaluation harness -> data/eval_report.json (shown on the Evaluation screen).

Part A  synthetic applications with randomly planted defects (fresh seed, isolated DB + registry):
        detection rate per defect type, unexplained alerts, lane accuracy, field-extraction accuracy (text vs OCR)
Part B  real public EoA letters: parser coverage, cross-year consistency, tamper detection on real letters
        (two attack styles) and false alarms on the untouched originals.

  python scripts/evaluate.py [--n 36] [--real 30]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "data" / "eval"
EVAL_DIR.mkdir(parents=True, exist_ok=True)
os.environ["SATYAPAN_DB"] = str(EVAL_DIR / "eval.sqlite")
os.environ["SATYAPAN_ISSUERS"] = str(EVAL_DIR / "eval_issuers.sqlite")
for f in EVAL_DIR.glob("eval*.sqlite*"):
    f.unlink()
sys.path.insert(0, str(ROOT / "backend"))
logging.disable(logging.CRITICAL)

from app import db, docmodel, pipeline  # noqa: E402
from app.config import DATA, EOA_DIR  # noqa: E402

DETECTORS = {
    "FIRE_EXPIRED": ["VAL-FIRE", "VER-FIRE_NOC_REGISTRY"], "TAMPER_WHITEOUT": ["FOR-WHITEOUT", "FOR-REVISION", "FOR-OVERLAP"],
    "REGISTRY_MISMATCH": ["VER-FIRE_NOC_REGISTRY", "VER-OCCUPANCY_REGISTRY", "VER-ESTAMP_REGISTRY", "VER-ICAI_UDIN"],
    "FSR_SHORTFALL": ["NORM-FSR"], "CADRE_SHORTFALL": ["NORM-CADRE"], "TER_UNDERPAID": ["NORM-TER"],
    "MISSING_DOC": ["DOC-MAP", "DOC-SSC", "DOC-FIRE", "DOC-OC", "DOC-AFFIDAVIT", "DOC-TER", "DOC-AUDIT"],
    "SSC_EXPIRED": ["VAL-SSC"], "STAMP_VALUE_LOW": ["VAL-STAMP", "VER-ESTAMP_REGISTRY"], "ESTAMP_NOT_FOUND": ["VER-ESTAMP_REGISTRY"],
    "NAME_MISMATCH": ["XDOC-NAME-OC", "XDOC-TRUST-OC"], "TAMPER_RESAVE": ["FOR-STRUCTURE", "FOR-EDITOR", "FOR-REVISION", "FOR-OVERLAP"],
    "INTAKE_EXCEEDS": ["LEDGER-INTAKE"], "SIGNATURE_BROKEN": ["VAL-DSC", "VER-DIGITAL_SIGNATURE"], "UDIN_NOT_FOUND": ["VER-ICAI_UDIN"],
    "PHOTO_GPS_MISMATCH": ["FOR-GPS"], "GHOST_FACULTY": ["NET-FACULTY", "NET-FACULTY_ID", "NET-FACULTY_PAN"], "PHOTO_REUSE": ["NET-PHOTO"],
    "DOC_REUSE": ["NET-REF_FIRE_NOC", "NET-DOC_SHA"], "ESTAMP_REUSE": ["NET-REF_AFFIDAVIT_2"],
}
# findings that a planted defect legitimately causes downstream (not false alarms)
CONSEQUENCES = {
    "INTAKE_EXCEEDS": ["NORM-FSR", "NORM-CADRE", "NORM-AREA", "NORM-TER", "XDOC-AREA-OC"],
    "TAMPER_WHITEOUT": ["VAL-FIRE", "FOR-STRUCTURE"], "SIGNATURE_BROKEN": ["FOR-REVISION", "FOR-WHITEOUT", "FOR-OVERLAP", "FOR-STRUCTURE"],
    "DOC_REUSE": ["VER-FIRE_NOC_REGISTRY", "VAL-FIRE", "VER-QR_PAYLOAD", "FOR-STRUCTURE"], "TAMPER_RESAVE": ["VER-QR_PAYLOAD", "XDOC-AREA-OC", "NORM-AREA"],
    "FSR_SHORTFALL": ["NORM-CADRE"], "CADRE_SHORTFALL": [], "SSC_MISSING": [], "ESTAMP_REUSE": ["VER-ESTAMP_REGISTRY"],
    "GHOST_FACULTY": [], "PHOTO_REUSE": [],
}
LABEL = {"FIRE_EXPIRED": "Expired fire NOC", "TAMPER_WHITEOUT": "Date white-boxed & retyped", "REGISTRY_MISMATCH": "Document differs from issuer record",
         "FSR_SHORTFALL": "Faculty:student ratio shortfall", "CADRE_SHORTFALL": "Cadre ratio shortfall", "TER_UNDERPAID": "TER under-paid",
         "MISSING_DOC": "Required document missing", "SSC_EXPIRED": "Structural certificate > 5 years", "STAMP_VALUE_LOW": "e-stamp below Rs.100",
         "ESTAMP_NOT_FOUND": "e-stamp not in SHCIL register", "NAME_MISMATCH": "Certificate in another name",
         "TAMPER_RESAVE": "Value edited & re-saved", "INTAKE_EXCEEDS": "Intake above approved", "SIGNATURE_BROKEN": "Edited after DSC signing",
         "UDIN_NOT_FOUND": "UDIN not registered", "PHOTO_GPS_MISMATCH": "Photos geotagged elsewhere", "GHOST_FACULTY": "Faculty on two rosters",
         "PHOTO_REUSE": "Photo re-used from another institution", "DOC_REUSE": "Another institution's NOC re-used", "ESTAMP_REUSE": "e-stamp re-used"}
SERIOUS = {"TAMPER_WHITEOUT", "REGISTRY_MISMATCH", "TAMPER_RESAVE", "SIGNATURE_BROKEN", "UDIN_NOT_FOUND", "ESTAMP_NOT_FOUND",
           "PHOTO_GPS_MISMATCH", "GHOST_FACULTY", "PHOTO_REUSE", "DOC_REUSE", "ESTAMP_REUSE"}


def norm_val(v):
    if v is None:
        return None
    s = str(v).strip()
    try:
        return round(float(s.replace(",", "")), 1)
    except ValueError:
        return re.sub(r"\s+", " ", s).upper().replace(" ", "")


def part_a(n: int) -> dict:
    from app.synth import generate
    from app.verify import registry
    root = DATA / "synthetic" / "eval"
    t0 = time.time()
    m = generate.generate("random", n=n, seed=4242, out_root=root)
    registry.set_available("fire_tn", True)
    # ledger copy of the real corpus isn't needed for synthetic institutions (their record comes with the set)
    ids = pipeline.import_synthetic(root, actor="eval")
    gen_secs = time.time() - t0
    per = defaultdict(lambda: {"planted": 0, "detected": 0, "by": Counter()})
    unexplained, lanes, clean_unexplained, n_clean = Counter(), Counter(), 0, 0
    ext = defaultdict(lambda: {"n": 0, "ok": 0})
    misses = []
    for a, aid in zip(m["applications"], ids):
        fails = db.q("SELECT rule_id, kind, severity FROM findings WHERE application_id=? AND status='fail'", (aid,))
        rules = {f["rule_id"] for f in fails}
        codes = [t["code"] for t in a["truth"]]
        explained = set()
        for t in a["truth"]:
            c = t["code"]
            det = [r for r in DETECTORS.get(c, []) if r in rules]
            if c == "MISSING_DOC":
                want = {"satellite_map": "DOC-MAP", "structural_stability": "DOC-SSC"}.get(t["doc"])
                det = [want] if want in rules else []
            per[c]["planted"] += 1
            if det:
                per[c]["detected"] += 1
                per[c]["by"].update(det)
            else:
                misses.append({"app": a["dir"], "code": c, "detail": t["detail"]})
            explained |= set(DETECTORS.get(c, [])) | set(CONSEQUENCES.get(c, []))
        stray = [r for r in rules if r not in explained]
        unexplained.update(stray)
        if not codes:
            n_clean += 1
            clean_unexplained += bool(stray)
        exp_lane = "red" if any(c in SERIOUS for c in codes) else ("amber" if codes else "green")
        got = db.q1("SELECT lane FROM applications WHERE id=?", (aid,))["lane"]
        lanes[(exp_lane, got)] += 1
        # extraction accuracy against values printed on the documents
        docs = {d["doc_type"]: d for d in db.q("SELECT doc_type, extraction, forensics FROM documents WHERE application_id=?", (aid,))}
        for dt, fields in a.get("doc_truth", {}).items():
            d = docs.get(dt)
            if not d:
                continue
            exd, fx = db.unj(d["extraction"], {}), db.unj(d["forensics"], {})
            mode = "ocr" if fx.get("ocr_pages") else "text"
            for fname, truth in fields.items():
                key = {"estamp_no": "estamp_cert_no", "engineer_reg": "engineer_reg_no"}.get(fname, fname)
                got_v = (exd.get(key) or {}).get("value") if isinstance(exd.get(key), dict) else None
                ext[mode]["n"] += 1
                tv, gv = norm_val(truth), norm_val(got_v)
                if isinstance(tv, str) and isinstance(gv, str) and len(tv) >= 10 and key in ("premises", "first_party", "owner"):
                    ok = tv == gv
                else:
                    ok = tv == gv
                ext[mode]["ok"] += int(ok)
    secs = [db.unj(r["summary"], {}).get("seconds") for r in db.q("SELECT summary FROM applications")]
    secs = [s for s in secs if s]
    return {
        "applications": len(ids), "planted_defects": sum(v["planted"] for v in per.values()),
        "clean_applications": n_clean, "clean_with_unexplained_alert": clean_unexplained,
        "per_defect": sorted([{"code": c, "label": LABEL.get(c, c), "planted": v["planted"], "detected": v["detected"],
                               "recall": round(v["detected"] / v["planted"], 3), "detected_by": dict(v["by"])} for c, v in per.items()],
                             key=lambda x: (x["recall"], x["code"])),
        "misses": misses[:30], "unexplained_alerts": dict(unexplained.most_common()),
        "lanes": [{"expected": e, "got": g, "n": n_} for (e, g), n_ in sorted(lanes.items())],
        "extraction": {k: {**v, "accuracy": round(v["ok"] / v["n"], 3) if v["n"] else None} for k, v in ext.items()},
        "avg_seconds": round(sum(secs) / len(secs), 1) if secs else None, "wall_seconds": round(gen_secs, 1),
    }


def part_b(n_real: int) -> dict:
    """Real public EoA letters: tamper detection and false alarms on genuine originals."""
    import pymupdf
    from app.forensics import pdf as FP
    sys.path.insert(0, str(ROOT / "scripts"))
    from make_eoa_samples import _redact_cell, _whiteout_cell, course_intake

    gens = {"Oracle BI Publisher 11.1.1.9.0", "Oracle Analytics Publisher"}
    picks = []
    for f in sorted(EOA_DIR.glob("*.pdf")):
        raw = f.read_bytes()
        d = pymupdf.open(stream=raw, filetype="pdf")
        if (d.metadata or {}).get("producer") in gens and d.page_count <= 8 and len(FP.revisions(raw)["revisions"]) == 1:
            picks.append((f, raw))
    picks = picks[:n_real]

    def alerts(raw: bytes) -> list[str]:
        doc = docmodel.load(Path("x.pdf"), data=raw, allow_ocr=False)
        fx = FP.analyse(doc)
        return [x["rule_id"] for x in pipeline.forensic_findings({"id": "x", "mime": "application/pdf", "doc_type": "eoa_letter", "forensics": fx}, {"form": {}})]

    genuine_flagged, att = 0, {"whiteout_incremental": [0, 0], "redact_resave": [0, 0]}
    by_signal = Counter()
    for f, raw in picks:
        a = alerts(raw)
        genuine_flagged += bool(a)
        hit = course_intake(raw)
        if not hit:
            continue
        _, old, new = hit
        for name, fn in (("whiteout_incremental", _whiteout_cell), ("redact_resave", _redact_cell)):
            try:
                t = fn(raw, old, new)
            except Exception:  # noqa: BLE001
                continue
            r = alerts(t)
            att[name][0] += 1
            att[name][1] += bool(r)
            by_signal.update(set(r))
    stats = json.loads((DATA / "corpus_stats.json").read_text("utf-8")) if (DATA / "corpus_stats.json").exists() else {}
    return {"genuine_letters_tested": len(picks), "genuine_false_alarms": genuine_flagged,
            "attacks": {k: {"tested": v[0], "detected": v[1], "rate": round(v[1] / v[0], 3) if v[0] else None} for k, v in att.items()},
            "signals": dict(by_signal), "corpus": stats,
            "note": "Tampered copies change one approved-intake figure on page 1, as a forger raising intake would. Detection here is from "
                    "file forensics alone; in the product the same letter is also checked against the AICTE record, which catches the change regardless."}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=36)
    ap.add_argument("--real", type=int, default=30)
    args = ap.parse_args()
    a = part_a(args.n)
    print(json.dumps({k: a[k] for k in ("applications", "planted_defects", "clean_applications", "clean_with_unexplained_alert", "extraction", "avg_seconds")}, indent=1))
    for x in a["per_defect"]:
        print(f"  {x['code']:20} {x['detected']}/{x['planted']}")
    print("  unexplained:", a["unexplained_alerts"])
    b = part_b(args.real)
    print(json.dumps({k: b[k] for k in ("genuine_letters_tested", "genuine_false_alarms", "attacks", "signals")}, indent=1))
    rep = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "synthetic": a, "real": b,
           "assumption_manual_minutes": {"value": 45, "note": "Assumed time for an officer to scrutinise 7 documents + roster by hand; "
                                         "an assumption for comparison, not a measurement."}}
    (DATA / "eval_report.json").write_text(json.dumps(rep, indent=1, default=str), "utf-8")
    print("wrote", DATA / "eval_report.json")


if __name__ == "__main__":
    main()
