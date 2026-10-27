"""HTTP API (FastAPI). Role-based access is enforced server-side on every route.

Run:  uvicorn app.api:app --port 8000   (from backend/)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pymupdf
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import audit, db, docmodel, graph, pipeline, wording
from .config import APH_PDF, DATA, RENDER, ROOT, STORE
from .extract import docs as D
from .rules import citations, engine, norms
from .verify import connectors, registry

logging.getLogger("pyhanko").setLevel(logging.CRITICAL)
app = FastAPI(title="Satyapan - application validation and document verification")
SECRET = b"satyapan-demo-secret"

USERS = {
    "officer": {"name": "R. Sharma", "role": "scrutiny_officer", "title": "Scrutiny Officer, South-Central Region"},
    "verifier": {"name": "A. Menon", "role": "verifier", "title": "Verification Cell"},
    "admin": {"name": "S. Iyer", "role": "admin", "title": "Approval Bureau (rules & sources)"},
}
ROLES_READ_ALL = {"scrutiny_officer", "verifier", "admin"}


# ------------------------------------------------------------------------------------ auth

def _sign(payload: str) -> str:
    return payload + "." + hmac.new(SECRET, payload.encode(), hashlib.sha256).hexdigest()[:24]


def user(x_token: str | None = Header(default=None)) -> dict:
    if not x_token or "." not in x_token:
        raise HTTPException(401, "login required")
    payload, sig = x_token.rsplit(".", 1)
    if _sign(payload) != x_token:
        raise HTTPException(401, "bad token")
    uid = payload
    if uid.startswith("inst:"):
        pid = uid[5:]
        inst = db.q1("SELECT name FROM institutions WHERE permanent_id=?", (pid,))
        return {"id": uid, "name": (inst or {}).get("name", pid), "role": "institution", "permanent_id": pid, "title": "Institution login"}
    u = USERS.get(uid)
    if not u:
        raise HTTPException(401, "unknown user")
    return {"id": uid, **u}


def need(*roles):
    def dep(u=Depends(user)):
        if u["role"] not in roles:
            raise HTTPException(403, f"role '{u['role']}' may not perform this action")
        return u
    return dep


def _can_see_app(u: dict, app_row: dict) -> None:
    if u["role"] in ROLES_READ_ALL:
        return
    if u["role"] == "institution" and app_row["permanent_id"] == u["permanent_id"]:
        return
    raise HTTPException(403, "not your application")


class Login(BaseModel):
    user: str


@app.post("/api/login")
def login(body: Login):
    uid = body.user
    if uid.startswith("inst:"):
        if not db.q1("SELECT 1 FROM institutions WHERE permanent_id=?", (uid[5:],)):
            raise HTTPException(404, "institution not found")
    elif uid not in USERS:
        raise HTTPException(404, "unknown user")
    tok = _sign(uid)
    u = user(tok)
    audit.log(uid, u["role"], "auth.login", uid, {})
    return {"token": tok, "user": u}


@app.get("/api/me")
def me(u=Depends(user)):
    return u


@app.get("/api/demo-users")
def demo_users():
    insts = db.q("SELECT a.permanent_id, i.name FROM applications a JOIN institutions i ON i.permanent_id=a.permanent_id ORDER BY i.name")
    return {"staff": [{"id": k, **v} for k, v in USERS.items()], "institutions": insts}


# ------------------------------------------------------------------------------------ views

def _applicant_lane(app_id: str) -> tuple[str, dict]:
    """Lane as the applicant may see it: computed without cross-institution intelligence."""
    fs = db.q("SELECT * FROM findings WHERE application_id=? AND kind != 'network'", (app_id,))
    vs = db.q("SELECT status FROM verifications WHERE application_id=?", (app_id,))
    lane, _, summary = pipeline._lane(fs, vs)
    return lane, summary


def _app_rows(where="", args=()):
    rows = db.q(f"SELECT a.id, a.permanent_id, a.category, a.academic_year, a.status, a.lane, a.risk, a.summary, a.created_at, "
                f"a.processed_at, a.source, i.name, i.state, i.region, i.source AS inst_source FROM applications a "
                f"LEFT JOIN institutions i ON i.permanent_id=a.permanent_id {where} ORDER BY a.risk DESC", args)
    sev = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    for r in rows:
        r["summary"] = db.unj(r["summary"], {})
        r["decision"] = _decision(r["id"])
        fs = [{**f, "title": wording.title(f)} for f in db.q("SELECT rule_id, title, kind, severity, status FROM findings WHERE application_id=? "
                                                              "AND status IN ('fail','warn','manual')", (r["id"],))]
        fs.sort(key=lambda f: ({"fail": 0, "warn": 1, "manual": 2}[f["status"]], sev.get(f["severity"], 9)))
        seen, top = set(), []
        for f in fs:
            if f["title"] not in seen and f["status"] == "fail":
                seen.add(f["title"]); top.append({"title": f["title"], "kind": f["kind"]})
        r["top"] = top[:3]
        r["n_fail"] = sum(1 for f in fs if f["status"] == "fail")
        r["n_check"] = sum(1 for f in fs if f["status"] != "fail")
    return rows


def _decision(app_id):
    r = db.q1("SELECT * FROM reviews WHERE application_id=? AND finding_id='__decision__' ORDER BY id DESC LIMIT 1", (app_id,))
    return r


@app.get("/api/stats")
def stats(u=Depends(need(*ROLES_READ_ALL))):
    apps = _app_rows("WHERE a.source != 'precheck'")
    lanes = {k: sum(1 for a in apps if a["lane"] == k) for k in ("green", "amber", "red")}
    ver = {r["status"]: r["n"] for r in db.q("SELECT status, COUNT(*) n FROM verifications GROUP BY status")}
    open_alerts = db.q1("SELECT COUNT(*) n FROM findings f WHERE status IN ('fail','warn','manual') AND NOT EXISTS "
                        "(SELECT 1 FROM reviews r WHERE r.finding_id=f.id)")["n"]
    secs = [a["summary"].get("seconds") for a in apps if a["summary"].get("seconds")]
    led = {"institutions": db.q1("SELECT COUNT(*) n FROM institutions WHERE source='public_eoa'")["n"],
           "approvals": db.q1("SELECT COUNT(*) n FROM approvals WHERE source_url != ''")["n"],
           "courses": db.q1("SELECT COUNT(*) n FROM approval_courses c JOIN approvals a ON a.id=c.approval_id WHERE a.source_url != ''")["n"]}
    return {"applications": len(apps), "lanes": lanes, "verifications": ver, "open_alerts": open_alerts,
            "avg_seconds": round(sum(secs) / len(secs), 1) if secs else None, "ledger": led,
            "network_links": len(graph.network()["edges"]), "audit": audit.verify_chain()}


@app.get("/api/applications")
def applications(u=Depends(user)):
    if u["role"] == "institution":
        rows = _app_rows("WHERE a.permanent_id=?", (u["permanent_id"],))
        for r in rows:
            r["lane"], summ = _applicant_lane(r["id"])
            r["summary"] = {**summ, "seconds": r["summary"].get("seconds")}
        return rows
    return _app_rows("WHERE a.source != 'precheck'")


def _findings(app_id: str, u: dict) -> list[dict]:
    rows = db.q("SELECT * FROM findings WHERE application_id=?", (app_id,))
    reviews = {r["finding_id"]: r for r in db.q("SELECT * FROM reviews WHERE application_id=? ORDER BY id", (app_id,))}
    remedies = {r["id"]: r.get("remedy") for r in engine.ruleset()["rules"]}
    out = []
    for f in rows:
        if f["rule_id"] in remedies and remedies[f["rule_id"]]:
            f["remedy"] = remedies[f["rule_id"]]          # rules are editable: always show the current wording
        if u["role"] == "institution" and f["kind"] in ("authenticity", "verification"):
            f["remedy"] = "Upload the original document exactly as the issuing office gave it, without any changes."
        if u["role"] == "institution" and f["kind"] in ("network",):
            continue        # cross-institution intelligence is not disclosed to applicants
        ev = db.unj(f["evidence"], {})
        cit = db.unj(f["citation"], {})
        if cit.get("quote") and not cit.get("loc"):
            cit["loc"] = citations.locate(cit["quote"])
        out.append({**f, "title": wording.title(f), "evidence": ev.get("items", []), "derivation": ev.get("derivation"), "citation": cit,
                    "review": reviews.get(f["id"])})
    order = {"fail": 0, "warn": 1, "manual": 2, "pass": 3, "na": 4}
    sev = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    return sorted(out, key=lambda f: (order.get(f["status"], 9), sev.get(f["severity"], 9)))


@app.get("/api/applications/{app_id}")
def application(app_id: str, u=Depends(user)):
    a = db.q1("SELECT * FROM applications WHERE id=?", (app_id,))
    if not a:
        raise HTTPException(404)
    _can_see_app(u, a)
    form = db.unj(a["form"], {})
    inst = db.q1("SELECT * FROM institutions WHERE permanent_id=?", (a["permanent_id"],))
    docs = db.q("SELECT id, declared_type, doc_type, filename, sha256, mime, pages, page_sizes, classification, extraction, forensics "
                "FROM documents WHERE application_id=?", (app_id,))
    for d in docs:
        for k in ("page_sizes", "classification", "extraction", "forensics"):
            d[k] = db.unj(d[k], {})
        d["title"] = D.DOC_TYPES.get(d["doc_type"], {}).get("title", d["doc_type"])
    verifs = []
    for v in db.q("SELECT * FROM verifications WHERE application_id=?", (app_id,)):
        resp = db.unj(v["response"], {})
        verifs.append({**v, "request": db.unj(v["request"], {}), "response": resp.get("response"), "checks": resp.get("checks", []),
                       "letter": resp.get("letter"), "evidence": resp.get("evidence", []), "resolution": resp.get("resolution")})
    ledger = pipeline._ledger(a["permanent_id"], a["academic_year"])
    delta = []
    if ledger and ledger.get("courses"):
        k = lambda c: ((c.get("level") or "").upper().replace(" ", ""), c["course"].upper())  # noqa: E731
        prev = {k(c): c["intake_curr"] for c in ledger["courses"]}
        for c in form.get("courses", []):
            p = prev.pop(k(c), None)
            delta.append({"course": c["course"], "approved": p, "applied": c["intake"],
                          "change": "new" if p is None else ("increase" if c["intake"] > p else ("decrease" if c["intake"] < p else "same"))})
        for kk, p in prev.items():
            if p:
                delta.append({"course": kk[1], "approved": p, "applied": 0, "change": "dropped"})
    req = {"faculty": norms.faculty_requirement(form.get("courses", [])), "area": norms.area_requirement(form.get("courses", [])),
           "ter": norms.ter_required(form.get("courses", []), a["academic_year"], (inst or {}).get("inst_type", ""))}
    form = {**form, "faculty": [{**f, "pan": "XXXXX" + f.get("pan", "")[5:9] + "X"} for f in form.get("faculty", [])]}
    audit.log(u["id"], u["role"], "application.viewed", app_id, {})
    summary = db.unj(a["summary"], {})
    if u["role"] == "institution":
        a = {**a}
        a["lane"], s2 = _applicant_lane(app_id)
        summary = {**s2, "seconds": summary.get("seconds")}
    return {"application": {**{k: a[k] for k in ("id", "permanent_id", "category", "academic_year", "status", "lane", "risk",
                                                 "created_at", "processed_at", "source")},
                            "summary": summary, "decision": _decision(app_id) if u["role"] != "institution" else None},
            "institution": inst, "form": form, "documents": docs, "findings": _findings(app_id, u),
            "verifications": verifs, "ledger": ledger, "delta": delta, "norms": req}


def _doc_or_404(doc_id: str, u: dict) -> dict:
    d = db.q1("SELECT * FROM documents WHERE id=?", (doc_id,))
    if not d:
        raise HTTPException(404)
    a = db.q1("SELECT permanent_id FROM applications WHERE id=?", (d["application_id"],))
    _can_see_app(u, a)
    return d


def _raw(d: dict) -> bytes:
    ext = Path(d["filename"]).suffix.lower()
    return (STORE / f"{d['sha256']}{ext}").read_bytes()


@app.get("/api/documents/{doc_id}/page/{n}.png")
def page_png(doc_id: str, n: int, t: str | None = None):
    u = user(t)
    d = _doc_or_404(doc_id, u)
    p = docmodel.render_page(_raw(d), d["sha256"], n, "image" if d["mime"].startswith("image") else "pdf")
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "max-age=3600"})


@app.get("/api/documents/{doc_id}/file")
def doc_file(doc_id: str, t: str | None = None):
    u = user(t)
    d = _doc_or_404(doc_id, u)
    audit.log(u["id"], u["role"], "document.downloaded", doc_id, {"sha256": d["sha256"]})
    return Response(_raw(d), media_type=d["mime"], headers={"Content-Disposition": f'inline; filename="{d["filename"]}"'})


@app.get("/api/documents/{doc_id}/revision/{k}.png")
def revision_png(doc_id: str, k: int, page: int = 0, t: str | None = None):
    """Render an earlier saved revision of a PDF (recovered from incremental updates)."""
    from .forensics.pdf import revisions
    u = user(t)
    d = _doc_or_404(doc_id, u)
    raw = _raw(d)
    revs = revisions(raw)["revisions"]
    if k >= len(revs):
        raise HTTPException(404)
    out = RENDER / f"{d['sha256']}_rev{k}_{page}.png"
    if not out.exists():
        pdf = pymupdf.open(stream=raw[:revs[k]["end"]], filetype="pdf")
        pdf[page].get_pixmap(matrix=pymupdf.Matrix(110 / 72, 110 / 72)).save(out)
    return FileResponse(out, media_type="image/png")


@app.get("/api/aph/page/{n}.png")
def aph_page(n: int):
    out = RENDER / f"aph_{n}.png"
    if not out.exists():
        pdf = pymupdf.open(APH_PDF)
        pdf[n].get_pixmap(matrix=pymupdf.Matrix(110 / 72, 110 / 72)).save(out)
    return FileResponse(out, media_type="image/png", headers={"Cache-Control": "max-age=86400"})


@app.get("/api/network")
def network(u=Depends(need(*ROLES_READ_ALL))):
    return graph.network()


@app.get("/api/verifications")
def verification_queue(status: str | None = None, u=Depends(need(*ROLES_READ_ALL))):
    rows = db.q("SELECT v.*, d.filename, d.doc_type, a.permanent_id, i.name FROM verifications v JOIN documents d ON d.id=v.document_id "
                "JOIN applications a ON a.id=v.application_id LEFT JOIN institutions i ON i.permanent_id=a.permanent_id "
                + ("WHERE v.status=? " if status else "") + "ORDER BY v.ts DESC", (status,) if status else ())
    for r in rows:
        resp = db.unj(r["response"], {})
        r.update({"request": db.unj(r["request"], {}), "checks": resp.get("checks", []), "letter": resp.get("letter"),
                  "resolution": resp.get("resolution"), "response": resp.get("response")})
    return rows


class Resolve(BaseModel):
    status: str
    note: str


@app.post("/api/verifications/{vid}/resolve")
def resolve_verification(vid: str, body: Resolve, u=Depends(need("verifier", "admin"))):
    if body.status not in ("verified", "mismatch", "expired", "manual_review", "pending"):
        raise HTTPException(400, "bad status")
    if len(body.note.strip()) < 5:
        raise HTTPException(400, "a note describing how the source was confirmed is required")
    v = db.q1("SELECT * FROM verifications WHERE id=?", (vid,))
    if not v:
        raise HTTPException(404)
    resp = db.unj(v["response"], {})
    resp["resolution"] = {"by": u["name"], "role": u["role"], "status": body.status, "note": body.note,
                          "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "previous": v["status"]}
    with db.tx() as c:
        c.execute("UPDATE verifications SET status=?, response=? WHERE id=?", (body.status, db.j(resp), vid))
    audit.log(u["id"], u["role"], "verification.resolved_manually", vid, {"from": v["status"], "to": body.status, "note": body.note})
    pipeline.refresh_network()
    return {"ok": True}


class Review(BaseModel):
    decision: str      # confirm | dismiss
    reason: str


@app.post("/api/findings/{fid}/review")
def review_finding(fid: str, body: Review, u=Depends(need("scrutiny_officer", "admin"))):
    f = db.q1("SELECT * FROM findings WHERE id=?", (fid,))
    if not f:
        raise HTTPException(404)
    if body.decision not in ("confirm", "dismiss"):
        raise HTTPException(400)
    if len(body.reason.strip()) < 5:
        raise HTTPException(400, "a reason is required for every review")
    db.insert("reviews", {"finding_id": fid, "application_id": f["application_id"], "actor": u["name"], "role": u["role"],
                          "decision": body.decision, "reason": body.reason, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    audit.log(u["id"], u["role"], f"finding.{body.decision}ed", fid, {"rule": f["rule_id"], "reason": body.reason, "app": f["application_id"]})
    return {"ok": True}


class Decision(BaseModel):
    recommendation: str   # recommend_eoa | deficiency_letter | refer_evc | refer_verification
    note: str


ADVERSE = {"deficiency_letter", "refer_evc", "refer_verification"}


@app.post("/api/applications/{app_id}/decision")
def decision(app_id: str, body: Decision, u=Depends(need("scrutiny_officer"))):
    """Recommendation by a human officer. Safeguard: adverse recommendations require every
    critical/high automated finding to have been reviewed by a person first."""
    a = db.q1("SELECT * FROM applications WHERE id=?", (app_id,))
    if not a:
        raise HTTPException(404)
    pending = db.q("SELECT id, title FROM findings f WHERE application_id=? AND status='fail' AND severity IN ('critical','high') "
                   "AND NOT EXISTS (SELECT 1 FROM reviews r WHERE r.finding_id=f.id)", (app_id,))
    if body.recommendation in ADVERSE and pending:
        raise HTTPException(409, {"message": "Review each critical/high automated finding before an adverse recommendation.",
                                  "unreviewed": pending})
    db.insert("reviews", {"finding_id": "__decision__", "application_id": app_id, "actor": u["name"], "role": u["role"],
                          "decision": body.recommendation, "reason": body.note, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    audit.log(u["id"], u["role"], "application.recommendation", app_id, {"recommendation": body.recommendation, "note": body.note})
    return {"ok": True}


# ------------------------------------------------------------------------------------ rules & sources

@app.get("/api/rules")
def rules(u=Depends(user)):
    return engine.ruleset()


class RulePatch(BaseModel):
    enabled: bool | None = None
    params: dict | None = None
    reason: str = ""


@app.put("/api/rules/{rule_id}")
def patch_rule(rule_id: str, body: RulePatch, u=Depends(need("admin"))):
    base = {r["id"]: r for r in engine._load()["rules"]}
    if rule_id not in base:
        raise HTTPException(404)
    cur = db.q1("SELECT * FROM rule_overrides WHERE rule_id=?", (rule_id,))
    enabled = body.enabled if body.enabled is not None else (bool(cur["enabled"]) if cur else True)
    params = {**(db.unj(cur["params"], {}) if cur else {}), **(body.params or {})}
    db.insert("rule_overrides", {"rule_id": rule_id, "enabled": int(enabled), "params": params, "updated_by": u["name"],
                                 "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}, replace=True)
    audit.log(u["id"], u["role"], "rule.changed", rule_id, {"enabled": enabled, "params": params, "reason": body.reason})
    return {"ok": True}


@app.get("/api/sources")
def sources(u=Depends(need(*ROLES_READ_ALL))):
    return registry.sources()


class SourcePatch(BaseModel):
    available: bool


@app.put("/api/sources/{name}")
def patch_source(name: str, body: SourcePatch, u=Depends(need("admin"))):
    registry.set_available(name, body.available)
    audit.log(u["id"], u["role"], "source.availability", name, {"available": body.available})
    return {"ok": True}


@app.post("/api/applications/{app_id}/reverify")
def reverify(app_id: str, u=Depends(need("verifier", "admin", "scrutiny_officer"))):
    """Retry source verification (e.g. after an issuer portal comes back online)."""
    a = db.q1("SELECT * FROM applications WHERE id=?", (app_id,))
    form = db.unj(a["form"], {})
    docs = [{**d, "extraction": db.unj(d["extraction"], {}), "forensics": db.unj(d["forensics"], {}),
             "classification": db.unj(d["classification"], {})} for d in db.q("SELECT * FROM documents WHERE application_id=?", (app_id,))]
    ctx = pipeline._ctx(a, form, docs)
    ctx["raw_by_doc"] = {d["id"]: _raw(d) for d in docs}
    changed = 0
    for v in db.q("SELECT * FROM verifications WHERE application_id=? AND status IN ('source_unavailable','pending')", (app_id,)):
        d = next(x for x in docs if x["id"] == v["document_id"])
        for nv in connectors.run(d, ctx):
            if nv["connector"] == v["connector"]:
                resp = {"response": nv["response"], "checks": nv["checks"], "letter": None, "evidence": nv["evidence"]}
                with db.tx() as c:
                    c.execute("UPDATE verifications SET status=?, source=?, response=?, detail=?, ts=? WHERE id=?",
                              (nv["status"], nv["source"], db.j(resp), nv["detail"], nv["ts"], v["id"]))
                audit.log(u["id"], u["role"], "verification.retried", v["id"], {"status": nv["status"]})
                changed += 1
    pipeline.refresh_network()
    return {"retried": changed}


# ------------------------------------------------------------------------------------ audit

@app.get("/api/audit")
def audit_log(limit: int = 300, target: str | None = None, u=Depends(need(*ROLES_READ_ALL))):
    if target:
        rows = db.q("SELECT * FROM audit WHERE target LIKE ? ORDER BY seq DESC LIMIT ?", (f"%{target}%", limit))
    else:
        rows = db.q("SELECT * FROM audit ORDER BY seq DESC LIMIT ?", (limit,))
    for r in rows:
        r["payload"] = db.unj(r["payload"], {})
    return {"entries": rows, "chain": audit.verify_chain()}


# ------------------------------------------------------------------------------------ institution pre-check

@app.post("/api/precheck")
async def precheck(form: str = Form(...), declared: str = Form(...), files: list[UploadFile] = File(...), u=Depends(user)):
    """Institution uploads its package *before* final submission and gets the same checks instantly."""
    f = json.loads(form)
    types = json.loads(declared)
    if u["role"] == "institution" and f.get("permanent_id") != u["permanent_id"]:
        raise HTTPException(403, "can only pre-check your own institution")
    payload = [(up.filename, await up.read(), types.get(up.filename)) for up in files]
    aid = pipeline.process(f, payload, source="precheck", actor=u["id"], role=u["role"])
    return {"application_id": aid}


@app.post("/api/precheck/{app_id}/resubmit")
async def resubmit(app_id: str, declared: str = Form("{}"), files: list[UploadFile] = File(default=[]), form: str | None = Form(None),
                   u=Depends(user)):
    """Re-run the checks with some documents replaced and/or form fields corrected (a pre-check loop)."""
    payload = [(up.filename, await up.read(), json.loads(declared).get(up.filename)) for up in files]
    return _rerun(app_id, payload, json.loads(form) if form else None, u)


def _rerun(app_id: str, new_files: list, form_patch: dict | None, u: dict) -> dict:
    a = db.q1("SELECT * FROM applications WHERE id=?", (app_id,))
    if not a:
        raise HTTPException(404)
    _can_see_app(u, a)
    original = db.unj(a["form"], {})
    if form_patch and "faculty" in form_patch:
        form_patch = {**form_patch, "faculty": _restore_pans(form_patch["faculty"], original.get("faculty", []))}
    form = {**original, **(form_patch or {})}
    replace_types = {t for _, _, t in new_files if t != "infra_photo"}
    old = [d for d in db.q("SELECT * FROM documents WHERE application_id=?", (app_id,)) if d["declared_type"] not in replace_types]
    payload = [(d["filename"], _raw(d), d["declared_type"]) for d in old] + new_files
    aid = pipeline.process(form, payload, source="precheck", actor=u["id"], role=u["role"])
    audit.log(u["id"], u["role"], "application.rechecked", aid, {"previous": app_id, "replaced": sorted(replace_types),
                                                                  "form_fields_changed": sorted((form_patch or {}).keys())})
    return {"application_id": aid, "previous": app_id}


FACULTY_COLS = ["name", "faculty_id", "designation", "qualification", "department", "date_of_joining", "dob", "pan", "gender"]


def _restore_pans(rows: list[dict], previous: list[dict]) -> list[dict]:
    """PANs are shown masked; when a downloaded list comes back, put the stored PAN back by faculty ID."""
    by_id = {f.get("faculty_id"): f for f in previous if f.get("faculty_id")}
    out = []
    for r in rows:
        r = {k: (str(v).strip() if v is not None else "") for k, v in r.items() if k in FACULTY_COLS}
        if not r.get("name"):
            continue
        prev = by_id.get(r.get("faculty_id"))
        if prev and (not r.get("pan") or r["pan"].upper().startswith("XXXXX")):
            r["pan"] = prev.get("pan", "")
            r.setdefault("dob", prev.get("dob", ""))
        out.append(r)
    return out


def _parse_faculty_csv(text: str) -> list[dict]:
    import csv
    import io
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    return [{k.strip().lower().replace(" ", "_"): v for k, v in r.items() if k} for r in rows]


@app.get("/api/precheck/{app_id}/fixes")
def demo_fixes(app_id: str, u=Depends(user)):
    """Corrected documents prepared for the demo (e.g. a renewed fire NOC), if any."""
    a = db.q1("SELECT * FROM applications WHERE id=?", (app_id,))
    _can_see_app(u, a)
    d = DATA / "synthetic" / "demo" / a["permanent_id"] / "fixes"
    return [{"file": p.name, "declared_type": p.stem.split("__")[0]} for p in sorted(d.glob("*"))] if d.exists() else []


@app.post("/api/precheck/{app_id}/fixes/{name}")
def apply_demo_fix(app_id: str, name: str, u=Depends(user)):
    a = db.q1("SELECT * FROM applications WHERE id=?", (app_id,))
    _can_see_app(u, a)
    p = DATA / "synthetic" / "demo" / a["permanent_id"] / "fixes" / Path(name).name
    if not p.exists():
        raise HTTPException(404)
    kind = p.stem.split("__")[0]
    if kind == "faculty":
        return _rerun(app_id, [], {"faculty": _parse_faculty_csv(p.read_text("utf-8"))}, u)
    return _rerun(app_id, [(p.name.split("__", 1)[1], p.read_bytes(), kind)], None, u)


# ------------------------------------------------------------------------------------ real EoA letter verification

@app.post("/api/eoa/verify")
async def verify_eoa(file: UploadFile = File(...), u=Depends(need(*ROLES_READ_ALL))):
    return _verify_eoa(file.filename, await file.read(), u)


@app.get("/api/eoa/samples")
def eoa_samples(u=Depends(need(*ROLES_READ_ALL))):
    p = DATA / "samples" / "samples.json"
    return json.loads(p.read_text("utf-8")) if p.exists() else []


@app.post("/api/eoa/samples/{sid}")
def eoa_sample_verify(sid: str, u=Depends(need(*ROLES_READ_ALL))):
    s = next((x for x in eoa_samples(u) if x["id"] == sid), None)
    if not s:
        raise HTTPException(404)
    return {**_verify_eoa(s["file"], (DATA / "samples" / s["file"]).read_bytes(), u), "sample": s}


def _verify_eoa(filename: str, raw: bytes, u: dict) -> dict:
    t0 = time.time()
    doc = docmodel.load(Path(filename), data=raw)
    from .forensics import pdf as FP
    fx = FP.analyse(doc)
    ex = D.extract(doc, "eoa_letter")
    letters = ex.get("letters", [])
    tmp = {"id": "tmp-" + uuid.uuid4().hex[:6], "doc_type": "eoa_letter", "extraction": ex, "mime": "application/pdf"}
    ver = connectors.aicte_eoa(tmp, {}) if letters else None
    dummy = {"id": tmp["id"], "mime": "application/pdf", "doc_type": "eoa_letter", "forensics": fx}
    ff = pipeline.forensic_findings(dummy, {"form": {}})
    sha = docmodel.sha256_bytes(raw)
    (STORE / f"{sha}.pdf").write_bytes(raw)
    docmodel.render_page(raw, sha, 0, "pdf")
    audit.log(u["id"], u["role"], "eoa.verified", filename, {"sha256": sha, "status": ver["status"] if ver else None})
    return {"sha256": sha, "pages": len(doc.pages), "page_sizes": [[p.width, p.height] for p in doc.pages],
            "letters": letters, "verification": ver, "forensics": fx, "findings": ff, "seconds": round(time.time() - t0, 1)}


@app.get("/api/eoa/page/{sha}/{n}.png")
def eoa_page(sha: str, n: int):
    if not all(c in "0123456789abcdef" for c in sha):
        raise HTTPException(400)
    p = STORE / f"{sha}.pdf"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(docmodel.render_page(p.read_bytes(), sha, n, "pdf"), media_type="image/png")


@app.get("/api/ledger")
def ledger(q: str = "", u=Depends(need(*ROLES_READ_ALL))):
    rows = db.q("SELECT i.permanent_id, i.name, i.state, i.region, i.inst_type, i.source, COUNT(a.id) letters, "
                "GROUP_CONCAT(a.academic_year) years FROM institutions i LEFT JOIN approvals a ON a.permanent_id=i.permanent_id "
                "WHERE i.source='public_eoa' AND (i.name LIKE ? OR i.permanent_id LIKE ?) GROUP BY i.permanent_id ORDER BY i.name",
                (f"%{q}%", f"%{q}%"))
    corpus = json.loads((DATA / "corpus_stats.json").read_text("utf-8")) if (DATA / "corpus_stats.json").exists() else None
    return {"institutions": rows, "corpus": corpus}


@app.get("/api/ledger/{pid}")
def ledger_inst(pid: str, u=Depends(need(*ROLES_READ_ALL))):
    inst = db.q1("SELECT * FROM institutions WHERE permanent_id=?", (pid,))
    appr = db.q("SELECT * FROM approvals WHERE permanent_id=? ORDER BY academic_year", (pid,))
    for a in appr:
        a["courses"] = db.q("SELECT * FROM approval_courses WHERE approval_id=?", (a["id"],))
        a["deficiencies"] = db.unj(a["deficiencies"], [])
    return {"institution": inst, "approvals": appr}


@app.get("/api/eval")
def eval_report(u=Depends(need(*ROLES_READ_ALL))):
    p = DATA / "eval_report.json"
    return json.loads(p.read_text("utf-8")) if p.exists() else {"missing": True}


@app.on_event("startup")
def _warm():
    for r in engine._load()["rules"]:
        citations.locate(r["cite"]["quote"])


DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
