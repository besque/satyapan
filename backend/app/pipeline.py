"""Application processing pipeline: ingest -> classify -> extract -> forensics -> rules ->
source verification -> cross-institution network -> risk lane. Every step is audit-logged."""
from __future__ import annotations

import json
import logging
import mimetypes
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from . import audit, db, docmodel, graph
from .config import STORE
from .extract import docs as D
from .forensics import image as FI, pdf as FP
from .rules import engine
from .verify import connectors

logging.getLogger("pyhanko").setLevel(logging.CRITICAL)
logging.getLogger("pyhanko_certvalidator").setLevel(logging.CRITICAL)

ISSUER_GENERATED = {"fire_noc", "occupancy_certificate", "ter_receipt", "eoa_letter"}
# Documents that must not change after they are issued/sworn. Institution-written documents
# (disclosures, statements) are edited legitimately, so revision checks don't apply to them.
FIXED_AFTER_ISSUE = ISSUER_GENERATED | {"affidavit_2", "structural_stability"}
AY_START_MONTH = 8


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _trust_roots():
    try:
        from .synth import pki
        return pki.trust_roots()
    except Exception:  # noqa: BLE001
        return []


def ingest_file(app_id: str, filename: str, raw: bytes, declared: str | None, actor="system", role="system") -> dict:
    sha = docmodel.sha256_bytes(raw)
    ext = Path(filename).suffix.lower() or ".bin"
    (STORE / f"{sha}{ext}").write_bytes(raw)
    is_photo = declared == "infra_photo" and Path(filename).suffix.lower() in docmodel.IMAGE_EXT
    doc = docmodel.load(Path(filename), data=raw, allow_ocr=not is_photo)
    cls = D.classify(doc, declared)
    dtype = cls["doc_type"]
    if dtype == "unknown" and declared:
        dtype = declared
    extraction = D.extract(doc, dtype)
    forensics = FP.analyse(doc, _trust_roots()) if doc.kind == "pdf" else FI.analyse(raw)
    row = {
        "id": uuid.uuid4().hex[:12], "application_id": app_id, "declared_type": declared, "doc_type": dtype,
        "filename": filename, "sha256": sha, "mime": mimetypes.guess_type(filename)[0] or "application/octet-stream",
        "pages": len(doc.pages), "page_sizes": [[p.width, p.height] for p in doc.pages],
        "classification": cls, "extraction": extraction, "forensics": forensics, "created_at": _now(),
    }
    db.insert("documents", row)
    row["_pages"] = doc.pages
    audit.log(actor, role, "document.ingested", f"{app_id}/{row['id']}",
              {"file": filename, "sha256": sha, "declared": declared, "classified_as": dtype, "score": cls.get("score"),
               "ocr_pages": [p.number for p in doc.pages if p.ocr]})
    return row


def _ledger(pid: str, before_year: str) -> dict | None:
    inst = db.q1("SELECT * FROM institutions WHERE permanent_id=?", (pid,))
    if not inst:
        return None
    appr = db.q1("SELECT * FROM approvals WHERE permanent_id=? AND academic_year < ? ORDER BY academic_year DESC, id DESC LIMIT 1",
                 (pid, before_year))
    courses = db.q("SELECT * FROM approval_courses WHERE approval_id=?", (appr["id"],)) if appr else []
    return {"institution": inst, "academic_year": appr["academic_year"] if appr else None, "courses": courses,
            "source_url": appr["source_url"] if appr else None, "source": inst.get("source")}


