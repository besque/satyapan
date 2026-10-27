# Satyapan — application validation and document verification for AICTE approvals

Pre-scrutiny decision support for **Extension of Approval (self-disclosure)** under the **APH 2024-27**.
Everything runs locally and free: no cloud APIs, no LLMs, no paid services.

## What it does

| Problem-statement objective | How it is done here |
|---|---|
| Missing / incomplete / expired / inconsistent documents | Annexure-2 (2.1) checklist as **executable rules** (`backend/app/rules/aph_2024_27.yaml`), each quoting its APH clause; date, name, number and coordinate cross-checks across documents and the form |
| Reuse AICTE's existing institutional records | **Ledger built from 84 real public EoA letters** (Annexure-18 mandatory disclosure): 70 institutions, 104 approvals, 1,052 course rows, each linked to its public source URL + SHA-256 |
| Detect alterations, duplication, anomalies | PDF **revision recovery and diff**, **white-out detection** (text painted over), overlapping text, **generator fingerprints** learned from genuine files, editor-producer checks, DSC validation (pyHanko), photo EXIF/GPS, perceptual hash + **ORB/RANSAC** photo matching |
| Verify with issuing authorities | Connector per source returning *verified / mismatch / expired / pending / source unavailable / manual review*, with request, response and timestamp; QR payload check; draft request letter when a source is down |
| Infrastructure compliance | Annexure-3 built-up area and Annexure-5 faculty/cadre norms computed with the working shown; photo geotag vs campus; reused photos |
| Dashboard, alerts, audit | Green/amber/red queue, cross-institution **network graph**, verification queue, **hash-chained audit log** |
| Human in the loop | Every finding is reviewable (reason required); adverse recommendations are **blocked** until critical/high findings are reviewed |

**The idea in one line:** clicking any highlight on a document shows *why* it was marked: the evidence on the page, the rule and APH clause (opens the handbook page highlighted), how the number was computed, and what fixes it.

## Real vs simulated

* **Real institutions (Bangalore):** Dayananda Sagar College of Engineering and B.M.S. College of Engineering are checked using only the documents they publish on their websites (approval letters 2015-2027, fire certificates, occupancy certificate, mandatory disclosures). Findings are worded as observations about the *publicly posted* copies, e.g. "the posted fire clearance was valid until 15 Mar 2024; a renewed one may exist".
* **Real:** APH 2024-27 text and norms, 84 public EoA letters and the ledger built from them, generator fingerprints learned from them, 43 CC-licensed infrastructure photos (Wikimedia Commons, attribution in `data/raw/photos/manifest.json`), OSM map tiles, all forensics/signature/QR/OCR computation.
* **Simulated (clearly labelled in the UI):** the 14 demo institutions (invented names), their certificates (every page carries a *SYNTHETIC TEST DOCUMENT* footer), the issuer registers (fire services, SHCIL e-stamp, municipal OC, ICAI UDIN), and the test DSC PKI.

## Run

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt     # Windows; use .venv/bin on Linux/macOS
python scripts/fetch_aph.py          # AICTE Approval Process Handbook 2024-27 (+ text)
python scripts/collect_eoa.py        # download public EoA letters (+ manifest with provenance)
python scripts/collect_photos.py     # CC-licensed photos
python scripts/dedupe_photos.py
python scripts/build_ledger.py       # parse letters -> institutional record
python scripts/build_profiles.py     # learn generator fingerprints (real letters + reference set)
python scripts/collect_real_institutions.py  # DSCE + BMSCE public documents
python scripts/make_eoa_samples.py   # real + tampered letters for the EoA verifier, corpus stats
python scripts/seed_demo.py          # generate + process the 14 test applications, then load the real colleges
python scripts/evaluate.py           # metrics -> Evaluation screen
cd frontend && npm install && npm run build && cd ..
cd backend && ../.venv/Scripts/python -m uvicorn app.api:app --port 8000
```
Open http://127.0.0.1:8000 (or `npm run dev` in `frontend/` for development on :5173).

## Demo script (about 6 minutes)

Quick sign-in links: `/?as=officer`, `/?as=verifier`, `/?as=admin`, `/?as=inst:1-9940183347`.

1. **Applications**: one table, red/orange/green. Filter "Real institutions" shows DSCE and BMSCE.
2. **B.M.S. College of Engineering** (real): *Fire safety certificate has expired*. Open the document; the side list shows each item, click one to see it on the page. The validity was worked out from "renewed for a further period of two years" (15 Mar 2022). Also: partial occupancy certificate from 2019, beyond the 2-year allowance in Annexure-3.
3. **Dayananda Sagar College of Engineering** (real): *Wrong document uploaded*. The file their disclosure links as "Fire and Safety Certificate" is a fire-extinguisher disposal certificate from a private firm.
4. **Neelkamal Tarai** (test): *Text covered and retyped*. "Show earlier version" brings back the original date.
5. **Links between institutions**: drag, zoom, Enlarge. Kesarveni ↔ Neelkamal Tarai share 6 faculty; Tejasvarna re-used Ratnaparvat's fire certificate (Ratnaparvat stays green, its copy is confirmed with the issuer).
6. **Issuer checks**: Tamil Nadu fire service offline → letter drafted; admin sets it online → retry → confirmed.
7. **Check an approval letter**: a real letter → matches the AICTE record; the same letter with the intake doubled → caught twice (the file and the record).
8. **Institution sign-in** (Shaktikund): Check before submitting → upload the renewed fire certificate → only the faculty shortfall remains.
9. **Activity log**: intact.

## Layout

```
backend/app/   docmodel (text layer + OCR with boxes) · extract/ (EoA parser, field extractors) · forensics/ (pdf, structure, image)
               rules/ (YAML + engine + norms + citations) · verify/ (connectors, registry) · graph · pipeline · api
scripts/       data collection, ledger, profiles, demo seed, evaluation
frontend/      React + Vite UI
data/          raw corpus, ledger DB, generated sets, eval report
```
