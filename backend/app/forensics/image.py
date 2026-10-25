"""Photo evidence checks: EXIF provenance (camera, software, time, GPS) and perceptual hashes."""
from __future__ import annotations

import io

import imagehash
import numpy as np
from PIL import ExifTags, Image

EDIT_SOFTWARE = ("photoshop", "gimp", "lightroom", "snapseed", "picsart", "canva", "pixlr", "facetune")


def _ratio(v):
    try:
        return float(v[0]) / float(v[1]) if isinstance(v, tuple) else float(v)
    except (TypeError, ZeroDivisionError):
        return 0.0


def _dms(vals, ref):
    d, m, s = (_ratio(x) for x in vals)
    v = d + m / 60 + s / 3600
    return -v if ref in ("S", "W", b"S", b"W") else v


def exif(raw: bytes) -> dict:
    im = Image.open(io.BytesIO(raw))
    out = {"width": im.width, "height": im.height}
    ex = im.getexif()
    if not ex:
        return out
    tags = {ExifTags.TAGS.get(k, k): v for k, v in ex.items()}
    out.update({"make": str(tags.get("Make", "")).strip("\x00"), "model": str(tags.get("Model", "")).strip("\x00"),
                "software": str(tags.get("Software", "")).strip("\x00")})
    sub = ex.get_ifd(0x8769)
    if sub:
        dto = sub.get(36867)
        if dto:
            out["taken"] = str(dto)
    gps = ex.get_ifd(0x8825)
    if gps and 2 in gps and 4 in gps:
        try:
            out["lat"] = round(_dms(gps[2], gps.get(1, "N")), 6)
            out["lon"] = round(_dms(gps[4], gps.get(3, "E")), 6)
        except Exception:  # noqa: BLE001
            pass
    return out


def hashes(raw: bytes) -> dict:
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    return {"phash": str(imagehash.phash(im)), "dhash": str(imagehash.dhash(im)),
            "phash_mirror": str(imagehash.phash(im.transpose(Image.FLIP_LEFT_RIGHT)))}


def ela_score(raw: bytes, quality: int = 90) -> float:
    """Error-level analysis summary: high local variance of recompression error hints at pasted regions."""
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    b = io.BytesIO(); im.save(b, format="JPEG", quality=quality); b.seek(0)
    re = Image.open(b)
    diff = np.abs(np.asarray(im, dtype=np.int16) - np.asarray(re, dtype=np.int16)).mean(axis=2)
    h, w = diff.shape
    cells = [diff[y:y + h // 8, x:x + w // 8].mean() for y in range(0, h - h // 8 + 1, h // 8) for x in range(0, w - w // 8 + 1, w // 8)]
    return float(np.max(cells) / (np.median(cells) + 1e-3))


def analyse(raw: bytes) -> dict:
    e = exif(raw)
    sw = (e.get("software") or "").lower()
    return {"kind": "image", "exif": e, "hashes": hashes(raw), "ela_ratio": round(ela_score(raw), 2),
            "edited_with": e.get("software") if any(s in sw for s in EDIT_SOFTWARE) else None}


def hamming(a: str, b: str) -> int:
    return int(imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b))


def same_scene(raw_a: bytes, raw_b: bytes, min_inliers: int = 25) -> dict:
    """Confirm a near-duplicate photo with ORB keypoints + RANSAC homography.

    Robust to the usual disguises (crop, resize, recompress, mirror) that defeat a plain hash.
    """
    import cv2

    def gray(raw):
        arr = np.frombuffer(raw, np.uint8)
        im = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        s = 900 / max(im.shape)
        return cv2.resize(im, None, fx=s, fy=s) if s < 1 else im

    a, b = gray(raw_a), gray(raw_b)
    orb = cv2.ORB_create(2000)
    ka, da = orb.detectAndCompute(a, None)
    best = {"inliers": 0, "mirrored": False}
    for mirrored, img_b in ((False, b), (True, cv2.flip(b, 1))):
        kb, db_ = orb.detectAndCompute(img_b, None)
        if da is None or db_ is None or len(ka) < 10 or len(kb) < 10:
            continue
        matches = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da, db_, k=2)
        good = [m for m, n in (p for p in matches if len(p) == 2) if m.distance < 0.75 * n.distance]
        if len(good) < 10:
            continue
        src = np.float32([ka[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst = np.float32([kb[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        _, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
        inl = int(mask.sum()) if mask is not None else 0
        if inl > best["inliers"]:
            best = {"inliers": inl, "mirrored": mirrored}
    best["same"] = best["inliers"] >= min_inliers
    return best