def _ctx(app: dict, form: dict, docs: list[dict]) -> dict:
    by_type: dict[str, list] = {}
    for d in docs:
        by_type.setdefault(d["doc_type"], []).append(d)
    ay = form["academic_year"]
    return {
        "application_id": app["id"], "form": form, "academic_year": ay, "category": form.get("category", "EOA_SELF_DISCLOSURE"),
        "application_date": date.fromisoformat(str(form.get("application_date", date.today().isoformat()))[:10]),
        "ay_start": date(int(ay[:4]), AY_START_MONTH, 1), "docs": by_type, "all_docs": docs,
        "ledger": _ledger(form["permanent_id"], ay), "raw_by_doc": {},
        "inst_type": (db.q1("SELECT inst_type FROM institutions WHERE permanent_id=?", (form["permanent_id"],)) or {}).get("inst_type", ""),
    }


# ---------------------------------------------------------------------------- forensic findings

def forensic_findings(d: dict, ctx: dict) -> list[dict]:
    f = d.get("forensics") or {}
    out = []
    cite = {"ref": "Problem statement safeguard / Clause 2.3.5 (b)",
            "quote": "If any document submitted is found to be fraudulent, criminal case shall be filed against the Director/"}

    def add(rule_id, severity, title, detail, ev, conf):
        out.append({"rule_id": rule_id, "kind": "authenticity", "severity": severity, "status": "fail", "title": title,
                    "detail": detail + " This is a preliminary indicator for human verification, not proof of forgery.",
                    "evidence": [e for e in ev if e], "confidence": conf, "document_id": d["id"], "citation": cite,
                    "remedy": "Verify the original with the issuing authority before drawing any conclusion."})

    if d["mime"] == "application/pdf" and d["doc_type"] not in FIXED_AFTER_ISSUE:
        return out
    if d["mime"] == "application/pdf":
        changes = [c for c in f.get("revision_diff") or [] if c.get("type") == "text_changed"]
        if changes:
            ev = [{"doc_id": d["id"], "page": c["page"], "bbox": c["bbox"], "kind": "forensic",
                   "label": f"Revision change: '{c['before'] or '(nothing)'}' -> '{c['after']}'"} for c in changes if c.get("bbox")]
            add("FOR-REVISION", "critical", "Text changed in a later revision of the PDF",
                f"The file contains {len(f['revisions']['revisions'])} saved revisions; the earlier revision was recovered and {len(changes)} text change(s) were found.",
                ev, 0.95)
        for h in f.get("hidden_text") or []:
            add("FOR-WHITEOUT", "critical", "Original text hidden under a white box",
                f"Text '{h['covered_text']}' is painted over by an opaque white rectangle; '{h['overlay_text'] or '(nothing)'}' is drawn on top.",
                [{"doc_id": d["id"], "page": h["page"], "bbox": h["bbox"], "kind": "forensic",
                  "label": f"Hidden: '{h['covered_text']}'  Visible: '{h['overlay_text']}'"}], 0.95)
        ow = f.get("overlapping_words") or []
        if ow and not f.get("hidden_text"):
            add("FOR-OVERLAP", "high", "Two different values printed at the same position",
                "; ".join(f"'{o['texts'][0]}' / '{o['texts'][1]}'" for o in ow[:3]),
                [{"doc_id": d["id"], "page": o["page"], "bbox": o["bbox"], "kind": "forensic", "label": " vs ".join(o["texts"])} for o in ow[:5]], 0.85)
        st = f.get("structure")
        if st and st.get("deviations"):
            dv = "; ".join(f"{x['feature']} = {x['observed']} (genuine files: {x['expected']}, {x['expected_share']:.0%})" for x in st["deviations"])
            add("FOR-STRUCTURE", "high", f"File structure inconsistent with its stated generator '{st['producer']}'",
                f"Compared with {st['samples']} known-genuine files from the same generator: {dv}. Suggests the file was re-saved by another tool.",
                [{"doc_id": d["id"], "page": 0, "bbox": None, "kind": "forensic", "label": "whole-file structure"}], 0.75)
        meta = f.get("meta") or {}
        signed = bool(f.get("signatures"))
        if d["doc_type"] in ISSUER_GENERATED and meta.get("kind") == "editor" and not signed:
            add("FOR-EDITOR", "high", f"Issuer certificate re-saved with an editing program ({meta.get('producer')})",
                "The certificate was last saved with a PDF editor and carries no digital signature, so there is no record of who changed it "
                "or what was changed.", [{"doc_id": d["id"], "page": 0, "bbox": None, "kind": "forensic", "label": f"Producer: {meta.get('producer')}"}], 0.7)
        elif d["doc_type"] in ISSUER_GENERATED and meta.get("kind") == "editor":
            out.append({"rule_id": "FOR-EDITOR", "kind": "authenticity", "severity": "low", "status": "warn",
                        "title": f"Last saved with an editing tool ({meta.get('producer')})",
                        "detail": "Common when an institution scans and signs a copy, so on its own this is only a note.",
                        "evidence": [], "confidence": 0.4, "document_id": d["id"], "citation": cite,
                        "remedy": "Compare with the issuing authority's copy if anything else looks wrong."})
        for fa in (f.get("font_anomalies") or [])[:3]:
            add("FOR-FONT", "medium", "Value set in a font foreign to the document",
                f"'{fa['text']}' uses {fa['font']} {fa['size']}pt while the rest of the line uses {fa['line_font']} {fa['line_size']}pt.",
                [{"doc_id": d["id"], "page": fa["page"], "bbox": fa["bbox"], "kind": "forensic", "label": f"{fa['font']} vs {fa['line_font']}"}], 0.6)
    else:
        ex = f.get("exif") or {}
        lat, lon = ctx["form"].get("campus_lat"), ctx["form"].get("campus_lon")
        if ex.get("lat") is not None and lat is not None:
            km = engine._km(ex["lat"], ex["lon"], float(lat), float(lon))
            if km > 5:
                add("FOR-GPS", "high", f"Photo geotagged {km:.0f} km away from the campus",
                    f"EXIF GPS {ex['lat']:.4f}, {ex['lon']:.4f} (taken {ex.get('taken', '?')}, {ex.get('make', '')} {ex.get('model', '')}).",
                    [{"doc_id": d["id"], "page": 0, "bbox": None, "kind": "forensic", "label": f"GPS {ex['lat']:.4f}, {ex['lon']:.4f}"}], 0.8)
        elif ex.get("lat") is None:
            out.append({"rule_id": "FOR-NOGPS", "kind": "authenticity", "severity": "low", "status": "warn",
                        "title": "Photo has no location metadata", "detail": "Location cannot be confirmed from the file; may need EVC confirmation.",
                        "evidence": [], "confidence": 0.4, "document_id": d["id"], "citation": cite, "remedy": "Ask for geotagged photographs."})
        if f.get("edited_with"):
            add("FOR-PHOTOEDIT", "medium", f"Photo processed with {f['edited_with']}", "EXIF Software tag shows an image editor.", [], 0.5)
    return out


