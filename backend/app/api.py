"""HTTP API (FastAPI). Role-based access is enforced server-side on every route.

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
from collections import Counter, defaultdict
from datetime import date, timedelta

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ai, audit, db, overlap, resolve, service, settings
from .config import DATA, ROOT
from .workflow import ACTIONS, OFFICER_ACTIONS, STATUS, d, timeline, today

app = FastAPI(title="Samanvay - institution complaint monitoring")
SECRET = b"samanvay-demo-secret"

USERS = {
    "pgrc": {"name": "K. Verma", "role": "officer", "bureau": "PGRC", "officer_id": "PGRC-1", "title": "Section Officer, Public Grievance Redressal Cell"},
    "rb": {"name": "S. Rao", "role": "officer", "bureau": "RB", "officer_id": "RB-1", "title": "Deputy Director, Regulation Bureau"},
    "ab": {"name": "M. Das", "role": "officer", "bureau": "AB", "officer_id": "AB-1", "title": "Assistant Director, Approval Bureau"},
    "arc": {"name": "N. Gupta", "role": "officer", "bureau": "ARC", "officer_id": "ARC-1", "title": "Officer, Anti-Ragging Cell"},
    "ro": {"name": "P. Nair", "role": "officer", "bureau": "RO", "officer_id": "RO-SW", "region": "South-Western", "title": "Regional Officer, South-Western Region"},
    "head": {"name": "Dr. A. Kulkarni", "role": "management", "bureau": None, "title": "Adviser (Monitoring), senior management"},
    "admin": {"name": "S. Iyer", "role": "admin", "bureau": None, "title": "System administrator"},
}


# ------------------------------------------------------------------------------------ auth

def _sign(payload: str) -> str:
    return payload + "." + hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()[:24]


def user(x_token: str | None = Header(default=None), t: str | None = Query(default=None)) -> dict:
    tok = x_token or t
    if not tok or "." not in tok:
        raise HTTPException(401, "login required")
    payload = tok.rsplit(".", 1)[0]
    if _sign(payload) != tok or payload not in USERS:
        raise HTTPException(401, "bad token")
    return {"id": payload, **USERS[payload]}


def need(*roles):
    def dep(u=Depends(user)):
        if u["role"] not in roles:
            raise HTTPException(403, f"role '{u['role']}' may not do this")
        return u
    return dep


class Login(BaseModel):
    user: str


@app.post("/api/login")
def login(body: Login):
    if body.user not in USERS:
        raise HTTPException(404, "unknown user")
    tok = _sign(body.user)
    u = {"id": body.user, **USERS[body.user]}
    audit.log(body.user, u["role"], "auth.login", body.user)
    return {"token": tok, "user": u}


@app.get("/api/me")
def me(u=Depends(user)):
    return u


@app.get("/api/demo-users")
def demo_users():
    return [{"id": k, **v} for k, v in USERS.items()]


# ------------------------------------------------------------------------------------ helpers

_inst_cache: dict | None = None
_officer_cache: dict | None = None


def insts() -> dict:
    global _inst_cache
    if _inst_cache is None:
        _inst_cache = {r["permanent_id"]: r for r in db.q("SELECT * FROM institutions")}
    return _inst_cache


def officers() -> dict:
    global _officer_cache
    if _officer_cache is None:
        _officer_cache = {r["id"]: r for r in db.q("SELECT * FROM officers")}
    return _officer_cache


def open_alerts() -> list[dict]:
    return db.q("SELECT * FROM coordination WHERE status IN ('open','acknowledged')")


class AlertMap(defaultdict):
    """case id -> open alerts it is part of; also remembers, per bureau, the alerts that involve that bureau."""

    def __init__(self):
        super().__init__(list)
        self.mine: dict[str | None, set[str]] = {}


def alerts_by_case() -> AlertMap:
    out = AlertMap()
    for a in open_alerts():
        for c in db.unj(a["cases"], []):
            out[c].append({"id": a["id"], "kind": a["kind"]})
    return out


def can_see(u: dict, c: dict, alert_map: dict | None = None) -> bool:
    """Full complaint text: the handling bureau, senior management, the regional office of the institution's
    region, and bureaus that share an open overlap alert with the case. Others see the summary only."""
    if u["role"] in ("management", "admin") or c["bureau"] == u.get("bureau"):
        return True
    inst = insts().get(c["permanent_id"] or "")
    if u.get("bureau") == "RO" and inst and inst["region"] == u.get("region"):
        return True
    amap = alert_map if alert_map is not None else alerts_by_case()
    if c["id"] not in amap:
        return False
    return any(a["id"] in _my_alert_ids(u, amap) for a in amap.get(c["id"], []))


def _my_alert_ids(u: dict, amap: AlertMap) -> set[str]:
    """Open alerts that include at least one case of the user's bureau (computed once per request)."""
    b = u.get("bureau")
    if b not in amap.mine:
        bureau_of = {r["id"]: r["bureau"] for r in db.q("SELECT id, bureau FROM cases")}
        amap.mine[b] = {a["id"] for cid, al in list(amap.items()) for a in al if bureau_of.get(cid) == b}
    return amap.mine[b]


def mask(name: str | None) -> str:
    if not name:
        return ""
    return " ".join(w[0] + "." for w in name.split() if w[:1].isalpha()) or "—"


