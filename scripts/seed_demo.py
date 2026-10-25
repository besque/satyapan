"""Regenerate the 14-application demo set and load it (the real public-EoA ledger is kept).

  python scripts/seed_demo.py [--no-generate]
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
logging.disable(logging.CRITICAL)

from app import audit, db, pipeline  # noqa: E402
from app.config import SYNTH  # noqa: E402


def reset_applications() -> None:
    with db.tx() as c:
        for t in ("applications", "documents", "findings", "verifications", "entities", "reviews", "audit"):
            c.execute(f"DELETE FROM {t}")
        c.execute("DELETE FROM approval_courses WHERE approval_id IN (SELECT id FROM approvals WHERE source_url IS NULL OR source_url='')")
        c.execute("DELETE FROM approvals WHERE source_url IS NULL OR source_url=''")
        c.execute("DELETE FROM institutions WHERE source='synthetic'")


def main() -> None:
    if "--no-generate" not in sys.argv:
        from app.synth import generate
        print("generating demo set ...", flush=True)
        generate.generate("demo")
    reset_applications()
    from app.verify import registry
    for src in registry.sources():
        if src["kind"] != "not connected":
            registry.set_available(src["name"], src["name"] != "fire_tn")   # demo: Tamil Nadu fire portal starts "offline"
    audit.log("seed", "system", "demo.seeded", "all", {"set": "demo"})
    ids = pipeline.import_synthetic(SYNTH / "demo")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import load_real_cases
    ids += load_real_cases.main()
    print()
    for aid in ids:
        a = db.q1("SELECT a.*, i.name FROM applications a JOIN institutions i ON i.permanent_id=a.permanent_id WHERE a.id=?", (aid,))
        fails = db.q("SELECT kind, rule_id FROM findings WHERE application_id=? AND status='fail'", (aid,))
        print(f"{aid} {a['lane']:6} risk={a['risk']:5.1f} {a['name'][:44]:44} fails={[f['rule_id'] for f in fails]}")
    print("audit chain:", audit.verify_chain())


if __name__ == "__main__":
    main()
