"""Test results (data/eval_report.json, shown on the Test results page).

1. Routing: every nature of application in APH Table 2.3, driven through the real workflow engine under several
   outcome scenarios, checked against the table as printed (encoded here by hand, separately from settings.yaml).
2. Rules: lease rule, security-deposit ladder, appeal window, certificate validity, compliance windows, countdown.
3. Alert timeliness: simulated approval cycles (independent random draws, not the demo data). For applications
   that end up decided after the Academic Calendar date, how early was each method warning?
     - time allowed per step: warn when any step is past its time allowed (the usual pendency alert)
     - countdown: warn when the calendar date is short at the usual pace (this system)
4. Real data, follow-ups sent automatically, and completeness of the activity log (from the demo database).
Run:  python scripts/evaluate.py      (after scripts/seed.py)
"""
from __future__ import annotations

import json
import os
import random
import sqlite3
import statistics
import sys
import tempfile
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO_DB = ROOT / "data" / "app.sqlite"
TMP = Path(tempfile.mkdtemp()) / "eval.sqlite"
os.environ["APP_DB"] = str(TMP)           # the engine works on a scratch database here
sys.path.insert(0, str(ROOT / "backend"))

from app import compliance, db, engine, settings  # noqa: E402
from app.clock import add_months, d, iso  # noqa: E402

# APH Table 2.3 as printed on page 30 (self-disclosure, scrutiny / re-scrutiny, EVC, SAC/SHC) + Chapter I.
TABLE = {
    "eoa_self_disclosure": ("Yes", "-", "-", "-"), "nri_seats": ("Yes", "-", "-", "-"), "conversion_level": ("-", "Yes", "Yes", "AA"),
    "name_change": ("-", "Yes", "-", "-"), "new_programme": ("-", "Yes", "Yes", "AA"), "merger": ("-", "Yes", "Yes", "AA"),
    "eoa_after_break": ("-", "Yes", "Yes", "AA"), "fn_oci_seats": ("-", "Yes", "-", "-"), "increase_intake": ("-", "Yes", "Yes", "AA"),
    "integrated_dual": ("-", "Yes", "Yes", "AA"), "fpm": ("-", "Yes", "Yes", "AA"), "course_change": ("-", "Yes", "-", "-"),
    "collaboration": ("-", "Yes", "Yes", "AA"), "change_of_site": ("-", "Yes", "Yes", "AA"), "closure_institution": ("-", "Yes", "-", "-"),
    "women_coed": ("-", "Yes", "-", "-"), "closure_programme": ("-", "Yes", "-", "-"), "bank_details": ("-", "Yes", "-", "-"),
    "trust_name_change": ("-", "Yes", "-", "-"), "deemed_university": ("-", "Yes", "Yes", "AA"), "odl_online": ("-", "Yes", "Yes", "AA"),
    "new_institution": ("-", "Yes", "Yes", "AA"),
}
PROCEDURAL = {"compliance", "ec"}   # steps every route has around the committees


def tri(r, lo, hi, mode):
    return int(round(r.triangular(lo, hi, mode)))


# ------------------------------------------------------------------------------------ 1. routing

def drive(nature: str, scenario: str) -> list[tuple[str, str]]:
    """Run one application through the engine; return (stage, outcome) in order."""
    pid = f"T-{nature}"
    if not db.q1("SELECT pid FROM institutions WHERE pid=?", (pid,)):
        db.insert("institutions", {"pid": pid, "name": f"Route test {nature}", "region": "Central", "ownership": "Private", "land": "own",
                                   "programmes": [{"years": 4}], "source": "test"})
    on = date(2027, 1, 5)
    a = engine.create_application(pid, nature, on, "Central", app_id=f"R-{nature}-{scenario}")
    first_check_done = False
    for _ in range(30):
        a = engine.app(a["id"])
        step = engine.current_step(a)
        if not step:
            break
        st = step["stage"]
        on += timedelta(days=1)
        if st in engine.COMMITTEES and step["phase"] in ("to_schedule", "awaiting_video"):
            engine.schedule(a["id"], on, on + timedelta(days=7), "physical", "t", "t")
            continue
        if st in engine.COMMITTEES or st == "self_disclosure":
            if st == "sac":
                engine.record_outcome(a["id"], on, "recommend", [], "", "t", "t")
                continue
            first = st in ("scrutiny", "self_disclosure") and not first_check_done
            has_evc = "evc" in settings.nature(nature)["route"]
            if scenario == "deficient_first":
                bad = first
            elif scenario == "deficient_late":        # EVC finds deficiencies (or, without an EVC, re-scrutiny does)
                bad = st == "evc" if has_evc else (first or st == "re_scrutiny")
            elif scenario == "appeal":                # deficiencies at EVC and at the hearing, then an appeal
                bad = st in ("evc", "shc")
            else:
                bad = False
            first_check_done = first_check_done or st in ("scrutiny", "self_disclosure")
            engine.record_outcome(a["id"], on, "deficient" if bad else "in_order", ["test deficiency"] if bad else [], "", "t", "t")
        elif st == "compliance":
            engine.submit_compliance(a["id"], on, "done", "t", "t")
        elif st in ("ec", "council"):
            dec = "lod" if st == "ec" and scenario in ("deficient_late", "appeal") and db.unj(a["deficiencies"], []) else "approve"
            engine.decide(a["id"], on, dec, "", "t", "t")
        elif st == "appeal":
            engine.file_appeal(a["id"], on, "grounds", "t", "t")
    return [(s["stage"], s["outcome"] or "") for s in db.q("SELECT stage, outcome FROM steps WHERE app_id=? ORDER BY id", (a["id"],))]


