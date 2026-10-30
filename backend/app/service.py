"""Operations on cases. Every change is written to the audit log and re-checks overlaps."""
from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timedelta, timezone

from . import ai, audit, db, overlap, resolve, settings
from .workflow import ACTIONS, apply_action, d, due_for, now, pick_officer, timeline, today

SALT = "samanvay-contact-v1"
DEVANAGARI = re.compile(r"[ऀ-ॿ]")


class Blocked(Exception):
    """An action would clash with another bureau's work and was not yet acknowledged."""

    def __init__(self, warnings):
        super().__init__("coordination check")
        self.warnings = warnings


def contact_hash(contact: str | None) -> str | None:
    """Complainant phone / e-mail is stored only as a salted fingerprint, enough to spot repeat filings."""
    if not contact:
        return None
    c = contact.strip().lower()
    digits = re.sub(r"\D", "", c)
    key = digits[-10:] if "@" not in c and len(digits) >= 10 else c
    return hashlib.sha256((SALT + key).encode()).hexdigest()[:20]


def lang_of(text: str) -> str:
    n = len(DEVANAGARI.findall(text or ""))
    return "hi" if n > 0.3 * max(1, len(re.sub(r"\s", "", text or ""))) else "en"


def next_id(bureau: str, year: int) -> str:
    pre = f"{bureau}/{year}/"
    r = db.q1("SELECT id FROM cases WHERE id LIKE ? ORDER BY id DESC LIMIT 1", (pre + "%",))
    n = int(r["id"].split("/")[-1]) + 1 if r else 1
    return f"{pre}{n:04d}"


def analyse(inst_text: str, subject: str, description: str, bureau: str | None = None, exclude: str | None = None,
            complainant: str | None = None) -> dict:
    """What the system makes of a complaint before it is saved: institution, nature, likely duplicates."""
    m = resolve.resolve(inst_text, f"{subject}\n{description}")
    cats = ai.classify(f"{subject}. {description}", inst_text=inst_text)
    home = settings.category(cats[0]["category"])["bureau"] if cats else None
    dup = []
    pid = m["permanent_id"] or (m["candidates"][0]["permanent_id"] if m["candidates"] and m["confidence"] >= 0.5 else None)
    if pid:
        draft = {"id": "__draft__", "subject": subject, "description": description, "category": cats[0]["category"] if cats else None,
                 "lang": lang_of(description), "received_on": today().isoformat(), "contact_hash": None, "complainant": complainant,
                 "category_ai": cats}
        others = [c for c in db.q("SELECT * FROM cases WHERE permanent_id=?", (pid,)) if c["id"] != exclude]
        if others:
            v = ai.embed([ai.case_text(draft)])[0]
            vecs = ai.case_vectors(others)
            for o in others:
                pm = overlap.same_matter(draft, o, v, vecs[o["id"]], {})
                if pm["score"] >= settings.get()["matching"]["same_matter"] - 0.04:
                    dup.append({"case": o["id"], "bureau": o["bureau"], "status": o["status"], "subject": o["subject"],
                                "score": pm["score"], "reasons": pm["reasons"]})
        dup.sort(key=lambda x: -x["score"])
    return {"match": m, "categories": cats, "suggested_bureau": home,
            "wrong_bureau": bool(bureau and home and bureau != home), "possible_duplicates": dup[:5],
            "spans": resolve.spans(description, pid), "lang": lang_of(description)}


def create_case(data: dict, actor: str, role: str, ts: str | None = None, refresh: bool = True, log: bool = True) -> dict:
    ts = ts or now().isoformat()
    received = data.get("received_on") or ts[:10]
    m = resolve.resolve(data.get("inst_text", ""), f"{data.get('subject', '')}\n{data.get('description', '')}")
    if data.get("permanent_id"):
        pid, state = data["permanent_id"], "confirmed"
    else:
        pid, state = m["permanent_id"], m["state"]
    cats = ai.classify(f"{data.get('subject', '')}. {data.get('description', '')}", inst_text=data.get("inst_text"))
    category = data.get("category") or cats[0]["category"]
    inst = db.q1("SELECT region FROM institutions WHERE permanent_id=?", (pid,)) if pid else None
    bureau = data["bureau"]
    cid = data.get("id") or next_id(bureau, int(received[:4]))
    row = {
        "id": cid, "bureau": bureau, "ext_ref": data.get("ext_ref"), "source": data.get("source", "Letter"),
        "received_on": received, "complainant": data.get("complainant"), "complainant_type": data.get("complainant_type"),
        "contact_hash": contact_hash(data.get("contact")), "inst_text": data.get("inst_text"), "permanent_id": pid,
        "match": {"confidence": m["confidence"], "candidates": m["candidates"], "state": m["state"]}, "match_state": state,
        "category": category, "category_ai": cats, "subject": data.get("subject"), "description": data.get("description"),
        "lang": lang_of(data.get("description", "")), "status": "pending", "officer_id": data.get("officer_id") or pick_officer(bureau, (inst or {}).get("region")),
        "last_action": "Received", "last_action_on": ts, "next_action": "Take up the complaint",
        "next_due": (d(received) + timedelta(days=7)).isoformat(), "due_on": due_for(category, received),
        "disposed_on": None, "outcome": None, "esc_level": -1, "created_at": ts,
    }
    db.insert("cases", row)
    db.insert("actions", {"case_id": cid, "ts": ts, "kind": "received", "bureau": bureau, "actor": actor,
                          "remarks": f"Received via {row['source']}" + (f" ({row['ext_ref']})" if row["ext_ref"] else ""),
                          "to_bureau": None, "extra": {}})
    if log:
        audit.log(actor, role, "case.received", cid, {"bureau": bureau, "permanent_id": pid, "match": state, "category": category})
    if refresh and pid and state in ("auto", "confirmed"):
        overlap.refresh(pid, ts)
    return row


