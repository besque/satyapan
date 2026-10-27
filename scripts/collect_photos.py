"""Collect freely-licensed infrastructure photos (classrooms, labs, libraries in India) from
Wikimedia Commons, with licence + attribution, to act as institution-submitted infrastructure evidence.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "photos"
API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "Satyapan/1.0 (document verification)"}
CATEGORIES = {
    "classroom": ["Category:Classrooms in India", "Category:Lecture halls in India"],
    "laboratory": ["Category:Laboratories in India", "Category:Computer labs in India", "Category:Engineering laboratories"],
    "library": ["Category:Libraries in India", "Category:University libraries in India"],
    "workshop": ["Category:Workshops (rooms)", "Category:Machine shops"],
    "building": ["Category:Engineering colleges in India"],
}
OK_LICENSES = re.compile(r"(CC0|CC BY|Public domain|PD|cc-by|cc-zero)", re.I)


def members(cat: str, limit: int = 40) -> list[dict]:
    r = requests.get(API, params={
        "action": "query", "format": "json", "generator": "categorymembers", "gcmtitle": cat, "gcmtype": "file",
        "gcmlimit": limit, "prop": "imageinfo", "iiprop": "url|extmetadata|size|mime", "iiurlwidth": 1024,
    }, headers=UA, timeout=40)
    pages = r.json().get("query", {}).get("pages", {})
    return list(pages.values())


def main(per_kind: int = 9) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8")) if manifest_path.exists() else {}
    for kind, cats in CATEGORIES.items():
        got = sum(1 for v in manifest.values() if v["kind"] == kind)
        for cat in cats:
            if got >= per_kind:
                break
            try:
                items = members(cat)
            except Exception as e:  # noqa: BLE001
                print("FAIL", cat, e); continue
            for it in items:
                if got >= per_kind:
                    break
                ii = (it.get("imageinfo") or [{}])[0]
                if ii.get("mime") not in ("image/jpeg",) or ii.get("width", 0) < 800:
                    continue
                meta = ii.get("extmetadata", {})
                lic = re.sub("<[^>]+>", "", meta.get("LicenseShortName", {}).get("value", ""))
                if not OK_LICENSES.search(lic):
                    continue
                url = ii.get("thumburl") or ii.get("url")
                name = f"{kind}_{it['pageid']}.jpg"
                if name in manifest:
                    continue
                try:
                    img = requests.get(url, headers=UA, timeout=60).content
                except Exception:  # noqa: BLE001
                    continue
                if not img.startswith(b"\xff\xd8"):
                    continue
                (OUT / name).write_bytes(img)
                manifest[name] = {
                    "kind": kind, "title": it["title"], "source": ii.get("descriptionurl"), "license": lic,
                    "artist": re.sub("<[^>]+>", "", meta.get("Artist", {}).get("value", ""))[:120],
                }
                got += 1
                print("OK", name, lic)
                time.sleep(0.4)
    manifest_path.write_text(json.dumps(manifest, indent=2), "utf-8")
    print("total", len(manifest))


if __name__ == "__main__":
    main()