def row(c: dict, u: dict, amap: dict) -> dict:
    inst = insts().get(c["permanent_id"] or "") or {}
    tl = timeline(c)
    vis = can_see(u, c, amap)
    off = officers().get(c["officer_id"] or "") or {}
    return {
        "id": c["id"], "bureau": c["bureau"], "received_on": c["received_on"], "source": c["source"], "ext_ref": c["ext_ref"],
        "permanent_id": c["permanent_id"], "institution": inst.get("name"), "city": inst.get("city"), "region": inst.get("region"),
        "inst_text": c["inst_text"], "match_state": c["match_state"],
        "category": c["category"], "category_label": settings.category(c["category"])["label"],
        "subject": c["subject"] if vis else None, "status": c["status"], "status_label": STATUS[c["status"]],
        "officer": off.get("name"), "officer_id": c["officer_id"], "last_action": c["last_action"], "last_action_on": c["last_action_on"],
        "next_action": c["next_action"], "next_due": c["next_due"], "due_on": c["due_on"], "disposed_on": c["disposed_on"],
        "outcome": c["outcome"], "timeline": tl, "esc_level": c["esc_level"], "lang": c["lang"],
        "alerts": amap.get(c["id"], []), "visible": vis,
    }


def _case(cid: str) -> dict:
    c = db.q1("SELECT * FROM cases WHERE id=?", (cid,))
    if not c:
        raise HTTPException(404, "case not found")
    return c


def _may_act(u: dict, c: dict) -> None:
    if u["role"] == "management":
        return
    if u["role"] != "officer" or c["bureau"] != u["bureau"]:
        raise HTTPException(403, f"Only {c['bureau']} officers can act on this case")


def _refresh_caches():
    global _inst_cache, _officer_cache
    _inst_cache = _officer_cache = None
    resolve.reload()


# ------------------------------------------------------------------------------------ overview

@app.get("/api/overview")
def overview(scope: str = "mine", u=Depends(user)):
    amap = alerts_by_case()
    cases = db.q("SELECT * FROM cases")
    if scope == "mine" and u.get("bureau"):
        cases = [c for c in cases if c["bureau"] == u["bureau"]]
    open_ = [c for c in cases if c["status"] != "disposed"]
    tls = {c["id"]: timeline(c) for c in open_}
    t30 = (today() - timedelta(days=30)).isoformat()
    disposed = [c for c in cases if c["status"] == "disposed"]
    counts = {
        "total": len(cases), "pending": sum(c["status"] == "pending" for c in cases),
        "under_process": sum(c["status"] == "under_process" for c in cases), "transferred": sum(c["status"] == "transferred" for c in cases),
        "escalated": sum((c["esc_level"] or -1) >= 2 for c in open_), "overdue": sum(tls[c["id"]].get("state") == "overdue" for c in open_),
        "due_soon": sum(tls[c["id"]].get("state") == "due_soon" for c in open_), "disposed": len(disposed),
        "received_30d": sum(c["received_on"] >= t30 for c in cases), "disposed_30d": sum((c["disposed_on"] or "") >= t30 for c in disposed),
        "unconfirmed": sum(c["match_state"] in ("confirm", "unmatched") for c in cases),
    }
    in_time = [c for c in disposed if timeline(c)["state"] == "in_time"]
    counts["in_time_rate"] = round(100 * len(in_time) / len(disposed)) if disposed else None
    buckets = [("0-7 days", 0, 7), ("8-14", 8, 14), ("15-21", 15, 21), ("22-30", 22, 30), ("31-60", 31, 60), ("Over 60", 61, 10**6)]
    ageing = [{"label": b, "n": sum(lo <= tls[c["id"]]["age"] <= hi for c in open_)} for b, lo, hi in buckets]
    bureaus = []
    for b, info in settings.get()["bureaus"].items():
        bc = [c for c in db.q("SELECT * FROM cases WHERE bureau=?", (b,))]
        bo = [c for c in bc if c["status"] != "disposed"]
        btl = [timeline(c) for c in bo]
        bureaus.append({"bureau": b, "name": info["name"], "open": len(bo), "overdue": sum(t.get("state") == "overdue" for t in btl),
                        "escalated": sum((c["esc_level"] or -1) >= 2 for c in bo),
                        "avg_age": round(sum(t["age"] for t in btl) / len(btl)) if btl else 0,
                        "disposed_30d": sum((c["disposed_on"] or "") >= t30 for c in bc),
                        "officers": len({c["officer_id"] for c in bo})})
    regions = Counter()
    reg_over = Counter()
    for c in open_:
        r = (insts().get(c["permanent_id"] or "") or {}).get("region") or "Not identified"
        regions[r] += 1
        reg_over[r] += tls[c["id"]].get("state") == "overdue"
    alerts = []
    my_bureau = u.get("bureau")
    ordered = sorted(open_alerts(), key=lambda a: a["created_at"], reverse=True)
    for a in sorted(ordered, key=lambda a: overlap.KIND[a["kind"]]["rank"]):
        cs = db.unj(a["cases"], [])
        bs = sorted({(db.q1("SELECT bureau FROM cases WHERE id=?", (x,)) or {}).get("bureau") for x in cs})
        if scope == "mine" and my_bureau and my_bureau not in bs:
            continue
        alerts.append(_alert_row(a, bs, u))
    attention = []
    if u.get("bureau"):
        mine = [c for c in open_ if c["bureau"] == u["bureau"]]
        strong = lambda c: any(a["kind"] != "parallel" for a in amap.get(c["id"], []))
        mine.sort(key=lambda c: (not strong(c), tls[c["id"]]["days_left"]))
        attention = [row(c, u, amap) for c in mine[:8]]
    return {"counts": counts, "ageing": ageing, "bureaus": bureaus, "alerts": alerts,
            "regions": [{"region": r, "open": n, "overdue": reg_over[r]} for r, n in sorted(regions.items())],
            "attention": attention, "model": ai.backend(), "today": today().isoformat()}


