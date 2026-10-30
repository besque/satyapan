"""Load the simulated test data: institutions, officers and about 400 complaint cases with their history.

Dates are relative to today, so timelines, overdue cases and escalations are always current.
Planted situations (each one a real coordination problem the system should catch):
  Kesarveni IT, Indore       five fee-refund complaints (pattern); RB show-cause while AB processes approval (conflict)
  Neelkamal Tarai CE, Lucknow  one student, Hindi complaint at PGRC + English e-mail to RB (same matter, two languages)
  Shaktikund CE, Bhopal      PGRC closed as resolved while RB ordered an inquiry on the same matter (conflict)
  Ratnaparvat IM, Pune       PGRC and RB both asked the institution for a reply on the same matter (conflict)
  Tejasvarna CE, Hyderabad   ragging: Anti-Ragging Cell case + parent's complaint at PGRC (same incident)
  Jalataranga CE, Mysuru     RB and Regional Office each ordered a visit (joint inquiry suggested)
  Kaveriprabha CE, Coimbatore  same student filed twice on CPGRAMS, two PGRC officers (duplicate)
  Sri Vanadurga, Hosur       two institutions of the same trust: complaint needs an officer to confirm which
Run:  python scripts/seed.py
"""
from __future__ import annotations

import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import ai, audit, db, demo, overlap, resolve, service, settings  # noqa: E402
from app.workflow import today  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
rng = random.Random(7)
T0 = today()
SCENARIO = {"Kesarveni", "Neelkamal Tarai", "Shaktikund", "Ratnaparvat", "Tejasvarna", "Jalataranga", "Kaveriprabha",
            "Sri Vanadurga", "Tarangvani"}

REMARK = {
    "accepted": ["Complaint examined; taken up.", "Taken up for necessary action.", "Assigned and taken up."],
    "sought_reply": ["Forwarded to the institution for comments within 15 days.", "Institution asked to submit a reply with documents."],
    "reply_received": ["Institution replied; under examination.", "Reply received from the institution with documents.",
                       "Institution states the matter is being settled."],
    "inquiry_ordered": ["Fact-finding visit ordered.", "Inquiry committee constituted to visit the institution."],
    "show_cause": ["Show-cause notice issued to the institution.", "Show-cause notice issued; reply awaited."],
    "hearing": ["Personal hearing held with the institution's representatives."],
    "penal_action": ["Penal action recommended to the competent authority."],
    "eoa_processing": ["Application received on the portal; scrutiny started."],
    "recommended_approval": ["Scrutiny complete; approval recommended."],
    "disposed_resolved": ["Grievance redressed; complainant informed.", "Matter settled; refund / documents given as confirmed by complainant."],
    "disposed_action_taken": ["Action taken against the institution; complainant informed."],
    "disposed_not_maintainable": ["Matter relates to the affiliating university; complainant advised accordingly.", "Not within AICTE's purview."],
}


def at(day: int, hour: int | None = None) -> str:
    h = hour if hour is not None else rng.randint(10, 17)
    return datetime.combine(T0 + timedelta(days=day), datetime.min.time(), tzinfo=IST).replace(hour=h, minute=rng.randint(0, 59)).isoformat()


def officer_name(oid: str) -> str:
    r = db.q1("SELECT name FROM officers WHERE id=?", (oid,))
    return r["name"] if r else "system"


