# Samanvay - institution complaint monitoring for AICTE

One view of every complaint and regulatory action on an institution, across the Regulation Bureau, the Public
Grievance Redressal Cell, the Anti-Ragging Cell, the Approval Bureau and the Regional Offices. It finds the
institution behind messy complaint text, spots when bureaus are working on the same institution or the same
matter (in Hindi or English), warns an officer **before** an action clashes with another bureau's, and keeps
every case on its timeline with reminders and escalation.

Everything runs locally and free: no cloud APIs, no paid services. The language model runs on the server's CPU.

## What it does

| Problem-statement need | How it is done here |
|---|---|
| Single view of all cases; which bureau has it | Cases list with search and filters (institution, Permanent ID, case/CPGRAMS no., bureau, region, nature, status, dates); case page with handling bureau, officer, last / next action, expected disposal |
| Identify the institution even when written differently | **Institution resolver**: name words (spelling-tolerant), consonant outline (transliteration-tolerant), acronym ("KIT Indore"), former name, place, quoted Permanent ID; Hindi names transliterated. Links automatically only when one institution is clearly ahead, otherwise an officer chooses. Each match says why |
| Overlap between RB, PGRC and others | Four kinds of alert per institution: **conflicting actions** (rules in `settings.yaml`, e.g. approval moving ahead while a show-cause is pending), **same matter in two places** (language-model text similarity, across Hindi and English, plus same complainant), **many complaints, one issue** (pattern), **parallel cases** (for information). Each with evidence and a suggested lead bureau; bureaus acknowledge and close |
| Avoid duplicate / conflicting action | **Before you act**: recording an action that clashes with another bureau's is stopped until the officer coordinates or records a reason (kept in the case and the log). New complaints are checked against existing ones while being typed |
| Status and movement of a case | Full history with who, when, remarks; transfers move the case with its history; per-institution **swimlane timeline** of every bureau's cases |
| Pending, overdue, escalated | Timeline per nature of complaint (21 days for grievances, DARPG OM of 23.08.2024; others configurable). Escalation ladder: due soon → overdue (section head) → bureau head → senior management. In-app alerts per bureau and level |
| Reports | Bureau-, region-, nature-, institution-wise; monthly received vs disposed; ageing; disposal rate; overlaps raised / closed. CSV download and print |
| Integration | REST API; **register import** (CSV from a bureau's spreadsheet) with matching and duplicate check before saving |
| Safeguards | Role-based access on every route; complaint text and complainant visible only to the handling bureau (and bureaus sharing an alert); contact numbers stored only as salted fingerprints; every view, action and setting change in a **hash-chained activity log**; alerts are advisory, officers act |

## The AI parts, and what they are

* **Multilingual sentence embeddings**: `paraphrase-multilingual-MiniLM-L12-v2` (50+ languages), quantised ONNX run
  by fastembed on CPU. Used for (1) nature of complaint, zero-shot against plain descriptions in `settings.yaml`
  and (2) same-matter similarity between complaints, including Hindi ↔ English. Nothing is trained on the test data.
* Everything else is rules and string matching, and says so on screen.
* **Test results** page (`scripts/evaluate.py`, inputs written separately from the demo data): institution
  matching 96% automatic and correct, 0% linked wrongly; nature of complaint 73% first choice, 92% in top 3;
  same matter precision 100%, recall 75%, all Hindi–English pairs found.

## Real vs simulated

* **Real:** AICTE regional office structure, DARPG 21-day grievance timeline, the language model.
* **Simulated (labelled on every page):** all institutions, people, complaints and actions. No real institution or
  person is named.

## Run

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Windows; .venv/bin on Linux/macOS
python scripts/seed.py         # test data (first run downloads the language model, about 240 MB on disk)
python scripts/evaluate.py     # Test results page
cd frontend && npm install && npm run build && cd ..
start.bat                      # or: cd backend && ../.venv/Scripts/python -m uvicorn app.api:app --port 8000
```
Open http://127.0.0.1:8000. `reset-demo.bat` reloads fresh test data (dates are relative to today) and starts the site.

Quick sign-in links: `/?as=pgrc`, `/?as=rb`, `/?as=ab`, `/?as=arc`, `/?as=ro`, `/?as=head` (senior management), `/?as=admin`.

## Demo script (about 3 minutes)

1. **Overview** as senior management (`?as=head`): counts, workload by bureau, ageing, **Needs coordination**.
2. **Kesarveni Institute of Technology** (institution page): five students complain of fee refunds at PGRC
   (pattern), RB has issued a show-cause, and the Approval Bureau is processing an intake increase. The swimlane shows all three at once.
3. Sign in as the **Approval Bureau** (`?as=ab`), open its Kesarveni case, record *Approval recommended*:
   **Before you act** stops it and shows RB's show-cause.
4. **Neelkamal Tarai**: the same student complained in Hindi to PGRC and in English to RB. The language model
   links them. As RB, *Reply sought from institution* is stopped: PGRC already asked.
5. **Register complaint** → *Hindi complaint, already filed elsewhere*: the institution, nature and the existing
   case appear while typing. *Ragging sent to the wrong cell* suggests the Anti-Ragging Cell.
6. **Coordination** → acknowledge, set lead, close with a note. **Reports**, **Alerts**, **Activity log** (intact).

## Layout

```
backend/app/   api · service (case operations) · workflow (actions, timelines) · overlap (alerts, before-you-act)
               resolve + textnorm (institution matching) · ai (language model) · settings.yaml · audit · demo (test data)
scripts/       seed.py (test data) · evaluate.py (test results)
frontend/      React + Vite UI
```