def _alert_row(a: dict, bureaus: list[str], u: dict) -> dict:
    inst = insts().get(a["permanent_id"]) or {}
    acks = db.unj(a["acks"], {})
    return {"id": a["id"], "kind": a["kind"], "kind_label": overlap.KIND[a["kind"]]["label"], "color": overlap.KIND[a["kind"]]["color"],
            "title": a["title"], "institution": inst.get("name"), "permanent_id": a["permanent_id"], "region": inst.get("region"),
            "cases": db.unj(a["cases"], []), "bureaus": bureaus, "lead": a["lead"], "status": a["status"], "acks": acks,
            "my_ack": (u.get("bureau") in acks) if u.get("bureau") else None, "created_at": a["created_at"], "updated_at": a["updated_at"]}


# ------------------------------------------------------------------------------------ cases

@app.get("/api/cases")
def cases(q: str = "", bureau: str = "", region: str = "", category: str = "", status: str = "", state: str = "",
          frm: str = "", to: str = "", pid: str = "", mine: int = 0, limit: int = 500, u=Depends(user)):
    amap = alerts_by_case()
    rows = db.q("SELECT * FROM cases ORDER BY received_on DESC")
    out = []
    ql = q.strip().lower()
    for c in rows:
        if bureau and c["bureau"] != bureau or category and c["category"] != category or pid and c["permanent_id"] != pid:
            continue
        if status == "open" and c["status"] == "disposed" or status and status != "open" and c["status"] != status:
            continue
        if mine and c["officer_id"] != u.get("officer_id"):
            continue
        if frm and c["received_on"] < frm or to and c["received_on"] > to:
            continue
        r = row(c, u, amap)
        if region and r["region"] != region:
            continue
        if state == "overdue" and r["timeline"].get("state") != "overdue" or state == "due_soon" and r["timeline"].get("state") != "due_soon":
            continue
        if state == "escalated" and not (c["status"] != "disposed" and (c["esc_level"] or -1) >= 2):
            continue
        if state == "overlap" and not r["alerts"] or state == "unconfirmed" and c["match_state"] not in ("confirm", "unmatched"):
            continue
        if ql:
            hay = " ".join(str(x or "") for x in (c["id"], c["ext_ref"], r["institution"], c["permanent_id"], c["inst_text"],
                                                  r["subject"], r["category_label"], r["city"])).lower()
            if ql not in hay:
                continue
        out.append(r)
    return {"rows": out[:limit], "total": len(out)}


@app.get("/api/cases/{cid:path}/detail")
def case_detail(cid: str, u=Depends(user)):
    c = _case(cid)
    amap = alerts_by_case()
    r = row(c, u, amap)
    vis = r["visible"]
    inst = insts().get(c["permanent_id"] or "")
    hist = db.q("SELECT * FROM actions WHERE case_id=? ORDER BY ts, id", (cid,))
    for h in hist:
        h["label"] = ACTIONS.get(h["kind"], {}).get("label", h["kind"])
        h["extra"] = db.unj(h["extra"], {})
    related = []
    if c["permanent_id"]:
        others = db.q("SELECT * FROM cases WHERE permanent_id=? AND id!=?", (c["permanent_id"], cid))
        if others:
            vecs = ai.case_vectors([c, *others])
            for o in others:
                pm = overlap.same_matter(c, o, vecs[cid], vecs[o["id"]])
                orow = row(o, u, amap)
                related.append({**orow, "same": pm["same"], "score": pm["score"], "reasons": pm["reasons"]})
            related.sort(key=lambda x: (x["status"] == "disposed", -x["score"]))
    al = []
    for a in open_alerts():
        if cid in db.unj(a["cases"], []):
            bs = sorted({db.q1("SELECT bureau FROM cases WHERE id=?", (x,))["bureau"] for x in db.unj(a["cases"], [])})
            al.append({**_alert_row(a, bs, u), "why": a["why"], "reasons": db.unj(a["reasons"], [])})
    audit.log(u["id"], u["role"], "case.viewed", cid, {"full_text": vis})
    match = db.unj(c["match"], {})
    return {
        **r, "description": c["description"] if vis else None,
        "complainant": c["complainant"] if vis and (u["role"] == "management" or c["bureau"] == u.get("bureau")) else mask(c["complainant"]),
        "complainant_type": c["complainant_type"], "institution_detail": inst, "match": match,
        "category_ai": db.unj(c["category_ai"], []), "history": hist, "related": related, "coordination": al,
        "spans": resolve.spans(c["description"], c["permanent_id"]) if vis else [],
        "inst_spans": resolve.spans(c["inst_text"], c["permanent_id"]),
        "can_act": u["role"] == "management" or (u["role"] == "officer" and c["bureau"] == u.get("bureau")),
        "actions": [{"kind": k, "label": ACTIONS[k]["label"]} for k in OFFICER_ACTIONS],
        "bureaus": [{"id": k, "name": v["name"]} for k, v in settings.get()["bureaus"].items()],
        "categories": [{"id": k, "label": v["label"], "bureau": v["bureau"]} for k, v in settings.get()["categories"].items()],
        "suggested_bureau": settings.category(c["category"])["bureau"],
    }


