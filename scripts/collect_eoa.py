"""Collect real AICTE EoA letters published by institutions (Annexure-18 mandatory disclosure).

Every download is recorded in data/raw/eoa/manifest.json with source URL, timestamp and
SHA-256 so each record in the institutional ledger can be traced back to its public source.

Usage:  python scripts/collect_eoa.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "eoa"
MANIFEST = OUT / "manifest.json"

# Gathered via web search of institution websites (public mandatory disclosures).
URLS = """
https://ncr.christuniversity.in/uploads/cmsmenu/NCR EOA Report 2024-2025_20240711045830.PDF
https://ncr.christuniversity.in/uploads/cmsmenu/EOA Report 22 23_20220730122752.PDF
https://christuniversity.in/uploads/userfiles/file/2024-25(2).pdf
https://christuniversity.in/uploads/userfiles/Main EOA-Report-2023-24(1).pdf
https://christuniversity.in/uploads/userfiles/file/Corrigendum%20Report%2026-27%20LoA.PDF
https://demoweb.christuniversity.in/uploads/userfiles/Kengeri-2022-231.pdf
https://www.psgcas.ac.in/wp-content/uploads/2026/04/EOA-Report-2025-26.pdf
https://www.jaipuria.ac.in/wp-content/uploads/2025/06/AICTE-EOA-Report-2025-26.pdf
https://www.shobhituniversity.ac.in/pdf/AICTE_2025_26.PDF
https://crescent.education/wp-content/uploads/2025/05/AICTE-EOA-Report-2025-26.pdf
https://soe.cusat.ac.in/assets/files/aicte_eoa_letters/EOA%20Report%202025-26.PDF
https://soe.cusat.ac.in/assets/files/aicte_eoa_letters/EOA-Report%2022-23.PDF
https://soe.cusat.ac.in/assets/files/aicte_eoa_letters/EOA_Report_2026-2027.pdf
https://snu.edu.in/site/assets/files/16490/eoa_report_202526.pdf
https://snu.edu.in/site/assets/files/16490/eoa_report_20242025.pdf?v=2
https://ifheindia.org/assets/pdf/recognitions-accreditations/EOA-Report2025-26.PDF
https://www.nielit.gov.in/sites/default/files/Patna/EOA%20Report%202025-26.PDF
https://din.cusat.ac.in/uploads/downloads/EOA Report 2025-26-2_1743096371.PDF
https://din.cusat.ac.in/uploads/approvals/EOA-Report-2023-24.PDF
https://thapar.edu/upload/files/AICTE approval TIET 2025-26.PDF
https://portal.thapar.edu/upload/files/AICTE Approval 2024-2025 (TIET).pdf
https://portal.thapar.edu/upload/files/AICTE Approval -2023-24 (TIET).PDF
https://portal.thapar.edu/upload/files/AICTE approval 2024-2025 (LMTSM).pdf
https://www.thapar.edu/upload/files/EOA 2023-2024 LMTSM.pdf
https://thapar.edu/upload/files/AICTE Approval LMTSM 2025-26.PDF
https://liberalartsform.thapar.edu/upload/files/EOA Report 26-27 (LMTSM).PDF
https://drait.edu.in/assets/files/Admissions/EOA Report 2024-2025.PDF
https://www.itmgoi.in/IQAC/docs/Extra/EOA_Report_2024-2025.pdf
https://www.jiit.ac.in/uploads/AICTE_Approvals_98664c3743.pdf
https://www.pondiuni.edu.in/wp-content/uploads/2024/06/AICTE-EOAReport2024-2025.pdf
https://www.pondiuni.edu.in/wp-content/uploads/2023/07/EOA-REPORT-2023-24.pdf
https://cs.cusat.ac.in/assets/pdf-files/eoa-24-25.pdf
https://www.gitam.edu/sites/default/files/docs/accrediation/aicte-eoa_report_25-26_blr.pdf
https://onlineprograms.drmgrdu.ac.in/assets/pdf/UGC/AICTE-EoA.PDF
https://mjcollege.ac.in/documents/EOA-Report 2023-24.PDF
https://urise.up.gov.in/resources/profile_image/tu/1106_1702632620_AICTE_EOA_GPM_merged_compressed-compressed.pdf
https://doe.cusat.ac.in/EOA Report 2023-24.PDF
https://manuu.edu.in/sites/default/files/2026-07/5.%20EOA%20Report%202025-2026.PDF
https://www.polygwalior.ac.in/file/EOA/EOA_Report_2025-26.PDF
https://bengaluru.nmims.edu/docs/AICTE_EOA_2025-26.PDF
https://polytechnic.wbtetsd.gov.in/polytechnic/college/download_file/537de305e941fccdbba5627e3eefbb24
https://gptcpalakkad.ac.in/pdf_files/EOA_Report_2025_26.PDF
https://gpp.goa.gov.in/wp-content/uploads/2023/06/EOA-Report-2023-24.pdf
https://gpp.goa.gov.in/wp-content/uploads/2023/02/EOA-Report-2022-23.pdf
https://patnawomenscollege.in/wp-content/uploads/2026/07/EOA-Report-2026-27.pdf
https://cs.uok.edu.in/Files/79755f07-9550-4aeb-bd6f-5d802d56b46d/Custom/EOA%20Report%2026-27.PDF
https://www.rcet.org.in/uploads/files/AICTE/EOA-Report-2026-27.PDF
https://cvru.ac.in/PDFDoc/CvruApprovalLetters/AICTE_EoA26-27.PDF
https://www.claretcollege.edu.in/pdf/AICTE_EoA_2026_27.pdf
https://www.jagannath.org/images/EOA Report 2026-27.PDF
https://sjec.ac.in/storage/files/documents/dynamic-pages/accreditation/aicte/EOA_2026-27.pdf
https://www.mitmoradabad.edu.in/wp-content/uploads/2026/05/EOA-Report-2026-2027.pdf
https://hpuniv.ac.in/upload/6889dae7aa195EOA Report 2025-26 (1).pdf
https://methodist.edu.in/web/uploads/AQAR/EOA-Report-2025-2026.pdf
https://charusat.ac.in/depstar/files/AICTE EOA/EOA Report_2025-26.pdf
https://new.nism.ac.in/wp-content/uploads/2025/08/EOA-Report-2025-26.pdf
https://mitmeerut.ac.in/media_image/AICTE_Approval_All.pdf
https://siu.edu.in/uploads/images/67fe28dfa84fe1744709855.pdf
https://smvec.ac.in/wp-content/uploads/2026/06/EOA-Report-2025-26.pdf
https://dca.cusat.ac.in/assets/pdf/EOA2025-26.pdf
https://pcenagpur.edu.in/img_akki/aicte/2024-25-AICTE-Approval.pdf
https://urise.up.gov.in/resources/uploads/Circulars/1772441807EOA_Report_2025-26.PDF
https://vit.edu.in/wp-content/uploads/2026/01/EOA_VIT-2025-26-1.pdf
https://pmec.ac.in/wp-content/uploads/2025/06/EOA-Report-2025-2026.pdf
https://skcet.ac.in/wp-content/uploads/2025/06/EOA-Report-2025-2026.pdf
https://admission.smvdu.ac.in/wp-content/uploads/2025/06/EOA-Report-2025-2026-AICTE.pdf
https://makautwb.ac.in/approvals/EOA Report 2025-26.pdf
https://bietjhs.ac.in/public/uploads/2026/03/EOA-Report-2025-26_280326.PDF
https://nmcollege.in/docs/aicte-bms/EOA Report 2025-2026.PDF
https://staspta.cpas.ac.in/static/38/uploads/EOA_Report_2025-26_2.PDF
https://stasktm.cpas.ac.in/static/2/uploads/EOA_Report_2025-2026-1.pdf
https://biet.ac.in/pdfs/MANDATORY DISCLOSURES/AICTE_EOA_Report_2025-26.pdf
https://diet.edu.in/site_assets/pdf/AICTE_EOA_2025-2026.pdf
https://nnrg.edu.in/PDF/AICTE/AICTE_EOA 2025-26.PDF
https://kitsw.ac.in/homepage_pages/pdfs/EOA Report 2025-26.pdf
https://www.mvsrec.edu.in/images/AICTE/EOAs/EOA_Report_2025-2026.pdf
https://www.nrtec.in/wp-content/uploads/2025/09/Revised-EOA-Report-2025-26.pdf
https://www.dypcoeakurdi.ac.in/images/EOA_202425.pdf
https://gcoeara.ac.in/pdf/EOA Report 2024-25 to 2026-27.pdf
https://zcoer.in/wp-content/uploads/2025/03/AICTE-Approval-Letter-2024-25.pdf
https://avcoe.org/aicte/EOA Report 2024-2025_compressed.pdf
https://bschool.dpu.edu.in/assets/document/EOA/EOA-Report-2024-2025.PDF
https://mitaoe.ac.in/assets/images/pdf/EOA-2024-2025.pdf
https://1.pict.edu/pdf/footer/AICTE Approval 21 April 2025.pdf
https://www.sakec.ac.in/wp-content/uploads/2024/11/EOA-2024-25.pdf
https://www.ltce.in/assets/AICTE/EOA-2024-25.pdf
https://nec.edu.in/wp-content/uploads/2026/05/EOA-Report-26-27.pdf
https://www.psyec.edu.in//assets/img/AICTE/2025-26.pdf
https://skcet.ac.in/wp-content/uploads/2026/06/MBA-2025-2026.pdf
https://gcebargur.ac.in/sites/gcebargur.ac.in/files/GCEB%20AICTE%20EOA%20Report%2026-27.PDF
https://aucearni.in/UCE Arni - EOA Report 2025-2026.PDF
https://www.citchennai.edu.in/wp-content/uploads/2025/05/EOA-Report-2025-26.pdf
https://resources.itmuniversity.ac.in/newweb/approvals/new/AICTE Approval 2025-2026.PDF
https://resources.itmuniversity.ac.in/newweb/soet/pdf/AICTE-All Approvals.pdf
https://www.ajiet.edu.in/img/quick-links/AICTE_Approvals.pdf
https://nsec.ac.in/circular/EOA-Report-25-26MCA.PDF
https://xime.org/uploads/userfiles/EOA 2025-26_1-44646519474.pdf
https://bteup.ac.in/PDFFILES/NEWS_639005651817728160.pdf
https://jamiahamdard.ac.in/CDOE/pdf/AICTE Approval for BBA BCA.pdf
""".split("\n")


def normalise(url: str) -> str:
    parts = urlsplit(url.strip())
    path = quote(requests.utils.unquote(parts.path), safe="/()-_.~,")
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text("utf-8")) if MANIFEST.exists() else {}
    seen_urls = {v["source_url"] for v in manifest.values()}
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) research-prototype"
    ok = fail = 0
    for raw in URLS:
        if not raw.strip():
            continue
        url = normalise(raw)
        if url in seen_urls:
            continue
        try:
            r = session.get(url, timeout=60, verify=True)
        except requests.exceptions.SSLError:
            try:
                r = session.get(url, timeout=60, verify=False)
            except Exception as e:  # noqa: BLE001
                print(f"FAIL {url}: {e}", file=sys.stderr); fail += 1; continue
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {url}: {e}", file=sys.stderr); fail += 1; continue
        if r.status_code != 200 or not r.content.startswith(b"%PDF"):
            print(f"SKIP {r.status_code} {url}", file=sys.stderr); fail += 1; continue
        sha = hashlib.sha256(r.content).hexdigest()
        if sha in manifest:
            manifest[sha].setdefault("mirrors", []).append(url)
            continue
        host = re.sub(r"[^a-z0-9]+", "_", urlsplit(url).netloc.lower()).strip("_")
        name = f"{host}__{sha[:10]}.pdf"
        (OUT / name).write_bytes(r.content)
        manifest[sha] = {
            "file": name,
            "source_url": url,
            "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "bytes": len(r.content),
        }
        ok += 1
        print(f"OK   {name}")
        time.sleep(0.3)
    MANIFEST.write_text(json.dumps(manifest, indent=2), "utf-8")
    print(f"\ndownloaded={ok} failed={fail} total_in_manifest={len(manifest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
