"""Simulated test data: invented institutions, officers and complaints.

No real institution or person is named. Complaint texts are written the way complaints arrive:
English or Hindi, institution names abbreviated, misspelt, given by acronym or by a former name.
"""
from __future__ import annotations

import random
import re

from indic_transliteration import sanscript

# stem (as written in English), ITRANS spelling for the Hindi name, type, city, state, region
INSTITUTIONS = [
    ("Kesarveni", "kesaraveNI", "IT", "Indore", "Madhya Pradesh", "Central"),
    ("Shaktikund", "shaktikuNDa", "CE", "Bhopal", "Madhya Pradesh", "Central"),
    ("Vindhyagiri", "vindhyagiri", "PH", "Jabalpur", "Madhya Pradesh", "Central"),
    ("Narmadatat", "narmadAtaTa", "IT", "Jabalpur", "Madhya Pradesh", "Central"),
    ("Hemshikhar", "hemashikhara", "IM", "Gwalior", "Madhya Pradesh", "Central"),
    ("Indravati", "indrAvatI", "CE", "Raipur", "Chhattisgarh", "Central"),
    ("Mahanadi Prabha", "mahAnadI prabhA", "PO", "Bilaspur", "Chhattisgarh", "Central"),
    ("Neelkamal Tarai", "nIlakamala tarAI", "CE", "Lucknow", "Uttar Pradesh", "Northern"),
    ("Gangotri Vihar", "gaNgotrI vihAra", "IT", "Kanpur", "Uttar Pradesh", "Northern"),
    ("Kashidhara", "kAshIdhArA", "CE", "Varanasi", "Uttar Pradesh", "Northern"),
    ("Saryuprabha", "sarayUprabhA", "IM", "Lucknow", "Uttar Pradesh", "Northern"),
    ("Hindonvan", "hiNDanavana", "IT", "Ghaziabad", "Uttar Pradesh", "Northern"),
    ("Devdaru", "devadAru", "PH", "Dehradun", "Uttarakhand", "Northern"),
    ("Panchnad", "pa~nchanada", "CE", "Mohali", "Punjab", "North-Western"),
    ("Sutlejdhara", "satalajadhArA", "IT", "Ludhiana", "Punjab", "North-Western"),
    ("Kurukshetra Vatika", "kurukShetra vATikA", "CE", "Karnal", "Haryana", "North-Western"),
    ("Aravalli Shikhar", "arAvalI shikhara", "IM", "Gurugram", "Haryana", "North-Western"),
    ("Yamunatat", "yamunAtaTa", "IT", "Delhi", "Delhi", "North-Western"),
    ("Brahmaputra Ghati", "brahmaputra ghATI", "CE", "Guwahati", "Assam", "North-Eastern"),
    ("Kamakhya Deep", "kAmAkhyA dIpa", "PO", "Guwahati", "Assam", "North-Eastern"),
    ("Hooghly Tarang", "hugalI taraNga", "CE", "Kolkata", "West Bengal", "Eastern"),
    ("Damodar Ghat", "dAmodara ghATa", "IT", "Durgapur", "West Bengal", "Eastern"),
    ("Mahendragiri", "mahendragiri", "CE", "Bhubaneswar", "Odisha", "Eastern"),
    ("Subarnadhara", "suvarNadhArA", "PH", "Ranchi", "Jharkhand", "Eastern"),
    ("Tejasvarna", "tejasvarNa", "CE", "Hyderabad", "Telangana", "South-Central"),
    ("Godavari Teer", "godAvarI tIra", "IT", "Warangal", "Telangana", "South-Central"),
    ("Krishnaveni Sagar", "kRRiShNaveNI sAgara", "CE", "Vijayawada", "Andhra Pradesh", "South-Central"),
    ("Charminar Vidya", "chAramInAra vidyA", "IM", "Hyderabad", "Telangana", "South-Central"),
    ("Sri Vanadurga", "shrI vanadurgA", "IT", "Hosur", "Tamil Nadu", "Southern"),
    ("Sri Vanadurga", "shrI vanadurgA", "CE", "Hosur", "Tamil Nadu", "Southern"),
    ("Kaveriprabha", "kAverIprabhA", "CE", "Coimbatore", "Tamil Nadu", "Southern"),
    ("Vaigaivani", "vaigaivANI", "IT", "Madurai", "Tamil Nadu", "Southern"),
    ("Marinatheeram", "marInAtIram", "PO", "Chennai", "Tamil Nadu", "Southern"),
    ("Tarangvani", "taraNgavANI", "IT", "Bengaluru", "Karnataka", "South-Western"),
    ("Jalataranga", "jalatara~Nga", "CE", "Mysuru", "Karnataka", "South-Western"),
    ("Ratnaparvat", "ratnaparvata", "IM", "Pune", "Maharashtra", "Western"),
    ("Sahyagiri Kunj", "sahyagiri ku~nja", "CE", "Pune", "Maharashtra", "Western"),
    ("Vidarbha Jyoti", "vidarbha jyoti", "IT", "Nagpur", "Maharashtra", "Western"),
    ("Konkan Ratna", "koMkaNa ratna", "PH", "Mumbai", "Maharashtra", "Western"),
    ("Sabarmati Tat", "sAbaramatI taTa", "CE", "Ahmedabad", "Gujarat", "Western"),
    ("Kanakdhara", "kanakadhArA", "IT", "Belagavi", "Karnataka", "South-Western"),
    ("Periyar Vanam", "periyAra vanam", "CE", "Kochi", "Kerala", "South-Western"),
]
TYPES = {
    "IT": ("Institute of Technology", "Engineering", "प्रौद्योगिकी संस्थान"),
    "CE": ("College of Engineering", "Engineering", "इंजीनियरिंग कॉलेज"),
    "IM": ("Institute of Management", "Management", "प्रबंधन संस्थान"),
    "PH": ("College of Pharmacy", "Pharmacy", "फार्मेसी कॉलेज"),
    "PO": ("Polytechnic", "Polytechnic", "पॉलिटेक्निक"),
}
HINDI_STATES = {"Madhya Pradesh", "Chhattisgarh", "Uttar Pradesh", "Uttarakhand", "Haryana", "Delhi", "Jharkhand"}
CITY_HI = {"Indore": "इंदौर", "Bhopal": "भोपाल", "Jabalpur": "जबलपुर", "Gwalior": "ग्वालियर", "Raipur": "रायपुर",
           "Bilaspur": "बिलासपुर", "Lucknow": "लखनऊ", "Kanpur": "कानपुर", "Varanasi": "वाराणसी", "Ghaziabad": "गाज़ियाबाद",
           "Dehradun": "देहरादून", "Ranchi": "रांची"}