def _wrong_slot(d: dict) -> bool:
    decl = d.get("declared_type")
    if not decl or decl == "infra_photo" or decl not in D.DOC_TYPES:
        return False
    cls = d.get("classification") or {}
    det = cls.get("doc_type")
    if det == "unknown":
        return True
    return det != decl and cls.get("score", 0) >= 0.55


def _apply_wrong_slots(findings: list[dict], wrong: list[dict]) -> list[dict]:
    if not wrong:
        return findings
    rules = {r["id"]: r for r in engine.ruleset()["rules"]}
    missing_rule = {r["params"]["doc_type"]: rid for rid, r in rules.items() if r["type"] == "document_present"}
    replaced = {missing_rule.get(d["declared_type"]) for d in wrong} | {"DOC-SLOT"}
    out = [f for f in findings if f["rule_id"] not in replaced]
    for d in wrong:
        decl = d["declared_type"]
        name = D.PLAIN.get(decl, decl.replace("_", " "))
        cls = d.get("classification") or {}
        det = cls.get("doc_type")
        if det and det != "unknown":
            other = D.PLAIN.get(det, det.replace("_", " "))
            detail = f"The file '{d['filename']}' was uploaded as the {name}, but it is actually the {other}."
            ev = [{"doc_id": d["id"], "doc_type": decl, "page": e["page"], "bbox": e["bbox"], "label": f"shows it is the {other}: '{e['phrase']}'",
                   "kind": "classifier"} for e in (cls.get("evidence") or [])[:3]]
        else:
            detail = (f"The file '{d['filename']}' was uploaded as the {name}, but it does not look like one: "
                      f"no issuing office, certificate number or validity date could be found in it.")
            ev = [{"doc_id": d["id"], "doc_type": decl, "page": 0, "bbox": None, "label": "whole document", "kind": "classifier"}]
        rule = rules.get(missing_rule.get(decl, ""), {})
        out.append({"rule_id": "WRONG-DOC", "kind": "deficiency", "severity": "high", "status": "fail",
                    "title": f"Wrong document uploaded as {name}", "detail": detail, "evidence": ev, "document_id": d["id"],
                    "remedy": rule.get("remedy") or f"Upload the correct {name}.",
                    "citation": {**rule.get("cite", {}), "loc": rule.get("cite_loc")} if rule else {}})
    return out


