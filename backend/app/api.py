"""HTTP API (FastAPI). Role-based access is enforced on every route; every action goes to the activity log.

Run:  uvicorn app.api:app --port 8000   (from backend/)
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import threading
import time
from datetime import timedelta
from typing import Any

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import alerts, aph, audit, clock, compliance, db, demo, engine, letters, settings, views
from .clock import d, iso
from .config import BRAND, DATA, ROOT, UPLOADS
from .engine import COMMITTEES, WorkflowError

app = FastAPI(title=f"{BRAND['name']}: {BRAND['tagline']}")
SECRET = b"approval-demo-secret"

USERS = {
    "rb": {"name": "S. Rao", "role": "rb", "offices": ["RB"], "title": "Deputy Director, Regulation Bureau (Approval)"},
    "ro": {"name": "P. Nair", "role": "ro", "region": "Central", "offices": ["RO:Central"], "title": "Regional Officer, Central Region (Bhopal)"},
    "expert": {"name": "Prof. R. Iyer", "role": "committee", "offices": [f"COMMITTEE:{s}" for s in COMMITTEES],
               "title": "Expert member, Scrutiny / EVC / hearing committees"},
    "ec": {"name": "Dr. V. Menon", "role": "ec", "offices": ["EC"], "title": "Member Secretary, for the Executive Committee"},
    "head": {"name": "Dr. A. Kulkarni", "role": "head", "offices": ["HEAD"], "title": "Adviser (Approval), senior management"},
    "admin": {"name": "S. Iyer", "role": "admin", "offices": [], "title": "System administrator"},
}
QUICK_INST = {"inst": "Kesarveni Institute of Technology", "inst2": "Neelkamal Tarai Institute of Technology"}
# User IDs typed on the sign-in page. Institutions sign in with their Permanent ID.
LOGIN_IDS = {"akulkarni": "head", "srao": "rb", "pnair": "ro", "riyer": "expert", "vmenon": "ec", "siyer": "admin"}
STAFF = ("rb", "ro", "committee", "ec", "head", "admin")


# ------------------------------------------------------------------------------------ auth

def resolve(uid: str) -> dict:
    uid = LOGIN_IDS.get(uid.strip().lower(), uid.strip())
    if db.q1("SELECT 1 FROM institutions WHERE pid=? AND source='test'", (uid,)):
        uid = f"inst:{uid}"
    if uid in USERS:
        return {"id": uid, **USERS[uid]}
    if uid in QUICK_INST:
        uid = f"inst:{demo.pid_for(QUICK_INST[uid])}"
    if uid.startswith("inst:"):
        inst = db.q1("SELECT * FROM institutions WHERE pid=? AND source='test'", (uid[5:],))
        if inst:
            return {"id": uid, "name": inst["name"], "role": "institution", "pid": inst["pid"], "offices": [f"INST:{inst['pid']}"],
                    "title": f"Institution login, Permanent ID {inst['pid']}"}
    if uid.startswith("ro:") and uid[3:] in settings.get()["regions"]:
        reg = uid[3:]
        return {"id": uid, "name": f"Regional Officer, {reg}", "role": "ro", "region": reg, "offices": [f"RO:{reg}"],
                "title": f"Regional Officer, {reg} Region ({settings.get()['regions'][reg]})"}
    raise HTTPException(404, "unknown user")


def _sign(payload: str) -> str:
    return payload + "." + hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()[:24]


def user(x_token: str | None = Header(default=None), t: str | None = Query(default=None)) -> dict:
    tok = x_token or t
    if not tok or "." not in tok:
        raise HTTPException(401, "login required")
    payload = tok.rsplit(".", 1)[0]
    if _sign(payload) != tok:
        raise HTTPException(401, "bad token")
    return resolve(payload)


def need(*roles):
    def dep(u=Depends(user)):
        if u["role"] not in roles:
            raise HTTPException(403, "Your role cannot do this")
        return u
    return dep


class LoginIn(BaseModel):
    user: str
    password: str | None = None   # not checked yet: authentication is to be connected to AICTE's own sign-in


@app.post("/api/login")
def login(body: LoginIn):
    try:
        u = resolve(body.user)
    except HTTPException:
        raise HTTPException(401, "User ID not recognised")
    audit.log(u["id"], u["role"], "auth.login", u["id"])
    return {"token": _sign(u["id"]), "user": u}


@app.get("/api/me")
def me(u=Depends(user)):
    return u


@app.get("/api/brand")
def brand():
    return BRAND


@app.get("/api/demo-users")
def demo_users():
    by_id = {v: k for k, v in LOGIN_IDS.items()}
    out = [{"id": k, "login": by_id.get(k, k), **v} for k, v in USERS.items()]
    for k in QUICK_INST:
        try:
            u = resolve(k)
            out.append({**u, "id": k, "login": u["pid"]})
        except HTTPException:
            pass
    return out


def can_see(u: dict, a: dict) -> bool:
    r = u["role"]
    if r in ("rb", "ec", "head", "admin"):
        return True
    if r == "ro":
        return a["region"] == u["region"]
    if r == "committee":
        return bool(db.q1(f"SELECT 1 FROM steps WHERE app_id=? AND stage IN ({','.join('?' * len(COMMITTEES))})", (a["id"], *COMMITTEES)))
    return r == "institution" and a["pid"] == u["pid"]


def _app(app_id: str, u: dict) -> dict:
    try:
        a = engine.app(app_id)
    except WorkflowError:
        raise HTTPException(404, "No such application")
    if not can_see(u, a):
        raise HTTPException(403, "This application is not in your scope")
    return a


def _scope(u: dict) -> tuple[str, tuple]:
    if u["role"] == "ro":
        return "a.region=?", (u["region"],)
    if u["role"] == "institution":
        return "a.pid=?", (u["pid"],)
    if u["role"] == "committee":
        return "a.id IN (SELECT app_id FROM steps WHERE stage IN ('scrutiny','re_scrutiny','evc','shc','sac'))", ()
    return "1=1", ()


# ------------------------------------------------------------------------------------ clock

def clock_info() -> dict:
    t = clock.today()
    c = settings.get()["cycle"]
    return {"today": iso(t), "demo": clock.is_demo(), "ay": c["ay"], "last_date_approval": c["last_date_approval"],
            "last_date_after_appeal": c["last_date_after_appeal"], "days_left": (d(c["last_date_approval"]) - t).days}


@app.get("/api/clock")
def get_clock():
    return clock_info()


class ClockIn(BaseModel):
    days: int


_clock_lock = threading.Lock()


@app.post("/api/clock")
def move_clock(body: ClockIn, u=Depends(need("admin"))):
    if not clock.is_demo():
        raise HTTPException(400, "The system date follows the real date")
    if not 1 <= body.days <= 120:
        raise HTTPException(400, "Move forward by 1 to 120 days")
    with _clock_lock:
        start = clock.today() + timedelta(days=1)
        end = clock.today() + timedelta(days=body.days)
        r = alerts.run_until(start, end)
        settings.put("cycle.today", iso(end), u["id"], f"Demo clock moved forward {body.days} days")
        audit.log(u["id"], u["role"], "clock.moved", "clock", {"to": iso(end), "messages": r["sent"]})
    return {**clock_info(), "sent": r["sent"]}


@app.post("/api/admin/reset")
def reset_demo(u=Depends(need("admin"))):
    with _clock_lock:
        out = demo.build(verbose=False)
    return {"ok": True, "applications": out["applications"]}


# ------------------------------------------------------------------------------------ work, dashboards

@app.get("/api/meta")
def meta(u=Depends(user)):
    s = settings.get()
    return {"regions": list(s["regions"]), "natures": [{"id": k, "label": v["label"]} for k, v in s["natures"].items()],
            "stages": [{"id": k, "label": v["label"], "short": v["short"]} for k, v in s["stages"].items()], "risk": engine.RISK}


@app.get("/api/work")
def work(u=Depends(user)):
    on = clock.today()
    if u["role"] == "institution":
        return mine(u)
    offices = set(u["offices"])
    rows = views.app_rows(on, "WHERE s.id IS NOT NULL AND s.closed_on IS NULL")
    if u["role"] == "head":
        steps = [r for r in rows if r["esc_level"] >= 3 or r["risk"] in ("will_miss", "fast_track")]
    else:
        steps = [r for r in rows if r["holder"] in offices]
    tell = settings.get()["alerts"]["institution"]["tell_officer_after"]
    watch = []
    if u["role"] == "rb":   # waiting on institutions, and committees the Bureau convenes that are late or at risk
        watch = [r for r in rows if (r["holder_kind"] == "institution" and r["overdue"] >= tell)
                 or (r["holder"].startswith("COMMITTEE:") and r["stage"] != "evc" and (r["overdue"] > 0 or r["risk"] != "on_track"))]
    if u["role"] == "ro":   # EVCs of the region that someone else holds right now
        watch = [r for r in rows if r["region"] == u["region"] and r["stage"] == "evc" and r["holder"] not in offices]
    watch.sort(key=views.urgency)
    items = []
    if offices:
        items = views.item_rows(on, f"WHERE source='test' AND holder IN ({','.join('?' * len(offices))})", tuple(offices))
    steps.sort(key=views.urgency)
    week = on + timedelta(days=7)
    counts = {"total": len(steps) + len(items), "will_miss": sum(r["risk"] == "will_miss" for r in steps),
              "fast_track": sum(r["risk"] == "fast_track" for r in steps), "at_risk": sum(r["risk"] == "at_risk" for r in steps),
              "overdue": sum(r["overdue"] > 0 for r in steps) + sum(i["state"]["color"] == "red" for i in items),
              "this_week": sum(bool(r["due_on"]) and d(r["due_on"]) <= week for r in steps)}
    return {"steps": steps, "items": items, "watch": watch, "counts": counts}


def mine(u: dict) -> dict:
    on = clock.today()
    pid = u["pid"]
    inst = db.q1("SELECT * FROM institutions WHERE pid=?", (pid,))
    rows = views.app_rows(on, "WHERE a.pid=?", (pid,))
    items = views.item_rows(on, "WHERE pid=? AND source='test'", (pid,))
    return {"institution": views.institution_card(inst), "owe_steps": [r for r in rows if r["holder"] == f"INST:{pid}"],
            "owe_items": [i for i in items if i["status"] in ("open", "rejected")], "applications": rows, "items": items,
            "documents": views.documents(pid, on),
            "notices": db.q("SELECT * FROM alerts WHERE to_office=? ORDER BY on_date DESC, id DESC LIMIT 25", (f"INST:{pid}",))}


@app.get("/api/overview")
def overview(u=Depends(need(*STAFF))):
    return views.overview(clock.today(), u["region"] if u["role"] == "ro" else None)


# ------------------------------------------------------------------------------------ applications

@app.get("/api/applications")
def applications(q: str = "", region: str = "", nature: str = "", stage: str = "", risk: str = "", status: str = "",
                 holder: str = "", u=Depends(user)):
    where, args = _scope(u)
    rows = views.app_rows(clock.today(), f"WHERE {where}", args)
    ql = q.strip().lower()
    out = [r for r in rows if (not ql or ql in f"{r['id']} {r['institution']} {r['pid']} {r['city'] or ''}".lower())
           and (not region or r["region"] == region) and (not nature or r["nature"] == nature) and (not stage or r["stage"] == stage)
           and (not risk or r["risk"] == risk) and (not holder or r["holder_kind"] == holder)
           and (not status or (r["status"] == status if status != "open" else bool(r["phase"])))]
    out.sort(key=lambda r: (0 if r["phase"] else 1, views.urgency(r)))
    return out


@app.get("/api/applications/{app_id}")
def application(app_id: str, u=Depends(user)):
    _app(app_id, u)
    out = views.app_detail(app_id, u, clock.today())
    audit.log(u["id"], u["role"], "application.viewed", app_id)
    return out


class ActIn(BaseModel):
    action: str
    meeting_on: str | None = None
    mode: str | None = None
    result: str | None = None
    deficiencies: list[str] = []
    remarks: str = ""
    link: str | None = None
    decision: str | None = None
    conditions: list[dict] = []
    to: str | None = None
    reason: str = ""
    text: str = ""
    files: list[str] = []


@app.post("/api/applications/{app_id}/act")
def act(app_id: str, body: ActIn, u=Depends(user)):
    a = _app(app_id, u)
    step = engine.current_step(a)
    allowed = views.stage_actions(u, a, step)
    if body.action not in allowed:
        raise HTTPException(403, "You cannot do this on this application at its present step")
    on, who, role = clock.today(), u["id"], u["role"]
    try:
        if body.action == "schedule":
            engine.schedule(app_id, on, d(body.meeting_on), body.mode or "online", who, role)
        elif body.action == "outcome":
            engine.record_outcome(app_id, on, body.result or "", body.deficiencies, body.remarks, who, role)
        elif body.action == "video":
            engine.video_uploaded(app_id, on, body.link or "", who, role)
        elif body.action == "comply":
            engine.submit_compliance(app_id, on, body.remarks, who, role, body.files)
        elif body.action == "appeal":
            engine.file_appeal(app_id, on, body.remarks, who, role)
        elif body.action == "decide":
            engine.decide(app_id, on, body.decision or "", body.remarks, who, role, body.conditions)
        elif body.action == "revert":
            engine.revert(app_id, on, body.to or "", body.reason, who, role)
        elif body.action == "note":
            engine.add_note(app_id, on, body.text, who, role)
    except WorkflowError as e:
        raise HTTPException(400, str(e))
    alerts.sweep(on)
    return views.app_detail(app_id, u, on)


@app.get("/api/applications/{app_id}/letter/{kind}")
def letter(app_id: str, kind: str, u=Depends(user)):
    _app(app_id, u)
    if u["role"] == "institution" and kind == "escalation":
        raise HTTPException(403, "Not available to institutions")
    try:
        out = letters.build(kind, app_id, clock.today())
    except WorkflowError as e:
        raise HTTPException(400, str(e))
    audit.log(u["id"], u["role"], "letter.drafted", app_id, {"kind": kind})
    return out


@app.get("/api/evc")
def evc(region: str = "", u=Depends(need(*STAFF))):
    on = clock.today()
    reg = u["region"] if u["role"] == "ro" else region
    rows = db.q("SELECT s.*, a.region, a.nature, a.pid, a.status AS app_status, i.name AS institution FROM steps s "
                "JOIN applications a ON a.id=s.app_id JOIN institutions i ON i.pid=a.pid WHERE s.stage='evc'"
                + (" AND a.region=?" if reg else "") + " ORDER BY s.opened_on", (reg,) if reg else ())
    out = []
    for s in rows:
        a = engine.app(s["app_id"])
        live = not s["closed_on"]
        cd = engine.countdown(a, s, on) if live else None
        m = d(s["meeting_on"])
        group = ("done" if not live else s["phase"] if s["phase"] != "scheduled" else "report_due" if m and m < on else "scheduled")
        out.append({"app_id": s["app_id"], "institution": s["institution"], "pid": s["pid"], "region": s["region"],
                    "nature_label": settings.nature(s["nature"])["label"], "group": group, "phase": s["phase"], "attempt": s["attempt"],
                    "opened_on": s["opened_on"], "closed_on": s["closed_on"], "due_on": s["due_on"], "meeting_on": s["meeting_on"],
                    "mode": s["mode"], "outcome": engine.OUTCOME.get(s["outcome"] or "", ""), "waiting": (on - d(s["opened_on"])).days if live else None,
                    "overdue": max(0, (on - d(s["due_on"])).days) if live else 0, "risk": cd["risk"] if cd else None,
                    "risk_label": cd["risk_label"] if cd else None, "spare": cd["spare"] if cd else None, "hold_by": cd.get("hold_by") if cd else None,
                    "schedule_by": cd.get("schedule_by") if cd else None, "why": cd["why"] if cd else None,
                    "members": db.unj(s["members"], []) or [], "can_schedule": live and u["role"] == "ro" and f"RO:{s['region']}" in u["offices"]})
    return out


# ------------------------------------------------------------------------------------ compliance

@app.get("/api/compliance")
def compliance_list(kind: str = "", state: str = "", source: str = "", region: str = "", q: str = "", u=Depends(user)):
    on = clock.today()
    rows = views.item_rows(on)
    if u["role"] == "institution":
        rows = [r for r in rows if r["pid"] == u["pid"] and r["source"] == "test"]
    elif u["role"] == "ro":
        rows = [r for r in rows if r["region"] == u["region"]]
    ql = q.strip().lower()
    rows = [r for r in rows if (not kind or r["kind"] == kind) and (not source or r["source"] == source) and (not region or r["region"] == region)
            and (not state or r["state"]["key"] == state or (state == "late" and r["state"]["color"] == "red"))
            and (not ql or ql in f"{r['institution']} {r['title']} {r['pid']} {r['detail'] or ''}".lower())]
    order = {"red": 0, "orange": 1, "blue": 2, "grey": 3, "green": 4}
    rows.sort(key=lambda r: (r["source"] != "test", order.get(r["state"]["color"], 5), r["due_on"] or "9999"))
    return rows


class ItemIn(BaseModel):
    action: str
    note: str = ""
    files: list[str] = []
    valid_until: str | None = None
    reason: str = ""


@app.post("/api/compliance/{item_id}/act")
def compliance_act(item_id: str, body: ItemIn, u=Depends(user)):
    try:
        it = compliance.item(item_id)
    except WorkflowError:
        raise HTTPException(404, "No such item")
    if it["source"] != "test":
        raise HTTPException(400, "Real records from public letters are shown for reference only")
    on, who, role = clock.today(), u["id"], u["role"]
    try:
        if body.action == "submit":
            if role != "institution" or u["pid"] != it["pid"]:
                raise HTTPException(403, "Only the institution submits evidence")
            extra = None
            if it["kind"] in ("document", "lease"):
                if not body.valid_until:
                    raise HTTPException(400, "Give the validity date of the renewed document")
                extra = {"new_document": {"doc_type": it["doc_type"], "issued_on": iso(on), "valid_until": body.valid_until,
                                          "file_id": body.files[0] if body.files else None}}
            compliance.submit(item_id, on, body.note, who, role, body.files, extra)
        elif body.action in ("verify", "return"):
            if compliance.verifier(it) not in u["offices"]:
                raise HTTPException(403, "Only the verifying office can do this")
            compliance.verify(item_id, on, body.action == "verify", body.reason, who, role)
        elif body.action == "waive":
            if role not in ("head", "ec"):
                raise HTTPException(403, "Only the competent authority can waive a condition")
            compliance.waive(item_id, on, body.reason, who, role)
        else:
            raise HTTPException(400, "Unknown action")
    except WorkflowError as e:
        raise HTTPException(400, str(e))
    alerts.sweep(on)
    return views.item_row(compliance.item(item_id), on, db.q1("SELECT name, region FROM institutions WHERE pid=?", (it["pid"],)))


@app.get("/api/compliance/{item_id}")
def compliance_detail(item_id: str, u=Depends(user)):
    try:
        it = compliance.item(item_id)
    except WorkflowError:
        raise HTTPException(404, "No such item")
    inst = db.q1("SELECT name, region FROM institutions WHERE pid=?", (it["pid"],))
    if u["role"] == "institution" and u["pid"] != it["pid"]:
        raise HTTPException(403, "Not your institution")
    if u["role"] == "ro" and inst["region"] != u["region"]:
        raise HTTPException(403, "Not in your region")
    on = clock.today()
    row = views.item_row(it, on, inst)
    row["history"] = db.q("SELECT * FROM events WHERE item_id=? ORDER BY ts, id", (item_id,))
    row["alerts"] = db.q("SELECT * FROM alerts WHERE item_id=? ORDER BY on_date DESC, id DESC", (item_id,))
    row["time"] = engine.time_split(item_id, on)
    row["can"] = {"submit": u["role"] == "institution" and u.get("pid") == it["pid"] and it["status"] in ("open", "rejected") and it["source"] == "test",
                  "verify": it["status"] == "submitted" and it["source"] == "test" and compliance.verifier(it) in u["offices"],
                  "waive": u["role"] in ("head", "ec") and it["status"] in compliance.OPEN and it["source"] == "test"}
    return row


# ------------------------------------------------------------------------------------ institutions

@app.get("/api/institutions")
def institutions(q: str = "", source: str = "", u=Depends(need(*STAFF))):
    ql = q.strip().lower()
    rows = db.q("SELECT pid, name, city, state, region, inst_type, source, land, lease_until FROM institutions ORDER BY source DESC, name")
    if u["role"] == "ro":
        rows = [r for r in rows if r["region"] == u["region"]]
    counts = {r["pid"]: r for r in db.q("SELECT pid, COUNT(*) AS apps FROM applications GROUP BY pid")}
    letters_n = {r["pid"]: r["n"] for r in db.q("SELECT pid, COUNT(*) AS n FROM letters GROUP BY pid")}
    open_items = {r["pid"]: r["n"] for r in db.q("SELECT pid, COUNT(*) AS n FROM items WHERE status IN ('open','submitted','rejected') GROUP BY pid")}
    return [{**r, "applications": (counts.get(r["pid"]) or {}).get("apps", 0), "letters": letters_n.get(r["pid"], 0), "open_items": open_items.get(r["pid"], 0)}
            for r in rows if (not source or r["source"] == source) and (not ql or ql in f"{r['name']} {r['pid']} {r['city'] or ''} {r['state'] or ''}".lower())]


@app.get("/api/institutions/{pid}")
def institution(pid: str, u=Depends(user)):
    inst = db.q1("SELECT * FROM institutions WHERE pid=?", (pid,))
    if not inst:
        raise HTTPException(404, "No such institution")
    if (u["role"] == "institution" and u["pid"] != pid) or (u["role"] == "ro" and inst["region"] != u["region"]):
        raise HTTPException(403, "Not in your scope")
    on = clock.today()
    card = views.institution_card(inst)
    blk = compliance.lease_block(inst["lease_until"], card["max_years"]) if inst["land"] == "lease" else None
    return {"institution": {**card, "programmes": db.unj(inst["programmes"], []) or [], "est_year": inst["est_year"],
                            "ownership": inst["ownership"], "extra": db.unj(inst["extra"], {}) or {}},
            "lease": blk, "documents": views.documents(pid, on), "letters": views.letter_rows(pid),
            "applications": views.app_rows(on, "WHERE a.pid=?", (pid,)),
            "items": views.item_rows(on, "WHERE pid=?", (pid,))}


@app.get("/api/search")
def search(q: str, u=Depends(user)):
    q = q.strip()
    if len(q) < 2 or u["role"] == "institution":
        return {"applications": [], "institutions": []}
    like = f"%{q}%"
    where, args = _scope(u)
    apps = db.q(f"SELECT a.id, a.pid, i.name FROM applications a JOIN institutions i ON i.pid=a.pid WHERE {where} AND (a.id LIKE ? OR i.name LIKE ? OR a.pid LIKE ?) LIMIT 8",
                (*args, like, like, like))
    insts = db.q("SELECT pid, name, city, source FROM institutions WHERE name LIKE ? OR pid LIKE ? ORDER BY source DESC LIMIT 8", (like, like))
    return {"applications": apps, "institutions": insts}


# ------------------------------------------------------------------------------------ alerts, reports

def _my_offices(u: dict) -> list[str]:
    return list(u["offices"])


@app.get("/api/alerts")
def get_alerts(scope: str = "mine", kind: str = "", u=Depends(user)):
    if scope == "all" and u["role"] in ("head", "admin"):
        rows = db.q("SELECT * FROM alerts ORDER BY on_date DESC, id DESC LIMIT 600")
    else:
        offs = _my_offices(u)
        if not offs:
            return {"rows": [], "unread": 0}
        rows = db.q(f"SELECT * FROM alerts WHERE to_office IN ({','.join('?' * len(offs))}) ORDER BY on_date DESC, id DESC LIMIT 400", tuple(offs))
    names = {r["pid"]: r["name"] for r in db.q("SELECT pid, name FROM institutions")}
    out = []
    for r in rows:
        if kind and r["kind"] != kind:
            continue
        r["channels"] = db.unj(r["channels"], [])
        r["read"] = u["id"] in (db.unj(r["read_by"], []) or [])
        r["to_label"] = engine.holder_label(r["to_office"], names.get(r["to_office"][5:]) if r["to_office"].startswith("INST:") else None)
        r["institution"] = names.get(r["pid"])
        out.append(r)
    return {"rows": out, "unread": sum(not r["read"] for r in out)}


class ReadIn(BaseModel):
    ids: list[int] = []


@app.post("/api/alerts/read")
def read_alerts(body: ReadIn, u=Depends(user)):
    offs = _my_offices(u)
    if not offs:
        return {"ok": True}
    rows = db.q(f"SELECT id, read_by FROM alerts WHERE to_office IN ({','.join('?' * len(offs))})", tuple(offs))
    for r in rows:
        if body.ids and r["id"] not in body.ids:
            continue
        rb = db.unj(r["read_by"], []) or []
        if u["id"] not in rb:
            db.update("alerts", "id", r["id"], {"read_by": rb + [u["id"]]})
    return {"ok": True}


@app.get("/api/reports")
def reports(u=Depends(need(*STAFF))):
    return views.report(clock.today())


@app.get("/api/reports.csv")
def reports_csv(table: str, u=Depends(need(*STAFF))):
    r = views.report(clock.today())
    tables = {"stages": r["overview"]["stages"], "regions": r["overview"]["regions"], "evc": r["evc"], "compliance": r["compliance"],
              "overdue": [{k: x[k] for k in ("id", "institution", "region", "nature_label", "task", "holder_label", "due_on", "overdue", "risk_label")} for x in r["overdue"]],
              "applications": [{k: x[k] for k in ("id", "pid", "institution", "region", "nature_label", "status_label", "stage_label", "holder_label",
                                                  "due_on", "overdue", "risk_label", "spare", "submitted_on", "decided_on")} for x in views.app_rows(clock.today())]}
    rows = tables.get(table)
    if rows is None:
        raise HTTPException(404, "unknown table")
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    audit.log(u["id"], u["role"], "report.downloaded", table)
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{table}-{iso(clock.today())}.csv"'})


# ------------------------------------------------------------------------------------ rules, settings, handbook

@app.get("/api/rules")
def rules(u=Depends(user)):
    s = settings.get()
    cites = {k: {**v, "key": k, "loc": aph.locations().get(k)} for k, v in s["cites"].items()}
    natures = [{"id": k, "label": v["label"], "route": v["route"], "aa": v.get("aa", []), "deposit": bool(v.get("deposit")),
                "chapter": v.get("chapter", "II")} for k, v in s["natures"].items()]
    return {"cycle": s["cycle"], "stages": s["stages"], "natures": natures, "alerts": s["alerts"], "documents": s["documents"],
            "deposit": s["deposit"], "conditions": s["conditions"], "regions": s["regions"], "cites": cites,
            "overrides": settings.overrides()}


class SettingIn(BaseModel):
    key: str
    value: Any
    reason: str


@app.put("/api/settings")
def put_setting(body: SettingIn, u=Depends(need("admin"))):
    if body.key == "cycle.today":
        raise HTTPException(400, "Use the demo clock to move the date")
    if len(body.reason.strip()) < 5:
        raise HTTPException(400, "Record the reason for the change")
    try:
        old = settings.lookup(body.key)
    except KeyError:
        raise HTTPException(400, "Unknown setting")
    if isinstance(old, bool) != isinstance(body.value, bool) or (isinstance(old, (int, float)) and not isinstance(body.value, (int, float))) \
            or (isinstance(old, str) and not isinstance(body.value, str)) or (isinstance(old, list) and not isinstance(body.value, list)):
        raise HTTPException(400, "The new value is not of the same kind as the old one")
    settings.put(body.key, body.value, u["id"], body.reason.strip())
    audit.log(u["id"], u["role"], "settings.changed", body.key, {"old": old, "new": body.value, "reason": body.reason.strip()})
    alerts.sweep(clock.today())
    return {"ok": True}


@app.get("/api/aph/{key}")
def aph_cite(key: str):
    c = aph.cite(key)
    if not c:
        raise HTTPException(404, "unknown clause")
    return c


@app.get("/api/aph/page/{n}.png")
def aph_page(n: int):
    p = aph.page_file(n)
    if not p:
        raise HTTPException(404, "page not available")
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "max-age=86400"})


# ------------------------------------------------------------------------------------ audit, evaluation, files

@app.get("/api/audit")
def get_audit(limit: int = 300, target: str = "", u=Depends(need(*STAFF))):
    if target:
        rows = db.q("SELECT * FROM audit WHERE target=? ORDER BY seq DESC LIMIT ?", (target, limit))
    else:
        rows = db.q("SELECT * FROM audit ORDER BY seq DESC LIMIT ?", (limit,))
    for r in rows:
        r["payload"] = db.unj(r["payload"], {})
    return {"rows": rows, "chain": audit.verify_chain(), "total": db.q1("SELECT COUNT(*) AS n FROM audit")["n"]}


@app.get("/api/eval")
def get_eval(u=Depends(user)):
    p = DATA / "eval_report.json"
    if not p.exists():
        raise HTTPException(404, "Run scripts/evaluate.py")
    return json.loads(p.read_text(encoding="utf-8"))


@app.post("/api/files")
async def upload(file: UploadFile = File(...), u=Depends(user)):
    raw = await file.read()
    if len(raw) > 15 * 1024 * 1024:
        raise HTTPException(400, "Files up to 15 MB")
    sha = hashlib.sha256(raw).hexdigest()
    ext = (file.filename or "").rsplit(".", 1)[-1][:6].lower() if "." in (file.filename or "") else "bin"
    path = UPLOADS / f"{sha}.{ext}"
    path.write_bytes(raw)
    fid = f"F-{sha[:12]}"
    db.insert("files", {"id": fid, "name": file.filename, "mime": file.content_type, "path": str(path), "sha256": sha, "size": len(raw),
                        "uploaded_by": u["id"], "uploaded_on": iso(clock.today())}, replace=True)
    audit.log(u["id"], u["role"], "file.uploaded", fid, {"name": file.filename, "sha256": sha})
    return {"id": fid, "name": file.filename, "sha256": sha}


@app.get("/api/files/{fid}")
def get_file(fid: str, u=Depends(user)):
    f = db.q1("SELECT * FROM files WHERE id=?", (fid,))
    if not f:
        raise HTTPException(404, "No such file")
    if u["role"] == "institution" and f["uploaded_by"] != u["id"]:
        raise HTTPException(403, "Not your file")
    return FileResponse(f["path"], media_type=f["mime"] or "application/octet-stream", filename=f["name"])


# ------------------------------------------------------------------------------------ daily check (real-date mode)

def _daily():
    last = clock.today()
    while True:
        time.sleep(600)
        try:
            if not clock.is_demo() and clock.today() > last:
                alerts.run_until(last + timedelta(days=1), clock.today())
                last = clock.today()
        except Exception:   # never let the background check stop the server
            pass


@app.on_event("startup")
def _start():
    threading.Thread(target=_daily, daemon=True).start()


# ------------------------------------------------------------------------------------ static frontend

DIST = ROOT / "frontend" / "dist"
if DIST.exists() and (DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}")
def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "not found")
    f = DIST / path
    if path and f.is_file():
        return FileResponse(f)
    if not (DIST / "index.html").exists():
        return HTMLResponse("<p>Build the frontend first: cd frontend && npm install && npm run build</p>")
    html = (DIST / "index.html").read_text(encoding="utf-8").replace("__BRAND__", f"{BRAND['name']} · {BRAND['tagline']}")
    return HTMLResponse(html)
