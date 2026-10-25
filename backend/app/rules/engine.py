"""Rule engine: typed checks configured from YAML (APH-cited), producing evidence-linked results."""
from __future__ import annotations

import math
import re
from datetime import date
from functools import lru_cache

import yaml
from rapidfuzz import fuzz

from .. import db
from ..config import RULES_DIR
from . import citations, norms

STATUS_ORDER = {"fail": 0, "warn": 1, "manual": 2, "pass": 3, "na": 4}


@lru_cache(maxsize=1)
def _load() -> dict:
    return yaml.safe_load((RULES_DIR / "aph_2024_27.yaml").read_text("utf-8"))


def ruleset() -> dict:
    base = _load()
    overrides = {r["rule_id"]: r for r in db.q("SELECT * FROM rule_overrides")}
    rules = []
    for r in base["rules"]:
        r = dict(r)
        o = overrides.get(r["id"])
        r["enabled"] = True
        if o:
            r["enabled"] = bool(o["enabled"])
            r["params"] = {**r.get("params", {}), **db.unj(o["params"], {})}
            r["overridden_by"] = o["updated_by"]
        r["cite_loc"] = citations.locate(r["cite"]["quote"])
        rules.append(r)
    return {"version": base["version"], "categories": base["categories"], "rules": rules}


# ------------------------------------------------------------------------------------ helpers

def _norm_name(s: str) -> str:
    s = (s or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(w for w in s.split() if w not in {"the", "of", "and", "sri", "shri", "dr"})


def _compact_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower().replace("&", "").replace(" and ", ""))


GENERIC = sorted({"educational", "education", "society", "trust", "charitable", "foundation", "institute", "institution",
                  "college", "engineering", "technology", "technological", "management", "university", "school", "academy",
                  "sciences", "science", "research", "group", "institutions", "of", "and", "the", "for", "sri", "shri"},
                 key=len, reverse=True)


def _distinctive(s: str) -> str:
    """Compact name with generic words removed (works even when OCR merged the words)."""
    c = _compact_name(s)
    for g in GENERIC:
        c = c.replace(g, "")
    return c


def name_score(a: str, b: str) -> float:
    """Name similarity robust to OCR space loss ("VidyaJyothi Instituteof...") and word order, but not fooled
    by shared generic words: "Tarangvani Educational Society" must not match "Jalataranga Educational Society"."""
    na, nb = _norm_name(a), _norm_name(b)
    if not na or not nb:
        return 0.0
    token = min(fuzz.token_sort_ratio(na, nb), fuzz.ratio(na, nb) + 15)
    full = max(token, fuzz.ratio(_compact_name(a), _compact_name(b)))
    da, db_ = _distinctive(a), _distinctive(b)
    if len(da) >= 3 and len(db_) >= 3:
        return min(full, fuzz.ratio(da, db_))
    return full


def _ev(doc: dict | None, fld: dict | None, label: str, kind: str = "value") -> dict | None:
    if not doc or not fld or fld.get("bbox") is None:
        return None
    return {"doc_id": doc["id"], "doc_type": doc["doc_type"], "page": fld.get("page", 0), "bbox": fld["bbox"],
            "label": label, "kind": kind}


def _date(v):
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ------------------------------------------------------------------------------------ checks

def _first(ctx, dt):
    lst = ctx["docs"].get(dt) or []
    return lst[0] if lst else None


def ck_document_present(rule, ctx):
    p = rule["params"]
    dt = p["doc_type"]
    age_limit = p.get("when_building_age_over")
    if age_limit:
        yr = ctx["form"].get("building_completion_year")
        age = ctx["ay_start"].year - int(yr) if yr else None
        if age is None or age <= age_limit:
            return {"status": "na", "detail": f"Building age {age} years - certificate not required (> {age_limit} years)."}
    doc = _first(ctx, dt)
    if doc:
        return {"status": "pass", "detail": f"Found: {doc['filename']}", "evidence": [
            {"doc_id": doc["id"], "doc_type": dt, "page": 0, "bbox": None, "label": "document", "kind": "doc"}]}
    extra = ""
    if age_limit:
        extra = f" Building completed in {ctx['form'].get('building_completion_year')} (more than {age_limit} years before AY {ctx['academic_year']})."
    return {"status": "fail", "detail": f"No {dt.replace('_', ' ')} found among uploaded documents.{extra}",
            "evidence": [{"source": "form", "field": "building_completion_year", "label": "Building completion year",
                          "value": ctx["form"].get("building_completion_year")}] if age_limit else []}


