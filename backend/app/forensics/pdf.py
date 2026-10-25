"""PDF structural forensics. Each signal is a *preliminary indicator* with evidence boxes,
never a verdict: the reviewer sees exactly which words/regions triggered it.
"""
from __future__ import annotations

import difflib
import io
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

import imagehash
import pymupdf
from PIL import Image

from ..docmodel import Doc, Page, Word, load, union_bbox

EOF_RX = re.compile(rb"%%EOF[\r\n]*")

# Tools that *edit* PDFs (vs. merely merge/compress/print). Used for wording + severity only.
EDITORS = ["photoshop", "pdfescape", "sejda", "pdf-xchange", "foxit phantom", "nitro", "smallpdf", "pdffiller",
           "inkscape", "libreoffice", "microsoft® word", "microsoft word", "canva", "wps", "pdf candy", "acrobat pro",
           "pdf24", "dochub", "pdfelement", "master pdf", "ilovepdf edit"]
REPROCESSORS = ["ilovepdf", "pdfium", "cairo", "ghostscript", "adobe scan", "camscanner", "microsoft: print to pdf",
                "chrome", "skia", "quartz", "mac os x"]


def _pdf_date(s: str | None):
    if not s:
        return None
    m = re.match(r"D:(\d{4})(\d{2})(\d{2})(\d{2})?(\d{2})?(\d{2})?([+\-Z])?(\d{2})?'?(\d{2})?", s)
    if not m:
        return None
    y, mo, d, hh, mi, ss, sign, tzh, tzm = m.groups()
    dt = datetime(int(y), int(mo), int(d), int(hh or 0), int(mi or 0), int(ss or 0))
    if sign in ("+", "-") and tzh:
        off = timedelta(hours=int(tzh), minutes=int(tzm or 0))
        dt = dt.replace(tzinfo=timezone(off if sign == "+" else -off))
    return dt


def revisions(raw: bytes) -> dict:
    """Split a PDF into its saved revisions (incremental updates)."""
    ends = [m.end() for m in EOF_RX.finditer(raw)]
    head = raw[:2048]
    linearized = b"/Linearized" in head
    revs = []
    for e in ends:
        try:
            d = pymupdf.open(stream=raw[:e], filetype="pdf")
            revs.append({"end": e, "pages": d.page_count})
        except Exception:  # noqa: BLE001
            revs.append({"end": e, "pages": 0})
    # A linearized file's first %%EOF closes the first-page hint section, not a user edit.
    real = [r for r in revs if r["pages"] > 0]
    if linearized and len(revs) >= 2 and revs[0]["pages"] == 0:
        real = [r for r in revs[1:] if r["pages"] > 0] or real
    return {"linearized": linearized, "eof_markers": len(ends), "revisions": real}


def revision_diff(raw: bytes, doc_latest: Doc) -> list[dict]:
    """Recover previous revision(s) and report words that changed, with boxes in the final revision."""
    info = revisions(raw)
    revs = info["revisions"]
    if len(revs) < 2:
        return []
    out = []
    prev_raw = raw[:revs[-2]["end"]]
    try:
        prev_doc = load("prev.pdf", data=prev_raw)
    except Exception:  # noqa: BLE001
        return []
    if prev_doc.pages and len(doc_latest.pages) > len(prev_doc.pages) and all(
            _page_sig(prev_doc.pages[i]) in {_page_sig(p) for p in doc_latest.pages} for i in range(len(prev_doc.pages))):
        return [{"type": "pages_appended", "added": len(doc_latest.pages) - len(prev_doc.pages),
                 "prev_pages": len(prev_doc.pages)}]
    sig_rects = _signature_rects(raw)
    for i, page in enumerate(doc_latest.pages):
        if i >= len(prev_doc.pages):
            out.append({"type": "page_added", "page": i})
            continue
        if page.ocr or prev_doc.pages[i].ocr:
            # OCR output is not stable between two renders: compare the pages visually instead
            vis = _visual_change(prev_raw, raw, i, sig_rects.get(i, []))
            if vis:
                out.append({"type": "text_changed", "page": i, "op": "visual", "before": "(image region)",
                            "after": "(changed image region)", "bbox": vis})
            continue
        a = [w.text for w in prev_doc.pages[i].words]
        b = [w.text for w in page.words]
        if a == b:
            continue
        sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            new_words = page.words[j1:j2]
            if new_words and any(_inside(union_bbox(new_words), r) for r in sig_rects.get(i, [])):
                continue          # signature appearance added when the document was signed
            out.append({
                "type": "text_changed", "page": i, "op": tag,
                "before": " ".join(a[i1:i2]), "after": " ".join(b[j1:j2]),
                "bbox": union_bbox(new_words) if new_words else (union_bbox(prev_doc.pages[i].words[i1:i2]) if i2 > i1 else None),
            })
    return out


