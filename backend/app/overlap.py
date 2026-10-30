"""Cross-bureau overlap detection.

For every institution, the cases held by different bureaus are compared and four kinds of alert are
raised, most serious first:

  conflict   two bureaus have taken actions that clash (settings.yaml `conflicts`)
  duplicate  the same matter is open in two places (same complainant, or the language model finds
             the complaint texts say the same thing, across Hindi and English)
  pattern    several different people complain about the same issue: one inquiry, not many replies
  parallel   the institution has open cases in more than one bureau: they should know of each other

Each alert lists its cases, the evidence for linking them, and a suggested lead bureau. Bureaus
acknowledge alerts; nothing is merged or closed without an officer doing it.
"""
from __future__ import annotations

import hashlib
from datetime import timedelta
from itertools import combinations

from . import ai, audit, db, settings
from . import textnorm as T
from .workflow import d, now, today

KIND = {
    "conflict": {"label": "Conflicting actions", "color": "red", "rank": 0},
    "duplicate": {"label": "Same matter in two places", "color": "orange", "rank": 1},
    "pattern": {"label": "Many complaints, one issue", "color": "violet", "rank": 2},
    "parallel": {"label": "Parallel cases", "color": "grey", "rank": 3},
}
RECENT_DAYS = 90


def _cases_for(pid: str) -> list[dict]:
    cutoff = (today() - timedelta(days=RECENT_DAYS)).isoformat()
    return db.q("SELECT * FROM cases WHERE permanent_id=? AND match_state IN ('auto','confirmed') "
                "AND (status!='disposed' OR disposed_on>=?) ORDER BY received_on", (pid, cutoff))


def _links() -> dict[tuple[str, str], str]:
    return {(r["a"], r["b"]): r["kind"] for r in db.q("SELECT a, b, kind FROM links")}


def pair_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def same_matter(x: dict, y: dict, vx, vy, links=None) -> dict:
    """Score how likely two cases are about the same matter, with the reasons."""
    cfg = settings.get()["matching"]
    links = links if links is not None else _links()
    lk = links.get(pair_key(x["id"], y["id"]))
    if lk == "same":
        return {"score": 1.0, "same": True, "reasons": ["Marked as the same matter by an officer"]}
    if lk == "not_same":
        return {"score": 0.0, "same": False, "reasons": ["Marked as different matters by an officer"]}
    sim = ai.similarity(vx, vy)
    score, reasons = sim, [f"Complaint texts {round(sim * 100)}% similar (language model)"]
    if x["lang"] != y["lang"]:
        reasons[0] += f", across {_lang(x['lang'])} and {_lang(y['lang'])}"
    if x["category"] == y["category"]:
        score += 0.05
        reasons.append(f"Both about: {settings.category(x['category'])['label']}")
    elif not (_close(x) & _close(y)):
        score -= 0.12
    if x.get("contact_hash") and x["contact_hash"] == y.get("contact_hash"):
        score = max(score, 0.95)
        reasons.insert(0, "Same complainant (contact details match)")
    elif _person(x.get("complainant")) and _person(x.get("complainant")) == _person(y.get("complainant")):
        score += 0.08
        reasons.insert(0, "Same complainant name, different contact details")
    gap = abs((d(x["received_on"]) - d(y["received_on"])).days)
    if gap > 180:
        score -= 0.1
    reasons.append(f"Received {gap} days apart")
    score = max(0.0, min(score, 1.0))
    return {"score": round(score, 3), "same": score >= cfg["same_matter"], "reasons": reasons}


def _close(c: dict) -> set[str]:
    """The case's category plus any category the language model rated within 0.05 of its best guess."""
    ai_cats = db.unj(c.get("category_ai"), []) if isinstance(c.get("category_ai"), str) else (c.get("category_ai") or [])
    best = ai_cats[0]["score"] if ai_cats else 0
    return {c["category"]} | {a["category"] for a in ai_cats if a["score"] >= best - 0.05}


def _person(name: str | None) -> str | None:
    """A complainant name usable for matching: two or more words, not an organisation."""
    if not name or any(w in name.lower() for w in ("association", "reference", "caller", "government", "representation",
                                                   "institution", "parents", "students", "members")):
        return None
    words = T.plain_words(name)
    return " ".join(sorted(words)) if len(words) >= 2 else None