def ck_slot_matches(rule, ctx):
    from ..extract.docs import DOC_TYPES
    bad, lines, ev = [], [], []
    for d in ctx["all_docs"]:
        decl = d["declared_type"]
        cls = d["classification"] or {}
        det = cls.get("doc_type", d["doc_type"])
        if not decl or decl == "infra_photo" or decl not in DOC_TYPES:
            continue
        title = DOC_TYPES[decl]["title"]
        if det not in (decl, "unknown") and cls.get("score", 0) >= rule["params"]["min_confidence"]:
            lines.append(f"'{d['filename']}' was uploaded as {title} but reads as {DOC_TYPES[det]['title']}.")
            bad.append(d)
            for e in cls.get("evidence", [])[:3]:
                ev.append({"doc_id": d["id"], "doc_type": d["doc_type"], "page": e["page"], "bbox": e["bbox"],
                           "label": f"reads like {DOC_TYPES[det]['title']}: '{e['phrase']}'", "kind": "classifier"})
        elif det == "unknown":
            lines.append(f"'{d['filename']}' was uploaded as {title} but does not contain the wording expected of one "
                         f"(issuing authority, certificate number, validity).")
            bad.append(d)
            ev.append({"doc_id": d["id"], "doc_type": d["doc_type"], "page": 0, "bbox": None, "label": "whole document", "kind": "classifier"})
    if not bad:
        return {"status": "pass", "detail": "Every file matches the heading it was uploaded under."}
    return {"status": "fail", "detail": " ".join(lines), "evidence": ev}


def ck_partial_oc(rule, ctx):
    doc = _first(ctx, "occupancy_certificate")
    if not doc:
        return {"status": "na", "detail": "No occupancy certificate."}
    part = doc["extraction"].get("partial")
    if not part:
        return {"status": "pass", "detail": "Full occupancy certificate."}
    iss = doc["extraction"].get("issue_date")
    d = _date(iss["value"]) if iss else None
    ev = [{"doc_id": doc["id"], "doc_type": doc["doc_type"], "page": part["page"], "bbox": part["bbox"],
           "label": "Partial occupancy certificate", "kind": "value"}]
    if iss:
        ev.append(_ev(doc, iss, f"Dated {iss['value']}"))
    years = rule["params"].get("max_academic_years", 2)
    if d is None:
        return {"status": "manual", "detail": "Partial occupancy certificate; its date could not be read.", "evidence": ev}
    first_ay = d.year if d.month >= 6 else d.year - 1
    used = int(ctx["academic_year"][:4]) - first_ay + 1
    if used > years:
        return {"status": "fail", "detail": f"Partial occupancy certificate dated {d:%d %b %Y}: AY {ctx['academic_year']} would be its "
                                            f"{used}th academic year, but a partial certificate is accepted for {years} consecutive years only.",
                "evidence": ev}
    return {"status": "warn", "detail": f"Partial occupancy certificate dated {d:%d %b %Y}; accepted for {years} consecutive academic years.",
            "evidence": ev}


def ck_disclosure_items(rule, ctx):
    doc = _first(ctx, "mandatory_disclosure")
    if not doc:
        return {"status": "fail", "detail": "No mandatory disclosure document."}
    items = doc["extraction"].get("items", [])
    missing = [i["item"] for i in items if not i["found"]]
    ev = [{"doc_id": doc["id"], "doc_type": doc["doc_type"], "page": i["page"], "bbox": i["bbox"], "label": i["item"], "kind": "value"}
          for i in items if i["found"]]
    if missing:
        return {"status": "warn", "detail": "Not found in the disclosure: " + ", ".join(missing) + ".", "evidence": ev}
    return {"status": "pass", "detail": f"All {len(items)} checked items are present.", "evidence": ev}


