"""Plain-language titles shown when a check finds a problem (the rule titles describe what *should* be true)."""
from __future__ import annotations

PROBLEM = {
    "DOC-AFFIDAVIT": "Affidavit missing", "DOC-TER": "Fee receipt missing", "DOC-OC": "Occupancy certificate missing",
    "DOC-SSC": "Structural safety certificate missing", "DOC-FIRE": "Fire safety certificate missing", "DOC-MAP": "Location map missing",
    "DOC-AUDIT": "Audited accounts missing", "DOC-SLOT": "Wrong document uploaded",
    "VAL-FIRE": "Fire safety certificate has expired", "VAL-SSC": "Structural safety certificate is too old",
    "VAL-STAMP": "Stamp paper below Rs.100", "VAL-DSC": "Affidavit signature not valid",
    "VAL-OC-PARTIAL": "Partial occupancy certificate used too long",
    "XDOC-NAME-FIRE": "Fire certificate is in another name", "XDOC-NAME-OC": "Occupancy certificate is in another name",
    "XDOC-TRUST-OC": "Building is in another owner's name", "XDOC-AFF-APP": "Affidavit is for another application",
    "XDOC-TER-TXN": "Fee receipt is for another payment", "XDOC-AREA-OC": "Claimed area larger than certified",
    "XDOC-LATLON": "Map location does not match campus",
    "NORM-FSR": "Not enough faculty", "NORM-CADRE": "Too few professors / associate professors", "NORM-AREA": "Built-up area below requirement",
    "NORM-TER": "Fee under-paid", "NORM-PRINCIPAL": "No regular qualified principal",
    "LEDGER-INTAKE": "Intake above the approved intake", "LEDGER-IDENTITY": "Name differs from AICTE record",
    "DISC-ANNEX18": "Items missing from public disclosure",
    "FOR-REVISION": "Document edited after it was issued", "FOR-WHITEOUT": "Text covered and retyped",
    "FOR-OVERLAP": "Two values printed in the same place", "FOR-STRUCTURE": "File re-saved by a different program",
    "FOR-EDITOR": "Certificate re-saved with an editing program", "FOR-FONT": "Value typed in a different font",
    "FOR-GPS": "Photo taken far from the campus", "FOR-NOGPS": "Photo has no location", "FOR-PHOTOEDIT": "Photo edited",
    "VER-FIRE_NOC_REGISTRY": "Fire certificate does not match the fire department's record",
    "VER-OCCUPANCY_REGISTRY": "Occupancy certificate does not match the issuer's record",
    "VER-ESTAMP_REGISTRY": "e-Stamp paper does not match the stamp register",
    "VER-ICAI_UDIN": "Auditor's UDIN not found", "VER-ENGINEER_REGISTER": "Engineer not in the licence register",
    "VER-DIGITAL_SIGNATURE": "Signed document changed after signing", "VER-QR_PAYLOAD": "QR code does not match the printed number",
    "VER-AICTE_LEDGER": "Approval letter does not match AICTE record",
}
EXPIRED = {"VER-FIRE_NOC_REGISTRY": "Fire department's record shows the certificate expired"}


CHECK = {
    "XDOC-NAME-FIRE": "Check who the fire certificate is issued to", "XDOC-NAME-OC": "Check who the occupancy certificate is issued to",
    "XDOC-TRUST-OC": "Check the building owner's name", "VAL-FIRE": "Check the fire certificate's validity date",
    "VAL-SSC": "Check the structural certificate's date", "VAL-STAMP": "Check the stamp paper value", "NORM-TER": "Check the fee paid",
    "XDOC-AREA-OC": "Check the certified area", "LEDGER-INTAKE": "Check intake against AICTE record", "LEDGER-IDENTITY": "Check the institution's AICTE record",
    "XDOC-LATLON": "Check the map location", "VAL-OC-PARTIAL": "Partial occupancy certificate in use",
}


def title(f: dict) -> str:
    if f.get("status") == "pass" or f.get("kind") == "network":
        return f["title"]
    if f.get("status") in ("manual", "warn") and f.get("rule_id") in CHECK:
        return CHECK[f["rule_id"]]
    if f.get("rule_id") in EXPIRED and str(f.get("title", "")).startswith("Expired"):
        return EXPIRED[f["rule_id"]]
    return PROBLEM.get(f.get("rule_id"), f["title"])
