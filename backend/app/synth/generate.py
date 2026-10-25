"""Generate labelled test applications for AY 2027-28 Extension of Approval (self-disclosure).

Two modes:
  demo   - 14 fictional institutions in 3 clusters with hand-designed scenarios (the demo story)
  random - N institutions with randomly injected defects (for the evaluation harness)

Ground truth for every injected defect is written to <out>/truth.json.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import math
import random
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

import piexif
import requests
from PIL import Image

from ..config import RAW, SYNTH
from ..rules import norms
from ..verify import registry
from . import names as N
from . import pki, render, tamper

AY = "2027-28"
AY_START = date(2027, 8, 1)
PHOTO_DIR = RAW / "photos"
TILE_DIR = RAW / "tiles"


# --------------------------------------------------------------------------- helpers

def _pan(rnd):
    L = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    return "".join(rnd.choice(L) for _ in range(3)) + "P" + rnd.choice(L) + f"{rnd.randint(1000, 9999)}" + rnd.choice(L)


def _person(rnd, state, gender=None):
    g = gender or rnd.choice("MF")
    first = rnd.choice(N.FIRST_M if g == "M" else N.FIRST_F)
    return first, rnd.choice(N.SURNAMES[state]), g


def _words(n: int) -> str:
    return {100: "One Hundred", 50: "Fifty", 500: "Five Hundred"}.get(n, str(n))


def _tile(lat, lon, zoom=16):
    """Fetch & stitch 2x2 OpenStreetMap tiles (cached; used once per campus)."""
    TILE_DIR.mkdir(parents=True, exist_ok=True)
    n = 2 ** zoom
    xt = (lon + 180) / 360 * n
    yt = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    x0, y0 = int(xt - 0.5), int(yt - 0.5)
    canvas = Image.new("RGB", (512, 512), (230, 230, 230))
    for dx in range(2):
        for dy in range(2):
            p = TILE_DIR / f"{zoom}_{x0 + dx}_{y0 + dy}.png"
            if not p.exists():
                try:
                    r = requests.get(f"https://tile.openstreetmap.org/{zoom}/{x0 + dx}/{y0 + dy}.png",
                                     headers={"User-Agent": "SatyapanPrototype/0.1 (SIH research prototype)"}, timeout=20)
                    if r.status_code == 200:
                        p.write_bytes(r.content)
                except Exception:  # noqa: BLE001
                    return None
            if p.exists():
                canvas.paste(Image.open(p).convert("RGB"), (dx * 256, dy * 256))
    return canvas


def _gps_exif(img_bytes: bytes, lat: float, lon: float, when: datetime, model=("samsung", "SM-A546E")) -> bytes:
    def dms(v):
        v = abs(v); d = int(v); m = int((v - d) * 60); s = round(((v - d) * 60 - m) * 60 * 100)
        return ((d, 1), (m, 1), (s, 100))
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    exif = {"0th": {piexif.ImageIFD.Make: model[0].encode(), piexif.ImageIFD.Model: model[1].encode()},
            "Exif": {piexif.ExifIFD.DateTimeOriginal: when.strftime("%Y:%m:%d %H:%M:%S").encode()},
            "GPS": {piexif.GPSIFD.GPSLatitudeRef: b"N" if lat >= 0 else b"S", piexif.GPSIFD.GPSLatitude: dms(lat),
                    piexif.GPSIFD.GPSLongitudeRef: b"E" if lon >= 0 else b"W", piexif.GPSIFD.GPSLongitude: dms(lon)}}
    b = io.BytesIO()
    im.save(b, format="JPEG", quality=88, exif=piexif.dump(exif))
    return b.getvalue()


# --------------------------------------------------------------------------- clean application

def clean_spec(idx: int, cluster: str, rnd: random.Random, used_names: set, photo_pool: list | None = None, n_photos: int = 3) -> dict:
    cl = N.CLUSTERS[cluster]
    loc, lat, lon, district = cl["localities"][idx % len(cl["localities"])]
    lat += rnd.uniform(-0.01, 0.01); lon += rnd.uniform(-0.01, 0.01)
    while True:
        founder = rnd.choice(N.FOUNDERS)
        name = f"{founder} {rnd.choice(N.INST_SUFFIX)}"
        if founder not in used_names or len(used_names) >= len(N.FOUNDERS):
            if name in used_names:
                continue
            used_names.add(founder); used_names.add(name); break
    trust = f"{founder} Educational Society"
    pid = f"1-99{rnd.randint(10_000_000, 99_999_999)}"
    est = rnd.choice([1996, 1999, 2001, 2004, 2007, 2008, 2009, 2011])
    built_year = est - rnd.choice([0, 1])
    courses = []
    for course, opts in rnd.sample(N.UG_COURSES, rnd.randint(4, 6)):
        courses.append({"level": "UNDER GRADUATE", "program": "ENGINEERING AND TECHNOLOGY", "course": course,
                        "intake": rnd.choice(opts), "affiliating_body": cl["university"]})
    if rnd.random() < 0.6:
        c, prog, opts, _ = rnd.choice(N.PG_COURSES)
        courses.append({"level": "POST GRADUATE", "program": prog, "course": c, "intake": rnd.choice(opts),
                        "affiliating_body": cl["university"]})
    fac = norms.faculty_requirement(courses)
    area = norms.area_requirement(courses)
    ter = norms.ter_required(courses, AY)
    chair_f, chair_s, chair_g = _person(rnd, cluster)
    address = f"Sy. No. {rnd.randint(20, 480)}/{rnd.randint(1, 9)}, {loc}, {district} District, {cl['city']} Region, {cluster} - {rnd.randint(500, 640)}{rnd.randint(100, 999)}"
    app_no = f"1-99{rnd.randint(100_000_000, 999_999_999)}"
    app_date = date(2026, 10, rnd.randint(1, 20))
    builtup = round(area["required_builtup"] * rnd.uniform(1.06, 1.35), 2)

    # faculty roster: required + slack, with cadre ratio met
    need, profs, assocs = fac["required"], fac["professors"], fac["associates"]
    n_fac = need + rnd.randint(1, max(2, need // 12))
    roster = []
    depts = [c["course"] for c in courses]
    for i in range(n_fac):
        f, s, g = _person(rnd, cluster)
        desig = "Professor" if i < profs + rnd.randint(0, 2) else ("Associate Professor" if i < profs + assocs + rnd.randint(1, 4) else "Assistant Professor")
        roster.append({
            "faculty_id": f"1-{rnd.randint(4_000_000_000, 9_999_999_999)}",
            "name": f"{'Dr. ' if desig != 'Assistant Professor' and rnd.random() < 0.8 else ''}{f} {s}",
            "gender": g, "dob": date(rnd.randint(1962, 1995), rnd.randint(1, 12), rnd.randint(1, 28)).isoformat(),
            "pan": _pan(rnd), "designation": desig,
            "qualification": rnd.choice(N.QUALS[desig]),
            "department": depts[i % len(depts)],
            "date_of_joining": date(rnd.randint(max(est, 2005), 2025), rnd.randint(1, 12), rnd.randint(1, 28)).isoformat(),
        })
    spec = {
        "seed": idx, "cluster": cluster,
        "institution": {"permanent_id": pid, "name": name, "trust": trust, "address": address, "state": cluster,
                        "region": cl["region"], "inst_type": "Private-Self Financing", "est_year": est,
                        "lat": lat, "lon": lon, "locality": loc, "district": district, "city": cl["city"]},
        "form": {
            "application_no": app_no, "permanent_id": pid, "category": "EOA_SELF_DISCLOSURE", "academic_year": AY,
            "application_date": app_date.isoformat(), "institution_name": name, "trust_name": trust, "address": address,
            "state": cluster, "chairperson": f"{chair_f} {chair_s}", "courses": courses,
            "builtup_area_sqm": builtup, "building_completion_year": built_year, "campus_lat": lat, "campus_lon": lon,
            "ter_txn_id": f"TER{AY[:4]}{rnd.randint(10_000_000, 99_999_999)}", "faculty": roster,
            "principal": {"name": f"Dr. {_person(rnd, cluster)[0]} {_person(rnd, cluster)[1]}", "qualification": "Ph.D", "regular": True},
        },
        "prev_approval": {"academic_year": "2026-27", "courses": [{**c, "intake_curr": c["intake"]} for c in courses]},
        "docs": {}, "photos": [], "registry": [], "truth": [],
        "_norms": {"faculty": fac, "area": area, "ter": ter},
    }
    st = cl["state_code"]
    issue_fire = app_date - timedelta(days=rnd.randint(60, 300))
    spec["docs"]["fire_noc"] = {
        "noc_no": f"{st}FS/{district[:3].upper()}/{rnd.randint(2025, 2026)}/{rnd.randint(1000, 9999)}",
        "issue_date": issue_fire, "valid_until": issue_fire + timedelta(days=365 * rnd.choice([2, 3])),
        "premises": name, "address": address, "height": rnd.choice([14.5, 17.8, 20.9]), "floors": rnd.choice(["G+3", "G+4", "G+5"]),
        "applicant": trust, "authority": cl["fire"], "authority_addr": f"District Fire Office, {district}", "district": district,
        "officer": " ".join(_person(rnd, cluster)[:2]),
    }
    oc_issue = date(built_year + 1, rnd.randint(1, 12), rnd.randint(1, 28))
    spec["docs"]["occupancy_certificate"] = {
        "cert_no": f"OC/{st}/{built_year + 1}/{rnd.randint(10000, 99999)}", "issue_date": oc_issue, "owner": trust, "premises": name,
        "address": address, "survey_no": address.split(",")[0].replace("Sy. No. ", ""), "built_up_area": builtup,
        "floors": spec["docs"]["fire_noc"]["floors"], "permit_ref": f"BP/{built_year - 1}/{rnd.randint(100, 999)}",
        "authority": cl["municipal"], "authority_addr": f"{cl['city']} Region", "officer": " ".join(_person(rnd, cluster)[:2]),
    }
    if AY_START.year - built_year > 30 or rnd.random() < 0.35:
        insp = app_date - timedelta(days=rnd.randint(100, 600))
        eng_f, eng_s, _ = _person(rnd, cluster)
        spec["docs"]["structural_stability"] = {
            "firm": f"{eng_s} Structural Consultants", "firm_addr": f"{cl['city']}", "engineer": f"{eng_f} {eng_s}",
            "engineer_reg": f"SE/{st}/{rnd.randint(1000, 9999)}", "premises": name, "address": address,
            "construction_year": built_year, "inspected": insp, "issue_date": insp + timedelta(days=7),
            "valid_until": insp + timedelta(days=7 + 365 * 5),
        }
    est_dt = datetime.combine(app_date - timedelta(days=rnd.randint(3, 20)), datetime.min.time()) + timedelta(hours=rnd.randint(10, 17))
    notary_f, notary_s, _ = _person(rnd, cluster)
    spec["docs"]["affidavit_2"] = {
        "estamp_no": f"IN-{cl['estamp_state']}{rnd.randint(10**13, 10**14 - 1)}{rnd.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}",
        "estamp_date": est_dt, "estamp_udr": f"SUBIN-{st}{rnd.randint(10**9, 10**10 - 1)}", "state": cluster,
        "state_code": st, "locality": loc, "first_party": trust, "stamp_value": 100, "stamp_words": "One Hundred",
        "deponent": f"{chair_f} {chair_s}", "deponent_parent": " ".join(_person(rnd, cluster, "M")[:2]),
        "deponent_age": rnd.randint(48, 72), "trust": trust, "city": cl["city"], "academic_year": AY, "institution": name,
        "application_date": app_date, "application_no": app_no, "built_up_area": builtup,
        "notary": f"{notary_f} {notary_s}", "notary_reg": f"{st}/N/{rnd.randint(100, 9999)}/{rnd.randint(2015, 2024)}",
        "sworn_date": est_dt.date() + timedelta(days=1), "sign_dsc": True,
    }
    spec["docs"]["ter_receipt"] = {
        "permanent_id": pid, "application_no": app_no, "institution": name, "academic_year": AY,
        "divisions": sum(norms.divisions(c["intake"]) for c in courses), "txn_id": spec["form"]["ter_txn_id"],
        "bank_ref": f"{rnd.randint(10**11, 10**12 - 1)}", "payment_date": datetime.combine(app_date, datetime.min.time()) + timedelta(hours=11),
        "amount": ter["required"],
    }
    spec["docs"]["satellite_map"] = {"institution": name, "lat": lat, "lon": lon, "address": address}
    frn = f"{rnd.randint(100000, 999999)}{rnd.choice('SWNE')}"
    mno = f"{rnd.randint(200000, 299999)}"
    signed = date(2026, rnd.randint(6, 9), rnd.randint(1, 28))
    udin = f"{str(signed.year)[2:]}{mno}{''.join(rnd.choice('ABCDEFGHJKLMNPQRSTUVWXYZ') for _ in range(6))}{rnd.randint(1000, 9999)}"
    income = rnd.randint(18, 60) * 1_00_00_000 / 10
    p_f, p_s, _ = _person(rnd, cluster)
    spec["docs"]["audited_statement"] = {
        "ca_firm": f"{p_s} & Associates", "frn": frn, "ca_addr": cl["city"], "fy_end": 2026, "trust": trust,
        "corpus": income * 1.8, "reserve": income * 0.6, "loans": income * 0.4, "liab": income * 0.2,
        "fixed": income * 2.1, "fdr": income * 0.5, "curr": income * 0.25, "cash": income * 0.15,
        "income": income, "expenditure": income * rnd.uniform(0.82, 0.97), "partner": f"CA {p_f} {p_s}", "mno": mno,
        "udin": udin, "city": cl["city"], "signed_date": signed,
    }
    # infrastructure photos: taken on campus with GPS
    # photos are drawn without replacement so no two institutions share one by accident
    if photo_pool is None:
        photo_pool = rnd.sample(sorted(p.name for p in PHOTO_DIR.glob("*.jpg")), len(list(PHOTO_DIR.glob("*.jpg"))))
    picks = [photo_pool.pop() for _ in range(min(n_photos, len(photo_pool)))]
    for i, pn in enumerate(picks):
        spec["photos"].append({"file": pn, "lat": lat + rnd.uniform(-0.0015, 0.0015), "lon": lon + rnd.uniform(-0.0015, 0.0015),
                               "when": datetime(2026, rnd.randint(7, 9), rnd.randint(1, 28), rnd.randint(9, 16), rnd.randint(0, 59)),
                               "label": pn.split("_")[0], "reused_from": None})
    return spec


def register_truth(spec: dict) -> None:
    """Issuing authorities' records for the *genuine* documents."""
    st = N.CLUSTERS[spec["cluster"]]["state_code"].lower()
    f = spec["docs"]["fire_noc"]
    spec["registry"].append((f"fire_{st}", f["noc_no"], {"premises": f["premises"], "address": f["address"], "applicant": f["applicant"],
                             "issue_date": f["issue_date"].isoformat(), "valid_until": f["valid_until"].isoformat(), "status": "ACTIVE"}))
    o = spec["docs"]["occupancy_certificate"]
    spec["registry"].append((f"oc_{st}", o["cert_no"], {"owner": o["owner"], "premises": o["premises"], "address": o["address"],
                             "built_up_area": o["built_up_area"], "issue_date": o["issue_date"].isoformat()}))
    a = spec["docs"]["affidavit_2"]
    spec["registry"].append(("estamp", a["estamp_no"], {"first_party": a["first_party"], "second_party": "All India Council for Technical Education",
                             "amount": a["stamp_value"], "issue_date": a["estamp_date"].isoformat(), "article": "Article 4 Affidavit", "status": "LOCKED"}))
    u = spec["docs"]["audited_statement"]
    spec["registry"].append(("udin", u["udin"], {"frn": u["frn"], "membership_no": u["mno"], "client": u["trust"],
                             "document": "Audit Report / Financial Statements", "date": u["signed_date"].isoformat()}))
    if "structural_stability" in spec["docs"]:
        s = spec["docs"]["structural_stability"]
        spec["registry"].append(("engineers", s["engineer_reg"], {"name": s["engineer"], "licence_valid_until": "2029-03-31", "status": "ACTIVE"}))