def ck_date_valid(rule, ctx):
    p = rule["params"]
    doc = _first(ctx, p["doc_type"])
    if not doc:
        return {"status": "na", "detail": "Document not uploaded (covered by completeness rule)."}
    fld = doc["extraction"].get(p["field"])
    d = _date(fld["value"]) if fld else None
    if not d:
        return {"status": "manual", "detail": "Validity date could not be read reliably - manual check needed.",
                "evidence": [], "confidence": 0.3}
    ref = ctx["application_date"]
    ev = [_ev(doc, fld, f"Valid until {d.isoformat()}")]
    derived = str(fld.get("label", "")).startswith("derived")
    if d < ref and ctx.get("category") == "PUBLIC_REVIEW":
        how = f" (worked out from the letter: '{fld['raw']}')" if derived else ""
        return {"status": "fail", "detail": f"The publicly posted certificate was valid until {d:%d %b %Y}{how}. "
                                            "A renewed certificate may exist but is not in the public disclosure.",
                "evidence": ev, "confidence": fld.get("conf", 0.8)}
    if d < ref:
        return {"status": "fail", "detail": f"Expired on {d:%d %b %Y}, before the application date {ref:%d %b %Y}.",
                "evidence": ev, "confidence": fld.get("conf", 0.9)}
    if p.get("warn_if_before") == "academic_year_start" and d < ctx["ay_start"]:
        return {"status": "warn", "detail": f"Valid until {d:%d %b %Y} - expires before AY {ctx['academic_year']} begins ({ctx['ay_start']:%d %b %Y}).",
                "evidence": ev, "confidence": fld.get("conf", 0.9)}
    return {"status": "pass", "detail": f"Valid until {d:%d %b %Y}.", "evidence": ev, "confidence": fld.get("conf", 0.9)}


def ck_issued_within_years(rule, ctx):
    p = rule["params"]
    doc = _first(ctx, p["doc_type"])
    if not doc:
        return {"status": "na", "detail": "Document not uploaded."}
    fld = doc["extraction"].get(p["field"])
    d = _date(fld["value"]) if fld else None
    if not d:
        return {"status": "manual", "detail": "Issue date not readable - manual check needed."}
    age = (ctx["application_date"] - d).days / 365.25
    ev = [_ev(doc, fld, f"Issued {d.isoformat()}")]
    if age > p["years"]:
        return {"status": "fail", "detail": f"Issued {d:%d %b %Y}: {age:.1f} years old, beyond the {p['years']}-year validity.", "evidence": ev}
    return {"status": "pass", "detail": f"Issued {d:%d %b %Y} ({age:.1f} years ago).", "evidence": ev}


def ck_numeric_min(rule, ctx):
    p = rule["params"]
    doc = _first(ctx, p["doc_type"])
    if not doc:
        return {"status": "na", "detail": "Document not uploaded."}
    fld = doc["extraction"].get(p["field"])
    if not fld:
        return {"status": "manual", "detail": f"{p['field']} not readable."}
    v = float(fld["value"])
    ev = [_ev(doc, fld, f"{p['field']} = {v:g}")]
    if v < p["min"]:
        return {"status": "fail", "detail": f"Stamp value Rs.{v:g} is below the required Rs.{p['min']}.", "evidence": ev}
    return {"status": "pass", "detail": f"Rs.{v:g} e-stamp.", "evidence": ev}