def check_route(nature: str, scenario: str, path: list[tuple[str, str]]) -> list[str]:
    sd, scr, evc, aa = TABLE[nature]
    stages = [s for s, _ in path]
    problems = []
    yes = {"self_disclosure"} if sd == "Yes" else set()
    yes |= {"scrutiny"} if scr == "Yes" else set()
    yes |= {"evc"} if evc == "Yes" else set()
    for s in yes:
        if s not in stages:
            problems.append(f"missing {s}")
    allowed = yes | PROCEDURAL | ({"re_scrutiny"} if (scr == "Yes" or sd == "Yes") else set())
    if aa == "AA":
        allowed |= {"shc", "sac", "appeal", "council"}
    for s in stages:
        if s not in allowed:
            problems.append(f"{s} not in Table 2.3 for this nature")
    for s in ("shc", "sac"):          # "as applicable": only after a deficiency or a decision against the institution
        if s in stages:
            before = path[:stages.index(s)]
            if not any(o in ("deficient", "lod", "reject") for _, o in before):
                problems.append(f"{s} without a deficient outcome before it")
    if "evc" in stages and "scrutiny" in stages and stages.index("evc") < stages.index("scrutiny"):
        problems.append("EVC before scrutiny")
    if "ec" not in stages:
        problems.append("never reached the Executive Committee")
    return problems


def routing() -> dict:
    rows = []
    for nature in TABLE:
        scenarios = ["all_in_order", "deficient_first", "deficient_late"] + (["appeal"] if TABLE[nature][3] == "AA" else [])
        for sc in scenarios:
            path = drive(nature, sc)
            probs = check_route(nature, sc, path)
            rows.append({"nature": nature, "label": settings.nature(nature)["label"], "scenario": sc,
                         "path": " → ".join(f"{settings.stage(s)['short']}{' (' + engine.OUTCOME.get(o, o).lower() + ')' if o else ''}" for s, o in path),
                         "ok": not probs, "problems": probs})
    return {"natures": len(TABLE), "cases": len(rows), "passed": sum(r["ok"] for r in rows), "rows": rows}


# ------------------------------------------------------------------------------------ 2. rules

