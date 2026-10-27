"""Document types required by APH 2024-27 Annexure-2 (2.1) for EoA, their classifier signatures,
and their field schemas. Classification is keyword-evidence scoring, so it is explainable: the UI
shows which phrases made the system decide "this is a Fire NOC".
"""
from __future__ import annotations

import re

from ..docmodel import Doc, find_phrase, union_bbox
from . import fields as F

ESTAMP_RX = re.compile(r"IN-[A-Z]{2}\d{8,14}[A-Z]?")
UDIN_RX = re.compile(r"\b\d{2}\d{6}[A-Z]{6}\d{4}\b")
TXN_RX = re.compile(r"\b(?:TER|AICTE|TXN)[A-Z0-9\-]{6,24}\b")
APPNO_RX = re.compile(r"\b1-\d{9,12}\b")
LATLON_RX = re.compile(r"(-?\d{1,2}\.\d{3,8})\s*°?\s*([NS])?[,\s]+(-?\d{1,3}\.\d{3,8})\s*°?\s*([EW])?")

DOC_TYPES: dict[str, dict] = {
    "affidavit_2": {
        "title": "Affidavit 2 (on Rs.100 e-stamp paper)",
        "aph": "Annexure-2, 2.1(i)",
        "signals": {"affidavit": 2, "solemnly affirm": 3, "deponent": 2, "approval process handbook": 1,
                    "notary": 1, "e-stamp": 2, "stamp duty": 2, "certificate no": 1, "oath commissioner": 1},
    },
    "ter_receipt": {
        "title": "TER charges payment receipt",
        "aph": "Annexure-2, 2.1(ii)",
        "signals": {"technical education regulatory": 3, "ter charges": 3, "transaction id": 2, "payment receipt": 2,
                    "payment": 1, "amount paid": 2},
    },
    "occupancy_certificate": {
        "title": "Occupancy / Completion Certificate / Building License / Form D",
        "aph": "Annexure-2, 2.1(iii); Clause 6.17(g)",
        "signals": {"occupancy certificate": 4, "completion certificate": 3, "building license": 3, "building licence": 3, "form d": 2,
                    "built up area": 1, "building permission": 1, "fit for occupation": 2, "permission is hereby granted to occupy": 4,
                    "mahanagara palike": 2, "town planning": 2, "sanctioned plan": 2},
    },
    "structural_stability": {
        "title": "Structural Stability Certificate",
        "aph": "Annexure-2, 2.1(iv); Clause 6.17(h)",
        "signals": {"structural stability": 4, "structural engineer": 3, "fit for human habitation": 3,
                    "structurally safe": 2, "load bearing": 1},
    },
    "fire_noc": {
        "title": "Fire Safety Certificate (Fire NOC)",
        "aph": "Annexure-2, 2.1(v); Clause 6.17(i)",
        "signals": {"fire": 2, "fire safety": 3, "fire and emergency": 3, "fire service": 3, "no objection certificate": 2,
                    "fire noc": 4, "fire fighting": 2, "fire officer": 2, "clearance certificate": 3, "fire force": 3,
                    "fire prevention": 2},
    },
    "satellite_map": {
        "title": "Satellite map with latitude/longitude at main building entrance",
        "aph": "Annexure-2, 2.1(vi)",
        "signals": {"latitude": 3, "longitude": 3, "satellite": 3, "main building": 1, "entrance": 1, "map": 1},
    },
    "audited_statement": {
        "title": "Audited statement of accounts (previous year)",
        "aph": "Annexure-2, 2.1(vii)",
        "signals": {"balance sheet": 3, "income and expenditure": 3, "chartered accountant": 2, "udin": 3,
                    "auditor": 2, "audited": 2, "frn": 1},
    },
    "mandatory_disclosure": {
        "title": "Mandatory disclosure (Annexure-18)",
        "aph": "Annexure-18",
        "signals": {"mandatory disclosure": 5, "grievance redressal": 2, "anti ragging": 2, "name of the affiliating university": 2,
                    "internal quality assurance": 1, "organizational chart": 1, "organisational chart": 1},
    },
    "eoa_letter": {
        "title": "AICTE Extension of Approval letter",
        "aph": "Annexure-18 (LoA/EoA letters since inception)",
        "signals": {"extension of approval": 3, "all india council for technical education": 2, "permanent id": 3,
                    "intake approved": 3, "approval process": 1},
    },
    "infra_photo": {"title": "Infrastructure photograph", "aph": "Clause 2.3.5 / Annexure-18 18.15", "signals": {}},
}

