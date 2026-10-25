"""Consistency checks inside the institutional record itself (real public EoA letters).

Each EoA letter restates the previous year's approved intake. Letter(Y+1).intake_prev should equal
letter(Y).intake_curr for the same course; a difference means one of the two letters (or our reading
of it) needs a look. Courses are keyed by (level, course) so UG and PG courses with the same name
do not collide; zero rows (course not offered that year) are skipped.
"""
from __future__ import annotations

from collections import defaultdict

from . import db


def _prev_year(ay: str) -> str:
    y = int(ay[:4]) - 1
    return f"{y}-{str(y + 1)[-2:]}"


def cross_year(pid: str | None = None) -> dict:
    where = "WHERE a.source_url != ''" + (" AND a.permanent_id=?" if pid else "")
    rows = db.q("SELECT a.permanent_id, a.academic_year, a.source_url, c.level, c.course, c.intake_prev, c.intake_curr "
                f"FROM approvals a JOIN approval_courses c ON c.approval_id=a.id {where}", (pid,) if pid else ())
    idx: dict[tuple, dict] = defaultdict(dict)
    for r in rows:
        key = ((r["level"] or "").upper().replace(" ", ""), (r["course"] or "").upper())
        idx[(r["permanent_id"], r["academic_year"])][key] = r
    checks, issues = 0, []
    for (p, ay), courses in idx.items():
        prev = idx.get((p, _prev_year(ay)))
        if not prev:
            continue
        for key, r in courses.items():
            pr = prev.get(key)
            if r["intake_prev"] in (None, 0) or not pr or pr["intake_curr"] in (None, 0):
                continue
            checks += 1
            if pr["intake_curr"] != r["intake_prev"]:
                issues.append({"permanent_id": p, "course": r["course"], "level": r["level"],
                               "year": _prev_year(ay), "approved_then": pr["intake_curr"], "restated_next_year": r["intake_prev"],
                               "letters": [pr["source_url"], r["source_url"]]})
    return {"checks": checks, "issues": issues}