# --------------------------------------------------------------------------- defects

def truth(spec, code, doc=None, detail="", partner=None):
    spec["truth"].append({"code": code, "doc": doc, "detail": detail, "partner": partner})


def d_fire_expired(spec, rnd, **_):
    f = spec["docs"]["fire_noc"]
    f["issue_date"] = date(2023, rnd.randint(4, 10), rnd.randint(1, 28))
    f["valid_until"] = f["issue_date"] + timedelta(days=365 * 3)
    if f["valid_until"] >= date.fromisoformat(spec["form"]["application_date"]):
        f["valid_until"] = date.fromisoformat(spec["form"]["application_date"]) - timedelta(days=rnd.randint(20, 120))
    truth(spec, "FIRE_EXPIRED", "fire_noc", f"valid until {f['valid_until']}")


def d_fire_whiteout(spec, rnd, **_):
    """Genuine NOC expired; validity date white-boxed and retyped (incremental save)."""
    f = spec["docs"]["fire_noc"]
    f["issue_date"] = date(2022, rnd.randint(9, 12), rnd.randint(1, 28))
    f["valid_until"] = date(2025, rnd.randint(9, 12), rnd.randint(1, 28))
    forged = f["valid_until"].replace(year=2028)
    spec.setdefault("post", []).append(("fire_noc", "whiteout", render.d(f["valid_until"]), render.d(forged)))
    truth(spec, "TAMPER_WHITEOUT", "fire_noc", f"valid-until {f['valid_until']} changed to {forged}")
    truth(spec, "REGISTRY_MISMATCH", "fire_noc", "registry validity differs from document")


