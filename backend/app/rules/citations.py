"""Locate a rule's quoted clause inside the APH PDF so the UI can open the exact page, highlighted."""
from __future__ import annotations

from functools import lru_cache

import pymupdf

from ..config import APH_PDF


@lru_cache(maxsize=1)
def _doc():
    return pymupdf.open(APH_PDF)


@lru_cache(maxsize=512)
def locate(quote: str) -> dict | None:
    if not quote:
        return None
    d = _doc()
    probes = [quote, quote[:80], quote[:50], quote[:32]]
    for probe in probes:
        probe = " ".join(probe.split())
        for p in d:
            rects = p.search_for(probe)
            if rects:
                printed = None
                for ln in p.get_text().splitlines()[:6]:
                    if ln.strip().isdigit():
                        printed = int(ln.strip()); break
                return {"pdf_page": p.number, "printed_page": printed,
                        "rects": [[r.x0, r.y0, r.x1, r.y1] for r in rects[:6]],
                        "page_size": [p.rect.width, p.rect.height]}
    return None
