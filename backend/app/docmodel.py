"""Unified document model: every page becomes a list of words with bounding boxes.

Text-layer PDFs use the embedded text (exact, with font info). Scanned PDFs and photos fall
back to local OCR (RapidOCR / ONNX). Every downstream finding points back to these boxes,
which is what lets the UI highlight *exactly* why something was flagged.
"""
from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image

from .config import RENDER, RENDER_DPI

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


@dataclass
class Word:
    text: str
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    line: int            # global line id within page
    font: str = ""
    size: float = 0.0
    color: int = 0
    conf: float = 1.0    # OCR confidence (1.0 for text layer)

    @property
    def bbox(self) -> list[float]:
        return [self.x0, self.y0, self.x1, self.y1]


@dataclass
class Page:
    number: int
    width: float
    height: float
    words: list[Word] = field(default_factory=list)
    ocr: bool = False

    def text(self) -> str:
        if getattr(self, "_text", None) is None:
            out, last = [], None
            for w in self.words:
                if last is not None and w.line != last:
                    out.append("\n")
                elif last is not None:
                    out.append(" ")
                out.append(w.text)
                last = w.line
            self._text = "".join(out)
        return self._text

    def lines(self) -> list[list[Word]]:
        """Visual lines: words whose vertical centres align, regardless of how the PDF split them
        into blocks (a label and its value are often separate text objects)."""
        if getattr(self, "_lines", None) is not None:
            return self._lines
        ws = sorted(self.words, key=lambda w: ((w.y0 + w.y1) / 2, w.x0))
        rows: list[list[Word]] = []
        centres: list[float] = []
        for w in ws:
            yc, h = (w.y0 + w.y1) / 2, max(w.y1 - w.y0, 1.0)
            if rows and abs(yc - centres[-1]) <= 0.55 * h:
                rows[-1].append(w)
                centres[-1] = (centres[-1] * (len(rows[-1]) - 1) + yc) / len(rows[-1])
            else:
                rows.append([w]); centres.append(yc)
        self._lines = [sorted(r, key=lambda w: w.x0) for r in rows]
        return self._lines


@dataclass
class Doc:
    path: Path
    sha256: str
    kind: str                 # "pdf" | "image"
    pages: list[Page]
    raw: bytes

    @property
    def text(self) -> str:
        return "\n\n".join(p.text() for p in self.pages)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------- OCR

@lru_cache(maxsize=1)
def _ocr_engine():
    from rapidocr_onnxruntime import RapidOCR  # local ONNX models shipped with the wheel
    return RapidOCR()


def ocr_image(img: Image.Image, page_no: int, scale: float) -> list[Word]:
    """OCR an image; `scale` converts pixel coords back to page units."""
    arr = np.array(img.convert("RGB"))
    result, _ = _ocr_engine()(arr)
    words: list[Word] = []
    for li, (box, text, score) in enumerate(result or []):
        xs = [p[0] for p in box]; ys = [p[1] for p in box]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        tokens = text.split()
        if not tokens:
            continue
        total = sum(len(t) for t in tokens) + len(tokens) - 1
        cursor = x0
        for t in tokens:
            wlen = (x1 - x0) * len(t) / max(total, 1)
            words.append(Word(t, page_no, cursor * scale, y0 * scale, (cursor + wlen) * scale, y1 * scale,
                              line=li, conf=float(score)))
            cursor += wlen + (x1 - x0) / max(total, 1)
    return words


# ---------------------------------------------------------------- PDF text layer

def _pdf_words(page: pymupdf.Page) -> list[Word]:
    raw = page.get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
    words: list[Word] = []
    line_id = 0
    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            line_id += 1
            for span in line["spans"]:
                cur: list[dict] = []

                def flush():
                    if not cur:
                        return
                    t = "".join(c["c"] for c in cur)
                    words.append(Word(t, page.number, min(c["bbox"][0] for c in cur), min(c["bbox"][1] for c in cur),
                                      max(c["bbox"][2] for c in cur), max(c["bbox"][3] for c in cur), line=line_id,
                                      font=span["font"], size=round(span["size"], 2), color=span["color"]))
                    cur.clear()

                for ch in span["chars"]:
                    if ch["c"].isspace():
                        flush()
                    else:
                        cur.append(ch)
                flush()
    return words