def d_fsr_short(spec, rnd, **_):
    need = spec["_norms"]["faculty"]["required"]
    keep = int(need * rnd.uniform(0.72, 0.88))
    spec["form"]["faculty"] = spec["form"]["faculty"][:keep]
    truth(spec, "FSR_SHORTFALL", None, f"{keep} faculty vs required {need}")


def d_cadre_short(spec, rnd, **_):
    for f in spec["form"]["faculty"]:
        if f["designation"] == "Professor":
            f["designation"] = "Assistant Professor"
    truth(spec, "CADRE_SHORTFALL", None, "no Professors in roster")


def d_ter_under(spec, rnd, **_):
    t = spec["docs"]["ter_receipt"]
    t["amount"] = round(t["amount"] * rnd.choice([0.5, 0.6, 0.75]), 2)
    truth(spec, "TER_UNDERPAID", "ter_receipt", f"paid {t['amount']}")


def d_missing(spec, rnd, doc="satellite_map", **_):
    spec["docs"].pop(doc, None)
    truth(spec, "MISSING_DOC", doc, f"{doc} not uploaded")


def d_ssc_missing_old(spec, rnd, **_):
    spec["form"]["building_completion_year"] = 1992
    spec["docs"]["occupancy_certificate"]["issue_date"] = date(1993, 6, 14)
    spec["docs"].pop("structural_stability", None)
    truth(spec, "MISSING_DOC", "structural_stability", "building > 30 years, no structural stability certificate")