def _signature_rects(raw: bytes) -> dict[int, list]:
    out: dict[int, list] = {}
    try:
        d = pymupdf.open(stream=raw, filetype="pdf")
        for p in d:
            for w in p.widgets() or []:
                if w.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE:
                    out.setdefault(p.number, []).append(list(w.rect))
            for a in p.annots() or []:
                if a.type[1] in ("Widget", "Stamp", "FreeText"):
                    out.setdefault(p.number, []).append(list(a.rect))
    except Exception:  # noqa: BLE001
        pass
    return out


def _inside(b, r, pad=4) -> bool:
    return b[0] >= r[0] - pad and b[1] >= r[1] - pad and b[2] <= r[2] + pad and b[3] <= r[3] + pad


def _visual_change(raw_a: bytes, raw_b: bytes, page_no: int, mask: list) -> list | None:
    """Pixel difference between two revisions of a scanned page (signature boxes masked)."""
    import numpy as np
    try:
        pa = pymupdf.open(stream=raw_a, filetype="pdf")[page_no]
        pb = pymupdf.open(stream=raw_b, filetype="pdf")[page_no]
    except Exception:  # noqa: BLE001
        return None
    z = 60 / 72
    ia = pa.get_pixmap(matrix=pymupdf.Matrix(z, z), annots=False)
    ib = pb.get_pixmap(matrix=pymupdf.Matrix(z, z), annots=False)
    if (ia.width, ia.height) != (ib.width, ib.height):
        return [0, 0, pb.rect.width, pb.rect.height]
    a = np.frombuffer(ia.samples, np.uint8).reshape(ia.height, ia.width, ia.n)[:, :, :3].astype(np.int16)
    b = np.frombuffer(ib.samples, np.uint8).reshape(ib.height, ib.width, ib.n)[:, :, :3].astype(np.int16)
    diff = (np.abs(a - b).max(axis=2) > 40)
    for r in mask:
        diff[int(r[1] * z):int(r[3] * z) + 1, int(r[0] * z):int(r[2] * z) + 1] = False
    if diff.mean() < 0.002:
        return None
    ys, xs = np.nonzero(diff)
    return [float(xs.min() / z), float(ys.min() / z), float((xs.max() + 1) / z), float((ys.max() + 1) / z)]


def _page_sig(p: Page) -> str:
    return " ".join(w.text for w in p.words[:60])


def producer_profile(meta: dict) -> dict:
    prod = (meta.get("producer") or "").strip()
    creator = (meta.get("creator") or "").strip()
    both = f"{prod} {creator}".lower()
    kind = "unknown"
    if any(e in both for e in EDITORS):
        kind = "editor"
    elif any(r in both for r in REPROCESSORS):
        kind = "reprocessed"
    elif prod or creator:
        kind = "generator"
    return {"producer": prod, "creator": creator, "kind": kind,
            "created": meta.get("creationDate"), "modified": meta.get("modDate")}