def _lang(code: str) -> str:
    return {"hi": "Hindi", "en": "English"}.get(code, code)


def _kinds(case_id: str) -> set[str]:
    return {r["kind"] for r in db.q("SELECT kind FROM actions WHERE case_id=?", (case_id,))}


def _is_open(c: dict) -> bool:
    return c["status"] != "disposed"


def detect(pid: str) -> list[dict]:
    """All overlap alerts for one institution (not stored)."""
    cfg = settings.get()
    cases = _cases_for(pid)
    if len(cases) < 2:
        return []
    vecs = ai.case_vectors(cases)
    links = _links()
    kinds = {c["id"]: _kinds(c["id"]) for c in cases}
    by_id = {c["id"]: c for c in cases}
    pairs = {}
    for x, y in combinations(cases, 2):
        pairs[pair_key(x["id"], y["id"])] = same_matter(x, y, vecs[x["id"]], vecs[y["id"]], links)
    alerts: list[dict] = []
    covered_pairs: set[tuple[str, str]] = set()

    # 1. conflicting actions
    for rule in cfg["conflicts"]:
        A, B = set(rule["a"]), set(rule["b"])
        seen = set()
        for x in cases:
            for y in cases:
                if x["id"] == y["id"] or x["bureau"] == y["bureau"]:
                    continue
                pk = pair_key(x["id"], y["id"])
                if A == B and pk in seen:
                    continue
                if not (kinds[x["id"]] & A and kinds[y["id"]] & B):
                    continue
                if "disposed_resolved" in A and x["status"] != "disposed":
                    continue
                if "disposed_resolved" not in A and not _is_open(x):
                    continue
                if not _is_open(y):
                    continue
                pm = pairs[pk]
                if rule.get("same_matter") and not pm["same"]:
                    continue
                seen.add(pk)
                covered_pairs.add(pk)
                act_x = _first_label(x["id"], A)
                act_y = _first_label(y["id"], B)
                reasons = [f"{x['bureau']} {x['id']}: {act_x}", f"{y['bureau']} {y['id']}: {act_y}"]
                if pm["same"]:
                    reasons += pm["reasons"]
                alerts.append({"kind": "conflict", "rule": rule["id"], "title": rule["title"], "why": rule["why"],
                               "cases": [x["id"], y["id"]], "reasons": reasons,
                               "lead": _lead_conflict(rule["id"], x, y), "key": f"conflict:{rule['id']}:{x['id']}:{y['id']}"})

    # 2. many complaints, one issue
    in_pattern: dict[str, str] = {}
    win = cfg["matching"]["pattern_window_days"]
    by_cat: dict[str, list[dict]] = {}
    for c in cases:
        if c["category"] != "approval_application":
            by_cat.setdefault(c["category"], []).append(c)
    for cat, cs in by_cat.items():
        cs = [c for c in cs if (today() - d(c["received_on"])).days <= win]
        people = {c.get("contact_hash") or c["id"] for c in cs}
        if len(people) >= cfg["matching"]["pattern_min"] and any(_is_open(c) for c in cs):
            label = settings.category(cat)["label"]
            bureaus = sorted({c["bureau"] for c in cs})
            for c in cs:
                in_pattern[c["id"]] = cat
            alerts.append({"kind": "pattern", "rule": cat, "title": f"{len(people)} people report: {label.lower()}",
                           "why": "Several different complainants report the same issue at this institution. One inquiry "
                                  "into the issue settles all of them and avoids separate replies to each complaint.",
                           "cases": [c["id"] for c in cs],
                           "reasons": [f"{len(people)} different complainants within {win} days",
                                       f"Handled by {', '.join(f'{b} ({sum(1 for c in cs if c['bureau'] == b)})' for b in bureaus)}"],
                           "lead": "ARC" if cat == "ragging" else ("RB" if settings.category(cat)["bureau"] == "RB" or len(bureaus) > 1 or len(people) >= 5 else settings.category(cat)["bureau"]),
                           "key": f"pattern:{pid}:{cat}"})

    # 3. same matter in two places
    parent = {c["id"]: c["id"] for c in cases}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    dup_reasons: dict[tuple[str, str], dict] = {}
    for (a, b), pm in pairs.items():
        x, y = by_id[a], by_id[b]
        if not pm["same"] or (a, b) in covered_pairs or not (_is_open(x) or _is_open(y)):
            continue
        same_person = bool(x.get("contact_hash") and x["contact_hash"] == y.get("contact_hash"))
        if x["bureau"] == y["bureau"] and x["officer_id"] == y["officer_id"] and not same_person:
            continue
        if in_pattern.get(a) and in_pattern.get(a) == in_pattern.get(b) and not same_person:
            continue
        if x["bureau"] == y["bureau"] and not same_person and pm["reasons"][0] != "Marked as the same matter by an officer":
            continue
        parent[find(a)] = find(b)
        dup_reasons[(a, b)] = pm
    groups: dict[str, list[str]] = {}
    for c in cases:
        if any(c["id"] in k for k in dup_reasons):
            groups.setdefault(find(c["id"]), []).append(c["id"])
    for members in groups.values():
        if len(members) < 2:
            continue
        cs = [by_id[m] for m in members]
        reasons = []
        for (a, b), pm in dup_reasons.items():
            if a in members:
                reasons.append(f"{a} ↔ {b}: " + "; ".join(pm["reasons"]))
        bureaus = sorted({c["bureau"] for c in cs})
        first = min(cs, key=lambda c: c["received_on"])
        home = settings.category(first["category"])["bureau"]
        lead = home if home in bureaus else first["bureau"]
        where = " and ".join(bureaus) if len(bureaus) > 1 else f"two {bureaus[0]} files"
        alerts.append({"kind": "duplicate", "rule": "same-matter", "title": f"Same matter open at {where}",
                       "why": "These cases are about the same matter. One bureau should lead and the others link their "
                              "files to it, so the institution receives one consistent communication.",
                       "cases": [c["id"] for c in cs], "reasons": reasons, "lead": lead,
                       "key": f"duplicate:{pid}:{first['id']}"})

    # 4. parallel cases
    open_cases = [c for c in cases if _is_open(c)]
    bureaus = sorted({c["bureau"] for c in open_cases})
    covered = {cid for a in alerts for cid in a["cases"]}
    if len(bureaus) >= 2 and any(c["id"] not in covered for c in open_cases):
        alerts.append({"kind": "parallel", "rule": "parallel", "title": f"Open cases at {', '.join(bureaus)}",
                       "why": "Different bureaus are dealing with this institution at the same time. Each should know "
                              "what the others are doing before acting.",
                       "cases": [c["id"] for c in open_cases],
                       "reasons": [f"{c['bureau']} {c['id']}: {settings.category(c['category'])['label']} ({c['last_action'] or 'received'})" for c in open_cases],
                       "lead": None, "key": f"parallel:{pid}"})
    alerts.sort(key=lambda a: KIND[a["kind"]]["rank"])
    return alerts


