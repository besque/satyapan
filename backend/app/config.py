import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
MODELS = DATA / "models"          # local copy of the language model (downloaded once)
DB_PATH = Path(os.environ.get("SAMANVAY_DB", DATA / "samanvay.sqlite"))
SETTINGS_YAML = Path(__file__).resolve().parent / "settings.yaml"
EMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

for p in (DATA, MODELS):
    p.mkdir(parents=True, exist_ok=True)
