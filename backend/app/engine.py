"""Approval workflow: each application's route (APH Table 2.3), movement between stages, return / revert,
decisions, and the countdown to the Academic Calendar date.

Every movement is written to the application's history and to the tamper-evident activity log. Decisions
reserved for the competent authority are only recorded here when an authorised person takes them.
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta

from . import audit, clock, db, notify, settings
from .clock import d, iso

COMMITTEES = ("scrutiny", "re_scrutiny", "evc", "shc", "sac")
OUTCOME = {
    "in_order": "Found in order", "deficient": "Deficiencies found", "recommend": "Recommended",
    "not_recommend": "Not recommended", "fresh_evc": "Fresh EVC ordered", "reverted": "Returned",
    "submitted": "Compliance submitted", "appealed": "Appeal filed", "lapsed": "No appeal filed in time",
    "approve": "Approval granted", "lod": "Letter of Deficiency issued", "reject": "Rejected",
}
STATUS = {"in_process": "In process", "approved": "Approved", "lod": "Letter of Deficiency", "rejected": "Rejected"}
RISK = {
    "on_track": "On track", "at_risk": "At risk", "fast_track": "Needs fast-tracking", "will_miss": "Will miss the date",
}


class WorkflowError(Exception):
    pass


# ------------------------------------------------------------------------------------ holders

def inst_code(pid: str) -> str:
    return f"INST:{pid}"


def ro_code(region: str) -> str:
    return f"RO:{region}"


def holder_kind(code: str | None) -> str:
    return "institution" if (code or "").startswith("INST:") else "aicte"


def holder_label(code: str | None, inst_name: str | None = None) -> str:
    if not code:
        return "—"
    if code == "RB":
        return "Regulation Bureau"
    if code == "EC":
        return "Executive Committee"
    if code == "HEAD":
        return "Senior management"
    if code == "QUEUE":
        return "Queue until committees start"
    k, _, v = code.partition(":")
    if k == "RO":
        return f"Regional Office, {v} ({settings.get()['regions'].get(v, '')})"
    if k == "COMMITTEE":
        return settings.stage(v)["label"]
    if k == "INST":
        return inst_name or "Institution"
    return code


# ------------------------------------------------------------------------------------ records

def event(app_id: str | None, on: date, kind: str, actor: str, role: str, text: str, extra: dict | None = None,
          item_id: str | None = None) -> None:
    ts = clock.stamp(on)
    db.insert("events", {"app_id": app_id, "item_id": item_id, "on_date": iso(on), "ts": ts, "kind": kind,
                         "actor": actor, "text": text, "extra": extra or {}})
    audit.log(actor, role, f"{'application' if app_id else 'compliance'}.{kind}", app_id or item_id or "",
              {"text": text, **(extra or {})}, ts=ts)


def hold(ref: str, holder: str | None, on: date) -> None:
    with db.tx() as c:
        c.execute("UPDATE holds SET to_on=? WHERE ref=? AND to_on IS NULL", (iso(on), ref))
        if holder:
            c.execute("INSERT INTO holds (ref, holder, from_on) VALUES (?,?,?)", (ref, holder, iso(on)))


def queue_until(a: dict | None) -> date | None:
    """Committees for an application cannot be fixed before its window's start date: that wait is no office's delay."""
    if not a or settings.nature(a["nature"])["route"][0] not in COMMITTEES:
        return None
    return d(window_of(a["nature"], a["region"]).get("scrutiny_from"))


def split_holds(holds: list[dict], on: date, queue: date | None) -> dict:
    out = {"institution": 0, "aicte": 0, "by": {}}
    for r in holds:
        f, t = d(r["from_on"]), d(r["to_on"]) or on
        parts = [(r["holder"], f, t)]
        if queue and f < queue and (r["holder"] == "RB" or r["holder"].startswith("RO:")):
            parts = [("QUEUE", f, min(queue, t)), (r["holder"], min(queue, t), t)]
        for h, x, y in parts:
            n = max(0, (y - x).days)
            if n:
                out[holder_kind(h)] += n
                out["by"][h] = out["by"].get(h, 0) + n
    return out


def time_split(ref: str, on: date) -> dict:
    """Days the ball was with the institution and with AICTE (offices, committees, Executive Committee)."""
    a = db.q1("SELECT nature, region FROM applications WHERE id=?", (ref,))
    return split_holds(db.q("SELECT holder, from_on, to_on FROM holds WHERE ref=? ORDER BY id", (ref,)), on, queue_until(a))


def app(app_id: str) -> dict:
    a = db.q1("SELECT * FROM applications WHERE id=?", (app_id,))
    if not a:
        raise WorkflowError("No such application")
    return a


def current_step(a: dict) -> dict | None:
    if not a.get("step_id"):
        return None
    s = db.q1("SELECT * FROM steps WHERE id=?", (a["step_id"],))
    return s if s and not s["closed_on"] else None


def detail(a: dict) -> dict:
    return db.unj(a.get("detail"), {}) or {}


def _set_app(a: dict, **f) -> None:
    db.update("applications", "id", a["id"], f)
    a.update(f)


# ------------------------------------------------------------------------------------ Executive Committee dates

def ec_meetings() -> list[date]:
    return sorted(d(x) for x in settings.get()["cycle"].get("ec_meetings") or [])


def next_ec(on: date) -> date | None:
    return next((m for m in ec_meetings() if m >= on), None)


def last_ec_by(t: date) -> date | None:
    ms = [m for m in ec_meetings() if m <= t]
    return ms[-1] if ms else None


def deadline(appeal_track: bool) -> date:
    c = settings.get()["cycle"]
    return d(c["last_date_after_appeal"] if appeal_track else c["last_date_approval"])


# ------------------------------------------------------------------------------------ opening steps

def window_of(nature: str, region: str) -> dict:
    ws = settings.get()["cycle"]["windows"]
    if nature == "new_institution":
        return next((w for w in ws if w.get("new")), ws[-1])
    return next((w for w in ws if region in (w.get("regions") or [])), ws[0])


def _phase_for(a: dict, stage: str, on: date) -> tuple[str, str, date]:
    cfg = settings.stage(stage)
    if stage in COMMITTEES:
        holder = "RB" if cfg.get("schedule_by") == "RB" else ro_code(a["region"])
        start = max(on, d(window_of(a["nature"], a["region"]).get("scrutiny_from")) or on)
        return "to_schedule", holder, start + timedelta(days=cfg.get("schedule_days", 5))
    if stage in ("compliance", "appeal"):
        return ("with_institution" if stage == "compliance" else "window"), inst_code(a["pid"]), on + timedelta(days=cfg["days"])
    if stage == "self_disclosure":
        return "review", "RB", on + timedelta(days=cfg["days"])
    if stage == "ec":
        prep = settings.get()["cycle"].get("ec_prep_days", 3)
        return "pending", "EC", next_ec(on + timedelta(days=prep)) or on + timedelta(days=cfg["days"])
    return "pending", "EC", on + timedelta(days=cfg["days"])   # council


def open_step(a: dict, stage: str, on: date, actor: str = "system", role: str = "system", text: str | None = None,
              extra: dict | None = None) -> dict:
    cfg = settings.stage(stage)
    attempt = 1 + db.q1("SELECT COUNT(*) AS n FROM steps WHERE app_id=? AND stage=?", (a["id"], stage))["n"]
    phase, holder, due = _phase_for(a, stage, on)
    sid = db.insert("steps", {"app_id": a["id"], "stage": stage, "attempt": attempt, "opened_on": iso(on), "phase": phase,
                              "holder": holder, "due_on": iso(due), "extra": extra or {}})
    _set_app(a, stage=stage, phase=phase, holder=holder, step_id=sid, esc_level=-1)
    hold(a["id"], holder, on)
    event(a["id"], on, "moved", actor, role, text or f"Moved to {cfg['label']}" + (f" (round {attempt})" if attempt > 1 else ""),
          {"stage": stage})
    return db.q1("SELECT * FROM steps WHERE id=?", (sid,))


def _close(step: dict, on: date, outcome: str, actor: str, remarks: str = "", deficiencies: list | None = None) -> None:
    db.update("steps", "id", step["id"], {"closed_on": iso(on), "outcome": outcome, "actor": actor, "remarks": remarks,
                                          "deficiencies": deficiencies or []})


def create_application(pid: str, nature: str, on: date, region: str, officer: str | None = None, detail_: dict | None = None,
                       app_id: str | None = None, carried: list | None = None, actor: str = "system", role: str = "system") -> dict:
    n = settings.nature(nature)
    if not app_id:
        k = db.q1("SELECT COUNT(*) AS n FROM applications")["n"] + 1
        app_id = f"AP{settings.get()['cycle']['ay'][2:4]}-{k:04d}"
    a = {"id": app_id, "pid": pid, "ay": settings.get()["cycle"]["ay"], "nature": nature, "submitted_on": iso(on),
         "region": region, "status": "in_process", "officer": officer, "deficiencies": [], "carried": carried or [],
         "detail": detail_ or {}, "source": "test"}
    db.insert("applications", a)
    a = app(app_id)
    event(app_id, on, "submitted", actor, role, f"Application submitted: {n['label']}", {"nature": nature})
    if carried:
        event(app_id, on, "carried", "system", "system",
              f"{len(carried)} open condition(s) of the previous approval carried into this application; they must be met before the next EoA (Cl. 2.25 c)",
              {"items": [c["item_id"] for c in carried]})
    open_step(a, n["route"][0], on)
    return app(app_id)


# ------------------------------------------------------------------------------------ routing

def _main(a: dict) -> list[str]:
    return list(settings.nature(a["nature"])["route"]) + ["ec"]


def _aa(a: dict) -> list[str]:
    return list(settings.nature(a["nature"]).get("aa") or [])


def _after_scrutiny(a: dict) -> list[str]:
    main = _main(a)
    pos = "scrutiny" if "scrutiny" in main else "self_disclosure"
    return main[main.index(pos) + 1:]


def next_stage(a: dict, stage: str, result: str) -> str:
    aa = _aa(a)
    if stage == "self_disclosure":
        return "ec" if result == "in_order" else "compliance"
    if stage == "scrutiny":
        return _after_scrutiny(a)[0] if result == "in_order" else "compliance"
    if stage == "re_scrutiny":
        if result == "in_order":
            return _after_scrutiny(a)[0]
        return "shc" if "shc" in aa else "ec"
    if stage == "evc":
        if detail(a).get("appeal"):
            return "sac"
        if result == "in_order":
            return "ec"
        return "shc" if "shc" in aa else "ec"
    if stage == "shc":
        return "ec"
    if stage == "sac":
        return "evc" if result == "fresh_evc" else "council"
    raise WorkflowError(f"No route after {stage}")


def remaining_after(a: dict, stage: str) -> list[str]:
    """Stages still to come after `stage` if every outcome from here is in order."""
    if stage in ("ec", "council"):
        return []
    if stage == "appeal":
        return ["sac", "council"]
    if stage == "sac":
        return ["council"]
    if stage == "evc" and detail(a).get("appeal"):
        return ["sac", "council"]
    if stage in ("evc", "shc", "self_disclosure"):
        return ["ec"]
    return _after_scrutiny(a)


def remaining_path(a: dict, step: dict) -> list[str]:
    if step["stage"] == "compliance":
        ret = (db.unj(step.get("extra"), {}) or {}).get("return_to") or "re_scrutiny"
        return [ret] + remaining_after(a, ret)
    return remaining_after(a, step["stage"])


def appeal_allowed(a: dict) -> bool:
    return "sac" in _aa(a)


def allowed_reverts(a: dict, step: dict) -> list[str]:
    """Stages an application can be sent back to: committees it has already been through, or the institution."""
    if step["stage"] in ("appeal", "council"):
        return []
    seen = {r["stage"] for r in db.q("SELECT DISTINCT stage FROM steps WHERE app_id=? AND closed_on IS NOT NULL", (a["id"],))}
    if seen & {"scrutiny", "self_disclosure"}:
        seen.add("re_scrutiny")   # a fresh check of the points in question
    out = [s for s in ("self_disclosure", "scrutiny", "re_scrutiny", "evc") if s in seen and s != step["stage"]]
    if step["stage"] != "compliance":
        out.append("compliance")
    return out


# ------------------------------------------------------------------------------------ actions

def _require(step: dict | None, stages: tuple, phases: tuple | None = None) -> dict:
    if not step:
        raise WorkflowError("This application is not waiting on any step")
    if step["stage"] not in stages or (phases and step["phase"] not in phases):
        raise WorkflowError(f"Not possible now: the application is at '{settings.stage(step['stage'])['label']}' ({step['phase']})")
    return step


COMPOSITION = {
    "scrutiny": ["Professor (Government / central institution)", "Advocate", "Architect / structural engineer"],
    "re_scrutiny": ["Professor (Government / central institution)", "Advocate", "Architect / structural engineer"],
    "evc": ["Professor", "Associate Professor / industry expert", "Architect"],
    "shc": ["Chairperson (retired judge / Vice-Chancellor)", "Associate Professor", "Revenue / land expert"],
    "sac": ["Chairperson (retired judge / Vice-Chancellor)", "Associate Professor", "Revenue / land expert"],
}
EXPERTS = ["R. Iyer", "M. Banerjee", "S. Qureshi", "K. Raghavan", "P. Deshpande", "A. Chatterjee", "V. Nambiar", "L. Mathur",
           "G. Sethi", "H. Kaur", "D. Pillai", "N. Bhattacharya", "T. Rangan", "J. D'Souza", "B. Hegde", "C. Thakur"]


def pick_members(a: dict, stage: str, attempt: int) -> list[dict]:
    """Stand-in for the portal's automated selection of committee members (Cl. 1.8 a, 1.9 a)."""
    h = int(hashlib.sha256(f"{a['id']}:{stage}:{attempt}".encode()).hexdigest(), 16)
    out = []
    for i, role in enumerate(COMPOSITION[stage]):
        out.append({"name": ("Prof. " if i < 2 else "") + EXPERTS[(h >> (i * 8)) % len(EXPERTS)], "role": role})
    return out


