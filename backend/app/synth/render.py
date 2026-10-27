"""ReportLab templates for the Annexure-2 (2.1) document set. Every page carries a small
"SYNTHETIC TEST DOCUMENT" footer so these files can never pass as real certificates.
"""
from __future__ import annotations

import io
import math
import random
import textwrap
from datetime import date

import qrcode
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

W, H = A4
FOOT = "SYNTHETIC TEST DOCUMENT - not a real certificate."


def _canvas(producer: str, title: str):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, pageCompression=1)
    c.setTitle(title)
    c.setCreator(producer)
    c._doc.info.producer = producer
    return c, buf


def _foot(c):
    c.setFont("Helvetica", 6.5)
    c.setFillColor(colors.HexColor("#8a8a8a"))
    c.drawCentredString(W / 2, 10 * mm, FOOT)
    c.setFillColor(colors.black)


def _letterhead(c, lines: list[str], color="#1f3a5f", emblem=True):
    c.setFillColor(colors.HexColor(color))
    c.rect(0, H - 34 * mm, W, 34 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    if emblem:
        c.circle(22 * mm, H - 17 * mm, 10 * mm, stroke=1, fill=0)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString(22 * mm, H - 18 * mm, "SEAL")
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(W / 2 + 8 * mm, H - 14 * mm, lines[0])
    c.setFont("Helvetica", 9)
    for i, ln in enumerate(lines[1:3]):
        c.drawCentredString(W / 2 + 8 * mm, H - (21 + 5 * i) * mm, ln)
    c.setFillColor(colors.black)


def _title(c, text, y):
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(W / 2, y, text)
    c.setLineWidth(0.6)
    tw = c.stringWidth(text, "Helvetica-Bold", 13)
    c.line(W / 2 - tw / 2, y - 2, W / 2 + tw / 2, y - 2)


def _kv(c, rows: list[tuple[str, str]], x, y, label_w=62 * mm, size=9.5, gap=6.4 * mm, value_w=105 * mm):
    for label, value in rows:
        c.setFont("Helvetica", size)
        c.drawString(x, y, label)
        c.drawString(x + label_w - 4 * mm, y, ":")
        c.setFont("Helvetica-Bold", size)
        lines = textwrap.wrap(str(value), width=int(value_w / (size * 0.52))) or [""]
        for i, ln in enumerate(lines):
            c.drawString(x + label_w, y - i * (size + 2), ln)
        y -= gap + (len(lines) - 1) * (size + 2)
    return y


def _para(c, text, x, y, width=170 * mm, size=9.5, leading=13):
    c.setFont("Helvetica", size)
    for para in text.split("\n"):
        for ln in textwrap.wrap(para, width=int(width / (size * 0.5))):
            c.drawString(x, y, ln)
            y -= leading
        y -= 3
    return y


def _seal(c, x, y, top, mid, color="#2b3f8f", r=15 * mm):
    c.saveState()
    c.setStrokeColor(colors.HexColor(color)); c.setFillColor(colors.HexColor(color))
    c.setLineWidth(1.4); c.circle(x, y, r); c.setLineWidth(0.7); c.circle(x, y, r - 3 * mm)
    c.setFont("Helvetica-Bold", 6.2)
    n = len(top)
    for i, ch in enumerate(top):
        ang = math.radians(150 - 120 * i / max(n - 1, 1))
        c.saveState()
        c.translate(x + (r - 2.1 * mm) * math.cos(ang), y + (r - 2.1 * mm) * math.sin(ang))
        c.rotate(math.degrees(ang) - 90)
        c.drawCentredString(0, 0, ch)
        c.restoreState()
    c.setFont("Helvetica-Bold", 6.5)
    for i, ln in enumerate(textwrap.wrap(mid, 16)[:3]):
        c.drawCentredString(x, y + 2 - i * 8, ln)
    c.restoreState()


def _signature(c, x, y, seed: int, w=38 * mm):
    rnd = random.Random(seed)
    c.saveState()
    c.setStrokeColor(colors.HexColor("#0b2a8a")); c.setLineWidth(0.9)
    p = c.beginPath(); p.moveTo(x, y)
    cx = x
    for _ in range(7):
        nx = cx + w / 7
        p.curveTo(cx + rnd.uniform(0, 8), y + rnd.uniform(-9, 12), nx - rnd.uniform(0, 8), y + rnd.uniform(-12, 9), nx, y + rnd.uniform(-3, 3))
        cx = nx
    c.drawPath(p, stroke=1, fill=0)
    c.restoreState()


def _qr(c, data: str, x, y, size=24 * mm):
    img = qrcode.make(data, box_size=4, border=1)
    b = io.BytesIO(); img.save(b, format="PNG"); b.seek(0)
    c.drawImage(ImageReader(b), x, y, size, size)


def d(dt: date) -> str:
    return dt.strftime("%d/%m/%Y")


# --------------------------------------------------------------------------- documents

def affidavit(a: dict) -> bytes:
    c, buf = _canvas(a.get("producer", "SHCIL e-Stamp Certificate Generator"), "Affidavit 2")
    # e-stamp certificate block
    c.setStrokeColor(colors.HexColor("#6b4e16")); c.setLineWidth(1.2)
    c.rect(14 * mm, H - 128 * mm, W - 28 * mm, 114 * mm)
    c.setFillColor(colors.HexColor("#f6efd9")); c.rect(14.6 * mm, H - 127.4 * mm, W - 29.2 * mm, 112.8 * mm, stroke=0, fill=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 15); c.drawCentredString(W / 2, H - 24 * mm, "INDIA NON JUDICIAL")
    c.setFont("Helvetica", 10); c.drawCentredString(W / 2, H - 30 * mm, f"Government of {a['state']}")
    c.setFont("Helvetica-Bold", 12); c.drawCentredString(W / 2, H - 37 * mm, "e-Stamp")
    _kv(c, [
        ("Certificate No.", a["estamp_no"]),
        ("Certificate Issued Date", a["estamp_date"].strftime("%d-%b-%Y %I:%M %p")),
        ("Account Reference", f"SHCIL (FI)/ {a['state_code']}-SYN/ {a['locality'].upper()}"),
        ("Unique Doc. Reference", a["estamp_udr"]),
        ("Purchased by", a["first_party"]),
        ("Description of Document", "Article 4 Affidavit"),
        ("Consideration Price (Rs.)", "0 (Zero)"),
        ("First Party", a["first_party"]),
        ("Second Party", "All India Council for Technical Education"),
        ("Stamp Duty Paid By", a["first_party"]),
        ("Stamp Duty Amount(Rs.)", f"{a['stamp_value']} ({a['stamp_words']} only)"),
    ], 22 * mm, H - 47 * mm, label_w=58 * mm, size=8.6, gap=5.6 * mm, value_w=95 * mm)
    _qr(c, f"https://synthetic-estamp.example/verify?cert={a['estamp_no']}", W - 44 * mm, H - 122 * mm, 24 * mm)
    c.setFont("Helvetica-Bold", 12.5); c.drawCentredString(W / 2, H - 140 * mm, "AFFIDAVIT-2")
    c.setFont("Helvetica", 8.5); c.drawCentredString(W / 2, H - 145 * mm, "(For the applications submitted under Chapter I/II/IV except Closure of the Institution)")
    y = _para(c, (
        f"I/we, {a['deponent']}, Chairperson/ Secretary, {a['trust']}, son/ daughter of {a['deponent_parent']}, aged "
        f"{a['deponent_age']}, resident of {a['city']}, do hereby solemnly affirm and declare as under:\n"
        f"1. That I/we have applied for Extension of Approval for the Academic Year {a['academic_year']} for "
        f"{a['institution']} vide application dated {d(a['application_date'])}, Application No. {a['application_no']}.\n"
        "2. That I/ we will abide by all terms and conditions as laid down in the Approval Process Handbook 2024-27.\n"
        "3. That the information given in the application made to AICTE is true and complete. Nothing is false and no "
        "information/ material has been concealed;\n"
        "4. That the Institution is functioning in the location as approved by the Council;\n"
        "5. That I/we have uploaded the Occupancy/Completion Certificate/Building License/Form D issued by the Competent "
        "Authority and the Structural Stability Certificate by the Competent Authority;\n"
        f"6. That the Trust/ Society/ Company runs the following other Institutions in the same Campus; Total Built-Up Area available {a['built_up_area']:.0f} sq.m;\n"
        "7. That I/we have uploaded valid Fire Safety Certificate issued by the Competent Authority;\n"
        "8. That Principal of the Institution is regular and qualified as per AICTE norms;\n"
        "9. That the Faculty norms as well as Faculty : Student ratio is maintained as per Approval Process Handbook and "
        "the Faculty data uploaded is true and complete;"), 18 * mm, H - 154 * mm, width=174 * mm, size=8.6, leading=11.2)
    _foot(c); c.showPage()
    y = _para(c, (
        "10. That the I/we not demanded/ retained the Original Degree Certificates from the Faculty members;\n"
        "11. That the declaration, information and documents submitted/uploaded as per Annexure-1/2 of the Approval "
        f"Process Handbook with regard to Land, Built-up area and other Infrastructure therein for {a['institution']} is "
        "true, complete and nothing is false;\n12. That the Land is contiguous, there is no dispute pertaining to the said Land;\n"
        "13. That if any of the information is found to be false, incomplete, misleading, the Council shall be free to take "
        "any action, including Withdrawal of Approval."), 18 * mm, H - 24 * mm, width=174 * mm, size=8.8, leading=11.6)
    y = _kv(c, [("Name of the Institution", a["institution"]), ("Name of the Trust/ Society/ Company", a["trust"]),
                ("Total Built-up Area", f"{a['built_up_area']:.0f} sq.m")], 18 * mm, y - 6 * mm, label_w=66 * mm, size=9)
    if a.get("deponent_signed", True):
        _signature(c, 128 * mm, y - 6 * mm, seed=hash(a["deponent"]) & 0xffff)
    c.setFont("Helvetica-Bold", 9); c.drawString(128 * mm, y - 13 * mm, "DEPONENT")
    c.setFont("Helvetica", 8.5); c.drawString(128 * mm, y - 18 * mm, f"({a['deponent']}, Chairperson)")
    y = _para(c, ("VERIFICATION\nI/we, the above named deponent(s) do hereby verify that the facts stated in the above affidavit "
                  "are true to my/our knowledge. No part of the same is false and no material facts have been concealed therefrom.\n"
                  f"Verified at {a['city']} on this {d(a['sworn_date'])}."), 18 * mm, y - 30 * mm, size=8.8)
    if a.get("notarised", True):
        _para(c, f"Solemnly affirmed and signed before me by the deponent(s) on {d(a['sworn_date'])} at my office.",
              18 * mm, y - 4 * mm, size=8.8)
        _seal(c, 45 * mm, y - 32 * mm, "NOTARY PUBLIC  " + a["state"].upper(), f"{a['notary']} Regn {a['notary_reg']}", "#7a1f1f")
        _signature(c, 70 * mm, y - 30 * mm, seed=hash(a["notary"]) & 0xffff, w=30 * mm)
        _kv(c, [("Notary Public", a["notary"]), ("Regn. No", a["notary_reg"])], 70 * mm, y - 40 * mm, label_w=30 * mm, size=8.5)
    _foot(c); c.save()
    return buf.getvalue()


def ter_receipt(t: dict) -> bytes:
    c, buf = _canvas(t.get("producer", "JasperReports Library version 6.20.0"), "TER Payment Receipt")
    _letterhead(c, ["AICTE Web-Portal : Payment Receipt", "Technical Education Regulatory (TER) Charges",
                    "SYNTHETIC TEST RECEIPT - not issued by AICTE"], color="#3a2f6b")
    _title(c, "PAYMENT RECEIPT", H - 50 * mm)
    y = _kv(c, [("Permanent ID", t["permanent_id"]), ("Application No", t["application_no"]),
                ("Name of the Institution", t["institution"]), ("Purpose", f"Extension of Approval {t['academic_year']} (Self-Disclosure)"),
                ("Number of Divisions", str(t["divisions"])), ("Transaction ID", t["txn_id"]),
                ("Bank Reference No", t["bank_ref"]), ("Payment Date", t["payment_date"].strftime("%d-%m-%Y %H:%M")),
                ("Payment Mode", "Net Banking"), ("Amount Paid (Rs.)", f"{t['amount']:,.2f}"), ("Payment Status", "SUCCESS")],
            22 * mm, H - 64 * mm, label_w=60 * mm)
    _para(c, "This is a system generated receipt. TER Charges once paid are non-refundable as per Clause 2.3.2 of the "
             "Approval Process Handbook 2024-27.", 22 * mm, y - 8 * mm, size=8.5)
    _qr(c, f"TER|{t['txn_id']}|{t['amount']:.2f}|{t['permanent_id']}", W - 48 * mm, 30 * mm)
    _foot(c); c.save()
    return buf.getvalue()


def occupancy(o: dict) -> bytes:
    c, buf = _canvas(o.get("producer", "iText 5.5.13 (c)2000-2018 iText Group NV"), "Occupancy Certificate")
    _letterhead(c, [o["authority"], "Building Permission & Occupancy Wing", o["authority_addr"]], color="#164e3b")
    _title(c, "OCCUPANCY CERTIFICATE", H - 50 * mm)
    y = _kv(c, [("Certificate No", o["cert_no"]), ("Date of Issue", d(o["issue_date"])), ("Name of the Owner", o["owner"]),
                ("Name of the Building", o["premises"]), ("Address of the Premises", o["address"]),
                ("Survey No", o["survey_no"]), ("Total Built-up Area", f"{o['built_up_area']:.2f} sq.m"),
                ("No. of Floors", o["floors"]), ("Usage / Occupancy", "Educational (Institutional)"),
                ("Building Permit Ref", o["permit_ref"])], 22 * mm, H - 64 * mm, label_w=58 * mm)
    y = _para(c, (f"This is to certify that the building(s) referred above, constructed as per the sanctioned plan vide "
                  f"{o['permit_ref']}, has been inspected and is fit for occupation for the purpose of an educational "
                  "institution, subject to compliance with the conditions of the building bye-laws in force."), 22 * mm, y - 6 * mm)
    _seal(c, 55 * mm, 52 * mm, o["authority"][:30].upper(), "OCCUPANCY WING", "#164e3b")
    _signature(c, 128 * mm, 58 * mm, seed=hash(o["cert_no"]) & 0xffff)
    c.setFont("Helvetica-Bold", 9); c.drawString(128 * mm, 50 * mm, "Competent Authority")
    c.setFont("Helvetica", 8.5); c.drawString(128 * mm, 45 * mm, o["officer"])
    _qr(c, f"https://synthetic-oc.example/verify/{o['cert_no']}", W - 42 * mm, 15 * mm, 22 * mm)
    _foot(c); c.save()
    return buf.getvalue()


def structural(s: dict) -> bytes:
    c, buf = _canvas(s.get("producer", "Microsoft® Word 2019"), "Structural Stability Certificate")
    _letterhead(c, [s["firm"], f"Registered Structural Engineers | Reg. No. {s['engineer_reg']}", s["firm_addr"]], color="#5a3d1c", emblem=False)
    _title(c, "STRUCTURAL STABILITY CERTIFICATE", H - 50 * mm)
    y = _kv(c, [("Name of Institution", s["premises"]), ("Address", s["address"]), ("Year of Construction", str(s["construction_year"])),
                ("Inspected on", d(s["inspected"])), ("Date of Issue", d(s["issue_date"])), ("Valid up to", d(s["valid_until"]))],
            22 * mm, H - 64 * mm, label_w=55 * mm)
    y = _para(c, ("I have inspected the above building(s) and examined the structural members, foundations and load bearing "
                  "elements. Based on the inspection and non-destructive tests, I certify that the building is structurally "
                  "safe and fit for human habitation. This certificate is valid for a period of five years from the date of issue "
                  "(Clause 6.17(h), APH 2024-27)."), 22 * mm, y - 6 * mm)
    _signature(c, 125 * mm, 66 * mm, seed=hash(s["engineer"]) & 0xffff)
    _kv(c, [("Structural Engineer", s["engineer"]), ("Registration No", s["engineer_reg"]),
            ("Qualification", "M.Tech (Structural Engineering)")], 100 * mm, 58 * mm, label_w=36 * mm, size=8.5, value_w=60 * mm)
    _seal(c, 50 * mm, 62 * mm, "REGD. STRUCTURAL ENGINEER", s["engineer_reg"], "#5a3d1c")
    _foot(c); c.save()
    return buf.getvalue()


def fire_noc(f: dict) -> bytes:
    c, buf = _canvas(f.get("producer", "iText 5.5.13 (c)2000-2018 iText Group NV"), "Fire Safety Certificate")
    _letterhead(c, [f["authority"], "Fire Prevention Wing", f["authority_addr"]], color="#8a1c1c")
    _title(c, "FIRE SAFETY CERTIFICATE (NO OBJECTION CERTIFICATE)", H - 50 * mm)
    y = _kv(c, [("NOC No", f["noc_no"]), ("Date of Issue", d(f["issue_date"])), ("Valid up to", d(f["valid_until"])),
                ("Name of the Premises", f["premises"]), ("Address of the Premises", f["address"]),
                ("Type of Occupancy", "Educational - Group B"), ("Height of Building", f"{f['height']} m"),
                ("No. of Floors", f["floors"]), ("Applicant", f["applicant"])], 22 * mm, H - 64 * mm, label_w=55 * mm)
    y = _para(c, ("The premises mentioned above was inspected by the undersigned. The fire prevention and fire safety measures "
                  "provided are found to be satisfactory as per the National Building Code of India Part 4 and the State Fire "
                  "Service Act. This certificate is valid up to the date mentioned above, and renewal shall be applied for "
                  "before expiry."), 22 * mm, y - 6 * mm)
    _seal(c, 55 * mm, 52 * mm, "FIRE & EMERGENCY SERVICES", f["district"].upper(), "#8a1c1c")
    _signature(c, 128 * mm, 58 * mm, seed=hash(f["noc_no"]) & 0xffff)
    c.setFont("Helvetica-Bold", 9); c.drawString(128 * mm, 50 * mm, "District Fire Officer")
    c.setFont("Helvetica", 8.5); c.drawString(128 * mm, 45 * mm, f["officer"])
    _qr(c, f"https://synthetic-fire.example/noc/{f['noc_no']}", W - 42 * mm, 15 * mm, 22 * mm)
    _foot(c); c.save()
    return buf.getvalue()


def location_map(m: dict, tile_img=None) -> bytes:
    c, buf = _canvas(m.get("producer", "Microsoft: Print To PDF"), "Location map")
    _title(c, "SATELLITE / LOCATION MAP OF THE INSTITUTION", H - 22 * mm)
    c.setFont("Helvetica", 9.5); c.drawCentredString(W / 2, H - 29 * mm, m["institution"])
    box = (20 * mm, 70 * mm, W - 40 * mm, 150 * mm)
    if tile_img is not None:
        b = io.BytesIO(); tile_img.save(b, format="PNG"); b.seek(0)
        c.drawImage(ImageReader(b), *box)
    else:
        c.setFillColor(colors.HexColor("#dfe8d8")); c.rect(*box, stroke=1, fill=1)
    c.setFillColor(colors.HexColor("#c0392b"))
    cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
    p = c.beginPath(); p.moveTo(cx, cy); p.lineTo(cx - 4 * mm, cy + 9 * mm); p.lineTo(cx + 4 * mm, cy + 9 * mm); p.close()
    c.drawPath(p, fill=1, stroke=0); c.circle(cx, cy + 9 * mm, 4 * mm, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 10)
    lat, lon = m["lat"], m["lon"]
    c.drawString(20 * mm, 60 * mm, f"Main Building Entrance: {abs(lat):.6f} {'N' if lat >= 0 else 'S'}, {abs(lon):.6f} {'E' if lon >= 0 else 'W'}")
    _kv(c, [("Latitude", f"{lat:.6f}"), ("Longitude", f"{lon:.6f}"), ("Address", m["address"])], 20 * mm, 50 * mm, label_w=30 * mm, size=9)
    c.setFont("Helvetica", 7); c.drawString(20 * mm, 67 * mm, "Map data (c) OpenStreetMap contributors" if tile_img is not None else "Map tile unavailable offline")
    _foot(c); c.save()
    return buf.getvalue()


def audited(a: dict) -> bytes:
    c, buf = _canvas(a.get("producer", "Microsoft® Excel® 2019"), "Audited Statement of Accounts")
    _letterhead(c, [a["ca_firm"], f"Chartered Accountants | FRN: {a['frn']}", a["ca_addr"]], color="#2d4a22", emblem=False)
    _title(c, f"BALANCE SHEET AS AT 31st MARCH {a['fy_end']}", H - 48 * mm)
    c.setFont("Helvetica", 9.5); c.drawCentredString(W / 2, H - 55 * mm, f"Name of the Trust : {a['trust']}")
    rows = [("CORPUS FUND", a["corpus"]), ("GENERAL RESERVE", a["reserve"]), ("SECURED LOANS", a["loans"]),
            ("CURRENT LIABILITIES", a["liab"])]
    assets = [("FIXED ASSETS (NET BLOCK)", a["fixed"]), ("INVESTMENTS / FDR", a["fdr"]), ("CURRENT ASSETS", a["curr"]),
              ("CASH & BANK BALANCES", a["cash"])]
    y = H - 68 * mm
    c.setFont("Helvetica-Bold", 9); c.drawString(22 * mm, y, "LIABILITIES"); c.drawRightString(100 * mm, y, "Amount (Rs.)")
    c.drawString(110 * mm, y, "ASSETS"); c.drawRightString(188 * mm, y, "Amount (Rs.)")
    c.setFont("Helvetica", 9)
    for i in range(4):
        yy = y - (i + 1) * 7 * mm
        c.drawString(22 * mm, yy, rows[i][0]); c.drawRightString(100 * mm, yy, f"{rows[i][1]:,.0f}")
        c.drawString(110 * mm, yy, assets[i][0]); c.drawRightString(188 * mm, yy, f"{assets[i][1]:,.0f}")
    tot = sum(r[1] for r in rows)
    c.setFont("Helvetica-Bold", 9); yy = y - 5 * 7 * mm
    c.drawString(22 * mm, yy, "TOTAL"); c.drawRightString(100 * mm, yy, f"{tot:,.0f}")
    c.drawString(110 * mm, yy, "TOTAL"); c.drawRightString(188 * mm, yy, f"{sum(r[1] for r in assets):,.0f}")
    _title(c, f"INCOME AND EXPENDITURE ACCOUNT FOR THE YEAR ENDED 31st MARCH {a['fy_end']}", yy - 16 * mm)
    y2 = _kv(c, [("Fee Receipts", f"{a['income']:,.0f}"), ("Total Expenditure", f"{a['expenditure']:,.0f}"),
                 ("Excess of Income over Expenditure", f"{a['income'] - a['expenditure']:,.0f}")], 22 * mm, yy - 28 * mm, label_w=70 * mm)
    _para(c, "In our opinion and to the best of our information and according to the explanations given to us, the said accounts "
             "give a true and fair view of the state of affairs of the Trust.", 22 * mm, y2 - 4 * mm, size=8.8)
    _kv(c, [("For", a["ca_firm"]), ("FRN", a["frn"]), ("Partner", a["partner"]), ("M.No", a["mno"]), ("UDIN", a["udin"]),
            ("Place", a["city"]), ("Date", d(a["signed_date"]))], 110 * mm, 70 * mm, label_w=20 * mm, size=8.5, gap=5.2 * mm, value_w=70 * mm)
    _signature(c, 128 * mm, 76 * mm, seed=hash(a["partner"]) & 0xffff, w=30 * mm)
    _seal(c, 50 * mm, 52 * mm, "CHARTERED ACCOUNTANTS", a["frn"], "#2d4a22")
    _foot(c); c.save()
    return buf.getvalue()


# --------------------------------------------------------------------------- scan simulation

def to_scanned(pdf_bytes: bytes, seed: int, producer="CamScanner", dpi=150) -> bytes:
    """Rasterise + rotate + noise + JPEG: produces an image-only PDF that must go through OCR."""
    import numpy as np
    import pymupdf
    from PIL import Image, ImageFilter

    rnd = random.Random(seed)
    src = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    out = pymupdf.open()
    for p in src:
        pix = p.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72))
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        img = img.rotate(rnd.uniform(-0.7, 0.7), resample=Image.BICUBIC, expand=False, fillcolor=(250, 250, 248))
        arr = np.asarray(img).astype(np.int16)
        arr = arr + np.random.default_rng(seed).normal(0, 6, arr.shape).astype(np.int16)
        arr = (arr * 0.97 + 6).clip(0, 255).astype(np.uint8)
        img = Image.fromarray(arr).filter(ImageFilter.GaussianBlur(0.45))
        b = io.BytesIO(); img.save(b, format="JPEG", quality=72); b.seek(0)
        page = out.new_page(width=p.rect.width, height=p.rect.height)
        page.insert_image(page.rect, stream=b.getvalue())
    out.set_metadata({"producer": producer, "creator": producer})
    return out.tobytes(garbage=3, deflate=True)