def load(path: Path | str, data: bytes | None = None, force_ocr: bool = False, allow_ocr: bool = True) -> Doc:
    path = Path(path)
    raw = data if data is not None else path.read_bytes()
    sha = sha256_bytes(raw)
    if path.suffix.lower() in IMAGE_EXT:
        img = Image.open(io.BytesIO(raw))
        w, h = img.size
        page = Page(0, float(w), float(h), ocr_image(img, 0, 1.0) if allow_ocr else [], ocr=allow_ocr)
        return Doc(path, sha, "image", [page], raw)

    pdf = pymupdf.open(stream=raw, filetype="pdf")
    pages: list[Page] = []
    for p in pdf:
        words = [] if force_ocr else _pdf_words(p)
        n_chars = len("".join(w.text for w in words))
        # A scanned page can still carry a little text (e.g. a digital-signature stamp); OCR it when
        # the text layer is sparse and an image covers most of the page, and keep both word sets.
        image_heavy = n_chars < 400 and _image_coverage(p) > 0.7
        use_ocr = force_ocr or (allow_ocr and (n_chars < 25 or image_heavy))
        if use_ocr:
            zoom = 170 / 72
            pix = p.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            ocr_words = ocr_image(img, p.number, 1 / zoom)
            base = 0 if force_ocr else max((w.line for w in words), default=0) + 1
            for w in ocr_words:
                w.line += base
            words = ocr_words if (force_ocr or n_chars < 25) else words + ocr_words
        pages.append(Page(p.number, p.rect.width, p.rect.height, words, ocr=use_ocr))
    return Doc(path, sha, "pdf", pages, raw)


def _image_coverage(p: pymupdf.Page) -> float:
    area = p.rect.width * p.rect.height or 1
    cov = 0.0
    try:
        for info in p.get_image_info():
            b = pymupdf.Rect(info["bbox"]) & p.rect
            cov += b.width * b.height
    except Exception:  # noqa: BLE001
        return 0.0
    return min(1.0, cov / area)


def render_page(raw: bytes, sha: str, page_no: int, kind: str) -> Path:
    out = RENDER / f"{sha}_{page_no}.png"
    if out.exists():
        return out
    if kind == "image":
        Image.open(io.BytesIO(raw)).convert("RGB").save(out)
        return out
    pdf = pymupdf.open(stream=raw, filetype="pdf")
    zoom = RENDER_DPI / 72
    pdf[page_no].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).save(out)
    return out


# ---------------------------------------------------------------- search helpers

_norm_re = re.compile(r"[^a-z0-9]+")


def norm(s: str) -> str:
    return _norm_re.sub(" ", s.lower()).strip()


_compact_re = re.compile(r"[^a-z0-9]+")


def compact(s: str) -> str:
    return _compact_re.sub("", s.lower().replace("&", "and"))


def compact_line(words: list[Word]) -> tuple[str, list[int]]:
    """Concatenate words as lowercase alphanumerics with a char->word index map. Lets matching
    ignore spacing, which OCR engines frequently drop ("NOCNo", "DateofIssue")."""
    chars, owner = [], []
    for i, w in enumerate(words):
        c = compact(w.text)
        chars.append(c); owner.extend([i] * len(c))
    return "".join(chars), owner


def compact_boundaries(words: list[Word]) -> list[bool]:
    """For each compact char: does a new word or punctuation-separated part start here?"""
    out = []
    for w in words:
        prev_alnum = False
        for ch in w.text.lower().replace("&", "and"):
            if ch.isalnum():
                out.append(not prev_alnum)
                prev_alnum = True
            else:
                prev_alnum = False
    return out


def find_phrase(page: Page, phrase: str) -> list[list[Word]]:
    """Find a phrase (case/space/punctuation-insensitive) and return the matching word runs."""
    target = compact(phrase)
    if not target:
        return []
    cache = getattr(page, "_compact", None)
    if cache is None:
        cache = [(ln, *compact_line(ln), compact_boundaries(ln)) for ln in page.lines()]
        page._compact = cache
    hits = []
    for ln, s, owner, bnd in cache:
        start = s.find(target)
        while start != -1:
            # must begin at a word start, or after a run that clearly ends a word in OCR output
            if start == 0 or owner[start] != owner[start - 1] or (start < len(bnd) and bnd[start]) \
                    or not s[start - 1].isalpha() or not target[0].isalpha():
                hits.append(ln[owner[start]:owner[start + len(target) - 1] + 1])
            start = s.find(target, start + 1)
    return hits


def union_bbox(words: list[Word]) -> list[float]:
    return [min(w.x0 for w in words), min(w.y0 for w in words), max(w.x1 for w in words), max(w.y1 for w in words)]