class ActionIn(BaseModel):
    kind: str
    remarks: str = ""
    acknowledged: bool = False
    reason: str = ""
    to_bureau: str | None = None


@app.post("/api/cases/{cid:path}/precheck")
def case_precheck(cid: str, body: ActionIn, u=Depends(user)):
    return {"warnings": overlap.precheck(_case(cid), body.kind)}


@app.post("/api/cases/{cid:path}/action")
def case_action(cid: str, body: ActionIn, u=Depends(user)):
    c = _case(cid)
    _may_act(u, c)
    if body.kind == "transferred" and (not body.to_bureau or body.to_bureau == c["bureau"]):
        raise HTTPException(400, "choose the bureau to transfer to")
    if body.kind not in OFFICER_ACTIONS + ["transferred"]:
        raise HTTPException(400, "unknown action")
    if body.acknowledged and not body.reason.strip() and overlap.precheck(c, body.kind):
        raise HTTPException(400, "give a reason for going ahead")
    try:
        service.add_action(cid, body.kind, body.remarks, u["name"], u["role"], acknowledged=body.acknowledged,
                           reason=body.reason, to_bureau=body.to_bureau)
    except service.Blocked as e:
        return JSONResponse({"detail": "coordination check", "warnings": e.warnings}, status_code=409)
    return {"ok": True}


class CategoryIn(BaseModel):
    category: str


@app.post("/api/cases/{cid:path}/category")
def case_category(cid: str, body: CategoryIn, u=Depends(user)):
    c = _case(cid)
    _may_act(u, c)
    if body.category not in settings.get()["categories"]:
        raise HTTPException(400, "unknown category")
    db.update("cases", "id", cid, {"category": body.category, "due_on": service.due_for(body.category, c["received_on"])})
    audit.log(u["id"], u["role"], "case.category", cid, {"from": c["category"], "to": body.category})
    if c["permanent_id"]:
        overlap.refresh(c["permanent_id"], actor=u["name"])
    return {"ok": True}


class InstIn(BaseModel):
    permanent_id: str | None = None


@app.post("/api/cases/{cid:path}/institution")
def case_institution(cid: str, body: InstIn, u=Depends(user)):
    c = _case(cid)
    _may_act(u, c)
    if body.permanent_id and body.permanent_id not in insts():
        raise HTTPException(404, "institution not found")
    service.confirm_institution(cid, body.permanent_id, u["name"], u["role"])
    return {"ok": True}


class LinkIn(BaseModel):
    a: str
    b: str
    kind: str
    reason: str = ""


@app.post("/api/links")
def link(body: LinkIn, u=Depends(need("officer", "management"))):
    a, b = _case(body.a), _case(body.b)
    if u["role"] == "officer" and u["bureau"] not in (a["bureau"], b["bureau"]):
        raise HTTPException(403, "you can link cases of your own bureau only")
    if body.kind not in ("same", "not_same"):
        raise HTTPException(400, "kind must be same or not_same")
    service.set_link(body.a, body.b, body.kind, u["name"], u["role"], body.reason)
    return {"ok": True}


class NewCase(BaseModel):
    bureau: str | None = None
    source: str = "Letter"
    ext_ref: str | None = None
    received_on: str | None = None
    complainant: str = ""
    complainant_type: str = "Student"
    contact: str = ""
    inst_text: str = ""
    subject: str = ""
    description: str = ""
    category: str | None = None
    permanent_id: str | None = None


class AnalyseIn(BaseModel):
    complainant: str = ""
    inst_text: str = ""
    subject: str = ""
    description: str = ""
    bureau: str | None = None


@app.post("/api/analyse")
def analyse(body: AnalyseIn, u=Depends(user)):
    out = service.analyse(body.inst_text, body.subject, body.description, body.bureau or u.get("bureau"), complainant=body.complainant)
    out["inst_spans"] = resolve.spans(body.inst_text, out["match"]["permanent_id"] or (out["match"]["candidates"][0]["permanent_id"] if out["match"]["candidates"] else None))
    return out


@app.post("/api/cases")
def new_case(body: NewCase, u=Depends(need("officer", "management"))):
    bureau = body.bureau or u.get("bureau")
    if u["role"] == "officer" and bureau != u["bureau"]:
        raise HTTPException(403, "you can register cases for your own bureau only")
    if not body.description.strip() or not body.inst_text.strip():
        raise HTTPException(400, "institution and complaint text are required")
    data = body.model_dump()
    data["bureau"] = bureau
    r = service.create_case(data, u["name"], u["role"])
    return {"id": r["id"]}