DISTRICT = {"Hosur": "Krishnagiri", "Mohali": "SAS Nagar", "Gurugram": "Gurugram"}
FORMER = {"Kesarveni": "Kesarveni Engineering College", "Gangotri Vihar": "Gangotri Vihar College of Technology",
          "Ratnaparvat": "Ratnaparvat Business School", "Tarangvani": "Tarangvani Engineering College"}
SOCIETY = ["Shiksha Prasar Samiti", "Vidya Vikas Trust", "Gyan Jyoti Educational Society", "Lok Kalyan Shikshan Sanstha",
           "Sarvodaya Education Trust", "Pragati Shiksha Mandal"]

OFFICERS = {
    "PGRC": [("PGRC-1", "K. Verma", "officer"), ("PGRC-2", "R. Bhatt", "officer"), ("PGRC-3", "L. Fernandes", "officer"),
             ("PGRC-4", "T. Hussain", "officer"), ("PGRC-SH", "M. Chauhan", "section_head"), ("PGRC-H", "Dr. P. Menon", "bureau_head")],
    "RB": [("RB-1", "S. Rao", "officer"), ("RB-2", "A. Siddiqui", "officer"), ("RB-3", "D. Kulkarni", "officer"),
           ("RB-SH", "V. Saxena", "section_head"), ("RB-H", "Dr. N. Pillai", "bureau_head")],
    "ARC": [("ARC-1", "N. Gupta", "officer"), ("ARC-2", "J. Thomas", "officer"), ("ARC-H", "Dr. R. Banerjee", "bureau_head")],
    "AB": [("AB-1", "M. Das", "officer"), ("AB-2", "H. Joshi", "officer"), ("AB-3", "G. Reddy", "officer"), ("AB-H", "Dr. S. Mishra", "bureau_head")],
    "RO": [("RO-C", "B. Tiwari", "officer", "Central"), ("RO-N", "C. Srivastava", "officer", "Northern"),
           ("RO-NW", "I. Grewal", "officer", "North-Western"), ("RO-NE", "U. Baruah", "officer", "North-Eastern"),
           ("RO-E", "E. Ghosh", "officer", "Eastern"), ("RO-SC", "Y. Naidu", "officer", "South-Central"),
           ("RO-S", "F. Raman", "officer", "Southern"), ("RO-SW", "P. Nair", "officer", "South-Western"),
           ("RO-W", "O. Deshmukh", "officer", "Western")],
}