def d_ssc_expired(spec, rnd, **_):
    cl = N.CLUSTERS[spec["cluster"]]
    spec["form"]["building_completion_year"] = 1994
    spec["docs"]["occupancy_certificate"]["issue_date"] = date(1995, 3, 2)
    insp = date(2020, rnd.randint(1, 8), rnd.randint(1, 28))
    eng_f, eng_s, _ = _person(rnd, spec["cluster"])
    spec["docs"]["structural_stability"] = {
        "firm": f"{eng_s} Structural Consultants", "firm_addr": cl["city"], "engineer": f"{eng_f} {eng_s}",
        "engineer_reg": f"SE/{cl['state_code']}/{rnd.randint(1000, 9999)}", "premises": spec["institution"]["name"],
        "address": spec["institution"]["address"], "construction_year": 1994, "inspected": insp,
        "issue_date": insp + timedelta(days=5), "valid_until": insp + timedelta(days=5 + 365 * 5)}
    truth(spec, "SSC_EXPIRED", "structural_stability", f"issued {insp}, 5-year validity lapsed")


def d_stamp_low(spec, rnd, **_):
    a = spec["docs"]["affidavit_2"]
    a["stamp_value"], a["stamp_words"] = 50, "Fifty"
    truth(spec, "STAMP_VALUE_LOW", "affidavit_2", "Rs 50 e-stamp instead of Rs 100")