def new(inst, bureau, cat, day, *, lang="en", style=None, who=None, source=None, text=None, subject=None, officer=None,
        inst_text=None, ctype=None, fixed=False):
    name, contact = who or demo.person(rng)
    if inst_text is None:
        inst_text = demo.mention(inst, style or rng.choice(demo.styles_for(inst, lang)), rng) if inst else ""
    if text is None:
        subject, text = demo.complaint_text(cat, inst_text, lang, rng, T0 + timedelta(days=day - rng.randint(5, 40)))
    src = source or {"PGRC": "CPGRAMS", "ARC": "Anti-Ragging Helpline", "AB": "AICTE portal"}.get(bureau, rng.choice(["Letter", "E-mail", "MoE reference"]))
    ext = {"CPGRAMS": f"CPG/{(T0 + timedelta(days=day)).year}/{rng.randint(1000000, 9999999)}",
           "Anti-Ragging Helpline": f"ARH-{rng.randint(100000, 999999)}"}.get(src)
    row = service.create_case({
        "bureau": bureau, "source": src, "ext_ref": ext, "received_on": (T0 + timedelta(days=day)).isoformat(),
        "complainant": name if bureau != "AB" else "Institution", "complainant_type": ctype or ("Institution" if bureau == "AB" else rng.choice(["Student", "Student", "Parent", "Faculty"]) if cat != "faculty_issues" else "Faculty"),
        "contact": contact if bureau != "AB" else None, "inst_text": inst_text, "subject": subject, "description": text,
        "category": cat if bureau == "AB" or fixed else None, "officer_id": officer,
    }, actor="system", role="system", ts=at(day, 9), refresh=False, log=False)
    return row


def act(case, kind, day, remarks=None, to=None):
    if day > 0:
        return
    c = db.q1("SELECT * FROM cases WHERE id=?", (case["id"],))
    if c["status"] == "disposed" and kind != "reopened":
        return
    actor = "system" if kind == "escalated" else officer_name(c["officer_id"])
    service.add_action(case["id"], kind, remarks or rng.choice(REMARK.get(kind, [""])), actor, "officer", acknowledged=True,
                       to_bureau=to, ts=at(day), check=False, refresh=False, log=False)


def age_flow(case, bureau, cat, d0):
    """A plausible history for a background case received on day d0 (negative = past)."""
    stall = rng.random() < 0.2
    if stall and d0 < -50 and rng.random() < 0.93:
        late = d0 + rng.randint(35, 70)       # the slow ones that were eventually closed, late
        _flow(case, bureau, cat, d0, True)
        c = db.q1("SELECT status FROM cases WHERE id=?", (case["id"],))
        if c["status"] != "disposed":
            act(case, "disposed_resolved", late)
        return
    _flow(case, bureau, cat, d0, stall)


def _flow(case, bureau, cat, d0, stall):
    if bureau == "PGRC":
        a = d0 + rng.randint(1, 3)
        act(case, "accepted", a)
        if cat == "ragging" and rng.random() < 0.7:
            return act(case, "transferred", a + 1, "Ragging complaint: transferred to the Anti-Ragging Cell.", "ARC")
        if cat in ("excess_fee", "unapproved_admission", "faculty_issues") and rng.random() < 0.5:
            act(case, "transferred", a + rng.randint(1, 4), "Regulatory matter: transferred to the Regulation Bureau.", "RB")
            return rb_flow(case, a + 5, stall)
        s = a + rng.randint(1, 4)
        act(case, "sought_reply", s)
        if stall:
            return
        r = s + rng.randint(6, 12)
        act(case, "reply_received", r)
        end = r + rng.randint(1, 5) + (rng.randint(5, 15) if rng.random() < 0.2 else 0)
        kind = "disposed_not_maintainable" if cat == "exam_result" and rng.random() < 0.6 else rng.choice(
            ["disposed_resolved"] * 6 + ["disposed_action_taken", "disposed_not_maintainable"])
        act(case, kind, end)
    elif bureau == "RB":
        rb_flow(case, d0 + rng.randint(1, 4), stall)
    elif bureau == "ARC":
        act(case, "accepted", d0)
        act(case, "sought_reply", d0 + 1, "Institution's anti-ragging committee asked to report within 7 days.")
        if not stall:
            act(case, "reply_received", d0 + rng.randint(5, 9), "Report received: action taken against the students involved.")
            act(case, "disposed_action_taken", d0 + rng.randint(9, 12))
    elif bureau == "AB":
        act(case, "eoa_processing", d0 + rng.randint(1, 4))
        act(case, "recommended_approval", d0 + rng.randint(22, 34))
        act(case, "disposed_resolved", d0 + rng.randint(36, 44), "EoA letter issued.")
    elif bureau == "RO":
        act(case, "accepted", d0 + 2)
        act(case, "inquiry_ordered", d0 + rng.randint(5, 9))
        if not stall:
            act(case, "disposed_action_taken", d0 + rng.randint(35, 50), "Inquiry report submitted; recommendations forwarded.")