def schedule(app_id: str, on: date, meeting_on: date, mode: str, actor: str, role: str) -> dict:
    a = app(app_id)
    step = _require(current_step(a), COMMITTEES, ("to_schedule", "scheduled", "awaiting_video"))
    cfg = settings.stage(step["stage"])
    if meeting_on < on:
        raise WorkflowError("The meeting date cannot be in the past")
    resched = step["phase"] != "to_schedule"
    members = db.unj(step.get("members")) or pick_members(a, step["stage"], step["attempt"])
    if step["stage"] == "evc" and mode == "online" and not (db.unj(step.get("extra"), {}) or {}).get("video"):
        phase, holder = "awaiting_video", inst_code(a["pid"])
        due = max(on + timedelta(days=1), meeting_on - timedelta(days=cfg.get("video_before", 2)))
    else:
        phase, holder, due = "scheduled", f"COMMITTEE:{step['stage']}", meeting_on + timedelta(days=cfg.get("report", 2))
    db.update("steps", "id", step["id"], {"phase": phase, "holder": holder, "due_on": iso(due), "meeting_on": iso(meeting_on),
                                          "mode": mode, "members": members, "esc_level": -1})
    _set_app(a, phase=phase, holder=holder, esc_level=-1)
    hold(a["id"], holder, on)
    what = f"{cfg['label']} {'re-fixed' if resched else 'fixed'} for {meeting_on:%d %b %Y} ({mode})"
    event(app_id, on, "scheduled", actor, role, what, {"meeting_on": iso(meeting_on), "mode": mode})
    tail = f" Upload a video of all facilities (at least 30 minutes) and share the link by {due:%d %b %Y} (Cl. 1.9 f)." \
        if phase == "awaiting_video" else " Two authorised representatives must attend with original documents."
    notify.send(f"{step['id']}:intimation:{iso(meeting_on)}", on, inst_code(a["pid"]), "notice", what + "." + tail,
                app_id=app_id, pid=a["pid"])
    return app(app_id)


