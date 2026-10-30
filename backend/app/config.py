import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
REAL = DATA / "real"                 # real public data shipped with the repo (approval letters, handbook pages)
UPLOADS = DATA / "uploads"           # evidence uploaded by institutions
DB_PATH = Path(os.environ.get("APP_DB", DATA / "app.sqlite"))
SETTINGS_YAML = Path(__file__).resolve().parent / "settings.yaml"

# The product name lives in one file: brand.json at the repository root. Everything reads it from here.
BRAND = json.loads((ROOT / "brand.json").read_text(encoding="utf-8"))

for p in (DATA, UPLOADS):
    p.mkdir(parents=True, exist_ok=True)