# Plain names used in messages to institutions
PLAIN = {"affidavit_2": "affidavit", "ter_receipt": "fee receipt", "occupancy_certificate": "occupancy certificate",
         "structural_stability": "structural safety certificate", "fire_noc": "fire safety certificate", "satellite_map": "location map",
         "audited_statement": "audited accounts", "eoa_letter": "AICTE approval letter", "mandatory_disclosure": "public disclosure",
         "infra_photo": "photo"}

REQUIRED_EOA = ["affidavit_2", "ter_receipt", "occupancy_certificate", "fire_noc", "satellite_map", "audited_statement"]


def classify(doc: Doc, declared: str | None = None) -> dict:
    if doc.kind == "image" and len(doc.text.strip()) < 40:
        return {"doc_type": "infra_photo", "score": 1.0, "evidence": [], "scores": {}}
    scores, evidence = {}, {}
    for dt, spec in DOC_TYPES.items():
        s, ev = 0.0, []
        for phrase, wgt in spec["signals"].items():
            for page in doc.pages[:3]:
                hits = find_phrase(page, phrase)
                if hits:
                    s += wgt * min(len(hits), 2) ** 0.5
                    ev.append({"phrase": phrase, "page": page.number, "bbox": union_bbox(hits[0]), "weight": wgt})
                    break
        scores[dt] = round(s, 2)
        evidence[dt] = ev
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top, second = ranked[0], ranked[1]
    if top[1] < 3:
        return {"doc_type": "unknown", "score": 0.0, "evidence": [], "scores": scores}
    margin = (top[1] - second[1]) / max(top[1], 1e-6)
    return {"doc_type": top[0], "score": round(min(1.0, 0.5 + margin), 2), "evidence": evidence[top[0]],
            "scores": scores, "declared": declared}


# --------------------------------------------------------------------------- per-type extraction

NAME_STOPS = ["address", "date", "valid", "situated", "located", "survey", "plot", "no", "sy no", "ward"]


def _txt(doc, labels, stops=None, max_words=14):
    return F.find_label_value(doc, labels, "text", stop_labels=stops or NAME_STOPS, max_words=max_words)


def _date(doc, labels):
    return F.find_label_value(doc, labels, "date")


def _num(doc, labels):
    return F.find_label_value(doc, labels, "number")


def extract(doc: Doc, doc_type: str) -> dict:
    fx = EXTRACTORS.get(doc_type)
    if not fx:
        return {}
    out = {}
    for k, v in fx(doc).items():
        if v is not None:
            out[k] = v.as_dict() if hasattr(v, "as_dict") else v
    return out


