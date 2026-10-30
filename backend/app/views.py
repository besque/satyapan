"""Read models for the screens: lists, the application page, dashboards and reports."""
from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta

from . import compliance, db, engine, settings
from .clock import add_months, d, iso
from .engine import COMMITTEES, holder_kind, holder_label

RISK_ORDER = {"will_miss": 0, "fast_track": 1, "at_risk": 2, "on_track": 3, None: 4}
STAFF = ("rb", "ro", "committee", "ec", "head", "admin")


def median(xs: list) -> float | None:
    return round(statistics.median(xs), 1) if xs else None


def open_holds() -> dict:
    return {r["ref"]: r["from_on"] for r in db.q("SELECT ref, from_on FROM holds WHERE to_on IS NULL")}


def all_splits(on: date) -> dict:
    holds: dict = defaultdict(list)
    for r in db.q("SELECT ref, holder, from_on, to_on FROM holds ORDER BY id"):
        holds[r["ref"]].append(r)
    out: dict = defaultdict(lambda: {"institution": 0, "aicte": 0, "by": {}})
    for a in db.q("SELECT id, nature, region FROM applications"):
        out[a["id"]] = engine.split_holds(holds.get(a["id"], []), on, engine.queue_until(a))
    return out


def office_of(code: str) -> str:
    if code.startswith("RO:"):
        return "Regional Offices"
    if code.startswith("COMMITTEE:"):
        return "Expert committees"
    if code.startswith("INST:"):
        return "Institutions"
    return {"RB": "Regulation Bureau", "EC": "Executive Committee", "QUEUE": "Queue until committees start"}.get(code, code)


# ------------------------------------------------------------------------------------ applications

APP_SQL = ("SELECT a.*, i.name AS inst_name, i.city, s.stage AS s_stage, s.phase AS s_phase, s.holder AS s_holder, "
           "s.due_on AS s_due, s.opened_on AS s_opened, s.meeting_on AS s_meeting, s.mode AS s_mode, s.closed_on AS s_closed, "
           "s.extra AS s_extra, s.attempt AS s_attempt, s.id AS s_id FROM applications a JOIN institutions i ON i.pid=a.pid "
           "LEFT JOIN steps s ON s.id=a.step_id")


def _step_of(r: dict) -> dict | None:
    if r.get("s_id") is None or r.get("s_closed"):
        return None
    return {"id": r["s_id"], "stage": r["s_stage"], "phase": r["s_phase"], "holder": r["s_holder"], "due_on": r["s_due"],
            "opened_on": r["s_opened"], "meeting_on": r["s_meeting"], "mode": r["s_mode"], "extra": r["s_extra"],
            "attempt": r["s_attempt"], "closed_on": None}


def app_row(r: dict, on: date, holds: dict | None = None) -> dict:
    step = _step_of(r)
    cd = engine.countdown(r, step, on) if step else None
    due = d(step["due_on"]) if step else None
    since = d((holds or {}).get(r["id"])) if step else None
    return {
        "id": r["id"], "pid": r["pid"], "institution": r["inst_name"], "city": r.get("city"), "region": r["region"],
        "nature": r["nature"], "nature_label": settings.nature(r["nature"])["label"], "status": r["status"],
        "status_label": engine.STATUS.get(r["status"], r["status"]), "stage": step["stage"] if step else r["stage"],
        "stage_label": settings.stage(step["stage"])["short"] if step else None, "phase": step["phase"] if step else None,
        "task": engine.task_text(step) if step else None, "holder": step["holder"] if step else None,
        "holder_label": holder_label(step["holder"], r["inst_name"]) if step else None,
        "holder_kind": holder_kind(step["holder"]) if step else None, "with_days": (on - since).days if since else None,
        "due_on": iso(due), "overdue": max(0, (on - due).days) if due else 0, "days_left": (due - on).days if due else None,
        "meeting_on": step["meeting_on"] if step else None, "mode": step["mode"] if step else None,
        "risk": cd["risk"] if cd else None, "risk_label": cd["risk_label"] if cd else None, "spare": cd["spare"] if cd else None,
        "spare_fast": cd["spare_fast"] if cd else None, "finish_by": cd["finish_by"] if cd else None, "hold_by": cd.get("hold_by") if cd else None,
        "deadline": cd["deadline"] if cd else None, "why": cd["why"] if cd else None, "esc_level": r["esc_level"] if step else -1,
        "submitted_on": r["submitted_on"], "decided_on": r["decided_on"], "decision": r["decision"],
    }