def add_action(case_id: str, kind: str, remarks: str, actor: str, role: str, acknowledged: bool = False,
               reason: str = "", to_bureau: str | None = None, ts: str | None = None, check: bool = True,
               refresh: bool = True, log: bool = True) -> dict:
    c = db.q1("SELECT * FROM cases WHERE id=?", (case_id,))
    if kind not in ACTIONS:
        raise ValueError("unknown action")
    warnings = overlap.precheck(c, kind) if check else []
    if warnings and not acknowledged:
        raise Blocked(warnings)
    ts = ts or now().isoformat()
    inst = db.q1("SELECT region FROM institutions WHERE permanent_id=?", (c["permanent_id"],)) if c["permanent_id"] else None
    extra = {"warnings_seen": [w["case"] for w in warnings], "reason": reason} if warnings else {}
    changed = apply_action({**c, "region": (inst or {}).get("region")}, kind, ts, actor, remarks, to_bureau, extra)
    if log:
        audit.log(actor, role, f"case.{kind}", case_id, {"remarks": remarks, "to": to_bureau, **extra})
    if kind == "transferred" and to_bureau:
        overlap.notify_bureaus([to_bureau], "transfer", f"{case_id} transferred to you by {c['bureau']}", case_id=case_id, ts=ts,
                               key=f"{case_id}:transfer:{ts}")
    if refresh and c["permanent_id"] and c["match_state"] in ("auto", "confirmed"):
        overlap.refresh(c["permanent_id"], ts, actor)
    return changed


def confirm_institution(case_id: str, pid: str | None, actor: str, role: str) -> None:
    c = db.q1("SELECT * FROM cases WHERE id=?", (case_id,))
    state = "confirmed" if pid else "not_aicte"
    db.update("cases", "id", case_id, {"permanent_id": pid, "match_state": state})
    audit.log(actor, role, "case.institution_confirmed", case_id, {"from": c["permanent_id"], "to": pid})
    for p in {c["permanent_id"], pid} - {None}:
        overlap.refresh(p, actor=actor)


def set_link(a: str, b: str, kind: str, actor: str, role: str, reason: str = "") -> None:
    x, y = overlap.pair_key(a, b)
    db.insert("links", {"a": x, "b": y, "kind": kind, "actor": actor, "reason": reason, "ts": now().isoformat()}, replace=True)
    audit.log(actor, role, f"link.{kind}", f"{x}|{y}", {"reason": reason})
    for cid in (x, y):
        db.insert("actions", {"case_id": cid, "ts": now().isoformat(), "kind": "linked", "bureau": None, "actor": actor,
                              "remarks": f"{'Same matter as' if kind == 'same' else 'Not the same matter as'} {y if cid == x else x}" + (f": {reason}" if reason else ""),
                              "to_bureau": None, "extra": {}})
    pid = db.q1("SELECT permanent_id FROM cases WHERE id=?", (x,))["permanent_id"]
    if pid:
        overlap.refresh(pid, actor=actor)


def sweep(on: datetime | None = None, log: bool = True) -> int:
    """Timeline check for every open case: reminders, overdue alerts and escalation up the ladder."""
    on = on or now()
    ladder = settings.get()["escalation"]
    n = 0
    for c in db.q("SELECT * FROM cases WHERE status!='disposed'"):
        tl = timeline(c, on.astimezone().date())
        lvl = tl.get("level", -1)
        if lvl <= (c["esc_level"] if c["esc_level"] is not None else -1):
            continue
        rec = d(c["received_on"])
        total = tl["total"]
        for step in ladder:
            if step["level"] <= (c["esc_level"] if c["esc_level"] is not None else -1) or step["level"] > lvl:
                continue
            when = datetime.combine(rec + timedelta(days=math.ceil(step["at"] * total)), datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=4, minutes=30)
            when = min(when, on)
            text = f"{c['id']}: {step['label']} ({settings.category(c['category'])['label']})"
            overlap.notify_bureaus([c["bureau"]], "timeline", text, case_id=c["id"], ts=when.isoformat(),
                                   key=f"{c['id']}:esc:{step['level']}", role=step["to"])
            if step["to"] == "management":
                overlap.notify_bureaus(["MGMT"], "timeline", text, case_id=c["id"], ts=when.isoformat(),
                                       key=f"{c['id']}:esc:{step['level']}:mgmt", role="management")
            if step["level"] >= 1:
                db.insert("actions", {"case_id": c["id"], "ts": when.isoformat(), "kind": "escalated", "bureau": c["bureau"],
                                      "actor": "system", "remarks": f"{step['label']}: timeline of {total} days", "to_bureau": None,
                                      "extra": {"level": step["level"], "to": step["to"]}})
                if log:
                    audit.log("system", "system", "case.escalated", c["id"], {"level": step["level"], "to": step["to"]}, ts=when.isoformat())
            n += 1
        db.update("cases", "id", c["id"], {"esc_level": lvl})
    return n


def today_iso() -> str:
    return today().isoformat()