@app.post("/api/import")
async def import_csv(file: UploadFile = File(...), commit: int = 0, u=Depends(need("officer", "management"))):
    """A bureau's register (CSV/Excel export). Columns are matched by name; each row is analysed like a new case."""
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(raw)))
    if not rows:
        raise HTTPException(400, "empty file")
    cols = {k.lower().strip(): k for k in rows[0]}

    def col(*names):
        for n in names:
            for k, orig in cols.items():
                if n in k:
                    return orig
        return None

    m = {"ref": col("ref", "registration", "file no", "case"), "date": col("date", "received"), "who": col("complainant", "name"),
         "contact": col("contact", "phone", "mobile", "email"), "inst": col("institution", "college", "institute"),
         "subject": col("subject", "title"), "text": col("description", "complaint", "details", "grievance", "text")}
    if not m["inst"] or not m["text"]:
        raise HTTPException(400, "need at least an institution column and a complaint text column")
    bureau = u.get("bureau") or "PGRC"
    preview = []
    for r in rows[:200]:
        g = lambda k: (r.get(m[k]) or "").strip() if m[k] else ""
        a = service.analyse(g("inst"), g("subject"), g("text"), bureau)
        item = {"ref": g("ref"), "inst_text": g("inst"), "subject": g("subject"), "match": a["match"]["state"],
                "institution": (a["match"]["candidates"][0]["name"] if a["match"]["candidates"] else None),
                "confidence": a["match"]["confidence"], "category": a["categories"][0]["label"],
                "suggested_bureau": a["suggested_bureau"], "duplicates": [x["case"] for x in a["possible_duplicates"]]}
        if commit:
            rd = g("date")
            try:
                rd = date.fromisoformat(rd).isoformat() if rd else None
            except ValueError:
                rd = None
            c = service.create_case({"bureau": bureau, "source": "Register import", "ext_ref": g("ref") or None, "received_on": rd,
                                     "complainant": g("who"), "contact": g("contact"), "inst_text": g("inst"), "subject": g("subject"),
                                     "description": g("text")}, u["name"], u["role"])
            item["id"] = c["id"]
        preview.append(item)
    audit.log(u["id"], u["role"], "register.imported" if commit else "register.previewed", file.filename or "upload", {"rows": len(preview)})
    return {"columns": m, "rows": preview, "committed": bool(commit)}


# ------------------------------------------------------------------------------------ institutions

@app.get("/api/institutions")
def institutions(q: str = "", u=Depends(user)):
    counts = defaultdict(Counter)
    for c in db.q("SELECT permanent_id, bureau, status FROM cases WHERE permanent_id IS NOT NULL"):
        counts[c["permanent_id"]]["total"] += 1
        if c["status"] != "disposed":
            counts[c["permanent_id"]][c["bureau"]] += 1
            counts[c["permanent_id"]]["open"] += 1
    al = Counter(a["permanent_id"] for a in open_alerts() if a["kind"] != "parallel")
    rows = list(insts().values())
    if q.strip():
        m = resolve.resolve(q, "")
        ids = [c["permanent_id"] for c in m["candidates"] if c["confidence"] >= 0.4]
        direct = [r for r in rows if q.lower() in (r["name"] + r["permanent_id"] + r["city"]).lower()]
        rows = direct + [insts()[i] for i in ids if insts()[i] not in direct]
    out = []
    for r in rows:
        cnt = counts[r["permanent_id"]]
        out.append({**r, "aliases": db.unj(r["aliases"], []), "total": cnt["total"], "open": cnt["open"],
                    "open_by_bureau": {b: n for b, n in cnt.items() if b not in ("total", "open")}, "alerts": al[r["permanent_id"]]})
    if not q.strip():
        out.sort(key=lambda r: (-r["alerts"], -r["open"], r["name"]))
    return out


@app.get("/api/institutions/{pid}")
def institution(pid: str, u=Depends(user)):
    inst = insts().get(pid)
    if not inst:
        raise HTTPException(404, "institution not found")
    amap = alerts_by_case()
    cs = db.q("SELECT * FROM cases WHERE permanent_id=? ORDER BY received_on", (pid,))
    rows = [row(c, u, amap) for c in cs]
    lanes = defaultdict(list)
    for c, r in zip(cs, rows):
        acts = db.q("SELECT ts, kind, bureau, to_bureau FROM actions WHERE case_id=? ORDER BY ts, id", (c["id"],))
        segs, cur, start = [], (acts[0]["bureau"] if acts else c["bureau"]), c["received_on"]
        for a in acts:
            if a["kind"] == "transferred" and a["to_bureau"]:
                segs.append({"bureau": cur, "from": start, "to": a["ts"][:10], "moved_to": a["to_bureau"]})
                cur, start = a["to_bureau"], a["ts"][:10]
        segs.append({"bureau": cur, "from": start, "to": c["disposed_on"] or today().isoformat()})
        for s in segs:
            lanes[s["bureau"]].append({"case": c["id"], "from": s["from"], "to": s["to"], "status": c["status"] if "moved_to" not in s else "transferred",
                                       "moved_to": s.get("moved_to"), "label": r["category_label"], "alerts": [a["kind"] for a in r["alerts"]],
                                       "events": [{"ts": a["ts"][:10], "kind": a["kind"], "label": ACTIONS[a["kind"]]["label"]}
                                                  for a in acts if s["from"] <= a["ts"][:10] <= s["to"] and a["kind"] not in ("note", "linked", "received")]})
    al = []
    for a in db.q("SELECT * FROM coordination WHERE permanent_id=? ORDER BY created_at DESC", (pid,)):
        bs = sorted({db.q1("SELECT bureau FROM cases WHERE id=?", (x,))["bureau"] for x in db.unj(a["cases"], [])})
        al.append({**_alert_row(a, bs, u), "why": a["why"], "reasons": db.unj(a["reasons"], [])})
    cats = Counter(r["category_label"] for r in rows)
    return {**inst, "aliases": db.unj(inst["aliases"], []), "cases": rows, "lanes": dict(lanes), "alerts": al,
            "categories": cats.most_common(), "today": today().isoformat(),
            "bureaus": {k: v["name"] for k, v in settings.get()["bureaus"].items()}}


