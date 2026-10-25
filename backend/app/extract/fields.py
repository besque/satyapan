"""Label-anchored field extraction with evidence boxes.

Certificates from different issuers word things differently ("Valid upto", "Validity", "Expiry
Date"...), so each field lists label synonyms; the value is read to the right of the label on the
same line, or from the line directly below. Works the same on text-layer PDFs and OCR output.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from dateutil import parser as dparser

from ..docmodel import Doc, Page, Word, compact, compact_line, norm, union_bbox


@dataclass
class Value:
    value: object
    raw: str
    page: int
    bbox: list[float]
    label_bbox: list[float] | None
    conf: float
    label: str

    def as_dict(self) -> dict:
        v = self.value.isoformat() if isinstance(self.value, date) else self.value
        return {"value": v, "raw": self.raw, "page": self.page, "bbox": self.bbox,
                "label_bbox": self.label_bbox, "conf": round(self.conf, 3), "label": self.label}


MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"
DATE_RX = re.compile(
    rf"(\d{{1,2}}[\-/.]\d{{1,2}}[\-/.]\d{{2,4}}|\d{{4}}[\-/.]\d{{1,2}}[\-/.]\d{{1,2}}|\d{{1,2}}(?:st|nd|rd|th)?[\s\-]+{MONTHS}[\s\-,]+\d{{4}}|{MONTHS}\s+\d{{1,2}},?\s+\d{{4}})",
    re.I)
NUM_RX = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?![\w])")


def parse_date(s: str) -> date | None:
    m = DATE_RX.search(s)
    if not m:
        return None
    txt = re.sub(r"(\d)(st|nd|rd|th)", r"\1", m.group(1), flags=re.I)
    try:
        iso_first = re.match(r"\d{4}", txt) is not None
        return dparser.parse(txt, dayfirst=not iso_first, yearfirst=iso_first, fuzzy=True).date()
    except (ValueError, OverflowError):
        return None


def parse_number(s: str) -> float | None:
    m = NUM_RX.search(s.replace(" ", "") if re.fullmatch(r"[\d ,.]+", s.strip()) else s)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _match_label(line: list[Word], label: str) -> tuple[int, int, str] | None:
    """Locate `label` in a visual line, ignoring spacing/punctuation.

    Returns (start_word, end_word, remainder) where `remainder` is any value text glued to the
    label inside the same OCR token (e.g. "NOCNo:TNFS/123"). A label must begin the line or a new
    column (clear gap) - so "CERTIFICATE (NO ..." in a title does not match "Certificate No".
    """
    target = compact(label)
    if not target:
        return None
    s, owner = compact_line(line)
    pos = s.find(target)
    while pos != -1:
        wi = owner[pos]
        at_word_start = pos == 0 or owner[pos - 1] != wi
        col_start = wi == 0 or line[wi].x0 - line[wi - 1].x1 > 18
        if at_word_start and col_start:
            end_char = pos + len(target) - 1
            ew = owner[end_char]
            word_tail = compact(line[ew].text)
            consumed = sum(1 for k in range(end_char + 1) if owner[k] == ew)
            remainder = ""
            if consumed < len(word_tail):
                raw = line[ew].text
                # map consumed compact chars back onto the raw token
                cnt, cut = 0, len(raw)
                for ci, ch in enumerate(raw):
                    if ch.isalnum():
                        cnt += 1
                        if cnt == consumed:
                            cut = ci + 1; break
                remainder = raw[cut:].lstrip(":：-– ")
            return wi, ew + 1, remainder
        pos = s.find(target, pos + 1)
    return None


def find_label_value(doc: Doc, labels: list[str], kind: str = "text", pattern: re.Pattern | None = None,
                     stop_labels: list[str] | None = None, max_words: int = 14) -> Value | None:
    stop_norm = [compact(s) for s in (stop_labels or [])]
    best: Value | None = None
    for page in doc.pages:
        lines = page.lines()
        for li, line in enumerate(lines):
            for label in labels:
                hit = _match_label(line, label)
                if not hit:
                    continue
                s, e, remainder = hit
                label_words = line[s:e]
                after = line[e:]
                if remainder:
                    lw = line[e - 1]
                    after = [Word(remainder, lw.page, lw.x0 + (lw.x1 - lw.x0) * (1 - len(remainder) / max(len(lw.text), 1)), lw.y0,
                                  lw.x1, lw.y1, lw.line, lw.font, lw.size, lw.color, lw.conf)] + after
                cand_lines = [after]
                if li + 1 < len(lines):
                    below = [w for w in lines[li + 1] if w.x1 > label_words[0].x0 - 5]
                    cand_lines.append(below)
                for ci, cand in enumerate(cand_lines):
                    cand = [w for w in cand if w.text not in (":", "-", ":-", "–", "：")]
                    if cand and cand[0].text[:1] in (":", "："):
                        cand[0] = Word(cand[0].text.lstrip(":："), cand[0].page, cand[0].x0, cand[0].y0, cand[0].x1,
                                       cand[0].y1, cand[0].line, cand[0].font, cand[0].size, cand[0].color, cand[0].conf)
                        if not cand[0].text:
                            cand = cand[1:]
                    # cut at the next label on the same line / big horizontal gap
                    cut = []
                    for k, w in enumerate(cand[:max_words]):
                        if k and w.x0 - cand[k - 1].x1 > 40:
                            break
                        joined = compact(" ".join(x.text for x in cand[k:k + 4]))
                        if k and any(joined.startswith(sn) for sn in stop_norm if sn):
                            break
                        cut.append(w)
                    if not cut:
                        continue
                    raw = " ".join(w.text for w in cut).strip(" :-")
                    val, used = _coerce(raw, kind, pattern, cut)
                    if val is None:
                        continue
                    conf = (0.95 if ci == 0 else 0.8) * min(w.conf for w in used)
                    v = Value(val, raw, page.number, union_bbox(used), union_bbox(label_words), conf, label)
                    if best is None or v.conf > best.conf:
                        best = v
                    break
                # labels are ordered most-specific first: once one matches this line, a shorter
                # synonym ("Address" inside "Address of the Premises") must not override it
                break
    return best


def _coerce(raw: str, kind: str, pattern: re.Pattern | None, words: list[Word]):
    if kind == "date":
        m = DATE_RX.search(raw)
        if not m:
            return None, words
        d = parse_date(m.group(0))
        return d, _words_covering(words, m.group(0))
    if kind == "number":
        m = NUM_RX.search(raw)
        if not m:
            return None, words
        try:
            return float(m.group(1).replace(",", "")), _words_covering(words, m.group(1))
        except ValueError:
            return None, words
    if kind == "pattern" and pattern is not None:
        m = pattern.search(raw.replace(" ", "")) or pattern.search(raw)
        return (m.group(0), _words_covering(words, m.group(0).split()[0][:4])) if m else (None, words)
    return raw, words


def _words_covering(words: list[Word], fragment: str) -> list[Word]:
    toks = fragment.split()
    if not toks:
        return words
    for i, w in enumerate(words):
        if toks[0][:4] in w.text:
            return words[i:i + max(1, len(toks))]
    return words


def find_pattern(doc: Doc, pattern: re.Pattern) -> Value | None:
    """First match of a regex anywhere (ids like e-stamp certificate numbers)."""
    for page in doc.pages:
        for line in page.lines():
            text = " ".join(w.text for w in line)
            m = pattern.search(text)
            if m:
                frag = m.group(0)
                used = [w for w in line if w.text and (w.text in frag or frag.startswith(w.text[:5]) or w.text[:5] in frag)]
                return Value(m.group(0), m.group(0), page.number, union_bbox(used or line), None,
                             0.9 * min(w.conf for w in line), "pattern")
    return None


def contains(doc: Doc, phrases: list[str]) -> dict | None:
    from ..docmodel import find_phrase
    for page in doc.pages:
        for ph in phrases:
            hits = find_phrase(page, ph)
            if hits:
                return {"phrase": ph, "page": page.number, "bbox": union_bbox(hits[0])}
    return None