def rules() -> dict:
    rows = []

    def case(rule, desc, expected, got, cite):
        rows.append({"rule": rule, "case": desc, "expected": str(expected), "got": str(got), "ok": str(expected) == str(got), "cite": cite})

    for lease, years, exp in [("2031-06-30", 4, "2027-28"), ("2033-03-31", 4, "2029-30"), ("2032-07-01", 5, "2027-28"),
                              ("2040-06-30", 2, "2038-39"), ("2060-12-31", 4, "2057-58")]:
        b = compliance.lease_block(lease, years)
        case("Lease rule", f"lease to {lease}, longest course {years} years: EoA blocked from", exp, b["blocked_ay"] if b else None, "CL_2_1_E")
    it = {"status": "open", "due_on": "2027-05-14", "extra": json.dumps({"amount_lakh": 15})}
    for on, exp in [("2027-05-10", "due"), ("2027-05-20", "penalty_10"), ("2027-06-15", "penalty_20"), ("2027-08-02", "withdraw")]:
        case("Security deposit", f"intimated 29 Apr, on {on}", exp, compliance.deposit_state(it, d(on))["stage"], "CL_2_25_F")
    case("Appeal window", "Letter of Deficiency on 13 May 2027: appeal allowed until", "2027-05-20",
         iso(date(2027, 5, 13) + timedelta(days=settings.stage("appeal")["days"])), "CL_2_24_A")
    case("Structural stability", "issued 20 Jun 2022, valid five years: until", "2027-06-20", iso(add_months(date(2022, 6, 20), 60)), "CL_6_17_H")
    case("EoA letter", "issued 10 Apr 2026, 'within Six Months': due", "2026-10-10", iso(add_months(date(2026, 4, 10), 6)), "EOA_LETTER")
    case("EoA letter", "issued 30 Jun 2024, 'within One year': due", "2025-06-30", iso(add_months(date(2024, 6, 30), 12)), "EOA_LETTER")
    # countdown: EVC still to be fixed on 17 May; last EC meeting before 10 Jun is 8 Jun, with 3 days to place the case
    a = {"id": "X", "nature": "increase_intake", "region": "Central", "detail": "{}"}
    step = {"stage": "evc", "phase": "to_schedule", "due_on": "2027-05-03", "meeting_on": None, "extra": "{}"}
    cd = engine.countdown(a, step, date(2027, 5, 17))
    case("Countdown", "EVC not yet fixed on 17 May: must finish by", "2027-06-05", cd["finish_by"], "CL_2_25_J")
    case("Countdown", "same: spare days at the usual pace", 10, cd["spare"], "CL_2_25_J")
    case("Countdown", "same: one more deficiency round (SHC, 14 days)", "at_risk", cd["risk"], "CL_2_23_3")
    step2 = {"stage": "evc", "phase": "scheduled", "due_on": "2027-06-10", "meeting_on": "2027-06-08", "extra": "{}"}
    case("Countdown", "EVC fixed for 8 Jun: classed", "will_miss", engine.countdown({**a, "nature": "new_institution"}, step2, date(2027, 4, 15))["risk"], "CL_2_25_J")
    return {"cases": len(rows), "passed": sum(r["ok"] for r in rows), "rows": rows}


# ------------------------------------------------------------------------------------ 3. alert timeliness

def simulate(r: random.Random, nature: str, region: str, submitted: date) -> tuple[list[dict], date | None]:
    """One application's phases at random (same kind of draws as the demo, separate random stream)."""
    s = settings.get()
    n = settings.nature(nature)
    aa = n.get("aa") or []
    w = engine.window_of(nature, region)
    sfrom = d(w["scrutiny_from"])
    phases: list[dict] = []
    t = submitted
    stage, extra, defs = n["route"][0], {}, False
    after_scr = engine._after_scrutiny({"nature": nature})
    while True:
        cfg = settings.stage(stage)
        if stage == "self_disclosure":
            end = t + timedelta(days=tri(r, 1, 11, 4))
            phases.append({"stage": stage, "phase": "review", "start": t, "end": end, "due_on": t + timedelta(days=cfg["days"])})
            bad = r.random() < .22
            defs = bad
            t, stage = end, ("compliance" if bad else "ec")
            extra = {"return_to": "re_scrutiny"} if bad else {}
            continue
        if stage == "compliance":
            end = t + timedelta(days=tri(r, 3, 32, 11))
            phases.append({"stage": stage, "phase": "with_institution", "start": t, "end": end, "due_on": t + timedelta(days=cfg["days"]), "extra": dict(extra)})
            t, stage, extra = end, extra.get("return_to", "re_scrutiny"), {}
            continue
        if stage in engine.COMMITTEES:
            start = max(t, sfrom)
            act = start + timedelta(days=(tri(r, 3, 30, 12) if region == "Central" else tri(r, 1, 20, 7)) if stage == "evc"
                                    else tri(r, 1, 26, 9) if stage == "scrutiny" else tri(r, 1, 13, 5))
            phases.append({"stage": stage, "phase": "to_schedule", "start": t, "end": act, "due_on": start + timedelta(days=cfg.get("schedule_days", 5))})
            spread = {"scrutiny": (0, 75, 28), "evc": (0, 45, 16), "shc": (0, 30, 10), "re_scrutiny": (0, 20, 6), "sac": (0, 12, 4)}[stage]
            meeting = act + timedelta(days=cfg.get("lead", 7) + tri(r, *spread))
            rep = cfg.get("report", 2)
            report_on = meeting + timedelta(days=tri(r, 0, 2.4, 1) if r.random() < .93 else tri(r, 4, 12, 6))
            phases.append({"stage": stage, "phase": "scheduled", "start": act, "end": report_on, "due_on": meeting + timedelta(days=rep), "meeting_on": meeting})
            p = {"scrutiny": .4, "re_scrutiny": .18, "evc": .25, "shc": .35, "sac": 0}[stage]
            bad = r.random() < p
            t = report_on
            if stage == "scrutiny":
                stage, extra = ("compliance", {"return_to": "re_scrutiny"}) if bad else (after_scr[0], {})
                defs = bad
            elif stage == "re_scrutiny":
                defs = bad
                stage = (after_scr[0] if not bad else ("shc" if "shc" in aa else "ec"))
            elif stage == "evc":
                stage = "ec" if not bad else ("shc" if "shc" in aa else "ec")
            elif stage == "shc":
                stage = "ec"
            continue
        if stage == "ec":
            prep = s["cycle"].get("ec_prep_days", 3)
            m = engine.next_ec(t + timedelta(days=prep))
            phases.append({"stage": "ec", "phase": "pending", "start": t, "end": m or t + timedelta(days=60), "due_on": m or t + timedelta(days=10)})
            return phases, m
        raise RuntimeError(stage)