# ---------------------------------------------------------------------------- orchestration

SEV_W = {"critical": 40, "high": 15, "medium": 6, "low": 2}


def _lane(findings: list[dict], verifs: list[dict]) -> tuple[str, float, dict]:
    red = [f for f in findings if f["status"] == "fail" and (f["kind"] in ("authenticity", "network") and f["severity"] in ("critical", "high"))]
    red += [f for f in findings if f["kind"] == "verification" and f["status"] == "fail" and f["severity"] == "critical"]
    defic = [f for f in findings if f["status"] == "fail" and (f["kind"] == "deficiency" or (f["kind"] == "verification" and f["severity"] != "critical"))]
    soft = [f for f in findings if f["status"] in ("warn", "manual") and f["severity"] != "low"] + [v for v in verifs if v["status"] in ("pending", "source_unavailable", "manual_review")]
    risk = sum(SEV_W.get(f["severity"], 3) for f in findings if f["status"] == "fail") + 3 * len(soft)
    if red:
        lane = "red"
    elif defic or soft:
        lane = "amber"
    else:
        lane = "green"
    summary = {"authenticity": len([f for f in findings if f["kind"] == "authenticity" and f["status"] == "fail"]),
               "network": len([f for f in findings if f["kind"] == "network" and f["status"] == "fail"]),
               "deficiencies": len(defic), "warnings": len([f for f in findings if f["status"] == "warn"]),
               "manual": len([f for f in findings if f["status"] == "manual"]),
               "verifications": {s: len([v for v in verifs if v["status"] == s]) for s in
                                 ("verified", "mismatch", "expired", "pending", "source_unavailable", "manual_review")},
               "passed": len([f for f in findings if f["status"] == "pass"])}
    return lane, float(min(100, risk)), summary