def _first_label(case_id: str, kinds: set[str]) -> str:
    from .workflow import ACTIONS
    r = db.q1(f"SELECT kind, ts FROM actions WHERE case_id=? AND kind IN ({','.join('?' * len(kinds))}) ORDER BY ts DESC LIMIT 1",
              [case_id, *kinds])
    return f"{ACTIONS[r['kind']]['label']} on {r['ts'][:10]}" if r else ""


def _lead_conflict(rule: str, x: dict, y: dict) -> str:
    if rule == "approve-while-penal":
        return x["bureau"]
    if rule == "closed-while-inquiry":
        return y["bureau"]
    if rule == "parallel-inquiry":
        return "RO" if "RO" in (x["bureau"], y["bureau"]) else x["bureau"]
    home = settings.category(x["category"])["bureau"]
    return home if home in (x["bureau"], y["bureau"]) else x["bureau"]


def _cid(key: str) -> str:
    return "CO-" + hashlib.sha1(key.encode()).hexdigest()[:8].upper()


def refresh(pid: str, ts: str | None = None, actor: str = "system", log: bool = True) -> list[dict]:
    """Detect alerts for an institution and store them; new alerts notify the bureaus concerned.
    Alerts no longer detected are closed as 'cleared'."""
    ts = ts or now().isoformat()
    found = detect(pid)
    existing = {r["id"]: r for r in db.q("SELECT * FROM coordination WHERE permanent_id=?", (pid,))}
    keep = set()
    for a in found:
        cid = _cid(a["key"])
        keep.add(cid)
        row = existing.get(cid)
        bureaus = sorted({db.q1("SELECT bureau FROM cases WHERE id=?", (c,))["bureau"] for c in a["cases"]})
        if row and row["status"] not in ("cleared",):
            added = set(a["cases"]) - set(db.unj(row["cases"], []))
            db.update("coordination", "id", cid, {"cases": a["cases"], "reasons": a["reasons"], "title": a["title"], "updated_at": ts})
            if added and row["status"] != "resolved":
                db.update("coordination", "id", cid, {"status": "open", "acks": {}})
                notify_bureaus(bureaus, "coordination", f"New case added to: {a['title']}", coord_id=cid, ts=ts,
                               key=f"{cid}:added:{','.join(sorted(added))}")
            continue
        db.insert("coordination", {"id": cid, "permanent_id": pid, "kind": a["kind"], "rule": a["rule"], "title": a["title"],
                                   "why": a["why"], "cases": a["cases"], "reasons": a["reasons"], "lead": a["lead"],
                                   "status": "open", "acks": {}, "created_at": ts, "updated_at": ts, "closed_note": None},
                  replace=True)
        if log:
            audit.log(actor, "system", "coordination.raised", cid, {"kind": a["kind"], "cases": a["cases"], "lead": a["lead"]}, ts=ts)
        inst = db.q1("SELECT name FROM institutions WHERE permanent_id=?", (pid,))["name"]
        text = f"{KIND[a['kind']]['label']}: {inst}. {a['title']}"
        if a["kind"] != "parallel":
            notify_bureaus(bureaus, "coordination", text, coord_id=cid, ts=ts, key=f"{cid}:raised")
        if a["kind"] == "conflict":
            notify_bureaus(["MGMT"], "coordination", text, coord_id=cid, ts=ts, key=f"{cid}:raised:mgmt", role="management")
    for cid, row in existing.items():
        if cid not in keep and row["status"] in ("open", "acknowledged"):
            db.update("coordination", "id", cid, {"status": "cleared", "updated_at": ts,
                                                  "closed_note": "No longer overlapping (cases disposed or unlinked)"})
    return found


