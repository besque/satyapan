"""Measure the three automatic judgements on test inputs, and write data/eval_report.json.

1. Institution matching: every institution written in the ways complainants write it (full name, with
   city, abbreviated, acronym, misspelt, lower-case, Hindi, former name).
2. Nature of complaint: complaints written for this test only (not the demo templates, not the
   category descriptions in settings.yaml), in English and Hindi.
3. Same matter: pairs of complaints about the same incident (re-worded, or in the other language)
   against pairs about different matters at the same institution.
All inputs are synthetic. Run after scripts/seed.py:  python scripts/evaluate.py
"""
from __future__ import annotations

import json
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import ai, db, demo, overlap, resolve, settings  # noqa: E402
from app.config import DATA  # noqa: E402

CATEGORY_TESTS = [
    ("fee_refund", "Admission surrendered in the first week itself, still the institute has not paid back the 72,000 I deposited."),
    ("fee_refund", "Kindly help me get my money back, I left the course in September and the college says no refund."),
    ("fee_refund", "सीट छोड़ने के तीन महीने बाद भी कॉलेज ने जमा किए पैसे नहीं लौटाए।"),
    ("certificates_withheld", "The principal says my mark sheets will be given only after I clear dues for the full course."),
    ("certificates_withheld", "I need my school leaving certificate and 12th marks card back from the college for a new job."),
    ("certificates_withheld", "कॉलेज ने मेरी 12वीं की मार्कशीट रोक रखी है, नौकरी के लिए चाहिए।"),
    ("excess_fee", "Every student was told to pay 40,000 'lab development charges' on top of the approved fee."),
    ("excess_fee", "Seat was offered only if we paid 3 lakh in cash to the trust, apart from fees."),
    ("excess_fee", "फीस के अलावा हर छात्र से 30 हजार नकद लिए गए, कोई रसीद नहीं।"),
    ("ragging", "Second-years shaved the heads of freshers and made them dance at midnight in the hostel."),
    ("ragging", "My brother is too scared to go back to the hostel because seniors hit him last week."),
    ("ragging", "हॉस्टल में सीनियरों ने नए छात्रों को रात भर परेशान किया और पीटा।"),
    ("faculty_issues", "Teachers have been working without pay since June and many have left."),
    ("faculty_issues", "Names of professors on the college website are of people who left years ago; no one teaches us."),
    ("faculty_issues", "प्राध्यापकों का वेतन छह महीने से रुका हुआ है।"),
    ("infrastructure", "There is no computer centre, and the workshop machines have not worked for two years."),
    ("infrastructure", "The college runs from two floors of a shopping complex; there is no playground or hostel."),
    ("infrastructure", "लैब में कोई उपकरण नहीं है, लाइब्रेरी में किताबें नहीं।"),
    ("unapproved_admission", "Sixty extra students were enrolled in mechanical beyond the sanctioned seats."),
    ("unapproved_admission", "The diploma course we joined does not appear on the AICTE approved list."),
    ("scholarship", "As an SC student my fee is paid by the state scheme, but the college still asks me to deposit the tuition."),
    ("scholarship", "I got admission under the fee waiver quota but now they want full tuition."),
    ("exam_result", "Our sixth semester marks have not come even after five months."),
    ("exam_result", "Hall tickets were not issued by the college, so twenty of us missed the exam."),
    ("harassment", "The head of department keeps making remarks about my caste and threatens to fail me."),
    ("harassment", "I was thrown out of the hostel after I spoke to a newspaper about the fees."),
]

