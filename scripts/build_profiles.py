"""Learn generator fingerprints from documents known to be genuine:

* real AICTE EoA letters in the public corpus (Oracle BI / Analytics Publisher), single-revision only;
* a *separate* reference set of issuer documents verified at source (fire NOC, OC, receipts...),
  disjoint from the demo/evaluation applications, standing in for an issuer's known-good samples.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
logging.disable(logging.CRITICAL)

import pymupdf  # noqa: E402

from app.config import EOA_DIR, SYNTH  # noqa: E402
from app.forensics import pdf as F, structure  # noqa: E402

GENERATORS = {"Oracle BI Publisher 11.1.1.9.0", "Oracle Analytics Publisher"}


def main() -> None:
    if "--no-reference" not in sys.argv:
        from app.synth import generate
        generate.generate("reference", n=9, seed=77, out_root=SYNTH / "reference", reset_registry=False, clean_only=True)
    samples = []
    for f in sorted(EOA_DIR.glob("*.pdf")):
        raw = f.read_bytes()
        prod = (pymupdf.open(stream=raw, filetype="pdf").metadata or {}).get("producer", "")
        if prod in GENERATORS and len(F.revisions(raw)["revisions"]) == 1:
            samples.append((prod, raw))
    n_real = len(samples)
    for f in sorted((SYNTH / "reference").rglob("*.pdf")):
        if f.name.startswith("affidavit"):
            continue          # signed affidavits are institution-produced, not issuer output
        raw = f.read_bytes()
        prod = (pymupdf.open(stream=raw, filetype="pdf").metadata or {}).get("producer", "")
        if prod and len(F.revisions(raw)["revisions"]) == 1:
            samples.append((prod, raw))
    prof = structure.build_profiles(samples)
    print(f"real samples={n_real} reference samples={len(samples) - n_real}")
    for k, v in prof.items():
        print(f"  {k[:50]:50} n={v['n']}")


if __name__ == "__main__":
    main()
