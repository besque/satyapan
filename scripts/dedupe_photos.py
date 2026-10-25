"""Remove near-duplicate source photos (same scene, e.g. consecutive shots) from the pool, using the
same matcher the system uses for reuse detection. Writes data/raw/photos/duplicates.json."""
from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import RAW  # noqa: E402
from app.forensics.image import hamming, hashes, same_scene  # noqa: E402

D = RAW / "photos"


def main() -> None:
    files = sorted(D.glob("*.jpg"))
    raw = {f.name: f.read_bytes() for f in files}
    hs = {k: hashes(v) for k, v in raw.items()}
    drop: set[str] = set()
    for a, b in combinations(sorted(raw), 2):
        if a in drop or b in drop:
            continue
        d = min(hamming(hs[a]["phash"], hs[b]["phash"]), hamming(hs[a]["phash_mirror"], hs[b]["phash"]))
        if d <= 12 or (d <= 26 and same_scene(raw[a], raw[b])["same"]):
            drop.add(b)
            print(f"near-duplicate: {a} ~ {b} (hash distance {d})")
    (D / "duplicates.json").write_text(json.dumps(sorted(drop), indent=1), "utf-8")
    print(f"{len(drop)} dropped, {len(files) - len(drop)} unique photos remain")


if __name__ == "__main__":
    main()