SAME_PAIRS = [  # (category, text A, text B): same incident, different wording or language
    ("fee_refund", "I cancelled my MBA seat on 3 July; the refund of Rs 1,10,000 has not come.",
     "मैंने 3 जुलाई को एमबीए की सीट रद्द की थी, 1,10,000 रुपये की वापसी अब तक नहीं हुई।"),
    ("certificates_withheld", "The college has kept my 10th and 12th originals and asks Rs 50,000 to return them.",
     "कॉलेज मेरे 10वीं और 12वीं के मूल प्रमाणपत्र लौटाने के लिए 50,000 रुपये मांग रहा है।"),
    ("ragging", "Seniors beat my son in hostel block C on Saturday night.",
     "My son was assaulted by senior students in hostel C on the night of Saturday; he is in shock."),
    ("excess_fee", "Rs 25,000 bus fee is compulsory even for students who live next to the college.",
     "College forces every student, even day scholars living nearby, to pay 25,000 as transport fee."),
    ("faculty_issues", "Salary of all teaching staff is pending from April.",
     "अप्रैल से सभी शिक्षकों का वेतन बकाया है।"),
    ("infrastructure", "No chemistry lab; practicals are just written in the record book.",
     "There is no chemistry laboratory at all and we only copy practicals into our records."),
    ("scholarship", "My post-matric scholarship came to the college account but they still demand fees from me.",
     "छात्रवृत्ति कॉलेज के खाते में आ गई फिर भी कॉलेज मुझसे फीस मांग रहा है।"),
    ("exam_result", "Semester results of Electrical branch from May are still not declared.",
     "Results of the May semester exam for the electrical students have not been announced yet."),
]

DIFFERENT_PAIRS = [  # same institution, different matters
    ("fee_refund", "I cancelled my MBA seat on 3 July; the refund of Rs 1,10,000 has not come.",
     "ragging", "Seniors beat my son in hostel block C on Saturday night."),
    ("certificates_withheld", "The college has kept my 10th and 12th originals and asks Rs 50,000 to return them.",
     "infrastructure", "No chemistry lab; practicals are just written in the record book."),
    ("faculty_issues", "Salary of all teaching staff is pending from April.",
     "scholarship", "My post-matric scholarship came to the college account but they still demand fees from me."),
    ("exam_result", "Semester results of Electrical branch from May are still not declared.",
     "excess_fee", "Rs 25,000 bus fee is compulsory even for students who live next to the college."),
    ("harassment", "The hostel warden threatens girls who complain about the food.",
     "fee_refund", "Refund of caution deposit of Rs 10,000 not given after I finished the course."),
    ("ragging", "हॉस्टल में सीनियरों ने मारपीट की।", "certificates_withheld", "कॉलेज मूल अंकतालिका वापस नहीं कर रहा।"),
    ("infrastructure", "No library books for third year.", "faculty_issues", "Three teachers resigned because they were not paid."),
    ("scholarship", "Fee waiver denied though I am in the TFW list.", "exam_result", "Degree certificate not issued two years after passing."),
]


def institution_matching(rng):
    insts = demo.institutions(random.Random(7))   # same institutions as the seeded master
    master = {r["name"]: r["permanent_id"] for r in db.q("SELECT name, permanent_id FROM institutions")}
    per_style = defaultdict(Counter)
    examples = []
    for inst in insts:
        styles = ["full", "city", "abbrev", "acronym", "misspelt", "misspelt", "lower"]
        if inst["state"] in demo.HINDI_STATES:
            styles.append("hindi")
        if inst["aliases"]:
            styles.append("former")
        for st in styles:
            text = demo.mention(inst, st, rng)
            r = resolve.resolve(text, "")
            truth = master[inst["name"]]
            top = r["candidates"][0]["permanent_id"] if r["candidates"] else None
            if r["state"] == "auto":
                outcome = "auto_correct" if r["permanent_id"] == truth else "auto_wrong"
            elif r["state"] == "confirm":
                outcome = "confirm_top_correct" if top == truth else "confirm_top_wrong"
            else:
                outcome = "unmatched"
            per_style[st][outcome] += 1
            if outcome in ("auto_wrong", "confirm_top_wrong", "unmatched") and len(examples) < 12:
                examples.append({"text": text, "truth": inst["name"], "got": r["candidates"][0]["name"] if r["candidates"] else None,
                                 "outcome": outcome, "confidence": r["confidence"]})
    total = Counter()
    for c in per_style.values():
        total.update(c)
    n = sum(total.values())
    return {"n": n, "overall": {k: round(100 * v / n, 1) for k, v in total.items()},
            "by_style": {s: dict(c) for s, c in per_style.items()}, "misses": examples}


