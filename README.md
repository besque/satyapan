# Avadhi: AICTE approval workflow, compliance and deadline tracking

Smart India Hackathon 2026, problem statement **SIH26262**: Integrated AICTE Approval Workflow Automation, Compliance
Monitoring and Alert Management System.

An AICTE approval is not one decision; it is dozens of time limits held by different people: each processing stage, the
EVC to be held, a security deposit due in 15 days, a lease running out, a fire certificate expiring, an undertaking to
finish a building. Today nobody sees all of them at once, so the one that matters is noticed only after it has run out,
usually just before the Academic Calendar date that cannot move. Avadhi gives every pending item **one owner and one
countdown, and counts every countdown back from that date**.

## The idea

1. **Count back from the calendar date.** Each application's route comes from APH Table 2.3. From the stages still to
   come, their usual durations and the Executive Committee's meeting dates, the system knows the latest date the current
   step must finish, and says *"hold the EVC by 3 June or this will miss 10 June"*: weeks before any step is overdue.
2. **Whose court is the ball in.** Every open item has exactly one holder: an AICTE office, a committee, the Executive
   Committee or the institution. Reminders go to the holder; escalation climbs the holder's chain only; reports split
   every day into "with AICTE" and "with the institution". A late institution is never counted against an officer.
3. **An approval is a list of promises.** Every condition an approval is granted subject to, and every certificate with a
   validity, becomes an item with a due date, the evidence needed, who verifies it and the clause behind it. What is still
   open is carried into next year's application automatically (APH Cl. 2.25 c). The lease rule (Cl. 2.1 e) and the
   security-deposit ladder (Cl. 2.25 f) are computed exactly.

Decisions stay with the competent authority: the system routes, reminds, escalates and drafts; officers record outcomes
and decisions, and every action is in a tamper-evident activity log.

## What it covers

| Problem statement | How it is done here |
|---|---|
| A. Routing | Routes exactly as APH Table 2.3 (22 natures incl. Chapter I); moves on by itself when a stage is recorded; return / send back with the reason recorded; electronic case summary and standard letters drafted from the record |
| B. Dashboards, pendency | Role-based home for senior management, Regulation Bureau, Regional Offices, committees, Executive Committee and institutions; stage-wise pendency, region-wise performance, bottleneck, ageing split by holder; hash-chained activity log |
| C. EVC | Queue fills by itself after scrutiny; the Regional Office fixes the date with a warning if the date is too late for the calendar; online EVC video upload (Cl. 1.9 f); reminders and escalation |
| D. Undertakings | Conditions chosen when approval is recorded (suggested by the system); due dates, evidence upload, verification, reminders, escalation, carry-forward |
| E. Lease and documents | Validity of fire, structural stability, occupancy and lease documents; reminders at 90/60/30/7/0 days; renewal upload and verification; expiry escalation; lease rule computed |
| F. Notifications, reports | Configurable reminder and escalation schedule; every message logged with date and channels; reports with CSV and print |
| Configurable rules | Rules page: every time limit, calendar date and reminder; each change needs a reason and is logged |

## Real data, and what is simulated

* **Real:** the APH 2024-27 text and its Table 2.3; 29 cited clauses shown on the handbook page with the text highlighted;
  **123 public AICTE approval letters of 72 institutions** (each with source URL and SHA-256). 23 of them granted approval
  with deficiencies to comply within a time limit written in the letter; each becomes a tracked undertaking. Where the next
  year's letter is public, the same deficiency was noted again in 3 of 6 cases. Certificate validity of two Bengaluru
  colleges as posted on their own websites. No simulated activity is attached to a real institution, and no notices are
  sent to them.
* **Sample data:** the institutions applying in the 2027-28 cycle (invented names) and their applications. The cycle is
  simulated day by day through the same engine the officers use, so every step, reminder and escalation happened on the
  date shown. It runs on 17 May 2027, 24 days before the last date for approval. Records from published letters are
  marked "Public record" in the app.

## Test results (`scripts/evaluate.py`, Test results page)

