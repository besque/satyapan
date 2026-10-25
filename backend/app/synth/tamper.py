"""Realistic manipulation techniques used to build labelled forgery test cases."""
from __future__ import annotations

import io
import os
import random
import tempfile

import pymupdf
from PIL import Image, ImageOps


def _first_rect(page: pymupdf.Page, text: str):
    hits = page.search_for(text)
    if not hits:
        raise ValueError(f"text not found for tamper: {text!r}")
    return hits[0]


def whiteout_incremental(pdf: bytes, old: str, new: str, page_no: int | None = None) -> bytes:
    """Paint a white box over `old` and type `new` on top, saved as an incremental update
    (what most 'free PDF editor' tools do)."""
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "x.pdf")
        open(p, "wb").write(pdf)
        d = pymupdf.open(p)
        pages = [d[page_no]] if page_no is not None else list(d)
        for page in pages:
            hits = page.search_for(old)
            if not hits:
                continue
            r = hits[0]
            page.draw_rect(r + (-0.8, -0.8, 0.8, 0.8), color=None, fill=(1, 1, 1), overlay=True)
            page.insert_text((r.x0, r.y1 - 2.0), new, fontsize=r.height * 0.78, fontname="helv")
            break
        else:
            raise ValueError(f"text not found for tamper: {old!r}")
        d.saveIncr()
        d.close()
        return open(p, "rb").read()


def redact_resave(pdf: bytes, replacements: list[tuple[str, str]], producer: str | None = None) -> bytes:
    """Remove the original glyphs (true redaction), retype, and fully re-save (no revision history)."""
    d = pymupdf.open(stream=pdf, filetype="pdf")
    todo = []
    for page in d:
        for old, new in replacements:
            for r in page.search_for(old):
                page.add_redact_annot(r, fill=(1, 1, 1))
                todo.append((page, r, new))
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)
    for page, r, new in todo:
        page.insert_text((r.x0, r.y1 - 2.0), new, fontsize=r.height * 0.78, fontname="helv")
    if producer:
        md = d.metadata
        md["producer"] = producer
        md["creator"] = producer
        d.set_metadata(md)
    return d.tobytes(garbage=4, deflate=True)


def photo_reuse(img_bytes: bytes, seed: int) -> bytes:
    """Same photo resubmitted by another institution: crop, resize, maybe mirror, recompress."""
    rnd = random.Random(seed)
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    w, h = im.size
    dx, dy = int(w * rnd.uniform(0.03, 0.09)), int(h * rnd.uniform(0.03, 0.09))
    im = im.crop((dx, dy, w - dx // 2, h - dy // 2)).resize((int(w * 0.8), int(h * 0.8)))
    if rnd.random() < 0.3:
        im = ImageOps.mirror(im)
    b = io.BytesIO()
    im.save(b, format="JPEG", quality=rnd.randint(70, 85))
    return b.getvalue()