def d_estamp_unknown(spec, rnd, **_):
    a = spec["docs"]["affidavit_2"]
    a["estamp_no"] = a["estamp_no"][:-5] + f"{rnd.randint(1000, 9999)}Z"
    spec["_skip_registry"] = spec.get("_skip_registry", []) + ["estamp"]
    truth(spec, "ESTAMP_NOT_FOUND", "affidavit_2", "certificate number not in SHCIL registry")


def d_name_mismatch(spec, rnd, **_):
    o = spec["docs"]["occupancy_certificate"]
    o["premises"] = o["premises"].replace("Institute of", "College of").replace("Engineering College", "Polytechnic College")
    if o["premises"] == spec["institution"]["name"]:
        o["premises"] = spec["institution"]["name"].split()[0] + " Degree College"
    o["owner"] = o["owner"].replace("Educational Society", "Charitable Trust")
    truth(spec, "NAME_MISMATCH", "occupancy_certificate", f"OC issued to '{o['premises']}'")


def d_oc_area_resave(spec, rnd, **_):
    """Real OC shows less area than required; edited with an online editor and re-saved."""
    o = spec["docs"]["occupancy_certificate"]
    real = round(spec["_norms"]["area"]["required_builtup"] * rnd.uniform(0.62, 0.8), 2)
    o["built_up_area"] = real
    spec.setdefault("post", []).append(("occupancy_certificate", "resave", f"{real:.2f} sq.m", f"{spec['form']['builtup_area_sqm']:.2f} sq.m"))
    truth(spec, "TAMPER_RESAVE", "occupancy_certificate", f"area {real} edited to {spec['form']['builtup_area_sqm']}")
    truth(spec, "REGISTRY_MISMATCH", "occupancy_certificate", "registry built-up area differs")


def d_intake_exceeds(spec, rnd, **_):
    c = spec["form"]["courses"][0]
    c["intake"] = c["intake"] + 60
    truth(spec, "INTAKE_EXCEEDS", None, f"{c['course']} applied {c['intake']} > approved {c['intake'] - 60}")


def d_sign_broken(spec, rnd, **_):
    a = spec["docs"]["affidavit_2"]
    spec.setdefault("post", []).append(("affidavit_2", "whiteout_after_sign", f"{a['built_up_area']:.0f} sq.m", f"{a['built_up_area'] * 1.4:.0f} sq.m"))
    truth(spec, "SIGNATURE_BROKEN", "affidavit_2", "edited after DSC signature")


def d_udin_unknown(spec, rnd, **_):
    spec["_skip_registry"] = spec.get("_skip_registry", []) + ["udin"]
    truth(spec, "UDIN_NOT_FOUND", "audited_statement", "UDIN not registered with ICAI")


def d_gps_far(spec, rnd, **_):
    for ph in spec["photos"][:3]:
        ph["lat"] += rnd.choice([-1, 1]) * rnd.uniform(1.5, 3.0)
        ph["lon"] += rnd.choice([-1, 1]) * rnd.uniform(1.5, 3.0)
    truth(spec, "PHOTO_GPS_MISMATCH", "infra_photo", "photos geotagged > 150 km from campus")


