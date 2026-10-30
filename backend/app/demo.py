"""Test data for the 2027-28 approval cycle, plus the real public data shipped in data/real/.

The cycle is simulated day by day, from 1 July 2026 to the demo date, through the same workflow engine the
officers use: every step, reminder and escalation in the database happened in the simulation on the date it
shows. A few planted cases are scripted so the demo has clear examples. Real institutions get no simulated
activity; only what their public letters and postings say.
"""
from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from datetime import date, timedelta

from . import alerts, audit, clock, compliance, db, engine, settings
from .clock import add_months, d, iso
from .config import REAL

START = date(2026, 7, 1)

CITIES = {
    "Central": [("Indore", "Madhya Pradesh"), ("Bhopal", "Madhya Pradesh"), ("Jabalpur", "Madhya Pradesh"), ("Gwalior", "Madhya Pradesh"),
                ("Raipur", "Chhattisgarh"), ("Bilaspur", "Chhattisgarh"), ("Ujjain", "Madhya Pradesh"), ("Sagar", "Madhya Pradesh")],
    "Northern": [("Lucknow", "Uttar Pradesh"), ("Kanpur", "Uttar Pradesh"), ("Varanasi", "Uttar Pradesh"), ("Ghaziabad", "Uttar Pradesh"),
                 ("Dehradun", "Uttarakhand"), ("Prayagraj", "Uttar Pradesh"), ("Agra", "Uttar Pradesh"), ("Gorakhpur", "Uttar Pradesh")],
    "North-Western": [("Mohali", "Punjab"), ("Ludhiana", "Punjab"), ("Karnal", "Haryana"), ("Gurugram", "Haryana"), ("Delhi", "Delhi"),
                      ("Jaipur", "Rajasthan"), ("Jodhpur", "Rajasthan"), ("Shimla", "Himachal Pradesh")],
    "North-Eastern": [("Guwahati", "Assam"), ("Shillong", "Meghalaya"), ("Silchar", "Assam"), ("Agartala", "Tripura")],
    "Eastern": [("Kolkata", "West Bengal"), ("Durgapur", "West Bengal"), ("Bhubaneswar", "Odisha"), ("Ranchi", "Jharkhand"),
                ("Patna", "Bihar"), ("Cuttack", "Odisha")],
    "South-Central": [("Hyderabad", "Telangana"), ("Warangal", "Telangana"), ("Vijayawada", "Andhra Pradesh"),
                      ("Visakhapatnam", "Andhra Pradesh"), ("Guntur", "Andhra Pradesh"), ("Tirupati", "Andhra Pradesh")],
    "Southern": [("Chennai", "Tamil Nadu"), ("Coimbatore", "Tamil Nadu"), ("Madurai", "Tamil Nadu"), ("Hosur", "Tamil Nadu"),
                 ("Tiruchirappalli", "Tamil Nadu"), ("Salem", "Tamil Nadu"), ("Puducherry", "Puducherry")],
    "South-Western": [("Bengaluru", "Karnataka"), ("Mysuru", "Karnataka"), ("Belagavi", "Karnataka"), ("Mangaluru", "Karnataka"),
                      ("Kochi", "Kerala"), ("Thiruvananthapuram", "Kerala"), ("Kozhikode", "Kerala")],
    "Western": [("Pune", "Maharashtra"), ("Mumbai", "Maharashtra"), ("Nagpur", "Maharashtra"), ("Nashik", "Maharashtra"),
                ("Ahmedabad", "Gujarat"), ("Vadodara", "Gujarat"), ("Surat", "Gujarat"), ("Panaji", "Goa")],
}
REGION_WEIGHT = {"South-Western": 14, "Southern": 14, "Western": 15, "South-Central": 14, "Northern": 12, "Central": 10,
                 "North-Western": 9, "Eastern": 8, "North-Eastern": 4}
# Deliberately invented names (unusual compounds), so no simulated activity is attached to a real college.
PRE = ["Kesar", "Neel", "Shakti", "Tejas", "Ratna", "Jala", "Kaveri", "Vana", "Hem", "Swarna", "Megh", "Chandra", "Surya", "Amrut",
       "Sindhu", "Anand", "Dev", "Kanak", "Tamra", "Akash", "Harit", "Shweta", "Vasu", "Nirmal", "Pushpa", "Mriga", "Sahasra",
       "Kalpa", "Nava", "Ila", "Vindhya", "Tunga", "Sharav", "Mahi", "Prabhat", "Saras", "Mandar", "Kamal", "Shail", "Indu"]
SUF = ["veni", "kund", "varna", "parvat", "taranga", "prabha", "giri", "dhara", "shikhar", "deep", "vani", "kunj", "teer",
       "vihar", "mala", "jyoti", "ghati", "vatika", "vardhan", "tat", "kshetra", "rekha", "pushp", "chhaya"]
TYPES = {   # suffix, programme group, weight
    "IT": ("Institute of Technology", "Engineering", 26), "CE": ("College of Engineering", "Engineering", 30),
    "IET": ("Institute of Engineering and Technology", "Engineering", 12), "IM": ("Institute of Management", "Management", 14),
    "PO": ("Polytechnic", "Engineering", 12), "CA": ("College of Computer Applications", "Computer Applications", 6),
}
UG = [("Computer Science and Engineering", [60, 120, 180, 240]), ("Information Technology", [60, 120]),
      ("Electronics and Communication Engineering", [60, 120]), ("Electrical and Electronics Engineering", [60]),
      ("Mechanical Engineering", [60, 120]), ("Civil Engineering", [60]), ("Artificial Intelligence and Data Science", [60, 120]),
      ("Computer Science and Engineering (AI and ML)", [60, 120])]
DIPLOMA = ["Civil Engineering", "Mechanical Engineering", "Electrical Engineering", "Computer Engineering", "Electronics Engineering"]
# Deficiency wording as it appears in real approval letters and committee reports.
SD_DEFS = ["Faculty Deficiency", "Computer Centre", "Library & Reading Room", "Laboratory", "Classroom", "Tutorial Room", "Seminar Hall",
           "Establishment: Internal Committee(IC)", "Establishment: Committee for SC/ST", "Estb: Grievance Redressal Committee/OMBUDSMAN",
           "Constitution of Anti-Ragging Squad", "Implementation of PARAKH", "Internship", "Application S/W", "PCs to Student ratio"]