# ------------------------------------------------------------------------------------ coordination

@app.get("/api/coordination")
def coordination(status: str = "open", kind: str = "", u=Depends(user)):
    if status == "open":
        rows = db.q("SELECT * FROM coordination WHERE status IN ('open','acknowledged') ORDER BY created_at DESC")
    else:
        rows = db.q("SELECT * FROM coordination WHERE status IN ('resolved','cleared') ORDER BY updated_at DESC")
    out = []
    for a in rows:
        if kind and a["kind"] != kind:
            continue
        bs = sorted({(db.q1("SELECT bureau FROM cases WHERE id=?", (x,)) or {}).get("bureau") for x in db.unj(a["cases"], [])})
        out.append({**_alert_row(a, bs, u), "why": a["why"], "closed_note": a["closed_note"]})
    out.sort(key=lambda a: a["created_at"] or "", reverse=True)
    out.sort(key=lambda a: overlap.KIND[a["kind"]]["rank"])
    unconfirmed = db.q("SELECT * FROM cases WHERE match_state IN ('confirm','unmatched') ORDER BY received_on DESC")
    amap = alerts_by_case()
    return {"alerts": out, "unconfirmed": [{**row(c, u, amap), "match": db.unj(c["match"], {})} for c in unconfirmed],
            "kinds": overlap.KIND}


@app.get("/api/coordination/{aid}")
def coordination_detail(aid: str, u=Depends(user)):
    a = db.q1("SELECT * FROM coordination WHERE id=?", (aid,))
    if not a:
        raise HTTPException(404, "not found")
    amap = alerts_by_case()
    cs = [db.q1("SELECT * FROM cases WHERE id=?", (x,)) for x in db.unj(a["cases"], [])]
    rows = []
    for c in cs:
        r = row(c, u, amap)
        r["history"] = [{"ts": h["ts"], "label": ACTIONS[h["kind"]]["label"], "bureau": h["bureau"], "remarks": h["remarks"] if r["visible"] else None}
                        for h in db.q("SELECT * FROM actions WHERE case_id=? AND kind NOT IN ('note','linked') ORDER BY ts, id", (c["id"],))]
        r["description"] = c["description"] if r["visible"] else None
        rows.append(r)
    bs = sorted({c["bureau"] for c in cs})
    audit.log(u["id"], u["role"], "coordination.viewed", aid)
    return {**_alert_row(a, bs, u), "why": a["why"], "reasons": db.unj(a["reasons"], []), "closed_note": a["closed_note"],
            "case_rows": rows, "bureau_names": {k: v["name"] for k, v in settings.get()["bureaus"].items()},
            "can_respond": u["role"] == "management" or (u.get("bureau") in bs)}


class CoordIn(BaseModel):
    note: str = ""
    lead: str | None = None


@app.post("/api/coordination/{aid}/{what}")
def coordination_act(aid: str, what: str, body: CoordIn, u=Depends(need("officer", "management"))):
    a = db.q1("SELECT * FROM coordination WHERE id=?", (aid,))
    if not a:
        raise HTTPException(404, "not found")
    bs = sorted({db.q1("SELECT bureau FROM cases WHERE id=?", (x,))["bureau"] for x in db.unj(a["cases"], [])})
    if u["role"] == "officer" and u["bureau"] not in bs:
        raise HTTPException(403, "your bureau is not part of this alert")
    now = service.now().isoformat()
    acks = db.unj(a["acks"], {})
    if what == "ack":
        acks[u.get("bureau") or "MGMT"] = {"by": u["name"], "ts": now, "note": body.note}
        status = "acknowledged" if all(b in acks for b in bs) else a["status"]
        db.update("coordination", "id", aid, {"acks": acks, "status": status, "updated_at": now})
        others = [b for b in bs if b != u.get("bureau")]
        overlap.notify_bureaus(others, "coordination", f"{u.get('bureau') or 'Management'} acknowledged: {a['title']}", coord_id=aid, ts=now,
                               key=f"{aid}:ack:{u.get('bureau')}:{now}")
    elif what == "lead":
        if body.lead not in settings.get()["bureaus"]:
            raise HTTPException(400, "unknown bureau")
        db.update("coordination", "id", aid, {"lead": body.lead, "updated_at": now})
        overlap.notify_bureaus(bs, "coordination", f"Lead for '{a['title']}' set to {body.lead} by {u['name']}", coord_id=aid, ts=now,
                               key=f"{aid}:lead:{now}")
    elif what == "resolve":
        if not body.note.strip():
            raise HTTPException(400, "write what was agreed")
        if u["role"] == "officer" and a["lead"] and u["bureau"] != a["lead"]:
            raise HTTPException(403, f"only the lead bureau ({a['lead']}) or senior management can close this")
        db.update("coordination", "id", aid, {"status": "resolved", "closed_note": body.note, "updated_at": now})
        overlap.notify_bureaus(bs, "coordination", f"Closed: {a['title']} ({body.note})", coord_id=aid, ts=now, key=f"{aid}:resolved")
    else:
        raise HTTPException(404, "unknown")
    audit.log(u["id"], u["role"], f"coordination.{what}", aid, body.model_dump())
    return {"ok": True}