def _affidavit(doc):
    return {
        "estamp_cert_no": F.find_pattern(doc, ESTAMP_RX),
        "estamp_date": _date(doc, ["Certificate Issued Date", "Issued Date", "Date of Issue"]),
        "stamp_value": _num(doc, ["Stamp Duty Amount(Rs.)", "Stamp Duty Amount", "Stamp Duty", "Stamp Value"]),
        "first_party": _txt(doc, ["First Party", "Purchased by"], ["second party", "stamp", "description", "consideration"]),
        "deponent": _txt(doc, ["I/we,", "I/We", "I,"], ["chairperson", "secretary", "son", "daughter", ","], 6),
        "trust_name": _txt(doc, ["Name of the Trust/ Society/ Company", "Trust/Society/Company", "Name of the Trust"]),
        "institution_name": _txt(doc, ["Name of the Institution", "for the Institution"], ["address", "situated", "located", "programmes"]),
        "application_no": F.find_pattern(doc, APPNO_RX),
        "notary_name": _txt(doc, ["Notary Public", "Before me", "Notary"], ["reg", "registration", "date", "seal"], 6),
        "notary_reg_no": F.find_label_value(doc, ["Regn. No", "Reg. No", "Registration No"], "pattern",
                                             re.compile(r"[A-Z0-9/\-]{4,20}")),
        "sworn_date": _date(doc, ["Verified at", "on this", "Solemnly affirmed", "Date"]),
        "built_up_area": _num(doc, ["Total Built-Up Area available", "Total Built-up Area", "Built-up Area"]),
        "signed_phrase": F.contains(doc, ["Digitally signed by", "DEPONENT"]),
    }


def _ter(doc):
    return {
        "txn_id": F.find_label_value(doc, ["Transaction ID", "Transaction No", "Txn ID", "Reference No"], "pattern", TXN_RX)
        or F.find_pattern(doc, TXN_RX),
        "amount": _num(doc, ["Amount Paid (Rs.)", "Amount Paid", "Amount (Rs.)", "Amount"]),
        "payment_date": _date(doc, ["Payment Date", "Date of Payment", "Transaction Date", "Date"]),
        "permanent_id": F.find_label_value(doc, ["Permanent ID", "Permanent Id"], "pattern", re.compile(r"1-\d{6,12}")),
        "application_no": F.find_label_value(doc, ["Application No", "Application ID", "Application Id"], "pattern", APPNO_RX),
        "status": _txt(doc, ["Status", "Payment Status"], ["date", "amount"], 3),
    }


def _oc(doc):
    return {
        "partial": F.contains(doc, ["PARTIAL OCCUPANCY CERTIFICATE", "Provisional Occupancy Certificate", "PARTIAL OCCUPANCY"]),
        "cert_no": _txt(doc, ["Certificate No", "OC No", "Permit No", "Licence No", "File No"], ["date", "dated"], 4),
        "issue_date": _date(doc, ["Date of Issue", "Issue Date", "Dated", "Date"]) or _dated_anywhere(doc),
        "authority": _txt(doc, ["Issuing Authority", "Competent Authority", "Office of the"], ["date", "no"], 10),
        "owner": _txt(doc, ["Name of the Owner", "Owner/Applicant", "Applicant", "Issued to", "in favour of"],
                      ["address", "situated", "for", "at"], 12),
        "premises": _txt(doc, ["Name of the Building", "Building Name", "Name of Premises", "Premises"], NAME_STOPS, 12),
        "address": _txt(doc, ["Address of the Premises", "Address", "Situated at", "Location"], ["built", "area", "survey", "plot", "total"], 16),
        "built_up_area": _num(doc, ["Total Built-up Area", "Total Built up Area", "Built-up Area", "Built up area", "Plinth Area"]),
        "floors": _txt(doc, ["No. of Floors", "Number of Floors", "Floors"], ["built", "area"], 4),
    }


def _ssc(doc):
    return {
        "issue_date": _date(doc, ["Date of Issue", "Issue Date", "Inspected on", "Dated", "Date"]),
        "valid_until": _date(doc, ["Valid up to", "Valid upto", "Valid till", "Validity"]),
        "engineer": _txt(doc, ["Structural Engineer", "Name of Engineer", "Certified by"], ["reg", "registration", "license", "date", "qualification"], 6),
        "engineer_reg_no": F.find_label_value(doc, ["Registration No", "Reg. No", "License No", "Licence No"], "pattern",
                                               re.compile(r"[A-Z0-9/\-]{4,24}")),
        "premises": _txt(doc, ["Name of the Building", "Building", "Premises", "Name of Institution"], NAME_STOPS, 12),
        "address": _txt(doc, ["Address", "Situated at", "Location"], ["built", "area", "year", "constructed"], 16),
        "construction_year": _num(doc, ["Year of Construction", "Constructed in", "Completion Year"]),
    }