def app_rows(on: date, where: str = "", args: tuple = ()) -> list[dict]:
    holds = open_holds()
    return [app_row(r, on, holds) for r in db.q(f"{APP_SQL} {where} ORDER BY a.id", args)]


def urgency(r: dict) -> tuple:
    return (RISK_ORDER.get(r.get("risk")), -(r.get("overdue") or 0), r.get("due_on") or "9999")


def route_view(a: dict, steps: list[dict], step: dict | None, cd: dict | None) -> dict:
    n = settings.nature(a["nature"])
    chips = []
    for s in steps:
        cur = step is not None and s["id"] == step["id"]
        chips.append({"stage": s["stage"], "label": settings.stage(s["stage"])["short"], "state": "current" if cur else "done",
                      "outcome": s["outcome"], "outcome_label": engine.OUTCOME.get(s["outcome"] or "", ""), "opened_on": s["opened_on"],
                      "closed_on": s["closed_on"], "attempt": s["attempt"], "meeting_on": s["meeting_on"], "mode": s["mode"],
                      "holder_label": holder_label(s["holder"]) if cur else None})
    if step and cd:
        chips += [{"stage": s, "label": settings.stage(s)["short"], "state": "next"} for s in cd["path"]]
        visited = {s["stage"] for s in steps}
        maybe = []
        if step["stage"] in ("self_disclosure", "scrutiny"):
            maybe += ["compliance", "re_scrutiny"]
        for s in n.get("aa") or []:
            if s not in visited and s not in cd["path"]:
                maybe.append(s)
        chips += [{"stage": s, "label": settings.stage(s)["short"], "state": "maybe"} for s in maybe]
    table = {"self_disclosure": "Yes" if "self_disclosure" in n["route"] else "–",
             "scrutiny": "Yes" if "scrutiny" in n["route"] else "–", "evc": "Yes" if "evc" in n["route"] else "–",
             "sac_shc": "AA" if n.get("aa") else "–"}
    return {"chips": chips, "table": table, "chapter": n.get("chapter", "II")}


def stage_actions(u: dict, a: dict, step: dict | None) -> dict:
    if not step:
        return {}
    role, offices = u["role"], set(u.get("offices") or [])
    st, ph = step["stage"], step["phase"]
    out: dict = {}
    if st in COMMITTEES:
        cfg = settings.stage(st)
        sched_office = "RB" if cfg.get("schedule_by") == "RB" else engine.ro_code(a["region"])
        if sched_office in offices:
            out["schedule"] = {"lead": cfg.get("lead", 7), "modes": ["online", "physical"], "phase": ph}
        if ph == "scheduled" and role == "committee":
            out["outcome"] = {"options": ["recommend", "not_recommend", "fresh_evc"] if st == "sac" else ["in_order", "deficient"]}
    if st == "self_disclosure" and role == "rb":
        out["outcome"] = {"options": ["in_order", "deficient"]}
    if role == "institution" and u.get("pid") == a["pid"]:
        if ph == "awaiting_video":
            out["video"] = {}
        if st == "compliance":
            out["comply"] = {}
        if st == "appeal":
            out["appeal"] = {}
    if role == "ec" and st in ("ec", "council"):
        out["decide"] = {"suggest": compliance.suggest_conditions(a),
                         "conditions": [{"key": k, "label": v["label"]} for k, v in settings.get()["conditions"].items()]}
    if role in ("rb", "head") or (role == "ro" and engine.ro_code(a["region"]) in offices and st == "evc"):
        tg = engine.allowed_reverts(a, step)
        if tg:
            out["revert"] = {"targets": [{"stage": s, "label": "Institution (clarification)" if s == "compliance" else settings.stage(s)["label"]} for s in tg]}
    if role in STAFF and role != "admin":
        out["note"] = {}
    return out


