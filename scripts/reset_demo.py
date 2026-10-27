"""Put the demo back to its starting state.

  python scripts/reset_demo.py          quick reset (seconds): removes institution self-checks, officer
                                        reviews/recommendations and rule changes; sets issuer sources back
  python scripts/reset_demo.py full     full reset (~15 min): re-processes every application from scratch
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
logging.disable(logging.CRITICAL)

from app import audit, db, pipeline  # noqa: E402
from app.verify import registry  # noqa: E402


def quick() -> None:
    runs = [r["id"] for r in db.q("SELECT id FROM applications WHERE source='precheck'")]
    with db.tx() as c:
        for aid in runs:
            for t in ("findings", "verifications", "documents", "entities", "reviews"):
                c.execute(f"DELETE FROM {t} WHERE application_id=?", (aid,))
            c.execute("DELETE FROM applications WHERE id=?", (aid,))
        c.execute("DELETE FROM reviews")            # officer confirm/dismiss and recommendations
        c.execute("DELETE FROM rule_overrides")     # rule edits made on the Rules page
    for src in registry.sources():
        if src["kind"] != "not connected":
            registry.set_available(src["name"], src["name"] != "fire_tn")   # Tamil Nadu fire portal starts "offline"
    pipeline.refresh_network()
    audit.log("reset", "system", "demo.reset", "all", {"removed_self_checks": len(runs)})
    print(f"Demo reset: removed {len(runs)} self-check run(s), officer reviews and rule changes.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "full":
        subprocess.run([sys.executable, str(ROOT / "scripts" / "seed_demo.py"), "--no-generate"], check=True)
        print("Full reset done.")
    else:
        quick()