def process(form: dict, files: list[tuple[str, bytes, str | None]], source: str = "upload", actor="system", role="system",
            institution: dict | None = None, prev_approval: dict | None = None, defer_network=False) -> str:
    t0 = time.time()
    app_id = "APP-" + uuid.uuid4().hex[:8].upper()
    if institution:
        db.insert("institutions", {**{k: institution.get(k) for k in ("permanent_id", "name", "trust", "address", "state", "region",
                                                                     "inst_type", "est_year", "lat", "lon")}, "source": "synthetic", "extra": None},
                  replace=True)
    if prev_approval:
        with db.tx() as c:
            old = c.execute("SELECT id FROM approvals WHERE permanent_id=? AND academic_year=? AND (source_url IS NULL OR source_url='')",
                            (form["permanent_id"], prev_approval["academic_year"])).fetchall()
            for o in old:
                c.execute("DELETE FROM approval_courses WHERE approval_id=?", (o["id"],))
                c.execute("DELETE FROM approvals WHERE id=?", (o["id"],))
            cur = c.execute("INSERT INTO approvals (permanent_id, academic_year, application_id, fno, letter_kind, source_url) VALUES (?,?,?,?,?,?)",
                            (form["permanent_id"], prev_approval["academic_year"], "synthetic", "synthetic", "EoA", ""))
            for crs in prev_approval["courses"]:
                c.execute("INSERT INTO approval_courses VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                          (cur.lastrowid, crs["level"], crs["program"], crs["course"], None, crs.get("affiliating_body"),
                           None, crs["intake_curr"], "No", "No", 0))
    app = {"id": app_id, "permanent_id": form["permanent_id"], "category": form.get("category", "EOA_SELF_DISCLOSURE"),
           "academic_year": form["academic_year"], "form": form, "status": "processing", "lane": None, "risk": None,
           "summary": None, "created_at": _now(), "processed_at": None, "source": source}
    db.insert("applications", app)
    audit.log(actor, role, "application.received", app_id, {"permanent_id": form["permanent_id"], "files": [f[0] for f in files]})

    docs = []
    raws = {}
    for name, raw, declared in files:
        d = ingest_file(app_id, name, raw, declared, actor, role)
        docs.append(d)
        raws[d["id"]] = raw
    # A file uploaded under the wrong heading is reported once, clearly, and left out of every other
    # check - otherwise one mistake shows up as a dozen confusing failures (unreadable dates, issuer
    # lookups failing, "document missing"...).
    wrong = [d for d in docs if _wrong_slot(d)]
    checked = [d for d in docs if d not in wrong]
    ctx = _ctx(app, form, checked)
    ctx["raw_by_doc"] = raws

    findings = []
    for r in engine.evaluate(ctx):
        findings.append({**r, "kind": "deficiency", "document_id": next((e["doc_id"] for e in r.get("evidence", []) if e.get("doc_id")), None)})
    findings = _apply_wrong_slots(findings, wrong)
    audit.log("rules-engine", "system", "rules.evaluated", app_id,
              {"ruleset": engine.ruleset()["version"], "fail": [f["rule_id"] for f in findings if f["status"] == "fail"],
               "warn": [f["rule_id"] for f in findings if f["status"] == "warn"]})
    for d in checked:
        findings.extend(forensic_findings(d, ctx))

    verifs = []
    for d in checked:
        for v in connectors.run(d, ctx):
            v.update({"id": uuid.uuid4().hex[:12], "application_id": app_id, "document_id": d["id"]})
            if v["status"] in ("source_unavailable", "manual_review"):
                v["letter"] = connectors.draft_letter(v, d, ctx)
            verifs.append(v)
            db.insert("verifications", {"id": v["id"], "application_id": app_id, "document_id": d["id"], "connector": v["connector"],
                                        "status": v["status"], "source": v["source"], "simulated": int(v["simulated"]),
                                        "request": v["request"], "response": {"response": v["response"], "checks": v["checks"], "letter": v.get("letter"),
                                                                             "evidence": v["evidence"]},
                                        "detail": v["detail"], "ts": v["ts"]})
            audit.log(v["connector"], "connector", "verification.result", f"{app_id}/{d['id']}",
                      {"status": v["status"], "source": v["source"], "simulated": v["simulated"], "request": v["request"]})
            already = v["status"] == "expired" and any(f["status"] == "fail" and f["rule_id"].startswith("VAL-") and
                                                       (f.get("document_id") == d["id"]) for f in findings)
            if v["status"] in ("mismatch", "expired") and not already:      # don't repeat an expiry already reported
                findings.append({"rule_id": f"VER-{v['connector'].upper()}", "kind": "verification",
                                 "severity": "critical" if v["status"] == "mismatch" else "high", "status": "fail",
                                 "title": f"{'Source mismatch' if v['status'] == 'mismatch' else 'Expired per source'}: {D.DOC_TYPES.get(d['doc_type'], {}).get('title', d['doc_type'])}",
                                 "detail": v["detail"], "evidence": v["evidence"], "document_id": d["id"],
                                 "citation": {"ref": "Problem statement: verification through original issuing authorities", "quote": ""},
                                 "remedy": "Upload the certificate exactly as the issuing office gave it. If you think the office's record is wrong, contact that office.",
                                 "confidence": 0.9})

    if source != "precheck":   # an institution's dry run is not part of the scrutiny network
        graph.store_entities(app_id, graph.entities_for(app_id, form["permanent_id"], form, checked))
    _save_findings(app_id, findings)
    lane, risk, summary = _lane(findings, verifs)
    summary["seconds"] = round(time.time() - t0, 1)
    with db.tx() as c:
        c.execute("UPDATE applications SET status=?, lane=?, risk=?, summary=?, processed_at=? WHERE id=?",
                  ("processed", lane, risk, db.j(summary), _now(), app_id))
    audit.log("pipeline", "system", "application.processed", app_id, {"lane": lane, "risk": risk, "summary": summary})
    if not defer_network:
        refresh_network()
    return app_id