def replay(seasons: int = 6, per_season: int = 500) -> dict:
    s = settings.get()
    D = d(s["cycle"]["last_date_approval"])
    natures = list(s["natures"])
    weights = [52 if k == "eoa_self_disclosure" else 13 if k == "increase_intake" else 9 if k == "new_programme" else 7 if k == "new_institution" else 2 for k in natures]
    regions = list(s["regions"])
    res = []
    for season in range(seasons):
        r = random.Random(1000 + season)
        for k in range(per_season):
            nature = r.choices(natures, weights=weights)[0]
            region = r.choice(regions)
            w = engine.window_of(nature, region)
            a0, b0 = d(w["from"]), d(w["to"])
            sub = a0 + timedelta(days=r.randint(0, (b0 - a0).days))
            phases, decided = simulate(r, nature, region, sub)
            missed = decided is None or decided > D
            a = {"id": "R", "nature": nature, "region": region, "detail": "{}"}
            age_first = cd_first = risk_first = None
            fast_ok_at_first = None
            save = {}                 # method -> could fast-tracking still make the date on the day it first warned?
            flagged_days_age = flagged_days_cd = 0
            day = sub
            end = min(phases[-1]["start"], D)
            while day <= end:
                ph = next((p for p in phases if p["start"] <= day < p["end"]), None)
                if ph:
                    step = {"stage": ph["stage"], "phase": ph["phase"], "due_on": iso(ph["due_on"]), "meeting_on": iso(ph.get("meeting_on")),
                            "extra": json.dumps(ph.get("extra") or {})}
                    cd = engine.countdown(a, step, day)
                    late = day > ph["due_on"]
                    if late:
                        flagged_days_age += 1
                        if not age_first:
                            age_first, save["age"] = day, cd["spare_fast"] >= 0
                    if cd["spare"] < 0:
                        flagged_days_cd += 1
                        if not cd_first:
                            cd_first = day
                            fast_ok_at_first = save["cd"] = cd["spare_fast"] >= 0
                    if cd["risk"] != "on_track" and not risk_first:
                        risk_first, save["risk"] = day, cd["spare_fast"] >= 0
                day += timedelta(days=1)
            res.append({"missed": missed, "age": age_first, "cd": cd_first, "risk": risk_first, "fast_ok": fast_ok_at_first, "save": save,
                        "days_age": flagged_days_age, "days_cd": flagged_days_cd, "decided": decided})
    misses = [x for x in res if x["missed"]]
    made = [x for x in res if not x["missed"]]

    def method(key: str, name: str, how: str) -> dict:
        warned = [x for x in misses if x[key]]
        leads = [(D - x[key]).days for x in warned]
        flagged = [x for x in res if x[key]]
        return {"name": name, "how": how, "misses_warned": len(warned), "share_warned": round(100 * len(warned) / max(1, len(misses))),
                "share_warned_21": round(100 * sum(l >= 21 for l in leads) / max(1, len(misses))),
                "share_saveable": round(100 * sum(1 for x in misses if x["save"].get(key)) / max(1, len(misses))),
                "median_lead": statistics.median(leads) if leads else None,
                "flagged": len(flagged), "precision": round(100 * sum(x["missed"] for x in flagged) / max(1, len(flagged))),
                "false_alarms": round(100 * sum(1 for x in made if x[key]) / max(1, len(made)))}
    out = {"applications": len(res), "seasons": seasons, "missed": len(misses), "missed_share": round(100 * len(misses) / len(res), 1),
           "deadline": iso(D),
           "methods": [method("age", "Time allowed per step", "warn when any step is past its time allowed (the usual pendency alert)"),
                       method("cd", "Countdown to the calendar date", "warn when the date is short at the usual pace"),
                       method("risk", "Countdown, early warning", "also warn when one more deficiency round would miss the date")],
           "actionable": round(100 * sum(1 for x in misses if x["cd"] and x["fast_ok"]) / max(1, sum(1 for x in misses if x["cd"]))),
           "note": "Simulated cycles with random stage times (independent of the demo data). Both methods see the same applications on the same days."}
    return out