SCR_DEFS = ["Land use / conversion certificate not produced", "Building plan not approved by the competent authority",
            "Built-up area short of Annexure-3 norms", "Faculty Deficiency", "Affidavit not in the prescribed format",
            "Fire Safety Certificate not valid", "Bank certificate (Format 3) not produced", "Library titles and volumes short of norms"]
EVC_DEFS = ["Laboratory equipment short of the curriculum", "Computer Centre: PCs to student ratio", "Library: journals not subscribed",
            "Classrooms fewer than required for the intake", "Faculty appointed fewer than the cadre ratio",
            "Barrier-free access not provided", "Girls' common room not available"]
NATURE_WEIGHT = {"eoa_self_disclosure": 52, "increase_intake": 13, "new_programme": 9, "course_change": 4, "closure_programme": 3,
                 "change_of_site": 2, "eoa_after_break": 2, "nri_seats": 2, "fn_oci_seats": 2, "name_change": 1.5, "conversion_level": 1.5,
                 "merger": 1, "integrated_dual": 1, "fpm": 0.5, "collaboration": 1, "closure_institution": 1, "women_coed": 0.5,
                 "bank_details": 1, "trust_name_change": 1, "deemed_university": 0.5, "odl_online": 1}

# Who acts for an office in the simulation (the logins in api.USERS use the same ids).
def actor_for(office: str, region: str | None = None) -> tuple[str, str]:
    if office == "RB":
        return "rb", "rb"
    if office.startswith("RO:"):
        return ("ro", "ro") if office == "RO:Central" else (f"ro:{office[3:]}", "ro")
    if office.startswith("COMMITTEE:"):
        return "expert", "committee"
    if office == "EC":
        return "ec", "ec"
    if office.startswith("INST:"):
        return f"inst:{office[5:]}", "institution"
    return "system", "system"


def pid_for(name: str) -> str:
    return "1-00" + str(int(hashlib.sha256(name.encode()).hexdigest(), 16))[:8]