def hidden_text(raw: bytes) -> list[dict]:
    """Text that is painted over by a later opaque white shape (white-out), and the text drawn on top of it."""
    pdf = pymupdf.open(stream=raw, filetype="pdf")
    hits = []
    for page in pdf:
        try:
            traces = page.get_texttrace()
            drawings = page.get_drawings()
        except Exception:  # noqa: BLE001
            continue
        whites = []
        for d in drawings:
            fill = d.get("fill")
            if fill and all(c > 0.97 for c in fill[:3]) and d.get("fill_opacity", 1) > 0.9:
                r = d["rect"]
                if r.width * r.height < page.rect.width * page.rect.height * 0.25 and r.width > 3 and r.height > 3:
                    whites.append((d.get("seqno", 0), r))
        if not whites:
            continue
        for seq_w, r in whites:
            covered, on_top, fonts_top = [], [], set()
            for t in traces:
                if not pymupdf.Rect(t["bbox"]).intersects(r) or t.get("opacity", 1) == 0 or t.get("type") == 3:
                    continue
                for ch in t["chars"]:
                    cb = pymupdf.Rect(ch[3])
                    cx, cy = (cb.x0 + cb.x1) / 2, (cb.y0 + cb.y1) / 2
                    if not (r.x0 <= cx <= r.x1 and r.y0 <= cy <= r.y1) or chr(ch[0]).isspace():
                        continue
                    if t["seqno"] < seq_w:
                        covered.append(chr(ch[0]))
                    else:
                        on_top.append(chr(ch[0])); fonts_top.add(t["font"])
            if covered:
                hits.append({
                    "page": page.number, "bbox": list(r),
                    "covered_text": "".join(covered)[:200],
                    "overlay_text": "".join(on_top)[:200],
                    "overlay_fonts": sorted(fonts_top),
                })
    return hits


DATEISH = re.compile(r"\d")


def font_anomalies(doc: Doc) -> list[dict]:
    """Digits/date words set in a font that is rare in this document - typical of retyped values."""
    if doc.kind != "pdf":
        return []
    words = [w for p in doc.pages for w in p.words if not p.ocr]
    if len(words) < 40:
        return []
    # Compare font *families*: bold values beside regular labels are normal; a value set in
    # a different typeface (Arial inside a Times document) is what retyping tends to leave behind.
    fam = lambda f: re.split(r"[-,+]", re.sub(r"^[A-Z]{6}\+", "", f or ""))[0].replace("MT", "").replace("PS", "").lower()  # noqa: E731
    fonts = Counter(fam(w.font) for w in words)
    total = sum(fonts.values())
    out = []
    for p in doc.pages:
        if p.ocr:
            continue
        for ln in p.lines():
            line_fams = Counter(fam(w.font) for w in ln)
            for w in ln:
                f = fam(w.font)
                rare_doc = fonts[f] / total < 0.03
                odd_in_line = len(ln) >= 3 and line_fams[f] == 1 and len(line_fams) > 1
                if DATEISH.search(w.text) and rare_doc and odd_in_line:
                    dominant = next(x for x in ln if fam(x.font) == line_fams.most_common(1)[0][0])
                    out.append({"page": p.number, "bbox": w.bbox, "text": w.text, "font": w.font, "size": w.size,
                                "line_font": dominant.font, "line_size": dominant.size})
    return out


def overlapping_words(doc: Doc) -> list[dict]:
    """Two *different* words occupying the same spot: a value typed over another one that was hidden."""
    out = []
    for p in doc.pages:
        if p.ocr:
            continue
        ws = sorted((w for w in p.words if len(w.text) >= 2 and any(ch.isalnum() for ch in w.text)), key=lambda w: w.y0)
        for i, a in enumerate(ws):
            for b in ws[i + 1:]:
                if b.y0 > a.y1:
                    break
                ix = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
                iy = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
                inter = ix * iy
                small = min((a.x1 - a.x0) * (a.y1 - a.y0), (b.x1 - b.x0) * (b.y1 - b.y0))
                if small > 0 and inter / small > 0.5 and a.text != b.text:
                    out.append({"page": p.number, "bbox": union_bbox([a, b]), "texts": [a.text, b.text],
                                "fonts": [a.font, b.font]})
    return out