def rb_flow(case, a, stall):
    act(case, "accepted", a)
    s = a + rng.randint(3, 7)
    act(case, "sought_reply", s)
    if stall:
        return
    r = s + rng.randint(12, 20)
    act(case, "reply_received", r)
    p = rng.random()
    if p < 0.45:
        act(case, "disposed_resolved", r + rng.randint(5, 20))
    elif p < 0.7:
        act(case, "show_cause", r + rng.randint(5, 12))
        act(case, "hearing", r + rng.randint(20, 30))
        act(case, "disposed_action_taken", r + rng.randint(32, 45))
    else:
        act(case, "inquiry_ordered", r + rng.randint(5, 12))
        act(case, "disposed_action_taken", r + rng.randint(40, 55), "Inquiry report accepted; directions issued to the institution.")


def main():
    t_start = time.time()
    db.reset()
    settings._cache = None
    insts = demo.institutions(rng)
    for i in insts:
        db.insert("institutions", {k: v for k, v in i.items() if not k.startswith("_")})
    for b, rows in demo.OFFICERS.items():
        for r in rows:
            db.insert("officers", {"id": r[0], "name": r[1], "bureau": b, "rank": r[2], "region": r[3] if len(r) > 3 else None})
    resolve.reload()
    print("model:", ai.backend())
    by = {}
    for i in insts:
        by.setdefault(i["_stem"], []).append(i)
    I = {k: v[0] for k, v in by.items()}

    # ---------------- background: ordinary complaints ----------------
    cats = ["fee_refund"] * 22 + ["certificates_withheld"] * 16 + ["excess_fee"] * 10 + ["ragging"] * 4 + ["faculty_issues"] * 7 + \
        ["infrastructure"] * 9 + ["unapproved_admission"] * 4 + ["scholarship"] * 10 + ["exam_result"] * 10 + ["harassment"] * 8
    pool = [i for i in insts if i["_stem"] not in SCENARIO]
    weight = [rng.uniform(0.5, 2.0) for _ in pool]
    for _ in range(300):
        inst = rng.choices(pool, weight)[0]
        cat = rng.choice(cats)
        home = settings.category(cat)["bureau"]
        bureau = home if rng.random() < 0.82 else "PGRC"
        lang = "hi" if inst["state"] in demo.HINDI_STATES and cat in demo.TEXT_HI and rng.random() < 0.35 else "en"
        d0 = -rng.randint(1, 270)
        c = new(inst, bureau, cat, d0, lang=lang)
        age_flow(c, bureau, cat, d0)
    # regional office references and approval applications
    for _ in range(14):
        inst = rng.choice(pool)
        d0 = -rng.randint(10, 200)
        c = new(inst, "RO", rng.choice(["infrastructure", "faculty_issues"]), d0, source="State Government reference")
        age_flow(c, "RO", None, d0)
    for inst in rng.sample(pool, 22):
        d0 = -rng.randint(3, 70)
        c = new(inst, "AB", "approval_application", d0, inst_text=inst["name"], subject="Extension of Approval 2027-28",
                text=f"Application for Extension of Approval for 2027-28" + rng.choice(["", " with increase in intake in B.Tech CSE from 120 to 180", " with a new course in Artificial Intelligence and Data Science"]) + ".")
        age_flow(c, "AB", None, d0)

    # ---------------- planted situations ----------------
    k = I["Kesarveni"]
    students = [demo.person(rng) for _ in range(5)]
    for n, (d0, lang) in enumerate([(-62, "en"), (-48, "hi"), (-35, "en"), (-21, "hi"), (-9, "en")]):
        c = new(k, "PGRC", "fee_refund", d0, lang=lang, who=students[n])
        act(c, "accepted", d0 + 2)
        if d0 < -30:
            act(c, "sought_reply", d0 + 5)
            act(c, "reply_received", d0 + 18, "Institution says the refund is under process.")
    rb = new(k, "RB", "excess_fee", -50, who=("Parents' Association, Kesarveni IT", "kitparents@example.in"), ctype="Parent", source="Letter",
             inst_text="Kesarveni Institute of Technology, Indore (Permanent ID " + k["permanent_id"] + ")",
             subject="Excess fee and capitation at Kesarveni Institute of Technology",
             text="We, the parents of first-year students of Kesarveni Institute of Technology, Indore, state that the institution has collected "
                  "Rs 75,000 per student as 'development fund' over the fee fixed by the Fee Regulatory Committee, without receipts. "
                  "We request strict action.", officer="RB-1", fixed=True)
    act(rb, "accepted", -47); act(rb, "sought_reply", -44); act(rb, "reply_received", -30, "Institution denies; says fees are voluntary.")
    act(rb, "show_cause", -12, "Show-cause notice issued: why approval should not be withdrawn for charging fees above the FRC limit.")
    ab = new(k, "AB", "approval_application", -25, inst_text=k["name"], subject="Extension of Approval 2027-28 with increase in intake",
             text="Application for Extension of Approval for 2027-28 with increase in intake in B.Tech CSE from 120 to 180.", officer="AB-1")
    act(ab, "eoa_processing", -22)

    n = I["Neelkamal Tarai"]
    p_hi = new(n, "PGRC", "certificates_withheld", -26, lang="hi", who=("Pooja Yadav", "9415072231"), officer="PGRC-1", ctype="Student",
               inst_text="नीलकमल तराई इंजीनियरिंग कॉलेज, लखनऊ", subject="मूल प्रमाणपत्र वापस नहीं",
               text="नीलकमल तराई इंजीनियरिंग कॉलेज, लखनऊ ने मेरे मूल प्रमाणपत्र (10वीं और 12वीं की अंकतालिका और टीसी) वापस नहीं किए हैं। "
                    "मैंने अगस्त में कॉलेज छोड़ दिया है और दूसरे कॉलेज में प्रवेश लेना है, लेकिन कॉलेज 45,000 रुपये मांग रहा है।")
    act(p_hi, "accepted", -24); act(p_hi, "sought_reply", -21)
    rb2 = new(n, "RB", "certificates_withheld", -12, who=("Pooja Yadav", "pooja.yadav.lko@example.in"), source="MoE reference", officer="RB-1", ctype="Student",
              inst_text="Neelkamal Tarai Engg College, Lucknow", subject="College not returning original certificates",
              text="I left Neelkamal Tarai Engg College, Lucknow in August. The college is not returning my original 10th and 12th "
                   "marksheets and TC and is demanding Rs 45,000. I need them for admission in another college. Please help.")
    act(rb2, "accepted", -10)

    s = I["Shaktikund"]
    p1 = new(s, "PGRC", "certificates_withheld", -40, who=demo.person(rng), officer="PGRC-2", inst_text="Shaktikund Engineering College Bhopal",
             subject="Original certificates withheld",
             text="Shaktikund Engineering College, Bhopal is keeping the original certificates of students who left after first year "
                  "and is demanding fees for all four years before returning them.")
    act(p1, "accepted", -38); act(p1, "sought_reply", -35)
    act(p1, "reply_received", -24, "Institution states that all certificates have been returned.")
    act(p1, "disposed_resolved", -20, "Closed on the institution's reply that certificates were returned.")
    r1 = new(s, "RB", "certificates_withheld", -15, who=("Students' representation (forwarded by State Government)", "dte.mp@example.in"),
             source="State Government reference", officer="RB-2", inst_text="Shaktikund College of Engineering, Bhopal",
             subject="Original certificates retained by Shaktikund College",
             text="Students who left Shaktikund College of Engineering, Bhopal after the first year say the college still keeps their "
                  "original certificates and asks for the fees of all four years before returning them.")
    act(r1, "accepted", -13); act(r1, "inquiry_ordered", -5, "Regional Office asked to verify at the institution.")

    r = I["Ratnaparvat"]
    p2 = new(r, "PGRC", "excess_fee", -30, who=demo.person(rng), officer="PGRC-3", inst_text="Ratnaparvat Business School Pune",
             subject="Extra charges without receipt",
             text="Ratnaparvat Institute of Management, Pune collected Rs 60,000 extra from each MBA student for 'industry readiness' "
                  "that was made compulsory. No receipt was given.")
    act(p2, "accepted", -28); act(p2, "sought_reply", -26)
    r2 = new(r, "RB", "excess_fee", -22, who=("MBA students' parents", "ratna.parents@example.in"), officer="RB-3",
             inst_text="Ratnaparvat Institute of Management, Pune", subject="Compulsory extra fee",
             text="Parents complain that Ratnaparvat Institute of Management, Pune forced every MBA student to pay Rs 60,000 extra for "
                  "an 'industry readiness' programme over the approved fee, without receipts.")
    act(r2, "accepted", -20); act(r2, "sought_reply", -18)

    tj = I["Tejasvarna"]
    a1 = new(tj, "ARC", "ragging", -6, who=("Caller to helpline", "9849011420"), officer="ARC-1", inst_text="Tejasvarna College of Engineering, Hyderabad",
             subject="Ragging in hostel",
             text="First-year student of Tejasvarna College of Engineering, Hyderabad reports ragging by seniors in Block B hostel; "
                  "beaten on the night of the 2nd and made to stand for hours. Wants anonymity.")
    act(a1, "accepted", -6); act(a1, "sought_reply", -5, "Institution's anti-ragging committee asked to report within 7 days.")
    p3 = new(tj, "PGRC", "ragging", -5, who=("Ravi Teja", "9866055210"), officer="PGRC-4", ctype="Parent", inst_text="Tejasvarna Engg College Hyderabad",
             subject="My son ragged in hostel",
             text="My son is a first-year student at Tejasvarna Engg College, Hyderabad. Senior students ragged and beat him in the "
                  "hostel at night and made him stand for hours. The college is silent. Please act.")

    t = I["Tarangvani"]
    p4 = new(t, "PGRC", "scholarship", -18, who=demo.person(rng), officer="PGRC-2")
    act(p4, "accepted", -16); act(p4, "sought_reply", -14)
    r4 = new(t, "RB", "infrastructure", -33, who=demo.person(rng), officer="RB-2")
    act(r4, "accepted", -31); act(r4, "sought_reply", -28); act(r4, "reply_received", -12)
    ab2 = new(t, "AB", "approval_application", -15, inst_text=t["name"], subject="Extension of Approval 2027-28",
              text="Application for Extension of Approval for 2027-28 (no change).", officer="AB-2")
    act(ab2, "eoa_processing", -13)

    jt = I["Jalataranga"]
    r5 = new(jt, "RB", "faculty_issues", -45, who=("Faculty members' association", "jct.faculty@example.in"), officer="RB-3",
             inst_text="Jalataranga College of Engineering, Mysuru", subject="Faculty shown on paper; salary pending",
             text="Several faculty members listed by Jalataranga College of Engineering, Mysuru in its approval documents do not work "
                  "there; those who do have not been paid for four months.")
    act(r5, "accepted", -43); act(r5, "sought_reply", -40); act(r5, "reply_received", -25)
    act(r5, "inquiry_ordered", -8, "Committee to visit and verify faculty attendance and salary records.")
    ro = new(jt, "RO", "infrastructure", -20, who=("State Government reference", "dte.ka@example.in"), source="State Government reference",
             officer="RO-SW", inst_text="Jalataranga CE Mysuru", subject="Labs and library deficient",
             text="The Department of Technical Education reports that Jalataranga College of Engineering, Mysuru has non-functional "
                  "laboratories and a library far below norms. Verification requested.")
    act(ro, "accepted", -18); act(ro, "inquiry_ordered", -6, "Visit to verify laboratories and library.")

    kv = I["Kaveriprabha"]
    who = ("Arjun Pillai", "9443022871")
    d1 = new(kv, "PGRC", "fee_refund", -30, who=who, officer="PGRC-2", inst_text="Kaveriprabha College of Engineering, Coimbatore",
             subject="Fee refund not given",
             text="I cancelled my B.Tech admission at Kaveriprabha College of Engineering, Coimbatore on 5 August. The fee of Rs 88,000 "
                  "has not been refunded in spite of repeated requests.")
    act(d1, "accepted", -28); act(d1, "sought_reply", -25)
    d2 = new(kv, "PGRC", "fee_refund", -10, who=who, officer="PGRC-3", inst_text="Kaveriprabha Engg College Coimbatore",
             subject="Reminder: refund of Rs 88,000",
             text="Reminder. My refund of Rs 88,000 from Kaveriprabha Engg College, Coimbatore after cancelling admission is still "
                  "pending. Nobody replies.")
    act(d2, "accepted", -8)

    new(None, "PGRC", "fee_refund", -4, who=demo.person(rng), officer="PGRC-1", inst_text="Sri Vanadurga engg college, Hosur",
        subject="Refund pending", text="I cancelled my admission at Sri Vanadurga engg college, Hosur in July. Rs 45,000 not refunded yet.")
    new(None, "PGRC", "exam_result", -3, who=demo.person(rng), officer="PGRC-4", inst_text="Lotus Valley Coaching Institute, Patna",
        subject="Coaching fees", text="Lotus Valley Coaching Institute in Patna took Rs 25,000 for GATE coaching and closed the classes.")

    # ---------------- detection, timelines, activity log ----------------
    for i in insts:
        overlap.refresh(i["permanent_id"], log=False)
    for co in db.q("SELECT * FROM coordination"):
        ids = db.unj(co["cases"], [])
        last = db.q1(f"SELECT MAX(ts) AS t FROM actions WHERE case_id IN ({','.join('?' * len(ids))}) AND kind!='escalated'", ids)["t"]
        db.update("coordination", "id", co["id"], {"created_at": last, "updated_at": last})
        db.update("notifications", "coord_id", co["id"], {"created_at": last})
    service.sweep(log=False)
    for a in db.q("SELECT * FROM actions ORDER BY ts, id"):
        audit.log(a["actor"], "system" if a["actor"] == "system" else "officer", f"case.{a['kind']}", a["case_id"],
                  {"remarks": a["remarks"], "to": a["to_bureau"]}, ts=a["ts"])
    for co in db.q("SELECT * FROM coordination ORDER BY created_at"):
        audit.log("system", "system", "coordination.raised", co["id"], {"kind": co["kind"], "cases": db.unj(co["cases"])}, ts=co["created_at"])
    audit.log("system", "system", "demo.seeded", "all", {"cases": db.q1("SELECT COUNT(*) n FROM cases")["n"]})
    c = db.q1("SELECT COUNT(*) n, SUM(status!='disposed') o FROM cases")
    print(f"cases {c['n']} (open {c['o']}), alerts:",
          {r["kind"]: r["n"] for r in db.q("SELECT kind, COUNT(*) n FROM coordination WHERE status='open' GROUP BY kind")},
          f"in {time.time() - t_start:.0f}s")


if __name__ == "__main__":
    main()