def categories():
    rows, top1, top3 = [], 0, 0
    for cat, text in CATEGORY_TESTS:
        r = ai.classify(text)
        ok1, ok3 = r[0]["category"] == cat, cat in [x["category"] for x in r]
        top1 += ok1
        top3 += ok3
        rows.append({"expected": settings.category(cat)["label"], "got": r[0]["label"], "score": r[0]["score"], "ok": ok1,
                     "lang": "hi" if any("ऀ" <= ch <= "ॿ" for ch in text) else "en", "text": text})
    n = len(CATEGORY_TESTS)
    return {"n": n, "top1": round(100 * top1 / n, 1), "top3": round(100 * top3 / n, 1), "rows": rows}


def same_matter():
    thr = settings.get()["matching"]["same_matter"]

    def case(cat, text, i):
        return {"id": f"t{i}", "subject": "", "description": text, "category": cat, "category_ai": ai.classify(text),
                "lang": "hi" if any("ऀ" <= ch <= "ॿ" for ch in text) else "en", "received_on": "2026-09-01",
                "contact_hash": None, "complainant": None}
    rows = []
    for i, (cat, a, b) in enumerate(SAME_PAIRS):
        x, y = case(cat, a, 2 * i), case(cat, b, 2 * i + 1)
        x["category"], y["category"] = x["category_ai"][0]["category"], y["category_ai"][0]["category"]
        v = ai.embed([a, b])
        pm = overlap.same_matter(x, y, v[0], v[1], {})
        rows.append({"truth": "same", "score": pm["score"], "predicted_same": pm["same"], "a": a, "b": b})
    for i, (ca, a, cb, b) in enumerate(DIFFERENT_PAIRS):
        x, y = case(ca, a, 100 + 2 * i), case(cb, b, 101 + 2 * i)
        x["category"], y["category"] = x["category_ai"][0]["category"], y["category_ai"][0]["category"]
        v = ai.embed([a, b])
        pm = overlap.same_matter(x, y, v[0], v[1], {})
        rows.append({"truth": "different", "score": pm["score"], "predicted_same": pm["same"], "a": a, "b": b})
    tp = sum(r["truth"] == "same" and r["predicted_same"] for r in rows)
    fp = sum(r["truth"] == "different" and r["predicted_same"] for r in rows)
    fn = sum(r["truth"] == "same" and not r["predicted_same"] for r in rows)
    cross = [r for r in rows if r["truth"] == "same" and any("ऀ" <= ch <= "ॿ" for ch in r["b"])]
    return {"threshold": thr, "pairs": len(rows), "precision": round(100 * tp / max(1, tp + fp), 1),
            "recall": round(100 * tp / max(1, tp + fn), 1),
            "cross_language_found": f"{sum(r['predicted_same'] for r in cross)} of {len(cross)}", "rows": rows}


def main():
    t = time.time()
    rng = random.Random(99)
    rep = {"model": ai.backend(), "institution_matching": institution_matching(rng), "nature_of_complaint": categories(),
           "same_matter": same_matter(), "seconds": None,
           "note": "All test inputs are synthetic and written for this test. Real complaints will be messier; "
                   "these figures show behaviour, not field accuracy."}
    rep["seconds"] = round(time.time() - t, 1)
    (DATA / "eval_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    im = rep["institution_matching"]
    print("institution matching", im["n"], im["overall"])
    print("nature", rep["nature_of_complaint"]["top1"], rep["nature_of_complaint"]["top3"])
    sm = rep["same_matter"]
    print("same matter P/R", sm["precision"], sm["recall"], "cross-language", sm["cross_language_found"])
    for m in im["misses"]:
        print("  miss", m)
    for r in rep["nature_of_complaint"]["rows"]:
        if not r["ok"]:
            print("  cat", r["expected"], "->", r["got"], r["score"], r["text"][:60])
    for r in sm["rows"]:
        if r["predicted_same"] != (r["truth"] == "same"):
            print("  pair", r["truth"], r["score"], r["a"][:40], "|", r["b"][:40])


if __name__ == "__main__":
    main()
