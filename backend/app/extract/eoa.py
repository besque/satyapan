"""Parser for real AICTE Extension-of-Approval letters (portal-generated reports).

Handles single letters and merged multi-year PDFs (institutions often merge all EoAs since
inception into one mandatory-disclosure file). Every extracted value keeps its page + bbox.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache

import pymupdf

from ..docmodel import Doc, Page, Word, union_bbox

APP_NO = re.compile(r"Application\s*(?:No|Number)\s*:\s*(1-\d{6,12})")
PAGE_OF = re.compile(r"Page\s+(\d+)\s+of\s+(\d+)")
YEAR = re.compile(r"APPROVAL PROCESS\s*(\d{4})\s*-\s*(\d{2,4})", re.I)
FNO = re.compile(r"F\.\s*No\.\s*([A-Za-z\-]+/[^\s]+)")
DOA = re.compile(r"Date(?:\s+of\s+Approval)?\s*:\s*(\d{1,2}-[A-Za-z]{3}-\d{4})")
PRINTED = re.compile(r"Letter Printed On\s*:\s*([0-9]{1,2}\s+[A-Za-z]+\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})")
PRINTED_BY = re.compile(r"Printed By\s*:\s*(\S+)")
PID = re.compile(r"Permanent\s*Id\s*:?\s*(1-\d{6,12})", re.I)
KIND = re.compile(r"(Extension of Approval \(EoA\)|Letter of Approval|Corrigendum|Change in the Name|Closure|Increase in Intake)", re.I)

LABELS = {
    "Name of the Institution": "name",
    "Name of the Society/Trust": "trust",
    "Institution Address": "address",
    "Society/Trust Address": "trust_address",
    "Institution Type": "inst_type",
    "Region": "region",
    "Year of Establishment": "est_year",
    "Permanent Id": "permanent_id",
    "Application Id": "application_id",
}

STATES = ["Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa", "Gujarat", "Haryana",
          "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur",
          "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana",
          "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal", "Delhi", "Jammu and Kashmir", "Ladakh",
          "Puducherry", "Chandigarh", "Andaman and Nicobar Islands", "Lakshadweep",
          "Dadra and Nagar Haveli and Daman and Diu"]


@dataclass
class Field:
    value: str
    page: int
    bbox: list[float]

    def as_dict(self):
        return {"value": self.value, "page": self.page, "bbox": self.bbox}


@dataclass
class CourseRow:
    level: str
    program: str
    course: str
    affiliating_body: str
    intake_prev: int | None
    intake_curr: int | None
    nri: str
    fn: str
    is_new: bool
    page: int
    bbox: list[float]
    cells: dict = field(default_factory=dict)  # column -> Field (for evidence)
    intake_values: list = field(default_factory=list)   # every number printed in the cell (overlaps = suspicious)


@dataclass
class EoaLetter:
    application_no: str
    pages: list[int]
    fields: dict[str, Field] = field(default_factory=dict)
    courses: list[CourseRow] = field(default_factory=list)
    deficiencies: list[dict] = field(default_factory=list)
    year_prev: str | None = None
    year_curr: str | None = None

    @property
    def academic_year(self) -> str | None:
        f = self.fields.get("academic_year")
        return f.value if f else None

    def get(self, k: str) -> str | None:
        f = self.fields.get(k)
        return f.value if f else None

    def total_intake(self) -> int:
        return sum(c.intake_curr or 0 for c in self.courses)

    def as_dict(self) -> dict:
        return {
            "application_no": self.application_no,
            "pages": self.pages,
            "fields": {k: v.as_dict() for k, v in self.fields.items()},
            "courses": [{k: getattr(c, k) for k in ("level", "program", "course", "affiliating_body", "intake_prev",
                                                    "intake_curr", "nri", "fn", "is_new", "page", "bbox", "intake_values")}
                        | {"cells": {ck: cv.as_dict() for ck, cv in c.cells.items()}} for c in self.courses],
            "deficiencies": self.deficiencies,
            "year_prev": self.year_prev,
            "year_curr": self.year_curr,
        }


def _clean(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s*,\s*", ", ", s)
    return s.strip(" ,")


def _join_split(s: str) -> str:
    """Table cells wrap mid-word ("COMPUTE R APPLICATI ONS"). Re-join fragments of uppercase words."""
    return _clean(s)


_TABLE_CACHE: dict[tuple[int, int], object] = {}
_TABLE_HINTS = ("Intake", "Permanent", "Deficienc", "Institution")


class _NoTables:
    tables: list = []


def _tables(fitz_page: pymupdf.Page):
    """find_tables() is ~0.8 s/page, so run it once per page and only where tables can exist."""
    key = (id(fitz_page.parent), fitz_page.number)
    if key not in _TABLE_CACHE:
        text = fitz_page.get_text()
        _TABLE_CACHE[key] = fitz_page.find_tables() if any(h in text for h in _TABLE_HINTS) else _NoTables()
    return _TABLE_CACHE[key]


def _words_in(page: Page, rect) -> list[Word]:
    x0, y0, x1, y1 = rect
    out = [w for w in page.words if (w.x0 + w.x1) / 2 >= x0 - 0.5 and (w.x0 + w.x1) / 2 <= x1 + 0.5
           and (w.y0 + w.y1) / 2 >= y0 - 0.5 and (w.y0 + w.y1) / 2 <= y1 + 0.5]
    return sorted(out, key=lambda w: (round(w.y0), w.x0))


def _cell_field(page: Page, rect) -> Field | None:
    ws = _words_in(page, rect)
    if not ws:
        return None
    # Group into visual lines; a line whose last word touches the cell's right edge was wrapped
    # mid-word by the report generator ("COMPUTE" / "R"), so the next fragment is glued on.
    lines: list[list[Word]] = []
    for w in ws:
        if lines and abs(lines[-1][0].y0 - w.y0) < 2.5:
            lines[-1].append(w)
        else:
            lines.append([w])
    text = ""
    for i, ln in enumerate(lines):
        seg = " ".join(w.text for w in ln)
        if i == 0:
            text = seg
            continue
        a, b = lines[i - 1][-1].text, ln[0].text
        text += seg if _should_glue(a, b) else " " + seg
    return Field(_clean(text), page.number, union_bbox(ws))


@lru_cache(maxsize=1)
def _vocab() -> frozenset[str]:
    from ..config import APH_PDF
    words: set[str] = set()
    txt = APH_PDF.with_name("aph_text.txt")
    if txt.exists():
        words |= set(re.findall(r"[a-z]{2,}", txt.read_text("utf-8", errors="ignore").lower()))
    words |= {"and", "of", "in", "or", "to", "the", "computer", "applications", "engineering", "technology",
              "communication", "communications", "instrumentation", "intelligence", "artificial", "machine",
              "learning", "science", "electronics", "electrical", "mechanical", "management", "information",
              "telecommunication", "biotechnology", "mechatronics", "automobile", "aeronautical", "robotics"}
    return frozenset(words)


def _should_glue(a: str, b: str) -> bool:
    """Was `a`/`b` one word that the report generator wrapped across lines?"""
    if not (a[-1:].isalpha() and b[:1].isalpha()):
        return False
    va, vb = _vocab(), a.lower() + b.lower()
    joined = re.sub(r"[^a-z]", "", vb)
    if joined not in va:
        return False
    a_ok = re.sub(r"[^a-z]", "", a.lower()) in va
    b_ok = re.sub(r"[^a-z]", "", b.lower()) in va
    return not (a_ok and b_ok) or len(b) <= 2 or len(a) <= 2


def _info_from_tables(fitz_page: pymupdf.Page, page: Page) -> dict[str, Field]:
    out: dict[str, Field] = {}
    try:
        tabs = _tables(fitz_page)
    except Exception:  # noqa: BLE001
        return out
    labels_n = {re.sub(r"[^a-z]", "", k.lower()): v for k, v in LABELS.items()}
    for t in tabs.tables:
        for r in t.rows:
            cells = [(_cell_field(page, c) if c else None) for c in r.cells]
            for i, c in enumerate(cells[:-1]):
                if not c:
                    continue
                key = labels_n.get(re.sub(r"[^a-z]", "", c.value.lower()))
                if key and cells[i + 1] and key not in out:
                    out[key] = cells[i + 1]
    return out


def _int(s: str | None) -> int | None:
    if not s:
        return None
    m = re.search(r"\d+", s.replace(",", ""))
    return int(m.group()) if m else None


def _norm_year(a: str, b: str) -> str:
    return f"{a}-{b[-2:]}"


def _regex_field(page: Page, rx: re.Pattern, text: str | None = None) -> Field | None:
    text = text if text is not None else page.text()
    m = rx.search(text)
    if not m:
        return None
    val = m.group(1)
    # locate the value's words for a bbox
    toks = val.split()
    for i, w in enumerate(page.words):
        if toks[0] in w.text:
            run = page.words[i:i + len(toks)]
            return Field(val, page.number, union_bbox(run))
    return Field(val, page.number, [0, 0, 0, 0])


def _label_value_fields(page: Page) -> dict[str, Field]:
    """The info block is a 4-column label/value grid. Use pymupdf table cells when found, else line heuristics."""
    out: dict[str, Field] = {}
    lines = page.lines()
    texts = [" ".join(w.text for w in ln) for ln in lines]
    for i, t in enumerate(texts):
        for label, key in LABELS.items():
            if key in out:
                continue
            if t.strip().lower() == label.lower() or t.strip().lower().startswith(label.lower() + " "):
                rest = t[len(label):].strip(" :")
                if rest:
                    ws = [w for w in lines[i] if w.x0 > lines[i][0].x0 + 1][-len(rest.split()):]
                    out[key] = Field(_clean(rest), page.number, union_bbox(ws) if ws else union_bbox(lines[i]))
                    continue
                # value is on following lines until next label
                vals, vwords = [], []
                for j in range(i + 1, min(i + 6, len(texts))):
                    tj = texts[j].strip()
                    if any(tj.lower().startswith(l.lower()) for l in LABELS) or tj.lower().startswith(("to conduct", "opted for")):
                        break
                    vals.append(tj); vwords.extend(lines[j])
                    if key in ("permanent_id", "application_id", "region", "est_year", "inst_type"):
                        break
                if vals:
                    out[key] = Field(_clean(" ".join(vals)), page.number, union_bbox(vwords))
    return out


def _course_tables(fitz_page: pymupdf.Page, page: Page, letter: EoaLetter, new_section_y: float | None):
    try:
        tabs = _tables(fitz_page)
    except Exception:  # noqa: BLE001
        return
    for t in tabs.tables:
        if t.col_count < 5:
            continue
        rows = t.rows
        header = [(_cell_field(page, c) if c else None) for c in rows[0].cells]
        htxt = [(h.value.lower() if h else "") for h in header]
        if not any("course" in h for h in htxt) or not any("intake" in h for h in htxt):
            continue
        intake_cols = [i for i, h in enumerate(htxt) if "intake" in h]
        years = []
        for i in intake_cols:
            m = re.search(r"(\d{4})\s*-\s*(\d{2})", header[i].value) if header[i] else None
            years.append(_norm_year(m.group(1), m.group(2)) if m else None)
        col = {name: next((i for i, h in enumerate(htxt) if key in h), None) for name, key in
               [("level", "level"), ("program", "program"), ("course", "course"), ("aff", "affiliat"),
                ("shift", "shift"), ("nri", "nri"), ("fn", "foreign")]}
        if col["fn"] is None:
            col["fn"] = next((i for i, h in enumerate(htxt) if "international" in h or "fn" in h or "gulf" in h), None)
        is_new = new_section_y is not None and t.bbox[1] > new_section_y
        if len(intake_cols) >= 2:
            letter.year_prev, letter.year_curr = years[0] or letter.year_prev, years[-1] or letter.year_curr
        for r in rows[1:]:
            cells = [(_cell_field(page, c) if c else None) for c in r.cells]
            def g(i):
                return cells[i].value if i is not None and i < len(cells) and cells[i] else ""
            course = g(col["course"])
            if not course or course.lower().startswith("course"):
                continue
            prev = _int(g(intake_cols[0])) if len(intake_cols) >= 2 else None
            curr = _int(g(intake_cols[-1]))
            if curr is None and prev is None:
                continue
            cmap = {}
            for name, i in [("course", col["course"]), ("intake_curr", intake_cols[-1]),
                            ("intake_prev", intake_cols[0] if len(intake_cols) >= 2 else None),
                            ("affiliating_body", col["aff"])]:
                if i is not None and i < len(cells) and cells[i]:
                    cmap[name] = cells[i]
            row_bbox = [r.bbox[0], r.bbox[1], r.bbox[2], r.bbox[3]]
            all_vals = [int(x) for x in re.findall(r"\d+", g(intake_cols[-1]).replace(",", ""))]
            letter.courses.append(CourseRow(
                level=_join_split(g(col["level"])), program=_join_split(g(col["program"])),
                course=_join_split(course), affiliating_body=_join_split(g(col["aff"])),
                intake_prev=prev, intake_curr=curr, nri=g(col["nri"]), fn=g(col["fn"]),
                is_new=is_new or len(intake_cols) == 1, page=page.number, bbox=row_bbox, cells=cmap, intake_values=all_vals))


def _deficiencies(fitz_page: pymupdf.Page, page: Page) -> list[dict]:
    """'Deficiencies Noted based on Self Disclosure' table -> [{particular, status}]."""
    if "Deficienc" not in page.text():
        return []
    out = []
    try:
        tabs = _tables(fitz_page)
    except Exception:  # noqa: BLE001
        return out
    for t in tabs.tables:
        cells_text = " ".join(" ".join(str(c or "") for c in row) for row in t.extract()).lower()
        if "deficienc" not in cells_text:
            continue
        for r in t.rows:
            cells = [(_cell_field(page, c) if c else None) for c in r.cells]
            vals = [c for c in cells if c and c.value]
            if len(vals) < 2:
                continue
            status = vals[-1].value.strip().rstrip(".")
            label = re.sub(r"^\s*\d+\s*\.?\s*", "", " ".join(v.value for v in vals[:-1])).strip(" .")
            if status in ("Yes", "No") and label and "particular" not in label.lower():
                out.append({"particular": label, "status": status, "page": page.number,
                            "bbox": union_bbox([w for w in _words_in(page, r.bbox)]) if _words_in(page, r.bbox) else list(r.bbox)})
    return out


def parse(doc: Doc) -> list[EoaLetter]:
    pdf = pymupdf.open(stream=doc.raw, filetype="pdf")
    letters: list[EoaLetter] = []
    current: EoaLetter | None = None
    for page in doc.pages:
        text = page.text()
        m = APP_NO.search(text)
        pg = PAGE_OF.search(text)
        app_no = m.group(1) if m else None
        starts_new = app_no and (current is None or current.application_no != app_no or (pg and pg.group(1) == "1"))
        if starts_new:
            current = EoaLetter(application_no=app_no, pages=[])
            letters.append(current)
        if current is None:
            continue
        current.pages.append(page.number)
        f = current.fields
        for key, rx in [("fno", FNO), ("date_of_approval", DOA), ("letter_printed", PRINTED), ("printed_by", PRINTED_BY)]:
            if key not in f:
                v = _regex_field(page, rx, text)
                if v:
                    f[key] = v
        if "academic_year" not in f:
            ym = YEAR.search(text)
            if ym:
                fld = _regex_field(page, YEAR, text)
                f["academic_year"] = Field(_norm_year(ym.group(1), ym.group(2)), page.number, fld.bbox if fld else [0, 0, 0, 0])
        if "kind" not in f:
            km = KIND.search(text)
            if km:
                f["kind"] = Field(km.group(1), page.number, [0, 0, 0, 0])
        for k, v in _info_from_tables(pdf[page.number], page).items():
            f.setdefault(k, v)
        if "name" not in f and page.number == current.pages[0]:
            for k, v in _label_value_fields(page).items():
                f.setdefault(k, v)
        if "permanent_id" not in f:
            v = _regex_field(page, PID, text)
            if v:
                f["permanent_id"] = v
        new_y = None
        for hit in ("Approved New Course", "Approved New Program"):
            r = pdf[page.number].search_for(hit)
            if r:
                new_y = r[0].y0
        _course_tables(pdf[page.number], page, current, new_y)
        current.deficiencies.extend(_deficiencies(pdf[page.number], page))
    for k in [k for k in _TABLE_CACHE if k[0] == id(pdf)]:
        del _TABLE_CACHE[k]
    for L in letters:
        addr = (L.get("address") or L.get("trust_address") or "").lower()
        found = [(addr.rfind(s.lower()), s) for s in STATES if s.lower() in addr]
        st = max(found)[1] if found else None
        if st:
            L.fields["state"] = Field(st, L.fields["address"].page if "address" in L.fields else 0,
                                      L.fields["address"].bbox if "address" in L.fields else [0, 0, 0, 0])
    return letters


def parse_date(s: str | None):
    if not s:
        return None
    for fmt in ("%d-%b-%Y", "%d %B %Y", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s.strip().rstrip("."), fmt).date()
        except ValueError:
            continue
    return None
