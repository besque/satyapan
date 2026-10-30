"""Case workflow: what each action means, how it changes the case, and timelines / escalation."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from . import db, settings

# kind -> label, resulting status (None = unchanged), next action, days until next action is due
ACTIONS: dict[str, dict] = {
    "received":               {"label": "Received", "status": "pending"},
    "accepted":               {"label": "Taken up", "status": "under_process", "next": "Examine the complaint", "due": 7},
    "sought_reply":           {"label": "Reply sought from institution", "status": "under_process", "next": "Reply from institution", "due": "reply"},
    "reply_received":         {"label": "Institution replied", "status": "under_process", "next": "Examine the reply", "due": 7},
    "inquiry_ordered":        {"label": "Inquiry / visit ordered", "status": "under_process", "next": "Inquiry report", "due": 30},
    "show_cause":             {"label": "Show-cause notice issued", "status": "under_process", "next": "Reply to show-cause", "due": "reply"},
    "hearing":                {"label": "Hearing held", "status": "under_process", "next": "Decision after hearing", "due": 15},
    "penal_action":           {"label": "Penal action recommended", "status": "under_process", "next": "Order by competent authority", "due": 30},
    "eoa_processing":         {"label": "Approval application under process", "status": "under_process", "next": "Scrutiny / EVC", "due": 30},
    "recommended_approval":   {"label": "Approval recommended", "status": "under_process", "next": "Issue of letter", "due": 15},
    "transferred":            {"label": "Transferred", "status": "transferred", "next": "To be taken up by the receiving bureau", "due": 3},
    "note":                   {"label": "Note added"},
    "escalated":              {"label": "Escalated"},
    "linked":                 {"label": "Linked with another case"},
    "disposed_resolved":      {"label": "Disposed: resolved", "status": "disposed", "outcome": "Resolved"},
    "disposed_action_taken":  {"label": "Disposed: action taken", "status": "disposed", "outcome": "Action taken against institution"},
    "disposed_not_maintainable": {"label": "Disposed: not maintainable", "status": "disposed", "outcome": "Not maintainable / outside AICTE"},
    "disposed_merged":        {"label": "Disposed: merged with lead case", "status": "disposed", "outcome": "Merged with lead case"},
    "reopened":               {"label": "Reopened", "status": "under_process", "next": "Examine again", "due": 7},
}
# actions an officer can choose from the case page
OFFICER_ACTIONS = ["accepted", "sought_reply", "reply_received", "inquiry_ordered", "show_cause", "hearing", "penal_action",
                   "eoa_processing", "recommended_approval", "note", "disposed_resolved", "disposed_action_taken",
                   "disposed_not_maintainable", "disposed_merged", "reopened"]

STATUS = {"pending": "Pending", "under_process": "Under process", "transferred": "Transferred", "disposed": "Disposed"}


def now() -> datetime:
    return datetime.now(timezone.utc)


def today() -> date:
    return now().astimezone().date()


def d(s: str | None) -> date | None:
    return date.fromisoformat(s[:10]) if s else None


def due_for(category: str, received_on: str) -> str:
    return (d(received_on) + timedelta(days=int(settings.category(category)["days"]))).isoformat()


def timeline(c: dict, on: date | None = None) -> dict:
    """Where the case stands against its prescribed timeline."""
    on = on or today()
    rec, due = d(c["received_on"]), d(c["due_on"])
    end = d(c["disposed_on"]) if c["status"] == "disposed" else on
    total = max((due - rec).days, 1)
    used = (end - rec).days
    out = {"age": used, "total": total, "share": round(used / total, 2), "days_left": (due - end).days}
    if c["status"] == "disposed":
        out["state"] = "late" if used > total else "in_time"
        out["label"] = f"Disposed in {used} days" + (" (late)" if used > total else "")
        return out
    ladder = settings.get()["escalation"]
    step = None
    for s in ladder:
        if out["share"] >= s["at"]:
            step = s
    out["level"] = step["level"] if step else -1
    if not step:
        out["state"], out["label"] = "on_time", f"{out['days_left']} days left"
    elif step["level"] == 0:
        out["state"], out["label"] = "due_soon", f"Due in {out['days_left']} days"
    else:
        out["state"] = "overdue"
        out["label"] = "Due today" if out["days_left"] == 0 else f"Overdue by {-out['days_left']} day{'s' if out['days_left'] != -1 else ''}"
        out["escalation"] = step["label"]
    return out


def apply_action(case: dict, kind: str, ts: str, actor: str, remarks: str = "", to_bureau: str | None = None,
                 extra: dict | None = None) -> dict:
    """Record an action and update the case fields it affects. Returns the changed fields."""
    a = ACTIONS[kind]
    db.insert("actions", {"case_id": case["id"], "ts": ts, "kind": kind, "bureau": case["bureau"], "actor": actor,
                          "remarks": remarks, "to_bureau": to_bureau, "extra": extra or {}})
    f: dict = {}
    if kind not in ("note", "escalated", "linked"):
        f.update(last_action=a["label"] + (f" to {to_bureau}" if to_bureau else ""), last_action_on=ts)
    if a.get("status"):
        f["status"] = a["status"]
    if "next" in a:
        due = a["due"]
        days = settings.get()["institution_reply_days"] if due == "reply" else due
        f.update(next_action=a["next"], next_due=(d(ts) + timedelta(days=days)).isoformat())
    if a.get("status") == "disposed":
        f.update(disposed_on=ts[:10], outcome=a["outcome"], next_action=None, next_due=None)
    if kind == "reopened":
        f.update(disposed_on=None, outcome=None)
    if kind == "transferred" and to_bureau:
        f["bureau"] = to_bureau
        f["officer_id"] = pick_officer(to_bureau, case.get("region"))
    if f:
        db.update("cases", "id", case["id"], f)
    return f


def pick_officer(bureau: str, region: str | None = None) -> str | None:
    """Least-loaded officer of a bureau (regional offices: officer of the institution's region)."""
    rows = db.q("SELECT o.id, o.region, (SELECT COUNT(*) FROM cases c WHERE c.officer_id=o.id AND c.status!='disposed') AS n "
                "FROM officers o WHERE o.bureau=? AND o.rank='officer'", (bureau,))
    if bureau == "RO" and region:
        rows = [r for r in rows if r["region"] == region] or rows
    return min(rows, key=lambda r: (r["n"], r["id"]))["id"] if rows else None


def history_kinds(case_id: str) -> list[dict]:
    return db.q("SELECT kind, ts, bureau FROM actions WHERE case_id=? ORDER BY ts, id", (case_id,))