# ------------------------------------------------------------------------------------ 4. real data, follow-ups, audit

def real_and_demo() -> dict:
    insts = json.loads((ROOT / "data/real/institutions.json").read_text(encoding="utf-8"))
    letters = [l for i in insts for l in i["letters"]]
    with_defs = [(i, l) for i in insts for l in i["letters"] if l["deficiencies"]]
    pairs = again = 0
    examples = []
    for i, l in with_defs:
        y = int(l["ay"][:4]) + 1
        nxt = next((x for x in i["letters"] if x["ay"] == f"{y}-{str(y + 1)[2:]}"), None)
        if nxt:
            pairs += 1
            same = sorted(set(l["deficiencies"]) & set(nxt["deficiencies"]))
            if same:
                again += 1
                examples.append(f"{i['name'].title()}: {'; '.join(same)} ({l['ay']} and {nxt['ay']})")
    unit = lambda c: f"{c['n']} {c['unit'][:-1] if c['n'] == 1 else c['unit']}"  # noqa: E731
    windows = Counter(unit(l["comply_within"]) for _, l in with_defs if l.get("comply_within"))
    by_year = {}
    for _, l in with_defs:
        if l.get("comply_within"):
            by_year.setdefault(l["ay"], set()).add(unit(l["comply_within"]))
    real = {"institutions": len(insts), "letters": len(letters), "with_deficiencies": len(with_defs),
            "share_with_deficiencies": round(100 * len(with_defs) / max(1, len(letters))), "pairs": pairs, "noted_again": again,
            "examples": examples, "windows": dict(windows), "window_by_year": {k: sorted(v) for k, v in sorted(by_year.items())},
            "aph_clauses": len(json.loads((ROOT / "data/real/aph_locs.json").read_text()))}
    demo = {}
    if DEMO_DB.exists():
        c = sqlite3.connect(DEMO_DB)
        c.row_factory = sqlite3.Row
        kinds = Counter(r["kind"] for r in c.execute("SELECT kind FROM alerts"))
        apps = c.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        events = c.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        audited = c.execute("SELECT COUNT(*) FROM events e WHERE EXISTS (SELECT 1 FROM audit a WHERE a.ts=e.ts AND a.target=COALESCE(e.app_id, e.item_id))").fetchone()[0]
        demo = {"applications": apps, "messages": sum(kinds.values()), "by_kind": dict(kinds), "per_application": round(sum(kinds.values()) / max(1, apps), 1),
                "movements": events, "movements_logged": audited, "audit_entries": c.execute("SELECT COUNT(*) FROM audit").fetchone()[0]}
        sys.path.insert(0, str(ROOT / "backend"))
        rows = [dict(r) for r in c.execute("SELECT * FROM audit ORDER BY seq")]
        import hashlib
        prev, ok = "0" * 64, True
        for r in rows:
            h = hashlib.sha256("|".join([str(r["seq"]), r["ts"], r["actor"], r["role"], r["action"], r["target"], r["payload"], prev]).encode()).hexdigest()
            if r["prev_hash"] != prev or r["hash"] != h:
                ok = False
                break
            prev = r["hash"]
        demo["chain_ok"] = ok
    return {"real": real, "demo": demo}


def main() -> None:
    db.conn()
    out = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    out["routing"] = routing()
    out["rules"] = rules()
    out["replay"] = replay()
    out.update(real_and_demo())
    (ROOT / "data" / "eval_report.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    m = {x["name"]: x for x in out["replay"]["methods"]}
    print(f"routing {out['routing']['passed']}/{out['routing']['cases']} · rules {out['rules']['passed']}/{out['rules']['cases']}")
    print(f"replay: {out['replay']['applications']} applications, {out['replay']['missed']} decided after the date")
    for x in out["replay"]["methods"]:
        print(f"  {x['name']}: warned {x['share_warned']}% of misses (≥21 days ahead: {x['share_warned_21']}%; while still saveable: {x['share_saveable']}%), median {x['median_lead']} days ahead, "
              f"precision {x['precision']}%, false alarms {x['false_alarms']}% of on-time applications")
    print("real:", {k: v for k, v in out["real"].items() if k != "examples"})
    print("demo:", out.get("demo"))
    bad = [r for r in out["routing"]["rows"] + out["rules"]["rows"] if not r["ok"]]
    for r in bad[:10]:
        print("FAILED", r)


if __name__ == "__main__":
    main()