FIRST = ["Aarav", "Ananya", "Rohit", "Priya", "Vikram", "Sneha", "Arjun", "Kavya", "Rahul", "Pooja", "Karan", "Neha", "Aditya",
         "Divya", "Sanjay", "Meera", "Imran", "Fatima", "Joseph", "Lakshmi", "Harpreet", "Gurpreet", "Sourav", "Riya", "Manoj",
         "Shweta", "Ajay", "Nisha", "Deepak", "Swati", "Mohit", "Anjali", "Suresh", "Kiran", "Ramesh", "Sunita", "Vivek", "Asha"]
LAST = ["Sharma", "Verma", "Yadav", "Patel", "Reddy", "Nair", "Iyer", "Khan", "Singh", "Das", "Ghosh", "Mehta", "Joshi",
        "Kumar", "Mishra", "Pandey", "Tiwari", "Choudhary", "Rao", "Pillai", "Gill", "Bose", "Shetty", "Kulkarni", "Jain"]
COURSES = ["B.Tech CSE", "B.Tech Mechanical", "B.Tech Civil", "B.Tech ECE", "MBA", "B.Pharm", "Diploma in Electrical",
           "M.Tech", "B.Tech IT", "PGDM"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

SUBJECT = {
    "fee_refund": ["Fee refund not given", "Refund of fees after cancellation", "Non-refund of admission fee"],
    "certificates_withheld": ["Original certificates not returned", "College keeping original documents", "Return of original marksheets"],
    "excess_fee": ["Excess fee charged", "Capitation fee demanded", "Extra charges without receipt"],
    "ragging": ["Ragging in hostel", "Ragging complaint", "Harassment of first-year students by seniors"],
    "faculty_issues": ["Salary not paid to faculty", "Faculty shown only on paper", "Non-payment of salary"],
    "infrastructure": ["No labs and library", "Facilities not provided", "Lack of infrastructure"],
    "unapproved_admission": ["Admission beyond approved intake", "Course not approved by AICTE", "Excess admission"],
    "scholarship": ["Fee demanded from TFW student", "Scholarship not adjusted", "Tuition fee waiver denied"],
    "exam_result": ["Result not declared", "Exam form not forwarded", "Degree certificate delayed"],
    "harassment": ["Harassment by staff", "Threatened by management", "Misbehaviour by faculty"],
}
SUBJECT_HI = {"fee_refund": "फीस वापसी नहीं", "certificates_withheld": "मूल प्रमाणपत्र वापस नहीं", "excess_fee": "अधिक फीस वसूली",
              "ragging": "रैगिंग की शिकायत", "faculty_issues": "वेतन नहीं मिला", "infrastructure": "सुविधाओं का अभाव",
              "scholarship": "छात्रवृत्ति का लाभ नहीं", "exam_result": "परिणाम में देरी", "harassment": "उत्पीड़न"}

TEXT = {
    "fee_refund": [
        "I took admission in {course} at {inst} in {month} {year} and cancelled it on {date}, before the last date. The college has still not refunded my fee of Rs {amount} even after several visits. Kindly direct the college to refund.",
        "Withdrew admission from {inst} within the cut-off date. Refund of Rs. {amount} including caution deposit is pending for {months} months. Management keeps asking me to come again.",
        "My son left the {course} course at {inst} after the first week. They are keeping the full year fee and not returning Rs {amount}. Please help us.",
        "Request for refund of fees. I cancelled my seat at {inst} on {date}. As per AICTE rules the fee should be returned but the institute has not paid anything till now.",
    ],
    "certificates_withheld": [
        "{inst} is not returning my original 10th, 12th and transfer certificates. I want to join another college but they are asking Rs {amount} to release the documents.",
        "After leaving {inst}, my original marksheets are still kept by the college office. They say I must first pay the fees of the remaining years.",
        "My daughter submitted her original certificates at the time of admission to {inst}. She has now left the college and the office refuses to give them back.",
    ],
    "excess_fee": [
        "{inst} is charging Rs {amount} as development fee over and above the fee fixed by the Fee Regulatory Committee. No receipt is given for this amount.",
        "Management of {inst} demanded a donation of Rs {amount} for a seat in {course}. This is capitation fee and against AICTE norms.",
        "We parents of {course} students of {inst} complain that the college collected extra fees of Rs {amount} per student for bus, uniform and training, all made compulsory.",
    ],
    "ragging": [
        "My son, a first year student of {course} at {inst}, was ragged by senior students in the hostel on {date}. He was beaten and forced to do things. The college has taken no action.",
        "Freshers in the {inst} hostel are ragged every night by seniors. The anti-ragging squad does nothing. Please take urgent action.",
    ],
    "faculty_issues": [
        "We faculty members of {inst} have not received salary for the last {months} months. The salary is also not as per the AICTE pay scale.",
        "{inst} shows many faculty members on paper for AICTE approval but they never come to college. Our classes are taken by one or two teachers.",
    ],
    "infrastructure": [
        "There are no working labs in {inst}. Practicals for {course} are not conducted and the library has very few books.",
        "{inst} promised hostel, transport and computer labs at admission but none of these is available. The building is still under construction.",
    ],
    "unapproved_admission": [
        "{inst} has admitted more students in {course} than approved. Our batch has {n} students but the approved intake is {intake}.",
        "I was admitted to {course} at {inst} and now I learn that this course is not approved by AICTE. My future is in danger.",
    ],
    "scholarship": [
        "I am a tuition fee waiver student at {inst}, but the college is forcing me to pay a tuition fee of Rs {amount}.",
        "My post-matric scholarship of Rs {amount} was credited to the college, but {inst} has not adjusted it and is demanding the full fee.",
    ],
    "exam_result": [
        "The result of the semester exams held in {month} {year} at {inst} is still not declared. Degree certificates are also delayed.",
        "{inst} did not send my exam form to the university and I could not appear in the exam.",
    ],
    "harassment": [
        "A staff member of {inst} misbehaves with girl students and threatens to fail them. Complaints to the principal were ignored.",
        "I was suspended by {inst} without any inquiry after I complained about fees. They are threatening me.",
    ],
}
TEXT_HI = {
    "fee_refund": [
        "मैंने {inst} में {course} में प्रवेश लिया था और {date} को प्रवेश रद्द कर दिया। कॉलेज ने अभी तक मेरी {amount} रुपये फीस वापस नहीं की है। कृपया सहायता करें।",
        "{inst} द्वारा प्रवेश वापसी के बाद भी फीस वापस नहीं की जा रही है। {months} महीने हो गए, बार बार चक्कर लगवा रहे हैं।",
    ],
    "certificates_withheld": ["{inst} मेरे मूल प्रमाणपत्र (10वीं, 12वीं) वापस नहीं कर रहा है और {amount} रुपये की मांग कर रहा है।"],
    "excess_fee": ["{inst} में शुल्क नियामक समिति द्वारा तय फीस से अधिक {amount} रुपये वसूले जा रहे हैं और रसीद नहीं दी जाती।"],
    "ragging": ["{inst} के छात्रावास में {date} की रात सीनियर छात्रों ने मेरे बेटे के साथ रैगिंग और मारपीट की। कॉलेज ने कोई कार्रवाई नहीं की।"],
    "faculty_issues": ["{inst} में शिक्षकों को {months} महीने से वेतन नहीं मिला है।"],
    "infrastructure": ["{inst} में प्रयोगशाला और पुस्तकालय की सुविधा नहीं है, प्रैक्टिकल नहीं होते।"],
    "scholarship": ["{inst} ने छात्रवृत्ति मिलने के बाद भी {amount} रुपये फीस की मांग की है।"],
    "exam_result": ["{inst} में {month} {year} की परीक्षा का परिणाम अब तक घोषित नहीं हुआ।"],
}


def institutions(rng: random.Random) -> list[dict]:
    out, used = [], set()
    for i, (stem, itrans, t, city, state, region) in enumerate(INSTITUTIONS):
        suffix, itype, hi_type = TYPES[t]
        name = f"{stem} {suffix}"
        while True:
            pid = f"1-{rng.randint(10**8, 10**9 - 1)}"
            if pid not in used:
                used.add(pid)
                break
        aliases = [FORMER[stem]] if stem in FORMER and t in ("IT", "IM") else []
        hi = sanscript.transliterate(itrans, sanscript.ITRANS, sanscript.DEVANAGARI) + " " + hi_type
        out.append({"permanent_id": pid, "name": name, "aliases": aliases, "city": city, "district": DISTRICT.get(city, city),
                    "state": state, "region": region, "inst_type": itype, "society": rng.choice(SOCIETY),
                    "est_year": rng.randint(1995, 2015), "_hi": hi, "_stem": stem, "_t": t})
    return out


def misspell(word: str, rng: random.Random) -> str:
    if len(word) < 5:
        return word
    i = rng.randint(1, len(word) - 2)
    op = rng.choice(["drop", "swap", "vowel", "double"])
    if op == "drop":
        return word[:i] + word[i + 1:]
    if op == "swap":
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]
    if op == "vowel":
        vs = [j for j, ch in enumerate(word) if ch in "aeiou" and j > 0]
        if vs:
            j = rng.choice(vs)
            return word[:j] + rng.choice([v for v in "aeiou" if v != word[j]]) + word[j + 1:]
    return word[:i] + word[i] + word[i:]