def video_uploaded(app_id: str, on: date, link: str, actor: str, role: str) -> dict:
    a = app(app_id)
    step = _require(current_step(a), ("evc",), ("awaiting_video",))
    cfg = settings.stage("evc")
    ex = db.unj(step.get("extra"), {}) or {}
    ex["video"] = {"link": link, "on": iso(on)}
    m = d(step["meeting_on"])
    if m < on:   # too late for the date fixed: the Regional Office fixes a new one
        phase, holder, due = "to_schedule", ro_code(a["region"]), on + timedelta(days=3)
        text = f"Facilities video uploaded after the EVC date ({m:%d %b}); a new date is to be fixed"
    else:
        phase, holder, due = "scheduled", "COMMITTEE:evc", m + timedelta(days=cfg.get("report", 2))
        text = "Facilities video uploaded for the online EVC"
    db.update("steps", "id", step["id"], {"phase": phase, "holder": holder, "due_on": iso(due), "extra": ex, "esc_level": -1})
    _set_app(a, phase=phase, holder=holder, esc_level=-1)
    hold(a["id"], holder, on)
    event(app_id, on, "video", actor, role, text, {"link": link})
    return app(app_id)


def record_outcome(app_id: str, on: date, result: str, deficiencies: list[str], remarks: str, actor: str, role: str) -> dict:
    a = app(app_id)
    step = _require(current_step(a), COMMITTEES + ("self_disclosure",))
    if step["stage"] in COMMITTEES and step["phase"] == "to_schedule":
        raise WorkflowError("The meeting has not been fixed yet")
    allowed = ("recommend", "not_recommend", "fresh_evc") if step["stage"] == "sac" else ("in_order", "deficient")
    if result not in allowed:
        raise WorkflowError(f"Outcome must be one of {', '.join(allowed)}")
    defs = [x.strip() for x in deficiencies if x and x.strip()]
    if result == "deficient" and not defs:
        raise WorkflowError("List the deficiencies found")
    _close(step, on, result, actor, remarks, defs)
    label = settings.stage(step["stage"])["label"]
    if step["stage"] in ("re_scrutiny", "shc") and result == "in_order":
        open_defs = []
    elif result == "deficient":
        open_defs = defs
    else:
        open_defs = db.unj(a.get("deficiencies"), []) or []
    _set_app(a, deficiencies=open_defs)
    event(app_id, on, "outcome", actor, role, f"{label}: {OUTCOME[result].lower()}" + (f" ({len(defs)}: {'; '.join(defs)})" if defs else "")
          + (f". {remarks}" if remarks else ""), {"stage": step["stage"], "result": result, "deficiencies": defs})
    if result == "deficient":
        notify.send(f"{step['id']}:deficiency", on, inst_code(a["pid"]), "notice",
                    f"Deficiencies noted by the {label} on {on:%d %b %Y}: {'; '.join(defs)}.", app_id=app_id, pid=a["pid"])
    elif result == "in_order" and a.get("carried"):
        _close_carried(a, on, label, actor, role)
    nxt = next_stage(a, step["stage"], result)
    if nxt == "compliance":
        open_step(a, "compliance", on, extra={"return_to": "re_scrutiny", "raised_by": step["stage"]})
    else:
        open_step(a, nxt, on)
    return app(app_id)