PERIOD_RX = re.compile(r"(?:further\s*)?period\s*of\s*(one|two|three|four|five|\d)\s*\(?\d?\)?\s*years?", re.I)
NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
DATED_RX = re.compile(r"Dated\s*[:.\-]?\s*(\d{1,2}[\-/.]\d{1,2}[\-/.]\d{2,4})", re.I)


def _dated_anywhere(doc):
    """Letters put the date in running text ("Bangalore. Dated: 25-11-2019"), not in a form field."""
    for page in doc.pages[:2]:
        for line in page.lines():
            t = " ".join(w.text for w in line)
            m = DATED_RX.search(t)
            if m:
                d = F.parse_date(m.group(1))
                if d:
                    ws = [w for w in line if any(ch.isdigit() for ch in w.text)] or line
                    return F.Value(d, m.group(1), page.number, union_bbox(ws), None, 0.85 * min(w.conf for w in line), "Dated")
    return None


def _validity_from_period(doc, issue):
    """'renewed ... for a further period of two years' -> derived valid-until = issue date + N years."""
    if not issue:
        return None
    for page in doc.pages[:2]:
        for line in page.lines():
            t = " ".join(w.text for w in line)
            m = PERIOD_RX.search(t) or PERIOD_RX.search(t.replace(" ", ""))
            if m:
                n = NUM_WORDS.get(m.group(1).lower()) or int(m.group(1))
                start = issue.value
                try:
                    until = start.replace(year=start.year + n)
                except ValueError:
                    until = start.replace(year=start.year + n, day=28)
                return F.Value(until, f"renewed for {n} year{'s' if n > 1 else ''} from {start:%d %b %Y}", page.number, union_bbox(line), None,
                               0.8 * min(w.conf for w in line), "derived: period of validity")
    return None


def _fire(doc):
    issue = _date(doc, ["Date of Issue", "Issue Date", "Issued on", "Dated"]) or _dated_anywhere(doc)
    valid = _date(doc, ["Valid up to", "Valid upto", "Valid till", "Validity up to", "Validity", "Expiry Date", "Valid Until"])         or _validity_from_period(doc, issue)
    out = _fire_fields(doc)
    out["issue_date"], out["valid_until"] = issue, valid
    return out


def _fire_fields(doc):
    return {
        "noc_no": _txt(doc, ["NOC No", "Certificate No", "Fire NOC No", "Ref No", "Reference No"], ["date", "dated", "valid"], 3),
        "issue_date": _date(doc, ["Date of Issue", "Issue Date", "Issued on", "Dated"]),
        "valid_until": _date(doc, ["Valid up to", "Valid upto", "Valid till", "Validity up to", "Validity", "Expiry Date", "Valid Until"]),
        "premises": _txt(doc, ["Name of the Premises", "Name of Building", "Name of the Occupancy", "Premises", "Building Name"], NAME_STOPS, 12),
        "address": _txt(doc, ["Address of the Premises", "Address", "Situated at", "Location"], ["occupancy", "height", "floors", "valid", "built"], 16),
        "occupancy": _txt(doc, ["Type of Occupancy", "Occupancy", "Category"], ["height", "floors", "address"], 6),
        "authority": _txt(doc, ["Issued by", "Fire Officer", "Office of the"], ["date"], 10),
        "qr": None,
    }