def app_detail(app_id: str, u: dict, on: date) -> dict:
    a = engine.app(app_id)
    inst = db.q1("SELECT * FROM institutions WHERE pid=?", (a["pid"],))
    step = engine.current_step(a)
    cd = engine.countdown(a, step, on)
    steps = db.q("SELECT * FROM steps WHERE app_id=? ORDER BY id", (app_id,))
    for s in steps:
        s["label"] = settings.stage(s["stage"])["label"]
        s["outcome_label"] = engine.OUTCOME.get(s["outcome"] or "", "")
        s["deficiencies"] = db.unj(s["deficiencies"], []) or []
        s["members"] = db.unj(s["members"], []) or []
        s["extra"] = db.unj(s["extra"], {}) or {}
    split = engine.time_split(app_id, on)
    split["by"] = [{"holder": k, "label": holder_label(k, inst["name"]), "days": v, "kind": holder_kind(k)} for k, v in
                   sorted(split["by"].items(), key=lambda x: -x[1])]
    r = {**a, "inst_name": inst["name"], "city": inst["city"], "s_id": None}
    if step:
        r.update(s_id=step["id"], s_stage=step["stage"], s_phase=step["phase"], s_holder=step["holder"], s_due=step["due_on"],
                 s_opened=step["opened_on"], s_meeting=step["meeting_on"], s_mode=step["mode"], s_extra=step["extra"],
                 s_attempt=step["attempt"], s_closed=None)
    row = app_row(r, on, open_holds())
    carried = db.unj(a["carried"], []) or []
    for c in carried:
        it = db.q1("SELECT status FROM items WHERE id=?", (c["item_id"],))
        c["status"] = it["status"] if it else None
        c["status_label"] = compliance.STATUS.get(c["status"] or "", "")
    return {
        "app": {**row, "deficiencies": db.unj(a["deficiencies"], []) or [], "detail": db.unj(a["detail"], {}) or {}, "carried": carried},
        "institution": institution_card(inst),
        "step": {**step, "extra": db.unj(step["extra"], {}) or {}, "members": db.unj(step["members"], []) or [],
                 "label": settings.stage(step["stage"])["label"], "cite": settings.cite(settings.stage(step["stage"]).get("cite"))} if step else None,
        "countdown": cd, "route": route_view(a, steps, step, cd), "steps": steps, "time": split,
        "history": db.q("SELECT * FROM events WHERE app_id=? ORDER BY ts, id", (app_id,)),
        "items": [item_row(i, on) for i in db.q("SELECT * FROM items WHERE pid=? ORDER BY opened_on DESC", (a["pid"],))],
        "letters": letter_rows(a["pid"]), "actions": stage_actions(u, a, step),
        "alerts": db.q("SELECT * FROM alerts WHERE app_id=? ORDER BY on_date DESC, id DESC LIMIT 60", (app_id,)),
    }


def institution_card(inst: dict) -> dict:
    progs = db.unj(inst["programmes"], []) or []
    return {"pid": inst["pid"], "name": inst["name"], "city": inst["city"], "state": inst["state"], "region": inst["region"],
            "inst_type": inst["inst_type"], "trust": inst["trust"], "source": inst["source"], "land": inst["land"],
            "lease_until": inst["lease_until"], "building_year": inst["building_year"], "max_years": compliance.max_course_years(progs)}


def letter_rows(pid: str) -> list[dict]:
    out = []
    for l in db.q("SELECT * FROM letters WHERE pid=? ORDER BY ay DESC", (pid,)):
        l["deficiencies"] = db.unj(l["deficiencies"], []) or []
        l["courses"] = db.unj(l["courses"], {}) or {}
        out.append(l)
    return out


# ------------------------------------------------------------------------------------ compliance items

def item_state(it: dict, on: date) -> dict:
    ex = db.unj(it["extra"], {}) if isinstance(it["extra"], str) else (it["extra"] or {})
    if it["source"] == "public":
        rs = ex.get("real_status", "")
        color = "green" if rs.startswith("Not noted") else "orange" if rs.startswith("Noted again") else "grey"
        return {"key": "real", "label": rs, "color": color}
    if it["status"] in ("verified", "waived", "closed"):
        return {"key": it["status"], "label": compliance.STATUS[it["status"]], "color": "green" if it["status"] == "verified" else "grey"}
    if it["status"] == "submitted":
        vd = d(ex.get("verify_due"))
        late = vd and on > vd
        return {"key": "to_verify", "label": f"Submitted {d(it['submitted_on']):%d %b}; verify by {vd:%d %b}" + (" (overdue)" if late else ""),
                "color": "red" if late else "blue"}
    if it["kind"] == "deposit":
        st = compliance.deposit_state(it, on)
        return {"key": st["stage"], "label": st["label"], "color": "orange" if st["stage"] == "due" else "red"}
    due = d(it["due_on"])
    if not due:
        return {"key": "open", "label": "Open", "color": "orange"}
    left = (due - on).days
    if left < 0:
        word = "Expired" if it["kind"] == "document" else "Overdue"
        return {"key": "overdue", "label": f"{word} {-left} days" + (" (returned)" if it["status"] == "rejected" else ""), "color": "red"}
    if left <= 30:
        return {"key": "due_soon", "label": f"Due in {left} days", "color": "orange"}
    return {"key": "upcoming", "label": f"Due {due:%d %b %Y}", "color": "grey"}