def _close_carried(a: dict, on: date, label: str, actor: str, role: str) -> None:
    """Conditions carried from the previous approval are closed once a committee finds the application in order."""
    for c in db.unj(a.get("carried"), []) or []:
        it = db.q1("SELECT * FROM items WHERE id=?", (c["item_id"],))
        if not it or it["status"] not in ("open", "submitted", "rejected"):
            continue
        db.update("items", "id", it["id"], {"status": "verified", "holder": None, "closed_on": iso(on), "closed_by": actor, "esc_level": -1})
        hold(it["id"], None, on)
        event(None, on, "verified", actor, role, f"Found complied by the {label} while processing {a['id']}", item_id=it["id"])


def submit_compliance(app_id: str, on: date, note: str, actor: str, role: str, files: list | None = None) -> dict:
    a = app(app_id)
    step = _require(current_step(a), ("compliance",))
    _close(step, on, "submitted", actor, note)
    event(app_id, on, "compliance", actor, role, "Compliance submitted" + (f": {note}" if note else ""), {"files": files or []})
    ret = (db.unj(step.get("extra"), {}) or {}).get("return_to") or "re_scrutiny"
    open_step(a, ret, on)
    return app(app_id)


def decide(app_id: str, on: date, decision: str, remarks: str, actor: str, role: str, conditions: list | None = None) -> dict:
    """Decision of the Executive Committee (or Council after appeal). Only an authorised person calls this."""
    from . import compliance
    a = app(app_id)
    step = _require(current_step(a), ("ec", "council"))
    if decision not in ("approve", "lod", "reject"):
        raise WorkflowError("Decision must be approve, lod or reject")
    _close(step, on, decision, actor, remarks)
    who = "Executive Committee" if step["stage"] == "ec" else "Council"
    event(app_id, on, "decision", actor, role, f"{who}: {OUTCOME[decision].lower()}" + (f". {remarks}" if remarks else ""),
          {"decision": decision, "conditions": [c.get("key") for c in conditions or []]})
    if decision == "approve":
        _set_app(a, status="approved", decided_on=iso(on), decision=decision, phase=None, holder=None)
        hold(a["id"], None, on)
        compliance.attach_conditions(a, on, conditions or [], actor, role)
        if settings.nature(a["nature"]).get("deposit"):
            compliance.create_deposit(a, on, actor, role)
        notify.send(f"{a['id']}:decision", on, inst_code(a["pid"]), "notice",
                    f"{who}: approval granted for {settings.nature(a['nature'])['label']}"
                    + (f", subject to {len(conditions)} condition(s)" if conditions else "") + ".", app_id=app_id, pid=a["pid"])
        return app(app_id)
    status = "lod" if decision == "lod" else "rejected"
    _set_app(a, status=status, decided_on=iso(on), decision=decision)
    if step["stage"] == "ec" and appeal_allowed(a):
        open_step(a, "appeal", on, text="Appeal window opened (7 days)")
        notify.send(f"{a['id']}:decision", on, inst_code(a["pid"]), "notice",
                    f"{who}: {OUTCOME[decision]}. You may appeal once within 7 days (Cl. 2.24 a).", app_id=app_id, pid=a["pid"])
    else:
        _set_app(a, phase=None, holder=None)
        hold(a["id"], None, on)
        notify.send(f"{a['id']}:decision", on, inst_code(a["pid"]), "notice", f"{who}: {OUTCOME[decision]}.", app_id=app_id, pid=a["pid"])
    return app(app_id)