def notify_bureaus(bureaus, kind, text, case_id=None, coord_id=None, ts=None, key=None, role="officer"):
    for b in bureaus:
        k = f"{key}:{b}" if key else None
        with db.tx() as c:
            c.execute("INSERT OR IGNORE INTO notifications (key, to_bureau, to_role, kind, case_id, coord_id, text, created_at) "
                      "VALUES (?,?,?,?,?,?,?,?)", (k, b, role, kind, case_id, coord_id, text, ts or now().isoformat()))


def precheck(case: dict, kind: str) -> list[dict]:
    """Before an officer records an action: what other bureaus are doing that this would clash with."""
    if not case.get("permanent_id") or kind in ("note", "accepted", "reopened"):
        return []
    cfg = settings.get()
    others = [c for c in _cases_for(case["permanent_id"]) if c["id"] != case["id"] and c["bureau"] != case["bureau"]]
    if not others:
        return []
    vecs = ai.case_vectors([case, *others])
    links = _links()
    out = []
    for o in others:
        ok = _kinds(o["id"])
        pm = same_matter(case, o, vecs[case["id"]], vecs[o["id"]], links)
        for rule in cfg["conflicts"]:
            A, B = set(rule["a"]), set(rule["b"])
            hit = (kind in A and ok & B and _is_open(o)) or (kind in B and ok & A and
                                                              (_is_open(o) if "disposed_resolved" not in A else o["status"] == "disposed"))
            if hit and (not rule.get("same_matter") or pm["same"]):
                out.append({"severity": "red", "case": o["id"], "bureau": o["bureau"], "title": rule["title"], "why": rule["why"],
                            "their_action": o["last_action"], "their_on": (o["last_action_on"] or "")[:10]})
        # moving or merging a file towards the bureau that already holds the matter is the coordination itself
        if pm["same"] and _is_open(o) and kind not in ("disposed_merged", "transferred") and not any(w["case"] == o["id"] for w in out):
            out.append({"severity": "orange", "case": o["id"], "bureau": o["bureau"], "title": f"The same matter is open at {o['bureau']}",
                        "why": "; ".join(pm["reasons"]), "their_action": o["last_action"], "their_on": (o["last_action_on"] or "")[:10]})
    return out
