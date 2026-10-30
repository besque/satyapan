"""Compliance after approval: undertakings, document validity, lease extensions and security deposits.

Each item has one holder at a time: the institution until it submits evidence, then the verifying office.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import clock, db, notify, settings
from .clock import add_months, add_years, d, iso
from .engine import WorkflowError, event, hold, inst_code, ro_code

KIND = {"undertaking": "Undertaking", "document": "Document renewal", "lease": "Lease extension", "deposit": "Security deposit"}
STATUS = {"open": "Open", "submitted": "Submitted, to verify", "verified": "Verified", "rejected": "Returned to institution",
          "waived": "Waived", "closed": "Closed"}
OPEN = ("open", "submitted", "rejected")


def item(item_id: str) -> dict:
    it = db.q1("SELECT * FROM items WHERE id=?", (item_id,))
    if not it:
        raise WorkflowError("No such item")
    return it


def institution(pid: str) -> dict:
    return db.q1("SELECT * FROM institutions WHERE pid=?", (pid,)) or {}


def verifier(it: dict) -> str:
    return "RB" if it["verify_by"] == "RB" else ro_code(institution(it["pid"]).get("region") or "Central")


def create(kind: str, pid: str, title: str, due_on: date | None, on: date, cite: str | None, consequence: str = "",
           verify_by: str = "RB", app_id: str | None = None, doc_type: str | None = None, cond: str | None = None,
           detail: str = "", source: str = "test", source_url: str | None = None, extra: dict | None = None,
           actor: str = "system", role: str = "system", status: str = "open") -> dict:
    n = db.q1("SELECT COUNT(*) AS n FROM items")["n"] + 1
    iid = f"C-{n:05d}"
    holder = inst_code(pid) if status in ("open", "rejected") else None
    db.insert("items", {"id": iid, "kind": kind, "pid": pid, "app_id": app_id, "title": title, "detail": detail,
                        "doc_type": doc_type, "cond": cond, "cite": cite, "consequence": consequence,
                        "opened_on": iso(on), "due_on": iso(due_on), "status": status, "holder": holder,
                        "verify_by": verify_by, "evidence": [], "source": source, "source_url": source_url, "extra": extra or {}})
    if source == "test":
        hold(iid, holder, on)
        event(None, on, "created", actor, role, f"{KIND[kind]}: {title}" + (f" (due {due_on:%d %b %Y})" if due_on else ""), item_id=iid)
    return item(iid)


def submit(item_id: str, on: date, note: str, actor: str, role: str, files: list | None = None, extra: dict | None = None) -> dict:
    it = item(item_id)
    if it["status"] not in ("open", "rejected"):
        raise WorkflowError("Nothing to submit for this item now")
    ex = db.unj(it["extra"], {}) or {}
    ex.update(extra or {})
    ex["verify_due"] = iso(on + timedelta(days=settings.get()["alerts"]["verification"]["days"]))
    office = verifier(it)
    db.update("items", "id", item_id, {"status": "submitted", "holder": office, "submitted_on": iso(on), "esc_level": -1,
                                       "evidence": (db.unj(it["evidence"], []) or []) + (files or []), "note": note, "extra": ex})
    hold(item_id, office, on)
    event(None, on, "submitted", actor, role, "Evidence submitted" + (f": {note}" if note else ""), item_id=item_id)
    return item(item_id)


def verify(item_id: str, on: date, ok: bool, reason: str, actor: str, role: str) -> dict:
    it = item(item_id)
    if it["status"] != "submitted":
        raise WorkflowError("Only submitted evidence can be verified")
    if not ok and len((reason or "").strip()) < 5:
        raise WorkflowError("Give the reason for returning it")
    ex = db.unj(it["extra"], {}) or {}
    if ok:
        db.update("items", "id", item_id, {"status": "verified", "holder": None, "closed_on": iso(on), "closed_by": actor, "esc_level": -1})
        hold(item_id, None, on)
        if it["kind"] in ("document", "lease") and ex.get("new_document"):
            _register_renewal(it, ex["new_document"], on)
        event(None, on, "verified", actor, role, "Verified" + (f": {reason}" if reason else ""), item_id=item_id)
        notify.send(f"{item_id}:verified", on, inst_code(it["pid"]), "notice", f"Verified by AICTE: {it['title']}.", item_id=item_id, pid=it["pid"])
    else:
        db.update("items", "id", item_id, {"status": "rejected", "holder": inst_code(it["pid"]), "esc_level": -1})
        hold(item_id, inst_code(it["pid"]), on)
        event(None, on, "returned", actor, role, f"Returned to the institution: {reason}", item_id=item_id)
        notify.send(f"{item_id}:returned:{iso(on)}", on, inst_code(it["pid"]), "notice", f"Returned for correction: {it['title']}. {reason}",
                    item_id=item_id, pid=it["pid"])
    return item(item_id)


def waive(item_id: str, on: date, reason: str, actor: str, role: str) -> dict:
    it = item(item_id)
    if it["status"] not in OPEN:
        raise WorkflowError("This item is already closed")
    if len((reason or "").strip()) < 10:
        raise WorkflowError("Record the reason")
    db.update("items", "id", item_id, {"status": "waived", "holder": None, "closed_on": iso(on), "closed_by": actor})
    hold(item_id, None, on)
    event(None, on, "waived", actor, role, f"Waived by the competent authority: {reason}", item_id=item_id)
    return item(item_id)


def _register_renewal(it: dict, doc: dict, on: date) -> None:
    for old in db.q("SELECT id FROM documents WHERE pid=? AND doc_type=? AND status='current'", (it["pid"], doc["doc_type"])):
        db.update("documents", "id", old["id"], {"status": "superseded"})
    n = db.q1("SELECT COUNT(*) AS n FROM documents")["n"] + 1
    db.insert("documents", {"id": f"D-{n:05d}", "pid": it["pid"], "doc_type": doc["doc_type"], "number": doc.get("number"),
                            "issuer": doc.get("issuer"), "issued_on": doc.get("issued_on"), "valid_until": doc.get("valid_until"),
                            "status": "current", "file_id": doc.get("file_id"), "note": "Renewal verified", "source": "test"})
    if doc["doc_type"] == "lease_deed" and doc.get("valid_until"):
        db.update("institutions", "pid", it["pid"], {"lease_until": doc["valid_until"]})


# ------------------------------------------------------------------------------------ conditions on approval

def condition_due(key: str, on: date) -> date:
    c = settings.get()["conditions"][key]
    if c.get("due_years"):
        return add_years(on, c["due_years"])
    if c.get("due_months"):
        return add_months(on, c["due_months"])
    return d(settings.get()["cycle"]["ay_start"])


def attach_conditions(a: dict, on: date, conditions: list[dict], actor: str, role: str) -> list[dict]:
    out = []
    for c in conditions:
        cfg = settings.get()["conditions"][c["key"]]
        due = d(c.get("due_on")) or condition_due(c["key"], on)
        out.append(create("undertaking", a["pid"], cfg["label"], due, on, cfg.get("cite"), cfg.get("consequence", ""),
                          cfg.get("verify_by", "RB"), app_id=a["id"], cond=c["key"], detail=c.get("detail", ""),
                          extra={"carry_forward": bool(cfg.get("carry_forward"))}, actor=actor, role=role))
    return out


def suggest_conditions(a: dict) -> list[dict]:
    """Conditions the system proposes when an approval is being recorded. The decision-maker chooses."""
    out = []
    defs = db.unj(a.get("deficiencies"), []) or []
    if defs:
        out.append({"key": "letter_deficiencies", "detail": "; ".join(defs), "why": "Deficiencies are still open on this application"})
    if a["nature"] == "new_institution":
        out += [{"key": "faculty_before_start", "why": "New institution (Cl. 1.6 d)"},
                {"key": "affiliation_within_loa", "why": "New institution (Cl. 1.10 b ii)"},
                {"key": "remaining_requirements", "why": "Affidavit undertaking for new institutions"}]
    inst = institution(a["pid"])
    if (db.unj(inst.get("extra"), {}) or {}).get("building_under_construction"):
        out.append({"key": "occupancy_on_completion", "why": "Building under construction (Annexure-1, 1.1 iv)"})
    for c in out:
        c["label"] = settings.get()["conditions"][c["key"]]["label"]
    return out


# ------------------------------------------------------------------------------------ security deposit

LEVEL_OF = {"Diploma": 0, "UG": 1, "PG": 2}


def deposit_amount(inst: dict, programme: str, level: str) -> float:
    dep = settings.get()["deposit"]
    row = dep["amounts"].get(programme) or dep["amounts"]["Engineering"]
    amt = float(row[LEVEL_OF.get(level, 1)] or row[1])
    if inst.get("land") == "lease":
        amt *= 2
    return amt


def create_deposit(a: dict, on: date, actor: str, role: str) -> dict | None:
    inst = institution(a["pid"])
    if (inst.get("ownership") or "").startswith("Government"):
        return None
    dt = db.unj(a.get("detail"), {}) or {}
    programme, level = dt.get("programme", "Engineering"), dt.get("level", "UG")
    amt = deposit_amount(inst, programme, level)
    due = on + timedelta(days=settings.get()["deposit"]["days"])
    return create("deposit", a["pid"], f"Security deposit of Rs {amt:g} lakh with Affidavit 3", due, on, settings.get()["deposit"]["cite"],
                  settings.get()["deposit"]["after"], "RB", app_id=a["id"], detail=f"{programme}, {level}" + (" (doubled: leased land)" if inst.get("land") == "lease" else ""),
                  extra={"amount_lakh": amt, "intimated_on": iso(on)}, actor=actor, role=role)


def deposit_state(it: dict, on: date) -> dict:
    """Where a security deposit stands on the penalty ladder of Cl. 2.25 (f)."""
    ex = db.unj(it["extra"], {}) or {}
    amt = ex.get("amount_lakh", 0)
    if it["status"] in ("verified", "waived", "closed"):
        return {"stage": "paid", "label": "Paid" if it["status"] == "verified" else STATUS[it["status"]]}
    due = d(it["due_on"])
    if on <= due:
        return {"stage": "due", "label": f"Due by {due:%d %b %Y}", "penalty": 0}
    dep = settings.get()["deposit"]
    for st in dep["steps"]:
        mm, dd = (int(x) for x in st["until"].split("-"))
        until = date(due.year, mm, dd)
        if on <= until:
            return {"stage": f"penalty_{st['penalty']}", "label": f"{st['penalty']}% penalty (Rs {amt * st['penalty'] / 100:g} lakh) if paid by {until:%d %b %Y}",
                    "penalty": st["penalty"], "until": iso(until)}
    return {"stage": "withdraw", "label": dep["after"], "penalty": None}


# ------------------------------------------------------------------------------------ lease rule (Cl. 2.1 e)

def max_course_years(programmes: list[dict]) -> int:
    return max([int(p.get("years") or 0) for p in programmes] or [0])


def window_opens(ay_start_year: int) -> date:
    """Application window for the academic year starting in `ay_start_year` (first group opens in November)."""
    first = d(settings.get()["cycle"]["windows"][0]["from"])
    return date(ay_start_year - 1, first.month, first.day)


def lease_block(lease_until: str | date, max_years: int) -> dict | None:
    """First academic year for which EoA cannot be issued: the year the remaining (live) lease is no more than
    the longest course. Returns None if the lease is long enough for the foreseeable future."""
    L = d(lease_until)
    if not L or not max_years:
        return None
    ay0 = d(settings.get()["cycle"]["ay_start"])
    for y in range(ay0.year - 5, L.year + 1):
        start = date(y, ay0.month, ay0.day)
        if add_years(start, max_years) >= L:     # live lease is no more than the longest course (calendar years)
            return {"blocked_ay": f"{y}-{str(y + 1)[2:]}", "ay_start": iso(start), "live_years": round((L - start).days / 365.25, 1),
                    "max_years": max_years, "submit_by": iso(window_opens(y)), "lease_until": iso(L)}
    return None


# ------------------------------------------------------------------------------------ items the system opens by itself

def ensure_document_items(on: date) -> int:
    """Open a renewal item for every current document that expires within the first reminder window."""
    first = max(settings.get()["alerts"]["documents"]["remind_before"])
    made = 0
    rows = db.q("SELECT d.*, i.region FROM documents d JOIN institutions i ON i.pid=d.pid WHERE d.status='current' "
                "AND d.source='test' AND d.valid_until IS NOT NULL AND d.valid_until <= ?", (iso(on + timedelta(days=first)),))
    for doc in rows:
        if db.q1("SELECT id FROM items WHERE kind='document' AND pid=? AND doc_type=? AND status IN ('open','submitted','rejected')",
                 (doc["pid"], doc["doc_type"])):
            continue
        cfg = settings.get()["documents"][doc["doc_type"]]
        create("document", doc["pid"], f"Submit the renewed {cfg['label']}", d(doc["valid_until"]), on, cfg.get("cite"),
               f"Without a valid {cfg['label']} the institution does not meet the APH requirement", cfg.get("verify_by", "RO"),
               doc_type=doc["doc_type"], detail=f"Current certificate valid until {d(doc['valid_until']):%d %b %Y}",
               extra={"document_id": doc["id"]})
        made += 1
    return made


def ensure_lease_items(on: date) -> int:
    months = max(settings.get()["alerts"]["lease"]["remind_before_months"])
    made = 0
    for inst in db.q("SELECT * FROM institutions WHERE land='lease' AND lease_until IS NOT NULL AND source='test'"):
        blk = lease_block(inst["lease_until"], max_course_years(db.unj(inst["programmes"], []) or []))
        if not blk or add_months(d(blk["submit_by"]), -months) > on:
            continue
        if db.q1("SELECT id FROM items WHERE kind='lease' AND pid=? AND status IN ('open','submitted','rejected')", (inst["pid"],)):
            continue
        create("lease", inst["pid"], "Submit the lease extended by 30 years", d(blk["submit_by"]), on, "CL_2_1_E",
               f"EoA cannot be issued from {blk['blocked_ay']} unless the lease is extended (Cl. 2.1 e)", "RO", doc_type="lease_deed",
               detail=(f"Lease ends {d(blk['lease_until']):%d %b %Y}; longest course {blk['max_years']} years; live lease at the start of "
                       f"{blk['blocked_ay']} will be {blk['live_years']} years"), extra={"block": blk})
        made += 1
    return made