def file_appeal(app_id: str, on: date, grounds: str, actor: str, role: str) -> dict:
    a = app(app_id)
    step = _require(current_step(a), ("appeal",))
    _close(step, on, "appealed", actor, grounds)
    dt = detail(a)
    dt["appeal"] = True
    _set_app(a, status="in_process", detail=dt)
    event(app_id, on, "appeal", actor, role, "Appeal filed" + (f": {grounds}" if grounds else ""))
    open_step(a, "sac", on)
    return app(app_id)


def lapse_appeal(a: dict, step: dict, on: date) -> None:
    _close(step, on, "lapsed", "system")
    _set_app(a, phase=None, holder=None)
    hold(a["id"], None, on)
    event(a["id"], on, "lapsed", "system", "system", "No appeal filed within 7 days; the decision stands")


def revert(app_id: str, on: date, to: str, reason: str, actor: str, role: str) -> dict:
    a = app(app_id)
    step = current_step(a)
    if not step:
        raise WorkflowError("This application is not waiting on any step")
    if to not in allowed_reverts(a, step):
        raise WorkflowError("It cannot be sent back to that stage")
    if len((reason or "").strip()) < 10:
        raise WorkflowError("Record the reason (at least a sentence)")
    _close(step, on, "reverted", actor, reason)
    frm = settings.stage(step["stage"])["label"]
    if to == "compliance":
        open_step(a, "compliance", on, actor, role, f"Returned to the institution for clarification (from {frm})",
                  extra={"return_to": step["stage"], "raised_by": step["stage"], "clarification": reason})
        notify.send(f"{step['id']}:clarification", on, inst_code(a["pid"]), "notice", f"Clarification sought by the {frm}: {reason}",
                    app_id=app_id, pid=a["pid"])
    else:
        open_step(a, to, on, actor, role, f"Sent back from {frm} to {settings.stage(to)['label']}")
    event(app_id, on, "reverted", actor, role, f"Reason recorded: {reason}", {"from": step["stage"], "to": to})
    return app(app_id)