# ------------------------------------------------------------------------------------ notifications

def _my_notes(u: dict) -> list[dict]:
    if u["role"] in ("management", "admin"):
        rows = db.q("SELECT * FROM notifications WHERE to_bureau='MGMT' OR to_role='management' ORDER BY created_at DESC LIMIT 200")
    else:
        rows = db.q("SELECT * FROM notifications WHERE to_bureau=? ORDER BY created_at DESC LIMIT 200", (u["bureau"],))
    for r in rows:
        r["read"] = u["id"] in db.unj(r["read_by"], [])
    return rows


@app.get("/api/notifications")
def notifications(u=Depends(user)):
    rows = _my_notes(u)
    return {"rows": rows, "unread": sum(not r["read"] for r in rows)}


class ReadIn(BaseModel):
    ids: list[int] = []


@app.post("/api/notifications/read")
def notifications_read(body: ReadIn, u=Depends(user)):
    ids = body.ids or [r["id"] for r in _my_notes(u)]
    with db.tx() as cx:
        for i in ids:
            r = cx.execute("SELECT read_by FROM notifications WHERE id=?", (i,)).fetchone()
            if r:
                rb = set(db.unj(r["read_by"], []))
                rb.add(u["id"])
                cx.execute("UPDATE notifications SET read_by=? WHERE id=?", (db.j(sorted(rb)), i))
    return {"ok": True}


# ------------------------------------------------------------------------------------ reports

def _report(frm: str, to: str) -> dict:
    cases = db.q("SELECT * FROM cases")
    recv = [c for c in cases if frm <= c["received_on"] <= to]
    disp = [c for c in cases if c["disposed_on"] and frm <= c["disposed_on"] <= to]
    open_end = [c for c in cases if c["received_on"] <= to and (c["status"] != "disposed" or (c["disposed_on"] or "") > to)]
    end = min(d(to), today())

    def stats(group_key):
        g = defaultdict(lambda: {"received": 0, "disposed": 0, "in_time": 0, "open": 0, "overdue": 0, "days": []})
        for c in recv:
            g[group_key(c)]["received"] += 1
        for c in disp:
            k = g[group_key(c)]
            k["disposed"] += 1
            tl = timeline(c)
            k["in_time"] += tl["state"] == "in_time"
            k["days"].append(tl["age"])
        for c in open_end:
            k = g[group_key(c)]
            k["open"] += 1
            k["overdue"] += timeline({**c, "status": "under_process"}, end).get("state") == "overdue"
        out = []
        for name, v in g.items():
            days = v.pop("days")
            v["avg_days"] = round(sum(days) / len(days)) if days else None
            v["in_time_pct"] = round(100 * v["in_time"] / v["disposed"]) if v["disposed"] else None
            out.append({"name": name, **v})
        return sorted(out, key=lambda r: -(r["received"] + r["open"]))

    reg = lambda c: (insts().get(c["permanent_id"] or "") or {}).get("region") or "Not identified"
    inst_name = lambda c: (insts().get(c["permanent_id"] or "") or {}).get("name") or "Not identified"
    months = []
    m0 = date(d(frm).year, d(frm).month, 1)
    while m0 <= d(to):
        m1 = date(m0.year + (m0.month == 12), m0.month % 12 + 1, 1)
        months.append({"month": m0.strftime("%b %Y"), "received": sum(m0.isoformat() <= c["received_on"] < m1.isoformat() for c in cases),
                       "disposed": sum(bool(c["disposed_on"]) and m0.isoformat() <= c["disposed_on"] < m1.isoformat() for c in cases)})
        m0 = m1
    ageing = Counter()
    for c in open_end:
        a = (end - d(c["received_on"])).days
        ageing["0-21 days" if a <= 21 else "22-45 days" if a <= 45 else "46-90 days" if a <= 90 else "Over 90 days"] += 1
    co = db.q("SELECT * FROM coordination WHERE created_at>=? AND substr(created_at,1,10)<=?", (frm, to))
    return {
        "from": frm, "to": to,
        "totals": {"received": len(recv), "disposed": len(disp), "open_at_end": len(open_end),
                   "disposal_rate": round(100 * len(disp) / max(1, len(recv))), "overlaps": len([a for a in co if a["kind"] != "parallel"])},
        "bureau": stats(lambda c: c["bureau"]), "region": stats(reg), "category": stats(lambda c: settings.category(c["category"])["label"]),
        "status": [{"name": STATUS[s], "n": sum(c["status"] == s for c in cases if c["received_on"] <= to)} for s in STATUS],
        "institution": stats(inst_name)[:15], "monthly": months,
        "ageing": [{"name": k, "n": ageing[k]} for k in ("0-21 days", "22-45 days", "46-90 days", "Over 90 days")],
        "overlaps": [{"name": overlap.KIND[k]["label"], "raised": sum(a["kind"] == k for a in co),
                      "resolved": sum(a["kind"] == k and a["status"] == "resolved" for a in co),
                      "open": sum(a["kind"] == k and a["status"] in ("open", "acknowledged") for a in co)} for k in overlap.KIND],
    }