* Routing: 78 of 78 cases (22 natures × outcome scenarios) follow APH Table 2.3.
* Rules: 17 of 17 calculations correct (lease rule, deposit ladder, appeal window, validity, countdown).
* Alert timeliness, 3,000 simulated applications: 36% of late decisions never had a single overdue step, so per-step
  pendency alerts cannot see them; the countdown flagged 99%. Its early warning caught as many while still saveable as
  per-step alerts (62% vs 61%), with 70% of its warnings right against 13%, and 3% of on-time applications wrongly flagged
  against 25%.
* Every movement has its activity-log entry; the chain of fingerprints is intact.

## Run

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt     # Windows: .venv\Scripts\pip
python scripts/seed.py          # real data + the simulated cycle (a few seconds)
python scripts/evaluate.py      # Test results page
cd frontend && npm install && npm run build && cd ..
./start.sh                      # Windows: start.bat.  Open http://127.0.0.1:8000
```
`reset-demo.sh` / `reset-demo.bat` reload the demo and start the site.

Sign in with a user ID (any password for now; authentication is to be connected to AICTE's own sign-in), or click one of
the demo accounts under the sign-in box:

| User ID | Who |
|---|---|
| `akulkarni` | Adviser (Approval), senior management |
| `srao` | Deputy Director, Regulation Bureau |
| `pnair` | Regional Officer, Central Region |
| `riyer` | Expert member, scrutiny / EVC / hearing committees |
| `vmenon` | Member Secretary, for the Executive Committee |
| `siyer` | System administrator (Rules, system date) |
| Permanent ID | any institution, e.g. `1-0092614882` (Kesarveni), `1-0099246762` (Neelkamal Tarai) |

Shortcut links for presenting: `/?as=head`, `rb`, `ro`, `expert`, `ec`, `inst`, `inst2`, `admin`.

The cycle runs on a fixed system date (17 May 2027). The administrator can advance it on the Rules page; reminders and
escalations are checked for every day it moves. "Reload sample data" on the same page restores the starting state.

## Demo (about 5 minutes)

1. **Senior management** (`?as=head`): how many applications will miss 10 June, need fast-tracking or are at risk, and
   why each one; where applications wait; who held the ball; Kesarveni's EVC escalated to you today.
2. **Kesarveni** (`?as=ro`, My work): EVC 14 days past the time allowed, *at risk*. The page shows the remaining path against
   10 June and "hold by 3 June". Fix it for 24 May: the institution is told to upload the 30-minute video.
3. **Hemshikhar**: the EVC was fixed on time, for 8 June. Every step was on time, yet the application will miss the date:
   flagged the day it was fixed. Re-fix it for 24 May: back on track.
4. **Neelkamal Tarai** (`?as=inst2`): what the institution owes and by when; reminders at 7, 3 and 0 days. Submit the
   compliance: the application moves to re-scrutiny by itself, marked *needs fast-tracking*.
5. **Narmadatat**: the lease ends 30 June 2031 and the longest course is 4 years, so EoA is blocked from 2027-28 (Cl. 2.1 e).
   As the Regional Officer, verify the extended lease.
6. **Compliance**: Ratnaparvat's deposit (10% penalty now, 20% from 1 June; at the end, sign in as the administrator and
   advance the system date past 31 May to see it climb and the reminders and escalations go out).
   *From published approval letters* shows the 23 real undertakings with links to the letters.
7. **Rules** (click any clause: the handbook page opens highlighted), **Reports**, **Activity log** (intact), **Test results**.

## Change the name

The name lives in one file, `brand.json`. Run

```bash
python scripts/rename.py "NewName"          # optional: --tagline "..."
```
and restart the server. The header, sign-in page, browser tab, letters and API title read it from `brand.json`; the
script also replaces the name in this README. (The GitHub repository name is set on GitHub.)

## Layout

```
brand.json            product name, in one place
backend/app/          api · engine (routes, stages, countdown) · compliance (undertakings, documents, lease, deposit)
                      alerts (daily check: reminders, escalation) · views · letters · settings.yaml (all rules) · demo
scripts/              seed.py · evaluate.py · rename.py · build_real_data.py (rebuilds data/real from the public PDFs)
data/real/            real public data shipped with the repo
frontend/             React + Vite UI
```
