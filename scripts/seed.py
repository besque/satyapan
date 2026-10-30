"""Load the demo: real public data from data/real/ plus a simulated 2027-28 approval cycle up to the demo date.

The simulation runs day by day through the same workflow engine officers use, so the history, reminders and
escalations are exactly what the system would have produced. Planted cases (see backend/app/demo.py):
  Kesarveni IT, Indore            EVC waiting with the Regional Office, at risk; reaches senior management today
  Neelkamal Tarai IT, Lucknow     new institution; compliance overdue with the institution; needs fast-tracking
  Narmadatat IT, Jabalpur         live lease equals the longest course: EoA blocked until the extended lease is verified
  Shaktikund CE, Bhopal           lease runs out for 2029-30; reminders started two years ahead
  Ratnaparvat IM, Pune            approved 29 Apr; security deposit unpaid; penalty ladder of Cl. 2.25 (f)
  Tejasvarna CE, Hyderabad        fire safety certificate expires 5 June
  Jalataranga CE, Mysuru          last year's undertaking carried into this year's scrutiny, then closed
  Kaveriprabha CE, Coimbatore     sent back from EVC to re-scrutiny with the reason recorded
  Sri Vanadurga IT, Hosur         Letter of Deficiency, appeal filed, Standing Appellate Committee to be fixed
  Hemshikhar IM, Gwalior          EVC fixed on time but too late for the last Executive Committee
  Mahanadi Prabha, Bilaspur       EVC held, report not recorded
  Konkan Ratna CE, Mumbai         Structural Stability Certificate (five-year validity) runs out 19 June
  Swarnadeepa IT, Nagpur          new institution approved subject to conditions; deposit to be verified
Run:  python scripts/seed.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import demo  # noqa: E402

if __name__ == "__main__":
    demo.build()