def ck_dsc_valid(rule, ctx):
    doc = _first(ctx, rule["params"]["doc_type"])
    if not doc:
        return {"status": "na", "detail": "Document not uploaded."}
    sigs = (doc.get("forensics") or {}).get("signatures") or []
    if not sigs:
        return {"status": "fail", "detail": "No digital signature (DSC) found in the PDF.", "evidence": []}
    s = sigs[0]
    who = s.get("signer") or "?"
    if s.get("modified_after_signing"):
        changed = [c for c in (doc["forensics"].get("revision_diff") or []) if c.get("type") == "text_changed"]
        ev = [{"doc_id": doc["id"], "doc_type": doc["doc_type"], "page": c["page"], "bbox": c["bbox"],
               "label": f"changed after signing: '{c['before']}' -> '{c['after']}'", "kind": "forensic"} for c in changed if c.get("bbox")]
        return {"status": "fail", "detail": f"Signed by {who}, but the file was modified after signing - the signature no longer covers the content shown.",
                "evidence": ev}
    if not s.get("intact") or not s.get("valid"):
        return {"status": "fail", "detail": f"Signature by {who} is not cryptographically valid."}
    if not s.get("trusted"):
        return {"status": "warn", "detail": f"Signature by {who} is intact but the certificate does not chain to a trusted CCA root."}
    chair = ctx["form"].get("chairperson", "")
    if chair and name_score(chair, who.split("Common Name:")[-1].split(",")[0]) < 80:
        return {"status": "warn", "detail": f"Signed by '{who}', not by the Chairperson '{chair}' named in the application."}
    return {"status": "pass", "detail": f"Valid DSC by {who.split(',')[0].replace('Common Name: ', '')}; document unchanged since signing."}


def ck_name_matches(rule, ctx):
    p = rule["params"]
    doc = _first(ctx, p["doc_type"])
    if not doc:
        return {"status": "na", "detail": "Document not uploaded."}
    fld = doc["extraction"].get(p["field"])
    target = ctx["form"].get(p["against"], "")
    if not fld:
        # letters rarely have a "premises" field: look for the name anywhere in the text
        hit = _name_in_text(doc, target)
        if hit:
            return {"status": "pass", "detail": f"'{target}' appears in the document.", "evidence": [hit]}
        return {"status": "manual", "detail": f"The name '{target}' was not found in the document; check who it was issued to."}
    s = name_score(str(fld["value"]), target)
    ev = [_ev(doc, fld, f"Document says: {fld['value']}")]
    if s < p["threshold"]:
        return {"status": "fail", "detail": f"Document names '{fld['value']}' but the application is for '{target}' (similarity {s:.0f}%).",
                "evidence": ev, "confidence": round(1 - s / 100, 2)}
    return {"status": "pass", "detail": f"'{fld['value']}' matches the application (similarity {s:.0f}%).", "evidence": ev}


def _name_in_text(doc: dict, name: str) -> dict | None:
    from ..docmodel import find_phrase
    for page in (doc.get("_pages") or []):
        hits = find_phrase(page, name)
        if hits:
            from ..docmodel import union_bbox
            return {"doc_id": doc["id"], "doc_type": doc["doc_type"], "page": page.number, "bbox": union_bbox(hits[0]),
                    "label": "institution name", "kind": "value"}
    return None


def ck_field_equals(rule, ctx):
    p = rule["params"]
    doc = _first(ctx, p["doc_type"])
    if not doc:
        return {"status": "na", "detail": "Document not uploaded."}
    fld = doc["extraction"].get(p["field"])
    target = str(ctx["form"].get(p["against"], "")).strip().upper()
    if not fld:
        return {"status": "manual", "detail": f"Could not read '{p['field']}'."}
    val = re.sub(r"\s", "", str(fld["value"])).upper()
    ev = [_ev(doc, fld, f"Document: {fld['value']}")]
    if val != re.sub(r"\s", "", target):
        return {"status": "fail", "detail": f"Document shows {fld['value']}, application has {target}.", "evidence": ev}
    return {"status": "pass", "detail": f"{fld['value']} matches.", "evidence": ev}


def ck_number_supports(rule, ctx):
    p = rule["params"]
    doc = _first(ctx, p["doc_type"])
    if not doc:
        return {"status": "na", "detail": "Document not uploaded."}
    fld = doc["extraction"].get(p["field"])
    claim = float(ctx["form"].get(p["against"]) or 0)
    if not fld:
        return {"status": "manual", "detail": "Certified area not readable."}
    v = float(fld["value"])
    ev = [_ev(doc, fld, f"Certified: {v:,.2f} sq.m"),
          {"source": "form", "field": p["against"], "label": "Claimed in application", "value": claim}]
    if claim > v * (1 + p["tolerance"]):
        return {"status": "fail", "detail": f"Application claims {claim:,.0f} sq.m but the certificate certifies {v:,.0f} sq.m.", "evidence": ev}
    return {"status": "pass", "detail": f"Certificate supports {v:,.0f} sq.m (claimed {claim:,.0f}).", "evidence": ev}