def item_row(it: dict, on: date, inst: dict | None = None) -> dict:
    ex = db.unj(it["extra"], {}) or {}
    st = item_state({**it, "extra": ex}, on)
    return {"id": it["id"], "kind": it["kind"], "kind_label": compliance.KIND[it["kind"]], "pid": it["pid"],
            "institution": (inst or {}).get("name"), "region": (inst or {}).get("region"), "app_id": it["app_id"], "title": it["title"],
            "detail": it["detail"], "due_on": it["due_on"], "opened_on": it["opened_on"], "status": it["status"],
            "status_label": compliance.STATUS.get(it["status"], it["status"]), "state": st, "holder": it["holder"],
            "holder_label": holder_label(it["holder"], (inst or {}).get("name")) if it["holder"] else "—",
            "cite": settings.cite(it["cite"]), "consequence": it["consequence"], "source": it["source"], "source_url": it["source_url"],
            "esc_level": it["esc_level"], "evidence": db.unj(it["evidence"], []) or [], "note": it["note"], "extra": ex,
            "verifier": compliance.verifier(it) if it["source"] == "test" else None}


def item_rows(on: date, where: str = "", args: tuple = ()) -> list[dict]:
    insts = {r["pid"]: r for r in db.q("SELECT pid, name, region FROM institutions")}
    return [item_row(i, on, insts.get(i["pid"])) for i in db.q(f"SELECT * FROM items {where} ORDER BY due_on", args)]


def documents(pid: str, on: date) -> list[dict]:
    out = []
    for doc in db.q("SELECT * FROM documents WHERE pid=? ORDER BY doc_type, valid_until DESC", (pid,)):
        cfg = settings.get()["documents"].get(doc["doc_type"], {})
        vu = d(doc["valid_until"])
        if doc["source"] == "public":
            state = {"label": "As posted by the college", "color": "orange" if vu and vu < on else "grey"}
        elif doc["status"] == "superseded":
            state = {"label": "Superseded", "color": "grey"}
        elif not vu:
            state = {"label": "No expiry", "color": "green"}
        elif vu < on:
            state = {"label": f"Expired {(on - vu).days} days ago", "color": "red"}
        elif (vu - on).days <= 90:
            state = {"label": f"Expires in {(vu - on).days} days", "color": "orange"}
        else:
            state = {"label": f"Valid until {vu:%d %b %Y}", "color": "green"}
        out.append({**doc, "label": cfg.get("label", doc["doc_type"]), "cite": settings.cite(cfg.get("cite")), "state": state})
    return out


# ------------------------------------------------------------------------------------ dashboards