def _satellite(doc):
    best = None
    for page in doc.pages:
        for line in page.lines():
            t = " ".join(w.text for w in line)
            m = LATLON_RX.search(t)
            if m:
                lat, lon = float(m.group(1)), float(m.group(3))
                if m.group(2) == "S":
                    lat = -lat
                if m.group(4) == "W":
                    lon = -lon
                if 6 <= lat <= 37 and 68 <= lon <= 98:   # India bounding box
                    best = {"lat": lat, "lon": lon, "page": page.number, "bbox": union_bbox(line), "raw": m.group(0)}
                    break
        if best:
            break
    lat = _num(doc, ["Latitude", "Lat"]) if not best else None
    lon = _num(doc, ["Longitude", "Long", "Lon"]) if not best else None
    if not best and lat and lon:
        best = {"lat": lat.value, "lon": lon.value, "page": lat.page, "bbox": union_bbox_list([lat.bbox, lon.bbox]),
                "raw": f"{lat.raw}, {lon.raw}"}
    return {"latlon": best}


def union_bbox_list(bbs):
    return [min(b[0] for b in bbs), min(b[1] for b in bbs), max(b[2] for b in bbs), max(b[3] for b in bbs)]


def _audit(doc):
    return {
        "udin": F.find_label_value(doc, ["UDIN"], "pattern", UDIN_RX) or F.find_pattern(doc, UDIN_RX),
        "frn": F.find_label_value(doc, ["FRN", "Firm Registration No", "Firm Reg. No"], "pattern", re.compile(r"\d{6}[A-Z]")),
        "membership_no": F.find_label_value(doc, ["Membership No", "M. No", "M.No"], "pattern", re.compile(r"\d{6}")),
        "trust_name": _txt(doc, ["Name of the Trust", "Name of the Society", "Trust", "Society"], ["balance", "for the year", "as at", "address"], 10),
        "fy": F.find_label_value(doc, ["for the year ended", "Financial Year", "as at", "F.Y."], "date"),
        "signed_date": _date(doc, ["Date", "Dated", "Place"]),
    }


ANNEX18_ITEMS = [
    ("Fire and Safety Certificate", ["Fire and Safety Certificate", "Fire & Safety Certificate", "Fire and Safety"]),
    ("Faculty details / list", ["Faculty List", "List of Faculty", "Faculty details", "Permanent Faculty", "list Faculty members",
                                "Faculty members", "Profile of Faculty"]),
    ("Faculty : Student ratio", ["Student Ratio", "Faculty Student Ratio", "Faculty: Student", "Student Faculty Ratio", "Faculty Ratio",
                                "Teacher Ratio", "FSR"]),
    ("Approved intake / seats", ["Number of seats", "Intake", "seats sanctioned"]),
    ("Fee", ["Fee", "Fees"]),
    ("Grievance redressal", ["Grievance Redressal"]),
    ("Anti-ragging committee", ["Anti Ragging", "Anti-Ragging"]),
    ("Library", ["Library"]),
    ("Placement / enrolment details", ["Placement", "Enrolment", "Enrollment"]),
    ("AICTE approval letters (since inception)", ["LoA", "EoA", "Extension of Approval", "approved by AICTE", "Programmes approved by AICTE"]),
    ("Audited financial statements", ["Audited", "Financial Statement", "Balance Sheet"]),
]


def _disclosure(doc):
    items = []
    for label, phrases in ANNEX18_ITEMS:
        hit = F.contains(doc, phrases)
        items.append({"item": label, "found": bool(hit), **({"page": hit["page"], "bbox": hit["bbox"]} if hit else {})})
    return {"items": items}


def _eoa(doc):
    from . import eoa
    letters = eoa.parse(doc)
    return {"letters": [L.as_dict() for L in letters]}


EXTRACTORS = {
    "affidavit_2": _affidavit, "ter_receipt": _ter, "occupancy_certificate": _oc, "structural_stability": _ssc,
    "fire_noc": _fire, "satellite_map": _satellite, "audited_statement": _audit, "eoa_letter": _eoa,
    "mandatory_disclosure": _disclosure,
}