def ck_latlon_close(rule, ctx):
    doc = _first(ctx, rule["params"]["doc_type"])
    if not doc:
        return {"status": "na", "detail": "Map not uploaded."}
    ll = doc["extraction"].get("latlon")
    lat, lon = ctx["form"].get("campus_lat"), ctx["form"].get("campus_lon")
    if not ll or lat is None:
        return {"status": "manual", "detail": "Coordinates not readable from the map."}
    km = _km(ll["lat"], ll["lon"], float(lat), float(lon))
    ev = [{"doc_id": doc["id"], "doc_type": doc["doc_type"], "page": ll["page"], "bbox": ll["bbox"], "label": ll["raw"], "kind": "value"}]
    if km > rule["params"]["max_km"]:
        return {"status": "fail", "detail": f"Map point is {km:.1f} km from the campus coordinates on the application.", "evidence": ev}
    return {"status": "pass", "detail": f"Map point within {km * 1000:.0f} m of campus coordinates.", "evidence": ev}


def ck_faculty_ratio(rule, ctx):
    req = norms.faculty_requirement(ctx["form"].get("courses", []))
    have = len(ctx["form"].get("faculty", []))
    ev = [{"source": "form", "field": "faculty", "label": f"{have} faculty on roster", "value": have}]
    out = {"evidence": ev, "derivation": req["derivation"] + [f"Faculty on roster: {have}"]}
    if have < req["required"]:
        return {**out, "status": "fail", "detail": f"{have} faculty against {req['required']} required ({req['required'] - have} short)."}
    return {**out, "status": "pass", "detail": f"{have} faculty for {req['required']} required."}


def ck_cadre_ratio(rule, ctx):
    req = norms.faculty_requirement(ctx["form"].get("courses", []))
    fac = ctx["form"].get("faculty", [])
    prof = sum(1 for f in fac if f.get("designation") == "Professor")
    assoc = sum(1 for f in fac if f.get("designation") == "Associate Professor")
    shortp = max(0, req["professors"] - prof)
    surplus_assoc = max(0, assoc - req["associates"])
    covered = rule["params"].get("allow_associate_for_professor") and surplus_assoc >= shortp
    der = req["derivation"] + [f"Roster: {prof} Professors, {assoc} Associate Professors"]
    ev = [{"source": "form", "field": "faculty", "label": f"{prof} Prof / {assoc} Assoc", "value": [prof, assoc]}]
    if (shortp and not covered) or assoc + prof < req["associates"] + req["professors"]:
        return {"status": "fail", "detail": f"{prof} Professors / {assoc} Associate Professors against {req['professors']} / {req['associates']} required.",
                "derivation": der, "evidence": ev}
    return {"status": "pass", "detail": f"{prof} Professors / {assoc} Associate Professors (required {req['professors']} / {req['associates']}).",
            "derivation": der, "evidence": ev}


def ck_builtup_area(rule, ctx):
    req = norms.area_requirement(ctx["form"].get("courses", []))
    have = float(ctx["form"].get("builtup_area_sqm") or 0)
    ev = [{"source": "form", "field": "builtup_area_sqm", "label": f"{have:,.0f} sq.m declared", "value": have}]
    if have < req["required_builtup"]:
        return {"status": "fail", "detail": f"{have:,.0f} sq.m declared against {req['required_builtup']:,} sq.m required.",
                "derivation": req["derivation"], "evidence": ev}
    return {"status": "pass", "detail": f"{have:,.0f} sq.m declared; {req['required_builtup']:,} sq.m required.",
            "derivation": req["derivation"], "evidence": ev}