# cross-institution defects ------------------------------------------------------------

def x_ghost_faculty(a, b, rnd, n=6):
    """n faculty of `a` also listed by `b` - some with the same AICTE ID, some re-registered with a
    new ID but the same PAN + DOB and a name variant."""
    src = [f for f in a["form"]["faculty"] if f["designation"] != "Professor"][:n]
    for i, f in enumerate(src):
        g = copy.deepcopy(f)
        if i % 2 == 1:
            g["faculty_id"] = f"1-{rnd.randint(4_000_000_000, 9_999_999_999)}"
            parts = g["name"].replace("Dr. ", "").split()
            g["name"] = f"{parts[-1][0]}. {' '.join(parts[:-1])}" if len(parts) > 1 else g["name"]
        g["department"] = rnd.choice([c["course"] for c in b["form"]["courses"]])
        g["date_of_joining"] = "2026-07-01"
        b["form"]["faculty"].append(g)
    truth(b, "GHOST_FACULTY", None, f"{n} faculty also on roster of {a['institution']['name']}", partner=a["institution"]["permanent_id"])
    truth(a, "GHOST_FACULTY", None, f"{n} faculty also on roster of {b['institution']['name']}", partner=b["institution"]["permanent_id"])


def x_photo_reuse(a, b, rnd):
    ph = copy.deepcopy(a["photos"][0])
    ph["reused_from"] = a["institution"]["permanent_id"]
    ph["lat"], ph["lon"] = b["institution"]["lat"] + 0.0004, b["institution"]["lon"] - 0.0003
    if len(b["photos"]) > 1:
        b["photos"][1] = ph
    else:
        b["photos"].append(ph)
    truth(b, "PHOTO_REUSE", "infra_photo", f"photo reused from {a['institution']['name']}", partner=a["institution"]["permanent_id"])


def x_fire_reuse(a, b, rnd):
    """b submits a's fire NOC with the name/address swapped (redact + retype + re-save)."""
    b["docs"]["fire_noc"] = copy.deepcopy(a["docs"]["fire_noc"])
    b["_fire_clone_of"] = a
    b["_skip_registry"] = b.get("_skip_registry", []) + ["fire"]
    truth(b, "DOC_REUSE", "fire_noc", f"fire NOC of {a['institution']['name']} re-used", partner=a["institution"]["permanent_id"])
    truth(b, "REGISTRY_MISMATCH", "fire_noc", "registry shows NOC issued to another premises")
    truth(b, "TAMPER_RESAVE", "fire_noc", "names retyped on cloned NOC")


def x_estamp_reuse(a, b, rnd):
    b["docs"]["affidavit_2"]["estamp_no"] = a["docs"]["affidavit_2"]["estamp_no"]
    b["docs"]["affidavit_2"]["estamp_udr"] = a["docs"]["affidavit_2"]["estamp_udr"]
    b["_skip_registry"] = b.get("_skip_registry", []) + ["estamp"]
    truth(b, "ESTAMP_REUSE", "affidavit_2", f"same e-stamp certificate as {a['institution']['name']}", partner=a["institution"]["permanent_id"])
    truth(b, "REGISTRY_MISMATCH", "affidavit_2", "e-stamp registered to a different first party")


SINGLE = {"FIRE_EXPIRED": d_fire_expired, "TAMPER_WHITEOUT": d_fire_whiteout, "FSR_SHORTFALL": d_fsr_short,
          "CADRE_SHORTFALL": d_cadre_short, "TER_UNDERPAID": d_ter_under, "MISSING_MAP": d_missing,
          "SSC_MISSING": d_ssc_missing_old, "SSC_EXPIRED": d_ssc_expired, "STAMP_VALUE_LOW": d_stamp_low,
          "ESTAMP_NOT_FOUND": d_estamp_unknown, "NAME_MISMATCH": d_name_mismatch, "TAMPER_RESAVE": d_oc_area_resave,
          "INTAKE_EXCEEDS": d_intake_exceeds, "SIGNATURE_BROKEN": d_sign_broken, "UDIN_NOT_FOUND": d_udin_unknown,
          "PHOTO_GPS_MISMATCH": d_gps_far}
CROSS = {"GHOST_FACULTY": x_ghost_faculty, "PHOTO_REUSE": x_photo_reuse, "DOC_REUSE": x_fire_reuse, "ESTAMP_REUSE": x_estamp_reuse}