def overview(on: date, region: str | None = None) -> dict:
    rows = app_rows(on, "WHERE a.region=?", (region,)) if region else app_rows(on)
    live = [r for r in rows if r["phase"]]
    splits = all_splits(on)
    counts = {
        "applications": len(rows), "in_process": len(live), "approved": sum(r["status"] == "approved" for r in rows),
        "lod": sum(r["status"] in ("lod", "rejected") and not r["phase"] for r in rows),
        "will_miss": sum(r["risk"] == "will_miss" for r in live), "fast_track": sum(r["risk"] == "fast_track" for r in live),
        "at_risk": sum(r["risk"] == "at_risk" for r in live), "on_track": sum(r["risk"] == "on_track" for r in live),
        "overdue_aicte": sum(1 for r in live if r["overdue"] > 0 and r["holder_kind"] == "aicte"),
        "overdue_inst": sum(1 for r in live if r["overdue"] > 0 and r["holder_kind"] == "institution"),
    }
    stages = []
    for st, cfg in settings.get()["stages"].items():
        here = [r for r in live if r["stage"] == st]
        if not here:
            continue
        ages = [r["with_days"] or 0 for r in here]
        stages.append({"stage": st, "label": cfg["label"], "open": len(here), "median_days": median(ages), "max_days": max(ages),
                       "overdue": sum(r["overdue"] > 0 for r in here), "at_risk": sum(r["risk"] != "on_track" for r in here),
                       "with_institution": sum(r["holder_kind"] == "institution" for r in here)})
    regions = []
    for reg in settings.get()["regions"]:
        rr = [r for r in rows if r["region"] == reg]
        if not rr:
            continue
        lv = [r for r in rr if r["phase"]]
        evc_wait = [r["with_days"] or 0 for r in lv if r["stage"] == "evc" and r["phase"] == "to_schedule"]
        regions.append({"region": reg, "office": settings.get()["regions"][reg], "applications": len(rr), "in_process": len(lv),
                        "decided": len(rr) - len(lv), "risk": sum(r["risk"] in ("will_miss", "fast_track", "at_risk") for r in lv),
                        "overdue": sum(r["overdue"] > 0 and r["holder_kind"] == "aicte" for r in lv), "evc_to_schedule": len(evc_wait),
                        "evc_wait_median": median(evc_wait),
                        "days_aicte": median([splits[r["id"]]["aicte"] for r in rr]), "days_inst": median([splits[r["id"]]["institution"] for r in rr])})
    tot_a = sum(splits[r["id"]]["aicte"] for r in rows)
    tot_i = sum(splits[r["id"]]["institution"] for r in rows)
    by_office: Counter = Counter()
    for r in rows:
        for code, n in splits[r["id"]]["by"].items():
            by_office[office_of(code)] += n
    offices = [{"office": k, "days": v, "per_app": round(v / max(1, len(rows)), 1)} for k, v in by_office.most_common()]
    items = item_rows(on, "WHERE source='test'")
    comp = {
        "undertakings_open": sum(i["kind"] == "undertaking" and i["status"] in compliance.OPEN for i in items),
        "undertakings_overdue": sum(i["kind"] == "undertaking" and i["state"]["key"] == "overdue" for i in items),
        "documents_expiring": sum(i["kind"] == "document" and i["state"]["key"] == "due_soon" for i in items),
        "documents_expired": sum(i["kind"] == "document" and i["state"]["key"] == "overdue" for i in items),
        "deposits_late": sum(i["kind"] == "deposit" and i["state"]["key"].startswith(("penalty", "withdraw")) for i in items),
        "to_verify": sum(i["status"] == "submitted" for i in items),
        "lease": sum(i["kind"] == "lease" and i["status"] in compliance.OPEN for i in items),
    }
    bottleneck = max((s for s in stages if s["open"] >= 2), key=lambda s: (s["median_days"] or 0), default=None)
    return {"counts": counts, "stages": stages, "regions": regions, "compliance": comp,
            "split": {"aicte": tot_a, "institution": tot_i, "apps": len(rows), "offices": offices},
            "bottleneck": bottleneck, "at_risk": sorted([r for r in live if r["risk"] != "on_track"], key=urgency)[:12],
            "escalations": db.q("SELECT * FROM alerts WHERE level>=2 AND audience='aicte' ORDER BY on_date DESC, id DESC LIMIT 12")}


def report(on: date) -> dict:
    ov = overview(on)
    rows = app_rows(on)
    items = item_rows(on)
    evc = []
    for reg in settings.get()["regions"]:
        steps = db.q("SELECT s.* FROM steps s JOIN applications a ON a.id=s.app_id WHERE s.stage='evc' AND a.region=?", (reg,))
        if not steps:
            continue
        done = [s for s in steps if s["closed_on"]]
        evc.append({"region": reg, "total": len(steps), "to_schedule": sum(not s["closed_on"] and s["phase"] == "to_schedule" for s in steps),
                    "video_awaited": sum(not s["closed_on"] and s["phase"] == "awaiting_video" for s in steps),
                    "scheduled": sum(not s["closed_on"] and s["phase"] == "scheduled" for s in steps), "held": len(done),
                    "deficient": sum(s["outcome"] == "deficient" for s in done),
                    "median_days": median([(d(s["closed_on"]) - d(s["opened_on"])).days for s in done])})
    comp = []
    for kind, label in compliance.KIND.items():
        kk = [i for i in items if i["kind"] == kind and i["source"] == "test"]
        if kk:
            c = Counter(i["state"]["key"] for i in kk)
            comp.append({"kind": label, "total": len(kk), "verified": c.get("verified", 0), "to_verify": c.get("to_verify", 0),
                         "due_soon": c.get("due_soon", 0) + c.get("due", 0), "overdue": c.get("overdue", 0) + sum(v for k, v in c.items() if k.startswith(("penalty", "withdraw"))),
                         "upcoming": c.get("upcoming", 0)})
    overdue = [r for r in rows if r["overdue"] > 0 and r["phase"]]
    esc = Counter((a["level"], engine.holder_label(a["to_office"])) for a in db.q("SELECT level, to_office FROM alerts WHERE level>=2 AND audience='aicte'"))
    return {"overview": ov, "evc": evc, "compliance": comp,
            "overdue": sorted(overdue, key=lambda r: -r["overdue"]),
            "escalations": [{"level": k[0], "to": k[1], "count": v} for k, v in sorted(esc.items())],
            "real": {"letters": db.q1("SELECT COUNT(*) AS n FROM letters WHERE source='public'")["n"],
                     "with_deficiencies": db.q1("SELECT COUNT(*) AS n FROM items WHERE source='public'")["n"]}}