def add_note(app_id: str, on: date, text: str, actor: str, role: str) -> None:
    app(app_id)
    if not text.strip():
        raise WorkflowError("Write the note")
    event(app_id, on, "note", actor, role, text.strip())


# ------------------------------------------------------------------------------------ countdown

def _dur(stage: str, fast: bool) -> int:
    cfg = settings.stage(stage)
    if fast and stage in COMMITTEES:
        return cfg.get("lead", 7) + cfg.get("report", 2)
    return cfg["days"]


def latest_finish(path: list[str], D: date, fast: bool = False) -> date:
    """Latest date the current step may finish so that the rest of the path is still decided by D."""
    t = D
    prep = settings.get()["cycle"].get("ec_prep_days", 3)
    for s in reversed(path):
        if s == "ec":
            t = (last_ec_by(t) or t) - timedelta(days=prep)
        elif s == "council":
            t = t - timedelta(days=prep if fast else settings.stage(s)["days"])
        else:
            t = t - timedelta(days=_dur(s, fast))
    return t


def expected_finish(step: dict, on: date) -> date:
    stage, phase = step["stage"], step["phase"]
    cfg = settings.stage(stage)
    due = d(step["due_on"])
    if stage in COMMITTEES:
        m = d(step["meeting_on"])
        if phase == "to_schedule" or (phase == "awaiting_video" and m < on):
            return on + timedelta(days=cfg.get("lead", 7) + cfg.get("report", 2))
        return max(on, m + timedelta(days=cfg.get("report", 2)))
    if stage == "ec":
        return next_ec(on) or max(on, due)
    return max(on, due)