DEMO_PLAN = [
    # (cluster, single defects, scan docs?, fire source available?)
    ("Telangana", [], False),                               # T1 clean -> green lane
    ("Telangana", ["SSC_MISSING"], False),                  # T2 old building, no stability cert
    ("Telangana", ["FIRE_EXPIRED", "FSR_SHORTFALL"], False),
    ("Telangana", ["TAMPER_WHITEOUT"], False),             # T4 forged fire NOC validity
    ("Telangana", [], False),                               # T5 ghost faculty with T4, photo reuse from T1
    ("Telangana", ["ESTAMP_NOT_FOUND", "NAME_MISMATCH"], False),
    ("Maharashtra", [], False),                             # M1 clean
    ("Maharashtra", ["TER_UNDERPAID", "MISSING_MAP"], False),
    ("Maharashtra", ["TAMPER_RESAVE", "INTAKE_EXCEEDS"], False),
    ("Maharashtra", ["PHOTO_GPS_MISMATCH"], False),        # M4 also re-uses M1's fire NOC
    ("Tamil Nadu", [], True),                               # N1 clean but scanned + fire portal offline
    ("Tamil Nadu", ["SIGNATURE_BROKEN", "SSC_EXPIRED"], False),
    ("Tamil Nadu", ["CADRE_SHORTFALL", "UDIN_NOT_FOUND"], False),
    ("Tamil Nadu", [], True),                               # N4 scanned; shares e-stamp with N3
]
DEMO_CROSS = [("GHOST_FACULTY", 3, 4), ("PHOTO_REUSE", 0, 4), ("DOC_REUSE", 6, 9), ("ESTAMP_REUSE", 12, 13)]


# --------------------------------------------------------------------------- rendering

def _render_docs(spec: dict, out: Path, rnd: random.Random, scan: bool) -> list[dict]:
    files = []
    post = spec.get("post", [])
    for dt_, data in spec["docs"].items():
        data = dict(data)
        if dt_ == "fire_noc" and spec.get("_fire_clone_of"):
            src = spec["_fire_clone_of"]
            raw = render.fire_noc(src["docs"]["fire_noc"])
            raw = tamper.redact_resave(raw, [(src["institution"]["name"], spec["institution"]["name"]),
                                             (src["institution"]["address"][:60], spec["institution"]["address"][:60]),
                                             (src["institution"]["trust"], spec["institution"]["trust"])])
        else:
            fn = {"fire_noc": render.fire_noc, "occupancy_certificate": render.occupancy, "structural_stability": render.structural,
                  "affidavit_2": render.affidavit, "ter_receipt": render.ter_receipt, "audited_statement": render.audited,
                  "satellite_map": None}[dt_]
            raw = render.location_map(data, _tile(data["lat"], data["lon"])) if dt_ == "satellite_map" else fn(data)
        for pdt, op, old, new in post:
            if pdt != dt_ or op not in ("resave", "whiteout"):
                continue
            raw = tamper.whiteout_incremental(raw, old, new) if op == "whiteout" else tamper.redact_resave(raw, [(old, new)], producer="Sejda PDF Editor (sejda.com)")
        if dt_ == "affidavit_2" and data.get("sign_dsc"):
            raw = pki.sign_pdf(raw, data["deponent"], org=data["trust"][:60])
            for pdt, op, old, new in post:
                if pdt == dt_ and op == "whiteout_after_sign":
                    raw = tamper.whiteout_incremental(raw, old, new)
        if scan and dt_ not in ("affidavit_2",):
            raw = render.to_scanned(raw, seed=rnd.randint(0, 10**6), producer=rnd.choice(["CamScanner", "Adobe Scan for Android 25.11.10"]))
        name = f"{dt_}.pdf"
        (out / name).write_bytes(raw)
        files.append({"declared_type": dt_, "file": name})
    for i, ph in enumerate(spec["photos"]):
        img = (PHOTO_DIR / ph["file"]).read_bytes()
        if ph.get("reused_from"):
            img = tamper.photo_reuse(img, seed=i + spec["seed"])
        img = _gps_exif(img, ph["lat"], ph["lon"], ph["when"])
        name = f"photo_{i + 1}_{ph['label']}.jpg"
        (out / name).write_bytes(img)
        files.append({"declared_type": "infra_photo", "file": name, "label": ph["label"]})
    return files


TRUTH_FIELDS = {"fire_noc": ["noc_no", "issue_date", "valid_until", "premises"],
                "occupancy_certificate": ["cert_no", "issue_date", "built_up_area", "premises", "owner"],
                "affidavit_2": ["estamp_no", "stamp_value", "first_party"], "ter_receipt": ["txn_id", "amount"],
                "audited_statement": ["udin", "frn"], "structural_stability": ["issue_date", "engineer_reg"]}


def _doc_truth(s: dict) -> dict:
    """Values printed on each (untampered) document, for measuring extraction accuracy."""
    tampered = {p[0] for p in s.get("post", [])} | ({"fire_noc"} if s.get("_fire_clone_of") else set())
    out = {}
    for dt, fields in TRUTH_FIELDS.items():
        if dt in tampered or dt not in s["docs"]:
            continue
        out[dt] = {f: (v.isoformat() if hasattr(v, "isoformat") else v) for f in fields if (v := s["docs"][dt].get(f)) is not None}
    return out