def embedded_images(raw: bytes, max_images: int = 40) -> list[dict]:
    """Perceptual hashes of embedded images (seals, signatures, photos) for cross-document reuse detection."""
    pdf = pymupdf.open(stream=raw, filetype="pdf")
    out, seen = [], set()
    for page in pdf:
        for img in page.get_images(full=True):
            xref = img[0]
            if xref in seen or len(out) >= max_images:
                continue
            seen.add(xref)
            try:
                info = pdf.extract_image(xref)
                if info["width"] < 40 or info["height"] < 40:
                    continue
                pil = Image.open(io.BytesIO(info["image"])).convert("RGB")
                rects = page.get_image_rects(xref)
                out.append({"page": page.number, "xref": xref, "w": info["width"], "h": info["height"],
                            "phash": str(imagehash.phash(pil)), "bbox": list(rects[0]) if rects else None})
            except Exception:  # noqa: BLE001
                continue
    return out


def signatures(raw: bytes, trust_roots: list | None = None) -> list[dict]:
    """Validate embedded PAdES/CMS signatures with pyHanko. Reports coverage and post-signing changes."""
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    out = []
    try:
        reader = PdfFileReader(io.BytesIO(raw), strict=False)
        sigs = reader.embedded_signatures
    except Exception as e:  # noqa: BLE001
        return [{"error": f"unreadable: {e}"}]
    vc = ValidationContext(trust_roots=trust_roots or [], allow_fetching=False)
    for s in sigs:
        rec = {"field": s.field_name}
        try:
            st = validate_pdf_signature(s, vc)
            cert = st.signing_cert
            rec.update({
                "signer": cert.subject.human_friendly if cert else None,
                "issuer": cert.issuer.human_friendly if cert else None,
                "intact": st.intact, "valid": st.valid, "trusted": st.trusted,
                "coverage": st.coverage.name if st.coverage else None,
                "modified_after_signing": st.coverage is not None and st.coverage.name != "ENTIRE_FILE",
                "signing_time": str(st.signer_reported_dt) if st.signer_reported_dt else None,
                "bottom_line": st.bottom_line,
            })
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            try:
                cert = s.signer_cert
                rec["signer"] = cert.subject.human_friendly if cert else None
            except Exception:  # noqa: BLE001
                pass
            legacy = "1.2.840.113549.1.1.5" in msg or "sha1" in msg.lower()
            rec.update({"error": "signed with SHA-1, an outdated algorithm that cannot be validated" if legacy else msg[:200],
                        "intact": None, "legacy_algorithm": legacy})
        out.append(rec)
    return out


def analyse(doc: Doc, trust_roots: list | None = None) -> dict:
    if doc.kind != "pdf":
        return {"kind": "image"}
    pdf = pymupdf.open(stream=doc.raw, filetype="pdf")
    meta = pdf.metadata or {}
    rv = revisions(doc.raw)
    from . import structure
    prof = producer_profile(meta)
    return {
        "kind": "pdf",
        "meta": prof,
        "structure": structure.compare(prof["producer"], doc.raw) if prof["producer"] else None,
        "overlapping_words": overlapping_words(doc),
        "created_dt": str(_pdf_date(meta.get("creationDate")) or ""),
        "modified_dt": str(_pdf_date(meta.get("modDate")) or ""),
        "revisions": rv,
        "revision_diff": revision_diff(doc.raw, doc),
        "hidden_text": hidden_text(doc.raw),
        "font_anomalies": font_anomalies(doc),
        "images": embedded_images(doc.raw),
        "signatures": signatures(doc.raw, trust_roots),
        "ocr_pages": [p.number for p in doc.pages if p.ocr],
    }