def round_extra(a: dict, step: dict) -> int:
    """Extra days one more round of deficiencies would add from here."""
    aa = _aa(a)
    stage = step["stage"]
    if stage == "compliance":
        stage = (db.unj(step.get("extra"), {}) or {}).get("return_to") or "re_scrutiny"
    if stage in ("self_disclosure", "scrutiny"):
        return settings.stage("compliance")["days"] + settings.stage("re_scrutiny")["days"]
    if stage in ("re_scrutiny", "evc"):
        return settings.stage("shc")["days"] if "shc" in aa else 0
    return 0


def countdown(a: dict, step: dict | None, on: date) -> dict | None:
    if not step or step.get("closed_on"):
        return None
    appeal_track = step["stage"] in ("appeal", "sac", "council") or bool(detail(a).get("appeal"))
    D = deadline(appeal_track)
    path = remaining_path(a, step)
    lsf, lsf_fast = latest_finish(path, D), latest_finish(path, D, fast=True)
    ef = expected_finish(step, on)
    spare, spare_fast = (lsf - ef).days, (lsf_fast - ef).days
    extra = round_extra(a, step)
    spare_pess = spare - extra
    risk = "will_miss" if spare_fast < 0 else "fast_track" if spare < 0 else "at_risk" if spare_pess < 0 else "on_track"
    cfg = settings.stage(step["stage"])
    # expected dates of the remaining path at the usual pace, for the timeline on the application page
    segs = [{"stage": step["stage"], "label": cfg["short"], "from": iso(on), "to": iso(ef), "current": True}]
    t = ef
    prep = settings.get()["cycle"].get("ec_prep_days", 3)
    for s in path:
        end = (next_ec(t + timedelta(days=prep)) or t + timedelta(days=settings.stage(s)["days"])) if s == "ec" else t + timedelta(days=settings.stage(s)["days"])
        segs.append({"stage": s, "label": settings.stage(s)["short"], "from": iso(t), "to": iso(end)})
        t = end
    out = {"deadline": iso(D), "deadline_kind": "after appeal" if appeal_track else "approval", "path": path, "segments": segs,
           "decided_by": iso(t),
           "finish_by": iso(lsf), "finish_by_fast": iso(lsf_fast), "expected_finish": iso(ef), "spare": spare,
           "spare_fast": spare_fast, "spare_pess": spare_pess, "extra": extra, "risk": risk, "risk_label": RISK[risk]}
    if step["stage"] in COMMITTEES:
        hold_by = (lsf_fast if risk == "fast_track" else lsf) - timedelta(days=cfg.get("report", 2))
        out["hold_by"] = iso(hold_by)
        if step["phase"] == "to_schedule":
            out["schedule_by"] = iso(hold_by - timedelta(days=cfg.get("lead", 7)))
    out["why"] = _why(out, cfg, D)
    return out


