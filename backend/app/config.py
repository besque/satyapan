import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
RAW = DATA / "raw"
APH_PDF = RAW / "aph" / "APH_2024_27.pdf"
EOA_DIR = RAW / "eoa"
STORE = DATA / "store"          # uploaded documents, content-addressed by sha256
RENDER = DATA / "render"        # cached page renders
DB_PATH = Path(os.environ.get("SATYAPAN_DB", DATA / "satyapan.sqlite"))
SYNTH = DATA / "synthetic"
RULES_DIR = Path(__file__).resolve().parent / "rules"

for p in (STORE, RENDER, SYNTH):
    p.mkdir(parents=True, exist_ok=True)

RENDER_DPI = 110

ISSUERS_PATH = Path(os.environ.get("SATYAPAN_ISSUERS", DATA / "issuers.sqlite"))
