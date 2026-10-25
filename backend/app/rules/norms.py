"""Executable APH 2024-27 norms (Annexure-3 built-up area, Annexure-5 faculty), with the working shown.

Every function returns both the number and a human-readable derivation so the reviewer can see
*how* "required faculty = 96" was obtained, not just that it was.
"""
from __future__ import annotations

import math

X_CATEGORY = ("MECHANICAL", "PRODUCTION", "CIVIL", "ELECTRICAL", "CHEMICAL", "TEXTILE", "MARINE", "AERONAUTICAL",
              "AUTOMOBILE", "MINING", "METALLURGY")


def program_group(level: str, program: str, course: str) -> str:
    lv, pg, cs = (level or "").upper(), (program or "").upper(), (course or "").upper()
    if "DIPLOMA" in lv:
        return "DIPLOMA_ET"
    if "MANAGEMENT" in pg or "MBA" in cs or "PGDM" in cs or "BBA" in cs or "BMS" in cs:
        return "PG_MGMT" if "POST" in lv else "UG_MGMT"
    if "COMPUTER APPLICATION" in pg or "MCA" in cs or "BCA" in cs:
        return "PG_MCA" if "POST" in lv else "UG_BCA"
    return "PG_ET" if "POST" in lv else "UG_ET"


GROUPS = {
    #           duration, FSR, cadre applies, citation
    "UG_ET":     (4, 20, True, "Annexure-5, 5.2 (UG Engineering & Technology 1:20)"),
    "PG_ET":     (2, 15, True, "Annexure-5, 5.3 (PG Engineering & Technology 1:15)"),
    "DIPLOMA_ET": (3, 25, False, "Annexure-5, 5.1 (Diploma 1:25)"),
    "PG_MGMT":   (2, 20, True, "Annexure-5, 5.3 (MBA/PGDM 1:20)"),
    "UG_MGMT":   (3, 25, True, "Annexure-5, 5.2 (Management UG 1:25)"),
    "PG_MCA":    (2, 20, True, "Annexure-5, 5.3 (MCA 1:20)"),
    "UG_BCA":    (3, 25, True, "Annexure-5, 5.2 (Computer Applications UG 1:25)"),
}


def faculty_requirement(courses: list[dict]) -> dict:
    """courses: [{level, program, course, intake}] -> required faculty with derivation (Annexure-5)."""
    per_group: dict[str, int] = {}
    for c in courses:
        g = program_group(c.get("level", ""), c.get("program", ""), c.get("course", ""))
        dur = GROUPS[g][0]
        per_group[g] = per_group.get(g, 0) + int(c.get("intake") or 0) * dur
    lines, total, prof, assoc = [], 0, 0, 0
    for g, S in per_group.items():
        dur, ratio, cadre, cite = GROUPS[g]
        req = math.ceil(S / ratio)
        total += req
        if cadre:
            p = math.ceil(S / (ratio * 9)); a = math.ceil(2 * S / (ratio * 9))
            prof += p; assoc += a
        lines.append(f"{g}: S = sum(intake x {dur} yrs) = {S}; S/{ratio} = {req} [{cite}]")
    return {"required": total, "professors": prof, "associates": assoc, "S_by_group": per_group,
            "derivation": lines + [f"Cadre ratio 1:2:6 -> Professors >= {prof}, Associate Professors >= {assoc} (Annexure-5 note)"]}


def divisions(intake: int, size: int = 60) -> int:
    return max(1, math.ceil(intake / size)) if intake else 0


