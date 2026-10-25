"""Cross-institution network: identities and artefacts that should be unique to one institution
but appear in several (shared faculty, reused photos, re-used certificate / e-stamp numbers, identical files).

Per-application scrutiny cannot see these; they only appear when all applications are viewed together.
Personal identifiers (PAN) are only stored as salted hashes.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from itertools import combinations

from . import db
from .forensics.image import hamming

SALT = "satyapan-demo-salt"
UNIQUE_DOC_KEYS = {"fire_noc": "noc_no", "occupancy_certificate": "cert_no", "affidavit_2": "estamp_cert_no",
                   "audited_statement": "udin", "ter_receipt": "txn_id"}
ENTITY_LABEL = {"faculty": "faculty identity", "faculty_id": "AICTE faculty ID", "faculty_pan": "PAN (hashed) + DOB", "doc_sha": "identical file",
                "ref_fire_noc": "Fire NOC number", "ref_occupancy_certificate": "OC number", "ref_affidavit_2": "e-stamp certificate",
                "ref_audited_statement": "UDIN", "ref_ter_receipt": "TER transaction", "photo": "infrastructure photo"}
SEVERITY = {"faculty": "high", "faculty_id": "high", "faculty_pan": "high", "doc_sha": "critical", "ref_fire_noc": "critical",
            "ref_occupancy_certificate": "critical", "ref_affidavit_2": "critical", "ref_audited_statement": "high",
            "ref_ter_receipt": "critical", "photo": "high"}


def _h(s: str) -> str:
    return hashlib.sha256((SALT + s.upper().strip()).encode()).hexdigest()[:24]


def entities_for(app_id: str, pid: str, form: dict, docs: list[dict]) -> list[dict]:
    rows = []
    for i, f in enumerate(form.get("faculty", [])):
        base = {"permanent_id": pid, "application_id": app_id, "document_id": None, "page": i, "bbox": None}
        disp = f"{f.get('name')} ({f.get('designation')}, {f.get('department', '')[:30]})"
        if f.get("faculty_id"):
            rows.append({**base, "entity_type": "faculty_id", "key": f["faculty_id"], "display": disp,
                         "extra": {"name": f.get("name"), "dob": f.get("dob"), "row": i, "joined": f.get("date_of_joining")}})
        if f.get("pan") and f.get("dob"):
            rows.append({**base, "entity_type": "faculty_pan", "key": _h(f["pan"] + "|" + f["dob"]), "display": disp,
                         "extra": {"name": f.get("name"), "dob": f.get("dob"), "row": i, "pan_masked": "XXXXX" + f["pan"][5:9] + "X",
                                   "joined": f.get("date_of_joining")}})
    for d in docs:
        if d["doc_type"] == "infra_photo":
            h = (d.get("forensics") or {}).get("hashes") or {}
            if h:
                rows.append({"permanent_id": pid, "application_id": app_id, "document_id": d["id"], "page": 0, "bbox": None,
                             "entity_type": "photo", "key": h["phash"], "display": d["filename"], "extra": h})
            continue
        rows.append({"permanent_id": pid, "application_id": app_id, "document_id": d["id"], "page": 0, "bbox": None,
                     "entity_type": "doc_sha", "key": d["sha256"], "display": d["filename"], "extra": None})
        k = UNIQUE_DOC_KEYS.get(d["doc_type"])
        v = (d.get("extraction") or {}).get(k) if k else None
        if isinstance(v, dict) and v.get("value"):
            rows.append({"permanent_id": pid, "application_id": app_id, "document_id": d["id"], "page": v.get("page", 0),
                         "bbox": v.get("bbox"), "entity_type": f"ref_{d['doc_type']}", "key": re.sub(r"\s", "", str(v["value"]).upper()),
                         "display": f"{ENTITY_LABEL.get('ref_' + d['doc_type'])} {v['value']}", "extra": None})
    return rows


def store_entities(app_id: str, rows: list[dict]) -> None:
    with db.tx() as c:
        c.execute("DELETE FROM entities WHERE application_id=?", (app_id,))
        for r in rows:
            c.execute("INSERT INTO entities VALUES (?,?,?,?,?,?,?,?,?)",
                      (r["entity_type"], r["key"], r["display"], r["permanent_id"], r["application_id"], r["document_id"],
                       r["page"], db.j(r["bbox"]) if r["bbox"] else None, db.j(r["extra"]) if r["extra"] else None))


def links(photo_threshold: int = 12) -> list[dict]:
    """All entity collisions across >= 2 institutions."""
    out = []
    rows = db.q("SELECT * FROM entities WHERE entity_type != 'photo'")
    groups = defaultdict(list)
    for r in rows:
        groups[(r["entity_type"], r["key"])].append(r)
    for (et, key), members in groups.items():
        insts = {m["permanent_id"] for m in members}
        if len(insts) >= 2:
            out.append({"type": et, "key": key, "members": members})
    photos = db.q("SELECT * FROM entities WHERE entity_type='photo'")
    for a, b in combinations(photos, 2):
        if a["permanent_id"] == b["permanent_id"]:
            continue
        ea = db.unj(a["extra"], {})
        d = min(hamming(a["key"], b["key"]), hamming(ea.get("phash_mirror", a["key"]), b["key"]))
        if d <= photo_threshold:
            out.append({"type": "photo", "key": f"{a['key']}~{b['key']}", "distance": d, "members": [a, b], "method": "perceptual hash"})
        elif d <= 26:
            # hash is shaken by cropping: confirm candidates geometrically
            m = _orb_check(a["document_id"], b["document_id"])
            if m and m["same"]:
                out.append({"type": "photo", "key": f"{a['key']}~{b['key']}", "distance": d, "members": [a, b],
                            "method": f"ORB keypoints: {m['inliers']} geometric inliers{' (mirrored)' if m['mirrored'] else ''}"})
    return out


_ORB_CACHE: dict[tuple, dict | None] = {}


def _orb_check(doc_a: str, doc_b: str) -> dict | None:
    key = tuple(sorted((doc_a, doc_b)))
    if key not in _ORB_CACHE:
        from pathlib import Path
        from .config import STORE
        from .forensics.image import same_scene
        rows = {r["id"]: r for r in db.q("SELECT id, sha256, filename FROM documents WHERE id IN (?, ?)", key)}
        try:
            raws = [(STORE / f"{rows[k]['sha256']}{Path(rows[k]['filename']).suffix.lower()}").read_bytes() for k in key]
            _ORB_CACHE[key] = same_scene(*raws)
        except Exception:  # noqa: BLE001
            _ORB_CACHE[key] = None
    return _ORB_CACHE[key]


def network() -> dict:
    """Graph for the UI: institutions as nodes, shared artefacts as edges (grouped per pair)."""
    apps = {a["permanent_id"]: a for a in db.q("SELECT a.*, i.name, i.state, i.source AS inst_source FROM applications a "
                                               "LEFT JOIN institutions i ON i.permanent_id=a.permanent_id WHERE a.source != 'precheck' "
                                               "ORDER BY a.created_at")}
    pairs: dict[tuple, list] = defaultdict(list)
    for L in links():
        insts = sorted({m["permanent_id"] for m in L["members"]})
        for a, b in combinations(insts, 2):
            pairs[(a, b)].append(L)
    nodes = [{"id": pid, "label": a["name"], "state": a["state"], "lane": a["lane"], "application_id": a["id"],
              "linked": any(pid in k for k in pairs)} for pid, a in apps.items()]
    edges = []
    for (a, b), ls in pairs.items():
        by_type = defaultdict(list)
        for L in ls:
            by_type[L["type"]].append(L)
        edges.append({"source": a, "target": b, "weight": len(ls),
                      "kinds": {k: len(v) for k, v in by_type.items()},
                      "severity": "critical" if any(SEVERITY[k] == "critical" for k in by_type) else "high",
                      "items": [_item(L) for L in ls]})
    return {"nodes": nodes, "edges": edges}


def _item(L):
    m = L["members"]
    return {"type": L["type"], "label": ENTITY_LABEL.get(L["type"], L["type"]), "distance": L.get("distance"),
            "members": [{"permanent_id": x["permanent_id"], "application_id": x["application_id"], "document_id": x["document_id"],
                         "display": x["display"], "page": x["page"], "bbox": db.unj(x["bbox"]) if x.get("bbox") else None,
                         "extra": db.unj(x["extra"], {}) if x.get("extra") else {}} for x in m]}


def findings_by_application() -> dict[str, list[dict]]:
    """Turn collisions into per-application findings (each side gets one, with evidence from both)."""
    names = {i["permanent_id"]: i["name"] for i in db.q("SELECT permanent_id, name FROM institutions")}
    out: dict[str, list[dict]] = defaultdict(list)
    grouped: dict[tuple, list] = defaultdict(list)
    for L in links():
        for m in L["members"]:
            others = sorted({x["permanent_id"] for x in L["members"] if x["permanent_id"] != m["permanent_id"]})
            et_key = "faculty" if L["type"] in ("faculty_id", "faculty_pan") else L["type"]
            grouped[(m["application_id"], et_key, tuple(others))].append((m, L))
    verified_docs = {v["document_id"] for v in db.q("SELECT document_id FROM verifications WHERE status='verified' "
                                                     "AND connector NOT IN ('qr_payload','digital_signature')")}
    sizes = {d["id"]: db.unj(d["page_sizes"], [[0, 0]])[0] for d in db.q("SELECT id, page_sizes FROM documents WHERE doc_type='infra_photo'")}
    taken = {d["id"]: (db.unj(d["forensics"], {}).get("exif") or {}).get("taken", "9999")
             for d in db.q("SELECT id, forensics FROM documents WHERE doc_type='infra_photo'")}

    def likely_original(m, L) -> str | None:
        """Explain why this side is probably the legitimate holder, if the evidence says so."""
        if L["type"].startswith("ref_") and m["document_id"] in verified_docs:
            return "this institution's copy is confirmed by the issuing authority"
        if L["type"] == "photo":
            other = next(x for x in L["members"] if x is not m)
            a, b = sizes.get(m["document_id"], [0, 0]), sizes.get(other["document_id"], [0, 0])
            if a[0] * a[1] > b[0] * b[1] and taken.get(m["document_id"], "9") <= taken.get(other["document_id"], "9"):
                return "this copy has the higher resolution and the earlier capture time, so it is likely the original"
        return None

    for (app_id, et, others), items in grouped.items():
        other_names = ", ".join(names.get(o, o) for o in others)
        why_holder = [likely_original(m, L) for m, L in items]
        holder = all(why_holder)
        ev = []
        for m, L in items:
            for x in L["members"]:
                ev.append({"doc_id": x["document_id"], "page": x["page"], "bbox": db.unj(x["bbox"]) if x.get("bbox") else None,
                           "label": x["display"], "kind": "network", "permanent_id": x["permanent_id"], "application_id": x["application_id"],
                           "source": "form" if x["document_id"] is None else None, "field": "faculty" if x["document_id"] is None else None,
                           "row": db.unj(x["extra"], {}).get("row") if x.get("extra") else None})
        n = len(items)
        if et == "faculty":
            # one person may match by both ID and PAN+DOB: count people (roster rows), and say how each matched
            rows: dict[int, set] = {}
            for m, L in items:
                rows.setdefault(m["page"], set()).add(L["type"])
            n = len(rows)
            by_id = sum(1 for t in rows.values() if "faculty_id" in t)
            only_pan = sum(1 for t in rows.values() if t == {"faculty_pan"})
            title = f"{n} faculty member(s) also on the roster of {other_names}"
            detail = (f"{n} people on this roster also appear on {other_names}'s roster: {by_id} with the same AICTE faculty ID"
                      + (f", and {only_pan} under a different faculty ID but the same PAN and date of birth (re-registered)" if only_pan else "")
                      + ". This may be a transfer not yet updated, or the same person counted at two institutions. Check joining/relieving records.")
            seen, dedup = set(), []
            for e in ev:
                k = (e["application_id"], e.get("row"))
                if k not in seen:
                    seen.add(k); dedup.append(e)
            ev = dedup
        elif et == "photo":
            title = f"Infrastructure photo also submitted by {other_names}"
            detail = f"The same photograph appears in {other_names}'s evidence (matched by {items[0][1].get('method', 'perceptual hash')}; hash distance {items[0][1].get('distance')}), despite cropping/resizing."
        elif et == "doc_sha":
            title = f"Byte-identical document also submitted by {other_names}"
            detail = "The same file (same SHA-256) was uploaded by another institution."
        else:
            title = f"{ENTITY_LABEL.get(et, et)} also used by {other_names}"
            detail = f"{ENTITY_LABEL.get(et, et)} {items[0][1]['key']} should be unique to one institution but appears on documents of {other_names}."
        sev, status = SEVERITY.get(et, "high"), "fail"
        if holder:
            sev, status = "low", "warn"
            title = title.replace("also", "re-used by", 1) if " also " in title else title
            detail += f" However, {why_holder[0]}; the other application is the likely copy."
        out[app_id].append({"rule_id": f"NET-{et.upper()}", "kind": "network", "severity": sev, "status": status,
                            "title": title, "detail": detail, "evidence": ev, "remedy": "Seek clarification and verify with the other institution's records before any action.",
                            "citation": {"ref": "Clause 2.3.5 (b)", "quote": "If any document submitted is found to be fraudulent, criminal case shall be filed against the Director/"}})
    return out
