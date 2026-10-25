"""Verification against original issuing authorities / authorised records.

Status vocabulary (from the problem statement): verified, mismatch, expired, pending,
source_unavailable, manual_review. Every result records source, timestamp, request and response.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import cv2
import numpy as np
import pymupdf

from .. import db
from ..rules.engine import name_score
from . import registry

STATE_CODE = {"Telangana": "ts", "Maharashtra": "mh", "Tamil Nadu": "tn", "Karnataka": "ka"}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _val(doc, key):
    f = (doc.get("extraction") or {}).get(key)
    return f.get("value") if isinstance(f, dict) else None


def _result(connector, status, source, request, response, detail, simulated=True, checks=None, evidence=None):
    return {"connector": connector, "status": status, "source": source, "simulated": simulated, "ts": _now(),
            "request": request, "response": response, "detail": detail, "checks": checks or [], "evidence": evidence or []}


def _compare(checks: list, label: str, doc_val, src_val, ok: bool):
    checks.append({"field": label, "document": doc_val, "source": src_val, "match": ok})


def _registry_doc(doc, ctx, connector, source_key, key_field, comparisons, expiry_field=None):
    key = _val(doc, key_field)
    if not key:
        return _result(connector, "manual_review", source_key, {}, None,
                       f"Reference number ({key_field}) could not be read from the document, so it cannot be looked up.", simulated=True)
    res = registry.lookup(source_key, str(key))
    req = {key_field: key}
    if not res["available"]:
        return _result(connector, "source_unavailable", res["source"], req, None,
                       f"{res['source']} did not respond. Routed to manual confirmation; a verification request letter has been drafted.")
    if not res["found"]:
        return _result(connector, "mismatch", res["source"], req, {"found": False},
                       f"{key} does not exist in the issuing authority's register.",
                       evidence=[_ev(doc, key_field, f"{key} - not found at source")])
    rec, checks, ev = res["record"], [], []
    for label, doc_key, src_key, kind in comparisons:
        dv, sv = _val(doc, doc_key), rec.get(src_key)
        if dv is None or sv is None:
            continue
        if kind == "name":
            ok = name_score(str(dv), str(sv)) >= 86
        elif kind == "date":
            ok = str(dv)[:10] == str(sv)[:10]
        elif kind == "number":
            ok = abs(float(dv) - float(sv)) <= max(1.0, 0.01 * float(sv))
        else:
            ok = str(dv).strip().upper() == str(sv).strip().upper()
        _compare(checks, label, dv, sv, ok)
        if not ok:
            ev.append(_ev(doc, doc_key, f"Document: {dv} | Source: {sv}"))
    bad = [c for c in checks if not c["match"]]
    if bad:
        return _result(connector, "mismatch", res["source"], req, rec,
                       "Source record differs: " + "; ".join(f"{c['field']} (document '{c['document']}' vs source '{c['source']}')" for c in bad),
                       checks=checks, evidence=[e for e in ev if e])
    if expiry_field and rec.get(expiry_field) and date.fromisoformat(rec[expiry_field][:10]) < ctx["application_date"]:
        return _result(connector, "expired", res["source"], req, rec, f"Source confirms the certificate, but it expired on {rec[expiry_field][:10]}.",
                       checks=checks)
    return _result(connector, "verified", res["source"], req, rec, f"{key} confirmed by {res['source']}; {len(checks)} field(s) match.", checks=checks)


def _ev(doc, key, label):
    f = (doc.get("extraction") or {}).get(key)
    if not isinstance(f, dict) or not f.get("bbox"):
        return None
    return {"doc_id": doc["id"], "doc_type": doc["doc_type"], "page": f.get("page", 0), "bbox": f["bbox"], "label": label, "kind": "verification"}


# ---------------------------------------------------------------------------------- connectors

def fire(doc, ctx):
    st = STATE_CODE.get(ctx["form"].get("state"), "")
    return _registry_doc(doc, ctx, "fire_noc_registry", f"fire_{st}", "noc_no",
                         [("Premises", "premises", "premises", "name"), ("Valid up to", "valid_until", "valid_until", "date"),
                          ("Date of issue", "issue_date", "issue_date", "date")], expiry_field="valid_until")


def occupancy(doc, ctx):
    st = STATE_CODE.get(ctx["form"].get("state"), "")
    return _registry_doc(doc, ctx, "occupancy_registry", f"oc_{st}", "cert_no",
                         [("Premises", "premises", "premises", "name"), ("Owner", "owner", "owner", "name"),
                          ("Built-up area", "built_up_area", "built_up_area", "number"), ("Date of issue", "issue_date", "issue_date", "date")])


def estamp(doc, ctx):
    r = _registry_doc(doc, ctx, "estamp_registry", "estamp", "estamp_cert_no",
                      [("First party", "first_party", "first_party", "name"), ("Stamp duty (Rs.)", "stamp_value", "amount", "number")])
    return r


def udin(doc, ctx):
    return _registry_doc(doc, ctx, "icai_udin", "udin", "udin",
                         [("FRN", "frn", "frn", "exact"), ("Membership no.", "membership_no", "membership_no", "exact"),
                          ("Client", "trust_name", "client", "name")])


def engineer(doc, ctx):
    return _registry_doc(doc, ctx, "engineer_register", "engineers", "engineer_reg_no", [("Engineer", "engineer", "name", "name")])


def dsc(doc, ctx):
    sigs = (doc.get("forensics") or {}).get("signatures") or []
    if not sigs:
        return None
    s = sigs[0]
    signer = (s.get("signer") or "").replace("Common Name: ", "").split(",")[0] or "unknown signer"
    if s.get("legacy_algorithm"):
        return _result("digital_signature", "manual_review", "PAdES signature (pyHanko)", {"field": s.get("field")}, None,
                       f"Signed by {signer} using SHA-1, an outdated algorithm, so the signature cannot be validated.", simulated=False)
    if s.get("modified_after_signing"):
        return _result("digital_signature", "mismatch", "PAdES signature (pyHanko, local trust list)", {"field": s.get("field")}, s,
                       f"Signature by {signer} is valid for an earlier revision, but the file was changed after signing.", simulated=False)
    if s.get("bottom_line"):
        return _result("digital_signature", "verified", "PAdES signature (pyHanko, local trust list)", {"field": s.get("field")}, s,
                       f"Cryptographically valid signature by {signer}; covers the entire file.", simulated=False)
    return _result("digital_signature", "manual_review", "PAdES signature (pyHanko)", {"field": s.get("field")}, s,
                   f"Signature by {signer} could not be fully validated (trusted={s.get('trusted')}).", simulated=False)


def qr(doc, ctx):
    """Decode QR codes printed on the document and compare the payload with the printed reference."""
    raw = ctx["raw_by_doc"].get(doc["id"])
    if raw is None or doc.get("mime") != "application/pdf":
        return None
    pdf = pymupdf.open(stream=raw, filetype="pdf")
    det = cv2.QRCodeDetector()
    payloads = []
    for p in list(pdf)[:2]:
        pix = p.get_pixmap(matrix=pymupdf.Matrix(2.2, 2.2))
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)[:, :, :3]
        ok, data, pts, _ = det.detectAndDecodeMulti(np.ascontiguousarray(img))
        if ok:
            for dta, pt in zip(data, pts):
                if dta:
                    xs, ys = pt[:, 0] / 2.2, pt[:, 1] / 2.2
                    payloads.append({"data": dta, "page": p.number, "bbox": [float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())]})
    if not payloads:
        return None
    key_field = {"fire_noc": "noc_no", "occupancy_certificate": "cert_no", "affidavit_2": "estamp_cert_no", "ter_receipt": "txn_id"}.get(doc["doc_type"])
    printed = _val(doc, key_field) if key_field else None
    pl = payloads[0]
    ev = [{"doc_id": doc["id"], "doc_type": doc["doc_type"], "page": pl["page"], "bbox": pl["bbox"], "label": f"QR: {pl['data'][:60]}", "kind": "verification"}]
    ocr = bool((doc.get("forensics") or {}).get("ocr_pages"))
    if printed and ocr and str(printed).replace(" ", "") not in pl["data"] and _ocr_equiv(str(printed)) in _ocr_equiv(pl["data"]):
        return _result("qr_payload", "verified", "QR code printed on document", {"printed": printed}, {"qr": pl["data"]},
                       f"QR payload matches the printed reference (OCR read '{printed}'; the machine-readable QR gives the exact value).",
                       simulated=False, evidence=ev)
    if printed and str(printed).replace(" ", "") not in pl["data"].replace(" ", ""):
        return _result("qr_payload", "mismatch", "QR code printed on document", {"printed": printed}, {"qr": pl["data"]},
                       f"QR encodes '{pl['data']}', which does not contain the printed reference {printed}.", simulated=False, evidence=ev)
    return _result("qr_payload", "verified", "QR code printed on document", {"printed": printed}, {"qr": pl["data"]},
                   "QR payload is consistent with the printed reference number." + (" (Issuer URL lookup simulated.)" if "example" in pl["data"] else ""),
                   simulated=False, evidence=ev)


_OCR_MAP = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "|": "1", "S": "5", "B": "8", "Z": "2", "G": "6"})


def _ocr_equiv(s: str) -> str:
    """Collapse characters OCR engines commonly confuse, for tolerant comparison of scanned text."""
    return s.upper().replace(" ", "").translate(_OCR_MAP)


def aicte_eoa(doc, ctx):
    """Verify an uploaded AICTE EoA letter against the institutional ledger (built from real public letters)."""
    letters = (doc.get("extraction") or {}).get("letters") or []
    if not letters:
        return None
    L = letters[0]
    f = L["fields"]
    pid, ay = (f.get("permanent_id") or {}).get("value"), (f.get("academic_year") or {}).get("value")
    rec = db.q1("SELECT * FROM approvals WHERE permanent_id=? AND academic_year=? ORDER BY id LIMIT 1", (pid, ay))
    req = {"permanent_id": pid, "academic_year": ay, "application_id": L["application_no"]}
    if not rec:
        return _result("aicte_ledger", "manual_review", "AICTE approval record", req, None,
                       f"No approval for {pid} / {ay} in the ledger - confirm on AICTE portal.", simulated=False)
    key = lambda c: ((c.get("level") or "").upper().replace(" ", ""), c["course"].upper())  # noqa: E731
    courses = {key(c): c for c in db.q("SELECT * FROM approval_courses WHERE approval_id=?", (rec["id"],))}
    checks, ev = [], []
    for c in L["courses"]:
        src = courses.get(key(c))
        vals = c.get("intake_values") or [c["intake_curr"]]
        shown = " / ".join(str(v) for v in vals) if len(vals) > 1 else c["intake_curr"]
        ok = src is not None and all(v == src["intake_curr"] for v in vals)
        _compare(checks, f"Intake {c['course'][:40]}" + (" (two overlapping values in cell)" if len(vals) > 1 else ""), shown,
                 src["intake_curr"] if src else None, ok)
        if not ok:
            cell = (c.get("cells") or {}).get("intake_curr") or {"page": c["page"], "bbox": c["bbox"]}
            ev.append({"doc_id": doc["id"], "doc_type": doc["doc_type"], "page": cell["page"], "bbox": cell["bbox"],
                       "label": f"Letter: {c['intake_curr']} | AICTE record: {src['intake_curr'] if src else 'course absent'}", "kind": "verification"})
    _compare(checks, "Application ID", L["application_no"], rec["application_id"], L["application_no"] == rec["application_id"])
    _compare(checks, "Date of approval", (f.get("date_of_approval") or {}).get("value"), rec["date_of_approval"],
             (f.get("date_of_approval") or {}).get("value") == rec["date_of_approval"])
    bad = [c for c in checks if not c["match"]]
    srcname = "AICTE approval record" + (f" (public copy: {rec['source_url']})" if rec.get("source_url") else "")
    if bad:
        return _result("aicte_ledger", "mismatch", srcname, req, {"approval_id": rec["id"]},
                       "Letter differs from AICTE record: " + "; ".join(f"{c['field']} {c['document']} vs {c['source']}" for c in bad),
                       simulated=False, checks=checks, evidence=ev)
    return _result("aicte_ledger", "verified", srcname, req, {"approval_id": rec["id"]},
                   f"All {len(checks)} fields match the AICTE approval record for {ay}.", simulated=False, checks=checks)


BY_TYPE = {"fire_noc": [fire, dsc, qr], "occupancy_certificate": [occupancy, dsc, qr], "affidavit_2": [estamp, dsc, qr],
           "audited_statement": [udin], "structural_stability": [engineer], "eoa_letter": [aicte_eoa], "ter_receipt": [qr]}


def run(doc: dict, ctx: dict) -> list[dict]:
    out = []
    for fn in BY_TYPE.get(doc["doc_type"], []):
        try:
            r = fn(doc, ctx)
        except Exception as e:  # noqa: BLE001
            r = _result(fn.__name__, "manual_review", fn.__name__, {}, None, f"Connector error ({e.__class__.__name__}); manual confirmation needed.")
        if r:
            out.append(r)
    return out


def draft_letter(v: dict, doc: dict, ctx: dict) -> str:
    """Verification request to the issuing authority when automated verification is unavailable."""
    ref = next(iter(v.get("request", {}).values()), "")
    return (f"To\nThe Competent Authority,\n{v['source']}\n\nSub: Request for confirmation of {doc['doc_type'].replace('_', ' ').title()} No. {ref}\n\n"
            f"Sir/Madam,\n\n{ctx['form'].get('institution_name')} (AICTE Permanent ID {ctx['form'].get('permanent_id')}) has submitted the above "
            f"document in its application {ctx['form'].get('application_no')} for Extension of Approval for AY {ctx['academic_year']}. "
            "Automated verification through your online service was not available. You are requested to confirm whether the document was "
            "issued by your office, its date of issue, validity and the premises/party named in it.\n\n"
            "A copy of the document as submitted is enclosed.\n\nYours faithfully,\nScrutiny Officer, AICTE\n(Draft generated by Satyapan - to be reviewed before dispatch)")
