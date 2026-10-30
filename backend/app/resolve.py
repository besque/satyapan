"""Find which AICTE institution a complaint is about, and say why.

The complainant's text is compared with every institution in the master on four signals:
distinctive name words (spelling-tolerant), consonant outline (transliteration-tolerant), acronym,
and place (city / district / state). A quoted Permanent ID settles it. Only a clear winner is linked
automatically; anything close goes to an officer to confirm.
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz

from . import db, settings
from . import textnorm as T

PID = re.compile(r"\b1-\d{7,11}\b")
TOKEN = re.compile(r"[ऀ-ॿ]+|[A-Za-z0-9]+")
AMOUNT = re.compile(r"(?:₹|rs\.?|inr|रु\.?|रुपये)\s?[\d,]{3,}(?:/-)?|\b[\d,]{4,}\s?(?:रुपये|rupees)", re.I)
DATE = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b|\b\d{1,2}\s(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s\d{4}\b", re.I)


class Index:
    def __init__(self, rows: list[dict]):
        self.items = []
        for r in rows:
            names = [r["name"], *db.unj(r.get("aliases"), [])]
            forms = []
            for n in names:
                words = T.plain_words(n)
                d = T.distinct(words)
                forms.append({"name": n, "dist": " ".join(d), "skel": " ".join(T.skeleton(w) for w in d),
                              "acr": T.initials(n), "is_alias": n != r["name"]})
            self.items.append({**r, "forms": forms, "type_set": {r.get("inst_type")},
                               "city_f": T.fold(r["city"] or ""), "district_f": T.fold(r.get("district") or ""),
                               "state_f": T.fold(r["state"] or "")})
        self.cities = {i["city_f"] for i in self.items if i["city_f"]} | {i["district_f"] for i in self.items if i["district_f"]}
        self.by_id = {i["permanent_id"]: i for i in self.items}


_index: Index | None = None


def index() -> Index:
    global _index
    if _index is None:
        _index = Index(db.q("SELECT * FROM institutions"))
    return _index


def reload() -> None:
    global _index
    _index = None


def _place_hits(words: list[str], places: set[str]) -> set[str]:
    hits = set()
    for w in words:
        if len(w) < 4:
            continue
        for p in places:
            if w == p or (T.skeleton(w) == T.skeleton(p) and fuzz.ratio(w, p) >= 75):
                hits.add(p)
    return hits


def resolve(inst_text: str, context: str = "") -> dict:
    """Return {'state': auto|confirm|unmatched, 'permanent_id', 'confidence', 'candidates': [...]}."""
    ix = index()
    full = f"{inst_text or ''}\n{context or ''}"
    quoted = [m.group(0) for m in PID.finditer(full)]
    m_words = T.plain_words(inst_text or "")
    all_words = T.plain_words(full)
    places = _place_hits(all_words, ix.cities)
    m_dist = [w for w in T.distinct(m_words) if w not in places]
    m_skel = " ".join(T.skeleton(w) for w in m_dist)
    m_types = T.type_words(m_words)
    raw_tokens = {t.lower() for t in re.findall(r"[A-Za-z]{2,8}", inst_text or "")}

    scored = []
    for it in ix.items:
        reasons, conf = [], 0.0
        if it["permanent_id"] in quoted:
            scored.append({"permanent_id": it["permanent_id"], "confidence": 1.0,
                           "reasons": [f"Permanent ID {it['permanent_id']} quoted in the complaint"]})
            continue
        best, best_form = 0.0, None
        for f in it["forms"]:
            if not m_dist or not f["dist"]:
                s = 0.0
            else:
                s = 0.5 * fuzz.token_set_ratio(" ".join(m_dist), f["dist"]) / 100 + 0.5 * fuzz.token_set_ratio(m_skel, f["skel"]) / 100
            if s > best:
                best, best_form = s, f
            if len(f["acr"]) >= 3 and f["acr"] in raw_tokens and best < 0.8:
                best, best_form = 0.8, {**f, "via_acr": True}
        conf = best
        if best_form:
            if best_form.get("via_acr"):
                reasons.append(f"“{best_form['acr'].upper()}” is the short form of {best_form['name']}")
            elif best >= 0.6:
                what = "former name" if best_form["is_alias"] else "name"
                reasons.append(f"Name words match the {what} “{best_form['name']}” ({round(best * 100)}%)")
        here = {it["city_f"], it["district_f"]} - {""}
        if places & here:
            conf += 0.14
            reasons.append(f"Place matches: {it['city']}")
        elif places:
            conf -= 0.2
            reasons.append(f"Text mentions another place; this institution is in {it['city']}")
        elif it["state_f"] and it["state_f"] in all_words:
            conf += 0.05
            reasons.append(f"State matches: {it['state']}")
        if m_types and it.get("inst_type") not in m_types:
            conf -= 0.1
            reasons.append(f"Complaint says {', '.join(sorted(m_types)).lower()}; this is a {it['inst_type'].lower()} institution")
        # tie-breaker between sister institutions (same trust, same town): the full name, generic words included
        full = fuzz.token_set_ratio(" ".join(m_words), " ".join(T.plain_words(it["name"]))) / 100 if best else 0.0
        conf = max(0.0, min(conf, 0.95)) + 0.04 * full
        scored.append({"permanent_id": it["permanent_id"], "confidence": round(min(conf, 0.99), 3), "reasons": reasons})

    scored.sort(key=lambda x: -x["confidence"])
    top = scored[:3]
    for c in top:
        r = ix.by_id[c["permanent_id"]]
        c.update(name=r["name"], city=r["city"], state=r["state"], region=r["region"])
    cfg = settings.get()["matching"]
    s1 = top[0]["confidence"] if top else 0
    s2 = top[1]["confidence"] if len(top) > 1 else 0
    if s1 >= 1.0 or (s1 >= cfg["auto_link"] and s1 - s2 >= cfg["margin"]):
        state = "auto"
    elif s1 >= 0.5:
        state = "confirm"
    else:
        state = "unmatched"
    return {"state": state, "permanent_id": top[0]["permanent_id"] if state == "auto" else None,
            "confidence": s1, "candidates": top}


def spans(text: str, permanent_id: str | None) -> list[dict]:
    """Character ranges worth highlighting in a complaint, each with the reason it is marked."""
    out: list[dict] = []
    if not text:
        return out
    for m in PID.finditer(text):
        out.append({"start": m.start(), "end": m.end(), "kind": "id", "label": "Permanent ID"})
    for m in AMOUNT.finditer(text):
        out.append({"start": m.start(), "end": m.end(), "kind": "amount", "label": "Amount"})
    for m in DATE.finditer(text):
        out.append({"start": m.start(), "end": m.end(), "kind": "date", "label": "Date"})
    it = index().by_id.get(permanent_id or "")
    if it:
        name_words = set()
        for f in it["forms"]:
            name_words |= set(f["dist"].split())
        acrs = {f["acr"] for f in it["forms"] if len(f["acr"]) >= 3}
        places = {it["city_f"], it["district_f"]} - {""}
        for m in TOKEN.finditer(text):
            w = T.plain_words(m.group(0))
            if not w:
                continue
            w0 = w[0]
            if m.group(0).lower() in acrs:
                out.append({"start": m.start(), "end": m.end(), "kind": "institution", "label": f"Short form of {it['name']}"})
            elif len(w0) >= 4 and any(w0 == p or (T.skeleton(w0) == T.skeleton(p) and fuzz.ratio(w0, p) >= 75) for p in places):
                out.append({"start": m.start(), "end": m.end(), "kind": "place", "label": f"Place: {it['city']}"})
            elif len(w0) >= 4 and w0 not in T.GENERIC and any(fuzz.ratio(w0, n) >= 82 for n in name_words):
                out.append({"start": m.start(), "end": m.end(), "kind": "institution", "label": f"Part of the name {it['name']}"})
    out.sort(key=lambda s: s["start"])
    merged: list[dict] = []
    for s in out:
        if merged and s["start"] < merged[-1]["end"]:
            continue
        merged.append(s)
    return merged