def _demo_fixes(s: dict, out: Path, rnd: random.Random) -> None:
    """Corrected documents an institution would upload after a pre-check (renewed NOC, missing map)."""
    codes = {t["code"]: t for t in s["truth"]}
    fx = out / "fixes"
    if "FIRE_EXPIRED" in codes:
        fx.mkdir(exist_ok=True)
        f = dict(s["docs"]["fire_noc"])
        st = N.CLUSTERS[s["cluster"]]["state_code"]
        f["noc_no"] = f"{st}FS/{f['district'][:3].upper()}/2026/{rnd.randint(1000, 9999)}"
        f["issue_date"] = date(2026, 10, 21)
        f["valid_until"] = date(2029, 10, 20)
        (fx / "fire_noc__fire_noc_renewed.pdf").write_bytes(render.fire_noc(f))
        registry.put(f"fire_{st.lower()}", f["noc_no"], {"premises": f["premises"], "address": f["address"], "applicant": f["applicant"],
                                                        "issue_date": f["issue_date"].isoformat(), "valid_until": f["valid_until"].isoformat(), "status": "ACTIVE"})
    if codes.get("MISSING_DOC", {}).get("doc") == "satellite_map":
        fx.mkdir(exist_ok=True)
        m = {"institution": s["institution"]["name"], "lat": s["institution"]["lat"], "lon": s["institution"]["lon"], "address": s["institution"]["address"]}
        (fx / "satellite_map__satellite_map.pdf").write_bytes(render.location_map(m, _tile(m["lat"], m["lon"])))


def generate(mode: str = "demo", n: int = 40, seed: int = 2027, out_root: Path | None = None,
             reset_registry: bool = True, clean_only: bool = False) -> dict:
    rnd = random.Random(seed)
    out_root = out_root or (SYNTH / mode)
    if out_root.exists():
        shutil.rmtree(out_root)
    out_root.mkdir(parents=True)
    if reset_registry:
        registry.reset()
    used: set = set()
    specs: list[dict] = []
    dup_file = PHOTO_DIR / "duplicates.json"
    dups = set(json.loads(dup_file.read_text("utf-8"))) if dup_file.exists() else set()
    all_photos = sorted(p.name for p in PHOTO_DIR.glob("*.jpg") if p.name not in dups)
    photo_pool = rnd.sample(all_photos, len(all_photos))
    per_inst = 3 if mode == "demo" else max(1, len(all_photos) // max(n, 1))
    if mode == "demo":
        for i, (cluster, defects, scan) in enumerate(DEMO_PLAN):
            s = clean_spec(i, cluster, rnd, used, photo_pool, per_inst)
            s["_scan"] = scan
            for code in defects:
                SINGLE[code](s, rnd)
            specs.append(s)
        for code, ai, bi in DEMO_CROSS:
            CROSS[code](specs[ai], specs[bi], rnd)
        registry.set_available("fire_tn", True)
    else:
        clusters = list(N.CLUSTERS)
        for i in range(n):
            s = clean_spec(i, clusters[i % 3], rnd, used, photo_pool, per_inst)
            s["_scan"] = rnd.random() < 0.2
            if not clean_only and rnd.random() < 0.7:
                for code in rnd.sample(list(SINGLE), rnd.choice([1, 1, 2])):
                    if code == "SSC_EXPIRED" and "SSC_MISSING" in [t["code"] for t in s["truth"]]:
                        continue
                    SINGLE[code](s, rnd)
            specs.append(s)
        for code in ([] if clean_only else CROSS):
            for _ in range(max(1, n // 12)):
                a, b = rnd.sample(specs, 2)
                if a["cluster"] != b["cluster"] and code == "GHOST_FACULTY":
                    continue
                CROSS[code](a, b, rnd)

    manifest = {"mode": mode, "academic_year": AY, "applications": []}
    for s in specs:
        register_truth(s)
        skip = s.get("_skip_registry", [])
        for src, key, data in s["registry"]:
            if any(src.startswith(k) for k in skip):
                continue
            registry.put(src, key, data)
    for s in specs:
        out = out_root / s["institution"]["permanent_id"]
        out.mkdir()
        files = _render_docs(s, out, rnd, s.get("_scan", False))
        if mode == "demo":
            _demo_fixes(s, out, rnd)
        form = s["form"]
        (out / "application.json").write_text(json.dumps(form, indent=1, default=str), "utf-8")
        manifest["applications"].append({
            "dir": out.name, "institution": s["institution"], "prev_approval": s["prev_approval"],
            "files": files, "truth": s["truth"], "scanned": s.get("_scan", False), "doc_truth": _doc_truth(s),
        })
    if mode == "demo":
        registry.set_available("fire_tn", False)      # Tamil Nadu fire portal "down" -> pending/manual path
    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=1, default=str), "utf-8")
    return manifest