def area_requirement(courses: list[dict]) -> dict:
    """Minimum built-up area for an Engineering & Technology institution (Annexure-3, 3.2-3.4).

    Implements the instructional-area table for UG E&T, the 750/500 sq.m admin/amenities floor
    (pro-rata beyond 300 intake, an explicit configurable assumption), and ACA = 25% of built-up.
    """
    ug = [c for c in courses if program_group(c.get("level", ""), c.get("program", ""), c.get("course", "")) == "UG_ET"]
    others = [c for c in courses if c not in ug]
    total_intake = sum(int(c.get("intake") or 0) for c in courses)
    lines = []
    ina = 0.0
    if ug:
        div_year = sum(divisions(int(c["intake"])) for c in ug)
        classrooms = math.ceil(div_year * 4 * 0.5)
        tutorials = math.ceil(classrooms * 0.25)
        first_year_labs = 4 if total_intake <= 600 else 4 + math.ceil((total_intake - 600) / 600) * 4
        other_labs = sum(2 * 3 * max(1, math.ceil(int(c["intake"]) / 180)) for c in ug)
        x_labs = sum(1 for c in ug if any(k in c["course"].upper() for k in X_CATEGORY))
        k = 1 if total_intake <= 600 else 2
        library = 400 + max(0, math.ceil((total_intake - 420) / 60)) * 50
        parts = [("Class rooms", classrooms, 66), ("Tutorial rooms", tutorials, 33), ("Labs (first year)", first_year_labs, 66),
                 ("Labs (other years)", other_labs, 66), ("Workshop", k, 200), ("Additional lab for X-category", x_labs, 200),
                 ("CAD centre / drawing hall", k, 132), ("Computer centre", k, 150), ("Seminar hall", 1, 132),
                 ("Library", 1, library), ("Language lab", 1, 33)]
        for name, n, a in parts:
            ina += n * a
            lines.append(f"{name}: {n} x {a} = {n * a} sq.m")
    for c in others:
        g = program_group(c.get("level", ""), c.get("program", ""), c.get("course", ""))
        dur = GROUPS[g][0]
        rooms = divisions(int(c["intake"])) * dur
        ina += rooms * 66 + math.ceil(rooms * 0.25) * 33
        lines.append(f"{c['course'][:40]}: {rooms} class rooms x 66 + tutorials (Annexure-3, 3.2.1 F/G)")
    scale = max(1.0, total_intake / 300)
    ada, ama = 750 * scale, 500 * scale
    carpet = ina + ada + ama
    built = carpet / 0.75
    lines += [f"Instructional area (INA) = {ina:.0f} sq.m",
              f"Administrative area (ADA) = 750 x {scale:.2f} = {ada:.0f} sq.m (Annexure-3, 3.3; pro-rata assumption beyond 300 intake)",
              f"Amenities area (AMA) = 500 x {scale:.2f} = {ama:.0f} sq.m (Annexure-3, 3.4)",
              f"Built-up = (INA+ADA+AMA) / 0.75 (ACA = 25% of built-up, Annexure-3, 3.2 b-c) = {built:.0f} sq.m"]
    return {"required_builtup": round(built), "instructional": round(ina), "derivation": lines}


def ter_required(courses: list[dict], academic_year: str, inst_type: str = "private") -> dict:
    """Table 2.1 TER for EoA (self-disclosure): Rs 0.20 lakh per division (0.40 for PGDM/MBA),
    Govt/University Rs 0.05 / 0.15; +10% annually from 2024-25 (Note i)."""
    gov = any(k in (inst_type or "").lower() for k in ("government", "university"))
    base_rate, mba_rate = (5000, 15000) if gov else (20000, 40000)
    years = max(0, int(academic_year[:4]) - 2024)
    factor = 1.1 ** years
    total, lines = 0.0, []
    for c in courses:
        n = divisions(int(c.get("intake") or 0))
        mba = "MBA" in c.get("course", "").upper() or "MANAGEMENT" in c.get("program", "").upper()
        rate = (mba_rate if mba else base_rate) * factor
        total += n * rate
        lines.append(f"{c['course'][:44]}: {n} division(s) x Rs {rate:,.0f}")
    lines.append(f"Rates escalated by 10% per year for {years} year(s) after 2024-25 (Table 2.1, Note i)")
    return {"required": round(total, 2), "derivation": lines}
