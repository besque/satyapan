"""The daily check: reminders, overdue notices and escalations for every open step and compliance item.

Runs once per day (and for every day the demo clock is moved forward). Each message has a unique key, so
running the check twice never sends anything twice.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import compliance, db, engine, notify, settings
from .clock import add_months, d, iso
from .engine import holder_kind, inst_code

RANK = {"on_track": 0, "at_risk": 1, "fast_track": 2, "will_miss": 3}


def n_days(n: int) -> str:
    return f"{n} day{'' if n == 1 else 's'}"


def _inst_names() -> dict:
    return {r["pid"]: r["name"] for r in db.q("SELECT pid, name FROM institutions")}


def _escalation_target(holder: str, level: int, region: str | None = None) -> str:
    if level >= 3:
        return "HEAD"
    if holder.startswith("COMMITTEE:") and level >= 2:   # a late committee goes to the office that convenes it
        st = holder.split(":", 1)[1]
        return "RB" if settings.stage(st).get("schedule_by") == "RB" else engine.ro_code(region or "Central")
    return holder


def _ladder_level(over: int, spare: int | None, current: int) -> int:
    level = -1
    for step in settings.get()["alerts"]["aicte"]["ladder"]:
        hit = over >= step["after"] or (spare is not None and step.get("spare_below") is not None and spare < step["spare_below"])
        if hit:
            level = step["level"]
    return max(level, current if current is not None else -1)


def _ladder_label(level: int) -> str:
    return next((s["label"] for s in settings.get()["alerts"]["aicte"]["ladder"] if s["level"] == level), "Overdue")


def sweep(on: date) -> dict:
    s = settings.get()
    A = s["alerts"]
    names = _inst_names()
    sent = 0
    rows = db.q("SELECT a.*, s.id AS sid, s.stage AS s_stage, s.phase AS s_phase, s.holder AS s_holder, s.due_on AS s_due, "
                "s.esc_level AS s_esc, s.opened_on AS s_opened FROM applications a JOIN steps s ON s.id=a.step_id "
                "WHERE s.closed_on IS NULL AND a.source='test'")
    for r in rows:
        a = {k: v for k, v in r.items() if not k.startswith("s_") and k != "sid"}
        step = db.q1("SELECT * FROM steps WHERE id=?", (r["sid"],))
        name = names.get(a["pid"], a["pid"])
        task = engine.task_text(step)
        due = d(step["due_on"])
        holder = step["holder"]
        if step["stage"] == "appeal" and on > due:
            engine.lapse_appeal(a, step, on)
            continue
        cd = engine.countdown(a, step, on)
        prev_risk = a.get("risk")
        if (cd["risk"] if cd else None) != prev_risk:
            db.update("applications", "id", a["id"], {"risk": cd["risk"] if cd else None})
        ref = f"{a['id']} {name}"
        if holder_kind(holder) == "institution":
            left = (due - on).days
            if left in A["institution"]["remind_before"]:
                sent += notify.send(f"{step['id']}:remind:{left}", on, holder, "reminder",
                                    f"Reminder: {task} by {due:%d %b %Y}" + (" (today)" if left == 0 else f" ({left} days left)") + f". Application {a['id']}.",
                                    app_id=a["id"], pid=a["pid"])
            over = -left
            if over in A["institution"]["overdue_notice_after"]:
                sent += notify.send(f"{step['id']}:overdue:{over}", on, holder, "overdue",
                                    f"Overdue by {n_days(over)}: {task} (was due {due:%d %b %Y}). Application {a['id']}.",
                                    level=1, app_id=a["id"], pid=a["pid"])
            if over == A["institution"]["tell_officer_after"]:
                sent += notify.send(f"{step['id']}:officer", on, "RB", "info",
                                    f"{name} is {n_days(over)} late: {task[0].lower() + task[1:]}. Decide the next step: wait, issue a final notice, "
                                    f"or proceed on the record. ({a['id']})", app_id=a["id"], pid=a["pid"])
        else:
            left = (due - on).days
            if left == A["aicte"]["due_soon_days"]:
                sent += notify.send(f"{step['id']}:due_soon", on, holder, "due_soon", f"Due in {left} days: {task} for {ref}.", app_id=a["id"], pid=a["pid"])
            over = (on - due).days
            level = _ladder_level(over, cd["spare"] if cd else None, step["esc_level"])
            if level > step["esc_level"]:
                for lv in range(max(step["esc_level"], 0) + 1 if step["esc_level"] >= 0 else 1, level + 1):
                    if lv == 1 and over < 1:     # raised by the calendar, not by lateness: no "overdue" notice
                        continue
                    why = f"{task}: overdue by {n_days(over)}" if over >= 1 else f"{task}: {cd['risk_label'].lower()} ({cd['why']})"
                    to = _escalation_target(holder, lv, a["region"])
                    sent += notify.send(f"{step['id']}:esc:{lv}", on, to, "escalated" if lv >= 2 else "overdue",
                                        f"{_ladder_label(lv)}: {why}. {ref}, held by {engine.holder_label(holder)}.", level=lv,
                                        app_id=a["id"], pid=a["pid"])
                    if lv >= 2:
                        engine.event(a["id"], on, "escalated", "system", "system",
                                     f"{_ladder_label(lv)}{f' ({engine.holder_label(to)})' if lv == 2 else ''}: {why}")
                db.update("steps", "id", step["id"], {"esc_level": level})
                db.update("applications", "id", a["id"], {"esc_level": level})
        if cd and RANK[cd["risk"]] > RANK.get(prev_risk or "on_track", 0) and cd["risk"] != "on_track":
            sent += notify.send(f"{a['id']}:risk:{cd['risk']}", on, holder if holder_kind(holder) == "aicte" else "RB", "at_risk",
                                f"{cd['risk_label']}: {ref}. {cd['why']}", level=1 if cd["risk"] == "at_risk" else 2, app_id=a["id"], pid=a["pid"])
    compliance.ensure_document_items(on)
    compliance.ensure_lease_items(on)
    sent += _compliance(on, names)
    return {"date": iso(on), "sent": sent}


def _compliance(on: date, names: dict) -> int:
    A = settings.get()["alerts"]
    sent = 0
    for it in db.q("SELECT * FROM items WHERE source='test' AND status IN ('open','submitted','rejected')"):
        name = names.get(it["pid"], it["pid"])
        ex = db.unj(it["extra"], {}) or {}
        inst = inst_code(it["pid"])
        if it["status"] == "submitted":   # with an officer for verification
            vdue = d(ex.get("verify_due"))
            if vdue:
                over = (on - vdue).days
                level = _ladder_level(over, None, it["esc_level"]) if over >= 0 else -1
                if level > it["esc_level"]:
                    for lv in range(max(it["esc_level"], 0) + 1 if it["esc_level"] >= 0 else 1, level + 1):
                        sent += notify.send(f"{it['id']}:verify:{lv}", on, _escalation_target(it["holder"], lv), "escalated" if lv >= 2 else "overdue",
                                            f"{_ladder_label(lv)}: verify '{it['title']}' submitted by {name} on {d(it['submitted_on']):%d %b %Y}.",
                                            level=lv, item_id=it["id"], pid=it["pid"])
                    db.update("items", "id", it["id"], {"esc_level": level})
            continue
        due = d(it["due_on"])
        if not due:
            continue
        left = (due - on).days
        if it["kind"] == "lease":
            for m in A["lease"]["remind_before_months"]:
                if add_months(due, -m) == on:
                    sent += notify.send(f"{it['id']}:lease:{m}", on, inst, "reminder",
                                        f"{it['consequence']}. Submit the extended lease by {due:%d %b %Y} ({m} months left).", item_id=it["id"], pid=it["pid"])
                    sent += notify.send(f"{it['id']}:lease_ro:{m}", on, compliance.verifier(it), "info",
                                        f"{name}: {it['consequence'][0].lower() + it['consequence'][1:]}; lease extension due {due:%d %b %Y}.",
                                        item_id=it["id"], pid=it["pid"])
        if it["kind"] == "deposit":
            if left in (7, 3, 0):
                sent += notify.send(f"{it['id']}:remind:{left}", on, inst, "reminder",
                                    f"Reminder: {it['title']} due by {due:%d %b %Y}" + (" (today)." if left == 0 else f" ({left} days left)."), item_id=it["id"], pid=it["pid"])
            st = compliance.deposit_state(it, on)
            if st["stage"] != "due":
                lv = 3 if st["stage"] == "withdraw" else 1 if st["penalty"] == 10 else 2
                if lv > it["esc_level"]:
                    sent += notify.send(f"{it['id']}:deposit:{st['stage']}", on, inst, "overdue", f"Security deposit not received: {st['label']}.",
                                        level=lv, item_id=it["id"], pid=it["pid"])
                    sent += notify.send(f"{it['id']}:deposit_rb:{st['stage']}", on, "HEAD" if lv >= 3 else "RB", "escalated" if lv >= 2 else "overdue",
                                        f"{name}: security deposit not received. {st['label']}.", level=lv, item_id=it["id"], pid=it["pid"])
                    db.update("items", "id", it["id"], {"esc_level": lv})
                    if lv >= 3:
                        engine.event(None, on, "escalated", "system", "system", f"Referred to the competent authority: {st['label']}", item_id=it["id"])
            continue
        cfg = A["documents"] if it["kind"] in ("document", "lease") else A["undertakings"]
        if left in cfg["remind_before"] and it["kind"] != "lease":
            what = "valid until" if it["kind"] == "document" else "due"
            sent += notify.send(f"{it['id']}:remind:{left}", on, inst, "reminder",
                                f"Reminder: {it['title']} ({what} {due:%d %b %Y}" + (", today)." if left == 0 else f", {left} days left)."), item_id=it["id"], pid=it["pid"])
        over = -left
        for lv, after in enumerate(cfg["escalate_after"], start=1):
            if over >= after and lv > it["esc_level"]:
                state = "expired" if it["kind"] == "document" else "not submitted" if it["kind"] == "lease" else "overdue"
                sent += notify.send(f"{it['id']}:over:{lv}", on, inst, state, f"{it['title']}: {state} since {due:%d %b %Y}. {it['consequence'].rstrip('.')}.",
                                    level=lv, item_id=it["id"], pid=it["pid"])
                sent += notify.send(f"{it['id']}:esc:{lv}", on, compliance.verifier(it), "escalated" if lv >= 2 else "overdue",
                                    f"{'Escalated to head of office' if lv >= 2 else 'Overdue'}: {it['title']} for {name}, {state} since {due:%d %b %Y}.",
                                    level=lv, item_id=it["id"], pid=it["pid"])
                db.update("items", "id", it["id"], {"esc_level": lv})
                if lv >= 2:
                    engine.event(None, on, "escalated", "system", "system", f"Escalated: {state} for {over} days", item_id=it["id"])
    return sent


def run_until(start: date, end: date) -> dict:
    """Run the daily check for every day from start to end (inclusive)."""
    total, day = 0, start
    while day <= end:
        total += sweep(day)["sent"]
        day += timedelta(days=1)
    return {"from": iso(start), "to": iso(end), "sent": total}