def mention(inst: dict, style: str, rng: random.Random) -> str:
    stem, t, city = inst["_stem"], inst["_t"], inst["city"]
    short = {"IT": "Inst. of Tech.", "CE": "engg college", "IM": "management institute", "PH": "pharmacy college", "PO": "polytechnic"}[t]
    if style == "full":
        return inst["name"]
    if style == "city":
        return f"{inst['name']}, {city}"
    if style == "abbrev":
        return f"{stem} {short} {city}"
    if style == "acronym":
        acr = "".join(p[0] for p in re.findall(r"[A-Za-z]+", inst["name"]) if p.lower() not in {"of", "and"}).upper()
        return f"{acr} {city}"
    if style == "misspelt":
        return " ".join(misspell(w, rng) if len(w) > 4 else w for w in stem.split()) + f" {short.split()[0] if t != 'PO' else 'polytechnic'} {city}".lower()
    if style == "lower":
        return f"{stem.lower()} college {city.lower()}"
    if style == "hindi":
        return f"{inst['_hi']}, {CITY_HI.get(city, city)}"
    if style == "former":
        return inst["aliases"][0] if inst["aliases"] else inst["name"]
    return inst["name"]


def styles_for(inst: dict, lang: str) -> list[str]:
    if lang == "hi":
        return ["hindi"]
    s = ["full", "city", "city", "abbrev", "acronym", "misspelt", "lower"]
    if inst["aliases"]:
        s.append("former")
    return s


def person(rng: random.Random) -> tuple[str, str]:
    name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
    if rng.random() < 0.6:
        contact = f"9{rng.randint(100000000, 999999999)}"
    else:
        contact = f"{name.split()[0].lower()}.{rng.randint(10, 99)}@example.in"
    return name, contact


def complaint_text(cat: str, inst_text: str, lang: str, rng: random.Random, when) -> tuple[str, str]:
    pool = TEXT_HI.get(cat) if lang == "hi" else TEXT[cat]
    tmpl = rng.choice(pool)
    slots = {"inst": inst_text, "course": rng.choice(COURSES), "amount": f"{rng.choice([18, 25, 32, 45, 60, 75, 88, 1.2, 1.4])}"
             .replace("1.2", "1,20").replace("1.4", "1,40") + ",000", "date": when.strftime("%d.%m.%Y"),
             "month": MONTHS[when.month - 1], "year": when.year, "months": rng.randint(2, 7), "n": rng.choice([78, 84, 96, 132]),
             "intake": rng.choice([60, 66, 120])}
    subject = SUBJECT_HI[cat] if lang == "hi" and cat in SUBJECT_HI else rng.choice(SUBJECT[cat])
    return subject, tmpl.format(**slots)