class Builder:
    def __init__(self, seed: int = 2027):
        self.rng = random.Random(seed)
        self.T = clock.today()
        self.script: dict[date, list] = defaultdict(list)
        self.submissions: dict[date, list] = defaultdict(list)
        self.planted_pids: set[str] = set()
        self.planted_apps: dict[str, str] = {}     # key -> application id
        self.pid: dict[str, str] = {}              # planted key -> pid
        self.plan: dict[str, tuple] = {}           # app id -> (step id, phase, act on)
        self.item_plan: dict[str, tuple] = {}      # item id -> (status, act on, what)
        self.fate: dict[str, str] = {}             # prior-cycle undertaking -> on_time / late / never
        self.names: set[str] = set()

    # -------------------------------------------------------------------------------- helpers
    def tri(self, lo: float, hi: float, mode: float) -> int:
        return int(round(self.rng.triangular(lo, hi, mode)))

    def at(self, when: str, fn) -> None:
        self.script[d(when)].append(fn)

    def institution(self, name: str, region: str, city: str, state: str, group: str, ownership: str = "Private-Self Financing",
                    land: str = "own", lease_until: str | None = None, building_year: int | None = None, programmes: list | None = None,
                    est_year: int | None = None, extra: dict | None = None) -> str:
        pid = pid_for(name)
        programmes = programmes or self.programmes(group)
        db.insert("institutions", {"pid": pid, "name": name, "city": city, "state": state, "region": region,
                                   "inst_type": ownership, "trust": self.rng.choice(["Shiksha Prasar Samiti", "Vidya Vikas Trust",
                                   "Gyan Jyoti Educational Society", "Lok Kalyan Shikshan Sanstha", "Sarvodaya Education Trust",
                                   "Pragati Shiksha Mandal"]) if ownership.startswith("Private") else f"Government of {state}",
                                   "est_year": est_year or self.rng.randint(1985, 2016), "ownership": ownership, "land": land,
                                   "lease_until": lease_until, "building_year": building_year or self.rng.randint(1978, 2018),
                                   "programmes": programmes, "source": "test", "extra": extra or {}})
        self.names.add(name)
        return pid

    def programmes(self, group: str) -> list[dict]:
        r = self.rng
        if group == "Management":
            out = [{"level": "POST GRADUATE", "program": "MANAGEMENT", "course": "Master of Business Administration", "years": 2, "intake": r.choice([60, 120, 180])}]
            if r.random() < .5:
                out.append({"level": "UNDER GRADUATE", "program": "MANAGEMENT", "course": "Bachelor of Business Administration", "years": 3, "intake": 60})
            return out
        if group == "Computer Applications":
            return [{"level": "UNDER GRADUATE", "program": "COMPUTER APPLICATIONS", "course": "Bachelor of Computer Applications", "years": 3, "intake": r.choice([60, 120])},
                    {"level": "POST GRADUATE", "program": "COMPUTER APPLICATIONS", "course": "Master of Computer Applications", "years": 2, "intake": 60}]
        if group == "Diploma":
            return [{"level": "DIPLOMA", "program": "ENGINEERING AND TECHNOLOGY", "course": c, "years": 3, "intake": 60} for c in r.sample(DIPLOMA, r.randint(3, 5))]
        out = [{"level": "UNDER GRADUATE", "program": "ENGINEERING AND TECHNOLOGY", "course": c, "years": 4, "intake": r.choice(sizes)}
               for c, sizes in r.sample(UG, r.randint(4, 7))]
        if r.random() < .45:
            out.append({"level": "POST GRADUATE", "program": "ENGINEERING AND TECHNOLOGY", "course": "M.Tech Computer Science and Engineering", "years": 2, "intake": 18})
        if r.random() < .25:
            out.append({"level": "POST GRADUATE", "program": "MANAGEMENT", "course": "Master of Business Administration", "years": 2, "intake": 60})
        return out

    def document(self, pid: str, doc_type: str, issued: date, valid_until: date | None, number: str | None = None) -> None:
        n = db.q1("SELECT COUNT(*) AS n FROM documents")["n"] + 1
        issuer = {"fire_noc": "State Fire and Emergency Services", "structural_stability": "Registered structural engineer",
                  "occupancy": "Municipal / development authority", "lease_deed": "Sub-Registrar (registered lease)"}[doc_type]
        db.insert("documents", {"id": f"D-{n:05d}", "pid": pid, "doc_type": doc_type, "number": number or f"{doc_type[:3].upper()}/{issued.year}/{n:04d}",
                                "issuer": issuer, "issued_on": iso(issued), "valid_until": iso(valid_until), "status": "current", "source": "test"})

    def standard_documents(self, pid: str, building_year: int, land: str, lease_until: str | None, far: bool = False) -> None:
        r = self.rng
        if far:
            vu = date(2028, r.randint(1, 12), r.randint(1, 28))
        else:
            vu = START + timedelta(days=r.randint(40, 1100))
        self.document(pid, "fire_noc", add_months(vu, -24), vu)
        self.document(pid, "occupancy", date(building_year, r.randint(1, 12), r.randint(1, 28)), None)
        if building_year <= self.T.year - 30:
            issued = date(2022, 1, 1) + timedelta(days=r.randint(0, 1500)) if not far else date(2024, r.randint(1, 12), r.randint(1, 28))
            self.document(pid, "structural_stability", issued, add_months(issued, 60))
        if land == "lease" and lease_until:
            self.document(pid, "lease_deed", date(int(lease_until[:4]) - 30, 7, 1), d(lease_until))

    def name(self, kind: str) -> str:
        for _ in range(500):
            stem = self.rng.choice(PRE) + self.rng.choice(SUF)
            n = f"{stem} {TYPES[kind][0]}"
            if n not in self.names and stem not in ("Kesarveni", "Shaktikund", "Tejasvarna", "Ratnaparvat", "Jalataranga",
                                                    "Kaveriprabha", "Hemshikhar", "Swarnadeep", "Narmadatat"):
                return n
        raise RuntimeError("ran out of names")

    # -------------------------------------------------------------------------------- real data
    def load_real(self) -> dict:
        insts = json.loads((REAL / "institutions.json").read_text(encoding="utf-8"))
        n_items = 0
        for i in insts:
            gov = any(k in (i["inst_type"] or "") for k in ("Govt", "Government", "Govemment", "Central University", "State Government"))
            db.insert("institutions", {"pid": i["pid"], "name": i["name"], "city": None, "state": i["state"], "region": i["region"],
                                       "inst_type": i["inst_type"], "trust": i["trust"], "est_year": i["est_year"],
                                       "ownership": "Government" if gov else "Private", "land": None, "programmes": i["programmes"],
                                       "source": "public", "extra": {"address": i["address"]}})
            by_ay = {l["ay"]: l for l in i["letters"]}
            for l in i["letters"]:
                db.insert("letters", {"pid": i["pid"], "ay": l["ay"], "kind": l["kind"], "application_no": l["application_no"],
                                      "issued_on": l["issued_on"], "printed_on": l["printed_on"], "deficiencies": l["deficiencies"],
                                      "courses": {"n": l["courses"], "intake": l["intake"], "new": l["new_courses"], "comply_within": l["comply_within"]},
                                      "source": "public", "source_url": l["source_url"], "sha256": l["sha256"]})
                if not l["deficiencies"] or not l["issued_on"]:
                    continue
                cw = l["comply_within"]
                due = (add_months(d(l["issued_on"]), cw["n"] * (12 if cw["unit"] == "years" else 1)) if cw and cw["n"] else None)
                y = int(l["ay"][:4]) + 1
                nxt = by_ay.get(f"{y}-{str(y + 1)[2:]}")
                if nxt is None:
                    real, status = "No later letter in the public copies", "open"
                elif set(l["deficiencies"]) & set(nxt["deficiencies"]):
                    same = sorted(set(l["deficiencies"]) & set(nxt["deficiencies"]))
                    real, status = f"Noted again in the {nxt['ay']} letter: {'; '.join(same)}", "open"
                else:
                    real, status = f"Not noted in the {nxt['ay']} letter", "closed"
                within = f"{cw['n']} {cw['unit']}" if cw else "not stated in the parsed text"
                compliance.create("undertaking", i["pid"], f"Comply with {len(l['deficiencies'])} deficiencies noted in the {l['ay']} EoA letter",
                                  due, d(l["issued_on"]), "EOA_LETTER", "Noted again as a deficiency in the next year's letter (Cl. 2.25 c)", "RB",
                                  cond="letter_deficiencies", detail="; ".join(l["deficiencies"]), source="public", source_url=l["source_url"],
                                  status=status, extra={"real_status": real, "comply_within": within, "letter_ay": l["ay"],
                                                        "quote": (cw or {}).get("text"), "next_ay": nxt["ay"] if nxt else None})
                n_items += 1
        for doc in json.loads((REAL / "documents.json").read_text(encoding="utf-8")):
            n = db.q1("SELECT COUNT(*) AS n FROM documents")["n"] + 1
            db.insert("documents", {"id": f"D-{n:05d}", "pid": doc["pid"], "doc_type": doc["doc_type"], "issued_on": doc.get("issued_on"),
                                    "valid_until": doc.get("valid_until"), "status": "posted", "note": doc["note"], "source": "public",
                                    "source_url": doc["source_url"]})
        return {"institutions": len(insts), "letters": sum(len(i["letters"]) for i in insts), "undertakings": n_items}

    # -------------------------------------------------------------------------------- test institutions
    def make_institutions(self, n_existing: int = 165, n_new: int = 18) -> None:
        r = self.rng
        regions = list(REGION_WEIGHT)
        for k in range(n_existing + n_new):
            new = k >= n_existing
            region = r.choices(regions, weights=[REGION_WEIGHT[x] for x in regions])[0]
            city, state = r.choice(CITIES[region])
            kind = r.choices(list(TYPES), weights=[t[2] for t in TYPES.values()])[0]
            group = "Diploma" if kind == "PO" else TYPES[kind][1]
            name = self.name(kind)
            own = r.choices(["Private-Self Financing", "Government", "Govt aided"], weights=[76, 14, 10])[0] if not new else "Private-Self Financing"
            land = "lease" if r.random() < .14 else "own"
            lease_until = iso(date(r.randint(2032, 2062), r.choice([3, 6, 9, 12]), 30)) if land == "lease" else None
            by = r.randint(1976, 2019) if not new else r.randint(2024, 2026)
            pid = self.institution(name, region, city, state, group, own, land, lease_until, by, est_year=2027 if new else None)
            if new:
                self.submissions[self.window_day("new_institution", region)].append((pid, "new_institution", {"programme": group if group != "Diploma" else "Engineering", "level": "Diploma" if group == "Diploma" else "UG"}))
                continue
            self.standard_documents(pid, by, land, lease_until)
            self.prior_letter(pid)
            nature = r.choices(list(NATURE_WEIGHT), weights=list(NATURE_WEIGHT.values()))[0]
            self.submissions[self.window_day(nature, region)].append((pid, nature, self.app_detail(nature, group)))
        # every nature in APH Table 2.3 appears at least once
        used = {n for v in self.submissions.values() for (_, n, _) in v}
        pool = [(day, i) for day, v in self.submissions.items() for i, x in enumerate(v) if x[1] == "eoa_self_disclosure"]
        r.shuffle(pool)
        for nature in NATURE_WEIGHT:
            if nature not in used and pool:
                day, i = pool.pop()
                pid, _, _ = self.submissions[day][i]
                self.submissions[day][i] = (pid, nature, self.app_detail(nature, "Engineering"))

    def window_day(self, nature: str, region: str) -> date:
        w = engine.window_of(nature, region)
        a, b = d(w["from"]), d(w["to"])
        return a + timedelta(days=self.rng.randint(0, (b - a).days))

    def app_detail(self, nature: str, group: str) -> dict:
        r = self.rng
        lvl = "Diploma" if group == "Diploma" else "UG"
        prog = "Engineering" if group == "Diploma" else group
        if nature == "increase_intake":
            c, sizes = r.choice(UG)
            return {"course": c, "from": 60, "to": r.choice([120, 180]), "programme": prog, "level": lvl}
        if nature == "new_programme":
            return {"course": r.choice(["M.Tech Artificial Intelligence", "MBA", "MCA", "B.Tech Robotics and Automation"]), "programme": prog, "level": r.choice(["UG", "PG"])}
        return {"programme": prog, "level": lvl}

    def prior_letter(self, pid: str, issued: date | None = None, defs: list | None = None) -> None:
        """The institution's approval for 2026-27 (test data), with deficiencies to comply within six months."""
        r = self.rng
        issued = issued or date(2026, 3, 20) + timedelta(days=r.randint(0, 100))
        if defs is None:
            defs = r.sample(SD_DEFS, r.randint(1, 3)) if r.random() < .25 else []
        db.insert("letters", {"pid": pid, "ay": "2026-27", "kind": "Extension of Approval (EoA)", "application_no": f"1-4{r.randint(10**9, 10**10 - 1)}",
                              "issued_on": iso(issued), "printed_on": iso(issued + timedelta(days=r.randint(1, 9))), "deficiencies": defs,
                              "courses": {"comply_within": {"n": 6, "unit": "months"}}, "source": "test"})
        if defs:
            it = compliance.create("undertaking", pid, f"Comply with {len(defs)} deficiencies noted in the 2026-27 EoA letter", add_months(issued, 6),
                                   issued, "EOA_LETTER", settings.get()["conditions"]["letter_deficiencies"]["consequence"], "RB",
                                   cond="letter_deficiencies", detail="; ".join(defs), extra={"carry_forward": True})
            self.fate[it["id"]] = r.choices(["on_time", "late", "never"], weights=[58, 22, 20])[0]

    # -------------------------------------------------------------------------------- the simulated people
    def carried_for(self, pid: str, on: date) -> list[dict]:
        """Open conditions of the previous approval: they must be met before the next EoA (Cl. 2.25 c)."""
        rows = db.q("SELECT * FROM items WHERE pid=? AND kind='undertaking' AND source='test' AND status IN ('open','rejected')", (pid,))
        return [{"item_id": x["id"], "title": x["title"], "detail": x["detail"], "due_on": x["due_on"]} for x in rows
                if (db.unj(x["extra"], {}) or {}).get("carry_forward")]

    def act_date(self, a: dict, step: dict, day: date) -> date | None:
        st, ph = step["stage"], step["phase"]
        if st == "self_disclosure":
            return day + timedelta(days=self.tri(1, 11, 4))
        if st in engine.COMMITTEES and ph == "to_schedule":
            start = max(day, d(engine.window_of(a["nature"], a["region"])["scrutiny_from"]))
            if st == "evc":
                return start + timedelta(days=self.tri(3, 30, 12) if a["region"] == "Central" else self.tri(1, 20, 7))
            if st == "scrutiny":
                return start + timedelta(days=self.tri(1, 26, 9))
            return start + timedelta(days=self.tri(1, 13, 5))
        if ph == "awaiting_video":
            due = d(step["due_on"])
            return max(day, due - timedelta(days=self.tri(0, 6, 2))) if self.rng.random() < .88 else due + timedelta(days=self.tri(2, 10, 4))
        if ph == "scheduled":
            m = d(step["meeting_on"])
            return max(day, m + timedelta(days=self.tri(0, 2.4, 1) if self.rng.random() < .93 else self.tri(4, 12, 6)))
        if st == "compliance":
            return day + timedelta(days=self.tri(3, 32, 11))
        if st in ("ec", "council"):
            return max(day, d(step["due_on"]))
        if st == "appeal":
            return day + timedelta(days=self.tri(1, 6, 3)) if self.rng.random() < .6 else None
        return None

    def act(self, a: dict, step: dict, day: date) -> None:
        r = self.rng
        st, ph = step["stage"], step["phase"]
        actor, role = actor_for(step["holder"], a["region"])
        if st == "self_disclosure":
            carried = [c for c in db.unj(a["carried"], []) if db.q1("SELECT status FROM items WHERE id=?", (c["item_id"],))["status"] in ("open", "rejected")]
            defs = [f"{c['detail']} (carried from the 2026-27 approval)" for c in carried]
            if r.random() < .22:
                defs += r.sample(SD_DEFS, r.randint(1, 3))
            engine.record_outcome(a["id"], day, "deficient" if defs else "in_order", defs, "", actor, role)
        elif st in engine.COMMITTEES and ph == "to_schedule":
            cfg = settings.stage(st)
            # committee calendars fill up: the first free date is often weeks away
            spread = {"scrutiny": (0, 75, 28), "evc": (0, 45, 16), "shc": (0, 30, 10), "re_scrutiny": (0, 20, 6), "sac": (0, 12, 4)}[st]
            meeting = day + timedelta(days=cfg.get("lead", 7) + self.tri(*spread))
            mode = "online" if (st != "evc" or r.random() < .72) else "physical"
            engine.schedule(a["id"], day, meeting, mode, actor, role)
        elif ph == "awaiting_video":
            engine.video_uploaded(a["id"], day, "https://example.org/facilities-video", f"inst:{a['pid']}", "institution")
        elif ph == "scheduled":
            if st == "sac":
                res = r.choices(["recommend", "not_recommend", "fresh_evc"], weights=[55, 35, 10 if not any(s["stage"] == "evc" and s["attempt"] > 1 for s in db.q("SELECT stage, attempt FROM steps WHERE app_id=?", (a["id"],))) else 0])[0]
                engine.record_outcome(a["id"], day, res, [], "", actor, role)
                return
            p = {"scrutiny": .4, "re_scrutiny": .18, "evc": .25, "shc": .35}[st]
            defs = []
            if st == "scrutiny":
                carried = [c for c in db.unj(a["carried"], []) if db.q1("SELECT status FROM items WHERE id=?", (c["item_id"],))["status"] in ("open", "rejected")]
                defs = [f"{c['detail']} (carried from the 2026-27 approval)" for c in carried]
            if r.random() < p:
                defs += r.sample(EVC_DEFS if st in ("evc", "shc") else SCR_DEFS, r.randint(1, 3))
            if st in ("re_scrutiny", "shc") and defs:
                defs = defs[:1]
            engine.record_outcome(a["id"], day, "deficient" if defs else "in_order", defs, "", actor, role)
        elif st == "compliance":
            engine.submit_compliance(a["id"], day, "Compliance report and documents uploaded", f"inst:{a['pid']}", "institution")
        elif st in ("ec", "council"):
            defs = db.unj(a["deficiencies"], []) or []
            sd = settings.nature(a["nature"])["route"] == ["self_disclosure"]
            if not defs:
                dec = "reject" if (a["nature"] == "new_institution" and r.random() < .04) else "approve"
            elif sd:
                dec = "approve" if r.random() < .75 else "lod"
            else:
                dec = "lod" if r.random() < .8 else "approve"
            if st == "council":
                dec = "approve" if r.random() < .6 else "reject"
            conds = [{"key": c["key"], "detail": c.get("detail", "")} for c in compliance.suggest_conditions(a)] if dec == "approve" else []
            engine.decide(a["id"], day, dec, "", "ec", "ec", conds)
        elif st == "appeal":
            engine.file_appeal(a["id"], day, "Compliance documents submitted with the appeal", f"inst:{a['pid']}", "institution")

    def random_people(self, day: date) -> None:
        rows = db.q("SELECT a.*, s.id AS sid FROM applications a JOIN steps s ON s.id=a.step_id WHERE s.closed_on IS NULL AND a.source='test'")
        planted = set(self.planted_apps.values())
        for row in rows:
            if row["id"] in planted:
                continue
            step = db.q1("SELECT * FROM steps WHERE id=?", (row["sid"],))
            key = (step["id"], step["phase"])
            p = self.plan.get(row["id"])
            if not p or p[:2] != key:
                when = self.act_date(row, step, day)
                self.plan[row["id"]] = (*key, when)
                p = self.plan[row["id"]]
            if p[2] and p[2] <= day:
                self.act(engine.app(row["id"]), step, day)

    def compliance_people(self, day: date) -> None:
        r = self.rng
        for it in db.q("SELECT * FROM items WHERE source='test' AND status IN ('open','rejected','submitted')"):
            if it["pid"] in self.planted_pids:
                continue
            p = self.item_plan.get(it["id"])
            if not p or p[0] != it["status"]:
                due = d(it["due_on"])
                if it["status"] == "submitted":
                    when = day + timedelta(days=self.tri(1, 14, 4))
                elif it["kind"] == "document":
                    when = max(day, due - timedelta(days=self.tri(-25, 75, 20)))
                elif it["kind"] == "deposit":
                    when = day + timedelta(days=self.tri(2, 32, 9))
                elif it["kind"] == "lease":
                    blk = (db.unj(it["extra"], {}) or {}).get("block") or {}
                    when = due - timedelta(days=self.tri(30, 400, 120)) if blk.get("blocked_ay", "9999") <= "2029-30" else None
                    when = max(day, when) if when else None
                else:
                    fate = self.fate.get(it["id"], "on_time" if r.random() < .7 else "late")
                    when = {"on_time": due - timedelta(days=self.tri(5, 60, 20)), "late": due + timedelta(days=self.tri(5, 70, 25)), "never": None}[fate]
                    when = max(day, when) if when else None
                if it["status"] == "rejected":
                    when = day + timedelta(days=self.tri(3, 12, 6))
                self.item_plan[it["id"]] = (it["status"], when)
                p = self.item_plan[it["id"]]
            if not p[1] or p[1] > day:
                continue
            if it["status"] == "submitted":
                who, role = actor_for(it["holder"])
                ok = r.random() < .94
                compliance.verify(it["id"], day, ok, "" if ok else "The copy uploaded is not legible; upload a clear copy", who, role)
            else:
                extra = None
                if it["kind"] == "document":
                    extra = {"new_document": {"doc_type": it["doc_type"], "issued_on": iso(day), "valid_until": iso(add_months(day, r.choice([12, 24, 36]))
                             if it["doc_type"] != "structural_stability" else add_months(day, 60))}}
                if it["kind"] == "lease":
                    extra = {"new_document": {"doc_type": "lease_deed", "issued_on": iso(day), "valid_until": iso(date(day.year + 30, 6, 30))}}
                compliance.submit(it["id"], day, "Uploaded", f"inst:{it['pid']}", "institution", extra=extra)

    # -------------------------------------------------------------------------------- planted cases
    def plant(self) -> None:
        P = self.pid
        B = self.institution

        def eng(pid_key, *a, **k):
            P[pid_key] = B(*a, **k)
            self.planted_pids.add(P[pid_key])
            return P[pid_key]

        def submit(key, pid_key, when, nature, detail):
            def fn(day):
                a = engine.create_application(P[pid_key], nature, day, db.q1("SELECT region FROM institutions WHERE pid=?", (P[pid_key],))["region"],
                                              detail_=detail, carried=self.carried_for(P[pid_key], day))
                self.planted_apps[key] = a["id"]
            self.at(when, fn)

        A = self.planted_apps
        def sched(key, when, meeting, mode="online", who=("rb", "rb")):
            self.at(when, lambda day: engine.schedule(A[key], day, d(meeting), mode, *who))
        def out(key, when, result, defs=(), who=("expert", "committee"), remarks=""):
            self.at(when, lambda day: engine.record_outcome(A[key], day, result, list(defs), remarks, *who))
        def comply(key, pid_key, when, note):
            self.at(when, lambda day: engine.submit_compliance(A[key], day, note, f"inst:{P[pid_key]}", "institution"))
        def decide(key, when, dec, conds=(), remarks=""):
            self.at(when, lambda day: engine.decide(A[key], day, dec, remarks, "ec", "ec", [{"key": c} for c in conds]))
        ro = ("ro", "ro")

        # 1. Kesarveni: EVC waiting with the Regional Office; at risk; reaches senior management today.
        eng("kes", "Kesarveni Institute of Technology", "Central", "Indore", "Madhya Pradesh", "Engineering", building_year=2008, est_year=2008,
            programmes=[{"level": "UNDER GRADUATE", "program": "ENGINEERING AND TECHNOLOGY", "course": c, "years": 4, "intake": n} for c, n in
                        [("Computer Science and Engineering", 120), ("Electronics and Communication Engineering", 60), ("Mechanical Engineering", 60),
                         ("Civil Engineering", 60), ("Artificial Intelligence and Data Science", 60)]])
        self.standard_documents(P["kes"], 2008, "own", None, far=True)
        self.prior_letter(P["kes"], date(2026, 4, 22), [])
        submit("kes", "kes", "2026-11-12", "increase_intake", {"course": "Computer Science and Engineering", "from": 120, "to": 180, "programme": "Engineering", "level": "UG"})
        sched("kes", "2027-01-11", "2027-01-21")
        out("kes", "2027-01-22", "deficient", ["Faculty Deficiency", "Computer Centre: PCs to student ratio"])
        comply("kes", "kes", "2027-03-22", "Appointment orders for 9 faculty and purchase order for 120 PCs uploaded")
        sched("kes", "2027-04-08", "2027-04-17")
        out("kes", "2027-04-19", "in_order")

        # 2. Neelkamal Tarai (new institution): compliance overdue with the institution; needs fast-tracking.
        eng("neel", "Neelkamal Tarai Institute of Technology", "Northern", "Lucknow", "Uttar Pradesh", "Engineering", building_year=2026, est_year=2027)
        submit("neel", "neel", "2026-12-18", "new_institution", {"programme": "Engineering", "level": "UG"})
        sched("neel", "2027-03-01", "2027-03-15")
        out("neel", "2027-03-16", "deficient", ["Land use / conversion certificate not produced", "Building plan not approved by the competent authority",
                                                "Fire Safety Certificate not valid"])

        # 3. Narmadatat: leased land; live lease equals the longest course, so EoA for 2027-28 is blocked until extended.
        eng("narm", "Narmadatat Institute of Technology", "Central", "Jabalpur", "Madhya Pradesh", "Engineering", land="lease", lease_until="2031-06-30",
            building_year=2001, est_year=2001)
        self.document(P["narm"], "fire_noc", date(2026, 2, 1), date(2028, 1, 31))
        self.document(P["narm"], "occupancy", date(2001, 5, 12), None)
        self.document(P["narm"], "lease_deed", date(2001, 7, 1), date(2031, 6, 30))
        self.prior_letter(P["narm"], date(2026, 4, 9), [])
        submit("narm", "narm", "2026-11-10", "eoa_self_disclosure", {"programme": "Engineering", "level": "UG"})
        out("narm", "2026-11-16", "deficient", ["Live lease (4.0 years) is not more than the longest course (4 years): EoA cannot be issued from 2027-28 unless the lease is extended (Cl. 2.1 e)"],
            who=("rb", "rb"))

        def narm_submits(day):
            engine.submit_compliance(A["narm"], day, "Registered lease deed extended to 30 June 2061 uploaded", f"inst:{P['narm']}", "institution")
            it = db.q1("SELECT id FROM items WHERE pid=? AND kind='lease'", (P["narm"],))
            compliance.submit(it["id"], day, "Lease deed registered on 6 May 2027, extended to 30 June 2061", f"inst:{P['narm']}", "institution",
                              extra={"new_document": {"doc_type": "lease_deed", "issued_on": "2027-05-06", "valid_until": "2061-06-30"}})
        self.at("2027-05-10", narm_submits)

        # 4. Shaktikund: leased land; EoA approved; lease runs out for 2029-30, reminders started two years ahead.
        eng("shak", "Shaktikund College of Engineering", "Central", "Bhopal", "Madhya Pradesh", "Engineering", land="lease", lease_until="2033-03-31",
            building_year=1999, est_year=1999)
        self.document(P["shak"], "fire_noc", date(2026, 1, 10), date(2028, 1, 9))
        self.document(P["shak"], "occupancy", date(1999, 4, 2), None)
        self.document(P["shak"], "lease_deed", date(2003, 4, 1), date(2033, 3, 31))
        self.prior_letter(P["shak"], date(2026, 4, 15), [])
        submit("shak", "shak", "2026-11-09", "eoa_self_disclosure", {"programme": "Engineering", "level": "UG"})
        out("shak", "2026-11-14", "in_order", who=("rb", "rb"))
        decide("shak", "2027-01-28", "approve")

        # 5. Ratnaparvat: approved on 29 Apr; security deposit not paid; penalty ladder of Cl. 2.25 (f).
        eng("ratn", "Ratnaparvat Institute of Management", "Western", "Pune", "Maharashtra", "Management", building_year=2006, est_year=2006,
            programmes=[{"level": "POST GRADUATE", "program": "MANAGEMENT", "course": "Master of Business Administration", "years": 2, "intake": 120}])
        self.standard_documents(P["ratn"], 2006, "own", None, far=True)
        self.prior_letter(P["ratn"], date(2026, 4, 18), [])
        submit("ratn", "ratn", "2026-11-27", "new_programme", {"course": "PGDM (Business Analytics)", "programme": "Management", "level": "PG"})
        sched("ratn", "2027-01-20", "2027-02-09")
        out("ratn", "2027-02-10", "in_order")
        self.at("2027-02-16", lambda day: engine.schedule(A["ratn"], day, d("2027-03-02"), "physical", "ro:Western", "ro"))
        out("ratn", "2027-03-03", "deficient", ["Library: journals not subscribed", "Computer Centre: PCs to student ratio"])
        sched("ratn", "2027-03-08", "2027-04-12")
        out("ratn", "2027-04-13", "in_order")
        decide("ratn", "2027-04-29", "approve")

        # 6. Tejasvarna: fire safety certificate expires 5 June; reminders at 90, 60 and 30 days.
        eng("tej", "Tejasvarna College of Engineering", "South-Central", "Hyderabad", "Telangana", "Engineering", building_year=2004, est_year=2004)
        self.document(P["tej"], "fire_noc", date(2025, 6, 6), date(2027, 6, 5))
        self.document(P["tej"], "occupancy", date(2004, 8, 1), None)
        self.prior_letter(P["tej"], date(2026, 5, 2), [])
        submit("tej", "tej", "2026-11-28", "eoa_self_disclosure", {"programme": "Engineering", "level": "UG"})
        out("tej", "2026-12-03", "in_order", who=("rb", "rb"))
        decide("tej", "2027-01-28", "approve")

        # 7. Jalataranga: last year's undertaking (occupancy certificate) not met, carried into this year's scrutiny, then closed.
        eng("jal", "Jalataranga College of Engineering", "South-Western", "Mysuru", "Karnataka", "Engineering", building_year=2010, est_year=2010,
            extra={"building_under_construction": True})
        self.standard_documents(P["jal"], 2010, "own", None, far=True)
        db.insert("letters", {"pid": P["jal"], "ay": "2026-27", "kind": "Extension of Approval (EoA)", "application_no": "1-4100022031",
                              "issued_on": "2026-05-20", "printed_on": "2026-05-26", "deficiencies": [], "courses": {}, "source": "test"})
        compliance.create("undertaking", P["jal"], settings.get()["conditions"]["occupancy_on_completion"]["label"], date(2026, 11, 20), date(2026, 5, 20),
                          "ANX1_OC", "Carried into next year's scrutiny as a deficiency", "RO", cond="occupancy_on_completion",
                          detail="Occupancy / Completion Certificate for the new academic block (Block C)", extra={"carry_forward": True})
        submit("jal", "jal", "2026-12-01", "increase_intake", {"course": "Civil Engineering", "from": 60, "to": 120, "programme": "Engineering", "level": "UG"})
        sched("jal", "2027-01-14", "2027-01-25")
        out("jal", "2027-01-26", "deficient", ["Occupancy / Completion Certificate for the new academic block (Block C) (carried from the 2026-27 approval)", "Faculty Deficiency"])
        comply("jal", "jal", "2027-02-08", "Occupancy certificate for Block C and faculty appointment orders uploaded")
        sched("jal", "2027-02-12", "2027-02-22")
        out("jal", "2027-02-23", "in_order")
        self.at("2027-03-01", lambda day: engine.schedule(A["jal"], day, d("2027-03-15"), "online", "ro:South-Western", "ro"))
        self.at("2027-03-12", lambda day: engine.video_uploaded(A["jal"], day, "https://example.org/jalataranga-facilities", f"inst:{P['jal']}", "institution"))
        out("jal", "2027-03-16", "in_order")
        decide("jal", "2027-04-08", "approve")

        # 8. Kaveriprabha: EVC observation sends the case back to re-scrutiny (reason recorded); report now due.
        eng("kav", "Kaveriprabha College of Engineering", "Southern", "Coimbatore", "Tamil Nadu", "Engineering", building_year=2012, est_year=2012)
        self.standard_documents(P["kav"], 2012, "own", None, far=True)
        self.prior_letter(P["kav"], date(2026, 4, 2), [])
        submit("kav", "kav", "2026-11-28", "change_of_site", {"programme": "Engineering", "level": "UG"})
        sched("kav", "2027-01-18", "2027-01-29")
        out("kav", "2027-01-30", "in_order")
        self.at("2027-02-10", lambda day: engine.schedule(A["kav"], day, d("2027-04-21"), "physical", "ro:Southern", "ro"))
        self.at("2027-04-22", lambda day: engine.revert(A["kav"], day, "re_scrutiny",
                "The EVC found that the building plan at the new site differs from the plan signed at scrutiny. Re-verify the revised plan before a fresh EVC.",
                "rb", "rb"))
        sched("kav", "2027-05-06", "2027-05-14")

        # 9. Sri Vanadurga: Letter of Deficiency on 13 May; appeal filed; Standing Appellate Committee to be fixed.
        eng("svd", "Sri Vanadurga Institute of Technology", "Southern", "Hosur", "Tamil Nadu", "Engineering", building_year=2009, est_year=2009)
        self.standard_documents(P["svd"], 2009, "own", None, far=True)
        self.prior_letter(P["svd"], date(2026, 4, 28), [])
        submit("svd", "svd", "2026-12-02", "new_programme", {"course": "B.Tech Robotics and Automation", "programme": "Engineering", "level": "UG"})
        sched("svd", "2027-01-19", "2027-01-28")
        out("svd", "2027-01-29", "in_order")
        self.at("2027-02-05", lambda day: engine.schedule(A["svd"], day, d("2027-02-19"), "online", "ro:Southern", "ro"))
        self.at("2027-02-16", lambda day: engine.video_uploaded(A["svd"], day, "https://example.org/vanadurga-facilities", f"inst:{P['svd']}", "institution"))
        out("svd", "2027-02-20", "deficient", ["Laboratory equipment short of the curriculum", "Faculty appointed fewer than the cadre ratio"])
        sched("svd", "2027-02-26", "2027-04-26")
        out("svd", "2027-04-27", "deficient", ["Faculty appointed fewer than the cadre ratio"])
        decide("svd", "2027-05-13", "lod", remarks="Faculty shortfall not met at the hearing")
        self.at("2027-05-15", lambda day: engine.file_appeal(A["svd"], day, "Appointment orders for six faculty issued on 10 May 2027", f"inst:{P['svd']}", "institution"))

        # 10. Hemshikhar (new institution): EVC fixed on time but for 8 June, too late for the last Executive Committee.
        eng("hem", "Hemshikhar Institute of Management", "Central", "Gwalior", "Madhya Pradesh", "Management", building_year=2025, est_year=2027)
        submit("hem", "hem", "2026-12-20", "new_institution", {"programme": "Management", "level": "PG"})
        sched("hem", "2027-02-20", "2027-03-03")
        out("hem", "2027-03-04", "deficient", ["Bank certificate (Format 3) not produced"])
        comply("hem", "hem", "2027-03-17", "Bank certificate in Format 3 uploaded")
        sched("hem", "2027-03-22", "2027-04-02")
        out("hem", "2027-04-03", "in_order")
        self.at("2027-04-15", lambda day: engine.schedule(A["hem"], day, d("2027-06-08"), "physical", *ro))

        # 11. Mahanadi Prabha: EVC held on 10 May, report not yet recorded.
        eng("mah", "Mahanadi Prabha Polytechnic", "Central", "Bilaspur", "Chhattisgarh", "Diploma", building_year=2003, est_year=2003)
        self.standard_documents(P["mah"], 2003, "own", None, far=True)
        self.prior_letter(P["mah"], date(2026, 5, 11), [])
        submit("mah", "mah", "2026-11-13", "increase_intake", {"course": "Computer Engineering", "from": 60, "to": 120, "programme": "Engineering", "level": "Diploma"})
        sched("mah", "2027-01-20", "2027-02-01")
        out("mah", "2027-02-02", "deficient", ["Laboratory", "Faculty Deficiency"])
        comply("mah", "mah", "2027-03-30", "Laboratory purchase orders and faculty appointment orders uploaded")
        sched("mah", "2027-04-02", "2027-04-12")
        out("mah", "2027-04-13", "in_order")
        self.at("2027-04-24", lambda day: engine.schedule(A["mah"], day, d("2027-05-10"), "physical", *ro))

        # 12. Konkan Ratna: building over 30 years old; Structural Stability Certificate valid five years, to 19 June 2027.
        eng("kon", "Konkan Ratna College of Engineering", "Western", "Mumbai", "Maharashtra", "Engineering", building_year=1988, est_year=1988)
        self.document(P["kon"], "fire_noc", date(2026, 3, 1), date(2028, 2, 28))
        self.document(P["kon"], "occupancy", date(1988, 6, 1), None)
        self.document(P["kon"], "structural_stability", date(2022, 6, 20), date(2027, 6, 19))
        self.prior_letter(P["kon"], date(2026, 4, 25), [])
        submit("kon", "kon", "2026-12-04", "eoa_self_disclosure", {"programme": "Engineering", "level": "UG"})
        out("kon", "2026-12-08", "in_order", who=("rb", "rb"))
        decide("kon", "2027-01-28", "approve")

        # 13. Swarnadeepa (new institution): approved 29 Apr subject to three conditions; deposit paid, to be verified.
        eng("swa", "Swarnadeepa Institute of Technology", "Western", "Nagpur", "Maharashtra", "Engineering", building_year=2026, est_year=2027)
        submit("swa", "swa", "2026-12-16", "new_institution", {"programme": "Engineering", "level": "UG"})
        sched("swa", "2027-02-16", "2027-02-26")
        out("swa", "2027-02-27", "in_order")
        self.at("2027-03-30", lambda day: engine.schedule(A["swa"], day, d("2027-04-12"), "physical", "ro:Western", "ro"))
        out("swa", "2027-04-13", "in_order")
        decide("swa", "2027-04-29", "approve", ["faculty_before_start", "affiliation_within_loa", "remaining_requirements"])

        def swa_pays(day):
            it = db.q1("SELECT id FROM items WHERE pid=? AND kind='deposit'", (P["swa"],))
            compliance.submit(it["id"], day, "FDR No. 0042117 for Rs 35 lakh in favour of AICTE, with Affidavit 3", f"inst:{P['swa']}", "institution")
        self.at("2027-05-12", swa_pays)

    def mark_read(self, before: date) -> None:
        """Messages older than a few days have been read by the people they went to."""
        def readers(office: str) -> list[str]:
            if office.startswith("INST:"):
                return [f"inst:{office[5:]}"]
            if office.startswith("COMMITTEE:"):
                return ["expert"]
            if office.startswith("RO:"):
                return ["ro"] if office == "RO:Central" else [f"ro:{office[3:]}"]
            return {"RB": ["rb"], "EC": ["ec"], "HEAD": ["head"]}.get(office, [])
        with db.tx() as c:
            for r in c.execute("SELECT id, to_office FROM alerts WHERE on_date < ?", (iso(before),)).fetchall():
                c.execute("UPDATE alerts SET read_by=? WHERE id=?", (json.dumps(readers(r["to_office"])), r["id"]))

    # -------------------------------------------------------------------------------- run
    def run(self, verbose: bool = True) -> dict:
        t0 = __import__("time").time()
        real = self.load_real()
        self.plant()
        self.make_institutions()
        day, n = START, 0
        while day <= self.T:
            for pid, nature, det in self.submissions.get(day, []):
                region = db.q1("SELECT region FROM institutions WHERE pid=?", (pid,))["region"]
                engine.create_application(pid, nature, day, region, detail_=det, carried=self.carried_for(pid, day))
            for fn in self.script.get(day, []):
                fn(day)
            self.random_people(day)
            self.compliance_people(day)
            n += alerts.sweep(day)["sent"]
            day += timedelta(days=1)
        for a in db.q("SELECT * FROM applications"):
            engine.refresh(a, self.T)
        self.mark_read(self.T - timedelta(days=3))
        audit.log("system", "system", "demo.seeded", "database", {"cycle": settings.get()["cycle"]["ay"], "today": iso(self.T)})
        out = {"real": real, "applications": db.q1("SELECT COUNT(*) AS n FROM applications")["n"],
               "test_institutions": db.q1("SELECT COUNT(*) AS n FROM institutions WHERE source='test'")["n"],
               "items": db.q1("SELECT COUNT(*) AS n FROM items WHERE source='test'")["n"], "alerts": n,
               "seconds": round(__import__("time").time() - t0, 1), "planted": self.planted_apps}
        if verbose:
            print(json.dumps(out, indent=1))
        return out


def build(verbose: bool = True) -> dict:
    db.reset()
    settings.invalidate()
    return Builder().run(verbose)