def _save_findings(app_id: str, findings: list[dict]) -> None:
    with db.tx() as c:
        c.execute("DELETE FROM findings WHERE application_id=? AND kind != 'network'", (app_id,))
        for f in findings:
            c.execute("INSERT INTO findings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      (uuid.uuid4().hex[:12], app_id, f.get("document_id"), f["rule_id"], f["kind"], f["severity"], f["status"],
                       f["title"], f.get("detail"), db.j({"items": f.get("evidence", []), "derivation": f.get("derivation")}),
                       db.j(f.get("citation")), f.get("remedy"), f.get("confidence"), _now()))


def refresh_network() -> None:
    """Recompute cross-institution findings for every application and re-derive lanes."""
    per_app = graph.findings_by_application()
    with db.tx() as c:
        c.execute("DELETE FROM findings WHERE kind='network'")
        for app_id, fs in per_app.items():
            for f in fs:
                c.execute("INSERT INTO findings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (uuid.uuid4().hex[:12], app_id, None, f["rule_id"], "network", f["severity"], f["status"], f["title"],
                           f["detail"], db.j({"items": f["evidence"]}), db.j(f["citation"]), f["remedy"], 0.85, _now()))
    for a in db.q("SELECT id FROM applications WHERE status='processed'"):
        fs = [{**r, "evidence": None} for r in db.q("SELECT * FROM findings WHERE application_id=?", (a["id"],))]
        vs = db.q("SELECT status FROM verifications WHERE application_id=?", (a["id"],))
        lane, risk, summary = _lane(fs, vs)
        old = db.unj(db.q1("SELECT summary FROM applications WHERE id=?", (a["id"],))["summary"], {})
        summary["seconds"] = old.get("seconds")
        with db.tx() as c:
            c.execute("UPDATE applications SET lane=?, risk=?, summary=? WHERE id=?", (lane, risk, db.j(summary), a["id"]))
    audit.log("network", "system", "network.refreshed", "all", {"applications_with_links": len(per_app)})


def import_synthetic(root: Path, actor="seed", role="system") -> list[str]:
    manifest = json.loads((root / "manifest.json").read_text("utf-8"))
    ids = []
    for a in manifest["applications"]:
        d = root / a["dir"]
        form = json.loads((d / "application.json").read_text("utf-8"))
        files = [(f["file"], (d / f["file"]).read_bytes(), f["declared_type"]) for f in a["files"]]
        ids.append(process(form, files, source="synthetic", actor=actor, role=role, institution=a["institution"],
                           prev_approval=a["prev_approval"], defer_network=True))
        print(f"  processed {a['dir']} -> {ids[-1]}", flush=True)
    refresh_network()
    return ids
