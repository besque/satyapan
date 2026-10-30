"""Standard communications and the electronic case summary, filled from the record.

All of these are drafts: an authorised officer reviews and sends them. Nothing here decides anything.
"""
from __future__ import annotations

from datetime import date

from . import db, engine, settings, views
from .clock import d

KINDS = {"summary": "Case summary", "deficiency": "Deficiency letter", "evc": "EVC intimation",
         "decision": "Decision letter", "escalation": "Escalation note"}


def _f(x) -> str:
    x = d(x)
    return f"{x:%d %b %Y}" if x else "—"


def build(kind: str, app_id: str, on: date) -> dict:
    if kind not in KINDS:
        raise engine.WorkflowError("Unknown letter")
    det = views.app_detail(app_id, {"role": "head", "offices": []}, on)
    a, inst, cd = det["app"], det["institution"], det["countdown"]
    head = {"kind": kind, "title": KINDS[kind], "ref": f"{a['id']} / {settings.get()['cycle']['ay']}", "date": _f(on),
            "to": f"The Chairman / Secretary, {inst['name']}, {inst['city'] or inst['state']} (Permanent ID {inst['pid']})"}
    steps = det["steps"]
    if kind == "summary":
        rows = [[s["label"] + (f" (round {s['attempt']})" if s["attempt"] > 1 else ""), _f(s["opened_on"]), _f(s["closed_on"]) if s["closed_on"] else "open",
                 s["outcome_label"] or engine.task_text(s), "; ".join(s["deficiencies"])] for s in steps]
        open_items = [i for i in det["items"] if i["status"] in ("open", "submitted", "rejected") and i["source"] == "test"]
        esc = [x for x in det["alerts"] if (x["level"] or 0) >= 2]
        return {**head, "to": None, "subject": f"{a['nature_label']}: {inst['name']}",
                "facts": [["Institution", f"{inst['name']}, {inst['city'] or ''} ({inst['region']} region)"], ["Permanent ID", inst["pid"]],
                          ["Nature of application", a["nature_label"]], ["Submitted", _f(a["submitted_on"])],
                          ["Status", a["status_label"] + (f": {a['task']}" if a["task"] else "")],
                          ["With", f"{a['holder_label']} for {a['with_days']} days" if a["holder"] else "—"],
                          ["Due", _f(a["due_on"]) + (f" (overdue {a['overdue']} days)" if a["overdue"] else "")],
                          ["Calendar date", f"{_f(cd['deadline'])} ({cd['deadline_kind']}): {cd['risk_label']}. {cd['why']}" if cd else "—"],
                          ["Time taken", f"{det['time']['aicte']} days with AICTE, {det['time']['institution']} days with the institution"],
                          ["Open deficiencies", "; ".join(a["deficiencies"]) or "None"]],
                "table": {"head": ["Stage", "Opened", "Closed", "Outcome", "Deficiencies"], "rows": rows},
                "lists": [["Open compliance items", [f"{i['title']} — {i['state']['label']}" for i in open_items] or ["None"]],
                          ["Escalations", [f"{_f(x['on_date'])}: {x['text']}" for x in esc[:6]] or ["None"]]]}
    if kind == "deficiency":
        last = next((s for s in reversed(steps) if s["outcome"] == "deficient"), None)
        if not last:
            raise engine.WorkflowError("No deficiencies have been recorded on this application")
        comp = next((s for s in steps if s["stage"] == "compliance" and s["id"] > last["id"]), None)
        due = comp["due_on"] if comp else None
        return {**head, "subject": f"Deficiencies noted by the {last['label']}: {a['nature_label']}, {settings.get()['cycle']['ay']}",
                "paras": [f"The {last['label']} examined your application {a['id']} on {_f(last['closed_on'])} and noted the following deficiencies:"],
                "points": last["deficiencies"],
                "after": [f"Please submit compliance with supporting documents through the portal by {_f(due)}." if due else
                          "Please bring proof of compliance to the hearing.",
                          "The opportunity to submit compliance is given under Clause 2.4 of the Approval Process Handbook 2024-27. "
                          "If compliance is not received in time, the application will be processed on the record available."]}
    if kind == "evc":
        ev = next((s for s in reversed(steps) if s["stage"] == "evc" and s["meeting_on"]), None)
        if not ev:
            raise engine.WorkflowError("No EVC has been fixed for this application")
        online = ev["mode"] == "online"
        pts = (["Prepare a video of all infrastructural facilities, not less than 30 minutes, upload it on the Trust / Society website "
                "and share the link on the portal (Clause 1.9 f)."] if online else
               ["Arrange video recording of the entire visit with date and time, at the institution's expense (Clause 1.9 g)."])
        pts += ["The recording must show the entry and exit of the Committee, the building plan signed at scrutiny, and GPS coordinates "
                "at the entrance of the main, academic and administrative buildings and the library.",
                "Upload attested copies of the documents in Annexure-1 on the portal."]
        return {**head, "subject": f"Expert Visit Committee ({ev['mode']}) on {_f(ev['meeting_on'])}: {a['nature_label']}",
                "paras": [f"The Expert Visit Committee for application {a['id']} will be held {'online' if online else 'at the institution'} "
                          f"on {_f(ev['meeting_on'])}."], "points": pts,
                "after": ["Two authorised representatives must be present with self-attested photo identity proof."]}
    if kind == "decision":
        dec = next((s for s in reversed(steps) if s["stage"] in ("ec", "council") and s["outcome"]), None)
        if not dec:
            raise engine.WorkflowError("No decision has been recorded yet")
        who = "Executive Committee" if dec["stage"] == "ec" else "Council"
        conds = [i for i in det["items"] if i["app_id"] == a["id"]]
        if dec["outcome"] == "approve":
            return {**head, "subject": f"{'Letter of Approval' if a['nature'] == 'new_institution' else 'Approval'}: {a['nature_label']}, {settings.get()['cycle']['ay']}",
                    "paras": [f"The {who}, in its meeting on {_f(dec['closed_on'])}, approved application {a['id']}" + (", subject to the following:" if conds else ".")],
                    "points": [f"{i['title']} by {_f(i['due_on'])}" + (f" ({i['detail']})" if i["detail"] else "") for i in conds],
                    "after": ["Each condition is tracked; reminders are sent before the due date and non-compliance is reported to the competent authority."]}
        return {**head, "subject": f"{engine.OUTCOME[dec['outcome']]}: {a['nature_label']}, {settings.get()['cycle']['ay']}",
                "paras": [f"The {who}, in its meeting on {_f(dec['closed_on'])}, decided: {engine.OUTCOME[dec['outcome']]}."
                          + (f" Reasons: {dec['remarks']}." if dec["remarks"] else "")],
                "points": a["deficiencies"],
                "after": ["You may appeal once within 7 days of this decision through the portal (Clause 2.24 a)." if engine.appeal_allowed(engine.app(a["id"])) and dec["stage"] == "ec" else ""]}
    # escalation note
    return {**head, "to": "Senior management (Adviser, Approval)", "subject": f"Escalation: {a['id']} {inst['name']}",
            "paras": [f"Application {a['id']} ({a['nature_label']}) is waiting on: {a['task'] or '—'}.",
                      f"It has been with the {a['holder_label']} for {a['with_days']} days; it was due on {_f(a['due_on'])}"
                      + (f" and is {a['overdue']} days overdue." if a["overdue"] else "."),
                      (f"Against the Academic Calendar date of {_f(cd['deadline'])}: {cd['risk_label']}. {cd['why']}" if cd else "")],
            "points": [f"Latest date for this step to finish: {_f(cd['finish_by'])}" if cd else "",
                       f"Hold the committee by {_f(cd.get('hold_by'))}" if cd and cd.get("hold_by") else ""],
            "after": ["Suggested: direct the holding office to act by the date above, or record the reason for the delay."]}