def ck_ter_paid(rule, ctx):
    doc = _first(ctx, "ter_receipt")
    req = norms.ter_required(ctx["form"].get("courses", []), ctx["academic_year"], ctx.get("inst_type", ""))
    if not doc:
        return {"status": "na", "detail": "Receipt not uploaded."}
    fld = doc["extraction"].get("amount")
    if not fld:
        return {"status": "manual", "detail": "Amount not readable."}
    paid = float(fld["value"])
    ev = [_ev(doc, fld, f"Paid Rs.{paid:,.2f}")]
    if paid + 1 < req["required"]:
        return {"status": "fail", "detail": f"Rs.{paid:,.0f} paid; Rs.{req['required']:,.0f} due (short by Rs.{req['required'] - paid:,.0f}).",
                "derivation": req["derivation"], "evidence": ev}
    return {"status": "pass", "detail": f"Rs.{paid:,.0f} paid (Rs.{req['required']:,.0f} due).", "derivation": req["derivation"], "evidence": ev}


def ck_principal_regular(rule, ctx):
    p = ctx["form"].get("principal") or {}
    if not p.get("name"):
        return {"status": "fail", "detail": "No Principal/Director entered."}
    if not p.get("regular") or "ph" not in (p.get("qualification") or "").lower():
        return {"status": "fail", "detail": f"Principal {p.get('name')} is not regular / not Ph.D. qualified."}
    return {"status": "pass", "detail": f"{p['name']} ({p.get('qualification')}), regular."}


def ck_intake_within_approved(rule, ctx):
    led = ctx.get("ledger")
    if not led or not led.get("courses"):
        return {"status": "manual", "detail": "No approval record found for this institution in the AICTE ledger."}
    key = lambda c: (re.sub(r"\W", "", (c.get("level") or "").upper()), c["course"].upper())  # noqa: E731
    approved = {key(c): c for c in led["courses"]}
    over, ev = [], []
    for c in ctx["form"].get("courses", []):
        a = approved.get(key(c))
        if a is None:
            over.append(f"{c['course']} is not in the {led['academic_year']} approval")
        elif int(c["intake"]) > int(a["intake_curr"] or 0):
            over.append(f"{c['course']}: applied {c['intake']} vs approved {a['intake_curr']} ({led['academic_year']})")
    for o in over:
        ev.append({"source": "ledger", "label": o, "value": led.get("source_url")})
    if over:
        return {"status": "fail", "detail": "; ".join(over), "evidence": ev}
    return {"status": "pass", "detail": f"All courses within intake approved for {led['academic_year']} ({led.get('source', 'ledger')})."}


def ck_ledger_identity(rule, ctx):
    led = ctx.get("ledger")
    if not led:
        return {"status": "manual", "detail": "Permanent ID not found in the institutional ledger."}
    s = name_score(led["institution"].get("name") or "", ctx["form"].get("institution_name", ""))
    if s < rule["params"]["threshold"]:
        return {"status": "fail", "detail": f"AICTE record has '{led['institution']['name']}', application says '{ctx['form'].get('institution_name')}'."}
    return {"status": "pass", "detail": f"Matches AICTE record for {led['institution']['permanent_id']} (similarity {s:.0f}%)."}


CHECKS = {k[3:]: v for k, v in globals().items() if k.startswith("ck_")}


def evaluate(ctx: dict) -> list[dict]:
    rs = ruleset()
    out = []
    public = ctx.get("category") == "PUBLIC_REVIEW"
    for r in rs["rules"]:
        if not r.get("enabled", True):
            continue
        scope = r.get("scope", "all")
        if (public and scope == "private") or (not public and scope == "public"):
            if public:
                out.append({"rule_id": r["id"], "title": r["title"], "severity": r["severity"], "remedy": None,
                            "citation": {**r["cite"], "loc": r.get("cite_loc")}, "status": "na",
                            "detail": "Not in the public disclosure; checked when the institution applies.", "evidence": []})
            continue
        fn = CHECKS[r["type"]]
        try:
            res = fn(r, ctx)
        except Exception as e:  # noqa: BLE001
            res = {"status": "manual", "detail": f"Rule could not be evaluated automatically ({e.__class__.__name__}); route to manual review."}
        res["evidence"] = [e for e in (res.get("evidence") or []) if e]
        out.append({"rule_id": r["id"], "title": r["title"], "severity": r["severity"], "remedy": r.get("remedy"),
                    "citation": {**r["cite"], "loc": r.get("cite_loc")}, **res})
    return out