@app.get("/api/reports")
def reports(frm: str = "", to: str = "", u=Depends(user)):
    to = to or today().isoformat()
    frm = frm or (today() - timedelta(days=89)).isoformat()
    return _report(frm, to)


@app.get("/api/reports.csv")
def reports_csv(table: str, frm: str = "", to: str = "", u=Depends(user)):
    to = to or today().isoformat()
    frm = frm or (today() - timedelta(days=89)).isoformat()
    rep = _report(frm, to)
    rows = rep.get(table)
    if not isinstance(rows, list) or not rows:
        raise HTTPException(404, "no such table")
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
    audit.log(u["id"], u["role"], "report.downloaded", table, {"from": frm, "to": to})
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{table}_{frm}_{to}.csv"'})


# ------------------------------------------------------------------------------------ settings, audit, search

@app.get("/api/settings")
def get_settings(u=Depends(user)):
    s = settings.get()
    return {"settings": s, "overrides": settings.overrides(), "model": ai.backend()}


class SettingIn(BaseModel):
    key: str
    value: object


EDITABLE = ("categories.", "escalation", "matching.", "institution_reply_days")


@app.put("/api/settings")
def put_setting(body: SettingIn, u=Depends(need("admin"))):
    if not body.key.startswith(EDITABLE):
        raise HTTPException(400, "this setting cannot be changed here")
    parts = body.key.split(".")
    if parts[0] == "categories":
        if len(parts) != 3 or parts[1] not in settings.get()["categories"] or parts[2] not in ("days", "bureau", "label"):
            raise HTTPException(400, "unknown category setting")
        if parts[2] == "days" and not (isinstance(body.value, int) and 1 <= body.value <= 365):
            raise HTTPException(400, "days must be 1-365")
        if parts[2] == "bureau" and body.value not in settings.get()["bureaus"]:
            raise HTTPException(400, "unknown bureau")
    settings.put(body.key, body.value, u["name"])
    audit.log(u["id"], u["role"], "settings.changed", body.key, {"value": body.value})
    if parts[0] == "categories" and parts[2] == "days":
        for c in db.q("SELECT id, received_on FROM cases WHERE category=?", (parts[1],)):
            db.update("cases", "id", c["id"], {"due_on": service.due_for(parts[1], c["received_on"])})
        service.sweep()
    return {"ok": True}


@app.get("/api/audit")
def get_audit(limit: int = 300, target: str = "", u=Depends(need("management", "admin", "officer"))):
    if target:
        rows = db.q("SELECT * FROM audit WHERE target LIKE ? ORDER BY seq DESC LIMIT ?", (f"%{target}%", limit))
    else:
        rows = db.q("SELECT * FROM audit ORDER BY seq DESC LIMIT ?", (limit,))
    for r in rows:
        r["payload"] = db.unj(r["payload"], {})
    return {"entries": rows, "chain": audit.verify_chain()}


@app.get("/api/search")
def search(q: str, u=Depends(user)):
    q = q.strip()
    if len(q) < 2:
        return {"cases": [], "institutions": []}
    cs = db.q("SELECT id, bureau, status, permanent_id FROM cases WHERE id LIKE ? OR ext_ref LIKE ? LIMIT 8", (f"%{q}%", f"%{q}%"))
    for c in cs:
        c["institution"] = (insts().get(c["permanent_id"] or "") or {}).get("name")
    m = resolve.resolve(q, "")
    direct = [r for r in insts().values() if q.lower() in (r["name"] + " " + r["permanent_id"]).lower()]
    seen = {r["permanent_id"] for r in direct}
    fuzzy = [insts()[c["permanent_id"]] for c in m["candidates"] if c["confidence"] >= 0.45 and c["permanent_id"] not in seen]
    return {"cases": cs, "institutions": [{"permanent_id": r["permanent_id"], "name": r["name"], "city": r["city"]} for r in (direct + fuzzy)[:8]]}


@app.get("/api/eval")
def get_eval(u=Depends(user)):
    p = DATA / "eval_report.json"
    if not p.exists():
        raise HTTPException(404, "run scripts/evaluate.py")
    return json.loads(p.read_text(encoding="utf-8"))


@app.get("/api/meta")
def meta(u=Depends(user)):
    s = settings.get()
    return {"bureaus": [{"id": k, "name": v["name"]} for k, v in s["bureaus"].items()],
            "regions": list(s["regions"].keys()),
            "categories": [{"id": k, "label": v["label"], "bureau": v["bureau"], "days": v["days"]} for k, v in s["categories"].items()],
            "statuses": [{"id": k, "label": v} for k, v in STATUS.items()], "today": today().isoformat()}


# ------------------------------------------------------------------------------------ background timeline check

def _sweeper():
    while True:
        try:
            service.sweep()
        except Exception:  # never let the background check stop the server
            pass
        time.sleep(900)


@app.on_event("startup")
def _start():
    threading.Thread(target=lambda: (ai.backend(), _sweeper()), daemon=True).start()


# ------------------------------------------------------------------------------------ static frontend

DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