def _why(c: dict, cfg: dict, D: date) -> str:
    when = f"{D:%d %b}"
    if c["risk"] == "on_track":
        return f"{c['spare']} spare days before {when}. Even one more round of deficiencies would leave {c['spare_pess']}."
    if c["risk"] == "at_risk":
        return (f"{c['spare']} spare days before {when}, but one more round of deficiencies (about {c['extra']} days) "
                f"would push the decision past {when}.")
    if c["risk"] == "fast_track":
        return (f"At the usual pace the decision would come {-c['spare']} days after {when}. Holding each remaining "
                f"committee at the minimum notice still makes it, with {c['spare_fast']} days to spare.")
    return f"Even at the fastest possible pace the decision would come {-c['spare_fast']} days after {when}."


def refresh(a: dict, on: date) -> dict | None:
    """Recompute and store the countdown (used by lists and reports)."""
    cd = countdown(a, current_step(a), on)
    _set_app(a, risk=cd["risk"] if cd else None, spare=cd["spare"] if cd else None)
    return cd


# ------------------------------------------------------------------------------------ what each phase asks for

def task_text(step: dict) -> str:
    st, ph = step["stage"], step["phase"]
    label = settings.stage(st)["label"]
    if st in COMMITTEES:
        return {"to_schedule": f"Fix the date of the {label}", "awaiting_video": "Upload the facilities video (30 minutes) for the online EVC",
                "scheduled": f"Hold the {label} and record the outcome"}.get(ph, label)
    return {"self_disclosure": "Complete the self-disclosure check", "compliance": "Submit compliance of the deficiencies",
            "ec": "Place before the Executive Committee and record the decision", "appeal": "Appeal window (file an appeal, if any)",
            "council": "Record the Council's decision"}.get(st, label)
